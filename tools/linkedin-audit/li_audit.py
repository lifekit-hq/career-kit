"""career linkedin audit - deterministic rubric over a LinkedIn profile snapshot.

    python3 li_audit.py <snapshot-dir> [--json] [--keywords <regex>]

--keywords overrides the role-keyword regex used by the headline and
pinned-skills checks (default targets SMM/marketing profiles).

Reads a capture-store snapshot (li-scrape layout or legacy flat layout, same
section mapping as tools/linkedin-diff) and scores it against a rubric of
code-checkable signals. Judgment calls (prose quality, positioning, honesty)
are deliberately NOT here - they belong to the LLM pass in the calling skill,
which takes this report as input. Stdlib only.

Statuses: pass/fail count toward the score; warn flags a likely problem;
info is a metric or note, never scored.
"""
import json
import re
import sys
from pathlib import Path

SECTION_FILES = {
    "profile":    ["raw/profile.txt", "profile_text.txt"],
    "experience": ["raw/experience.txt", "experience.txt"],
    "education":  ["raw/education.txt", "education.txt"],
    "skills":     ["raw/skills.txt", "skills.txt"],
    "interests":  ["raw/interests.txt", "interests.txt"],
}

DEFAULT_KEYWORDS = r"social media|content|marketing|smm|brand"
SMM_WORDS = re.compile(DEFAULT_KEYWORDS, re.I)  # rebound per-run by audit()
MARKETING_INTEREST = re.compile(r"marketing|media|advertis|canva|institute|creator", re.I)


def load(snap: Path) -> dict:
    sections = {}
    for name, candidates in SECTION_FILES.items():
        for rel in candidates:
            p = snap / rel
            if p.is_file():
                lines = [l.strip() for l in
                         p.read_text(encoding="utf-8", errors="replace").splitlines()
                         if l.strip()]
                sections[name] = lines
                break
    manifest = {}
    mp = snap / "manifest.json"
    if mp.is_file():
        try:
            manifest = json.loads(mp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    structured = {}
    for rel in ("profile.json", "profile_structured.json"):
        sp = snap / rel
        if sp.is_file():
            try:
                structured = json.loads(sp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
            break
    return {"sections": sections, "manifest": manifest, "structured": structured}


def _check_headline(s):
    top = s["sections"].get("profile", [])[:40]
    for line in top:
        if "|" in line and len(line.split()) >= 3 and SMM_WORDS.search(line):
            return "pass", f"headline-like line found: {line!r}"
        if "|" in line and len(line.split()) >= 3:
            return "warn", f"headline found but no role keywords: {line!r}"
    return "fail", "no 'A | B · C'-shaped headline line in the top card"


def _check_about(s):
    lines = s["sections"].get("profile", [])
    prose = [l for l in lines if len(l) > 80]
    if len(prose) >= 3:
        return "pass", f"{len(prose)} long prose lines - About present with substance"
    if prose:
        return "warn", "only a thin About-like block found"
    return "fail", "no About-like prose in the profile capture"


def _check_pinned_skills(s):
    lines = s["sections"].get("profile", [])
    for i, line in enumerate(lines):
        if line.lower() == "top skills" and i + 1 < len(lines):
            skills = [x.strip() for x in re.split(r"[•·]", lines[i + 1]) if x.strip()]
            if any(SMM_WORDS.search(x) for x in skills):
                return "pass", f"pinned: {', '.join(skills)}"
            return "warn", f"pinned skills lack role keywords: {', '.join(skills)}"
    return "fail", "no 'Top skills' block on the top card"


def _check_skill_count(s):
    lines = s["sections"].get("skills", [])
    m = None
    for line in lines:
        m = re.search(r"Skills \((\d+)\)", line) or m
    if m:
        n = int(m.group(1))
        return ("pass" if n >= 5 else "warn"), f"{n} skills listed"
    skills = s["structured"].get("skills")
    if isinstance(skills, list) and skills:
        n = len(skills)
        return ("pass" if n >= 5 else "warn"), f"{n} skills (from structured parse)"
    return "info", "skill count not detectable in capture"


def _check_experience_bullets(s):
    lines = s["sections"].get("experience", [])
    bullets = [l for l in lines if l.startswith(("-", "•"))]
    if len(bullets) >= 3:
        return "pass", f"{len(bullets)} bullet lines across roles"
    positions = s["structured"].get("positions")
    if isinstance(positions, list) and positions:
        described = sum(1 for p in positions if p.get("description"))
        if described == len(positions):
            return "pass", f"all {described} roles carry prose descriptions"
        if described:
            return "warn", f"{described}/{len(positions)} roles described"
    if bullets:
        return "warn", f"only {len(bullets)} bullet lines - roles thinly described"
    return "fail", "experience entries have no descriptions"


def _check_education(s):
    text = " ".join(s["sections"].get("education", []) + s["sections"].get("profile", []))
    if re.search(r"bachelor|master|university|degree|BA\b|BSc\b", text, re.I):
        return "pass", "education entry present"
    return "warn", "no education entry detected"


def _check_interests(s):
    lines = s["sections"].get("interests", [])
    hits = [l for l in lines if MARKETING_INTEREST.search(l) and "followers" not in l.lower()]
    companies = sum(1 for l in lines if l.endswith(", Company"))
    if hits:
        return "pass", f"{len(hits)} marketing-aligned interests (of ~{companies} companies followed)"
    if lines:
        return "warn", f"~{companies} companies followed, none marketing-aligned"
    return "info", "no interests section captured"


def _check_dash_hygiene(s):
    for name, lines in s["sections"].items():
        for line in lines:
            if "—" in line:
                return "warn", f"em dash in {name}: {line[:70]!r} (reads as AI slop - use '-')"
    return "pass", "no em dashes in captured text"


def _check_vanity_url(s):
    target = str(s["manifest"].get("target", ""))
    if re.search(r"-\d{4,}$", target):
        return "info", "auto-generated profile slug (vanity URL unclaimed - clickable links still work)"
    return "info", "custom/clean profile slug" if target else "target unknown"


def _check_followers(s):
    for line in s["sections"].get("profile", []):
        m = re.fullmatch(r"([\d,]+) followers", line)
        if m:
            return "info", f"{m.group(1)} followers"
    return "info", "follower count not detected"


def _check_open_to_work(s):
    text = " ".join(s["sections"].get("profile", []))
    if re.search(r"open to work", text, re.I):
        return "info", "'Open to work' visible on profile"
    return "info", "'Open to work' badge not visible in capture (may be recruiters-only)"


CHECKS = [
    ("headline", "Headline is role-shaped with keywords", _check_headline),
    ("about", "About section present with substance", _check_about),
    ("pinned_skills", "Top skills pinned with role keywords", _check_pinned_skills),
    ("skill_count", "At least 5 skills listed", _check_skill_count),
    ("experience_bullets", "Roles carry bullet descriptions", _check_experience_bullets),
    ("education", "Education entry present", _check_education),
    ("interests", "Marketing-aligned interests followed", _check_interests),
    ("dash_hygiene", "No em dashes in profile text", _check_dash_hygiene),
    ("vanity_url", "Profile URL slug", _check_vanity_url),
    ("followers", "Follower count", _check_followers),
    ("open_to_work", "Open-to-work visibility", _check_open_to_work),
]


def audit(snap: Path, keywords: str | None = None) -> dict:
    global SMM_WORDS
    SMM_WORDS = re.compile(keywords or DEFAULT_KEYWORDS, re.I)
    s = load(snap)
    results = []
    for cid, title, fn in CHECKS:
        status, detail = fn(s)
        results.append({"id": cid, "title": title, "status": status, "detail": detail})
    scored = [r for r in results if r["status"] in ("pass", "fail")]
    passed = sum(1 for r in scored if r["status"] == "pass")
    return {"snapshot": str(snap), "score": f"{passed}/{len(scored)}", "checks": results}


def to_markdown(report: dict) -> str:
    icon = {"pass": "✓", "fail": "✗", "warn": "!", "info": "·"}
    out = [f"# LinkedIn audit - `{report['snapshot']}`",
           f"Score: **{report['score']}** (pass/fail checks; warn/info unscored)", ""]
    for r in report["checks"]:
        out.append(f"- {icon[r['status']]} **{r['title']}** - {r['detail']}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    argv = [x for x in argv if x != "--json"]
    keywords = None
    if "--keywords" in argv:
        i = argv.index("--keywords")
        try:
            keywords = argv[i + 1]
        except IndexError:
            print("--keywords needs a regex", file=sys.stderr)
            return 2
        del argv[i:i + 2]
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    snap = Path(argv[0])
    if not snap.is_dir():
        print(f"not a snapshot dir: {snap}", file=sys.stderr)
        return 1
    report = audit(snap, keywords)
    print(json.dumps(report) if as_json else to_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
