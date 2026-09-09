"""package_registry_data.py — Load and validate the unified package-manager registry.

Single source of truth for FOSS package-manager identity (name/coordinates/
owner) across every registry in actual use: pypi, nuget, maven, npm,
go_modules, cargo. Replaces the split data/foss_packages.json (Maven-only)
and data/cargo_packages.json (Cargo-only) files -- see Mission
MT015-2026-07-30-PACKAGE-REGISTRY (plans/master-plan.md) for the design
rationale: splitting state by registry conflated coordinate *shape* (which
legitimately varies) with *file location* (which doesn't need to), and the
two prior files had already diverged as a direct result.

vcpkg and Conan are deliberately excluded from REGISTRY_TYPES -- confirmed
never implemented in practice; Aspose.PDF FOSS for C++ ships via NuGet under
its own package ID (Aspose.PDF.Cpp.FOSS), distinct from the .NET package.

Registry file: data/package_registry.json (git-tracked).
Schema file: data/schemas/package-registry-schema.json (git-tracked).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

REGISTRY_TYPES = {"pypi", "nuget", "maven", "npm", "go_modules", "cargo"}

# Discriminated candidate shape per registry_type -- mirrors the schema's
# oneOf. Maps registry_type -> required candidate field.
_CANDIDATE_REQUIRED_FIELD = {
    "maven": ("group_id", "artifact_id"),
    "go_modules": ("module_path",),
    "pypi": ("name",),
    "nuget": ("name",),
    "npm": ("name",),
    "cargo": ("name",),
}

_ENTRY_REQUIRED_FIELDS = ("registry_type", "candidate", "candidate_owner", "verification", "owner_match")
_VERIFICATION_REQUIRED_FIELDS = ("published", "verified_at", "verified_owner", "evidence_url", "method")
_IDENTITY_BASIS_VALUES = (None, "manifest-extracted", "foss-convention-match", "corroborated-non-convention-match")
# Registries with a flat `candidate.name` field -- the ones the foss-substring
# rule applies to directly. maven/go_modules have their own structured
# identity (groupId/artifactId; a fully-qualified module path) and are not
# subject to this specific check.
_FLAT_NAME_REGISTRY_TYPES = {"pypi", "nuget", "npm", "cargo"}


def default_registry_path() -> Path:
    return Path("data/package_registry.json")


def _check_required(data: dict, fields: tuple, context: str, errors: list[str]) -> None:
    for field in fields:
        if field not in data:
            errors.append(f"{context}: missing required field '{field}'")


def validate_package_registry(data: dict[str, Any]) -> list[str]:
    """Validate the full registry structure. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root: must be an object"]

    for family, platforms in data.items():
        if family.startswith("_"):
            continue  # allow a leading _comment key, matching foss_packages.json/cargo_packages.json convention
        if not isinstance(platforms, dict):
            errors.append(f"{family}: platform map must be an object")
            continue
        for platform, entry in platforms.items():
            context = f"{family}.{platform}"
            errors.extend(validate_package_entry(entry, context))
    return errors


def validate_package_entry(entry: dict[str, Any], context: str = "entry") -> list[str]:
    """Validate a single PackageEntry. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []
    if not isinstance(entry, dict):
        return [f"{context}: entry must be an object"]

    _check_required(entry, _ENTRY_REQUIRED_FIELDS, context, errors)
    if errors:
        return errors  # can't check shape-dependent fields without the required scaffolding

    registry_type = entry["registry_type"]
    if registry_type not in REGISTRY_TYPES:
        errors.append(
            f"{context}: registry_type '{registry_type}' not in {sorted(REGISTRY_TYPES)} "
            f"(vcpkg/conan are not valid -- never implemented in practice)"
        )
        return errors  # can't validate candidate shape against an unknown registry_type

    candidate = entry["candidate"]
    if not isinstance(candidate, dict):
        errors.append(f"{context}.candidate: must be an object")
    else:
        for field in _CANDIDATE_REQUIRED_FIELD[registry_type]:
            if field not in candidate:
                errors.append(
                    f"{context}.candidate: registry_type '{registry_type}' requires field '{field}'"
                )

    verification = entry["verification"]
    if not isinstance(verification, dict):
        errors.append(f"{context}.verification: must be an object")
    else:
        _check_required(verification, _VERIFICATION_REQUIRED_FIELDS, f"{context}.verification", errors)
        if "published" in verification and not isinstance(verification["published"], bool):
            errors.append(f"{context}.verification.published: must be a boolean")

        identity_basis = verification.get("identity_basis")
        if identity_basis not in _IDENTITY_BASIS_VALUES:
            errors.append(
                f"{context}.verification.identity_basis: '{identity_basis}' not in {_IDENTITY_BASIS_VALUES}"
            )
        elif (
            verification.get("published") is True
            and registry_type in _FLAT_NAME_REGISTRY_TYPES
            and isinstance(candidate, dict)
            and "foss" not in str(candidate.get("name", "")).lower()
        ):
            # Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE identity rule:
            # a published:true entry whose candidate name has no "foss"
            # substring must have been corroborated, not accepted on name
            # alone -- e.g. PyPI's real aspose-note package.
            if identity_basis != "corroborated-non-convention-match":
                errors.append(
                    f"{context}.verification: candidate name {candidate.get('name')!r} has no 'foss' "
                    f"substring but published=true -- identity_basis must be "
                    f"'corroborated-non-convention-match', got {identity_basis!r}"
                )
            elif not verification.get("evidence_note"):
                errors.append(
                    f"{context}.verification: identity_basis='corroborated-non-convention-match' "
                    f"requires a non-empty evidence_note explaining the corroboration"
                )

    owner_match = entry["owner_match"]
    if owner_match is not None and not isinstance(owner_match, bool):
        errors.append(f"{context}.owner_match: must be a boolean or null")

    # `conflict` (Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION) is
    # optional -- absent or null means "no unresolved identity conflict for
    # this entry", the overwhelmingly common case. Only validate its shape
    # when actually present.
    if "conflict" in entry and entry["conflict"] is not None:
        conflict = entry["conflict"]
        if not isinstance(conflict, dict):
            errors.append(f"{context}.conflict: must be an object or null")
        else:
            _check_required(conflict, ("candidates", "note"), f"{context}.conflict", errors)
            if "candidates" in conflict and not (
                isinstance(conflict["candidates"], list)
                and all(isinstance(c, str) for c in conflict["candidates"])
            ):
                errors.append(f"{context}.conflict.candidates: must be a list of strings")
            if "note" in conflict and not (isinstance(conflict["note"], str) and conflict["note"].strip()):
                errors.append(f"{context}.conflict.note: must be a non-empty string")

    return errors


def load_registry(path: Path | None = None) -> dict[str, Any]:
    import json
    path = path or default_registry_path()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Naming-convention candidate fallback (TC-MT015-07)
#
# package_manifest.py's scout-time extraction is 100% deterministic but can
# only extract identity that actually exists in the upstream repo's manifest
# file -- and that is format-dependent, not a wiring bug: Cargo.toml
# structurally requires [package] name/version, but .NET's .csproj has no
# mandatory PackageId/Version at all (confirmed: the real slides/net and
# words/net .csproj files declare neither -- these are typically injected
# only at NuGet-pack/CI time). For registries in this position, the only
# available "candidate" before a real manifest value or a live registry
# check exists is a naming-convention guess -- explicitly a guess, tracked
# via `scout_source` so it's never confused with a source-extracted value.
# ---------------------------------------------------------------------------

# Families whose display form is an acronym, not a title-cased word --
# mirrors commands/knowledge/index.py's _display_name() special-casing
# (kept in sync manually; both are small, stable, rarely-changed tables).
_ACRONYM_FAMILIES = {"3d": "3D", "pdf": "PDF"}


def _title_case_family(family: str) -> str:
    return _ACRONYM_FAMILIES.get(family, family.title())


def naming_convention_candidate(family: str, platform: str, registry_type: str) -> dict[str, Any] | None:
    """Convention-based candidate coordinate for a family/platform, per the
    naming schema supplied for Mission MT015-2026-07-30-PACKAGE-REGISTRY
    (worked example: Aspose.PDF FOSS). Returns None for "maven" (a real
    pom.xml groupId/artifactId almost always exists -- no fallback attempted)
    and for any registry_type this schema doesn't cover.

    Honesty note: the one real shipped NuGet package this repo has today
    (org.aspose:aspose-slides-foss's NuGet counterpart) is named
    "Aspose.Slides.Foss" -- title-case "Foss", not the all-caps "FOSS" this
    function produces. That's an earlier, different precedent, not this
    schema; this function follows the user's current explicit instruction
    for anything NEW rather than silently matching it. Every value this
    function returns is a guess, not a confirmed identity -- callers must
    record `scout_source="naming-convention-fallback"` and leave
    `verification.published`/`owner_match` unresolved until a live check or
    human review settles it.
    """
    fam = _title_case_family(family)
    if registry_type == "pypi":
        return {"name": f"aspose-{family}-foss"}
    if registry_type == "nuget":
        if platform == "cpp":
            return {"name": f"Aspose.{fam}.Cpp.FOSS"}
        return {"name": f"Aspose.{fam}.FOSS"}
    if registry_type == "npm":
        return {"name": f"@asposefoss/{family}"}
    if registry_type == "go_modules":
        return {"module_path": f"github.com/aspose-{family}-foss/aspose-{family}-foss-for-go"}
    if registry_type == "cargo":
        return {"name": f"aspose-{family}-foss"}
    return None


def naming_convention_owner(registry_type: str, *, family: str = "") -> str | None:
    """Convention-based expected publisher org/namespace, per the same schema.
    Go's candidate owner is the per-family GitHub org itself (no single
    shared "asposefoss"-style org for Go, per the supplied schema table)."""
    if registry_type == "maven":
        return "org.aspose"
    if registry_type == "go_modules":
        return f"aspose-{family}-foss" if family else None
    if registry_type in ("pypi", "nuget", "npm", "cargo"):
        return "asposefoss"
    return None
