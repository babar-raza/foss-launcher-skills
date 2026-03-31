"""Fixer: add missing ``categories`` to blog post frontmatter.

Derives the category from the product family name.
E.g. family ``3d`` → ``categories: ["Aspose.3D"]``.
"""

from __future__ import annotations

import re
from typing import Any

from ...models import Finding
from . import BaseFixer

_FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)

# Family → display category
_FAMILY_TO_CATEGORY: dict[str, str] = {
    "3d": "Aspose.3D",
    "cells": "Aspose.Cells",
    "slides": "Aspose.Slides",
    "email": "Aspose.Email",
    "note": "Aspose.Note",
    "pdf": "Aspose.PDF",
    "words": "Aspose.Words",
    "barcode": "Aspose.BarCode",
    "imaging": "Aspose.Imaging",
    "html": "Aspose.HTML",
    "zip": "Aspose.ZIP",
    "svg": "Aspose.SVG",
    "tex": "Aspose.TeX",
    "font": "Aspose.Font",
    "cad": "Aspose.CAD",
    "ocr": "Aspose.OCR",
    "psd": "Aspose.PSD",
    "tasks": "Aspose.Tasks",
    "diagram": "Aspose.Diagram",
    "gis": "Aspose.GIS",
    "drawing": "Aspose.Drawing",
    "page": "Aspose.Page",
    "pub": "Aspose.PUB",
}


class FrontmatterCategoriesFixer(BaseFixer):
    name = "frontmatter_categories"
    categories = {"RV"}

    def can_fix(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> bool:
        if "categories" not in finding.message.lower():
            return False
        if meta.get("subdomain") != "blog":
            return False
        family = meta.get("family", "")
        if family not in _FAMILY_TO_CATEGORY:
            return False
        m = _FM_RE.match(page_text)
        if not m:
            return False
        fm_body = m.group(2)
        if re.search(r"^categories\s*:", fm_body, re.MULTILINE):
            return False  # already has categories
        return True

    def apply(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> str:
        family = meta.get("family", "")
        category = _FAMILY_TO_CATEGORY.get(family)
        if not category:
            return page_text

        m = _FM_RE.match(page_text)
        if not m:
            return page_text

        fm_body = m.group(2)

        # Idempotency
        if re.search(r"^categories\s*:", fm_body, re.MULTILINE):
            return page_text

        # Insert after title: line
        title_match = re.search(r"^(title\s*:.*)", fm_body, re.MULTILINE)
        if title_match:
            insert_pos = title_match.end()
            new_fm = (
                fm_body[:insert_pos]
                + f"\ncategories:\n- {category}"
                + fm_body[insert_pos:]
            )
        else:
            new_fm = fm_body + f"\ncategories:\n- {category}"

        return m.group(1) + new_fm + m.group(3) + page_text[m.end():]
