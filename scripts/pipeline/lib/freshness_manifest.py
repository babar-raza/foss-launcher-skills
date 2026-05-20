"""freshness_manifest.py — Per-product/per-subdomain freshness manifest I/O.

Ported from aspose.org scripts/pipeline/lib/freshness_manifest.py.

A freshness manifest records the state of a single surface (reference, products,
docs, blog, kb) for a single product at the time of the last generation run.
It separates input fingerprints (what determines whether to regenerate) from
output state (what determines whether to reconcile).

Storage: runs/state/{family}/{platform}/{subdomain}/freshness-manifest.json
Note: runs/ is gitignored; manifests are durable within a run but not committed.

Atomic write: {path}.tmp -> os.replace -> {path} so interruption never leaves
a partial file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------------------

VALID_STATUSES: frozenset[str] = frozenset({
    "FRESH",
    "BASELINED_UNPROVEN",
    "REGENERATE_UPSTREAM",
    "REGENERATE_GENERATOR",
    "REGENERATE_METADATA",
    "REGENERATE_POLICY",
    "RECONCILE_MISSING",
    "RECONCILE_DRIFTED",
    "VALIDATE_ONLY",
    "BLOCKED",
    "DRY_RUN_PASS",
    "PARTIAL_PASS",
})

REQUIRED_FIELDS: frozenset[str] = frozenset({
    "manifest_version",
    "product",
    "subdomain",
    "surface_type",
    "input_fingerprints",
    "output_state",
    "manifest_status",
    "generation_timestamp",
    "run_id",
})

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised when a manifest dict is missing required fields or has an invalid status."""


# ---------------------------------------------------------------------------
# FreshnessManifest wrapper
# ---------------------------------------------------------------------------


class FreshnessManifest:
    """Typed wrapper around a freshness manifest dictionary.

    Use :func:`load`, :func:`save`, or :func:`migrate_from_missing` to create instances.
    Direct construction is permitted for tests.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        _validate(data)
        self._data: dict[str, Any] = dict(data)

    @property
    def product(self) -> str:
        return self._data["product"]

    @property
    def subdomain(self) -> str:
        return self._data["subdomain"]

    @property
    def manifest_status(self) -> str:
        return self._data["manifest_status"]

    @property
    def run_id(self) -> str:
        return self._data["run_id"]

    @property
    def input_fingerprints(self) -> dict[str, Any]:
        return dict(self._data.get("input_fingerprints", {}))

    @property
    def output_state(self) -> dict[str, Any]:
        return dict(self._data.get("output_state", {}))

    @property
    def changed_input_fingerprints(self) -> list[str]:
        return list(self._data.get("changed_input_fingerprints", []))

    def with_updates(self, **kwargs: Any) -> "FreshnessManifest":
        """Return a new FreshnessManifest with specified fields updated."""
        updated = dict(self._data)
        updated.update(kwargs)
        return FreshnessManifest(updated)

    def to_dict(self) -> dict[str, Any]:
        """Return a shallow copy of the underlying data dict."""
        return dict(self._data)

    def __repr__(self) -> str:
        return (
            f"FreshnessManifest(product={self.product!r}, "
            f"subdomain={self.subdomain!r}, "
            f"status={self.manifest_status!r})"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _manifest_path(product: str, subdomain: str, state_root: str | Path) -> Path:
    """Compute the manifest file path for a given product/subdomain."""
    family, platform = product.split("/", 1)
    return Path(state_root) / family / platform / subdomain / "freshness-manifest.json"


def _validate(data: dict[str, Any]) -> None:
    """Raise ValidationError if the manifest dict is structurally invalid."""
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise ValidationError(f"Missing required fields: {sorted(missing)}")
    status = data.get("manifest_status")
    if status not in VALID_STATUSES:
        raise ValidationError(
            f"Invalid manifest_status: {status!r}. "
            f"Must be one of: {sorted(VALID_STATUSES)}"
        )
    output_state = data.get("output_state", {})
    if not isinstance(output_state, dict):
        raise ValidationError("output_state must be a dict")
    if "output_exists" not in output_state:
        raise ValidationError("output_state must contain 'output_exists'")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load(
    product: str,
    subdomain: str,
    state_root: str | Path = "runs/state",
) -> Optional[FreshnessManifest]:
    """Load a freshness manifest for the given product and subdomain.

    Returns None if the manifest file does not exist, is not valid JSON,
    or fails structural validation. Never raises.
    """
    path = _manifest_path(product, subdomain, state_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return FreshnessManifest(data)
    except (json.JSONDecodeError, OSError, ValidationError):
        return None


def save(
    manifest: FreshnessManifest,
    state_root: str | Path = "runs/state",
) -> None:
    """Save a freshness manifest to disk atomically.

    Uses {path}.tmp + os.replace to avoid partial writes on interruption.
    Creates parent directories as needed.
    """
    data = manifest.to_dict()
    path = _manifest_path(data["product"], data["subdomain"], state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def migrate_from_missing(
    product: str,
    subdomain: str,
    disk_state: dict[str, Any],
) -> FreshnessManifest:
    """Create a baseline manifest from current disk state when no manifest exists.

    Status is ALWAYS BASELINED_UNPROVEN, NEVER FRESH.

    BASELINED_UNPROVEN means: a manifest has been created from existing disk state
    but the relationship between current inputs and that output has NOT been proven
    by a fresh governed generation run. This status may NOT satisfy the production
    freshness contract; it must be upgraded to FRESH by the next successful run.
    """
    data: dict[str, Any] = {
        "manifest_version": "1.0",
        "product": product,
        "subdomain": subdomain,
        "surface_type": disk_state.get("surface_type", "unknown"),
        "input_fingerprints": dict(disk_state.get("input_fingerprints", {})),
        "output_state": dict(disk_state.get("output_state", {"output_exists": False})),
        "manifest_status": "BASELINED_UNPROVEN",  # NEVER FRESH on cold-start migration
        "generation_timestamp": _now_iso(),
        "command_used": None,
        "run_id": disk_state.get("run_id", f"baseline-{_now_iso()[:10]}"),
        "governance_status": None,
        "decision": "VALIDATE_ONLY",
        "skip_reason": "Migrated from disk state; no proven input-output relationship",
        "changed_input_fingerprints": [],
        "prior_manifest_ref": None,
    }
    return FreshnessManifest(data)


# ---------------------------------------------------------------------------
# Output content hash helpers
# ---------------------------------------------------------------------------

# Pattern matching a genuine sha256 hash: exactly 64 lowercase hex chars after "sha256:".
_REAL_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def is_placeholder_hash(h: Optional[str]) -> bool:
    """Return True if h is a synthetic placeholder, not a real content hash."""
    if h is None:
        return False
    if not h.startswith("sha256:"):
        return False
    return not bool(_REAL_HASH_RE.match(h))


def compute_output_content_hash(content_root: Path) -> Optional[str]:
    """Compute a deterministic sha256 hash over all expected output files.

    Algorithm:
      1. Find all *.md files under content_root (recursive).
      2. Sort paths lexicographically (using forward-slash-normalised relative paths).
      3. For each file: concatenate "<relative_path>\\n<content>\\n" (line endings normalised).
      4. SHA256 the entire concatenation.

    Returns sha256:<hex> string, or None if content_root has no .md files.
    """
    if not content_root.is_dir():
        return None
    files = sorted(content_root.rglob("*.md"))
    if not files:
        return None
    h = hashlib.sha256()
    for f in files:
        rel = str(f.relative_to(content_root)).replace("\\", "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\n")
        content = f.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        h.update(content)
        h.update(b"\n")
    return f"sha256:{h.hexdigest()}"


def check_dirty_state(repo_root: Path, generator_path: Optional[str]) -> tuple:
    """Check whether the generator script has uncommitted working tree changes.

    Returns (is_dirty, dirty_files) where is_dirty=True if the generator has
    uncommitted changes, and dirty_files lists the modified paths.
    """
    if not generator_path:
        return False, []
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", generator_path],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        dirty_files = [
            line.strip() for line in result.stdout.splitlines() if line.strip()
        ]
        return bool(dirty_files), dirty_files
    except (subprocess.TimeoutExpired, OSError):
        return False, []


def validate_for_fresh(
    input_fingerprints: dict,
    output_content_hash: Optional[str],
    generator_path: Optional[str] = None,
    repo_root: Optional[Path] = None,
    fingerprints_required: Optional[list] = None,
) -> list:
    """Validate that all conditions are met before a manifest may be set to FRESH.

    Returns a list of violation strings. Empty list = all conditions met.
    """
    violations: list = []

    required = fingerprints_required or list(input_fingerprints.keys())
    missing = [k for k in required if input_fingerprints.get(k) is None]
    if missing:
        violations.append(f"Required fingerprints are None: {missing}")

    if output_content_hash is None:
        violations.append("output_content_hash is None — must be computed before FRESH status")
    elif is_placeholder_hash(output_content_hash):
        violations.append(
            f"output_content_hash is a placeholder ({output_content_hash!r}) — "
            "compute real hash with compute_output_content_hash()"
        )

    if generator_path and repo_root is not None:
        is_dirty, dirty_files = check_dirty_state(repo_root, generator_path)
        if is_dirty:
            violations.append(
                f"Generator has uncommitted changes — dirty_state=True: {dirty_files}"
            )

    return violations
