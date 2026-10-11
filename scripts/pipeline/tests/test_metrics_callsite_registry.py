"""Tests for metrics_callsite_registry.yaml — Slice 1 of Agent Metrics Integration.

Validates registry structure, call-site entries, and boundary exclusions.
No network calls. No posting. No secrets.
"""

import re
from pathlib import Path

import pytest
import yaml

_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "metrics_callsite_registry.yaml"
)

ALLOWED_CAPTURE_METHODS = {
    "wrapper_native",
    "llm_router_native",
    "approved_adapter",
    "blocked",
}

EXPECTED_TRANSPORT_IDS = {"CS-001", "CS-002", "CS-004", "CS-009", "CS-010", "CS-014", "CS-015"}
BOUNDARY_ONLY_IDS = {"CS-011", "CS-012", "CS-013"}

# Values that must NOT appear as endpoint_source
NOT_ENDPOINT_SOURCES = {"LITELLM_KEY", "LLM_API_KEY", "PROFESSIONALIZE_API_KEY"}


@pytest.fixture(scope="module")
def registry():
    with open(_REGISTRY_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def call_sites(registry):
    return registry["call_sites"]


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #


class TestRegistryStructure:
    def test_yaml_loads(self, registry):
        assert isinstance(registry, dict)

    def test_has_call_sites(self, registry):
        assert "call_sites" in registry
        assert isinstance(registry["call_sites"], dict)

    def test_has_allowed_capture_methods(self, registry):
        assert "allowed_capture_methods" in registry

    def test_summary_counts_match_call_sites(self, registry):
        call_sites = registry["call_sites"]
        summary = registry["summary"]
        assert summary["total_registered_transport_sites"] == len(call_sites)
        assert summary["active"] == sum(
            entry["status"] == "active" for entry in call_sites.values()
        )
        for method in ("wrapper_native", "llm_router_native", "approved_adapter"):
            assert summary[method] == sum(
                entry["capture_method"] == method for entry in call_sites.values()
            )

    def test_router_native_entries_do_not_claim_direct_transport(self, call_sites):
        for call_site_id, entry in call_sites.items():
            if entry["capture_method"] != "llm_router_native":
                continue
            assert "LLMRouter" in entry["transport_type"], call_site_id
            assert "direct urllib" not in str(entry).lower(), call_site_id


# --------------------------------------------------------------------------- #
# Expected Transport Sites
# --------------------------------------------------------------------------- #


class TestTransportSites:
    def test_exactly_expected_transport_sites(self, call_sites):
        registered_ids = set(call_sites.keys())
        assert registered_ids == EXPECTED_TRANSPORT_IDS

    @pytest.mark.parametrize("cs_id", sorted(EXPECTED_TRANSPORT_IDS))
    def test_transport_site_exists(self, call_sites, cs_id):
        assert cs_id in call_sites

    def test_cs013_m2m_not_registered(self, call_sites):
        assert "CS-013" not in call_sites

    @pytest.mark.parametrize("cs_id", sorted(BOUNDARY_ONLY_IDS))
    def test_boundary_not_registered(self, call_sites, cs_id):
        assert cs_id not in call_sites


# --------------------------------------------------------------------------- #
# Field Separation (base_url_source, endpoint_source, api_key_source)
# --------------------------------------------------------------------------- #


class TestFieldSeparation:
    @pytest.mark.parametrize("cs_id", sorted(EXPECTED_TRANSPORT_IDS))
    def test_has_base_url_source(self, call_sites, cs_id):
        entry = call_sites[cs_id]
        assert "base_url_source" in entry
        assert entry["base_url_source"]

    @pytest.mark.parametrize("cs_id", sorted(EXPECTED_TRANSPORT_IDS))
    def test_has_endpoint_source(self, call_sites, cs_id):
        entry = call_sites[cs_id]
        assert "endpoint_source" in entry
        assert entry["endpoint_source"]

    @pytest.mark.parametrize("cs_id", sorted(EXPECTED_TRANSPORT_IDS))
    def test_has_api_key_source(self, call_sites, cs_id):
        entry = call_sites[cs_id]
        assert "api_key_source" in entry
        assert entry["api_key_source"]

    @pytest.mark.parametrize("cs_id", sorted(EXPECTED_TRANSPORT_IDS))
    def test_endpoint_source_is_not_api_key(self, call_sites, cs_id):
        entry = call_sites[cs_id]
        assert entry["endpoint_source"] not in NOT_ENDPOINT_SOURCES, (
            f"{cs_id} endpoint_source must not be an API key env var"
        )


# --------------------------------------------------------------------------- #
# Capture Methods
# --------------------------------------------------------------------------- #


class TestCaptureMethods:
    @pytest.mark.parametrize("cs_id", sorted(EXPECTED_TRANSPORT_IDS))
    def test_capture_method_in_allowed_enum(self, call_sites, cs_id):
        entry = call_sites[cs_id]
        assert entry["capture_method"] in ALLOWED_CAPTURE_METHODS

    def test_direct_bypasses_use_approved_adapter_or_stricter(self, call_sites):
        bypass_ids = {"CS-004", "CS-009", "CS-014"}
        strict_methods = {"llm_router_native", "wrapper_native"}
        for cs_id in bypass_ids:
            entry = call_sites[cs_id]
            assert entry["capture_method"] in strict_methods, (
                f"{cs_id} bypass must use approved_adapter or wrapper_native"
            )


# --------------------------------------------------------------------------- #
# Required Fields Per Entry
# --------------------------------------------------------------------------- #

REQUIRED_ENTRY_FIELDS = {
    "call_site_id",
    "category",
    "path",
    "function_or_class",
    "current_provider",
    "transport_type",
    "base_url_source",
    "endpoint_source",
    "api_key_source",
    "model_source",
    "capture_method",
    "allowed_capture_methods",
    "owner_component",
    "work_slice_context_source",
    "status",
    "usage_metadata_expected",
    "api_call_count_required",
    "retry_behavior",
    "batching_behavior",
    "cache_behavior",
    "tests",
    "last_verified",
    "evidence_reference",
}


class TestEntryCompleteness:
    @pytest.mark.parametrize("cs_id", sorted(EXPECTED_TRANSPORT_IDS))
    def test_entry_has_all_required_fields(self, call_sites, cs_id):
        entry = call_sites[cs_id]
        missing = REQUIRED_ENTRY_FIELDS - set(entry.keys())
        assert not missing, f"{cs_id} missing fields: {missing}"

    @pytest.mark.parametrize("cs_id", sorted(EXPECTED_TRANSPORT_IDS))
    def test_entry_has_tests(self, call_sites, cs_id):
        entry = call_sites[cs_id]
        assert entry["tests"], f"{cs_id} must have tests defined"

    @pytest.mark.parametrize("cs_id", sorted(EXPECTED_TRANSPORT_IDS))
    def test_entry_has_evidence_reference(self, call_sites, cs_id):
        entry = call_sites[cs_id]
        assert entry["evidence_reference"], f"{cs_id} must have evidence_reference"


# --------------------------------------------------------------------------- #
# Secret Scan
# --------------------------------------------------------------------------- #

_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{10,})"
    r"|(ghp_[A-Za-z0-9]{10,})"
    r"|(AIzaSy[A-Za-z0-9_-]{10,})"
    r"|(Bearer\s+[A-Za-z0-9._-]{20,})",
    re.IGNORECASE,
)


class TestNoSecrets:
    def test_no_secrets_in_registry(self):
        text = _REGISTRY_PATH.read_text()
        assert _SECRET_PATTERN.search(text) is None, "Registry contains secret-like values"
