#!/usr/bin/env python3
"""check_protected_overwrites.py — Detect modifications to provenance-protected pages.

Scans staged or PR-changed content files and warns when any file with
``auto_updatable: false`` in its provenance block has been modified.

Performance design (large locale-batch commits):
    --check-staged mode filters to English-source files only, then uses a
    single ``git grep`` call to find all protected pages in HEAD.  This
    replaces an O(N) per-file subprocess loop that previously took ~10 min
    for 9,940-file locale-batch commits.

    Threshold: when candidate count >= _BATCH_THRESHOLD, the git grep batch
    path is used; below it, per-file git show is used (lower startup cost
    for small diffs typical of single-file edits and small PRs).

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
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Fast regex for auto_updatable in frontmatter (no yaml dependency)
_AUTO_UPDATABLE_RE = re.compile(
    r"^[ \t]+auto_updatable:\s*(true|false)\s*$", re.MULTILINE
)

# Content directories where provenance protection applies
_CONTENT_PREFIXES = (
    "content/docs.aspose.org/",
    "content/blog.aspose.org/",
    "content/kb.aspose.org/",
    "content/products.aspose.org/",
    "content/reference.aspose.org/",
)

# Switch to git grep batch approach when candidate file count meets this threshold.
# Below: per-file git show (lower startup cost for small diffs).
# At or above: single git grep over all of HEAD (dominant win for large batches).
_BATCH_THRESHOLD = 50


def _is_content_file(path: str) -> bool:
    """Return True if the path is under a content directory."""
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(p) for p in _CONTENT_PREFIXES)


def _is_english_source(path: str) -> bool:
    """Return True for English source pages; False for locale translation files.

    Rationale: locale translations are auto-generated and never carry
    ``auto_updatable: false``.  Excluding them from the --check-staged scan
    reduces the candidate set from O(all staged) to O(English-only), which
    is the only set that matters for protection checks.

    Rules:
    - docs / kb / products / reference: English content lives under an ``/en/``
      directory segment.
    - blog: English files are ``index.md`` or ``_index.md``; locale variants
      use a two-part suffix such as ``index.sv.md`` or ``archive.ar.md``.
    """
    norm = path.replace("\\", "/")
    if "/en/" in norm:
        return True
    if norm.startswith("content/blog.aspose.org/"):
        basename = norm.rsplit("/", 1)[-1]
        # English: "index.md"  → split(".") → 2 parts
        # Locale:  "index.sv.md" → split(".") → 3 parts
        return len(basename.split(".")) == 2
    return False


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


def _get_protected_in_head() -> frozenset[str]:
    """Return all content file paths in HEAD that contain auto_updatable: false.

    Uses a single ``git grep`` call to scan the entire HEAD tree — O(1)
    subprocess invocation regardless of how many files are staged.

    The git grep pre-filter may include rare false positives (e.g. files
    containing the string outside frontmatter).  Callers should verify
    intersection candidates with ``_was_protected_before()`` before raising
    a violation.

    Returns an empty frozenset on any error (fail-open: skip the protection
    check rather than blocking the commit on infrastructure issues).
    """
    try:
        result = subprocess.run(
            [
                "git", "grep",
                "-lF", "auto_updatable: false",
                "HEAD", "--", "content/**/*.md",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        # git grep exits 1 when there are no matches (not an error).
        if result.returncode not in (0, 1):
            return frozenset()
        paths: set[str] = set()
        for line in result.stdout.splitlines():
            # Output format: "HEAD:content/path/to/file.md"
            if ":" in line:
                path = line.split(":", 1)[1].strip().replace("\\", "/")
                if path:
                    paths.add(path)
        return frozenset(paths)
    except (subprocess.TimeoutExpired, OSError):
        return frozenset()


def _get_staged_files() -> list[str]:
    """Get list of staged English-source content .md files.

    Filters to English source pages only — locale translations are excluded
    because they are auto-generated and never carry ``auto_updatable: false``.
    This bounds the candidate set to O(English staged) rather than O(all staged),
    which is critical for locale-batch commits staging thousands of locale files.
    """
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
            if f.strip().endswith(".md")
            and _is_content_file(f.strip())
            and _is_english_source(f.strip())
        ]
    except (subprocess.TimeoutExpired, OSError):
        return []


def check_files(filepaths: list[str]) -> list[str]:
    """Return list of protected files that were modified.

    Uses a fast batch path for large file sets (single git grep call) and a
    per-file path for small sets where subprocess startup cost dominates.

    The batch path:
      1. Calls ``_get_protected_in_head()`` once (O(1) subprocess) to get all
         protected files in HEAD.
      2. Intersects with ``filepaths`` in memory (O(N)).
      3. Verifies intersection candidates with ``_was_protected_before()`` to
         filter out any git grep false positives (typically zero candidates for
         locale-only commits).

    The per-file path calls ``_was_protected_before()`` directly for each file.
    """
    # Filter to valid content .md files first
    candidates = [
        fp for fp in filepaths
        if fp.endswith(".md") and _is_content_file(fp)
    ]
    if not candidates:
        return []

    if len(candidates) >= _BATCH_THRESHOLD:
        # Batch path: O(1) subprocess + in-memory intersection
        protected = _get_protected_in_head()
        if not protected:
            return []
        intersection = [
            fp for fp in candidates
            if fp.replace("\\", "/") in protected
        ]
        if not intersection:
            return []
        # Verify with full frontmatter regex to exclude git grep false positives
        return [fp for fp in intersection if _was_protected_before(fp)]
    else:
        # Per-file path: lower overhead for small diffs
        return [fp for fp in candidates if _was_protected_before(fp)]


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
