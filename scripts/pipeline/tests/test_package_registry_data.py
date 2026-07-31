"""
Tests for data/package_registry.json (Mission MT015-2026-07-30-PACKAGE-REGISTRY,
TC-MT015-01).

Unified single source of truth for FOSS package-manager identity, replacing
the split data/foss_packages.json (Maven-only) + data/cargo_packages.json
(Cargo-only) files. See data/schemas/package-registry-schema.json for the
full schema and scripts/pipeline/lib/package_registry_data.py for the
hand-written validator (this repo has no `jsonschema` package installed --
confirmed this session -- so validation is Python, matching the existing
dependency_registry.py::validate_registry convention, not a generic
JSON-Schema library).

These tests validate the data file's shape and known-fact invariants only.
Shortcode-render behaviour is out of scope here -- the shortcodes are not
yet repointed at this file (TC-MT015-02, pending Hugo build byte-parity
proof); data/foss_packages.json and data/cargo_packages.json remain the live
rendering path until then.
"""

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_PATH = _REPO_ROOT / "data" / "package_registry.json"
_LIB_DIR = _REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from package_registry_data import (  # noqa: E402
    REGISTRY_TYPES,
    validate_package_entry,
    validate_package_registry,
)


def _load():
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def test_file_exists_and_is_valid_json():
    assert _DATA_PATH.is_file(), f"{_DATA_PATH} must exist"
    _load()  # raises on invalid JSON


def test_schema_file_exists():
    schema_path = _REPO_ROOT / "data" / "schemas" / "package-registry-schema.json"
    assert schema_path.is_file(), f"{schema_path} must exist"
    json.loads(schema_path.read_text(encoding="utf-8"))  # raises on invalid JSON


def test_validate_package_registry_reports_no_errors():
    data = _load()
    errors = validate_package_registry(data)
    assert errors == [], f"Schema validation errors: {errors}"


def test_migrated_families_present():
    """Migration from foss_packages.json/cargo_packages.json is like-for-like:
    same 4 Java-FOSS families + cells/rust, nothing added or dropped."""
    data = _load()
    families = {k for k in data if not k.startswith("_")}
    assert families == {"cells", "3d", "pdf", "slides"}
    assert set(data["cells"].keys()) == {"java", "rust"}


def test_registry_type_never_vcpkg_or_conan():
    """Regression pin: vcpkg/Conan were confirmed never implemented in practice
    (C++ ships via NuGet under its own package ID) -- must never appear here."""
    data = _load()
    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            assert entry["registry_type"] in REGISTRY_TYPES
            assert entry["registry_type"] not in {"vcpkg", "conan"}


def test_every_entry_individually_valid():
    data = _load()
    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            errors = validate_package_entry(entry, f"{family}.{platform}")
            assert errors == [], f"{family}/{platform}: {errors}"


def test_published_true_implies_verified_at_and_evidence_populated():
    """A published:true entry must carry real evidence -- the invariant a future
    shortcode's render-vs-errorf branch will depend on, mirroring the old
    foss_packages.json published<->confirmed invariant."""
    data = _load()
    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            v = entry["verification"]
            if v["published"]:
                assert v["verified_at"] is not None, f"{family}/{platform}: published but verified_at is null"
                assert v["evidence_url"], f"{family}/{platform}: published but no evidence_url"


def test_published_false_implies_verified_at_is_null():
    data = _load()
    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            v = entry["verification"]
            if not v["published"]:
                assert v["verified_at"] is None, f"{family}/{platform}: not published but verified_at is set"


def test_owner_match_honestly_null_for_migrated_entries():
    """Root cause 5 (no owner-verification field existed in the source files):
    this migration must not fabricate a verified owner_match value it never
    actually checked -- every migrated entry must carry owner_match: null,
    not a guessed True."""
    data = _load()
    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            assert entry["owner_match"] is None, (
                f"{family}/{platform}: owner_match should still be null (unverified) "
                f"post-migration, got {entry['owner_match']!r}"
            )


def test_slides_java_is_published():
    """Matches the CURRENT foss_packages.json state (TC-MT008-09 resolved
    2026-07-27): slides/java is live on Maven Central. (The older
    test_foss_packages_data.py::test_slides_is_not_published pins the
    pre-resolution state and is now stale against current data -- not this
    migration's file to fix.)"""
    data = _load()
    assert data["slides"]["java"]["verification"]["published"] is True


def test_cells_3d_pdf_use_org_aspose_groupid():
    """Regression pin carried forward from foss_packages.json: org.aspose is
    the real, live-verified Maven Central groupId for these 3 families."""
    data = _load()
    for family in ("cells", "3d", "pdf"):
        entry = data[family]["java"]
        assert entry["candidate"]["group_id"] == "org.aspose"
