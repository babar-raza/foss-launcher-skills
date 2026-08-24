"""
semantic_diff.py — S-104: Convert knowledge_delta.json into typed semantic change objects.

Input:  knowledge/{family}/{platform}/merged/knowledge_delta.json
Output: reports/refresh_review/{family}/{platform}/semantic_changes.json

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.knowledge.semantic_diff pdf net
    PYTHONPATH=scripts/pipeline python -m commands.knowledge.semantic_diff pdf net \
        --output reports/refresh_review/pdf/net/semantic_changes.json

Knowledge-delta schema (C-001: the *_apis/*_claims arrays are plain strings,
not objects -- Task 17 (§9.12) added two new, additive lookup dicts alongside
them rather than changing that shape):
    {
      "base_sha": "...", "current_sha": "...",
      "new_apis": ["ClassName"], "removed_apis": ["ClassName"],
      "modified_apis": ["ClassName"], "resurrected_apis": ["ClassName"],
      "new_claims": ["CLM-..."], "removed_claims": ["CLM-..."],
      "modified_claims": ["CLM-..."],
      "claim_text_changes": {"CLM-...": {"old_text": "...|null", "new_text": "...|null"}},
      "api_signature_changes": {"ClassName": {"added_methods": [...], "removed_methods": [...],
                                               "added_properties": [...], "removed_properties": [...]}}
    }
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import json
import re
from typing import Any

# ── Change type constants ───────────────────────────────────────────────────

# API change types
API_REMOVED = "API_REMOVED"
API_ADDED = "API_ADDED"
API_RESURRECTED = "API_RESURRECTED"
API_MODIFIED = "API_MODIFIED"
API_SIGNATURE_CHANGED = "API_SIGNATURE_CHANGED"
API_RENAMED = "API_RENAMED"

# Claim change types
FEATURE_REMOVED = "FEATURE_REMOVED"
FEATURE_ADDED = "FEATURE_ADDED"
FEATURE_CHANGED = "FEATURE_CHANGED"
BEHAVIOR_CHANGED = "BEHAVIOR_CHANGED"
LIMITATION_CHANGED = "LIMITATION_CHANGED"
CLAIM_MODIFIED = "CLAIM_MODIFIED"

# Public impact
USER_VISIBLE = "USER_VISIBLE"
INTERNAL_ONLY = "INTERNAL_ONLY"
UNKNOWN_VISIBILITY = "UNKNOWN_VISIBILITY"

# Content impact
BODY_UPDATE = "BODY_UPDATE"
REVIEW_ONLY = "REVIEW_ONLY"
NO_ACTION = "NO_ACTION"

# ── Configurable defaults (can be overridden in tests via configure()) ──────

_cfg_knowledge_root: str = "knowledge"
_cfg_reports_root: str = "reports/refresh_review"


def configure(
    knowledge_root: str | None = None,
    reports_root: str | None = None,
) -> None:
    """Override path roots for testing."""
    global _cfg_knowledge_root, _cfg_reports_root
    if knowledge_root is not None:
        _cfg_knowledge_root = knowledge_root
    if reports_root is not None:
        _cfg_reports_root = reports_root


# ── Core logic ─────────────────────────────────────────────────────────────

def _read_delta(family: str, platform: str) -> dict:
    """Read knowledge_delta.json for the given product."""
    path = Path(_cfg_knowledge_root) / family / platform / "merged" / "knowledge_delta.json"
    if not path.exists():
        raise FileNotFoundError(
            f"knowledge_delta.json not found at {path}. "
            "Run refresh_knowledge.py first."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_INTERNAL_PATTERNS = re.compile(
    r"^(Internal|Private|Abstract|Base|Impl|Stub|Mock|Helper|"
    r"Factory|Builder|Adapter|Proxy|Handler|Delegate|Callback|"
    r"EventArgs|Exception|Error|Token|Node|Visitor|"
    r"I[A-Z])",  # interfaces are user-visible — reconsider if needed
    re.IGNORECASE,
)


def _classify_api_visibility(class_name: str) -> str:
    """Heuristic: is this class name likely user-visible?"""
    # Interfaces starting with I + uppercase are public contracts
    if re.match(r"^I[A-Z]", class_name):
        return USER_VISIBLE
    # Internal-pattern classes
    if re.match(r"^(Internal|Impl|Stub|Mock|Helper|Factory|Builder|"
                r"Adapter|Proxy|Handler|Delegate|EventArgs|"
                r"Node|Visitor|Token).*", class_name, re.IGNORECASE):
        return INTERNAL_ONLY
    return USER_VISIBLE


def _classify_api_change(class_name: str, delta: dict) -> dict:
    """Produce a typed change object for an API (class) change."""
    removed = delta.get("removed_apis", [])
    added = delta.get("new_apis", [])

    if class_name in removed:
        change_type = API_REMOVED
    elif class_name in added:
        change_type = API_ADDED
    elif class_name in delta.get("resurrected_apis", []):
        change_type = API_RESURRECTED
    elif class_name in delta.get("modified_apis", []):
        change_type = API_MODIFIED
    else:
        change_type = API_MODIFIED  # fallback

    visibility = _classify_api_visibility(class_name)

    # Determine content impact
    if visibility == INTERNAL_ONLY:
        content_impact = NO_ACTION
    elif change_type in (API_REMOVED, API_ADDED, API_RESURRECTED):
        content_impact = BODY_UPDATE
    elif change_type in (API_MODIFIED, API_SIGNATURE_CHANGED, API_RENAMED):
        content_impact = BODY_UPDATE
    else:
        content_impact = REVIEW_ONLY

    confidence = 0.95 if visibility == USER_VISIBLE else 0.60

    result = {
        "change_type": change_type,
        "symbol": class_name,
        "symbol_kind": "class",
        "public_impact": visibility,
        "content_impact": content_impact,
        "confidence": confidence,
    }
    # Task 17 (§9.12): expose the structured signature diff for review/matrix
    # consumers (refresh_knowledge.py's _write_knowledge_delta, Task 17) --
    # only present for a real method/property name-set change, not every
    # modified_apis entry (e.g. an ERC-doc-coverage-only change has none).
    sig_change = (delta.get("api_signature_changes", {}) or {}).get(class_name)
    if sig_change:
        result["signature_summary"] = sig_change
    return result


_CLM_FEATURE_PATTERN = re.compile(r"CLM-[a-z]+-[a-f0-9]+")
_BEHAVIOR_KEYWORDS = ("behavior", "behav", "output", "result", "return")
_LIMITATION_KEYWORDS = ("limit", "restrict", "not support", "unsupport", "cannot", "does not")
_FEATURE_KEYWORDS = ("support", "can ", "allow", "enabl", "convert", "export", "import")


def _classify_claim_change(claim_id: str, delta: dict) -> dict:
    """Produce a typed change object for a claim change.

    Task 17 (§9.12, closes the other half of G10): sub-classification now
    matches keywords against the claim's real TEXT (delta["claim_text_changes"],
    written by refresh_knowledge.py's _write_knowledge_delta, Task 17) instead
    of the opaque claim_id string -- a hash like "CLM-pdf-a1b2c3" can never
    contain a word like "deprecated" or "not supported", so this branch was
    previously dead code in practice, always falling through to the generic
    CLAIM_MODIFIED bucket. Also wires up _FEATURE_KEYWORDS (defined since this
    module's introduction but never referenced anywhere before this fix) as a
    third sub-classification, producing FEATURE_CHANGED for the first time.
    Falls back to the old ID-based (non-)match, never crashing, for a
    knowledge_delta.json written before this field existed (older, pre-Task-17
    knowledge models) -- classification is simply less precise there, exactly
    the pre-existing behavior.
    """
    removed = delta.get("removed_claims", [])
    added = delta.get("new_claims", [])
    modified = delta.get("modified_claims", [])
    text_changes = delta.get("claim_text_changes", {}) or {}

    entry = text_changes.get(claim_id, {})
    reference_text = (entry.get("new_text") or entry.get("old_text") or claim_id).lower()

    if claim_id in removed:
        change_type = FEATURE_REMOVED
        content_impact = BODY_UPDATE
    elif claim_id in added:
        change_type = FEATURE_ADDED
        content_impact = BODY_UPDATE
    elif claim_id in modified:
        # Sub-classification from the claim's real text (falls back to the
        # claim_id string itself when no knowledge_delta.json text entry
        # exists -- matches this branch's pre-Task-17 behavior exactly).
        if any(k in reference_text for k in _BEHAVIOR_KEYWORDS):
            change_type = BEHAVIOR_CHANGED
        elif any(k in reference_text for k in _LIMITATION_KEYWORDS):
            change_type = LIMITATION_CHANGED
        elif any(k in reference_text for k in _FEATURE_KEYWORDS):
            change_type = FEATURE_CHANGED
        else:
            change_type = CLAIM_MODIFIED
        content_impact = BODY_UPDATE
    else:
        change_type = CLAIM_MODIFIED
        content_impact = REVIEW_ONLY

    result = {
        "change_type": change_type,
        "symbol": claim_id,
        "symbol_kind": "claim",
        "public_impact": USER_VISIBLE,
        "content_impact": content_impact,
        "confidence": 0.80,
    }
    if entry:
        result["old_text"] = entry.get("old_text")
        result["new_text"] = entry.get("new_text")
    return result


def _build_changes(family: str, platform: str, delta: dict) -> list[dict]:
    """Convert raw delta arrays into typed change objects."""
    changes = []
    base_sha = delta.get("base_sha", "")
    current_sha = delta.get("current_sha", "")
    evidence = [f"knowledge/{family}/{platform}/merged/knowledge_delta.json"]

    change_counter = 0

    def _make_change(base: dict) -> dict:
        nonlocal change_counter
        change_counter += 1
        return {
            "change_id": f"CHG-{family}-{platform}-{change_counter:04d}",
            "family": family,
            "platform": platform,
            "base_sha": base_sha,
            "current_sha": current_sha,
            "evidence_paths": evidence,
            **base,
        }

    # API changes
    for cls in delta.get("removed_apis", []):
        changes.append(_make_change(_classify_api_change(cls, delta)))
    for cls in delta.get("new_apis", []):
        changes.append(_make_change(_classify_api_change(cls, delta)))
    for cls in delta.get("resurrected_apis", []):
        changes.append(_make_change(_classify_api_change(cls, delta)))
    for cls in delta.get("modified_apis", []):
        changes.append(_make_change(_classify_api_change(cls, delta)))

    # Claim changes
    for clm in delta.get("removed_claims", []):
        changes.append(_make_change(_classify_claim_change(clm, delta)))
    for clm in delta.get("new_claims", []):
        changes.append(_make_change(_classify_claim_change(clm, delta)))
    for clm in delta.get("modified_claims", []):
        changes.append(_make_change(_classify_claim_change(clm, delta)))

    return changes


def _write_semantic_changes(changes: list[dict], output_path: Path) -> None:
    """Write changes list as JSON to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(changes, f, indent=2)


def run(family: str, platform: str, output: str | None = None) -> list[dict]:
    """
    Main logic entry point (importable by tests and CLI).

    Returns the list of typed change objects.
    """
    delta = _read_delta(family, platform)
    changes = _build_changes(family, platform, delta)

    if output:
        out_path = Path(output)
    else:
        out_path = (
            Path(_cfg_reports_root)
            / family
            / platform
            / "semantic_changes.json"
        )

    _write_semantic_changes(changes, out_path)
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "semantic_diff — S-104: Convert knowledge_delta.json into typed semantic "
            "change objects for the body refresh pipeline."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=scripts/pipeline python -m commands.knowledge.semantic_diff pdf net
  PYTHONPATH=scripts/pipeline python -m commands.knowledge.semantic_diff 3d java
  PYTHONPATH=scripts/pipeline python -m commands.knowledge.semantic_diff pdf net \\
      --output reports/refresh_review/pdf/net/semantic_changes.json

Output schema per change object:
  change_id        — unique ID (CHG-{family}-{platform}-NNNN)
  change_type      — API_REMOVED | API_ADDED | API_MODIFIED | API_SIGNATURE_CHANGED |
                     FEATURE_REMOVED | FEATURE_ADDED | BEHAVIOR_CHANGED | CLAIM_MODIFIED
  symbol           — class name or claim ID
  symbol_kind      — "class" | "claim"
  public_impact    — USER_VISIBLE | INTERNAL_ONLY
  content_impact   — BODY_UPDATE | REVIEW_ONLY | NO_ACTION
  confidence       — float 0.0–1.0
  evidence_paths   — list of source files
        """,
    )
    parser.add_argument("family", help="Product family (e.g. pdf, 3d, cells)")
    parser.add_argument("platform", help="Platform (e.g. net, java, python)")
    parser.add_argument(
        "--output",
        default=None,
        help="Override output path (default: reports/refresh_review/{family}/{platform}/semantic_changes.json)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print change summary to stdout",
    )
    args = parser.parse_args()

    try:
        changes = run(args.family, args.platform, args.output)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.summary or True:  # always print summary
        by_type: dict[str, int] = {}
        body_update = 0
        for c in changes:
            by_type[c["change_type"]] = by_type.get(c["change_type"], 0) + 1
            if c["content_impact"] == BODY_UPDATE:
                body_update += 1

        out_path = args.output or f"reports/refresh_review/{args.family}/{args.platform}/semantic_changes.json"
        print(f"semantic_diff: {args.family}/{args.platform}")
        print(f"  total changes : {len(changes)}")
        print(f"  body_update   : {body_update}")
        print(f"  by type       : {dict(sorted(by_type.items()))}")
        print(f"  output        : {out_path}")


if __name__ == "__main__":
    main()
