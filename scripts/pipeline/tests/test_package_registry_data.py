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
    naming_convention_candidate,
    naming_convention_owner,
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
    same 4 Java-FOSS families + cells/rust, plus words/net (TC-MT015-07)."""
    data = _load()
    families = {k for k in data if not k.startswith("_")}
    assert families == {"cells", "3d", "pdf", "slides", "words"}
    assert set(data["cells"].keys()) == {"java", "rust"}


def test_words_net_uses_naming_convention_fallback_and_is_unpublished():
    """Regression pin (TC-MT015-07): words/net is this mission's own worked
    example -- a product launched on aspose.org before its NuGet package
    exists. Its candidate must come from the naming-convention fallback
    (package_manifest.py has nothing to extract from the real .csproj), and
    it must honestly reflect the currently-true unpublished state, matching
    the live content across all 4 subdomains."""
    data = _load()
    entry = data["words"]["net"]
    assert entry["registry_type"] == "nuget"
    assert entry["candidate"]["name"] == "Aspose.Words.FOSS"
    assert entry["scout_source"] == "naming-convention-fallback"
    assert entry["verification"]["published"] is False
    assert entry["owner_match"] is None


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


def test_unchecked_entry_implies_verified_at_is_null():
    """A published:false entry with method:null (no live check ever performed --
    e.g. a pure naming-convention guess) must not carry a fabricated verified_at.
    A published:false entry WITH a method set (a live check was actually performed
    and confirmed the package is not published -- e.g. slides/net's 4-point NuGet
    verification) legitimately carries a real verified_at: that timestamp records
    when the check ran, not that the package is live. Conflating "never checked"
    with "checked and confirmed absent" would make the schema unable to represent
    genuine negative verification, which is exactly the kind of rigor this field
    exists to capture."""
    data = _load()
    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            v = entry["verification"]
            if not v["published"] and v["method"] is None:
                assert v["verified_at"] is None, (
                    f"{family}/{platform}: no live check performed (method is null) "
                    "but verified_at is set"
                )


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


def test_slides_net_is_confirmed_not_published():
    """slides/net (TC-MT015-06, 2026-08-01): a real, live 4-point verification
    (nuget.org v3-flatcontainer 404 across 4 name variants, nuget.org search API,
    real .csproj has no PackageId/Version, CI workflow has no publish/pack step)
    confirmed Aspose.Slides.Foss has never been published to NuGet. Unlike words/net
    (a pure naming-convention guess, never live-checked), this entry legitimately
    carries a non-null verified_at and method -- a live check WAS performed, it just
    confirmed absence rather than presence. See test_unchecked_entry_implies_verified_at_is_null
    for why that distinction matters."""
    data = _load()
    entry = data["slides"]["net"]
    v = entry["verification"]
    assert entry["registry_type"] == "nuget"
    assert entry["candidate"]["name"] == "Aspose.Slides.Foss"
    assert v["published"] is False
    assert v["verified_at"] is not None
    assert v["method"] == "nuget-api-v3-live-check"


def test_cells_3d_pdf_use_org_aspose_groupid():
    """Regression pin carried forward from foss_packages.json: org.aspose is
    the real, live-verified Maven Central groupId for these 3 families."""
    data = _load()
    for family in ("cells", "3d", "pdf"):
        entry = data[family]["java"]
        assert entry["candidate"]["group_id"] == "org.aspose"


# ---------------------------------------------------------------------------
# TC-MT015-07: naming-convention candidate fallback
# ---------------------------------------------------------------------------

class TestNamingConventionCandidate:
    def test_pypi_flat_name(self):
        assert naming_convention_candidate("pdf", "python", "pypi") == {"name": "aspose-pdf-foss"}

    def test_nuget_net_title_case(self):
        assert naming_convention_candidate("words", "net", "nuget") == {"name": "Aspose.Words.FOSS"}

    def test_nuget_cpp_distinct_from_net(self):
        """Regression pin for the user's own worked example: C++ ships via NuGet
        under its own package ID, distinct from the .NET package."""
        cpp = naming_convention_candidate("pdf", "cpp", "nuget")
        net = naming_convention_candidate("pdf", "net", "nuget")
        assert cpp == {"name": "Aspose.PDF.Cpp.FOSS"}
        assert net == {"name": "Aspose.PDF.FOSS"}
        assert cpp != net

    def test_nuget_acronym_family_stays_uppercase(self):
        assert naming_convention_candidate("3d", "net", "nuget") == {"name": "Aspose.3D.FOSS"}

    def test_nuget_non_acronym_family_is_title_cased(self):
        assert naming_convention_candidate("slides", "net", "nuget") == {"name": "Aspose.Slides.FOSS"}

    def test_npm_scoped_name(self):
        assert naming_convention_candidate("pdf", "typescript", "npm") == {"name": "@asposefoss/pdf"}

    def test_go_module_path(self):
        assert naming_convention_candidate("pdf", "go", "go_modules") == {
            "module_path": "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"
        }

    def test_cargo_flat_name(self):
        assert naming_convention_candidate("cells", "rust", "cargo") == {"name": "aspose-cells-foss"}

    def test_maven_returns_none(self):
        """No convention fallback for Maven -- a real pom.xml groupId/artifactId
        almost always exists; guessing here would be worse than the empty
        field it would replace."""
        assert naming_convention_candidate("pdf", "java", "maven") is None

    def test_unknown_registry_type_returns_none(self):
        assert naming_convention_candidate("pdf", "net", "vcpkg") is None

    def test_result_shape_is_schema_valid_for_each_registry_type(self):
        """Every non-None result must satisfy validate_package_entry's candidate
        shape requirement for its registry_type -- a guessed candidate must be
        just as structurally valid as an extracted one."""
        cases = [
            ("pdf", "python", "pypi"), ("pdf", "net", "nuget"), ("pdf", "cpp", "nuget"),
            ("pdf", "typescript", "npm"), ("pdf", "go", "go_modules"), ("cells", "rust", "cargo"),
        ]
        for family, platform, registry_type in cases:
            candidate = naming_convention_candidate(family, platform, registry_type)
            entry = {
                "registry_type": registry_type, "candidate": candidate,
                "candidate_owner": naming_convention_owner(registry_type, family=family),
                "verification": {"published": False, "verified_at": None, "verified_owner": None,
                                  "evidence_url": None, "method": None},
                "owner_match": None,
            }
            errors = validate_package_entry(entry, f"{family}.{platform}")
            assert errors == [], f"{family}/{platform} ({registry_type}): {errors}"


class TestNamingConventionOwner:
    def test_maven_owner(self):
        assert naming_convention_owner("maven") == "org.aspose"

    def test_go_owner_is_per_family_org(self):
        assert naming_convention_owner("go_modules", family="pdf") == "aspose-pdf-foss"

    def test_go_owner_without_family_is_none(self):
        assert naming_convention_owner("go_modules") is None

    def test_pypi_nuget_npm_cargo_owner_is_asposefoss(self):
        for registry_type in ("pypi", "nuget", "npm", "cargo"):
            assert naming_convention_owner(registry_type) == "asposefoss"

    def test_unknown_registry_type_returns_none(self):
        assert naming_convention_owner("vcpkg") is None


def test_slides_java_candidate_matches_live_verified_coordinate():
    """Regression pin: TC-MT015-02's first migration draft copied slides/java's
    *scouted* (provisional) coordinate (org.aspose.slides.foss:1.0.0) into
    `candidate` instead of the real, live-verified *confirmed* one
    (org.aspose:26.7.0, per TC-MT008-09) -- caught only by a real Hugo build
    byte-parity check against the old foss_packages.json-backed shortcode
    output, not by any shape test. This pins the correct value so the same
    scouted/confirmed mix-up can't silently regress again."""
    data = _load()
    entry = data["slides"]["java"]
    assert entry["candidate"]["group_id"] == "org.aspose"
    assert entry["candidate"]["artifact_id"] == "aspose-slides-foss"
    assert entry["candidate"]["version"] == "26.7.0"
