#!/usr/bin/env python3
"""_plan_gate.py — helper for check_plan_origination_gate_hook.sh (PSE-03/04).

Reads the breadcrumb written by _plan_capture.py (via the Write/Edit capture
hook), runs check_plan_origination.py against the recorded plan file if the
breadcrumb is present and fresh, and prints exactly one verdict line to
stdout for the bash wrapper to act on:

    SKIP|<reason>              nothing to check / fail open — never block
    ALLOW|no findings          plan is clean
    SHADOW_BLOCK|<rules>       would have blocked, but mode=shadow never blocks
    BLOCK|<rules>|<reasons>    mode=enforce and a violation was found

All path handling stays in Python (pathlib) deliberately — see
check_plan_origination_capture_hook.sh's header comment for why: bash string
substitution for backslash/drive-letter normalization was found unreliable
in this environment, and native Windows Python does not understand
git-bash's "/c/Users/..." POSIX path convention for file I/O.

Usage: python _plan_gate.py <mode: shadow|enforce>
"""
import sys
import os
import json
import datetime
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _HOOKS_DIR.parent.parent.parent  # scripts/ci/hooks -> scripts/ci -> scripts -> repo root
_CHECKS_DIR = _REPO_ROOT / "scripts" / "ci" / "checks"

sys.path.insert(0, str(_CHECKS_DIR))


def _emit(line: str) -> int:
    print(line)
    return 0


def main(argv) -> int:
    mode = argv[1] if len(argv) > 1 else "shadow"

    home = Path(os.environ.get("HOME", os.path.expanduser("~")))
    breadcrumb = home / ".claude" / "plans" / ".last-plan-write.json"

    if not breadcrumb.is_file():
        return _emit("SKIP|no-breadcrumb")

    try:
        data = json.loads(breadcrumb.read_text(encoding="utf-8"))
        written_at = datetime.datetime.strptime(data["written_at"], "%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return _emit("SKIP|unreadable-breadcrumb")

    age = (datetime.datetime.utcnow() - written_at).total_seconds()
    if age < 0 or age > 3600:
        return _emit("SKIP|stale-breadcrumb")

    plan_file = data.get("file_path", "")
    if not plan_file or not Path(plan_file).is_file():
        return _emit("SKIP|plan-file-missing")

    import check_plan_origination as checker

    findings = checker.scan_file(plan_file)

    log_dir = _REPO_ROOT / "reports" / "governance"
    log_file = log_dir / "plan-origination-gate.log"
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        rules_str = ",".join(f.rule for f in findings) if findings else "no findings"
        verdict_str = "ALLOW" if not findings else ("BLOCK" if mode == "enforce" else "SHADOW_WOULD_BLOCK")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{timestamp}|{mode}|{plan_file}|{verdict_str}|{rules_str}\n")
    except Exception:
        pass

    if not findings:
        return _emit("ALLOW|no findings")

    rules = ",".join(f.rule for f in findings)
    reasons = "; ".join(f.reason for f in findings)

    if mode == "enforce":
        return _emit(f"BLOCK|{rules}|{reasons}")
    return _emit(f"SHADOW_BLOCK|{rules}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
