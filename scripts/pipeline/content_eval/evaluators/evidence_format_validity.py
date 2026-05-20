# Adapted from aspose.org
"""Evidence format validity evaluator — detects false-positive format extensions in evidence blocks.

CV2-003 guard: When formats.json is cleaned of false positives (CV2-001), existing content
pages may still carry stale evidence.formats entries with invalid extensions (e.g. "font",
"binary", "bit", "argb"). This evaluator catches those.

Checks:
  - Each ext in evidence.formats exists in the product's merged/formats.json
  - Each ext in section-level formats also exists in formats.json
  - Known false-positive extensions are flagged even if they appear in formats.json

Severity:
  - Invalid top-level evidence.formats ext → WARN (category EFV)
  - Invalid section-level formats ext → INFO (category EFV)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")

# Maximum plausible file extension length
_MAX_EXT_LEN = 8

# Known false-positive extensions that appear in formats.json but aren't real file formats.
# Mirrors _FALSE_POSITIVE_EXTS in evidence/mapper.py.
_FALSE_POSITIVE_EXTS = frozenset({
    "col", "row", "main", "elem", "package", "storage", "value", "address",
    "flags", "reserved", "clsid", "difat", "double", "black", "el",
    "font", "binary", "bit", "slice", "pos", "format",
    "geometry", "mesh", "material", "rotation", "matrix",
    "argb", "remove", "parts", "i",
})


def _load_valid_exts(family: str, platform: str) -> set[str]:
    """Load valid format extensions from merged/formats.json."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError):
        return set()
    if not isinstance(data, list):
        return set()
    exts = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        ext = (
            entry.get("extension", entry.get("ext", entry.get("format", "")))
            .lower()
            .lstrip(".")
        )
        if ext and len(ext) <= _MAX_EXT_LEN:
            exts.add(ext)
    return exts


class EvidenceFormatValidityEvaluator(BaseEvaluator):
    """Detect evidence.formats entries whose ext is not in formats.json."""

    name = "evidence_format_validity"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not page.family or not page.platform:
            return []

        evidence = page.frontmatter.get("evidence", {})
        if not evidence:
            return []

        valid_exts = _load_valid_exts(page.family, page.platform)
        if not valid_exts:
            return []  # No formats.json — can't validate

        findings: list[Finding] = []

        # Check top-level evidence.formats
        formats = evidence.get("formats") or []
        for fmt in formats:
            if isinstance(fmt, dict) and "ext" in fmt:
                ext = fmt["ext"]
                if ext not in valid_exts or ext in _FALSE_POSITIVE_EXTS:
                    reason = ("known false positive" if ext in _FALSE_POSITIVE_EXTS
                              else "not found in formats.json")
                    findings.append(Finding(
                        level="WARN",
                        category="EFV",
                        filepath=str(page.filepath),
                        line_no=1,
                        message=(
                            f"evidence.formats contains invalid extension '{ext}' "
                            f"({reason})"
                        ),
                        suggestion=(
                            f"Remove '{ext}' from evidence.formats — it is a "
                            f"false positive from stale format extraction"
                        ),
                        evaluator=self.name,
                    ))

        # Check section-level formats
        sections = evidence.get("sections") or []
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            sec_formats = sec.get("formats") or []
            heading = sec.get("heading", "unknown")
            for fmt in sec_formats:
                if isinstance(fmt, dict) and "ext" in fmt:
                    ext = fmt["ext"]
                    if ext not in valid_exts or ext in _FALSE_POSITIVE_EXTS:
                        findings.append(Finding(
                            level="INFO",
                            category="EFV",
                            filepath=str(page.filepath),
                            line_no=sec.get("line", 1),
                            message=(
                                f"Section '{heading}' evidence.formats contains "
                                f"invalid extension '{ext}'"
                            ),
                            suggestion=(
                                f"Remove '{ext}' from section formats — "
                                f"not in formats.json"
                            ),
                            evaluator=self.name,
                        ))

        return findings
