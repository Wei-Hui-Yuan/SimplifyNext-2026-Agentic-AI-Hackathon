"""
Runs the backend and frontend dev servers as one process group -- so a
single `Ctrl+C` (or one process dying on its own) stops both, instead of
leaving one dangling in a second terminal, which is what actually happened
during this branch's testing (the backend's --reload watcher and the Vite
dev server have each independently died silently on Windows).

The backend is started WITHOUT uvicorn's --reload: see docs/DEVELOPMENT.md's
"Troubleshooting" section -- the watchfiles-based reloader's subprocess has
been observed serving stale code (or exiting outright) after an edit. Restart
this script after backend changes instead.
"""

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _stream(proc: subprocess.Popen, label: str) -> None:
    for line in proc.stdout:
        print(f"[{label}] {line}", end="")


def main() -> None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        print("npm not found on PATH -- install Node.js first.")
        sys.exit(1)

    backend = subprocess.Popen(
        [sys.executable, "-c", "import uvicorn; uvicorn.run('app.server:app', host='0.0.0.0', port=8000)"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    frontend = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=ROOT / "frontend", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    procs = {"backend": backend, "frontend": frontend}

    for label, proc in procs.items():
        threading.Thread(target=_stream, args=(proc, label), daemon=True).start()

    print("\nBackend:  http://localhost:8000  (docs at /docs)")
    print("Frontend: http://localhost:5173")
    print("Press Ctrl+C to stop both.\n")

    try:
        while all(p.poll() is None for p in procs.values()):
            time.sleep(0.5)
        dead = next(label for label, p in procs.items() if p.poll() is not None)
        print(f"\n[{dead}] exited on its own (code {procs[dead].returncode}) -- stopping the other one too.")
    except KeyboardInterrupt:
        print("\nStopping both...")
    finally:
        for p in procs.values():
            if p.poll() is None:
                p.terminate()
        for p in procs.values():
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
