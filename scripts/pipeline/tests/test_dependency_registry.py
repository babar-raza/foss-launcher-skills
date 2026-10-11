"""Tests for dependency_registry.py — Phase 1 (TC-PROD-002A + TC-PROD-002B).

Covers:
  test_unknown_surface_raises_error
  test_empty_fingerprints_required_raises_error
  test_loader_produces_typed_entries
  test_all_five_surfaces_have_entries
  test_no_entry_has_backing_generator_when_validate_only
  test_unsupported_surfaces_have_status_set
  test_load_registry_validates_on_load
  test_products_content_root_uses_family_not_platform
  test_blog_content_root_has_no_en_prefix
  test_blog_config_is_yaml_not_toml
  test_reference_has_backing_generator
  test_registry_schema_structure_valid
  test_registry_instance_validates_against_schema
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# conftest.py adds scripts/pipeline/lib/ to sys.path
from dependency_registry import (
    DependencyRegistry,
    RegistryValidationError,
    SurfaceEntry,
    UnknownSurfaceError,
    get_surface,
    load_registry,
    validate_registry,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY_PATH = _REPO_ROOT / "data" / "refresh-dependencies.json"


def _minimal_registry() -> dict:
    return {
        "reference": {
            "description": "API reference pages",
            "backing_generator": "scripts/pipeline/commands/content/batch_reference.py",
            "backing_skill": "S-62",
            "fingerprints_required": ["upstream_repo_sha", "local_knowledge_sha"],
            "template_paths": ["themes/docs/layouts"],
            "config_path": "configs/reference.aspose.org.toml",
            "content_root": "content/reference.aspose.org/en/{family}/{platform}",
            "expected_output_source": "registry_rules",
            "regeneration_triggers": ["upstream_repo_sha"],
            "reconciliation_triggers": ["output_missing"],
            "triage_checker": "triage_confirm.triage_confirm",
            "supports_targeted_run": True,
            "status": "supported",
        }
    }


# ---------------------------------------------------------------------------
# UnknownSurfaceError tests
# ---------------------------------------------------------------------------

def test_unknown_surface_raises_error():
    """get_surface() raises UnknownSurfaceError for unregistered surface names."""
    registry = DependencyRegistry(_minimal_registry())
    with pytest.raises(UnknownSurfaceError) as exc_info:
        registry.get_surface("nonexistent_surface")

    err = exc_info.value
    assert err.surface_name == "nonexistent_surface"
    assert "reference" in err.known


def test_unknown_surface_error_message_includes_known_surfaces():
    """UnknownSurfaceError message lists known surfaces for debugging."""
    registry = DependencyRegistry(_minimal_registry())
    with pytest.raises(UnknownSurfaceError, match="reference"):
        registry.get_surface("blog")


# ---------------------------------------------------------------------------
# validate_registry tests
# ---------------------------------------------------------------------------

def test_empty_fingerprints_required_raises_error():
    """validate_registry() reports error when fingerprints_required is empty."""
    data = _minimal_registry()
    data["reference"]["fingerprints_required"] = []
    errors = validate_registry(data)
    assert any("fingerprints_required" in e for e in errors)


def test_invalid_status_raises_error():
    """validate_registry() reports error for invalid status value."""
    data = _minimal_registry()
    data["reference"]["status"] = "INVALID_STATUS"
    errors = validate_registry(data)
    assert any("status" in e for e in errors)


def test_validate_only_with_backing_generator_raises_error():
    """validate_registry() reports error when validate_only surface claims a generator."""
    data = _minimal_registry()
    data["reference"]["status"] = "validate_only"
    # backing_generator is set -- this should be an error for validate_only
    errors = validate_registry(data)
    assert any("backing_generator" in e or "agent-executed" in e for e in errors)


def test_valid_registry_returns_no_errors():
    """validate_registry() returns empty list for a well-formed registry."""
    errors = validate_registry(_minimal_registry())
    assert errors == []


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------

def test_loader_produces_typed_entries():
    """load_registry() returns a DependencyRegistry with typed SurfaceEntry objects."""
    import tempfile
    import json
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(_minimal_registry(), f)
        tmp_path = f.name

    try:
        registry = load_registry(tmp_path)
        assert isinstance(registry, DependencyRegistry)
        surface = registry.get_surface("reference")
        assert isinstance(surface, SurfaceEntry)
        assert surface.name == "reference"
        assert surface.is_script_backed is True
        assert surface.status == "supported"
    finally:
        import os
        os.unlink(tmp_path)


def test_load_registry_validates_on_load():
    """load_registry() raises RegistryValidationError for an invalid registry."""
    import tempfile
    import json
    bad_data = {"reference": {"description": "no other required keys"}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(bad_data, f)
        tmp_path = f.name

    try:
        with pytest.raises(RegistryValidationError):
            load_registry(tmp_path)
    finally:
        import os
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Production registry tests (data/refresh-dependencies.json)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _REGISTRY_PATH.exists(),
    reason="data/refresh-dependencies.json not found"
)
def test_all_five_surfaces_have_entries():
    """The production registry contains all 5 required surface entries."""
    registry = load_registry(_REGISTRY_PATH)
    required = {"reference", "products", "docs", "blog", "kb"}
    registered = set(registry.surface_names())
    assert required.issubset(registered), (
        f"Missing surfaces: {required - registered}"
    )


@pytest.mark.skipif(
    not _REGISTRY_PATH.exists(),
    reason="data/refresh-dependencies.json not found"
)
def test_no_entry_has_backing_generator_when_validate_only():
    """validate_only surfaces in the production registry have no backing_generator."""
    registry = load_registry(_REGISTRY_PATH)
    for name in registry.surface_names():
        surface = registry.get_surface(name)
        if surface.status == "validate_only":
            assert surface.backing_generator is None, (
                f"Surface {name!r} is validate_only but has backing_generator="
                f"{surface.backing_generator!r}"
            )


@pytest.mark.skipif(
    not _REGISTRY_PATH.exists(),
    reason="data/refresh-dependencies.json not found"
)
def test_reference_has_backing_generator():
    """The reference surface has a script-backed generator."""
    registry = load_registry(_REGISTRY_PATH)
    ref = registry.get_surface("reference")
    assert ref.backing_generator is not None
    assert "batch_reference.py" in ref.backing_generator
    assert ref.is_script_backed is True


@pytest.mark.skipif(
    not _REGISTRY_PATH.exists(),
    reason="data/refresh-dependencies.json not found"
)
def test_products_content_root_uses_family_not_platform():
    """Products content root must be at family level, not family/platform.

    Phase 0 verified: actual products pages are at content/products.aspose.org/en/{family}
    NOT content/products.aspose.org/en/{family}/{platform}.
    This test guards against the stale site_planner.py SITE_PATHS value being used.
    """
    registry = load_registry(_REGISTRY_PATH)
    products = registry.get_surface("products")
    root = products.content_root
    # Must contain {family}
    assert "{family}" in root
    # Must NOT contain {platform}
    assert "{platform}" not in root, (
        f"Products content_root incorrectly includes {{platform}}: {root!r}. "
        "Phase 0 verified that products pages are at family level only."
    )


@pytest.mark.skipif(
    not _REGISTRY_PATH.exists(),
    reason="data/refresh-dependencies.json not found"
)
def test_blog_content_root_has_no_en_prefix():
    """Blog content root must NOT contain /en/ — Phase 0 verified this anomaly."""
    registry = load_registry(_REGISTRY_PATH)
    blog = registry.get_surface("blog")
    assert "/en/" not in blog.content_root, (
        f"Blog content_root incorrectly includes /en/: {blog.content_root!r}. "
        "Phase 0 verified that blog uses content/blog.aspose.org/{{family}}/{{platform}} "
        "(no /en/ prefix, unlike other subdomains)."
    )


@pytest.mark.skipif(
    not _REGISTRY_PATH.exists(),
    reason="data/refresh-dependencies.json not found"
)
def test_blog_config_is_yaml_not_toml():
    """Blog config must be .yml, not .toml — Phase 0 verified this anomaly."""
    registry = load_registry(_REGISTRY_PATH)
    blog = registry.get_surface("blog")
    assert blog.config_path is not None
    assert blog.config_path.endswith(".yml"), (
        f"Blog config_path should end in .yml: {blog.config_path!r}. "
        "Phase 0 verified: configs/blog.aspose.org.yml (unique YAML config)."
    )


@pytest.mark.skipif(
    not _REGISTRY_PATH.exists(),
    reason="data/refresh-dependencies.json not found"
)
def test_unsupported_surfaces_have_status_set():
    """All surfaces have a recognised status (no None or missing status)."""
    registry = load_registry(_REGISTRY_PATH)
    valid_statuses = {"supported", "validate_only", "unsupported"}
    for name in registry.surface_names():
        surface = registry.get_surface(name)
        assert surface.status in valid_statuses, (
            f"Surface {name!r} has unrecognised status: {surface.status!r}"
        )


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

def test_registry_schema_structure_valid():
    """The dependency registry JSON schema is itself structurally valid."""
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema_path = _REPO_ROOT / "data" / "schemas" / "dependency-registry-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)


@pytest.mark.skipif(
    not _REGISTRY_PATH.exists(),
    reason="data/refresh-dependencies.json not found"
)
def test_registry_instance_validates_against_schema():
    """The production registry file validates against the dependency registry schema."""
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema_path = _REPO_ROOT / "data" / "schemas" / "dependency-registry-schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    instance = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance, schema)
