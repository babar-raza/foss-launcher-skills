"""detect_source_drift.py -- Detect upstream (aspose.org) drift for ported artifacts.

Sibling to detect_adapter_drift.py, but checks a different axis: whether the
artifacts this repo ported from aspose.org have changed in aspose.org SINCE
they were anchored, instead of whether this repo's own generated adapter
mirrors have drifted from their own canonical source.

Reads docs/parity/source-anchors.yaml (target_path/source_path/commit_sha
rows). For each anchor with a commit_sha, runs a READ-ONLY git diff inside
the source repo comparing the anchored commit to the source repo's current
HEAD for that one file. Never writes to the source repo.

Source repo location is resolved via the SOURCE_REPO_PATH environment
variable ONLY -- this script must never hardcode a filesystem path to
aspose.org (see docs/governance/ portability rules and
tests/fixtures/portability/banned_strings.txt).

HONEST LIMITATION: this check requires both repos checked out side by side
on the same machine. It is not wired into this repo's per-push CI today
(GitHub Actions/GitLab CI runners here do not clone aspose.org) -- it is an
agent/session-invoked check, not a CI gate. Making it a scheduled CI job
would require a runner with both repos available; that is a follow-up
decision, not something this script solves.

Emits .governance/generated/source-drift-report.yaml.

Usage:
    export SOURCE_REPO_PATH=/path/to/aspose-org-checkout
    .venv/bin/python tools/capability_sync/detect_source_drift.py --check
    .venv/bin/python tools/capability_sync/detect_source_drift.py --sync

Exit codes:
  0 -- no drift detected (including: SOURCE_REPO_PATH not set -- this is the
       normal case when the source repo isn't checked out alongside this one;
       skipping is not an error, it's advisory and fails OPEN)
  1 -- --check mode and at least one anchor has drifted
  2 -- SOURCE_REPO_PATH is set but not a valid directory / not a git repo
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ANCHORS_FILE = _REPO_ROOT / "docs" / "parity" / "source-anchors.yaml"
_DRIFT_REPORT = _REPO_ROOT / ".governance" / "generated" / "source-drift-report.yaml"

ENV_SOURCE_REPO_PATH = "SOURCE_REPO_PATH"


def load_anchors():
    if not _HAS_YAML:
        raise RuntimeError("pyyaml required")
    if not _ANCHORS_FILE.exists():
        return []
    with open(_ANCHORS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("anchors", []) or []


def resolve_source_repo(env=None):
    env = os.environ if env is None else env
    raw = env.get(ENV_SOURCE_REPO_PATH, "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    if not (path / ".git").exists():
        raise ValueError("SOURCE_REPO_PATH is not a git working tree (no .git found): " + raw)
    return path


def _run_git(args, repo_root):
    return subprocess.run(
        ["git"] + args, capture_output=True, text=True, cwd=str(repo_root), timeout=30,
    )


def check_anchor(anchor, source_repo):
    source_path = anchor.get("source_path", "")
    commit_sha = anchor.get("commit_sha", "")
    if not source_path or not commit_sha:
        return None

    exists = _run_git(["cat-file", "-e", "HEAD:" + source_path], source_repo)
    if exists.returncode != 0:
        return {
            "target_path": anchor.get("target_path", ""),
            "source_path": source_path,
            "capability_id": anchor.get("capability_id"),
            "anchored_sha": commit_sha,
            "drift_detected": True,
            "reason": "source file no longer exists at HEAD (deleted, renamed, or moved)",
        }

    diff = _run_git(["diff", "--quiet", commit_sha, "HEAD", "--", source_path], source_repo)
    if diff.returncode == 0:
        return None
    if diff.returncode != 1:
        return {
            "target_path": anchor.get("target_path", ""),
            "source_path": source_path,
            "capability_id": anchor.get("capability_id"),
            "anchored_sha": commit_sha,
            "drift_detected": True,
            "reason": "could not diff against anchored commit (git exit %s): %s" % (
                diff.returncode, diff.stderr.strip()[:200]),
        }

    current_sha_result = _run_git(["log", "-1", "--format=%H", "HEAD", "--", source_path], source_repo)
    current_sha = current_sha_result.stdout.strip()[:10] if current_sha_result.returncode == 0 else "?"
    return {
        "target_path": anchor.get("target_path", ""),
        "source_path": source_path,
        "capability_id": anchor.get("capability_id"),
        "anchored_sha": commit_sha,
        "current_sha": current_sha,
        "drift_detected": True,
        "reason": "source file has changed since this artifact was anchored",
    }


def detect_drift(source_repo):
    anchors = load_anchors()
    drift_entries = []
    for anchor in anchors:
        entry = check_anchor(anchor, source_repo)
        if entry:
            drift_entries.append(entry)
    return drift_entries, len(anchors)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Diff only; exit 1 if drift detected")
    mode.add_argument("--sync", action="store_true", help="Write source-drift-report.yaml")
    args = parser.parse_args(argv)

    try:
        source_repo = resolve_source_repo()
    except ValueError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2

    if source_repo is None:
        print(
            "SKIPPED: SOURCE_REPO_PATH not set -- source-drift check requires the "
            "aspose.org repo checked out locally and pointed to via this env var. "
            "This is expected when running without the source repo available (e.g. most CI "
            "runners); it is advisory and does not block anything on its own.",
            file=sys.stderr,
        )
        return 0

    try:
        drift_entries, total = detect_drift(source_repo)
    except Exception as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "generator": "tools/capability_sync/detect_source_drift.py",
        "source_repo_label": "aspose.org",
        "summary": {
            "total_anchors_checked": total,
            "drift_detected_count": len(drift_entries),
            "verdict": "NO_DRIFT" if not drift_entries else "DRIFT_DETECTED",
        },
        "drift_entries": drift_entries,
    }

    if args.sync and _HAS_YAML:
        _DRIFT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        with open(_DRIFT_REPORT, "w", encoding="utf-8") as f:
            yaml.dump(report, f, default_flow_style=False, allow_unicode=True)
        print("Source-drift report written to " + str(_DRIFT_REPORT.relative_to(_REPO_ROOT)))

    if drift_entries:
        print("SOURCE DRIFT: %d anchored artifact(s) have changed upstream since they were ported:" % len(drift_entries))
        for entry in drift_entries:
            print("  %s (source: %s)" % (entry["target_path"], entry["source_path"]))
            print("    anchored at %s -- %s" % (entry["anchored_sha"][:10], entry["reason"]))
        print("")
        print("Re-review these artifacts against the current source and update the anchor "
              "(docs/parity/source-anchors.yaml) once reconciled.")
        if args.check:
            return 1
    else:
        print("PASS: all %d anchored artifact(s) match their upstream state as of anchoring" % total)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
