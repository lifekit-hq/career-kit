# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

career-kit is a **multi-client, end-to-end career workbench**: research → strategy → optimized LinkedIn → ATS-ready CV, general enough to serve any person. Its CV engine is YAML-driven — one source of truth for facts per client, per-role framing layered on top — delegating rendering to [RenderCV](https://github.com/rendercv/rendercv) (invoked via `uvx`, not installed globally). It is a local tool/skill, not a deployed service. Part of the lifekit ecosystem.

Each person is a **client** under `clients/<name>/` (e.g. `clients/ada-lovelace/`). The whole `clients/` tree is private (see the privacy split below) - **real client names never appear in a committed file**, this one included; the repo is public.

## Commands

`bin/career` is the executor CLI — one precise chunk of career work per verb,
honoring the contract in `docs/CONTRACT.md` (JSON envelope via `--json`, exit
codes, per-client resolution). Destination/milestones: `docs/PLAN.md`; backlog:
GitHub issues.

```bash
bin/career cv build|ats|match [...] [-c client] [--json]  # CV lane (delegates to bin/cv)
bin/career cv lint [variant] [-c client]  # cross-check CV vs latest LinkedIn snapshot (exit 1 on mismatch)
                                          # headline: the role noun (before the first '|') must match;
                                          # a variant may tailor the modifiers after it (warn, not fail)
bin/career linkedin capture <url|id> [-c client]  # snapshot -> clients/<c>/captures/<ISO>/ (+manifest)
bin/career linkedin diff [snapA snapB] [-c client]  # compare snapshots (default: two latest)
bin/career linkedin audit [snapshot] [-c client]  # rubric-score a snapshot (default: latest)
bin/career linkedin jd <jobs-url|job-id> [-c client]  # snapshot a job post (manifest kind: job)
bin/career linkedin keywords [variant] [-c client]  # JD keyword corpus, marked against the CV text
bin/career linkedin benchmark <snap-dir>...  # target model from reference-profile captures (ad-hoc out-dirs)

bin/career cv letter <jd-snapshot> [variant] [-c client]  # grounded pack for a cover letter (facts, matched JD language, unbacked terms, scaffold)
bin/career cv version <variant> <jd-snapshot> [--id X] [-c client]  # build + freeze an immutable cut: applications/<company>/<vacancy-id>-<title>/v<N>/
                                          # (variant.yml, cv.rendercv.yaml, CV.pdf, CV.md, REVIEW.md skeleton) + a VERSIONS.md row; refuses a 2-page build

bin/career apply add <jd-snapshot> [--variant v] [--version vN] [--id X] [--reapply] [-c client]  # record an application (company/role read from the capture; --version = the frozen cut sent)
                                          # row id = the posting's vacancy id (jobId); --id when the capture has none;
                                          # the same posting twice is refused unless --reapply (id gets a -2 suffix)
bin/career apply list [--status s] [-c client]  # the ledger (+ derived days-quiet / chase count)
bin/career apply set <vacancy-id> --status sent|replied|interview|rejected|ghosted [--followup DATE]
bin/career apply set <vacancy-id> --chased [DATE]  # record a chase (notes marker); restarts the follow-up clock
bin/career apply followup [--on DATE] [-c client]  # what is due to chase, most overdue first

bin/career doctor [-c client]  # preflight: python, uv/uvx, CDP Chrome, client, design

bin/cv build [variant] [-c client]   # back-compat alias: merge YAML + render -> PDF
bin/cv ats   [variant] [-c client]   # print RenderCV's .md (the exact text an ATS parser sees)
bin/cv match [variant] <jd> [-c client]   # list JD keywords absent from the CV text
uv run generate.py [variant] [-c client]  # merge only -> build/<client>/<variant>.rendercv.yaml
```

`linkedin capture` needs the logged-in CDP Chrome from
`tools/linkedin-scrape/README.md` and also takes `/jobs/view/` URLs (job-post
snapshots). The LinkedIn lane is **read-only** — never automate writes to a
LinkedIn account (contract hard rule).

`variant` defaults to `baseline`; `client` defaults to whatever `clients/.default` names; with no `-c` and no `.default`, commands refuse rather than guess. Requires [`uv`](https://docs.astral.sh/uv/); RenderCV self-fetches via `uvx --from "rendercv[full]" rendercv` on first run (needs internet once). **Single stack: Python** (decided 2026-08-19) — every tool is Python (`uv` scripts; the scraper declares its `playwright` dep inline), with bash only as thin CLI glue (`bin/career`, `bin/cv`). Each `tools/<dir>` carries its own tests (`python3 -m unittest discover -s tools/<dir>`); the CV engine's live beside it at the repo root (`python3 -m unittest test_generate`).

## Architecture

The CV engine is a **three-layer split** that RenderCV itself has no concept of — the one-profile/many-variants overlay is exactly what this repo adds on top of the engine. Layers are per-client under `clients/<client>/`, except the shared look:

| Layer | File | Role |
|-------|------|------|
| **Truth** | `clients/<client>/profile.yml` | Facts stated once: name, contacts, keyed experience, education, default skills. Stable across applications. |
| **Framing** | `clients/<client>/variants/<role>.yml` | Per-role: selection, order, and prose overrides. Everything optional; omitted keys fall back to profile. |
| **Look** | `data/design.yaml` | Shared RenderCV `design` block. Applied to every variant; a client may override with `clients/<client>/design.yaml`. |

`generate.py` resolves the client (`-c`, else `clients/.default`), then: deep-copies that client's profile, overlays the variant (`merge()`), translates the authoring schema into a RenderCV input file (`to_rendercv()`), and RenderCV renders it to PDF + Markdown. **The RenderCV Markdown *is* the ATS text** — that's why `ats`/`match` read from `build/<client>/<variant>/*_CV.md`.

Beyond the CV engine, a client dir also holds `captures/` (dated LinkedIn snapshots — `<ISO-timestamp>/` dirs with a `manifest.json`, append-only evidence; legacy flat captures are wrapped as a snapshot with `"legacy": true`) `applications/<company>/<vacancy-id>-<title-kebab>/` (one folder per posting: `VERSIONS.md`, the letter, and immutable `v<N>/` cuts frozen by `career cv version`; see `examples/applications/` for the fabricated layout), and `docs/` (intake, strategy, research). Standalone tooling lives under `tools/`, one directory per verb-family, each with its own tests: `linkedin-scrape/`, `linkedin-diff/`, `linkedin-audit/`, `linkedin-benchmark/`, `jd-intel/` (the `keywords` verb), `career-lint/`, `career-apply/` (the application ledger), `career-letter/`, `career-doctor/`, and `career-cli/` (contract-level tests over `bin/career` itself: the `--json` envelope, exit codes, and the no-client-identities privacy guard).

### `generate.py` internals

- `merge()`: scalar/list keys (`name`, `headline`, `summary`, `contacts`, `skills`, `projects`, `education`, `languages`, `sections`) are **replaced wholesale** by the variant if present. Experience is special: `profile.yml` owns the canonical roles keyed by `key:`; the variant picks order via `experience_order` and patches individual roles via `experience_overrides.<key>` (a shallow `dict.update` per role). Referencing an unknown experience key is a hard error.
- Section builders (`_sec_profile`, `_sec_experience`, …) live in the `BUILDERS` dict keyed by section name (`profile · experience · projects · skills · education · languages`). The `sections:` list controls both **which** sections render and **their order**; empty sections are dropped.
- `_contacts()` maps our flat `contacts` list to RenderCV's `email`/`phone`/`website`/`social_networks` by sniffing the `href` (mailto:, tel:, linkedin.com/in/, github.com/).

To add a new section type, add a builder to `BUILDERS` and reference its name in `sections:`.

## Editing rules (important)

- **Edit data, never the generated output.** `build/**/*.rendercv.yaml` and `build/**/*.typ` are generated — regenerate from YAML, never hand-edit.
- Facts go in `clients/<client>/profile.yml`; only framing/prose goes in that client's variants.
- `examples/profile.example.yml` is the schema documented with **fabricated** data. Keep it in sync when the schema changes.
- **Never write `" - "` (space-hyphen-space) inside a bullet.** RenderCV treats it as a new list
  item and splits that bullet into two, in the rendered PDF *and* in the ATS Markdown. Use a comma,
  a semicolon, or a rewrite instead. The same string is fine in `summary` and in `location`, which
  are not list items. `generate.py` enforces this and fails the build naming the offending bullets.
- **A bullet holding `": "` (colon-space) must be quoted.** To YAML a plain scalar with `": "`
  inside is a one-key mapping, not text; unguarded, RenderCV dies with an opaque `KeyError`.
  `generate.py` fails the build naming the bullet. Quote it, or use a comma or a semicolon.
- **Keep CV text plain ASCII.** `generate.py` silently deletes invisible controls
  (zero-width, bidi, soft hyphen, variation selectors) and folds exotic spaces (NBSP,
  thin, narrow-NBSP) to `U+0020` across every rendered field, then **hard-errors** on a
  non-Latin lookalike (Cyrillic `а` in "Manager", fullwidth `Ａ`) - an ATS keyword
  search never matches those, and `career cv match` cannot see the problem either since
  it reads the same text. Model-drafted YAML is where they come from; retype the word.
- To restyle everything, edit `data/design.yaml` (shared); for one client only, add `clients/<client>/design.yaml`. Full option list: `uvx --from "rendercv[full]" rendercv new "x" --theme sb2nov`.

## Code/data privacy split

The **tool** is publishable; the **content** is not. Enforced by `.gitignore`:

- **Never committed:** the entire `clients/` tree (profiles, variants, scraped `captures/`, `docs/` — and the client *directory name* itself is an identity), plus `build/`.
- **Safe to commit:** `generate.py`, `bin/`, `data/design.yaml`, `tools/` code, `.claude/skills/`, `examples/`, docs. `examples/profile.example.yml` (fabricated) is the committed schema/fidelity anchor.

See `PRIVATE.md` for the full contract.

## Mandatory gates

Green locally before any PR — CI runs the same three and none soft-fails:

```bash
ruff check .                                       # correctness rules only (.ruff.toml: F + E9)
python3 -m unittest test_generate                  # the CV engine
for d in tools/*/; do python3 -m unittest discover -s "$d"; done   # every tool suite
```

CI adds a render smoke over `examples/profile.example.yml` (needs network for
RenderCV; not part of the local hook). Install the local wall once per clone:

```bash
git config core.hooksPath .githooks   # pre-commit = ruff + both unittest gates
```

## Conventions (ecosystem-standard)

Per the lifekit [repo gold standard](https://github.com/lifekit-hq/.github/blob/main/REPO-STANDARD.md):

- **Branch**: `<type>/<issue#>-<slug>` (e.g. `feat/20-apply-ledger`); create via
  `gh issue develop <n>`.
- **Commits / PR titles**: conventional commits; scope = tool or lane where it
  helps (`feat(apply): …`, `fix(linkedin-scrape): …`).
- **PR body**: what + why, then a **Validation** section stating exactly what
  was run and green.
- **Issues**: imperative title, no priority prefix — priority lives in the
  `P1`/`P2` label. P1 issues carry acceptance criteria; P2/P3 stay one-liners
  until promoted.
- **Milestones**: `M<n> — <outcome>`, named for the outcome, never a date.
- Main is protected in spirit: all changes land via squash-merged PR, CI green
  first.
- Only `README.md` and `CLAUDE.md` belong at the repo root — durable docs live
  in `docs/` (destination/milestones: `docs/PLAN.md`); session artifacts don't
  get files.

### Gold-standard divergences

- **`PRIVATE.md` stays at the root** (a third root doc): it is the privacy
  contract for the gitignored `clients/` tree, referenced by `.gitignore`, the
  code, and the privacy tests. Privacy failure is this repo's one unrecoverable
  mistake, so the contract stays unmissable at the root rather than in `docs/`.
- **No release-please / Weekly Release / publish job** (§5): career-kit
  publishes no artifact — it is a local tool, has no package, no CHANGELOG, and
  cuts no releases. Revisit if it ever ships one.
- **No format check** (§6): the lint gate is deliberately correctness-only
  (`.ruff.toml`, F + E9). Adopting `ruff format`/full style rules would rewrite
  most of `tools/`; do it as its own change if ever, never silently in CI.

## The tailor-cv skill

`.claude/skills/tailor-cv/SKILL.md` (project-scoped, so `/tailor-cv` is available when working in this repo) orchestrates the tailoring loop (JD + facts → variant YAML → PDF → ATS check). Before drafting any variant it reads `~/memory/domains/career.md` for **hard truth constraints and honest-framing rules** (e.g. what NOT to claim about a given employer). The governing rule: truth over keyword-matching — every claim must survive a technical interview and a real work-trial. Stretch framing is fine; fabrication is not.
