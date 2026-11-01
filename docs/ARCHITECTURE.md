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

Concurrency across workflows: a single shared Actions `concurrency` group was rejected, because GitHub keeps only **one pending run per group** and cancels the rest. Three quick approvals would lose the middle one. Instead:

- Workflows run freely. `.github/scripts/commit-and-push.sh` commits, and if the push is rejected it runs `git pull --rebase` and retries (up to 5 times).
- During the rebase, a custom Git merge driver (`tektizen/merge.py`, registered via `.gitattributes`) merges `data/*.json` **record by record** (by `id`). Concurrent additions are all kept. A record edited on both sides keeps the newer `updated_at`, and `agent_metrics` counters add their deltas. The merged result is schema-validated, and an invalid merge fails loudly instead of committing.
- Publishing is the exception: it has its own `concurrency` group, so only one publisher ever runs. A replaced queued run is harmless because each run publishes everything that is ready.

Verified with two real clones pushing concurrently (both sides' content and memory changes survive).

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

Eight agents, each a Markdown prompt plus a Python output validator. The design assumes **free models**: code does everything it can, and each agent gets one narrow job with real source text in front of it.

| Agent | Input | Output contract |
|---|---|---|
| Trend Researcher | Feed items + full article text fetched in code | `ideas[]` with `source_urls` (must be fetched URLs) and `facts[]` whose `quote` must appear in the source text (checked in code) |
| Content Strategist | Ideas, recent content, memory | `briefs[]` (format, angle, hook strategy, key points) |
| Content Creator | Brief, verified facts, memory | **English** master draft `hook/body/cta/posts[]` (≤380 chars/post) + `claims[]` → `fact_id` |
| Malay Localizer | English draft + `config/style_examples.md` + recently approved posts | Casual Bahasa Melayu Malaysia, same posts and facts, ≤500 chars |
| Quality Evaluator | BM draft, brief, recent hooks | 10 criterion scores (overall recomputed in code), `issues[]` |
| Fact Checker | BM draft, verified facts | Per-claim verdicts; `critical_failure`, status, and score recomputed in code |
| Content Editor | Draft + both evaluations + code checks | Final draft or `changed: false` |
| Learning Analyst | Approvals, edits, performance | `add`-only memory operations with evidence IDs |

Research (`tektizen/research.py`) is plain code, so the model never "searches" from memory:

1. Fetch 13 free RSS feeds (official AI blogs, tech media, Malaysian outlets including Amanz in BM, and Google News MY) plus Hacker News via the Algolia API. All were verified reachable on 2026-11-01 and are editable in Settings.
2. Filter general-tech feeds by AI keywords, drop items older than `max_age_days`, and dedupe by URL and title similarity, excluding sources already used.
3. Score by source tier, recency, Malaysian relevance, practical value, and HN points. Google News links are down-weighted because they are redirects with no extractable text. Each publisher is capped at 2 items.
4. Extract full article text (`trafilatura`) for the top 4 stories, so the model works from the article rather than a one-line summary.

The researcher may only cite fetched URLs, and every fact must carry a quote that is found in that source's text.

Code enforces what prompts ask for: post length ≤ 500, post count per format, source URL membership, Indonesian-vocabulary detection, repetition similarity against recent content, and confidence caps on learning by evidence count.

## OpenRouter

- `POST https://openrouter.ai/api/v1/chat/completions`, OpenAI-compatible.
- Default model `openrouter/free`; per-agent overrides in settings. Never switches to a paid model.
- Per-run request budget (`ai.max_requests_per_run`); bounded retries with exponential backoff on 429/5xx/timeouts.
- JSON extraction tolerant of code fences, then schema validation; one repair attempt per call at most.
- Usage (`prompt_tokens`, `completion_tokens`) and the actual `model` returned are logged per stage.

## Zernio (verified against docs.zernio.com, 2026-11-01)

- Base `https://zernio.com/api/v1`, `Authorization: Bearer $ZERNIO_API_KEY`.
- Account ID: `GET /v1/accounts?platform=threads` → `accounts[]._id`. Set as the GitHub repository variable `THREADS_ACCOUNT_ID` (or a secret of that name), passed to the publish workflow. `settings.publishing.threads_account_id` is only a fallback and isn't shown in the dashboard.
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
- **Writes:** the dashboard never writes files. Every mutation is a command, sent as `workflow_dispatch` on `dashboard-command.yml` with a JSON payload (`approve`, `reject`, `edit_approve`, `regenerate`, `refine`, `archive`, `update_settings`, `memory_add/update/delete/reset`, `update_prompt`, `update_config`, `save_draft`, `submit_for_review`, `reconcile_publish`). Generation requests go to `manual-generation.yml` instead. The workflow validates the payload against the current state, applies it with the same Python code and validation as the automation, commits, and triggers publishing when needed.
- **Viewer credential:** the user enters a **fine-grained personal access token scoped to this one repository** with `Actions: Read and write` and `Contents: Read-only`. It is entered at runtime and kept in `sessionStorage` (cleared when the tab closes). It is never bundled and never sent anywhere but `api.github.com`. Even if it leaked, it could not push code. It can only trigger the workflows, whose inputs are validated.
- **Least privilege in workflows:** each workflow declares minimal `permissions:` (`contents: write` only where it commits, `actions: write` only where it dispatches another workflow).
- **Upgrade path:** for multi-user or stricter setups, replace the PAT with a GitHub App and a small token-exchange function (e.g. a Cloudflare Pages Function). The command protocol stays the same.

## Phase status

| Phase | Status |
|---|---|
| 1. Foundation: structure, schemas, storage, settings, memory, prompts, docs | Done |
| 2. Dashboard (10 sections, demo mode, responsive, dark/light) | Done |
| 3. AI engine (OpenRouter, 8 agents, pipeline, learning) | Done (mocked tests; live quality depends on free models) |
| 4. GitHub integration (7 workflows, dashboard commands, merge driver) | Done |
| 5. Zernio integration (publish, threads, analytics, reconciliation) | Done (mocked tests; first live publish is the real check) |
| 6. Testing | 117 Python tests; dashboard type-check, build, and demo-mode render |
| 7. Deployment docs | Done: see `docs/SETUP.md` |
