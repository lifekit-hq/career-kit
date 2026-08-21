"""career doctor - say what a verb needs before it fails cryptically.

    python3 career_doctor.py <repo-root> [--client NAME] [--json]

`career linkedin capture` dies with "no CDP Chrome on :9777" only once it is
already halfway through the work, and a missing uv surfaces as a RenderCV
traceback. This reports the whole preflight up front, and distinguishes what is
broken (fail) from what is merely absent for the lane you are not using (warn).

Exit codes: 0 = no failures (warnings are fine), 1 = at least one failure.
"""
import argparse
import json
import shutil
import socket
import sys
from pathlib import Path

CDP_HOST, CDP_PORT = "127.0.0.1", 9777
MIN_PYTHON = (3, 11)

OK, WARN, FAIL = "ok", "warn", "fail"


def _c(status, name, detail, fix=""):
    return {"status": status, "check": name, "detail": detail, "fix": fix}


def check_python(version=None):
    v = version or sys.version_info[:3]
    pretty = ".".join(str(n) for n in v)
    if tuple(v[:2]) >= MIN_PYTHON:
        return _c(OK, "python", pretty)
    return _c(FAIL, "python", f"{pretty} - generate.py requires >= "
              + ".".join(str(n) for n in MIN_PYTHON), "install a newer python3")


def check_uv(which=shutil.which):
    """uv runs generate.py (PEP 723 deps) and uvx fetches RenderCV."""
    if not which("uv"):
        return _c(FAIL, "uv", "not on PATH",
                  "https://docs.astral.sh/uv/ - every tool here is a uv script")
    if not which("uvx"):
        return _c(FAIL, "uvx", "uv present but uvx missing", "reinstall uv")
    return _c(OK, "uv", "uv and uvx on PATH (RenderCV self-fetches on first render)")


def check_cdp(host=CDP_HOST, port=CDP_PORT, connect=None):
    """Only the linkedin lane needs it, so absence is a warning, not a failure."""
    connect = connect or (lambda: socket.create_connection((host, port), timeout=2))
    try:
        connect().close()
    except OSError:
        return _c(WARN, "cdp-chrome", f"nothing listening on {host}:{port}",
                  "only the linkedin lane needs it - see tools/linkedin-scrape/README.md")
    return _c(OK, "cdp-chrome", f"reachable on {host}:{port}")


def check_client(root: Path, client=None):
    default = root / "clients" / ".default"
    if client is None:
        if not default.exists():
            return _c(WARN, "client", "no clients/.default and no -c given",
                      "pass -c <name>, or write a name into clients/.default")
        client = default.read_text(encoding="utf-8").strip()
    cdir = root / "clients" / client
    if not cdir.is_dir():
        return _c(FAIL, "client", f"{client}: no such directory under clients/",
                  "career only ever operates on one existing client")
    if not (cdir / "profile.yml").is_file():
        return _c(FAIL, "client", f"{client}: no profile.yml",
                  "copy examples/profile.example.yml and fill in real facts")
    n = len(list((cdir / "variants").glob("*.yml"))) if (cdir / "variants").is_dir() else 0
    return _c(OK, "client", f"{client} (profile.yml, {n} variant(s))")


def check_design(root: Path):
    p = root / "data" / "design.yaml"
    if p.is_file():
        return _c(OK, "design", "data/design.yaml")
    return _c(FAIL, "design", "data/design.yaml missing",
              "the shared RenderCV design block - every variant renders through it")


def run_checks(root: Path, client=None, **probes):
    return [
        check_python(probes.get("version")),
        check_uv(probes.get("which", shutil.which)),
        check_cdp(connect=probes.get("connect")),
        check_client(root, client),
        check_design(root),
    ]


def summarize(checks):
    counts = {s: sum(1 for c in checks if c["status"] == s) for s in (OK, WARN, FAIL)}
    return {"checks": checks, "counts": counts, "ok": counts[FAIL] == 0}


def render(report):
    glyph = {OK: "ok  ", WARN: "warn", FAIL: "FAIL"}
    lines = [f"  {glyph[c['status']]}  {c['check']}: {c['detail']}"
             + (f"\n          -> {c['fix']}" if c["fix"] and c["status"] != OK else "")
             for c in report["checks"]]
    c = report["counts"]
    tail = (f"{c[FAIL]} failure(s), {c[WARN]} warning(s)" if c[FAIL]
            else (f"ready, {c[WARN]} warning(s)" if c[WARN] else "ready"))
    return "career doctor\n" + "\n".join(lines) + f"\n{tail}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    ap.add_argument("--client")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    report = summarize(run_checks(Path(args.root), args.client))
    print(json.dumps(report) if args.json else render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
