# Adapted from aspose.org scripts/pipeline/lib/ for standalone use
"""content_discovery.py — Content file discovery helpers.

Extracted from knowledge_core.py (R-1a). Provides constants and functions for
discovering content files and products in the repository.

Public API:
    KNOWLEDGE_ROOT  — Path to knowledge/ directory
    PLATFORM_MAP    — {} (empty; paths now use the same names)
    PLATFORM_RMAP   — {} (reverse; empty)
    SITE_PATHS      — list of (site, path_pattern) tuples
    LOCALE_RE       — regex to detect translation file suffixes
    discover_content(family, platform) -> list[Path]
    discover_products() -> list[(family, platform)]
    infer_product(filepath) -> (family, platform) | (None, None)

Note: knowledge_core.py imports and re-exports all of the above for backward
compatibility with existing consumers (Sprint R-1a). Constants are defined
here (zero stdlib deps) to avoid a circular import.
"""
from __future__ import annotations
import os

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants (zero deps — only stdlib re + pathlib)
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = Path(os.environ.get(
    "CONTENT_REPO_PATH",
    str(_SCRIPT_DIR.parent.parent.parent),  # scripts/pipeline/lib/ -> pipeline/ -> scripts/ -> repo root
))
_REPO_ROOT = _DEFAULT_REPO_ROOT

KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"


def configure(*, repo_root: "Path | str | None" = None, knowledge_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, KNOWLEDGE_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _REPO_ROOT / "knowledge"

# Platform path mapping: content paths and knowledge directories now use the
# same name. These dicts remain for API compatibility but are intentionally empty.
PLATFORM_MAP: dict[str, str] = {}
PLATFORM_RMAP: dict[str, str] = {}

# Site content paths — absolute, CWD-independent
SITE_PATHS = [
    ("products.aspose.org", str(_REPO_ROOT / "content/products.aspose.org/en/{family}/{platform}")),
    ("reference.aspose.org", str(_REPO_ROOT / "content/reference.aspose.org/en/{family}/{platform}")),
    ("docs.aspose.org", str(_REPO_ROOT / "content/docs.aspose.org/en/{family}/{platform}")),
    ("blog.aspose.org", str(_REPO_ROOT / "content/blog.aspose.org/{family}/{platform}")),
    ("kb.aspose.org", str(_REPO_ROOT / "content/kb.aspose.org/en/{family}/{platform}")),
]

# Locale codes to skip (translation files)
LOCALE_RE = re.compile(r"\.(?:ar|bg|ca|cs|da|de|el|es|et|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sl|sr|sv|th|tr|uk|vi|zh)\.md$")


def _infer_subdomain(filepath: Path) -> str | None:
    """Return the canonical subdomain name for a content file path.

    Uses the site names from SITE_PATHS as the authority. Returns None when
    the path is not under any known content site.

    Examples:
        content/reference.aspose.org/... → "reference.aspose.org"
        content/blog.aspose.org/...      → "blog.aspose.org"
        /tmp/other/file.md               → None
    """
    parts = filepath.parts
    for site_name, _ in SITE_PATHS:
        if site_name in parts:
            return site_name
    return None


def discover_content(family: str, platform: str, *, skip_drafts: bool = False) -> list[Path]:
    """Find all English content .md files for a family/platform.

    Args:
        skip_drafts: When True, skip files whose frontmatter contains ``draft: true``.
            Requires reading each file's frontmatter; adds I/O overhead proportional
            to the number of files.  Defaults to False for backward compatibility.
    """
    content_platform = PLATFORM_RMAP.get(platform, platform)
    files = []
    for site_name, pattern in SITE_PATHS:
        # Try mapped platform name first, fall back to original
        path = Path(pattern.format(family=family, platform=content_platform))
        if not path.exists() and content_platform != platform:
            path = Path(pattern.format(family=family, platform=platform))
        if path.exists():
            for f in sorted(path.rglob("*.md")):
                # Skip translation files
                if LOCALE_RE.search(f.name):
                    continue
                if skip_drafts and _is_draft(f):
                    continue
                files.append(f)
    return files


def _is_draft(filepath: Path) -> bool:
    """Return True if the file's frontmatter has ``draft: true``."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
        # Fast path: avoid YAML parse if "draft:" not in file at all
        if "draft:" not in text:
            return False
        if not text.startswith("---"):
            return False
        end = text.find("\n---", 3)
        if end == -1:
            return False
        fm_text = text[3:end]
        # Match "draft: true" as a YAML scalar (not "draft: false" or similar)
        import re as _re
        return bool(_re.search(r"^\s*draft\s*:\s*true\b", fm_text, _re.MULTILINE))
    except OSError:
        return False


def infer_product(filepath: Path) -> tuple[str, str] | tuple[None, None]:
    """Infer (family, platform) from a content file path."""
    parts = filepath.parts
    for i, p in enumerate(parts):
        if p in ("products.aspose.org", "reference.aspose.org",
                  "docs.aspose.org", "blog.aspose.org", "kb.aspose.org"):
            # Path structure: .../site/[en/]{family}/{platform}/...
            remaining = parts[i + 1:]
            if remaining and remaining[0] == "en":
                remaining = remaining[1:]
            if len(remaining) >= 2:
                family = remaining[0]
                platform = remaining[1]
                knowledge_platform = PLATFORM_MAP.get(platform, platform)
                return family, knowledge_platform
    return None, None


def discover_products() -> list[tuple[str, str]]:
    """Find all products with knowledge models (have api_surface.json)."""
    products = []
    for family_dir in sorted(KNOWLEDGE_ROOT.iterdir()):
        if not family_dir.is_dir() or family_dir.name.startswith("_"):
            continue
        for plat_dir in sorted(family_dir.iterdir()):
            if not plat_dir.is_dir():
                continue
            if (plat_dir / "merged" / "api_surface.json").exists():
                products.append((family_dir.name, plat_dir.name))
    return products
