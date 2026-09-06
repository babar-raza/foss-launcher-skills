"""freshness_guard.py — single source of truth for knowledge-bundle freshness.

CONTRACT: scripts/pipeline/lib/freshness_guard.py
  purpose: FRESH-001 (2026-08-14). Before this module, every consumer (batch_reference.py,
           refresh_run.py, launch_gate.py, readiness_gate.py) independently read
           `model.yaml["stale_since"]` and treated `None` as "safe to use" — a cached
           boolean that is only ever updated by a human/agent remembering to run
           `/knowledge-diff`, never a live-provable relationship to upstream. This module
           is the one place that state gets computed, in 10 explicit states with
           strict/degraded/offline modes, so every gate can be migrated to call the same
           function instead of re-deriving the same (previously wrong) assumption.
  resolution order: merged/model.yaml is now git-tracked (T0/T2) and is the single
           canonical writer of "accepted baseline SHA" — data/upstream_baselines.json and
           data/knowledge_state.json are DERIVED, REGENERATED projections
           (regen_baseline_projections.py), not independent beliefs. resolve_baseline()
           therefore prefers model.yaml first; the projections are consulted only as a
           fast-lookup fallback (and to detect CORRUPT — see below), and the pre-existing
           local ledger / content-frontmatter fallbacks (baseline_resolver.py's
           `_sample_content_model_sha`) remain the last resort for cold-start products.
  reachability (RC-1 / TC-11, readme-refresh-hardening-and-regen-2026-08-30): a resolved
           baseline SHA is now also checked for git reachability against the product's
           local clone cache (local-only, no network — safe in degraded AND strict modes,
           deliberately skipped in offline mode) — see _check_baseline_reachability()'s own
           docstring for the full rationale (font/python vs. slides/python: two orphaned-
           baseline cases requiring OPPOSITE verdicts, which a commit-SHA-only check could
           never distinguish).
  states:  CURRENT, STALE, REFRESHING, REFRESH_FAILED, UPSTREAM_UNAVAILABLE,
           PROVENANCE_MISSING, CORRUPT, LAST_KNOWN_GOOD, HISTORY_REWRITTEN_CONTENT_IDENTICAL,
           STALE_ORPHANED — see check_freshness()'s docstring for the full semantics of each.
  modes:   strict (requires a live upstream comparison + bundle self-verification;
           network failure -> UPSTREAM_UNAVAILABLE, never a silent downgrade),
           degraded (no network call — the default for high-volume generation-time
           callers, resolves purely from durable/local source agreement), offline
           (resolve_baseline() only, never fails/hangs — for read-only status CLIs).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import yaml

# Self-register both scripts/pipeline/ (for core.*/commands.* subpackage imports)
# AND this file's own lib/ directory (for bare sibling imports like
# `from baseline_resolver import ...` / `from knowledge_regen_lock import ...` below)
# -- production scripts are invoked with only PYTHONPATH=scripts/pipeline set, which
# does not put scripts/pipeline/lib itself on sys.path (conftest.py does this for
# tests, but this module must be self-sufficient outside pytest too).
_PIPELINE_DIR = Path(__file__).resolve().parents[1]  # lib/ -> pipeline/
_LIB_DIR = Path(__file__).resolve().parent  # lib/ itself
for _p in (str(_PIPELINE_DIR), str(_LIB_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root
REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
DATA_DIR = REPO_ROOT / "data"
PRODUCTS_JSON = DATA_DIR / "products.json"
UPSTREAM_BASELINES_PATH = DATA_DIR / "upstream_baselines.json"
KNOWLEDGE_STATE_PATH = DATA_DIR / "knowledge_state.json"
LAST_KNOWN_GOOD_LOG = REPO_ROOT / "reports" / "freshness_guard" / "last_known_good.log.jsonl"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, KNOWLEDGE_ROOT, DATA_DIR, PRODUCTS_JSON, UPSTREAM_BASELINES_PATH
    global KNOWLEDGE_STATE_PATH, LAST_KNOWN_GOOD_LOG
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
    DATA_DIR = REPO_ROOT / "data"
    PRODUCTS_JSON = DATA_DIR / "products.json"
    UPSTREAM_BASELINES_PATH = DATA_DIR / "upstream_baselines.json"
    KNOWLEDGE_STATE_PATH = DATA_DIR / "knowledge_state.json"
    LAST_KNOWN_GOOD_LOG = REPO_ROOT / "reports" / "freshness_guard" / "last_known_good.log.jsonl"


STATES = frozenset({
    "CURRENT", "STALE", "REFRESHING", "REFRESH_FAILED",
    "UPSTREAM_UNAVAILABLE", "PROVENANCE_MISSING", "CORRUPT", "LAST_KNOWN_GOOD",
    "HISTORY_REWRITTEN_CONTENT_IDENTICAL", "STALE_ORPHANED",
})
MODES = frozenset({"strict", "degraded", "offline"})


class FreshnessResult(NamedTuple):
    state: str
    reason: str
    resolved_sha: "str | None" = None
    live_sha: "str | None" = None
    resolved_from: "str | None" = None


# ---------------------------------------------------------------------------
# Baseline resolution (the collapsed single-writer + regenerated-projections model)
# ---------------------------------------------------------------------------


def _model_path(family: str, platform: str) -> Path:
    return KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"


def _load_model(family: str, platform: str) -> "dict | None":
    path = _model_path(family, platform)
    if not path.is_file():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None


def _projection_sha(path: Path, key: str, *, nested: "str | None" = None) -> "str | None":
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if nested:
        entry = data.get(key)
        if not isinstance(entry, dict):
            return None
        nested_val = entry.get(nested)
        return nested_val.get("repo_sha") if isinstance(nested_val, dict) else None
    val = data.get(key)
    return val if isinstance(val, str) and val else None


def resolve_baseline(family: str, platform: str) -> "tuple[str | None, str]":
    """Resolve the accepted baseline SHA for one product.

    Order: (1) the git-tracked, now-canonical merged/model.yaml.repo_sha; (2) the
    regenerated fast-lookup projections (data/upstream_baselines.json, then
    data/knowledge_state.json); (3) the local baseline_ledger_head.json cache; (4)
    evidence.model_sha sampled from committed content frontmatter (last resort,
    reused from baseline_resolver.py — the one source guaranteed to survive a fresh
    clone even for a product that predates this whole mechanism).

    Returns (sha, source) — source is None-safe ("none") when nothing resolved.
    """
    model = _load_model(family, platform)
    if model:
        sha = model.get("repo_sha")
        if sha:
            return sha, "model.yaml"

    sha = _projection_sha(UPSTREAM_BASELINES_PATH, f"{family}/{platform}", nested=None)
    if sha:
        return sha, "upstream_baselines.json"

    sha = _projection_sha(KNOWLEDGE_STATE_PATH, f"{family}/{platform}", nested="accepted_baseline")
    if sha:
        return sha, "knowledge_state.json"

    ledger_head = KNOWLEDGE_ROOT / family / platform / "merged" / "baseline_ledger_head.json"
    if ledger_head.is_file():
        try:
            data = json.loads(ledger_head.read_text(encoding="utf-8"))
            sha = data.get("new_repo_sha")
            if sha:
                return sha, "baseline_ledger_head.json"
        except (OSError, json.JSONDecodeError):
            pass

    try:
        from baseline_resolver import _sample_content_model_sha
        sha = _sample_content_model_sha(family, platform)
        if sha:
            return sha, "content_evidence_sample"
    except Exception:
        pass

    return None, "none"


def _durable_sources_agree(family: str, platform: str) -> "tuple[bool, dict]":
    """Compare the durable sources' recorded SHAs. Returns (agree, detail).

    Only compares sources that actually have an entry — an absent entry in a
    not-yet-migrated projection is a staleness/PROVENANCE_MISSING concern, not a
    disagreement. Real disagreement (both present, different values) is what
    resolve_baseline()'s old triple-writer design could produce and this collapsed
    model is designed to make structurally rare-to-never.
    """
    model = _load_model(family, platform)
    model_sha = model.get("repo_sha") if model else None
    upstream_sha = _projection_sha(UPSTREAM_BASELINES_PATH, f"{family}/{platform}")
    state_sha = _projection_sha(KNOWLEDGE_STATE_PATH, f"{family}/{platform}", nested="accepted_baseline")

    present = {k: v for k, v in {
        "model.yaml": model_sha, "upstream_baselines.json": upstream_sha,
        "knowledge_state.json": state_sha,
    }.items() if v}
    distinct = set(present.values())
    return (len(distinct) <= 1), present


def _live_upstream_sha(repo_url: str, *, timeout: float = 15.0) -> "str | None":
    """git ls-remote HEAD -- read-only, no clone/fetch. Returns None on any failure
    (network, auth, timeout) rather than raising; callers treat None as
    UPSTREAM_UNAVAILABLE."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", repo_url, "HEAD"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        sha = line.split()[0] if line else ""
        return sha or None
    except Exception:
        return None


def _repo_url(family: str, platform: str) -> "str | None":
    try:
        products = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for entry in products:
        if entry.get("family") == family and entry.get("platform") == platform:
            return entry.get("clone_url") or entry.get("repo_url")
    return None


# ---------------------------------------------------------------------------
# Baseline tree identity (RC-1: identity by content, not mutable pointer)
# ---------------------------------------------------------------------------


def _resolve_recorded_tree_sha(family: str, platform: str, resolved_sha: str) -> "str | None":
    """The repo_tree_sha the baseline ledger recorded for `resolved_sha`, if any
    (TC-10 — additive field, absent on any entry written before this feature or by
    a caller that couldn't compute it at promote time). Searches history newest-
    first since the same commit sha is only ever recorded once in practice, but a
    duplicate would resolve to the most recent write, matching this ledger's own
    append-only "latest wins" read convention elsewhere."""
    try:
        from baseline_ledger import BaselineLedger
    except Exception:
        return None
    try:
        ledger = BaselineLedger(family, platform, repo_root=REPO_ROOT)
        for entry in reversed(ledger.history()):
            if entry.get("new_repo_sha") == resolved_sha and entry.get("repo_tree_sha"):
                return entry["repo_tree_sha"]
    except Exception:
        return None
    return None


def _clone_head_tree_sha(repo_path: Path) -> "str | None":
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD^{tree}"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _orphaned_commit_tree_sha(repo_path: Path, orphaned_sha: str) -> "str | None":
    """Live fallback for `_resolve_recorded_tree_sha` (readme-refresh-hardening-and-
    regen-2026-08-30, TC-27b canary): an orphaned commit produced by a history
    rewrite (font/python's real GitLab-canonical -> GitHub-mirror resync) remains a
    dangling-but-present loose object in the local clone cache until garbage-
    collected -- `git rev-parse <sha>^{tree}` still resolves directly against it,
    with no need for a prior `baseline_ledger.jsonl` write. This is intentionally
    the SECOND choice, tried only when the ledger has no durably recorded
    `repo_tree_sha` for this sha (`_resolve_recorded_tree_sha` returned None): the
    ledger value survives a `git gc`/fresh clone-cache reset that this live lookup
    would not, so it stays authoritative when present. Returns None (never raises)
    on any git failure, including the case where the object has since been
    garbage-collected -- callers correctly fall through to STALE_ORPHANED, the
    same fail-closed behavior as an absent ledger record.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", f"{orphaned_sha}^{{tree}}"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _check_baseline_reachability(
    family: str, platform: str, resolved_sha: "str | None",
) -> "tuple[str, str] | None":
    """RC-1 (the closed forensic audit's own unifying root cause): "is this the same
    thing as before?" was answered everywhere in this pipeline by comparing a
    mutable pointer (a commit SHA) that can change without the underlying content
    changing, or by never checking reachability at all in degraded mode (this
    module's own prior behavior — confirmed by direct code read before this fix:
    resolve_baseline() never tested reachability, only `_durable_sources_agree()`
    and a local `stale_since` flag).

    Live-reproduced why this matters (readme-refresh-hardening-and-regen-2026-08-30):
    font/python's upstream is a GitLab-canonical -> GitHub-mirror architecture that
    periodically rewrites history (a real zero-parent orphan commit, twice) with
    BYTE-IDENTICAL content each time (`git diff --stat` empty; tree SHAs equal).
    slides/python has the structurally IDENTICAL-LOOKING orphaned-baseline shape —
    same "commit unreachable" signal — but its tree SHA genuinely differs (a real
    747-line README change, a real source change). One mechanism must produce two
    OPPOSITE correct answers from these two cases; a commit-SHA-only check cannot.

    Returns `(state, reason)` when an orphan condition was actually determined
    (`HISTORY_REWRITTEN_CONTENT_IDENTICAL` or `STALE_ORPHANED`), or `None` when this
    check could not run (no clone cache reachable for this product — the common case
    for CI/cold-start callers) or the baseline IS reachable (the common case in
    steady-state operation) — `None` means "fall through to the pre-existing
    stale_since-only logic, unchanged", never "assume current" or "assume stale".
    Local-only (a `git cat-file`/`rev-parse` against the already-fetched clone
    cache, never a network call) — safe to run in both degraded and strict modes;
    deliberately NOT run in offline mode, which must never touch the filesystem
    beyond resolve_baseline() by contract.
    """
    if not resolved_sha:
        return None
    try:
        from core.clone_cache import clone_path, clone_exists
    except Exception:
        return None
    if not clone_exists(family, platform):
        return None
    repo_path = clone_path(family, platform)
    try:
        from baseline_resolver import git_reachable
    except Exception:
        return None
    if git_reachable(repo_path)(resolved_sha):
        return None

    recorded_tree_sha = _resolve_recorded_tree_sha(family, platform, resolved_sha)
    tree_sha_source = "recorded"
    if not recorded_tree_sha:
        recorded_tree_sha = _orphaned_commit_tree_sha(repo_path, resolved_sha)
        tree_sha_source = "live (object still present, not yet garbage-collected)"
    live_tree_sha = _clone_head_tree_sha(repo_path)
    if recorded_tree_sha and live_tree_sha and recorded_tree_sha == live_tree_sha:
        return (
            "HISTORY_REWRITTEN_CONTENT_IDENTICAL",
            f"baseline commit {resolved_sha[:10]} is unreachable from the clone-cache HEAD, "
            f"but its {tree_sha_source} tree SHA ({recorded_tree_sha[:10]}) matches the tree SHA "
            f"now at HEAD -- a content-identical history rewrite (e.g. a GitLab-canonical -> "
            f"GitHub-mirror resync), not real staleness",
        )
    return (
        "STALE_ORPHANED",
        f"baseline commit {resolved_sha[:10]} is unreachable from the clone-cache HEAD, and "
        + (
            "its tree SHA genuinely differs from HEAD's -- real content drift, not just a "
            "rewritten history"
            if recorded_tree_sha and live_tree_sha
            else "no recorded tree SHA is available to prove the content is unchanged (a "
                 "pre-TC-10 baseline, or a promote that ran without clone-cache access) -- "
                 "treated as stale rather than assumed safe"
        ),
    )


# ---------------------------------------------------------------------------
# Disagreement classification (ST-188 follow-on, 2026-09-06): _durable_sources_agree()
# correctly hard-fails CORRUPT the moment model.yaml and its derived projections disagree,
# but gives no signal at all about WHICH side is stale -- confirmed live this session that
# this is not a hypothetical distinction: pdf/go and note/python were both found disagreeing
# on the same day, for OPPOSITE reasons (pdf/go: model.yaml itself is behind live upstream;
# note/python: the projections never got regenerated after a legitimate model.yaml update).
# A single "just run rebuild-all on CORRUPT" auto-heal would silently make the pdf/go-class
# case worse (overwriting the correct, current projection value with model.yaml's stale one)
# while fixing the note/python-class case -- so this function exists to tell the two apart
# before anything touches either file, using the same local-clone-cache ancestry primitives
# _check_baseline_reachability() above already relies on.
# ---------------------------------------------------------------------------

DISAGREEMENT_PROJECTION_STALE = "PROJECTION_STALE"
DISAGREEMENT_MODEL_STALE = "MODEL_STALE"
DISAGREEMENT_DIVERGENT_OR_UNKNOWN = "DIVERGENT_OR_UNKNOWN"
DISAGREEMENT_STATUSES = frozenset({
    DISAGREEMENT_PROJECTION_STALE, DISAGREEMENT_MODEL_STALE, DISAGREEMENT_DIVERGENT_OR_UNKNOWN,
})


def _is_ancestor(repo_path: Path, ancestor_sha: str, descendant_sha: str) -> "bool | None":
    """True/False from `git merge-base --is-ancestor`; None (never a silent False) when this
    could not be determined at all (bad/unresolvable SHA, git failure, timeout) -- callers must
    treat None as "can't tell", not as a negative answer."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "merge-base", "--is-ancestor", ancestor_sha, descendant_sha],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0 if result.returncode in (0, 1) else None
    except Exception:
        return None


def classify_baseline_disagreement(
    family: str, platform: str, *, clone_cache_path: "Path | None" = None,
) -> "dict | None":
    """Explains a _durable_sources_agree() == False (CORRUPT) result for one product.

    Returns None when the durable sources actually agree (mirrors _check_baseline_
    reachability()'s own "None = not applicable" convention above) -- there is nothing to
    classify. Otherwise returns a dict:
        {"status": one of DISAGREEMENT_STATUSES, "reason": str, "safe_to_rebuild": bool,
         "model_sha": str | None, "projection_sha": str | None}

    `safe_to_rebuild` is True ONLY for PROJECTION_STALE (model.yaml is ahead; the projections
    -- data/upstream_baselines.json / data/knowledge_state.json -- are simply behind and can be
    safely regenerated FROM model.yaml via regen_baseline_projections.rebuild_one/rebuild_all).
    MODEL_STALE means the opposite -- model.yaml itself is behind the value the projections (and
    the local clone) agree on -- and running rebuild-all there would overwrite a correct,
    current projection value with a stale one; the real fix is a fresh re-scout/truth-merge to
    bring model.yaml's own extracted knowledge current, not a projection rebuild.
    DIVERGENT_OR_UNKNOWN covers every case this function cannot safely resolve (no local clone
    cache available, an unresolvable SHA, the two projections disagreeing with each other, or a
    genuine fork where neither SHA is a git ancestor of the other) -- always fail-safe, never a
    guess, and safe_to_rebuild is always False for it.

    Deliberately local-clone-cache-only: never makes a live `git ls-remote` network call. This
    function answers a closed question -- which of two ALREADY-RECORDED SHAs is downstream of
    the other -- that `git merge-base` settles directly; confirming the winning SHA is ALSO still
    current relative to today's live upstream is check_freshness(mode="strict")'s separate job.
    Pass `clone_cache_path` explicitly (as audit_portfolio does, via its own already-resolved
    per-product clone-cache path) rather than relying on this module's own core.clone_cache
    default, which is configured independently of this module's configure() seam and will not
    see a test's scratch repo_root.
    """
    agree, present = _durable_sources_agree(family, platform)
    if agree:
        return None

    model_sha = present.get("model.yaml")
    upstream_sha = present.get("upstream_baselines.json")
    state_sha = present.get("knowledge_state.json")

    if not model_sha:
        return {
            "status": DISAGREEMENT_DIVERGENT_OR_UNKNOWN, "safe_to_rebuild": False,
            "reason": "no model.yaml repo_sha present to compare against",
            "model_sha": None, "projection_sha": None,
        }
    if upstream_sha and state_sha and upstream_sha != state_sha:
        return {
            "status": DISAGREEMENT_DIVERGENT_OR_UNKNOWN, "safe_to_rebuild": False,
            "reason": "the two projections (upstream_baselines.json, knowledge_state.json) "
                      "disagree with each other, not just with model.yaml -- looks like a "
                      "partial/interrupted regen; refusing to guess which one to trust",
            "model_sha": model_sha, "projection_sha": None,
        }
    projection_sha = upstream_sha or state_sha
    if not projection_sha or projection_sha == model_sha:
        return {
            "status": DISAGREEMENT_DIVERGENT_OR_UNKNOWN, "safe_to_rebuild": False,
            "reason": "could not isolate a single distinct projection SHA to compare",
            "model_sha": model_sha, "projection_sha": projection_sha,
        }

    if clone_cache_path is not None:
        repo_path = clone_cache_path
        if not (repo_path / ".git").is_dir():
            return {
                "status": DISAGREEMENT_DIVERGENT_OR_UNKNOWN, "safe_to_rebuild": False,
                "reason": f"no local clone cache at {repo_path}",
                "model_sha": model_sha, "projection_sha": projection_sha,
            }
    else:
        try:
            from core.clone_cache import clone_path, clone_exists
        except Exception:
            return {
                "status": DISAGREEMENT_DIVERGENT_OR_UNKNOWN, "safe_to_rebuild": False,
                "reason": "core.clone_cache unavailable",
                "model_sha": model_sha, "projection_sha": projection_sha,
            }
        if not clone_exists(family, platform):
            return {
                "status": DISAGREEMENT_DIVERGENT_OR_UNKNOWN, "safe_to_rebuild": False,
                "reason": "no local clone cache available to determine ancestry",
                "model_sha": model_sha, "projection_sha": projection_sha,
            }
        repo_path = clone_path(family, platform)

    model_ancestor = _is_ancestor(repo_path, model_sha, projection_sha)
    projection_ancestor = _is_ancestor(repo_path, projection_sha, model_sha)

    if model_ancestor is None or projection_ancestor is None:
        return {
            "status": DISAGREEMENT_DIVERGENT_OR_UNKNOWN, "safe_to_rebuild": False,
            "reason": "git ancestry could not be determined for one or both SHAs",
            "model_sha": model_sha, "projection_sha": projection_sha,
        }
    if model_ancestor and not projection_ancestor:
        return {
            "status": DISAGREEMENT_MODEL_STALE, "safe_to_rebuild": False,
            "reason": f"model.yaml's repo_sha ({model_sha[:10]}) is an ancestor of the "
                      f"projections' value ({projection_sha[:10]}) -- model.yaml is behind; "
                      f"do NOT run rebuild-all, a real re-scout is needed",
            "model_sha": model_sha, "projection_sha": projection_sha,
        }
    if projection_ancestor and not model_ancestor:
        return {
            "status": DISAGREEMENT_PROJECTION_STALE, "safe_to_rebuild": True,
            "reason": f"the projections' value ({projection_sha[:10]}) is an ancestor of "
                      f"model.yaml's repo_sha ({model_sha[:10]}) -- projections are simply "
                      f"behind; safe to regenerate via rebuild_one/rebuild_all",
            "model_sha": model_sha, "projection_sha": projection_sha,
        }
    return {
        "status": DISAGREEMENT_DIVERGENT_OR_UNKNOWN, "safe_to_rebuild": False,
        "reason": "neither SHA is a git ancestor of the other -- real fork/divergent history, "
                  "needs manual review",
        "model_sha": model_sha, "projection_sha": projection_sha,
    }


# ---------------------------------------------------------------------------
# Regen lock / failure-marker inspection
# ---------------------------------------------------------------------------


def _is_refreshing(family: str, platform: str) -> bool:
    try:
        from knowledge_regen_lock import inspect_lock
    except Exception:
        return False
    return inspect_lock(family, platform, knowledge_root=KNOWLEDGE_ROOT) is not None


def _regen_failed_marker(family: str, platform: str) -> Path:
    return KNOWLEDGE_ROOT / family / platform / "merged" / ".regen_failed"


def mark_regen_failed(family: str, platform: str, *, reason: str) -> None:
    """Called by the regen chain on a non-zero exit after the lock was acquired, so
    a previous failure is surfaced (REFRESH_FAILED) rather than silently papered
    over by whatever bundle was left behind. Cleared by mark_regen_succeeded()."""
    path = _regen_failed_marker(family, platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(reason, encoding="utf-8")


def mark_regen_succeeded(family: str, platform: str) -> None:
    path = _regen_failed_marker(family, platform)
    if path.is_file():
        path.unlink()


# ---------------------------------------------------------------------------
# check_freshness / is_generation_allowed
# ---------------------------------------------------------------------------


def check_freshness(family: str, platform: str, *, mode: str = "degraded") -> FreshnessResult:
    """Compute the freshness state for one product.

    strict:   requires bundle_manifest.json present with status COMPLETE; requires
              the durable sources to AGREE (disagreement -> CORRUPT, never "pick
              one" — the direct fix for the MIGRATE-C04 fabricated-timestamp bug
              class); does one cheap `git ls-remote` against live upstream.
              Network/auth failure -> UPSTREAM_UNAVAILABLE, never a silent
              downgrade to a stale-local comparison.
    degraded: same as strict minus the live network call — resolves purely from
              durable/local source agreement. Default for high-volume
              generation-time callers, to bound network cost.
    offline:  resolve_baseline() only, no cross-source check, no network. For
              read-only status/reporting CLIs that must never fail or hang.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}, got {mode!r}")

    if _is_refreshing(family, platform):
        return FreshnessResult("REFRESHING", "a regen lock is currently held for this product")

    if _regen_failed_marker(family, platform).is_file():
        reason = _regen_failed_marker(family, platform).read_text(encoding="utf-8", errors="replace")
        return FreshnessResult("REFRESH_FAILED", f"previous regen attempt failed: {reason.strip()[:200]}")

    model = _load_model(family, platform)
    if model is None:
        # _load_model() collapses "file missing" and "file present but
        # unparseable" into the same None -- distinguish them here so a
        # corrupt model.yaml (a much more concerning signal than "knowledge
        # was never bootstrapped") reports CORRUPT, matching the existing
        # CORRUPT-on-unparseable-bundle_manifest.json precedent below,
        # instead of the misleading "not found" message.
        if _model_path(family, platform).is_file():
            return FreshnessResult(
                "CORRUPT", "merged/model.yaml parse error -- file exists but is not valid YAML",
            )
        return FreshnessResult("PROVENANCE_MISSING", "no merged/model.yaml found for this product")

    resolved_sha, resolved_from = resolve_baseline(family, platform)
    if resolved_sha is None:
        return FreshnessResult("PROVENANCE_MISSING", "no baseline SHA could be resolved from any source")

    if mode == "offline":
        return FreshnessResult("CURRENT", "offline mode — resolved baseline only, not upstream-verified",
                                resolved_sha=resolved_sha, resolved_from=resolved_from)

    agree, detail = _durable_sources_agree(family, platform)
    if not agree:
        return FreshnessResult(
            "CORRUPT", f"durable baseline sources disagree: {detail}",
            resolved_sha=resolved_sha, resolved_from=resolved_from,
        )

    bundle_manifest_path = KNOWLEDGE_ROOT / family / platform / "merged" / "bundle_manifest.json"
    if bundle_manifest_path.is_file():
        try:
            manifest = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
            if manifest.get("status") != "COMPLETE":
                return FreshnessResult(
                    "CORRUPT", f"bundle_manifest.json status={manifest.get('status')!r}, expected COMPLETE",
                    resolved_sha=resolved_sha, resolved_from=resolved_from,
                )
        except (OSError, json.JSONDecodeError):
            return FreshnessResult(
                "CORRUPT", "bundle_manifest.json present but unreadable",
                resolved_sha=resolved_sha, resolved_from=resolved_from,
            )
    # Absence of bundle_manifest.json is tolerated (not CORRUPT) for products not
    # yet migrated to schema v2 -- PROVENANCE_MISSING already covers "no model.yaml
    # at all"; a v1 model.yaml with no bundle_manifest.json is legacy-but-usable in
    # degraded mode. Strict mode's network check below is still the real gate.

    # RC-1 / TC-11 (readme-refresh-hardening-and-regen-2026-08-30): local-only (no
    # network), so safe to run in both degraded and strict modes -- deliberately
    # BEFORE strict mode's live upstream comparison below, since a raw SHA-string
    # mismatch against a live remote is exactly the wrong signal once the baseline
    # is already known to be an orphan; running that check first would just
    # reproduce the bug this one exists to fix, in a different disguise. Returns
    # None (fall through, unchanged) for the common case -- reachable baseline, or
    # no clone cache available to check against at all.
    orphan_result = _check_baseline_reachability(family, platform, resolved_sha)
    if orphan_result is not None:
        orphan_state, orphan_reason = orphan_result
        return FreshnessResult(
            orphan_state, orphan_reason, resolved_sha=resolved_sha, resolved_from=resolved_from,
        )

    if mode == "degraded":
        # Stale local model_yaml stale_since is still an authored signal (set by
        # /knowledge-diff) worth honoring even without a live check.
        if model.get("stale_since") is not None:
            return FreshnessResult(
                "STALE", f"stale_since={model.get('stale_since')!r} recorded locally",
                resolved_sha=resolved_sha, resolved_from=resolved_from,
            )
        return FreshnessResult(
            "CURRENT", "degraded mode — durable sources agree, no local stale_since flag set",
            resolved_sha=resolved_sha, resolved_from=resolved_from,
        )

    # strict mode: live upstream comparison
    repo_url = _repo_url(family, platform)
    if not repo_url:
        return FreshnessResult(
            "UPSTREAM_UNAVAILABLE", "no repo_url/clone_url found in data/products.json",
            resolved_sha=resolved_sha, resolved_from=resolved_from,
        )
    live_sha = _live_upstream_sha(repo_url)
    if live_sha is None:
        return FreshnessResult(
            "UPSTREAM_UNAVAILABLE", f"could not reach upstream ({repo_url}) to verify freshness",
            resolved_sha=resolved_sha, resolved_from=resolved_from,
        )
    if live_sha == resolved_sha:
        return FreshnessResult(
            "CURRENT", "resolved baseline matches live upstream HEAD",
            resolved_sha=resolved_sha, live_sha=live_sha, resolved_from=resolved_from,
        )
    return FreshnessResult(
        "STALE", f"resolved baseline {resolved_sha[:10]} != live upstream HEAD {live_sha[:10]}",
        resolved_sha=resolved_sha, live_sha=live_sha, resolved_from=resolved_from,
    )


def is_generation_allowed(
    family: str,
    platform: str,
    *,
    mode: str = "degraded",
    allow_last_known_good: bool = False,
) -> "tuple[bool, FreshnessResult]":
    """The function every gate should call instead of reading model.yaml['stale_since']
    directly. Returns (allowed, result).

    allowed=True only for CURRENT, for HISTORY_REWRITTEN_CONTENT_IDENTICAL (TC-11 —
    the baseline commit is unreachable, but its real content is proven, via tree
    SHA, unchanged; forcing a re-scout here would be pure waste, not caution), or
    for LAST_KNOWN_GOOD when the caller explicitly opts in AND a prior successfully-
    generated bundle exists. Every LAST_KNOWN_GOOD use is appended to
    reports/freshness_guard/last_known_good.log.jsonl for audit. Launch/readiness
    gates must never pass allow_last_known_good=True. STALE_ORPHANED is
    deliberately NOT allowed by default and NOT LAST_KNOWN_GOOD-eligible — real
    content drift, or a baseline old enough to predate tree-SHA recording, must be
    treated the same as ordinary STALE, not assumed safe.
    """
    result = check_freshness(family, platform, mode=mode)
    if result.state in ("CURRENT", "HISTORY_REWRITTEN_CONTENT_IDENTICAL"):
        return True, result

    if allow_last_known_good and result.state in ("UPSTREAM_UNAVAILABLE", "REFRESH_FAILED"):
        merged_dir = KNOWLEDGE_ROOT / family / platform / "merged"
        if (merged_dir / "model.yaml").is_file():
            _log_last_known_good(family, platform, result)
            return True, result._replace(state="LAST_KNOWN_GOOD")

    return False, result


def _log_last_known_good(family: str, platform: str, result: FreshnessResult) -> None:
    LAST_KNOWN_GOOD_LOG.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    entry = {
        "family": family, "platform": platform,
        "underlying_state": result.state, "reason": result.reason,
        "resolved_sha": result.resolved_sha,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with LAST_KNOWN_GOOD_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # audit-log write failure must not block the (already-decided) fallback
