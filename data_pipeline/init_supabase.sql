-- Run once in the Supabase SQL editor for a fresh project.
-- jsonb columns hold structured blobs directly — supabase-py accepts
-- dicts/lists as-is, no json.dumps needed on the Python side.

create table if not exists students (
    student_id text primary key,
    name text,
    year int,
    cap real,
    modules_taken jsonb,
    interests jsonb,
    goal text,
    created_at timestamptz default now()
);

create table if not exists trajectory_sets (
    trajectory_set_id bigint generated always as identity primary key,
    student_id text references students(student_id),
    generated_at timestamptz default now(),
    constraint_note text,
    is_whatif boolean default false,
    paths jsonb
);

create table if not exists leverage_lists (
    leverage_list_id bigint generated always as identity primary key,
    student_id text references students(student_id),
    trajectory_set_id bigint references trajectory_sets(trajectory_set_id),
    generated_at timestamptz default now(),
    moves jsonb
);

create table if not exists actions (
    action_id bigint generated always as identity primary key,
    student_id text references students(student_id),
    action_type text,
    ref_id text,
    detail jsonb,
    logged_at timestamptz default now()
);

create table if not exists outreach_drafts (
    draft_id bigint generated always as identity primary key,
    student_id text references students(student_id),
    target_type text,
    target_id text,
    subject text,
    body text,
    status text default 'draft',
    created_at timestamptz default now(),
    reviewed_at timestamptz
);

create table if not exists checkpoints (
    checkpoint_id bigint generated always as identity primary key,
    student_id text references students(student_id),
    baseline_trajectory_set_id bigint references trajectory_sets(trajectory_set_id),
    created_at timestamptz default now(),
    actions_since_baseline jsonb,
    alignment_delta jsonb,
    updated_recommendation jsonb
);

create index if not exists idx_actions_student_time on actions(student_id, logged_at);
create index if not exists idx_trajectory_sets_student on trajectory_sets(student_id, generated_at desc);
