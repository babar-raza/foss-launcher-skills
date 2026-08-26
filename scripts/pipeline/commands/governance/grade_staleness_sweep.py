"""grade_staleness_sweep.py — cheap, deterministic, no-LLM tripwire that flags
pages whose persisted grade (A/B) no longer matches a live audit.py FAIL.

Phase C (MT037-2026-08-24-FOSS-PORTFOLIO-FORENSIC-HEAL blind-spot audit,
A-09 repair): closes a real, confirmed gap -- a page could carry a live,
deterministically-reproducible defect while its persisted grade still read
A/B, because nothing ever re-checked a graded page's live state after the
fact. Modeled directly on this repo's own S-94 change-sweep cost-containment
pattern: a cheap, deterministic, no-LLM full-portfolio scan that only FLAGS
(never auto-corrects) findings, routing the flagged subset to governed
review (S-90) rather than an automated grade downgrade -- a possibly-buggy
check must never silently rewrite a page's grade on its own say-so.

This sweep does NOT run content_eval or gap-eval (both LLM-capable, heavier,
and already have their own invocation paths) -- it deliberately only
re-checks the same fast, deterministic checks audit.py already runs, exactly
the class of defect this campaign found (grade: A pages with live,
deterministic audit.py FAILs) sitting undetected.

Usage:
    python scripts/pipeline/commands/governance/grade_staleness_sweep.py --all
    python scripts/pipeline/commands/governance/grade_staleness_sweep.py --family tex --platform python
    python scripts/pipeline/commands/governance/grade_staleness_sweep.py --all --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]  # commands/governance/ -> commands/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from grade_manifest import load_manifest, mark_stale, clear_stale  # noqa: E402
from audit.runner import audit_files  # noqa: E402

_DEFAULT_REPO_ROOT = _PIPELINE_ROOT.parent.parent
_REPO_ROOT = _DEFAULT_REPO_ROOT
_STALE_ELIGIBLE_GRADES = frozenset({"A", "B"})
_DEFAULT_REPORT_DIR = _DEFAULT_REPO_ROOT / "reports" / "governance"

_AUDIT_FILES_FN = audit_files
_UNSET = object()


def configure(*, repo_root: "Path | str | None" = _UNSET, audit_files_fn=_UNSET) -> None:
    """Override module-level path/dependency seams for testing.

    Each parameter is independently sticky: passing it explicitly as ``None``
    resets that one seam to its real default; omitting it leaves it
    unchanged (so a test can set ``repo_root`` once in an autouse fixture and
    later swap ``audit_files_fn`` per-test without losing the repo_root
    override).
    """
    global _REPO_ROOT, _AUDIT_FILES_FN
    if repo_root is not _UNSET:
        _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    if audit_files_fn is not _UNSET:
        _AUDIT_FILES_FN = audit_files_fn if audit_files_fn is not None else audit_files


def _repo_relative(path_str: str) -> Path:
    """Resolve a manifest key (repo-relative, forward-slash) to a real Path."""
    return _REPO_ROOT / path_str


def sweep(
    *,
    family: str | None = None,
    platform: str | None = None,
    manifest_path: Path | str | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the sweep and return a summary dict. Does not print or write a
    report file itself -- see main() for the CLI's reporting behavior.
    """
    manifest = load_manifest(manifest_path)

    candidates: list[str] = []
    for rel_path, entry in manifest.items():
        if entry.get("grade") not in _STALE_ELIGIBLE_GRADES:
            continue
        if family and f"/{family}/" not in rel_path:
            continue
        if platform and f"/{platform}/" not in rel_path:
            continue
        real_path = _repo_relative(rel_path)
        if not real_path.is_file():
            continue  # manifest entry for a page that no longer exists on disk
        candidates.append(rel_path)

    summary = {
        "swept_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pages_checked": len(candidates),
        "newly_flagged_stale": [],
        "cleared_stale": [],
        "already_stale_still_stale": [],
        "clean": 0,
        "dry_run": dry_run,
    }

    if not candidates:
        return summary

    real_paths = [_repo_relative(p) for p in candidates]
    findings = _AUDIT_FILES_FN(real_paths, check_evidence=True, check_snippets=False)

    fails_by_file: dict[str, list] = {}
    for f in findings:
        if f.level != "FAIL":
            continue
        # Finding.filepath is repo-relative (matches audit.py's own convention).
        key = str(f.filepath).replace("\\", "/")
        fails_by_file.setdefault(key, []).append(f)

    for rel_path in candidates:
        entry = manifest.get(rel_path, {})
        was_stale = bool(entry.get("stale"))
        live_fails = fails_by_file.get(rel_path, [])

        if live_fails:
            reason = (
                f"grade_staleness_sweep found {len(live_fails)} live audit.py FAIL(s) "
                f"on a page graded {entry.get('grade')}: "
                + "; ".join(f.message[:120] for f in live_fails[:3])
            )
            summary["newly_flagged_stale"].append({"file": rel_path, "reason": reason})
            if not dry_run:
                mark_stale(rel_path, reason, manifest=manifest, save=False)
        elif was_stale:
            summary["cleared_stale"].append(rel_path)
            if not dry_run:
                clear_stale(rel_path, manifest=manifest, save=False)
        else:
            summary["clean"] += 1

    if not dry_run and (summary["newly_flagged_stale"] or summary["cleared_stale"]):
        from grade_manifest import save_manifest
        save_manifest(manifest, manifest_path)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="Sweep every graded page in the manifest")
    scope.add_argument("--family", help="Scope to one family (optionally combine with --platform)")
    parser.add_argument("--platform", help="Scope to one platform (requires --family for a single product)")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not write manifest changes")
    parser.add_argument("--out", default=None, help="Report output path (default: reports/governance/grade-staleness-sweep-<timestamp>.json)")
    args = parser.parse_args()

    if args.platform and not args.family and not args.all:
        parser.error("--platform requires --family unless --all is given")

    result = sweep(family=args.family, platform=args.platform, dry_run=args.dry_run)

    out_path = Path(args.out) if args.out else (
        _DEFAULT_REPORT_DIR / f"grade-staleness-sweep-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    if not args.dry_run or args.out:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Report written to {out_path}")

    print(
        f"Swept {result['pages_checked']} page(s): "
        f"{len(result['newly_flagged_stale'])} newly flagged stale, "
        f"{len(result['cleared_stale'])} cleared, "
        f"{result['clean']} clean."
    )
    for item in result["newly_flagged_stale"]:
        print(f"  STALE: {item['file']}")
        print(f"    {item['reason']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
