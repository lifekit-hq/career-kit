# The executor contract

career-kit is the **executor layer** of a career platform: every chunk of
career work is a precise, agent-callable command. This file is the contract
those commands honor. Higher-level agents (skills, devclaw, a future platform)
compose these chunks; the chunks themselves stay small, deterministic where
possible, and honest about failure.

## Command taxonomy

```
career <lane> <verb> [args] [-c|--client <name>] [--json]
```

- **lane** - a domain of career work. Current lanes:

  | Lane | Verbs (implemented) | Verbs (planned) |
  |------|---------------------|-----------------|
  | `cv` | `build`, `ats`, `match`, `lint`, `letter`, `version`, `verdict`, `prep` | - |
  | `linkedin` | `capture`, `diff`, `audit`, `jd`, `keywords`, `benchmark` | - |
  | `apply` | `add`, `list`, `set`, `followup` | - |
  | `jd` | `add` | - |
  | `portfolio` | - | (lane reserved) |
  | `strategy` | - | (lane reserved) |

- `career doctor` is the one command outside the lane grammar: it reports what
  a verb needs (python, uv/uvx, the CDP Chrome the linkedin lane drives, the
  client, the shared design) **before** the verb needs it. It answers with the
  envelope as `lane: doctor, verb: check`; exit 1 means at least one failure,
  and a warning alone is exit 0.

- **verb** - one precise chunk of work with a defined result. A verb never
  grows modes; a new behavior is a new verb.
- **client** - resolved from `-c`, else `clients/.default`. Every command
  operates on exactly one client.
- **data root** - `clients/` and `build/` live under `$CAREER_KIT_HOME` when it
  is set (it must be an existing directory: a bad value is a usage error, never
  created), else under the checkout. Setting it is how the private tree stays
  out of the repo with no symlinks.
- **jd add** - `jd add <url|file>` writes the same `kind: job` snapshot as
  `linkedin jd`, from a public Ashby, Greenhouse or Lever posting URL (their
  public JSON APIs, no login, no browser) or from a local text/HTML file given
  `--company` and `--title`. Read-only. The vacancy id is `ashby-<id8>`,
  `lever-<id8>`, or Greenhouse's numeric id; a file has none unless `--id`.
- **built CV** - a verb that compares against the CV text (`cv letter`,
  `cv ats`, `cv match`, `linkedin keywords`) needs the variant built first and
  exits 1 naming the missing `build/<client>/<variant>` when it is not.
- **version** - `cv version <variant> <jd-snapshot>` builds the variant and
  freezes the cut as `clients/<c>/applications/<company>/<vacancy-id>-<title>/v<N>/`
  (the variant, the merged RenderCV input, the PDF, the ATS text, and a
  `REVIEW.md` skeleton), appending a row to that application's `VERSIONS.md`.
  A `v<N>/` is never written twice; a build that is not one page is refused
  (exit 1). `apply add --version v<N>` records which frozen cut was sent.
- **verdict** - `cv verdict v<N> <rejected|submittable|confirm>` records the
  review's verdict on a frozen cut in both places it lives, the row in
  `VERSIONS.md` and the `Verdict:` line of `v<N>/REVIEW.md`, in one step so
  they cannot disagree (`confirm` is stored as "submittable with
  confirmations"; `--note` writes the confirmations under it). The application
  is named with `--jd <snapshot>` or `--app <company/vacancy-dir>`, or implied
  when only one holds that `v<N>`. A later verdict replaces an earlier one;
  nothing else in a frozen `v<N>/` is touched.
- **prep** - `cv prep <jd-snapshot> [variant]` assembles an interview-prep pack
  and invents nothing: a story per CV claim (the claim verbatim, `[YOU: ...]`
  slots for the telling), the posting's requirement terms the built CV lacks,
  the latest frozen cut's `REVIEW.md` points (or `--version v<N>`), and
  questions to ask seeded from the posting's requirement terms. The variant
  must be built first.
- **lint** - `cv lint [variant]` checks the merged CV (profile plus that
  variant; a named variant with no file is a usage error) against the latest
  profile snapshot, and warns - never fails - when the snapshot is more than
  30 days old or cannot be dated.
- **forbidden claims** - an optional `clients/<c>/forbidden_claims.yml` lists
  phrases the client must never claim (`examples/forbidden_claims.example.yml`).
  A build whose CV text holds one fails, naming the phrase, its reason and the
  text it was found in; `cv version` builds first, so no cut is frozen with
  one. The match is on the words, not the spelling, and also inside longer words.
- **application status** - a ledger row is `drafted` (prepared, not sent: no
  applied or follow-up date, never chased), then `sent`, `replied`,
  `interview`, and ends `rejected`, `ghosted` or `withdrawn`. `apply add
  --status drafted|sent` chooses where a row starts; `apply set --status sent`
  on a draft dates it today. Only the open statuses (`sent`, `replied`,
  `interview`) are ever due to chase. Recording a role whose company and
  normalised title already sit in the ledger under another id succeeds with a
  `warnings` entry naming that row; only a human can say they are one job.
- **application id** - a ledger row (`apply` lane) is keyed by the posting's
  own vacancy id, read from the capture (`jobId`); a capture without one needs
  an explicit `--id`, and the same id twice is a usage error unless `--reapply`
  (which suffixes it). The tool never mints an id of its own.

`bin/cv` remains as a back-compat alias for the `cv` lane.

## Output envelope

Default output is human-readable text. With `--json`, a command prints exactly
one JSON object to stdout:

```json
{
  "ok": true,
  "lane": "linkedin",
  "verb": "capture",
  "client": "some-client",
  "data": { "...verb-specific result..." },
  "error": null
}
```

- `ok: false` implies `error: {"message": "..."}` and `data: null`.
- Diagnostics and progress go to stderr, never stdout, so `--json` output is
  always parseable.
- **Every** verb honors this, on every path. A usage error, an unknown client
  and a missing argument all answer with the envelope and the exit code below -
  a failure that skips it breaks callers that do `json.loads(stdout)`.
  `tools/career-cli/test_envelope.py` holds the whole taxonomy to it.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success |
| 1 | operational failure (missing snapshot, scraper error, render error) |
| 2 | usage error (unknown lane/verb, bad arguments, unknown client) |

## Data layout the commands own

- `clients/<client>/captures/<ISO-8601-UTC>/` - one **snapshot** per capture:
  the scraper's output plus a `manifest.json` (`target`, `captured_at`,
  `tool`, `kind`, `pages`). `kind` is `profile` or `job` (absent reads as
  `profile`); default snapshot resolution filters by kind, so job captures
  never pollute profile diffs/audits. Snapshots are immutable evidence:
  append-only, never edited, never committed (the whole `clients/` tree is
  gitignored).
- Legacy flat captures are wrapped as a dated snapshot with
  `"legacy": true` in the manifest; readers must accept both layouts.
- `build/<client>/<variant>/` - CV lane output (generated, disposable).

## Hard rules

- **The LinkedIn lane is READ-ONLY.** No command automates writes to a
  LinkedIn account (profile edits, connection requests, posts). Rewrites are
  paste-ready documents a human applies. This is a client-safety rule
  (account restriction mid-job-hunt), not a technical limitation.
- **Rate discipline**: capture is human-triggered, one profile at a time,
  using the operator's own logged-in session (see tools/linkedin-scrape).
- **Truth over keyword-matching**: no verb fabricates content; synthesis verbs
  frame facts that exist in the client's truth layer.
