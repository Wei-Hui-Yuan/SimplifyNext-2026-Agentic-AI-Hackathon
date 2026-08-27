"""
Build a prerequisite graph from cached NUSMods module details.

Real-data quirks confirmed by fetching CS2103 live before writing this:
  - prereqTree leaves are "CODE:GRADE" strings (e.g. "CS2030S:D"), not bare
    codes — the grade suffix must be stripped.
  - prereqTree can contain non-prerequisite rule keys too, e.g.
    {"cohort": {"rule": "MUST_BE_IN", "years": ["S:2017"]}} (seen on
    BSN3701) — only "and"/"or" keys are walked; anything else is ignored
    rather than mis-parsed as a code.
  - fulfillRequirements is already a flat list of bare codes — the reverse
    "unlocks" edge, given for free, no parsing needed.

v1 deliberately does not attempt full AND/OR satisfiability evaluation
against a student's modules_taken — that needs a boolean-logic solver that
isn't worth building under hackathon time pressure. Instead this stores the
flattened leaf-code list (for "you still need: X, Y" style display) alongside
the raw tree (for anyone who wants to render it later).

  uv run python data_pipeline/build_prereq_graph.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import MODULES_DIR, PREREQ_GRAPH_FILE, PROCESSED_DIR


def extract_leaf_codes(tree) -> list[str]:
    """Flatten a prereqTree into the bare module codes it references.
    Only walks "and"/"or" keys; other rule keys (e.g. "cohort") are ignored."""
    if tree is None:
        return []
    if isinstance(tree, str):
        return [tree.split(":")[0]]
    if isinstance(tree, dict):
        codes: list[str] = []
        for key in ("and", "or"):
            for item in tree.get(key, []):
                codes.extend(extract_leaf_codes(item))
        return codes
    return []


def build_graph(modules: dict[str, dict]) -> dict:
    nodes = {
        code: {
            "title": m.get("title"),
            "department": m.get("department"),
            "faculty": m.get("faculty"),
            "moduleCredit": m.get("moduleCredit"),
        }
        for code, m in modules.items()
    }

    edges: list[dict] = []
    for code, m in modules.items():
        for req_code in extract_leaf_codes(m.get("prereqTree")):
            edges.append({"from": req_code, "to": code, "type": "prereq"})
        for unlocked_code in m.get("fulfillRequirements") or []:
            edges.append({"from": code, "to": unlocked_code, "type": "unlocks"})

    return {"nodes": nodes, "edges": edges}


def main() -> None:
    modules = {}
    for f in MODULES_DIR.glob("*.json"):
        m = json.loads(f.read_text())
        modules[m["moduleCode"]] = m

    if not modules:
        sys.exit(
            "No cached modules found in workspace/raw/modules/. "
            "Run data_pipeline/fetch_nusmods.py first."
        )

    graph = build_graph(modules)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    PREREQ_GRAPH_FILE.write_text(json.dumps(graph))
    print(
        f"{len(modules)} modules -> {len(graph['nodes'])} nodes, "
        f"{len(graph['edges'])} edges -> {PREREQ_GRAPH_FILE}"
    )


if __name__ == "__main__":
    main()
