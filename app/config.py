"""Shared config: academic year, department scoping, workspace paths.

WORKSPACE is pinned via Path(__file__), never a bare relative string — a bare
"./workspace" is relative to the shell's cwd, not this file, which is the
exact gotcha lab/section_5_deepagents/README.md calls out for
FilesystemBackend(root_dir="./workspace").
"""

from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent / "workspace"
RAW_DIR = WORKSPACE / "raw"
MODULES_DIR = RAW_DIR / "modules"
PROCESSED_DIR = WORKSPACE / "processed"

ACADEMIC_YEAR = "2025-2026"

# Stage 1: cheap pre-filter on moduleList.json module codes, to bound how many
# per-module detail calls fetch_nusmods.py makes. Verified against the live
# 2025-2026 catalog (7138 modules total) via
# `python data_pipeline/fetch_nusmods.py --list-prefixes`, then checking
# titles for "entrepreneurship"/"innovation" hits: BSP/BSN/TR/ETP/MNO are the
# real entrepreneurship-relevant undergrad prefixes (e.g. BSN3703
# "Entrepreneurial Strategy", ETP3321 "Summer Programme in
# Entrepreneurship") — an earlier guess of a single "BSP" prefix undercounted
# this badly. This set yields 727 candidate modules before the stage-2
# department filter, comfortably inside the 500-2000 target range.
MODULE_CODE_PREFIXES = [
    "CS", "IS", "CP",            # Computing
    "DSA", "ST", "MA",           # Data Science/Analytics, Statistics, Math
    "EE",                        # Electrical & Computer Engineering
    "BSP", "BSN", "TR", "ETP", "MNO",  # Business core + entrepreneurship track
]

# Stage 2: authoritative post-filter on each module's real `department`/
# `faculty` field. Left empty by default (stage 1 alone is applied) until
# someone fills this in after inspecting real fetched data — an empty
# allowlist here means "don't filter further", not "filter everything out".
DEPARTMENT_NAME_ALLOWLIST: list[str] = []

# Synthetic (non-NUSMods) data — hand-authored, no real people/companies.
SYNTHETIC_DIR = Path(__file__).resolve().parent.parent / "data_pipeline" / "synthetic"
PROFESSORS_FILE = SYNTHETIC_DIR / "professors.json"
OPPORTUNITIES_FILE = SYNTHETIC_DIR / "opportunities.json"
COMPETITIONS_FILE = SYNTHETIC_DIR / "competitions.json"
SCHOLARSHIPS_FILE = SYNTHETIC_DIR / "scholarships.json"
ALUMNI_FILE = SYNTHETIC_DIR / "alumni_trajectories.json"

EMBEDDINGS_FILE = PROCESSED_DIR / "embeddings.npy"
EMBEDDINGS_META_FILE = PROCESSED_DIR / "embeddings_meta.json"
PREREQ_GRAPH_FILE = PROCESSED_DIR / "prereq_graph.json"
