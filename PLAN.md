# career-kit - plan

## Destination

career-kit carries client #1 through a real Dublin job hunt end to end -
apply, track, follow up, learn - and every verb it grows is one that hunt
demanded. It stays the executor layer of a career platform: one unified CLI
(`bin/career`) exposing each chunk as a precise, agent-callable command with
JSON in/out. Lanes get built on demand, never to complete a grid.
(Agreed 2026-08-21; supersedes the 2026-08-19 lane-coverage destination, which
the LinkedIn and CV lanes fulfilled.)

## How work is tracked

The backlog lives in GitHub issues (labels `P1` = firmed and sized, `P2` =
named, unsized). The contract every command honors is `docs/CONTRACT.md`.
Architecture and editing rules are in `CLAUDE.md`.

## Milestones

- **M1 (in progress)**: executor contract + `bin/career` skeleton, dated
  capture store, `linkedin diff` (issues #1-#3).
- **M2**: LinkedIn analysis verbs - `audit`, `jd` intel, scraper hardening
  (issues #4-#6).
- **M3**: `benchmark`, `career lint` cross-artifact consistency (issues #7-#8).

## Out of scope

- Any write automation against LinkedIn accounts (see CONTRACT.md hard rules).
- A deployed service, database, or UI - career-kit stays a local tool a
  human or agent drives.
