"""career jd add - snapshot a public job posting without LinkedIn.

    python3 jd_add.py <captures-dir> <url|file> [--company X] [--title Y]
                      [--location Z] [--id ID] [--source URL] [--json]

`career linkedin jd` needs the logged-in CDP Chrome. Ashby, Greenhouse and Lever
boards publish every posting through a public JSON API that needs neither, so a
posting on one of them is fetched from there:

    https://jobs.ashbyhq.com/<org>/<uuid>
    https://boards.greenhouse.io/<org>/jobs/<id>   (and job-boards.greenhouse.io)
    https://jobs.lever.co/<org>/<uuid>

A local text (or .html) file is wrapped as a snapshot too, for a posting that is
on none of those: it needs --company and --title, since a file does not say.

The result is the same `li-scrape-job/1` snapshot `linkedin jd` writes
(captures/<ISO>/ with job.json, raw/job.txt and a kind: job manifest), so
`cv letter`, `cv version`, `apply add` and `linkedin keywords` take it unchanged.
A URL snapshot also keeps the API payload as raw/api.json, the evidence the
parse came from. Stdlib only; read-only; it never logs in or posts anything.

Exit codes: 0 = ok, 1 = operational failure, 2 = usage error.
"""
import argparse
import datetime
import html
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

SCHEMA_JOB = "li-scrape-job/1"
TOOL = "career-jd-add"
TIMEOUT = 20
MAX_BYTES = 8 * 1024 * 1024

SLUG = r"[A-Za-z0-9][A-Za-z0-9._-]*"
UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
ASHBY = re.compile(rf"^https://jobs\.ashbyhq\.com/({SLUG})/({UUID})(?:/.*)?$")
GREENHOUSE = re.compile(
    rf"^https://(?:boards|job-boards)\.greenhouse\.io/({SLUG})/jobs/(\d+)(?:/.*)?$")
LEVER = re.compile(rf"^https://jobs\.lever\.co/({SLUG})/({UUID})(?:/.*)?$")

SUPPORTED = ("https://jobs.ashbyhq.com/<org>/<uuid>, "
             "https://boards.greenhouse.io/<org>/jobs/<id>, "
             "https://jobs.lever.co/<org>/<uuid>")


class Usage(Exception):
    """Bad arguments - exit 2."""


class Failure(Exception):
    """Could not do the work - exit 1."""


# --- HTML -> lines ---------------------------------------------------------

_BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
          "tr", "section", "article", "header", "footer", "table"}


class _Lines(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = [""]
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.parts.append("")

    def handle_data(self, data):
        if not self._skip:
            self.parts[-1] += data


def html_to_lines(markup: str) -> list:
    """Paragraphs and list items of an HTML fragment, one line each."""
    p = _Lines()
    p.feed(markup)
    p.close()
    return text_to_lines("\n".join(p.parts))


def text_to_lines(text: str) -> list:
    lines = (re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines())
    return [ln for ln in lines if ln]


# --- the three boards ------------------------------------------------------

def fetch_json(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": "career-kit-jd-add/1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise Failure(f"not found: {url} - the board no longer lists this "
                          "posting (closed, or the id is wrong)")
        raise Failure(f"{url}: HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Failure(f"could not reach {url}: {getattr(e, 'reason', e)}")
    if len(body) > MAX_BYTES:
        raise Failure(f"{url}: response is larger than {MAX_BYTES} bytes")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise Failure(f"{url}: the API did not answer with JSON")


def parse_url(url: str):
    """(board, org, posting id) for a supported posting URL, else None."""
    url = url.strip().split("#")[0].split("?")[0]
    for board, rx in (("ashby", ASHBY), ("greenhouse", GREENHOUSE), ("lever", LEVER)):
        m = rx.match(url)
        if m:
            return board, m.group(1), m.group(2).lower() if board != "greenhouse" else m.group(2)
    return None


def _title_case(slug: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_.]+", slug) if w)


def from_ashby(org, pid, fetch):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"
    payload = fetch(url)
    job = next((j for j in payload.get("jobs", []) if str(j.get("id", "")).lower() == pid), None)
    if job is None:
        raise Failure(f"ashby board {org!r} does not list posting {pid} - closed, or "
                      "the id is wrong")
    plain = job.get("descriptionPlain")
    lines = text_to_lines(plain) if plain else html_to_lines(job.get("descriptionHtml") or "")
    return {
        "jobId": f"ashby-{pid[:8]}", "title": job.get("title"),
        "company": _title_case(org), "location": job.get("location"),
        "source": job.get("jobUrl") or f"https://jobs.ashbyhq.com/{org}/{pid}",
        "description": lines, "raw": job,
    }


def from_greenhouse(org, pid, fetch):
    job = fetch(f"https://boards-api.greenhouse.io/v1/boards/{org}/jobs/{pid}")
    # `content` is HTML that was entity-escaped once more for transport.
    lines = html_to_lines(html.unescape(job.get("content") or ""))
    return {
        "jobId": str(job.get("id") or pid), "title": job.get("title"),
        "company": job.get("company_name") or _title_case(org),
        "location": (job.get("location") or {}).get("name"),
        "source": job.get("absolute_url") or f"https://boards.greenhouse.io/{org}/jobs/{pid}",
        "description": lines, "raw": job,
    }


def from_lever(org, pid, fetch):
    job = fetch(f"https://api.lever.co/v0/postings/{org}/{pid}")
    lines = text_to_lines(job.get("descriptionPlain") or "")
    for block in job.get("lists") or []:
        lines += text_to_lines(block.get("text") or "")
        lines += html_to_lines(block.get("content") or "")
    lines += text_to_lines(job.get("additionalPlain") or "")
    return {
        "jobId": f"lever-{pid[:8]}", "title": job.get("text"),
        "company": _title_case(org),
        "location": (job.get("categories") or {}).get("location"),
        "source": job.get("hostedUrl") or f"https://jobs.lever.co/{org}/{pid}",
        "description": lines, "raw": job,
    }


BOARDS = {"ashby": from_ashby, "greenhouse": from_greenhouse, "lever": from_lever}


def from_file(path: Path, args) -> dict:
    if not (args.company and args.title):
        raise Usage("a file does not say who posted what: pass --company and --title")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = (html_to_lines(text) if path.suffix.lower() in (".html", ".htm")
             else text_to_lines(text))
    return {"jobId": None, "title": None, "company": None, "location": None,
            "source": None, "description": lines, "raw": None}


# --- the snapshot ----------------------------------------------------------

def write_snapshot(captures: Path, job: dict, target: str, now: datetime.datetime) -> Path:
    stamp = now.replace(microsecond=0)
    while True:                                  # never reuse a snapshot dir
        snap = captures / stamp.strftime("%Y-%m-%dT%H-%M-%SZ")
        try:
            (snap / "raw").mkdir(parents=True)
            break
        except FileExistsError:
            stamp += datetime.timedelta(seconds=1)
    (snap / "raw" / "job.txt").write_text(
        f"{job['company']}\n\n{job['title']}\n\n{job['location'] or ''}\n\n"
        + "\n".join(job["description"]) + "\n", encoding="utf-8")
    if job.get("raw") is not None:
        (snap / "raw" / "api.json").write_text(
            json.dumps(job["raw"], indent=2, ensure_ascii=False), encoding="utf-8")
    record = {"schema": SCHEMA_JOB, "jobId": job["jobId"], "source": job["source"],
              "title": job["title"], "company": job["company"],
              "location": job["location"], "description": job["description"]}
    (snap / "job.json").write_text(
        json.dumps({k: v for k, v in record.items() if v not in (None, "")
                    or k in ("description",)}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    (snap / "manifest.json").write_text(json.dumps({
        "target": target, "captured_at": now.isoformat(), "tool": TOOL, "kind": "job",
        "pages": ["raw/job.txt"], "legacy": False}, indent=2), encoding="utf-8")
    return snap


def add(captures: Path, ref: str, args, fetch=fetch_json, now=None) -> dict:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    parsed = parse_url(ref) if re.match(r"https?://", ref) else None
    if parsed:
        board, org, pid = parsed
        job = BOARDS[board](org, pid, fetch)
    elif re.match(r"https?://", ref):
        raise Usage(f"not a supported posting URL: {ref}\nsupported: {SUPPORTED}\n"
                    "(a LinkedIn posting: career linkedin jd; any other posting: "
                    "save its text to a file and pass that)")
    else:
        path = Path(ref)
        if not path.is_file():
            raise Usage(f"neither a posting URL nor a file: {ref}\nsupported URLs: {SUPPORTED}")
        job = from_file(path, args)
    # Explicit flags win over what the board said: the board only knows its own slug.
    for key in ("company", "title", "location", "source"):
        if getattr(args, key, None):
            job[key] = getattr(args, key)
    if args.id:
        job["jobId"] = args.id
    if not job["title"] or not job["company"]:
        raise Failure("the posting has no title or company - pass --title/--company")
    if not job["description"]:
        raise Failure("the posting has an empty description - nothing to snapshot")
    snap = write_snapshot(captures, job, ref, now)
    return {"snapshot": str(snap), "jobId": job["jobId"], "title": job["title"],
            "company": job["company"], "location": job["location"],
            "source": job["source"], "lines": len(job["description"])}


def main(argv=None, fetch=fetch_json, now=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("captures")
    ap.add_argument("ref", metavar="url|file")
    for flag in ("company", "title", "location", "id", "source"):
        ap.add_argument(f"--{flag}")
    ap.add_argument("--json", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        out = add(Path(args.captures), args.ref, args, fetch, now)
    except Usage as e:
        print(e, file=sys.stderr)
        return 2
    except Failure as e:
        print(e, file=sys.stderr)
        return 1
    print(json.dumps(out) if args.json else f"→ {out['snapshot']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
