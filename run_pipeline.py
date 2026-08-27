"""Runs the data pipeline steps in order. Each step is also runnable on its
own -- see the docstring at the top of each file in data_pipeline/."""

import subprocess
import sys
from pathlib import Path

STEPS = [
    ["fetch_nusmods.py"],
    ["build_prereq_graph.py"],
    ["build_embeddings.py"],
]

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    for step in STEPS:
        script = root / "data_pipeline" / step[0]
        print(f"\n$ python {script.name} {' '.join(step[1:])}")
        result = subprocess.run([sys.executable, str(script), *step[1:]], cwd=root)
        if result.returncode != 0:
            sys.exit(result.returncode)
