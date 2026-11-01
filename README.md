# TektiZen Content Intelligence

AI-powered content strategy, generation, review, and publishing for the Threads account **@tektizen**: practical AI and technology content in Bahasa Melayu Malaysia.

- **GitHub-first.** All state is JSON in this repository. GitHub Actions runs the automation and makes every write. There is no database and no server.
- **Grounded in real news.** Free RSS feeds and Hacker News are fetched in code, full article text is extracted, and every fact the AI uses must quote its source.
- **Eight specialised agents:** research → strategy → English draft → Malay localisation → quality → fact-check → editing → learning. Each is defined in an editable Markdown file.
- **Human approval by default.** Optional auto-publishing sits behind strict, code-enforced gates, with a kill switch.
- **Learns through structured memory**, with confidence levels and evidence, all editable from the dashboard.
- **Dashboard** on Cloudflare Pages: static, holds no secrets, and sends actions through GitHub Actions.

**New here? Follow [docs/SETUP.md](docs/SETUP.md).** The design is explained in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## How it works

```
08:00 MYT  Daily Content Generation
           fetch news (RSS, HN) → full text → Trend Researcher (ideas + quoted facts)
           → Strategist → Creator (English) → Malay Localizer → code checks
           → Quality Evaluator + Fact Checker → Editor (if needed) → Approval Center

You        approve / edit / reject / refine / regenerate in the dashboard
           → Publish Approved Content → Zernio → Threads

22:00 MYT  Performance Analysis: Zernio metrics → Learning Analyst → memory
```

## Repository layout

| Path | What it is |
|---|---|
| `web/` | Dashboard (React + Vite + Tailwind + shadcn/ui), built with npm |
| `tektizen/` | Python engine (pipeline, agents, storage, publishing, learning) |
| `integrations/zernio_client.py` | Zernio API client (publishing + analytics) |
| `agents/prompts/` | One Markdown instruction file per agent |
| `config/` | Brand profile, content rules, style examples, approval policy |
| `data/` | All state as JSON (written by the automation) |
| `schemas/` | JSON Schemas that every data write is validated against |
| `tests/` | Python test suite (external APIs mocked) |
| `.github/workflows/` | Automation schedules and dashboard command handler |
| `docs/` | Setup and architecture documentation |

## Workflows

| Workflow | Trigger | Does |
|---|---|---|
| `daily-content.yml` | 08:00 MYT + manual | Research, generate, evaluate, queue for approval |
| `manual-generation.yml` | Dashboard / manual | One post on a given topic and format, or ideas only |
| `publish-approved.yml` | After approval + every 3h | Publishes approved content safely |
| `performance-analysis.yml` | 22:00 MYT + manual | Collects metrics, updates learning memory |
| `dashboard-command.yml` | Dashboard | Applies validated UI actions (approve, settings, memory, prompts…) |
| `zernio-accounts.yml` | Manual | Prints your Threads account ID |
| `ci.yml` | Push / PR | Runs tests and builds the dashboard |

## Local development

```bash
# Engine (Python 3.11 in CI; 3.10+ works locally)
pip install -r requirements-dev.txt
python -m tektizen check                    # validate data, prompts, config
python -m pytest                             # 117 tests, no network or keys needed
python -m tektizen generate --mode daily     # real run: needs OPENROUTER_API_KEY

# Dashboard
cd web
npm install
npm run dev                                  # open http://localhost:5173/?demo for sample data
```

Copy `.env.example` to `.env` for local runs. Never commit real keys, and never put secrets in `VITE_*` variables.

## What is and isn't verified

- **Verified locally:** all engine logic (117 tests), live news fetching and full-text extraction against the real feeds, the Git merge driver with two concurrent clones, the dashboard build, and the dashboard's rendering in demo mode.
- **Needs your keys to verify live:** OpenRouter generation quality with free models, and Zernio publishing and analytics. The Zernio client follows the documented API (checked November 2026) and is covered by mocked tests. The first real publish is the live check. The analytics response parser is deliberately tolerant because Zernio's docs don't show a full example response.
