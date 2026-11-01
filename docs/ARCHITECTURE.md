# Architecture

TektiZen Content Intelligence is a GitHub-first content operating system. The repository *is* the database, GitHub Actions is the compute and the only writer, and a static dashboard on Cloudflare Pages is the control surface.

```
                         ┌───────────────────────────────────────────┐
                         │  GitHub repository (source of truth)      │
                         │                                           │
                         │  config/*.md          brand, rules, policy│
                         │  agents/prompts/*.md  agent instructions  │
                         │  data/*.json          all state           │
                         │  schemas/*.json       data contracts      │
                         └───────▲──────────────────────┬────────────┘
                     commit      │                      │  read (Contents API)
          (only via Actions)     │                      │
┌────────────────────────────────┴──────┐      ┌────────▼───────────────────────────┐
│ GitHub Actions  (Python 3.11 engine)  │      │ Dashboard (React, Cloudflare Pages)│
│                                       │◄─────┤                                    │
│ daily-content       schedule + manual │ dispatch  Reads data/*.json + *.md        │
│ manual-generation   workflow_dispatch │ (workflow_dispatch)                       │
│ publish-approved    on approval       │      │ Sends commands, never writes files │
│ performance-analysis schedule         │      └────────────────────────────────────┘
│ dashboard-command   workflow_dispatch │
└──────┬─────────────────────┬──────────┘
       │                     │
┌──────▼───────┐      ┌──────▼───────┐
│ OpenRouter   │      │ Zernio API   │
│ (free models)│      │ → Threads    │
└──────────────┘      └──────────────┘
```

## Repository layout

| Path | Purpose |
|---|---|
| `tektizen/` | Python engine (storage, settings, memory, prompts, agents, pipeline, publishing) |
| `integrations/zernio_client.py` | Zernio HTTP client — the only module that knows Zernio's API shape |
| `config/` | Brand profile, content rules, approval policy (Markdown, editable from the dashboard) |
| `agents/prompts/` | One Markdown prompt per agent, loaded at runtime |
| `data/` | All persistent state as JSON |
| `schemas/` | JSON Schema (draft 2020-12) for every data file |
| `tests/` | pytest suite (no network; external APIs are mocked) |
| `web/` | Vite + React + TypeScript + Tailwind + shadcn/ui dashboard |
| `.github/workflows/` | Automation workflows |

## Data layer

All state lives in nine JSON files under `data/`, each validated against `schemas/<name>.schema.json`.

| File | Contents |
|---|---|
| `settings.json` | Approval mode, kill switch, publish limits, model config, quality thresholds, research feeds |
| `content.json` | Every content item with its draft, versions, per-agent stage outputs, evaluation, approval, publishing state |
| `ideas.json` | Researched ideas with source URLs and retrieval timestamps |
| `approvals.json` | Append-only log of human decisions (approve / reject / edit / regenerate / refine / archive) |
| `publishing_history.json` | Append-only log of every publish attempt and its outcome |
| `performance.json` | Metric snapshots per published item (`null` = unavailable, distinct from `0`) |
| `learning_memory.json` | Categorised insights with confidence, evidence, and a change history |
| `automation_runs.json` | Run records: timings, AI request counts, token usage, errors, logs |
| `agent_metrics.json` | Per-agent execution / success / failure counters |

Guarantees (`tektizen/storage.py`):

- **Missing file** → read as empty default; written only when something is stored. Works with an empty `data/`.
- **Corrupted / invalid file** → `DataError`; the run aborts. Never silently replaced by defaults.
- **Validate before write** → schema validation on every save.
- **Atomic writes** → temp file in the same directory + `os.replace`.
- **Locking** → per-file lock (`data/.locks/`, gitignored) with stale-lock recovery for the read-modify-write cycle.
- **No empty commits** → unchanged documents are not rewritten.
- **Schema versions** → every file carries `schema_version`; newer-than-engine files are refused; migrations hook in `_migrate`.
- **IDs and time** → prefixed, time-sortable IDs (`cnt_…`, `idea_…`); ISO 8601 UTC (`…Z`).

Concurrency across workflows: every workflow that mutates `data/` shares one Actions `concurrency` group (`tektizen-data`, `cancel-in-progress: false`), so writers are serialised. Each workflow also rebases before pushing and retries the push a bounded number of times.

## Content lifecycle

```
IDEA → RESEARCH → GENERATION → EVALUATION → REFINEMENT → PENDING_APPROVAL → READY_TO_PUBLISH → PUBLISHING → PUBLISHED
                                                     │                │
                                                     └→ FAILED        ├→ REJECTED
                                                                      └→ ARCHIVED
PUBLISHING → PUBLISH_UNCERTAIN   (never auto-retried; human reconciles)
DRAFT      → studio drafts not yet sent to the pipeline
```

Every stage appends a `stages[]` entry with the agent, model, token usage, structured output, and error, so the dashboard can show the full journey.

## Agents

Seven agents, each a Markdown prompt plus a Python output validator:

| Agent | Input | Output contract |
|---|---|---|
| Trend Researcher | Real feed items (RSS) fetched in code | `ideas[]` with `source_urls` that must match fetched URLs |
| Content Strategist | Ideas, recent content, memory | `briefs[]` (format, angle, hook strategy, key points) |
| Content Creator | Brief, sources, memory | `hook/body/cta/posts[]` + `claims[]` |
| Quality Evaluator | Draft, brief, recent hooks | 10 criterion scores, `overall_score`, `issues[]` |
| Fact Checker | Draft, claims, sources | Per-claim verdicts, `critical_failure`, `factuality_score` |
| Content Editor | Draft + both evaluations | Final draft or `changed: false` |
| Learning Analyst | Approvals, edits, performance | `add`-only memory operations with evidence IDs |

Research uses real RSS feeds (configurable in settings) fetched by code, so the model never "searches" from memory. The researcher may only cite URLs that were fetched.

Code enforces what prompts ask for: post length ≤ 500, post count per format, source URL membership, Indonesian-vocabulary detection, repetition similarity against recent content, and confidence caps on learning by evidence count.

## OpenRouter

- `POST https://openrouter.ai/api/v1/chat/completions`, OpenAI-compatible.
- Default model `openrouter/free`; per-agent overrides in settings. Never switches to a paid model.
- Per-run request budget (`ai.max_requests_per_run`); bounded retries with exponential backoff on 429/5xx/timeouts.
- JSON extraction tolerant of code fences, then schema validation; one repair attempt per call at most.
- Usage (`prompt_tokens`, `completion_tokens`) and the actual `model` returned are logged per stage.

## Zernio (verified against docs.zernio.com, 2026-11-01)

- Base `https://zernio.com/api/v1`, `Authorization: Bearer $ZERNIO_API_KEY`.
- Account ID: `GET /v1/accounts?platform=threads` → `accounts[]._id`. Stored in `settings.publishing.threads_account_id`.
- Publish: `POST /v1/posts` with `platforms: [{platform: "threads", accountId, platformSpecificData}]` and `publishNow: true`.
- Threads sequence: `platformSpecificData.threadItems: [{content}, …]`. Item 0 is the root post; top-level `content` is then display-only.
- Success requires `post.status == "published"` and the Threads platform entry `status == "published"`. Anything else is not success.
- Duplicate protection: an `Idempotency-Key` header (a stable per-item key; a retry within 24h returns the original post), plus Zernio's own 24h content-hash 409, plus our own publishing state and content hash.
- Analytics: `GET /v1/analytics?postId=…`. Threads exposes `views`, `likes`, `comments` (→ replies), and `shares` (reposts are counted in shares). There is **no separate quotes metric**, so `quotes` and `reposts` are stored as `null` (unavailable), never `0`. A 402 `analytics_addon_required` response marks analytics as unavailable.
- Limits: 500 chars per post; 250 posts per 24h per account; 25 posts per hour.

## Publishing safety gate

`tektizen/publishing/gate.py` is the single function that decides whether an item may be published. It is used by both the auto-publish path and the human-approved path. The rules are listed in `config/approval_policy.md`. Key points:

- Unknown or missing approval mode → human approval.
- The kill switch blocks everything.
- A critical fact failure blocks even human-approved content.
- An uncertain outcome (request sent, no definitive answer) → `PUBLISH_UNCERTAIN`, never retried automatically.

## Dashboard ↔ repository (security model)

A static site cannot hold a secret. So:

- **No secrets in the bundle.** Only non-secret `VITE_GITHUB_OWNER/REPO/BRANCH` are build-time config. OpenRouter and Zernio keys exist only as GitHub Actions Secrets.
- **Reads:** GitHub REST Contents API (`/repos/{owner}/{repo}/contents/data/*.json`). Public repos need no token. Private repos use the viewer's token (below).
- **Writes:** the dashboard never writes files. Every mutation is a command, sent as `workflow_dispatch` on `dashboard-command.yml` with a JSON payload (`approve`, `reject`, `edit_approve`, `regenerate`, `refine`, `archive`, `update_settings`, `memory_add/update/delete/reset`, `update_prompt`, `update_config`, `generate`, `reconcile_publish`). The workflow validates the payload against the current state, applies it with the same Python code and validation as the automation, commits, and triggers publishing when needed.
- **Viewer credential:** the user enters a **fine-grained personal access token scoped to this one repository** with `Actions: Read and write` and `Contents: Read-only`. It is entered at runtime and kept in `sessionStorage` (cleared when the tab closes). It is never bundled and never sent anywhere but `api.github.com`. Even if it leaked, it could not push code. It can only trigger the workflows, whose inputs are validated.
- **Least privilege in workflows:** each workflow declares minimal `permissions:` (`contents: write` only where it commits, `actions: write` only where it dispatches another workflow).
- **Upgrade path:** for multi-user or stricter setups, replace the PAT with a GitHub App and a small token-exchange function (e.g. a Cloudflare Pages Function). The command protocol stays the same.

## Phase status

| Phase | Status |
|---|---|
| 1. Foundation: structure, schemas, storage, settings, memory, prompts, docs | Done |
| 2. Dashboard | Pending |
| 3. AI engine (OpenRouter, agents, pipeline, learning) | Pending |
| 4. GitHub integration (workflows, dashboard commands) | Pending |
| 5. Zernio integration | Pending |
| 6. Testing | Ongoing (foundation covered) |
| 7. Deployment docs | Pending |
