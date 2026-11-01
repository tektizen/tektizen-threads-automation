# TektiZen Content Intelligence

AI-powered content strategy, generation, review, and publishing for the Threads account **@tektizen**: practical AI and technology content in Bahasa Melayu Malaysia.

- **GitHub-first:** all state is JSON in this repository; GitHub Actions runs the automation and makes every write.
- **Seven specialised agents** (research → strategy → creation → quality → fact-check → editing → learning), each defined in Markdown.
- **Human approval by default.** Optional auto-publishing sits behind strict, code-enforced quality and safety gates.
- **Learns through structured memory,** not retraining. Insights carry confidence and evidence and are fully editable.
- **Dashboard** on Cloudflare Pages (static). It holds no secrets.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

> **Status:** Phase 1 (foundation) is complete. The dashboard, AI pipeline, workflows, and Zernio publishing are under construction. Setup and deployment instructions will be completed in Phase 7.

## Local development

```bash
# Engine (Python 3.11+ recommended; 3.10 works locally)
pip install -r requirements-dev.txt
python -m tektizen init     # creates missing data files, never overwrites
python -m tektizen check    # validates data, prompts, config
python -m pytest

# Dashboard
cd web
npm install
npm run dev
```

Copy `.env.example` to `.env` for local runs. Never commit real keys, and never put secrets in `VITE_*` variables.
