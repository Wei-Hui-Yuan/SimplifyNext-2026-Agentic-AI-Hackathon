"""
Supabase backend — plain functions, no ORM. Selected by app/db.py when
SUPABASE_URL/SUPABASE_KEY are configured; see app/db_sqlite.py for the
zero-setup fallback used otherwise. Every function here must keep the exact
same signature as its counterpart in db_sqlite.py.

Schema created by data_pipeline/init_supabase.sql, not from here.
"""

from datetime import datetime, timezone

from app.common import SUPABASE_KEY, SUPABASE_URL, require_supabase_config

_client = None


def _sb():
    global _client
    if _client is None:
        require_supabase_config()
        from supabase import create_client

        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Connectivity check only — tables are created via init_supabase.sql."""
    _sb().table("students").select("student_id").limit(1).execute()


def upsert_student(
    student_id: str, name: str, year: int, cap: float,
    modules_taken: list[str], interests: list[str], goal: str,
) -> dict:
    row = {
        "student_id": student_id, "name": name, "year": year, "cap": cap,
        "modules_taken": modules_taken, "interests": interests, "goal": goal,
    }
    return _sb().table("students").upsert(row).execute().data[0]


def get_student(student_id: str) -> dict | None:
    res = _sb().table("students").select("*").eq("student_id", student_id).execute()
    return res.data[0] if res.data else None


def insert_trajectory_set(
    student_id: str, paths: list[dict], *, constraint_note: str | None = None, is_whatif: bool = False,
) -> dict:
    row = {
        "student_id": student_id, "constraint_note": constraint_note,
        "is_whatif": is_whatif, "paths": paths,
    }
    return _sb().table("trajectory_sets").insert(row).execute().data[0]


def get_latest_trajectory_set(student_id: str, *, is_whatif: bool = False) -> dict | None:
    res = (
        _sb().table("trajectory_sets").select("*")
        .eq("student_id", student_id).eq("is_whatif", is_whatif)
        .order("generated_at", desc=True).limit(1).execute()
    )
    return res.data[0] if res.data else None


def insert_leverage_list(student_id: str, trajectory_set_id: int, moves: list[dict]) -> dict:
    row = {"student_id": student_id, "trajectory_set_id": trajectory_set_id, "moves": moves}
    return _sb().table("leverage_lists").insert(row).execute().data[0]


def log_action(student_id: str, action_type: str, ref_id: str, detail: dict) -> dict:
    row = {"student_id": student_id, "action_type": action_type, "ref_id": ref_id, "detail": detail}
    return _sb().table("actions").insert(row).execute().data[0]


def get_actions_since(student_id: str, since_ts: str) -> list[dict]:
    res = (
        _sb().table("actions").select("*")
        .eq("student_id", student_id).gte("logged_at", since_ts)
        .order("logged_at").execute()
    )
    return res.data


def insert_outreach_draft(student_id: str, target_type: str, target_id: str, subject: str, body: str) -> dict:
    row = {
        "student_id": student_id, "target_type": target_type, "target_id": target_id,
        "subject": subject, "body": body, "status": "draft",
    }
    return _sb().table("outreach_drafts").insert(row).execute().data[0]


def update_outreach_status(draft_id: int, status: str) -> dict:
    row = {"status": status, "reviewed_at": _now()}
    return _sb().table("outreach_drafts").update(row).eq("draft_id", draft_id).execute().data[0]


def insert_checkpoint(
    student_id: str, baseline_trajectory_set_id: int, actions_since_baseline: list[dict],
    alignment_delta: dict, updated_recommendation: dict,
) -> dict:
    row = {
        "student_id": student_id, "baseline_trajectory_set_id": baseline_trajectory_set_id,
        "actions_since_baseline": actions_since_baseline, "alignment_delta": alignment_delta,
        "updated_recommendation": updated_recommendation,
    }
    return _sb().table("checkpoints").insert(row).execute().data[0]


def get_checkpoint_history(student_id: str) -> list[dict]:
    res = (
        _sb().table("checkpoints").select("*")
        .eq("student_id", student_id).order("created_at").execute()
    )
    return res.data
