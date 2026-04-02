"""Shared constants for the pipeline.

All pipeline modules should import shared values from here rather than
defining them independently.  Each constant is marked with the files that
previously defined it (for migration traceability).

NOTE on KNOWLEDGE_ROOT
----------------------
``Path("knowledge")`` is relative to CWD.  The convention is: all pipeline
scripts must be invoked from the repository root (the directory that contains
the ``knowledge/`` directory).  ``refresh_knowledge.py`` legitimately uses an
absolute path (``REPO_ROOT / "knowledge"``) for subprocess calls — that usage
is intentional and should *not* be changed to use this constant.
"""
from __future__ import annotations

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Directory roots
# ---------------------------------------------------------------------------

KNOWLEDGE_ROOT = Path("knowledge")
"""Root of the knowledge model directory (relative to repo root / CWD)."""

CONTENT_ROOT = Path("content")
"""Root of the site content directory (relative to repo root / CWD)."""


# ---------------------------------------------------------------------------
# Report directories
# ---------------------------------------------------------------------------

AUDIT_REPORTS_DIR = Path("reports") / "audit"
CONTENT_EVAL_REPORTS_DIR = Path("reports") / "content_eval"
REMEDIATION_REPORTS_DIR = Path("reports") / "remediation"
SEO_REPORTS_DIR = Path("reports") / "seo"
KILOCODE_REPORTS_DIR = Path("reports") / "kilocode"
PLANS_REPORTS_DIR = Path("reports") / "plans"
PATCHES_DIR = Path("patches")
LLMS_OUTPUT_DIR = Path("llms-output")


# ---------------------------------------------------------------------------
# Platform mappings
# ---------------------------------------------------------------------------

# Content and knowledge directories use the same platform names.
# These dicts remain for API compatibility but are intentionally empty.
PLATFORM_MAP: dict[str, str] = {}
PLATFORM_RMAP: dict[str, str] = {}

# Site content paths relative to repo root
SITE_PATHS = [
    ("products.aspose.org", "content/products.aspose.org/en/{family}/{platform}"),
    ("reference.aspose.org", "content/reference.aspose.org/en/{family}/{platform}"),
    ("docs.aspose.org", "content/docs.aspose.org/en/{family}/{platform}"),
    ("blog.aspose.org", "content/blog.aspose.org/{family}/{platform}"),
    ("kb.aspose.org", "content/kb.aspose.org/en/{family}/{platform}"),
]

# Locale codes: translation files matching this suffix are skipped
# during content discovery.
LOCALE_RE = re.compile(
    r"\.(?:ar|bg|ca|cs|da|de|el|es|et|fi|fr|he|hi|hr|hu|id|it|ja|ko|"
    r"lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sl|sr|sv|th|tr|uk|vi|zh)\.md$"
)


# ---------------------------------------------------------------------------
# Path patterns for filtering (previously duplicated in merge.py + index.py)
# ---------------------------------------------------------------------------

# File paths that indicate test code — skip these when building the public
# API surface.
_TEST_PATH_PATTERNS = ("tests/", "/tests/", "/test_", "test_", "conftest")

# File paths indicating internal/private implementation details.
_INTERNAL_PATH_PATTERNS = ("/_internal/", "/_private/", "/_impl/")


# ---------------------------------------------------------------------------
# Quality trend
# ---------------------------------------------------------------------------

QUALITY_TREND_MAX_ENTRIES = 180
"""Maximum number of entries kept in quality_trend.jsonl before pruning."""


# ---------------------------------------------------------------------------
# Merge algorithm
# ---------------------------------------------------------------------------

DUAL_OVERLAP_THRESHOLD = 0.8
"""Minimum Jaccard token overlap for a scout+FL claim pair to be tagged 'dual'."""


# ---------------------------------------------------------------------------
# Scout limits
# ---------------------------------------------------------------------------

MAX_FILES = 500
"""Maximum number of source files the scout will process per product."""

MAX_SNIPPETS = 200
"""Maximum number of snippets the scout will extract per product."""
