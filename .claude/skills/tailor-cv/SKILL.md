---
name: tailor-cv
description: >-
  Tailor Denys's CV to a specific job description using career-kit. Use when
  Denys says "tailor my CV for <role/company>", "make a CV variant", "/tailor-cv",
  pastes a JD and asks for a matching CV, or wants to iterate on an existing
  variant. Produces a new/updated data/variants/<name>.yml, renders the PDF, and
  ATS-checks it — never edits LaTeX by hand.
---

# tailor-cv

Orchestrates the career-kit loop: JD + facts → variant YAML → PDF → ATS check.
The tool lives at `~/projects/career-kit`. **Edit data, never the template.**

## Inputs
- A target: company + role, and ideally the JD text (save it to a file for `match`).
- Ground truth: `~/memory/domains/career.md` (targets, honest framing, what NOT
  to claim), `identity.md`, `engineering.md`. **Read career.md first** — it holds
  hard constraints (e.g. SS&C is mostly frontend + a .NET proxy API; do NOT frame
  it as privacy-engineering work — that's fabrication the work-trial would expose).

## Steps
1. **Read** `career.md` for constraints and the honest framing rules. Confirm the
   target role with Denys if ambiguous.
2. **Draft the variant** `data/variants/<name>.yml`:
   - `headline`, `summary` — rewritten for the role (prose lives in the variant).
   - `experience_order` — select/order roles by key; drop irrelevant ones.
   - `experience_overrides.<key>.bullets` — restate bullets toward the JD, staying
     truthful to what Denys actually did.
   - `sections` — e.g. add `projects` when side-project depth is the leverage.
   - `skills` — regroup/emphasize to hit JD keywords honestly.
3. **Build**: `bin/cv build <name>` → `build/<name>/..._CV.pdf` (RenderCV).
4. **ATS-check**: `bin/cv ats <name>` (RenderCV's Markdown = what an ATS sees)
   and, with the JD saved, `bin/cv match <name> jd.txt` (missing keywords →
   address only if truthful).
5. **Show Denys** the PDF + the missing-keyword list. Iterate on the YAML.
6. Keep it **one page** unless Denys says otherwise.

## Rules
- Truth over keyword-matching. Every claim must survive a technical interview and
  a real work-trial. Stretch framing is fine; fabrication is not.
- Facts belong in `profile.yml`; only framing/prose goes in the variant.
- Never hand-edit `build/*.tex` — regenerate from YAML.
