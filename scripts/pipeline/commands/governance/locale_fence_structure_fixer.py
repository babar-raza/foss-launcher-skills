"""locale_fence_structure_fixer.py -- MT073 TC-09 (LOCALE-CODE-BLOCK-DEFECT-
REMEDIATION).

CLI for fence_structure_repair.py. Re-runs locale_code_block_equivalence.py's
own `run_check()` (reused directly, not reimplemented) to find ST-215 Bucket 3
(isolated drift: a LANG_MISMATCH/COUNT_MISMATCH group whose locale fan-out is
1-3) candidates, then asks fence_structure_repair.repair_file() to compute a
verified structural repair for each affected (english, locale) file pair.

Every write is gated on repair_file()'s own mandatory post-repair
verification (the repaired locale's block list must exactly match English's,
by canonical language AND sha256_norm content) -- a file whose real defect
doesn't match either known corruption signature is reported as `unresolved`
and NEVER written to, dry-run or not. This is deliberate: TC-09's own
categorization pass found several Bucket-3 files carry a SEPARATE, unrelated
content-drift defect on top of (or instead of) the fence-structure one this
tool targets, and guessing at those would risk live-site content, not just
this taskcard's own file.

Usage:
    python locale_fence_structure_fixer.py --report out.json
    python locale_fence_structure_fixer.py --report out.json --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent
_LIB_DIR = _PIPELINE_ROOT / "lib"
for _p in (str(_PIPELINE_ROOT), str(_LIB_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from example_verification.fence_structure_repair import repair_file  # noqa: E402
from locale_code_block_equivalence import run_check  # noqa: E402

_BUCKET3_MIN_FANOUT = 1
_BUCKET3_MAX_FANOUT = 3
_TARGET_KINDS = {"LANG_MISMATCH", "COUNT_MISMATCH"}


def find_bucket3_pairs(*, repo_root: "Path | None" = None) -> "list[tuple[str, str]]":
    """(en_path, locale_path) pairs for every Bucket-3 LANG_MISMATCH/
    COUNT_MISMATCH group, deduplicated across block indices (a page with N
    affected blocks in the same locale needs exactly one repair attempt, not
    N -- repair_file() already reconciles every English block in one pass)."""
    report = run_check(repo_root=repo_root)
    groups: "dict[tuple, list[dict]]" = defaultdict(list)
    for f in report["findings"]:
        if f["kind"] not in _TARGET_KINDS:
            continue
        groups[(f["en_path"], f["block_index"], f["kind"])].append(f)

    pairs: "set[tuple[str, str]]" = set()
    for (en_path, _block_idx, _kind), items in groups.items():
        if not (_BUCKET3_MIN_FANOUT <= len(items) <= _BUCKET3_MAX_FANOUT):
            continue
        for item in items:
            pairs.add((en_path, item["locale_path"]))
    return sorted(pairs)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="write the full result list to this path")
    parser.add_argument("--apply", action="store_true", help="write verified repairs to disk (default: dry-run)")
    parser.add_argument("--limit", type=int, help="process at most N file pairs (for reviewable batches)")
    parser.add_argument("--repo-root", type=Path, default=None, help="override repo root (testing)")
    args = parser.parse_args(argv)

    repo_root = args.repo_root or _PIPELINE_ROOT.parent.parent
    pairs = find_bucket3_pairs(repo_root=repo_root)
    if args.limit:
        pairs = pairs[: args.limit]

    results = []
    applied = 0
    status_counts: "dict[str, int]" = defaultdict(int)
    for en_path, loc_path in pairs:
        en_abs = repo_root / en_path
        loc_abs = repo_root / loc_path
        result = repair_file(en_abs, loc_abs)
        status_counts[result.status] += 1
        entry = {
            "en_path": en_path,
            "locale_path": loc_path,
            "status": result.status,
            "kind": result.kind,
            "detail": result.detail,
            "num_repairs": len(result.repairs),
        }
        if result.status == "ok" and args.apply:
            loc_abs.write_bytes(result.new_text.encode("utf-8"))
            applied += 1
            entry["applied"] = True
        results.append(entry)

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "apply" if args.apply else "dry-run",
        "pair_count": len(pairs),
        "status_counts": dict(status_counts),
        "applied_count": applied,
        "results": results,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"mode={report['mode']} pairs={report['pair_count']} status_counts={dict(status_counts)} applied={applied}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
