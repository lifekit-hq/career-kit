# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.40"]
# ///
"""li_scrape.py - free LinkedIn profile/job-post -> analyzable data. No paid API, no OCR.

Drives an already-authenticated Chrome over CDP, visits each profile section
(or a job post), and extracts the RENDERED TEXT from the DOM (exact - not
screenshots, not OCR). Screenshots are saved alongside only as a human-viewable
artifact / vision fallback. A best-effort structured parse is written too; for
a rich parse, hand `profile.raw.txt` to an LLM.

The pure text/URL helpers are plain functions covered by test_li_scrape.py;
the browser runner only executes under __main__.

One-time setup (headed Chrome you log into once):
    "$CHROME_BIN" --user-data-dir="$HOME/.cache/pw-li-profile" \
        --remote-debugging-port=9777 --no-first-run about:blank &
    # ...log into LinkedIn once; the session persists in the profile dir.

Usage:
    uv run li_scrape.py <profile-url-or-public-id> [outDir]
    uv run li_scrape.py <jobs-view-url-or-job-id>  [outDir]
"""
import json
import re
import sys
import time
from pathlib import Path

CDP_ENDPOINT = "http://127.0.0.1:9777"
SCHEMA_PROFILE = "li-scrape/1"
SCHEMA_JOB = "li-scrape-job/1"

# Profile sections to visit. '' is the top card + activity.
SECTIONS = ["", "details/experience", "details/education", "details/skills", "details/interests"]

# Lines that mark the end of a profile's own content on a details page.
SECTION_END_MARKERS = [
    "More profiles for you",
    "People you may know",
    "You might like",
    "Explore Premium profiles",
]

# Lines that mark the end of the job description block.
JOB_END_MARKERS = [
    "About the company",
    "Set alert for similar jobs",
    "How you match",
    "Benefits found from the job description",
]

# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------

def parse_public_id(value):
    """Public id from a profile URL, an `/in/<id>` fragment, or the bare id."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    s = re.split(r"[?#]", s)[0]
    s = s.rstrip("/")
    if "/in/" in s:
        s = s.split("/in/")[1]
    elif "linkedin.com" in s:
        return None  # a LinkedIn URL but not a profile
    return s.split("/")[0].strip() or None


def profile_base(public_id):
    return f"https://www.linkedin.com/in/{public_id}"


def section_url(public_id, section):
    base = profile_base(public_id)
    return f"{base}/{section}/" if section else f"{base}/"


def section_name(section):
    return section.split("/")[-1] if section else "profile"


def is_blocked_url(url):
    return isinstance(url, str) and bool(
        re.search(r"(authwall|/login|/checkpoint/|/uas/login)", url))


def out_dir_for(cwd, name, override=None):
    return str((Path(cwd) / override).resolve()) if override else str(Path(cwd) / f"out-{name}")


def normalize_lines(raw):
    """Trimmed non-empty lines, collapsing runs of the same line."""
    out = []
    for line in str(raw or "").split("\n"):
        t = line.strip()
        if t and (not out or out[-1] != t):
            out.append(t)
    return out


def slice_section(raw, heading, end_markers=SECTION_END_MARKERS):
    """Lines from `heading` (exclusive) to the first end marker (exclusive)."""
    lines = normalize_lines(raw)
    try:
        start = lines.index(heading) + 1
    except ValueError:
        start = 0
    end = len(lines)
    for i in range(start, len(lines)):
        if any(lines[i] == m or lines[i].startswith(m) for m in end_markers):
            end = i
            break
    return lines[start:end]


def split_company_type(line):
    parts = [p.strip() for p in str(line).split("·")]
    return {"company": parts[0] or None,
            "employmentType": parts[1] if len(parts) > 1 else None}


def split_location_arrangement(line):
    parts = [p.strip() for p in str(line).split("·")]
    arr = parts[-1] if len(parts) > 1 else None
    if arr and re.fullmatch(r"(Remote|Hybrid|On-site|Onsite)", arr, re.I):
        return {"location": " · ".join(parts[:-1]) or None, "arrangement": arr}
    return {"location": line.strip() or None, "arrangement": None}


DATE_LINE = re.compile(r"(present|\d{4}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.I)
DURATION_TAIL = re.compile(r"·\s*[^·]*\b(yr|yrs|mo|mos)\b[^·]*$", re.I)


def looks_like_date_line(line):
    return bool(DATE_LINE.search(line)) and bool(re.search(r"[-–—]|present", line, re.I))


def strip_duration(line):
    return DURATION_TAIL.sub("", str(line)).strip()


def parse_experience(raw):
    """Best-effort Experience parse; see test fixtures for the shape."""
    lines = slice_section(raw, "Experience")
    positions = []
    i = 0
    while i < len(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if nxt and "·" in nxt and not looks_like_date_line(nxt) and not looks_like_date_line(lines[i]):
            ct = split_company_type(nxt)
            pos = {"title": lines[i], "company": ct["company"],
                   "employmentType": ct["employmentType"], "dateRange": None,
                   "location": None, "arrangement": None, "description": []}
            j = i + 2
            if j < len(lines) and looks_like_date_line(lines[j]):
                pos["dateRange"] = strip_duration(lines[j])
                j += 1
            if (j < len(lines) and not looks_like_date_line(lines[j])
                    and not (j + 1 < len(lines) and "·" in lines[j + 1]
                             and not looks_like_date_line(lines[j + 1]))):
                la = split_location_arrangement(lines[j])
                pos["location"], pos["arrangement"] = la["location"], la["arrangement"]
                j += 1
            while j < len(lines):
                l = lines[j]
                peek = lines[j + 1] if j + 1 < len(lines) else None
                if peek and "·" in peek and not looks_like_date_line(peek):
                    break  # next entry
                if (re.search(r"\band \+\d+ skills?$", l) or re.fullmatch(r"…?\s*more", l, re.I)
                        or l == "Show translation"):
                    j += 1
                    continue
                pos["description"].append(l)
                j += 1
            positions.append(pos)
            i = j
        else:
            i += 1
    return positions


def parse_education(raw):
    """Best-effort Education parse: school / 'Degree, Field' / date range."""
    lines = slice_section(raw, "Education")
    edu = []
    i = 0
    while i < len(lines):
        detail = lines[i + 1] if i + 1 < len(lines) else None
        date = lines[i + 2] if i + 2 < len(lines) else None
        if (detail and date and looks_like_date_line(date)
                and not looks_like_date_line(lines[i]) and not looks_like_date_line(detail)):
            degree, _, rest = detail.partition(",")
            edu.append({
                "school": lines[i],
                "degree": degree.strip() if rest else None,
                "field": rest.strip() if rest else degree.strip(),
                "dateRange": strip_duration(date),
            })
            i += 3
        else:
            i += 1
    return edu


def parse_skills(raw):
    """Best-effort Skills parse -> [{name, endorsements}]."""
    lines = [l for l in slice_section(raw, "Skills") if l != "All"]
    skills = []

    def is_noise(l):
        return (re.search(r"\bendorsement", l, re.I) or l == "Endorsed"
                or " at " in l or l.startswith("Show"))

    for i, l in enumerate(lines):
        if is_noise(l):
            continue
        endorsements = 0
        for k in range(1, 4):
            if i + k < len(lines):
                m = re.search(r"(\d+)\s+endorsement", lines[i + k], re.I)
                if m:
                    endorsements = int(m.group(1))
                    break
        if not any(s["name"] == l for s in skills):
            skills.append({"name": l, "endorsements": endorsements})
    return skills


def extract_email(text):
    m = re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", str(text or ""), re.I)
    return m.group(0) if m else None


def parse_job_id(value):
    """Numeric job id from a /jobs/view/ URL or a bare id."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    s = re.split(r"[?#]", s)[0]
    if re.fullmatch(r"\d{6,}", s):
        return s
    m = re.search(r"/jobs/view/(\d+)", s)
    return m.group(1) if m else None


def job_url(job_id):
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def parse_job_text(raw):
    """Best-effort job-page parse.

    Anchors on the meta line ('Location · N days ago · M applicants'): the line
    before it is the title, the one before that the company. Description =
    lines after 'About the job' up to the first end marker.
    """
    lines = normalize_lines(raw)
    meta_idx = next((i for i, l in enumerate(lines)
                     if "·" in l and re.search(r"\bapplicants?\b|\bago\b", l, re.I)), -1)
    title = lines[meta_idx - 1] if meta_idx > 0 else None
    company = lines[meta_idx - 2] if meta_idx > 1 else None
    location = (lines[meta_idx].split("·")[0].strip() or None) if meta_idx >= 0 else None
    description = []
    try:
        start = lines.index("About the job") + 1
        end = len(lines)
        for i in range(start, len(lines)):
            if any(lines[i] == m or lines[i].startswith(m) for m in JOB_END_MARKERS):
                end = i
                break
        description = lines[start:end]
    except ValueError:
        pass
    return {"title": title, "company": company, "location": location,
            "description": description}


# ---------------------------------------------------------------------------
# Browser runner (only under __main__)
# ---------------------------------------------------------------------------

def _connect():
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    try:
        browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
    except Exception:
        print(f"Cannot reach Chrome at {CDP_ENDPOINT}. Start it and log into "
              "LinkedIn once (see header).", file=sys.stderr)
        raise SystemExit(1)
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "linkedin.com" in pg.url), None) or ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 1000})
    return p, browser, page


EXPAND_JS = """async () => {
  const a = document.querySelector('aside.msg-overlay-list-bubble, aside#msg-overlay');
  if (a) a.style.display = 'none';
  document.querySelectorAll('main button').forEach((b) => {
    if ((b.innerText || '').trim().toLowerCase().includes('see more')) b.click();
  });
  const s = document.scrollingElement;
  for (let y = 0; y < s.scrollHeight; y += 700) {
    s.scrollTop = y; await new Promise((r) => setTimeout(r, 150));
  }
  s.scrollTop = 0;
}"""

MAIN_TEXT_JS = "() => (document.querySelector('main') || document.body).innerText"


def _grab(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3.5)
    if is_blocked_url(page.url):
        print("\nNOT LOGGED IN - log into LinkedIn in the Chrome window first.",
              file=sys.stderr)
        raise SystemExit(2)
    page.evaluate(EXPAND_JS)
    time.sleep(0.8)
    return page.evaluate(MAIN_TEXT_JS)


def run_profile(public_id, out_dir):
    raw_dir = Path(out_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    p, browser, page = _connect()
    texts = {}
    for section in SECTIONS:
        name = section_name(section)
        print(f"  {name} … ", end="", file=sys.stderr, flush=True)
        txt = _grab(page, section_url(public_id, section))
        texts[name] = txt
        (raw_dir / f"{name}.txt").write_text(txt, encoding="utf-8")
        try:
            page.screenshot(path=str(raw_dir / f"{name}.png"), full_page=True)
        except Exception:
            pass
        print(f"{len(txt)} chars", file=sys.stderr)

    # Contact-info modal (email lives here, not on the section pages).
    contact_email = None
    try:
        print("  contact … ", end="", file=sys.stderr, flush=True)
        page.goto(profile_base(public_id) + "/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        page.evaluate("""() => {
          for (const el of document.querySelectorAll('a,button,span')) {
            const own = [...el.childNodes].filter((n) => n.nodeType === 3)
              .map((n) => n.textContent.trim()).join('');
            if (own === 'Contact info') { el.click(); return; }
          }
        }""")
        time.sleep(2)
        modal = page.evaluate("""() => {
          const m = document.querySelector('[role="dialog"], .artdeco-modal');
          return m ? m.innerText : null;
        }""")
        contact_email = extract_email(modal)
        if modal:
            (raw_dir / "contact.txt").write_text(modal, encoding="utf-8")
        page.keyboard.press("Escape")
        print(contact_email or "(none)", file=sys.stderr)
    except Exception as e:
        print(f"(skipped: {e})", file=sys.stderr)

    (Path(out_dir) / "profile.raw.txt").write_text(
        "\n".join(f"\n===== {k} =====\n{v}" for k, v in texts.items()), encoding="utf-8")
    structured = {
        "schema": SCHEMA_PROFILE,
        "publicId": public_id,
        "source": profile_base(public_id),
        "contact": {"email": contact_email},
        "positions": parse_experience(texts.get("experience", "")),
        "education": parse_education(texts.get("education", "")),
        "skills": parse_skills(texts.get("skills", "")),
    }
    (Path(out_dir) / "profile.json").write_text(
        json.dumps(structured, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nDone -> {out_dir}", file=sys.stderr)
    print("  raw/*.txt + raw/*.png per section, contact.txt", file=sys.stderr)
    print("  profile.json      (best-effort structured parse)", file=sys.stderr)
    print("  profile.raw.txt   (feed to an LLM for a rich parse)", file=sys.stderr)
    browser.close()
    p.stop()


def run_job(job_id, out_dir):
    raw_dir = Path(out_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    p, browser, page = _connect()
    print("  job … ", end="", file=sys.stderr, flush=True)
    txt = _grab(page, job_url(job_id))
    (raw_dir / "job.txt").write_text(txt, encoding="utf-8")
    try:
        page.screenshot(path=str(raw_dir / "job.png"), full_page=True)
    except Exception:
        pass
    print(f"{len(txt)} chars", file=sys.stderr)
    parsed = parse_job_text(txt)
    job = {"schema": SCHEMA_JOB, "jobId": job_id, "source": job_url(job_id), **parsed}
    (Path(out_dir) / "job.json").write_text(
        json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone -> {out_dir}", file=sys.stderr)
    print("  raw/job.txt + raw/job.png, job.json", file=sys.stderr)
    browser.close()
    p.stop()


def main(argv):
    if not argv:
        print("usage: uv run li_scrape.py <profile-url-or-id | jobs-view-url-or-job-id> [outDir]",
              file=sys.stderr)
        return 1
    target, override = argv[0], (argv[1] if len(argv) > 1 else None)
    job_id = parse_job_id(target) if ("/jobs/" in target or re.fullmatch(r"\d{6,}", target.strip())) else None
    if job_id:
        run_job(job_id, out_dir_for(Path.cwd(), f"job-{job_id}", override))
        return 0
    public_id = parse_public_id(target)
    if not public_id:
        print(f"could not parse a public id or job id from: {target}", file=sys.stderr)
        return 1
    run_profile(public_id, out_dir_for(Path.cwd(), public_id, override))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
