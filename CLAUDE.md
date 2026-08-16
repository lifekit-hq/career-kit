# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

career-kit is a YAML-driven CV tailoring tool. It maintains **one source of truth for facts** and layers **per-role framing** on top, then delegates rendering to [RenderCV](https://github.com/rendercv/rendercv) (invoked via `uvx`, not installed globally). It is a local tool/skill, not a deployed service. Part of the lifekit ecosystem.

## Commands

```bash
bin/cv build [variant]        # merge YAML + render -> build/<variant>/..._CV.pdf
bin/cv ats   [variant]        # print RenderCV's .md (the exact text an ATS parser sees)
bin/cv match [variant] <jd>   # list JD keywords absent from the CV text
uv run generate.py [variant]  # merge only -> build/<variant>.rendercv.yaml (no render)
```

`variant` defaults to `baseline`. Requires [`uv`](https://docs.astral.sh/uv/); RenderCV self-fetches via `uvx --from "rendercv[full]" rendercv` on first run (needs internet once). There is no test suite, linter, or build step beyond these.

## Architecture

The core idea is a **three-layer split** that RenderCV itself has no concept of — the one-profile/many-variants overlay is exactly what this repo adds on top of the engine:

| Layer | File | Role |
|-------|------|------|
| **Truth** | `data/profile.yml` | Facts stated once: name, contacts, keyed experience, education, default skills. Stable across applications. |
| **Framing** | `data/variants/<role>.yml` | Per-role: selection, order, and prose overrides. Everything optional; omitted keys fall back to profile. |
| **Look** | `data/design.yaml` | Shared RenderCV `design` block, applied to every variant. |

Data flow: `generate.py` deep-copies the profile, overlays the variant (`merge()`), translates the authoring schema into a RenderCV input file (`to_rendercv()`), and RenderCV renders it to PDF + Markdown. **The RenderCV Markdown *is* the ATS text** — that's why `ats`/`match` read from `build/<variant>/*_CV.md`.

### `generate.py` internals

- `merge()`: scalar/list keys (`name`, `headline`, `summary`, `contacts`, `skills`, `projects`, `education`, `languages`, `sections`) are **replaced wholesale** by the variant if present. Experience is special: `profile.yml` owns the canonical roles keyed by `key:`; the variant picks order via `experience_order` and patches individual roles via `experience_overrides.<key>` (a shallow `dict.update` per role). Referencing an unknown experience key is a hard error.
- Section builders (`_sec_profile`, `_sec_experience`, …) live in the `BUILDERS` dict keyed by section name (`profile · experience · projects · skills · education · languages`). The `sections:` list controls both **which** sections render and **their order**; empty sections are dropped.
- `_contacts()` maps our flat `contacts` list to RenderCV's `email`/`phone`/`website`/`social_networks` by sniffing the `href` (mailto:, tel:, linkedin.com/in/, github.com/).

To add a new section type, add a builder to `BUILDERS` and reference its name in `sections:`.

## Editing rules (important)

- **Edit data, never the generated output.** `build/*.rendercv.yaml` and `build/*.typ` are generated — regenerate from YAML, never hand-edit.
- Facts go in `profile.yml`; only framing/prose goes in variants.
- `examples/profile.example.yml` is the schema documented with **fabricated** data. Keep it in sync when the schema changes.
- To restyle all variants at once, edit `data/design.yaml`. Full option list: `uvx --from "rendercv[full]" rendercv new "x" --theme sb2nov`.

## Code/data privacy split

The **tool** is publishable; the **content** is not. Enforced by `.gitignore`:

- **Never committed:** `data/profile.yml`, `data/variants/*.yml`, `build/`.
- **Exception:** `data/variants/baseline.yml` is committed — it holds no content (defaults only) and serves as the generator fidelity anchor.
- **Safe to commit:** `generate.py`, `bin/`, `.claude/skills/`, `examples/`, docs.

See `PRIVATE.md` for the full contract.

## The tailor-cv skill

`.claude/skills/tailor-cv/SKILL.md` (project-scoped, so `/tailor-cv` is available when working in this repo) orchestrates the tailoring loop (JD + facts → variant YAML → PDF → ATS check). Before drafting any variant it reads `~/memory/domains/career.md` for **hard truth constraints and honest-framing rules** (e.g. what NOT to claim about a given employer). The governing rule: truth over keyword-matching — every claim must survive a technical interview and a real work-trial. Stretch framing is fine; fabrication is not.
