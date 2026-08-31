"""API completeness evaluator — verifies reference pages document all public members.

H-12: For reference pages, checks that all public methods and properties from
api_surface.json for the documented class are present on the page (in prose
backtick mentions, code blocks, or markdown tables).

Severity:
    >30% missing public members → FAIL
    10-30% missing → WARN
    <10% missing → no finding
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")

# Patterns to extract member names mentioned on the page
# Matches `name` and `name()` and `name(args)` inside backticks
#
# HARDEN-cpp-destructor (2026-07-28, MT012): C++ destructor method names are
# literally "~ClassName" in api_surface.json (e.g. Device's destructor is
# named '~Device') -- the leading "~" is not a \w character, so the original
# `(\w+)` group never matched a documented `~Device()` table row at all,
# making every C++ class with a destructor permanently "undocumented" for
# that one member regardless of real page content. `~?` makes the tilde
# optional without affecting any other language's member names.
_BACKTICK_MEMBER_RE = re.compile(r"`(~?\w+)(?:\([^`]*\))?`")
_TABLE_MEMBER_RE = re.compile(
    r"^\|\s*`(~?\w+)(?:\([^)]*\))?`",
    re.MULTILINE,
)
# Section headers of the form "### MethodName()" or "## MethodName" or "### MethodName() → RetType"
_SECTION_HEADER_RE = re.compile(
    r"^#{1,4}\s+(~?\w+)\s*(?:\([^)]*\))?",
    re.MULTILINE,
)

# Language-level members that are universally present in a platform's object model
# and do not need explicit documentation in reference pages.
_UNIVERSAL_SKIP: frozenset[str] = frozenset({
    "constructor",   # TypeScript / JavaScript class constructor keyword
    "toString",      # Object.toString() — inherited by all JS/TS objects
    "hashCode",      # Java Object.hashCode()
    "equals",        # Java Object.equals()
    "finalize",      # Java Object.finalize()
    "getClass",      # Java Object.getClass()
    "notify",        # Java Object.notify()
    "notifyAll",     # Java Object.notifyAll()
    "wait",          # Java Object.wait() overloads
    "__init__",      # Python constructor (already filtered by leading-_ rule)
    "__str__",       # Python str() — already filtered by leading-_ rule
    "__repr__",      # Python repr() — already filtered by leading-_ rule
})


class ApiCompletenessEvaluator(BaseEvaluator):
    """Verify reference pages document all public members from api_surface.json."""

    name = "api_completeness"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Only applies to reference pages
        if page.subdomain != "reference":
            return []
        if not page.family or not page.platform:
            return []

        api_surface = self._load_api_surface(page)
        if not api_surface:
            return []

        # Derive class name from page
        class_name = page.frontmatter.get("linkTitle", "") or page.filepath.stem
        if not class_name:
            return []

        # Find matching class entry/entries
        candidates = [c for c in api_surface if c.get("name") == class_name]
        if not candidates:
            return []
        cls_entry = candidates[0]
        if len(candidates) > 1:
            # HARDEN-cpp-namespace-collision (2026-07-28, MT012): when two
            # unrelated classes share a short name across namespaces (e.g.
            # C++'s Aspose::Pdf::Rectangle vs Aspose::Pdf::Drawing::Rectangle),
            # batch_reference.py disambiguates the FILENAME as
            # "{ClassName}-{namespace_with_underscores}.md" but this evaluator
            # was matching by bare class_name only -- picking whichever
            # candidate happened to be first in api_surface.json regardless of
            # which one the page actually documents, and reporting the OTHER
            # class's members as "missing" from a page that never claimed to
            # cover them. Resolve using the page's own filename suffix, which
            # encodes the real namespace.
            stem = page.filepath.stem
            suffix = stem[len(class_name) + 1:] if stem.startswith(class_name + "-") else ""
            if suffix:
                matched = None
                for c in candidates:
                    ns_slug = re.sub(r"[^A-Za-z0-9]+", "_", c.get("canonical_namespace", "")).strip("_")
                    if ns_slug == suffix:
                        matched = c
                        break
                if matched is None:
                    # ST-121: the namespace-collision disambiguation above only
                    # matches C++'s multi-segment canonical_namespace shape
                    # (e.g. "Aspose::Pdf::Drawing::Rectangle" -> exact slug
                    # match). batch_reference.py's OTHER collision-suffix
                    # convention -- flat TypeScript packages disambiguating by
                    # SOURCE FILE STEM (e.g. Style-types.md / Style-style.md
                    # for a same-named interface in types.ts vs a class in
                    # style.ts) -- names the suffix after just the last
                    # dot-segment of canonical_namespace (or equivalently the
                    # source file's own stem), which never equals the FULL
                    # normalized namespace. Confirmed live 2026-08-30
                    # (MT040 Phase I, cells/typescript refresh): this silently
                    # fell through to candidates[0], reporting the class
                    # Style's 36 methods as "missing" from the interface
                    # Style's page (which only ever had 6 real properties).
                    for c in candidates:
                        ns = c.get("canonical_namespace", "")
                        last_segment = re.sub(r"[^A-Za-z0-9]+", "_", ns.rsplit(".", 1)[-1]) if ns else ""
                        file_stem = Path(c.get("file", "")).stem if c.get("file") else ""
                        if suffix in (last_segment, file_stem):
                            matched = c
                            break
                if matched is not None:
                    cls_entry = matched

        # Collect all public members expected
        expected_members: set[str] = set()
        for method in cls_entry.get("methods", []):
            name = method.get("name", "")
            # Skip private/internal members and universal language-level members
            if name and not name.startswith("_") and name not in _UNIVERSAL_SKIP:
                expected_members.add(name)
        for prop in cls_entry.get("properties", []):
            name = prop.get("name", "")
            if name and not name.startswith("_") and name not in _UNIVERSAL_SKIP:
                expected_members.add(name)

        if not expected_members:
            return []

        # Collect members documented on the page
        documented: set[str] = set()
        raw = page.filepath.read_text(encoding="utf-8", errors="replace")

        # From markdown tables
        for m in _TABLE_MEMBER_RE.finditer(raw):
            documented.add(m.group(1))

        # From section headers (### MethodName() or ## PropertyName)
        for m in _SECTION_HEADER_RE.finditer(raw):
            documented.add(m.group(1))

        # From backtick references in prose
        for _, line in page.prose_lines:
            for m in _BACKTICK_MEMBER_RE.finditer(line):
                documented.add(m.group(1))

        # From code blocks
        for block in page.code_blocks:
            for word in re.findall(r"\b(\w+)\b", block.content):
                if word in expected_members:
                    documented.add(word)

        missing = expected_members - documented
        if not missing:
            return []

        # ST-149: a subclass's own api_surface.json entry can list a member
        # it inherited from a base class (the TS scout duplicates inherited-
        # and-redeclared names onto every subclass entry rather than only the
        # base). When that base class also has its own reference page and
        # genuinely documents the member there, the documentation is
        # complete -- just correctly split across base/subclass pages
        # instead of repeated on every subclass page. Confirmed live
        # 2026-08-31 (MT040 Phase I): 12 subclass pages
        # ({Collada,Fbx,Gltf,Obj,Stl,ThreeMf}{Load,Save}Options.md) were
        # false-capped A->C this way. Suppress only members actually found
        # documented on an ancestor's own page -- a genuinely undocumented
        # member is still flagged even if it happens to share a name with
        # something on a base class.
        missing -= self._documented_on_a_base_page(missing, cls_entry, api_surface, page)
        if not missing:
            return []

        missing_pct = len(missing) / len(expected_members) * 100

        if missing_pct > 30:
            level = "FAIL"
        elif missing_pct > 10:
            level = "WARN"
        else:
            return []  # Less than 10% missing — acceptable

        top_missing = sorted(missing)[:8]
        names_str = ", ".join(f"`{n}`" for n in top_missing)
        suffix = f" (and {len(missing) - 8} more)" if len(missing) > 8 else ""

        return [Finding(
            level=level,
            category="AC",
            filepath=str(page.filepath),
            line_no=1,
            message=(
                f"{len(missing)}/{len(expected_members)} public members "
                f"({missing_pct:.0f}%) not documented: {names_str}{suffix}"
            ),
            suggestion="Add documentation for missing methods/properties",
            evaluator=self.name,
        )]

    def _documented_on_a_base_page(
        self, missing: set[str], cls_entry: dict, api_surface: list[dict], page: Page,
    ) -> set[str]:
        """Return the subset of `missing` that is genuinely documented on
        some ancestor class's own reference page (walking `bases`, cycle-
        safe). Best-effort file lookup: tries the plain `{BaseName}.md`
        sibling first, then a `{BaseName}-*.md` glob for the
        namespace/collision-suffixed naming convention batch_reference.py
        also uses -- a base class involved in its own collision is not
        resolved further here (moderate-scope fix; the exact suffix is a
        second cross-page lookup this evaluator has no need for otherwise)."""
        satisfied: set[str] = set()
        still_missing = set(missing)
        seen_bases: set[str] = set()
        queue = list(cls_entry.get("bases") or [])
        while queue and still_missing:
            base_name = queue.pop(0)
            if not base_name or base_name in seen_bases:
                continue
            seen_bases.add(base_name)
            base_entries = [c for c in api_surface if c.get("name") == base_name]
            for base_entry in base_entries:
                queue.extend(base_entry.get("bases") or [])
                base_own_members = self._own_public_members(base_entry)
                candidates = still_missing & base_own_members
                if not candidates:
                    continue
                base_page = self._find_class_page(page.filepath, base_name)
                if base_page is None:
                    continue
                documented_on_base = self._extract_documented_members(base_page, candidates)
                satisfied |= documented_on_base
                still_missing -= documented_on_base
        return satisfied

    @staticmethod
    def _own_public_members(cls_entry: dict) -> set[str]:
        names: set[str] = set()
        for method in cls_entry.get("methods", []):
            name = method.get("name", "")
            if name and not name.startswith("_") and name not in _UNIVERSAL_SKIP:
                names.add(name)
        for prop in cls_entry.get("properties", []):
            name = prop.get("name", "")
            if name and not name.startswith("_") and name not in _UNIVERSAL_SKIP:
                names.add(name)
        return names

    @staticmethod
    def _find_class_page(sibling_of: Path, class_name: str) -> "Path | None":
        directory = sibling_of.parent
        plain = directory / f"{class_name}.md"
        if plain.is_file() and plain != sibling_of:
            return plain
        for candidate in sorted(directory.glob(f"{class_name}-*.md")):
            if candidate != sibling_of:
                return candidate
        return None

    @staticmethod
    def _extract_documented_members(filepath: Path, candidates: set[str]) -> set[str]:
        try:
            raw = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return set()
        documented: set[str] = set()
        for m in _TABLE_MEMBER_RE.finditer(raw):
            documented.add(m.group(1))
        for m in _SECTION_HEADER_RE.finditer(raw):
            documented.add(m.group(1))
        for m in _BACKTICK_MEMBER_RE.finditer(raw):
            documented.add(m.group(1))
        return documented & candidates

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
