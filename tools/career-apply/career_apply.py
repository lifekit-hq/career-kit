"""career apply - the application ledger.

    python3 career_apply.py add  <client-dir> <jd-snapshot> [--variant V] [--version vN] [--id X] [--reapply] ...
    python3 career_apply.py list <client-dir> [--status S] [--json]
    python3 career_apply.py set  <client-dir> <id> [--status S] [--followup D] ...
    python3 career_apply.py followup <client-dir> [--on DATE] [--json]

A hunt without a ledger loses the thread: which variant went where, on what
date, and what came back. The store is `<client-dir>/applications.yml`, private
like the rest of clients/ (PRIVATE.md), append-mostly, and readable by hand -
the point is that a human can audit it, not that a tool can parse it fast.

`add` reads the job snapshot's job.json for company/title/source so the ledger
never restates by hand what the capture already knows. The row's `id` is the
posting's own vacancy id (`jobId`), the one thing that tells two live postings
of the same role apart and the thing a human already types when chasing; a
capture without one needs an explicit `--id`, never a guessed counter.

Exit codes: 0 = ok, 1 = operational failure, 2 = usage error.
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
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
    """The file is advertised as hand-editable, so it has to tolerate what a
    hand writes: an `applications:` key with nothing under it parses as None,
    not as an empty list."""
    p = client_dir / LEDGER
    if not p.exists():
        return {"schema": SCHEMA, "applications": []}
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(doc, dict):
        raise Usage(f"{p} is not a mapping - expected `applications:` at the top level")
    doc["schema"] = doc.get("schema") or SCHEMA
    apps = doc.get("applications") or []
    if not isinstance(apps, list):
        raise Usage(f"{p}: `applications` must be a list, got {type(apps).__name__}")
    doc["applications"] = [_normalize(a, p) for a in apps]
    return doc


def _normalize(entry, path):
    """YAML parses an unquoted 2026-08-01 as a date object, and we compare and
    store these as ISO strings. Our own writer quotes them, so this only bites
    a hand-edited file - which is exactly the file we tell people to edit."""
    if not isinstance(entry, dict):
        raise Usage(f"{path}: every application must be a mapping, got "
                    f"{type(entry).__name__}")
    for k in ("applied", "followup"):
        v = entry.get(k)
        if isinstance(v, datetime):
            entry[k] = v.date().isoformat()
        elif isinstance(v, date):
            entry[k] = v.isoformat()
    return entry


def save(client_dir: Path, doc: dict) -> None:
    (client_dir / LEDGER).write_text(
        "# career-kit application ledger - `career apply`. Hand-editable.\n"
        + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8")


def row_id(apps: list, job: dict, explicit, reapply: bool) -> str:
    """The vacancy id from the capture (or --id when the capture has none).
    A second row for the same posting is refused: it is almost always the
    same application recorded twice. A genuine re-application says so with
    --reapply and gets a suffixed id, so the first row stays intact."""
    base = explicit or job.get("jobId")
    if not base:
        raise Usage("this capture has no vacancy id (jobId) - pass --id <value>")
    base = str(base)
    used = {a.get("id") for a in apps}
    if base not in used:
        return base
    if not reapply:
        raise Usage(f"application {base!r} is already recorded - see: career apply "
                    "list; pass --reapply if this is a genuine second application")
    n = 2
    while f"{base}-{n}" in used:
        n += 1
    return f"{base}-{n}"


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


# A chase lives in `notes` as a dated marker rather than a separate field, so a
# hand-written "chased 2026-09-01" counts exactly like one `--chased` recorded.
CHASE_RE = re.compile(r"chased (\d{4}-\d{2}-\d{2})")


def chase_dates(entry: dict) -> list:
    return CHASE_RE.findall(str(entry.get("notes") or ""))


def days_quiet(entry: dict, today: str):
    """Days since the last thing WE did - applying, or the latest chase. Derived
    at read time, never stored; a terminal application has no quiet to measure.
    A hand-typed garbage date degrades to no value, not a crash."""
    if entry.get("status") not in OPEN_STATUSES:
        return None
    try:
        last = max(d for d in [entry.get("applied"), *chase_dates(entry)] if d)
        return (date.fromisoformat(today) - date.fromisoformat(last)).days
    except (ValueError, TypeError):
        return None


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
        "id": row_id(doc["applications"], job, args.id, args.reapply),
        "jd": rel,
        "company": job.get("company"),
        "role": job.get("title"),
        "source": job.get("source"),
        "variant": args.variant,
        "version": args.version,
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
    # Derived fields only - cmd_list never save()s, so these cannot leak into
    # the ledger file.
    for a in apps:
        a["days_quiet"] = days_quiet(a, args.today)
        a["chases"] = len(chase_dates(a))
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
        elif not entry.get("followup"):
            # ...and reopening one has to give the date back, or the
            # application reads as live while being invisible to `followup`
            # forever - the exact lost thread this ledger exists to prevent.
            entry["followup"] = (date.fromisoformat(args.today)
                                 + timedelta(days=FOLLOWUP_DAYS)).isoformat()
    if args.notes is not None:
        entry["notes"] = args.notes
    if args.chased is not None:
        # Recording a chase against a closed application would fake activity
        # on something that has nothing left to chase.
        if entry.get("status") not in OPEN_STATUSES:
            raise Usage(f"{args.id} is {entry.get('status')} - nothing to chase")
        chased = parse_date(args.chased, "chased") if args.chased else args.today
        notes = str(entry.get("notes") or "")
        entry["notes"] = (f"{notes}; " if notes else "") + f"chased {chased}"
        # A chase restarts the clock; an explicit --followup below still wins.
        entry["followup"] = (date.fromisoformat(chased)
                             + timedelta(days=FOLLOWUP_DAYS)).isoformat()
    if args.followup:
        entry["followup"] = parse_date(args.followup, "followup")
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
        a["chases"] = len(chase_dates(a))     # how many times already chased
    return {"due": due, "count": len(due), "on": on}


def render(verb: str, data: dict) -> str:
    if verb == "add":
        e = data["added"]
        return (f"→ {e['id']}  {e['company']} - {e['role']}\n"
                f"  variant {e['variant'] or '(none)'}"
                + (f" {e['version']}" if e.get('version') else "")
                + f" · applied {e['applied']} · follow up {e['followup']}")
    if verb == "set":
        e = data["updated"]
        return f"→ {e['id']}  status {e['status']} · follow up {e['followup'] or '-'}"
    if verb == "followup":
        due = data["due"]
        if not due:
            return f"nothing due as of {data['on']}"
        rows = [f"  {a['id']}  {a['days_overdue']:>3}d  "
                f"{(a.get('company') or '?')} - {(a.get('role') or '?')}"
                f"  (due {a['followup']}"
                + (f", chased x{a['chases']}" if a.get("chases") else "") + ")"
                for a in due]
        return f"{len(due)} follow-up(s) due as of {data['on']}:\n" + "\n".join(rows)
    apps = data["applications"]
    if not apps:
        return "no applications recorded"
    rows = [f"  {a['id']}  {a.get('status',''):<9} {a.get('applied',''):<11} "
            f"{(a.get('company') or '?')} - {(a.get('role') or '?')}"
            + (f"  [{a['version']}]" if a.get("version") else "")
            + (f"  · quiet {a['days_quiet']}d" if a.get("days_quiet") is not None
               else "")
            + (f" · chased x{a['chases']}" if a.get("chases") else "")
            for a in apps]
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
    a.add_argument("--id", help="vacancy id, when the capture carries none")
    a.add_argument("--version", help="the frozen cut that was sent (career cv version), e.g. v2")
    a.add_argument("--reapply", action="store_true",
                   help="record a genuine second application to the same posting")
    a.add_argument("--applied"); a.add_argument("--followup"); a.add_argument("--notes")

    l = sub.add_parser("list", parents=[common]); l.set_defaults(fn=cmd_list)
    l.add_argument("client_dir"); l.add_argument("--status")

    f = sub.add_parser("followup", parents=[common]); f.set_defaults(fn=cmd_followup)
    f.add_argument("client_dir")
    f.add_argument("--on", help="evaluate as of this ISO date (default: today)")

    s = sub.add_parser("set", parents=[common]); s.set_defaults(fn=cmd_set)
    s.add_argument("client_dir"); s.add_argument("id")
    s.add_argument("--status"); s.add_argument("--followup"); s.add_argument("--notes")
    s.add_argument("--chased", nargs="?", const="", metavar="DATE",
                   help="record a chase sent on DATE (default: today); "
                        "restarts the follow-up clock")

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
