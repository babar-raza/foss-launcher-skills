"""Page loader — discovers and loads content pages into Page models."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .models import Page

# Reuse audit.py discovery machinery
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from audit import (  # noqa: E402
    LOCALE_RE,
    PLATFORM_MAP,
    PLATFORM_RMAP,
    SITE_PATHS,
    discover_content,
    discover_products,
    infer_product,
)


def load_pages(family: str, platform: str) -> list[Page]:
    """Discover and load all content pages for a product."""
    files = discover_content(family, platform)
    return [Page.load(f) for f in files]


def load_files(file_paths: list[str | Path]) -> list[Page]:
    """Load specific files as Pages."""
    pages = []
    for fp in file_paths:
        p = Path(fp)
        if p.exists() and p.suffix == ".md":
            if LOCALE_RE.search(p.name):
                continue
            pages.append(Page.load(p))
    return pages


def load_all_products() -> dict[tuple[str, str], list[Page]]:
    """Discover all products and load their pages."""
    products = discover_products()
    result = {}
    for family, platform in products:
        pages = load_pages(family, platform)
        if pages:
            result[(family, platform)] = pages
    return result
