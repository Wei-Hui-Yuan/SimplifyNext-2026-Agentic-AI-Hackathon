"""
@tool surface. Most of this is NOT on the core demo's hot path -- the 5
compiled graphs in graph.py call the underlying functions directly (plain
Python, no tool-calling loop needed for a single-shot structured-output
call). This file exists for:
  (a) utilities the deterministic graph nodes call, wrapped as callables the
      graphs can also expose to an optional day-2 "chat with Compass" mode
      via create_agent(tools=[...]);
  (b) the InjectedState/Command(update=...) tools that specifically must
      know student_id from graph state rather than from the model, so the
      model can never write to (or draft outreach for) the wrong student.

Round-trip/error convention throughout: pure-read tools return a JSON string
and never raise -- an error becomes an error string, same as
lab/section_2_agentic_ai_basic/02_tools.py's get_order.
"""

import json
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app import db, retrieval
from app.config import PREREQ_GRAPH_FILE


@tool
def search_modules(query: str, top_k: int = 5) -> str:
    """Search cached NUSMods module embeddings by free-text query.
    Returns a JSON string: list of {moduleCode, title, department, score}."""
    try:
        matrix, meta = retrieval.load_index()
        hits = retrieval.cosine_topk(
            retrieval.embed_query(query), matrix, meta, k=top_k, record_type="module"
        )
        return json.dumps([
            {**h["payload"], "score": round(h["score"], 3)} for h in hits
        ])
    except Exception as exc:  # noqa: BLE001
        return f"search_modules failed: {exc}"


@tool
def match_opportunities(query: str, record_type: str = "opportunity", top_k: int = 5) -> str:
    """Match student interests/goal text against synthetic records.
    record_type: 'opportunity' | 'professor' | 'competition' | 'scholarship' | 'alumni'.
    Returns a JSON string list of matches with similarity scores."""
    try:
        matrix, meta = retrieval.load_index()
        hits = retrieval.cosine_topk(
            retrieval.embed_query(query), matrix, meta, k=top_k, record_type=record_type
        )
        return json.dumps([
            {**h["payload"], "score": round(h["score"], 3)} for h in hits
        ])
    except Exception as exc:  # noqa: BLE001
        return f"match_opportunities failed: {exc}"


@tool
def get_prereq_chain(module_code: str) -> str:
    """Return the prereqs and 'unlocks' list for one module code from the
    cached prereq graph. Returns an error string (not raised) if unknown."""
    if not PREREQ_GRAPH_FILE.exists():
        return "prereq graph not built yet -- run data_pipeline/build_prereq_graph.py"
    graph = json.loads(PREREQ_GRAPH_FILE.read_text())
    if module_code not in graph["nodes"]:
        return f"unknown module code: {module_code}"
    prereqs = [e["from"] for e in graph["edges"] if e["to"] == module_code and e["type"] == "prereq"]
    unlocks = [e["to"] for e in graph["edges"] if e["from"] == module_code and e["type"] == "unlocks"]
    return json.dumps({"module": module_code, "prereqs": prereqs, "unlocks": unlocks})


@tool
def approve_outreach(draft_id: int, decision: str) -> str:
    """Human-in-the-loop approval ('approved'|'rejected') for a staged draft.
    Updates the stored status only -- never sends a real email. Called
    directly from server.py, not through a model loop, since approval is a
    human action, not something an LLM should decide."""
    if decision not in ("approved", "rejected"):
        return f"invalid decision {decision!r}, expected 'approved' or 'rejected'"
    row = db.update_outreach_status(draft_id, decision)
    return json.dumps(row)


@tool
def draft_outreach(
    target_type: str,
    target_id: str,
    student_id_hint: str,
    subject: str,
    body: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Stage a drafted outreach message for human review (never sent).
    student_id comes from graph state, not the model -- student_id_hint is
    accepted but ignored, so a model can't be talked into writing to the
    wrong student's record; see lab/section_4_langgraph/02_tool_writes_state.py."""
    draft = db.insert_outreach_draft(state["student_id"], target_type, target_id, subject, body)
    return Command(update={
        "outreach_draft": draft,
        "messages": [ToolMessage(f"drafted outreach #{draft['draft_id']}", tool_call_id=tool_call_id)],
    })


@tool
def log_action(
    action_type: str,
    ref_id: str,
    detail: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Record a real student action (module_enrolled | outreach_sent |
    opportunity_applied | competition_joined | manual_note). This is the
    write path the checkpoint/adaptation feature reads back via
    db.get_actions_since()."""
    row = db.log_action(state["student_id"], action_type, ref_id, {"note": detail})
    return Command(update={
        "messages": [ToolMessage(f"logged action #{row['action_id']}", tool_call_id=tool_call_id)],
    })
