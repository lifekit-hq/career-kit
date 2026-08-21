---
name: tailor-cv
description: >-
  Tailor Denys's CV to a specific job description using career-kit. Use when
  Denys says "tailor my CV for <role/company>", "make a CV variant", "/tailor-cv",
  pastes a JD and asks for a matching CV, or wants to iterate on an existing
  variant. Produces a new/updated clients/<client>/variants/<name>.yml, renders
  the PDF, and ATS-checks it — never edits generated output by hand.
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
3. **Build**: `bin/career cv build <name> -c <client>` → `build/<client>/<name>/..._CV.pdf`.
4. **ATS-check**: `bin/career cv ats <name> -c <client>` (RenderCV's Markdown = what
   an ATS sees) and, with the JD saved, `bin/career cv match <name> jd.txt -c <client>`
   (missing keywords → address only if truthful). When the JD came from a capture,
   `bin/career linkedin keywords <name> -c <client>` is richer.
5. **Consistency-check**: `bin/career cv lint <name> -c <client>` cross-checks the CV
   against the latest LinkedIn snapshot. Recruiters do this by hand; a mismatch in a
   role title or a date is the cheapest kind of credibility loss.
6. **Show the PDF** + the missing-keyword list to Denys. Iterate on the YAML.
7. Keep it **one page** unless told otherwise.

## After the CV: the rest of the application
- **Cover letter**: `bin/career cv letter <jd-snapshot> <name> -c <client>` returns the
  facts the letter may stand on, the JD language the CV already backs, and the language
  nothing backs. **You** write the prose from that pack - the verb deliberately does not,
  and nothing in the letter may rest on a term in `unevidenced`.
- **Record it**: `bin/career apply add <jd-snapshot> --variant <name> -c <client>` once
  the application is actually sent. Only record what was really submitted - a ledger
  that invents history is worse than no ledger.
- **Chase it**: `bin/career apply followup -c <client>`.
- If a verb fails oddly, `bin/career doctor -c <client>` says what is missing.

## Rules
- Truth over keyword-matching. Every claim must survive a technical interview and
  a real work-trial. Stretch framing is fine; fabrication is not.
- Facts belong in the client's `profile.yml`; only framing/prose goes in the variant.
- Never hand-edit anything under `build/` — it is generated (RenderCV/Typst: `.typ`,
  `.rendercv.yaml`, the PDF and the ATS `.md`). Regenerate from YAML.
- **Never write `" - "` (space-hyphen-space) inside a bullet.** RenderCV parses it as a
  new list item and silently splits the bullet in two, in the PDF *and* the ATS text.
  Use a comma, a semicolon, or a rewrite. `generate.py` hard-fails the build on it.
- **Keep the YAML plain ASCII.** Model-drafted prose carries no-break spaces, curly
  quotes and zero-width characters; a non-Latin lookalike (Cyrillic `а` in "Manager")
  makes the keyword unmatchable to an ATS. The build folds the invisible ones and
  hard-fails on lookalikes - if it does, retype the word rather than pasting again.
