"""Layer 2 body-prose scanner for refresh pipeline triage.

Complements the Layer 1 SHA-based staleness detection in refresh_knowledge.py
with a content-level scan that detects when page body prose references
API classes or knowledge claims that have changed or been removed.

RH-201: P-8 diagnostic — missing Layer 2 detection causes false negatives where
the knowledge SHA has not changed but the page's rendered prose is stale relative
to the current knowledge state (e.g., after a partial refresh cycle).

CONTRACT: scripts/pipeline/lib/triage_confirm.py (RPR-F-03, S-111)
  purpose: real CLI for the S-92 triage-confirm Layer 2 scan, replacing the
           documented-but-nonexistent invocation the SKILL.md previously described
           (this file had no argparse/__main__ prior to RPR-F-03 — the documented
           command silently no-op'd if run literally as written).
  inputs:  content pages for {family}/{platform} (via content_discovery.discover_content)
           knowledge/{family}/{platform}/merged/{api_surface.json,claims.json,knowledge_delta.json}
  outputs: reports/refresh_review/{family}/{platform}/triage_verdict.yaml
  idempotent: yes — overwrites output on each run; pure read+scan, no content writes
  exit codes: 0 = confirmed (no page scored stale), 1 = unresolved (>=1 page stale),
              2 = error (knowledge artifacts unreadable/absent)

Library usage::

    from triage_confirm import triage_confirm

    result = triage_confirm(page_path, knowledge)
    if result['stale']:
        for reason in result['reasons']:
            print(reason)

CLI usage::

    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/triage_confirm.py pdf net
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parents[0]
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_PIPELINE_ROOT = Path(__file__).resolve().parents[1]  # lib/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root=None):
    """Redirect module-level paths for testing. Call with no args to reset."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


_TYPE_WORDS = {
    "bool", "boolean", "byte", "char", "decimal", "double", "float", "int",
    "integer", "long", "object", "short", "str", "string", "uint", "ulong",
    "ushort", "void",
}


def _split_signature_params(value: str) -> list[str]:
    params: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(value):
        if char in "<[(":
            depth += 1
        elif char in ">])" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            params.append(value[start:index].strip())
            start = index + 1
    tail = value[start:].strip()
    if tail:
        params.append(tail)
    return params


def _normalize_type(value: str) -> str:
    value = re.sub(r"^(?:ref|out|in|params)\s+", "", value.strip(), flags=re.I)
    value = re.sub(r"\s+", "", value)
    value = value.replace("System.", "")
    return value.lower()


def _signature_claim(value: str) -> tuple[str, ...] | None:
    """Return normalized type tokens, or None when text looks like call values."""
    if not value.strip():
        # RPR-ST087-01: bare `Class.member()` in running prose (no params
        # written between the parens) is virtually always just NAMING the
        # method, not asserting it takes zero arguments -- e.g. "call
        # `Workbook.save()` to persist changes" is accurate prose even
        # though save() takes several real params. Treating this as an
        # explicit zero-arity claim compared it against every real
        # non-zero-arity method and produced a false "stale signature"
        # finding on completely normal documentation style. Found live
        # 2026-08-18, cells/python S-84 remediation attempt #7: 9 of the
        # session's 17 reported "stale" pages were driven entirely by this
        # single false-positive pattern (Workbook.save(), Cell.apply_style(),
        # Cell.put_value(), Cells.iter_rows(), Worksheet.protect(), etc. --
        # every one a real, current, non-zero-arity method cited by bare
        # name in prose). None is the correct return here, matching every
        # other "can't tell what this claims" branch below -- skip the
        # check rather than manufacture a false positive. A genuinely
        # zero-arg method cited with empty parens is unaffected: it simply
        # isn't checked either way, since prose can't misrepresent an
        # arity it never stated.
        return None
    types: list[str] = []
    for raw in _split_signature_params(value):
        if (
            not raw
            or any(char in raw for char in "\"'=")
            or re.fullmatch(r"[-+]?\d+(?:\.\d+)?", raw)
        ):
            return None
        # Accept both ``String`` and ``String value`` documentation forms.
        token = raw.split()[0]
        core = re.sub(r"[\[\]<>?,]", "", token)
        if not core:
            return None
        if not (
            token.lower() in _TYPE_WORDS
            or token[0].isupper()
            or "." in token
            or any(char in token for char in "[]<>?")
        ):
            return None
        types.append(_normalize_type(token))
    return tuple(types)


def triage_confirm(
    page_path: str | Path,
    knowledge: dict[str, Any],
) -> dict[str, Any]:
    """Scan page body for stale prose relative to current knowledge.

    Layer 2 complement to the SHA-based (Layer 1) staleness gate.  Reads the
    page at *page_path*, checks it against the supplied *knowledge* dict, and
    returns a verdict dict.

    Args:
        page_path: Absolute or relative path to a Hugo content page (.md).
        knowledge: Dict with any combination of:
            'api_surface'  — list of current API class dicts (name, methods, properties)
            'claims'       — list of current claim dicts (claim_id, text, …)
            'delta'        — knowledge_delta.json contents (new/removed/modified lists)

    Returns:
        {
            'stale':      bool   — True if any staleness signal detected,
            'reasons':    list[str],
            'confidence': float  — 0.0 (no signal) to 1.0 (high confidence stale),
        }
    """
    page_path = Path(page_path)
    reasons: list[str] = []
    advisories: list[str] = []
    confidence = 0.0

    # Read the page; if unreadable return a distinct "read_error" verdict (TC-2).
    # Callers must treat "read_error" as unknown — NOT as "current".
    try:
        page_text = page_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {
            "stale": False,
            "verdict": "read_error",
            "reasons": [f"could not read page: {exc}"],
            "advisories": [],
            "confidence": 0.0,
        }

    truth_errors = list(knowledge.get("_truth_errors") or [])
    if not truth_errors and "api_surface" not in knowledge and "delta" not in knowledge:
        truth_errors = ["api_surface and knowledge delta were not supplied"]
    if truth_errors:
        return {
            "stale": False,
            "verdict": "unknown",
            "reasons": [f"truth unavailable: {error}" for error in truth_errors],
            "advisories": [],
            "confidence": 0.0,
        }

    # This is a body-prose gate. Evidence/frontmatter drift has separate,
    # stronger validators and must not manufacture a prose-staleness verdict.
    body = page_text
    if page_text.startswith("---"):
        boundary = page_text.find("\n---", 3)
        if boundary != -1:
            body = page_text[boundary + 4:]

    delta: dict[str, Any] = knowledge.get("delta") or {}
    api_surface: list[dict] = knowledge.get("api_surface") or []
    current_api_names: set[str] = {
        e["name"] for e in api_surface if isinstance(e, dict) and "name" in e
    }

    # --- Signal 1: page body mentions APIs that have been removed ---
    removed_apis: list[str] = delta.get("removed_apis") or []
    for api_name in removed_apis:
        # Word-boundary match to avoid false positives (e.g. "Workbook" in "WorkbookSettings")
        if re.search(rf"\b{re.escape(api_name)}\b", body):
            reasons.append(f"body references removed API '{api_name}'")
            confidence = max(confidence, 0.9)

    # --- Advisory 1: page body mentions APIs that have been modified ---
    #
    # "Modified" says that the API still exists and some source representation
    # changed. Mere presence of its class name does not prove that any sentence
    # on the page is stale. The old implementation treated presence alone as a
    # blocking 0.6-confidence verdict, making every valid continued reference a
    # false positive. Removed APIs/members and explicit contradictions remain
    # blocking signals; a modified-name hit is retained for review evidence.
    modified_apis: list[str] = delta.get("modified_apis") or []
    current_members: dict[str, set[str]] = {}
    current_signatures: dict[tuple[str, str], set[tuple[str, ...]]] = {}
    for entry in api_surface:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        class_name = entry["name"]
        members: set[str] = set()
        for field in ("methods", "properties", "members", "values"):
            for member in entry.get(field) or []:
                if isinstance(member, str):
                    members.add(member)
                elif isinstance(member, dict) and isinstance(member.get("name"), str):
                    member_name = member["name"]
                    members.add(member_name)
                    if field == "methods":
                        params = member.get("params")
                        if params is None:
                            params = member.get("parameters")
                        if isinstance(params, list):
                            signature: list[str] = []
                            for param in params:
                                if isinstance(param, str):
                                    param_type = param
                                elif isinstance(param, dict):
                                    param_type = (
                                        param.get("type")
                                        or param.get("data_type")
                                        or param.get("param_type")
                                        or ""
                                    )
                                else:
                                    param_type = ""
                                signature.append(_normalize_type(str(param_type)))
                            current_signatures.setdefault(
                                (class_name, member_name), set()
                            ).add(tuple(signature))
        # A merged surface can legitimately contain multiple same-name class
        # entries (for example namespaces/partials). Never let the last entry
        # erase members observed in earlier authoritative rows.
        current_members.setdefault(class_name, set()).update(members)
    for api_name in modified_apis:
        if re.search(rf"\b{re.escape(api_name)}\b", body):
            advisories.append(
                f"body references modified API '{api_name}'; "
                "presence alone does not prove stale prose"
            )
        # Found live (MT014-2026-07-29-PDF-GO-REDO): [^`]* inside the
        # parameter group is greedy across parens, so a CHAINED call in the
        # same backtick span -- e.g. `Document.Form().Field(name)` -- has its
        # first call's "()" swallow everything up to the LAST ")" before the
        # backtick ("). Field(name" became the claimed param list for
        # Form(), which takes none, producing a false "stale signature"
        # finding on prose that was actually accurate). Excluding parens from
        # the captured class means the match simply stops at the first
        # real ")" -- a chained call then fails to match at all (silently
        # skipped, not mis-attributed), while a real single call's params
        # ("path, opts") are still captured correctly.
        for member in re.findall(
            rf"`{re.escape(api_name)}\.([A-Za-z_][A-Za-z0-9_]*)"
            rf"(?:\([^`()]*\))?`",
            body,
        ):
            if api_name in current_members and member not in current_members[api_name]:
                reasons.append(
                    f"body references missing member '{api_name}.{member}' "
                    "on a modified API"
                )
                confidence = max(confidence, 0.9)
        for member, raw_params in re.findall(
            rf"`{re.escape(api_name)}\.([A-Za-z_][A-Za-z0-9_]*)"
            rf"\(([^`()]*)\)`",
            body,
        ):
            claimed = _signature_claim(raw_params)
            if claimed is None:
                continue
            known = current_signatures.get((api_name, member))
            if known is not None and claimed not in known:
                reasons.append(
                    f"body references stale signature "
                    f"'{api_name}.{member}({raw_params})' on a modified API"
                )
                confidence = max(confidence, 0.9)

    # --- Signal 3: page slug references a class not in current api_surface ---
    slug = page_path.stem  # e.g. "Workbook" from "Workbook.md"
    if current_api_names and slug and slug[0].isupper():
        if slug not in current_api_names:
            reasons.append(f"page slug '{slug}' not found in current api_surface")
            confidence = max(confidence, 0.8)

    # --- Signal 4: page body contains a removed claim ID ---
    removed_claims: list[str] = delta.get("removed_claims") or []
    for claim_id in removed_claims:
        if claim_id in body:
            reasons.append(f"body contains removed claim ID '{claim_id}'")
            confidence = max(confidence, 0.7)

    stale = bool(reasons)
    return {
        "stale": stale,
        "reasons": reasons,
        "advisories": advisories,
        "confidence": confidence,
    }


# ── CLI (RPR-F-03) ───────────────────────────────────────────────────────────

def _load_knowledge(family: str, platform: str, repo_root: Path) -> dict[str, Any]:
    """Load the knowledge dict shape triage_confirm() expects from merged/ artifacts."""
    merged = repo_root / "knowledge" / family / platform / "merged"
    knowledge: dict[str, Any] = {"_truth_errors": []}

    def _load_required(name: str, *, list_key: str | None = None) -> Any:
        path = merged / name
        if not path.is_file():
            knowledge["_truth_errors"].append(f"{name} is missing")
            return [] if list_key is not None else {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            knowledge["_truth_errors"].append(f"{name} is unreadable: {exc}")
            return [] if list_key is not None else {}
        if list_key is not None:
            value = data if isinstance(data, list) else (
                data.get(list_key, []) if isinstance(data, dict) else []
            )
            if not isinstance(value, list):
                knowledge["_truth_errors"].append(f"{name} has an invalid list shape")
                return []
            return value
        if not isinstance(data, dict):
            knowledge["_truth_errors"].append(f"{name} must contain an object")
            return {}
        return data

    knowledge["api_surface"] = _load_required(
        "api_surface.json", list_key="classes"
    )
    knowledge["claims"] = _load_required("claims.json", list_key="claims")
    knowledge["delta"] = _load_required("knowledge_delta.json")

    return knowledge


def run(family: str, platform: str, *, repo_root: Path | None = None, files: list[str] | None = None) -> dict[str, Any]:
    """Run the Layer 2 scan across every English content page for a product.

    Returns a summary dict; also the basis for the CLI's exit code and the
    written triage_verdict.yaml. Raises FileNotFoundError only when the
    product has no reachable knowledge/merged/ directory at all (a genuine
    error, distinct from "merged/ exists but individual files are absent",
    which degrades gracefully to empty lists per _load_knowledge above).
    """
    root = repo_root or _REPO_ROOT
    merged_dir = root / "knowledge" / family / platform / "merged"
    if not merged_dir.exists():
        raise FileNotFoundError(
            f"knowledge/{family}/{platform}/merged/ not found at {merged_dir} — "
            f"run knowledge bootstrap (S-54) before triage-confirm"
        )

    knowledge = _load_knowledge(family, platform, root)

    if files:
        pages = [Path(f) for f in files]
    else:
        sys.path.insert(0, str(root / "scripts" / "pipeline" / "lib"))
        from content_discovery import discover_content  # noqa: E402  (import here: only needed for this path)
        pages = discover_content(family, platform, skip_drafts=True)

    results = []
    stale_count = 0
    error_count = 0
    unknown_count = 0
    for page in pages:
        result = triage_confirm(page, knowledge)
        result["page_path"] = str(page)
        results.append(result)
        if result.get("verdict") == "read_error":
            error_count += 1
        elif result.get("verdict") == "unknown":
            unknown_count += 1
        elif result.get("stale"):
            stale_count += 1

    return {
        "family": family,
        "platform": platform,
        "pages_checked": len(pages),
        "stale_count": stale_count,
        "error_count": error_count,
        "unknown_count": unknown_count,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "triage_confirm — S-92 Layer 2 body-prose staleness scanner. "
            "Real CLI (RPR-F-03) replacing the previously-documented-but-nonexistent invocation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/triage_confirm.py pdf net
  PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/triage_confirm.py pdf net --json

Exit codes:
  0 = confirmed (no page scored stale)
  1 = unresolved (>=1 page scored stale — the caller should re-run the relevant content update step)
  2 = error (knowledge/{family}/{platform}/merged/ not found)
        """,
    )
    parser.add_argument("family", help="Product family (e.g. pdf, 3d)")
    parser.add_argument("platform", help="Platform (e.g. net, java)")
    parser.add_argument("--files", nargs="*", help="Specific page paths to check (default: all discovered English pages)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary")
    args = parser.parse_args(argv)

    try:
        summary = run(args.family, args.platform, files=args.files)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    out_dir = _REPO_ROOT / "reports" / "refresh_review" / args.family / args.platform
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "triage_verdict.yaml"
    try:
        import yaml
        out_path.write_text(yaml.dump(summary, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except ImportError:
        out_path.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"triage_confirm: {args.family}/{args.platform}")
        print(f"  pages checked : {summary['pages_checked']}")
        print(f"  stale         : {summary['stale_count']}")
        print(f"  read errors   : {summary['error_count']}")
        print(f"  unknown       : {summary['unknown_count']}")
        if summary["stale_count"]:
            print("  STALE PAGES:")
            for r in summary["results"]:
                if r.get("stale"):
                    print(f"    - {r['page_path']}: {'; '.join(r['reasons'])}")

    if summary["stale_count"]:
        return 1
    if summary["error_count"] or summary["unknown_count"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
