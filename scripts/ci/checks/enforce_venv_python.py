# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""
enforce_venv_python.py — Check or fix bare python/pip invocations in skill bash blocks,
GitHub Actions workflow run: blocks, and Claude Code settings allow lists.

All Python execution in this repo must use .venv/Scripts/python (Windows) or
.venv/bin/python (Linux/macOS) instead of bare `python`, to ensure only
venv-installed dependencies are available.

Usage:
  .venv/Scripts/python scripts/ci/checks/enforce_venv_python.py --check   # report violations, exit 1 if any
  .venv/Scripts/python scripts/ci/checks/enforce_venv_python.py --fix     # rewrite skill files in place

Scans (markdown skill files — auto-fixable):
  skills/*.md                (canonical source of truth — primary target)
  .agents/skills/*/SKILL.md
  .kilocode/skills/*/SKILL.md
  .claude/commands/*.md

Scans (GitHub Actions workflow YAML — check-only, never auto-fixed):
  .github/workflows/*.yml

Scans (Claude Code settings — check-only, never auto-fixed):
  .claude/settings.json
  .claude/settings.local.json

Skips:
  getting-started  (bootstraps the venv itself — handled separately)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent

# Skill markdown directories — fully auto-fixable
SCAN_DIRS = [
    REPO_ROOT / "skills",               # canonical source — primary target
    REPO_ROOT / ".agents" / "skills",
    REPO_ROOT / ".kilocode" / "skills",
    REPO_ROOT / ".claude" / "commands",
]

SKIP_PATTERNS = [
    "getting-started",
]

# GitHub Actions workflow directories — check-only (never auto-fixed)
WORKFLOW_DIRS: list[Path] = [
    REPO_ROOT / ".github" / "workflows",
]

# Claude Code settings files — check-only (never auto-fixed)
SETTINGS_FILES: list[Path] = [
    REPO_ROOT / ".claude" / "settings.json",
    REPO_ROOT / ".claude" / "settings.local.json",
]

# Shell hook scripts in scripts/ci/ — check-only (never auto-fixed).
# These scripts implement the enforcement chain itself, so they must be verified
# to use $PYTHON (resolved to venv) rather than bare python/python3.
SHELL_SCAN_DIRS: list[Path] = [
    REPO_ROOT / "scripts" / "ci",
]


# Governance-critical scripts that are ALWAYS scanned regardless of --include-shell.
# These scripts implement the enforcement chain itself (pre-commit hook, smoke test)
# and must never regress to bare python. Added by TC-VE-06.
GOVERNANCE_CRITICAL_SCRIPTS: list[Path] = [
    REPO_ROOT / "scripts" / "pre-commit-audit.sh",
    REPO_ROOT / "scripts" / "ci" / "hooks" / "smoke_chain.sh",
]

# Lines in workflow run: blocks that require bare system python (exempt from rule).
# python -m venv .venv must use system python to bootstrap the venv itself.
WORKFLOW_EXEMPT_RE = re.compile(r"python\s+-m\s+venv\b")

# Detects the idiomatic GitHub Actions pattern for adding .venv/bin to PATH:
#   echo "$(pwd)/.venv/bin" >> $GITHUB_PATH
# When present in any step of a workflow, bare `python`/`pip` in subsequent
# steps resolve to the venv Python via PATH — semantically equivalent to
# explicit .venv/bin/python and accepted as compliant.
_VENV_PATH_EXPORT_RE = re.compile(r"\.venv/bin.*GITHUB_PATH")

# Replacement rules: (compiled pattern, replacement)
# Applied only inside ```bash ... ``` fences.
RULES: list[tuple[re.Pattern[str], str]] = [
    # bare `python` not already prefixed by .venv or other path
    (re.compile(r"(?<![./\w])python(?=[ \t])"), ".venv/Scripts/python"),
    # bare `pip` for install/show/freeze/uninstall subcommands
    (re.compile(r"(?<![./\w])pip(?=[ \t]+(?:install|show|freeze|uninstall|check))"), ".venv/Scripts/pip"),
]

# Lines containing a venv python/pip invocation already — any additional `python`
# or `pip` token on the SAME line is a CLI argument (e.g. "font python --mode"),
# not a bare invocation.  Skip RULES matching for these lines.
_VENV_INVOCATION_RE = re.compile(r"\.venv/(?:Scripts|bin)/(?:python|pip)\b")

# Deny-only patterns: these are flagged as violations but NOT auto-fixed
# (the correct fix depends on context — manual skill redesign required).
DENY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"pip\s+install\b[^#\n]*--user"), "pip install --user bypasses .venv"),
    (re.compile(r"PYTHONPATH.*\$USER_SITE"), "PYTHONPATH=$USER_SITE bypasses .venv"),
]

# Matches fenced code blocks: ```bash, ```sh, or untagged ```
# (skill files use all three for shell commands)
FENCE_RE = re.compile(r"(```(?:bash|sh)?\n)(.*?)(```)", re.DOTALL)


def _fix_fence(fence_content: str) -> tuple[str, list[str], list[str]]:
    """Apply rules to lines inside a fence.

    Returns (new_content, list_of_fixable_violations, list_of_deny_violations).
    Deny violations are reported but never auto-fixed.
    """
    lines = fence_content.split("\n")
    new_lines = []
    violations: list[str] = []
    deny_violations: list[str] = []
    for line in lines:
        new_line = line
        # If the line already invokes venv python/pip, any later `python`/`pip`
        # token is a CLI argument (e.g. "content_enrich.py font python --mode"),
        # not a bare invocation — skip RULES for this line.
        line_has_venv = bool(_VENV_INVOCATION_RE.search(line))
        if not line_has_venv:
            for pattern, replacement in RULES:
                if pattern.search(new_line):
                    violations.append(line.rstrip())
                    new_line = pattern.sub(replacement, new_line)
        for pattern, description in DENY_PATTERNS:
            if pattern.search(new_line):
                deny_violations.append(f"{description}: {line.rstrip()}")
        new_lines.append(new_line)
    return "\n".join(new_lines), violations, deny_violations


def process_file(path: Path, fix: bool) -> tuple[list[str], list[str]]:
    """Process one markdown file. Returns (fixable_violations, deny_violations)."""
    text = path.read_text(encoding="utf-8")
    all_violations: list[str] = []
    all_deny: list[str] = []

    def replace_fence(m: re.Match[str]) -> str:
        open_tag, content, close_tag = m.group(1), m.group(2), m.group(3)
        new_content, viols, deny = _fix_fence(content)
        all_violations.extend(viols)
        all_deny.extend(deny)
        if fix:
            return open_tag + new_content + close_tag
        return m.group(0)  # unchanged in check mode

    new_text = FENCE_RE.sub(replace_fence, text)

    if fix and new_text != text:
        path.write_text(new_text, encoding="utf-8")

    return all_violations, all_deny


def should_skip(path: Path) -> bool:
    for pattern in SKIP_PATTERNS:
        if pattern in path.parts or pattern in str(path):
            return True
    return False


def collect_files() -> list[Path]:
    files: list[Path] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for md in scan_dir.rglob("*.md"):
            if not should_skip(md):
                files.append(md)
    return sorted(files)


def scan_workflow_file(path: Path) -> tuple[list[str], list[str]]:
    """Scan a GitHub Actions YAML workflow for venv violations in run: blocks.

    CHECK-ONLY — never auto-fixes. Returns (violations, deny_violations).
    Gracefully returns ([], []) if pyyaml is absent or the file cannot be parsed.

    Bare python/pip detection is context-aware: if any step in the workflow
    exports .venv/bin to $GITHUB_PATH (the idiomatic GH Actions venv pattern),
    bare `python`/`pip` calls in run: blocks are semantically compliant and not
    flagged.  DENY patterns (--user, $USER_SITE) are always checked regardless.

    A workflow that does NOT export .venv/bin to $GITHUB_PATH is flagged for
    every bare python/pip call (no venv active — true governance violation).
    """
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        return [], []

    text = path.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(text)
    except Exception:  # noqa: BLE001 — any YAML parse failure
        return [], []

    if not isinstance(doc, dict):
        return [], []

    # Detect whether the workflow activates the venv via $GITHUB_PATH export.
    # If yes, bare `python`/`pip` calls route through venv and are accepted.
    venv_on_path = False
    jobs = doc.get("jobs") or {}
    for _job in jobs.values():
        if not isinstance(_job, dict):
            continue
        for _step in (_job.get("steps") or []):
            run = (isinstance(_step, dict) and _step.get("run")) or ""
            if isinstance(run, str) and _VENV_PATH_EXPORT_RE.search(run):
                venv_on_path = True
                break
        if venv_on_path:
            break

    violations: list[str] = []
    deny_violations: list[str] = []

    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        for step in steps:
            if not isinstance(step, dict):
                continue
            run_block = step.get("run")
            if not isinstance(run_block, str):
                continue
            step_label = step.get("name") or f"job:{job_name}"
            for line in run_block.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                # Bare python/pip: only flag if venv is NOT on PATH
                if not venv_on_path and not WORKFLOW_EXEMPT_RE.search(line):
                    for pattern, _replacement in RULES:
                        if pattern.search(line):
                            violations.append(f"step={step_label!r}: {stripped}")
                            break
                # DENY patterns are always checked regardless of PATH state
                for pattern, description in DENY_PATTERNS:
                    if pattern.search(line):
                        deny_violations.append(
                            f"{description} — step={step_label!r}: {stripped}"
                        )

    return violations, deny_violations


def collect_workflow_files() -> list[Path]:
    """Collect GitHub Actions workflow YAML files for scanning."""
    files: list[Path] = []
    for wf_dir in WORKFLOW_DIRS:
        if not wf_dir.exists():
            continue
        for yml in sorted(wf_dir.glob("*.yml")):
            files.append(yml)
        for yml in sorted(wf_dir.glob("*.yaml")):
            files.append(yml)
    return files


# Regex to extract the command string from Bash(...) allow-list entries
_BASH_ENTRY_RE = re.compile(r"^Bash\((.+)\)$")


def scan_shell_file(path: Path) -> tuple[list[str], list[str]]:
    """Scan a shell script for bare python/pip invocations.

    CHECK-ONLY — never auto-fixes. Returns (violations, deny_violations).

    Exemptions:
    - Lines containing ``python -m venv`` (bootstrap — must use system Python)
    - Lines where the python/pip token appears in a ``PYTHON=`` or ``PIP=``
      assignment (setting a variable, not invoking Python)
    - Lines where the invocation is via ``"$PYTHON"`` or ``$PYTHON`` (already
      resolved to the venv path by the script's own variable setup)
    - Comment lines (starting with #, after stripping whitespace)
    """
    text = path.read_text(encoding="utf-8")
    violations: list[str] = []
    deny_violations: list[str] = []

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Skip variable assignment lines: PYTHON=... or PIP=...
        if re.match(r'^(?:PYTHON|PIP)\s*=', line):
            continue

        # Skip lines that already reference the venv variable (compliant)
        if '"$PYTHON"' in line or "'$PYTHON'" in line or '$PYTHON' in line:
            continue

        # Skip venv bootstrap invocations (must use system python)
        if WORKFLOW_EXEMPT_RE.search(line):
            continue

        # Check bare python/pip rules
        for pattern, _replacement in RULES:
            if pattern.search(line):
                violations.append(f"line {lineno}: {line}")
                break

        # Check deny patterns
        for pattern, description in DENY_PATTERNS:
            if pattern.search(line):
                deny_violations.append(f"{description} — line {lineno}: {line}")

    return violations, deny_violations


def collect_shell_files() -> list[Path]:
    """Collect shell scripts from SHELL_SCAN_DIRS for scanning."""
    files: list[Path] = []
    for scan_dir in SHELL_SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for sh in sorted(scan_dir.glob("*.sh")):
            files.append(sh)
    return files


def scan_settings_file(path: Path) -> tuple[list[str], list[str]]:
    """Scan a Claude Code settings JSON file for venv violations in Bash allow entries.

    CHECK-ONLY — never auto-fixes. Returns (violations, deny_violations).
    """
    if not path.exists():
        return [], []

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], []

    allow_list = (doc.get("permissions") or {}).get("allow") or []
    violations: list[str] = []
    deny_violations: list[str] = []

    for entry in allow_list:
        if not isinstance(entry, str):
            continue
        m = _BASH_ENTRY_RE.match(entry)
        if not m:
            continue
        cmd = m.group(1)
        # Check bare python/pip rules
        for pattern, _replacement in RULES:
            if pattern.search(cmd):
                violations.append(cmd)
                break
        # Check deny patterns
        for pattern, description in DENY_PATTERNS:
            if pattern.search(cmd):
                deny_violations.append(f"{description}: {cmd}")

    return violations, deny_violations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Report violations; exit 1 if any found")
    group.add_argument("--fix", action="store_true", help="Rewrite files in place")
    parser.add_argument(
        "--include-shell",
        action="store_true",
        default=False,
        help=(
            "Also scan shell scripts in scripts/ci/*.sh for bare python/pip invocations "
            "(check-only; never auto-fixed). Off by default to avoid CI noise from legacy "
            "test/simulation scripts that have pre-existing violations. Enable locally to "
            "audit the enforcement chain itself."
        ),
    )
    args = parser.parse_args()

    files = collect_files()
    total_violations = 0
    total_deny = 0
    total_files_changed = 0

    for path in files:
        violations, deny = process_file(path, fix=args.fix)
        rel = path.relative_to(REPO_ROOT)
        if violations:
            total_violations += len(violations)
            total_files_changed += 1
            if args.check:
                print(f"\n{rel}:")
                for v in violations:
                    print(f"  BARE PYTHON: {v.strip()}")
            else:
                print(f"  fixed ({len(violations)} line{'s' if len(violations) != 1 else ''}): {rel}")
        if deny:
            total_deny += len(deny)
            print(f"\n{rel}:")
            for d in deny:
                print(f"  DENY: {d}")

    # Scan GitHub Actions workflow YAML files (check-only regardless of --fix flag)
    total_workflow_violations = 0
    total_workflow_deny = 0
    for path in collect_workflow_files():
        wf_viols, wf_deny = scan_workflow_file(path)
        rel = path.relative_to(REPO_ROOT)
        if wf_viols:
            total_workflow_violations += len(wf_viols)
            print(f"\n{rel} [workflow]:")
            for v in wf_viols:
                print(f"  BARE PYTHON: {v}")
        if wf_deny:
            total_workflow_deny += len(wf_deny)
            print(f"\n{rel} [workflow]:")
            for d in wf_deny:
                print(f"  DENY: {d}")

    # Scan Claude Code settings files (check-only regardless of --fix flag)
    total_settings_violations = 0
    total_settings_deny = 0
    for path in SETTINGS_FILES:
        s_viols, s_deny = scan_settings_file(path)
        if path.exists():
            rel = path.relative_to(REPO_ROOT)
        else:
            continue
        if s_viols:
            total_settings_violations += len(s_viols)
            print(f"\n{rel} [settings]:")
            for v in s_viols:
                print(f"  BARE PYTHON: {v}")
        if s_deny:
            total_settings_deny += len(s_deny)
            print(f"\n{rel} [settings]:")
            for d in s_deny:
                print(f"  DENY: {d}")

    # Scan shell hook scripts in scripts/ci/ (opt-in via --include-shell).
    # Off by default: legacy test/simulation scripts have pre-existing violations
    # that need separate remediation. Enable locally to audit enforcement hook scripts.
    # GOVERNANCE_CRITICAL_SCRIPTS are always scanned regardless of --include-shell (TC-VE-06).
    total_shell_violations = 0
    total_shell_deny = 0
    shell_paths = list(GOVERNANCE_CRITICAL_SCRIPTS)
    if args.include_shell:
        for p in collect_shell_files():
            if p not in shell_paths:
                shell_paths.append(p)
    for path in shell_paths:
        sh_viols, sh_deny = scan_shell_file(path)
        rel = path.relative_to(REPO_ROOT)
        if sh_viols:
            total_shell_violations += len(sh_viols)
            print(f"\n{rel} [shell]:")
            for v in sh_viols:
                print(f"  BARE PYTHON: {v}")
        if sh_deny:
            total_shell_deny += len(sh_deny)
            print(f"\n{rel} [shell]:")
            for d in sh_deny:
                print(f"  DENY: {d}")

    print()
    if args.fix:
        print(f"Fixed {total_violations} violation(s) across {total_files_changed} file(s).")
        if total_deny:
            print(f"Found {total_deny} deny-pattern violation(s) (manual fix required).")
        if total_workflow_violations or total_workflow_deny:
            print(
                f"Found {total_workflow_violations + total_workflow_deny} workflow violation(s) "
                "(manual fix required — workflow files are never auto-fixed)."
            )
        if total_settings_violations or total_settings_deny:
            print(
                f"Found {total_settings_violations + total_settings_deny} settings violation(s) "
                "(manual fix required — settings files are never auto-fixed)."
            )
        if total_shell_violations or total_shell_deny:
            print(
                f"Found {total_shell_violations + total_shell_deny} shell hook violation(s) "
                "(manual fix required — shell files are never auto-fixed)."
            )
        if (total_deny or total_workflow_violations or total_workflow_deny
                or total_settings_violations or total_settings_deny
                or total_shell_violations or total_shell_deny):
            sys.exit(1)
    else:
        has_issues = (total_violations + total_deny + total_workflow_violations + total_workflow_deny
                      + total_settings_violations + total_settings_deny
                      + total_shell_violations + total_shell_deny)
        if has_issues:
            if total_violations:
                print(f"Found {total_violations} bare-python violation(s) across {total_files_changed} file(s).")
                print("Run with --fix to auto-correct bare-python violations in skill files.")
            if total_deny:
                print(f"Found {total_deny} deny-pattern violation(s) (manual fix required).")
            if total_workflow_violations:
                print(f"Found {total_workflow_violations} bare-python violation(s) in workflow files (manual fix required).")
            if total_workflow_deny:
                print(f"Found {total_workflow_deny} deny-pattern violation(s) in workflow files (manual fix required).")
            if total_settings_violations:
                print(f"Found {total_settings_violations} bare-python violation(s) in settings files (manual fix required).")
            if total_settings_deny:
                print(f"Found {total_settings_deny} deny-pattern violation(s) in settings files (manual fix required).")
            if total_shell_violations:
                print(f"Found {total_shell_violations} bare-python violation(s) in shell hook files (manual fix required).")
            if total_shell_deny:
                print(f"Found {total_shell_deny} deny-pattern violation(s) in shell hook files (manual fix required).")
            sys.exit(1)
        else:
            print("No violations found.")


if __name__ == "__main__":
    main()
