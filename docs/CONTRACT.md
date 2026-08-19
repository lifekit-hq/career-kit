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
  | `cv` | `build`, `ats`, `match` | - |
  | `linkedin` | `capture`, `diff` | `audit`, `jd`, `benchmark` |
  | `portfolio` | - | (lane reserved) |
  | `strategy` | - | (lane reserved) |

- **verb** - one precise chunk of work with a defined result. A verb never
  grows modes; a new behavior is a new verb.
- **client** - resolved from `-c`, else `clients/.default`. Every command
  operates on exactly one client.

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

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | success |
| 1 | operational failure (missing snapshot, scraper error, render error) |
| 2 | usage error (unknown lane/verb, bad arguments, unknown client) |

## Data layout the commands own

- `clients/<client>/captures/<ISO-8601-UTC>/` - one **snapshot** per capture:
  the scraper's output plus a `manifest.json` (`target`, `captured_at`,
  `tool`, `pages`). Snapshots are immutable evidence: append-only, never
  edited, never committed (the whole `clients/` tree is gitignored).
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
