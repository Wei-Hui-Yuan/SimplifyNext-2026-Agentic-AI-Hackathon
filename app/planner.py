"""
Prerequisite-graph planning engine: pathfinding to a target module,
trajectory-aware unlock analysis, and workload feasibility -- the three
pieces of data_pipeline/build_prereq_graph.py's 727-node/5,030-edge graph
(and NUSMods' per-module `workload` field) that were fetched but never
actually used for anything beyond one flat scalar in app/graph.py's
score_candidates.

Self-contained on purpose: reads app/config.py paths directly, does not
import from app/graph.py, so graph.py can import THIS module without a
circular dependency -- graph.py's score_candidates is the one place that
calls into here.

Two data-shape quirks drive the design, both confirmed against the live
727-node graph before writing this:

1. Edge semantics. A "prereq" edge ({from: req, to: code}, derived from
   `code`'s prereqTree) and an "unlocks" edge ({from: code, to: dep},
   derived from `code`'s fulfillRequirements) encode the *same* directed
   relationship -- from=prerequisite, to=dependent -- just captured from two
   NUSMods fields that don't always agree with each other. _adjacency()
   merges both edge types into one adjacency in each direction: a missed
   edge is a correctness bug for pathfinding, a duplicate is not.

2. The flattened graph loses AND/OR structure, and
   data_pipeline/build_prereq_graph.py's own docstring says so explicitly
   ("v1 deliberately does not attempt full AND/OR satisfiability
   evaluation"). Confirmed live: CS2103's prereqTree is
   {"and": [{"or": ["CS2030S:D","CS2030:D","CS2030DE:D"]},
            {"or": [...5 CS2040 variants...]}]}, but the flattened edges
   treat all 8 as required. For pathfinding specifically, that's the
   difference between a correct plan and one that tells a student to take
   three different intro programming modules. So pathfinding reads
   prereqTree directly from the cached raw module JSON (_prereq_tree) and
   evaluates AND/OR properly, instead of using the flattened graph.
   unlock_analysis keeps using the flattened graph -- fulfillRequirements is
   already a flat list with no AND/OR ambiguity, so the graph is correct for
   that direction.

Grade requirements (the ":D" suffix on prereqTree leaves) are ignored -- we
track completion, not grades. A documented simplification, consistent with
build_prereq_graph.py's own stance on this data.
"""

import json
import re

from app.config import MODULES_DIR, PREREQ_GRAPH_FILE

_STOPWORDS = {"a", "an", "the", "and", "or", "to", "in", "of", "for", "with", "on"}

_graph_cache: dict | None = None
_adjacency_cache: tuple[dict[str, set], dict[str, set]] | None = None
_workload_cache: dict[str, float | None] = {}
_prereq_tree_cache: dict[str, object] = {}

DEFAULT_TOTAL_YEARS = 4
DEFAULT_SEMESTERS_PER_YEAR = 2
DEFAULT_SLOTS_PER_SEMESTER = 5
OVERCOMMIT_THRESHOLD_HOURS = 48.0

_MISSING = object()  # sentinel: distinguishes "module not cached" from "cached with prereqTree: null"


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOPWORDS}


# ---------------------------------------------------------------------------
# Flattened graph (workspace/processed/prereq_graph.json) -- used only for
# unlock_analysis, where fulfillRequirements has no AND/OR ambiguity.
# ---------------------------------------------------------------------------

def _load_graph() -> dict:
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = (
            json.loads(PREREQ_GRAPH_FILE.read_text())
            if PREREQ_GRAPH_FILE.exists() else {"nodes": {}, "edges": []}
        )
    return _graph_cache


def _adjacency() -> tuple[dict[str, set], dict[str, set]]:
    global _adjacency_cache
    if _adjacency_cache is None:
        graph = _load_graph()
        prereq_of: dict[str, set] = {}
        unlocks_of: dict[str, set] = {}
        for e in graph["edges"]:
            prereq, dependent = e["from"], e["to"]
            prereq_of.setdefault(dependent, set()).add(prereq)
            unlocks_of.setdefault(prereq, set()).add(dependent)
        _adjacency_cache = (prereq_of, unlocks_of)
    return _adjacency_cache


# ---------------------------------------------------------------------------
# Raw prereqTree (workspace/raw/modules/{code}.json) -- used only for
# pathfinding, where AND/OR structure actually matters.
# ---------------------------------------------------------------------------

def _module_json(code: str) -> dict | None:
    path = MODULES_DIR / f"{code}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _module_known(code: str) -> bool:
    return (MODULES_DIR / f"{code}.json").exists()


def _prereq_tree(code: str):
    """Raw prereqTree for `code`, or the _MISSING sentinel if the module
    isn't cached at all (distinct from a real `prereqTree: null`, which
    means "no prerequisites")."""
    if code not in _prereq_tree_cache:
        data = _module_json(code)
        _prereq_tree_cache[code] = data.get("prereqTree") if data is not None else _MISSING
    return _prereq_tree_cache[code]


def _pick_satisfying_leaves(tree, taken: set[str]) -> list[str]:
    """One leaf code per OR-branch (prefers an already-taken option; else
    the first-listed option), all leaves for an AND-branch. This is a
    greedy heuristic, not an optimal-path solver -- good enough to produce a
    genuinely valid plan, not necessarily the only or shortest one."""
    if tree is None or tree is _MISSING:
        return []
    if isinstance(tree, str):
        return [tree.split(":")[0]]
    if isinstance(tree, dict):
        if "and" in tree:
            out: list[str] = []
            for item in tree["and"]:
                out.extend(_pick_satisfying_leaves(item, taken))
            return out
        if "or" in tree:
            options = tree["or"]
            for item in options:
                leaves = _pick_satisfying_leaves(item, taken)
                if leaves and all(leaf in taken for leaf in leaves):
                    return leaves  # already-satisfied branch -- nothing new needed
            return _pick_satisfying_leaves(options[0], taken) if options else []
        return []  # unknown rule key (e.g. "cohort") -- can't evaluate, don't block a path on a rule we don't understand
    return []


def _resolve_missing_modules(
    code: str, taken: set[str], resolved: set[str], visiting: set[str], expanded: set[str],
) -> None:
    """Recursively expands what NEW modules must be added to satisfy
    `code`'s prereqTree, respecting AND/OR structure. Populates `resolved`
    in place. `visiting` guards against cycles in malformed data.

    `expanded` (not `resolved`) is the recursion guard -- `resolved` tracks
    "needs to be taken", which a leaf gets added to *before* we recurse into
    it (so the caller's loop can see it immediately). Guarding recursion on
    `resolved` instead of a separate `expanded` set means a module's own
    prerequisites never get walked, because by the time the recursive call
    checks its guard condition, the module is already sitting in `resolved`.
    Confirmed live: resolving CS3213 picked CS2103T (an alias of CS2103,
    first-listed in CS3213's OR-group) and silently dropped CS2103T's own
    CS2030/CS2040 requirement entirely."""
    if code in taken or code in expanded or code in visiting:
        return
    visiting.add(code)
    expanded.add(code)
    for leaf in _pick_satisfying_leaves(_prereq_tree(code), taken):
        if leaf not in taken:
            resolved.add(leaf)
        _resolve_missing_modules(leaf, taken, resolved, visiting, expanded)
    visiting.discard(code)


# ---------------------------------------------------------------------------
# Shared scheduling helpers
# ---------------------------------------------------------------------------

def _topo_order(codes: set[str], prereq_of: dict[str, set]) -> list[str]:
    """Kahn's algorithm restricted to `codes`. Deterministic tie-break
    (alphabetical) so results are reproducible run to run."""
    remaining = set(codes)
    result: list[str] = []
    while remaining:
        ready = sorted(c for c in remaining if not (prereq_of.get(c, set()) & remaining))
        if not ready:
            ready = [sorted(remaining)[0]]  # cycle/bad data -- break deterministically rather than hang
        for c in ready:
            result.append(c)
            remaining.discard(c)
    return result


def _bucket_into_semesters(ordered_codes: list[str], prereq_of: dict[str, set], slots_per_semester: int) -> list[list[str]]:
    placed: dict[str, int] = {}
    semesters: list[list[str]] = []
    ordered_set = set(ordered_codes)
    for code in ordered_codes:
        prereqs_in_plan = prereq_of.get(code, set()) & ordered_set
        earliest = max((placed[p] for p in prereqs_in_plan), default=-1) + 1
        sem = earliest
        while True:
            if sem >= len(semesters):
                semesters.append([])
            if len(semesters[sem]) < slots_per_semester:
                break
            sem += 1
        semesters[sem].append(code)
        placed[code] = sem
    return semesters


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_path_to_module(
    target_code: str, modules_taken: list[str], *,
    current_year: int = 1, total_years: int = DEFAULT_TOTAL_YEARS,
    semesters_per_year: int = DEFAULT_SEMESTERS_PER_YEAR,
    slots_per_semester: int = DEFAULT_SLOTS_PER_SEMESTER,
) -> dict:
    """Ordered plan to reach `target_code` from `modules_taken`, respecting
    real AND/OR prerequisite logic, or a clear reason it doesn't fit in the
    remaining semesters."""
    target_code = target_code.strip().upper()
    taken = {c.strip().upper() for c in modules_taken}

    if not _module_known(target_code):
        return {
            "target": target_code, "reachable": False, "already_completed": False,
            "steps": [], "semester_plan": [], "remaining_semesters": 0,
            "reason": f"{target_code} was not found in the scoped module catalog",
        }

    if target_code in taken:
        return {
            "target": target_code, "reachable": True, "already_completed": True,
            "steps": [], "semester_plan": [], "remaining_semesters": None, "reason": None,
        }

    resolved: set[str] = set()
    _resolve_missing_modules(target_code, taken, resolved, set(), set())
    resolved.add(target_code)

    prereq_of_local = {c: set(_pick_satisfying_leaves(_prereq_tree(c), taken)) & resolved for c in resolved}
    ordered = _topo_order(resolved, prereq_of_local)
    semester_plan = _bucket_into_semesters(ordered, prereq_of_local, slots_per_semester)

    remaining_years = max(total_years - current_year + 1, 0)
    remaining_semesters = remaining_years * semesters_per_year
    reachable = bool(remaining_semesters) and len(semester_plan) <= remaining_semesters

    reason = None
    if not reachable:
        reason = (
            f"needs {len(semester_plan)} semester(s) of prerequisites but only "
            f"{remaining_semesters} remain before graduation (Year {current_year} of {total_years})"
        )

    return {
        "target": target_code, "reachable": reachable, "already_completed": False,
        "steps": ordered, "semester_plan": semester_plan,
        "remaining_semesters": remaining_semesters, "reason": reason,
    }


def unlock_analysis(code: str, trajectory_step_texts: list[str] | None = None) -> dict:
    """How many modules `code` unlocks, and how many of those are actually
    relevant to the given trajectory step text -- vs. raw out-degree, which
    is all app/graph.py used before this."""
    code = code.strip().upper()
    graph = _load_graph()
    _, unlocks_of = _adjacency()
    downstream = sorted(unlocks_of.get(code, set()))

    relevant: list[str] = []
    if trajectory_step_texts:
        step_words = _words(" ".join(trajectory_step_texts))
        for d in downstream:
            node = graph["nodes"].get(d, {})
            title_words = _words(f"{d} {node.get('title', '')}")
            if title_words & step_words:
                relevant.append(d)

    return {
        "code": code,
        "unlocks_count": len(downstream),
        "unlocks": downstream[:10],
        "trajectory_relevant_count": len(relevant),
        "trajectory_relevant": relevant,
    }


def trajectory_aware_unlock_score(code: str, trajectories: list[dict] | None) -> float:
    """Drop-in replacement for app/graph.py's old
    _unlock_count_normalized(): scores a module's downstream unlocks against
    the student's actual chosen trajectory instead of raw out-degree. Falls
    back to the old raw-count normalization when there's no trajectory
    context yet."""
    step_texts = [s for path in (trajectories or []) for s in path.get("steps", [])]
    analysis = unlock_analysis(code, step_texts)
    if step_texts and analysis["unlocks_count"] > 0:
        return min(analysis["trajectory_relevant_count"] / 5.0, 1.0)
    return min(analysis["unlocks_count"] / 10.0, 1.0)


def module_workload_hours(code: str) -> float | None:
    """Sum of NUSMods' 5-element `workload` array (lecture/tutorial/lab/
    project/preparation hours per week -- NUSMods' documented convention,
    not something this repo's own fetched data explains anywhere). Read
    from the cached raw module JSON, since prereq_graph.json only keeps
    title/department/faculty/moduleCredit. None if uncached or null
    (observed live: one module, ETP3121, has workload: null)."""
    code = code.strip().upper()
    if code in _workload_cache:
        return _workload_cache[code]
    hours = None
    data = _module_json(code)
    if data is not None:
        workload = data.get("workload")
        if isinstance(workload, list):
            try:
                hours = float(sum(workload))
            except (TypeError, ValueError):
                hours = None
    _workload_cache[code] = hours
    return hours


def workload_for_modules(codes: list[str]) -> dict:
    """Feasibility check for a proposed set of modules taken together (e.g.
    one semester's plan): real weekly hours, and a warning when it's more
    than a student can sustain alongside anything else -- this is what backs
    the 'don't overcommit' promise from the pitch, previously unbacked by
    any real number."""
    codes = [c.strip().upper() for c in codes]
    per_module: dict[str, float | None] = {}
    missing: list[str] = []
    total = 0.0
    for code in codes:
        hours = module_workload_hours(code)
        per_module[code] = hours
        if hours is None:
            missing.append(code)
        else:
            total += hours

    overcommitted = total > OVERCOMMIT_THRESHOLD_HOURS
    warning = None
    if overcommitted:
        warning = (
            f"this plan is {total:.0f} hrs/week of coursework alone -- "
            f"above the {OVERCOMMIT_THRESHOLD_HOURS:.0f} hr/week most students "
            "can sustain alongside CCAs, a job, research, or sleep"
        )

    return {
        "codes": codes, "total_hours_per_week": round(total, 1),
        "per_module": per_module, "missing_data_for": missing,
        "overcommitted": overcommitted, "warning": warning,
    }
