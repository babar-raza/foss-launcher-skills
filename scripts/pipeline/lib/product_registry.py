"""product_registry.py — Read-side loader for product identity + FOSS package-name
resolution.

Mission MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH, TC-MT040-46 (D-7).

Root problem this closes: install-command text (`npm install X`, `pip install Y`,
...) has historically been generated from THREE independent, disagreeing sources:
data/package_registry.json (the real intended single source of truth),
commands/knowledge/index.py's own hardcoded `_install_command()` typescript branch,
and commands/ops/batch_gen_missing.py's hand-maintained `PACKAGE_NAMES` dict. This
module is the shared loader those two call sites now go through instead of
hardcoding or duplicating identity logic.

Two read-only responsibilities, kept intentionally separate:

1. Product identity (`load_products` / `get_product`): data/products.json is the
   canonical family/platform product list, but consumers that read it directly
   have zero awareness of data/registry_exclusions.json -- the safety net
   update_product_registry.py itself enforces at merge time (see
   `_load_exclusions`/`_is_excluded`/`_enforce_exclusions` there). A product can
   be excluded (e.g. cells/typescript -- BLOCKED_REPO_NOT_LAUNCHABLE per
   INV-002/INV-004: no LICENSE file, GitLab-boilerplate README, and a
   non-Aspose package.json name) while its data/products.json record still says
   `active: true`, because nothing re-runs update_product_registry.py's merge on
   every read. This module reproduces the SAME matching semantics
   (`_is_excluded`) read-only, without touching or replacing that script's own
   enforcement. Unlike `_enforce_exclusions` (which mutates entries in place,
   setting `active: false` / `excluded: true` so the audit trail is preserved in
   data/products.json), this loader simply omits excluded entries from the
   returned list -- callers here want "is this a real, currently-launchable
   product", not a persisted registry-state audit.

2. Package-name resolution (`get_package_name`): resolves the best-known package
   name for a family/platform/registry_type from data/package_registry.json,
   falling back to lib/package_registry_data.py's `naming_convention_candidate()`
   guess only when the registry has nothing at all. Deliberately returns a bare
   name string with no opinion on whether it's safe to render as a real install
   command -- callers (e.g. index.py's `_install_command`) are responsible for
   checking `verification.published` themselves before doing that, exactly as
   `_java_install_command` already does for Maven.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    # Preferred: works whenever this module is imported dotted (`lib.product_registry`
    # or `from lib import product_registry`), which only requires the pipeline root
    # on sys.path -- the common denominator across every real caller (commands/
    # entrypoints that lazily insert the pipeline root, PYTHONPATH=scripts/pipeline
    # in tests/CI).
    from lib.package_registry_data import load_registry, naming_convention_candidate
except ImportError:
    # Fallback: this module's OWN directory (scripts/pipeline/lib/) is directly on
    # sys.path instead -- the pattern content_eval/evaluators/install_recipe.py and
    # audit/package_install_literal.py already use for reaching this same sibling.
    from package_registry_data import load_registry, naming_convention_candidate

# ---------------------------------------------------------------------------
# Configuration seam (mirrors commands/knowledge/index.py's configure()
# pattern: module-level globals + a configure() override, so tests can point
# every path at fixture files instead of the real repo data).
# ---------------------------------------------------------------------------

_DEFAULT_PRODUCTS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "products.json"
_DEFAULT_EXCLUSIONS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "registry_exclusions.json"
_DEFAULT_PACKAGE_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "package_registry.json"

PRODUCTS_PATH = _DEFAULT_PRODUCTS_PATH
EXCLUSIONS_PATH = _DEFAULT_EXCLUSIONS_PATH
PACKAGE_REGISTRY_PATH = _DEFAULT_PACKAGE_REGISTRY_PATH


def configure(
    *,
    products_path: "Path | str | None" = None,
    exclusions_path: "Path | str | None" = None,
    package_registry_path: "Path | str | None" = None,
) -> None:
    """Override module-level path constants for testing.

    Passing None for any single argument resets JUST that path back to its
    real-repo default -- matching index.py's configure() semantics -- so a
    test can override only the file(s) it actually needs a fixture for.
    """
    global PRODUCTS_PATH, EXCLUSIONS_PATH, PACKAGE_REGISTRY_PATH
    PRODUCTS_PATH = Path(products_path) if products_path is not None else _DEFAULT_PRODUCTS_PATH
    EXCLUSIONS_PATH = Path(exclusions_path) if exclusions_path is not None else _DEFAULT_EXCLUSIONS_PATH
    PACKAGE_REGISTRY_PATH = (
        Path(package_registry_path) if package_registry_path is not None else _DEFAULT_PACKAGE_REGISTRY_PATH
    )


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


# ---------------------------------------------------------------------------
# Exclusions -- read-only reproduction of update_product_registry.py's
# _load_exclusions()/_is_excluded() matching semantics (that script's own
# comment notes repo_patrol.py duplicates it too, per PIPELINE.md's "2 scripts
# need it -> duplicate and comment" rule; this is now a 3rd, library-owned
# copy specifically for read-side consumers -- NOT a replacement for either).
# ---------------------------------------------------------------------------

def _load_exclusions() -> list[dict]:
    data = _load_json(EXCLUSIONS_PATH, [])
    return data if isinstance(data, list) else []


def _is_excluded(exclusions: list[dict], *, repo_name: str = "", family: str = "", platform: str = "") -> bool:
    for ex in exclusions:
        if ex.get("match") == "repo_name" and repo_name and ex.get("value", "").lower() == repo_name.lower():
            return True
        if ex.get("match") == "family_platform" and family and platform \
                and ex.get("family") == family and ex.get("platform") == platform:
            return True
    return False


# ---------------------------------------------------------------------------
# Product identity
# ---------------------------------------------------------------------------

def load_products(apply_exclusions: bool = True) -> list[dict]:
    """Return the product list from data/products.json.

    When apply_exclusions is True (default), entries matching
    data/registry_exclusions.json are omitted entirely -- see module
    docstring for why this differs from update_product_registry.py's own
    in-place `active: false` mutation.
    """
    products = _load_json(PRODUCTS_PATH, [])
    if not isinstance(products, list):
        return []
    if not apply_exclusions:
        return products

    exclusions = _load_exclusions()
    return [
        p for p in products
        if not _is_excluded(
            exclusions,
            repo_name=p.get("repo_name", ""),
            family=p.get("family", ""),
            platform=p.get("platform", ""),
        )
    ]


def get_product(family: str, platform: str, apply_exclusions: bool = True) -> "dict | None":
    """Look up a single product by family/platform. Returns None if not found
    (or found but excluded, when apply_exclusions is True)."""
    for product in load_products(apply_exclusions=apply_exclusions):
        if product.get("family") == family and product.get("platform") == platform:
            return product
    return None


# ---------------------------------------------------------------------------
# Package-name resolution
# ---------------------------------------------------------------------------

def get_package_name(family: str, platform: str, registry_type: str) -> "str | None":
    """Resolve the best-known package name for family/platform under registry_type.

    Priority:
      1. data/package_registry.json's own candidate name for this exact
         family/platform/registry_type -- returned REGARDLESS of
         verification.published. A scouted/manifest-extracted (or even a
         previously recorded naming-convention-fallback) candidate the
         registry already has on file is more truthful than a fresh generic
         guess, even when it isn't confirmed live yet: e.g. cells/typescript's
         real candidate.name is "excel-cells" (unpublished, npm-backfill-scan
         evidence) -- a caller must not prefer the generic
         "@asposefoss/cells" convention guess over that just because the
         registry entry says published=false. Callers that need to know
         whether it's SAFE to render this name in a live install command
         (vs. an "unpublished" placeholder) must check
         verification.published on the same entry themselves -- this
         function deliberately returns a bare name with no opinion on
         publish state, exactly as its own docstring says.
      2. lib/package_registry_data.py's naming_convention_candidate() pure
         guess -- only reached when the registry has NO entry (or no
         candidate name) at all for this family/platform, i.e. there isn't
         even an unconfirmed scouted value to prefer over a guess.
      3. None -- caller decides the placeholder.
    """
    try:
        registry = load_registry(PACKAGE_REGISTRY_PATH)
    except (OSError, json.JSONDecodeError):
        registry = {}
    if not isinstance(registry, dict):
        registry = {}

    entry = registry.get(family, {})
    entry = entry.get(platform) if isinstance(entry, dict) else None
    if isinstance(entry, dict) and entry.get("registry_type") == registry_type:
        candidate = entry.get("candidate") or {}
        # go_modules identifies a package by module_path, not name -- every
        # other supported registry_type (npm/pypi/nuget/cargo) uses "name".
        # See package_registry_data.py's _CANDIDATE_REQUIRED_FIELD for the
        # authoritative per-registry_type shape.
        name = candidate.get("name") or candidate.get("module_path")
        if name:
            return name

    convention = naming_convention_candidate(family, platform, registry_type)
    if convention:
        name = convention.get("name") or convention.get("module_path")
        if name:
            return name

    return None
