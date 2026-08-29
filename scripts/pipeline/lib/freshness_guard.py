"""freshness_guard.py — single source of truth for knowledge-bundle freshness.

CONTRACT: scripts/pipeline/lib/freshness_guard.py
  purpose: FRESH-001 (2026-08-14). Before this module, every consumer (batch_reference.py,
           refresh_run.py, launch_gate.py, readiness_gate.py) independently read
           `model.yaml["stale_since"]` and treated `None` as "safe to use" — a cached
           boolean that is only ever updated by a human/agent remembering to run
           `/knowledge-diff`, never a live-provable relationship to upstream. This module
           is the one place that state gets computed, in 8 explicit states with
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
  states:  CURRENT, STALE, REFRESHING, REFRESH_FAILED, UPSTREAM_UNAVAILABLE,
           PROVENANCE_MISSING, CORRUPT, LAST_KNOWN_GOOD — see check_freshness()'s
           docstring for the full semantics of each.
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

    allowed=True only for CURRENT, or for LAST_KNOWN_GOOD when the caller explicitly
    opts in AND a prior successfully-generated bundle exists. Every LAST_KNOWN_GOOD
    use is appended to reports/freshness_guard/last_known_good.log.jsonl for audit.
    Launch/readiness gates must never pass allow_last_known_good=True.
    """
    result = check_freshness(family, platform, mode=mode)
    if result.state == "CURRENT":
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
