# Adapted from aspose.org scripts/ci/checks/ for standalone use
#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_protected_overwrites.py — Detect modifications to provenance-protected pages.

Scans staged or PR-changed content files and warns when any file with
``auto_updatable: false`` in its provenance block has been modified.

Usage:
    # Check staged files (pre-commit hook):
    python scripts/ci/checks/check_protected_overwrites.py --check-staged

    # Check files from a PR diff:
    python scripts/ci/checks/check_protected_overwrites.py file1.md file2.md ...
    # Files from: git diff --name-only origin/main...HEAD -- 'content/**/*.md'

Exit codes:
    0  No protected pages were overwritten
    1  Internal error
    2  One or more protected pages were modified (blocks commit/PR)
"""

from __future__ import annotations

import re
import subprocess
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parents[3])))))

# Fast regex for auto_updatable in frontmatter (no yaml dependency)
_AUTO_UPDATABLE_RE = re.compile(
    r"^[ \t]+auto_updatable:\s*(true|false)\s*$", re.MULTILINE
)

# Content directories where provenance protection applies
_CONTENT_PREFIXES = (
    "content/",
)


def _is_content_file(path: str) -> bool:
    """Return True if the path is under a content directory."""
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(p) for p in _CONTENT_PREFIXES)


def _was_protected_before(filepath: str) -> bool:
    """Check if the file had auto_updatable: false BEFORE the current change.

    Uses git show HEAD:<path> to read the committed version. If the file
    is new (not in HEAD), it was not previously protected.
    """
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{filepath}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if result.returncode != 0:
            return False  # File not in HEAD → new file, not protected
        if result.stdout is None:
            return False  # Encoding error reading file -- treat as not protected
        m = _AUTO_UPDATABLE_RE.search(result.stdout)
        if m:
            return m.group(1) == "false"
        return False  # No auto_updatable field → not protected
    except (subprocess.TimeoutExpired, OSError):
        return False


def _get_staged_files() -> list[str]:
    """Get list of staged content .md files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return []
        return [
            f.strip() for f in result.stdout.splitlines()
            if f.strip().endswith(".md") and _is_content_file(f.strip())
        ]
    except (subprocess.TimeoutExpired, OSError):
        return []


def check_files(filepaths: list[str]) -> list[str]:
    """Return list of protected files that were modified."""
    violations = []
    for fp in filepaths:
        if not _is_content_file(fp):
            continue
        if not fp.endswith(".md"):
            continue
        if _was_protected_before(fp):
            violations.append(fp)
    return violations


def main(argv: list[str]) -> int:
    if "--check-staged" in argv:
        files = _get_staged_files()
        mode = "staged"
    else:
        files = [f for f in argv if f.endswith(".md")]
        mode = "PR"

    if not files:
        print(f"No content .md files in {mode} changes — nothing to check.")
        return 0

    content_files = [f for f in files if _is_content_file(f)]
    if not content_files:
        print(f"No content files in {mode} changes — nothing to check.")
        return 0

    violations = check_files(content_files)

    if not violations:
        print(
            f"Provenance protection: OK — {len(content_files)} content file(s) checked, "
            "none were protected."
        )
        return 0

    print(f"PROTECTED PAGE OVERWRITE DETECTED — {len(violations)} file(s):")
    for v in violations:
        print(f"  BLOCKED: {v} (auto_updatable: false in committed version)")
    print(
        "\nThese files have auto_updatable: false in their provenance block, "
        "which means they contain manually curated content that should not be "
        "overwritten by automated processes."
    )
    print(
        "\nTo fix: either revert the change, or explicitly set auto_updatable: true "
        "in the file's provenance block (requires human approval)."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
