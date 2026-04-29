"""S-44 gap-plan — Fix decision rules engine.

Maps each finding type to a fix strategy:
  - auto     : Scripted bulk replacement (safe to run unattended)
  - llm      : LLM-planned patch (requires fix_spec.py)
  - plan     : Plan-only (requires page generation skill)
  - human    : Needs manual review
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FixRule:
    finding_type: str
    strategy: str       # auto | llm | plan | human
    wave: int           # 1=auto bulk, 2=LLM manual, 3=plan/generate, 4=human
    auto_method: str | None = None   # sed | link-audit | bulk-correct
    description: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Rule table — matches plan Section 6 (S-44 Stage 1)
# ---------------------------------------------------------------------------

RULES: list[FixRule] = [
    FixRule(
        finding_type="wrong-package",
        strategy="auto",
        wave=1,
        auto_method="bulk-replace",
        description="Uniform package name replacement across all files",
        notes="Only auto-fix when pattern is uniform (same wrong→right across all files). "
              "If multiple wrong values → split into separate findings first.",
    ),
    FixRule(
        finding_type="broken-link",
        strategy="auto",
        wave=1,
        auto_method="link-audit",
        description="Resolve or remove broken internal links",
        notes="Auto when renamed target exists at known new path. "
              "Auto-remove when target deleted and no replacement. "
              "LLM-plan if replacement is ambiguous.",
    ),
    FixRule(
        finding_type="phantom-api",
        strategy="llm",
        wave=2,
        description="Delete or replace content referencing non-existent API",
        notes="LLM generates 'delete this section' or 'replace with correct API X'.",
    ),
    FixRule(
        finding_type="wrong-api-name",
        strategy="llm",
        wave=2,
        description="Replace wrong API name with correct name from clone cache",
        notes="LLM generates exact old→new substitution grounded in clone cache evidence.",
    ),
    FixRule(
        finding_type="wrong-claim",
        strategy="llm",
        wave=2,
        description="Replace false capability claim with accurate statement",
        notes="LLM generates corrected statement. Must be grounded in clone cache source.",
    ),
    FixRule(
        finding_type="wrong-unit",
        strategy="llm",
        wave=2,
        description="Replace incorrect value or unit with correct value",
        notes="LLM generates corrected value + prose.",
    ),
    FixRule(
        finding_type="unimplemented-as-working",
        strategy="llm",
        wave=2,
        description="Replace 'working' presentation of stub with limitation disclosure",
        notes="LLM generates limitation disclosure text referencing stub evidence.",
    ),
    FixRule(
        finding_type="missing-section",
        strategy="plan",
        wave=3,
        description="Generate missing mandatory content section",
        notes="Requires page-draft (S-19) or appropriate page generation skill.",
    ),
    FixRule(
        finding_type="missing-page",
        strategy="plan",
        wave=3,
        description="Generate missing content page identified by site_plan.yaml",
        notes="Page-level detection supersedes missing-section when site_plan.yaml exists. "
              "Use page-draft (S-19) or new-docs-page / new-kb-howto skill to generate.",
    ),
    FixRule(
        finding_type="structural-reference-page",
        strategy="auto",
        wave=1,
        auto_method="bulk-replace",
        description="Add missing standard headers/sections to reference pages",
        notes="Auto when fix is purely structural (no content invention required).",
    ),
    FixRule(
        finding_type="knowledge-model-wrong",
        strategy="human",
        wave=4,
        description="Knowledge model discrepancy — requires knowledge-update skill",
        notes="Run S-12 (knowledge-diff) then S-14 (knowledge-update) first.",
    ),
    FixRule(
        finding_type="internal-class-wrong-package",
        strategy="auto",
        wave=1,
        auto_method="bulk-correct",
        description="Correct wrong package name for internal class references",
        notes="Add implementation warning comment alongside the correction.",
    ),
]

_RULES_BY_TYPE: dict[str, FixRule] = {r.finding_type: r for r in RULES}


def get_rule(finding_type: str) -> FixRule:
    """Return the fix rule for a finding type, with a default human fallback."""
    return _RULES_BY_TYPE.get(
        finding_type,
        FixRule(
            finding_type=finding_type,
            strategy="human",
            wave=4,
            description=f"Unknown finding type '{finding_type}' — manual review required",
        ),
    )


def classify_findings(findings: list[dict]) -> dict[int, list[dict]]:
    """Group findings by wave number based on fix rules.

    Returns {wave_number: [findings]} dict.
    """
    waves: dict[int, list[dict]] = {1: [], 2: [], 3: [], 4: []}
    for finding in findings:
        if finding.get("status") in ("fixed", "wontfix"):
            continue
        ftype = finding.get("type", "")
        rule = get_rule(ftype)
        waves[rule.wave].append({**finding, "_fix_rule": rule})
    return waves


def wave_summary(waves: dict[int, list[dict]]) -> str:
    """Return a human-readable summary of waves."""
    labels = {
        1: "Wave 1 — Auto-fix (scripted bulk)",
        2: "Wave 2 — LLM-planned manual patches",
        3: "Wave 3 — Plan-only (page generation required)",
        4: "Wave 4 — NEEDS_HUMAN_EDIT (manual review)",
    }
    lines: list[str] = []
    for wave_num in sorted(waves):
        items = waves[wave_num]
        if items:
            lines.append(f"\n### {labels[wave_num]} ({len(items)} findings)")
            for f in items:
                rule = f.get("_fix_rule")
                method = f" [{rule.auto_method}]" if (rule and rule.auto_method) else ""
                lines.append(
                    f"- **{f.get('id', '?')}** `{f.get('type', '?')}`{method} "
                    f"[{f.get('severity', '?')}] `{f.get('file', '?')}:{f.get('line', '?')}`"
                )
    return "\n".join(lines) if lines else "_No open findings._"
