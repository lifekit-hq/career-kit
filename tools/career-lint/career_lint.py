"""career cv lint - cross-check the CV truth layer against the live LinkedIn.

    python3 career_lint.py <profile.yml> <profile-snapshot-dir>
                           [--variant <variant.yml>] [--json]

Recruiters cross-check the CV against LinkedIn; this makes that check a
mechanism. Compares the merged CV view (profile + optional variant, via
generate.merge - exactly what renders) against a capture-store profile
snapshot: headline equality, each role's title/company/start date, education.

Exit codes: 0 = clean, 1 = findings (any fail), 2 = usage/operational error.
"""
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from generate import merge  # noqa: E402  (the repo's own merge = what renders)

SECTION_FILES = {
    "profile":    ["raw/profile.txt", "profile_text.txt"],
    "experience": ["raw/experience.txt", "experience.txt"],
    "education":  ["raw/education.txt", "education.txt"],
}


def norm(s):
    """Lowercase, unify &/and, strip dots and extra spaces - for fuzzy contains."""
    s = str(s or "").lower().replace("&", "and").replace(".", "")
    return re.sub(r"\s+", " ", s).strip()


def load_snapshot(snap: Path) -> dict:
    texts = {}
    for name, candidates in SECTION_FILES.items():
        for rel in candidates:
            p = snap / rel
            if p.is_file():
                texts[name] = p.read_text(encoding="utf-8", errors="replace")
                break
    structured = {}
    for rel in ("profile.json", "profile_structured.json"):
        p = snap / rel
        if p.is_file():
            try:
                structured = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
            break
    return {"texts": texts, "structured": structured}


def _find_position(positions, role):
    """Match by company name or any lint_aliases entry (e.g. a Cyrillic
    company page name for a transliterated CV company)."""
    wants = [norm(role.get("company"))] + [norm(a) for a in role.get("lint_aliases", [])]
    for p in positions or []:
        have = norm(p.get("company"))
        if any(w and w in have for w in wants):
            return p
    return None


DEGREE_CLASS = [(r"\b(ba|bsc|bachelor)\b", "bachelor"), (r"\b(ma|msc|master)\b", "master"),
                (r"\bphd\b|doctor", "doctorate")]


def degree_class(s):
    n = norm(s)
    for pat, cls in DEGREE_CLASS:
        if re.search(pat, n):
            return cls
    return None


def lint(cfg: dict, snap: dict) -> list[dict]:
    findings = []

    def add(status, check, detail):
        findings.append({"status": status, "check": check, "detail": detail})

    all_text = norm(" ".join(snap["texts"].values()))

    headline = cfg.get("headline", "")
    if norm(headline) in norm(snap["texts"].get("profile", "")):
        add("pass", "headline", f"CV headline found on LinkedIn: {headline!r}")
    else:
        add("fail", "headline", f"CV headline not on LinkedIn: {headline!r}")

    positions = snap["structured"].get("positions")
    for role in cfg.get("experience", []):
        label = f"{role.get('title')} @ {role.get('company')}"
        pos = _find_position(positions, role)
        if pos is None:
            if norm(role.get("company")) in all_text:
                add("warn", f"role: {label}",
                    "company found in text but not in the structured parse - "
                    "title/date not verifiable")
            else:
                add("fail", f"role: {label}", "company not found on LinkedIn")
            continue
        if norm(pos.get("title")) == norm(role.get("title")):
            add("pass", f"role: {label}", "title matches")
        else:
            add("fail", f"role: {label}",
                f"title differs on LinkedIn: {pos.get('title')!r}")
        cv_start = norm(role.get("start"))
        li_range = norm(pos.get("dateRange"))
        if cv_start and li_range:
            if li_range.startswith(cv_start):
                add("pass", f"start date: {label}", f"{role.get('start')} matches")
            else:
                add("fail", f"start date: {label}",
                    f"CV says {role.get('start')!r}, LinkedIn says {pos.get('dateRange')!r}")
        else:
            add("warn", f"start date: {label}", "date not verifiable in the parse")

    for edu in cfg.get("education", []):
        school = edu.get("school", "")
        if norm(school) in all_text:
            add("pass", f"education: {school}", "school found on LinkedIn")
        else:
            add("fail", f"education: {school}", "school not found on LinkedIn")
        cv_cls = degree_class(edu.get("degree"))
        li_entries = snap["structured"].get("education") or []
        li_cls = next((degree_class(e.get("degree")) for e in li_entries
                       if norm(school) in norm(e.get("school"))), None)
        if cv_cls and li_cls and cv_cls != li_cls:
            add("fail", f"degree: {school}",
                f"CV degree class {cv_cls!r} vs LinkedIn {li_cls!r}")
        elif cv_cls and li_cls:
            add("pass", f"degree: {school}", f"degree class matches ({cv_cls})")
        field = edu.get("area", "")
        if field and norm(field) in all_text:
            add("pass", f"field: {school}", f"{field!r} found on LinkedIn")
        elif field:
            add("warn", f"field: {school}", f"{field!r} not found verbatim on LinkedIn")

    return findings


def to_markdown(findings, profile_path, snap_path):
    icon = {"pass": "✓", "fail": "✗", "warn": "!"}
    fails = sum(1 for f in findings if f["status"] == "fail")
    out = [f"# career lint - CV vs LinkedIn",
           f"- CV: `{profile_path}`", f"- snapshot: `{snap_path}`",
           f"- result: **{'CLEAN' if fails == 0 else f'{fails} MISMATCH(ES)'}**", ""]
    for f in findings:
        out.append(f"- {icon[f['status']]} **{f['check']}** - {f['detail']}")
    return "\n".join(out)


def main(argv):
    as_json = "--json" in argv
    argv = [x for x in argv if x != "--json"]
    variant = {}
    if "--variant" in argv:
        i = argv.index("--variant")
        try:
            variant = yaml.safe_load(Path(argv[i + 1]).read_text(encoding="utf-8")) or {}
        except (IndexError, OSError) as e:
            print(f"--variant: {e}", file=sys.stderr)
            return 2
        del argv[i:i + 2]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    profile_path, snap_path = Path(argv[0]), Path(argv[1])
    if not profile_path.is_file() or not snap_path.is_dir():
        print(f"bad inputs: {profile_path} / {snap_path}", file=sys.stderr)
        return 2
    cfg = merge(yaml.safe_load(profile_path.read_text(encoding="utf-8")), variant)
    findings = lint(cfg, load_snapshot(snap_path))
    fails = sum(1 for f in findings if f["status"] == "fail")
    if as_json:
        print(json.dumps({"cv": str(profile_path), "snapshot": str(snap_path),
                          "failed": fails, "findings": findings}))
    else:
        print(to_markdown(findings, profile_path, snap_path))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
