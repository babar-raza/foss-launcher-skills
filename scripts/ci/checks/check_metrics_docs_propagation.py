# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_metrics_docs_propagation.py — Prepare enforcement for Slices 10+11 docs/skills propagation.

Scans AGENTS.md, docs/, README files, and skill files for metrics obligation clauses.
Classifies each as PRESENT, MISSING, NOT_APPLICABLE, or PENDING.

Default mode: advisory / pre-propagation — exits 0 even if clauses are missing.
Writes a clear pending report to show what still needs propagation.

Strict mode (--strict): fails if required docs/skills clauses are missing.
This checker becomes strict after propagation is complete.

Does NOT modify docs or skills. Does NOT add clauses.

Usage:
    python scripts/ci/checks/check_metrics_docs_propagation.py
    python scripts/ci/checks/check_metrics_docs_propagation.py --strict
    python scripts/ci/checks/check_metrics_docs_propagation.py --json-output

Exit codes:
    0  Advisory mode: always (writes pending report). Strict mode: all required clauses present.
    1  Strict mode only: one or more required clauses missing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent.parent.parent))

# Docs and files to inspect
_DOCS_TO_CHECK: list[tuple[str, str, bool]] = [
    # (rel_path, description, required_in_strict)
    ("AGENTS.md", "Root governance document", True),
    ("docs/governance/", "Governance directory (all .md files)", True),
    ("scripts/pipeline/commands/ops/README.md", "Pipeline ops README", False),
    ("scripts/README.md", "Scripts README", False),
    (".env.example", "Example env file", False),
]

# Skill file directories to scan
_SKILL_DIRS = [
    ".claude/commands",
]

# Keywords indicating a metrics clause is present
_METRICS_CLAUSE_KEYWORDS = [
    "AGENT_METRICS",
    "metrics capture",
    "RunMetrics",
    "ProfessionalizeClient",
    "professionalize metrics",
    "metrics obligation",
    "token_usage",
    "api_calls_count",
    "metrics_submitter",
    "dry-run",
    "metrics evidence",
]

# LLM-related keywords that indicate a skill uses LLM
_LLM_SKILL_KEYWORDS = [
    "llm", "professionalize", "LLMRouter", "call_chat", "embed",
    "knowledge_enrich", "translate", "gap-eval", "seo", "recommend",
]


@dataclass
class PropagationItem:
    path: str
    description: str
    status: str  # PRESENT | MISSING | NOT_APPLICABLE | PENDING | FILE_NOT_FOUND
    metrics_clause_found: bool = False
    llm_usage_detected: bool = False
    note: str = ""


@dataclass
class PropagationResult:
    passed: bool = True  # always True in advisory mode; conditional in strict mode
    advisory_mode: bool = True
    items: list[PropagationItem] = field(default_factory=list)
    present_count: int = 0
    missing_count: int = 0
    pending_count: int = 0
    not_applicable_count: int = 0


def _has_metrics_clause(text: str) -> bool:
    lower = text.lower()
    for kw in _METRICS_CLAUSE_KEYWORDS:
        if kw.lower() in lower:
            return True
    return False


def _has_llm_usage(text: str) -> bool:
    lower = text.lower()
    for kw in _LLM_SKILL_KEYWORDS:
        if kw.lower() in lower:
            return True
    return False


def _check_file(path: Path, description: str, strict_required: bool, root: Path | None = None) -> PropagationItem:
    ref_root = root or _REPO_ROOT
    try:
        rel = path.relative_to(ref_root).as_posix()
    except ValueError:
        rel = str(path)
    if not path.exists():
        return PropagationItem(
            path=rel,
            description=description,
            status="FILE_NOT_FOUND",
            note="File does not exist — pending creation or already propagated via other path",
        )
    text = path.read_text(encoding="utf-8", errors="ignore")
    has_clause = _has_metrics_clause(text)
    status = "PRESENT" if has_clause else ("MISSING" if strict_required else "PENDING")
    return PropagationItem(
        path=rel,
        description=description,
        status=status,
        metrics_clause_found=has_clause,
        note="" if has_clause else "Metrics clause expected after docs propagation",
    )


def _check_skill_file(path: Path, root: Path | None = None) -> PropagationItem:
    ref_root = root or _REPO_ROOT
    try:
        rel = path.relative_to(ref_root).as_posix()
    except ValueError:
        rel = str(path)
    if not path.exists():
        return PropagationItem(path=rel, description="Skill file", status="FILE_NOT_FOUND")
    text = path.read_text(encoding="utf-8", errors="ignore")
    is_llm = _has_llm_usage(text)
    if not is_llm:
        return PropagationItem(
            path=rel, description="Skill file",
            status="NOT_APPLICABLE",
            llm_usage_detected=False,
            note="No LLM usage detected — metrics clause not required",
        )
    has_clause = _has_metrics_clause(text)
    status = "PRESENT" if has_clause else "PENDING"
    return PropagationItem(
        path=rel, description="Skill file (LLM-using)",
        status=status,
        metrics_clause_found=has_clause,
        llm_usage_detected=True,
        note="" if has_clause else "LLM-using skill: metrics clause expected after skill propagation",
    )


def run_check(root: Path, strict: bool = False) -> PropagationResult:
    result = PropagationResult(advisory_mode=not strict)

    # Check docs files
    for rel_path, description, strict_required in _DOCS_TO_CHECK:
        full = root / rel_path
        if full.is_dir():
            # Scan all .md files in directory
            md_files = sorted(full.rglob("*.md"))
            if not md_files:
                result.items.append(PropagationItem(
                    path=rel_path, description=description,
                    status="FILE_NOT_FOUND",
                    note="Directory exists but no .md files found",
                ))
            for md_file in md_files:
                item = _check_file(md_file, description, strict_required, root=root)
                result.items.append(item)
        else:
            item = _check_file(full, description, strict_required, root=root)
            result.items.append(item)

    # Check skill files
    for skill_dir in _SKILL_DIRS:
        skill_path = root / skill_dir
        if not skill_path.exists():
            continue
        for skill_file in sorted(skill_path.rglob("*.md")):
            item = _check_skill_file(skill_file, root=root)
            result.items.append(item)

    # Count
    for item in result.items:
        if item.status == "PRESENT":
            result.present_count += 1
        elif item.status == "MISSING":
            result.missing_count += 1
        elif item.status == "PENDING":
            result.pending_count += 1
        elif item.status == "NOT_APPLICABLE":
            result.not_applicable_count += 1

    # Determine pass/fail
    if strict:
        # In strict mode, MISSING or PENDING items are failures
        failing = [i for i in result.items if i.status in ("MISSING", "PENDING")]
        if failing:
            result.passed = False
    else:
        # Advisory mode: always pass
        result.passed = True

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check metrics obligation clause propagation in docs and skill files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Default mode: advisory — always exits 0 but reports pending items.\n"
            "Strict mode: exits 1 if required clauses are missing.\n"
            "Becomes strict after propagation is complete."
        ),
    )
    parser.add_argument("--strict", action="store_true",
                        help="Fail if required docs/skills clauses are missing (for post-propagation use)")
    parser.add_argument("--json-output", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    result = run_check(root=_REPO_ROOT, strict=args.strict)

    if args.json_output:
        print(json.dumps({
            "passed": result.passed,
            "advisory_mode": result.advisory_mode,
            "present_count": result.present_count,
            "missing_count": result.missing_count,
            "pending_count": result.pending_count,
            "not_applicable_count": result.not_applicable_count,
            "items": [
                {
                    "path": i.path,
                    "status": i.status,
                    "metrics_clause_found": i.metrics_clause_found,
                    "llm_usage_detected": i.llm_usage_detected,
                    "note": i.note,
                }
                for i in result.items
            ],
        }, indent=2))
    else:
        mode_label = "STRICT" if args.strict else "ADVISORY"
        print(f"check_metrics_docs_propagation [{mode_label}]: "
              f"present={result.present_count}, pending={result.pending_count}, "
              f"missing={result.missing_count}, n/a={result.not_applicable_count}")
        if result.pending_count or result.missing_count:
            print(f"  NOTE: {result.pending_count} item(s) pending propagation, "
                  f"{result.missing_count} missing")
            if args.strict:
                failing = [i for i in result.items if i.status in ("MISSING", "PENDING")]
                for i in failing:
                    print(f"  FAIL {i.status}: {i.path}  ({i.note})")
            else:
                print("  Advisory mode — these will become failures after propagation is complete.")
        if result.passed:
            print(f"check_metrics_docs_propagation: {'PASS' if args.strict else 'PASS (advisory)'}")
        else:
            print("check_metrics_docs_propagation: FAIL (strict mode)")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
