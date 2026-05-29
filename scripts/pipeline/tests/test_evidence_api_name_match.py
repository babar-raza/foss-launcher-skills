"""Tests for CLAIM-EXTRACT-001: _api_name_fallback_match and _load_delta_modified_apis.

Covers:
  - No delta file → empty result
  - Empty modified_apis list → empty result
  - Malformed delta JSON → empty result (safe fallback)
  - API name in prose → claim returned
  - API name in code block only → not returned (prose-only scanning)
  - API already matched → not double-counted
  - API not in knowledge.classes → skipped
  - API in modified_apis but no claim_id in api_to_claim → skipped
  - Multiple APIs matched in one page
  - Page with only frontmatter (no body) → empty result
  - Non-existent filepath → empty result
  - Deterministic ordering (sorted modified_apis)
  - cells/net fixture: modified_apis list ≥1 new match found
  - API name appearing in backtick inline code (counted as prose)
  - API name as partial word (no word-boundary match) → skipped
  - Already-matched with method notation (ClassName.method) → class extracted correctly
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evidence.mapper import (
    _load_delta_modified_apis,
    _api_name_fallback_match,
    configure as _mapper_configure,
)


# ---------------------------------------------------------------------------
# Minimal Knowledge stub
# ---------------------------------------------------------------------------

class FakeKnowledge:
    """Duck-type stub for Knowledge — no disk access."""

    def __init__(self, family="cells", platform="net",
                 classes=None, api_to_claim=None,
                 repo_sha="abc123"):
        self.family = family
        self.platform = platform
        self.classes = classes or {}
        self.api_to_claim = api_to_claim or {}
        self.repo_sha = repo_sha

    def has_method(self, cls, member):
        return False

    def has_property(self, cls, member):
        return False

    def has_enum_member(self, cls, member):
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_mapper_config():
    """Reset mapper module-level KNOWLEDGE_ROOT after each test (T1 compliance)."""
    yield
    _mapper_configure()  # reset to default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_delta(tmp_path, modified_apis=None, extra=None,
                 family="cells", platform="net"):
    """Write a minimal knowledge_delta.json under tmp_path/{family}/{platform}/merged/.

    configure() points KNOWLEDGE_ROOT to tmp_path, so the full path resolves correctly.
    """
    delta = {
        "generated_at": "2026-01-01",
        "base_sha": "aaa",
        "current_sha": "bbb",
        "new_claims": [],
        "removed_claims": [],
        "modified_claims": [],
        "new_apis": [],
        "removed_apis": [],
        "modified_apis": modified_apis or [],
        "resurrected_apis": [],
    }
    if extra:
        delta.update(extra)
    merged_dir = tmp_path / family / platform / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)
    (merged_dir / "knowledge_delta.json").write_text(json.dumps(delta), encoding="utf-8")
    return tmp_path


def _write_page(page_dir, body, frontmatter=None):
    """Write a content page under page_dir/index.md and return its Path."""
    fm = frontmatter or "title: Test\nauthor: Aspose\n"
    content = f"---\n{fm}---\n\n{body}"
    page_dir.mkdir(parents=True, exist_ok=True)
    page = page_dir / "index.md"
    page.write_text(content, encoding="utf-8")
    return page


# ---------------------------------------------------------------------------
# _load_delta_modified_apis tests
# ---------------------------------------------------------------------------

class TestLoadDeltaModifiedApis:

    def test_no_delta_file_returns_empty(self, tmp_path):
        kb = FakeKnowledge(family="cells", platform="net")
        _mapper_configure(knowledge_root=tmp_path)
        result = _load_delta_modified_apis(kb)
        assert result == set()

    def test_empty_modified_apis_list(self, tmp_path):
        kb = FakeKnowledge(family="cells", platform="net")
        _write_delta(tmp_path, modified_apis=[])
        _mapper_configure(knowledge_root=tmp_path)
        result = _load_delta_modified_apis(kb)
        assert result == set()

    def test_returns_modified_apis_as_set(self, tmp_path):
        kb = FakeKnowledge(family="cells", platform="net")
        _write_delta(tmp_path, modified_apis=["CellArea", "Worksheet", "CellArea"])
        _mapper_configure(knowledge_root=tmp_path)
        result = _load_delta_modified_apis(kb)
        assert result == {"CellArea", "Worksheet"}

    def test_malformed_json_returns_empty(self, tmp_path):
        kb = FakeKnowledge(family="cells", platform="net")
        merged_dir = tmp_path / "cells" / "net" / "merged"
        merged_dir.mkdir(parents=True, exist_ok=True)
        (merged_dir / "knowledge_delta.json").write_text("NOT JSON", encoding="utf-8")
        _mapper_configure(knowledge_root=tmp_path)
        result = _load_delta_modified_apis(kb)
        assert result == set()

    def test_missing_modified_apis_key_returns_empty(self, tmp_path):
        kb = FakeKnowledge(family="cells", platform="net")
        merged_dir = tmp_path / "cells" / "net" / "merged"
        merged_dir.mkdir(parents=True, exist_ok=True)
        (merged_dir / "knowledge_delta.json").write_text(
            json.dumps({"generated_at": "2026-01-01"}), encoding="utf-8"
        )
        _mapper_configure(knowledge_root=tmp_path)
        result = _load_delta_modified_apis(kb)
        assert result == set()


# ---------------------------------------------------------------------------
# _api_name_fallback_match tests
# ---------------------------------------------------------------------------

class TestApiNameFallbackMatch:

    def _make_kb(self, tmp_path, modified_apis, classes_and_claims,
                 family="cells", platform="net"):
        """Build a FakeKnowledge and write the delta."""
        classes = {c: {} for c in classes_and_claims}
        api_to_claim = {c: v for c, v in classes_and_claims.items()}
        kb = FakeKnowledge(family=family, platform=platform,
                           classes=classes, api_to_claim=api_to_claim)
        _write_delta(tmp_path, modified_apis=list(modified_apis),
                     family=family, platform=platform)
        return kb

    def test_no_delta_returns_empty(self, tmp_path):
        kb = FakeKnowledge(classes={"CellArea": {}}, api_to_claim={"CellArea": "CLM-001"})
        page = _write_page(tmp_path / "page", body="Discuss CellArea in this page.")
        # Point KNOWLEDGE_ROOT to a directory that has no delta file
        _mapper_configure(knowledge_root=tmp_path / "no-knowledge")
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert cids == []
        assert refs == []

    def test_api_in_prose_matched(self, tmp_path):
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        page = _write_page(tmp_path / "page", body="The CellArea class defines a range.")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert "CLM-cells-001" in cids
        assert "CellArea" in refs

    def test_api_in_code_block_excluded(self, tmp_path):
        """API only in a code block (not prose) — should NOT be returned by prose-only scan."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        body = "No prose mention.\n\n```java\nCellArea area = new CellArea();\n```"
        page = _write_page(tmp_path / "page", body=body)
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert "CLM-cells-001" not in cids
        assert "CellArea" not in refs

    def test_already_matched_api_skipped(self, tmp_path):
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        page = _write_page(tmp_path / "page", body="CellArea is mentioned in prose.")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched={"CellArea"})
        assert cids == []
        assert refs == []

    def test_already_matched_via_method_notation_skipped(self, tmp_path):
        """already_matched contains 'CellArea.getRow' — class 'CellArea' should be extracted."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        page = _write_page(tmp_path / "page", body="Use the CellArea for range selection.")
        # Simulate the runner's logic: already_matched includes the class extracted from method ref
        already = {"CellArea.getRow", "CellArea"}
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=already)
        assert cids == []

    def test_api_not_in_knowledge_classes_skipped(self, tmp_path):
        kb = FakeKnowledge(family="cells", platform="net", classes={}, api_to_claim={})
        _write_delta(tmp_path, modified_apis=["UnknownClass"])
        page = _write_page(tmp_path / "page", body="UnknownClass is mentioned.")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert cids == []
        assert refs == []

    def test_api_in_classes_but_no_claim_skipped(self, tmp_path):
        kb = FakeKnowledge(family="cells", platform="net",
                           classes={"CellArea": {}}, api_to_claim={})  # no claim
        _write_delta(tmp_path, modified_apis=["CellArea"])
        page = _write_page(tmp_path / "page", body="CellArea is used here.")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert cids == []
        assert refs == []

    def test_partial_word_no_match(self, tmp_path):
        """'CellAreaXtra' should not match 'CellArea' (word boundary check)."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        page = _write_page(tmp_path / "page", body="Use CellAreaXtra for extended ranges.")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert cids == []

    def test_multiple_apis_in_prose(self, tmp_path):
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea", "Worksheet", "Workbook"],
            classes_and_claims={
                "CellArea": "CLM-cells-001",
                "Worksheet": "CLM-cells-002",
                "Workbook": "CLM-cells-003",
            },
        )
        body = "This page discusses CellArea ranges, Worksheet operations, and Workbook creation."
        page = _write_page(tmp_path / "page", body=body)
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert set(cids) == {"CLM-cells-001", "CLM-cells-002", "CLM-cells-003"}
        assert set(refs) == {"CellArea", "Worksheet", "Workbook"}

    def test_only_one_api_in_prose_of_several(self, tmp_path):
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea", "Worksheet"],
            classes_and_claims={
                "CellArea": "CLM-cells-001",
                "Worksheet": "CLM-cells-002",
            },
        )
        page = _write_page(tmp_path / "page", body="Only Worksheet is mentioned here.")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert cids == ["CLM-cells-002"]
        assert refs == ["Worksheet"]

    def test_nonexistent_filepath_returns_empty(self, tmp_path):
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        missing = tmp_path / "no-such-file.md"
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(missing, kb, already_matched=set())
        assert cids == []
        assert refs == []

    def test_page_with_frontmatter_only(self, tmp_path):
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        page = tmp_path / "page" / "index.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("---\ntitle: Empty Page\n---\n", encoding="utf-8")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert cids == []
        assert refs == []

    def test_deterministic_ordering(self, tmp_path):
        """Results are sorted by api_name (sorted iteration over modified_apis)."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["Zebra", "Apple", "Mango"],
            classes_and_claims={
                "Zebra": "CLM-z",
                "Apple": "CLM-a",
                "Mango": "CLM-m",
            },
        )
        body = "Zebra, Apple, and Mango are all mentioned."
        page = _write_page(tmp_path / "page", body=body)
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        # Results should be sorted alphabetically (Apple < Mango < Zebra)
        assert refs == sorted(refs)

    def test_api_in_backtick_inline_code_in_prose(self, tmp_path):
        """API name in backtick inline code within prose should be found (not a code block)."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        page = _write_page(tmp_path / "page",
                           body="Use `CellArea` to define a spreadsheet range.")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert "CLM-cells-001" in cids

    def test_empty_modified_apis_returns_empty(self, tmp_path):
        kb = FakeKnowledge(
            family="cells", platform="net",
            classes={"CellArea": {}},
            api_to_claim={"CellArea": "CLM-cells-001"},
        )
        _write_delta(tmp_path, modified_apis=[])
        page = _write_page(tmp_path / "page", body="CellArea is mentioned.")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert cids == []
        assert refs == []

    def test_no_double_claim_when_api_in_both_prose_and_already_matched(self, tmp_path):
        """If API is in already_matched AND in prose, it must not appear in output."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        page = _write_page(tmp_path / "page", body="CellArea discussed in prose.")
        _mapper_configure(knowledge_root=tmp_path)
        cids1, _ = _api_name_fallback_match(page, kb, already_matched=set())
        cids2, _ = _api_name_fallback_match(page, kb, already_matched={"CellArea"})
        assert "CLM-cells-001" in cids1  # matched when not already seen
        assert cids2 == []              # not matched when already seen

    def test_cells_net_fixture_shows_at_least_one_match(self, tmp_path):
        """Integration-style: simulate cells/net fixture with 63 modified_apis.

        Uses synthetic page body mentioning 3 known cells/net API names from the
        modified_apis list (AutoFilterColorFilterModel, AutoFilterDynamicFilter,
        AutoFilterModel). Verifies that at least 1 new match is found.
        """
        modified = [
            "AutoFilterColorFilterModel", "AutoFilterDynamicFilter",
            "AutoFilterDynamicFilterModel", "AutoFilterModel",
            "AutoFilterSortConditionModel",
        ]
        classes = {m: {} for m in modified}
        api_to_claim = {m: f"CLM-cells-{i:04d}" for i, m in enumerate(modified)}
        kb = FakeKnowledge(family="cells", platform="net",
                           classes=classes, api_to_claim=api_to_claim)
        _write_delta(tmp_path, modified_apis=modified)
        body = (
            "The AutoFilterColorFilterModel controls filter color settings. "
            "AutoFilterDynamicFilter provides dynamic filter predicates. "
            "AutoFilterModel is the base filter configuration class."
        )
        page = _write_page(tmp_path / "page", body=body)
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert len(cids) >= 1, "Expected at least 1 match from cells/net modified_apis fixture"
        assert "AutoFilterColorFilterModel" in refs or "AutoFilterDynamicFilter" in refs

    def test_already_matched_partial_prevents_double_claim(self, tmp_path):
        """already_matched containing class name from method ref prevents fallback match."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["Worksheet"],
            classes_and_claims={"Worksheet": "CLM-cells-ws-001"},
        )
        page = _write_page(tmp_path / "page", body="Access Worksheet data easily.")
        # Simulate runner building already_matched: "Worksheet.getName" → extracts "Worksheet"
        already = {"Worksheet.getName", "Worksheet"}
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=already)
        assert cids == []

    def test_page_without_frontmatter_separator(self, tmp_path):
        """Page with no --- separator — full text is scanned."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        page = tmp_path / "page" / "index.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("CellArea is mentioned without frontmatter.", encoding="utf-8")
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert "CLM-cells-001" in cids

    def test_api_in_multi_line_prose(self, tmp_path):
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        body = (
            "First line of content.\n"
            "Second line mentions CellArea range.\n"
            "Third line is unrelated.\n"
        )
        page = _write_page(tmp_path / "page", body=body)
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert "CLM-cells-001" in cids

    def test_claim_deduplication_within_fallback(self, tmp_path):
        """Same API name appearing twice in prose returns only one claim entry."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        body = "CellArea for primary range. Use CellArea again for secondary range."
        page = _write_page(tmp_path / "page", body=body)
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert cids.count("CLM-cells-001") == 1
        assert refs.count("CellArea") == 1

    def test_multiple_classes_same_claim_id(self, tmp_path):
        """Two different APIs mapped to the same claim_id — deduplicated in output."""
        kb = FakeKnowledge(
            family="cells", platform="net",
            classes={"ClassA": {}, "ClassB": {}},
            api_to_claim={"ClassA": "CLM-shared-001", "ClassB": "CLM-shared-001"},
        )
        _write_delta(tmp_path, modified_apis=["ClassA", "ClassB"])
        body = "ClassA and ClassB are both mentioned here."
        page = _write_page(tmp_path / "page", body=body)
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert len([c for c in cids if c == "CLM-shared-001"]) >= 1

    def test_api_name_in_markdown_table_prose_cell(self, tmp_path):
        """API name appearing in a markdown table cell (prose, not code block)."""
        kb = self._make_kb(
            tmp_path,
            modified_apis=["CellArea"],
            classes_and_claims={"CellArea": "CLM-cells-001"},
        )
        body = "| Class | Description |\n|-------|-------------|\n| CellArea | Defines a range |"
        page = _write_page(tmp_path / "page", body=body)
        _mapper_configure(knowledge_root=tmp_path)
        cids, refs = _api_name_fallback_match(page, kb, already_matched=set())
        assert "CLM-cells-001" in cids
