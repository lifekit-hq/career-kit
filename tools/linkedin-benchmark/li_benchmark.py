"""career linkedin benchmark - mine reference profiles into a target model.

    python3 li_benchmark.py <profile-snapshot-dir>... [--json]

Feed it li-scrape snapshots of people who HOLD the target role in the target
market; it aggregates what their profiles have in common - skill frequency,
headline keywords, headline shapes - to ground a rewrite in market data
instead of taste.

Reference captures are third-party data: keep them in ad-hoc gitignored
out-dirs, never inside a client dir, and respect the scraper's rate
discipline (a few profiles, human-paced). Stdlib only.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

TOKEN = re.compile(r"[a-z][a-z0-9.+/#&'-]{2,}")
STOPWORDS = {"and", "the", "for", "with", "your", "our", "into", "from", "who",
             "helping", "building", "driving", "passionate", "expert", "specialist"}


def headline_of(snap: Path) -> str | None:
    """First 'A | B'-shaped line near the top of the profile capture."""
    for rel in ("raw/profile.txt", "profile_text.txt"):
        p = snap / rel
        if p.is_file():
            lines = [l.strip() for l in p.read_text(encoding="utf-8", errors="replace")
                     .splitlines() if l.strip()][:40]
            for line in lines:
                if "|" in line and len(line.split()) >= 3:
                    return line
            return None
    return None


def skills_of(snap: Path) -> list[str]:
    for rel in ("profile.json", "profile_structured.json"):
        p = snap / rel
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
            skills = data.get("skills") or []
            return [s["name"] if isinstance(s, dict) else str(s) for s in skills]
    return []


def tokens(text):
    out = []
    for t in TOKEN.findall(str(text or "").lower()):
        t = re.sub(r"[^a-z0-9]+$", "", t)
        if len(t) >= 3 and t not in STOPWORDS:
            out.append(t)
    return out


def benchmark(snaps: list[Path]) -> dict:
    headlines, skill_df, kw_df = [], Counter(), Counter()
    for snap in snaps:
        h = headline_of(snap)
        if h:
            headlines.append(h)
            kw_df.update(set(tokens(h)))
        skill_df.update({s.strip().lower() for s in skills_of(snap) if s.strip()})
    n = len(snaps)
    return {
        "profiles": n,
        "headlines": headlines,
        "headline_keywords": [{"term": t, "profiles": c}
                              for t, c in kw_df.most_common()],
        "skills": [{"skill": s, "profiles": c} for s, c in skill_df.most_common(40)],
        "pipe_headline_share": round(sum("|" in h for h in headlines) / n, 2) if n else 0,
    }


def to_markdown(report: dict, sources: list[str]) -> str:
    n = report["profiles"]
    out = [f"# LinkedIn benchmark - {n} reference profile(s)", ""]
    out += [f"- source: `{s}`" for s in sources]
    out.append("")
    out.append("## Headlines observed")
    out += [f"- {h}" for h in report["headlines"]] or ["- (none detected)"]
    out.append(f"\n{int(report['pipe_headline_share'] * 100)}% use the 'A | B | C' shape.")
    out.append("\n## Headline keywords (by profile count)")
    for t in report["headline_keywords"][:20]:
        out.append(f"- {t['term']} ({t['profiles']}/{n})")
    out.append("\n## Skills (by profile count)")
    for s in report["skills"][:25]:
        out.append(f"- {s['skill']} ({s['profiles']}/{n})")
    return "\n".join(out)


def main(argv):
    as_json = "--json" in argv
    argv = [x for x in argv if x != "--json"]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    snaps = [Path(a) for a in argv]
    for s in snaps:
        if not s.is_dir():
            print(f"not a snapshot dir: {s}", file=sys.stderr)
            return 1
    report = benchmark(snaps)
    print(json.dumps(report) if as_json else to_markdown(report, [str(s) for s in snaps]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
