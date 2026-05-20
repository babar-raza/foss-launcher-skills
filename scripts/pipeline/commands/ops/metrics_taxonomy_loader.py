# Adapted from aspose.org
"""Taxonomy display-name resolution helpers for RunMetrics.

Reads scripts/pipeline/config/metrics_taxonomy.yaml and provides
resolve_* functions for agent_name, job_type, product, and platform.
Falls back to the raw key on any lookup failure — never raises.

Public API
----------
    resolve_agent_name(key)     — agents[key].display_name or key
    resolve_job_type(key)       — job_types[key].display_name or key
    resolve_product(key)        — products[key] display value or key
    resolve_platform(key)       — platforms[key] display value or key
    build_item_name(product, platform) — short title-case item_name

No side effects on import. No HTTP calls. No secrets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Default taxonomy path (relative to this file)
# scripts/pipeline/commands/ops/  →  scripts/pipeline/config/
# ---------------------------------------------------------------------------

_DEFAULT_TAXONOMY_PATH: Path = (
    Path(__file__).parent.parent.parent  # scripts/pipeline/
    / "config"
    / "metrics_taxonomy.yaml"
)


def _load(taxonomy_path: str | Path | None = None) -> dict[str, Any]:
    """Load and return the taxonomy YAML as a dict. Never raises."""
    try:
        import yaml  # type: ignore[import-untyped]
        p = Path(taxonomy_path) if taxonomy_path else _DEFAULT_TAXONOMY_PATH
        with p.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def resolve_agent_name(key: str, taxonomy_path: str | Path | None = None) -> str:
    """Return display_name for an agent key, or *key* unchanged if not found."""
    taxonomy = _load(taxonomy_path)
    entry = taxonomy.get("agents", {}).get(key)
    if isinstance(entry, dict):
        display = entry.get("display_name")
        if isinstance(display, str) and display.strip():
            return display
    return key


def resolve_job_type(key: str, taxonomy_path: str | Path | None = None) -> str:
    """Return display_name for a job_type key, or *key* unchanged if not found."""
    taxonomy = _load(taxonomy_path)
    entry = taxonomy.get("job_types", {}).get(key)
    if isinstance(entry, dict):
        display = entry.get("display_name")
        if isinstance(display, str) and display.strip():
            return display
    return key


def resolve_product(key: str, taxonomy_path: str | Path | None = None) -> str:
    """Return display name for a product key (e.g. ``"cells"`` → ``"Aspose.Cells"``).

    Returns *key* unchanged if not found.
    """
    taxonomy = _load(taxonomy_path)
    value = taxonomy.get("products", {}).get(key)
    if isinstance(value, str) and value.strip():
        return value
    return key


def resolve_platform(key: str, taxonomy_path: str | Path | None = None) -> str:
    """Return display name for a platform key (e.g. ``"java"`` → ``"Java"``).

    Returns *key* unchanged if not found.
    """
    taxonomy = _load(taxonomy_path)
    value = taxonomy.get("platforms", {}).get(key)
    if isinstance(value, str) and value.strip():
        return value
    return key


# ---------------------------------------------------------------------------
# item_name builder
# ---------------------------------------------------------------------------


def build_item_name(product_display: str, platform_display: str) -> str:
    """Build a short title-case item_name (target 10–14 chars).

    Strips the ``"Aspose."`` prefix from *product_display*.
    Format: ``"{ProductShort} {Platform} Run"``

    Examples::

        build_item_name("Aspose.Cells", "Java")  →  "Cells Java Run"
        build_item_name("Aspose.Words", ".NET")  →  "Words .NET Run"
        build_item_name("Aspose.Total", "All")   →  "Total All Run"
    """
    prod_short = (
        product_display[len("Aspose."):]
        if product_display.startswith("Aspose.")
        else product_display
    )
    return f"{prod_short} {platform_display} Run"
