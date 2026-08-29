"""Tests for lib/product_registry.py (Mission MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH,
TC-MT040-46).

Covers: load_products()/get_product() exclusion semantics (mirroring
update_product_registry.py's own _is_excluded() matching), and
get_package_name()'s priority order (published registry candidate > unpublished
registry candidate > naming-convention guess > None). All fixtures go through
the configure() seam and tmp_path -- no monkeypatch.setattr on internals.
"""

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib import product_registry as sut


@pytest.fixture(autouse=True)
def isolate_paths():
    """Each test gets fresh, unset paths -- reset to real-repo defaults after."""
    yield
    sut.configure(products_path=None, exclusions_path=None, package_registry_path=None)


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# load_products() / get_product() -- exclusion semantics
# ---------------------------------------------------------------------------

def test_load_products_returns_all_entries_when_nothing_excluded(tmp_path):
    products_path = tmp_path / "products.json"
    exclusions_path = tmp_path / "registry_exclusions.json"
    _write_json(products_path, [
        {"family": "cells", "platform": "python", "repo_name": "Aspose.Cells-FOSS-for-Python", "active": True},
        {"family": "cells", "platform": "net", "repo_name": "Aspose.Cells-FOSS-for-.NET", "active": True},
    ])
    _write_json(exclusions_path, [])
    sut.configure(products_path=products_path, exclusions_path=exclusions_path)

    products = sut.load_products()
    assert len(products) == 2


def test_load_products_omits_family_platform_excluded_entry(tmp_path):
    """Mirrors the real cells/typescript case: products.json still says
    active: true, but registry_exclusions.json's family_platform match
    excludes it -- the loader must independently apply that exclusion,
    not just trust products.json's own active flag."""
    products_path = tmp_path / "products.json"
    exclusions_path = tmp_path / "registry_exclusions.json"
    _write_json(products_path, [
        {"family": "cells", "platform": "typescript", "repo_name": "Aspose.Cells-FOSS-for-TypeScript", "active": True},
        {"family": "cells", "platform": "python", "repo_name": "Aspose.Cells-FOSS-for-Python", "active": True},
    ])
    _write_json(exclusions_path, [
        {"match": "family_platform", "family": "cells", "platform": "typescript", "reason": "test exclusion"},
    ])
    sut.configure(products_path=products_path, exclusions_path=exclusions_path)

    products = sut.load_products()
    assert len(products) == 1
    assert products[0]["platform"] == "python"

    assert sut.get_product("cells", "typescript") is None
    assert sut.get_product("cells", "python") is not None


def test_load_products_omits_repo_name_excluded_entry_case_insensitive(tmp_path):
    products_path = tmp_path / "products.json"
    exclusions_path = tmp_path / "registry_exclusions.json"
    _write_json(products_path, [
        {"family": "slides", "platform": "net", "repo_name": ".GitHub", "active": True},
    ])
    _write_json(exclusions_path, [
        {"match": "repo_name", "value": ".github", "reason": "org profile repo"},
    ])
    sut.configure(products_path=products_path, exclusions_path=exclusions_path)

    assert sut.load_products() == []


def test_apply_exclusions_false_returns_raw_list(tmp_path):
    products_path = tmp_path / "products.json"
    exclusions_path = tmp_path / "registry_exclusions.json"
    _write_json(products_path, [
        {"family": "cells", "platform": "typescript", "repo_name": "Aspose.Cells-FOSS-for-TypeScript", "active": True},
    ])
    _write_json(exclusions_path, [
        {"match": "family_platform", "family": "cells", "platform": "typescript", "reason": "test exclusion"},
    ])
    sut.configure(products_path=products_path, exclusions_path=exclusions_path)

    assert len(sut.load_products(apply_exclusions=False)) == 1
    assert sut.get_product("cells", "typescript", apply_exclusions=False) is not None


def test_get_product_missing_returns_none(tmp_path):
    products_path = tmp_path / "products.json"
    _write_json(products_path, [])
    sut.configure(products_path=products_path)
    assert sut.get_product("nonexistent", "python") is None


def test_load_products_missing_file_degrades_to_empty_list(tmp_path):
    sut.configure(products_path=tmp_path / "does-not-exist.json")
    assert sut.load_products() == []


# ---------------------------------------------------------------------------
# get_package_name()
# ---------------------------------------------------------------------------

def test_get_package_name_prefers_published_registry_candidate(tmp_path):
    registry_path = tmp_path / "package_registry.json"
    _write_json(registry_path, {
        "cells": {"typescript": {
            "registry_type": "npm",
            "candidate": {"name": "@asposefoss/cells", "version": "1.0.0"},
            "verification": {"published": True},
        }}
    })
    sut.configure(package_registry_path=registry_path)
    assert sut.get_package_name("cells", "typescript", "npm") == "@asposefoss/cells"


def test_get_package_name_prefers_unpublished_registry_candidate_over_convention_guess(tmp_path):
    """The real cells/typescript case: the registry's own scouted candidate
    name ("excel-cells") is more truthful than a fresh
    naming_convention_candidate() guess ("@asposefoss/cells"), even though
    the registry entry is unpublished."""
    registry_path = tmp_path / "package_registry.json"
    _write_json(registry_path, {
        "cells": {"typescript": {
            "registry_type": "npm",
            "candidate": {"name": "excel-cells"},
            "verification": {"published": False},
        }}
    })
    sut.configure(package_registry_path=registry_path)
    assert sut.get_package_name("cells", "typescript", "npm") == "excel-cells"


def test_get_package_name_falls_back_to_naming_convention_when_no_entry(tmp_path):
    registry_path = tmp_path / "package_registry.json"
    _write_json(registry_path, {})
    sut.configure(package_registry_path=registry_path)
    assert sut.get_package_name("widgets", "typescript", "npm") == "@asposefoss/widgets"


def test_get_package_name_returns_none_when_registry_missing_and_no_convention(tmp_path):
    # go_modules IS covered by naming_convention_candidate; use a
    # registry_type naming_convention_candidate() doesn't support (maven has
    # no npm/pypi/etc-style fallback path -- it returns None per its own
    # docstring) to reach the true "nothing at all" case.
    sut.configure(package_registry_path=tmp_path / "does-not-exist.json")
    assert sut.get_package_name("widgets", "java", "maven") is None


def test_get_package_name_registry_type_mismatch_falls_through(tmp_path):
    """An entry exists for this family/platform but under a DIFFERENT
    registry_type than requested -- must not be trusted; falls through to
    the naming-convention guess instead."""
    registry_path = tmp_path / "package_registry.json"
    _write_json(registry_path, {
        "cells": {"typescript": {
            "registry_type": "npm",
            "candidate": {"name": "excel-cells"},
            "verification": {"published": False},
        }}
    })
    sut.configure(package_registry_path=registry_path)
    assert sut.get_package_name("cells", "typescript", "pypi") == "aspose-cells-foss"
