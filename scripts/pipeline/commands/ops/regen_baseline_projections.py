"""regen_baseline_projections.py — collapse the triple-baseline-writer problem.

CONTRACT: scripts/pipeline/commands/ops/regen_baseline_projections.py
  purpose: Before FRESH-001, `data/upstream_baselines.json` and `data/knowledge_state.json`
           were independently-writable "beliefs" about a product's accepted baseline SHA,
           alongside `merged/model.yaml.repo_sha` -- three stores that could (and, on
           pdf/java, did) disagree. Now that `merged/model.yaml` is git-tracked (T0), it
           can be the one canonical writer; this module makes the other two DERIVED,
           REGENERATED projections instead of independent writers. Because they are
           rebuilt from the tracked source, they cannot disagree with it by construction
           -- they can only be stale relative to it, which is trivially detected
           (check_staleness) and trivially fixed (rebuild_all).
  called from: promote.py's acceptance choke point (rebuild_one, replacing the old ad hoc
           direct calls to knowledge_state.record_baseline_accepted/update_upstream_baseline),
           and standalone by the scheduled freshness workflow (rebuild_all) as an
           independent reconciliation step.
  non-fatal by design: same philosophy as the code it replaces -- a projection-rebuild
           failure must never abort the promotion or the caller that triggered it.

Usage:
    python scripts/pipeline/commands/ops/regen_baseline_projections.py rebuild-all
    python scripts/pipeline/commands/ops/regen_baseline_projections.py check-staleness
    python scripts/pipeline/commands/ops/regen_baseline_projections.py check-staleness --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import yaml  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
UPSTREAM_BASELINES_PATH = REPO_ROOT / "data" / "upstream_baselines.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, KNOWLEDGE_ROOT, UPSTREAM_BASELINES_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
    UPSTREAM_BASELINES_PATH = REPO_ROOT / "data" / "upstream_baselines.json"
    import lib.knowledge_state as _ks
    _ks._REPO_ROOT = REPO_ROOT
    _ks._STATE_PATH = REPO_ROOT / "data" / "knowledge_state.json"
    _ks._LOCK_PATH = REPO_ROOT / "data" / "knowledge_state.json.lock"
    _ks._UPSTREAM_BASELINES_PATH = REPO_ROOT / "data" / "upstream_baselines.json"
    _ks._UPSTREAM_BASELINES_LOCK_PATH = REPO_ROOT / "data" / "upstream_baselines.json.lock"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def rebuild_one(family: str, platform: str, model: dict, *, run_id: "str | None" = None) -> bool:
    """Regenerate this product's entries in both derived projections from an
    already-loaded model.yaml dict (the canonical, now git-tracked source).

    Returns True on success. Non-fatal by design -- callers (promote.py) wrap this
    the same way they already wrap BaselineLedger.append(): a projection-rebuild
    failure must never fail the promotion that triggered it.
    """
    from lib.knowledge_state import record_baseline_accepted, update_upstream_baseline

    repo_sha = model.get("repo_sha", "")
    if not repo_sha:
        return False
    effective_run_id = run_id or f"regen-projections-{_now_iso()}"
    try:
        record_baseline_accepted(
            family, platform,
            repo_sha=repo_sha,
            sha_source="model.yaml",
            run_id=effective_run_id,
            accepted_at=model.get("promoted_at") or _now_iso(),
        )
        update_upstream_baseline(family, platform, repo_sha)
        return True
    except Exception as exc:
        print(f"WARNING: rebuild_one({family}/{platform}) failed (non-fatal): {exc}", file=sys.stderr)
        return False


def _iter_tracked_models() -> "list[tuple[str, str, dict]]":
    """Discover every knowledge/{family}/{platform}/merged/model.yaml on disk and
    return (family, platform, model_dict) for each one that parses cleanly."""
    results = []
    if not KNOWLEDGE_ROOT.is_dir():
        return results
    for family_dir in sorted(KNOWLEDGE_ROOT.iterdir()):
        if not family_dir.is_dir() or family_dir.name.startswith("_"):
            continue
        for platform_dir in sorted(family_dir.iterdir()):
            model_path = platform_dir / "merged" / "model.yaml"
            if not model_path.is_file():
                continue
            try:
                model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError):
                continue
            results.append((family_dir.name, platform_dir.name, model))
    return results


def rebuild_all() -> dict:
    """Full-fleet reconciliation: rebuild both projections from every tracked
    model.yaml on disk. Returns a summary dict."""
    rebuilt, skipped, errors = [], [], []
    for family, platform, model in _iter_tracked_models():
        if not model.get("repo_sha"):
            skipped.append(f"{family}/{platform}")
            continue
        ok = rebuild_one(family, platform, model, run_id=f"rebuild-all-{_now_iso()}")
        (rebuilt if ok else errors).append(f"{family}/{platform}")
    return {"rebuilt": rebuilt, "skipped": skipped, "errors": errors}


def check_staleness() -> list[dict]:
    """Compare data/upstream_baselines.json against each tracked model.yaml's
    repo_sha. Returns a list of {family, platform, projection_sha, source_sha}
    for every mismatch. In steady state (rebuild_all/rebuild_one kept current)
    this should be empty -- a non-empty result means the projection is stale
    relative to the canonical source, not that the two disagree unrecoverably."""
    try:
        baselines = json.loads(UPSTREAM_BASELINES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        baselines = {}

    mismatches = []
    for family, platform, model in _iter_tracked_models():
        source_sha = model.get("repo_sha", "")
        if not source_sha:
            continue
        key = f"{family}/{platform}"
        projection_sha = baselines.get(key)
        if projection_sha != source_sha:
            mismatches.append({
                "family": family, "platform": platform,
                "projection_sha": projection_sha, "source_sha": source_sha,
            })
    return mismatches


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate derived baseline projections from tracked model.yaml files")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rebuild-all", help="Rebuild both projections from every tracked model.yaml")
    p_check = sub.add_parser("check-staleness", help="Report projections stale relative to their tracked source")
    p_check.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args(argv)

    if args.command == "rebuild-all":
        result = rebuild_all()
        print(json.dumps(result, indent=2))
        return 0 if not result["errors"] else 1

    if args.command == "check-staleness":
        mismatches = check_staleness()
        if args.as_json:
            print(json.dumps(mismatches, indent=2))
        else:
            if not mismatches:
                print("OK: all projections match their tracked source model.yaml.")
            else:
                for m in mismatches:
                    print(f"STALE PROJECTION: {m['family']}/{m['platform']} "
                          f"projection={m['projection_sha']!r} source={m['source_sha']!r}")
        return 1 if mismatches else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
