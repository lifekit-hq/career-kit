# PRIVATE — what must never be committed

career-kit follows the lifekit code/data split: the **tool** is public-able,
the **content** is not. This file is the contract (mirrors lifekit-stack).

## Never commit
- `data/profile.yml` — real personal facts (name, phone, email, employers, dates).
- `data/variants/*.yml` — per-role framing that reveals job-search targeting
  (which company, which role, tailored prose). Exception: `baseline.yml`, which
  holds no content (defaults-only) and is kept as the generator fidelity anchor.
- `build/` — rendered `.tex`/`.pdf` carry the same content as the data.

## Safe to commit (the tool)
- `generate.py`, `templates/`, `bin/`, `.claude/skills/`, `examples/`, docs.
- `examples/profile.example.yml` — **fabricated** data showing the schema only.

Enforced by `.gitignore`. If this ever goes public, add a gitleaks pre-commit
hook as lifekit-stack does before the first push.
