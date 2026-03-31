"""Deterministic pre-write change guard — validates proposed text against knowledge.

Checks proposed text for forbidden claim matches, API reference accuracy,
and format direction consistency. Returns PASS/WARN/DENY.

Usage:
    python scripts/pipeline/change_guard.py {family} {platform} "proposed text"
    python scripts/pipeline/change_guard.py {family} {platform} --file path.md
    echo "text" | python scripts/pipeline/change_guard.py {family} {platform} --stdin

Exit codes:
    0  PASS — text consistent with knowledge
    1  WARN — no direct evidence, but no contradiction
    2  DENY — text contradicts known facts
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve imports from sibling modules
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# --- Standalone repo path resolution via config_loader ---
_HERE = Path(__file__).resolve().parent          # scripts/pipeline/
_SCRIPTS = _HERE.parent                          # scripts/
import sys as _sys
if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))
from config_loader import (                       # noqa: E402
    resolve_knowledge_root as _resolve_knowledge_root,
)
# --------------------------------------------------------

from knowledge_core import Knowledge, PLATFORM_MAP  # noqa: E402

KNOWLEDGE_ROOT = _resolve_knowledge_root()


def _log(*args, **kwargs):
    """Print to stderr so stdout stays clean for --json."""
    print(*args, file=sys.stderr, **kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Core guard logic
# ---------------------------------------------------------------------------
DECISION_PASS = "PASS"
DECISION_WARN = "WARN"
DECISION_DENY = "DENY"


def guard_text(text: str, family: str, platform: str) -> dict:
    """Validate proposed text against knowledge.

    Returns dict with keys: decision, issues (list of dicts with
    sentence, check, detail).
    """
    knowledge = Knowledge(family, platform)
    forbidden = _load_forbidden_claims(family, platform)
    formats_list = _load_formats(family, platform)

    # Pre-compute
    forbidden_tokens = [
        (fc, _tokenize(fc)) for fc in forbidden if len(fc) > 5
    ]
    format_support: dict[str, str] = {}
    for fmt in formats_list:
        ext = (fmt.get("format") or fmt.get("ext") or "").lower()
        direction = (fmt.get("direction") or fmt.get("support") or "").lower()
        if ext:
            format_support[ext] = direction

    # Split into sentences
    sentences = _SENTENCE_SPLIT_RE.split(text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    issues: list[dict] = []
    overall = DECISION_PASS
    has_evidence = False

    for sentence in sentences:
        tokens = _tokenize(sentence)
        if len(tokens) < 3:
            continue

        # --- Check forbidden claims ---
        for fc_text, fc_toks in forbidden_tokens:
            if len(fc_toks) < 2:
                continue
            overlap = tokens & fc_toks
            if len(overlap) >= len(fc_toks) * 0.7 and len(overlap) >= 3:
                issues.append({
                    "sentence": sentence,
                    "check": "forbidden_claim",
                    "detail": f"Matches forbidden claim: \"{fc_text}\"",
                    "decision": DECISION_DENY,
                })
                overall = DECISION_DENY

        # --- Check API references ---
        api_refs = _API_REF_RE.findall(sentence)
        if api_refs and knowledge.available:
            for ref in api_refs:
                parts = ref.split(".")
                cls_name = parts[0]
                if cls_name not in knowledge.classes:
                    continue  # Unknown class — don't penalize
                has_evidence = True
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
                else:
                    has_evidence = True  # Class exists

        # --- Check format references ---
        for m in _FORMAT_CLAIM_RE.finditer(sentence):
            claimed = m.group(1).lower()
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

    # Determine final decision
    if overall == DECISION_DENY:
        pass  # already set
    elif has_evidence:
        overall = DECISION_PASS
    else:
        overall = DECISION_WARN

    return {
        "decision": overall,
        "issues": issues,
        "sentences_checked": len(sentences),
        "has_evidence": has_evidence,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------
def _format_result(result: dict, as_json: bool) -> str:
    if as_json:
        return json.dumps(result, indent=2, ensure_ascii=False)

    lines = [f"Decision: {result['decision']}"]
    lines.append(f"Sentences checked: {result['sentences_checked']}")
    lines.append(f"Evidence found: {'yes' if result['has_evidence'] else 'no'}")

    if result["issues"]:
        lines.append("")
        lines.append("Issues:")
        for iss in result["issues"]:
            lines.append(f"  [{iss['decision']}] {iss['check']}: {iss['detail']}")
            lines.append(f"         Sentence: {iss['sentence'][:120]}")

    if result["decision"] == DECISION_PASS:
        lines.append("")
        lines.append("PASS: Proposed text is consistent with verified knowledge")
    elif result["decision"] == DECISION_WARN:
        lines.append("")
        lines.append("WARN: No direct evidence found, but no contradiction detected")
    else:
        lines.append("")
        lines.append("DENY: Proposed text contradicts known facts — must be revised")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="change_guard",
        description="Deterministic pre-write change guard (S-33)",
    )
    parser.add_argument("family", help="Product family (e.g. 3d, cells, slides)")
    parser.add_argument("platform", help="Platform (e.g. python, dotnet, java)")
    parser.add_argument("text", nargs="?", default=None,
                        help="Proposed text to validate (inline)")
    parser.add_argument("--file", help="Read proposed text from a file")
    parser.add_argument("--stdin", action="store_true",
                        help="Read proposed text from stdin")
    parser.add_argument("--json", action="store_true",
                        help="Machine-readable JSON output")
    args = parser.parse_args(argv)

    platform = PLATFORM_MAP.get(args.platform, args.platform)

    # Resolve text
    if args.stdin:
        text = sys.stdin.read()
    elif args.file:
        p = Path(args.file)
        if not p.exists():
            _log(f"File not found: {args.file}")
            sys.exit(2)
        text = p.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        parser.print_help()
        sys.exit(0)

    if not text.strip():
        _log("Empty text — nothing to check")
        sys.exit(0)

    # Check knowledge exists
    merged = KNOWLEDGE_ROOT / args.family / platform / "merged"
    if not merged.exists():
        _log(f"No knowledge found at {merged}")
        _log("WARN: Cannot validate — no knowledge model")
        sys.exit(1)

    result = guard_text(text, args.family, platform)

    output = _format_result(result, args.json)
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")

    # Exit code
    if result["decision"] == DECISION_PASS:
        sys.exit(0)
    elif result["decision"] == DECISION_WARN:
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
