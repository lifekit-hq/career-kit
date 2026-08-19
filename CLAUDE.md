# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

career-kit is a **multi-client, end-to-end career workbench**: research → strategy → optimized LinkedIn → ATS-ready CV, general enough to serve any person. Its CV engine is YAML-driven — one source of truth for facts per client, per-role framing layered on top — delegating rendering to [RenderCV](https://github.com/rendercv/rendercv) (invoked via `uvx`, not installed globally). It is a local tool/skill, not a deployed service. Part of the lifekit ecosystem.

Each person is a **client** under `clients/<name>/` (e.g. `clients/denys-sychov/`, `clients/yelyzaveta-morozova/`). The whole `clients/` tree is private (see the privacy split below).

## Commands

`bin/career` is the executor CLI — one precise chunk of career work per verb,
honoring the contract in `docs/CONTRACT.md` (JSON envelope via `--json`, exit
codes, per-client resolution). Destination/milestones: `PLAN.md`; backlog:
GitHub issues.

```bash
bin/career cv build|ats|match [...] [-c client] [--json]  # CV lane (delegates to bin/cv)
bin/career cv lint [variant] [-c client]  # cross-check CV vs latest LinkedIn snapshot (exit 1 on mismatch)
bin/career linkedin capture <url|id> [-c client]  # snapshot -> clients/<c>/captures/<ISO>/ (+manifest)
bin/career linkedin diff [snapA snapB] [-c client]  # compare snapshots (default: two latest)
bin/career linkedin audit [snapshot] [-c client]  # rubric-score a snapshot (default: latest)
bin/career linkedin jd <jobs-url|job-id> [-c client]  # snapshot a job post (manifest kind: job)
bin/career linkedin keywords [variant] [-c client]  # JD keyword corpus, marked against the CV text
bin/career linkedin benchmark <snap-dir>...  # target model from reference-profile captures (ad-hoc out-dirs)

bin/cv build [variant] [-c client]   # back-compat alias: merge YAML + render -> PDF
bin/cv ats   [variant] [-c client]   # print RenderCV's .md (the exact text an ATS parser sees)
bin/cv match [variant] <jd> [-c client]   # list JD keywords absent from the CV text
uv run generate.py [variant] [-c client]  # merge only -> build/<client>/<variant>.rendercv.yaml
```

`linkedin capture` needs the logged-in CDP Chrome from
`tools/linkedin-scrape/README.md` and also takes `/jobs/view/` URLs (job-post
snapshots). The LinkedIn lane is **read-only** — never automate writes to a
LinkedIn account (contract hard rule).

`variant` defaults to `baseline`; `client` defaults to `clients/.default` (currently `denys-sychov`). Requires [`uv`](https://docs.astral.sh/uv/); RenderCV self-fetches via `uvx --from "rendercv[full]" rendercv` on first run (needs internet once). **Single stack: Python** (decided 2026-08-19) — every tool is Python (`uv` scripts; the scraper declares its `playwright` dep inline), with bash only as thin CLI glue (`bin/career`, `bin/cv`). The CV engine has no test suite; each `tools/linkedin-*` dir carries its own: `python3 -m unittest discover -s tools/<dir>`.

## Architecture

The CV engine is a **three-layer split** that RenderCV itself has no concept of — the one-profile/many-variants overlay is exactly what this repo adds on top of the engine. Layers are per-client under `clients/<client>/`, except the shared look:

| Layer | File | Role |
|-------|------|------|
| **Truth** | `clients/<client>/profile.yml` | Facts stated once: name, contacts, keyed experience, education, default skills. Stable across applications. |
| **Framing** | `clients/<client>/variants/<role>.yml` | Per-role: selection, order, and prose overrides. Everything optional; omitted keys fall back to profile. |
| **Look** | `data/design.yaml` | Shared RenderCV `design` block. Applied to every variant; a client may override with `clients/<client>/design.yaml`. |

`generate.py` resolves the client (`-c`, else `clients/.default`), then: deep-copies that client's profile, overlays the variant (`merge()`), translates the authoring schema into a RenderCV input file (`to_rendercv()`), and RenderCV renders it to PDF + Markdown. **The RenderCV Markdown *is* the ATS text** — that's why `ats`/`match` read from `build/<client>/<variant>/*_CV.md`.

Beyond the CV engine, a client dir also holds `captures/` (dated LinkedIn snapshots — `<ISO-timestamp>/` dirs with a `manifest.json`, append-only evidence; legacy flat captures are wrapped as a snapshot with `"legacy": true`) and `docs/` (intake, strategy, research). Standalone tooling lives under `tools/` (`tools/linkedin-scrape/`, `tools/linkedin-diff/`).

### `generate.py` internals

- `merge()`: scalar/list keys (`name`, `headline`, `summary`, `contacts`, `skills`, `projects`, `education`, `languages`, `sections`) are **replaced wholesale** by the variant if present. Experience is special: `profile.yml` owns the canonical roles keyed by `key:`; the variant picks order via `experience_order` and patches individual roles via `experience_overrides.<key>` (a shallow `dict.update` per role). Referencing an unknown experience key is a hard error.
- Section builders (`_sec_profile`, `_sec_experience`, …) live in the `BUILDERS` dict keyed by section name (`profile · experience · projects · skills · education · languages`). The `sections:` list controls both **which** sections render and **their order**; empty sections are dropped.
- `_contacts()` maps our flat `contacts` list to RenderCV's `email`/`phone`/`website`/`social_networks` by sniffing the `href` (mailto:, tel:, linkedin.com/in/, github.com/).

To add a new section type, add a builder to `BUILDERS` and reference its name in `sections:`.

## Editing rules (important)

- **Edit data, never the generated output.** `build/**/*.rendercv.yaml` and `build/**/*.typ` are generated — regenerate from YAML, never hand-edit.
- Facts go in `clients/<client>/profile.yml`; only framing/prose goes in that client's variants.
- `examples/profile.example.yml` is the schema documented with **fabricated** data. Keep it in sync when the schema changes.
- To restyle everything, edit `data/design.yaml` (shared); for one client only, add `clients/<client>/design.yaml`. Full option list: `uvx --from "rendercv[full]" rendercv new "x" --theme sb2nov`.

## Code/data privacy split

The **tool** is publishable; the **content** is not. Enforced by `.gitignore`:

- **Never committed:** the entire `clients/` tree (profiles, variants, scraped `captures/`, `docs/` — and the client *directory name* itself is an identity), plus `build/`.
- **Safe to commit:** `generate.py`, `bin/`, `data/design.yaml`, `tools/` code, `.claude/skills/`, `examples/`, docs. `examples/profile.example.yml` (fabricated) is the committed schema/fidelity anchor.

See `PRIVATE.md` for the full contract.

## The tailor-cv skill

`.claude/skills/tailor-cv/SKILL.md` (project-scoped, so `/tailor-cv` is available when working in this repo) orchestrates the tailoring loop (JD + facts → variant YAML → PDF → ATS check). Before drafting any variant it reads `~/memory/domains/career.md` for **hard truth constraints and honest-framing rules** (e.g. what NOT to claim about a given employer). The governing rule: truth over keyword-matching — every claim must survive a technical interview and a real work-trial. Stretch framing is fine; fabrication is not.
