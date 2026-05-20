# Adapted from aspose.org
"""Deterministic pre-write change guard - validates proposed text against knowledge.

Checks proposed text for forbidden claim matches, API reference accuracy,
package/install accuracy, prerequisite accuracy, and format direction
consistency. Returns PASS/WARN/DENY.

Usage:
    python scripts/pipeline/commands/governance/change_guard.py {family} {platform} "proposed text"
    python scripts/pipeline/commands/governance/change_guard.py {family} {platform} --file path.md
    echo "text" | python scripts/pipeline/commands/governance/change_guard.py {family} {platform} --stdin

Exit codes:
    0  PASS - text consistent with knowledge
    1  WARN - no direct evidence, but no contradiction
    2  DENY - text contradicts known facts
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from knowledge_core import Knowledge  # noqa: E402
# Platform alias map -- inline fallback (foss does not have content_discovery)
PLATFORM_MAP: dict[str, str] = {}


_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent  # commands/governance/ -> commands/ -> pipeline/ -> scripts/ -> repo
_REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, KNOWLEDGE_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"


def _log(*args, **kwargs):
    """Print to stderr so stdout stays clean for --json."""
    print(*args, file=sys.stderr, **kwargs)


def _tokenize(text: str) -> set[str]:
    """Extract lowercase word tokens (3+ chars)."""
    return set(re.findall(r"[a-z][a-z0-9_]+", text.lower()))


_API_REF_RE = re.compile(r"`(\w+(?:\.\w+)*)`")
_FORMAT_CLAIM_RE = re.compile(
    r"(?:supports?|import|export|convert|load|save|read|write)\w*\s+"
    r"(?:the\s+)?(?:to\s+|from\s+)?(\w{2,6})\s+(?:format|file|document)",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_INSTALL_CLAIM_RE = re.compile(
    r"(?:pip|npm)\s+install\s+[`'\"]?([a-z0-9_.-]+)",
    re.IGNORECASE,
)
_FALSE_PREREQ_RE = re.compile(
    r"\b(?:requires?|needs?|depends on)\s+(?:microsoft\s+)?"
    r"(office|powerpoint|excel|word)\b",
    re.IGNORECASE,
)
_FC_API_RE = re.compile(r"supports?\s+(\w+)\.(\w+)", re.IGNORECASE)


def _load_forbidden_claims(family: str, platform: str) -> list[str]:
    index_path = KNOWLEDGE_ROOT / family / platform / "merged" / "index.json"
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return data.get("forbidden_claims", [])
    except (json.JSONDecodeError, KeyError):
        return []


def _load_formats(family: str, platform: str) -> list[dict]:
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "formats.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return []


_SAVE_FORMAT_RE = re.compile(r"SaveFormat\.(\w+)", re.IGNORECASE)


def _load_save_formats(family: str, platform: str) -> set[str]:
    """Extract save/export format names from claims.json.

    formats.json only contains input FileFormat entries. Save formats
    (SaveFormat.Pdf, SaveFormat.Html, etc.) live in claims.json. This
    function extracts them so the guard doesn't false-positive on
    legitimate export-format claims.
    """
    claims_path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not claims_path.exists():
        return set()
    try:
        data = json.loads(claims_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return set()
    save_fmts: set[str] = set()
    claims = data if isinstance(data, list) else data.get("claims", [])
    for claim in claims:
        text = claim.get("text", "") if isinstance(claim, dict) else str(claim)
        for m in _SAVE_FORMAT_RE.finditer(text):
            save_fmts.add(m.group(1).lower())
    return save_fmts


def _parse_not_implemented(forbidden: list[str]) -> set[tuple[str, str]]:
    """Extract (ClassName, member_name) pairs from forbidden_claims strings."""
    result: set[tuple[str, str]] = set()
    for fc in forbidden:
        match = _FC_API_RE.search(fc)
        if match:
            result.add((match.group(1), match.group(2)))
    return result


DECISION_PASS = "PASS"
DECISION_WARN = "WARN"
DECISION_DENY = "DENY"


def guard_text(text: str, family: str, platform: str) -> dict:
    """Validate proposed text against knowledge."""
    knowledge = Knowledge(family, platform)
    forbidden = _load_forbidden_claims(family, platform)
    formats_list = _load_formats(family, platform)

    forbidden_tokens = [(fc, _tokenize(fc)) for fc in forbidden if len(fc) > 2]
    not_implemented = _parse_not_implemented(forbidden)
    format_support: dict[str, str] = {}
    for fmt in formats_list:
        ext = (fmt.get("format") or fmt.get("ext") or fmt.get("extension") or "").lower()
        direction = (fmt.get("direction") or fmt.get("support") or "").lower()
        if ext:
            format_support[ext] = direction
    # Merge save/export formats from claims.json (formats.json only has input formats)
    for sf in _load_save_formats(family, platform):
        if sf not in format_support:
            format_support[sf] = "export"

    sentences = _SENTENCE_SPLIT_RE.split(text.strip())
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]

    issues: list[dict] = []
    overall = DECISION_PASS
    has_evidence = False

    for sentence in sentences:
        tokens = _tokenize(sentence)
        if len(tokens) < 3:
            continue

        for fc_text, fc_toks in forbidden_tokens:
            if len(fc_toks) < 2:
                continue
            overlap = tokens & fc_toks
            if len(overlap) >= len(fc_toks) * 0.7 and len(overlap) >= 3:
                issues.append({
                    "sentence": sentence,
                    "check": "forbidden_claim",
                    "detail": f'Matches forbidden claim: "{fc_text}"',
                    "decision": DECISION_DENY,
                })
                overall = DECISION_DENY

        api_refs = _API_REF_RE.findall(sentence)
        if api_refs and knowledge.available:
            for ref in api_refs:
                parts = ref.split(".")
                cls_name = parts[0]
                if cls_name not in knowledge.classes:
                    issues.append({
                        "sentence": sentence,
                        "check": "api_reference",
                        "detail": f"`{ref}` class not found in API surface",
                        "decision": DECISION_DENY,
                    })
                    overall = DECISION_DENY
                    continue
                if len(parts) >= 2:
                    member = parts[1]
                    if not knowledge.has_method(cls_name, member) and \
                       not knowledge.has_property(cls_name, member):
                        issues.append({
                            "sentence": sentence,
                            "check": "api_reference",
                            "detail": f"`{ref}` member not found in API surface",
                            "decision": DECISION_DENY,
                        })
                        overall = DECISION_DENY
                    elif (cls_name, member) in not_implemented:
                        issues.append({
                            "sentence": sentence,
                            "check": "not_implemented",
                            "detail": (
                                f"`{ref}` is in the API surface but raises "
                                "NotImplementedError - do not document as supported"
                            ),
                            "decision": DECISION_DENY,
                        })
                        overall = DECISION_DENY
                    else:
                        has_evidence = True
                else:
                    has_evidence = True

        for match in _FORMAT_CLAIM_RE.finditer(sentence):
            claimed = match.group(1).lower()
            if claimed in format_support:
                has_evidence = True
                direction = format_support[claimed]
                sent_lower = sentence.lower()
                if "export" in sent_lower and direction == "import":
                    issues.append({
                        "sentence": sentence,
                        "check": "format_direction",
                        "detail": f"{claimed.upper()} export claimed but knowledge shows import-only",
                        "decision": DECISION_DENY,
                    })
                    overall = DECISION_DENY
                elif "import" in sent_lower and direction == "export":
                    issues.append({
                        "sentence": sentence,
                        "check": "format_direction",
                        "detail": f"{claimed.upper()} import claimed but knowledge shows export-only",
                        "decision": DECISION_DENY,
                    })
                    overall = DECISION_DENY
            elif format_support and len(claimed) >= 2:
                issues.append({
                    "sentence": sentence,
                    "check": "unknown_format",
                    "detail": (f"Format `{claimed.upper()}` not found in knowledge "
                              f"(known formats: {', '.join(sorted(format_support.keys())[:10])})"),
                    "decision": DECISION_DENY,
                })
                overall = DECISION_DENY

        install_claim = _INSTALL_CLAIM_RE.search(sentence)
        if install_claim:
            claimed_pkg = install_claim.group(1)
            actual_install = (knowledge.install_cmd or "").strip()
            if actual_install:
                actual_parts = actual_install.split()
                actual_pkg = actual_parts[-1] if actual_parts else ""
                if claimed_pkg != actual_pkg:
                    issues.append({
                        "sentence": sentence,
                        "check": "install_package",
                        "detail": (
                            f"Install package `{claimed_pkg}` contradicts knowledge install command "
                            f"`{actual_install}`"
                        ),
                        "decision": DECISION_DENY,
                    })
                    overall = DECISION_DENY
                else:
                    has_evidence = True

        prereq = _FALSE_PREREQ_RE.search(sentence)
        if prereq and knowledge.install_cmd:
            issues.append({
                "sentence": sentence,
                "check": "prerequisite",
                "detail": (
                    f"Prerequisite claim `{prereq.group(0)}` contradicts package-based install "
                    f"command `{knowledge.install_cmd}`"
                ),
                "decision": DECISION_DENY,
            })
            overall = DECISION_DENY

    # Track knowledge gaps — surface when checks were silently skipped
    knowledge_gaps: list[str] = []
    if not forbidden_tokens:
        knowledge_gaps.append(
            "forbidden_claims list is empty — forbidden claim check was skipped"
        )
    if not knowledge or not getattr(knowledge, "available", False):
        knowledge_gaps.append(
            "knowledge unavailable — API reference and format checks were skipped"
        )

    for gap in knowledge_gaps:
        issues.append({
            "sentence": "(knowledge gap)",
            "check": "knowledge_availability",
            "detail": gap,
            "decision": DECISION_WARN,
        })

    if overall == DECISION_DENY:
        pass
    elif has_evidence:
        overall = DECISION_PASS
    elif knowledge_gaps:
        overall = DECISION_WARN
    else:
        overall = DECISION_WARN

    return {
        "decision": overall,
        "issues": issues,
        "sentences_checked": len(sentences),
        "has_evidence": has_evidence,
    }


def _format_result(result: dict, as_json: bool) -> str:
    if as_json:
        return json.dumps(result, indent=2, ensure_ascii=False)

    lines = [f"Decision: {result['decision']}"]
    lines.append(f"Sentences checked: {result['sentences_checked']}")
    lines.append(f"Evidence found: {'yes' if result['has_evidence'] else 'no'}")

    if result["issues"]:
        lines.append("")
        lines.append("Issues:")
        for issue in result["issues"]:
            lines.append(f"  [{issue['decision']}] {issue['check']}: {issue['detail']}")
            lines.append(f"         Sentence: {issue['sentence'][:120]}")

    if result["decision"] == DECISION_PASS:
        lines.append("")
        lines.append("PASS: Proposed text is consistent with verified knowledge")
    elif result["decision"] == DECISION_WARN:
        lines.append("")
        lines.append("WARN: No direct evidence found, but no contradiction detected")
    else:
        lines.append("")
        lines.append("DENY: Proposed text contradicts known facts - must be revised")

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="change_guard",
        description="Deterministic pre-write change guard (S-33)",
    )
    parser.add_argument("family", help="Product family (e.g. 3d, cells, slides)")
    parser.add_argument("platform", help="Platform (e.g. python, net, java)")
    parser.add_argument("text", nargs="?", default=None, help="Proposed text to validate (inline)")
    parser.add_argument("--file", help="Read proposed text from a file")
    parser.add_argument("--stdin", action="store_true", help="Read proposed text from stdin")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = parser.parse_args(argv)

    platform = PLATFORM_MAP.get(args.platform, args.platform)

    if args.stdin:
        text = sys.stdin.read()
    elif args.file:
        path = Path(args.file)
        if not path.exists():
            _log(f"File not found: {args.file}")
            return 2
        text = path.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        parser.print_help()
        return 0

    if not text.strip():
        _log("Empty text - nothing to check")
        return 0

    merged = KNOWLEDGE_ROOT / args.family / platform / "merged"
    if not merged.exists():
        _log(f"No knowledge found at {merged}")
        _log("WARN: Cannot validate - no knowledge model")
        return 1

    result = guard_text(text, args.family, platform)
    output = _format_result(result, args.json)
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")

    if result["decision"] == DECISION_PASS:
        return 0
    if result["decision"] == DECISION_WARN:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())