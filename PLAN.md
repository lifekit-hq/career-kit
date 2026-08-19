# career-kit - plan

## Destination

career-kit is the executor layer of a career platform: one unified CLI
(`bin/career`) exposing every career-work chunk as a precise, agent-callable
command with JSON in/out - lanes: `linkedin`, `cv`, `portfolio`, `strategy` -
with the LinkedIn lane as the first fully-built implementation.
(Agreed 2026-08-19.)

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
