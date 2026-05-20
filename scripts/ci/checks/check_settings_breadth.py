# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""
check_settings_breadth.py — Validate that .claude/settings.json permissions.allow
entries are narrow and do not grant overbroad auto-approval.

This scanner reads .claude/settings.json (and .claude/settings.local.json if present),
extracts Bash(...) entries from permissions.allow, and rejects entries whose command
patterns are too broad.  Broad patterns are dangerous because they auto-approve
tool calls without user confirmation — even though hooks still fire, the user loses
the opportunity to review each command before execution.

Usage:
  .venv/Scripts/python scripts/ci/checks/check_settings_breadth.py          # scan real settings
  .venv/Scripts/python scripts/ci/checks/check_settings_breadth.py FILE...  # scan specific files

Exit codes:
  0 = all entries are narrow enough
  1 = overbroad or dangerous entries found

Never modifies files.
"""
from __future__ import annotations

import json
import re
import os
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", str(Path(__file__).resolve().parent.parent.parent.parent)))

DEFAULT_FILES: list[Path] = [
    REPO_ROOT / ".claude" / "settings.json",
    REPO_ROOT / ".claude" / "settings.local.json",
]

# Extract the command string from Bash(...) entries.
_BASH_RE = re.compile(r"^Bash\((.+)\)$", re.DOTALL)

# ---------------------------------------------------------------------------
# Overbroad pattern definitions
# ---------------------------------------------------------------------------
# Each tuple: (compiled regex, human-readable reason)
# These patterns match against the COMMAND portion inside Bash(...).

OVERBROAD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Arbitrary Python execution
    (re.compile(r"^\.venv/(?:Scripts|bin)/python\s+\*$"),
     "arbitrary Python execution (.venv/.../python *)"),
    (re.compile(r"^\.venv/(?:Scripts|bin)/python\s+scripts/\*$"),
     "arbitrary repo script execution (.venv/.../python scripts/*)"),
    (re.compile(r"^\.venv/(?:Scripts|bin)/python\s+-m\s+pytest\s+\*$"),
     "pytest on any directory (.venv/.../python -m pytest *)"),

    # Bare Python/Python3/py (no venv) — TC-AUDIT-01
    (re.compile(r"^(?:python3?|py)\s"),
     "bare Python execution without venv"),

    # Pip / package install — TC-AUDIT-01
    (re.compile(r"^(?:pip3?|\.venv/(?:Scripts|bin)/pip)\s+install\s"),
     "pip install auto-approval"),
    (re.compile(r"^\.venv/(?:Scripts|bin)/python\s+-m\s+pip\s+install\s"),
     "pip install via python -m pip"),

    # Remote code execution (curl/wget piped to shell) — TC-AUDIT-01
    (re.compile(r"(?:curl|wget)\s.*\|\s*(?:ba)?sh"),
     "remote code execution (curl/wget piped to shell)"),

    # PowerShell remote execution (iwr/irm piped to iex) — TC-AUDIT-01
    (re.compile(r"(?:iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\s.*\|\s*iex"),
     "PowerShell remote code execution (iwr/irm piped to iex)"),

    # Overly permissive file permissions — TC-AUDIT-01
    (re.compile(r"^chmod\s+(?:-R\s+)?777\s"),
     "chmod 777 auto-approval"),

    # Privilege escalation — TC-AUDIT-01
    (re.compile(r"^sudo\s"),
     "sudo auto-approval"),

    # Arbitrary PYTHONPATH + execution
    (re.compile(r"^PYTHONPATH=\*\s"),
     "arbitrary PYTHONPATH prefix (PYTHONPATH=* ...)"),

    # Arbitrary shell/system execution
    (re.compile(r"^bash\s+\*$"),
     "arbitrary bash execution (bash *)"),
    (re.compile(r"^(?:powershell|pwsh)\s"),
     "PowerShell execution"),
    (re.compile(r"^cmd\s"),
     "cmd execution"),

    # Destructive commands
    (re.compile(r"^rm\s+"),
     "rm auto-approval"),
    (re.compile(r"^del\s"),
     "del auto-approval"),
    (re.compile(r"^git\s+push\s+\*"),
     "broad git push auto-approval (git push *)"),
    (re.compile(r"^git\s+reset\s+\*"),
     "broad git reset auto-approval (git reset *)"),
    (re.compile(r"^git\s+clean\s"),
     "git clean auto-approval"),

    # Catch-all: any entry that is ONLY a wildcard
    (re.compile(r"^\*$"),
     "wildcard-only entry (*)"),
]

# Structural breadth checks (applied after pattern matching).
_TRAILING_STAR_SCRIPT_RE = re.compile(
    r"\.venv/(?:Scripts|bin)/python\s+scripts/\S+/\*$"
)


def _is_overbroad_structural(cmd: str) -> str | None:
    """Return a reason string if the command is structurally overbroad, else None.

    Catches patterns like:
      .venv/Scripts/python scripts/pipeline/* (auto-approves entire directory tree)

    But allows:
      .venv/Scripts/python scripts/ci/checks/check_foo.py (exact)
      .venv/Scripts/python -m pytest scripts/pipeline/tests/* (test dirs OK)
    """
    # Allow pytest wildcards on known test directories — these are safe.
    if re.search(r"-m\s+pytest\s+", cmd):
        return None
    # Allow -m unittest wildcards similarly
    if re.search(r"-m\s+unittest\s+", cmd):
        return None

    # Flag scripts/<subdir>/* that is NOT a test runner
    if _TRAILING_STAR_SCRIPT_RE.search(cmd):
        return f"auto-approves entire script directory: {cmd}"

    return None


def scan_allow_list(entries: list[str]) -> list[tuple[str, str]]:
    """Scan a permissions.allow list. Returns list of (entry, reason) violations.

    TC-AUDIT-02: Reports ALL matching violations per entry (no early break).
    TC-AUDIT-03: Non-string entries produce a diagnostic violation.
    """
    violations: list[tuple[str, str]] = []

    for entry in entries:
        # TC-AUDIT-03: non-string entries get a diagnostic
        if not isinstance(entry, str):
            violations.append(
                ("<type-error>", f"non-string entry in permissions.allow: {entry!r}"))
            continue
        m = _BASH_RE.match(entry)
        if not m:
            continue
        cmd = m.group(1)

        # TC-AUDIT-02: collect ALL matching pattern violations (no break)
        for pattern, reason in OVERBROAD_PATTERNS:
            if pattern.search(cmd):
                violations.append((entry, reason))

        # Structural breadth check (always runs, independent of pattern matches)
        structural = _is_overbroad_structural(cmd)
        if structural:
            violations.append((entry, structural))

    return violations


def scan_file(path: Path) -> list[tuple[str, str]]:
    """Scan one settings file. Returns list of (entry, reason) violations."""
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [("<parse-error>", f"could not parse {path}")]

    allow_list = (doc.get("permissions") or {}).get("allow") or []

    # TC-AUDIT-03: permissions.allow must be a list if present
    if not isinstance(allow_list, list):
        return [("<type-error>",
                 f"permissions.allow must be a list, got {type(allow_list).__name__}")]

    return scan_allow_list(allow_list)


def main() -> None:
    files = [Path(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else DEFAULT_FILES

    total_violations = 0
    for path in files:
        violations = scan_file(path)
        if violations:
            rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
            print(f"\n{rel}:")
            for entry, reason in violations:
                print(f"  OVERBROAD: {entry}")
                print(f"    reason:  {reason}")
            total_violations += len(violations)

    if total_violations:
        print(f"\nFound {total_violations} overbroad permission(s). "
              "Narrow the patterns or remove them.")
        sys.exit(1)
    else:
        print("No overbroad permissions found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
