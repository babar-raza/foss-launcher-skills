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
    set_content_healing_status,
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
    same 4 Java-FOSS families + cells/rust, plus words/net (TC-MT015-07) --
    this was the state BEFORE TC-MT018-06's full backfill. As of
    2026-08-01, the registry covers all 31 launched family/platform pairs
    (Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE) -- assert the
    original 5 migrated families are still present as a subset, not that
    they're the only families (that assumption is what this pin originally
    checked and is now intentionally superseded)."""
    data = _load()
    families = {k for k in data if not k.startswith("_")}
    assert {"cells", "3d", "pdf", "slides", "words"}.issubset(families)
    assert {"java", "rust"}.issubset(set(data["cells"].keys()))


def test_all_31_launched_products_are_registered():
    """Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-06: the
    full backfill closed the coverage gap MT015 left open (only 7 of 31
    launched products were ever registered). Pin the complete, correct
    state so a future regression (e.g. someone reverting the backfill) is
    caught immediately.

    Updated 2026-08-29 (MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH TC-MT040-24):
    31 -> 32. pdf/typescript's package identity was backfilled into this
    registry AHEAD of its own site launch (still in progress in that
    mission) -- this file legitimately tracks package identity for a
    product before it is fully launched, the same way words/net's own entry
    below predates that product's real NuGet publish. The test's name keeps
    saying "31" for history/traceability; the assertion is the real,
    current, honest count.
    """
    # Re-derived 2026-09-18 (33 entries by then, so the hardcoded 32 above had
    # rotted a third time -- 31 -> 32 -> 33, each a manual bump after a real
    # product was added, each bump leaving this test red in between). The
    # guarantee this test exists for is COVERAGE, not a number: every product
    # the repo knows about (data/products.json) has a registry identity entry.
    # Derive the expectation from that source of truth so adding a product can
    # never make this test stale; registry entries may still lead products.json
    # (identity backfilled ahead of a launch, see the note above), so the check
    # is one-directional.
    data = _load()
    registered = {(family, platform) for family, platforms in data.items() if not family.startswith("_") for platform in platforms}
    products = json.loads((_REPO_ROOT / "data" / "products.json").read_text(encoding="utf-8"))
    known_products = {(p["family"], p["platform"]) for p in products}
    assert known_products, "data/products.json unexpectedly empty -- the coverage check would pass vacuously"
    assert known_products - registered == set(), (
        f"products known to data/products.json with no package_registry.json entry: "
        f"{sorted(known_products - registered)}"
    )


def test_words_net_uses_naming_convention_fallback_and_is_now_published():
    """Regression pin (TC-MT015-07, updated 2026-09-09 -- pre-existing stale
    test found and fixed while working an unrelated Phase-1 taskcard under
    Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION): words/net was
    originally this mission's own worked example of a product launched on
    aspose.org before its NuGet package existed. It has since actually been
    published for real (commit 5a62662be3, 2026-09-04: package-publish-watch
    confirmed Aspose.Words.FOSS live on NuGet, 26.2.0/26.3.0) -- this test
    asserted the old, now-false 'still unpublished' state and would have
    stayed silently wrong indefinitely. The naming-convention-fallback
    candidate itself is still correct (that's how the identity was
    originally sourced, before any live check existed) and owner_match is
    still honestly null (no owner-match check has run, independent of the
    publish check that did)."""
    data = _load()
    entry = data["words"]["net"]
    assert entry["registry_type"] == "nuget"
    assert entry["candidate"]["name"] == "Aspose.Words.FOSS"
    assert entry["scout_source"] == "naming-convention-fallback"
    assert entry["verification"]["published"] is True
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


def test_slides_net_identity_and_verification_are_coherent():
    """slides/net (TC-MT015-06, 2026-08-01): originally a real, live 4-point
    verification (nuget.org v3-flatcontainer 404 across 4 name variants, search
    API, .csproj without PackageId/Version, CI without a pack step) confirmed
    Aspose.Slides.Foss had never been published to NuGet, and this test pinned
    `published is False` + method `nuget-api-v3-live-check`.

    Rewritten 2026-09-18: that pin asserted a point-in-time fact about an
    external registry, so it went red the moment the package was really
    published (package-publish-watch flipped it 2026-09-13; NuGet serves
    26.9.0). A test that fails BECAUSE the world improved is a broken
    regression control -- it trains everyone to ignore red. Pin what is stable
    (the identity that was hand-verified) and the invariant that must hold in
    EITHER state (a live check was performed, so verified_at/method are
    recorded; a published entry carries the evidence URL that justifies it).
    See test_unchecked_entry_implies_verified_at_is_null for why the
    verified_at distinction matters."""
    data = _load()
    entry = data["slides"]["net"]
    v = entry["verification"]
    assert entry["registry_type"] == "nuget"
    assert entry["candidate"]["name"] == "Aspose.Slides.Foss"
    assert v["verified_at"] is not None
    assert v["method"] is not None
    if v["published"]:
        assert v["evidence_url"], "a published:true entry must carry the evidence URL that justified the flip"


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


def _minimal_entry(*, registry_type="pypi", name="aspose-x-foss", published=False,
                    identity_basis=None, evidence_note=None):
    return {
        "registry_type": registry_type,
        "candidate": {"name": name},
        "candidate_owner": "asposefoss",
        "verification": {
            "published": published,
            "verified_at": None,
            "verified_owner": None,
            "evidence_url": None,
            "evidence_note": evidence_note,
            "method": None,
            "identity_basis": identity_basis,
        },
        "owner_match": None,
    }


class TestIdentityBasisValidation:
    """Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE: identity_basis
    schema field + the rule that a published:true entry with no 'foss'
    substring in its candidate name must be corroborated, not accepted on
    name alone."""

    def test_unknown_identity_basis_value_rejected(self):
        entry = _minimal_entry(identity_basis="just-guessed")
        errors = validate_package_entry(entry)
        assert any("identity_basis" in e for e in errors)

    def test_null_identity_basis_is_valid_when_unpublished(self):
        entry = _minimal_entry(published=False, identity_basis=None)
        assert validate_package_entry(entry) == []

    def test_foss_substring_name_needs_no_corroboration(self):
        """candidate.name already contains 'foss' -- any identity_basis
        (including manifest-extracted) is fine, no evidence_note required."""
        entry = _minimal_entry(name="aspose-x-foss", published=True, identity_basis="manifest-extracted")
        assert validate_package_entry(entry) == []

    def test_non_foss_name_published_true_requires_corroborated_basis(self):
        """Real case: PyPI's aspose-note (no 'foss') published:true must
        carry identity_basis='corroborated-non-convention-match', not
        'foss-convention-match' or anything else."""
        entry = _minimal_entry(
            name="aspose-note", published=True, identity_basis="foss-convention-match",
            evidence_note="some note",
        )
        errors = validate_package_entry(entry)
        assert any("corroborated-non-convention-match" in e for e in errors)

    def test_non_foss_name_corroborated_basis_requires_evidence_note(self):
        entry = _minimal_entry(
            name="aspose-note", published=True, identity_basis="corroborated-non-convention-match",
            evidence_note=None,
        )
        errors = validate_package_entry(entry)
        assert any("evidence_note" in e for e in errors)

    def test_non_foss_name_corroborated_basis_with_evidence_note_passes(self):
        entry = _minimal_entry(
            name="aspose-note", published=True, identity_basis="corroborated-non-convention-match",
            evidence_note="project_urls matches github.com/aspose-note-foss/... exactly",
        )
        assert validate_package_entry(entry) == []

    def test_maven_and_go_modules_are_exempt_from_the_flat_name_check(self):
        """maven (groupId/artifactId) and go_modules (fully-qualified module
        path) have their own structured identity and are not subject to the
        flat candidate.name foss-substring check."""
        maven_entry = {
            "registry_type": "maven",
            "candidate": {"group_id": "org.aspose", "artifact_id": "aspose-note"},
            "candidate_owner": "org.aspose",
            "verification": {
                "published": True, "verified_at": "2026-01-01", "verified_owner": None,
                "evidence_url": "u", "evidence_note": None, "method": "m", "identity_basis": None,
            },
            "owner_match": None,
        }
        assert validate_package_entry(maven_entry) == []

    def test_existing_7_registry_entries_all_pass_with_new_rule(self):
        """Regression pin: adding identity_basis validation must not break
        any of the 7 already-committed, already-verified entries."""
        data = _load()
        errors = validate_package_registry(data)
        assert errors == []


class TestConflictField:
    """Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 1: the
    new optional `conflict` field, non-null only when candidate discovery
    found multiple plausible identity hits it could not safely resolve."""

    def test_absent_conflict_is_valid(self):
        entry = _minimal_entry()
        assert validate_package_entry(entry) == []

    def test_null_conflict_is_valid(self):
        entry = _minimal_entry()
        entry["conflict"] = None
        assert validate_package_entry(entry) == []

    def test_well_formed_conflict_is_valid(self):
        entry = _minimal_entry()
        entry["conflict"] = {
            "candidates": ["aspose-x", "aspose-x-foss-mirror"],
            "note": "Two hits, neither corroborated by project_url; needs human review",
        }
        assert validate_package_entry(entry) == []

    def test_conflict_must_be_object_or_null(self):
        entry = _minimal_entry()
        entry["conflict"] = "aspose-x"
        errors = validate_package_entry(entry)
        assert any("conflict" in e and "object or null" in e for e in errors)

    def test_conflict_missing_candidates_is_rejected(self):
        entry = _minimal_entry()
        entry["conflict"] = {"note": "missing candidates list"}
        errors = validate_package_entry(entry)
        assert any("candidates" in e for e in errors)

    def test_conflict_missing_note_is_rejected(self):
        entry = _minimal_entry()
        entry["conflict"] = {"candidates": ["a", "b"]}
        errors = validate_package_entry(entry)
        assert any("note" in e for e in errors)

    def test_conflict_candidates_must_be_list_of_strings(self):
        entry = _minimal_entry()
        entry["conflict"] = {"candidates": [1, 2], "note": "bad shape"}
        errors = validate_package_entry(entry)
        assert any("candidates" in e and "list of strings" in e for e in errors)

    def test_conflict_note_must_be_non_empty(self):
        entry = _minimal_entry()
        entry["conflict"] = {"candidates": ["a"], "note": "   "}
        errors = validate_package_entry(entry)
        assert any("note" in e and "non-empty" in e for e in errors)

    def test_no_current_registry_entry_carries_a_conflict(self):
        """Regression pin: today, zero entries should have an unresolved
        conflict -- if this ever fails, it means a real one was found and
        should be triaged, not silently normalized away."""
        data = _load()
        for family, platforms in data.items():
            if family.startswith("_"):
                continue
            for platform, entry in platforms.items():
                assert entry.get("conflict") is None, f"{family}/{platform} has an unresolved conflict"


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


class TestSetContentHealingStatus:
    """PKGINSTALL-CONTENT-HEALING-STATUS-WRITEBACK (2026-09-10): the single
    choke point for this mutation, extracted from
    package_publish_watch.py::apply_proposal()'s previously-inlined code so
    that writer and reconcile_content_healing_status.py's own writer can
    never silently diverge on field shape."""

    def test_sets_all_three_fields(self):
        entry = {"registry_type": "pypi", "candidate": {"name": "x"}}
        set_content_healing_status(entry, "pending", checked_at="2026-09-10", reason="test reason")
        assert entry["content_healing_status"] == "pending"
        assert entry["content_healing_status_set_at"] == "2026-09-10"
        assert entry["content_healing_status_reason"] == "test reason"

    def test_reason_defaults_to_empty_string(self):
        entry = {}
        set_content_healing_status(entry, "not_needed", checked_at="2026-09-10")
        assert entry["content_healing_status_reason"] == ""

    def test_rejects_unknown_status(self):
        entry = {}
        try:
            set_content_healing_status(entry, "bogus", checked_at="2026-09-10")
            assert False, "expected ValueError"
        except ValueError:
            pass
        assert "content_healing_status" not in entry, "must not partially mutate on rejection"

    def test_healed_is_a_valid_status(self):
        """The new terminal state reconcile_content_healing_status.py
        transitions into -- must not be rejected as 'unknown'."""
        entry = {}
        set_content_healing_status(entry, "healed", checked_at="2026-09-10", reason="0 remaining findings")
        assert entry["content_healing_status"] == "healed"

    def test_overwrites_existing_values_in_place(self):
        entry = {
            "content_healing_status": "pending",
            "content_healing_status_set_at": "2026-08-01",
            "content_healing_status_reason": "old reason",
        }
        set_content_healing_status(entry, "healed", checked_at="2026-09-10", reason="new reason")
        assert entry["content_healing_status"] == "healed"
        assert entry["content_healing_status_set_at"] == "2026-09-10"
        assert entry["content_healing_status_reason"] == "new reason"
