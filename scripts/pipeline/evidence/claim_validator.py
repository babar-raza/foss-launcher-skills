"""claim_validator.py — Stale/orphan claim and api reference detection without mutation.

Detects claim IDs in evidence frontmatter that are no longer present in the
knowledge model (merged/claims.json), and api entries whose class names are no
longer present in the knowledge model (merged/api_surface.json).
All operations are read-only: no content files are written.

Public API:
    detect_stale_claims(filepath, knowledge) -> list[str]
    report_stale_claims(family, platform, subdomain=None) -> dict
    detect_stale_apis(filepath, knowledge) -> list[str]
    report_stale_apis(family, platform, subdomain=None) -> dict

CLI usage (via attach_evidence.py):
    attach_evidence cells java --detect-stale-claims
    attach_evidence cells java --detect-stale-claims --subdomain reference.aspose.org
    attach_evidence cells java --detect-stale-claims --report-json out.json
"""
from __future__ import annotations

import sys
from pathlib import Path

# sibling-import guard
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from content_discovery import discover_content, _infer_subdomain  # noqa: E402
from core.markdown import parse_frontmatter  # noqa: E402


def detect_stale_claims(filepath: "Path | str", knowledge) -> list[str]:
    """Return claim IDs in evidence.claims not present in knowledge.claim_ids.

    Args:
        filepath: Path to a content .md file.
        knowledge: A loaded Knowledge object (must have .claim_ids set).

    Returns:
        List of stale claim ID strings. Empty list when all claims are current.
    """
    fm = parse_frontmatter(Path(filepath))
    evidence = fm.get("evidence") or {}
    if not isinstance(evidence, dict):
        return []
    page_claims = evidence.get("claims", [])
    if not isinstance(page_claims, list):
        return []
    known = knowledge.claim_ids
    return [c for c in page_claims if isinstance(c, str) and c not in known]


def report_stale_claims(
    family: str,
    platform: str,
    subdomain: str | None = None,
) -> dict:
    """Scan all content files and return a stale-claim report. Never writes.

    Args:
        family: Product family (e.g. "cells").
        platform: Product platform (e.g. "java").
        subdomain: When set, restrict scan to this canonical subdomain only.

    Returns:
        {
            "family": str,
            "platform": str,
            "subdomain": str | None,
            "total_files_scanned": int,
            "files_with_stale_claims": int,
            "total_stale_claims": int,
            "stale": { "<filepath>": ["<stale_claim_id>", ...], ... }
        }
    """
    from knowledge_core import Knowledge  # noqa: E402 (avoid circular at module level)

    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        return {
            "family": family,
            "platform": platform,
            "subdomain": subdomain,
            "error": f"No knowledge model available for {family}/{platform}",
            "total_files_scanned": 0,
            "files_with_stale_claims": 0,
            "total_stale_claims": 0,
            "stale": {},
        }

    files = discover_content(family, platform)
    if subdomain is not None:
        files = [f for f in files if _infer_subdomain(f) == subdomain]

    stale_map: dict[str, list[str]] = {}
    for f in files:
        stale = detect_stale_claims(f, knowledge)
        if stale:
            stale_map[str(f)] = stale

    return {
        "family": family,
        "platform": platform,
        "subdomain": subdomain,
        "total_files_scanned": len(files),
        "files_with_stale_claims": len(stale_map),
        "total_stale_claims": sum(len(v) for v in stale_map.values()),
        "stale": stale_map,
    }


def detect_stale_apis(filepath: "Path | str", knowledge) -> list[str]:
    """Return api entries in evidence.apis whose class names are absent from the knowledge model.

    Validates class-name presence only (not member-level). This is a lighter check
    than evidence_verifier.py's full audit validation — use this for standalone stale
    detection without running a full audit.

    Args:
        filepath: Path to a content .md file.
        knowledge: A loaded Knowledge object (must have .classes attribute —
                   a set or dict of class names).

    Returns:
        List of stale api entry strings (e.g. "UnknownClass.method"). Empty list when
        all class names are present in the knowledge model.
    """
    fm = parse_frontmatter(Path(filepath))
    evidence = fm.get("evidence") or {}
    if not isinstance(evidence, dict):
        return []
    page_apis = evidence.get("apis", [])
    if not isinstance(page_apis, list):
        return []
    known_classes = knowledge.classes
    stale = []
    for api_ref in page_apis:
        if not isinstance(api_ref, str) or not api_ref:
            continue
        cls_name = api_ref.split(".")[0]
        if cls_name not in known_classes:
            stale.append(api_ref)
    return stale


def report_stale_apis(
    family: str,
    platform: str,
    subdomain: str | None = None,
) -> dict:
    """Scan all content files and return a stale-api report. Never writes.

    Args:
        family: Product family (e.g. "cells").
        platform: Product platform (e.g. "java").
        subdomain: When set, restrict scan to this canonical subdomain only.

    Returns:
        {
            "family": str,
            "platform": str,
            "subdomain": str | None,
            "total_files_scanned": int,
            "files_with_stale_apis": int,
            "total_stale_apis": int,
            "stale": { "<filepath>": ["<stale_api_entry>", ...], ... }
        }
    """
    from knowledge_core import Knowledge  # noqa: E402 (avoid circular at module level)

    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        return {
            "family": family,
            "platform": platform,
            "subdomain": subdomain,
            "error": f"No knowledge model available for {family}/{platform}",
            "total_files_scanned": 0,
            "files_with_stale_apis": 0,
            "total_stale_apis": 0,
            "stale": {},
        }

    files = discover_content(family, platform)
    if subdomain is not None:
        files = [f for f in files if _infer_subdomain(f) == subdomain]

    stale_map: dict[str, list[str]] = {}
    for f in files:
        stale = detect_stale_apis(f, knowledge)
        if stale:
            stale_map[str(f)] = stale

    return {
        "family": family,
        "platform": platform,
        "subdomain": subdomain,
        "total_files_scanned": len(files),
        "files_with_stale_apis": len(stale_map),
        "total_stale_apis": sum(len(v) for v in stale_map.values()),
        "stale": stale_map,
    }
