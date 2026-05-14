"""Standalone healing controller primitives.

This module restores the practical orchestration contract used by skills:
HEAL_HINT routing and grouping findings into auto/llm/regen/human buckets. It
does not apply edits; execution remains an explicit downstream step.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

MAX_HEAL_DEPTH = 3

HINT_DISPATCH: dict[str, dict[str, str]] = {
    "forbidden_path": {
        "action": "run_command",
        "command": "override_manager.py create --paths {path} --reason \"{reason}\"",
        "description": "Create an override token for the forbidden path",
    },
    "no_active_context": {
        "action": "run_command",
        "command": "skill_context.py begin --skill {suggested_skill} --scope \"*\"",
        "description": "Begin a skill context before retrying",
    },
    "missing_skill_context": {
        "action": "run_command",
        "command": "skill_context.py begin --skill {suggested_skill} --scope \"{path}\"",
        "description": "Begin or widen skill context",
    },
    "missing_manual_edit_skill": {
        "action": "invoke_skill",
        "command": "/manual-edit",
        "description": "Invoke the manual-edit skill",
    },
    "missing_content_check_pass": {
        "action": "invoke_skill",
        "command": "/content-check {path}",
        "description": "Run content-check for the target path",
    },
    "unsanctioned_py_location": {
        "action": "escalate",
        "command": "",
        "description": "Move Python file to a sanctioned location",
    },
}


def route_from_hint(hint: dict[str, Any]) -> dict[str, Any]:
    violation_type = str(hint.get("violation_type", ""))
    template = HINT_DISPATCH.get(violation_type)
    if template is None:
        return {"violation_type": violation_type, "action": "escalate", "command": "", "description": f"Unknown violation type: {violation_type}", "resolved": False}
    command = template["command"]
    for key, value in hint.items():
        command = command.replace("{" + key + "}", str(value))
    return {"violation_type": violation_type, "action": template["action"], "command": command, "description": template["description"], "resolved": True}


@dataclass(frozen=True)
class HintResolution:
    violation_type: str
    action: str
    resolved: bool
    run_argv: list[str] = field(default_factory=list)
    skill_name: str = ""
    skill_args: str = ""
    escalation_msg: str = ""


def resolve_hint(hint: dict[str, Any]) -> HintResolution:
    route = route_from_hint(hint)
    action = route["action"]
    command = str(route.get("command", ""))
    if action == "run_command" and command:
        return HintResolution(route["violation_type"], action, route["resolved"], run_argv=shlex.split(command))
    if action == "invoke_skill" and command:
        parts = command.split(None, 1)
        return HintResolution(route["violation_type"], action, route["resolved"], skill_name=parts[0], skill_args=parts[1] if len(parts) > 1 else "")
    return HintResolution(route["violation_type"], "escalate", route["resolved"], escalation_msg=str(route.get("description", "")))


def _mode_for(finding: dict[str, Any]) -> str:
    if int(finding.get("heal_depth", 0) or 0) >= MAX_HEAL_DEPTH:
        return "human"
    if finding.get("level") == "INFO" or finding.get("severity") == "I":
        return "skip"
    if finding.get("fix_type"):
        return str(finding["fix_type"])
    category = str(finding.get("category", "")).upper()
    if category in {"UPSTREAM", "LINK"}:
        return "regen"
    if category in {"AA", "PC", "FC", "PT", "CP", "RL", "ST", "RV"}:
        return "llm"
    if category in {"FMT", "STRUCTURE", "FRONTMATTER"}:
        return "auto"
    return "human"


@dataclass
class HealPlan:
    total_findings: int
    groups: dict[str, list[dict[str, Any]]]

    @property
    def total_enabled(self) -> int:
        return sum(len(self.groups.get(mode, [])) for mode in ("auto", "llm", "regen"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_findings": self.total_findings,
            "total_enabled": self.total_enabled,
            "groups": {key: value for key, value in sorted(self.groups.items()) if value},
        }


class HealController:
    def plan(self, findings: list[dict[str, Any]]) -> HealPlan:
        groups: dict[str, list[dict[str, Any]]] = {"auto": [], "llm": [], "regen": [], "human": [], "skip": []}
        for finding in findings:
            groups.setdefault(_mode_for(finding), []).append(finding)
        return HealPlan(total_findings=len(findings), groups=groups)

    def execute(self, plan: HealPlan, *, dry_run: bool = True) -> dict[str, Any]:
        return {
            "dry_run": dry_run,
            "planned": plan.to_dict(),
            "executed": {} if dry_run else {"status": "not_implemented"},
        }
