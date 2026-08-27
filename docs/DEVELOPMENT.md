# Development setup

Technical companion to the [pitch](../README.md) and the
[architecture doc](ARCHITECTURE.md). See `AGENTS.md` for contribution rules
(branch per change, PR review before merging to `main`).

## Quick start

```bash
uv sync                              # or: python -m venv .venv && .venv/Scripts/pip install -e .
cp .env.example .env                 # fill in GROQ_API_KEY, AWS creds, SUPABASE_URL/KEY
```

Then, in order:

```bash
# 1. Data pipeline (real NUSMods data + synthetic opportunities -> cached embeddings)
uv run python run_pipeline.py
#   or step by step:
#   uv run python data_pipeline/fetch_nusmods.py --list-prefixes   # sanity-check scope first
#   uv run python data_pipeline/fetch_nusmods.py
#   uv run python data_pipeline/build_prereq_graph.py
#   uv run python data_pipeline/build_embeddings.py

# 2. Supabase schema (once, in the Supabase SQL editor)
#    run data_pipeline/init_supabase.sql

# 3. Terminal walkthrough -- proves the graphs + DB work before touching the UI
uv run python demo_cli.py

# 4. Backend
uv run python run_server.py          # http://localhost:8000, docs at /docs

# 5. Frontend (separate terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

A `.claude/launch.json` is included so `compass-backend`/`compass-frontend`
can be started from Claude Code's preview tooling directly, if you're using it.

## What's real vs synthetic

- **Real**: the NUSMods module catalog (`data_pipeline/fetch_nusmods.py`),
  scoped to Computing + AI-adjacent quant faculties + business/entrepreneurship
  prefixes (`app/config.py`'s `MODULE_CODE_PREFIXES` -- verified against the
  live 2025-2026 catalog, 727 candidate modules).
- **Synthetic**: everything in `data_pipeline/synthetic/` -- professors,
  internships/RA openings, competitions, scholarships, alumni stories. All
  fictional -- no real NUS staff, students, or companies. See
  `data_pipeline/synthetic/README.md`.

## Embeddings: Bedrock Titan, with an automatic fallback

`data_pipeline/build_embeddings.py` tries Bedrock Titan Embed Text v2 first.
If AWS credentials/model access aren't available, it automatically falls back
to a TF-IDF vectorizer (pure CPU, no network) and records which provider was
used in `workspace/processed/embeddings_meta.json` -- `app/retrieval.py`
reads that at runtime and embeds queries the same way, so nothing downstream
needs to know or care which one is active. Verified end-to-end on the TF-IDF
path already; switching to real AWS credentials should need zero code
changes, just an `aws sso login`.

## Never sent, never overwritten

Outreach drafts are staged in Supabase with `status='draft'` and only ever
move to `approved`/`rejected` -- nothing in this codebase sends a real email.
`/students/{id}/whatif` always inserts a **new** `trajectory_sets` row with
`is_whatif=true`; it never overwrites the baseline, so both can be shown side
by side.

## Status as of this branch

Data pipeline, all 5 LangGraph graphs, and the FastAPI/React wiring are built
and structurally verified (real NUSMods fetch, real prereq-graph parsing,
embeddings via the TF-IDF fallback, all graphs compile, full request path
tested through a live browser click). What still needs real credentials to
exercise: actual LLM-generated trajectories/leverage moves/outreach drafts
(needs `GROQ_API_KEY` or Bedrock), and Supabase persistence (needs a live
project + `data_pipeline/init_supabase.sql` run once). See "Known
limitations" in the PR this branch was opened from.

## If port 8000 or 5173 is taken

Backend: `PORT=8010 uv run python run_server.py`, then update
`frontend/vite.config.js`'s proxy `target` to match. Frontend:
`npm run dev -- --port 5174`, then update `app/server.py`'s
`allow_origins` to match.
