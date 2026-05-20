# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""Audit agent-governance instruction surfaces for cross-provider drift.

Detects repo-local asymmetries that can cause one agent runtime to follow
governance more reliably than another. The check is intentionally surface-level
and deterministic: it inspects tracked markdown/config files and reports
findings with file/line evidence.

Usage:
    python scripts/ci/checks/check_agent_governance_surface.py
    python scripts/ci/checks/check_agent_governance_surface.py --json
    python scripts/ci/checks/check_agent_governance_surface.py --check-baseline
    python scripts/ci/checks/check_agent_governance_surface.py --check-baseline --ship
    python scripts/ci/checks/check_agent_governance_surface.py --baseline-path path/to/baseline.json

Exit codes:
    0  Report generated successfully; baseline check passed if requested
    1  One or more new findings not present in the approved baseline;
       OR --ship specified and any HIGH severity finding exists
"""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))
_DEFAULT_BASELINE = _REPO_ROOT / "scripts" / "ci" / "fixtures" / "agent_governance_surface_baseline.json"


@dataclass(frozen=True)
class Evidence:
    path: str
    line: int | None
    excerpt: str


@dataclass(frozen=True)
class Finding:
    finding_id: str
    severity: str
    title: str
    detail: str
    evidence: list[Evidence]


def _read_text(repo_root: Path, rel_path: str) -> str:
    p = repo_root / rel_path
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")


def _locate_line(text: str, needle: str) -> tuple[int | None, str]:
    for lineno, line in enumerate(text.splitlines(), start=1):
        if needle.lower() in line.lower():
            return lineno, line.strip()
    return None, needle


def _make_evidence(path: str, text: str, needle: str) -> Evidence:
    line, excerpt = _locate_line(text, needle)
    return Evidence(path=path, line=line, excerpt=excerpt)


def _extract_section(text: str, heading_contains: str) -> str:
    lines = text.splitlines()
    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.startswith("##") and heading_contains.lower() in line.lower():
            start_idx = idx
            break
    if start_idx is None:
        return text

    collected: list[str] = []
    for idx in range(start_idx, len(lines)):
        line = lines[idx]
        if idx > start_idx and line.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected)


def analyze_repo(repo_root: Path) -> list[Finding]:
    claude_md = _read_text(repo_root, "CLAUDE.md")
    codex_md = _read_text(repo_root, "CODEX.md")
    operator_guide = _read_text(repo_root, "OPERATOR_GUIDE.md")
    root_readme = _read_text(repo_root, "README.md")
    claude_readme = _read_text(repo_root, ".claude/commands/README.md")
    agents_readme = _read_text(repo_root, ".agents/skills/README.md")
    operator_invocation = _extract_section(operator_guide, "How to Invoke a Skill")

    findings: list[Finding] = []

    if ".venv" in claude_md.lower() and ".venv" not in codex_md.lower():
        findings.append(
            Finding(
                finding_id="CODEX_MISSING_VENV_RULE",
                severity="high",
                title="CODEX.md omits the explicit .venv rule that CLAUDE.md promotes",
                detail=(
                    "Claude's entrypoint file explicitly tells the agent to use .venv "
                    "instead of system Python, while CODEX.md does not mention .venv. "
                    "That leaves Codex with less repo-specific operational guidance."
                ),
                evidence=[
                    _make_evidence("CLAUDE.md", claude_md, ".venv"),
                    _make_evidence("CODEX.md", codex_md, "## Critical Rules"),
                ],
            )
        )

    if "read agents.md first" in claude_md.lower() and "read agents.md first" not in codex_md.lower():
        findings.append(
            Finding(
                finding_id="CODEX_MISSING_READ_FIRST_RULE",
                severity="medium",
                title="CODEX.md does not restate the 'Read AGENTS.md first' rule in its critical rules",
                detail=(
                    "CLAUDE.md elevates 'Read AGENTS.md first' into Critical Rules. "
                    "CODEX.md has a Read Order section, but it does not repeat that rule "
                    "as an emphasized operational instruction."
                ),
                evidence=[
                    _make_evidence("CLAUDE.md", claude_md, "Read AGENTS.md first"),
                    _make_evidence("CODEX.md", codex_md, "## Read Order"),
                ],
            )
        )

    if "uses ai agents (claude)" in operator_guide.lower():
        findings.append(
            Finding(
                finding_id="OPERATOR_GUIDE_CLAUDE_CENTRIC_SCOPE",
                severity="medium",
                title="OPERATOR_GUIDE.md describes the system as Claude-based",
                detail=(
                    "The operator guide frames the repo around Claude specifically, which "
                    "can bias execution and troubleshooting toward one provider surface."
                ),
                evidence=[
                    _make_evidence("OPERATOR_GUIDE.md", operator_guide, "uses AI agents (Claude)"),
                ],
            )
        )

    if "claude code cli" in operator_invocation.lower() and "codex" not in operator_invocation.lower():
        findings.append(
            Finding(
                finding_id="OPERATOR_GUIDE_MISSING_CODEX_INVOCATION",
                severity="high",
                title="OPERATOR_GUIDE.md documents Claude invocation but not Codex invocation",
                detail=(
                    "The operator guide includes a Claude-only invocation path in the "
                    "main 'How to Invoke a Skill' section and does not provide a parallel "
                    "Codex entrypoint."
                ),
                evidence=[
                    _make_evidence("OPERATOR_GUIDE.md", operator_invocation, "Claude Code CLI"),
                ],
            )
        )

    if "skills are invoked as slash commands" in root_readme.lower() and "codex" not in root_readme.lower():
        findings.append(
            Finding(
                finding_id="README_SLASH_COMMAND_ONLY",
                severity="medium",
                title="README.md teaches slash-command invocation without a Codex-specific entrypoint",
                detail=(
                    "The root README presents skills as slash commands but does not explain "
                    "how Codex should enter the governed workflow, leaving Codex behavior "
                    "more inference-driven."
                ),
                evidence=[
                    _make_evidence("README.md", root_readme, "Skills are invoked as slash commands"),
                ],
            )
        )

    if "auto-invoked" in claude_readme.lower() and "codex invokes them directly" in agents_readme.lower():
        findings.append(
            Finding(
                finding_id="INTERNAL_SKILL_EXECUTION_ASYMMETRY",
                severity="medium",
                title="Provider READMEs document different internal-skill execution models",
                detail=(
                    "Claude's provider README describes internal skills as auto-invoked or "
                    "auto-enforced, while the Codex provider README says Codex orchestrates "
                    "the full canonical set directly. That raises the chance of runtime drift."
                ),
                evidence=[
                    _make_evidence(".claude/commands/README.md", claude_readme, "auto-invoked"),
                    _make_evidence(".agents/skills/README.md", agents_readme, "Codex invokes them directly"),
                ],
            )
        )

    # --- Registry and preflight parity checks ---

    registry_path = repo_root / "skills" / "registry.json"
    if not registry_path.exists():
        findings.append(
            Finding(
                finding_id="REGISTRY_JSON_MISSING",
                severity="high",
                title="skills/registry.json does not exist",
                detail=(
                    "The machine-readable skill registry is missing. Run: "
                    "the sync_providers script to generate it."
                ),
                evidence=[
                    Evidence(path="skills/registry.json", line=None, excerpt="file not found"),
                ],
            )
        )
    else:
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            # Count canonical skills that have S-XX IDs (matching registry generator logic)
            _id_re = re.compile(r"^#\s+(S-\d+):")
            canonical_count = 0
            skills_dir = repo_root / "skills"
            if skills_dir.is_dir():
                for md in skills_dir.glob("*.md"):
                    if md.stem.lower() == "readme":
                        continue
                    text = md.read_text(encoding="utf-8", errors="ignore")[:1500]
                    if any(_id_re.match(line) for line in text.splitlines()):
                        canonical_count += 1
            if registry.get("skill_count", 0) != canonical_count:
                findings.append(
                    Finding(
                        finding_id="REGISTRY_JSON_STALE",
                        severity="high",
                        title="skills/registry.json skill count does not match canonical skills/",
                        detail=(
                            f"Registry has {registry.get('skill_count')} skills but canonical "
                            f"has {canonical_count}. Run the sync_providers script"
                        ),
                        evidence=[
                            Evidence(
                                path="skills/registry.json",
                                line=None,
                                excerpt=f"skill_count: {registry.get('skill_count')}",
                            ),
                        ],
                    )
                )
        except (json.JSONDecodeError, OSError):
            findings.append(
                Finding(
                    finding_id="REGISTRY_JSON_INVALID",
                    severity="high",
                    title="skills/registry.json is not valid JSON",
                    detail="The registry file exists but cannot be parsed as JSON.",
                    evidence=[
                        Evidence(path="skills/registry.json", line=None, excerpt="parse error"),
                    ],
                )
            )

    kilocode_gov = _read_text(repo_root, ".kilocode/rules-code/governance.md")

    if "preflight.py" not in codex_md:
        findings.append(
            Finding(
                finding_id="CODEX_MISSING_PREFLIGHT_RULE",
                severity="high",
                title="CODEX.md does not reference the preflight check script",
                detail=(
                    "The universal preflight script provides "
                    "agent-agnostic pre-write enforcement. CODEX.md should instruct agents to "
                    "run it before every write."
                ),
                evidence=[
                    _make_evidence("CODEX.md", codex_md, "## Critical Rules"),
                ],
            )
        )

    if "preflight.py" not in kilocode_gov:
        findings.append(
            Finding(
                finding_id="KILOCODE_MISSING_PREFLIGHT_RULE",
                severity="high",
                title="Kilo Code governance does not reference the preflight check script",
                detail=(
                    "The universal preflight script provides "
                    "agent-agnostic pre-write enforcement. .kilocode/rules-code/governance.md "
                    "should instruct agents to run it before every write."
                ),
                evidence=[
                    _make_evidence(
                        ".kilocode/rules-code/governance.md",
                        kilocode_gov,
                        "## Do / Don't",
                    ),
                ],
            )
        )

    if "registry.json" not in codex_md:
        findings.append(
            Finding(
                finding_id="CODEX_MISSING_REGISTRY_REFERENCE",
                severity="medium",
                title="CODEX.md does not reference skills/registry.json",
                detail=(
                    "The machine-readable skill registry provides structured skill discovery. "
                    "CODEX.md should reference it for Codex agents."
                ),
                evidence=[
                    _make_evidence("CODEX.md", codex_md, "## Skills"),
                ],
            )
        )

    if "registry.json" not in kilocode_gov:
        findings.append(
            Finding(
                finding_id="KILOCODE_MISSING_REGISTRY_REFERENCE",
                severity="medium",
                title="Kilo Code governance does not reference skills/registry.json",
                detail=(
                    "The machine-readable skill registry provides structured skill discovery. "
                    ".kilocode/rules-code/governance.md should reference it."
                ),
                evidence=[
                    _make_evidence(
                        ".kilocode/rules-code/governance.md",
                        kilocode_gov,
                        "## Skills",
                    ),
                ],
            )
        )

    return findings


def _load_baseline_ids(baseline_path: Path) -> set[str]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    return {entry["finding_id"] for entry in payload.get("findings", [])}


def compare_to_baseline(findings: list[Finding], baseline_path: Path) -> dict[str, list[str]]:
    current_ids = {finding.finding_id for finding in findings}
    baseline_ids = _load_baseline_ids(baseline_path)
    return {
        "new_findings": sorted(current_ids - baseline_ids),
        "resolved_findings": sorted(baseline_ids - current_ids),
        "matching_findings": sorted(current_ids & baseline_ids),
    }


def _serialize_findings(findings: list[Finding]) -> list[dict]:
    return [asdict(finding) for finding in findings]


def _print_report(findings: list[Finding], baseline_result: dict[str, list[str]] | None) -> None:
    if not findings:
        print("PASS: No governance-surface findings detected")
    else:
        print(f"Governance surface findings: {len(findings)}")
        for finding in findings:
            print(f"\n[{finding.severity.upper()}] {finding.finding_id}")
            print(f"  {finding.title}")
            print(f"  {finding.detail}")
            for evidence in finding.evidence:
                line = f":{evidence.line}" if evidence.line is not None else ""
                print(f"    - {evidence.path}{line} -> {evidence.excerpt}")

    if baseline_result is not None:
        print("\nBaseline comparison")
        print(f"  Matching: {len(baseline_result['matching_findings'])}")
        print(f"  New: {len(baseline_result['new_findings'])}")
        print(f"  Resolved: {len(baseline_result['resolved_findings'])}")
        if baseline_result["new_findings"]:
            print("  New findings: " + ", ".join(baseline_result["new_findings"]))
        if baseline_result["resolved_findings"]:
            print("  Resolved findings: " + ", ".join(baseline_result["resolved_findings"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit repo-local agent governance surfaces for provider drift.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(_REPO_ROOT),
        help="Repository root to inspect (defaults to current repo root).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Emit a human-readable report (default if no output mode is selected).",
    )
    parser.add_argument(
        "--check-baseline",
        action="store_true",
        help="Compare findings to the approved baseline and exit 1 on new findings.",
    )
    parser.add_argument(
        "--baseline-path",
        default=str(_DEFAULT_BASELINE),
        help="Path to baseline JSON used by --check-baseline.",
    )
    parser.add_argument(
        "--ship",
        action="store_true",
        help=(
            "Ship mode: exit 1 if any HIGH severity finding exists, regardless of "
            "whether it is in the approved baseline. Use for readiness gates where "
            "HIGH findings must be resolved before merging. Advisory findings "
            "(MEDIUM/LOW) do not block in this mode."
        ),
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    findings = analyze_repo(repo_root)

    baseline_result = None
    if args.check_baseline:
        baseline_result = compare_to_baseline(findings, Path(args.baseline_path))

    payload = {
        "repo_root": str(repo_root),
        "findings": _serialize_findings(findings),
        "summary": {
            "count": len(findings),
        },
    }
    if baseline_result is not None:
        payload["baseline"] = baseline_result

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        _print_report(findings, baseline_result)

    if baseline_result is not None and baseline_result["new_findings"]:
        return 1

    # Ship mode: block on any HIGH severity finding regardless of baseline status.
    if args.ship:
        high_findings = [f for f in findings if f.severity.lower() == "high"]
        if high_findings:
            if not args.json:
                print(
                    f"\nSHIP-MODE BLOCK: {len(high_findings)} HIGH finding(s) must be "
                    f"resolved before this PR can be merged.\n"
                    f"Use --check-baseline (advisory) to track drift without blocking."
                )
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
