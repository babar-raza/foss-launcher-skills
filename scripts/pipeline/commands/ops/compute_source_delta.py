"""compute_source_delta.py -- repeatable "what changed upstream" delta step.

New in this repo (2026-08-29 sync). This is the tool-assisted replacement
for what the 2026-08-29 sync itself had to do by hand: spin up several
research agents for an afternoon to read both repos and work out what
changed since the last comparison. With a source-anchors.yaml commit_sha in
hand (see docs/parity/source-anchors.yaml and
tools/capability_sync/detect_source_drift.py), "what's new since we last
looked" becomes one `git log` against the source repo instead of a full
manual re-audit.

SCOPE, STATED HONESTLY: this script produces a coarse, pre-triaged list, not
a finished decision. It classifies each changed file into a rough bucket
(NEW_SKILL_CANDIDATE / MODIFIED_EXISTING / NEW_INFRA_MODULE / OTHER) and
flags files whose SOURCE content trips the same structural-coupling and
banned-string heuristics used elsewhere in this repo -- it does NOT decide
whether a change belongs in this repo, how to generalize it, or whether a
"MODIFIED_EXISTING" entry represents a real improvement worth porting.
Those are still judgment calls for whoever reviews this script's output
(see the mission's six-way classification taxonomy in TASK_BACKLOG.md --
this tool narrows the expensive part of getting to that taxonomy, it does
not replace it).

Source repo location is resolved via SOURCE_REPO_PATH ONLY -- never
hardcoded (see docs/governance/ portability rules).

Usage:
    export SOURCE_REPO_PATH=/path/to/aspose-org-checkout
    .venv/bin/python scripts/pipeline/commands/ops/compute_source_delta.py --since-sha <sha>
    .venv/bin/python scripts/pipeline/commands/ops/compute_source_delta.py --since-sha <sha> --output reports/source-delta.json

Exit codes:
  0 -- delta computed successfully (even if empty)
  2 -- SOURCE_REPO_PATH not set, invalid, or --since-sha not resolvable
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_DEFAULT_PATHS = [
    "skills/",
    ".claude/commands/",
    "scripts/pipeline/lib/",
    "scripts/pipeline/commands/",
    "docs/governance/",
    "docs/workflows/",
]
ENV_SOURCE_REPO_PATH = "SOURCE_REPO_PATH"

_LINT_DIR = _REPO_ROOT / "scripts" / "ci" / "checks"
if str(_LINT_DIR) not in sys.path:
    sys.path.insert(0, str(_LINT_DIR))
try:
    from check_hardcoded_external_coupling import find_hardcoded_paths, find_hardcoded_subdomain_lists
except ImportError:  # pragma: no cover - defensive
    find_hardcoded_paths = None
    find_hardcoded_subdomain_lists = None


def resolve_source_repo() -> Path:
    raw = os.environ.get(ENV_SOURCE_REPO_PATH, "").strip()
    if not raw:
        raise ValueError("SOURCE_REPO_PATH is not set")
    path = Path(raw).expanduser().resolve()
    if not (path / ".git").exists():
        raise ValueError("SOURCE_REPO_PATH is not a git working tree: " + raw)
    return path


def _run_git(args, repo_root):
    return subprocess.run(
        ["git"] + args, capture_output=True, text=True, cwd=str(repo_root), timeout=60,
    )


def collect_changed_files(source_repo: Path, since_sha: str, paths: list) -> dict:
    """Return {path: latest_status} for every file touched under `paths`
    since since_sha, where latest_status is git's status letter (A/M/D/R...)
    at the MOST RECENT commit that touched it (not every intermediate
    status across the whole range)."""
    result = _run_git(
        ["log", since_sha + "..HEAD", "--name-status", "--format=", "--"] + paths,
        source_repo,
    )
    if result.returncode != 0:
        raise ValueError("git log failed: " + result.stderr.strip())

    changed: dict = {}
    # git log output is newest-first, so the FIRST time we see a path is its
    # most recent status -- do not overwrite on later (older) sightings.
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        status, _, path = line.partition("\t")
        status = status[0]  # collapse R100 etc. to R
        path = path.split("\t")[-1]  # renames: "old\tnew" -- keep new path
        if path not in changed:
            changed[path] = status
    return changed


def classify_file(source_repo: Path, path: str, status: str, target_repo_root: Path) -> dict:
    """Coarse bucket + heuristic flags for one changed source-repo file."""
    p = Path(path)
    target_candidates = _target_candidate_paths(p)
    target_exists = any((target_repo_root / c).exists() for c in target_candidates)

    if p.suffix == ".md" and (p.parts[0] in ("skills", ".claude") or ".claude" in p.parts):
        bucket = "MODIFIED_EXISTING" if target_exists else "NEW_SKILL_CANDIDATE"
    elif "scripts/pipeline/lib" in path or "scripts/pipeline/commands" in path:
        bucket = "MODIFIED_EXISTING" if target_exists else "NEW_INFRA_MODULE"
    else:
        bucket = "MODIFIED_EXISTING" if target_exists else "OTHER"

    flags = []
    if status == "D":
        bucket = "REMOVED_UPSTREAM"
    else:
        full_path = source_repo / path
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if find_hardcoded_paths is not None and p.suffix == ".py":
            if find_hardcoded_paths(text):
                flags.append("hardcoded_absolute_path_in_source")
            if find_hardcoded_subdomain_lists(text):
                flags.append("hardcoded_subdomain_list_in_source")

    return {
        "path": path,
        "git_status": status,
        "bucket": bucket,
        "target_already_exists": target_exists,
        "heuristic_flags": flags,
    }


def _target_candidate_paths(source_path: Path) -> list:
    """Plausible target-repo paths for a given source-repo path, given the
    two repos' differing (but overlapping) layouts -- used only to detect
    'does something with this name already exist', not an exact mapping."""
    candidates = [source_path]
    if source_path.parts[:2] == (".claude", "commands"):
        candidates.append(Path("skills") / source_path.name)
    if source_path.parts[0] == "skills":
        candidates.append(Path(".claude") / "commands" / source_path.name)
    return candidates


def compute_delta(source_repo: Path, since_sha: str, paths: list, target_repo_root: Path) -> dict:
    changed = collect_changed_files(source_repo, since_sha, paths)
    entries = [
        classify_file(source_repo, path, status, target_repo_root)
        for path, status in sorted(changed.items())
    ]
    by_bucket: dict = {}
    for e in entries:
        by_bucket.setdefault(e["bucket"], 0)
        by_bucket[e["bucket"]] += 1
    return {
        "since_sha": since_sha,
        "paths_scanned": paths,
        "total_changed_files": len(entries),
        "counts_by_bucket": by_bucket,
        "entries": entries,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since-sha", required=True, help="Source repo commit SHA to diff from")
    parser.add_argument("--paths", nargs="*", default=_DEFAULT_PATHS,
                         help="Source-repo-relative path prefixes to scan (default: skill/governance surface)")
    parser.add_argument("--output", default=None, help="Write JSON to this file instead of stdout only")
    args = parser.parse_args(argv)

    try:
        source_repo = resolve_source_repo()
    except ValueError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2

    try:
        delta = compute_delta(source_repo, args.since_sha, args.paths, _REPO_ROOT)
    except ValueError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2

    payload = json.dumps(delta, indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print("Delta written to " + str(out_path))
    else:
        print(payload)

    print(
        "\n%d file(s) changed upstream since %s. Buckets: %s"
        % (delta["total_changed_files"], args.since_sha[:10], delta["counts_by_bucket"]),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
