"""promote_recover.py — auto-detect and correct interrupted knowledge-bundle swaps.

CONTRACT: scripts/pipeline/commands/ops/promote_recover.py
  purpose: promote.py's promote_atomic() (FRESH-001 T3) writes a full knowledge bundle
           into an isolated `merged.staging.{bundle_id}/` directory, then swaps it into
           place via merged/ -> merged.atomic-bak/ -> (staging becomes) merged/ -> delete
           merged.atomic-bak/. A crash between any two of those steps leaves the product
           directory in one of three well-defined, recoverable states. This module
           detects which state (if any) a product is in and corrects it -- run
           automatically as promote_atomic()'s own first step (self-healing
           precondition), so this is invisible in the common case, and also available
           as a standalone CLI for manual inspection/repair.
  full detail: docs/workflows/knowledge-bundle-recovery.md
  states:
    HEALTHY      merged/ exists, no .bak, no staging.* -- nothing to do.
    COLD_START   merged/ absent, no .bak, no staging.* -- never promoted yet, not a
                 swap-interruption case.
    STATE_A      merged/ exists AND staging.* exists AND no .bak: the swap never
                 started, or crashed before renaming merged/ -> .bak. The old bundle
                 is untouched. Recovery: delete the stale staging dir(s); the next
                 promote_atomic() run starts a fresh one.
    STATE_B      merged/ absent AND .bak exists: crashed between renaming
                 merged/ -> .bak and staging -> merged/. Recovery: rename
                 .bak -> merged/ (restoring the last known good bundle), delete any
                 stale staging dir(s).
    STATE_C      merged/ exists AND .bak exists: the swap itself fully succeeded
                 (both renames completed); only the final .bak cleanup is pending.
                 Recovery: verify merged/bundle_manifest.json is COMPLETE, then
                 delete .bak.
    AMBIGUOUS    more than one staging.* directory present alongside .bak -- should be
                 unreachable (promote_atomic refuses to start a new swap while .bak
                 exists), but if seen, refuse to guess and report for manual review.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))


def _staging_dirs(product_dir: Path) -> "list[Path]":
    if not product_dir.is_dir():
        return []
    return sorted(p for p in product_dir.glob("merged.staging.*") if p.is_dir())


def detect_state(product_dir: Path) -> dict:
    """Classify the current on-disk state of product_dir (knowledge/{family}/{platform}/).

    Returns {"state": <name>, "merged_dir": Path, "bak_dir": Path, "staging_dirs": [Path]}.
    Pure inspection -- never mutates anything.
    """
    merged_dir = product_dir / "merged"
    bak_dir = product_dir / "merged.atomic-bak"
    staging = _staging_dirs(product_dir)

    merged_exists = merged_dir.is_dir()
    bak_exists = bak_dir.is_dir()

    if merged_exists and bak_exists and staging:
        state = "AMBIGUOUS"
    elif merged_exists and bak_exists:
        state = "STATE_C"
    elif not merged_exists and bak_exists:
        state = "STATE_B"
    elif merged_exists and staging and not bak_exists:
        state = "STATE_A"
    elif merged_exists:
        state = "HEALTHY"
    else:
        state = "COLD_START"

    return {"state": state, "merged_dir": merged_dir, "bak_dir": bak_dir, "staging_dirs": staging}


def recover(product_dir: Path) -> dict:
    """Auto-correct product_dir if it is in a recoverable interrupted-swap state.

    Returns {"state": ..., "action_taken": ..., "ok": bool}. HEALTHY and COLD_START
    are reported as ok=True with action_taken="none" (nothing to correct). AMBIGUOUS
    is reported as ok=False -- refuse to guess, surface for manual review.
    """
    info = detect_state(product_dir)
    state = info["state"]
    merged_dir, bak_dir, staging = info["merged_dir"], info["bak_dir"], info["staging_dirs"]

    if state in ("HEALTHY", "COLD_START"):
        return {"state": state, "action_taken": "none", "ok": True}

    if state == "STATE_A":
        for s in staging:
            shutil.rmtree(s, ignore_errors=True)
        return {"state": state, "action_taken": f"removed {len(staging)} stale staging dir(s); "
                                                  f"merged/ untouched (swap never started)", "ok": True}

    if state == "STATE_B":
        for s in staging:
            shutil.rmtree(s, ignore_errors=True)
        try:
            bak_dir.rename(merged_dir)
        except OSError as exc:
            return {"state": state, "action_taken": f"FAILED to restore merged.atomic-bak/ -> merged/: {exc}", "ok": False}
        return {"state": state, "action_taken": "restored merged.atomic-bak/ -> merged/ "
                                                  "(swap was interrupted before completing)", "ok": True}

    if state == "STATE_C":
        manifest_path = merged_dir / "bundle_manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"state": state, "action_taken": f"REFUSING to delete merged.atomic-bak/: could not verify "
                                                      f"merged/bundle_manifest.json ({exc})", "ok": False}
        if manifest.get("status") != "COMPLETE":
            return {"state": state, "action_taken": f"REFUSING to delete merged.atomic-bak/: merged/bundle_manifest.json "
                                                      f"status={manifest.get('status')!r}, not COMPLETE", "ok": False}
        shutil.rmtree(bak_dir, ignore_errors=True)
        return {"state": state, "action_taken": "verified merged/bundle_manifest.json is COMPLETE; "
                                                  "deleted merged.atomic-bak/ (swap had already succeeded)", "ok": True}

    # AMBIGUOUS
    return {"state": state, "action_taken": "refusing to guess -- merged/, merged.atomic-bak/, and "
                                              f"{len(staging)} staging dir(s) all present; "
                                              "inspect manually", "ok": False}


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Detect and correct interrupted knowledge-bundle swaps")
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--knowledge-root", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Only report the detected state, do not correct it")
    args = parser.parse_args(argv)

    base = (Path(args.knowledge_root) if args.knowledge_root else Path("knowledge")) / args.family / args.platform

    if args.dry_run:
        info = detect_state(base)
        print(f"STATE: {info['state']}")
        print(f"  merged_dir exists: {info['merged_dir'].is_dir()}")
        print(f"  bak_dir exists: {info['bak_dir'].is_dir()}")
        print(f"  staging_dirs: {[str(p) for p in info['staging_dirs']]}")
        return 0

    result = recover(base)
    print(f"STATE: {result['state']}")
    print(f"ACTION: {result['action_taken']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
