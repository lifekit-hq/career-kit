# career-kit
A multi-client career workbench driven from a local CLI (`bin/career`): YAML facts plus per-role framing render ATS-clean CVs, LinkedIn and job-post snapshots are captured and analysed, and applications are tracked. The glossary covers the tool's own nouns (layers, lanes, snapshots, frozen cuts, ledger); it deliberately contains no client data.

## Language

**Client**:
One person served by the workbench, held under `clients/<name>/`. Every command operates on exactly one client, resolved from `-c` or `clients/.default`.

**Data root**:
The directory that holds `clients/` and `build/`: `$CAREER_KIT_HOME` when set, else the checkout. It keeps the private tree out of the repo.

**Truth**:
The layer `clients/<client>/profile.yml`: facts stated once (contacts, keyed experience, education, default skills) that do not change per application.
_Avoid_: scaffold (used as a synonym in docs)

**Profile**:
The `profile.yml` file that is the Truth layer. Its experience roles are keyed by `key:`.

**Framing**:
The layer `clients/<client>/variants/<role>.yml`: per-role selection, order and prose overrides; anything omitted falls back to the profile.

**Variant**:
One framing file for a target role (`baseline` by default), carrying `headline`, `summary`, `experience_order`, `experience_overrides` and `sections`.

**Look**:
The shared RenderCV design block `data/design.yaml`, applied to every variant (a client may override it).

**Lane**:
A domain of career work in the command grammar `career <lane> <verb>`: `cv`, `linkedin`, `apply`, `jd` implemented; `portfolio` and `strategy` reserved.

**Verb**:
One precise, agent-callable chunk of work within a lane (`cv build`, `apply followup`). A verb never grows modes; new behaviour is a new verb.

**Executor contract**:
`docs/CONTRACT.md`: the rules every verb honours (JSON envelope, exit codes, per-client resolution, hard rules).

**Envelope**:
The single JSON object a verb prints with `--json` (`ok`, `lane`, `verb`, `client`, `data`, `error`). Exit 0 is success, 1 operational failure, 2 usage error.

**Built CV**:
The rendered output under `build/<client>/<variant>/` (PDF and RenderCV Markdown) that comparing verbs (`cv letter`, `cv ats`, `cv match`, `linkedin keywords`) require first.

**ATS text**:
The RenderCV Markdown of a built CV, the exact text an applicant-tracking parser sees.

**Snapshot**:
A dated, immutable, append-only capture under `clients/<c>/captures/<ISO>/` with a `manifest.json`; its `kind` is `profile` or `job`.
_Avoid_: capture (also used for the same directory and the act)

**Job snapshot**:
A snapshot of kind `job`: a job posting captured by `linkedin jd` or `jd add`, referred to as the JD snapshot.

**Vacancy id**:
The posting's own id (`jobId`, or `ashby-<id8>`, `lever-<id8>`, a Greenhouse number) that keys an application; the tool never mints one.

**Forbidden claims**:
An optional per-client `forbidden_claims.yml` of phrases the CV must never contain; a build that holds one fails.

**Cut**:
An immutable frozen version `v<N>/` of the CV for one posting, written by `cv version` and never written twice; a build that is not one page is refused.
_Avoid_: version (the verb and `VERSIONS.md` use it for the same thing)

**Verdict**:
The review outcome recorded on a cut: `rejected`, `submittable`, or `confirm` (stored as submittable with confirmations), written to `VERSIONS.md` and `REVIEW.md` together.

**Grounding review**:
The review step of `tailor-cv` that checks every CV claim against the client's facts.

**Credibility review**:
The review step of `tailor-cv` that enforces the writing rules (problem and decision before framework feature).

**Application ledger**:
`applications.yml`, the record of applications sent or drafted, one row per posting with a status and derived days-quiet and chase count.

**Application status**:
The ledger row's state: `drafted`, `sent`, `replied`, `interview`, then ending `rejected`, `ghosted` or `withdrawn`. Only `sent`, `replied` and `interview` are ever due to chase.

**Chase**:
A recorded follow-up against a posting (`apply set --chased`), which restarts the follow-up clock; `apply followup` lists what is due.

**Prep pack**:
`cv prep`: an interview pack with a story per CV claim, the gaps, and questions to ask, inventing nothing.

## Relationships
- A **Client** has one **Profile** (Truth), many **Variants** (Framing) and a shared **Look**; `generate.py` merges them into a RenderCV input.
- A **Variant** is built into a **Built CV**, which yields the **ATS text**.
- A **Job snapshot** is the input of `cv letter`, `cv version`, `cv prep` and `apply add`.
- `cv version` freezes a **Cut** from a **Variant** and a **Job snapshot**, under one application folder keyed by the **Vacancy id**.
- A **Cut** gets one **Verdict** after the **Grounding review** and **Credibility review**; **Forbidden claims** block a build before it is frozen.
- An **Application ledger** row is keyed by a **Vacancy id**, names the **Cut** sent and has one **Application status**.
- Every **Verb** belongs to one **Lane**, takes one **Client**, and answers with the **Envelope** under `--json`.

## Flagged ambiguities
- "snapshot" vs "capture": `docs/CONTRACT.md` ("Data layout") calls the dated directory a snapshot, while the directory is `captures/` and the verb `linkedin capture`.
- "version" vs "cut": `cv version` and `VERSIONS.md` say version, while `docs/CONTRACT.md` ("version" entry) calls the frozen artifact a cut.
- "Truth/profile" vs "scaffold": `README.md` and `CLAUDE.md` call the layer Truth, while `README.md` ("Why" and the file tree) also uses scaffold for the same profile; `CLAUDE.md` uses scaffold only for the letter pack's outline, a different thing.
- "Client" vs "person"/"user": `CLAUDE.md` defines each person as a client, while the tailor-cv skill speaks of "the vault-backed client" and "every client" as if they were different kinds of client.

