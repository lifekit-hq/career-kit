"""career cv version - freeze a CV cut as an immutable version of an application.

    python3 career_version.py <client-dir> <variant-file> <jd-snapshot> <build-dir>
                              [--id X] [--json]

A variant file is overwritten on every re-cut and build/ is regenerated on
every build, so once an application goes out the exact artifact that was sent
is unrecoverable, and the reviewer's verdict on each cut lives nowhere. This
verb freezes one cut:

    <client-dir>/applications/<company>/<jobid>-<title-kebab>/
        VERSIONS.md      one row per version: date, one line, verdict
        v<N>/variant.yml the framing layer as it was
        v<N>/cv.rendercv.yaml  the merged input RenderCV rendered (facts + framing)
        v<N>/CV.pdf  v<N>/CV.md  the PDF and the ATS text
        v<N>/REVIEW.md   skeleton: grounding, credibility, an empty Verdict

A v<N>/ folder is never written twice: the next cut is v<N+1>. The verb
refuses a build that is not one page, because a two-page cut is not a
candidate and freezing it would only record a mistake.

Exit codes: 0 = ok, 1 = operational failure, 2 = usage error.
"""
import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path


APPLICATIONS = "applications"
VERSIONS = "VERSIONS.md"
REVIEW = "REVIEW.md"


class Usage(Exception):
    """Bad arguments - exit 2, per docs/CONTRACT.md."""


class Failure(Exception):
    """Could not do the work - exit 1."""


def kebab(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "untitled"


def read_job(snap: Path) -> dict:
    p = snap / "job.json"
    if not p.is_file():
        raise Usage(f"{snap} has no job.json - is it a job capture? "
                    "(career linkedin jd <url>)")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Failure(f"{p}: unreadable job.json ({e})")


def application_dir(client_dir: Path, job: dict, explicit) -> Path:
    vid = explicit or job.get("jobId")
    if not vid:
        raise Usage("this capture has no vacancy id (jobId) - pass --id <value>")
    return (client_dir / APPLICATIONS / kebab(job.get("company"))
            / f"{kebab(str(vid))}-{kebab(job.get('title'))}")


def next_version(app: Path) -> int:
    used = [int(p.name[1:]) for p in app.glob("v*")
            if p.is_dir() and p.name[1:].isdigit()]
    return max(used, default=0) + 1


def build_artifacts(build_dir: Path) -> dict:
    """The PDF, the ATS Markdown, and the page count (RenderCV writes one PNG
    per page, so counting them needs no PDF library)."""
    pdfs = sorted(build_dir.glob("*_CV.pdf"))
    mds = sorted(build_dir.glob("*_CV.md"))
    if not pdfs or not mds:
        raise Failure(f"{build_dir} holds no rendered CV - build the variant first")
    pages = len(list(build_dir.glob("*_CV_*.png")))
    return {"pdf": pdfs[0], "md": mds[0], "pages": pages}


def review_skeleton(n: int, today: str, variant: str, snap_rel: str) -> str:
    return (f"# v{n} review ({today})\n\n"
            f"Variant: {variant}. JD snapshot: {snap_rel}.\n\n"
            "## Grounding\n\n"
            "Every claim traces to profile.yml or a public artifact; anything that\n"
            "rests on inference rather than a stated fact is listed here.\n\n"
            "## Credibility\n\n"
            "Read as the target company's recruiter (30 seconds) and as an engineer\n"
            "on the hiring team (2 minutes): what each would discount, per sentence.\n\n"
            "## Verdict\n\n"
            "Verdict: \n")


def versions_header(job: dict, snap_rel: str) -> str:
    return (f"# {job.get('company') or '?'}, {job.get('title') or '?'}, "
            f"vacancy {job.get('jobId') or '?'}\n\n"
            f"JD snapshot: {snap_rel}. Versions are frozen: never edit a v<N>/ "
            "folder; cut the next one.\n\n"
            "| version | date | one line | verdict |\n|---|---|---|---|\n")


def freeze(client_dir: Path, variant_file: Path, snap: Path, build_dir: Path,
           explicit_id, today: str) -> dict:
    if not variant_file.is_file():
        raise Usage(f"no variant file: {variant_file}")
    if not snap.is_dir():
        raise Usage(f"no such job snapshot: {snap}")
    job = read_job(snap)
    art = build_artifacts(build_dir)
    if art["pages"] != 1:
        raise Failure(f"the build is {art['pages']} page(s), not one - a version "
                      "is a candidate, and a candidate is one page")
    merged = build_dir.parent / f"{variant_file.stem}.rendercv.yaml"
    app = application_dir(client_dir, job, explicit_id)
    n = next_version(app)
    vdir = app / f"v{n}"
    if vdir.exists():
        raise Failure(f"{vdir} already exists - versions are never overwritten")
    try:
        snap_rel = str(snap.resolve().relative_to(client_dir.resolve()))
    except ValueError:
        snap_rel = str(snap.resolve())
    vdir.mkdir(parents=True)
    shutil.copy(variant_file, vdir / "variant.yml")
    if merged.is_file():
        shutil.copy(merged, vdir / "cv.rendercv.yaml")
    shutil.copy(art["pdf"], vdir / "CV.pdf")
    shutil.copy(art["md"], vdir / "CV.md")
    (vdir / REVIEW).write_text(review_skeleton(n, today, variant_file.stem, snap_rel),
                               encoding="utf-8")
    vfile = app / VERSIONS
    if not vfile.is_file():
        vfile.write_text(versions_header(job, snap_rel), encoding="utf-8")
    with vfile.open("a", encoding="utf-8") as f:
        f.write(f"| v{n} | {today} | {variant_file.stem} | (pending review) |\n")
    try:
        app_rel = str(app.resolve().relative_to(client_dir.resolve()))
    except ValueError:
        app_rel = str(app.resolve())
    return {"application": app_rel, "version": f"v{n}", "dir": str(vdir),
            "company": job.get("company"), "role": job.get("title"),
            "vacancy_id": str(explicit_id or job.get("jobId")),
            "files": sorted(p.name for p in vdir.iterdir())}


def render(d: dict) -> str:
    return (f"→ {d['application']}/{d['version']}  {d['company']} - {d['role']}\n"
            f"  frozen: {', '.join(d['files'])}\n"
            f"  next: write the review and verdict in {d['version']}/{REVIEW}")


def main(argv=None, today=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("client_dir"); ap.add_argument("variant_file")
    ap.add_argument("jd"); ap.add_argument("build_dir")
    ap.add_argument("--id", help="vacancy id, when the capture carries none")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    client_dir = Path(args.client_dir)
    snap = next((c for c in (Path(args.jd), client_dir / args.jd,
                             client_dir / "captures" / args.jd) if c.is_dir()),
                Path(args.jd))
    try:
        data = freeze(client_dir, Path(args.variant_file), snap, Path(args.build_dir),
                      args.id, today or date.today().isoformat())
    except Usage as e:
        print(f"{e}", file=sys.stderr)
        return 2
    except Failure as e:
        print(f"{e}", file=sys.stderr)
        return 1
    print(json.dumps(data) if args.json else render(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
