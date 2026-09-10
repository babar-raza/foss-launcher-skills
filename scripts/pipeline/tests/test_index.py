"""Tests for index.py — pure functions and minimal fixture-based tests.

Covers:
  - compute_api_confidence: pure function, no I/O
  - _is_public_api_entry: pure function
  - _is_interface_name: pure function
  - _has_surface: pure function
  - build_index: disk-based, tested via temp directory fixture
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from index import (
    compute_api_confidence,
    _is_public_api_entry,
    _is_interface_name,
    _has_surface,
    build_index,
    KNOWLEDGE_ROOT,
)
import index as _index_module


@pytest.fixture(autouse=True)
def _reset_index():
    yield
    _index_module.configure()


# ---------------------------------------------------------------------------
# compute_api_confidence — pure function
# ---------------------------------------------------------------------------

class TestComputeApiConfidence:
    def test_high_tier(self):
        assert compute_api_confidence(20, 0.5) == "high"

    def test_high_boundary(self):
        # Exactly at the minimum high threshold
        assert compute_api_confidence(15, 0.20) == "high"

    def test_medium_tier(self):
        assert compute_api_confidence(8, 0.15) == "medium"

    def test_medium_boundary(self):
        assert compute_api_confidence(5, 0.10) == "medium"

    def test_low_api_total_too_small(self):
        assert compute_api_confidence(4, 0.50) == "low"

    def test_low_method_pct_too_small(self):
        assert compute_api_confidence(20, 0.05) == "low"

    def test_low_empty(self):
        assert compute_api_confidence(0, 0.0) == "low"

    def test_high_method_pct_at_0_20(self):
        # Exact boundary: api_total=15, method_pct=0.20 → high
        assert compute_api_confidence(15, 0.20) == "high"

    def test_medium_method_pct_below_high(self):
        # api_total=15, method_pct=0.19 → not high → try medium: 15>=5 and 0.19>=0.10 → medium
        assert compute_api_confidence(15, 0.19) == "medium"


# ---------------------------------------------------------------------------
# _is_interface_name — pure function
# ---------------------------------------------------------------------------

class TestIsInterfaceName:
    def test_valid_interface(self):
        assert _is_interface_name("IShape")

    def test_valid_interface_longer(self):
        assert _is_interface_name("ISlide")

    def test_io_prefix_excluded(self):
        # IO = Input/Output, not the interface marker
        assert not _is_interface_name("IOService")

    def test_lowercase_second_char_excluded(self):
        assert not _is_interface_name("Invalid")

    def test_too_short(self):
        assert not _is_interface_name("I")
        assert not _is_interface_name("IX")

    def test_not_starting_with_I(self):
        assert not _is_interface_name("Shape")


# ---------------------------------------------------------------------------
# _has_surface — pure function
# ---------------------------------------------------------------------------

class TestHasSurface:
    def test_has_methods(self):
        assert _has_surface({"methods": [{"name": "foo"}]})

    def test_has_properties(self):
        assert _has_surface({"properties": ["Width"]})

    def test_has_enum_members(self):
        assert _has_surface({"enum_members": ["A", "B"]})

    def test_empty_entry(self):
        assert not _has_surface({})

    def test_empty_lists(self):
        assert not _has_surface({"methods": [], "properties": [], "enum_members": []})


# ---------------------------------------------------------------------------
# _is_public_api_entry — pure function
# ---------------------------------------------------------------------------

class TestIsPublicApiEntry:
    def test_public_class(self):
        entry = {"kind": "class", "name": "Workbook", "file": "aspose/cells/workbook.py"}
        assert _is_public_api_entry(entry)

    def test_private_name(self):
        entry = {"kind": "class", "name": "_InternalHelper", "file": "aspose/cells/helper.py"}
        assert not _is_public_api_entry(entry)

    def test_function_kind(self):
        entry = {"kind": "function", "name": "public_func", "file": "aspose/cells/util.py"}
        assert not _is_public_api_entry(entry)

    def test_empty_name(self):
        entry = {"kind": "class", "name": "", "file": "aspose/cells/empty.py"}
        assert not _is_public_api_entry(entry)

    def test_test_file(self):
        entry = {"kind": "class", "name": "TestHelper", "file": "tests/test_helper.py"}
        assert not _is_public_api_entry(entry)

    def test_non_dict(self):
        assert not _is_public_api_entry("not a dict")
        assert not _is_public_api_entry(None)


# ---------------------------------------------------------------------------
# build_index — disk fixture test
# ---------------------------------------------------------------------------

def _make_merged_dir(tmp_path: Path, family: str, platform: str) -> Path:
    """Create a minimal merged/ directory fixture for build_index."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)

    model = {
        "family": family,
        "platform": platform,
        "repo_sha": "abc123",
        "merged_at": "2026-01-01T00:00:00Z",
        "stats": {"total_classes": 2},
        "stale_since": None,
    }
    (merged / "model.yaml").write_text(
        "family: " + family + "\n"
        "platform: " + platform + "\n"
        "repo_sha: abc123\n"
        "merged_at: '2026-01-01T00:00:00Z'\n"
        "stale_since: null\n"
        "stats:\n"
        "  total_classes: 2\n",
        encoding="utf-8",
    )

    api_surface = [
        {"kind": "class", "name": "Workbook", "file": "aspose/cells/workbook.py",
         "methods": [{"name": "save"}, {"name": "load"}], "properties": ["FileName"]},
        {"kind": "class", "name": "Worksheet", "file": "aspose/cells/worksheet.py",
         "methods": [{"name": "add_row"}], "properties": []},
        # This one should be filtered out by _is_public_api_entry (function kind)
        {"kind": "function", "name": "helper_func", "file": "aspose/cells/util.py"},
    ]
    (merged / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
    (merged / "claims.json").write_text(json.dumps([
        "Workbook supports loading XLSX files.",
        "Worksheet.add_row adds a new row to the sheet.",
    ]), encoding="utf-8")
    (merged / "formats.json").write_text(json.dumps([
        {"format": "xlsx", "can_import": True, "can_export": True},
        {"format": "csv", "direction": "export"},
    ]), encoding="utf-8")
    return merged


def test_build_index_returns_dict(tmp_path, monkeypatch):
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    result = build_index("cells", "python")
    assert result is not None
    assert isinstance(result, dict)


def test_build_index_summary_fields(tmp_path, monkeypatch):
    """build_index returns a condensed summary dict; full index is written to index.json."""
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    result = build_index("cells", "python")
    # Return value has summary keys
    for key in ("family", "platform", "api_confidence", "class_count", "claim_count"):
        assert key in result, f"Missing key in return value: {key}"
    # Full index is written to disk
    index_path = tmp_path / "knowledge" / "cells" / "python" / "merged" / "index.json"
    assert index_path.exists(), "index.json must be written to disk"
    written = json.loads(index_path.read_text(encoding="utf-8"))
    for key in ("family", "platform", "api_confidence", "classes"):
        assert key in written, f"Missing key in written index.json: {key}"


def test_build_index_api_confidence_returned(tmp_path, monkeypatch):
    """api_confidence must be present in return value."""
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    result = build_index("cells", "python")
    assert result["api_confidence"] in ("high", "medium", "low")


def test_build_index_filters_function_kind(tmp_path, monkeypatch):
    """helper_func with kind=function must not appear in classes list in written index.json."""
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    build_index("cells", "python")
    written = json.loads(
        (tmp_path / "knowledge" / "cells" / "python" / "merged" / "index.json")
        .read_text(encoding="utf-8")
    )
    assert "helper_func" not in written["classes"]
    assert "Workbook" in written["classes"]


def test_build_index_formats_split(tmp_path, monkeypatch):
    """Formats should be split into import/export lists in written index.json."""
    _make_merged_dir(tmp_path, "cells", "python")
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    build_index("cells", "python")
    written = json.loads(
        (tmp_path / "knowledge" / "cells" / "python" / "merged" / "index.json")
        .read_text(encoding="utf-8")
    )
    assert "xlsx" in written["formats"]["import"]
    assert "xlsx" in written["formats"]["export"]
    assert "csv" in written["formats"]["export"]
    assert "csv" not in written["formats"]["import"]


def test_build_index_no_model_yaml_returns_none(tmp_path, monkeypatch):
    """build_index returns None when model.yaml is missing."""
    merged = tmp_path / "knowledge" / "cells" / "python" / "merged"
    merged.mkdir(parents=True)
    _index_module.configure(knowledge_root=tmp_path / "knowledge")
    result = build_index("cells", "python")
    assert result is None


class TestCrossProductIndexNotTruncatedBySingleProductInvocation:
    """HARDEN-words-net (2026-07-22): main()'s single-product invocation
    (`index.py {family} {platform}`, as opposed to `index.py all`) used to
    overwrite knowledge/_index.json — documented as a CROSS-PRODUCT summary
    — with an entry for ONLY the requested product, silently discarding
    every other product's summary. Found live: running `index.py words net`
    truncated a ~26-product _index.json down to 1 entry. Fixed by always
    rebuilding the full cross-product list from discover_products(),
    regardless of which invocation mode triggered the write."""

    def test_single_product_invocation_preserves_other_products(self, tmp_path, monkeypatch):
        _make_merged_dir(tmp_path, "cells", "python")
        _make_merged_dir(tmp_path, "pdf", "net")
        _make_merged_dir(tmp_path, "words", "net")
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        # First, build the full index (as `index.py all` would).
        monkeypatch.setattr(sys, "argv", ["index.py", "all"])
        _index_module.main()
        index_path = tmp_path / "knowledge" / "_index.json"
        full = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(full["products"]) == 3

        # Now invoke single-product mode for just ONE of the three --
        # this must NOT truncate the cross-product index to 1 entry.
        monkeypatch.setattr(sys, "argv", ["index.py", "words", "net"])
        _index_module.main()
        after = json.loads(index_path.read_text(encoding="utf-8"))
        families = {(p["family"], p["platform"]) for p in after["products"]}
        assert len(after["products"]) == 3, (
            "single-product invocation must not truncate the cross-product "
            "index -- this is the exact live regression found on words/net"
        )
        assert families == {("cells", "python"), ("pdf", "net"), ("words", "net")}

    def test_single_product_invocation_updates_that_products_own_entry(self, tmp_path, monkeypatch):
        """The requested product's OWN entry must still be freshly
        recomputed (not just preserved stale) -- confirms this fix doesn't
        regress into reading a prior _index.json's stale entries."""
        merged = _make_merged_dir(tmp_path, "words", "net")
        _make_merged_dir(tmp_path, "cells", "python")
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        monkeypatch.setattr(sys, "argv", ["index.py", "all"])
        _index_module.main()

        # Mutate words/net's claims.json so a fresh build_index() call
        # would see a different claim_count than the stale first pass.
        (merged / "claims.json").write_text(json.dumps([
            "Claim one.", "Claim two.", "Claim three.",
        ]), encoding="utf-8")

        monkeypatch.setattr(sys, "argv", ["index.py", "words", "net"])
        _index_module.main()
        index_path = tmp_path / "knowledge" / "_index.json"
        after = json.loads(index_path.read_text(encoding="utf-8"))
        words_net = next(p for p in after["products"] if p["family"] == "words")
        assert words_net["claim_count"] == 3

    def test_single_product_invocation_on_first_ever_run_still_writes_full_index(self, tmp_path, monkeypatch):
        """No prior _index.json exists at all -- single-product mode must
        still discover and include every product with merged/ present, not
        just the one requested."""
        _make_merged_dir(tmp_path, "cells", "python")
        _make_merged_dir(tmp_path, "words", "net")
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        monkeypatch.setattr(sys, "argv", ["index.py", "words", "net"])
        _index_module.main()
        index_path = tmp_path / "knowledge" / "_index.json"
        result = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(result["products"]) == 2

    def test_requested_product_own_entry_never_dropped_when_missing_claims_json(self, tmp_path, monkeypatch):
        """HARDEN-words-net (adversarial re-review, 2026-07-22): a product
        with model.yaml but no claims.json builds a valid entry
        (build_index() defaults absent claims.json to []) but never appears
        in discover_products()'s scan (which requires claims.json to exist
        as its candidacy signal). Without an explicit guarantee, the
        just-explicitly-requested product's OWN entry -- despite being
        successfully built -- would silently never be appended to
        _index.json, since the main loop only matches tuples that
        discover_products() actually yields."""
        _make_merged_dir(tmp_path, "cells", "python")

        # words/net: model.yaml + api_surface.json present, but NO claims.json
        words_merged = tmp_path / "knowledge" / "words" / "net" / "merged"
        words_merged.mkdir(parents=True)
        words_merged.joinpath("model.yaml").write_text(
            "family: words\nplatform: net\nrepo_sha: abc123\n"
            "merged_at: '2026-01-01T00:00:00Z'\nstale_since: null\n"
            "stats:\n  total_classes: 1\n",
            encoding="utf-8",
        )
        words_merged.joinpath("api_surface.json").write_text(json.dumps([
            {"kind": "class", "name": "Document", "file": "aspose/words/document.py",
             "methods": [{"name": "save"}], "properties": []},
        ]), encoding="utf-8")
        # deliberately no claims.json written here

        _index_module.configure(knowledge_root=tmp_path / "knowledge")
        monkeypatch.setattr(sys, "argv", ["index.py", "words", "net"])
        _index_module.main()

        index_path = tmp_path / "knowledge" / "_index.json"
        result = json.loads(index_path.read_text(encoding="utf-8"))
        families = {(p["family"], p["platform"]) for p in result["products"]}
        assert ("words", "net") in families, (
            "the explicitly-requested product's own entry must never be "
            "silently dropped, even when it's absent from discover_products()'s "
            "candidacy scan"
        )
        assert ("cells", "python") in families


# ---------------------------------------------------------------------------
# vectors_current / vectors_status / vectors_generated_at (TC-VEC-03-C, RC2)
# ---------------------------------------------------------------------------

def _write_active_vector_profile(tmp_path, family, platform, *, source_hash, generated_at="2026-09-10T00:00:00Z"):
    root = tmp_path / "knowledge" / "_vectors" / family / platform
    profile_dir = root / "profiles" / "p1"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (root / "active.json").write_text(
        json.dumps({"version": "2.0.0", "profile_id": "p1"}), encoding="utf-8"
    )
    (profile_dir / "manifest.json").write_text(
        json.dumps({"profile_id": "p1", "source_hash": source_hash, "generated_at": generated_at}),
        encoding="utf-8",
    )


class TestBuildIndexVectorsCurrent:
    def test_missing_when_no_vectors_dir(self, tmp_path):
        _make_merged_dir(tmp_path, "cells", "python")
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        result = build_index("cells", "python")

        assert result["vectors_current"] is False
        assert result["vectors_status"] == "missing"
        assert result["vectors_generated_at"] is None

    def test_current_when_hash_matches_live_api_surface(self, tmp_path):
        import hashlib

        _make_merged_dir(tmp_path, "cells", "python")
        api_path = tmp_path / "knowledge" / "cells" / "python" / "merged" / "api_surface.json"
        matching_hash = hashlib.sha256(api_path.read_bytes()).hexdigest()
        _write_active_vector_profile(tmp_path, "cells", "python", source_hash=matching_hash)
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        result = build_index("cells", "python")

        assert result["vectors_current"] is True
        assert result["vectors_status"] == "current"
        assert result["vectors_generated_at"] == "2026-09-10T00:00:00Z"

    def test_stale_when_hash_mismatches(self, tmp_path):
        _make_merged_dir(tmp_path, "cells", "python")
        _write_active_vector_profile(tmp_path, "cells", "python", source_hash="0" * 64)
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        result = build_index("cells", "python")

        assert result["vectors_current"] is False
        assert result["vectors_status"] == "stale"
        # A stale profile still recorded a real generation timestamp — must
        # not be conflated with "missing" (which reports None here).
        assert result["vectors_generated_at"] == "2026-09-10T00:00:00Z"
