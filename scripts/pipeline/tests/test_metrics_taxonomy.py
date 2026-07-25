"""Tests for metrics_taxonomy.yaml — Slice 1 of Agent Metrics Integration.

Validates taxonomy structure, required values, and boundary exclusions.
No network calls. No posting. No secrets.
"""

import re
from pathlib import Path

import pytest
import yaml

_TAXONOMY_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "metrics_taxonomy.yaml"
)


@pytest.fixture(scope="module")
def taxonomy():
    with open(_TAXONOMY_PATH) as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #


class TestTaxonomyStructure:
    def test_yaml_loads(self, taxonomy):
        assert isinstance(taxonomy, dict)

    def test_required_top_level_keys(self, taxonomy):
        required = {
            "version",
            "agent_owner",
            "default_website_mapping",
            "website_sections",
            "products",
            "platforms",
            "agents",
            "job_types",
            "field_derivation_rules",
            "non_professionalize_boundaries",
            "posting_modes",
        }
        assert required.issubset(taxonomy.keys())


# --------------------------------------------------------------------------- #
# Owner
# --------------------------------------------------------------------------- #


class TestAgentOwner:
    def test_agent_owner_is_babar_raza(self, taxonomy):
        assert taxonomy["agent_owner"] == "Babar Raza"


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #


class TestAgents:
    REQUIRED_AGENTS = [
        "aspose-org-knowledge-enrichment",
        "aspose-org-knowledge-embedding",
        "aspose-org-gap-evaluation",
        "aspose-org-gap-synthesis",
        "aspose-org-fix-specification",
        "aspose-org-translator",
        "aspose-org-seo-recommendation",
    ]

    @pytest.mark.parametrize("agent_name", REQUIRED_AGENTS)
    def test_required_agent_exists(self, taxonomy, agent_name):
        assert agent_name in taxonomy["agents"]


# --------------------------------------------------------------------------- #
# Job Types
# --------------------------------------------------------------------------- #


class TestJobTypes:
    REQUIRED_JOB_TYPES = [
        "knowledge_enrichment",
        "knowledge_embedding",
        "gap_evaluation",
        "gap_synthesis",
        "fix_specification",
        "content_translation",
        "seo_recommendation",
        "test",
    ]

    @pytest.mark.parametrize("job_type", REQUIRED_JOB_TYPES)
    def test_required_job_type_exists(self, taxonomy, job_type):
        assert job_type in taxonomy["job_types"]


# --------------------------------------------------------------------------- #
# Products and Platforms
# --------------------------------------------------------------------------- #


class TestProducts:
    REQUIRED_PRODUCTS = [
        "3d", "barcode", "cad", "cells", "diagram", "email", "html",
        "imaging", "note", "ocr", "page", "pdf", "psd", "slides", "svg",
        "tasks", "tex", "words", "zip", "_all",
    ]

    @pytest.mark.parametrize("product_key", REQUIRED_PRODUCTS)
    def test_required_product_exists(self, taxonomy, product_key):
        assert product_key in taxonomy["products"]


class TestPlatforms:
    REQUIRED_PLATFORMS = [
        "python", "net", "java", "cpp", "rust",
    ]

    @pytest.mark.parametrize("platform_key", REQUIRED_PLATFORMS)
    def test_required_platform_exists(self, taxonomy, platform_key):
        assert platform_key in taxonomy["platforms"]


# --------------------------------------------------------------------------- #
# Posting Modes
# --------------------------------------------------------------------------- #


class TestPostingModes:
    def test_dry_run_default(self, taxonomy):
        assert taxonomy["posting_modes"]["dry_run_default"] is True

    def test_test_mode_job_type(self, taxonomy):
        assert taxonomy["posting_modes"]["test_mode_job_type"] == "test"

    def test_test_mode_item_prefix(self, taxonomy):
        assert taxonomy["posting_modes"]["test_mode_item_prefix"] == "[TEST] "

    def test_max_test_rows(self, taxonomy):
        assert taxonomy["posting_modes"]["max_test_rows_per_sprint"] == 2

    def test_hard_test_row_limit(self, taxonomy):
        assert taxonomy["posting_modes"]["hard_test_row_limit"] == 3

    def test_production_requires_approval(self, taxonomy):
        assert taxonomy["posting_modes"]["production_requires_owner_approval"] is True


# --------------------------------------------------------------------------- #
# Boundary Exclusions
# --------------------------------------------------------------------------- #


class TestBoundaries:
    BOUNDARY_SYSTEMS = ["gemini", "ollama", "m2m100"]

    @pytest.mark.parametrize("system", BOUNDARY_SYSTEMS)
    def test_boundary_excluded_from_token_usage(self, taxonomy, system):
        entry = taxonomy["non_professionalize_boundaries"][system]
        assert entry["excluded_from_token_usage"] is True

    @pytest.mark.parametrize("system", BOUNDARY_SYSTEMS)
    def test_boundary_excluded_from_api_calls_count(self, taxonomy, system):
        entry = taxonomy["non_professionalize_boundaries"][system]
        assert entry["excluded_from_api_calls_count"] is True

    @pytest.mark.parametrize("system", BOUNDARY_SYSTEMS)
    def test_boundary_migration_out_of_scope(self, taxonomy, system):
        entry = taxonomy["non_professionalize_boundaries"][system]
        assert entry["migration_out_of_scope"] is True


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
    def test_no_secrets_in_taxonomy(self):
        text = _TAXONOMY_PATH.read_text()
        assert _SECRET_PATTERN.search(text) is None, "Taxonomy contains secret-like values"
