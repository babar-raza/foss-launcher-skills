# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""CI gate: block PRs where EVALUATOR_LOGIC_VERSION diverges from EVALUATOR_FREEZE_VERSION.

Usage:
    python scripts/ci/checks/check_evaluator_freeze.py

Exit codes:
    0 — freeze not declared (EVALUATOR_FREEZE_VERSION is None) or versions match
    1 — freeze violation: EVALUATOR_LOGIC_VERSION != EVALUATOR_FREEZE_VERSION

When no freeze is active (EVALUATOR_FREEZE_VERSION is None), this check is a
no-op.  Once a freeze is declared, any ELV bump that does not also update the
freeze constant will fail CI.  See GRADE_CONTRACT.md for the post-freeze
change protocol.
"""
import re
import os
import sys
from pathlib import Path

# Repo-root-relative path to content_eval/__init__.py
_INIT_PATH = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent))) / "scripts" / "pipeline" / "content_eval" / "__init__.py"

_RE_LOGIC = re.compile(r'^EVALUATOR_LOGIC_VERSION\s*=\s*"(\d+)"', re.MULTILINE)
_RE_FREEZE = re.compile(r'^EVALUATOR_FREEZE_VERSION\s*(?::\s*str\s*\|\s*None\s*)?=\s*(.+)', re.MULTILINE)


def read_versions(init_text: str) -> tuple[str, str | None]:
    """Parse EVALUATOR_LOGIC_VERSION and EVALUATOR_FREEZE_VERSION from source text.

    Returns (logic_version, freeze_version) where freeze_version is None
    when the constant is set to None.
    """
    m_logic = _RE_LOGIC.search(init_text)
    if not m_logic:
        raise ValueError("Cannot find EVALUATOR_LOGIC_VERSION in __init__.py")

    m_freeze = _RE_FREEZE.search(init_text)
    if not m_freeze:
        raise ValueError("Cannot find EVALUATOR_FREEZE_VERSION in __init__.py")

    logic_version = m_logic.group(1)

    freeze_raw = m_freeze.group(1).strip()
    if freeze_raw == "None":
        freeze_version = None
    else:
        # Strip quotes: "16" -> 16
        freeze_version = freeze_raw.strip('"').strip("'")

    return logic_version, freeze_version


def check(init_text: str) -> int:
    """Run the freeze check on the given source text.

    Returns 0 on success, 1 on freeze violation.
    """
    logic_version, freeze_version = read_versions(init_text)

    if freeze_version is None:
        print("OK: EVALUATOR_FREEZE_VERSION is None — freeze not declared.")
        return 0

    if logic_version == freeze_version:
        print(f"OK: EVALUATOR_LOGIC_VERSION ({logic_version}) == EVALUATOR_FREEZE_VERSION ({freeze_version}).")
        return 0

    print(
        f"Evaluator freeze violation: EVALUATOR_LOGIC_VERSION ({logic_version}) "
        f"!= EVALUATOR_FREEZE_VERSION ({freeze_version}). "
        f"See GRADE_CONTRACT.md for post-freeze change protocol.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    import argparse as _ap
    _parser = _ap.ArgumentParser(description="Check evaluator freeze consistency.")
    _parser.add_argument(
        "--init-path",
        default=os.environ.get("EVALUATOR_INIT_PATH", str(_INIT_PATH)),
        help="Path to content_eval/__init__.py",
    )
    _args = _parser.parse_args()
    init_path = Path(_args.init_path)
    if not init_path.exists():
        print(f"ERROR: file not found: {init_path}", file=sys.stderr)
        return 2

    init_text = init_path.read_text(encoding="utf-8")
    return check(init_text)


if __name__ == "__main__":
    sys.exit(main())
