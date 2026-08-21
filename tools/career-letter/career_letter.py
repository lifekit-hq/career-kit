"""career cv letter - the grounded input pack for a cover letter.

    python3 career_letter.py <profile.yml> <job-snapshot> [--variant V] [--cv CV.md] [--json]

The letter is the one application artifact written outside the truth constraints
the CV lane enforces, which makes it the easiest place to inflate. This does not
write the prose: judgement calls belong to the LLM pass in the calling skill,
the same split li_audit and li_scrape already use. What it does is assemble what
the prose is allowed to stand on:

  evidence   - every fact the merged CV actually carries, quotable verbatim
  matched    - JD language the CV already backs, i.e. what to lead with
  unevidenced- JD language nothing in the CV backs. A raw single-document
               signal, not a curated list of asks: unigrams cannot tell a
               requirement from prose, and deciding which is which is exactly
               the judgement the skill does. Treat it as the set to check a
               draft against, not a list to answer point by point.
  scaffold   - a deterministic skeleton with the judgement slots marked

Exit codes: 0 = ok, 1 = operational failure, 2 = usage error.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "jd-intel"))

import generate                                    # noqa: E402
import jd_intel                                    # noqa: E402

CONSTRAINTS = [
    "Every claim must trace to an entry in `evidence`; JD language only decides "
    "emphasis and order, it never introduces a fact.",
    "Nothing from `unevidenced` may be claimed, implied, or softened into a claim.",
    "Plain ASCII: no smart quotes, em dashes or non-breaking spaces.",
]


# Unfalsifiable self-description. A letter calling itself "passionate" needs no
# evidence gate - nobody can be caught out by it - so listing these as things
# not to claim buries the terms that ARE claimable capabilities.
BOILERPLATE = {
    "dynamic", "exciting", "creative", "passionate", "professional", "innovative",
    "motivated", "enthusiastic", "driven", "talented", "competitive", "proven",
    "exceptional", "ideal", "successful", "leading", "growing", "fast-growing",
    "vibrant", "collaborative", "flexible", "reliable", "organised", "organized",
    "detail-oriented", "self-starter", "hands-on", "world-class", "cutting-edge",
}


class Usage(Exception):
    """Bad arguments - exit 2."""


def merged_cv(profile_path: Path, variant_path=None) -> dict:
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    variant = (yaml.safe_load(variant_path.read_text(encoding="utf-8"))
               if variant_path and variant_path.exists() else {})
    return generate.merge(profile, variant or {})


def evidence(cfg: dict) -> dict:
    """Everything the letter is allowed to stand on, quoted from the CV itself."""
    return {
        "roles": [{"title": r["title"], "company": r["company"],
                   "dates": f'{r["start"]} - {r["end"]}', "bullets": r["bullets"]}
                  for r in cfg.get("experience", [])],
        "skills": [{"group": g["group"], "items": g["items"]}
                   for g in cfg.get("skills", [])],
        "projects": [{"name": p["name"], "bullets": p.get("bullets", [])}
                     for p in cfg.get("projects", [])],
        "summary": cfg.get("summary", ""),
    }


def cv_text(cfg: dict, cv_md: Path = None) -> str:
    """The ATS markdown when it exists - that is the text a parser really sees -
    else the merged YAML's own prose."""
    if cv_md and cv_md.is_file():
        return cv_md.read_text(encoding="utf-8")
    ev = evidence(cfg)
    parts = [cfg.get("headline", ""), ev["summary"]]
    for r in ev["roles"]:
        parts += [r["title"], r["company"], *r["bullets"]]
    parts += [g["items"] for g in ev["skills"]]
    for p in ev["projects"]:
        parts += [p["name"], *p["bullets"]]
    return "\n".join(str(x) for x in parts)


def signals(job: dict, text: str) -> dict:
    have = set(jd_intel.tokens(text))
    want = jd_intel.tokens(jd_intel.job_text(job))
    # The employer's own name and where it operates are not capabilities anyone
    # could falsely claim, so they are noise in a do-not-claim list.
    about_them = set(jd_intel.tokens(
        " ".join(str(job.get(k, "")) for k in ("company", "location"))))
    seen, matched, missing, dropped = set(), [], [], 0
    for w in want:                                  # keep JD order, drop repeats
        if w in seen:
            continue
        seen.add(w)
        if w in have:
            matched.append(w)
        elif w in about_them or w in BOILERPLATE:
            dropped += 1
        else:
            missing.append(w)
    return {"matched": matched, "unevidenced": missing, "noise_filtered": dropped}


def scaffold(cfg: dict, job: dict, sig: dict) -> str:
    lead = ", ".join(sig["matched"][:3]) or "the role's core ask"
    contacts = " | ".join(c["label"] for c in cfg.get("contacts", [])[:2])
    return "\n".join([
        cfg.get("name", ""),
        contacts,
        "",
        f'Application: {job.get("title", "?")} at {job.get("company", "?")}',
        "",
        "Dear Hiring Team,",
        "",
        f"[OPENING: why this role, in your own words. Lead with {lead} - the JD "
        "asks for these and the CV already backs them.]",
        "",
        "[EVIDENCE: two facts from `evidence`, each with what you did and what "
        "changed. Quote the CV; do not upgrade it.]",
        "",
        "[CLOSE: availability"
        + (f", and right to work in {cfg['location']}" if cfg.get("location") else "")
        + ".]",
        "",
        cfg.get("name", ""),
    ])


def build(profile_path: Path, snap: Path, variant_path=None, cv_md=None) -> dict:
    job = jd_intel.load_job(snap)
    if not job:
        raise Usage(f"{snap} has no readable job.json - is it a job capture? "
                    "(career linkedin jd <url>)")
    cfg = merged_cv(profile_path, variant_path)
    sig = signals(job, cv_text(cfg, cv_md))
    pack = {
        "job": {k: job.get(k) for k in ("title", "company", "location", "source")},
        "applicant": {k: cfg.get(k) for k in ("name", "headline", "location")},
        "evidence": evidence(cfg),
        "signals": sig,
        "constraints": CONSTRAINTS,
        "scaffold": scaffold(cfg, job, sig),
    }
    # Same Unicode hygiene the CV gets (#18): model-drafted YAML is where these
    # come from, and a letter is pasted straight into someone's form. The " - "
    # splitter guard is not applied - it is a RenderCV list-item rule, and a
    # letter has no list items, exactly as `summary` is exempt in the CV.
    pack = generate._fold_unicode(pack)
    generate._check_confusables(pack)
    return pack


def render(pack: dict) -> str:
    s = pack["signals"]
    out = [pack["scaffold"], "", "-" * 60,
           "FACTS YOU MAY CITE (from the CV, verbatim):"]
    for r in pack["evidence"]["roles"]:
        out.append(f'  {r["title"]}, {r["company"]} ({r["dates"]})')
        out += [f"    - {b}" for b in r["bullets"]]
    shown = s["unevidenced"][:40]
    more = len(s["unevidenced"]) - len(shown)
    out += ["", f'UNBACKED JD LANGUAGE ({len(s["unevidenced"])} term(s); raw signal - '
            "no claim in the letter may rest on any of these):",
            "  " + ", ".join(shown or ["(none)"])
            + (f"  ... and {more} more" if more else "")]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("profile"); ap.add_argument("snapshot")
    ap.add_argument("--variant"); ap.add_argument("--cv")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        pack = build(Path(args.profile), Path(args.snapshot),
                     Path(args.variant) if args.variant else None,
                     Path(args.cv) if args.cv else None)
    except Usage as e:
        print(e, file=sys.stderr)
        return 2
    print(json.dumps(pack) if args.json else render(pack))
    return 0


if __name__ == "__main__":
    sys.exit(main())
