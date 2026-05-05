"""Evidence completeness evaluator — detects structurally empty evidence blocks.

H-18: Reference pages with known API members must not have empty evidence arrays.

Checks:
  - Reference page has apis: [] but class has known API members → WARN/FAIL
  - Reference page has claims: [] → WARN

Severity rules:
  - apis: [] AND class has >5 known members  → FAIL (category EC)
  - apis: [] AND class has 1–5 known members → WARN (category EC)
  - claims: [] on reference page             → WARN (category EC)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

try:
    import sys as _sys
    from pathlib import Path as _Path
    _scripts = _Path(__file__).resolve().parent.parent.parent.parent
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from config_loader import resolve_knowledge_root as _rkr
    KNOWLEDGE_ROOT = _rkr()
except Exception:
    KNOWLEDGE_ROOT = Path("knowledge")


class EvidenceCompletenessEvaluator(BaseEvaluator):
    """Detect reference pages where evidence arrays are empty despite known API members."""

    name = "evidence_completeness"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Only applies to reference pages
        if page.subdomain != "reference":
            return []
        if not page.family or not page.platform:
            return []

        # Skip structural pages (index, home)
        layout = page.frontmatter.get("layout", "")
        if layout not in ("reference-single",):
            return []

        evidence = page.frontmatter.get("evidence", {})
        if not evidence:
            # No evidence block at all — evidence_depth handles this
            return []

        findings: list[Finding] = []
        apis = evidence.get("apis") or []
        claims = evidence.get("claims") or []

        # --- claims: [] check ---
        if not claims:
            findings.append(Finding(
                level="WARN",
                category="EC",
                filepath=str(page.filepath),
                line_no=1,
                message="Reference page has empty claims: [] in evidence block",
                suggestion="Run attach_evidence.py or batch_reference.py to populate evidence claims",
                evaluator=self.name,
            ))

        # --- apis: [] check against known API surface ---
        if not apis:
            member_count = self._count_known_members(page)
            if member_count > 5:
                findings.append(Finding(
                    level="FAIL",
                    category="EC",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=(
                        f"Reference page has apis: [] but class has {member_count} known API members "
                        "in api_surface.json — evidence is structurally incomplete"
                    ),
                    suggestion=(
                        "Regenerate page with healed batch_reference.py (WP-3) to populate apis: "
                        "from api_surface.json metadata"
                    ),
                    evaluator=self.name,
                ))
            elif member_count > 0:
                findings.append(Finding(
                    level="WARN",
                    category="EC",
                    filepath=str(page.filepath),
                    line_no=1,
                    message=(
                        f"Reference page has apis: [] but class has {member_count} known API members "
                        "in api_surface.json"
                    ),
                    suggestion=(
                        "Regenerate page with healed batch_reference.py to populate apis: "
                        "from api_surface.json metadata"
                    ),
                    evaluator=self.name,
                ))
            # member_count == 0 means no known members → empty apis is acceptable

        return findings

    def _count_known_members(self, page: Page) -> int:
        """Return count of public API members known for this page's class."""
        api_surface = self._load_api_surface(page)
        if not api_surface:
            return 0

        class_name = page.frontmatter.get("linkTitle", "") or page.filepath.stem
        if not class_name:
            return 0

        cls_entry = next(
            (c for c in api_surface if c.get("name") == class_name), None
        )
        if not cls_entry:
            return 0

        count = 0
        for method in cls_entry.get("methods", []):
            name = method.get("name", "")
            if name and not name.startswith("_"):
                count += 1
        for prop in cls_entry.get("properties", []):
            name = prop.get("name", "")
            if name and not name.startswith("_"):
                count += 1
        return count

    def _load_api_surface(self, page: Page) -> list[dict]:
        if not page.family or not page.platform:
            return []
        api_path = (
            KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "api_surface.json"
        )
        if not api_path.exists():
            return []
        try:
            return json.loads(api_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
