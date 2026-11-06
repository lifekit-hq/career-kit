"""career cv verdict - record the reviewer's verdict on a frozen CV cut.

    python3 career_verdict.py <client-dir> <v<N>> <rejected|submittable|confirm>
                              [--jd <snapshot> [--id X] | --app <company/vacancy-dir>]
                              [--note TEXT] [--json]

`career cv version` freezes a cut with `(pending review)` in VERSIONS.md and an
empty `Verdict:` in v<N>/REVIEW.md. The verdict lives in two places, and two
places drift: this writes both, in one step, so they cannot disagree.

    rejected      the cut is dropped; cut again
    submittable   ready to send
    confirm       submittable once the client confirms the phrasings that rest
                  on inference (list them with --note); stored as
                  "submittable with confirmations"

The application is found from --jd (the same snapshot the cut was frozen from),
or --app (its path under applications/); with neither, the version must exist
in exactly one application. Recording again replaces the earlier verdict: a
review can change its mind, the frozen artifacts cannot.

Exit codes: 0 = ok, 1 = operational failure, 2 = usage error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "career-version"))
import career_version as cv                                  # noqa: E402

VERDICTS = {"rejected": "rejected", "submittable": "submittable",
            "confirm": "submittable with confirmations"}

VERDICT_HEADING = "## Verdict"


def find_application(client_dir: Path, version: str, jd, explicit_id, app) -> Path:
    root = client_dir / cv.APPLICATIONS
    if app:
        found = root / app
        if not found.is_dir():
            raise cv.Usage(f"no such application: {found}")
        return found
    if jd:
        snap = next((c for c in (Path(jd), client_dir / jd, client_dir / "captures" / jd)
                     if c.is_dir()), None)
        if snap is None:
            raise cv.Usage(f"no such job snapshot: {jd}")
        return cv.application_dir(client_dir, cv.read_job(snap), explicit_id)
    holders = sorted(p.parent for p in root.glob(f"*/*/{version}") if p.is_dir())
    if len(holders) == 1:
        return holders[0]
    if not holders:
        raise cv.Usage(f"no application holds {version} - see: {root}")
    listing = "\n".join(f"  {p.relative_to(root)}" for p in holders)
    raise cv.Usage(f"{version} exists in {len(holders)} applications; say which with "
                   f"--jd <snapshot> or --app <path>:\n{listing}")


def set_review_verdict(text: str, verdict: str, note) -> str:
    """Set the `Verdict:` line under `## Verdict`, keeping everything else there
    (the reviewer's confirmations, an earlier note). A review with no such
    heading gets it. A note is added unless it is already in the review."""
    line = f"Verdict: {verdict}"
    i = text.find(VERDICT_HEADING)
    if i < 0:
        text = text.rstrip("\n") + f"\n\n{VERDICT_HEADING}\n\n{line}\n"
    else:
        head, tail = text[:i + len(VERDICT_HEADING)], text[i + len(VERDICT_HEADING):]
        tail, n = re.subn(r"(?m)^Verdict:.*$", line, tail, count=1)
        text = head + (tail if n else f"\n\n{line}{tail}")
    note = note.strip() if note else ""
    if note and note not in text:
        text = text.rstrip("\n") + f"\n\n{note}\n"
    return text


def set_versions_verdict(text: str, version: str, verdict: str) -> str:
    out, hit = [], False
    for line in text.splitlines(keepends=True):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and len(cells) == 4 and cells[0] == version:
            hit = True
            line = f"| {cells[0]} | {cells[1]} | {cells[2]} | {verdict} |\n"
        out.append(line)
    if not hit:
        raise cv.Failure(f"{cv.VERSIONS} has no row for {version}")
    return "".join(out)


def record(client_dir: Path, version: str, verdict_key: str, jd=None, explicit_id=None,
           app=None, note=None) -> dict:
    if not re.fullmatch(r"v[1-9]\d*", version):
        raise cv.Usage(f"version must look like v1, v2, ..., got {version!r}")
    if verdict_key not in VERDICTS:
        raise cv.Usage(f"verdict is one of {', '.join(VERDICTS)}, got {verdict_key!r}")
    verdict = VERDICTS[verdict_key]
    appdir = find_application(client_dir, version, jd, explicit_id, app)
    vdir = appdir / version
    review, versions = vdir / cv.REVIEW, appdir / cv.VERSIONS
    if not vdir.is_dir():
        raise cv.Usage(f"{vdir} does not exist - see {versions} for the cuts")
    if not versions.is_file():
        raise cv.Failure(f"{versions} is missing")
    new_versions = set_versions_verdict(versions.read_text(encoding="utf-8"), version, verdict)
    old_review = review.read_text(encoding="utf-8") if review.is_file() else ""
    # Both texts are computed before either file is written, so a malformed
    # VERSIONS.md cannot leave REVIEW.md ahead of it.
    review.write_text(set_review_verdict(old_review, verdict, note), encoding="utf-8")
    versions.write_text(new_versions, encoding="utf-8")
    try:
        rel = str(appdir.resolve().relative_to(client_dir.resolve()))
    except ValueError:
        rel = str(appdir.resolve())
    return {"application": rel, "version": version, "verdict": verdict,
            "files": [str(review), str(versions)]}


def render(d: dict) -> str:
    return (f"→ {d['application']}/{d['version']}  verdict: {d['verdict']}\n"
            f"  written to {cv.REVIEW} and {cv.VERSIONS}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("client_dir"); ap.add_argument("version")
    ap.add_argument("verdict", help="|".join(VERDICTS))
    ap.add_argument("--jd", help="the job snapshot the cut was frozen from")
    ap.add_argument("--id", help="vacancy id, when the capture carries none")
    ap.add_argument("--app", help="the application's path under applications/")
    ap.add_argument("--note", help="written under the verdict in REVIEW.md, e.g. "
                    "the phrasings the client must confirm")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        data = record(Path(args.client_dir), args.version, args.verdict,
                      args.jd, args.id, args.app, args.note)
    except cv.Usage as e:
        print(e, file=sys.stderr)
        return 2
    except cv.Failure as e:
        print(e, file=sys.stderr)
        return 1
    print(json.dumps(data) if args.json else render(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
