"""career linkedin keywords - aggregate JD keywords across job snapshots.

    python3 jd_intel.py <job-snapshot-dir>... [--cv <cv-md-file>] [--json]

Each snapshot dir must contain a job.json (schema li-scrape-job/1). Emits
keyword document-frequency across the corpus - unigrams plus bigrams that
repeat - and, when --cv is given, marks which keywords are missing from the
CV text (the RenderCV markdown, i.e. exactly what an ATS parser sees).
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
        t = re.sub(r"[^a-z0-9]+$", "", t)  # strip trailing punctuation
        if len(t) >= 3 and t not in STOPWORDS:
            out.append(t)
    return out


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
        toks = tokens(job_text(job))
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


def main(argv):
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
