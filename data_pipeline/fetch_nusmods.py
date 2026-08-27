"""
Fetch a scoped subset of the NUSMods catalog and cache it to disk.

Public API, no auth needed:
  https://api.nusmods.com/v2/{academicYear}/moduleList.json
  https://api.nusmods.com/v2/{academicYear}/modules/{CODE}.json

Two-stage filter: a cheap prefix pre-filter on module codes (bounds how many
detail calls we make), then an authoritative post-filter on each module's
real `department`/`faculty` field. Every fetch is cached per-file so an
interrupted run resumes without re-fetching, and a bad code is logged and
skipped rather than killing the run.

  uv run python data_pipeline/fetch_nusmods.py --list-prefixes   # discover real prefixes first
  uv run python data_pipeline/fetch_nusmods.py --limit 10        # dev iteration
  uv run python data_pipeline/fetch_nusmods.py                   # full scoped fetch
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import (
    ACADEMIC_YEAR,
    DEPARTMENT_NAME_ALLOWLIST,
    MODULE_CODE_PREFIXES,
    MODULES_DIR,
    RAW_DIR,
)

BASE_URL = "https://api.nusmods.com/v2"
PREFIX_RE = re.compile(r"^[A-Z]+")


def fetch_module_list(academic_year: str = ACADEMIC_YEAR, *, refresh: bool = False) -> list[dict]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = RAW_DIR / "moduleList.json"
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text())
    resp = httpx.get(f"{BASE_URL}/{academic_year}/moduleList.json", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    cache_path.write_text(json.dumps(data))
    return data


def fetch_module_detail(
    code: str, academic_year: str = ACADEMIC_YEAR, *, refresh: bool = False
) -> dict | None:
    MODULES_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = MODULES_DIR / f"{code}.json"
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text())
    try:
        resp = httpx.get(f"{BASE_URL}/{academic_year}/modules/{code}.json", timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — one bad code must not kill the run
        print(f"  [skip] {code}: {exc}")
        return None
    cache_path.write_text(json.dumps(data))
    return data


def list_prefixes(modules: list[dict]) -> None:
    counts = Counter(PREFIX_RE.match(m["moduleCode"]).group() for m in modules if PREFIX_RE.match(m["moduleCode"]))
    print(f"{len(modules)} modules total, {len(counts)} distinct prefixes:\n")
    for prefix, n in counts.most_common(40):
        print(f"  {prefix:<8} {n}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--academic-year", default=ACADEMIC_YEAR)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--list-prefixes", action="store_true")
    args = parser.parse_args()

    print(f"Fetching module list for {args.academic_year}...")
    all_modules = fetch_module_list(args.academic_year, refresh=args.refresh)

    if args.list_prefixes:
        list_prefixes(all_modules)
        return

    candidates = [
        m for m in all_modules
        if any(m["moduleCode"].startswith(p) for p in MODULE_CODE_PREFIXES)
    ]
    if args.limit:
        candidates = candidates[: args.limit]

    print(f"{len(all_modules)} modules total -> {len(candidates)} after prefix pre-filter")

    kept: list[str] = []
    dropped_by_dept = 0
    for i, m in enumerate(candidates, 1):
        code = m["moduleCode"]
        detail = fetch_module_detail(code, args.academic_year, refresh=args.refresh)
        if detail is None:
            continue
        if DEPARTMENT_NAME_ALLOWLIST and detail.get("department") not in DEPARTMENT_NAME_ALLOWLIST:
            dropped_by_dept += 1
            continue
        kept.append(code)
        if i % 50 == 0:
            print(f"  ...{i}/{len(candidates)}")
        time.sleep(0.05)

    manifest = {
        "academic_year": args.academic_year,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "candidates_after_prefix_filter": len(candidates),
        "dropped_by_department_filter": dropped_by_dept,
        "kept_after_dept_filter": len(kept),
        "codes": kept,
    }
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nKept {len(kept)} modules. Manifest -> {RAW_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()
