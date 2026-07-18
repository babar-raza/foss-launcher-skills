"""refresh_run_manifest.py — ST-034: capture base_commit_sha before a refresh begins.

The independent Lane I review of the aspose-org-foss-refresh-tidy-lightning
plan's Lane J re-foundation (RPR-J-10, 2026-07-17) identified this as the
single biggest gap blocking safe use of the git-founded verification gates:
RPR-J-17 built `post_refresh_verify.py`'s --base override and
`_load_base_commit_sha()` reader, but nothing ever WROTE the
`base_commit_sha` a refresh-run manifest is supposed to supply. With zero
manifests on disk, every `--verify` run defaults to comparing against
`HEAD`, which is vacuous the moment a refresh has already been committed
(HEAD then *is* the post-refresh state) — proven for real, not
hypothetically, via git forensics on 3d/net and cells/java during that
review.

Scope (deliberately narrow — see ST-034's backlog entry): this module
captures ONLY `base_commit_sha`, at the one moment it is unambiguous —
before any refresh work begins, i.e. S-84 Step 1 (knowledge-diff). It does
NOT attempt to build the full schema-5e manifest (baseline_ledger_ref,
product_change_refs, page_coverage_ledger_ref, patch_receipt_refs, the
`validation` dict, etc.) — those fields depend on pipeline stages (PIA,
S-105 body-refresh receipts, oracle, triage_confirm, SEO stability) that
haven't run yet when this is called, and populating them honestly requires
deeper integration across the whole S-84 chain that is out of scope for
the one, proven, narrow gap this fixes. The manifest this writes is
intentionally partial: `validate_refresh_run_manifest()` (schema
validators) would correctly report several fields as missing if run
against it — that is expected, not a bug, for an in-progress manifest.
A more complete end-of-run manifest writer remains a separate, unscoped
follow-up.

Public API:
    capture_base_commit_sha(family, platform, run_id=None) -> Path
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent  # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT

_cfg_git_rev_parse = None  # None -> real `git rev-parse HEAD`; tests inject a stub


def configure(*, repo_root: "Path | str | None" = None, git_rev_parse=None) -> None:
    """Reconfigure module-level paths for testing. Call with no args to reset."""
    global REPO_ROOT, _cfg_git_rev_parse
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _cfg_git_rev_parse = git_rev_parse


def _current_head_sha() -> "str | None":
    """Return the repo's current HEAD sha, or None if it can't be resolved
    (not a git repo, git unavailable, detached-but-unborn HEAD, etc.) —
    callers must treat None as "could not capture," never fabricate a sha."""
    if _cfg_git_rev_parse is not None:
        return _cfg_git_rev_parse()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=10,
        )
        sha = result.stdout.strip()
        return sha if result.returncode == 0 and sha else None
    except Exception:
        return None


def _manifest_dir(family: str, platform: str) -> Path:
    return REPO_ROOT / "reports" / "refresh_runs" / family / platform


def _generate_run_id(family: str, platform: str) -> str:
    """Human-readable timestamp prefix, plus a nanosecond-precision numeric
    suffix so lexicographic sort (used by
    post_refresh_verify._load_base_commit_sha to find the "newest" manifest)
    is GUARANTEED to match true chronological order, including for two
    captures within the same second -- second-precision alone collided in
    testing (a real, if narrow, correctness gap: without it, a second
    capture in the same second would silently overwrite the first rather
    than producing a distinct, individually-resolvable, correctly-ordered
    manifest). A random suffix was considered and rejected: it would only
    guarantee uniqueness, not correct relative ordering, for two captures
    within the same second."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{time.time_ns()}-{family}-{platform}"


def capture_base_commit_sha(
    family: str, platform: str, *, run_id: "str | None" = None
) -> "Path | None":
    """Write a partial refresh-run manifest capturing the pre-refresh
    base_commit_sha. Call this ONCE, before any content or knowledge change
    for this refresh has been made (S-84 Step 1 / knowledge-diff) — calling
    it after changes have already landed defeats its entire purpose, the
    exact HEAD-vacuity bug this exists to prevent.

    Returns the manifest path on success, or None if HEAD could not be
    resolved (e.g. not a git repo) — callers must not treat None as a
    silent no-op; --verify will simply fall back to "HEAD" as before,
    which is the status quo, not a regression.
    """
    head_sha = _current_head_sha()
    if head_sha is None:
        return None

    rid = run_id or _generate_run_id(family, platform)
    manifest_dir = _manifest_dir(family, platform)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{rid}.manifest.json"

    manifest = {
        "run_id": rid,
        "family": family,
        "platform": platform,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base_commit_sha": head_sha,
        "status": "in_progress",
        # RPR-J-10/ST-034 scope note: the fields below are part of schema 5e
        # but are not yet knowable at this stage (S-84 Step 1, before the
        # refresh has scoped its own changes) -- present as schema-shaped
        # empty placeholders, not populated. A full-manifest writer that
        # fills these in from real pipeline state (baseline_ledger,
        # page_impact_assess, S-105 receipts, oracle/triage_confirm/SEO
        # results) is a separate, unscoped follow-up.
        "baseline_ledger_ref": None,
        "product_change_refs": [],
        "page_coverage_ledger_ref": None,
        "patch_receipt_refs": [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="refresh_run_manifest",
        description="ST-034: capture base_commit_sha before a refresh begins (S-84 Step 1).",
    )
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--capture-base", action="store_true", required=True,
                        help="Capture the current HEAD as this refresh's base_commit_sha")
    args = parser.parse_args(argv)

    path = capture_base_commit_sha(args.family, args.platform)
    if path is None:
        print(f"ERROR: could not resolve HEAD for {args.family}/{args.platform} "
              f"(not a git repo, or git unavailable) -- no manifest written.", file=sys.stderr)
        return 1
    print(f"base_commit_sha captured: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
