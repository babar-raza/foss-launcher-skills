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

    owner_match = entry["owner_match"]
    if owner_match is not None and not isinstance(owner_match, bool):
        errors.append(f"{context}.owner_match: must be a boolean or null")

    return errors


def load_registry(path: Path | None = None) -> dict[str, Any]:
    import json
    path = path or default_registry_path()
    with open(path, encoding="utf-8") as f:
        return json.load(f)
