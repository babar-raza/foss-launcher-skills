#!/usr/bin/env python3
"""baseline_resolver.py — RPR-C-03: resolve a git-reachable baseline SHA, with a
real orphaned-SHA fallback.

Plan §2.3 found that the `orphaned_sha` recovery documented in S-12's skill for
the force-push/rebase case had **zero implementation anywhere** (grep, 0 matches),
and that S-12 read the baseline from a single mutable `model.yaml.repo_sha` scalar
that `promote.py` overwrites every run. This module closes both:

  * It sources the baseline from the append-only `baseline_ledger.jsonl`
    (RPR-C-01) via `last_accepted()`, falling back to the `model.yaml` scalar only
    when the ledger has no accepted entry yet (pre-migration products).
  * When the chosen baseline SHA is **not reachable** in the current git history
    (upstream force-push/rebase), it walks the ledger history newest→oldest for the
    most recent reachable ancestor — the actual `orphaned-recovered` path.
  * When nothing resolves, it raises `OrphanedBaselineError` (an explicit
    ORPHANED_BASELINE state) rather than letting a caller compute an empty diff and
    silently conclude "no changes" — the exact silent-failure §2.3 warns against.

The git-reachability probe is injected (`reachable=`), so the resolution logic is
pure and unit-testable without a repo; `git_reachable(repo_path)` builds the real
probe for production callers (S-12).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_THIS = Path(__file__).resolve()
_PIPELINE_ROOT = _THIS.parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.baseline_ledger import BaselineLedger  # noqa: E402


class OrphanedBaselineError(Exception):
    """No baseline SHA resolves to a reachable git commit (ORPHANED_BASELINE state).

    Raised instead of silently returning an empty diff when the stored baseline was
    force-pushed/rebased away and no ledger ancestor is reachable either.
    """

    def __init__(self, family: str, platform: str, tried: list[str]):
        self.family = family
        self.platform = platform
        self.tried = list(tried)
        super().__init__(
            f"ORPHANED_BASELINE: no reachable baseline SHA for {family}/{platform}; "
            f"tried {self.tried!r} (upstream likely force-pushed/rebased — resolve manually "
            f"or re-establish a baseline via a fresh promote)"
        )


@dataclass
class BaselineResolution:
    """Result of resolving a product's baseline SHA."""

    sha: str
    source: str  # "ledger" | "model-yaml" | "orphaned-recovered"
    orphaned_from: str | None = None  # the unreachable sha this recovered past, if any

    @property
    def is_orphaned_recovery(self) -> bool:
        return self.source == "orphaned-recovered"


def git_reachable(repo_path: Path | str) -> Callable[[str], bool]:
    """Build a callable(sha) -> bool testing whether sha is a commit in repo_path."""
    repo = str(repo_path)

    def _check(sha: str) -> bool:
        if not sha:
            return False
        try:
            result = subprocess.run(
                ["git", "-C", repo, "cat-file", "-e", f"{sha}^{{commit}}"],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    return _check


def resolve_baseline_sha(
    family: str,
    platform: str,
    *,
    reachable: Callable[[str], bool],
    repo_root: Path | str | None = None,
    merged_dir: Path | str | None = None,
    model_repo_sha: str | None = None,
) -> BaselineResolution:
    """Resolve the baseline SHA to diff the current HEAD against.

    Args:
        reachable: callable(sha) -> bool, true iff sha is a commit in the FOSS clone.
            Inject a fake in tests; use `git_reachable(repo_path)` in production.
        repo_root / merged_dir: locate the product's baseline ledger (same convention
            as BaselineLedger).
        model_repo_sha: the legacy `model.yaml.repo_sha` scalar, used only as a
            fallback when the ledger has no accepted entry yet (pre-migration).

    Returns:
        BaselineResolution with the reachable sha and how it was found.

    Raises:
        OrphanedBaselineError: nothing reachable — an explicit state, never a silent
            empty diff.
    """
    ledger = BaselineLedger(family, platform, repo_root=repo_root, merged_dir=merged_dir)
    tried: list[str] = []

    # 1. Preferred baseline: the ledger's most recent accepted entry; else the
    #    legacy model.yaml scalar (pre-migration products only).
    last = ledger.last_accepted()
    primary = (last or {}).get("new_repo_sha")
    primary_source = "ledger"
    if not primary and model_repo_sha:
        primary = model_repo_sha
        primary_source = "model-yaml"

    if primary:
        tried.append(primary)
        if reachable(primary):
            return BaselineResolution(sha=primary, source=primary_source)

    # 2. Orphaned baseline: walk history newest→oldest for the first reachable ancestor.
    for entry in reversed(ledger.history()):
        sha = entry.get("new_repo_sha")
        if not sha or sha in tried:
            continue
        tried.append(sha)
        if reachable(sha):
            return BaselineResolution(sha=sha, source="orphaned-recovered", orphaned_from=primary)

    # 3. Nothing reachable — explicit orphaned state.
    raise OrphanedBaselineError(family, platform, tried)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a git-reachable baseline SHA for a product (RPR-C-03)."
    )
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--repo-path", required=True, help="Path to the FOSS clone (for reachability)")
    parser.add_argument("--repo-root", default=None, help="Repo root holding knowledge/ (default: this repo)")
    parser.add_argument("--model-sha", default=None, help="Legacy model.yaml.repo_sha fallback")
    args = parser.parse_args(argv)

    try:
        resolution = resolve_baseline_sha(
            args.family,
            args.platform,
            reachable=git_reachable(args.repo_path),
            repo_root=args.repo_root,
            model_repo_sha=args.model_sha,
        )
    except OrphanedBaselineError as exc:
        print(f"ORPHANED_BASELINE\t{exc}", file=sys.stderr)
        return 3
    print(f"{resolution.sha}\t{resolution.source}\t{resolution.orphaned_from or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
