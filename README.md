# career-kit

A multi-client, end-to-end career workbench: research → strategy → optimized
LinkedIn → ATS-ready CV → application, tracked. YAML is the single source of
truth for a person's facts; per-role variants control framing;
[RenderCV](https://github.com/rendercv/rendercv) renders ATS-clean PDFs. Part of
the lifekit ecosystem — a local tool/skill, not a deployed service.

## Why

Tailoring a CV per role shouldn't mean editing a template. The scaffold (who/
where/when) never changes; only the framing does. career-kit separates the two,
and delegates rendering to RenderCV (MIT) instead of a hand-rolled engine:

| Layer | File | Changes per application? |
|-------|------|--------------------------|
| **Truth** | `clients/<client>/profile.yml` | No — facts stated once |
| **Framing** | `clients/<client>/variants/<role>.yml` | Yes — selection, order, prose |
| **Look** | `data/design.yaml` | No — shared RenderCV design |
| **Engine** | RenderCV (via `uvx`) | No — renders any variant |

RenderCV has no notion of "one profile → many variants"; that overlay is what
career-kit adds. `generate.py` merges profile+variant and emits a RenderCV input
file; RenderCV turns it into PDF + Markdown (the Markdown *is* the ATS text).

## Layout

```
bin/career                     the executor CLI - every verb, JSON in/out
bin/cv                         back-compat alias for the cv lane
generate.py                    merge profile+variant -> RenderCV input YAML
data/design.yaml               shared RenderCV look (committed)
docs/CONTRACT.md               the contract every verb honors
tools/<verb-family>/           one dir per tool, each with its own tests
examples/profile.example.yml   the schema, with fabricated data
.claude/skills/tailor-cv/      the /tailor-cv orchestration skill

clients/<client>/              PRIVATE (gitignored) - one dir per person
  profile.yml                  the scaffold (facts, keyed experience)
  variants/<role>.yml          the framing (select/order/prose overrides)
  captures/<ISO>/              dated LinkedIn + job-post snapshots
  applications.yml             the application ledger
  docs/                        intake, strategy, research
build/<client>/<variant>/      generated output (gitignored)
```

## Usage

```bash
mkdir -p clients/<name> && cp examples/profile.example.yml clients/<name>/profile.yml
echo <name> > clients/.default          # or pass -c <name> to every command

bin/career doctor                            # preflight: what's installed, what's missing

bin/career cv build openai                   # merge + render -> build/<client>/openai/..._CV.pdf
bin/career cv ats   openai                   # the text an ATS parser sees (RenderCV .md)
bin/career cv match openai jd.txt            # JD keywords missing from the CV
bin/career cv lint  openai                   # cross-check the CV against the LinkedIn snapshot

bin/career linkedin capture <profile-url>    # snapshot a profile into the capture store
bin/career linkedin jd <jobs-url>            # snapshot a job post
bin/career linkedin keywords openai          # JD keyword corpus, marked against the CV
bin/career linkedin diff                     # compare the two latest snapshots
bin/career linkedin audit                    # rubric-score the latest profile snapshot

bin/career cv letter <jd-snapshot> openai    # grounded input pack for a cover letter
bin/career apply add <jd-snapshot> --variant openai   # record an application you sent
bin/career apply followup                    # what's due to chase
```

Every verb takes `-c <client>` and `--json`. With `--json` it prints exactly one
envelope object; exit 2 is a usage error, 1 is an operational failure. There is
no default client fallback — with no `-c` and no `clients/.default`, commands
refuse rather than guess which person they are building a CV for.

Requires [`uv`](https://docs.astral.sh/uv/). RenderCV runs via
`uvx --from "rendercv[full]" rendercv` — no global install; it self-fetches on
first run.

## Adding / tailoring a variant

Create `clients/<client>/variants/<role>.yml`. Everything is optional; anything
you omit falls back to `profile.yml`:

```yaml
headline: Software Engineer | Backend & Platform
summary: >-
  Rewritten for this role...
experience_order: [acme, globex]        # select + order roles by key
experience_overrides:
  acme:
    bullets:
      - Restated for the target JD (truthfully).
sections: [profile, experience, skills, projects, education]   # order + which
```

Keys under `experience_overrides` match the `key:` of each role in
`profile.yml`. Section names map to builders in `generate.py`
(profile · experience · projects · skills · education · languages).

Two rules the build enforces, because both fail invisibly in the YAML and ship
straight to a recruiter:

- **Never write `" - "` inside a bullet.** RenderCV parses it as a new list item
  and splits the bullet in two, in the PDF *and* the ATS text.
- **Keep the text plain ASCII.** Invisible and exotic-space characters are
  folded automatically; a non-Latin lookalike (a Cyrillic `а` in "Manager")
  hard-fails the build, because an ATS keyword search never matches it.

## Restyle everything at once

Edit `data/design.yaml` (margins, fonts, spacing, bullets) — the RenderCV
`design` block applied to every variant. A single client can override it with
`clients/<client>/design.yaml`. Full option list:
`uvx --from "rendercv[full]" rendercv new "x" --theme sb2nov`.

## Data / code split

The tool is publishable; the content is not. The whole `clients/` tree and
`build/` are gitignored and never committed — **a client's directory name is
itself an identity**, so it must not appear in a committed file either. That
rule is enforced by a test (`tools/career-cli/test_privacy.py`), not just
documented. See `PRIVATE.md`.

## Tests

```bash
python3 -m unittest test_generate                 # the CV engine
for d in tools/*/; do python3 -m unittest discover -s "$d"; done
```

CI runs both on every push and PR, plus a render smoke test over
`examples/profile.example.yml` — the only profile it can see, since `clients/`
is private.
