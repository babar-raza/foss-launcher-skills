"""Deterministic fix routing rules for standalone gap-eval reports."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FixRule:
    finding_type: str
    strategy: str
    wave: int
    auto_method: str | None = None
    description: str = ""
    notes: str = ""


RULES: tuple[FixRule, ...] = (
    FixRule("wrong-package", "auto", 1, "bulk-replace", "Uniform package name replacement"),
    FixRule("broken-link", "auto", 1, "link-audit", "Resolve or remove broken internal links"),
    FixRule("structural-reference-page", "auto", 1, "bulk-replace", "Repair reference page structure"),
    FixRule("internal-class-wrong-package", "auto", 1, "bulk-correct", "Correct internal class package"),
    FixRule("phantom-api", "llm", 2, description="Replace or remove non-existent API references"),
    FixRule("wrong-api-name", "llm", 2, description="Replace wrong API names with grounded names"),
    FixRule("wrong-claim", "llm", 2, description="Replace false capability claims"),
    FixRule("wrong-unit", "llm", 2, description="Replace incorrect values or units"),
    FixRule("unimplemented-as-working", "llm", 2, description="Disclose known limitations"),
    FixRule("missing-section", "plan", 3, description="Generate missing mandatory section"),
    FixRule("missing-page", "plan", 3, description="Generate missing planned page"),
    FixRule("knowledge-model-wrong", "human", 4, description="Knowledge model discrepancy"),
)

_RULES_BY_TYPE = {rule.finding_type: rule for rule in RULES}


def get_rule(finding_type: str) -> FixRule:
    return _RULES_BY_TYPE.get(
        finding_type,
        FixRule(
            finding_type=finding_type,
            strategy="human",
            wave=4,
            description=f"Unknown finding type '{finding_type}' requires operator review",
        ),
    )


def classify_findings(findings: list[dict]) -> dict[int, list[dict]]:
    waves: dict[int, list[dict]] = {1: [], 2: [], 3: [], 4: []}
    for finding in findings:
        if finding.get("status") in {"fixed", "wontfix"}:
            continue
        rule = get_rule(str(finding.get("type", "")))
        waves[rule.wave].append({**finding, "_fix_rule": rule})
    return waves


def wave_summary(waves: dict[int, list[dict]]) -> str:
    labels = {
        1: "Wave 1 - Auto-fix",
        2: "Wave 2 - Planned patch",
        3: "Wave 3 - Generation plan",
        4: "Wave 4 - Operator review",
    }
    lines: list[str] = []
    for wave in sorted(waves):
        findings = waves[wave]
        if not findings:
            continue
        lines.append(f"### {labels[wave]} ({len(findings)})")
        for finding in findings:
            rule = finding.get("_fix_rule")
            method = f" [{rule.auto_method}]" if rule and rule.auto_method else ""
            lines.append(
                f"- {finding.get('id', '?')} `{finding.get('type', '?')}`{method}: "
                f"{finding.get('description', '')}"
            )
    return "\n".join(lines) if lines else "_No open findings._"
