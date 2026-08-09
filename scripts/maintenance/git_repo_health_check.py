"""Advisory git object-store health check: git fsck + loose-object count vs gc.auto threshold.

Read-only. Reports findings; does not modify the repository. Run manually or at
session start to catch the "broken link" / loose-object-backlog incident class
(see reports/skill-gaps/2026-08-09-git-object-store-maintenance.md) before it
requires a live forensic re-investigation.

Usage:
    python scripts/maintenance/git_repo_health_check.py
"""
import subprocess
import sys
from pathlib import Path

GC_AUTO_DEFAULT_THRESHOLD = 6700


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _loose_object_count(git_dir: Path) -> int:
    objects_dir = git_dir / "objects"
    count = 0
    for shard in objects_dir.iterdir():
        if shard.is_dir() and len(shard.name) == 2:
            count += sum(1 for f in shard.iterdir() if f.is_file())
    return count


def _find_git_dir() -> Path:
    result = _run(["git", "rev-parse", "--git-common-dir"])
    if result.returncode != 0:
        print("ERROR: not a git repository (or git not on PATH)", file=sys.stderr)
        sys.exit(2)
    return Path(result.stdout.strip())


def main() -> int:
    git_dir = _find_git_dir()
    findings = []

    fsck = _run(["git", "fsck", "--no-progress"])
    broken_links = [line for line in fsck.stdout.splitlines() if "broken link" in line]
    if broken_links:
        findings.append(f"BROKEN LINKS: {len(broken_links)} found (git fsck --no-progress for detail)")

    loose_count = _loose_object_count(git_dir)
    if loose_count > GC_AUTO_DEFAULT_THRESHOLD:
        findings.append(
            f"LOOSE OBJECT BACKLOG: {loose_count} loose objects "
            f"({loose_count / GC_AUTO_DEFAULT_THRESHOLD:.1f}x the gc.auto default threshold "
            f"of {GC_AUTO_DEFAULT_THRESHOLD}) — a prior gc/repack attempt may be failing "
            f"or gc.auto may be disabled without a replacement maintenance schedule"
        )

    gc_auto = _run(["git", "config", "--local", "--get", "gc.auto"])
    gc_auto_value = gc_auto.stdout.strip() or "(unset — git default, effectively enabled)"

    print(f"git-repo-health: {git_dir}")
    print(f"  loose objects: {loose_count} (gc.auto threshold: {GC_AUTO_DEFAULT_THRESHOLD})")
    print(f"  gc.auto: {gc_auto_value}")
    print(f"  fsck broken-link warnings: {len(broken_links)}")

    if findings:
        print("\nFINDINGS:")
        for f in findings:
            print(f"  - {f}")
        return 1

    print("\nHEALTHY: no broken links, loose-object count within threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
