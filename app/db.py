"""
Storage dispatcher -- graph.py/tools.py/server.py import from here and never
know or care which backend answered. Supabase when SUPABASE_URL/SUPABASE_KEY
are configured (app/db_supabase.py); otherwise a local SQLite file that needs
no setup at all (app/db_sqlite.py) -- the same fallback shape
data_pipeline/build_embeddings.py already uses for embeddings, so the whole
app is testable with nothing but a GROQ_API_KEY.
"""

from app.common import SUPABASE_KEY, SUPABASE_URL

if SUPABASE_URL and SUPABASE_KEY:
    from app import db_supabase as _backend

    BACKEND = "supabase"
else:
    from app import db_sqlite as _backend

    BACKEND = "sqlite"

init_db = _backend.init_db
upsert_student = _backend.upsert_student
get_student = _backend.get_student
insert_trajectory_set = _backend.insert_trajectory_set
get_latest_trajectory_set = _backend.get_latest_trajectory_set
insert_leverage_list = _backend.insert_leverage_list
log_action = _backend.log_action
get_actions_since = _backend.get_actions_since
insert_outreach_draft = _backend.insert_outreach_draft
update_outreach_status = _backend.update_outreach_status
insert_checkpoint = _backend.insert_checkpoint
get_checkpoint_history = _backend.get_checkpoint_history
