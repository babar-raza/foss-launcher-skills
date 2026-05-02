"""dependency_registry.py — Load and query the refresh dependency registry.

The registry (data/refresh-dependencies.json) declares per-surface metadata:
which generator script or skill backs each surface, which fingerprints apply,
which template directories to hash, and the operational status.

Plan reference: serene-jingling-rain.md TC-PROD-002A and TC-PROD-002B.
Registry file: data/refresh-dependencies.json (git-tracked).
Schema file: data/schemas/dependency-registry-schema.json (git-tracked).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class UnknownSurfaceError(KeyError):
    """Raised when a surface name is not in the registry."""

    def __init__(self, surface_name: str, known: list[str]) -> None:
        self.surface_name = surface_name
        self.known = sorted(known)
        super().__init__(
            f"Unknown surface: {surface_name!r}. "
            f"Known surfaces: {self.known}"
        )


class RegistryValidationError(ValueError):
    """Raised when the registry fails structural validation."""


# ---------------------------------------------------------------------------
# SurfaceEntry dataclass-like wrapper
# ---------------------------------------------------------------------------


class SurfaceEntry:
    """Typed accessor for a single surface entry from the registry."""

    def __init__(self, name: str, data: dict[str, Any]) -> None:
        self._name = name
        self._data = dict(data)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._data["description"]

    @property
    def backing_generator(self) -> Optional[str]:
        return self._data.get("backing_generator")

    @property
    def backing_skill(self) -> Optional[str]:
        return self._data.get("backing_skill")

    @property
    def fingerprints_required(self) -> list[str]:
        return list(self._data["fingerprints_required"])

    @property
    def template_paths(self) -> list[str]:
        return list(self._data.get("template_paths", []))

    @property
    def config_path(self) -> Optional[str]:
        return self._data.get("config_path")

    @property
    def content_root(self) -> str:
        return self._data["content_root"]

    @property
    def expected_output_source(self) -> Optional[str]:
        return self._data.get("expected_output_source")

    @property
    def regeneration_triggers(self) -> list[str]:
        return list(self._data.get("regeneration_triggers", []))

    @property
    def reconciliation_triggers(self) -> list[str]:
        return list(self._data.get("reconciliation_triggers", []))

    @property
    def triage_checker(self) -> Optional[str]:
        return self._data.get("triage_checker")

    @property
    def supports_targeted_run(self) -> bool:
        return bool(self._data.get("supports_targeted_run", False))

    @property
    def status(self) -> str:
        return self._data["status"]

    @property
    def is_script_backed(self) -> bool:
        return self._data.get("backing_generator") is not None

    @property
    def is_agent_executed(self) -> bool:
        return self._data.get("backing_generator") is None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return (
            f"SurfaceEntry(name={self._name!r}, "
            f"status={self.status!r}, "
            f"script_backed={self.is_script_backed})"
        )


# ---------------------------------------------------------------------------
# DependencyRegistry wrapper
# ---------------------------------------------------------------------------


class DependencyRegistry:
    """Typed wrapper around the refresh dependency registry."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._surfaces: dict[str, SurfaceEntry] = {
            name: SurfaceEntry(name, entry)
            for name, entry in data.items()
        }

    def surface_names(self) -> list[str]:
        return sorted(self._surfaces.keys())

    def get_surface(self, surface_name: str) -> SurfaceEntry:
        """Return the SurfaceEntry for the given surface name.

        Raises UnknownSurfaceError if the surface is not registered.
        """
        if surface_name not in self._surfaces:
            raise UnknownSurfaceError(surface_name, list(self._surfaces.keys()))
        return self._surfaces[surface_name]

    def supported_surfaces(self) -> list[SurfaceEntry]:
        return [s for s in self._surfaces.values() if s.status == "supported"]

    def validate_only_surfaces(self) -> list[SurfaceEntry]:
        return [s for s in self._surfaces.values() if s.status == "validate_only"]

    def __contains__(self, surface_name: str) -> bool:
        return surface_name in self._surfaces

    def __len__(self) -> int:
        return len(self._surfaces)

    def __repr__(self) -> str:
        return f"DependencyRegistry(surfaces={self.surface_names()})"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_registry(data: dict[str, Any]) -> list[str]:
    """Validate the raw registry dict.

    Returns a list of validation error strings (empty = valid).
    Does not raise; callers decide whether errors are fatal.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        errors.append("Registry must be a JSON object, not a list or scalar")
        return errors

    valid_statuses = {"supported", "validate_only", "unsupported"}
    valid_output_sources = {"site_planner_output", "registry_rules", "product_inventory", None}
    required_keys = {"description", "fingerprints_required", "content_root",
                     "expected_output_source", "regeneration_triggers",
                     "reconciliation_triggers", "supports_targeted_run", "status"}

    for surface_name, entry in data.items():
        prefix = f"[{surface_name}]"

        if not isinstance(entry, dict):
            errors.append(f"{prefix} entry must be an object")
            continue

        # Required keys
        missing = required_keys - set(entry.keys())
        if missing:
            errors.append(f"{prefix} missing required keys: {sorted(missing)}")

        # fingerprints_required must be non-empty
        fps = entry.get("fingerprints_required", [])
        if not isinstance(fps, list) or len(fps) == 0:
            errors.append(f"{prefix} fingerprints_required must be a non-empty list")

        # status must be valid
        status = entry.get("status")
        if status not in valid_statuses:
            errors.append(f"{prefix} invalid status: {status!r}. Must be one of {sorted(valid_statuses)}")

        # expected_output_source must be valid (or null)
        eos = entry.get("expected_output_source")
        if eos not in valid_output_sources:
            errors.append(f"{prefix} invalid expected_output_source: {eos!r}")

        # validate_only/unsupported surfaces should NOT have backing_generator
        if status in ("validate_only", "unsupported") and entry.get("backing_generator"):
            errors.append(
                f"{prefix} status is {status!r} but backing_generator is set; "
                "agent-executed surfaces must not claim a script generator"
            )

    return errors


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_registry(
    path: str | Path = "data/refresh-dependencies.json",
) -> DependencyRegistry:
    """Load and validate the dependency registry from a JSON file.

    Raises:
        FileNotFoundError: if the path does not exist
        RegistryValidationError: if the registry fails structural validation
        json.JSONDecodeError: if the file is not valid JSON
    """
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_registry(data)
    if errors:
        raise RegistryValidationError(
            f"Registry at {path} has {len(errors)} validation error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
    return DependencyRegistry(data)


def get_surface(registry: DependencyRegistry, surface_name: str) -> SurfaceEntry:
    """Convenience wrapper: get a surface entry, raising UnknownSurfaceError if not found."""
    return registry.get_surface(surface_name)
