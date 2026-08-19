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

Needs [`playwright-core`](https://www.npmjs.com/package/playwright-core) and a Chrome/Chromium binary.

```bash
cd tools/linkedin-scrape
npm install                      # installs playwright-core

# Find a Chrome binary (any of these usually exist):
#   ~/.cache/puppeteer/chrome/*/chrome-linux64/chrome
#   ~/.cache/ms-playwright/chromium-*/chrome-linux/chrome
#   /usr/bin/google-chrome
export CHROME_BIN=/path/to/chrome
```

### One-time: launch a headed Chrome and log in once

The session persists in the user-data dir, so you log in a single time.

```bash
"$CHROME_BIN" --user-data-dir="$HOME/.cache/pw-li-profile" \
    --remote-debugging-port=9777 --no-first-run about:blank &
# Log into LinkedIn in that window. Leave it running.
```

## Usage

```bash
CHROME_BIN=/path/to/chrome node li-scrape.js <profile-url-or-public-id> [outDir]

# examples
node li-scrape.js https://www.linkedin.com/in/some-person-12345/
node li-scrape.js some-person-12345 ./out-some-person
```

Accepts a full profile URL (any section) or a bare public ID. Default `outDir` is `./out-<publicId>/`.

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

The pure text/URL/parse helpers are covered by a unit suite that needs **zero npm install** — it uses Node's built-in `node:test` and never loads `playwright-core` (the browser runner only executes when the file is run directly):

```bash
cd tools/linkedin-scrape
npm test          # or: node --test
```

The extractor now also writes `profile.json` automatically as a **best-effort** structured parse of the rendered text (positions, education, skills, contact email). It's a heuristic over shifting markup — hand `profile.raw.txt` to an LLM when you need a rich, robust parse.

## Limitations

- Requires a logged-in session (LinkedIn shows nothing useful anonymously).
- The built-in `profile.json` parser is intentionally minimal — LinkedIn's markup is obfuscated and shifts between builds, so the durable parse path is the LLM pass over `profile.raw.txt`, not brittle DOM selectors.
- Contact-info (email) lives behind a modal, not in the section pages; capture it separately if you need it.
