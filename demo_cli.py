"""
Terminal walkthrough of the full narrative, invoking the compiled graphs
directly -- no HTTP/UI needed. Proves the graphs + Supabase are wired
correctly before (or instead of) the FastAPI/React layer, and doubles as a
live-demo fallback if the UI has issues on stage.

  uv run python demo_cli.py
"""

import json
import sys

# Windows consoles default to cp1252, which can't encode characters an LLM
# routinely produces (non-breaking hyphens, em-dashes, smart quotes) --
# observed live: a real trajectory response crashed print() on U+2011.
# Reconfigure stdout/stderr to UTF-8 before any output happens.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app import db
from app.common import banner
from app.graph import (
    build_checkpoint_graph,
    build_intake_graph,
    build_leverage_graph,
    build_outreach_graph,
    build_whatif_graph,
)

DEMO_STUDENT = {
    "student_id": "demo_001",
    "name": "Alex Tan (demo)",
    "year": 1,
    "cap": 4.3,
    "modules_taken": ["CS1101S", "CS1231S", "MA1521"],
    "interests": ["machine learning", "natural language processing", "AI safety"],
    "goal": "I think I want to work in AI, but I'm not sure whether I want to do research or industry.",
}


def _base_state(student_id: str, mode: str) -> dict:
    return {
        "messages": [], "mode": mode, "student_id": student_id, "profile": {},
        "weight_overrides": {}, "constraint_note": "", "trajectories": [],
        "candidate_pool": [], "leverage_moves": [], "outreach_target": {},
        "outreach_draft": {}, "baseline_checkpoint_id": None,
        "actions_since_baseline": [], "alignment_delta": {}, "result_ref_id": None,
    }


def main() -> None:
    banner("0. Create demo student")
    db.upsert_student(**{k: v for k, v in DEMO_STUDENT.items()})
    print(json.dumps(DEMO_STUDENT, indent=2))

    banner("1. Generate trajectories")
    intake_graph = build_intake_graph()
    final = intake_graph.invoke(_base_state(DEMO_STUDENT["student_id"], "intake"))
    for p in final["trajectories"]:
        print(f"\n-- {p['name']} --\n{p['rationale']}")
        for s in p["steps"]:
            print(f"  - {s}")

    banner("2. This semester's top 5 moves")
    leverage_graph = build_leverage_graph()
    final = leverage_graph.invoke(_base_state(DEMO_STUDENT["student_id"], "leverage"))
    for m in final["leverage_moves"]:
        print(f"\n[{m['move_type']}] {m['title']}")
        print(f"  why: {m['why']}")
        if m.get("deadline"):
            print(f"  deadline: {m['deadline']}")

    apply_move = next((m for m in final["leverage_moves"] if m["move_type"] == "apply" and m.get("ref_id")), None)
    if apply_move:
        banner(f"3. Draft outreach for: {apply_move['title']}")
        target_type = "professor" if apply_move["ref_id"].startswith("prof_") else "opportunity"
        outreach_graph = build_outreach_graph()
        state = _base_state(DEMO_STUDENT["student_id"], "outreach")
        state["outreach_target"] = {"type": target_type, "id": apply_move["ref_id"]}
        final = outreach_graph.invoke(state)
        draft = final["outreach_draft"]
        print(f"\nSubject: {draft['subject']}\n\n{draft['body']}")

        banner("4. Approve the draft")
        db.update_outreach_status(draft["draft_id"], "approved")
        print(f"draft #{draft['draft_id']} -> approved (never actually sent)")

    banner("5. Log a few actions (simulating time passing)")
    for action_type, ref_id, note in [
        ("outreach_sent", apply_move["ref_id"] if apply_move else "n/a", "sent the approved draft"),
        ("competition_joined", "comp_nus_ai_hackathon", "joined the AI hackathon"),
        ("manual_note", "", "started CS3244 this semester"),
    ]:
        row = db.log_action(DEMO_STUDENT["student_id"], action_type, ref_id, {"note": note})
        print(f"  logged #{row['action_id']}: {action_type} -- {note}")

    banner("6. Checkpoint -- how does this change the recommendation?")
    checkpoint_graph = build_checkpoint_graph()
    final = checkpoint_graph.invoke(_base_state(DEMO_STUDENT["student_id"], "checkpoint"))
    print("alignment_delta:", json.dumps(final["alignment_delta"], indent=2))

    banner("7. What-if: prioritize CAP over internships")
    whatif_graph = build_whatif_graph()
    state = _base_state(DEMO_STUDENT["student_id"], "whatif")
    state["weight_overrides"] = {"cap_weight": 0.8, "internship_weight": 0.1}
    final = whatif_graph.invoke(state)
    for p in final["trajectories"]:
        print(f"\n-- {p['name']} (what-if) --\n{p['rationale']}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:  # missing GROQ_API_KEY / AWS creds / Supabase config
        sys.exit(str(exc))
