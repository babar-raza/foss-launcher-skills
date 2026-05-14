#!/usr/bin/env python3
"""Generate deterministic remediation plans for gap-eval findings.

The reference site can use LLM-backed fix planning. The standalone repo keeps
the same operator-facing contract while remaining safe by default: it emits
exact plans and conservative replacement specs from findings, without editing
content or calling remote models.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from scripts.content_repo_adapter import assert_write_allowed, resolve_clone_cache, resolve_output_root  # noqa: E402

_FIX_RULES_PATH = Path(__file__).resolve().parent / "fix_rules.py"
_SPEC = importlib.util.spec_from_file_location("standalone_gap_eval_fix_rules", _FIX_RULES_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover
    raise ImportError(f"Unable to load {_FIX_RULES_PATH}")
_FIX_RULES = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _FIX_RULES
_SPEC.loader.exec_module(_FIX_RULES)
classify_findings = _FIX_RULES.classify_findings
wave_summary = _FIX_RULES.wave_summary


def _source_excerpt(path: Path, line: int, radius: int = 3) -> str:
    if not path.exists() or line <= 0:
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(0, line - radius - 1)
    end = min(len(lines), line + radius)
    return "\n".join(lines[start:end])


def generate_fix_spec(finding: dict[str, Any], clone_cache: Path | None = None) -> dict[str, Any]:
    old = str(finding.get("old_value") or "")
    new = str(finding.get("correct_value") or "")
    rule = _FIX_RULES.get_rule(str(finding.get("type", "")))
    evidence_source = ""
    file_name = finding.get("file")
    if file_name:
        evidence_source = _source_excerpt(Path(str(file_name)), int(finding.get("line") or 0))
    if not evidence_source and clone_cache:
        evidence_source = f"clone_cache={clone_cache}"

    if rule.strategy == "auto" and old and new:
        strategy = "auto"
        rationale = f"Apply {rule.auto_method or 'deterministic'} correction from finding metadata."
    elif rule.strategy == "llm" and old and new:
        strategy = "planned_substitution"
        rationale = "Conservative replacement derived from explicit finding old_value/correct_value."
    else:
        strategy = "needs_operator_edit"
        rationale = "Finding lacks enough grounded replacement metadata for unattended planning."

    return {
        "finding_id": finding.get("id", "?"),
        "finding_type": finding.get("type", ""),
        "strategy": strategy,
        "old": old,
        "new": new,
        "rationale": rationale,
        "evidence_source": evidence_source[:500],
    }


def generate_fix_specs(findings: list[dict[str, Any]], *, clone_cache: Path | None = None) -> list[dict[str, Any]]:
    return [generate_fix_spec(finding, clone_cache) for finding in findings if finding.get("status") not in {"fixed", "wontfix"}]


def format_plan_md(family: str, platform: str, waves: dict[int, list[dict]], specs: list[dict[str, Any]]) -> str:
    specs_by_id = {spec["finding_id"]: spec for spec in specs}
    lines = [
        f"# Remediation Plan: {family}/{platform}",
        "",
        "This plan is generated without editing source content.",
        "",
        wave_summary(waves),
        "",
        "## Fix Specifications",
        "",
    ]
    for spec in specs:
        lines.extend(
            [
                f"### {spec['finding_id']}",
                f"- Type: `{spec['finding_type']}`",
                f"- Strategy: `{spec['strategy']}`",
                f"- Old: `{spec['old']}`",
                f"- New: `{spec['new']}`",
                f"- Rationale: {spec['rationale']}",
                "",
            ]
        )
    unresolved = [spec for spec in specs_by_id.values() if spec["strategy"] == "needs_operator_edit"]
    lines.extend(["## Unresolved", ""])
    lines.append(f"- Operator-edit specs: {len(unresolved)}")
    return "\n".join(lines)


def _load_findings(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    findings = data.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("findings must be a list")
    return [item for item in findings if isinstance(item, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--findings-json", type=Path)
    parser.add_argument("--output-root")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    findings_path = args.findings_json or (resolve_output_root(args.output_root) / "gap-analysis" / f"{args.family}-{args.platform}.json")
    if not findings_path.exists():
        print(f"error: findings JSON not found: {findings_path}", file=sys.stderr)
        return 1

    try:
        findings = _load_findings(findings_path)
        clone_cache = resolve_clone_cache() / f"aspose_{args.family}_{args.platform}"
        waves = classify_findings(findings)
        specs = generate_fix_specs(findings, clone_cache=clone_cache)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = {"family": args.family, "platform": args.platform, "findings_count": len(findings), "fix_specs": specs}
    plan_md = format_plan_md(args.family, args.platform, waves, specs)
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    out_dir = args.out_dir or (resolve_output_root(args.output_root) / "agents" / "remediation" / f"{args.family}-{args.platform}")
    try:
        plan_path = out_dir / "plan.md"
        specs_path = out_dir / "fix_specs.json"
        assert_write_allowed(plan_path, dry_run=False)
        assert_write_allowed(specs_path, dry_run=False)
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(plan_md, encoding="utf-8")
        specs_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        print(f"error: failed to write fix plan: {exc}", file=sys.stderr)
        return 3
    print(specs_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
