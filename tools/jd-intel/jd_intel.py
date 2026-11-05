"""career linkedin keywords - aggregate JD keywords across job snapshots.

    python3 jd_intel.py <job-snapshot-dir>... [--cv <cv-md-file>] [--json]
    python3 jd_intel.py --missing <cv-md-file> <jd-file | job-snapshot-dir>

Each snapshot dir must contain a job.json (schema li-scrape-job/1). Emits
keyword document-frequency across the corpus - unigrams plus bigrams that
repeat - and, when --cv is given, marks which keywords are missing from the
CV text (the RenderCV markdown, i.e. exactly what an ATS parser sees).
--missing is the single-posting form behind `career cv match`.

Only what a candidate could be asked to have is counted: EEO and legal
boilerplate, benefits and company-pitch sections, URLs and the posting's own
company and place names are dropped before tokenizing (see requirement_lines).
Stdlib only.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

TOKEN = re.compile(r"[a-z][a-z0-9.+/#&'-]{2,}")

# Function words + JD boilerplate that carries no matchable signal.
STOPWORDS = {
    "the", "and", "for", "you", "your", "our", "with", "will", "are", "have",
    "has", "this", "that", "not", "but", "all", "can", "who", "what", "when",
    "where", "how", "why", "their", "they", "them", "from", "into", "about",
    "across", "within", "including", "able", "well", "more", "most", "other",
    "such", "than", "then", "there", "these", "those", "was", "were", "been",
    "being", "its", "it's", "we're", "you'll", "you're", "per", "via", "etc",
    "role", "job", "work", "working", "team", "teams", "company", "companies",
    "candidate", "candidates", "experience", "years", "year", "skills",
    "ability", "strong", "excellent", "good", "great", "plus", "bonus",
    "required", "requirements", "requirement", "responsibilities",
    "responsibility", "preferred", "must", "should", "would", "looking",
    "join", "opportunity", "opportunities", "benefits", "salary", "based",
    "ideal", "successful", "day-to-day", "day", "days", "new", "help",
    "ensure", "using", "use", "also", "may", "any", "own", "out", "off",
    "while", "both", "meet", "best", "similar", "multiple", "additional",
    "proven", "aligned", "personal", "various", "high", "level", "under",
    "over", "each", "every", "least", "well-", "andor", "and/or",
}


def tokens(text):
    out = []
    for t in TOKEN.findall(str(text).lower()):
        # Trailing punctuation is never part of a keyword ("accountability."),
        # but a trailing + or # is ("c++", "c#").
        t = re.sub(r"[^a-z0-9+#]+$", "", t)
        if len(t) >= 3 and t not in STOPWORDS:
            out.append(t)
    return out


# --- what counts as a requirement ------------------------------------------
# A posting is mostly not requirements: the EEO statement, the legal notices,
# the benefits list and the company pitch all carry words ("california",
# "veteran", "ordinance") that no CV could or should answer.

URL = re.compile(r"(?:https?://|www\.)\S+|\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"
                 r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|ai|co|dev|gov)\b\S*",
                 re.I)

# Sentences that are legal or EEO text wherever they sit in the posting.
BOILERPLATE_LINE = re.compile(
    r"equal (employment )?opportunity|\beeo\b|affirmative action|regardless of"
    r"|sexual orientation|gender identity|protected (class|status|characteristic)"
    r"|\bveterans?\b|disabilit|reasonable accommodation|fair chance|\barrest"
    r"|\bconvictions?\b|criminal (history|record)|background (check|screen)"
    r"|e-?verify|privacy (policy|notice|statement)|data protection"
    r"|\bordinance\b|work authori[sz]ation|visa sponsorship",
    re.I)

# Headings that open a section nobody answers with a CV, and the headings that
# return to the part that matters. A section runs until the next recognised one.
DROP_HEADING = re.compile(
    r"benefit|perk|what we offer|compensation|salary|\bpay\b|equal opportunity"
    r"|\beeo\b|diversity|accommodation|privacy|legal|how we.?re different"
    r"|about (us|the company)|our (mission|values|culture)|why (join|work)",
    re.I)
KEEP_HEADING = re.compile(
    r"\brole\b|\bteam\b|\byou\b|responsibilit|requirement|qualification"
    r"|\bskills?\b|experience|nice to have|preferred|bonus|minimum|basic"
    r"|looking for|\bbring\b|impact|\bdo\b|\bwill\b|\bthrive\b",
    re.I)


def is_heading(line: str) -> bool:
    line = line.strip()
    if line.endswith(":"):
        return len(line) <= 120
    return len(line) <= 70 and len(line.split()) <= 10 and not line.endswith((".", ";", ","))


def requirement_lines(job: dict) -> list:
    """The posting's lines that can state a requirement, in order.

    Lines inside a benefits/EEO/company-pitch section, EEO and legal sentences
    wherever they sit, and section headings themselves are dropped. A posting
    with no recognisable headings is kept whole (minus the legal sentences).
    """
    company = str(job.get("company") or "").strip().lower()
    drop_company = (re.compile(r"^about\s+" + re.escape(company) + r"\b", re.I)
                    if company else None)
    desc = job.get("description") or []
    lines = [desc] if isinstance(desc, str) else list(desc)
    kept, dropping = [], False
    for raw in lines:
        line = str(raw).strip()
        if not line:
            continue
        if is_heading(line):
            if DROP_HEADING.search(line) or (drop_company and drop_company.match(line)):
                dropping = True
                continue
            if KEEP_HEADING.search(line):
                dropping = False
                continue
        if dropping or BOILERPLATE_LINE.search(line):
            continue
        kept.append(line)
    return kept


def requirement_text(job: dict) -> str:
    """Title plus the requirement lines, with URLs and emails removed."""
    return URL.sub(" ", " ".join(filter(None, [job.get("title") or ""]
                                        + requirement_lines(job))))


def requirement_tokens(job: dict) -> list:
    """Keyword tokens of the requirement text. The posting's own company and
    location words are not capabilities anyone could claim, so they go too."""
    about_them = set(tokens(" ".join(
        str(job.get(k) or "") for k in ("company", "location"))))
    return [t for t in tokens(requirement_text(job)) if t not in about_them]


def missing_from_cv(job: dict, cv_text: str) -> list:
    """Requirement keywords of one posting that the CV text lacks, sorted."""
    cv = cv_text.lower()
    return sorted({t for t in requirement_tokens(job) if t not in cv})


def load_job(snap: Path) -> dict | None:
    p = snap / "job.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def job_text(job: dict) -> str:
    # description is a list of lines in li-scrape-job/1, but a plain string
    # would otherwise be list()-ed into single characters and silently drop
    # every keyword - zero output, no error.
    desc = job.get("description") or []
    lines = [desc] if isinstance(desc, str) else list(desc)
    return " ".join(filter(None, [job.get("title") or ""] + lines))


def aggregate(jobs: list[dict], cv_text: str | None = None) -> dict:
    """Keyword document-frequency across jobs; bigrams kept when they repeat."""
    uni_df, bi_total = Counter(), Counter()
    for job in jobs:
        toks = requirement_tokens(job)
        uni_df.update(set(toks))
        bi_total.update(f"{a} {b}" for a, b in zip(toks, toks[1:]))
    terms = [{"term": t, "jobs": df} for t, df in uni_df.items()]
    terms += [{"term": t, "jobs": None, "count": c}
              for t, c in bi_total.items() if c >= 2]
    if cv_text is not None:
        cv = cv_text.lower()
        for t in terms:
            t["in_cv"] = all(w in cv for w in t["term"].split())
    terms.sort(key=lambda t: (-(t["jobs"] or 0), -(t.get("count") or 0), t["term"]))
    return {"jobs": len(jobs), "terms": terms}


def to_markdown(report: dict, sources: list[str]) -> str:
    out = [f"# JD keyword intel - {report['jobs']} job(s)", ""]
    out += [f"- source: `{s}`" for s in sources]
    out.append("")
    missing = [t for t in report["terms"] if t.get("in_cv") is False]
    if missing:
        out.append(f"## Missing from the CV ({len(missing)} - top 40 by frequency)")
        for t in missing[:40]:
            freq = f"{t['jobs']}/{report['jobs']} jobs" if t["jobs"] else f"x{t['count']}"
            out.append(f"- **{t['term']}** ({freq})")
        if len(missing) > 40:
            out.append(f"- ... {len(missing) - 40} more (use --json for all)")
        out.append("")
    out.append("## All keywords by frequency")
    for t in report["terms"][:60]:
        freq = f"{t['jobs']}/{report['jobs']} jobs" if t["jobs"] else f"x{t['count']}"
        mark = "" if t.get("in_cv") in (True, None) else "  <- missing from CV"
        out.append(f"- {t['term']} ({freq}){mark}")
    if len(report["terms"]) > 60:
        out.append(f"- ... {len(report['terms']) - 60} more (use --json for all)")
    return "\n".join(out)


def job_from_arg(arg: str) -> dict:
    """A job snapshot dir, or a plain-text JD file (one line per paragraph)."""
    p = Path(arg)
    if p.is_dir():
        job = load_job(p)
        if job is None:
            raise OSError(f"no job.json in: {p}")
        return job
    return {"description": p.read_text(encoding="utf-8").splitlines()}


def main_missing(argv):
    if len(argv) != 2:
        print("usage: jd_intel.py --missing <cv-md-file> <jd-file | job-snapshot-dir>",
              file=sys.stderr)
        return 2
    try:
        cv_text = Path(argv[0]).read_text(encoding="utf-8")
        job = job_from_arg(argv[1])
    except OSError as e:
        print(e, file=sys.stderr)
        return 1
    print("Keywords in JD not found in CV text:")
    for w in missing_from_cv(job, cv_text):
        print(f"  - {w}")
    return 0


def main(argv):
    if argv and argv[0] == "--missing":
        return main_missing(argv[1:])
    as_json = "--json" in argv
    argv = [x for x in argv if x != "--json"]
    cv_text = None
    if "--cv" in argv:
        i = argv.index("--cv")
        try:
            cv_text = Path(argv[i + 1]).read_text(encoding="utf-8")
        except (IndexError, OSError) as e:
            print(f"--cv: {e}", file=sys.stderr)
            return 2
        del argv[i:i + 2]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    snaps = [Path(a) for a in argv]
    jobs = []
    for s in snaps:
        job = load_job(s)
        if job is None:
            print(f"no job.json in: {s}", file=sys.stderr)
            return 1
        jobs.append(job)
    report = aggregate(jobs, cv_text)
    print(json.dumps(report) if as_json else to_markdown(report, [str(s) for s in snaps]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
