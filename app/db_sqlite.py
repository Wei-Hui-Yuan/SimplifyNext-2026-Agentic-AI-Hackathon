"""
SQLite backend — zero-setup fallback selected by app/db.py when
SUPABASE_URL/SUPABASE_KEY aren't configured, so the app is fully testable
with nothing but a GROQ_API_KEY (embeddings already have their own fallback
to TF-IDF in data_pipeline/build_embeddings.py; this is the same idea for
storage). Every function here must keep the exact same signature as its
counterpart in db_supabase.py -- graph.py/tools.py/server.py call through
app/db.py and never know which backend answered.

Schema is created here (CREATE TABLE IF NOT EXISTS on every connection --
cheap and idempotent), unlike the Supabase path where it's a one-time SQL
editor step, since there's no equivalent "run this once" moment for a local
file that should just work the first time someone runs the app.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import SQLITE_DB_FILE

_SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name TEXT, year INTEGER, cap REAL,
    modules_taken TEXT, interests TEXT, goal TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS trajectory_sets (
    trajectory_set_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT, generated_at TEXT, constraint_note TEXT,
    is_whatif INTEGER DEFAULT 0, paths TEXT
);
CREATE TABLE IF NOT EXISTS leverage_lists (
    leverage_list_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT, trajectory_set_id INTEGER, generated_at TEXT, moves TEXT
);
CREATE TABLE IF NOT EXISTS actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT, action_type TEXT, ref_id TEXT, detail TEXT, logged_at TEXT
);
CREATE TABLE IF NOT EXISTS outreach_drafts (
    draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT, target_type TEXT, target_id TEXT, subject TEXT, body TEXT,
    status TEXT DEFAULT 'draft', created_at TEXT, reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT, baseline_trajectory_set_id INTEGER, created_at TEXT,
    actions_since_baseline TEXT, alignment_delta TEXT, updated_recommendation TEXT
);
"""


@contextmanager
def _conn():
    SQLITE_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _conn():
        pass  # opening the connection already runs the schema script


def upsert_student(
    student_id: str, name: str, year: int, cap: float,
    modules_taken: list[str], interests: list[str], goal: str,
) -> dict:
    with _conn() as c:
        c.execute(
            """
            INSERT INTO students (student_id, name, year, cap, modules_taken, interests, goal, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(student_id) DO UPDATE SET
                name=excluded.name, year=excluded.year, cap=excluded.cap,
                modules_taken=excluded.modules_taken, interests=excluded.interests, goal=excluded.goal
            """,
            (student_id, name, year, cap, json.dumps(modules_taken), json.dumps(interests), goal, _now()),
        )
    return get_student(student_id)


def get_student(student_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["modules_taken"] = json.loads(d["modules_taken"] or "[]")
    d["interests"] = json.loads(d["interests"] or "[]")
    return d


def insert_trajectory_set(
    student_id: str, paths: list[dict], *, constraint_note: str | None = None, is_whatif: bool = False,
) -> dict:
    now = _now()
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO trajectory_sets (student_id, generated_at, constraint_note, is_whatif, paths)
            VALUES (?, ?, ?, ?, ?)
            """,
            (student_id, now, constraint_note, int(is_whatif), json.dumps(paths)),
        )
        row_id = cur.lastrowid
    return {
        "trajectory_set_id": row_id, "student_id": student_id, "generated_at": now,
        "constraint_note": constraint_note, "is_whatif": is_whatif, "paths": paths,
    }


def get_latest_trajectory_set(student_id: str, *, is_whatif: bool = False) -> dict | None:
    with _conn() as c:
        row = c.execute(
            """
            SELECT * FROM trajectory_sets WHERE student_id = ? AND is_whatif = ?
            ORDER BY generated_at DESC LIMIT 1
            """,
            (student_id, int(is_whatif)),
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["paths"] = json.loads(d["paths"] or "[]")
    d["is_whatif"] = bool(d["is_whatif"])
    return d


def insert_leverage_list(student_id: str, trajectory_set_id: int | None, moves: list[dict]) -> dict:
    now = _now()
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO leverage_lists (student_id, trajectory_set_id, generated_at, moves)
            VALUES (?, ?, ?, ?)
            """,
            (student_id, trajectory_set_id, now, json.dumps(moves)),
        )
        row_id = cur.lastrowid
    return {
        "leverage_list_id": row_id, "student_id": student_id,
        "trajectory_set_id": trajectory_set_id, "generated_at": now, "moves": moves,
    }


def log_action(student_id: str, action_type: str, ref_id: str, detail: dict) -> dict:
    now = _now()
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO actions (student_id, action_type, ref_id, detail, logged_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (student_id, action_type, ref_id, json.dumps(detail), now),
        )
        row_id = cur.lastrowid
    return {
        "action_id": row_id, "student_id": student_id, "action_type": action_type,
        "ref_id": ref_id, "detail": detail, "logged_at": now,
    }


def get_actions_since(student_id: str, since_ts: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM actions WHERE student_id = ? AND logged_at >= ? ORDER BY logged_at",
            (student_id, since_ts),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["detail"] = json.loads(d["detail"] or "{}")
        result.append(d)
    return result


def insert_outreach_draft(student_id: str, target_type: str, target_id: str, subject: str, body: str) -> dict:
    now = _now()
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO outreach_drafts (student_id, target_type, target_id, subject, body, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'draft', ?)
            """,
            (student_id, target_type, target_id, subject, body, now),
        )
        row_id = cur.lastrowid
    return {
        "draft_id": row_id, "student_id": student_id, "target_type": target_type,
        "target_id": target_id, "subject": subject, "body": body, "status": "draft",
        "created_at": now, "reviewed_at": None,
    }


def update_outreach_status(draft_id: int, status: str) -> dict:
    now = _now()
    with _conn() as c:
        c.execute(
            "UPDATE outreach_drafts SET status = ?, reviewed_at = ? WHERE draft_id = ?",
            (status, now, draft_id),
        )
        row = c.execute("SELECT * FROM outreach_drafts WHERE draft_id = ?", (draft_id,)).fetchone()
    return dict(row) if row else None


def insert_checkpoint(
    student_id: str, baseline_trajectory_set_id: int | None, actions_since_baseline: list[dict],
    alignment_delta: dict, updated_recommendation: dict,
) -> dict:
    now = _now()
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO checkpoints (student_id, baseline_trajectory_set_id, created_at,
                actions_since_baseline, alignment_delta, updated_recommendation)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                student_id, baseline_trajectory_set_id, now,
                json.dumps(actions_since_baseline), json.dumps(alignment_delta),
                json.dumps(updated_recommendation),
            ),
        )
        row_id = cur.lastrowid
    return {
        "checkpoint_id": row_id, "student_id": student_id,
        "baseline_trajectory_set_id": baseline_trajectory_set_id, "created_at": now,
        "actions_since_baseline": actions_since_baseline, "alignment_delta": alignment_delta,
        "updated_recommendation": updated_recommendation,
    }


def get_checkpoint_history(student_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM checkpoints WHERE student_id = ? ORDER BY created_at", (student_id,)
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["actions_since_baseline"] = json.loads(d["actions_since_baseline"] or "[]")
        d["alignment_delta"] = json.loads(d["alignment_delta"] or "{}")
        d["updated_recommendation"] = json.loads(d["updated_recommendation"] or "{}")
        result.append(d)
    return result
