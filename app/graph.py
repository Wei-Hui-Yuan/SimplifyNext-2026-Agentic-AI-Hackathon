"""
CompassState + five small, linear LangGraph graphs, one per feature. No
back-edges, no conditional loops -- none of these need iteration, which keeps
per-feature latency predictable for a live demo and explicitly avoids the
~90s/invoke DeepAgents cost measured in lab/section_5_deepagents (mostly
harness-prompt overhead this app doesn't need). Every model-calling node is a
single chat_model().with_structured_output(...) call -- the
04a_planning_decomposition.py pattern, not a ReAct tool-loop.

Five graphs share one state type and reuse nodes across each other
(generate_trajectories/explain_leverage_moves are called from 3 of the 5),
which is why they're plain `state -> dict` functions rather than baked into
one graph each.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app import db, planner, retrieval
from app.common import chat_model
from app.config import PREREQ_GRAPH_FILE
from app.schemas import LeverageList, OutreachDraft, TrajectorySet

_STOPWORDS = {"a", "an", "the", "and", "or", "to", "in", "of", "for", "with", "on"}
_prereq_graph_cache: dict | None = None


class CompassState(TypedDict):
    messages: Annotated[list, add_messages]  # unused by the 5 core graphs; reserved for an optional chat mode
    mode: str
    student_id: str
    profile: dict
    weight_overrides: dict
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


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOPWORDS}


def _prereq_graph() -> dict:
    global _prereq_graph_cache
    if _prereq_graph_cache is None:
        if PREREQ_GRAPH_FILE.exists():
            _prereq_graph_cache = json.loads(PREREQ_GRAPH_FILE.read_text())
        else:
            _prereq_graph_cache = {"nodes": {}, "edges": []}
    return _prereq_graph_cache


def _unlock_count_normalized(module_code: str) -> float:
    graph = _prereq_graph()
    n = sum(1 for e in graph["edges"] if e["from"] == module_code and e["type"] == "unlocks")
    return min(n / 10.0, 1.0)


def _trajectory_alignment(candidate_text: str, trajectories: list[dict]) -> float:
    if not trajectories:
        return 0.0
    cand_words = _words(candidate_text)
    if not cand_words:
        return 0.0
    best = 0.0
    for path in trajectories:
        step_words = _words(" ".join(path.get("steps", [])))
        if not step_words:
            continue
        overlap = len(cand_words & step_words) / len(cand_words)
        best = max(best, overlap)
    return best


def _urgency_bonus(deadline: str | None) -> float:
    if not deadline or deadline == "rolling":
        return 0.0
    try:
        due = datetime.fromisoformat(deadline).replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    days = (due - datetime.now(timezone.utc)).days
    if days < 0:
        return 0.0
    if days <= 14:
        return 1.0
    if days <= 30:
        return 0.5
    return 0.1


# ---------------------------------------------------------------------------
# Plain Python nodes -- no model call.
# ---------------------------------------------------------------------------

def load_student_context(state: CompassState) -> dict:
    student = db.get_student(state["student_id"])
    if student is None:
        raise ValueError(f"unknown student_id {state['student_id']!r} -- create it via POST /students first")
    profile = {
        "year": student["year"], "cap": student["cap"],
        "modules_taken": student["modules_taken"], "interests": student["interests"],
        "goal": student["goal"],
    }
    # The leverage/outreach graphs are invoked as separate requests AFTER the
    # intake graph already generated a baseline trajectory (see app/server.py:
    # POST /trajectories then POST /leverage-moves are two calls, not one
    # invoke()). Without loading it back here, score_candidates'
    # _trajectory_alignment and explain_leverage_moves' prompt would always
    # see an empty trajectories list for those two graphs. intake/whatif/
    # checkpoint immediately overwrite this with fresh trajectories anyway,
    # so it's harmless there.
    baseline = db.get_latest_trajectory_set(state["student_id"], is_whatif=False)
    return {"profile": profile, "trajectories": baseline["paths"] if baseline else []}


def score_candidates(state: CompassState) -> dict:
    profile = state["profile"]
    query_text = " ".join(profile.get("interests", [])) + " " + (profile.get("goal") or "")
    matrix, meta = retrieval.load_index()
    qv = retrieval.embed_query(query_text)

    pool = (
        retrieval.cosine_topk(qv, matrix, meta, k=15, record_type="module")
        + retrieval.cosine_topk(qv, matrix, meta, k=8, record_type="opportunity")
        + retrieval.cosine_topk(qv, matrix, meta, k=5, record_type="professor")
        + retrieval.cosine_topk(qv, matrix, meta, k=4, record_type="competition")
        + retrieval.cosine_topk(qv, matrix, meta, k=3, record_type="scholarship")
    )

    trajectories = state.get("trajectories", [])
    scored = []
    for c in pool:
        similarity = c["score"]
        trajectory_alignment = _trajectory_alignment(c["text"], trajectories)
        is_module = c["record_type"] == "module"
        # planner.trajectory_aware_unlock_score replaces the old flat
        # _unlock_count_normalized (raw out-degree only) -- it counts how
        # many of a module's downstream unlocks are actually relevant to the
        # student's chosen trajectory, falling back to the old raw-count
        # behavior when there's no trajectory context yet.
        unlock_count_normalized = (
            planner.trajectory_aware_unlock_score(c["id"], trajectories) if is_module else 0.0
        )
        urgency_bonus = _urgency_bonus(c["payload"].get("deadline"))
        leverage_score = (
            0.4 * similarity + 0.3 * trajectory_alignment
            + 0.2 * unlock_count_normalized + 0.1 * urgency_bonus
        )
        # Real NUSMods workload hours, previously fetched and never read --
        # lets downstream consumers (explain_leverage_moves, the frontend)
        # back the "don't overcommit" promise with an actual number.
        extra = {"workload_hours": planner.module_workload_hours(c["id"])} if is_module else {}
        scored.append({**c, **extra, "leverage_score": round(leverage_score, 4)})

    scored.sort(key=lambda c: c["leverage_score"], reverse=True)
    return {"candidate_pool": scored[:20]}


def apply_whatif_constraint(state: CompassState) -> dict:
    overrides = state.get("weight_overrides", {})
    parts = [f"{k.replace('_', ' ')}={v}" for k, v in overrides.items()]
    note = "What-if constraint: " + ", ".join(parts) if parts else ""
    return {
        "profile": {**state["profile"], "weight_overrides": overrides},
        "constraint_note": note,
    }


def compute_alignment_delta(state: CompassState) -> dict:
    baseline = db.get_latest_trajectory_set(state["student_id"], is_whatif=False)
    if baseline is None:
        return {"baseline_checkpoint_id": None, "actions_since_baseline": [], "alignment_delta": {}}

    actions = db.get_actions_since(state["student_id"], baseline["generated_at"])
    action_words: set[str] = set()
    for a in actions:
        action_words |= _words(a.get("ref_id", "")) | _words(json.dumps(a.get("detail") or {}))

    delta = {}
    for path in baseline["paths"]:
        step_words = _words(" ".join(path.get("steps", [])))
        delta[path["name"]] = (
            round(len(action_words & step_words) / len(step_words), 3) if step_words else 0.0
        )

    return {
        "baseline_checkpoint_id": baseline["trajectory_set_id"],
        "trajectories": baseline["paths"],
        "actions_since_baseline": actions,
        "alignment_delta": delta,
    }


def persist_result(state: CompassState) -> dict:
    mode = state["mode"]
    student_id = state["student_id"]

    if mode == "intake":
        row = db.insert_trajectory_set(student_id, state["trajectories"])
        return {"result_ref_id": row["trajectory_set_id"]}

    if mode == "leverage":
        ts = db.get_latest_trajectory_set(student_id, is_whatif=False)
        ts_id = ts["trajectory_set_id"] if ts else None
        row = db.insert_leverage_list(student_id, ts_id, state["leverage_moves"])
        return {"result_ref_id": row["leverage_list_id"]}

    if mode == "outreach":
        # draft_outreach_node already persisted the row.
        return {"result_ref_id": state["outreach_draft"]["draft_id"]}

    if mode == "whatif":
        ts = db.insert_trajectory_set(
            student_id, state["trajectories"],
            constraint_note=state.get("constraint_note"), is_whatif=True,
        )
        db.insert_leverage_list(student_id, ts["trajectory_set_id"], state["leverage_moves"])
        return {"result_ref_id": ts["trajectory_set_id"]}

    if mode == "checkpoint":
        row = db.insert_checkpoint(
            student_id, state.get("baseline_checkpoint_id"),
            state.get("actions_since_baseline", []), state.get("alignment_delta", {}),
            {"trajectories": state.get("trajectories"), "leverage_moves": state.get("leverage_moves")},
        )
        return {"result_ref_id": row["checkpoint_id"]}

    raise ValueError(f"unknown mode {mode!r}")


# ---------------------------------------------------------------------------
# Model-calling nodes -- one chat_model().with_structured_output(...) call each.
# ---------------------------------------------------------------------------

TRAJECTORY_SYSTEM_PROMPT = """You are NUS Compass, helping an NUS student see how today's choices
connect to different 3-year outcomes. Given the student's profile below, propose 2-3 distinct,
named trajectory paths (e.g. "AI Research", "AI Industry", "AI + Entrepreneurship" -- pick names
that fit THIS student's actual stated goal, don't force these exact three).

For each path give: a short rationale tied to their specific goal/interests, 4-7 concrete steps in
rough order (modules to take, an RA/internship type to pursue, projects to build -- general enough
that it doesn't need to name exact NUS module codes), and 2-3 likely outcomes.

If a constraint is given, respect it explicitly in the rationale (e.g. if told to weight CAP over
internships, the proposed paths should reflect a lighter external commitment load)."""


def generate_trajectories(state: CompassState) -> dict:
    planner = chat_model(temperature=0.2, max_tokens=3000).with_structured_output(TrajectorySet)
    prompt = json.dumps(state["profile"])
    if state.get("constraint_note"):
        prompt += f"\n\n{state['constraint_note']}"
    result = planner.invoke([SystemMessage(TRAJECTORY_SYSTEM_PROMPT), HumanMessage(prompt)])
    return {"trajectories": [p.model_dump() for p in result.paths]}


LEVERAGE_SYSTEM_PROMPT = """You are NUS Compass. Given a student's profile, their current
trajectory paths, and a pool of REAL candidate modules/opportunities/professors/competitions/
scholarships (each with an id and a leverage_score already computed), pick and explain exactly 5
highest-leverage moves for THIS semester.

Rules:
- Every move except a "skip" move must reference a real candidate from the pool by its id (put
  the id in ref_id) and real title -- do not invent modules or opportunities that aren't in the pool.
- move_type is one of: module | meeting | apply | skip | event.
- Include at least one "skip" move if the student's profile suggests overcommitment (e.g. many
  interests + a high course load already) -- explicitly recommending NOT doing something is a
  valid, valuable move, not a filler.
- why must be one sentence, specific to this student, not generic advice."""


def _display_title(record_type: str, payload: dict) -> str:
    # professors/alumni: `title` is an academic rank ("Assistant Professor"),
    # not a name -- `name` is the display label. Every other record_type
    # uses `title` as the display label instead.
    if record_type in ("professor", "alumni"):
        return payload.get("name") or payload.get("title")
    return payload.get("title") or payload.get("name")


def explain_leverage_moves(state: CompassState) -> dict:
    planner = chat_model(temperature=0.2, max_tokens=3000).with_structured_output(LeverageList)
    prompt = json.dumps({
        "profile": state["profile"],
        "trajectories": state.get("trajectories", []),
        "candidate_pool": [
            {"id": c["id"], "record_type": c["record_type"],
             "title": _display_title(c["record_type"], c["payload"]),
             "leverage_score": c["leverage_score"], "deadline": c["payload"].get("deadline")}
            for c in state.get("candidate_pool", [])
        ],
    })
    result = planner.invoke([SystemMessage(LEVERAGE_SYSTEM_PROMPT), HumanMessage(prompt)])
    return {"leverage_moves": [m.model_dump() for m in result.moves]}


OUTREACH_SYSTEM_PROMPT = """You are drafting a short outreach email on behalf of an NUS student,
to be reviewed and approved by the student before it is ever sent. Reference the student's real
background (modules taken, interests, goal) and the target's real details specifically -- avoid
generic phrasing. Keep the body under 150 words."""


def _find_record(record_type: str, record_id: str) -> dict | None:
    _matrix, meta = retrieval.load_index()
    for r in meta:
        if r["record_type"] == record_type and r["id"] == record_id:
            return r["payload"]
    return None


def draft_outreach_node(state: CompassState) -> dict:
    target = state["outreach_target"]
    target_record = _find_record(target["type"], target["id"]) or {}
    planner = chat_model(temperature=0.3, max_tokens=1500).with_structured_output(OutreachDraft)
    prompt = json.dumps({"profile": state["profile"], "target": target_record})
    result = planner.invoke([SystemMessage(OUTREACH_SYSTEM_PROMPT), HumanMessage(prompt)])
    draft_row = db.insert_outreach_draft(
        state["student_id"], target["type"], target["id"], result.subject, result.body
    )
    return {"outreach_draft": draft_row}


# ---------------------------------------------------------------------------
# Compiled graphs.
# ---------------------------------------------------------------------------

def _linear(*nodes) -> StateGraph:
    builder = StateGraph(CompassState)
    for fn in nodes:
        builder.add_node(fn.__name__, fn)
    builder.add_edge(START, nodes[0].__name__)
    for a, b in zip(nodes, nodes[1:]):
        builder.add_edge(a.__name__, b.__name__)
    builder.add_edge(nodes[-1].__name__, END)
    return builder.compile()


def build_intake_graph():
    return _linear(load_student_context, generate_trajectories, persist_result)


def build_leverage_graph():
    return _linear(load_student_context, score_candidates, explain_leverage_moves, persist_result)


def build_outreach_graph():
    return _linear(load_student_context, draft_outreach_node, persist_result)


def build_whatif_graph():
    return _linear(
        load_student_context, apply_whatif_constraint, generate_trajectories,
        score_candidates, explain_leverage_moves, persist_result,
    )


def build_checkpoint_graph():
    return _linear(
        load_student_context, compute_alignment_delta, score_candidates,
        explain_leverage_moves, persist_result,
    )
