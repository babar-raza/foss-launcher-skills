"""
changelog_grounding.py — MT036-2026-08-21 (PDF/Java Maven publish hardening, gap G5).

Builds a structured, evidence-grounded CHANGELOG.md entry (Added / Changed / Fixed /
Deprecated / Removed / Compatibility / Migration) for a Java-FOSS product republication,
and validates it before it may ever reach a real CHANGELOG.md commit.

Deliberately NOT a diff engine. This repo already has one: semantic_diff.py (S-104)
converts knowledge_delta.json into typed, evidence-cited change objects
(reports/refresh_review/{family}/{platform}/semantic_changes.json) -- every object
carries a real symbol (class name or claim_id) and evidence_paths pointing at the
knowledge artifact it came from. This module is purely a consumer/formatter/validator
on top of that existing, already-grounded output -- reusing it is the whole point (see
skills/foss-java-publish.md Step A9a: "reuse this repo's own existing, evidence-grounded
extraction machinery... never free-generate changelog content from a raw git log").

Grounding discipline (AGENTS.md 5/11, mirrored here for release notes): every Added/
Changed/Removed line must cite a real `symbol` present in the semantic_changes.json
input. GitHub's own `gh release create --generate-notes` text is never treated as an
input to this module or as a substitute for its output.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.knowledge.changelog_grounding \\
        pdf java --previous-version 26.6.0 --new-version 26.8.0 \\
        --group-id org.aspose --artifact-id aspose-pdf-foss
"""

from __future__ import annotations

import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import json
import re
from datetime import datetime, timezone
from typing import Any

# ── Change-type -> changelog-category mapping ───────────────────────────────
# semantic_diff.py's change_type constants, mapped onto Added/Changed/Removed/
# Compatibility. There is no DEPRECATED signal in semantic_diff.py's output today
# (it has no concept of "still present but scheduled for removal") -- that category
# stays empty unless a future extension of semantic_diff.py adds one; never
# fabricated here to fill the section.

_ADDED_TYPES = {"API_ADDED", "API_RESURRECTED", "FEATURE_ADDED"}
_CHANGED_TYPES = {"API_MODIFIED", "BEHAVIOR_CHANGED", "CLAIM_MODIFIED", "LIMITATION_CHANGED"}
_REMOVED_TYPES = {"API_REMOVED", "FEATURE_REMOVED"}
_BREAKING_TYPES = {"API_REMOVED", "API_SIGNATURE_CHANGED", "API_RENAMED"}

_CATEGORY_ORDER = ("Added", "Changed", "Fixed", "Deprecated", "Removed")

# Heading of the section that holds events semantic_diff.py flagged ``verify_against_source``
# (a removal/modification seen across an extractor change, so it may be extractor noise).
# Such events never enter a category, ``breaking_changes`` or ``migration_guidance``.
UNCONFIRMED_HEADING = "Unconfirmed (verify against source before publishing)"

# ── Marketing-language rejection list ────────────────────────────────────────
# Not exhaustive by design -- a cheap, high-precision heuristic gate, not an NLP
# classifier. Extend if a real draft slips an obvious unsupported claim through.
_MARKETING_PHRASES = (
    "blazing fast", "blazingly fast", "revolutionary", "industry-leading",
    "industry leading", "best-in-class", "best in class", "seamless",
    "seamlessly", "cutting-edge", "cutting edge", "world-class", "world class",
    "game-changing", "game changing", "unmatched", "unparalleled",
    "next-generation", "next generation", "state-of-the-art",
)

_cfg_reports_root: str = "reports/refresh_review"


def configure(reports_root: "str | None" = None) -> None:
    """Override path roots for testing (configure() seam, AGENTS.md 16)."""
    global _cfg_reports_root
    if reports_root is not None:
        _cfg_reports_root = reports_root


def load_semantic_changes(family: str, platform: str) -> list[dict[str, Any]]:
    """Load semantic_diff.py's output for this product.

    Raises FileNotFoundError with an actionable message if /knowledge-diff (or a
    direct semantic_diff.py run) hasn't produced it yet -- this module never
    silently falls back to an empty or fabricated change list.
    """
    path = Path(_cfg_reports_root) / family / platform / "semantic_changes.json"
    if not path.exists():
        raise FileNotFoundError(
            f"semantic_changes.json not found at {path}. Run "
            f"`/knowledge-diff {family} {platform}` (or "
            f"`commands.knowledge.semantic_diff {family} {platform}` directly) first -- "
            "this module never generates changelog content without real, evidence-backed "
            "change data."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_changelog_draft(
    changes: list[dict[str, Any]],
    *,
    family: str,
    platform: str,
    previous_version: str,
    new_version: str,
    group_id: str,
    artifact_id: str,
    released_at: "str | None" = None,
) -> dict[str, Any]:
    """Build a structured changelog draft from semantic_diff.py's typed change objects.

    Only USER_VISIBLE changes are included -- INTERNAL_ONLY changes are real per
    semantic_diff.py's own classification, but noise for a Maven Central consumer
    reading a public changelog; they remain fully visible in semantic_changes.json
    for anyone who needs the complete picture.

    Every entry line carries the change's real `symbol` and `change_id` so the
    validator (and any human reviewer) can trace it back to semantic_changes.json,
    and transitively to the knowledge_delta.json evidence semantic_diff.py itself cites.
    """
    released_at = released_at or datetime.now(timezone.utc).date().isoformat()

    categories: dict[str, list[dict[str, Any]]] = {c: [] for c in _CATEGORY_ORDER}
    breaking: list[dict[str, Any]] = []
    unconfirmed: list[dict[str, Any]] = []

    for change in changes:
        if change.get("public_impact") != "USER_VISIBLE":
            continue
        change_type = change.get("change_type")
        entry = {
            "symbol": change.get("symbol"),
            "symbol_kind": change.get("symbol_kind"),
            "change_id": change.get("change_id"),
            "evidence_paths": change.get("evidence_paths", []),
        }
        if change.get("verify_against_source"):
            # Unverified (extractor changed/unknown): a human must confirm against source
            # before this is published. Never a category line, never "breaking"/migration.
            entry["change_type"] = change_type
            for key in ("enum_members_added", "enum_members_removed"):
                if change.get(key):
                    entry[key] = list(change[key])
            unconfirmed.append(entry)
            continue
        if change.get("symbol_kind") == "enum" and change_type == "FEATURE_ADDED":
            # An enum-level event is a constant added to a PRE-EXISTING type -- not a new type.
            entry["constants_added"] = list(change.get("enum_members_added") or [])
            entry["label"] = f"constant added to {change.get('symbol')}"
        if change_type in _ADDED_TYPES:
            categories["Added"].append(entry)
        elif change_type in _CHANGED_TYPES:
            categories["Changed"].append(entry)
        elif change_type in _REMOVED_TYPES:
            categories["Removed"].append(entry)
        if change_type in _BREAKING_TYPES:
            breaking.append(entry)

    return {
        "family": family,
        "platform": platform,
        "previous_version": previous_version,
        "new_version": new_version,
        "released_at": released_at,
        "maven": {
            "group_id": group_id,
            "artifact_id": artifact_id,
            "install_snippet": (
                f"<dependency>\n  <groupId>{group_id}</groupId>\n"
                f"  <artifactId>{artifact_id}</artifactId>\n"
                f"  <version>{new_version}</version>\n</dependency>"
            ),
        },
        "categories": categories,
        "unconfirmed": unconfirmed,
        "breaking_changes": breaking,
        "migration_guidance": [
            f"`{e['symbol']}` changed in a way that may require code changes — see "
            f"{', '.join(e['evidence_paths']) or 'the knowledge model'} for the exact delta."
            for e in breaking
        ],
    }


def validate_changelog_draft(
    draft: dict[str, Any], changes: list[dict[str, Any]]
) -> list[str]:
    """Return a list of violation strings; empty list == valid.

    Checks, in order:
    1. Every cited symbol in every category traces to a real entry in `changes`
       (catches a fabricated or hand-edited-in claim that was never in the grounded
       source data).
    2. No banned marketing phrase anywhere in the draft's free text.
    3. Maven coordinates + install snippet present.
    4. At least one category is non-empty, OR this is explicitly an initial release
       (previous_version is None) -- an empty draft for a real republish is itself
       a sign something upstream failed silently, not a valid "nothing changed" state.
    """
    violations: list[str] = []
    real_symbols = {c.get("symbol") for c in changes if c.get("symbol")}

    for category, entries in draft.get("categories", {}).items():
        for entry in entries:
            symbol = entry.get("symbol")
            if symbol not in real_symbols:
                violations.append(
                    f"{category}: symbol '{symbol}' (change_id={entry.get('change_id')}) "
                    "is not present in the source semantic_changes.json data -- "
                    "uncited/fabricated claim, must be removed or corrected."
                )
            if not entry.get("evidence_paths"):
                violations.append(
                    f"{category}: symbol '{symbol}' has no evidence_paths -- "
                    "every line must trace to a real knowledge artifact."
                )

    for entry in draft.get("unconfirmed", []) or []:
        if entry.get("symbol") not in real_symbols:
            violations.append(
                f"Unconfirmed: symbol '{entry.get('symbol')}' (change_id={entry.get('change_id')}) "
                "is not present in the source semantic_changes.json data."
            )

    draft_text = json.dumps(draft).lower()
    for phrase in _MARKETING_PHRASES:
        if phrase in draft_text:
            violations.append(f"Unsupported marketing language found: '{phrase}'")

    maven = draft.get("maven") or {}
    if not maven.get("group_id") or not maven.get("artifact_id") or not maven.get("install_snippet"):
        violations.append("Maven coordinates / install snippet section is missing or incomplete.")

    total_entries = sum(len(v) for v in draft.get("categories", {}).values())
    if total_entries == 0 and draft.get("previous_version"):
        violations.append(
            "Changelog draft is empty for a republish (previous_version is set) -- "
            "either no USER_VISIBLE changes were found (verify this is expected, not a "
            "silent upstream failure) or semantic_changes.json itself needs regenerating."
        )

    return violations


def format_markdown(draft: dict[str, Any]) -> str:
    """Render a validated draft as the Markdown block to prepend to CHANGELOG.md.

    Caller is responsible for validating first (validate_changelog_draft) -- this
    function does not re-validate, it only formats.
    """
    lines = [f"## {draft['new_version']} — {draft['released_at']}", ""]

    for category in _CATEGORY_ORDER:
        entries = draft["categories"].get(category, [])
        if not entries:
            continue
        lines.append(f"### {category}")
        for e in entries:
            evidence = f" ({', '.join(e['evidence_paths'])})" if e.get("evidence_paths") else ""
            if e.get("label"):  # enum-constant addition: say what was actually added, and where
                constants = e.get("constants_added") or []
                if constants:
                    for const in constants:
                        lines.append(f"- `{const}` — {e['label']}{evidence}")
                else:
                    lines.append(f"- {e['label']}{evidence}")
            else:
                lines.append(f"- `{e['symbol']}`{evidence}")
        lines.append("")

    if draft.get("breaking_changes"):
        lines.append("### Compatibility")
        for e in draft["breaking_changes"]:
            lines.append(f"- `{e['symbol']}` — potentially breaking, see Migration below")
        lines.append("")

    if draft.get("migration_guidance"):
        lines.append("### Migration")
        for line in draft["migration_guidance"]:
            lines.append(f"- {line}")
        lines.append("")

    if draft.get("unconfirmed"):
        lines.append(f"### {UNCONFIRMED_HEADING}")
        for e in draft["unconfirmed"]:
            evidence = f" ({', '.join(e['evidence_paths'])})" if e.get("evidence_paths") else ""
            detail = ""
            if e.get("enum_members_removed"):
                detail = f" — constants possibly removed: {', '.join(f'`{c}`' for c in e['enum_members_removed'])}"
            elif e.get("enum_members_added"):
                detail = f" — constants possibly added: {', '.join(f'`{c}`' for c in e['enum_members_added'])}"
            lines.append(f"- `{e['symbol']}` ({e.get('change_type')}){detail}{evidence}")
        lines.append("")

    maven = draft["maven"]
    lines.append("### Maven Coordinates")
    lines.append("")
    lines.append("```xml")
    lines.append(maven["install_snippet"])
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="changelog_grounding",
        description="Build and validate an evidence-grounded CHANGELOG.md entry from semantic_diff.py's output.",
    )
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--previous-version", required=True)
    parser.add_argument("--new-version", required=True)
    parser.add_argument("--group-id", default="org.aspose")
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--output", metavar="PATH", help="Write the validated Markdown to this path instead of stdout")
    args = parser.parse_args(argv)

    changes = load_semantic_changes(args.family, args.platform)
    draft = build_changelog_draft(
        changes,
        family=args.family,
        platform=args.platform,
        previous_version=args.previous_version,
        new_version=args.new_version,
        group_id=args.group_id,
        artifact_id=args.artifact_id,
    )

    violations = validate_changelog_draft(draft, changes)
    if violations:
        print("changelog_grounding: VALIDATION FAILED", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    body = format_markdown(draft)
    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
