# PRIVATE — what must never be committed

career-kit follows the lifekit code/data split: the **tool** is public-able,
the **content** is not. This file is the contract (mirrors lifekit-stack).

## Never commit
- `clients/` — the entire tree. career-kit is a multi-client workbench; each
  person lives under `clients/<name>/`. This holds:
  - `profile.yml` — real personal facts (name, phone, email, employers, dates).
  - `variants/*.yml` — per-role framing that reveals job-search targeting
    (which company, which role, tailored prose).
  - `captures/` — scraped LinkedIn data (third-party personal data).
  - `docs/` — intake, strategy, research notes.
  The **directory name itself is a client's identity**, so the whole `clients/`
  tree is gitignored — not individual files inside it.
- `build/` — rendered `.tex`/`.pdf` carry the same content as the data.

## Safe to commit (the tool)
- `generate.py`, `bin/`, `data/design.yaml` (shared look, no personal facts),
  `.claude/skills/`, `examples/`, docs.
- `examples/profile.example.yml` — **fabricated** data showing the schema. This
  is the committed fidelity/schema anchor now that real client data (including
  the old `baseline.yml`) lives under the ignored `clients/` tree.

Enforced by `.gitignore`. If this ever goes public, add a gitleaks pre-commit
hook as lifekit-stack does before the first push.
