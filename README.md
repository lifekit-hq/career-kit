# career-kit

YAML-driven CV tailoring. One source of truth for your facts; per-role variants
control framing; [RenderCV](https://github.com/rendercv/rendercv) renders
ATS-clean PDFs. Part of the lifekit ecosystem — a local tool/skill, not a
deployed service.

## Why

Tailoring a CV per role shouldn't mean editing a template. The scaffold (who/
where/when) never changes; only the framing does. career-kit separates the two,
and delegates rendering to RenderCV (17k★, MIT) instead of a hand-rolled engine:

| Layer | File | Changes per application? |
|-------|------|--------------------------|
| **Truth** | `data/profile.yml` | No — facts stated once |
| **Framing** | `data/variants/<role>.yml` | Yes — selection, order, prose |
| **Look** | `data/design.yaml` | No — shared RenderCV design |
| **Engine** | RenderCV (via `uvx`) | No — renders any variant |

RenderCV has no notion of "one profile → many variants"; that overlay is what
career-kit adds. `generate.py` merges profile+variant and emits a RenderCV input
file; RenderCV turns it into PDF + Markdown (the Markdown *is* the ATS text).

## Layout

```
generate.py                 merge profile+variant -> RenderCV input YAML
data/                       PRIVATE (gitignored) — your real content
  profile.yml               the scaffold (facts, keyed experience)
  variants/<role>.yml       the framing (select/order/prose overrides)
  design.yaml               shared RenderCV look (sb2nov + Roboto, 1 page)
bin/cv                      build / ats / match driver
.claude/skills/tailor-cv/   the /tailor-cv orchestration skill (project-scoped)
examples/profile.example.yml  the schema, with fake data
build/<variant>/            generated RenderCV output (gitignored)
```

## Usage

```bash
cp examples/profile.example.yml data/profile.yml   # then fill in your facts

bin/cv build baseline        # merge + render -> build/baseline/..._CV.pdf
bin/cv build openai          # a tailored variant
bin/cv ats   openai          # print the text an ATS parser sees (RenderCV .md)
bin/cv match openai jd.txt   # list JD keywords missing from the CV
```

Requires [`uv`](https://docs.astral.sh/uv/). RenderCV runs via
`uvx --from "rendercv[full]" rendercv` — no global install; it self-fetches on
first run.

## Adding / tailoring a variant

Create `data/variants/<role>.yml`. Everything is optional; anything you omit
falls back to `profile.yml`:

```yaml
headline: Software Engineer | Backend & Security
summary: >-
  Rewritten for this role...
experience_order: [ssc, it-innovations, itop]   # select + order roles by key
experience_overrides:
  ssc:
    bullets:
      - Restated for the target JD (truthfully).
sections: [profile, experience, skills, projects, education]   # order + which
```

Keys under `experience_overrides` match the `key:` of each role in
`profile.yml`. Section names map to builders in `generate.py`
(profile · experience · projects · skills · education · languages).

## Restyle everything at once

Edit `data/design.yaml` (margins, fonts, spacing, bullets) — it's the RenderCV
`design` block applied to every variant. Full option list:
`uvx --from "rendercv[full]" rendercv new "x" --theme sb2nov` shows the schema.

## Data / code split

Real content (`data/`, `build/`) is gitignored and never committed. The tool is
publishable as-is. See `PRIVATE.md`.
