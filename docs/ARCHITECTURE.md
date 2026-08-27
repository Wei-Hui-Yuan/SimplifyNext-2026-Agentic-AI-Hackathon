# NUS Compass — Architecture

The build plan this codebase was implemented from. Copied in from the
Claude Code session that scaffolded it, so the team has it without needing
that session's local plan file.

## Context

Team went through a design-thinking exercise (POV format, 4-question pressure test) and landed on **NUS Compass**: an agent that helps an NUS student (worked persona: a Year 1 student unsure between AI research vs AI industry vs entrepreneurship) see how today's module/activity choices connect to different 3-year outcomes, gives a small ranked "highest-leverage moves" list each check-in, drafts human-approved outreach to opportunities, and re-scores trajectory alignment as the student takes real actions over time. Build window is **~2 days**. Confirmed stack: **React frontend, FastAPI backend, Supabase (hosted Postgres) for all student/app data.**

This code was originally scaffolded inside a separate training-curriculum repo (`agentic_ai_hackathon_2026`, a workshop lab under `lab/` covering LLM foundations → agents → Bedrock → LangGraph → DeepAgents → AgentCore deployment) and then moved into this repo. It deliberately reuses proven patterns from that curriculum (`chat_model()` provider switch, `.with_structured_output()` for planning, the `@tool`/`ToolMessage` round trip, LangGraph's `StateGraph`/`InjectedState`/`Command` idiom) rather than reinventing them, while being fully self-contained — nothing here imports from that other repo.

**Confirmed real external data source**: NUSMods public API (no auth) — `https://api.nusmods.com/v2/{academicYear}/moduleList.json` (full catalog) and `.../modules/{CODE}.json` (per-module detail: `description`, `department`, `faculty`, `moduleCredit`, `workload`, `prerequisite`, `prereqTree`, `preclusion`, `fulfillRequirements` — the reverse prereq edge, given for free). Verified live for academic year `2025-2026`. No public API exists for professors/RA-openings/competitions/scholarships/alumni — those are a small hand-authored synthetic dataset (~10-15 entries each), no real people or companies.

## Top-level layout

```
.
├── pyproject.toml              # own uv project (package = false), own deps
├── .env / .env.example
├── run_pipeline.py             # runs data_pipeline/*.py in order
├── run_server.py                # uv run python run_server.py -> uvicorn on :8000
├── demo_cli.py                  # terminal fallback: invokes compiled graphs directly, no HTTP/UI needed
├── app/
│   ├── common.py                # self-contained chat_model()/PROVIDER/.env loader
│   ├── config.py                 # ACADEMIC_YEAR, dept allowlist, WORKSPACE = Path(__file__).resolve().parent.parent / "workspace"
│   ├── schemas.py                # Pydantic: TrajectoryPath, TrajectorySet, LeverageMove, LeverageList, OutreachDraft
│   ├── db.py                     # Supabase client wrapper, no ORM
│   ├── retrieval.py              # load_index / embed_query / cosine_topk
│   ├── tools.py                  # @tool surface
│   ├── graph.py                  # CompassState + 5 linear StateGraphs + node functions
│   └── server.py                 # FastAPI app + CORS, thin wrappers around graph.invoke()
├── data_pipeline/
│   ├── fetch_nusmods.py          # scoped fetch + per-file disk cache
│   ├── build_prereq_graph.py     # prereqTree/fulfillRequirements -> nodes/edges
│   ├── build_embeddings.py       # embeddings, cached to disk, idempotent
│   ├── init_supabase.sql         # run once in the Supabase SQL editor
│   └── synthetic/
│       ├── professors.json
│       ├── opportunities.json
│       ├── competitions.json
│       ├── scholarships.json
│       └── alumni_trajectories.json
├── workspace/                    # gitignored; every path via app.config.WORKSPACE, never a bare "./workspace" string
│   └── {raw/{moduleList.json, manifest.json, modules/{CODE}.json}, processed/{prereq_graph.json, embeddings.npy, embeddings_meta.json}}
│       # local derived-data cache only (module catalog + embeddings) — student/app data lives in Supabase, not here
├── frontend/                     # Vite + React
│   ├── package.json / vite.config.js  (dev proxy /api -> http://localhost:8000)
│   └── src/
│       ├── main.jsx, App.jsx (tab nav: Intake | Trajectories & Moves | Outreach | What-if | Checkpoint)
│       ├── api.js               # fetch wrappers, one per FastAPI endpoint below
│       └── components/
│           ├── IntakeForm.jsx          # year, CAP, modules taken, interests, goal text
│           ├── TrajectoryCard.jsx      # Path A/B/C: name, rationale, step sequence
│           ├── LeverageMoveCard.jsx    # one of the top-5: type badge, why, deadline/probability
│           ├── OutreachDraftPanel.jsx  # subject/body + Approve/Reject buttons -> /outreach/{id}/approve
│           ├── WhatIfPanel.jsx         # constraint toggles (e.g. CAP weight vs internship weight) -> new trajectory_set
│           └── CheckpointView.jsx      # alignment_delta + action timeline ("Path B now looks more aligned")
└── docs/
    ├── ARCHITECTURE.md           # this file
    └── DEVELOPMENT.md            # setup/run instructions
```

`.gitignore` covers: `.env`, `workspace/`, `.venv/`, `frontend/node_modules/`, `frontend/dist/`.

Base deps: `fastapi`, `uvicorn`, `langchain`, `langgraph`, `pydantic`, `groq`, `langchain-groq`, `numpy`, `httpx`, `boto3`/`langchain-aws` (needed as a base dep — the embedding pipeline needs Bedrock Titan regardless of which `LLM_PROVIDER` the chat model uses), `supabase` (the `supabase-py` client, used by `app/db.py`), `scikit-learn` (the TF-IDF embedding fallback).

`.env` needs `SUPABASE_URL` and `SUPABASE_KEY` (service-role key — backend-only, never shipped to the React client) alongside `GROQ_API_KEY`/`LLM_PROVIDER`/AWS vars.

## Data pipeline

**`fetch_nusmods.py`** — two-stage filter: (1) cheap prefix pre-filter on `moduleList.json` (`config.py`'s `MODULE_CODE_PREFIXES`: `CS`, `IS`, `CP` for Computing; `DSA`, `ST`, `MA`, `EE` for AI-adjacent quant faculties; `BSP`, `BSN`, `TR`, `ETP`, `MNO` for business/entrepreneurship — **verified against the live 2025-2026 catalog**, 727 candidate modules), then (2) an optional authoritative post-filter on each candidate's real `department`/`faculty` field (left empty by default — the prefix filter alone already produced a coherent set). Log both counts to `workspace/raw/manifest.json`. Cache per-module-file (`workspace/raw/modules/{CODE}.json`) so an interrupted run resumes without re-fetching. Every fetch wrapped in try/except, logged and skipped on failure — never let one bad module code kill the run. CLI: `--academic-year 2025-2026 [--refresh] [--limit N] [--list-prefixes]`.

**`build_prereq_graph.py`** — `build_graph(modules: dict[str, dict]) -> dict` produces `{"nodes": {code: {title, department, moduleCredit, faculty}}, "edges": [{"from", "to", "type": "prereq"|"unlocks"}]}`. `extract_leaf_codes(tree)` flattens `prereqTree`. Real-data quirk found while building this: leaves are `"CODE:GRADE"` strings (e.g. `"CS2030S:D"`), and the tree can contain non-prerequisite rule keys too (e.g. `{"cohort": {"rule": "MUST_BE_IN", ...}}`) — only `"and"`/`"or"` keys are walked, everything else is ignored rather than mis-parsed. v1 deliberately doesn't attempt full AND/OR satisfiability evaluation against `modules_taken` — just stores the flattened leaf-code list for display. `fulfillRequirements` gives the reverse `"unlocks"` edge for free, one line per module.

**`build_embeddings.py`** — one vector per record (module or synthetic entry), tagged by `record_type` so every feature shares one index. Titan Embed Text v2 with `dimensions=1024, normalize=True` — pre-normalized vectors mean query-time cosine similarity is a plain dot product. **Falls back automatically to TF-IDF** (`sklearn.feature_extraction.text.TfidfVectorizer`) if Bedrock credentials/access aren't available — verified this fallback path end-to-end already. Idempotent on the Bedrock path: skips re-embedding a record whose `id`+text hash already exists in the previous meta file.

**`app/retrieval.py`** runtime API:

```python
def load_index() -> tuple[np.ndarray, list[dict]]:
    """Load embeddings.npy + embeddings_meta.json once; module-level cache."""

def embed_query(text: str) -> np.ndarray:
    """The only live embedding call at runtime -- reads which provider
    build_embeddings.py used from embeddings_meta.json and embeds the same way."""

def cosine_topk(query_vec, matrix, meta, k=5, record_type=None, min_score=0.05) -> list[dict]:
    """scores = matrix @ query_vec (both normalized). Optional record_type mask
    post-matmul. Returns meta records + 'score', sorted desc, thresholded, sliced to k."""
```

## Storage — Supabase (hosted Postgres), with a SQLite fallback

Used specifically because the checkpoint/adaptation feature needs an ordered, appendable action log plus multiple checkpoint snapshots compared over time — a natural fit for relational tables — and Supabase's table/SQL editor gives everyone on the team a shared, inspectable view of `actions`/`checkpoints` while narrating "adaptation" live to judges, without anyone needing a local DB file. The module catalog + embeddings (`workspace/processed/`) stay as local cached files, not Supabase tables — that's derived, regenerable data with no student-specific state.

`app/db.py` is a thin dispatcher (`app/db_supabase.py` vs `app/db_sqlite.py`, chosen by whether `SUPABASE_URL`/`SUPABASE_KEY` are set) rather than a hard Supabase dependency — same fallback shape as the embeddings pipeline. The SQLite backend auto-creates its schema in `workspace/db/compass.sqlite3` on first use, so anyone can test every feature except the LLM call itself with zero external services. Both backends implement the identical function signatures graph.py/tools.py/server.py call — neither caller knows or cares which one answered.

Schema: `data_pipeline/init_supabase.sql` (run once in the Supabase SQL editor) — `students`, `trajectory_sets` (`is_whatif` flag distinguishes baseline from what-if runs, never overwritten), `leverage_lists`, `actions` (the log the adaptation feature diffs against), `outreach_drafts` (`status`: `draft` → `approved`/`rejected`, never `sent` — nothing in this codebase sends real email), `checkpoints`.

`app/db.py` wraps a single module-level `supabase-py` client, plain functions, no ORM: `init_db()`, `upsert_student()`, `get_student()`, `insert_trajectory_set()`, `get_latest_trajectory_set(student_id, is_whatif=False)`, `insert_leverage_list()`, `log_action()`, `get_actions_since(student_id, since_ts)`, `insert_outreach_draft()`, `update_outreach_status(draft_id, status)`, `insert_checkpoint()`, `get_checkpoint_history(student_id)`. Every Supabase call lives in this file so `graph.py`/`tools.py` never import the client directly.

**Optional stretch, not required for the MVP**: since Supabase is already Postgres, `pgvector` could later replace the local `embeddings.npy`/`embeddings_meta.json` files with a proper table + `<=>` similarity search in SQL. `app/retrieval.py`'s `load_index()`/`cosine_topk()` signatures would stay the same either way.

## Agent design — five linear LangGraph graphs, one shared state

Five small graphs sharing one `CompassState`, rather than one large router graph — lets teammates build/test their own graph in parallel, and every flow is linear (**no back-edges, no conditional loops**) since none need iteration — this keeps per-feature latency predictable for a live demo and explicitly avoids the multi-tens-of-seconds-per-invoke cost of heavier agent harnesses (measured in the training curriculum's DeepAgents section) this app doesn't need. Every model-calling node is a single `chat_model().with_structured_output(...)` call, not a ReAct tool-loop.

```python
class CompassState(TypedDict):
    messages: Annotated[list, add_messages]   # unused by the 5 core graphs; reserved for an optional day-2 chat mode
    mode: str
    student_id: str
    profile: dict                # year, cap, modules_taken, interests, goal
    weight_overrides: dict        # whatif only, e.g. {"cap_weight": 0.7, "internship_weight": 0.1}
    constraint_note: str
    trajectories: list[dict]
    candidate_pool: list[dict]
    leverage_moves: list[dict]
    outreach_target: dict
    outreach_draft: dict
    baseline_checkpoint_id: int | None
    actions_since_baseline: list[dict]
    alignment_delta: dict
    result_ref_id: int | None
```

Plain Python nodes (no model call): `load_student_context`, `score_candidates` (calls `retrieval.cosine_topk` for modules + opportunities, computes `leverage_score = 0.4*similarity + 0.3*trajectory_alignment + 0.2*unlock_count_normalized + 0.1*urgency_bonus` — tune weights as needed), `apply_whatif_constraint`, `compute_alignment_delta` (diffs `db.get_actions_since()` against the baseline trajectory's expected moves), `persist_result` (common tail, branches on `state["mode"]`).

Model-calling nodes: `generate_trajectories`, `explain_leverage_moves`, `draft_outreach_node` — reused across graphs.

Five compiled graphs (all verified to compile with correct node wiring):
- `build_intake_graph()`: `load_student_context -> generate_trajectories -> persist_result`
- `build_leverage_graph()`: `load_student_context -> score_candidates -> explain_leverage_moves -> persist_result`
- `build_outreach_graph()`: `load_student_context -> draft_outreach_node -> persist_result` (writes `status='draft'`; approval is a plain DB write outside the graph, not agent logic)
- `build_whatif_graph()`: `load_student_context -> apply_whatif_constraint -> generate_trajectories -> score_candidates -> explain_leverage_moves -> persist_result` (writes a **new** `trajectory_sets` row with `is_whatif=true` — never overwrites baseline)
- `build_checkpoint_graph()`: `load_student_context -> compute_alignment_delta -> score_candidates -> explain_leverage_moves -> persist_result`

## Tools (`app/tools.py`)

Most of this surface is *not* on the core demo's hot path (the 5 graphs call node logic directly) — it exists for (a) utilities the deterministic nodes call, and (b) an optional future "chat with Compass" mode via `create_agent(tools=[...])`.

`search_modules`, `match_opportunities`, `get_prereq_chain`, `approve_outreach` are plain string-returning `@tool`s (pure reads / a status-only write, never raise — errors return as strings). `draft_outreach` and `log_action` use `InjectedState`/`InjectedToolCallId` + `Command(update=...)`, specifically so `student_id` comes from graph state, never from the model — it should never be able to write to (or draft outreach for) the wrong student.

## FastAPI (`app/server.py`)

CORS enabled for the Vite dev origin (`http://localhost:5173`). A global `RuntimeError` handler returns a clean 503 with the underlying friendly message (missing `GROQ_API_KEY`/AWS creds/Supabase config) instead of letting a missing-credential error take down the process — verified live.

Endpoints: `POST /students`, `GET /students/{id}`, `POST /students/{id}/trajectories`, `POST /students/{id}/leverage-moves`, `POST /students/{id}/outreach`, `POST /outreach/{draft_id}/approve`, `POST /students/{id}/whatif`, `POST /students/{id}/checkpoint`, `POST /students/{id}/actions` (lets the demo "fast-forward" time without waiting for a real second visit).

## React frontend (`frontend/`)

Vite + React, plain `fetch` in `api.js`. Tab-based `App.jsx` — Intake, Trajectories & Moves, Outreach, What-if, Checkpoint — matching the FastAPI endpoints above. Full request path (form submit → Vite proxy → FastAPI → error handling → UI) verified live in a browser.

Optional polish: `npm run build`, serve `frontend/dist/` from FastAPI via `StaticFiles` so a demo runs as one process instead of two dev servers.

## Known limitations / what's untested

Everything above is verified (real NUSMods data, real prereq-graph parsing, the TF-IDF embedding fallback end-to-end, the SQLite storage fallback's full function surface including a real `POST`/`GET /students` round trip through the running server, all 5 graphs compiling, the full frontend-to-backend request path). **Not yet exercised**: actual LLM-generated trajectories/leverage moves/outreach drafts, which needs a live `GROQ_API_KEY` (or AWS Bedrock) — this is the one thing with no fallback, since it's the actual product. Once `.env` has a Groq key, `demo_cli.py` walks the full narrative — trajectories → leverage moves → outreach draft → approve → log actions → checkpoint → what-if — end to end in the terminal against the local SQLite fallback, no AWS or Supabase setup required, which is the fastest way to confirm real model output before trusting the UI.
