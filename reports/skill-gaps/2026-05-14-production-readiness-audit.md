SKILL GAP ESCALATION
Task: Whole-system production-readiness audit of the aspose.org skills system
Capability state: PARTIAL
Skills invoked (completed): session-start guidance reviewed; existing validators run manually (validate_skills, sync_commands, sync_agents, check_setup, pytest)
Uncovered requirement: No registered skill provides an end-to-end production-readiness audit covering skill definitions, installer behavior, packaging entrypoints, orchestration dependencies, docs, operator workflows, and live script behavior as a single repeatable gate.
Impact: Operators can validate registry sync and selected helper behavior, but cannot run one authoritative readiness command that proves the shipped system is installable, callable, documented, dependency-complete, and safe across launch, refresh, audit, repair, and recovery workflows.

ENHANCEMENT PLAN
  Title: System readiness audit gate
  Proposed skill ID: production-readiness-audit
  Input: repo root, optional content repo path, optional family/platform fixture, optional live-product allowlist
  Output: readiness report, machine-readable findings JSON, runnable command/doc path validation, installer smoke report, dependency graph report, acceptance test matrix, ship/no-ship verdict
  Skill file location: skills/production-readiness-audit.md
  Depends on: session-start, getting-started, validate_skills.py, sync_commands.py, sync_agents.py, check_setup.py, content-eval, launch-product, publish-readiness-review
  Estimated complexity: HIGH
  Workaround available: YES
