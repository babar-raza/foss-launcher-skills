# Adapted from aspose.org
#!/usr/bin/env python3
"""fix_last_mechanism.py — Repair stale last_mechanism values in the corpus.

Scans content files for ``last_mechanism: grade-writer`` (and optionally
``evidence-attach``) and replaces them with the correct current value:
  - ``skill`` if ``content_origin`` is ``skill-generated``
  - ``unknown`` otherwise

Usage:
    python fix_last_mechanism.py                          # dry-run (default)
    python fix_last_mechanism.py --apply                  # write changes
    python fix_last_mechanism.py --path content/blog/
    python fix_last_mechanism.py --values grade-writer evidence-attach
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from lib.provenance import read_provenance, update_mechanism  # noqa: E402

# Stale mechanism values to repair (default)
_DEFAULT_STALE_VALUES = frozenset({"grade-writer"})


def determine_replacement(prov: dict) -> str:
    """Choose the correct replacement mechanism based on content_origin."""
    origin = prov.get("content_origin", "")
    if origin == "skill-generated":
        return "skill"
    return "unknown"


def process_file(
    filepath: Path, stale_values: frozenset[str], apply: bool
) -> str:
    """Check and optionally repair a single file.

    Returns: 'repaired', 'skipped', 'no-provenance', or 'error'.
    """
    prov = read_provenance(filepath)
    if prov is None:
        return "no-provenance"

    mechanism = prov.get("last_mechanism", "")
    if mechanism not in stale_values:
        return "skipped"

    replacement = determine_replacement(prov)

    if apply:
        try:
            ok = update_mechanism(filepath, replacement)
            if not ok:
                print(f"  ERROR writing {filepath}")
                return "error"
            print(f"  REPAIRED  {filepath}  {mechanism} -> {replacement}")
        except Exception as exc:
            print(f"  ERROR {filepath}: {exc}")
            return "error"
    else:
        print(f"  WOULD REPAIR  {filepath}  {mechanism} -> {replacement}")

    return "repaired"


def scan_and_fix(
    root: Path, stale_values: frozenset[str], apply: bool
) -> dict[str, int]:
    """Scan directory and repair stale mechanisms. Returns counters."""
    counters = {"total": 0, "repaired": 0, "skipped": 0, "no_provenance": 0, "errors": 0}
    for md_file in sorted(root.rglob("*.md")):
        counters["total"] += 1
        result = process_file(md_file, stale_values, apply)
        if result == "repaired":
            counters["repaired"] += 1
        elif result == "skipped":
            counters["skipped"] += 1
        elif result == "no-provenance":
            counters["no_provenance"] += 1
        elif result == "error":
            counters["errors"] += 1
    return counters


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Repair stale last_mechanism values (grade-writer, evidence-attach)."
    )
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="Write changes to disk (default: dry-run)",
    )
    parser.add_argument(
        "--path", default=None,
        help="Directory to scan (default: content/)",
    )
    parser.add_argument(
        "--values", nargs="*", default=None,
        help="Stale mechanism values to repair (default: grade-writer)",
    )
    args = parser.parse_args(argv)

    stale_values = frozenset(args.values) if args.values else _DEFAULT_STALE_VALUES

    if args.path:
        scan_root = Path(args.path).resolve()
    else:
        scan_root = (_HERE / ".." / ".." / ".." / ".." / "content").resolve()

    if not scan_root.exists():
        print(f"ERROR: path does not exist: {scan_root}", file=sys.stderr)
        return 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"fix_last_mechanism — mode={mode}  root={scan_root}")
    print(f"  stale values: {', '.join(sorted(stale_values))}")
    print()

    counters = scan_and_fix(scan_root, stale_values, args.apply)

    print()
    print("=" * 60)
    print(f"Files scanned   : {counters['total']}")
    print(f"No provenance   : {counters['no_provenance']}")
    print(f"Skipped (ok)    : {counters['skipped']}")
    label = "Repaired" if args.apply else "Would repair"
    print(f"{label:16s}: {counters['repaired']}")
    print(f"Errors          : {counters['errors']}")
    print("=" * 60)

    return 1 if counters["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())