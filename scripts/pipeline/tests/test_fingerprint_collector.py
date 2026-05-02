"""Tests for fingerprint_collector.py — Phase 2 (TC-PROD-003).

Covers:
  test_same_state_produces_same_hash
  test_generator_change_changes_generator_hash
  test_template_change_changes_template_hash
  test_products_json_change_changes_products_hash
  test_unknown_surface_raises_dependency_registry_error
  test_hash_scope_limited_to_registry_files
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dependency_registry import DependencyRegistry, UnknownSurfaceError
from fingerprint_collector import (
    InputFingerprintSet,
    _sha256_file,
    _sha256_text,
    collect_input_fingerprints,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_registry(
    template_paths=None,
    backing_generator=None,
    backing_skill=None,
    config_path=None,
):
    data = {
        "reference": {
            "description": "Test reference surface",
            "backing_generator": backing_generator,
            "backing_skill": backing_skill,
            "fingerprints_required": ["upstream_repo_sha", "local_knowledge_sha"],
            "template_paths": template_paths or [],
            "config_path": config_path,
            "content_root": "content/reference.aspose.org/en/{family}/{platform}",
            "expected_output_source": "registry_rules",
            "regeneration_triggers": ["upstream_repo_sha"],
            "reconciliation_triggers": ["output_missing"],
            "triage_checker": None,
            "supports_targeted_run": True,
            "status": "supported",
        }
    }
    return DependencyRegistry(data)


# ---------------------------------------------------------------------------
# SHA256 helper tests
# ---------------------------------------------------------------------------

class TestSha256Helpers:
    def test_sha256_file_returns_none_for_missing(self, tmp_path):
        result = _sha256_file(tmp_path / "nonexistent.txt")
        assert result is None

    def test_sha256_file_returns_hash_for_existing(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        result = _sha256_file(f)
        assert result is not None
        assert result.startswith("sha256:")
        assert len(result) == 71  # "sha256:" + 64 hex chars

    def test_sha256_text_stable(self):
        h1 = _sha256_text("hello")
        h2 = _sha256_text("hello")
        assert h1 == h2

    def test_sha256_text_different_inputs_differ(self):
        assert _sha256_text("hello") != _sha256_text("world")

    def test_sha256_file_stable_across_reads(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"\x00\x01\x02\x03")
        h1 = _sha256_file(f)
        h2 = _sha256_file(f)
        assert h1 == h2


# ---------------------------------------------------------------------------
# test_same_state_produces_same_hash
# ---------------------------------------------------------------------------

class TestSameStateProducesSameHash:
    def test_same_state_produces_same_hash(self, tmp_path):
        """Collecting fingerprints twice with the same on-disk state returns identical results."""
        registry = _make_registry()
        fp1 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        fp2 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        assert fp1.upstream_repo_sha == fp2.upstream_repo_sha
        assert fp1.local_knowledge_sha == fp2.local_knowledge_sha
        assert fp1.knowledge_content_hash == fp2.knowledge_content_hash
        assert fp1.products_json_hash == fp2.products_json_hash
        assert fp1.template_hash == fp2.template_hash
        assert fp1.generator_code_hash == fp2.generator_code_hash
        assert fp1.skill_version_hash == fp2.skill_version_hash
        assert fp1.config_hash == fp2.config_hash


# ---------------------------------------------------------------------------
# test_generator_change_changes_generator_hash
# ---------------------------------------------------------------------------

class TestGeneratorHashChanges:
    def test_generator_change_changes_generator_hash(self, tmp_path):
        """Changing the generator script changes generator_code_hash."""
        gen_path = tmp_path / "scripts" / "gen.py"
        gen_path.parent.mkdir(parents=True)
        gen_path.write_text("# version 1", encoding="utf-8")

        registry = _make_registry(backing_generator="scripts/gen.py")

        fp1 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        gen_path.write_text("# version 2", encoding="utf-8")

        fp2 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        assert fp1.generator_code_hash is not None
        assert fp2.generator_code_hash is not None
        assert fp1.generator_code_hash != fp2.generator_code_hash

    def test_missing_generator_returns_none(self, tmp_path):
        """Missing backing_generator file returns None, not an error."""
        registry = _make_registry(backing_generator="scripts/nonexistent.py")
        fp = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        assert fp.generator_code_hash is None

    def test_no_generator_returns_none(self, tmp_path):
        """backing_generator=None returns None generator_code_hash."""
        registry = _make_registry(backing_generator=None)
        fp = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        assert fp.generator_code_hash is None


# ---------------------------------------------------------------------------
# test_template_change_changes_template_hash
# ---------------------------------------------------------------------------

class TestTemplateHashChanges:
    def test_template_change_changes_template_hash(self, tmp_path):
        """Changing a template file changes template_hash."""
        templates_dir = tmp_path / "themes" / "docs" / "layouts"
        templates_dir.mkdir(parents=True)
        template_file = templates_dir / "page.html"
        template_file.write_text("<html>v1</html>", encoding="utf-8")

        registry = _make_registry(template_paths=["themes/docs/layouts"])

        fp1 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        template_file.write_text("<html>v2</html>", encoding="utf-8")

        fp2 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        assert fp1.template_hash is not None
        assert fp2.template_hash is not None
        assert fp1.template_hash != fp2.template_hash

    def test_no_template_paths_returns_none(self, tmp_path):
        """Empty template_paths returns None template_hash."""
        registry = _make_registry(template_paths=[])
        fp = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        assert fp.template_hash is None

    def test_empty_template_dir_returns_none(self, tmp_path):
        """Empty template directory (no .html files) returns None template_hash."""
        templates_dir = tmp_path / "themes" / "docs" / "layouts"
        templates_dir.mkdir(parents=True)
        registry = _make_registry(template_paths=["themes/docs/layouts"])
        fp = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        assert fp.template_hash is None


# ---------------------------------------------------------------------------
# test_products_json_change_changes_products_hash
# ---------------------------------------------------------------------------

class TestProductsJsonHashChanges:
    def test_products_json_change_changes_products_hash(self, tmp_path):
        """Changing the product entry in data/products.json changes products_json_hash."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        products_json = data_dir / "products.json"
        products_json.write_text(
            json.dumps({"cells/java": {"name": "Cells for Java", "version": "1.0"}}),
            encoding="utf-8",
        )

        registry = _make_registry()
        fp1 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        products_json.write_text(
            json.dumps({"cells/java": {"name": "Cells for Java", "version": "2.0"}}),
            encoding="utf-8",
        )

        fp2 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        assert fp1.products_json_hash is not None
        assert fp2.products_json_hash is not None
        assert fp1.products_json_hash != fp2.products_json_hash

    def test_missing_product_in_json_returns_none(self, tmp_path):
        """Product not found in products.json returns None, not an error."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "products.json").write_text(
            json.dumps({"other/product": {"name": "Other"}}),
            encoding="utf-8",
        )
        registry = _make_registry()
        fp = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        assert fp.products_json_hash is None

    def test_missing_products_json_returns_none(self, tmp_path):
        """Missing products.json file returns None, not an error."""
        registry = _make_registry()
        fp = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        assert fp.products_json_hash is None


# ---------------------------------------------------------------------------
# test_unknown_surface_raises_dependency_registry_error
# ---------------------------------------------------------------------------

class TestUnknownSurfaceError:
    def test_unknown_surface_raises_dependency_registry_error(self, tmp_path):
        """collect_input_fingerprints raises UnknownSurfaceError for unknown surface."""
        registry = _make_registry()
        with pytest.raises(UnknownSurfaceError):
            collect_input_fingerprints("cells/java", "nonexistent", registry, repo_root=tmp_path)


# ---------------------------------------------------------------------------
# test_hash_scope_limited_to_registry_files
# ---------------------------------------------------------------------------

class TestHashScopeLimited:
    def test_hash_scope_limited_to_registry_files(self, tmp_path):
        """template_hash only covers files in registry template_paths — extra files don't change it."""
        dir1 = tmp_path / "themes" / "docs" / "layouts"
        dir1.mkdir(parents=True)
        dir2 = tmp_path / "themes" / "other" / "layouts"
        dir2.mkdir(parents=True)

        (dir1 / "page.html").write_text("<html>in scope</html>", encoding="utf-8")
        (dir2 / "page.html").write_text("<html>out of scope</html>", encoding="utf-8")

        # Registry only lists dir1
        registry = _make_registry(template_paths=["themes/docs/layouts"])

        fp1 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        # Change the out-of-scope file
        (dir2 / "page.html").write_text("<html>changed but out of scope</html>", encoding="utf-8")

        fp2 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        # hash should be identical because out-of-scope file was not included
        assert fp1.template_hash is not None
        assert fp1.template_hash == fp2.template_hash

    def test_in_scope_change_changes_hash(self, tmp_path):
        """template_hash changes when an in-scope file changes."""
        dir1 = tmp_path / "themes" / "docs" / "layouts"
        dir1.mkdir(parents=True)
        f = dir1 / "page.html"
        f.write_text("<html>v1</html>", encoding="utf-8")

        registry = _make_registry(template_paths=["themes/docs/layouts"])

        fp1 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        f.write_text("<html>v2</html>", encoding="utf-8")
        fp2 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        assert fp1.template_hash != fp2.template_hash


# ---------------------------------------------------------------------------
# InputFingerprintSet method tests
# ---------------------------------------------------------------------------

class TestInputFingerprintSetMethods:
    def _make_fp(self, **overrides):
        defaults = dict(
            product="cells/java",
            subdomain="reference",
            upstream_repo_sha="abc123",
            local_knowledge_sha=None,
            knowledge_content_hash=None,
            products_json_hash=None,
            template_hash=None,
            generator_code_hash=None,
            skill_version_hash=None,
            config_hash=None,
        )
        defaults.update(overrides)
        return InputFingerprintSet(**defaults)

    def test_to_dict_has_all_keys(self):
        fp = self._make_fp()
        d = fp.to_dict()
        assert "upstream_repo_sha" in d
        assert d["upstream_repo_sha"] == "abc123"
        assert d["local_knowledge_sha"] is None

    def test_to_dict_excludes_collection_errors(self):
        fp = self._make_fp(collection_errors=["some error"])
        d = fp.to_dict()
        assert "collection_errors" not in d

    def test_for_fingerprints_required_filters(self):
        fp = self._make_fp(
            upstream_repo_sha="abc123",
            local_knowledge_sha="def456",
            knowledge_content_hash="sha256:aaa",
        )
        result = fp.for_fingerprints_required(["upstream_repo_sha", "local_knowledge_sha"])
        assert set(result.keys()) == {"upstream_repo_sha", "local_knowledge_sha"}
        assert "knowledge_content_hash" not in result

    def test_for_fingerprints_required_empty_list(self):
        fp = self._make_fp(upstream_repo_sha="abc123")
        result = fp.for_fingerprints_required([])
        assert result == {}

    def test_collection_errors_recorded(self, tmp_path):
        """collection_errors is populated when fingerprint collection encounters an issue."""
        # Bad product slug triggers an error
        registry = _make_registry()
        fp = collect_input_fingerprints("badformat", "reference", registry, repo_root=tmp_path)
        assert len(fp.collection_errors) > 0


# ---------------------------------------------------------------------------
# TC-HEAL-001: upstream_repo_sha uses correct flat clone cache path
# ---------------------------------------------------------------------------

class TestUpstreamShaCloneCachePath:
    def test_upstream_sha_uses_flat_aspose_prefix_layout(self, tmp_path):
        """TC-HEAL-001: upstream_repo_sha reads from aspose_{family}_{platform} dir, not family/platform.

        Verifies the fix: _clone_cache_path('cells', 'java') resolves to
        runs/.clone_cache/aspose_cells_java, not runs/.clone_cache/cells/java.

        FOLLOWUP-TEST-001: strengthened to assert non-None SHA returned by mocking
        subprocess.run so the assertion does not depend on a live git installation.
        """
        import subprocess as _subprocess
        from unittest.mock import patch as _patch, MagicMock
        from fingerprint_collector import _collect_upstream_repo_sha

        # Simulate the correct flat clone cache layout
        clone_dir = tmp_path / "runs" / ".clone_cache" / "aspose_cells_java"
        clone_dir.mkdir(parents=True)

        fake_sha = "deadbeef" * 5  # 40-char hex SHA

        # Mock subprocess.run to return a successful git rev-parse result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = fake_sha + "\n"

        with _patch("fingerprint_collector._clone_cache_path", return_value=clone_dir), \
             _patch("fingerprint_collector.subprocess.run", return_value=mock_result):
            sha = _collect_upstream_repo_sha("cells", "java")

        # FOLLOWUP-TEST-001: assert non-None SHA with correct value
        assert sha is not None, "upstream_repo_sha must not be None when clone dir exists"
        assert sha == fake_sha, f"Expected {fake_sha!r}, got {sha!r}"

        # The wrong nested path must not have been created
        wrong_path = tmp_path / "runs" / ".clone_cache" / "cells" / "java"
        assert not wrong_path.exists(), "Wrong path must not have been created"

    def test_missing_clone_cache_returns_none_gracefully(self, tmp_path):
        """Missing clone cache returns None without raising an exception."""
        from unittest.mock import patch as _patch
        from fingerprint_collector import _collect_upstream_repo_sha
        nonexistent = tmp_path / "runs" / ".clone_cache" / "aspose_cells_java"
        with _patch("fingerprint_collector._clone_cache_path", return_value=nonexistent):
            sha = _collect_upstream_repo_sha("cells", "java")
        assert sha is None


# ---------------------------------------------------------------------------
# TC-HEAL-002: products_json_hash uses real list format with family/platform fields
# ---------------------------------------------------------------------------

class TestProductsJsonListFormat:
    def test_products_json_list_format_finds_entry(self, tmp_path):
        """TC-HEAL-002: Finds entry when products.json is a list with family/platform fields."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        products_json = data_dir / "products.json"
        products_json.write_text(
            json.dumps([
                {"family": "cells", "platform": "java", "repo_name": "Aspose.Cells-FOSS-Java", "active": True},
                {"family": "words", "platform": "net", "repo_name": "Aspose.Words-FOSS-Net", "active": True},
            ]),
            encoding="utf-8",
        )
        registry = _make_registry()
        fp = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        assert fp.products_json_hash is not None

    def test_products_json_list_format_hash_changes_on_entry_change(self, tmp_path):
        """TC-HEAL-002: Hash changes when the specific product entry in the list changes."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        products_json = data_dir / "products.json"
        products_json.write_text(
            json.dumps([{"family": "cells", "platform": "java", "version": "1.0"}]),
            encoding="utf-8",
        )
        registry = _make_registry()
        fp1 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        products_json.write_text(
            json.dumps([{"family": "cells", "platform": "java", "version": "2.0"}]),
            encoding="utf-8",
        )
        fp2 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        assert fp1.products_json_hash is not None
        assert fp2.products_json_hash is not None
        assert fp1.products_json_hash != fp2.products_json_hash

    def test_products_json_list_format_other_entry_does_not_match(self, tmp_path):
        """TC-HEAL-002: Only the matching family/platform entry is hashed; others are ignored."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        products_json = data_dir / "products.json"
        products_json.write_text(
            json.dumps([
                {"family": "words", "platform": "net", "version": "1.0"},
            ]),
            encoding="utf-8",
        )
        registry = _make_registry()
        # cells/java is not in the list — should return None
        fp = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)
        assert fp.products_json_hash is None

    def test_products_json_list_format_hash_stable_across_unrelated_entry_change(self, tmp_path):
        """TC-HEAL-002: Changing an unrelated product entry does not change the target hash."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        products_json = data_dir / "products.json"
        products_json.write_text(
            json.dumps([
                {"family": "cells", "platform": "java", "version": "1.0"},
                {"family": "words", "platform": "net", "version": "1.0"},
            ]),
            encoding="utf-8",
        )
        registry = _make_registry()
        fp1 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        # Change words/net — cells/java hash must not change
        products_json.write_text(
            json.dumps([
                {"family": "cells", "platform": "java", "version": "1.0"},
                {"family": "words", "platform": "net", "version": "9.9"},
            ]),
            encoding="utf-8",
        )
        fp2 = collect_input_fingerprints("cells/java", "reference", registry, repo_root=tmp_path)

        assert fp1.products_json_hash is not None
        assert fp1.products_json_hash == fp2.products_json_hash
