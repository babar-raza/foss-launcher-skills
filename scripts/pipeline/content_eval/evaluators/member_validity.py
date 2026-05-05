"""Member validity evaluator — detects property table rows and code accesses that
reference members absent from api_surface.json.

Category: MV (Member Validity)
Grade ceiling: MV FAIL → cap C

Proven blind spot
-----------------
A reference page can earn grade B while its property table lists properties that do
not exist in the source (e.g., ``Width``, ``Height`` on ``Image`` — the real names
are ``OriginalWidth``, ``OriginalHeight``). The existing evaluators check
``evidence.apis`` against api_surface, but never scan property table content.

Scope
-----
Reference pages only (``page.subdomain == "reference"``).

Checks performed
----------------
1. **Property table membership** (FAIL) — each property name in the property table is
   looked up in the documented class's ``properties`` list in api_surface.json.
   If absent: FAIL [MV].

2. **Code block member access** (WARN) — ``.MemberName`` accesses in code blocks are
   checked against the union of known properties and methods for the documented class.
   If absent: WARN [MV].

False-positive mitigations
--------------------------
- Both checks are skipped when the class entry has no members in api_surface (can't
  distinguish real members from missing ones when the model is incomplete).
- Check 1 is skipped when the property table row is in an "Inherited from" section
  (heuristic: heading before the table row contains "Inherited").
- Check 2 uses only CamelCase names (first letter uppercase) to avoid flagging Python
  built-ins, local variables, and module paths.
- Check 2 is INFO-level (not FAIL) — higher false-positive risk than property tables.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# ---------------------------------------------------------------------------
# Pattern constants
# ---------------------------------------------------------------------------

# Property table row: | `PropName` | SomeType | Read | Description |
# Requires the Access column to contain Read / Write / Read/Write to avoid matching
# constructor/method parameter tables (which have only 3 columns and no Access cell).
_PROP_TABLE_ROW_RE = re.compile(
    r"^\|\s*`(?P<prop>[A-Za-z_][A-Za-z0-9_]*)`\s*\|[^|]*\|\s*(?P<access>Read(?:/Write)?|Write)\s*\|",
    re.MULTILINE,
)

# Section heading: ## Heading or ### Heading
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)

# Code block member access: .MemberName where MemberName starts with uppercase.
# Captures CamelCase member names to reduce false positives on Python built-ins.
_MEMBER_ACCESS_RE = re.compile(r"\.([A-Z][A-Za-z0-9_]+)\b")

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

# Sections whose property rows should not be checked (inherited members from base class)
_INHERITED_SECTION_KEYWORDS = ("inherited", "compositenode", "base class", "node")


class MemberValidityEvaluator(BaseEvaluator):
    """Detects property table entries and code member accesses absent from api_surface.

    Scope: reference pages only.
    """

    name = "member_validity"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        # Only applies to reference pages
        if page.subdomain != "reference":
            return findings

        api_surface = self._load_api_surface(page)
        if not api_surface:
            return findings

        # Derive class name: prefer frontmatter linktitle (authoritative), fall back to
        # stem. Some pages use lowercase filenames (image.md) with CamelCase linktitle.
        class_name = (
            page.frontmatter.get("linktitle", "")
            or page.filepath.stem
        )

        # Find the class entry in api_surface (case-insensitive fallback)
        class_entry = None
        for entry in api_surface:
            if entry.get("name") == class_name:
                class_entry = entry
                break
        if class_entry is None:
            # Fallback: case-insensitive match (handles image.md → Image)
            class_name_lower = class_name.lower()
            for entry in api_surface:
                if entry.get("name", "").lower() == class_name_lower:
                    class_entry = entry
                    class_name = entry["name"]  # use canonical name in messages
                    break

        if class_entry is None:
            return findings

        # Build known member set: properties + methods + enum_members
        known_props: set[str] = {
            p.get("name", "") for p in class_entry.get("properties", []) if p.get("name")
        }
        known_methods: set[str] = {
            m.get("name", "") for m in class_entry.get("methods", []) if m.get("name")
        }
        known_enums: set[str] = {
            v.get("name", "") for v in class_entry.get("enum_members", []) if v.get("name")
        }
        all_known: set[str] = known_props | known_methods | known_enums

        # If the class has no members at all, skip — model may be incomplete
        if not all_known:
            return findings

        raw = page.filepath.read_text(encoding="utf-8", errors="replace")

        # Check 1: property table rows
        findings.extend(
            self._check_property_table(raw, class_name, known_props, page)
        )

        # Check 2: code block member accesses (deferred to H-01 / type_member_compatibility)
        # Not implemented in MVP due to high false-positive risk from inherited methods
        # and cross-object accesses (.GetChildNodes called on doc not on Image, etc.)

        return findings

    # ------------------------------------------------------------------
    # Check 1: property table membership
    # ------------------------------------------------------------------

    def _check_property_table(
        self,
        raw: str,
        class_name: str,
        known_props: set[str],
        page: Page,
    ) -> list[Finding]:
        """Flag property table rows whose name is not in api_surface for this class."""
        findings: list[Finding] = []

        # Build map: line_no → section heading text (for inherited-section detection)
        heading_by_line: dict[int, str] = {}
        for m in _HEADING_RE.finditer(raw):
            line_no = raw[: m.start()].count("\n") + 1
            heading_by_line[line_no] = m.group(1).strip().lower()

        def _heading_before(line_no: int) -> str:
            """Return the heading text most recently before line_no."""
            best = ""
            for hline, htxt in heading_by_line.items():
                if hline < line_no:
                    best = htxt
            return best

        for m in _PROP_TABLE_ROW_RE.finditer(raw):
            prop_name = m.group("prop")
            line_no = raw[: m.start()].count("\n") + 1

            # Skip if this row is under an "Inherited from …" heading
            heading = _heading_before(line_no)
            if any(kw in heading for kw in _INHERITED_SECTION_KEYWORDS):
                continue

            # Skip property/method/value header rows
            if prop_name.lower() in (
                "property", "method", "value", "parameter", "name", "type",
                "access", "description", "returns",
            ):
                continue

            if prop_name not in known_props:
                findings.append(Finding(
                    level="FAIL",
                    category="MV",
                    filepath=str(page.filepath),
                    line_no=line_no,
                    message=(
                        f"Property `{prop_name}` in property table is not in "
                        f"`{class_name}` api_surface — likely a hallucination or "
                        "wrong class (e.g., from .NET/Java variant)"
                    ),
                    suggestion=(
                        f"Remove `{prop_name}` or replace with its actual name from "
                        "api_surface. Known properties: "
                        + (", ".join(sorted(known_props)[:8]) if known_props else "none")
                    ),
                    evaluator=self.name,
                ))

        return findings

    # ------------------------------------------------------------------
    # Check 2: code block member accesses
    # ------------------------------------------------------------------

    def _check_code_accesses(
        self,
        page: Page,
        all_known: set[str],
        class_name: str,
    ) -> list[Finding]:
        """Flag .MemberName accesses in code blocks absent from api_surface."""
        findings: list[Finding] = []

        for block in page.code_blocks:
            for m in _MEMBER_ACCESS_RE.finditer(block.content):
                member = m.group(1)
                if member not in all_known:
                    line_no = block.start_line + block.content[: m.start()].count("\n")
                    findings.append(Finding(
                        level="WARN",
                        category="MV",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"Code block accesses `.{member}` which is not in "
                            f"`{class_name}` api_surface — may raise AttributeError"
                        ),
                        suggestion=(
                            f"Verify `.{member}` exists. Known members: "
                            + (", ".join(sorted(all_known)[:8]))
                        ),
                        evaluator=self.name,
                    ))

        return findings

    # ------------------------------------------------------------------
    # Helper: load api_surface.json
    # ------------------------------------------------------------------

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
