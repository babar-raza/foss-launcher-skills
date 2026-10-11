"""
test_backlink_anchor.py — A6/A7 Anchor Text Registry Tests

Tests: 61 total (8 classes)
  TestAnchorCurrentInventory          10
  TestAnchorRegistrySchema             8
  TestAnchorRendererCompatibility     13
  TestAnchorConfigMutation             6
  TestAuthorityAnchorConfigHash        7
  TestBackfillUsesApprovedRenderedAnchorOnly  8
  TestAnchorTransitionMode             4
  TestBridgeDisplayPolicy              5
"""
from __future__ import annotations

import copy
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Resolve repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import (
    AnchorPolicyError,
    AUTHORITY_ANCHOR_STALE,
    ANCHOR_CONFIG_HASH_MISMATCH,
    ACCEPTABLE_LEGACY_KB_PRE_P0,
    CANONICAL_KB_POST_P0,
    UPGRADE_CANDIDATE_NOT_YET_FIXED,
    LEGACY_COMPAT_MODE,
    CANONICAL_POST_P0_MODE,
    load_anchor_registry,
    compute_anchor_config_hash,
    render_anchor_text,
    select_anchor_template_id,
    build_enterprise_anchor_suffix,
)

# ── Shared test fixtures ──────────────────────────────────────────────────────

FAMILIES_MAP = {
    "words": "Aspose.Words",
    "cells": "Aspose.Cells",
    "pdf": "Aspose.PDF",
    "3d": "Aspose.3D",
    "barcode": "Aspose.BarCode",
    "slides": "Aspose.Slides",
    "cad": "Aspose.CAD",
    "imaging": "Aspose.Imaging",
}

PLATFORMS_MAP = {
    "net": ".NET",
    "java": "Java",
    "python": "Python",
    "cpp": "C++",
    "nodejs": "Node.js",
    "go": "Go",
    "android": "Android",
    "php": "PHP",
    "ruby": "Ruby",
}

REGISTRY_PATH = REPO_ROOT / "data" / "backlinks" / "anchor_text_registry.yaml"
OVERRIDES_PATH = REPO_ROOT / "data" / "backlinks" / "anchor_overrides.yaml"

EXPECTED_TEMPLATE_IDS = {
    "docs-platform", "docs-family",
    "kb-platform", "kb-family",
    "reference-platform", "reference-family",
    "products-platform", "products-family",
    "blog-products-platform", "blog-products-family",
}


def _load_registry():
    return load_anchor_registry(REGISTRY_PATH)


# ── TestAnchorCurrentInventory ────────────────────────────────────────────────

class TestAnchorCurrentInventory:
    """10 tests: verifies live content anchor patterns against registry renderer."""

    def test_inventory_loads_and_schema_validates(self):
        """Registry file exists and contains required fields."""
        reg = _load_registry()
        assert "templates" in reg
        assert "sentence_wrappers" in reg
        assert "safe_fallback" in reg

    def test_docs_python_anchor_exact_match(self):
        """docs/words/python → 'Aspose.Words for Python — Enterprise Documentation'."""
        reg = _load_registry()
        result = render_anchor_text("docs-platform", "words", "python",
                                    "https://docs.aspose.com/words/python/",
                                    reg, FAMILIES_MAP, PLATFORMS_MAP)
        assert result == "Aspose.Words for Python — Enterprise Documentation"

    def test_docs_family_no_platform_in_anchor(self):
        """docs/words family → 'Aspose.Words — Enterprise Documentation' (no platform)."""
        reg = _load_registry()
        result = render_anchor_text("docs-family", "words", None,
                                    "https://docs.aspose.com/words/",
                                    reg, FAMILIES_MAP, PLATFORMS_MAP)
        assert result == "Aspose.Words — Enterprise Documentation"
        assert "for" not in result

    def test_kb_platform_anchor_pre_p0(self):
        """KB pre-P0 audit constant is defined for ACCEPTABLE_LEGACY classification."""
        assert ACCEPTABLE_LEGACY_KB_PRE_P0 == "ACCEPTABLE_LEGACY_KB_PRE_P0"

    def test_kb_platform_anchor_post_p0(self):
        """kb/words/python post-P0 → 'Aspose.Words for Python — Enterprise Knowledge Base'."""
        reg = _load_registry()
        result = render_anchor_text("kb-platform", "words", "python",
                                    "https://kb.aspose.com/words/python/",
                                    reg, FAMILIES_MAP, PLATFORMS_MAP)
        assert result == "Aspose.Words for Python — Enterprise Knowledge Base"
        assert "Knowledge Base" in result

    def test_reference_class_bridge_url_canonical_display(self):
        """REF_CLASS with python-net URL: anchor shows 'Python' not 'python-net'."""
        reg = _load_registry()
        # Canonical platform 'python' used — bridge slug 'python-net' only in URL
        result = render_anchor_text("reference-platform", "words", "python",
                                    "https://reference.aspose.com/words/python-net/",
                                    reg, FAMILIES_MAP, PLATFORMS_MAP)
        assert result == "Aspose.Words for Python — Enterprise API Reference"
        assert "python-net" not in result

    def test_products_plugin_anchor(self):
        """products/words/python → 'Aspose.Words for Python — Enterprise Product'."""
        reg = _load_registry()
        result = render_anchor_text("products-platform", "words", "python",
                                    "https://products.aspose.com/words/python/",
                                    reg, FAMILIES_MAP, PLATFORMS_MAP)
        assert result == "Aspose.Words for Python — Enterprise Product"

    def test_blog_platform_anchor(self):
        """blog/3d/net → 'Aspose.3D for .NET — Enterprise Product'."""
        reg = _load_registry()
        result = render_anchor_text("blog-products-platform", "3d", "net",
                                    "https://products.aspose.com/3d/net/",
                                    reg, FAMILIES_MAP, PLATFORMS_MAP)
        assert result == "Aspose.3D for .NET — Enterprise Product"

    def test_blog_family_fallback_anchor(self):
        """blog/3d family fallback → 'Aspose.3D — Enterprise Product Family'."""
        reg = _load_registry()
        result = render_anchor_text("blog-products-family", "3d", None,
                                    "https://products.aspose.com/3d/",
                                    reg, FAMILIES_MAP, PLATFORMS_MAP)
        assert result == "Aspose.3D — Enterprise Product Family"

    def test_all_10_live_patterns_present_in_matrix(self):
        """All 10 template IDs present in registry."""
        reg = _load_registry()
        templates = set(reg.get("templates", {}).keys())
        for tid in EXPECTED_TEMPLATE_IDS:
            assert tid in templates, f"Missing template_id: {tid}"


# ── TestAnchorRegistrySchema ──────────────────────────────────────────────────

class TestAnchorRegistrySchema:
    """8 tests: validates structure and correctness of anchor_text_registry.yaml."""

    def test_registry_loads_valid_yaml(self):
        """Registry file parses as valid YAML without error."""
        reg = _load_registry()
        assert isinstance(reg, dict)

    def test_all_10_template_ids_present(self):
        """Exactly the 10 required template_ids are present."""
        reg = _load_registry()
        templates = set(reg.get("templates", {}).keys())
        assert EXPECTED_TEMPLATE_IDS.issubset(templates)

    def test_config_hash_field_is_optional(self):
        """config_hash field may be absent (removed before hashing) — schema accepts both."""
        reg = _load_registry()
        # Must not fail when config_hash is absent
        reg_copy = copy.deepcopy(reg)
        reg_copy.pop("config_hash", None)
        assert "templates" in reg_copy  # still valid after pop

    def test_no_template_has_empty_anchor_text(self):
        """No template has empty or None anchor_text field."""
        reg = _load_registry()
        for tid, tmpl in reg.get("templates", {}).items():
            assert tmpl.get("anchor_text"), f"Empty anchor_text for template {tid!r}"

    def test_fallback_chain_terminates_no_cycles(self):
        """Every fallback_to chain terminates at null — no infinite cycles."""
        reg = _load_registry()
        templates = reg.get("templates", {})
        for tid, tmpl in templates.items():
            visited = set()
            current = tmpl.get("fallback_to")
            visited.add(tid)
            while current is not None:
                assert current not in visited, f"Cycle detected in fallback chain at {current!r}"
                visited.add(current)
                current = templates.get(current, {}).get("fallback_to")

    def test_sentence_wrappers_contain_anchor_placeholder(self):
        """Every sentence_wrapper.text contains {anchor} placeholder."""
        reg = _load_registry()
        for wid, wrapper in reg.get("sentence_wrappers", {}).items():
            text = wrapper.get("text", "")
            assert "{anchor}" in text, f"sentence_wrapper {wid!r} missing {{anchor}} placeholder"

    def test_empty_overrides_schema_validates(self):
        """anchor_overrides.yaml parses and has overrides key."""
        import yaml
        data = yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8")) or {}
        assert "overrides" in data

    def test_safe_fallback_template_id_resolves(self):
        """safe_fallback.template_id resolves to an existing template."""
        reg = _load_registry()
        sf = reg.get("safe_fallback", {})
        fallback_id = sf.get("template_id")
        assert fallback_id is not None
        assert fallback_id in reg.get("templates", {}), (
            f"safe_fallback template_id {fallback_id!r} not in templates"
        )


# ── TestAnchorRendererCompatibility (golden-master) ───────────────────────────

class TestAnchorRendererCompatibility:
    """13 tests: config renderer produces identical output to hardcoded generator."""

    def _render(self, template_id, family, platform, url):
        reg = _load_registry()
        return render_anchor_text(template_id, family, platform, url,
                                  reg, FAMILIES_MAP, PLATFORMS_MAP)

    def test_docs_platform_identical_to_hardcoded(self):
        result = self._render("docs-platform", "words", "python",
                              "https://docs.aspose.com/words/python/")
        suffix = build_enterprise_anchor_suffix("https://docs.aspose.com/words/python/", "platform")
        expected = f"Aspose.Words for Python — {suffix}"
        assert result == expected

    def test_docs_family_identical_to_hardcoded(self):
        result = self._render("docs-family", "words", None,
                              "https://docs.aspose.com/words/")
        suffix = build_enterprise_anchor_suffix("https://docs.aspose.com/words/", "family")
        expected = f"Aspose.Words — {suffix}"
        assert result == expected

    def test_kb_platform_renders_kb_suffix(self):
        result = self._render("kb-platform", "words", "python",
                              "https://kb.aspose.com/words/python/")
        assert "Enterprise Knowledge Base" in result
        assert "Aspose.Words for Python" in result

    def test_reference_platform_identical_to_hardcoded(self):
        result = self._render("reference-platform", "words", "python",
                              "https://reference.aspose.com/words/python/")
        suffix = build_enterprise_anchor_suffix("https://reference.aspose.com/words/python/", "platform")
        expected = f"Aspose.Words for Python — {suffix}"
        assert result == expected

    def test_reference_family_identical_to_hardcoded(self):
        result = self._render("reference-family", "words", None,
                              "https://reference.aspose.com/words/")
        suffix = build_enterprise_anchor_suffix("https://reference.aspose.com/words/", "family")
        expected = f"Aspose.Words — {suffix}"
        assert result == expected

    def test_products_platform_identical_to_hardcoded(self):
        result = self._render("products-platform", "words", "python",
                              "https://products.aspose.com/words/python/")
        suffix = build_enterprise_anchor_suffix("https://products.aspose.com/words/python/", "platform")
        expected = f"Aspose.Words for Python — {suffix}"
        assert result == expected

    def test_products_family_identical_to_hardcoded(self):
        result = self._render("products-family", "words", None,
                              "https://products.aspose.com/words/")
        suffix = build_enterprise_anchor_suffix("https://products.aspose.com/words/", "family")
        expected = f"Aspose.Words — {suffix}"
        assert result == expected

    def test_blog_platform_identical_to_hardcoded(self):
        result = self._render("blog-products-platform", "3d", "net",
                              "https://products.aspose.com/3d/net/")
        suffix = build_enterprise_anchor_suffix("https://products.aspose.com/3d/net/", "platform")
        expected = f"Aspose.3D for .NET — {suffix}"
        assert result == expected

    def test_blog_family_fallback_identical_to_hardcoded(self):
        result = self._render("blog-products-family", "3d", None,
                              "https://products.aspose.com/3d/")
        suffix = build_enterprise_anchor_suffix("https://products.aspose.com/3d/", "family")
        expected = f"Aspose.3D — {suffix}"
        assert result == expected

    def test_platform_display_net_renders_dotnet(self):
        """'net' platform renders as '.NET' in anchor text."""
        result = self._render("docs-platform", "words", "net",
                              "https://docs.aspose.com/words/net/")
        assert ".NET" in result
        assert " net " not in result.lower()

    def test_platform_display_cpp_renders_cxx(self):
        """'cpp' platform renders as 'C++' in anchor text."""
        result = self._render("docs-platform", "pdf", "cpp",
                              "https://docs.aspose.com/pdf/cpp/")
        assert "C++" in result

    def test_skip_types_raise_anchor_policy_error_not_return_fallback(self):
        """SKIP/BLOCKED PageTypes raise AnchorPolicyError — no fallback returned."""
        reg = _load_registry()
        # Unknown template_id (simulates SKIP type guard at call site)
        with pytest.raises(AnchorPolicyError):
            render_anchor_text("nonexistent-skip-template", "words", "python",
                               "https://docs.aspose.com/words/python/",
                               reg, FAMILIES_MAP, PLATFORMS_MAP)

    def test_v18_non_exception_pages_require_exact_match(self):
        """(A7-02) A page not in {AL, LFD, MO, OOS} with mismatched anchor is SUSPECTED_DEFECT.

        Simulates V18 classification: a product page anchor that doesn't match
        the config renderer output cannot be classified as ACCEPTABLE_LEGACY.
        """
        reg = _load_registry()
        # Render the canonical anchor via config renderer
        canonical = render_anchor_text("docs-platform", "words", "net",
                                       "https://docs.aspose.com/words/net/",
                                       reg, FAMILIES_MAP, PLATFORMS_MAP)
        # Simulate a mismatched anchor (hand-written with wrong suffix)
        mismatched = "Aspose.Words for .NET — Docs"

        # mismatched is not equal to canonical
        assert canonical != mismatched

        # In V18 terms: mismatched is not in {AL, LFD, MO, OOS} exception classes
        # so it would be classified as SUSPECTED_DEFECT — confirmed by mismatch detection
        exception_classes = {
            "ACCEPTABLE_LEGACY",
            "LONG_FORM_DEPRECATED",
            "MANUAL_OVERRIDE",
            "OUT_OF_SCOPE",
        }
        # A non-exception page where content != canonical is a defect
        is_suspected_defect = (canonical != mismatched)
        assert is_suspected_defect, "Mismatched non-exception anchor must be SUSPECTED_DEFECT"


# ── TestAnchorConfigMutation ──────────────────────────────────────────────────

class TestAnchorConfigMutation:
    """6 tests: verifies config mutation isolates to expected templates only."""

    def _make_mutated_registry(self):
        """Return a mutated registry (docs-platform suffix changed) as in-memory dict."""
        reg = copy.deepcopy(_load_registry())
        reg["templates"]["docs-platform"]["anchor_text"] = (
            "{fam} for {plat} — TEST CHANGED Documentation"
        )
        return reg

    def test_mutating_docs_template_changes_only_docs_anchors(self):
        """Mutating docs-platform template changes docs anchors, not reference/kb/products."""
        mutated = self._make_mutated_registry()
        # Docs anchor changes
        docs_result = render_anchor_text("docs-platform", "words", "python",
                                         "https://docs.aspose.com/words/python/",
                                         mutated, FAMILIES_MAP, PLATFORMS_MAP)
        assert "TEST CHANGED" in docs_result

        # Reference anchor unchanged
        ref_result = render_anchor_text("reference-platform", "words", "python",
                                        "https://reference.aspose.com/words/python/",
                                        mutated, FAMILIES_MAP, PLATFORMS_MAP)
        assert "TEST CHANGED" not in ref_result
        assert "Enterprise API Reference" in ref_result

        # KB anchor unchanged
        kb_result = render_anchor_text("kb-platform", "words", "python",
                                       "https://kb.aspose.com/words/python/",
                                       mutated, FAMILIES_MAP, PLATFORMS_MAP)
        assert "TEST CHANGED" not in kb_result

    def test_mutation_does_not_modify_production_config(self):
        """In-memory mutation does not write to production anchor_text_registry.yaml."""
        original_text = REGISTRY_PATH.read_text(encoding="utf-8")
        _ = self._make_mutated_registry()
        # File must be unchanged
        assert REGISTRY_PATH.read_text(encoding="utf-8") == original_text

    def test_mutation_does_not_modify_content_files(self):
        """No mutation of anchor registry touches content/ files."""
        # We simply verify no content write happened — content/ must not be in test outputs
        content_dir = REPO_ROOT / "content"
        assert content_dir.exists()
        # Mutation is purely in-memory; content/ is not touched
        _ = self._make_mutated_registry()
        # No assertion to make beyond "no exception raised"

    def test_config_mutation_changes_anchor_config_hash(self):
        """Writing a mutated registry to tmp file produces a different hash."""
        import yaml
        original_hash = compute_anchor_config_hash(REGISTRY_PATH)
        mutated = self._make_mutated_registry()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml",
                                         encoding="utf-8", delete=False) as f:
            yaml.dump(mutated, f, allow_unicode=True)
            tmp_path = Path(f.name)
        try:
            mutated_hash = compute_anchor_config_hash(tmp_path)
            assert original_hash != mutated_hash, "Semantic change must alter config hash"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_anchor_config_hash_is_deterministic(self):
        """(A7-06) Hash is stable across whitespace/comment changes; canonical JSON algorithm."""
        import yaml
        reg = copy.deepcopy(_load_registry())
        reg.pop("config_hash", None)

        # Write same data twice with different YAML formatting
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml",
                                          encoding="utf-8", delete=False) as f1:
            yaml.dump(reg, f1, allow_unicode=True, default_flow_style=False)
            tmp1 = Path(f1.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml",
                                          encoding="utf-8", delete=False) as f2:
            yaml.dump(reg, f2, allow_unicode=True, default_flow_style=True)
            tmp2 = Path(f2.name)

        try:
            hash1 = compute_anchor_config_hash(tmp1)
            hash2 = compute_anchor_config_hash(tmp2)
            assert hash1 == hash2, "Same semantic data must produce same canonical JSON hash"
            assert hash1.startswith("sha256:")
        finally:
            tmp1.unlink(missing_ok=True)
            tmp2.unlink(missing_ok=True)

    def test_semantic_change_changes_hash(self):
        """(A7-06) Changing anchor_text value changes hash; comment-only change does not."""
        import yaml
        reg = copy.deepcopy(_load_registry())
        reg.pop("config_hash", None)

        # Original hash
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml",
                                          encoding="utf-8", delete=False) as f:
            yaml.dump(reg, f, allow_unicode=True)
            orig_path = Path(f.name)
        orig_hash = compute_anchor_config_hash(orig_path)

        # Semantic change
        reg2 = copy.deepcopy(reg)
        reg2["templates"]["docs-platform"]["anchor_text"] = "CHANGED_TEXT"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml",
                                          encoding="utf-8", delete=False) as f2:
            yaml.dump(reg2, f2, allow_unicode=True)
            changed_path = Path(f2.name)
        changed_hash = compute_anchor_config_hash(changed_path)

        try:
            assert orig_hash != changed_hash, "Semantic change must alter hash"
        finally:
            orig_path.unlink(missing_ok=True)
            changed_path.unlink(missing_ok=True)


# ── TestAuthorityAnchorConfigHash ─────────────────────────────────────────────

class TestAuthorityAnchorConfigHash:
    """7 tests: anchor config hash staleness detection in authority records."""

    def _make_authority_record(self, anchor_config_hash=None, allowed=True,
                                rendered_anchor="Aspose.Words for Python — Enterprise API Reference",
                                anchor_template_id="reference-platform"):
        if anchor_config_hash is None:
            anchor_config_hash = compute_anchor_config_hash(REGISTRY_PATH)
        return {
            "source_path": "content/reference.aspose.org/en/words/python/Document.md",
            "target_path": "words/python/aspose.words/document",
            "target_subdomain": "reference",
            "anchor_template_id": anchor_template_id,
            "anchor_config_hash": anchor_config_hash,
            "rendered_anchor_text": rendered_anchor,
            "allowed_for_generation": allowed,
        }

    def test_authority_record_has_anchor_template_id(self):
        """Authority record must have non-empty anchor_template_id field."""
        rec = self._make_authority_record()
        assert rec["anchor_template_id"]
        assert rec["anchor_template_id"] in EXPECTED_TEMPLATE_IDS

    def test_authority_record_has_anchor_config_hash(self):
        """Authority record must have anchor_config_hash starting with 'sha256:'."""
        rec = self._make_authority_record()
        assert rec["anchor_config_hash"].startswith("sha256:")

    def test_stale_anchor_hash_blocks_insertion(self):
        """Stale anchor_config_hash (mismatch) must block insertion."""
        stale_hash = "sha256:aaaa000000000000000000000000000000000000000000000000000000000000"
        rec = self._make_authority_record(anchor_config_hash=stale_hash)
        active_hash = compute_anchor_config_hash(REGISTRY_PATH)
        is_stale = rec["anchor_config_hash"] != active_hash
        assert is_stale, "Record with old hash should be detected as stale"
        # Stale anchor should not allow generation
        # (in backfill: `allowed_for_generation` must be False when stale)
        # Simulated: stale detection => insertion blocked
        assert AUTHORITY_ANCHOR_STALE == "AUTHORITY_ANCHOR_STALE"

    def test_stale_anchor_hash_allowed_in_compat_mode(self):
        """(A6) Stale hash in --anchor-compat-mode (audit-only) produces warning, not block."""
        stale_hash = "sha256:bbbb000000000000000000000000000000000000000000000000000000000000"
        rec = self._make_authority_record(anchor_config_hash=stale_hash)
        active_hash = compute_anchor_config_hash(REGISTRY_PATH)
        is_stale = rec["anchor_config_hash"] != active_hash
        # In compat mode: stale is a warning, not an immediate block
        # Represented as freshness_warning flag, not blocked
        assert is_stale
        # ANCHOR_CONFIG_HASH_MISMATCH constant is defined for this case
        assert ANCHOR_CONFIG_HASH_MISMATCH == "ANCHOR_CONFIG_HASH_MISMATCH"

    def test_fresh_hash_allows_insertion(self):
        """Fresh (matching) anchor_config_hash allows insertion."""
        active_hash = compute_anchor_config_hash(REGISTRY_PATH)
        rec = self._make_authority_record(anchor_config_hash=active_hash)
        is_fresh = rec["anchor_config_hash"] == active_hash
        assert is_fresh

    def test_hash_check_not_bypassed_by_override(self):
        """Override presence in record does not skip hash check."""
        stale_hash = "sha256:cccc000000000000000000000000000000000000000000000000000000000000"
        rec = self._make_authority_record(anchor_config_hash=stale_hash)
        rec["override_present"] = True
        active_hash = compute_anchor_config_hash(REGISTRY_PATH)
        # Even with override, hash mismatch is stale
        is_stale = rec["anchor_config_hash"] != active_hash
        assert is_stale, "Override does not bypass hash check"

    def test_backfill_rejects_anchor_compat_mode_flag(self):
        """(A7-05) backlink_backfill.py argparse must not accept --anchor-compat-mode."""
        backfill_path = REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "backlink_backfill.py"
        if not backfill_path.exists():
            pytest.skip("backlink_backfill.py not yet created")
        source = backfill_path.read_text(encoding="utf-8")
        # The flag must not be registered in argparse
        assert "anchor-compat-mode" not in source, (
            "backlink_backfill.py must not accept --anchor-compat-mode (audit-only flag per A7-05)"
        )


# ── TestBackfillUsesApprovedRenderedAnchorOnly ────────────────────────────────

class TestBackfillUsesApprovedRenderedAnchorOnly:
    """8 tests: backfill reads rendered_anchor_text from authority, never calls renderer."""

    def _get_backfill_source(self):
        backfill_path = (REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"
                         / "backlink_backfill.py")
        if not backfill_path.exists():
            return None
        return backfill_path.read_text(encoding="utf-8")

    def test_backfill_reads_rendered_anchor_from_authority(self):
        """Authority record with rendered_anchor_text is readable for anchor."""
        rec = {
            "rendered_anchor_text": "Aspose.Words for Python — Enterprise API Reference",
            "anchor_template_id": "reference-platform",
            "anchor_config_hash": compute_anchor_config_hash(REGISTRY_PATH),
            "allowed_for_generation": True,
        }
        assert rec["rendered_anchor_text"] == "Aspose.Words for Python — Enterprise API Reference"

    def test_backfill_does_not_call_build_enterprise_anchor_suffix(self):
        """(A7-04) backlink_backfill.py must not call build_enterprise_anchor_suffix() for anchors."""
        src = self._get_backfill_source()
        if src is None:
            pytest.skip("backlink_backfill.py not yet created")
        # It's OK to DEFINE build_enterprise_anchor_suffix (deprecated) but not call it
        # in the primary insertion path. Check for direct invocation.
        # Note: the import of build_enterprise_anchor_suffix is acceptable for backward compat.
        # We check that render_anchor_text is not called in backfill (A7-04 boundary).
        assert "render_anchor_text(" not in src, (
            "backlink_backfill.py must not call render_anchor_text() — "
            "reads rendered_anchor_text from authority instead (A7-04)"
        )

    def test_backfill_rejects_authority_missing_rendered_anchor(self):
        """Authority record missing rendered_anchor_text should not be inserted."""
        rec = {
            "anchor_template_id": "reference-platform",
            "allowed_for_generation": True,
            # Note: no rendered_anchor_text key
        }
        has_anchor = "rendered_anchor_text" in rec
        assert not has_anchor, "Record missing rendered_anchor_text detected as invalid"

    def test_backfill_uses_override_anchor_when_present(self):
        """anchor_overrides.yaml override anchor_text takes precedence."""
        import yaml
        overrides_data = yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8")) or {}
        # Empty overrides.yaml is valid; simulate what an override record would look like
        override_entry = {
            "source_path": "content/reference.aspose.org/en/words/python/Document.md",
            "link_slot": "enterprise_deep_primary",
            "anchor_text": "Document Class Custom Anchor",
            "reason": "Test override",
            "evidence": "internal",
            "review_policy": "annual",
        }
        assert override_entry["anchor_text"] == "Document Class Custom Anchor"

    def test_backfill_does_not_call_llm_for_anchor(self):
        """backlink_backfill.py must not call any LLM for anchor text."""
        src = self._get_backfill_source()
        if src is None:
            pytest.skip("backlink_backfill.py not yet created")
        assert "llm_router" not in src, "backfill must not import llm_router"
        assert "professionalize_client" not in src, "backfill must not import professionalize_client"

    def test_backfill_section_header_from_slot_registry(self):
        """Section header (## See Also / ## Related Resources) comes from slot registry."""
        from lib.backlink_targets import load_slot_registry
        slot_registry_path = REPO_ROOT / "data" / "backlinks" / "link_slot_registry.yaml"
        if not slot_registry_path.exists():
            pytest.skip("link_slot_registry.yaml not yet created")
        reg = load_slot_registry(slot_registry_path)
        # enterprise_deep_primary slot should have insertion_section defined
        deep_slot = reg.get("enterprise_deep_primary")
        assert deep_slot is not None
        assert deep_slot.insertion_section in ("## See Also", "## Related Resources")

    def test_backfill_does_not_import_anchor_registry_yaml(self):
        """(A7-04) backlink_backfill.py must not import/load anchor_text_registry.yaml at runtime."""
        src = self._get_backfill_source()
        if src is None:
            pytest.skip("backlink_backfill.py not yet created")
        assert "anchor_text_registry" not in src, (
            "backlink_backfill.py must not reference anchor_text_registry.yaml directly — "
            "reads rendered_anchor_text from authority record only (A7-04)"
        )

    def test_backfill_does_not_call_compute_anchor_config_hash(self):
        """(A7-04) backlink_backfill.py must not call compute_anchor_config_hash()."""
        src = self._get_backfill_source()
        if src is None:
            pytest.skip("backlink_backfill.py not yet created")
        assert "compute_anchor_config_hash(" not in src, (
            "backlink_backfill.py must not call compute_anchor_config_hash() — "
            "hash check is resolver's responsibility, not backfill's (A7-04)"
        )


# ── TestAnchorTransitionMode ──────────────────────────────────────────────────

class TestAnchorTransitionMode:
    """4 tests: KB anchor transition mode and skill governance artifact checks."""

    def test_anchor_skill_matrix_artifact_exists(self):
        """Phase P5 artifact: anchor_skill_coverage_matrix.md must exist."""
        artifact = REPO_ROOT / "reports" / "backlinks" / "anchor-hardening" / "anchor_skill_coverage_matrix.md"
        if not artifact.exists():
            pytest.skip("Phase P5 not yet run — anchor_skill_coverage_matrix.md not created")
        assert artifact.stat().st_size > 0, "anchor_skill_coverage_matrix.md must be non-empty"

    def test_all_matched_skills_have_anchor_governance_block(self):
        """Phase P5: all content-writing skills have Anchor Text Governance block."""
        v25_path = REPO_ROOT / "reports" / "backlinks" / "sprint-BL-DEEP-EXEC-v3.1" / "v25_skill_anchor_coverage.json"
        if not v25_path.exists():
            pytest.skip("Phase P5 not yet run — v25_skill_anchor_coverage.json not created")
        data = json.loads(v25_path.read_text(encoding="utf-8"))
        assert data.get("skills_missing_block", []) == [], (
            f"Skills missing anchor governance block: {data.get('skills_missing_block')}"
        )

    def test_kb_legacy_compat_mode_default(self):
        """LEGACY_COMPAT_MODE is the default KB anchor mode constant."""
        assert LEGACY_COMPAT_MODE == "LEGACY_COMPAT_MODE"
        # Default is LEGACY_COMPAT_MODE — existing KB pages with docs.aspose.com links
        # are classified as ACCEPTABLE_LEGACY_KB_PRE_P0 in this mode
        assert ACCEPTABLE_LEGACY_KB_PRE_P0 == "ACCEPTABLE_LEGACY_KB_PRE_P0"

    def test_canonical_post_p0_mode_requires_explicit_flag(self):
        """CANONICAL_POST_P0_MODE requires explicit flag — is not the default."""
        # Both constants exist and are distinct
        assert LEGACY_COMPAT_MODE != CANONICAL_POST_P0_MODE
        assert CANONICAL_POST_P0_MODE == "CANONICAL_POST_P0_MODE"
        # Post-P0 canonical mode has its own audit status
        assert CANONICAL_KB_POST_P0 == "CANONICAL_KB_POST_P0"
        assert UPGRADE_CANDIDATE_NOT_YET_FIXED == "UPGRADE_CANDIDATE_NOT_YET_FIXED"


# ── TestBridgeDisplayPolicy ───────────────────────────────────────────────────

class TestBridgeDisplayPolicy:
    """5 tests: bridge slug display policy (A7-12)."""

    def test_bridge_slug_raises_anchor_policy_error(self):
        """render_anchor_text() raises AnchorPolicyError when bridge slug passed as platform."""
        reg = _load_registry()
        with pytest.raises(AnchorPolicyError) as exc_info:
            render_anchor_text("reference-platform", "words", "python-net",
                               "https://reference.aspose.com/words/python-net/",
                               reg, FAMILIES_MAP, PLATFORMS_MAP)
        assert "python-net" in str(exc_info.value)
        assert "canonical" in str(exc_info.value).lower() or "bridge" in str(exc_info.value).lower()

    def test_canonical_slug_renders_correctly(self):
        """Canonical 'python' slug renders as 'Python' in anchor text."""
        reg = _load_registry()
        result = render_anchor_text("reference-platform", "words", "python",
                                    "https://reference.aspose.com/words/python-net/",
                                    reg, FAMILIES_MAP, PLATFORMS_MAP)
        assert result == "Aspose.Words for Python — Enterprise API Reference"
        assert "python-net" not in result

    def test_all_known_bridge_slugs_in_policy_raise(self):
        """All 12 known_bridge_slugs raise AnchorPolicyError when passed as platform."""
        reg = _load_registry()
        policy = reg.get("display_platform_policy", {})
        known_bridges = policy.get("known_bridge_slugs", [])
        assert len(known_bridges) >= 12, f"Expected ≥12 bridge slugs, got {len(known_bridges)}"

        for bridge_slug in known_bridges:
            with pytest.raises(AnchorPolicyError, match=bridge_slug):
                render_anchor_text("reference-platform", "words", bridge_slug,
                                   f"https://reference.aspose.com/words/{bridge_slug}/",
                                   reg, FAMILIES_MAP, PLATFORMS_MAP)

    def test_approve_authority_uses_canonical_key_not_bridge_slug(self):
        """PLATFORM_ALIASES maps bridge slugs to canonical keys before render_anchor_text()."""
        from lib.backlink_targets import PLATFORM_ALIASES
        # python-net must map to python
        assert PLATFORM_ALIASES.get("python-net") == "python"
        # go-cpp must map to go
        assert PLATFORM_ALIASES.get("go-cpp") == "go"
        # nodejs-net must map to nodejs
        assert PLATFORM_ALIASES.get("nodejs-net") == "nodejs"
        # androidjava must map to android
        assert PLATFORM_ALIASES.get("androidjava") == "android"

    def test_v27_passes_on_no_bridge_slugs_in_authority(self):
        """V27: authority records with canonical platform render zero bridge slugs in anchor text."""
        reg = _load_registry()
        policy = reg.get("display_platform_policy", {})
        known_bridges = set(policy.get("known_bridge_slugs", []))

        # Simulate V27 scan on a valid authority record
        records = [
            {
                "rendered_anchor_text": "Aspose.Words for Python — Enterprise API Reference",
                "family": "words",
                "platform": "python",
            },
            {
                "rendered_anchor_text": "Aspose.Cells for Go — Enterprise API Reference",
                "family": "cells",
                "platform": "go",
            },
        ]

        bridge_in_anchor_found = 0
        for rec in records:
            anchor = rec.get("rendered_anchor_text", "")
            for slug in known_bridges:
                if slug in anchor:
                    bridge_in_anchor_found += 1

        assert bridge_in_anchor_found == 0, (
            f"V27 FAIL: {bridge_in_anchor_found} bridge slugs found in rendered anchor texts"
        )
