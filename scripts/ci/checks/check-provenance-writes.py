#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check-provenance-writes.py — Lint: detect scripts that write provenance fields
without using the official provenance module API.

Violation = Python file in scripts/ that:
  - Uses re.sub / str.replace on 'last_mechanism' pattern (raw regex manipulation)
  - Writes 'last_mechanism:' to file content without importing provenance module

What is NOT a violation:
  - Files that import ``from provenance import`` or ``import provenance``
  - ``scripts/pipeline/lib/provenance.py`` itself
  - Test files (under ``*/tests/*``, named ``test_*.py``, or ``*_test.py``)
  - Files that reference ``last_mechanism`` in string literals for
    documentation/logging only — no re.sub/str.replace/file-write context

Exit 0 = clean; Exit 1 = violations found.

Usage:
    python scripts/ci/checks/check-provenance-writes.py [scripts_root]

The optional argument overrides the default scripts/ directory (useful for tests).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Matches: re.sub(r'last_mechanism', ...) or re.sub("last_mechanism", ...)
# Uses non-greedy .*? so the open-paren anchor doesn't consume the string literal.
# DOTALL is not needed because these calls are typically single-line, but we use
# it anyway to handle multi-line re.sub calls.
_RE_SUB_LAST_MECH = re.compile(
    r"re\.sub\s*\(.*?['\"]last_mechanism",
    re.DOTALL,
)

# Matches str.replace("last_mechanism", ...) or str.replace('last_mechanism', ...)
# The first argument to .replace must literally start with last_mechanism.
_STR_REPLACE_LAST_MECH = re.compile(
    r"\.replace\s*\(\s*['\"]last_mechanism",
)

# Detects 'last_mechanism:' as a YAML key inside a string literal.
# Matches: 'last_mechanism:', "last_mechanism:", or embedded after \\n / other
# escape sequences in the string body (e.g. '  last_mechanism: fixer\n').
_LITERAL_LAST_MECH_YAML = re.compile(
    r"""['"][^'"]*last_mechanism:""",
    re.DOTALL,
)

# Detects file-write calls: .write_text( / atomic_write( / .write( with content
_WRITE_CALL = re.compile(
    r"\.(write_text|write)\s*\(|atomic_write\s*\(",
)

# Detects a provenance import in the file
_PROVENANCE_IMPORT = re.compile(
    r"(?:from\s+provenance\s+import|import\s+provenance)",
)


# ---------------------------------------------------------------------------
# Exclusion helpers
# ---------------------------------------------------------------------------

def _is_excluded(path: Path, scripts_root: Path) -> bool:
    """Return True if *path* should be skipped by the linter."""
    name = path.name

    # Exclude provenance.py itself
    if name == "provenance.py":
        return True

    # Exclude this script itself (its own regex definitions would self-trigger)
    if name == "check-provenance-writes.py":
        return True

    # Exclude test files by name pattern
    if name.startswith("test_") or name.endswith("_test.py"):
        return True

    # Exclude files under any 'tests' directory
    try:
        rel = path.relative_to(scripts_root)
    except ValueError:
        rel = path
    if "tests" in rel.parts:
        return True

    return False


# ---------------------------------------------------------------------------
# Per-file checks
# ---------------------------------------------------------------------------

def check_file(path: Path) -> list[str]:
    """Return a list of violation messages for *path* (empty = clean)."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"  Cannot read file: {exc}"]

    violations: list[str] = []

    # Check 1: raw re.sub on 'last_mechanism' string pattern
    for m in _RE_SUB_LAST_MECH.finditer(source):
        line_no = source[: m.start()].count("\n") + 1
        violations.append(
            f"  line {line_no}: re.sub on 'last_mechanism' — "
            "use provenance.update_mechanism() instead"
        )

    # Check 2: str.replace on 'last_mechanism' string pattern
    for m in _STR_REPLACE_LAST_MECH.finditer(source):
        line_no = source[: m.start()].count("\n") + 1
        violations.append(
            f"  line {line_no}: str.replace on 'last_mechanism' — "
            "use provenance.update_mechanism() instead"
        )

    # Check 3: writes 'last_mechanism:' as a YAML literal to a file,
    # without having imported the provenance module.
    has_provenance_import = bool(_PROVENANCE_IMPORT.search(source))
    has_write_call = bool(_WRITE_CALL.search(source))
    has_literal_yaml_key = bool(_LITERAL_LAST_MECH_YAML.search(source))

    if has_literal_yaml_key and has_write_call and not has_provenance_import:
        # Find first occurrence for the line number
        m = _LITERAL_LAST_MECH_YAML.search(source)
        line_no = source[: m.start()].count("\n") + 1 if m else "?"
        violations.append(
            f"  line {line_no}: literal 'last_mechanism:' in file-write context "
            "without importing provenance module — "
            "use provenance.write_provenance() or provenance.update_mechanism() instead"
        )

    return violations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(scripts_root: Path) -> int:
    """Walk *scripts_root* and report violations.  Returns exit code."""
    if not scripts_root.is_dir():
        print(f"ERROR: scripts root not found: {scripts_root}", file=sys.stderr)
        return 2

    py_files = sorted(scripts_root.rglob("*.py"))
    violations_found = 0

    for path in py_files:
        if _is_excluded(path, scripts_root):
            continue

        messages = check_file(path)
        if messages:
            violations_found += 1
            print(f"VIOLATION  {path}")
            for msg in messages:
                print(msg)

    if violations_found:
        print(
            f"\n{violations_found} file(s) with rogue provenance writes — "
            "provenance-writes check FAILED."
        )
        return 1

    print("Provenance-writes check PASSED — 0 violations.")
    return 0


def main() -> int:
    if len(sys.argv) > 1:
        scripts_root = Path(sys.argv[1]).resolve()
    else:
        # Default: scripts/ sibling of this file's ci/ directory
        scripts_root = Path(__file__).resolve().parents[2]

    return run(scripts_root)


if __name__ == "__main__":
    sys.exit(main())
