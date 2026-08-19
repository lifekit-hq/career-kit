"""career linkedin diff - compare two LinkedIn profile snapshots.

    python3 li_diff.py <snapA> <snapB> [--json]

A snapshot is a capture-store dir (see docs/CONTRACT.md): either the
li-scrape layout (raw/<section>.txt + profile.json) or the legacy flat
layout (profile_text.txt, experience.txt, ... + profile_structured.json).

Design note: same-layout snapshots cancel LinkedIn chrome (nav, footers) via
set difference alone; the chrome stoplist below only exists so legacy-vs-new
comparisons stay clean too (the old hand-scrapes included page chrome the
tool strips). Stdlib only.
"""
import json
import re
import sys
from pathlib import Path

# LinkedIn page chrome: never profile content, safe to drop before diffing.
CHROME_EXACT = {
    "Home", "My Network", "Jobs", "Messaging", "Notifications", "Me",
    "For Business", "About", "Accessibility", "Talent Solutions",
    "Community Guidelines", "Careers", "Marketing Solutions", "Privacy & Terms",
    "Ad Choices", "Advertising", "Sales Solutions", "Mobile", "Small Business",
    "Safety Center", "Questions?", "Visit our Help Center.",
    "Manage your account and privacy", "Go to your Settings.",
    "Recommendation transparency", "Learn more about Recommended Content.",
    "Select language", "Keyboard shortcuts", "Close jump menu",
    "new feed updates notifications",
}
CHROME_RE = re.compile(
    r"^(Skip to |\d+ notifications|Reactivate Premium|LinkedIn Corporation ©)"
    r"|\((Arabic|Bangla|Czech|Danish|German|Greek|English|Spanish|Persian|"
    r"Finnish|French|Hindi|Hungarian|Indonesian|Italian|Hebrew|Japanese|"
    r"Korean|Marathi|Malay|Dutch|Norwegian|Punjabi|Polish|Portuguese|"
    r"Romanian|Russian|Swedish|Telugu|Thai|Tagalog|Turkish|Ukrainian|"
    r"Vietnamese|Chinese \((Simplified|Traditional)\))\)$")


def is_chrome(line: str) -> bool:
    return line in CHROME_EXACT or bool(CHROME_RE.search(line))

# section name -> candidate files, first hit wins (new layout, then legacy)
SECTION_FILES = {
    "profile":    ["raw/profile.txt", "profile_text.txt"],
    "experience": ["raw/experience.txt", "experience.txt"],
    "education":  ["raw/education.txt", "education.txt"],
    "skills":     ["raw/skills.txt", "skills.txt"],
    "interests":  ["raw/interests.txt", "interests.txt"],
    "activity":   ["raw/activity.txt", "activity.txt"],
}
STRUCTURED_FILES = ["profile.json", "profile_structured.json"]


def _lines(path: Path) -> list[str]:
    seen, out = set(), []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and line not in seen and not is_chrome(line):
            seen.add(line)
            out.append(line)
    return out


def load_snapshot(snap: Path) -> dict:
    sections = {}
    for name, candidates in SECTION_FILES.items():
        for rel in candidates:
            p = snap / rel
            if p.is_file():
                sections[name] = _lines(p)
                break
    structured = None
    for rel in STRUCTURED_FILES:
        p = snap / rel
        if p.is_file():
            try:
                structured = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
            break
    return {"sections": sections, "structured": structured}


def _flatten(obj, prefix="") -> dict:
    """Nested dict/list -> {dotted.path: scalar}."""
    flat = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            flat.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flat.update(_flatten(v, f"{prefix}{i}."))
    else:
        flat[prefix[:-1]] = obj
    return flat


def diff_snapshots(a: dict, b: dict) -> dict:
    sections = {}
    for name in SECTION_FILES:
        la, lb = a["sections"].get(name), b["sections"].get(name)
        if la is None and lb is None:
            continue
        if la is None or lb is None:
            sections[name] = {"only_in": "b" if la is None else "a",
                              "added": lb or [], "removed": la or []}
            continue
        sa, sb = set(la), set(lb)
        added = [l for l in lb if l not in sa]
        removed = [l for l in la if l not in sb]
        if added or removed:
            sections[name] = {"added": added, "removed": removed}

    fields = {}
    if a["structured"] is not None and b["structured"] is not None:
        fa, fb = _flatten(a["structured"]), _flatten(b["structured"])
        for path in sorted(fa.keys() | fb.keys()):
            va, vb = fa.get(path), fb.get(path)
            if va != vb:
                fields[path] = {"a": va, "b": vb}
    return {"sections": sections, "fields": fields}


def to_markdown(diff: dict, a: str, b: str) -> str:
    out = [f"# LinkedIn snapshot diff", f"- A (old): `{a}`", f"- B (new): `{b}`", ""]
    if not diff["sections"] and not diff["fields"]:
        out.append("No changes detected.")
        return "\n".join(out)
    for name, d in diff["sections"].items():
        out.append(f"## {name}")
        if d.get("only_in"):
            out.append(f"*section present only in snapshot {d['only_in'].upper()}*")
        for l in d["added"]:
            out.append(f"+ {l}")
        for l in d["removed"]:
            out.append(f"- {l}")
        out.append("")
    if diff["fields"]:
        out.append("## structured fields")
        for path, ch in diff["fields"].items():
            out.append(f"- `{path}`: {ch['a']!r} -> {ch['b']!r}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    argv = [x for x in argv if x != "--json"]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    a_dir, b_dir = Path(argv[0]), Path(argv[1])
    for d in (a_dir, b_dir):
        if not d.is_dir():
            print(f"not a snapshot dir: {d}", file=sys.stderr)
            return 1
    diff = diff_snapshots(load_snapshot(a_dir), load_snapshot(b_dir))
    if as_json:
        print(json.dumps({"a": str(a_dir), "b": str(b_dir), **diff}))
    else:
        print(to_markdown(diff, str(a_dir), str(b_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
