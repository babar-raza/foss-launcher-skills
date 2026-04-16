"""Tests for check_agent_governance_surface.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_CI_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_CI_ROOT),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_agent_governance_surface  # noqa: E402


def _write(rel_path: Path, text: str) -> None:
    rel_path.parent.mkdir(parents=True, exist_ok=True)
    rel_path.write_text(text, encoding="utf-8")


def _fixture_repo(tmp_path: Path) -> Path:
    _write(
        tmp_path / "CLAUDE.md",
        "# CLAUDE.md\n\n## Critical Rules\n\n1. Read AGENTS.md first\n2. Activate .venv\n",
    )
    _write(
        tmp_path / "CODEX.md",
        "# CODEX.md\n\n## Read Order\n\n1. AGENTS.md\n\n## Critical Rules\n\n1. Skill-first execution\n",
    )
    _write(
        tmp_path / "OPERATOR_GUIDE.md",
        "# Guide\n\nThe system uses AI agents (Claude).\n\n1. Open a Claude Code CLI session.\n",
    )
    _write(
        tmp_path / "README.md",
        "# README\n\nSkills are invoked as slash commands: /skill-name {family} {platform}\n",
    )
    _write(
        tmp_path / ".claude" / "commands" / "README.md",
        "# Claude Code Skills\n\nInternal skills are auto-invoked and auto-enforced.\n",
    )
    _write(
        tmp_path / ".agents" / "skills" / "README.md",
        "# Codex CLI Skills\n\nInternal skills are included here because Codex invokes them directly.\n",
    )
    _write(
        tmp_path / ".kilocode" / "rules-code" / "governance.md",
        "# Governance Rules for Kilo Code\n\n## Skills\n\nSkills are in `.kilocode/skills/`.\n\n## Do / Don't\n\n- **Do** check knowledge\n",
    )
    return tmp_path


def test_analyze_repo_detects_expected_fixture_findings(tmp_path):
    repo_root = _fixture_repo(tmp_path)
    findings = check_agent_governance_surface.analyze_repo(repo_root)
    ids = {finding.finding_id for finding in findings}
    assert ids == {
        "CODEX_MISSING_VENV_RULE",
        "CODEX_MISSING_READ_FIRST_RULE",
        "OPERATOR_GUIDE_CLAUDE_CENTRIC_SCOPE",
        "OPERATOR_GUIDE_MISSING_CODEX_INVOCATION",
        "README_SLASH_COMMAND_ONLY",
        "INTERNAL_SKILL_EXECUTION_ASYMMETRY",
        "REGISTRY_JSON_MISSING",
        "CODEX_MISSING_PREFLIGHT_RULE",
        "KILOCODE_MISSING_PREFLIGHT_RULE",
        "CODEX_MISSING_REGISTRY_REFERENCE",
        "KILOCODE_MISSING_REGISTRY_REFERENCE",
    }


def test_check_baseline_passes_when_all_findings_are_listed(tmp_path):
    repo_root = _fixture_repo(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "findings": [
                    {"finding_id": "CODEX_MISSING_VENV_RULE"},
                    {"finding_id": "CODEX_MISSING_READ_FIRST_RULE"},
                    {"finding_id": "OPERATOR_GUIDE_CLAUDE_CENTRIC_SCOPE"},
                    {"finding_id": "OPERATOR_GUIDE_MISSING_CODEX_INVOCATION"},
                    {"finding_id": "README_SLASH_COMMAND_ONLY"},
                    {"finding_id": "INTERNAL_SKILL_EXECUTION_ASYMMETRY"},
                    {"finding_id": "REGISTRY_JSON_MISSING"},
                    {"finding_id": "CODEX_MISSING_PREFLIGHT_RULE"},
                    {"finding_id": "KILOCODE_MISSING_PREFLIGHT_RULE"},
                    {"finding_id": "CODEX_MISSING_REGISTRY_REFERENCE"},
                    {"finding_id": "KILOCODE_MISSING_REGISTRY_REFERENCE"},
                ]
            }
        ),
        encoding="utf-8",
    )
    rc = check_agent_governance_surface.main(
        [
            "--repo-root",
            str(repo_root),
            "--check-baseline",
            "--baseline-path",
            str(baseline),
        ]
    )
    assert rc == 0


def test_check_baseline_fails_on_new_findings(tmp_path):
    repo_root = _fixture_repo(tmp_path)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "findings": [
                    {"finding_id": "CODEX_MISSING_VENV_RULE"},
                ]
            }
        ),
        encoding="utf-8",
    )
    rc = check_agent_governance_surface.main(
        [
            "--repo-root",
            str(repo_root),
            "--check-baseline",
            "--baseline-path",
            str(baseline),
        ]
    )
    assert rc == 1


def test_repo_baseline_allows_current_repo_findings():
    baseline = _CI_ROOT / "fixtures" / "agent_governance_surface_baseline.json"
    findings = check_agent_governance_surface.analyze_repo(check_agent_governance_surface._REPO_ROOT)
    result = check_agent_governance_surface.compare_to_baseline(findings, baseline)
    assert result["new_findings"] == []
