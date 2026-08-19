# linkedin-scrape

Free LinkedIn profile → structured data. No paid API, no OCR, no dead libraries.

## Why this exists

The obvious routes to "parse a LinkedIn profile as data" are all closed or broken:

- **Official API** — does not expose arbitrary member profiles (only the authenticated user's own basics).
- **`linkedin-api` (OSS)** — latest release (2.3.1) is broken: its `get_profile` endpoint (`/identity/profiles/{id}/profileView`) now returns **HTTP 410 Gone**. Its skills/contact endpoints too.
- **Paid scrapers** (Apify, Bright Data) — work, but cost money.

What *does* work for free and stays durable: drive an **already-logged-in browser**, visit each profile section, and read the **rendered text straight from the DOM** — exact, no OCR loss. LinkedIn keeps killing its undocumented APIs and obfuscating its markup, but the rendered text is stable.

## The two-step method

1. **Extract (this tool, deterministic, free):** navigates each section in your Chrome, saves per-section rendered text (`raw/*.txt`) + full-page screenshots (`raw/*.png`), and concatenates the text into `profile.raw.txt`.
2. **Parse (an LLM pass, flexible):** feed `profile.raw.txt` to an LLM to get clean structured JSON. An LLM reading exact text is robust to LinkedIn's shifting layout in a way a hardcoded parser is not — and it handles Cyrillic/emoji correctly. Screenshots are only a human artifact / vision fallback, **never** the parse source (OCR would lose fidelity the DOM text already gives you).

## Setup

Python via [`uv`](https://docs.astral.sh/uv/) - the script declares its own
dependency (`playwright`) and uv fetches it on first run. No install step. A
Chrome/Chromium binary is only needed to LAUNCH the logged-in browser below
(the script itself just connects over CDP).

### One-time: launch a headed Chrome and log in once

The session persists in the user-data dir, so you log in a single time.

```bash
"$CHROME_BIN" --user-data-dir="$HOME/.cache/pw-li-profile" \
    --remote-debugging-port=9777 --no-first-run about:blank &
# Log into LinkedIn in that window. Leave it running.
```

## Usage

```bash
uv run li_scrape.py <profile-url-or-public-id> [outDir]
uv run li_scrape.py <jobs-view-url-or-job-id>  [outDir]

# examples
uv run li_scrape.py https://www.linkedin.com/in/some-person-12345/
uv run li_scrape.py some-person-12345 ./out-some-person
uv run li_scrape.py https://www.linkedin.com/jobs/view/4012345678/
```

Accepts a full profile URL (any section), a bare public ID, a `/jobs/view/`
URL, or a bare numeric job id. Default `outDir` is `./out-<publicId>/` (or
`./out-job-<id>/`). Job mode writes `raw/job.txt` + `raw/job.png` + `job.json`
(schema `li-scrape-job/1`: title, company, location, description).

### Output

```
out-<publicId>/
  raw/profile.txt      raw/profile.png        top card + activity
  raw/experience.txt   raw/experience.png
  raw/education.txt    raw/education.png
  raw/skills.txt       raw/skills.png
  raw/interests.txt    raw/interests.png
  profile.raw.txt      ← concatenated text; hand THIS to an LLM for structured JSON
  profile.json         ← minimal stub (publicId/source); the LLM pass fills the rest
```

## Guardrails / etiquette

- **Auth check:** if it hits `authwall`/`login`, it exits with a clear message instead of writing garbage.
- **Rate discipline:** human-paced delays, one profile at a time. LinkedIn's anti-abuse guard is real — observed flipping `200 → 401` on rapid repeated requests. This uses **your** account; don't loop it over many profiles.
- **Privacy:** scraped output is third-party personal data. `out-*/` is gitignored — never commit it. Only this tool's code is tracked.

## Tests

The pure text/URL/parse helpers are covered by a stdlib `unittest` suite that
never imports playwright (the runner imports it lazily):

```bash
python3 -m unittest discover -s tools/linkedin-scrape
```

The extractor also writes `profile.json` (schema `li-scrape/1`) as a **best-effort** structured parse of the rendered text (positions, education, skills, contact email). It's a heuristic over shifting markup — hand `profile.raw.txt` to an LLM when you need a rich, robust parse.

## Limitations

- Requires a logged-in session (LinkedIn shows nothing useful anonymously).
- The built-in `profile.json` parser is intentionally minimal — LinkedIn's markup is obfuscated and shifts between builds, so the durable parse path is the LLM pass over `profile.raw.txt`, not brittle DOM selectors.
- Contact-info (email) lives behind a modal, not in the section pages; capture it separately if you need it.
