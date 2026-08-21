"""career apply - the application ledger.

    python3 career_apply.py add  <client-dir> <jd-snapshot> [--variant V] ...
    python3 career_apply.py list <client-dir> [--status S] [--json]
    python3 career_apply.py set  <client-dir> <id> [--status S] [--followup D] ...
    python3 career_apply.py followup <client-dir> [--on DATE] [--json]

A hunt without a ledger loses the thread: which variant went where, on what
date, and what came back. The store is `<client-dir>/applications.yml`, private
like the rest of clients/ (PRIVATE.md), append-mostly, and readable by hand -
the point is that a human can audit it, not that a tool can parse it fast.

`add` reads the job snapshot's job.json for company/title/source so the ledger
never restates by hand what the capture already knows.

Exit codes: 0 = ok, 1 = operational failure, 2 = usage error.
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

SCHEMA = "career-apply/1"
LEDGER = "applications.yml"

# The lifecycle a sent application can be in. `ghosted` is a real terminal
# state, not a missing value - naming it keeps it out of the follow-up queue.
STATUSES = ("sent", "replied", "interview", "rejected", "ghosted")
OPEN_STATUSES = ("sent", "replied", "interview")

FOLLOWUP_DAYS = 7


class Usage(Exception):
    """Bad arguments - exit 2, per docs/CONTRACT.md."""


def load(client_dir: Path) -> dict:
    p = client_dir / LEDGER
    if not p.exists():
        return {"schema": SCHEMA, "applications": []}
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    doc.setdefault("schema", SCHEMA)
    doc.setdefault("applications", [])
    return doc


def save(client_dir: Path, doc: dict) -> None:
    (client_dir / LEDGER).write_text(
        "# career-kit application ledger - `career apply`. Hand-editable.\n"
        + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8")


def next_id(apps: list) -> str:
    used = {int(a["id"][1:]) for a in apps
            if isinstance(a.get("id"), str) and a["id"][1:].isdigit()}
    return f"a{max(used, default=0) + 1:03d}"


def read_job(snap: Path) -> dict:
    """Company/role/source straight from the capture, so the ledger cannot
    disagree with the evidence it points at."""
    p = snap / "job.json"
    if not p.is_file():
        return {}
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {k: j.get(k) for k in ("title", "company", "location", "jobId", "source")
            if j.get(k)}


def parse_date(s: str, field: str) -> str:
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        raise Usage(f"--{field} must be an ISO date (YYYY-MM-DD), got {s!r}")


def cmd_add(args) -> dict:
    client_dir = Path(args.client_dir)
    # Accept whatever the user has to hand: the path `career linkedin jd`
    # printed, a client-relative one, or the bare capture timestamp.
    snap = next((c for c in (Path(args.jd), client_dir / args.jd,
                             client_dir / "captures" / args.jd) if c.is_dir()), None)
    if snap is None:
        raise Usage(f"no such job snapshot: {args.jd}")
    job = read_job(snap)
    if not job:
        raise Usage(f"{snap} has no readable job.json - is it a job capture? "
                    "(career linkedin jd <url>)")

    applied = parse_date(args.applied, "applied") if args.applied else args.today
    followup = (parse_date(args.followup, "followup") if args.followup else
                (date.fromisoformat(applied) + timedelta(days=FOLLOWUP_DAYS)).isoformat())

    doc = load(client_dir)
    try:
        rel = str(snap.resolve().relative_to(client_dir.resolve()))
    except ValueError:
        rel = str(snap.resolve())

    entry = {
        "id": next_id(doc["applications"]),
        "jd": rel,
        "company": job.get("company"),
        "role": job.get("title"),
        "source": job.get("source"),
        "variant": args.variant,
        "applied": applied,
        "channel": args.channel,
        "status": "sent",
        "followup": followup,
        "notes": args.notes or "",
    }
    doc["applications"].append(entry)
    save(client_dir, doc)
    return {"added": entry, "count": len(doc["applications"])}


def cmd_list(args) -> dict:
    apps = load(Path(args.client_dir))["applications"]
    if args.status:
        if args.status not in STATUSES:
            raise Usage(f"unknown status {args.status!r}; one of {', '.join(STATUSES)}")
        apps = [a for a in apps if a.get("status") == args.status]
    return {"applications": apps, "count": len(apps)}


def cmd_set(args) -> dict:
    client_dir = Path(args.client_dir)
    doc = load(client_dir)
    match = [a for a in doc["applications"] if a.get("id") == args.id]
    if not match:
        raise Usage(f"no application with id {args.id!r} - see: career apply list")
    entry = match[0]
    if args.status:
        if args.status not in STATUSES:
            raise Usage(f"unknown status {args.status!r}; one of {', '.join(STATUSES)}")
        entry["status"] = args.status
        # A terminal state has nothing left to chase; leaving a date behind
        # would keep it surfacing in the follow-up queue forever.
        if args.status in ("rejected", "ghosted"):
            entry["followup"] = None
    if args.followup:
        entry["followup"] = parse_date(args.followup, "followup")
    if args.notes is not None:
        entry["notes"] = args.notes
    save(client_dir, doc)
    return {"updated": entry}


def cmd_followup(args) -> dict:
    """What is due. Open statuses only - a rejected or ghosted application has
    nothing left to chase, and its followup date was cleared when it got there."""
    on = parse_date(args.on, "on") if args.on else args.today
    due = [a for a in load(Path(args.client_dir))["applications"]
           if a.get("status") in OPEN_STATUSES and a.get("followup")
           and a["followup"] <= on]
    due.sort(key=lambda a: a["followup"])          # most overdue first
    for a in due:
        a["days_overdue"] = (date.fromisoformat(on)
                             - date.fromisoformat(a["followup"])).days
    return {"due": due, "count": len(due), "on": on}


def render(verb: str, data: dict) -> str:
    if verb == "add":
        e = data["added"]
        return (f"→ {e['id']}  {e['company']} - {e['role']}\n"
                f"  variant {e['variant'] or '(none)'} · applied {e['applied']} · "
                f"follow up {e['followup']}")
    if verb == "set":
        e = data["updated"]
        return f"→ {e['id']}  status {e['status']} · follow up {e['followup'] or '-'}"
    if verb == "followup":
        due = data["due"]
        if not due:
            return f"nothing due as of {data['on']}"
        rows = [f"  {a['id']}  {a['days_overdue']:>3}d  "
                f"{(a.get('company') or '?')} - {(a.get('role') or '?')}"
                f"  (due {a['followup']})" for a in due]
        return f"{len(due)} follow-up(s) due as of {data['on']}:\n" + "\n".join(rows)
    apps = data["applications"]
    if not apps:
        return "no applications recorded"
    rows = [f"  {a['id']}  {a.get('status',''):<9} {a.get('applied',''):<11} "
            f"{(a.get('company') or '?')} - {(a.get('role') or '?')}" for a in apps]
    return f"{len(apps)} application(s):\n" + "\n".join(rows)


def main(argv=None, today=None):
    # --json has to work on both sides of the subcommand: bin/career appends
    # global flags at the end of the line, argparse wants them before the verb.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 parents=[common])
    sub = ap.add_subparsers(dest="verb", required=True)

    a = sub.add_parser("add", parents=[common]); a.set_defaults(fn=cmd_add)
    a.add_argument("client_dir"); a.add_argument("jd")
    a.add_argument("--variant"); a.add_argument("--channel", default="linkedin")
    a.add_argument("--applied"); a.add_argument("--followup"); a.add_argument("--notes")

    l = sub.add_parser("list", parents=[common]); l.set_defaults(fn=cmd_list)
    l.add_argument("client_dir"); l.add_argument("--status")

    f = sub.add_parser("followup", parents=[common]); f.set_defaults(fn=cmd_followup)
    f.add_argument("client_dir")
    f.add_argument("--on", help="evaluate as of this ISO date (default: today)")

    s = sub.add_parser("set", parents=[common]); s.set_defaults(fn=cmd_set)
    s.add_argument("client_dir"); s.add_argument("id")
    s.add_argument("--status"); s.add_argument("--followup"); s.add_argument("--notes")

    args = ap.parse_args(argv)
    args.today = today or date.today().isoformat()
    try:
        data = args.fn(args)
    except Usage as e:
        print(f"{e}", file=sys.stderr)
        return 2
    print(json.dumps(data) if args.json else render(args.verb, data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
