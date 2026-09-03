# Development setup

Technical companion to the [pitch](../README.md) and the
[architecture doc](ARCHITECTURE.md). See `AGENTS.md` for contribution rules
(branch per change, PR review before merging to `main`).

## Fastest path to testing features: just a Groq key

Everything except the LLM call itself has a zero-setup fallback:
embeddings fall back from Bedrock Titan to a local TF-IDF vectorizer, and
storage falls back from Supabase to a local SQLite file
(`workspace/db/compass.sqlite3`, auto-created on first use) whenever
`SUPABASE_URL`/`SUPABASE_KEY` aren't set. So to click through every feature
with no AWS and no Supabase project, all you need is:

```bash
echo 'GROQ_API_KEY=gsk_...' > .env   # console.groq.com -> API Keys, free, no card
```

then skip straight to `uv run python demo_cli.py` or `run_server.py` below.
AWS/Supabase only matter once you want real semantic embeddings and shared
persistence instead of the local fallbacks.

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

# 4 + 5. Backend + frontend together, one command, one terminal:
cd frontend && npm install && cd ..
uv run python run_dev.py             # backend on :8000 (docs at /docs), frontend on :5173

#   or run them separately in two terminals, if you want independent control:
#   uv run python run_server.py
#   cd frontend && npm run dev
```

`run_dev.py` starts both as one process group and prefixes their interleaved
output with `[backend]`/`[frontend]`. If either one dies on its own -- this
has happened during development, both the backend's `--reload` watcher and
the Vite dev server have independently exited without warning on Windows --
it stops the other one too instead of leaving you with a silently half-broken
app. `Ctrl+C` stops both cleanly. The backend it starts does NOT use
`--reload` (see "Troubleshooting" below); restart `run_dev.py` after backend
edits.

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
and verified (real NUSMods fetch, real prereq-graph parsing, embeddings via
the TF-IDF fallback, storage via the SQLite fallback — full `POST`/`GET
/students` round trip confirmed working with zero external services, all
graphs compile, full request path tested through a live browser click). The
one thing that genuinely can't be tested without a key: real LLM-generated
trajectories/leverage moves/outreach drafts, which needs `GROQ_API_KEY` (or
AWS Bedrock). See "Known limitations" in the PR this branch was opened from.

## Troubleshooting

**Server seems to ignore code changes.** `run_server.py` runs with
`reload=True`. In some sandboxed/containerized environments the
watchfiles-based reloader's subprocess can end up serving stale code after an
edit (observed once during development). If a change doesn't seem to take
effect, kill every python process for this project and restart, or run
without reload: `uv run python -c "import uvicorn; uvicorn.run('app.server:app', host='0.0.0.0', port=8000)"`.

## If port 8000 or 5173 is taken

Backend: `PORT=8010 uv run python run_server.py`, then update
`frontend/vite.config.js`'s proxy `target` to match. Frontend:
`npm run dev -- --port 5174`, then update `app/server.py`'s
`allow_origins` to match.
