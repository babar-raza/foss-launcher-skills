"""manifest_consumer.py — Load, select, and preflight enrichment handoff manifests.

Planning/preflight tool for Lane D swarm sprint. Does NOT invoke skills
or write content — it reads the handoff manifest, selects candidates,
runs preflight checks, and emits run-plan JSON for downstream execution.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo root resolution
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[3]  # enrichment -> lib -> pipeline -> scripts -> repo root

# ---------------------------------------------------------------------------
# Action-to-skill mapping
# ---------------------------------------------------------------------------
ACTION_TO_SKILL: dict[str, str] = {
    "create_new_blog_post": "/new-blog-post",
    "create_new_kb_page": "/new-kb-howto",
    "create_new_docs_page": "/new-docs-page",
    "update_existing_blog_post": "/page-update",
    "update_existing_kb_page": "/page-update",
    "update_existing_docs_page": "/page-update",
}

# ---------------------------------------------------------------------------
# Subdomain to content-path templates
# ---------------------------------------------------------------------------
_TARGET_TEMPLATES: dict[str, str] = {
    "blog.aspose.org": "content/blog.aspose.org/{family}/{platform}/{slug}/index.md",
    "kb.aspose.org": "content/kb.aspose.org/en/{family}/{platform}/{slug}.md",
    "docs.aspose.org": "content/docs.aspose.org/en/{family}/{platform}/{section}/{slug}.md",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_handoff_manifest(family: str, platform: str) -> dict:
    """Load reports/enrichment/{family}/{platform}/handoff-manifest.json."""
    manifest_path = (
        _REPO_ROOT / "reports" / "enrichment" / family / platform / "handoff-manifest.json"
    )
    if not manifest_path.exists():
        raise FileNotFoundError(f"Handoff manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def select_candidate(
    manifest: dict,
    *,
    cluster: str | None = None,
    index: int | None = None,
    subdomain: str | None = None,
) -> dict:
    """Select one manifest item.

    Priority: index > cluster > subdomain.
    Raises ValueError if not found or ambiguous.
    """
    items = manifest.get("manifest_items", [])
    if not items:
        raise ValueError("Manifest contains no items")

    # --- By index (highest priority) ---
    if index is not None:
        if index < 0 or index >= len(items):
            raise ValueError(f"Index {index} out of range (0..{len(items) - 1})")
        return items[index]

    # --- By cluster ---
    if cluster is not None:
        matches = [it for it in items if it.get("cluster") == cluster]
        if not matches:
            clusters = sorted({it.get("cluster", "?") for it in items})
            raise ValueError(
                f"Cluster '{cluster}' not found. Available: {', '.join(clusters)}"
            )
        if len(matches) > 1 and subdomain:
            matches = [m for m in matches if m.get("subdomain") == subdomain]
        if len(matches) > 1:
            raise ValueError(
                f"Cluster '{cluster}' is ambiguous ({len(matches)} items). "
                "Narrow with --subdomain or --index."
            )
        return matches[0]

    # --- By subdomain only ---
    if subdomain is not None:
        matches = [it for it in items if it.get("subdomain") == subdomain]
        if not matches:
            raise ValueError(f"No items for subdomain '{subdomain}'")
        if len(matches) > 1:
            raise ValueError(
                f"Subdomain '{subdomain}' matches {len(matches)} items. "
                "Narrow with --cluster or --index."
            )
        return matches[0]

    raise ValueError("Provide at least one of: index, cluster, or subdomain")


def _make_slug(cluster: str, family: str, platform: str) -> str:
    """Build slug from cluster name.  e.g. 'tables' -> 'font-tables-in-python'."""
    return f"{family}-{cluster}-in-{platform}"


def _infer_target_path(
    candidate: dict, family: str, platform: str
) -> str | None:
    """Infer the content target path for a candidate (relative to repo root)."""
    subdomain = candidate.get("subdomain", "")
    template = _TARGET_TEMPLATES.get(subdomain)
    if not template:
        return None
    cluster = candidate.get("cluster", "unknown")
    slug = _make_slug(cluster, family, platform)
    # docs needs a section — use cluster as section placeholder
    section = cluster
    return template.format(
        family=family, platform=platform, slug=slug, section=section,
    )


def build_skill_invocation(candidate: dict, family: str, platform: str) -> str:
    """Build the skill command string.

    Example: '/new-blog-post font python vendor-blog'
    """
    action = candidate.get("action", "")
    skill = ACTION_TO_SKILL.get(action)
    if not skill:
        return f"# No skill mapped for action '{action}'"
    cluster = candidate.get("cluster", "unknown")
    return f"{skill} {family} {platform} {cluster}"


def preflight_check(candidate: dict, family: str, platform: str) -> dict:
    """Run preflight: knowledge exists, clone cache exists, target path check.

    Returns {"passed": bool, "issues": [...], "warnings": [...]}.
    """
    issues: list[str] = []
    warnings: list[str] = []

    # 1. Knowledge model must exist
    model_path = (
        _REPO_ROOT / "knowledge" / family / platform / "merged" / "model.yaml"
    )
    if not model_path.exists():
        issues.append(f"Knowledge model missing: {model_path.relative_to(_REPO_ROOT)}")

    # 2. Clone cache should exist
    cache_dir = _REPO_ROOT / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
    if not cache_dir.exists():
        warnings.append(
            f"Clone cache missing: {cache_dir.relative_to(_REPO_ROOT)} "
            "(skill may re-clone)"
        )

    # 3. Target path check
    action = candidate.get("action", "")
    target_rel = _infer_target_path(candidate, family, platform)
    if target_rel:
        target_abs = _REPO_ROOT / target_rel
        is_create = action.startswith("create_new")
        is_update = action.startswith("update_existing")
        if is_create and target_abs.exists():
            issues.append(
                f"Target already exists (create blocked): {target_rel}"
            )
        if is_update and not target_abs.exists():
            warnings.append(
                f"Target not found for update (may use different slug): {target_rel}"
            )

    passed = len(issues) == 0
    return {"passed": passed, "issues": issues, "warnings": warnings}


def list_candidates(
    manifest: dict, *, subdomain_filter: str | None = None
) -> str:
    """Return formatted table of all candidates."""
    items = manifest.get("manifest_items", [])
    if subdomain_filter:
        items = [it for it in items if it.get("subdomain") == subdomain_filter]

    if not items:
        return "(no candidates)"

    # Header
    lines = [
        f"{'Idx':<5} {'Cluster':<20} {'Action':<30} {'Subdomain':<20} {'Score':<6}",
        f"{'---':<5} {'---':<20} {'---':<30} {'---':<20} {'---':<6}",
    ]
    for i, it in enumerate(manifest.get("manifest_items", [])):
        if subdomain_filter and it.get("subdomain") != subdomain_filter:
            continue
        lines.append(
            f"{i:<5} {it.get('cluster', '?'):<20} {it.get('action', '?'):<30} "
            f"{it.get('subdomain', '?'):<20} {it.get('score', 0):<6.3f}"
        )
    lines.append(f"\nTotal: {len(items)} candidate(s)")
    return "\n".join(lines)
