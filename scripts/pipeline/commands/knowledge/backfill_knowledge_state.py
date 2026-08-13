#!/usr/bin/env python3
"""
backfill_knowledge_state.py — one-time seed of data/knowledge_state.json from
whichever local knowledge/ caches this checkout happens to have.

CONTRACT: scripts/pipeline/commands/knowledge/backfill_knowledge_state.py
  purpose: data/knowledge_state.json starts empty and populates lazily as products
           get refreshed post-deploy (promote.py's new choke-point write, truth_audit.py's
           new write). Before check_backlog_reconciliation_gate.py (Step 32) goes live,
           run this once so products that were ALREADY refreshed under the old,
           non-durable-writing code don't show up as "insufficient_data" forever just
           because they haven't been refreshed AGAIN since this fix landed. Best-effort,
           local-cache-only (knowledge/ is gitignored, so this only backfills whatever
           this one checkout happens to have on disk) -- run again from any other
           checkout that has different products cached, or just let steady-state
           writes catch up over time; this script never blocks anything, it only adds.
  inputs:  knowledge/{family}/{platform}/merged/model.yaml (repo_sha), baseline_ledger.jsonl
           (accepted_at/run_id/sha_source when present, more precise than model.yaml alone)
  outputs: data/knowledge_state.json (accepted_baseline section only -- truth_audit and
           evidence_skips populate from real S-38/attach_evidence.py runs, not backfilled
           here, since there's no reliable historical verdict to backfill them FROM)
  idempotent: yes -- record_baseline_accepted() overwrites only the accepted_baseline
           section per product; safe to re-run.

Usage::
    .venv/Scripts/python scripts/pipeline/commands/knowledge/backfill_knowledge_state.py
    .venv/Scripts/python scripts/pipeline/commands/knowledge/backfill_knowledge_state.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PIPELINE_LIB_DIR = _REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_PIPELINE_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_LIB_DIR))

from knowledge_state import record_baseline_accepted  # noqa: E402

KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"


def discover_products(knowledge_root: Path = KNOWLEDGE_ROOT) -> list[tuple[str, str]]:
    """Return every (family, platform) pair with a local merged/model.yaml."""
    products: list[tuple[str, str]] = []
    if not knowledge_root.is_dir():
        return products
    for family_dir in sorted(knowledge_root.iterdir()):
        if not family_dir.is_dir():
            continue
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            if (platform_dir / "merged" / "model.yaml").is_file():
                products.append((family_dir.name, platform_dir.name))
    return products


def backfill_one(family: str, platform: str, knowledge_root: Path = KNOWLEDGE_ROOT) -> dict | None:
    """Seed accepted_baseline for one product from its local caches. Returns the
    recorded data, or None if no usable repo_sha was found (nothing to backfill)."""
    merged_dir = knowledge_root / family / platform / "merged"
    model_path = merged_dir / "model.yaml"
    if not model_path.is_file():
        return None
    try:
        model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    repo_sha = model.get("repo_sha")
    if not repo_sha:
        return None

    sha_source = "backfill"
    run_id = f"backfill-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    accepted_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    ledger_path = merged_dir / "baseline_ledger.jsonl"
    if ledger_path.is_file():
        try:
            last_accepted = None
            for line in ledger_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("status") == "accepted" and entry.get("new_repo_sha") == repo_sha:
                    last_accepted = entry
            if last_accepted is not None:
                sha_source = last_accepted.get("sha_source", sha_source)
                run_id = last_accepted.get("run_id", run_id)
                accepted_at = last_accepted.get("accepted_at", accepted_at)
        except (OSError, json.JSONDecodeError):
            pass  # fall back to the model.yaml-only defaults above

    record_baseline_accepted(
        family, platform,
        repo_sha=repo_sha, sha_source=sha_source, run_id=run_id, accepted_at=accepted_at,
    )
    return {"family": family, "platform": platform, "repo_sha": repo_sha, "sha_source": sha_source}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would be backfilled, write nothing")
    args = parser.parse_args(argv)

    # Read the module global fresh here (not as a function default-argument
    # binding, which is evaluated once at def-time and would silently ignore a
    # test's or caller's monkeypatch/override of KNOWLEDGE_ROOT).
    knowledge_root = KNOWLEDGE_ROOT
    products = discover_products(knowledge_root)
    if not products:
        print("backfill_knowledge_state: no local knowledge/ caches found — nothing to backfill")
        return 0

    backfilled = []
    for family, platform in products:
        if args.dry_run:
            merged_dir = knowledge_root / family / platform / "merged"
            model_path = merged_dir / "model.yaml"
            try:
                model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                model = {}
            if model.get("repo_sha"):
                backfilled.append({"family": family, "platform": platform, "repo_sha": model["repo_sha"]})
            continue
        result = backfill_one(family, platform, knowledge_root)
        if result is not None:
            backfilled.append(result)

    verb = "would backfill" if args.dry_run else "backfilled"
    print(f"backfill_knowledge_state: {verb} {len(backfilled)}/{len(products)} product(s)")
    for entry in backfilled:
        print(f"  {entry['family']}/{entry['platform']}: {entry['repo_sha'][:12]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
