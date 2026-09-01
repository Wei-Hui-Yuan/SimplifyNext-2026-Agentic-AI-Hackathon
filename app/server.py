"""
FastAPI wrapper around the five compiled graphs. Thin on purpose -- every
route either invokes one compiled graph or calls db.py/tools.py directly for
the two actions that aren't agent logic (approving a draft, logging a manual
action).
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import db, planner
from app.graph import (
    build_checkpoint_graph,
    build_intake_graph,
    build_leverage_graph,
    build_outreach_graph,
    build_whatif_graph,
)

app = FastAPI(title="NUS Compass")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RuntimeError)
def _missing_config_handler(request: Request, exc: RuntimeError):
    # RuntimeError here means a missing GROQ_API_KEY / AWS credential / Supabase
    # config (see app/common.py) -- a config problem, not a client error, so 503
    # rather than 500, and the message is the friendly one written for a human
    # to read and act on.
    return JSONResponse(status_code=503, content={"detail": str(exc)})

_intake_graph = None
_leverage_graph = None
_outreach_graph = None
_whatif_graph = None
_checkpoint_graph = None


def _graphs():
    global _intake_graph, _leverage_graph, _outreach_graph, _whatif_graph, _checkpoint_graph
    if _intake_graph is None:
        _intake_graph = build_intake_graph()
        _leverage_graph = build_leverage_graph()
        _outreach_graph = build_outreach_graph()
        _whatif_graph = build_whatif_graph()
        _checkpoint_graph = build_checkpoint_graph()
    return _intake_graph, _leverage_graph, _outreach_graph, _whatif_graph, _checkpoint_graph


class StudentIn(BaseModel):
    student_id: str
    name: str
    year: int
    cap: float
    modules_taken: list[str] = []
    interests: list[str] = []
    goal: str


class OutreachIn(BaseModel):
    target_type: str
    target_id: str


class ApproveIn(BaseModel):
    decision: str  # "approved" | "rejected"


class WhatIfIn(BaseModel):
    weight_overrides: dict = {}


class ActionIn(BaseModel):
    action_type: str
    ref_id: str = ""
    detail: dict = {}


class WorkloadIn(BaseModel):
    module_codes: list[str]


def _base_state(student_id: str, mode: str) -> dict:
    return {
        "messages": [], "mode": mode, "student_id": student_id, "profile": {},
        "weight_overrides": {}, "constraint_note": "", "trajectories": [],
        "candidate_pool": [], "leverage_moves": [], "outreach_target": {},
        "outreach_draft": {}, "baseline_checkpoint_id": None,
        "actions_since_baseline": [], "alignment_delta": {}, "result_ref_id": None,
    }


@app.post("/students")
def create_student(body: StudentIn):
    return db.upsert_student(
        body.student_id, body.name, body.year, body.cap,
        body.modules_taken, body.interests, body.goal,
    )


@app.get("/students/{student_id}")
def get_student(student_id: str):
    student = db.get_student(student_id)
    if student is None:
        raise HTTPException(404, "student not found")
    return student


@app.post("/students/{student_id}/trajectories")
def create_trajectories(student_id: str):
    intake_graph, *_ = _graphs()
    try:
        return intake_graph.invoke(_base_state(student_id, "intake"))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/students/{student_id}/leverage-moves")
def create_leverage_moves(student_id: str):
    _, leverage_graph, *_ = _graphs()
    try:
        return leverage_graph.invoke(_base_state(student_id, "leverage"))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/students/{student_id}/outreach")
def create_outreach(student_id: str, body: OutreachIn):
    _, _, outreach_graph, _, _ = _graphs()
    state = _base_state(student_id, "outreach")
    state["outreach_target"] = {"type": body.target_type, "id": body.target_id}
    try:
        return outreach_graph.invoke(state)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/outreach/{draft_id}/approve")
def approve(draft_id: int, body: ApproveIn):
    # Calls db.py directly rather than the approve_outreach @tool: that tool
    # returns json.dumps(row) (a string, for eventual LLM/chat-mode
    # consumption per tools.py's own docstring), and returning a string
    # straight from a FastAPI route serializes as a JSON string literal, not
    # a JSON object -- the frontend's draft.subject/body/status all read as
    # undefined against that. Found live: Approve blanked out the whole
    # panel instead of showing the approved status.
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(400, f"invalid decision {body.decision!r}, expected 'approved' or 'rejected'")
    return db.update_outreach_status(draft_id, body.decision)


@app.post("/students/{student_id}/whatif")
def create_whatif(student_id: str, body: WhatIfIn):
    *_, whatif_graph, _ = _graphs()
    state = _base_state(student_id, "whatif")
    state["weight_overrides"] = body.weight_overrides
    try:
        return whatif_graph.invoke(state)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/students/{student_id}/checkpoint")
def create_checkpoint(student_id: str):
    *_, checkpoint_graph = _graphs()
    try:
        return checkpoint_graph.invoke(_base_state(student_id, "checkpoint"))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/students/{student_id}/actions")
def create_action(student_id: str, body: ActionIn):
    """Lets the demo 'fast-forward' time by logging actions directly,
    without waiting for a real second visit."""
    return db.log_action(student_id, body.action_type, body.ref_id, body.detail)


# ---------------------------------------------------------------------------
# Planner: pathfinding, unlock analysis, workload feasibility. All three are
# deterministic (no LLM call), so they call app/planner.py directly rather
# than going through a compiled graph -- same reasoning as /actions above.
# ---------------------------------------------------------------------------

@app.get("/planner/path/{student_id}/{module_code}")
def path_to_module(student_id: str, module_code: str):
    student = db.get_student(student_id)
    if student is None:
        raise HTTPException(404, "student not found")
    return planner.find_path_to_module(
        module_code, student["modules_taken"], current_year=student["year"],
    )


@app.get("/planner/unlocks/{module_code}")
def unlocks_for_module(module_code: str, student_id: str | None = None):
    trajectories = []
    if student_id:
        ts = db.get_latest_trajectory_set(student_id, is_whatif=False)
        if ts:
            trajectories = ts["paths"]
    step_texts = [s for path in trajectories for s in path.get("steps", [])]
    return planner.unlock_analysis(module_code, step_texts)


@app.post("/planner/workload")
def workload_check(body: WorkloadIn):
    return planner.workload_for_modules(body.module_codes)
