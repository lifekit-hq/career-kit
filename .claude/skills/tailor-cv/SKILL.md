---
name: tailor-cv
description: >-
  Tailor Denys's CV to a specific job description using career-kit. Use when
  Denys says "tailor my CV for <role/company>", "make a CV variant", "/tailor-cv",
  pastes a JD and asks for a matching CV, or wants to iterate on an existing
  variant. Produces a new/updated clients/<client>/variants/<name>.yml, renders
  the PDF, and ATS-checks it — never edits LaTeX by hand.
---

# tailor-cv

Orchestrates the career-kit loop: JD + facts → variant YAML → PDF → ATS check.
The tool lives at `~/projects/career-kit`. **Edit data, never the template.**

career-kit is multi-client. First fix the **client** (`-c <name>`, else
whatever `clients/.default` names - with neither, commands refuse rather than
guess). All that client's data lives under `clients/<client>/`, which is
private: never name a client in a file that gets committed.

## Inputs
- A target: company + role, and ideally the JD text (save it to a file for `match`).
- Ground truth (the honest-framing constraints — read BEFORE drafting):
  - **The vault-backed client**: `~/memory/domains/career.md` (targets, and the
    hard list of what NOT to claim), plus `identity.md` and `engineering.md`.
    **Read career.md first** - it names the specific employers and technologies
    that must not be reframed, because that is exactly the fabrication a work
    trial exposes. Those constraints live in the vault, never here: this file is
    committed to a public repo.
  - **Every client**: `clients/<client>/docs/` (intake.md, strategy.md) and their
    `captures/` (scraped LinkedIn). Never claim beyond what those support.

## Steps
1. **Read the client's ground truth** for constraints and honest framing. Confirm
   the target role with the client (via Denys) if ambiguous.
2. **Draft the variant** `clients/<client>/variants/<name>.yml`:
   - `headline`, `summary` — rewritten for the role (prose lives in the variant).
   - `experience_order` — select/order roles by key; drop irrelevant ones.
   - `experience_overrides.<key>.bullets` — restate bullets toward the JD, staying
     truthful to what the person actually did.
   - `sections` — e.g. add `projects` when side-project depth is the leverage.
   - `skills` — regroup/emphasize to hit JD keywords honestly.
3. **Build**: `bin/cv build <name> -c <client>` → `build/<client>/<name>/..._CV.pdf`.
4. **ATS-check**: `bin/cv ats <name> -c <client>` (RenderCV's Markdown = what an ATS
   sees) and, with the JD saved, `bin/cv match <name> jd.txt -c <client>` (missing
   keywords → address only if truthful).
5. **Show the PDF** + the missing-keyword list to Denys. Iterate on the YAML.
6. Keep it **one page** unless told otherwise.

## Rules
- Truth over keyword-matching. Every claim must survive a technical interview and
  a real work-trial. Stretch framing is fine; fabrication is not.
- Facts belong in the client's `profile.yml`; only framing/prose goes in the variant.
- Never hand-edit `build/**/*.tex` — regenerate from YAML.
