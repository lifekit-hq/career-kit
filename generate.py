# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""career-kit CV generator.

Merges a per-role variant onto the canonical profile, then translates our
authoring schema into a RenderCV input file. RenderCV (the engine) does the
rendering — we own the one-profile/many-variants layer it lacks.

    uv run generate.py [variant] [-c client]   # -> build/<client>/<variant>.rendercv.yaml

Render it with:  rendercv render build/<client>/<variant>.rendercv.yaml
(bin/cv does both.)

Design contract (per client, under clients/<client>/):
  profile.yml   = the scaffold (facts stated once): who/where/when, contact,
                  education, default skills. Stable across applications.
  variants/*.yml = the framing (per role): selection, order, and prose.
  design.yaml    = RenderCV design block (the look). Shared from data/design.yaml,
                   overridable per client at clients/<client>/design.yaml.
"""
import argparse
import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"                 # shared assets (design.yaml)
CLIENTS = ROOT / "clients"           # per-client data: <client>/profile.yml, variants/
BUILD = ROOT / "build"


def default_client() -> str:
    """The client used when none is given: clients/.default, else 'denys-sychov'."""
    marker = CLIENTS / ".default"
    if marker.exists():
        name = marker.read_text().strip()
        if name:
            return name
    return "denys-sychov"


def merge(profile: dict, variant: dict) -> dict:
    """Overlay a variant onto the profile.

    - Scalars/lists (headline, summary, skills, projects, education, languages,
      sections, contacts): variant value replaces profile value if present.
    - experience: profile owns the canonical keyed roles; the variant selects
      order via `experience_order` and patches fields via `experience_overrides`.
    """
    cfg = copy.deepcopy(profile)
    v = variant or {}

    for key in ("name", "headline", "summary", "contacts", "skills",
                "projects", "education", "languages", "sections"):
        if key in v:
            cfg[key] = v[key]

    roles = {r["key"]: r for r in profile.get("experience", [])}
    order = v.get("experience_order") or [r["key"] for r in profile.get("experience", [])]
    overrides = v.get("experience_overrides") or {}
    final = []
    for k in order:
        if k not in roles:
            raise SystemExit(f"variant references unknown experience key: {k!r}")
        role = copy.deepcopy(roles[k])
        role.update(overrides.get(k, {}))
        final.append(role)
    cfg["experience"] = final
    return cfg


def _contacts(cfg) -> dict:
    """Map our contacts list -> RenderCV email/phone/social_networks."""
    out, socials = {}, []
    for c in cfg.get("contacts", []):
        href = c["href"].rstrip("/")
        if href.startswith("mailto:"):
            out["email"] = href[len("mailto:"):]
        elif href.startswith("tel:"):
            out["phone"] = href[len("tel:"):]           # RenderCV formats it
        elif "linkedin.com/in/" in href:
            socials.append({"network": "LinkedIn", "username": href.split("/in/")[-1]})
        elif "github.com/" in href:
            socials.append({"network": "GitHub", "username": href.split("github.com/")[-1]})
        else:
            out["website"] = href
    if socials:
        out["social_networks"] = socials
    return out


# Section builders: our schema -> RenderCV entry lists. Keyed by section name.
def _sec_profile(cfg):
    return "Profile", [cfg["summary"]]


def _sec_experience(cfg):
    return "Experience", [
        {"position": j["title"], "company": j["company"],
         "date": f'{j["start"]} – {j["end"]}', "location": j["location"],
         "highlights": j["bullets"]}
        for j in cfg.get("experience", [])
    ]


def _sec_projects(cfg):
    entries = []
    for p in cfg.get("projects", []):
        name = f'[**{p["name"]}**]({p["url"]})'
        if p.get("tech"):
            name += f' | {p["tech"]}'
        entries.append({"name": name, "highlights": p["bullets"]})
    return "Projects", entries


def _sec_skills(cfg):
    return "Technical Skills", [
        {"label": g["group"], "details": g["items"]} for g in cfg.get("skills", [])
    ]


def _sec_education(cfg):
    entries = []
    for e in cfg.get("education", []):
        entry = {"institution": e["school"], "area": e["area"],
                 "date": e["dates"], "location": e["location"]}
        if e.get("degree"):
            entry["degree"] = e["degree"]
        if e.get("bullets"):
            entry["highlights"] = e["bullets"]
        entries.append(entry)
    return "Education", entries


def _sec_languages(cfg):
    return "Languages", [
        {"label": l["name"], "details": l["level"]} for l in cfg.get("languages", [])
    ]


BUILDERS = {
    "profile": _sec_profile, "experience": _sec_experience, "projects": _sec_projects,
    "skills": _sec_skills, "education": _sec_education, "languages": _sec_languages,
}


def to_rendercv(cfg: dict, design: dict) -> dict:
    cv = {"name": cfg["name"], "headline": cfg["headline"]}
    cv.update(_contacts(cfg))
    sections = {}
    for name in cfg.get("sections", list(BUILDERS)):
        title, entries = BUILDERS[name](cfg)
        if entries:
            sections[title] = entries
    cv["sections"] = sections
    return {"cv": cv, "design": design, "locale": {"language": "english"}}


def main():
    ap = argparse.ArgumentParser(description="Generate a RenderCV input file from YAML.")
    ap.add_argument("variant", nargs="?", default="baseline")
    ap.add_argument("-c", "--client", default=None,
                    help="client under clients/ (default: clients/.default)")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    client = args.client or default_client()
    cdir = CLIENTS / client
    if not cdir.is_dir():
        raise SystemExit(f"no such client: {client} (looked in {cdir})")

    ppath = cdir / "profile.yml"
    if not ppath.exists():
        raise SystemExit(f"no profile for client {client!r}: {ppath}")
    profile = yaml.safe_load(ppath.read_text())

    vpath = cdir / "variants" / f"{args.variant}.yml"
    if not vpath.exists() and args.variant != "baseline":
        raise SystemExit(f"no variant file: {vpath}")
    variant = yaml.safe_load(vpath.read_text()) if vpath.exists() else {}

    # Look is shared, but a client may override with clients/<client>/design.yaml.
    dpath = cdir / "design.yaml"
    design = yaml.safe_load((dpath if dpath.exists() else DATA / "design.yaml").read_text())

    doc = to_rendercv(merge(profile, variant), design)

    outdir = BUILD / client
    outdir.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else outdir / f"{args.variant}.rendercv.yaml"
    out.write_text(
        "# Generated by career-kit generate.py — do not edit by hand.\n"
        f"# Edit clients/{client}/profile.yml + clients/{client}/variants/<name>.yml instead.\n"
        + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000)
    )
    print(out)


if __name__ == "__main__":
    main()
