"""check_backlog_reconciliation_gate.py — pre-commit Step 32: backlog closure gate.

MT030-2026-08-13: PDF-JAVA-REFRESH-003 stayed Status=queued through two real
knowledge refreshes, then when it finally got hand-closed the closing note was
already 8 days stale on its own central claim ("no truth-audit report exists" —
one had landed 4 days earlier and nobody reconciled it back). Nothing on the
commit path ever checked a backlog row's closure claim against anything durable.

This gate fires ONLY when a commit stages backlog/BACKLOG.md AND that diff
contains a Cat=knowledge row transitioning INTO a closed-family status (was not
closed at HEAD, is closed in the staged version). It fails OPEN (never blocks)
when data/knowledge_state.json has no entry for the row's product yet — a
product nothing has ever recorded state for is not this gate's business, matching
check_stale_file_regression.py's own stated philosophy (missing infra != a red
flag). It blocks only when the durable projection shows no confirmed clean
truth-audit backing a closure claim, and even then only in the absence of a
governed override token (same escape hatch as Step 22/Step 30 — no new bypass
channel).

Usage: staged content paths on stdin (one per line, exactly like Step 22/30);
exit 0 pass / 1 block. If backlog/BACKLOG.md is not among the staged paths,
exits 0 immediately without reading anything else.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_LIB_DIR = _REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_PIPELINE_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_LIB_DIR))

from backlog_parser import parse_table_rows, extract_product_key  # noqa: E402
from knowledge_state import read_state  # noqa: E402

_CLOSED_STATUSES = {"CLOSED", "CLOSED/INVALID", "ACCEPTED", "ACCEPTED_CEILING"}


def _is_closed_status(status: str) -> bool:
    upper = (status or "").upper().strip()
    return any(s in upper for s in _CLOSED_STATUSES)


def _read_git_blob(ref: str, path: str, repo_root: Path) -> str | None:
    """Return the text content of *path* at *ref*, or None if it doesn't exist there."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        return None


def _has_override(path: str, repo_root: Path = _REPO_ROOT) -> bool:
    """Governed override check (same mechanism as Step 21/22/30 — no new bypass channel)."""
    script = repo_root / "scripts" / "pipeline" / "commands" / "governance" / "override_manager.py"
    if not script.is_file():
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(script), "validate-for-path", path],
            capture_output=True, timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_newly_closed_knowledge_rows(head_text: str, staged_text: str) -> list[dict]:
    """Diff HEAD's and the staged version's Cat=knowledge rows; return rows whose
    status transitioned from not-closed (or didn't exist) at HEAD to closed in
    the staged version."""
    head_rows = {r["id"]: r for r in parse_table_rows(head_text) if (r.get("cat") or "").strip().lower() == "knowledge"}
    staged_rows = [r for r in parse_table_rows(staged_text) if (r.get("cat") or "").strip().lower() == "knowledge"]

    newly_closed = []
    for row in staged_rows:
        if not _is_closed_status(row.get("status", "")):
            continue
        prior = head_rows.get(row["id"])
        was_closed_before = prior is not None and _is_closed_status(prior.get("status", ""))
        if not was_closed_before:
            newly_closed.append(row)
    return newly_closed


def check_backlog_closure(head_text: str, staged_text: str, repo_root: Path = _REPO_ROOT) -> list[tuple[str, str]]:
    """Return [(row_id, reason)] for newly-closed Cat=knowledge rows whose closure
    claim isn't backed by a confirmed-clean durable truth-audit record, and that
    lack a governed override."""
    blocked: list[tuple[str, str]] = []
    for row in find_newly_closed_knowledge_rows(head_text, staged_text):
        product_key = extract_product_key(row.get("title", ""))
        if product_key is None:
            continue  # can't resolve a product — nothing to check, don't punish unparseable rows
        family, platform = product_key.split("/", 1)
        state = read_state(family, platform)
        if state is None:
            continue  # fail-open: nothing recorded yet for this product

        truth_audit = state.get("truth_audit")
        if truth_audit is None or truth_audit.get("verdict") != "PASS":
            if _has_override("backlog/BACKLOG.md", repo_root=repo_root):
                continue
            verdict = truth_audit.get("verdict") if truth_audit else "no record"
            blocked.append((
                row["id"],
                f"claims closure ({row.get('status')}) but knowledge_state's last "
                f"truth-audit for {product_key} is {verdict} — re-run S-38 truth-audit "
                f"and confirm PASS before closing, or create a governed override",
            ))
    return blocked


def main() -> int:
    staged = [line.strip().replace("\\", "/") for line in sys.stdin if line.strip()]
    if "backlog/BACKLOG.md" not in staged:
        return 0

    staged_text = _read_git_blob(":", "backlog/BACKLOG.md", _REPO_ROOT)  # ":" = index (staged)
    if staged_text is None:
        return 0  # can't read the staged blob — nothing to check, fail open
    head_text = _read_git_blob("HEAD", "backlog/BACKLOG.md", _REPO_ROOT) or ""

    blocked = check_backlog_closure(head_text, staged_text)
    if blocked:
        print(f"BLOCKED: {len(blocked)} backlog row(s) closing without a confirmed "
              f"clean truth-audit on record:", file=sys.stderr)
        for row_id, reason in blocked:
            print(f"  {row_id}: {reason}", file=sys.stderr)
        print("Fix: re-run the product's S-38 truth-audit and confirm 0 FAIL, then "
              "retry the commit — or create a governed override: "
              "override_manager.py create --paths backlog/BACKLOG.md --reason '...' "
              "--plan '<plan>'", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
