"""
compare.py — Diff state vs expected; produce ordered action list.

Ingests discovery_result (from discover.py) and validation_result (from validate.py).
NO_ACTIONS_READY is a valid status (fresh repo) — not an error.

Action types:
  INVESTIGATE_MISSING_STATE — product missing model.yaml
  REFRESH_PRODUCT           — product with stale_since != null
  HEAL_PAGES                — Grade D/F pages
  ENRICH_PAGES              — Grade C pages
  HANDOFF_UPDATE            — session handoff (execute mode only)
  NO_ACTIONS_READY          — fresh repo, nothing to do

Exit 0 always (NO_ACTIONS_READY is valid). Exit 1 on fatal input errors.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT, base_args, safe_emit


def _read_backlog_priority(repo_root):
    """Read wave-0 active items from backlog/BACKLOG.md. Returns (ids, status_str)."""
    backlog_path = Path(repo_root) / "backlog" / "BACKLOG.md"
    if not backlog_path.exists():
        return [], "BACKLOG_ABSENT"
    try:
        text = backlog_path.read_text(encoding="utf-8")
        active_match = re.search(r"## Active.*?(?=\n## |\Z)", text, re.DOTALL)
        if not active_match:
            return [], "ACTIVE_SECTION_NOT_FOUND"
        ids = re.findall(r"\|\s*([A-Z][A-Z0-9-]+-\d+)\s*\|", active_match.group(0))
        return ids[:20], "BACKLOG_LOADED"
    except Exception as exc:
        return [], f"BACKLOG_READ_ERROR: {exc}"


def compare(discovery, validation, repo_root=None):
    root = Path(repo_root or REPO_ROOT)
    actions = []
    warnings = list(discovery.get("warnings", [])) + list(validation.get("warnings", []))

    # Missing model.yaml → INVESTIGATE
    for prod in discovery.get("missing_products", []):
        actions.append({
            "type": "INVESTIGATE_MISSING_STATE",
            "family": prod["family"],
            "platform": prod["platform"],
            "reason": prod.get("reason", "model.yaml missing"),
            "priority": 0,
            "skill_chain": "needs_skill_contract_discovery",
            "suggested_skills": [
                "/repo-scout {family} {platform}",
                "/knowledge-update {family} {platform}",
            ],
        })

    # Stale model.yaml → REFRESH
    for prod in discovery.get("stale_products", []):
        actions.append({
            "type": "REFRESH_PRODUCT",
            "family": prod["family"],
            "platform": prod["platform"],
            "reason": f"stale_since={prod.get('stale_since')}",
            "priority": 1,
            "skill_chain": "needs_skill_contract_discovery",
            "suggested_skills": [
                "/knowledge-diff {family} {platform}",
                "/knowledge-update {family} {platform}",
                "/delta-site-plan {family} {platform}",
                "/page-update {family} {platform}",
                "/batch-reference {family} {platform}",
                "/family-sync {family}",
                "/commit",
            ],
        })

    # Grade D/F → HEAL
    heal_pages = [p for p in validation.get("pages_needing_heal", [])
                  if p.get("grade") in ("D", "F")]
    if heal_pages:
        actions.append({
            "type": "HEAL_PAGES",
            "count": len(heal_pages),
            "pages": heal_pages[:10],
            "reason": f"{len(heal_pages)} Grade D/F pages need healing",
            "priority": 2,
            "skill_chain": "needs_skill_contract_discovery",
            "suggested_skills": ["/heal-page {family} {platform} {page}"],
        })

    # Grade C → ENRICH
    enrich_pages = [p for p in validation.get("pages_needing_heal", [])
                    if p.get("grade") == "C"]
    if enrich_pages:
        actions.append({
            "type": "ENRICH_PAGES",
            "count": len(enrich_pages),
            "pages": enrich_pages[:10],
            "reason": f"{len(enrich_pages)} Grade C pages need enrichment",
            "priority": 3,
            "skill_chain": "needs_skill_contract_discovery",
            "suggested_skills": ["/page-enhance {family} {platform} {page}"],
        })

    # Backlog priority weighting
    backlog_ids, backlog_status = _read_backlog_priority(root)

    # Sort by priority
    actions.sort(key=lambda a: a.get("priority", 99))

    status = "NO_ACTIONS_READY" if not actions else "ACTIONS_READY"

    return {
        "status": status,
        "actions": actions,
        "action_count": len(actions),
        "backlog_status": backlog_status,
        "backlog_priority_ids": backlog_ids,
        "warnings": warnings,
    }


def main():
    parser = base_args("Compare state vs expected; produce action list")
    parser.add_argument("--discovery", required=True, help="Path to discover.py output JSON")
    parser.add_argument("--validation", required=True, help="Path to validate.py output JSON")
    args = parser.parse_args()

    try:
        discovery = json.loads(Path(args.discovery).read_text(encoding="utf-8"))
        validation = json.loads(Path(args.validation).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FATAL: Could not load inputs: {exc}", file=sys.stderr)
        return 1

    data = compare(discovery, validation)

    if args.output:
        safe_emit(data, args.output)
        print(f"Compare complete: status={data['status']}, "
              f"actions={data['action_count']}")
        print(f"Written to {args.output}")
    else:
        print(json.dumps(data, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
