# Adapted from aspose.org scripts/pipeline/lib/ for standalone use
"""denominator_reconciler.py — Verify page count matches api_surface scope.

Compares the number of scope-eligible api_surface entries against the
number of generated reference pages on disk.  Produces a structured
reconciliation report with per-entry disposition.

Usage (library):
    from denominator_reconciler import reconcile

    report = reconcile("font", "python",
                       knowledge_root=Path("knowledge"),
                       content_root=Path("content"))
    assert report["denominator_gap"] == 0
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
_CMD_CONTENT = _PIPELINE_ROOT / "commands" / "content"
if str(_CMD_CONTENT) not in sys.path:
    sys.path.insert(0, str(_CMD_CONTENT))


def reconcile(
    family: str,
    platform: str,
    *,
    knowledge_root: Path,
    content_root: Path,
) -> dict:
    """Reconcile api_surface entries against generated pages.

    Returns a dict with keys:
        api_surface_total   — raw entry count in api_surface.json
        scope_eligible      — entries passing _passes_platform_scope
        scope_filtered      — entries excluded by scope rules
        pages_on_disk       — .md files in content dir (excluding _index.md)
        denominator_gap     — scope_eligible - pages_on_disk
        scope_filter_log    — list of {name, reason} for filtered entries
        missing_pages       — names in scope but no page on disk
        orphan_pages        — pages on disk with no api_surface entry
    """
    import batch_reference as br

    api_path = knowledge_root / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        return {
            "api_surface_total": 0,
            "scope_eligible": 0,
            "scope_filtered": 0,
            "pages_on_disk": 0,
            "denominator_gap": 0,
            "scope_filter_log": [],
            "missing_pages": [],
            "orphan_pages": [],
            "error": f"api_surface.json not found at {api_path}",
        }

    api_surface = json.loads(api_path.read_text(encoding="utf-8"))
    total = len(api_surface)

    # Determine scope-eligible entries
    eligible = []
    filtered_log = []
    for entry in api_surface:
        name = entry.get("name", "")
        if br._passes_platform_scope(entry, platform):
            eligible.append(entry)
        else:
            filtered_log.append({
                "name": name,
                "reason": _infer_filter_reason(entry, platform),
            })

    # Apply kind filter (all) and dedup — mirror batch_reference logic
    # We use "all" because the reconciler checks the full scope
    kind_filtered = br._apply_kind_filter(eligible, "all", platform)

    # Dedup by name (same logic as batch_reference)
    _VIS_RANK = {"exported": 3, "public": 2, "conventional": 1}
    seen: dict[str, int] = {}
    dedup = []
    for entry in kind_filtered:
        name = entry.get("name", "")
        rank = _VIS_RANK.get(entry.get("visibility", "conventional"), 1)
        if name in seen:
            prev_idx = seen[name]
            prev_rank = _VIS_RANK.get(dedup[prev_idx].get("visibility", "conventional"), 1)
            if rank > prev_rank:
                dedup[prev_idx] = entry
        else:
            seen[name] = len(dedup)
            dedup.append(entry)

    eligible_names = {e.get("name", "") for e in dedup}

    # Count pages on disk
    content_dir = content_root / "reference.aspose.org" / "en" / family / platform
    if content_dir.exists():
        page_files = [
            f for f in content_dir.glob("*.md")
            if f.name != "_index.md"
        ]
    else:
        page_files = []

    page_names = {f.stem for f in page_files}

    # Compute gaps
    missing = sorted(eligible_names - page_names)
    orphans = sorted(page_names - eligible_names)
    gap = len(eligible_names) - len(page_names)

    return {
        "api_surface_total": total,
        "scope_eligible": len(eligible_names),
        "scope_filtered": total - len(kind_filtered),
        "pages_on_disk": len(page_names),
        "denominator_gap": gap,
        "scope_filter_log": filtered_log,
        "missing_pages": missing,
        "orphan_pages": orphans,
    }


def _infer_filter_reason(entry: dict, platform: str) -> str:
    """Heuristic to explain why an entry was filtered."""
    name = entry.get("name", "")
    kind = entry.get("kind", "")
    file_path = entry.get("file", "")

    if platform == "python" and name.startswith("_"):
        return "underscore-prefixed (Python scope rule)"
    if platform == "cpp" and name.startswith("I") and name[1:2].isupper():
        return "I-prefixed interface excluded for C++"
    if "/internal/" in file_path or "\\internal\\" in file_path:
        return "internal package path"
    if platform == "java":
        from batch_reference import _JAVA_RETIRED_INTERNAL_CLASSES
        if name in _JAVA_RETIRED_INTERNAL_CLASSES:
            return "Java retired internal class"
    return f"scope filter ({platform})"
