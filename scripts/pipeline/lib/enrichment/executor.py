"""executor.py — Controlled local execution for S-98 enrichment.

Execute mode is disabled by default and requires explicit --allow-local-content-write.
This module creates handoff manifests and execution logs but delegates actual
content generation to downstream skills via the manifest pattern.

Safety requirements:
1. Execute mode disabled by default (CLI flag required)
2. Pre-write snapshot/diff
3. Writes through handoff manifest pattern (no direct content writes)
4. Source evidence attached
5. Failures routed to backlog
6. No publish/deploy/push/PR
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .taxonomy import CandidateDisposition


def execute_plan(plan_result: dict, family: str, platform: str) -> dict:
    """Execute the enrichment plan locally.

    This does NOT directly write content pages. Instead, it:
    1. Validates the plan
    2. Selects the highest-confidence candidates (conservative subset)
    3. Creates an execution manifest with skill-level instructions
    4. Logs the execution for downstream skill invocation

    Actual page creation is done by operators invoking the target skills
    listed in the manifest (S-56, S-57, S-58, S-20).
    """
    manifest = plan_result.get("manifest", {})
    decisions = plan_result.get("decisions", {})
    denominator = plan_result.get("denominator_check", {})

    if not denominator.get("valid"):
        return {"error": "denominator_invariant_failed", "details": denominator}

    manifest_items = manifest.get("manifest_items", [])
    backlog_items = manifest.get("backlog_items", [])

    # Conservative selection: limit to 2 items for pilot
    selected = manifest_items[:2]
    deferred_from_execute = manifest_items[2:]

    exec_log = {
        "family": family,
        "platform": platform,
        "executed_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": "execute",
        "selected_count": len(selected),
        "deferred_from_execute_count": len(deferred_from_execute),
        "backlog_count": len(backlog_items),
        "selected_items": selected,
        "deferred_from_execute": [
            {
                "cluster": item["cluster"],
                "subdomain": item["subdomain"],
                "action": item["action"],
                "reason": "Deferred from execute: conservative pilot limit",
            }
            for item in deferred_from_execute
        ],
        "backlog_items": backlog_items,
        "execution_results": [],
        "status": "manifest_ready",
        "note": (
            "Execute mode creates a skill-invocation manifest. "
            "Actual content generation requires operator invocation of the "
            "listed skills. No content files were directly written by S-98."
        ),
    }

    # Write execution log
    from .coverage_matrix import _repo_root
    out_dir = _repo_root() / "reports" / "enrichment" / family / platform
    out_dir.mkdir(parents=True, exist_ok=True)

    log_path = out_dir / "execution-log.json"
    log_path.write_text(json.dumps(exec_log, indent=2, default=str), encoding="utf-8")

    # Write execution report
    report = _build_execution_report(exec_log)
    report_path = out_dir / "enrichment-report.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"Execute manifest ready for {family}/{platform}")
    print(f"  Selected for execution: {len(selected)}")
    print(f"  Deferred from execute: {len(deferred_from_execute)}")
    print(f"  Backlog items: {len(backlog_items)}")
    print(f"  Status: {exec_log['status']}")
    print(f"  Output: {out_dir}")

    return exec_log


def _build_execution_report(exec_log: dict) -> str:
    """Build human-readable execution report."""
    lines = [
        f"# Enrichment Execution Report: {exec_log['family']}/{exec_log['platform']}",
        "",
        f"Executed: {exec_log['executed_at']}",
        f"Mode: {exec_log['mode']}",
        f"Status: {exec_log['status']}",
        "",
        "## Selected for Execution",
        "",
    ]

    for item in exec_log.get("selected_items", []):
        lines.append(
            f"- **{item['cluster']}** / {item['subdomain']}: "
            f"{item['action']} (skill: {item['target_skill']}, score: {item['score']})"
        )

    if exec_log.get("deferred_from_execute"):
        lines.append("")
        lines.append("## Deferred from Execute (Conservative Pilot Limit)")
        lines.append("")
        for item in exec_log["deferred_from_execute"]:
            lines.append(f"- {item['cluster']} / {item['subdomain']}: {item['reason']}")

    if exec_log.get("backlog_items"):
        lines.append("")
        lines.append("## Backlog Items")
        lines.append("")
        for item in exec_log["backlog_items"]:
            lines.append(f"- {item['cluster']} / {item['subdomain']}: {item['reason']} (score: {item['score']})")

    lines.append("")
    lines.append("## Operator Instructions")
    lines.append("")
    lines.append("To execute the selected items, invoke the listed skills:")
    lines.append("")
    for item in exec_log.get("selected_items", []):
        skill = item["target_skill"]
        lines.append(f"1. `/{_skill_command(skill)}` for {item['cluster']} ({item['subdomain']})")
    lines.append("")
    lines.append("No content was directly written by S-98 execute mode.")
    lines.append("")

    return "\n".join(lines)


def _skill_command(skill_id: str) -> str:
    """Map skill ID to slash command name."""
    commands = {
        "S-56": "new-docs-page",
        "S-57": "new-blog-post",
        "S-58": "new-kb-howto",
        "S-20": "page-update",
    }
    return commands.get(skill_id, f"skill-{skill_id}")
