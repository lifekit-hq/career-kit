---
name: linkedin-scrape
description: >-
  Scrape a LinkedIn profile into analyzable data (rendered text + screenshots +
  structured JSON) for free — no paid API, no OCR. Use when Denys says "scrape
  this LinkedIn profile", "analyze this person's LinkedIn", "/linkedin-scrape
  <url>", pastes a linkedin.com/in/ URL and wants it parsed, or wants to research
  a person/candidate/recruiter behind a profile. Drives an already-logged-in
  Chrome over CDP and reads the DOM text — never the official API or the broken
  linkedin-api library.
---

# linkedin-scrape

Turn a `linkedin.com/in/<id>` profile into data you can analyze. The tool lives at
`tools/linkedin-scrape/` in this repo. **Extract exact rendered text from the DOM;
let the LLM (you) turn text → JSON. Never OCR the screenshots.**

## Why the other routes don't work (don't waste time re-discovering this)
- **Official LinkedIn API** — exposes only the *authenticated user's own* basics,
  never arbitrary member profiles. Dead end.
- **`linkedin-api` (OSS, tomquirk)** — latest release 2.3.1 is BROKEN: `get_profile`
  hits `/identity/profiles/{id}/profileView` → **HTTP 410 Gone**; skills/contact
  endpoints too. The newer `/identity/dash/profiles?...FullProfile` endpoint exists
  but needs rotating decorationIds + CSRF and trips anti-abuse (observed 200→401 on
  repeats). Not worth it.
- **Paid scrapers** (Apify, Bright Data) — work, cost money. Only suggest if Denys
  wants volume/hands-off.
- **Winner: logged-in browser + rendered DOM text.** Durable because LinkedIn keeps
  killing undocumented APIs and obfuscating markup, but the rendered text is stable.

## Prerequisites
- **A logged-in Chrome over CDP on port 9777.** The Playwright/Chrome-DevTools MCPs
  fail on this machine (they want Chrome at `/opt/google/chrome`, which needs sudo).
  The tool connects to this Chrome over CDP (Python `playwright`); the binary
  below is only needed to launch the browser itself:
  ```bash
  CHROME_BIN=$(find ~/.cache/puppeteer/chrome ~/.cache/ms-playwright -name chrome -type f 2>/dev/null | head -1)
  "$CHROME_BIN" --user-data-dir="$HOME/.cache/pw-li-profile" \
      --remote-debugging-port=9777 --no-first-run about:blank &
  ```
- **Denys logs into LinkedIn once** in that window; the session persists in the
  user-data dir. LinkedIn shows nothing useful anonymously (authwall).
- Nothing else: the tool is a `uv` script that declares its own `playwright`
  dependency (fetched on first run). No npm, no install step.

## Steps
1. **Ensure the browser is up and logged in.** If `connectOverCDP('http://127.0.0.1:9777')`
   fails, launch Chrome as above and ask Denys to log in. If a page lands on
   `authwall`/`login`, the session expired — ask him to log in again.
2. **Run the tool** - prefer the CLI so the capture lands in the dated store:
   ```bash
   bin/career linkedin capture <profile-url-or-id> -c <client>
   # or, standalone (ad-hoc target, e.g. researching a recruiter):
   uv run tools/linkedin-scrape/li_scrape.py <profile-url-or-id> [outDir]
   # job posts too:
   uv run tools/linkedin-scrape/li_scrape.py <jobs-view-url-or-job-id> [outDir]
   ```
   It visits profile + experience/education/skills/interests, saving
   `raw/<section>.txt` (parse source), `raw/<section>.png` (human artifact), and
   `profile.raw.txt` (concatenated). Job mode saves `raw/job.txt` + `job.json`.
3. **Contact info** (email) is behind a modal, not the section pages. If needed,
   click the "Contact info" link and read the `[role=dialog]` text separately.
4. **Parse text → JSON yourself.** Read `profile.raw.txt` and write clean structured
   JSON (basics, positions with normalized dates, education, skills+endorsements,
   interests, activity). This LLM pass is the robust parser — the tool's built-in
   `profile.json` is only a stub, because hardcoded DOM selectors break on LinkedIn's
   shifting obfuscated markup.
5. **Analyze / report** what Denys actually asked for (candidate fit, who the person
   is, red flags, etc.), citing the captured data.

## Rules
- **Privacy:** scraped output is third-party personal data. It goes under an
  ignored path (`tools/linkedin-scrape/out-*/` or `captures/`) — NEVER commit it.
  Only tool *code* is tracked. See `PRIVATE.md`.
- **Session tokens:** to reuse cookies with a library, export them to a local file
  and pass them through — never print `li_at`/`JSESSIONID` values to logs (the
  sandbox classifier blocks that, correctly). Delete any exported cookie file after.
- **Rate discipline:** human-paced, one profile at a time. It's Denys's account;
  bursts trip LinkedIn's anti-abuse guard and risk the account. Don't loop over many
  profiles; if he needs volume, point him at a paid scraper.
- **Don't OCR screenshots** — the DOM text is exact and free; pixels lose fidelity
  (esp. Cyrillic/emoji). Screenshots are a human artifact / vision fallback only.
