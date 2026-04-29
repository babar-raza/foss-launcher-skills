"""heal_controller.py — Orchestrates the healing pipeline.

Coordinates triage → policy lookup → grouping by heal mode → execution
dispatch → verification → reporting.

Usage:
    from heal_controller import HealController

    ctrl = HealController()
    plan = ctrl.plan(findings)
    results = ctrl.execute(plan, dry_run=True)
    # results["auto"], results["llm"], results["regen"]
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from content_eval.models import Finding
from content_eval.remediation.runner import FixResult, run_fixes
from content_eval.remediation.triage import TriagedFinding, triage_finding
from heal_policy import HealPolicy, lookup, is_heal_enabled
_LIB_DIR = str(Path(__file__).resolve().parent)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_CMD_HEALING = str(Path(__file__).resolve().parent.parent / "commands" / "healing")
if _CMD_HEALING not in sys.path:
    sys.path.insert(0, _CMD_HEALING)
from verify import HealingReport, verify_healing

# TC-3: maximum number of healing rounds before a finding is escalated to human.
MAX_HEAL_DEPTH = 3

# ---------------------------------------------------------------------------
# Hook-healing dispatch (HK-01 TC-HK01-3a)
# ---------------------------------------------------------------------------

# Maps violation_type (from HEAL_HINT JSON) → remediation descriptor.
# Each value is a dict with:
#   action  — "run_command" | "invoke_skill" | "escalate"
#   command — shell command or skill invocation string
#   description — human-readable explanation
_HINT_DISPATCH: dict[str, dict[str, str]] = {
    "forbidden_path": {
        "action": "run_command",
        "command": "override_manager.py create --paths {path} --reason \"{reason}\"",
        "description": "Create an override token for the forbidden path",
    },
    "no_active_context": {
        "action": "run_command",
        "command": "skill_context.py begin --skill {suggested_skill} --scope \"*\"",
        "description": "Begin a skill context before retrying the blocked operation",
    },
    "missing_skill_context": {
        "action": "run_command",
        "command": "skill_context.py begin --skill {suggested_skill} --scope \"{path}\"",
        "description": "Begin or widen skill context to cover the target path",
    },
    "missing_manual_edit_skill": {
        "action": "invoke_skill",
        "command": "/manual-edit",
        "description": "Invoke S-73 manual-edit skill which sets SKIP_CONTENT_EDIT_CHECK=1",
    },
    "missing_content_check_pass": {
        "action": "invoke_skill",
        "command": "/content-check {path}",
        "description": "Run S-23 content-check to produce the .pass marker",
    },
    "unsanctioned_py_location": {
        "action": "escalate",
        "command": "",
        "description": "Move .py file to a sanctioned location (scripts/pipeline/, scripts/ci/, etc.)",
    },
}


def route_from_hint(hint: dict[str, Any]) -> dict[str, Any]:
    """Route a HEAL_HINT to a remediation action.

    Args:
        hint: Parsed HEAL_HINT JSON dict with at least ``violation_type``.

    Returns:
        Dict with keys ``violation_type``, ``action``, ``command`` (with
        placeholders resolved from *hint*), ``description``, and
        ``resolved`` (bool — True if dispatch matched).
    """
    vtype = hint.get("violation_type", "")
    template = _HINT_DISPATCH.get(vtype)

    if template is None:
        return {
            "violation_type": vtype,
            "action": "escalate",
            "command": "",
            "description": f"Unknown violation type: {vtype}",
            "resolved": False,
        }

    # Resolve {placeholders} from hint fields (best-effort)
    command = template["command"]
    for key, val in hint.items():
        command = command.replace(f"{{{key}}}", str(val))

    return {
        "violation_type": vtype,
        "action": template["action"],
        "command": command,
        "description": template["description"],
        "resolved": True,
    }


@dataclass(slots=True)
class HintResolution:
    """Actionable resolution produced by resolve_hint().

    Fields:
        violation_type: The original violation from the HEAL_HINT.
        action: One of "run_command", "invoke_skill", "escalate".
        resolved: True if the dispatch table matched the violation type.
        run_argv: For run_command actions — argv list suitable for subprocess.
        skill_name: For invoke_skill actions — slash-command name (e.g. "/manual-edit").
        skill_args: For invoke_skill actions — argument string after the skill name.
        escalation_msg: For escalate actions — human-readable message.
    """

    violation_type: str
    action: str
    resolved: bool
    run_argv: list[str] = field(default_factory=list)
    skill_name: str = ""
    skill_args: str = ""
    escalation_msg: str = ""


def resolve_hint(hint: dict[str, Any]) -> HintResolution:
    """Resolve a HEAL_HINT to an actionable HintResolution.

    Calls route_from_hint() for dispatch lookup, then populates typed
    fields that downstream code (CLI, orchestrator) can consume directly.

    Args:
        hint: Parsed HEAL_HINT JSON dict with at least ``violation_type``.

    Returns:
        HintResolution with action-specific fields populated.
    """
    route = route_from_hint(hint)
    vtype = route["violation_type"]
    action = route["action"]
    resolved = route["resolved"]
    command = route.get("command", "")

    if action == "run_command" and command:
        # Split into argv — first token is the script name
        import shlex
        argv = shlex.split(command)
        return HintResolution(
            violation_type=vtype, action=action, resolved=resolved,
            run_argv=argv,
        )

    if action == "invoke_skill" and command:
        parts = command.split(None, 1)
        name = parts[0]            # e.g. "/manual-edit" or "/content-check"
        args = parts[1] if len(parts) > 1 else ""
        return HintResolution(
            violation_type=vtype, action=action, resolved=resolved,
            skill_name=name, skill_args=args,
        )

    # escalate (explicit or fallback for unknown types)
    return HintResolution(
        violation_type=vtype, action="escalate", resolved=resolved,
        escalation_msg=route.get("description", f"Escalate: {vtype}"),
    )


@dataclass(slots=True)
class HealItem:
    """A single finding with its triage and policy resolution."""

    finding: Finding
    triaged: TriagedFinding
    policy: HealPolicy
    depth: int = 0          # number of prior healing rounds for this finding (TC-3)
    skip_reason: str = ""   # non-empty when depth guard or policy forces skip

    @property
    def filepath(self) -> str:
        return self.finding.filepath

    @property
    def heal_mode(self) -> str:
        return self.policy.heal_mode

    @property
    def skill(self) -> str:
        return self.policy.skill

    @property
    def is_enabled(self) -> bool:
        return self.heal_mode in ("auto", "llm", "regen")


@dataclass(slots=True)
class HealGroup:
    """A group of HealItems sharing the same heal_mode."""

    heal_mode: str
    items: list[HealItem] = field(default_factory=list)
    files: set[str] = field(default_factory=set)

    @property
    def count(self) -> int:
        return len(self.items)

    def add(self, item: HealItem) -> None:
        self.items.append(item)
        self.files.add(item.filepath)

    def to_dict(self) -> dict[str, Any]:
        return {
            "heal_mode": self.heal_mode,
            "count": self.count,
            "files": sorted(self.files),
            "items": [
                {
                    "finding_id": it.finding.id,
                    "filepath": it.filepath,
                    "category": it.finding.category,
                    "message": it.finding.message,
                    "skill": it.skill,
                    "effort": it.policy.effort,
                }
                for it in self.items
            ],
        }


@dataclass
class HealPlan:
    """The output of HealController.plan() — findings grouped by heal mode."""

    total_findings: int = 0
    total_enabled: int = 0
    total_skipped: int = 0
    total_human: int = 0
    all_files: set[str] = field(default_factory=set)

    auto_group: HealGroup = field(default_factory=lambda: HealGroup(heal_mode="auto"))
    llm_group: HealGroup = field(default_factory=lambda: HealGroup(heal_mode="llm"))
    regen_group: HealGroup = field(default_factory=lambda: HealGroup(heal_mode="regen"))
    human_group: HealGroup = field(default_factory=lambda: HealGroup(heal_mode="human"))
    skip_group: HealGroup = field(default_factory=lambda: HealGroup(heal_mode="skip"))

    @property
    def enabled_files(self) -> set[str]:
        """Files that will be touched by automated healing."""
        return self.auto_group.files | self.llm_group.files | self.regen_group.files

    @property
    def groups(self) -> list[HealGroup]:
        return [self.auto_group, self.llm_group, self.regen_group,
                self.human_group, self.skip_group]

    @property
    def enabled_groups(self) -> list[HealGroup]:
        return [g for g in self.groups if g.heal_mode in ("auto", "llm", "regen") and g.count > 0]

    def to_dict(self) -> dict[str, Any]:
        # depth_map keyed by finding ID — persisted so subsequent runs can increment depth (TC-3)
        depth_map: dict[str, int] = {}
        for g in self.groups:
            for item in g.items:
                depth_map[item.finding.id] = item.depth
        return {
            "total_findings": self.total_findings,
            "total_enabled": self.total_enabled,
            "total_skipped": self.total_skipped,
            "total_human": self.total_human,
            "all_files": sorted(self.all_files),
            "enabled_files": sorted(self.enabled_files),
            "groups": {g.heal_mode: g.to_dict() for g in self.groups if g.count > 0},
            "depth_map": depth_map,
        }

    def summary(self) -> str:
        """One-line summary for logging."""
        parts = []
        for g in self.groups:
            if g.count > 0:
                parts.append(f"{g.heal_mode}={g.count}")
        return (f"HealPlan: {self.total_findings} findings → "
                f"{self.total_enabled} enabled, {self.total_human} human, "
                f"{self.total_skipped} skip [{', '.join(parts)}]")


class HealController:
    """Orchestrates the healing pipeline.

    plan()         — triage + policy lookup + grouping (TH-B1)
    execute_auto() — run deterministic auto-fixers (TH-B2)
    execute_llm()  — emit LLM skill invocation descriptors (TH-B3)
    execute_regen() — emit regen/backtrack skill descriptors (TH-B4)
    execute()      — orchestrate all three modes
    verify()       — compare before/after findings for regression detection (TH-B5)
    """

    def plan(
        self,
        findings: list[Finding],
        depth_map: dict[str, int] | None = None,
    ) -> HealPlan:
        """Triage findings, look up heal policies, group by mode.

        Args:
            findings:  Raw evaluation findings to plan healing for.
            depth_map: Optional mapping of finding_id → prior heal depth (TC-3).
                       Findings at or above MAX_HEAL_DEPTH are routed to human.

        Returns:
            HealPlan with findings grouped by heal_mode.
        """
        result = HealPlan(total_findings=len(findings))
        _depth_map = depth_map or {}

        for finding in findings:
            triaged = triage_finding(finding)
            policy = lookup(triaged)
            depth = _depth_map.get(finding.id, 0)
            item = HealItem(finding=finding, triaged=triaged, policy=policy, depth=depth)

            result.all_files.add(finding.filepath)

            # TC-3: depth guard — escalate to human after MAX_HEAL_DEPTH rounds
            if depth >= MAX_HEAL_DEPTH:
                item.skip_reason = f"max_heal_depth_exceeded ({depth})"
                result.human_group.add(item)
                result.total_human += 1
                continue

            # Route to the correct group
            mode = policy.heal_mode
            if mode == "auto":
                item.depth = depth + 1  # TC-3 FIX-01: increment depth for heal attempt
                result.auto_group.add(item)
                result.total_enabled += 1
            elif mode == "llm":
                item.depth = depth + 1  # TC-3 FIX-01: increment depth for heal attempt
                result.llm_group.add(item)
                result.total_enabled += 1
            elif mode == "regen":
                item.depth = depth + 1  # TC-3 FIX-01: increment depth for heal attempt
                result.regen_group.add(item)
                result.total_enabled += 1
            elif mode == "human":
                result.human_group.add(item)
                result.total_human += 1
            else:  # skip
                result.skip_group.add(item)
                result.total_skipped += 1

        return result

    def plan_for_files(
        self,
        findings: list[Finding],
        target_files: set[str] | list[str],
        depth_map: dict[str, int] | None = None,
    ) -> HealPlan:
        """Plan healing for a specific set of files only.

        Filters findings to those matching target_files before planning.
        """
        target = set(target_files)
        filtered = [f for f in findings if f.filepath in target]
        return self.plan(filtered, depth_map=depth_map)

    # ------------------------------------------------------------------
    # Execute methods (TH-B2, TH-B3, TH-B4)
    # ------------------------------------------------------------------

    def execute_auto(
        self,
        plan: HealPlan,
        *,
        dry_run: bool = False,
        categories: set[str] | None = None,
    ) -> list[FixResult]:
        """Run deterministic auto-fixers on plan.auto_group items.

        Delegates to run_fixes() which handles file batching, fixer
        ordering, and safe file writes.

        Args:
            plan: HealPlan from plan().
            dry_run: If True, report what would change without writing.
            categories: If set, only fix findings in these categories.

        Returns:
            List of FixResult for each finding processed.
        """
        triaged_list = [item.triaged for item in plan.auto_group.items]
        return run_fixes(triaged_list, dry_run=dry_run, categories=categories)

    def execute_llm(self, plan: HealPlan) -> list[dict[str, Any]]:
        """Emit LLM skill invocation descriptors for plan.llm_group items.

        Does NOT invoke skills — returns structured payloads that a CLI
        or orchestrator can consume to invoke S-21 (page-enhance) or
        other LLM-based skills.

        Returns:
            List of dicts, each describing one skill invocation.
        """
        return [
            {
                "skill": item.skill,
                "filepath": item.filepath,
                "finding_id": item.finding.id,
                "category": item.finding.category,
                "level": item.finding.level,
                "message": item.finding.message,
                "suggestion": item.finding.suggestion,
                "effort": item.policy.effort,
                "triage_reason": item.triaged.reason,
            }
            for item in plan.llm_group.items
        ]

    def execute_regen(self, plan: HealPlan) -> list[dict[str, Any]]:
        """Emit regen skill invocation descriptors for plan.regen_group items.

        Regen items require upstream causal backtracking (S-80) before
        local fixes can be applied. The regen_after flag indicates that
        a page regeneration is needed after backtracking completes.

        Returns:
            List of dicts, each describing one skill invocation.
        """
        return [
            {
                "skill": item.skill,
                "filepath": item.filepath,
                "finding_id": item.finding.id,
                "category": item.finding.category,
                "level": item.finding.level,
                "message": item.finding.message,
                "effort": item.policy.effort,
                "regen_after": item.policy.regen_after,
            }
            for item in plan.regen_group.items
        ]

    def execute(
        self,
        plan: HealPlan,
        *,
        dry_run: bool = False,
        mode: str = "all",
    ) -> dict[str, Any]:
        """Orchestrate execution across all heal modes.

        Args:
            plan: HealPlan from plan().
            dry_run: If True, auto-fixers report without writing.
            mode: "auto", "llm", "regen", or "all".

        Returns:
            Dict with keys "auto", "llm", "regen" containing results
            for each executed mode, plus "summary" with counts.
        """
        result: dict[str, Any] = {
            "auto": [],
            "llm": [],
            "regen": [],
        }

        if mode in ("auto", "all") and plan.auto_group.count > 0:
            result["auto"] = self.execute_auto(plan, dry_run=dry_run)

        if mode in ("llm", "all") and plan.llm_group.count > 0:
            result["llm"] = self.execute_llm(plan)

        if mode in ("regen", "all") and plan.regen_group.count > 0:
            result["regen"] = self.execute_regen(plan)

        result["summary"] = {
            "auto_processed": len(result["auto"]),
            "llm_queued": len(result["llm"]),
            "regen_queued": len(result["regen"]),
            "mode": mode,
            "dry_run": dry_run,
        }

        return result

    # ------------------------------------------------------------------
    # Verify (TH-B5)
    # ------------------------------------------------------------------

    def verify(
        self,
        plan: HealPlan,
        *,
        before_findings: list[Finding] | None = None,
        after_findings: list[Finding] | None = None,
        after_report_path: Path | None = None,
    ) -> HealingReport:
        """Verify healing results — compare before/after findings.

        Delegates to verify_healing() for the plan's enabled files.
        Uses the plan's source findings as before_findings if not
        explicitly provided.

        Args:
            plan: HealPlan from plan().
            before_findings: Pre-healing findings. If None, extracts
                from plan's items.
            after_findings: Post-healing findings (from re-evaluation).
            after_report_path: Path to post-healing eval report JSON.

        Returns:
            HealingReport with per-page results and regression detection.
        """
        if before_findings is None:
            before_findings = [
                item.finding for group in plan.groups
                for item in group.items
            ]

        return verify_healing(
            healed_files=plan.enabled_files,
            before_findings=before_findings,
            after_findings=after_findings,
            after_report_path=after_report_path,
        )
