#!/usr/bin/env python3
"""S-44 gap-plan — LLM fix specification generator.

For each non-auto-fixable finding, generates an exact {old, new, rationale}
substitution grounded in clone cache evidence.

Usage (standalone):
    python scripts/gap-eval/fix_spec.py {family} {platform}

Or import and call generate_fix_specs() directly from gap-plan.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

from core.env_loader import load_env  # noqa: E402
load_env()

# Fix strategy prompt — see plan Section 9 (Fix Specification Prompt)
_SYSTEM_PROMPT = (
    "You are a technical documentation editor. Generate the minimal correct "
    "substitution to fix a documentation error. Output only valid JSON."
)

_USER_PROMPT_TEMPLATE = """Clone cache evidence confirming the correct behavior:
---
{evidence}
---

Wrong content in documentation:
{wrong_content}

Output only valid JSON:
{{
  "old": "exact substring to replace (verbatim)",
  "new": "replacement text grounded in the evidence above",
  "rationale": "one sentence explaining the change"
}}

Rules: Do not change anything outside the error. Do not add content not in the evidence."""


_router = None  # lazy singleton


def _get_router():
    """Return cached LLMRouter instance (lazy init)."""
    global _router
    if _router is None:
        from lib.llm_router import LLMRouter
        _router = LLMRouter()
    return _router


def _llm_call(system: str, user: str) -> dict | None:
    """Call LLM: professionalize.com gpt-oss → Ollama llama3.2 fallback.

    Delegates to shared LLMRouter.
    """
    try:
        from lib.llm_router import EndpointStatus
        router = _get_router()
    except (ImportError, RuntimeError) as exc:
        log.warning("LLM router unavailable: %s", exc)
        return None

    result = router.call_chat(
        system, user,
        temperature=0.1,
        timeout=45,
        json_extract=True,
        json_array=False,
    )

    if result.status == EndpointStatus.OK and isinstance(result.data, dict):
        log.info("LLM call via %s", result.provider)
        if "old" in result.data and "new" in result.data:
            return result.data
    return None


def _get_evidence(finding: dict, clone_cache: Path) -> str:
    """Retrieve clone cache source excerpt relevant to this finding."""
    search_term = finding.get("correct_value") or finding.get("old_value") or ""
    if not search_term or not clone_cache.exists():
        return ""
    try:
        result = subprocess.run(
            ["grep", "-r", "--include=*.java", "--include=*.py", "--include=*.cs",
             "--include=*.ts", "--include=*.cpp", "--include=*.h",
             "-l", search_term, str(clone_cache)],
            capture_output=True, text=True, timeout=10
        )
        files = result.stdout.strip().splitlines()[:2]
        if not files:
            return ""
        excerpts: list[str] = []
        for fpath in files:
            try:
                text = Path(fpath).read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
                for i, line in enumerate(lines):
                    if search_term in line:
                        start = max(0, i - 3)
                        end = min(len(lines), i + 20)
                        excerpts.append("\n".join(lines[start:end]))
                        break
            except OSError:
                continue
        return "\n\n---\n\n".join(excerpts)[:2000]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _get_wrong_content(finding: dict) -> str:
    """Get the wrong content block from the source file."""
    file_path = finding.get("file", "")
    line_no = finding.get("line", 0)
    if not file_path or not line_no:
        return finding.get("old_value", "")
    try:
        lines = Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, line_no - 3)
        end = min(len(lines), line_no + 10)
        return "\n".join(lines[start:end])
    except OSError:
        return finding.get("old_value", "")


def generate_fix_spec(finding: dict, clone_cache: Path) -> dict:
    """Generate a fix specification for a single finding.

    Returns:
      {
        "finding_id": str,
        "strategy": "llm" | "needs_human_edit",
        "old": str,        # exact text to replace
        "new": str,        # replacement text
        "rationale": str,
        "evidence_source": str,
      }
    """
    fid = finding.get("id", "?")
    evidence = _get_evidence(finding, clone_cache)
    wrong_content = _get_wrong_content(finding)

    if not evidence:
        return {
            "finding_id": fid,
            "strategy": "needs_human_edit",
            "old": finding.get("old_value", ""),
            "new": finding.get("correct_value") or "REPLACE_WITH_CORRECT_VALUE",
            "rationale": "No clone cache evidence found — manual edit required",
            "evidence_source": "",
        }

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        evidence=evidence,
        wrong_content=wrong_content,
    )

    result = _llm_call(_SYSTEM_PROMPT, user_prompt)
    if result:
        return {
            "finding_id": fid,
            "strategy": "llm",
            "old": result.get("old", finding.get("old_value", "")),
            "new": result.get("new", ""),
            "rationale": result.get("rationale", ""),
            "evidence_source": evidence[:300],
        }

    return {
        "finding_id": fid,
        "strategy": "needs_human_edit",
        "old": finding.get("old_value", ""),
        "new": finding.get("correct_value") or "REPLACE_WITH_CORRECT_VALUE",
        "rationale": "LLM unavailable — manual edit required",
        "evidence_source": evidence[:300],
    }


def generate_fix_specs(
    family: str,
    platform: str,
    findings: list[dict],
    wave2_only: bool = True,
) -> list[dict]:
    """Generate fix specs for all LLM-strategy findings.

    Args:
        wave2_only: If True, only generate specs for wave-2 (LLM-strategy) findings.
                    Set to False to also attempt auto-fix documentation for wave-1.
    """
    from fix_rules import get_rule, classify_findings  # type: ignore

    sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
    from core.clone_cache import clone_path as _clone_path  # noqa: PLC0415
    clone_cache = _clone_path(family, platform)

    waves = classify_findings(findings)
    target_findings = waves.get(2, [])  # Wave 2 = LLM strategy
    if not wave2_only:
        target_findings = waves.get(1, []) + target_findings

    specs: list[dict] = []
    for finding in target_findings:
        log.info("Generating fix spec for %s (%s)", finding.get("id"), finding.get("type"))
        spec = generate_fix_spec(finding, clone_cache)
        specs.append(spec)

    return specs


def format_evidence_md(
    family: str,
    platform: str,
    specs: list[dict],
) -> str:
    """Format clone cache citations as a Markdown evidence document."""
    lines = [
        f"# Evidence Citations: {family}/{platform}",
        "",
        "Clone cache excerpts supporting each LLM-planned fix.",
        "",
    ]
    for spec in specs:
        fid = spec.get("finding_id", "?")
        strategy = spec.get("strategy", "?")
        evidence = spec.get("evidence_source", "")
        lines += [
            f"## {fid}",
            f"**Strategy**: {strategy}",
            f"**Old**: `{spec.get('old', '')}`",
            f"**New**: `{spec.get('new', '')}`",
            "",
        ]
        if evidence:
            lines += [
                "**Clone cache evidence**:",
                "```",
                evidence,
                "```",
            ]
        else:
            lines.append("_No clone cache evidence found — manual verification required._")
        lines.append("")
    return "\n".join(lines)


def format_plan_md(
    family: str,
    platform: str,
    waves: dict,
    specs: list[dict],
) -> str:
    """Format the wave-ordered remediation plan as Markdown."""
    specs_by_id: dict[str, dict] = {s["finding_id"]: s for s in specs}

    lines = [
        f"# Remediation Plan: {family}/{platform}",
        "",
        "Wave 1 = auto-fix (scripted), Wave 2 = LLM-planned, "
        "Wave 3 = page generation, Wave 4 = manual.",
        "",
    ]

    wave_labels = {
        1: "Wave 1 — Auto-Fix (Run Unattended)",
        2: "Wave 2 — LLM-Planned Patches (Apply File-by-File)",
        3: "Wave 3 — Page Generation Required",
        4: "Wave 4 — Manual Review Required",
    }

    for wave_num in sorted(waves):
        items = waves[wave_num]
        if not items:
            continue
        lines += [f"## {wave_labels[wave_num]}", ""]
        for finding in items:
            fid = finding.get("id", "?")
            ftype = finding.get("type", "?")
            sev = finding.get("severity", "?")
            ffile = finding.get("file", "?")
            fline = finding.get("line", "?")
            lines += [
                f"### {fid}",
                f"**Type**: `{ftype}` | **Severity**: {sev} | **File**: `{ffile}:{fline}`",
                f"**Description**: {finding.get('description', '')}",
                "",
            ]
            spec = specs_by_id.get(fid)
            if spec and spec.get("strategy") == "llm":
                lines += [
                    "**Fix**:",
                    "```diff",
                    f"-{spec['old']}",
                    f"+{spec['new']}",
                    "```",
                    f"**Rationale**: {spec['rationale']}",
                ]
            elif spec and spec.get("strategy") == "needs_human_edit":
                lines += [
                    "**Fix**: NEEDS_HUMAN_EDIT",
                    f"**Old**: `{spec['old']}`",
                    f"**Correct value**: `{spec['new']}`",
                    f"**Note**: {spec['rationale']}",
                ]
            elif wave_num == 1:
                rule = finding.get("_fix_rule")
                method = rule.auto_method if rule else "auto"
                lines += [
                    f"**Fix**: Auto-apply via `{method}`",
                    f"**Old value**: `{finding.get('old_value', '')}`",
                    f"**Correct value**: `{finding.get('correct_value', 'N/A')}`",
                ]
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="S-44: Generate fix specs for gap-eval findings")
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--findings-json", type=Path, default=None,
                        help="Path to findings JSON (default: reports/gap-analysis/{family}-{platform}.json)")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="Output directory (default: reports/agents/remediation/{family}-{platform}/)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    findings_path = args.findings_json or (
        _REPO_ROOT / "reports" / "gap-analysis" / f"{args.family}-{args.platform}.json"
    )
    if not findings_path.exists():
        log.error("Findings JSON not found: %s  (run gap-eval first)", findings_path)
        sys.exit(1)

    data = json.loads(findings_path.read_text(encoding="utf-8"))
    findings = data.get("findings", [])
    log.info("Loaded %d findings for %s/%s", len(findings), args.family, args.platform)

    from fix_rules import classify_findings, wave_summary  # type: ignore

    waves = classify_findings(findings)
    log.info("Wave summary:\n%s", wave_summary(waves))

    specs = generate_fix_specs(args.family, args.platform, findings)
    log.info("Generated %d fix specs", len(specs))

    plan_md = format_plan_md(args.family, args.platform, waves, specs)

    if not args.dry_run:
        out_dir = args.out_dir or (
            _REPO_ROOT / "reports" / "agents" / "remediation" / f"{args.family}-{args.platform}"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_path = out_dir / "plan.md"
        plan_path.write_text(plan_md, encoding="utf-8")
        log.info("Plan written to %s", plan_path)

        specs_path = out_dir / "fix_specs.json"
        specs_path.write_text(json.dumps(specs, indent=2), encoding="utf-8")
        log.info("Fix specs written to %s", specs_path)

        evidence_md = format_evidence_md(args.family, args.platform, specs)
        evidence_path = out_dir / "evidence.md"
        evidence_path.write_text(evidence_md, encoding="utf-8")
        log.info("Evidence citations written to %s", evidence_path)
    else:
        print(plan_md)


if __name__ == "__main__":
    main()
