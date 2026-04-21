"""generate_status.py — Auto-generate the test-count header in reports/STATUS.md.

Usage:
    python scripts/generate_status.py [--append] [--label <milestone-label>]

Runs pytest (--tb=no -q), captures pass/skip/fail counts, reads the latest git
commit message as the milestone label, and updates the top section of
reports/STATUS.md with a new entry.

Options:
    --append        Append a new line to STATUS.md header (default: print-only)
    --label TEXT    Override milestone label (default: first line of git log HEAD)
    --no-tests      Skip running pytest; read last test result from STATUS.md
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = REPO_ROOT / "reports" / "STATUS.md"
PYTEST_SITE = "C:/Users/prora/AppData/Roaming/Python/Python313/site-packages"


def _run_tests() -> tuple[int, int, int]:
    """Run pytest and return (passed, skipped, failed)."""
    result = subprocess.run(
        [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, {PYTEST_SITE!r}); "
            "import pytest; sys.exit(pytest.main(['tests/', '--tb=no', '-q']))",
        ],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300,
    )
    output = result.stdout + result.stderr
    # Parse: "541 passed, 15 skipped in 45.36s" or "2 failed, 539 passed, 15 skipped"
    passed = skipped = failed = 0
    m = re.search(r"(\d+)\s+passed", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+skipped", output)
    if m:
        skipped = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", output)
    if m:
        failed = int(m.group(1))
    return passed, skipped, failed


def _get_git_label() -> str:
    """Return the first line of the most recent git commit message."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    return result.stdout.strip() or "latest"


def _read_status_header(text: str) -> list[str]:
    """Extract the header lines (before the first '---') from STATUS.md text."""
    lines = text.split("\n")
    header = []
    for line in lines:
        if line.strip() == "---":
            break
        header.append(line)
    return header


def _build_entry(passed: int, skipped: int, failed: int, label: str) -> str:
    today = date.today().isoformat()
    total = passed + skipped + failed
    if failed == 0:
        status = "PASS"
    else:
        status = f"FAIL ({failed} failed)"
    parts = [f"**{passed} passed"]
    if skipped:
        parts.append(f"{skipped} skipped")
    if failed:
        parts.append(f"{failed} failed")
    counts = ", ".join(parts) + f" ({total} total), {status}**"
    return f"**{label} ({today})**: {counts}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate STATUS.md test-count entry")
    parser.add_argument("--append", action="store_true", help="Append entry to STATUS.md")
    parser.add_argument("--label", default=None, help="Milestone label override")
    parser.add_argument("--no-tests", action="store_true", help="Skip running tests")
    args = parser.parse_args()

    if args.no_tests:
        # Parse last count from STATUS.md header lines (before the first "---")
        # Format: "**Label (date)**: 541 passed, 15 skipped, 0 failed"
        text = STATUS_FILE.read_text(encoding="utf-8")
        header = text.split("\n---")[0]
        passed = skipped = failed = 0
        for line in reversed(header.split("\n")):
            m = re.search(r"(\d+)\s+passed", line)
            if m:
                passed = int(m.group(1))
                ms = re.search(r"(\d+)\s+skipped", line)
                skipped = int(ms.group(1)) if ms else 0
                mf = re.search(r"(\d+)\s+failed", line)
                failed = int(mf.group(1)) if mf else 0
                break
        print("[INFO] Skipping test run; using values from last STATUS.md entry", file=sys.stderr)
    else:
        print("[INFO] Running pytest ...", file=sys.stderr)
        passed, skipped, failed = _run_tests()

    label = args.label or _get_git_label()
    entry = _build_entry(passed, skipped, failed, label)
    print(entry)

    if args.append:
        text = STATUS_FILE.read_text(encoding="utf-8")
        # Find the last **Post-... line and insert after it, before the first ---
        lines = text.split("\n")
        insert_at = 0
        for i, line in enumerate(lines):
            if line.strip() == "---":
                insert_at = i
                break
        lines.insert(insert_at, entry)
        STATUS_FILE.write_text("\n".join(lines), encoding="utf-8")
        print(f"[INFO] Appended entry to {STATUS_FILE}", file=sys.stderr)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
