"""Deterministic pre-write downgrade guard.

Prevents a newly generated page from silently overwriting a higher-quality
existing page. Uses content_eval grade as the quality measure.

Ported from aspose.org scripts/pipeline/no_downgrade_guard.py.
Adapted for foss-launcher-skills-gitlab module structure.

Exit codes:
  0  ALLOW — write is safe
  1  WARN  — degradation possible, user should review
  2  BLOCK — write would regress quality past allowed floor
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

DECISION_ALLOW = "ALLOW"
DECISION_WARN = "WARN"
DECISION_BLOCK = "BLOCK"

# Grade ordering (higher index = better)
_GRADE_ORDER = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}


def _read_proposed(args) -> str:
    if args.stdin:
        return sys.stdin.read()
    if args.proposed_file:
        return Path(args.proposed_file).read_text(encoding="utf-8")
    if args.proposed_content is not None:
        return args.proposed_content
    raise ValueError(
        "Provide proposed content inline, via --proposed-file, or via --stdin."
    )


def _run_eval(path: Path, repo_root: Path) -> str | None:
    """Run content_eval on a file and return its letter grade, or None on failure."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.pipeline.content_eval",
                "evaluate",
                "--files",
                str(path),
                "--format",
                "json",
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return _fallback_grade_from_audit(path, repo_root)
        data = json.loads(result.stdout)
        # content_eval JSON structure: {"files": [{"grade": "B", ...}]}
        files = data.get("files") or data.get("results") or []
        if files and isinstance(files, list):
            return files[0].get("grade")
        return data.get("grade")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return _fallback_grade_from_audit(path, repo_root)


def _fallback_grade_from_audit(path: Path, repo_root: Path) -> str:
    """Fallback: run audit.py and grade by FAIL count."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(repo_root / "scripts" / "pipeline" / "audit.py"),
                "--files",
                str(path),
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        fail_count = output.count("FAIL")
        if fail_count == 0:
            return "B"
        if fail_count <= 2:
            return "C"
        if fail_count <= 5:
            return "D"
        return "F"
    except Exception:
        return "C"  # Neutral fallback when evaluation is impossible


def _decision(existing_grade: str | None, predicted_grade: str, target_exists: bool) -> str:
    """Apply the no-downgrade decision matrix."""
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
    """Detect catastrophic structural regressions before grade comparison.

    Returns (decision, reason) if regression detected, else None.
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

    # Plugin-page (frontmatter-only) check
    ex_fm_raw = _extract_frontmatter_yaml(existing_text)
    pr_fm_raw = _extract_frontmatter_yaml(proposed_text)
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


def _extract_frontmatter_yaml(text: str) -> str | None:
    """Extract raw YAML from frontmatter block, or None if not present."""
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    return match.group(1) if match else None


def compare_content(
    target_path: Path,
    proposed_text: str,
    repo_root: Path,
    force_regenerate: bool = False,
) -> dict:
    """Core comparison logic. Returns a result dict with decision, grades, reason."""
    target_exists = target_path.exists()

    # Structural regression check (runs before grade comparison)
    if target_exists and not force_regenerate:
        existing_text = target_path.read_text(encoding="utf-8")
        structural = _structural_check(existing_text, proposed_text)
        if structural:
            decision, reason = structural
            return {
                "decision": decision,
                "reason": reason,
                "target_exists": target_exists,
                "target_path": str(target_path),
                "existing": {"grade": None},
                "proposed": {"grade": None},
            }

    # Evaluate existing file
    existing_grade = None
    if target_exists:
        existing_grade = _run_eval(target_path, repo_root)

    # Evaluate proposed content (write to temp file)
    proposed_grade = None
    suffix = target_path.suffix or ".md"
    with NamedTemporaryFile(
        mode="w",
        suffix=suffix,
        prefix="foss-proposed-",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(proposed_text)
        tmp_path = Path(tmp.name)

    try:
        proposed_grade = _run_eval(tmp_path, repo_root)
    finally:
        tmp_path.unlink(missing_ok=True)

    if force_regenerate:
        decision = DECISION_ALLOW
        reason = "force-regenerate: grade downgrade guard bypassed by operator"
    else:
        decision = _decision(existing_grade, proposed_grade or "C", target_exists)
        reason = {
            DECISION_ALLOW: "proposed content is equal or better under deterministic audit proxy",
            DECISION_WARN: "proposed content degrades the target to C-grade risk",
            DECISION_BLOCK: "proposed content regresses beyond the allowed quality floor",
        }[decision]

    return {
        "decision": decision,
        "reason": reason,
        "target_exists": target_exists,
        "target_path": str(target_path),
        "existing": {"grade": existing_grade},
        "proposed": {"grade": proposed_grade},
        "force_regenerate": force_regenerate,
    }


def _print_result(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"Decision: {result['decision']}")
    print(f"Reason: {result['reason']}")
    if result["target_exists"]:
        ex_grade = result["existing"].get("grade")
        print(f"Existing grade: {ex_grade or 'unknown'}")
    else:
        print("Target: new file (no prior grade to protect)")
    print(f"Proposed grade: {result['proposed'].get('grade') or 'unknown'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="no_downgrade_guard",
        description="Deterministic pre-write downgrade guard based on content quality grades.",
    )
    parser.add_argument("target_path", help="Existing content path to protect")
    parser.add_argument(
        "proposed_content", nargs="?", default=None, help="Inline proposed markdown"
    )
    parser.add_argument(
        "--proposed-file", help="Read proposed markdown from a file"
    )
    parser.add_argument(
        "--stdin", action="store_true", help="Read proposed markdown from stdin"
    )
    parser.add_argument("--json", dest="as_json", action="store_true")
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Bypass structural and grade downgrade guards (operator override)",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root path (default: 2 levels up from this script)",
    )
    args = parser.parse_args(argv)

    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parent.parent.parent

    proposed_text = _read_proposed(args)
    result = compare_content(
        Path(args.target_path),
        proposed_text,
        repo_root=repo_root,
        force_regenerate=args.force_regenerate,
    )
    _print_result(result, args.as_json)
    if result["decision"] == DECISION_BLOCK:
        return 2
    if result["decision"] == DECISION_WARN:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
