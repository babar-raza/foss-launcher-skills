"""Tests for cleanroom_scope.py — TC-S96-004."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIB_DIR = str(_REPO_ROOT / "scripts" / "pipeline" / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from cleanroom_scope import resolve, resolve_file_subdomain, VALID_SUBDOMAINS


# ---------------------------------------------------------------------------
# Basic resolution
# ---------------------------------------------------------------------------

def test_cells_java_reference_resolves_content_root():
    m = resolve("cells", "java", ["reference"])
    assert m.is_valid
    assert "reference" in m.content_roots
    assert "cells/java" in m.content_roots["reference"].replace("\\", "/")


def test_cells_java_reference_has_script_generator():
    m = resolve("cells", "java", ["reference"])
    assert m.is_valid
    gen = m.generation_entry_points["reference"]
    assert gen["type"] == "script"
    assert "batch_reference.py" in gen["command"]


def test_cells_java_reference_resolves_knowledge_paths():
    m = resolve("cells", "java", ["reference"])
    assert m.knowledge_model_path is not None
    assert "cells/java" in m.knowledge_model_path.replace("\\", "/")
    assert m.claims_path is not None
    assert m.api_surface_path is not None


def test_cells_java_blog_resolves_blog_directory_root():
    m = resolve("cells", "java", ["blog"])
    assert m.is_valid
    # Blog must NOT contain /en/ in path
    blog_root = m.content_roots["blog"].replace("\\", "/")
    assert "/en/" not in blog_root
    assert "blog.aspose.org" in blog_root
    assert "cells/java" in blog_root


def test_blog_path_never_contains_en_prefix():
    m = resolve("cells", "java", ["blog"])
    blog_root = m.content_roots["blog"].replace("\\", "/")
    assert "/en/" not in blog_root, f"Blog root must not contain /en/: {blog_root}"


def test_cells_java_products_resolves_to_products_directory():
    m = resolve("cells", "java", ["products"])
    assert m.is_valid
    products_root = m.content_roots["products"].replace("\\", "/")
    assert "products.aspose.org" in products_root
    assert "cells/java" in products_root


def test_cells_java_all_subdomains_resolves_five():
    m = resolve("cells", "java")
    assert m.is_valid
    assert len(m.subdomains) == 5
    for sub in VALID_SUBDOMAINS:
        assert sub in m.content_roots


def test_unknown_family_returns_structured_error():
    m = resolve("nonexistent_family_xyz", "java", ["reference"])
    assert not m.is_valid
    assert any("Unknown family" in e for e in m._errors)


def test_single_file_inside_scope_accepted():
    m = resolve(
        "cells", "java", ["reference"],
        file_path="content/reference.aspose.org/en/cells/java/Workbook.md"
    )
    assert m.is_valid, f"Expected valid scope; errors: {m._errors}"
    assert len(m.files) == 1


def test_single_file_outside_scope_rejected():
    m = resolve(
        "cells", "java", ["reference"],
        file_path="content/docs.aspose.org/en/cells/java/features.md"
    )
    assert not m.is_valid
    assert any("outside declared scope" in e for e in m._errors)


def test_blog_generator_is_agent_type():
    m = resolve("cells", "java", ["blog"])
    gen = m.generation_entry_points["blog"]
    assert gen["type"] == "agent"
    assert gen["skill"] == "S-57"


def test_docs_generator_is_agent_type():
    m = resolve("cells", "java", ["docs"])
    gen = m.generation_entry_points["docs"]
    assert gen["type"] == "agent"
    assert gen["skill"] == "S-56"


def test_kb_generator_is_agent_type():
    m = resolve("cells", "java", ["kb"])
    gen = m.generation_entry_points["kb"]
    assert gen["type"] == "agent"
    assert gen["skill"] == "S-58"


def test_products_generator_is_agent_type():
    m = resolve("cells", "java", ["products"])
    gen = m.generation_entry_points["products"]
    assert gen["type"] == "agent"
    assert gen["skill"] == "S-61"


def test_to_dict_is_json_serializable():
    import json
    m = resolve("cells", "java", ["reference"])
    d = m.to_dict()
    # Must not raise
    json.dumps(d)


def test_resolve_file_subdomain_reference():
    sub = resolve_file_subdomain(
        "content/reference.aspose.org/en/cells/java/Workbook.md",
        "cells", "java"
    )
    assert sub == "reference"


def test_resolve_file_subdomain_unknown():
    sub = resolve_file_subdomain(
        "scripts/pipeline/lib/cleanroom_scope.py",
        "cells", "java"
    )
    assert sub is None
