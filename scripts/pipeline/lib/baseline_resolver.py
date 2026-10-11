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

RPR-J-04 correction (session 5): `baseline_ledger.jsonl` lives under `knowledge/`,
which is entirely gitignored (`.gitignore:20`, `/knowledge`). It is therefore a
fast, concurrency-safe **local cache** — real and useful within one checkout — but
it is NOT durable across a fresh clone, contrary to RPR-C-01's original framing.
The one baseline source that genuinely survives a fresh clone is `evidence.model_sha`,
already committed on every generated content page's frontmatter. When the ledger and
the legacy `model.yaml` scalar are both unavailable (fresh clone, or a product never
migrated), this module now falls back to sampling that field directly from committed
content before giving up — see `_sample_content_model_sha` and its use in
`resolve_baseline_sha`.

NETWORK CONTRACT (MT074 B1): everything here is local EXCEPT one step: when the clone is
shallow and a baseline SHA is not an ancestor of HEAD, `git_reachability_state`/`git_reachable`
call a bounded deepen probe (core.clone_cache: `git fetch` of a few commits, memoized and
capped per process, 60s per fetch). Results are tri-state: reachable / orphaned / unknown; an
outage or cap is "unknown" (`git_reachable` -> False, or raises BaselineReachabilityUnknown
with on_unknown="raise"), never an orphan verdict. Set `ASPOSE_BASELINE_OFFLINE=1` (or pass
`offline=True`) to forbid the fetch entirely.
"""
from __future__ import annotations

import argparse
import os
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
from lib.content_discovery import discover_content  # noqa: E402
from core.markdown import parse_frontmatter  # noqa: E402
from core.clone_cache import REACHABLE, ORPHANED, UNKNOWN  # noqa: E402


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


class BaselineReachabilityUnknown(Exception):
    """Reachability of a baseline SHA could not be determined (network/lock/timeout/cap).

    Raised by ``git_reachable(..., on_unknown="raise")`` instead of reporting False -- an
    unverifiable baseline is NOT an orphaned baseline (see ``git_reachability_state``).
    """

    def __init__(self, sha: str):
        self.sha = sha
        super().__init__(f"baseline reachability unverifiable for {sha[:10]!r} (network/lock/timeout/cap)")


# Setting this environment variable to a truthy value (1/true/yes) forbids ALL network access
# from git_reachability_state/git_reachable: a shallow clone whose ancestry probe fails is then
# UNKNOWN (unverifiable) instead of triggering a deepen fetch.
OFFLINE_ENV = "ASPOSE_BASELINE_OFFLINE"


def _env_offline() -> bool:
    return os.environ.get(OFFLINE_ENV, "").strip().lower() in ("1", "true", "yes")


def _default_deepen(repo_path: "Path | str", sha: str) -> str:
    """Default deepen seam: tri-state verdict from core.clone_cache's memoized, capped,
    time-bounded deepen probe (the ONLY network-touching step in this module). Any import or
    runtime failure is UNKNOWN -- never ORPHANED."""
    try:
        from core.clone_cache import probe_baseline_reachability_at
        return probe_baseline_reachability_at(repo_path, sha)
    except Exception:
        return UNKNOWN


def _is_shallow(repo: str) -> "bool | None":
    """True/False from git; None when git cannot answer. Local-only."""
    try:
        result = subprocess.run(
            ["git", "-C", repo, "rev-parse", "--is-shallow-repository"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() == "true"


def _normalise_deepen_result(result: object) -> str:
    """Map a deepen-seam return value onto REACHABLE / ORPHANED / UNKNOWN.

    A seam may return a tri-state string, or a bool (True = "a deepen completed and claims
    success", False = "completed, still not reachable"). Anything else is UNKNOWN. A REACHABLE
    claim is always re-verified by the caller against real ancestry.
    """
    if result is True:
        return REACHABLE
    if result is False:
        return ORPHANED
    if result in (REACHABLE, ORPHANED, UNKNOWN):
        return str(result)
    return UNKNOWN


def git_reachability_state(
    repo_path: Path | str,
    *,
    deepen: "Callable[[str], object] | None" = None,
    is_shallow: "Callable[[], bool | None] | None" = None,
    offline: "bool | None" = None,
) -> Callable[[str], str]:
    """Build callable(sha) -> "reachable" | "orphaned" | "unknown" for sha vs HEAD in repo_path.

    NETWORK CONTRACT: the plain probe (`git merge-base --is-ancestor`) is local. Only when the
    repo is SHALLOW and the sha is not an ancestor does this call ``deepen(sha)`` -- by default
    core.clone_cache's progressive ``git fetch --deepen`` probe, which is memoized per process
    (including negative/unknown verdicts), capped per process, and time-bounded per fetch.
    A full repo never triggers it. ``offline=True`` (or env ``ASPOSE_BASELINE_OFFLINE=1``)
    forbids it entirely: such a case is "unknown", the honest answer for a truncated history.

    Verdicts: REACHABLE = ancestor of HEAD (re-verified locally AFTER any deepen -- a seam's
    claim of success is never trusted); ORPHANED = full repo, or a COMPLETED deepen, still has
    no path to the sha; UNKNOWN = the deepen could not finish (network, lock, timeout, cap,
    seam error). UNKNOWN must never be reported as an orphan.
    """
    repo = str(repo_path)
    shallow_probe = is_shallow if is_shallow is not None else (lambda: _is_shallow(repo))
    deepen_fn = deepen if deepen is not None else (lambda s: _default_deepen(repo, s))

    def _ancestor(sha: str) -> bool:
        try:
            result = subprocess.run(
                ["git", "-C", repo, "merge-base", "--is-ancestor", sha, "HEAD"],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _state(sha: str) -> str:
        if not sha:
            return ORPHANED
        if _ancestor(sha):
            return REACHABLE
        shallow = shallow_probe()
        if shallow is None:
            return UNKNOWN
        if not shallow:
            return ORPHANED  # full history: definitively not an ancestor
        if offline if offline is not None else _env_offline():
            return UNKNOWN
        try:
            verdict = _normalise_deepen_result(deepen_fn(sha))
        except Exception:
            return UNKNOWN
        if verdict == REACHABLE:
            # Never trust the seam: ancestry is re-verified locally after the deepen.
            return REACHABLE if _ancestor(sha) else ORPHANED
        return verdict

    return _state


def git_reachable(
    repo_path: Path | str,
    *,
    deepen: "Callable[[str], object] | None" = None,
    is_shallow: "Callable[[], bool | None] | None" = None,
    offline: "bool | None" = None,
    on_unknown: str = "false",
) -> Callable[[str], bool]:
    """Build a callable(sha) -> bool testing whether sha is reachable from HEAD in
    repo_path -- i.e. whether it is an ancestor of (or equal to) the current tip,
    not merely whether the commit OBJECT still exists somewhere in the object
    database.

    Bool view of ``git_reachability_state`` (see it for the network contract and the
    deepen/offline seams). ``on_unknown="false"`` (default, legacy) reports an UNKNOWN verdict
    as False; ``on_unknown="raise"`` raises ``BaselineReachabilityUnknown`` so a caller can
    distinguish "unverifiable" from "orphaned" instead of treating an outage as a force-push.

    MT074 B1 (shallow-clone false orphan): the clone cache is ``--depth 2``, so a healthy
    baseline older than the two fetched commits is not an ancestor of HEAD as far as the
    truncated history can tell; the shallow-only deepen path removes that false orphan while a
    genuinely rewritten-away sha stays False.

    RC-1 follow-up (readme-refresh-hardening-and-regen-2026-08-30, found live
    during the font/python TC-27b canary): this previously ran `git cat-file -e
    <sha>^{commit}`, which only tests object EXISTENCE. A history-rewritten orphan
    commit (font/python's real GitLab-canonical -> GitHub-mirror resync) remains a
    dangling-but-present loose object in the local clone cache until garbage-
    collected, so `cat-file -e` wrongly reported it reachable -- silently defeating
    `_check_baseline_reachability`'s entire orphan-detection mechanism for exactly
    the production case it was built to catch (confirmed live: `cat-file -e` exited
    0, `merge-base --is-ancestor` exited 1, for the same SHA against the same real
    clone). `merge-base --is-ancestor sha HEAD` tests true reachability: exit 0 =
    ancestor of HEAD, exit 1 = not an ancestor, any other exit (invalid/missing
    object) also correctly resolves to False here.
    """
    if on_unknown not in ("false", "raise"):
        raise ValueError(f"on_unknown must be 'false' or 'raise', got {on_unknown!r}")
    state_fn = git_reachability_state(repo_path, deepen=deepen, is_shallow=is_shallow, offline=offline)

    def _check(sha: str) -> bool:
        state = state_fn(sha)
        if state == UNKNOWN and on_unknown == "raise":
            raise BaselineReachabilityUnknown(sha)
        return state == REACHABLE

    return _check


def _sample_content_model_sha(
    family: str,
    platform: str,
    *,
    discover_content_fn: Callable[[str, str], list] = discover_content,
) -> str | None:
    """Return the `evidence.model_sha` stamped on the first committed content page
    for this product that has one, or None if no page carries an evidence block yet.

    This is the git-durable fallback RPR-J-04 adds: unlike `baseline_ledger.jsonl`
    (gitignored, local-only), a page's frontmatter is committed, so this value
    survives a fresh clone. Mirrors the read-one-sample-page pattern already used
    by `evidence.runner._sample_stamped_model_version` (same idea, different field).
    """
    for f in discover_content_fn(family, platform):
        fm = parse_frontmatter(f)
        evidence = fm.get("evidence") or {}
        if isinstance(evidence, dict):
            sha = evidence.get("model_sha")
            if sha:
                return sha
    return None


def resolve_baseline_sha(
    family: str,
    platform: str,
    *,
    reachable: Callable[[str], bool],
    repo_root: Path | str | None = None,
    merged_dir: Path | str | None = None,
    model_repo_sha: str | None = None,
    sample_content_model_sha: Callable[[str, str], "str | None"] = _sample_content_model_sha,
) -> BaselineResolution:
    """Resolve the baseline SHA to diff the current HEAD against.

    Args:
        reachable: callable(sha) -> bool, true iff sha is a commit in the FOSS clone.
            Inject a fake in tests; use `git_reachable(repo_path)` in production.
        repo_root / merged_dir: locate the product's baseline ledger (same convention
            as BaselineLedger). This is a local performance cache — see RPR-J-04 — not
            the durable source of truth.
        model_repo_sha: the legacy `model.yaml.repo_sha` scalar, used only as a
            fallback when the ledger has no accepted entry yet (pre-migration).
        sample_content_model_sha: callable(family, platform) -> sha | None, injectable
            for tests; defaults to sampling committed content frontmatter (see
            `_sample_content_model_sha`).

    Returns:
        BaselineResolution with the reachable sha and how it was found.

    Raises:
        OrphanedBaselineError: nothing reachable — an explicit state, never a silent
            empty diff.
    """
    ledger = BaselineLedger(family, platform, repo_root=repo_root, merged_dir=merged_dir)
    tried: list[str] = []

    # 1. Preferred baseline: the ledger's most recent accepted entry (a local cache,
    #    fast when present); else the legacy model.yaml scalar (pre-migration products).
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
    else:
        # RPR-J-04: neither local artifact exists (fresh clone, or a product never
        # migrated to the ledger) — fall back to the one source that IS git-durable:
        # evidence.model_sha, already committed on generated content pages.
        content_sha = sample_content_model_sha(family, platform)
        if content_sha:
            tried.append(content_sha)
            if reachable(content_sha):
                return BaselineResolution(sha=content_sha, source="content-frontmatter")

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
            reachable=git_reachable(args.repo_path, on_unknown="raise"),
            repo_root=args.repo_root,
            model_repo_sha=args.model_sha,
        )
    except BaselineReachabilityUnknown as exc:
        print(f"BASELINE_REACHABILITY_UNVERIFIABLE\t{exc}", file=sys.stderr)
        return 4
    except OrphanedBaselineError as exc:
        print(f"ORPHANED_BASELINE\t{exc}", file=sys.stderr)
        return 3
    print(f"{resolution.sha}\t{resolution.source}\t{resolution.orphaned_from or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
