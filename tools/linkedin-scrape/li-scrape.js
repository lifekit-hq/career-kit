#!/usr/bin/env node
/**
 * li-scrape.js — free LinkedIn profile -> analyzable data. No paid API, no OCR.
 *
 * Drives an already-authenticated Chrome over CDP, visits each profile section,
 * and extracts the RENDERED TEXT from the DOM (exact — not screenshots, not OCR).
 * Screenshots are saved alongside only as a human-viewable artifact / vision
 * fallback. A best-effort structured parse of the rendered text is written too;
 * for a rich parse, hand `profile.raw.txt` to an LLM.
 *
 * The pure text/URL helpers are exported for unit testing; the browser runner
 * only executes when this file is run directly (see the bottom of the file).
 *
 * One-time setup (headed Chrome you log into once):
 *   "$CHROME_BIN" --user-data-dir="$HOME/.cache/pw-li-profile" \
 *       --remote-debugging-port=9777 --no-first-run about:blank &
 *   # ...log into LinkedIn once; the session persists in the profile dir.
 *
 * Usage:
 *   CHROME_BIN=/path/to/chrome node li-scrape.js <profile-url-or-public-id> [outDir]
 */
'use strict';

const CDP_ENDPOINT = 'http://127.0.0.1:9777';

/** Profile sections to visit. '' is the top card + activity. */
const SECTIONS = ['', 'details/experience', 'details/education', 'details/skills', 'details/interests'];

/** Lines that mark the end of a profile's own content on a details page. */
const SECTION_END_MARKERS = [
  'More profiles for you',
  'People you may know',
  'You might like',
  'Explore Premium profiles',
];

// ---------------------------------------------------------------------------
// Pure helpers (exported, unit-tested)
// ---------------------------------------------------------------------------

/**
 * Extract the public id from a profile URL or a bare id.
 * Accepts full URLs (any section/query/trailing slash), `/in/<id>` fragments,
 * or the bare id itself. Returns null if nothing usable is found.
 */
function parsePublicId(input) {
  if (typeof input !== 'string') return null;
  let s = input.trim();
  if (!s) return null;
  s = s.split(/[?#]/)[0];           // drop query/hash
  s = s.replace(/\/+$/, '');        // drop trailing slashes
  if (s.includes('/in/')) s = s.split('/in/')[1];
  else if (s.includes('linkedin.com')) return null; // a LinkedIn URL but not a profile
  const id = s.split('/')[0].trim();
  return id || null;
}

/** Canonical profile base URL for a public id. */
function profileBase(publicId) {
  return `https://www.linkedin.com/in/${publicId}`;
}

/** URL for a given section ('' = top card). */
function sectionUrl(publicId, section) {
  const base = profileBase(publicId);
  return section ? `${base}/${section}/` : `${base}/`;
}

/** Short filesystem-safe name for a section ('' -> 'profile'). */
function sectionName(section) {
  return section ? section.split('/').pop() : 'profile';
}

/** True if a URL indicates we are logged out / gated. */
function isBlockedUrl(url) {
  return typeof url === 'string' && /(authwall|\/login|\/checkpoint\/|\/uas\/login)/.test(url);
}

/** Resolve the output directory for a run. */
function outDirFor(cwd, publicId, override) {
  const path = require('path');
  return override ? path.resolve(cwd, override) : path.join(cwd, `out-${publicId}`);
}

/**
 * Split raw innerText into trimmed non-empty lines, collapsing runs of the same
 * line (LinkedIn renders a visible + a visually-hidden copy of most text).
 */
function normalizeLines(raw) {
  const out = [];
  for (const line of String(raw || '').split('\n')) {
    const t = line.trim();
    if (!t) continue;
    if (out[out.length - 1] !== t) out.push(t);
  }
  return out;
}

/**
 * Return the lines of one section: from the line equal to `heading` up to the
 * first end-marker (exclusive). If the heading is absent, returns all lines
 * (already normalized), so callers still get something to work with.
 */
function sliceSection(raw, heading, endMarkers = SECTION_END_MARKERS) {
  const lines = normalizeLines(raw);
  let start = lines.findIndex((l) => l === heading);
  start = start === -1 ? 0 : start + 1;
  let end = lines.length;
  for (let i = start; i < lines.length; i++) {
    if (endMarkers.some((m) => lines[i] === m || lines[i].startsWith(m))) { end = i; break; }
  }
  return lines.slice(start, end);
}

/** Parse a "Company · Full-time" style line into {company, employmentType}. */
function splitCompanyType(line) {
  const parts = String(line).split('·').map((s) => s.trim());
  return { company: parts[0] || null, employmentType: parts[1] || null };
}

/** Parse a "Location · Remote" style line into {location, arrangement}. */
function splitLocationArrangement(line) {
  const parts = String(line).split('·').map((s) => s.trim());
  const arr = parts.length > 1 ? parts[parts.length - 1] : null;
  const known = /^(Remote|Hybrid|On-site|Onsite)$/i;
  if (arr && known.test(arr)) {
    return { location: parts.slice(0, -1).join(' · ') || null, arrangement: arr };
  }
  return { location: line.trim() || null, arrangement: null };
}

const DATE_LINE = /(present|\d{4}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i;
const DURATION_TAIL = /·\s*[^·]*\b(yr|yrs|mo|mos)\b[^·]*$/i;

/** True if a line looks like a LinkedIn date range ("Apr 2026 - Present · 5 mos"). */
function looksLikeDateLine(line) {
  return DATE_LINE.test(line) && /[-–—]|present/i.test(line);
}

/** Strip the "· 5 mos" duration tail from a date line. */
function stripDuration(line) {
  return String(line).replace(DURATION_TAIL, '').trim();
}

/**
 * Best-effort parse of the Experience details text into position records.
 * Heuristic: an entry is a title line immediately followed by a "Company · Type"
 * line; the next date line and location line are attached; remaining lines up to
 * the next entry (or a "…skills" trailer) become the description.
 */
function parseExperience(raw) {
  const lines = sliceSection(raw, 'Experience');
  const positions = [];
  for (let i = 0; i < lines.length; i++) {
    const next = lines[i + 1];
    if (next && next.includes('·') && !looksLikeDateLine(next) && !looksLikeDateLine(lines[i])) {
      const { company, employmentType } = splitCompanyType(next);
      const pos = { title: lines[i], company, employmentType, dateRange: null, location: null, arrangement: null, description: [] };
      let j = i + 2;
      if (lines[j] && looksLikeDateLine(lines[j])) { pos.dateRange = stripDuration(lines[j]); j++; }
      if (lines[j] && !looksLikeDateLine(lines[j]) && !(lines[j + 1] && lines[j + 1].includes('·') && !looksLikeDateLine(lines[j + 1]))) {
        const { location, arrangement } = splitLocationArrangement(lines[j]);
        pos.location = location; pos.arrangement = arrangement; j++;
      }
      while (j < lines.length) {
        const l = lines[j];
        const peek = lines[j + 1];
        if (peek && peek.includes('·') && !looksLikeDateLine(peek)) break; // next entry
        if (/\band \+\d+ skills?$/.test(l) || /^…?\s*more$/i.test(l) || l === 'Show translation') { j++; continue; }
        pos.description.push(l);
        j++;
      }
      positions.push(pos);
      i = j - 1;
    }
  }
  return positions;
}

/**
 * Best-effort parse of Education details text.
 * Entry shape: school / "Degree, Field" / date range.
 */
function parseEducation(raw) {
  const lines = sliceSection(raw, 'Education');
  const edu = [];
  for (let i = 0; i < lines.length; i++) {
    const detail = lines[i + 1];
    const date = lines[i + 2];
    if (detail && date && looksLikeDateLine(date) && !looksLikeDateLine(lines[i]) && !looksLikeDateLine(detail)) {
      const [degree, ...rest] = detail.split(',');
      edu.push({
        school: lines[i],
        degree: rest.length ? degree.trim() : null,
        field: rest.length ? rest.join(',').trim() : degree.trim(),
        dateRange: stripDuration(date),
      });
      i += 2;
    }
  }
  return edu;
}

/**
 * Best-effort parse of Skills details text -> [{name, endorsements}].
 * A skill is a line whose following lines may include "N endorsement(s)".
 * Lines that are sub-labels ("... at Company", "Endorsed") are skipped.
 */
function parseSkills(raw) {
  const lines = sliceSection(raw, 'Skills').filter((l) => l !== 'All');
  const skills = [];
  const isNoise = (l) => /\bendorsement/i.test(l) || l === 'Endorsed' || / at /.test(l) || /^Show/.test(l);
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (isNoise(l)) continue;
    // look ahead for an endorsement count within the next 3 lines
    let endorsements = 0;
    for (let k = 1; k <= 3 && lines[i + k]; k++) {
      const m = lines[i + k].match(/(\d+)\s+endorsement/i);
      if (m) { endorsements = Number(m[1]); break; }
    }
    if (!skills.some((s) => s.name === l)) skills.push({ name: l, endorsements });
  }
  return skills;
}

/** Pull the first email address out of contact-modal text, or null. */
function extractEmail(text) {
  const m = String(text || '').match(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i);
  return m ? m[0] : null;
}

const helpers = {
  CDP_ENDPOINT, SECTIONS, SECTION_END_MARKERS,
  parsePublicId, profileBase, sectionUrl, sectionName, isBlockedUrl, outDirFor,
  normalizeLines, sliceSection, splitCompanyType, splitLocationArrangement,
  looksLikeDateLine, stripDuration, parseExperience, parseEducation, parseSkills,
  extractEmail,
};

module.exports = helpers;

// ---------------------------------------------------------------------------
// Browser runner (only when executed directly)
// ---------------------------------------------------------------------------

async function run() {
  const fs = require('fs');
  const path = require('path');
  const { chromium } = require('playwright-core');

  const arg = process.argv[2];
  if (!arg) { console.error('usage: node li-scrape.js <profile-url-or-public-id> [outDir]'); process.exit(1); }
  const publicId = parsePublicId(arg);
  if (!publicId) { console.error(`could not parse a public id from: ${arg}`); process.exit(1); }

  const outDir = outDirFor(process.cwd(), publicId, process.argv[3]);
  const rawDir = path.join(outDir, 'raw');
  fs.mkdirSync(rawDir, { recursive: true });

  const browser = await chromium.connectOverCDP(CDP_ENDPOINT).catch(() => {
    console.error(`Cannot reach Chrome at ${CDP_ENDPOINT}. Start it and log into LinkedIn once (see header).`);
    process.exit(1);
  });
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => p.url().includes('linkedin.com')) || (await ctx.newPage());
  await page.setViewportSize({ width: 1440, height: 1000 });

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const texts = {};

  for (const section of SECTIONS) {
    const name = sectionName(section);
    process.stderr.write(`  ${name} … `);
    await page.goto(sectionUrl(publicId, section), { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(3500);
    if (isBlockedUrl(page.url())) { console.error('\nNOT LOGGED IN — log into LinkedIn in the Chrome window first.'); process.exit(2); }
    await page.evaluate(async () => {
      const a = document.querySelector('aside.msg-overlay-list-bubble, aside#msg-overlay'); if (a) a.style.display = 'none';
      document.querySelectorAll('main button').forEach((b) => { if ((b.innerText || '').trim().toLowerCase().includes('see more')) b.click(); });
      const s = document.scrollingElement;
      for (let y = 0; y < s.scrollHeight; y += 700) { s.scrollTop = y; await new Promise((r) => setTimeout(r, 150)); }
      s.scrollTop = 0;
    });
    await sleep(800);
    const txt = await page.evaluate(() => (document.querySelector('main') || document.body).innerText);
    texts[name] = txt;
    fs.writeFileSync(path.join(rawDir, `${name}.txt`), txt);
    await page.screenshot({ path: path.join(rawDir, `${name}.png`), fullPage: true }).catch(() => {});
    console.error(`${txt.length} chars`);
  }

  // Contact-info modal (email lives here, not on the section pages).
  let contact = { email: null, raw: null };
  try {
    process.stderr.write('  contact … ');
    await page.goto(profileBase(publicId) + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await sleep(3000);
    await page.evaluate(() => {
      for (const el of document.querySelectorAll('a,button,span')) {
        const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
        if (own === 'Contact info') { el.click(); return; }
      }
    });
    await sleep(2000);
    const modal = await page.evaluate(() => {
      const m = document.querySelector('[role="dialog"], .artdeco-modal');
      return m ? m.innerText : null;
    });
    contact = { email: extractEmail(modal), raw: modal };
    if (modal) fs.writeFileSync(path.join(rawDir, 'contact.txt'), modal);
    await page.keyboard.press('Escape').catch(() => {});
    console.error(contact.email || '(none)');
  } catch (e) { console.error('(skipped:', e.message + ')'); }

  // Concatenated raw text for the LLM parse pass.
  fs.writeFileSync(path.join(outDir, 'profile.raw.txt'),
    Object.entries(texts).map(([k, v]) => `\n===== ${k} =====\n${v}`).join('\n'));

  // Best-effort structured parse.
  const structured = {
    publicId,
    source: profileBase(publicId),
    contact: { email: contact.email },
    positions: parseExperience(texts.experience || ''),
    education: parseEducation(texts.education || ''),
    skills: parseSkills(texts.skills || ''),
  };
  fs.writeFileSync(path.join(outDir, 'profile.json'), JSON.stringify(structured, null, 2));

  console.error(`\nDone -> ${outDir}`);
  console.error('  raw/*.txt + raw/*.png per section, contact.txt');
  console.error('  profile.json      (best-effort structured parse)');
  console.error('  profile.raw.txt   (feed to an LLM for a rich parse)');
  await browser.close(); // detaches CDP only; Chrome keeps running
}

if (require.main === module) {
  run().catch((e) => { console.error('ERR:', e.message); process.exit(1); });
}
