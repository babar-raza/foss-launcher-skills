"""Deterministic pre-write downgrade guard.

Uses the canonical A-F grade scale from content_eval.models and reads
stored grades from frontmatter when available (fast path).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from knowledge_core import Knowledge  # noqa: E402
from content_discovery import infer_product  # noqa: E402  (R-1b: was knowledge_core)
from evidence_verifier import verify_evidence  # noqa: E402  (R-3b: was knowledge_core)
from core.markdown import parse_frontmatter, extract_frontmatter_body  # R-2a: was knowledge_core
from token_ops import extract_tokens, verify_tokens
from content_eval.models import compute_grade, Page
from content_eval.evaluators.type_accuracy import TypeAccuracyEvaluator
from grade_writer import read_grade


DECISION_ALLOW = "ALLOW"
DECISION_WARN = "WARN"
DECISION_BLOCK = "BLOCK"


def _read_proposed(args) -> str:
    if args.stdin:
        return sys.stdin.read()
    if args.proposed_file:
        return Path(args.proposed_file).read_text(encoding="utf-8")
    if args.proposed_content is not None:
        return args.proposed_content
    raise ValueError("Provide proposed content inline, via --proposed-file, or via --stdin.")


def _evaluate_file(path: Path, family: str, platform: str) -> dict:
    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        raise FileNotFoundError(f"No knowledge available for {family}/{platform}")

    findings = verify_tokens(extract_tokens(path, platform), knowledge, path)
    findings.extend(verify_evidence(parse_frontmatter(path), knowledge, path))
    # TC-24: Run type_accuracy evaluator so TA findings reach the guard.
    try:
        page = Page.load(path)
        if page is not None:
            page.family = family
            page.platform = platform
            ta_ev = TypeAccuracyEvaluator()
            findings.extend(ta_ev.evaluate(page, None))
    except Exception:
        pass  # type_accuracy is best-effort in the guard
    fails = [f for f in findings if f.level == "FAIL"]
    warns = [f for f in findings if f.level == "WARN"]
    return {
        "fail_count": len(fails),
        "warn_count": len(warns),
        "grade": compute_grade(len(fails), len(warns)),
        "findings": [
            {
                "level": f.level,
                "message": f.message,
                "line": f.line_no,
                "category": getattr(f, "category", ""),
            }
            for f in findings
        ],
    }


def _decision(existing_grade: str | None, predicted_grade: str, target_exists: bool) -> str:
    if not target_exists or existing_grade is None:
        return DECISION_ALLOW
    if existing_grade in {"D", "F"}:
        return DECISION_ALLOW
    if existing_grade == "C":
        return DECISION_BLOCK if predicted_grade in {"D", "F"} else DECISION_ALLOW
    if existing_grade in {"A", "B"}:
        if predicted_grade in {"D", "F"}:
            return DECISION_BLOCK
        if predicted_grade == "C":
            return DECISION_WARN
        return DECISION_ALLOW
    return DECISION_ALLOW


def _structural_check(existing_text: str, proposed_text: str) -> tuple[str, str] | None:
    """Return (decision, reason) if structural regression detected, else None.

    This catches catastrophic content destruction (e.g. replacing a 500-word page
    with a 10-word stub) that the grade-comparison path misses because trash
    content with 0 API tokens gets graded A.
    """
    ex_words = len(existing_text.split())
    pr_words = len(proposed_text.split())
    if ex_words > 50 and pr_words < ex_words * 0.3:
        return (
            DECISION_BLOCK,
            f"structural regression: word count dropped from {ex_words} to {pr_words} (<30%)",
        )
    ex_headings = len(re.findall(r"^#{2,3}\s", existing_text, re.MULTILINE))
    pr_headings = len(re.findall(r"^#{2,3}\s", proposed_text, re.MULTILINE))
    if ex_headings >= 3 and pr_headings < ex_headings * 0.5:
        return (
            DECISION_BLOCK,
            f"structural regression: heading count dropped from {ex_headings} to {pr_headings} (<50%)",
        )
    ex_code = len(re.findall(r"^```", existing_text, re.MULTILINE))
    pr_code = len(re.findall(r"^```", proposed_text, re.MULTILINE))
    if ex_code >= 2 and pr_code == 0:
        return (
            DECISION_WARN,
            f"structural regression: code blocks dropped from {ex_code} to 0",
        )

    # Plugin-page check: compare frontmatter section presence.
    # Plugin pages have empty bodies, so body-based checks above are no-ops.
    ex_fm_raw = extract_frontmatter_body(existing_text)
    pr_fm_raw = extract_frontmatter_body(proposed_text)
    if ex_fm_raw and pr_fm_raw:
        try:
            ex_fm = yaml.safe_load(ex_fm_raw) or {}
            pr_fm = yaml.safe_load(pr_fm_raw) or {}
        except yaml.YAMLError:
            ex_fm, pr_fm = {}, {}
        if ex_fm.get("layout") == "plugin":
            ex_sections = {
                k for k in ex_fm
                if isinstance(ex_fm[k], dict) and ex_fm[k].get("enable")
            }
            pr_sections = {
                k for k in pr_fm
                if isinstance(pr_fm[k], dict) and pr_fm[k].get("enable")
            }
            lost = ex_sections - pr_sections
            if lost:
                return (
                    DECISION_BLOCK,
                    f"structural regression: enabled sections removed: {sorted(lost)}",
                )

    return None


def compare_content(target_path: Path, proposed_text: str, family: str | None = None, platform: str | None = None, force_regenerate: bool = False) -> dict:
    inferred_family, inferred_platform = infer_product(target_path)
    family = family or inferred_family
    platform = platform or inferred_platform
    if not family or not platform:
        raise ValueError("Could not infer product from target path; pass --family and --platform.")

    target_exists = target_path.exists()

    # --- Structural regression check (runs BEFORE grade comparison) ---
    # Skipped when force_regenerate is set — operator intentionally overriding.
    if target_exists and not force_regenerate:
        existing_text = target_path.read_text(encoding="utf-8")
        structural = _structural_check(existing_text, proposed_text)
        if structural:
            decision, reason = structural
            return {
                "decision": decision,
                "reason": reason,
                "target_exists": target_exists,
                "family": family,
                "platform": platform,
                "target_path": str(target_path),
                "existing": {"grade": None, "fail_count": None, "warn_count": None, "findings": []},
                "proposed": {"grade": None, "fail_count": None, "warn_count": None, "findings": []},
            }

    # Fast path: use stored grade if valid (same knowledge version).
    existing = None
    from_stored = False
    if target_exists:
        stored = read_grade(target_path)
        knowledge = Knowledge(family, platform)
        if stored and stored["model_sha"] and knowledge.available and stored["model_sha"] == knowledge.repo_sha:
            existing = {
                "fail_count": None,
                "warn_count": None,
                "grade": stored["grade"],
                "findings": [],
                "from_stored": True,
            }
            from_stored = True
        else:
            existing = _evaluate_file(target_path, family, platform)

    with TemporaryDirectory(prefix="aspose-no-downgrade-") as temp_dir:
        proposed_path = Path(temp_dir) / (target_path.name or "candidate.md")
        proposed_path.write_text(proposed_text, encoding="utf-8")
        proposed = _evaluate_file(proposed_path, family, platform)

    # When force_regenerate is set, bypass the grade-based decision matrix
    # and always allow — the operator is intentionally overriding the guard.
    if force_regenerate:
        decision = DECISION_ALLOW
        reason = "force-regenerate: grade downgrade guard bypassed by operator"
    else:
        existing_grade = existing["grade"] if existing else None
        decision = _decision(existing_grade, proposed["grade"], target_exists)
        reason = {
            DECISION_ALLOW: "proposed content is equal or better under deterministic audit proxy",
            DECISION_WARN: "proposed content degrades the target to C-grade risk",
            DECISION_BLOCK: "proposed content regresses beyond the allowed quality floor",
        }[decision]

    # TC-24: Escalate WARN → BLOCK when type-accuracy findings cause the
    # grade regression.  This makes the guard a hard gate for TA-caused
    # A→C / B→C transitions while leaving non-TA WARN behaviour unchanged.
    if decision == DECISION_WARN:
        ta_findings = [
            f for f in proposed["findings"]
            if f.get("category") == "TA"
        ]
        if ta_findings:
            decision = DECISION_BLOCK
            reason = (
                f"type accuracy findings block this regression: "
                f"{len(ta_findings)} TA issue(s)"
            )

    result = {
        "decision": decision,
        "reason": reason,
        "target_exists": target_exists,
        "family": family,
        "platform": platform,
        "target_path": str(target_path),
        "existing": existing,
        "proposed": proposed,
    }
    if force_regenerate:
        result["force_regenerate"] = True
    return result


def _print_result(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"Decision: {result['decision']}")
    print(f"Reason: {result['reason']}")
    if result["target_exists"]:
        ex = result["existing"]
        if ex.get("from_stored"):
            print(f"Existing: grade {ex['grade']} (from stored frontmatter)")
        else:
            print(
                f"Existing: grade {ex['grade']} "
                f"({ex['fail_count']} FAIL, {ex['warn_count']} WARN)"
            )
    else:
        print("Target: new file")
    print(
        f"Proposed: grade {result['proposed']['grade']} "
        f"({result['proposed']['fail_count']} FAIL, {result['proposed']['warn_count']} WARN)"
    )
    if result["decision"] == DECISION_BLOCK:
        print("Blocking FAIL findings:")
        for finding in result["proposed"]["findings"]:
            if finding["level"] == "FAIL":
                print(f"  - {finding['message']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="no_downgrade_guard",
        description="Deterministic pre-write downgrade guard based on audit failure counts.",
    )
    parser.add_argument("target_path", help="Existing content path to protect")
    parser.add_argument("proposed_content", nargs="?", default=None, help="Inline proposed markdown")
    parser.add_argument("--proposed-file", help="Read proposed markdown from a file")
    parser.add_argument("--stdin", action="store_true", help="Read proposed markdown from stdin")
    parser.add_argument("--family", help="Override inferred family")
    parser.add_argument("--platform", help="Override inferred platform")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--force-regenerate", action="store_true",
                        help="Bypass structural and grade downgrade guards (operator override)")
    args = parser.parse_args(argv)

    result = compare_content(
        Path(args.target_path),
        _read_proposed(args),
        family=args.family,
        platform=args.platform,
        force_regenerate=args.force_regenerate,
    )
    _print_result(result, args.json)
    if result["decision"] == DECISION_BLOCK:
        return 2
    if result["decision"] == DECISION_WARN:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())