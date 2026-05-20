# Adapted from aspose.org scripts/pipeline/lib/ for standalone use
"""fingerprint_collector.py — TC-PROD-003: Input fingerprint collection for the refresh decision engine.

Collects all input fingerprints for a (product, subdomain) pair as defined in the
dependency registry. These fingerprints feed decision_engine.decide().

All fingerprints are sha256 hashes of file contents (or git SHAs). They are NOT
compared here — comparison is in decision_engine.py.

Phase 2 (shadow-only): results are written to shadow paths, never to production manifests.
Each fingerprint is collected independently. Missing files or errors set the value to None
and are recorded in collection_errors. This function never raises.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from scripts.pipeline.lib.dependency_registry import DependencyRegistry, SurfaceEntry

# TC-HEAL-001: Use the canonical clone cache path resolver from core.clone_cache
# so the path pattern stays in sync with the rest of the pipeline.
# Correct layout: runs/.clone_cache/aspose_{family}_{platform} (flat with aspose_ prefix).
# Previous code used _CLONE_CACHE / family / platform which does not match actual dirs.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.clone_cache import clone_path as _clone_cache_path

_REPO_ROOT = Path(os.environ.get("CONTENT_REPO_PATH", str(Path(__file__).resolve().parents[3])))

_VALID_RUN_TYPES = frozenset({
    "full-s84", "reference-only", "knowledge-only", "targeted", "harness", "unknown"
})


@dataclass(frozen=True)
class InputFingerprintSet:
    """All collected input fingerprints for a (product, subdomain) pair."""

    product: str
    subdomain: str
    upstream_repo_sha: Optional[str]
    local_knowledge_sha: Optional[str]
    knowledge_content_hash: Optional[str]
    products_json_hash: Optional[str]
    template_hash: Optional[str]
    generator_code_hash: Optional[str]
    skill_version_hash: Optional[str]
    config_hash: Optional[str]
    collection_errors: list = field(default_factory=list, compare=False)

    def to_dict(self) -> dict:
        """Return fingerprint values as a plain dict (excludes collection_errors)."""
        return {
            "upstream_repo_sha": self.upstream_repo_sha,
            "local_knowledge_sha": self.local_knowledge_sha,
            "knowledge_content_hash": self.knowledge_content_hash,
            "products_json_hash": self.products_json_hash,
            "template_hash": self.template_hash,
            "generator_code_hash": self.generator_code_hash,
            "skill_version_hash": self.skill_version_hash,
            "config_hash": self.config_hash,
        }

    def for_fingerprints_required(self, fingerprints_required: list) -> dict:
        """Return only the fingerprints listed in the registry entry."""
        data = self.to_dict()
        return {k: v for k, v in data.items() if k in fingerprints_required}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> Optional[str]:
    """Return sha256 hex digest of a file's contents, or None if missing."""
    if not path.is_file():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def _sha256_text(text: str) -> str:
    """Return sha256 hex digest of a UTF-8 string."""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _collect_upstream_repo_sha(family: str, platform: str) -> Optional[str]:
    """Get HEAD SHA from the clone cache for this product.

    TC-HEAL-001: Uses core.clone_cache.clone_path() for the canonical flat layout
    (runs/.clone_cache/aspose_{family}_{platform}), not the incorrect
    runs/.clone_cache/{family}/{platform} pattern the previous code used.
    """
    clone_dir = _clone_cache_path(family, platform)
    if not clone_dir.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(clone_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _collect_local_knowledge_sha(repo_root: Path, family: str, platform: str) -> Optional[str]:
    """Read repo_sha from knowledge/{family}/{platform}/merged/model.yaml."""
    model_yaml = repo_root / "knowledge" / family / platform / "merged" / "model.yaml"
    if not model_yaml.is_file():
        return None
    try:
        for line in model_yaml.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("repo_sha:"):
                val = stripped[len("repo_sha:"):].strip().strip('"').strip("'")
                return val if val else None
    except OSError:
        pass
    return None


def _collect_knowledge_content_hash(repo_root: Path, family: str, platform: str) -> Optional[str]:
    """sha256 of the full content of knowledge/{family}/{platform}/merged/model.yaml."""
    model_yaml = repo_root / "knowledge" / family / platform / "merged" / "model.yaml"
    return _sha256_file(model_yaml)


def _collect_products_json_hash(repo_root: Path, product: str) -> Optional[str]:
    """sha256 of the relevant product entry in data/products.json.

    TC-HEAL-002: data/products.json is a JSON array where each entry has "family"
    and "platform" fields (e.g., {"family": "cells", "platform": "java", ...}).
    The product slug "cells/java" is split to match these fields.
    Previous code looked for "slug" or "id" keys that don't exist in the real file.
    """
    products_json = repo_root / "data" / "products.json"
    if not products_json.is_file():
        return None
    try:
        # Split product slug "family/platform" into components for field matching.
        family, _, platform = product.partition("/")
        if not family or not platform:
            return None
        data = json.loads(products_json.read_text(encoding="utf-8"))
        if isinstance(data, list):
            entry = next(
                (x for x in data
                 if x.get("family") == family and x.get("platform") == platform),
                None,
            )
        elif isinstance(data, dict):
            # Legacy dict format fallback (not used in production but kept for test compat)
            entry = data.get(product)
        else:
            entry = None
        if entry is None:
            return None
        serialized = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        return _sha256_text(serialized)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _collect_template_hash(repo_root: Path, template_paths: list) -> Optional[str]:
    """sha256 of sorted concatenated content of files in template_paths.

    Line endings are normalized before hashing to reduce noise.
    Only files listed in the registry paths are included (no recursive dependencies
    beyond the declared template_paths directories).
    """
    if not template_paths:
        return None
    collected = []
    for tp in template_paths:
        path = repo_root / tp
        if path.is_file():
            collected.append(path.read_text(encoding="utf-8", errors="replace"))
        elif path.is_dir():
            for f in sorted(path.rglob("*.html")):
                collected.append(f.read_text(encoding="utf-8", errors="replace"))
    if not collected:
        return None
    normalized = "\n".join(t.replace("\r\n", "\n").replace("\r", "\n") for t in collected)
    return _sha256_text(normalized)


def _collect_generator_code_hash(repo_root: Path, backing_generator: Optional[str]) -> Optional[str]:
    """sha256 of the backing generator script content."""
    if not backing_generator:
        return None
    return _sha256_file(repo_root / backing_generator)


def _collect_skill_version_hash(repo_root: Path, backing_skill: Optional[str]) -> Optional[str]:
    """sha256 of the relevant .claude/commands/{skill}.md content."""
    if not backing_skill:
        return None
    commands_dir = repo_root / ".claude" / "commands"
    skill_lower = backing_skill.lower()
    candidates = [
        commands_dir / f"{skill_lower}.md",
        commands_dir / f"{skill_lower.replace('-', '_')}.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return _sha256_file(candidate)
    return None


def _collect_config_hash(repo_root: Path, config_path: Optional[str]) -> Optional[str]:
    """sha256 of the config file content."""
    if not config_path:
        return None
    return _sha256_file(repo_root / config_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_input_fingerprints(
    product: str,
    subdomain: str,
    registry: DependencyRegistry,
    *,
    repo_root: Optional[Path] = None,
) -> InputFingerprintSet:
    """Collect all input fingerprints for (product, subdomain) as defined by the registry.

    Each fingerprint is independently computed. Missing files or collection errors
    are recorded in collection_errors; the corresponding fingerprint is set to None.
    This function never raises.

    Args:
        product: Product slug in "{family}/{platform}" format.
        subdomain: Surface name (e.g., "reference", "products").
        registry: Loaded DependencyRegistry instance.
        repo_root: Override repo root for testing (default: auto-detected).

    Returns:
        InputFingerprintSet with all fingerprint values (some may be None).

    Raises:
        UnknownSurfaceError: if subdomain is not in the registry.
    """
    root = repo_root if repo_root is not None else _REPO_ROOT
    surface: SurfaceEntry = registry.get_surface(subdomain)

    errors: list = []

    parts = product.split("/", 1)
    if len(parts) != 2:
        errors.append(f"Product {product!r} is not in family/platform format")
        family, platform = product, "unknown"
    else:
        family, platform = parts

    def _safe(name: str, fn):
        try:
            return fn()
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            return None

    upstream_repo_sha = _safe(
        "upstream_repo_sha",
        lambda: _collect_upstream_repo_sha(family, platform),
    )
    local_knowledge_sha = _safe(
        "local_knowledge_sha",
        lambda: _collect_local_knowledge_sha(root, family, platform),
    )
    knowledge_content_hash = _safe(
        "knowledge_content_hash",
        lambda: _collect_knowledge_content_hash(root, family, platform),
    )
    products_json_hash = _safe(
        "products_json_hash",
        lambda: _collect_products_json_hash(root, product),
    )
    template_hash = _safe(
        "template_hash",
        lambda: _collect_template_hash(root, surface.template_paths or []),
    )
    generator_code_hash = _safe(
        "generator_code_hash",
        lambda: _collect_generator_code_hash(root, surface.backing_generator),
    )
    skill_version_hash = _safe(
        "skill_version_hash",
        lambda: _collect_skill_version_hash(root, surface.backing_skill),
    )
    config_hash = _safe(
        "config_hash",
        lambda: _collect_config_hash(root, surface.config_path),
    )

    return InputFingerprintSet(
        product=product,
        subdomain=subdomain,
        upstream_repo_sha=upstream_repo_sha,
        local_knowledge_sha=local_knowledge_sha,
        knowledge_content_hash=knowledge_content_hash,
        products_json_hash=products_json_hash,
        template_hash=template_hash,
        generator_code_hash=generator_code_hash,
        skill_version_hash=skill_version_hash,
        config_hash=config_hash,
        collection_errors=errors,
    )
