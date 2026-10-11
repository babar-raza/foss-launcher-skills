"""post_refresh_verify.py — Post-refresh verification gate and progress tracker.

Provides two complementary functions:

1. Progress tracking (--step):
   Records named pipeline steps as complete in
   ``reports/refresh_state/{family}/{platform}/progress.json``.
   This lets an orchestrator confirm which steps ran.

2. Verification gate (--verify):
   Runs a post-refresh checklist and exits 0 (clean) or 1 (failures):
   - stale_detect.py reports 0 stale pages
   - No content/*.md cites claim IDs absent from merged/claims.json
   - No reference pages exist for classes absent from merged/api_surface.json
   - All pages listed in progress.json pages_updated/pages_generated pass audit.py

3. Status display (--status):
   Prints the current progress.json in human-readable form.

Usage:
    python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --step knowledge_refresh
    python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --verify
    python scripts/pipeline/commands/ops/post_refresh_verify.py {family} {platform} --status

progress.json is local-only (gitignored); never committed.
--verify is read-only; never modifies content or knowledge files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent  # commands/ops/ -> commands/ -> pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from core.env_loader import load_env  # noqa: E402
load_env()

from lib.knowledge_tiers import is_tier2_claim_id  # noqa: E402
from commands.ops.refresh_run import (  # noqa: E402
    _casefold_path_diff,
    _load_extra_allowed_hashes,
)

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_HERE = Path(__file__).resolve().parents[2]  # commands/ops/ -> commands/ -> pipeline/

REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
CONTENT_ROOT = REPO_ROOT / "content"
REPORTS_ROOT = REPO_ROOT / "reports" / "refresh_state"
_REVIEW_ROOT = REPO_ROOT / "reports" / "refresh_review"

_cfg_subprocess_run = None           # None → use subprocess.run directly
_cfg_detect_grade_regressions = None  # None → import from audit_content_hash
_cfg_detect_seo_violations = None    # None → import from seo_stability_check
_cfg_git_body_changed = None         # None → real git-founded check (RPR-J-05)
_cfg_git_base_blobs = None           # None → real `git cat-file --batch` (Check 12)

# MT074 B15 (Check 12, mass-deletion guard) thresholds. Module-level defaults
# with a configure(mass_deletion_thresholds=...) override; no config-file
# loader pattern exists for verify checks, so none is introduced.
MASS_DELETION_DEFAULTS: dict = {
    # (a) per-page: body shrank by more than this fraction AND by more words.
    "max_shrink_fraction": 0.40,
    "min_shrink_words": 80,
    # (b) run-wide: share of comparable in-scope pages with a large shrink
    #     exceeds this fraction AND is at least this many pages.
    "max_run_share": 0.05,
    "min_run_pages": 3,
    # (c) knowledge delta: removed claims exceed this share of the base
    #     claims without enough reidentified_claims reconciliation.
    "max_removed_claim_share": 0.30,
    "min_reidentified_coverage": 0.95,
    # (R3-1) fail-closed floor: when fewer than this fraction of the in-scope
    # pages that SHOULD have a base version (all but GENERATED ones) could be
    # read at the base ref, the guard could not really look -> UNKNOWN.
    "min_comparable_fraction": 0.5,
}
_cfg_mass_deletion: dict = dict(MASS_DELETION_DEFAULTS)

# Page-decision dispositions / intended actions that EXPLAIN a large body
# shrink (a governed retirement or deliberate section removal). The current
# refresh_page_decision vocabulary only carries RETIRED for this; the other
# two are accepted forward-compatibly. A BODY_UPDATED decision alone never
# explains a large shrink -- body_refresh records the same disposition for a
# one-word fix and for a whole-body deletion -- so an intentional large
# removal must be authorized per page via the run manifest's optional
# ``intentional_body_removals`` list (same pattern as intentional_renames).
_SHRINK_EXPLAINING_MARKERS = {"RETIRED", "PAGE_RETIRED", "SECTION_REMOVED"}


def configure(
    *,
    repo_root: "Path | str | None" = None,
    knowledge_root: "Path | str | None" = None,
    content_root: "Path | str | None" = None,
    reports_root: "Path | str | None" = None,
    here: "Path | str | None" = None,
    subprocess_run=None,
    detect_grade_regressions=None,
    detect_seo_violations=None,
    git_body_changed=None,
    git_base_blobs=None,
    mass_deletion_thresholds: "dict | None" = None,
) -> None:
    """Reconfigure module-level paths for testing or alternative layouts.

    Call with no arguments to reset all paths to their defaults.
    Tests call ``post_refresh_verify.configure(repo_root=tmp_path, ...)``
    in a yield-based fixture and reset with ``configure()`` at teardown.
    """
    global REPO_ROOT, KNOWLEDGE_ROOT, CONTENT_ROOT, REPORTS_ROOT, _REVIEW_ROOT, _HERE
    global _cfg_subprocess_run, _cfg_detect_grade_regressions, _cfg_detect_seo_violations
    global _cfg_git_body_changed, _cfg_git_base_blobs, _cfg_mass_deletion
    _root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    REPO_ROOT = _root
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _root / "knowledge"
    CONTENT_ROOT = Path(content_root) if content_root is not None else _root / "content"
    REPORTS_ROOT = Path(reports_root) if reports_root is not None else _root / "reports" / "refresh_state"
    _REVIEW_ROOT = _root / "reports" / "refresh_review"
    _HERE = Path(here) if here is not None else _DEFAULT_HERE
    _cfg_subprocess_run = subprocess_run
    _cfg_detect_grade_regressions = detect_grade_regressions
    _cfg_detect_seo_violations = detect_seo_violations
    _cfg_git_body_changed = git_body_changed
    _cfg_git_base_blobs = git_base_blobs
    unknown_keys = set(mass_deletion_thresholds or {}) - set(MASS_DELETION_DEFAULTS)
    if unknown_keys:
        raise ValueError(f"unknown mass_deletion_thresholds: {sorted(unknown_keys)}")
    _cfg_mass_deletion = {**MASS_DELETION_DEFAULTS, **(mass_deletion_thresholds or {})}


_SITE_PATTERNS = (
    "docs.aspose.org/en/{family}/{platform}",
    "kb.aspose.org/en/{family}/{platform}",
    "products.aspose.org/en/{family}/{platform}",
    "reference.aspose.org/en/{family}/{platform}",
    "blog.aspose.org/{family}/{platform}",
)

# RPR-J-08: every derived (gitignored) artifact this file writes is stamped with
# its own schema_version so a reader can tell "genuinely nothing recorded" apart
# from "recorded under a shape this code no longer understands" -- the second
# case must route to UNKNOWN (RPR-J-06), never silently fall through to a
# dict.get(..., []) default that reads identically to "recorded, and empty."
_PROGRESS_SCHEMA_VERSION = 2
_RECONCILIATION_SCHEMA_VERSION = 2
_PAGE_DECISIONS_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

def _progress_path(family: str, platform: str) -> Path:
    return REPORTS_ROOT / family / platform / "progress.json"


def _load_progress(family: str, platform: str) -> dict:
    p = _progress_path(family, platform)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"family": family, "platform": platform, "steps": [], "pages_updated": [], "pages_generated": []}


def _git_body_changed_pages(family: str, platform: str, base_ref: str = "HEAD") -> "dict | None":
    """RPR-J-05: the durable, git-founded replacement for Checks 7/8's old
    bookkeeping-derived "did pages really change" question.

    Compares every discovered page's working-tree body against base_ref using
    the exact primitive audit_content_hash.py already exports for F-04/F-05
    (git show + normalized body hash) — no new git-diffing mechanism, per
    plan §19.3/§19.5. progress.json / execution_reconciliation.json are not
    consulted here; they remain resume hints elsewhere in this file, never a
    verdict input for this function.

    Returns None when nothing can be verified from git — no pages discovered,
    or every discovered page is new at base_ref (no prior version to diff),
    or audit_content_hash is unimportable. Callers must treat None as
    UNKNOWN, never as "changed=0". Otherwise returns:
        {"total": N, "changed": M, "changed_paths": {rel_path, ...},
         "unchanged_paths": {rel_path, ...}}
    where N is the count of pages that existed at base_ref and were
    comparable; changed_paths/unchanged_paths partition that N (a page
    outside both sets is new at base_ref — unverifiable, not "unchanged").
    Consumers cross-checking a specific page's claimed disposition (e.g.
    page_decisions.json's BODY_UPDATED) must use this partition, not just
    "changed==0", to avoid flagging a legitimately new page as mislabeled.
    """
    if _cfg_git_body_changed is not None:
        return _cfg_git_body_changed(family, platform, base_ref)

    discovered = _discover_content_files(family, platform)
    if not discovered:
        return None
    try:
        from commands.content.audit_content_hash import _git_show, _body_hash
    except ImportError:
        return None

    changed_paths: set = set()
    unchanged_paths: set = set()
    for f in discovered:
        try:
            rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            rel = str(f).replace("\\", "/")
        old = _git_show(base_ref, rel)
        if old is None:
            continue  # no version at base_ref (new page) — not a body-change signal
        try:
            new = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _body_hash(old) != _body_hash(new):
            changed_paths.add(rel)
        else:
            unchanged_paths.add(rel)

    checked = len(changed_paths) + len(unchanged_paths)
    if checked == 0:
        return None
    return {
        "total": checked,
        "changed": len(changed_paths),
        "changed_paths": changed_paths,
        "unchanged_paths": unchanged_paths,
    }


def _load_base_commit_sha(family: str, platform: str) -> "str | None":
    """Legacy forensic helper for schema-5e tests and explicit diagnostics.

    Commit readiness never calls this function and never selects a newest
    manifest. It loads the exact schema-v3 run requested with ``--run-id``.
    """
    manifest_dir = REPO_ROOT / "reports" / "refresh_runs" / family / platform
    if not manifest_dir.is_dir():
        return None
    manifests = sorted(manifest_dir.glob("*.manifest.json"))
    if not manifests:
        return None
    try:
        data = json.loads(manifests[-1].read_text(encoding="utf-8"))
        sha = data.get("base_commit_sha")
        return sha if isinstance(sha, str) and sha.strip() else None
    except Exception:
        return None


def _load_intentional_renames(family: str, platform: str) -> set:
    """Best-effort read of `intentional_renames` from the newest refresh-run manifest
    (schema 5e) for this product. Empty set if no manifest exists yet (RPR-F-05)."""
    manifest_dir = REPO_ROOT / "reports" / "refresh_runs" / family / platform
    if not manifest_dir.is_dir():
        return set()
    manifests = sorted(manifest_dir.glob("*.manifest.json"))
    if not manifests:
        return set()
    try:
        data = json.loads(manifests[-1].read_text(encoding="utf-8"))
        return set(data.get("intentional_renames") or [])
    except Exception:
        return set()


def _load_bound_run(family: str, platform: str, run_id: str) -> dict:
    """Load and validate the exact schema-v3 run selected by the caller."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise ValueError(f"unsafe run_id: {run_id!r}")
    run_root = REPO_ROOT / "reports" / "refresh_runs" / family / platform / run_id
    manifest_path = run_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"run manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    from lib.schema_validators import validate_refresh_run_manifest

    errors = validate_refresh_run_manifest(manifest, phase=manifest.get("state"))
    if errors:
        raise ValueError(f"invalid run manifest {run_id}: {errors}")
    if manifest.get("run_id") != run_id:
        raise ValueError(
            f"run manifest identity mismatch: requested {run_id}, "
            f"found {manifest.get('run_id')}"
        )
    if (manifest.get("family"), manifest.get("platform")) != (family, platform):
        raise ValueError(
            "run manifest product mismatch: "
            f"{manifest.get('family')}/{manifest.get('platform')}"
        )
    if manifest.get("state") not in {
        "VALIDATING",
        "READY_TO_COMMIT",
        "COMMITTED",
    }:
        raise ValueError(
            f"run {run_id} is not verifiable in state {manifest.get('state')}"
        )
    return {"manifest": manifest, "run_root": run_root}


def _load_run_decisions(run_root: Path, run_id: str) -> list[dict]:
    """Load only same-run JSONL decisions and reject malformed/mixed evidence."""
    path = run_root / "page_decisions.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"run decision ledger not found: {path}")
    from lib.schema_validators import validate_refresh_page_decision

    rows: list[dict] = []
    seen_paths: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        errors = validate_refresh_page_decision(row)
        if errors:
            raise ValueError(
                f"invalid page decision at line {line_number}: {errors}"
            )
        if row.get("run_id") != run_id:
            raise ValueError(
                f"wrong-run page decision at line {line_number}: "
                f"{row.get('run_id')!r}"
            )
        path_value = row["page_path"]
        if path_value in seen_paths:
            raise ValueError(f"duplicate page decision for {path_value}")
        seen_paths.add(path_value)
        rows.append(row)
    return rows


def _validate_run_receipts(
    run_root: Path,
    run_id: str,
    decisions: list[dict],
) -> None:
    """Validate every decision's immutable, same-run receipt and digest."""
    from lib.schema_validators import validate_page_patch_receipt

    seen_receipt_ids: set[str] = set()
    resolved_root = run_root.resolve()
    for row in decisions:
        ref = Path(row["receipt_ref"])
        if ref.is_absolute() or ".." in ref.parts:
            raise ValueError(f"unsafe receipt_ref for {row['page_path']}: {ref}")
        receipt_path = (run_root / ref).resolve()
        try:
            receipt_path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"receipt escapes run root: {ref}") from exc
        if not receipt_path.is_file():
            raise FileNotFoundError(f"receipt not found: {ref}")
        raw = receipt_path.read_bytes()
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if digest != row["receipt_digest"]:
            raise ValueError(
                f"receipt digest mismatch for {row['page_path']}: "
                f"{row['receipt_digest']} != {digest}"
            )
        document = yaml.safe_load(raw.decode("utf-8")) or {}
        receipt = document.get("content_refresh_receipt")
        if not isinstance(receipt, dict):
            raise ValueError(f"receipt wrapper missing in {ref}")
        errors = validate_page_patch_receipt(receipt)
        if errors:
            raise ValueError(f"invalid receipt {ref}: {errors}")
        if receipt.get("run_id") != run_id:
            raise ValueError(
                f"wrong-run receipt {ref}: {receipt.get('run_id')!r}"
            )
        if receipt.get("page_path") != row.get("page_path"):
            raise ValueError(
                f"receipt/decision page mismatch in {ref}: "
                f"{receipt.get('page_path')!r} != {row.get('page_path')!r}"
            )
        receipt_id = receipt["receipt_id"]
        if receipt_id in seen_receipt_ids:
            raise ValueError(f"duplicate receipt_id in run: {receipt_id}")
        seen_receipt_ids.add(receipt_id)


def _validate_bound_run_evidence(
    manifest: dict,
    run_root: Path,
    decisions: list[dict],
) -> None:
    """Require a complete, digest-bound, all-PASS run evidence join."""
    output_digests = manifest.get("output_digests") or {}
    scope_path = run_root / "scope.json"
    decisions_path = run_root / "page_decisions.jsonl"

    def _digest(path: Path) -> str:
        return (
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file()
            else "MISSING"
        )

    if output_digests.get("scope") != _digest(scope_path):
        raise ValueError("run scope digest mismatch")
    if output_digests.get("page_decisions") != _digest(decisions_path):
        raise ValueError("run page-decision digest mismatch")
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    scope_paths = list((manifest.get("scope") or {}).get("paths") or [])
    logical_scope = "sha256:" + hashlib.sha256(
        json.dumps(
            {
                "paths": sorted(scope_paths),
                "input_digest": (manifest.get("scope") or {}).get(
                    "input_digest"
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if (
        scope.get("run_id") != manifest["run_id"]
        or scope.get("family") != manifest["family"]
        or scope.get("platform") != manifest["platform"]
        or scope.get("paths") != scope_paths
        or (manifest.get("scope") or {}).get("digest") != logical_scope
    ):
        raise ValueError("run scope identity mismatch")
    # Found live (MT014-2026-07-29-PDF-GO-REDO): an exact 1:1 count/set match
    # between scope_paths and decision page_paths is too strict -- the same
    # root cause fixed in refresh_run.py's apply_run()/
    # _assert_run_evidence_ready() (see _reconcile_scope_and_decisions()
    # there for the full rationale, kept as a self-contained copy here since
    # this is a separately-invoked CLI script, not an import of that
    # module's internals). body_refresh.py has early-exit paths that record
    # no decision for a legitimate no-op scoped page; batch_reference.py's
    # --update mode logs (and sometimes additively writes) decisions beyond
    # this run's pinned scope. Check the real safety properties instead of
    # exact equality: a duplicate decision for the SAME in-scope page is
    # still a genuine problem and remains a hard block.
    decision_paths = [str(row.get("page_path")) for row in decisions]
    scope_path_set = set(scope_paths)
    initial_hashes = scope.get("initial_hashes") or {}

    def _current_hash(relative_path: str) -> str:
        target = REPO_ROOT / relative_path
        return (
            "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            if target.is_file()
            else "MISSING"
        )

    # Case-insensitive-filesystem aliasing (e.g. 'camera.md' vs 'Camera.md')
    # can make the SAME physical page appear under different casing in
    # scope vs decision paths; treat such pairs as a match, not a real
    # scope/decision gap (mirrors refresh_run.py's own OCC-guard fix for
    # the identical class of finding, confirmed live 2026-08-14, 3d/java).
    missing_candidates, _ = _casefold_path_diff(scope_path_set, set(decision_paths))
    extra_allowed = _load_extra_allowed_hashes(run_root)
    missing = []
    for p in missing_candidates:
        if _current_hash(p) == initial_hashes.get(p, "MISSING"):
            continue
        # Some writers deliberately record no decision row for an
        # authorized out-of-band write (e.g. TC-DUPIDX-02's _index.md
        # regeneration, or an S-73 manual-edit fallback) -- accept it if
        # its current hash matches a recorded extra-allowed value.
        if _current_hash(p) in extra_allowed.get(p, set()):
            continue
        missing.append(p)
    from commands.content.body_refresh import _normalized_body_hash

    empty_hash = _normalized_body_hash("")
    write_dispositions = {"BODY_UPDATED", "EVIDENCE_ONLY", "GENERATED", "RETIRED"}
    decisions_by_path: dict[str, list[dict]] = {}
    for row in decisions:
        decisions_by_path.setdefault(str(row.get("page_path")), []).append(row)

    def _is_real_violation(row: dict) -> bool:
        disposition = row.get("disposition")
        if disposition not in write_dispositions:
            return False
        if disposition == "GENERATED" and row.get("body_hash_before") == empty_hash:
            return False
        return True

    _, unexpected_candidates = _casefold_path_diff(scope_path_set, set(decision_paths))
    unexpected = [
        p for p in unexpected_candidates
        if any(_is_real_violation(row) for row in decisions_by_path.get(p, []))
    ]
    scoped_decision_paths = [p for p in decision_paths if p in scope_path_set]
    if (
        missing
        or unexpected
        or len(set(scoped_decision_paths)) != len(scoped_decision_paths)
    ):
        raise ValueError(
            "run scope does not exactly reconcile with decisions: "
            f"missing={missing[:5]}, unexpected={unexpected[:5]}"
        )
    required_validators = {"receipt", "forbidden_claims", "regrounding"}
    for row in decisions:
        validators = row.get("validator_results") or {}
        if set(validators) != required_validators or any(
            value != "PASS" for value in validators.values()
        ):
            raise ValueError(
                f"page decision is not all-PASS: {row.get('page_path')}"
            )

    receipt_paths = sorted((run_root / "receipts").glob("*.yaml"))
    receipts_digest = "sha256:" + hashlib.sha256(
        "\n".join(
            f"{path.name}:{_digest(path)}" for path in receipt_paths
        ).encode("utf-8")
    ).hexdigest()
    if output_digests.get("receipts") != receipts_digest:
        raise ValueError("run receipt-set digest mismatch")
    actual_refs = {
        path.relative_to(run_root).as_posix() for path in receipt_paths
    }
    decision_refs = {Path(row["receipt_ref"]).as_posix() for row in decisions}
    manifest_refs = {
        Path(value).as_posix() for value in manifest.get("receipt_refs") or []
    }
    expected_manifest_refs = {
        (run_root / value).relative_to(REPO_ROOT).as_posix()
        for value in actual_refs
    }
    if (
        actual_refs != decision_refs
        or manifest_refs != expected_manifest_refs
        or manifest.get("page_decision_ref")
        != decisions_path.relative_to(REPO_ROOT).as_posix()
    ):
        raise ValueError("run contains unbound or mismatched receipt references")


def _artifact_schema_state(path: Path, expected_version: int) -> str:
    """RPR-J-08: classify a derived artifact's schema state.

    Returns "absent" (file doesn't exist — legitimately nothing recorded yet,
    not ambiguous; callers should treat this the same as before, e.g. SKIP),
    "current" (parses, schema_version matches expected_version), or
    "stale_or_unversioned" (file exists but predates schema_version or the
    version doesn't match — callers must treat this as UNKNOWN, per RPR-J-06,
    never silently proceed with stale-shape field defaults that read
    identically to "recorded, and empty").
    """
    if not path.is_file():
        return "absent"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "stale_or_unversioned"
    if not isinstance(data, dict) or data.get("schema_version") != expected_version:
        return "stale_or_unversioned"
    return "current"


def _save_progress(family: str, platform: str, data: dict) -> None:
    data["schema_version"] = _PROGRESS_SCHEMA_VERSION
    p = _progress_path(family, platform)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:
        print(f"WARN: could not write progress.json: {exc}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def record_step(family: str, platform: str, step_name: str) -> None:
    """Record a named pipeline step as complete in progress.json."""
    data = _load_progress(family, platform)
    steps = data.setdefault("steps", [])
    # Avoid duplicate step entries
    if step_name not in steps:
        steps.append(step_name)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_progress(family, platform, data)
    print(f"STEP recorded: {step_name} for {family}/{platform}")


def record_pages(
    family: str,
    platform: str,
    *,
    updated: list[str] | None = None,
    generated: list[str] | None = None,
) -> None:
    """Record paths of updated/generated pages in progress.json.

    Appends to the existing lists — safe to call multiple times.  Paths
    that are already recorded are deduplicated.

    Args:
        updated: List of file paths that had their body content modified.
        generated: List of file paths that were newly created.
    """
    data = _load_progress(family, platform)
    if updated:
        existing = set(data.setdefault("pages_updated", []))
        for p in updated:
            if p not in existing:
                data["pages_updated"].append(p)
                existing.add(p)
    if generated:
        existing = set(data.setdefault("pages_generated", []))
        for p in generated:
            if p not in existing:
                data["pages_generated"].append(p)
                existing.add(p)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_progress(family, platform, data)


def print_status(family: str, platform: str) -> None:
    """Print current progress.json in human-readable form."""
    data = _load_progress(family, platform)
    print(f"Progress for {family}/{platform}:")
    steps = data.get("steps", [])
    if steps:
        print(f"  Completed steps ({len(steps)}):")
        for s in steps:
            print(f"    - {s}")
    else:
        print("  No steps recorded yet.")
    pages_updated = data.get("pages_updated", [])
    pages_generated = data.get("pages_generated", [])
    print(f"  Pages updated: {len(pages_updated)}")
    if pages_updated:
        for p in pages_updated[:5]:
            print(f"    - {p}")
        if len(pages_updated) > 5:
            print(f"    ... and {len(pages_updated) - 5} more")
    print(f"  Pages generated: {len(pages_generated)}")
    if pages_generated:
        for p in pages_generated[:5]:
            print(f"    - {p}")
        if len(pages_generated) > 5:
            print(f"    ... and {len(pages_generated) - 5} more")
    last = data.get("last_updated")
    if last:
        print(f"  Last updated: {last}")


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------

def _load_json_list(path: Path) -> list:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _discover_content_files(family: str, platform: str) -> list[Path]:
    files = []
    for pattern in _SITE_PATTERNS:
        site_root = CONTENT_ROOT / Path(pattern.format(family=family, platform=platform))
        if site_root.is_dir():
            for path in sorted(site_root.rglob("*.md")):
                # Skip locale files (e.g., index.fr.md)
                if "." in path.stem:
                    continue
                files.append(path)
    return files


def _get_page_evidence(path: Path) -> dict:
    """Read evidence dict from page frontmatter, or return {}."""
    try:
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
        if not m:
            return {}
        data = yaml.safe_load(m.group(1)) or {}
        ev = data.get("evidence")
        return ev if isinstance(ev, dict) else {}
    except Exception:
        return {}


def check_stale_reference_pages(
    api_surface_path: Path,
    ref_root: Path,
) -> tuple[bool, list[str]]:
    """Check 3: reference pages that cite API classes no longer in api_surface.json.

    A reference page is stale when its stem (lowercased) does not appear in the
    set of class names extracted from api_surface.json.  ``_index`` pages are
    always excluded from this check.

    If api_surface_path is missing or api_surface contains no named entries,
    the check is silently skipped and (True, []) is returned — absence of
    evidence is not treated as a failure.

    Returns (passed, failures) where failures is a list of human-readable
    problem descriptions.
    """
    api_list = _load_json_list(api_surface_path)
    valid_api_names: set[str] = {
        e["name"].lower() for e in api_list if isinstance(e, dict) and "name" in e
    }

    if not ref_root.is_dir() or not valid_api_names:
        return True, []

    # Recognized non-class structural reference pages -- hand-curated
    # landing/overview pages that intentionally cite MANY classes in their
    # own evidence.apis rather than documenting exactly one. "api-overview"
    # is not a generator output (no batch_reference.py/site_planner.py hit
    # produces it -- confirmed live 2026-08-31); it exists today under
    # 3d/typescript and cells/python (70 locale copies combined) and was
    # never previously caught by this check.
    _STRUCTURAL_REF_STEMS = ("_index", "api-overview")

    stale_ref_pages = []
    for ref_page in sorted(ref_root.glob("*.md")):
        class_name = ref_page.stem.lower()
        if class_name not in valid_api_names and class_name not in _STRUCTURAL_REF_STEMS:
            # Skip namespace-disambiguated pages like Axis-ThreeD.md or Property-GLTF.md.
            # These are valid pages for a class whose base name IS in the api_surface,
            # generated with a namespace suffix to avoid slug collisions.
            base_name = class_name.rsplit("-", 1)[0]
            if base_name in valid_api_names:
                continue
            # Skip retired (draft: true) pages — intentionally kept on disk
            # but excluded from the live site.
            try:
                fm_text = ref_page.read_text(encoding="utf-8")
                fm_match = re.match(r"^---\s*\n(.*?)\n---", fm_text, re.DOTALL)
                if fm_match:
                    fm_data = yaml.safe_load(fm_match.group(1)) or {}
                    if fm_data.get("draft") is True:
                        continue
            except Exception:
                pass  # If we can't read it, flag it as stale
            stale_ref_pages.append(ref_page)

    if not stale_ref_pages:
        return True, []

    failures: list[str] = []
    for p in stale_ref_pages[:5]:
        try:
            display_path = p.relative_to(REPO_ROOT)
        except ValueError:
            display_path = p
        failures.append(f"Reference page for absent API class: {display_path}")
    if len(stale_ref_pages) > 5:
        failures.append(f"... and {len(stale_ref_pages) - 5} more stale reference pages")
    return False, failures


def check_incorrectly_retired_pages(
    api_surface_path: Path,
    ref_root: Path,
) -> tuple[bool, list[str]]:
    """Check 3b: retired reference pages for classes that exist in api_surface.json.

    Finds pages with ``draft: true`` whose class name IS in the current API
    surface. These pages should have been un-retired when the API class was
    re-added to the source (Fix E — healing sprint 2026-04-15).

    Returns (passed, failures) where failures lists incorrectly-retired pages.
    """
    api_list = _load_json_list(api_surface_path)
    # Exclude _internal/ classes: Python FOSS repos place implementation-only classes
    # under _internal/ directories. Extraction does not filter them, so they appear in
    # api_surface.json, but they are correctly retired from content. Do not flag them.
    internal_names: set[str] = {
        e["name"].lower()
        for e in api_list
        if isinstance(e, dict) and "_internal/" in e.get("file", "")
    }
    valid_api_names: set[str] = {
        e["name"].lower()
        for e in api_list
        if isinstance(e, dict) and "name" in e and e["name"].lower() not in internal_names
    }
    # Exclude collision names: batch_reference.py's own namespace-disambiguation
    # (e.g. a TypeScript `class Style` and `interface Style` in different source
    # files sharing one name) permanently retires the OLD undisambiguated page
    # in favor of new, separately-named replacement pages -- that retirement is
    # correct and intentional, not "forgot to un-retire when the class came
    # back." Without this exclusion, every such collision is a false positive
    # here forever (the plain-named page must stay draft:true; there is no
    # "correct" un-retired state for it to reach). Found live 2026-08-28,
    # cells/typescript: Style/DataValidation/CellCoordinates/CellRange each
    # have both a class_declaration and an interface_declaration entry.
    _name_counts: dict[str, int] = {}
    for e in api_list:
        if isinstance(e, dict) and "name" in e:
            _n = e["name"].lower()
            _name_counts[_n] = _name_counts.get(_n, 0) + 1
    collision_names: set[str] = {n for n, c in _name_counts.items() if c > 1}

    if not ref_root.is_dir() or not valid_api_names:
        return True, []

    incorrectly_retired = []
    for ref_page in sorted(ref_root.glob("*.md")):
        class_name = ref_page.stem.lower()
        if class_name in ("_index",):
            continue
        if class_name not in valid_api_names:
            continue
        if class_name in collision_names:
            continue
        # Check if this public-API page is incorrectly retired
        try:
            fm_text = ref_page.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\s*\n(.*?)\n---", fm_text, re.DOTALL)
            if fm_match:
                fm_data = yaml.safe_load(fm_match.group(1)) or {}
                if fm_data.get("draft") is True:
                    incorrectly_retired.append(ref_page)
        except Exception:
            pass

    if not incorrectly_retired:
        return True, []

    failures: list[str] = []
    for p in incorrectly_retired[:10]:
        try:
            display_path = p.relative_to(REPO_ROOT)
        except ValueError:
            display_path = p
        failures.append(f"Incorrectly retired — class exists in api_surface: {display_path}")
    if len(incorrectly_retired) > 10:
        failures.append(f"... and {len(incorrectly_retired) - 10} more incorrectly retired pages")
    return False, failures


# ---------------------------------------------------------------------------
# Execution reconciliation (TC-103)
# ---------------------------------------------------------------------------

import hashlib as _hashlib


def _body_hash(path: Path) -> str:
    """SHA-256 of the body content (everything after the closing --- fence)."""
    try:
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n.*?\n---\s*(?:\n|$)", text, re.DOTALL)
        body = text[m.end():] if m else text
        return _hashlib.sha256(body.encode("utf-8")).hexdigest()
    except Exception:
        return ""


_CONTENT_STEPS = {
    "page_update",
    "delta_dispatch",
    "reference_update",
}
"""Steps that must complete before write_reconciliation() produces meaningful output.

Reconciliation compares planned (site_plan.yaml delta) vs executed work.  It
is only meaningful after content steps have run — writing it before Step 4
(page_update) produces ``planned: 0 / executed: 0`` which is worse than absent
because it looks like the chain completed successfully with nothing to do.
"""


def write_reconciliation(
    family: str,
    platform: str,
    *,
    pre_hashes: dict[str, str] | None = None,
    require_content_steps: bool = True,
) -> Path:
    """Produce execution_reconciliation.json comparing planned vs executed work.

    Reads planned counts from site_plan.yaml delta, computes executed counts
    by comparing pre/post body hashes (if provided) or checking file existence.

    Args:
        require_content_steps: When True (default), raises RuntimeError if none
            of the required content steps (page_update, delta_dispatch,
            reference_update) have been recorded in progress.json.  Set False
            only in tests or one-off diagnostic runs.

    Returns the path to the written artifact.
    """
    if require_content_steps:
        progress = _load_progress(family, platform)
        completed = set(progress.get("steps", []))
        if not completed.intersection(_CONTENT_STEPS):
            raise RuntimeError(
                f"write_reconciliation() called before any content steps completed "
                f"for {family}/{platform}. Completed steps: {sorted(completed) or '(none)'}. "
                f"Required: at least one of {sorted(_CONTENT_STEPS)}. "
                f"Call --reconcile after Step 7 (reference_update) in S-84, not before."
            )
    plans_root = REPO_ROOT / "reports" / "plans" / family / platform
    recon_dir = REPORTS_ROOT / family / platform
    recon_dir.mkdir(parents=True, exist_ok=True)
    recon_path = recon_dir / "execution_reconciliation.json"

    # Read site_plan.yaml delta section
    site_plan_path = plans_root / "site_plan.yaml"
    planned = {"pages_to_update": 0, "pages_to_add": 0, "pages_to_remove": 0}
    delta_pages_to_add: list[dict] = []
    delta_pages_to_update: list[dict] = []
    delta_pages_to_remove: list[dict] = []

    if site_plan_path.is_file():
        try:
            sp = yaml.safe_load(site_plan_path.read_text(encoding="utf-8")) or {}
            # site_plan.yaml structure: top-level "plan" key contains "delta"
            delta = sp.get("plan", {}).get("delta", {})
            delta_pages_to_add = delta.get("pages_to_add", [])
            delta_pages_to_update = delta.get("pages_to_update", [])
            delta_pages_to_remove = delta.get("pages_to_remove", [])
            planned["pages_to_add"] = len(delta_pages_to_add)
            planned["pages_to_update"] = len(delta_pages_to_update)
            planned["pages_to_remove"] = len(delta_pages_to_remove)
        except Exception:
            pass

    def _entry_path(entry: "str | dict") -> str:
        """Extract file path from a delta entry — accepts both str and dict formats."""
        if isinstance(entry, str):
            return entry
        return entry.get("path") or entry.get("slug", "")

    # Compute executed: check existence of pages_to_add paths
    pages_added = 0
    for entry in delta_pages_to_add:
        slug = _entry_path(entry)
        if slug:
            target = REPO_ROOT / slug if not Path(slug).is_absolute() else Path(slug)
            if target.exists():
                pages_added += 1

    # For pages_to_update: compare body hashes if available
    files_with_body_diff = 0
    files_metadata_only = 0
    metadata_only_files: list[str] = []

    for entry in delta_pages_to_update:
        path_str = _entry_path(entry)
        if not path_str:
            continue
        full_path = REPO_ROOT / path_str
        if not full_path.exists():
            continue
        if pre_hashes and path_str in pre_hashes:
            post_hash = _body_hash(full_path)
            if post_hash != pre_hashes[path_str]:
                files_with_body_diff += 1
            else:
                files_metadata_only += 1
                metadata_only_files.append(path_str)
        else:
            # No pre-hash available; count as updated (can't distinguish)
            files_with_body_diff += 1

    # For pages_to_remove: check if draft:true was set
    pages_removed = 0
    for entry in delta_pages_to_remove:
        path_str = _entry_path(entry)
        if not path_str:
            continue
        full_path = REPO_ROOT / path_str
        if full_path.exists():
            try:
                text = full_path.read_text(encoding="utf-8")
                fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
                if fm_match:
                    fm = yaml.safe_load(fm_match.group(1)) or {}
                    if fm.get("draft") is True:
                        pages_removed += 1
            except Exception:
                pass

    pages_add_skipped = max(0, planned["pages_to_add"] - pages_added)

    recon = {
        "schema_version": _RECONCILIATION_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "delta_source": f"reports/plans/{family}/{platform}/knowledge_delta.json",
        "site_plan_source": f"reports/plans/{family}/{platform}/site_plan.yaml",
        "planned": planned,
        "executed": {
            "pages_updated": files_with_body_diff + files_metadata_only,
            "pages_added": pages_added,
            "pages_removed": pages_removed,
        },
        "skipped": {
            "pages_update_skipped": planned["pages_to_update"] - files_with_body_diff - files_metadata_only,
            # TC-14: pages_add_skipped > 0 is a FAIL condition (see assert_no_skipped_pages).
            # Only valid exemption: explicit DEFERRED_LOW_IMPORTANCE with operator acknowledgment.
            "pages_add_skipped": pages_add_skipped,
        },
        "body_changes": {
            "files_with_body_diff": files_with_body_diff,
            "files_metadata_only": files_metadata_only,
            "metadata_only_files": metadata_only_files[:20],  # cap list length
        },
    }

    recon_path.write_text(
        json.dumps(recon, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Reconciliation artifact written: {recon_path}")
    return recon_path


class SkippedPagesError(RuntimeError):
    """Raised by assert_no_skipped_pages() when pages_add_skipped > 0 (TC-14).

    Indicates that the delta dispatch step planned new content pages (via
    delta-site-plan / S-82) but did not create them.  Committing in this state
    leaves reference pages that link to missing docs/KB pages.

    Resolve by creating the missing pages (use S-57 for docs, S-58 for KB how-tos)
    or by explicitly acknowledging deferral via mark_pages_deferred_low_importance().
    """


class ReconciliationSchemaUnknownError(RuntimeError):
    """Raised by assert_no_skipped_pages() (RPR-J-10 follow-up, found by
    independent review) when execution_reconciliation.json exists but predates
    schema_version or doesn't match. Reading skipped.pages_add_skipped with a
    .get(key, 0) default on an old/incompatible shape would silently read as
    "0 skipped" -- a false PASS. This function must never let that happen; it
    raises instead of returning normally, so a caller cannot mistake "could
    not verify" for "verified clean."
    """


def assert_no_skipped_pages(
    family: str,
    platform: str,
    *,
    allow_explicit_deferral: bool = True,
) -> None:
    """Assert that no planned new pages were silently skipped in delta dispatch.

    Reads execution_reconciliation.json and raises SkippedPagesError if
    skipped.pages_add_skipped > 0 and the skipped pages have no explicit
    DEFERRED_LOW_IMPORTANCE acknowledgment.

    Args:
        allow_explicit_deferral: When True (default), pages with explicit
            DEFERRED_LOW_IMPORTANCE status in the reconciliation are not
            counted as violations.  Set False in strict mode.

    Raises:
        SkippedPagesError: If any planned pages were not created.
        FileNotFoundError: If execution_reconciliation.json does not exist.
        ReconciliationSchemaUnknownError: If the artifact exists but predates
            schema_version (or doesn't match) -- its shape cannot be trusted.
    """
    recon_path = REPORTS_ROOT / family / platform / "execution_reconciliation.json"
    if not recon_path.is_file():
        raise FileNotFoundError(
            f"execution_reconciliation.json not found for {family}/{platform}. "
            f"Run write_reconciliation() before assert_no_skipped_pages()."
        )

    recon = json.loads(recon_path.read_text(encoding="utf-8"))
    if recon.get("schema_version") != _RECONCILIATION_SCHEMA_VERSION:
        raise ReconciliationSchemaUnknownError(
            f"{family}/{platform}: execution_reconciliation.json predates schema_version "
            f"{_RECONCILIATION_SCHEMA_VERSION} (or doesn't match) — cannot trust its "
            f"skipped.pages_add_skipped shape. Re-run write_reconciliation() to regenerate "
            f"a current-schema artifact before asserting no pages were skipped."
        )
    skipped = recon.get("skipped", {})
    pages_add_skipped = int(skipped.get("pages_add_skipped", 0))

    if pages_add_skipped == 0:
        print(
            f"  {family}/{platform}: assert_no_skipped_pages PASS "
            f"(0 skipped pages; all planned pages created)"
        )
        return

    # Check for explicit deferral acknowledgment
    if allow_explicit_deferral:
        deferred_count = int(skipped.get("pages_deferred_low_importance", 0))
        unaccounted = pages_add_skipped - deferred_count
        if unaccounted <= 0:
            print(
                f"  {family}/{platform}: assert_no_skipped_pages PASS "
                f"({pages_add_skipped} pages explicitly deferred with DEFERRED_LOW_IMPORTANCE)"
            )
            return

        skip_reason = skipped.get("skip_reason", "no reason provided")
        raise SkippedPagesError(
            f"{family}/{platform}: {unaccounted} planned new pages were not created "
            f"and have no DEFERRED_LOW_IMPORTANCE acknowledgment.\n"
            f"  pages_add_skipped: {pages_add_skipped}\n"
            f"  pages_deferred_low_importance: {deferred_count}\n"
            f"  unaccounted skipped: {unaccounted}\n"
            f"  skip_reason recorded: {skip_reason!r}\n"
            f"\n"
            f"RESOLUTION: Create the missing pages (S-57 for docs, S-58 for KB how-tos)\n"
            f"  OR call mark_pages_deferred_low_importance() with operator acknowledgment\n"
            f"  before this assertion will pass.\n"
            f"\n"
            f"Reconciliation: {recon_path}"
        )

    raise SkippedPagesError(
        f"{family}/{platform}: {pages_add_skipped} planned new pages were skipped. "
        f"Reconciliation: {recon_path}"
    )


def mark_pages_deferred_low_importance(
    family: str,
    platform: str,
    *,
    count: int,
    operator_reason: str,
) -> None:
    """Record an explicit DEFERRED_LOW_IMPORTANCE deferral in execution_reconciliation.json.

    This is the ONLY valid way to prevent assert_no_skipped_pages() from failing
    when pages_add_skipped > 0.  The operator_reason must be non-empty.

    Precondition: execution_reconciliation.json must already exist (call
    write_reconciliation() first).

    Args:
        count: Number of pages being explicitly deferred (must equal pages_add_skipped).
        operator_reason: Non-empty string explaining why deferral is acceptable.
            Must mention class_importance or equivalent justification.
    """
    if not operator_reason or not operator_reason.strip():
        raise ValueError("operator_reason must be non-empty for DEFERRED_LOW_IMPORTANCE.")

    recon_path = REPORTS_ROOT / family / platform / "execution_reconciliation.json"
    if not recon_path.is_file():
        raise FileNotFoundError(
            f"execution_reconciliation.json not found for {family}/{platform}. "
            f"Run write_reconciliation() first."
        )

    recon = json.loads(recon_path.read_text(encoding="utf-8"))
    recon.setdefault("skipped", {})["pages_deferred_low_importance"] = count
    recon["skipped"]["deferred_reason"] = operator_reason.strip()

    recon_path.write_text(json.dumps(recon, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"  {family}/{platform}: DEFERRED_LOW_IMPORTANCE recorded "
        f"({count} pages; reason: {operator_reason[:80]!r})"
    )


def capture_pre_update_hashes(family: str, platform: str) -> dict[str, str]:
    """Capture body-content hashes for all content files of a product.

    Call this BEFORE running S-20 (page-update). Pass the result to
    write_reconciliation(pre_hashes=...) after S-20 completes.
    """
    hashes: dict[str, str] = {}
    content_files = _discover_content_files(family, platform)
    for f in content_files:
        try:
            rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
            hashes[rel] = _body_hash(f)
        except Exception:
            continue
    return hashes


def check_coverage_completeness(
    family: str,
    platform: str,
    *,
    review_root: Path | None = None,
    tolerance: float = 0.01,
    decision_rows: list[dict] | None = None,
    scope_paths: list[str] | None = None,
    initial_hashes: dict[str, str] | None = None,
    run_root: Path | None = None,
) -> tuple[bool, list[str]]:
    """Check 6: Verify page_decisions.json covers all discovered English pages.

    Compares every non-draft English .md file discovered by _discover_content_files
    against the paths recorded in page_decisions.json.

    Args:
        tolerance: Fraction of pages that may be uncovered without failing (default 1%).
                   This handles edge cases where new pages are created after PIA runs.
        review_root: Override for reports/refresh_review/ base (tests only).
        initial_hashes: pinned per-path baseline hashes from scope.json. A page missing
            a decision row is exempt from "uncovered" when its current bytes still match
            this baseline — body_refresh.py's early-exit paths (auto_updatable:false,
            zero-actionable-claims) legitimately never call _emit_run_decision for a
            genuinely untouched page, mirroring the same tolerance
            refresh_run.py._reconcile_scope_and_decisions already applies to the
            scope/decision reconciliation gate. Only a page whose bytes actually changed
            with no recorded decision is a real coverage gap.
        run_root: the bound run's root dir, if any. Used two ways, mirroring
            refresh_run.py's own fixes for this exact defect class
            (confirmed live 2026-08-14, 3d/java): (1) `discovered_rel` vs
            `recorded_paths` is compared casefold-tolerant, since a
            case-insensitive-filesystem alias (e.g. 'camera.md' tracked in
            git vs 'Camera.md' the generator wrote) is the same physical
            page, not a real coverage gap; (2) a page recorded only in
            `_record_extra_allowed_hash`'s sidecar (deliberately
            receipt-less writes like TC-DUPIDX-02's _index.md regeneration,
            or an S-73 manual-edit fallback) is exempt when its current
            bytes match the authorized hash.

    Returns:
        (passed: bool, failures: list[str])
    """
    root = review_root or _REVIEW_ROOT
    decisions_path = root / family / platform / "page_decisions.json"

    discovered = _discover_content_files(family, platform)
    # Normalise to forward-slash repo-relative paths for comparison
    discovered_rel: list[str] = []
    for f in discovered:
        try:
            rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            rel = str(f).replace("\\", "/")
        # Skip draft pages — they may not be in decisions
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            if "draft:" in text and "draft: true" in text[:500]:
                continue
        except OSError:
            pass
        discovered_rel.append(rel)

    if scope_paths is not None:
        scoped = {Path(path).as_posix() for path in scope_paths}
        discovered_rel = [path for path in discovered_rel if path in scoped]
        # Scope can contain planned new pages that do not exist yet; those must
        # still receive a disposition rather than disappearing from coverage.
        discovered_rel.extend(sorted(scoped.difference(discovered_rel)))

    total = len(discovered_rel)
    if total == 0:
        # No pages discovered — either product not generated yet or wrong paths.
        # Treat as passing to avoid blocking on products without content.
        return True, []

    if decision_rows is not None:
        recorded_paths = {
            row["page_path"] for row in decision_rows if isinstance(row, dict)
        }
    # Only require the legacy decisions file in explicit forensic compatibility mode.
    elif not decisions_path.is_file():
        return False, [
            f"page_decisions.json not found: {decisions_path}. "
            "Run page_impact_assess.py and the S-20 / S-84 refresh chain before --verify."
        ]

    else:
        try:
            data = json.loads(decisions_path.read_text(encoding="utf-8")) or {}
            recorded_paths = set(data.get("pages", {}).keys())
        except Exception as exc:
            return False, [f"Could not read page_decisions.json: {exc}"]

    uncovered, _ = _casefold_path_diff(set(discovered_rel), recorded_paths)
    # Preserve discovered_rel's original order/dedup semantics instead of the
    # arbitrary set order _casefold_path_diff returns.
    uncovered = [p for p in discovered_rel if p in uncovered]
    if initial_hashes or run_root is not None:
        extra_allowed = _load_extra_allowed_hashes(run_root) if run_root else {}

        def _unchanged(rel: str) -> bool:
            target = REPO_ROOT / rel
            if not target.is_file():
                return False
            current = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
            if current == (initial_hashes or {}).get(rel):
                return True
            return current in extra_allowed.get(rel, set())

        uncovered = [p for p in uncovered if not _unchanged(p)]
    uncovered_frac = len(uncovered) / total

    if uncovered_frac <= tolerance:
        return True, []

    failures: list[str] = [
        f"Coverage incomplete: {len(uncovered)} of {total} pages not in page_decisions.json "
        f"({uncovered_frac:.1%} uncovered, tolerance {tolerance:.1%})"
    ]
    for p in uncovered[:10]:
        failures.append(f"  - Missing: {p}")
    if len(uncovered) > 10:
        failures.append(f"  ... and {len(uncovered) - 10} more uncovered pages")
    return False, failures


# ---------------------------------------------------------------------------
# Check 12 (MT074 B15): mass-deletion guard
# ---------------------------------------------------------------------------
#
# Incident: after a claim-ID reassignment, _write_knowledge_delta treated
# 11,942 of 11,945 removed claims as removed (text-identical to added ones),
# semantic_diff made FEATURE_REMOVED events, body_impact UT_REMOVAL, and
# body_refresh DELETED the whole body of 41 pages (2,390 deletions, 0
# additions) -- caught only by a human diff review. The text-reconciliation
# fix (reidentified_claims) exists, but nothing GUARDED the outcome. This
# check compares base vs working bytes for every in-scope page and trips on
# the outcome itself, whatever upstream stage caused it.

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*(?:\n|$)", re.DOTALL)


def _split_body(text: str) -> str:
    """Body of a markdown page: everything after the closing frontmatter fence."""
    text = text.replace("\r\n", "\n")
    m = _FRONTMATTER_RE.match(text)
    return text[m.end():] if m else text


def _read_base_blobs(paths: list[str], base_ref: str) -> "dict[str, bytes | None]":
    """Bytes of each repo-relative path at base_ref (None = absent there).

    One ``git cat-file --batch`` process for the whole list: a run scope can
    carry 1000+ pages and a ``git show`` per page would be needlessly slow.
    Any git failure yields None for every path (callers treat that as "no
    comparable base", i.e. SKIP, never a fabricated defect).
    """
    if _cfg_git_base_blobs is not None:
        return _cfg_git_base_blobs(paths, base_ref)
    out: "dict[str, bytes | None]" = {p: None for p in paths}
    if not paths:
        return out
    request = "".join(f"{base_ref}:{p}\n" for p in paths).encode("utf-8")
    try:
        proc = subprocess.run(
            ["git", "cat-file", "--batch"],
            input=request, capture_output=True,
            cwd=str(REPO_ROOT), timeout=300,
        )
    except Exception:
        return out
    if proc.returncode != 0:
        return out
    data, pos = proc.stdout, 0
    for p in paths:
        eol = data.find(b"\n", pos)
        if eol < 0:
            break
        header = data[pos:eol].split()
        pos = eol + 1
        # `<sha> <type> <size>` for ANY found object (blob, tree, commit, tag);
        # `<spec> missing` / `<spec> ambiguous` carry no body. Advance past the
        # body of every found object, not just blobs, or one directory path in
        # the list (a tree) desynchronises every later read.
        if len(header) == 3 and header[2].isdigit():
            size = int(header[2])
            if header[1] == b"blob":
                out[p] = data[pos:pos + size]
            pos += size + 1  # trailing newline after the object body
    return out


def _body_shrink_rows(paths: list[str], base_ref: str) -> list[dict]:
    """Per-page body size change for every path that exists at base_ref.

    A path with no version at base_ref (a genuinely new page) is not
    comparable and is omitted. A path whose working file is gone counts as
    an empty body (a whole-page deletion is the extreme shrink).
    """
    blobs = _read_base_blobs(paths, base_ref)
    rows: list[dict] = []
    for rel in paths:
        base_bytes = blobs.get(rel)
        if base_bytes is None:
            continue
        base_body = _split_body(base_bytes.decode("utf-8", errors="replace"))
        try:
            new_body = _split_body(
                (REPO_ROOT / rel).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError):
            new_body = ""
        base_words = len(base_body.split())
        new_words = len(new_body.split())
        base_lines = Counter(l.strip() for l in base_body.splitlines() if l.strip())
        new_lines = Counter(l.strip() for l in new_body.splitlines() if l.strip())
        shrink_words = base_words - new_words
        rows.append({
            "path": rel,
            "base_words": base_words,
            "new_words": new_words,
            "shrink_words": shrink_words,
            "shrink_fraction": (shrink_words / base_words) if base_words else 0.0,
            "deleted_lines": sum((base_lines - new_lines).values()),
            "added_lines": sum((new_lines - base_lines).values()),
        })
    return rows


def check_mass_deletion(
    paths: list[str],
    *,
    base_ref: str,
    decision_rows: "list[dict] | None" = None,
    authorized_paths: "set[str] | None" = None,
    claims_current_total: "int | None" = None,
    knowledge_delta: "dict | None" = None,
) -> "tuple[list[str], list[str], list[str]]":
    """Check 12 core: returns (failures, notes, unknowns). Pure apart from
    reading git and the working tree; thresholds come from ``_cfg_mass_deletion``.

    UNKNOWN (RPR-J-06, fail-closed): when the guard could not read a base
    version for enough in-scope pages -- none at all, or fewer than
    ``min_comparable_fraction`` of the pages that should have one (every .md
    page except those a GENERATED decision explains as new) -- it did not
    really look, so the outcome is an ``unknowns`` entry, never a silent PASS.

    (a) a page's body shrank by more than ``max_shrink_fraction`` AND by more
        than ``min_shrink_words`` words, with no explaining disposition;
    (b) run-wide, the share of comparable in-scope pages with such a shrink
        exceeds ``max_run_share`` and is at least ``min_run_pages`` pages;
    (c) the knowledge delta's removed-claim share of the base claims exceeds
        ``max_removed_claim_share`` while ``reidentified_claims`` covers less
        than ``min_reidentified_coverage`` of the removed ids.

    A page is "explained" when its page decision's disposition or
    intended_action is in ``_SHRINK_EXPLAINING_MARKERS`` or the page is
    listed in ``authorized_paths``. Explained pages are excluded from (a)
    and (b). Evidence-only restamps change frontmatter only, so they never
    shrink a body and can never trip this check.
    """
    cfg = _cfg_mass_deletion
    failures: list[str] = []
    notes: list[str] = []
    unknowns: list[str] = []

    explained: set[str] = {p.casefold() for p in (authorized_paths or set())}
    for row in decision_rows or []:
        markers = {
            str(row.get("disposition") or "").upper(),
            str(row.get("intended_action") or "").upper(),
        }
        if markers & _SHRINK_EXPLAINING_MARKERS:
            explained.add(str(row.get("page_path") or "").casefold())

    md_paths = [p for p in paths if p.endswith(".md")]
    rows = _body_shrink_rows(md_paths, base_ref)
    new_pages = {
        str(row.get("page_path") or "").casefold()
        for row in (decision_rows or [])
        if str(row.get("disposition") or "").upper() == "GENERATED"
    }
    expected_comparable = [p for p in md_paths if p.casefold() not in new_pages]
    if expected_comparable and len(rows) < max(
        1, cfg["min_comparable_fraction"] * len(expected_comparable)
    ):
        unknowns.append(
            f"Check 12 (mass-deletion guard): could not read a base version at "
            f"{base_ref!r} for {len(expected_comparable) - len(rows)} of "
            f"{len(expected_comparable)} in-scope page(s) (git failure, unknown "
            f"base ref, or path absent at base) -- only {len(rows)} comparable; "
            "cannot confirm the absence of mass deletion"
        )
    large = [
        r for r in rows
        if r["shrink_fraction"] > cfg["max_shrink_fraction"]
        and r["shrink_words"] > cfg["min_shrink_words"]
    ]
    unexplained = [r for r in large if r["path"].casefold() not in explained]
    unexplained.sort(key=lambda r: (-r["shrink_words"], r["path"]))

    def _describe(r: dict) -> str:
        return (
            f"{r['path']} ({r['base_words']} -> {r['new_words']} words, "
            f"-{r['shrink_fraction']:.0%}; lines -{r['deleted_lines']}/"
            f"+{r['added_lines']})"
        )

    for r in unexplained[:5]:
        failures.append(
            "Check 12 (mass-deletion guard): body shrank beyond "
            f"{cfg['max_shrink_fraction']:.0%}/{cfg['min_shrink_words']} words "
            f"with no explaining disposition: {_describe(r)}"
        )
    if len(unexplained) > 5:
        failures.append(
            f"Check 12 (mass-deletion guard): ... and {len(unexplained) - 5} "
            "more page(s) with an unexplained large body shrink"
        )

    comparable = len(rows)
    if (
        comparable
        and len(unexplained) >= cfg["min_run_pages"]
        and len(unexplained) / comparable > cfg["max_run_share"]
    ):
        total_deleted = sum(r["deleted_lines"] for r in unexplained)
        total_added = sum(r["added_lines"] for r in unexplained)
        failures.append(
            "Check 12 (mass-deletion guard, run-wide): "
            f"{len(unexplained)} of {comparable} comparable in-scope pages "
            f"({len(unexplained) / comparable:.1%}) lost >"
            f"{cfg['max_shrink_fraction']:.0%} of their body "
            f"(> {cfg['max_run_share']:.0%} and >= {cfg['min_run_pages']} pages "
            f"allowed); {total_deleted} lines deleted vs {total_added} added. "
            f"Worst: {', '.join(r['path'] for r in unexplained[:3])}"
        )
    elif comparable:
        notes.append(
            f"{len(large) - len(unexplained)} explained and "
            f"{len(unexplained)} unexplained large shrink(s) across "
            f"{comparable} comparable page(s)"
        )

    if knowledge_delta is not None and claims_current_total:
        removed = list(knowledge_delta.get("removed_claims") or [])
        reidentified = knowledge_delta.get("reidentified_claims") or {}
        new = list(knowledge_delta.get("new_claims") or [])
        # removed_claims is already net of reidentified ids; the raw removal
        # count is removed + reidentified. The base total follows from the
        # current total (reidentified ids cancel out of added vs removed).
        raw_removed = len(removed) + len(reidentified)
        base_total = claims_current_total - len(new) + len(removed)
        if base_total > 0 and raw_removed:
            share = raw_removed / base_total
            coverage = len(reidentified) / raw_removed
            if (
                share > cfg["max_removed_claim_share"]
                and coverage < cfg["min_reidentified_coverage"]
            ):
                failures.append(
                    "Check 12 (mass-deletion guard, knowledge delta): "
                    f"{raw_removed} of {base_total} base claims removed "
                    f"({share:.1%} > {cfg['max_removed_claim_share']:.0%}) but "
                    f"reidentified_claims covers only {coverage:.1%} of them "
                    f"(< {cfg['min_reidentified_coverage']:.0%}) -- a claim-ID "
                    "reassignment storm would delete real content downstream"
                )
            else:
                notes.append(
                    f"claim removal {raw_removed}/{base_total} ({share:.1%}), "
                    f"reidentified coverage {coverage:.1%}"
                )
    return failures, notes, unknowns


# ---------------------------------------------------------------------------
# Check 13 (MT074 B4): plan-time capability ledger
# ---------------------------------------------------------------------------

def check_capability_ledger_plan(
    manifest: "dict | None",
) -> "tuple[list[str], list[str], str]":
    """Returns (failures, warnings, note-for-the-PASS/NA-line).

    Applies to run-bound upstream/combined runs. prepare_run records
    ``manifest["capability_ledger"] = {path, plan_fingerprint, initial_sha256,
    release_surface}`` for a real knowledge delta; this check requires the file
    to exist, the PLAN IDENTITY recomputed from the CURRENT file (sorted unit
    ids + schema_version) to equal the recorded ``plan_fingerprint`` -- units
    cannot be silently added/removed/regrouped after planning, while
    set-disposition edits (which never touch unit ids) are allowed at any run
    state -- and ``validate_ledger_ex(stage='plan')`` to report NO errors
    (warnings are returned for display, never blocking;
    ``initial_sha256`` is informational only). Not
    applicable: no bound run, remediation mode, or a run whose delta was not
    real (``blog_announcement_required`` false -- no ledger is built then).
    A real-delta run with no recorded ledger FAILS only when its manifest
    carries ``capability_ledger_required`` (written by create_run for NEW
    upstream/combined runs); manifests created before the ledger existed are
    NA ("run predates capability ledger") so in-flight runs still verify.
    """
    if manifest is None:
        return [], [], "NA — no run-bound manifest (capability ledger not applicable)"
    mode = manifest.get("mode")
    if mode not in {"upstream", "combined"}:
        return [], [], f"NA — {mode} run has no capability ledger"
    record = manifest.get("capability_ledger")
    if not isinstance(record, dict):
        if not manifest.get("capability_ledger_required"):
            return [], [], "NA — run predates capability ledger (no capability_ledger_required marker)"
        if manifest.get("blog_announcement_required"):
            return (
                ["Check 13 (capability_ledger_plan): real knowledge delta but no "
                 "capability_ledger is recorded in the run manifest"],
                [], "",
            )
        return [], [], "NA — empty/no-op knowledge delta, no capability ledger"
    ref = str(record.get("path") or "")
    path = Path(ref)
    if not path.is_absolute():
        path = REPO_ROOT / ref
    if not path.is_file():
        return [f"Check 13 (capability_ledger_plan): ledger file missing: {ref}"], [], ""
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"Check 13 (capability_ledger_plan): ledger unreadable: {exc}"], [], ""
    from commands.ops.refresh_run import capability_plan_fingerprint

    actual = capability_plan_fingerprint(ledger if isinstance(ledger, dict) else {})
    if actual != record.get("plan_fingerprint"):
        return [
            "Check 13 (capability_ledger_plan): ledger plan identity changed since "
            "planning (units added, removed or regrouped): fingerprint "
            f"{actual} != recorded {record.get('plan_fingerprint')}: {ref}"
        ], [], ""
    from lib.capability_delta import validate_ledger_ex

    errors, warnings = validate_ledger_ex(ledger, stage="plan")
    if errors:
        shown = "; ".join(errors[:5]) + (
            f"; ... and {len(errors) - 5} more" if len(errors) > 5 else ""
        )
        return [
            f"Check 13 (capability_ledger_plan): ledger invalid at plan stage "
            f"({len(errors)} error(s)): {shown}"
        ], list(warnings), ""
    return [], list(warnings), (
        f"PASS — capability ledger valid at plan stage "
        f"({len(ledger.get('units') or [])} unit(s), {len(warnings)} warning(s), "
        f"release_surface={record.get('release_surface')})"
    )


def verify(family: str, platform: str, *, allow_warn: bool = False,
           unknowns_out: "list | None" = None,
           base_ref: "str | None" = None,
           run_id: "str | None" = None) -> tuple[bool, list[str]]:
    """Run the post-refresh verification checklist.

    Returns (passed: bool, failures: list[str]).
    This function is read-only — it never modifies any files.

    RPR-F-01: Check 7's "ran-and-did-nothing" branch and Check 8 (both sub-cases)
    are now BLOCKING by default — they were WARN-only in exactly the branches the
    real PDF-NET-REFRESH-001 v26.7.0 tracking gap reproduces (plan §2.4). Pass
    allow_warn=True to demote them back to WARN (explicit opt-out only, never the
    default), for the rare case where an operator has manually confirmed the
    condition is benign.

    RPR-J-00 (tri-state, originally Checks 7/8): a check whose durable/recording inputs
    are absent, old-schema, or mutually-contradictory returns UNKNOWN rather than a
    fabricated FAIL with a made-up count. UNKNOWN items are appended to `unknowns_out`
    (when provided) and printed, but do NOT enter `failures` — so `passed` is not
    flipped by "I could not verify". A caller that must not ship an unverified refresh
    treats a non-empty unknowns list as commit-blocking (see main()'s exit code 3),
    which is different from a content defect (exit 1).

    RPR-J-06 (tri-state, broadened to every check in this function): the same
    principle now applies wherever an artifact that WAS applicable (it existed, or a
    subprocess ran) failed to parse, timed out, or raised — Checks 1, 4, 5, 7, 8 Case B,
    9, 10, and 11 all route that class of failure to `unknowns`, never to `failures`.
    A tool crashing or a file being unparseable proves the check couldn't run; it does
    not prove the underlying content is defective. A check that is simply not
    applicable (no pages discovered, no updated pages recorded, no report generated
    yet) is unaffected — that stays a plain, non-blocking SKIP/PASS, since there is
    nothing to be uncertain about.

    ``run_id`` selects the exact schema-v3 manifest, decision JSONL, receipts,
    and pinned base used for commit readiness. Without a run ID, ``base_ref`` is
    an explicit forensic interval. The importable diagnostic API retains HEAD
    as a compatibility default; the CLI rejects an omitted run/base.
    """
    failures = []
    unknowns = unknowns_out if unknowns_out is not None else []
    bound_manifest: dict | None = None
    run_decisions: list[dict] | None = None
    run_scope: list[str] | None = None
    run_initial_hashes: dict[str, str] | None = None
    run_root_for_coverage: Path | None = None
    if run_id is not None:
        try:
            bound = _load_bound_run(family, platform, run_id)
            bound_manifest = bound["manifest"]
            run_root_for_coverage = bound["run_root"]
            run_decisions = _load_run_decisions(bound["run_root"], run_id)
            _validate_run_receipts(bound["run_root"], run_id, run_decisions)
            _validate_bound_run_evidence(
                bound_manifest, bound["run_root"], run_decisions
            )
            run_scope = bound_manifest.get("scope", {}).get("paths") or []
            scope_json_path = bound["run_root"] / "scope.json"
            if scope_json_path.is_file():
                run_initial_hashes = (
                    json.loads(scope_json_path.read_text(encoding="utf-8")).get(
                        "initial_hashes"
                    )
                    or {}
                )
            if base_ref is not None and base_ref != bound_manifest["base_commit_sha"]:
                raise ValueError(
                    f"--base {base_ref} conflicts with run base "
                    f"{bound_manifest['base_commit_sha']}"
                )
            base_ref = bound_manifest["base_commit_sha"]
        except Exception as exc:
            unknowns.append(f"Run binding unavailable: {exc}")
            return True, []
    elif base_ref is None:
        # Compatibility for the importable diagnostic API. The commit-readiness
        # CLI requires either --run-id or an explicit forensic --base.
        base_ref = "HEAD"

    merged = KNOWLEDGE_ROOT / family / platform / "merged"

    # Check 1: model.yaml shows no stale_since
    model_path = merged / "model.yaml"
    if model_path.is_file():
        try:
            model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
            if model.get("stale_since") is not None:
                failures.append(
                    f"stale_since is set in merged/model.yaml: {model['stale_since']}"
                )
        except Exception as exc:
            # RPR-J-06: an unparseable model.yaml proves nothing about whether the
            # model is actually stale -- UNKNOWN, not a fabricated FAIL.
            msg = f"Check 1: could not read model.yaml: {exc}"
            unknowns.append(msg)
            print(f"  Check 1: UNKNOWN (RPR-J-06) — {msg}")

    # Check 2 (RPR-J-07, tier-aware): No content pages cite claim IDs absent
    # from merged/claims.json. A missing Tier-1 (CLM-*, scout/deterministic)
    # claim_id is a real defect and still blocks. A missing Tier-2 (ERC-*,
    # LLM-enriched) claim_id is expected enrichment churn -- capability-mode
    # enriched claims are still content-hash-keyed (RPR-J-16 only stabilized
    # the member-doc majority) and legitimately re-key across a knowledge
    # rebuild -- so it is reported, not blocked.
    claims_path = merged / "claims.json"
    valid_claim_ids: set[str] = set()
    claims_list = _load_json_list(claims_path)
    for c in claims_list:
        if isinstance(c, dict) and "claim_id" in c:
            valid_claim_ids.add(c["claim_id"])

    if valid_claim_ids or claims_path.is_file():
        content_files = _discover_content_files(family, platform)
        orphaned_pages = []
        tier2_orphaned_pages = []
        for page in content_files:
            evidence = _get_page_evidence(page)
            cited_claims = evidence.get("claims") or []
            orphaned_all = [cid for cid in cited_claims if cid not in valid_claim_ids]
            if not orphaned_all:
                continue
            tier1_orphaned = [cid for cid in orphaned_all if not is_tier2_claim_id(cid)]
            tier2_orphaned = [cid for cid in orphaned_all if is_tier2_claim_id(cid)]
            if tier1_orphaned:
                orphaned_pages.append((page, tier1_orphaned))
            if tier2_orphaned:
                tier2_orphaned_pages.append((page, tier2_orphaned))
        if orphaned_pages:
            for page, orphaned in orphaned_pages[:5]:  # cap at 5 in message
                try:
                    display_path = page.relative_to(REPO_ROOT)
                except ValueError:
                    display_path = page
                failures.append(
                    f"Orphaned claims in {display_path}: {orphaned[:3]}"
                )
            if len(orphaned_pages) > 5:
                failures.append(f"... and {len(orphaned_pages) - 5} more pages with orphaned claims")
        if tier2_orphaned_pages:
            print(f"  Check 2: {sum(len(o) for _, o in tier2_orphaned_pages)} Tier-2/enriched "
                  f"orphaned claim citation(s) across {len(tier2_orphaned_pages)} page(s) — "
                  f"non-blocking (RPR-J-07), expected enrichment churn")

    # Check 3: No reference pages exist for classes absent from api_surface.json
    api_path = merged / "api_surface.json"
    ref_root = CONTENT_ROOT / f"reference.aspose.org/en/{family}/{platform}"
    check3_passed, check3_failures = check_stale_reference_pages(api_path, ref_root)
    failures.extend(check3_failures)

    # Check 3b: retired reference pages for classes that exist in api_surface
    check3b_passed, check3b_failures = check_incorrectly_retired_pages(api_path, ref_root)
    failures.extend(check3b_failures)
    if not check3b_passed:
        print(f"  Check 3b: FAIL — {len(check3b_failures)} incorrectly retired reference page(s)")
    else:
        print("  Check 3b: PASS — no incorrectly retired reference pages")

    # Check 4: stale_detect.py reports 0 stale pages
    # SPEC DEVIATION (intentional): TC-05 acceptance check specified running audit.py on
    # pages listed in progress.json (pages_updated + pages_generated).  That approach was
    # not implemented because:
    #   (a) S-20 and S-23 already run audit.py on each page during the chain — adding a
    #       second full-page audit in --verify adds O(N) latency with no new signal.
    #   (b) progress.json tracks step names, not individual page paths; extending it to
    #       accumulate page paths would couple the tracker to every content-generation skill.
    # stale_detect.py is a correct end-state proxy: a page that fails audit would have its
    # model_sha left stale (stale_detect catches it) or its orphaned claims flagged (Check 2).
    stale_detect = _HERE / "stale_detect.py"
    if stale_detect.is_file():
        try:
            _run = _cfg_subprocess_run if _cfg_subprocess_run is not None else subprocess.run
            result = _run(
                [sys.executable, str(stale_detect),
                 family, platform, "--json",
                 "--content-root", str(CONTENT_ROOT),
                 "--knowledge-root", str(KNOWLEDGE_ROOT)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(REPO_ROOT),
            )
            if result.returncode != 0:
                # returncode 1 means stale pages found
                try:
                    report = json.loads(result.stdout)
                    stale_count = report.get("stale_pages", 0)
                    if stale_count:
                        failures.append(f"stale_detect reports {stale_count} stale page(s)")
                        # List first few
                        for page_info in report.get("pages", [])[:3]:
                            failures.append(
                                f"  - {page_info.get('file', '?')} ({page_info.get('issues', [])})"
                            )
                except json.JSONDecodeError:
                    # RPR-J-06: a non-zero exit with unparseable output proves the tool
                    # misbehaved, not that N pages are stale -- UNKNOWN, not a fabricated
                    # defect count.
                    msg = f"Check 4: stale_detect.py exited {result.returncode} with unparseable output"
                    unknowns.append(msg)
                    print(f"  Check 4: UNKNOWN (RPR-J-06) — {msg}")
        except subprocess.TimeoutExpired:
            msg = "Check 4: stale_detect.py timed out — could not verify"
            unknowns.append(msg)
            print(f"  Check 4: UNKNOWN (RPR-J-06) — {msg}")
        except Exception as exc:
            msg = f"Check 4: could not run stale_detect.py: {exc}"
            unknowns.append(msg)
            print(f"  Check 4: UNKNOWN (RPR-J-06) — {msg}")

    # Check 5: Reconciliation artifact shows no unreconciled planned work
    recon_path = REPORTS_ROOT / family / platform / "execution_reconciliation.json"
    if recon_path.is_file():
        try:
            recon = json.loads(recon_path.read_text(encoding="utf-8"))
            if recon.get("schema_version") != _RECONCILIATION_SCHEMA_VERSION:
                # RPR-J-08: a pre-schema-versioning artifact may use a different
                # field shape entirely -- reading its planned/executed/skipped
                # dicts with .get(key, 0) would silently read as "0 planned, 0
                # executed" (identical to a genuinely empty, reconciled run).
                # UNKNOWN, not a silent pass or a fabricated FAIL.
                msg = (
                    f"Check 5: execution_reconciliation.json predates schema_version "
                    f"{_RECONCILIATION_SCHEMA_VERSION} (or doesn't match) — cannot "
                    f"trust its planned/executed/skipped shape."
                )
                unknowns.append(msg)
                print(f"  Check 5: UNKNOWN (RPR-J-08) — {msg}")
            else:
                p = recon.get("planned", {})
                e = recon.get("executed", {})
                s = recon.get("skipped", {})
                key_map = {
                    "pages_to_update": "pages_updated",
                    "pages_to_add": "pages_added",
                    "pages_to_remove": "pages_removed",
                }
                for plan_key, exec_key in key_map.items():
                    planned_n = p.get(plan_key, 0)
                    executed_n = e.get(exec_key, 0)
                    skipped_key = plan_key.replace("pages_to_", "pages_") + "_skipped"
                    skipped_n = s.get(skipped_key, 0)
                    if executed_n + skipped_n < planned_n:
                        failures.append(
                            f"Reconciliation: {plan_key}={planned_n}, "
                            f"executed={executed_n}, skipped={skipped_n}"
                        )
        except Exception as exc:
            # RPR-J-06: an unparseable reconciliation artifact proves nothing about
            # whether planned work was actually reconciled -- UNKNOWN, not a
            # fabricated FAIL.
            msg = f"Check 5: could not read reconciliation artifact: {exc}"
            unknowns.append(msg)
            print(f"  Check 5: UNKNOWN (RPR-J-06) — {msg}")

    # Check 7 (G-16, re-founded RPR-J-05): Completeness guard — if the knowledge
    # delta shows significant claim removal (>50) but git shows literally zero
    # real body changes anywhere in this product's discovered pages, that's a
    # genuine defect. Re-founded on a real git diff (reusing
    # audit_content_hash.py's existing _git_show/_body_hash primitives, per
    # plan §19.3/§19.5) instead of progress.json/execution_reconciliation.json
    # bookkeeping — those files are no longer consulted for this verdict.
    claim_delta_path = KNOWLEDGE_ROOT / family / platform / "merged" / "knowledge_delta.json"
    if claim_delta_path.is_file():
        try:
            claim_delta = json.loads(claim_delta_path.read_text(encoding="utf-8"))
            removed_count = len(claim_delta.get("removed_claims", []))
            if removed_count <= 50:
                print("  Check 7: PASS — completeness guard (removed_count <= 50)")
            else:
                git_view = _git_body_changed_pages(family, platform, base_ref=base_ref)
                if git_view is None:
                    msg = (
                        f"Check 7: {removed_count} removed claims, but git-founded body-diff "
                        f"verification is unavailable (no comparable pages at HEAD, or not a "
                        f"git repo) — cannot confirm whether page bodies actually changed."
                    )
                    unknowns.append(msg)
                    print(f"  Check 7: UNKNOWN (RPR-J-05) — {msg}")
                elif git_view["changed"] > 0:
                    print(f"  Check 7: PASS — {git_view['changed']} of {git_view['total']} "
                          f"discovered pages have a real body diff vs {base_ref}")
                else:
                    msg = (
                        f"Check 7: {removed_count} removed claims but git shows 0 of "
                        f"{git_view['total']} discovered pages with a real body diff vs {base_ref}. "
                        f"Pass --allow-warn only after manually confirming this is benign."
                    )
                    if allow_warn:
                        print(f"  Check 7: WARN (--allow-warn) — {msg}")
                    else:
                        failures.append(msg)
                        print(f"  Check 7: FAIL (RPR-J-05) — {msg}")
        except Exception as exc:
            # RPR-J-06: the file exists (guarded above) but failed to parse or another
            # unexpected error occurred -- that's "couldn't verify," not silence. A
            # bare `pass` here would make Check 7 vanish with no signal at all.
            msg = f"Check 7: could not read/parse knowledge_delta.json: {exc}"
            unknowns.append(msg)
            print(f"  Check 7: UNKNOWN (RPR-J-06) — {msg}")

    # Check 8 (G-16): Tracking-gap and stale-prose detection.
    # CASE A (re-founded RPR-J-05): cross-check page_decisions.json's own
    #         BODY_UPDATED claims against git — a decision that claims a page's
    #         body was updated, but which git shows as byte-identical to HEAD,
    #         is the literal PDF-NET-REFRESH-001 tracking-gap shape, now caught
    #         directly against the durable git record instead of comparing two
    #         ephemeral bookkeeping files against each other. A page with no
    #         version at HEAD (a genuinely new page) is unverifiable by this
    #         method and is excluded, not flagged.
    # CASE B: prose_stale_scan report exists with hits — G-15 scan found stale prose
    #         references to removed APIs that have not yet been remediated.
    git_view_c8 = _git_body_changed_pages(family, platform, base_ref=base_ref)
    decisions_path_c8 = _REVIEW_ROOT / family / platform / "page_decisions.json"
    if git_view_c8 is None:
        print("  Check 8 Case A: UNKNOWN — git-founded body-diff verification unavailable "
              "(no comparable pages at HEAD, or not a git repo)")
        unknowns.append("Check 8 (Case A): git-founded verification unavailable")
    elif run_decisions is None and not decisions_path_c8.is_file():
        print("  Check 8 Case A: UNKNOWN — page_decisions.json not present "
              "(nothing to cross-check against git)")
        unknowns.append("Check 8 (Case A): page_decisions.json absent — tracking unverifiable")
    else:
        try:
            if run_decisions is not None:
                body_updated_claims = [
                    row["page_path"]
                    for row in run_decisions
                    if row.get("disposition") == "BODY_UPDATED"
                ]
            else:
                body_updated_claims = [
                    p
                    for p, entry in (
                        (
                            json.loads(
                                decisions_path_c8.read_text(encoding="utf-8")
                            )
                            or {}
                        ).get("pages", {})
                        or {}
                    ).items()
                    if isinstance(entry, dict)
                    and entry.get("decision") == "BODY_UPDATED"
                ]
                decisions_data = json.loads(
                    decisions_path_c8.read_text(encoding="utf-8")
                ) or {}
                if decisions_data.get("schema_version") != _PAGE_DECISIONS_SCHEMA_VERSION:
                    msg = (
                        f"Check 8 (Case A): page_decisions.json predates schema_version "
                        f"{_PAGE_DECISIONS_SCHEMA_VERSION} (or doesn't match) — cannot trust "
                        f"its recorded decisions."
                    )
                    unknowns.append(msg)
                    print(f"  Check 8 Case A: UNKNOWN (RPR-J-08) — {msg}")
                    body_updated_claims = []

            # Only claims git can actually verify (excludes genuinely new pages,
            # which have no version at base_ref to diff against).
            verifiable = [
                p for p in body_updated_claims
                if p in git_view_c8["changed_paths"]
                or p in git_view_c8["unchanged_paths"]
            ]
            mislabeled = [
                p for p in verifiable if p in git_view_c8["unchanged_paths"]
            ]
            if not verifiable:
                print("  Check 8 Case A: PASS — no verifiable BODY_UPDATED decisions "
                      "(none recorded, or all are new pages with no base version)")
            elif not mislabeled:
                print(f"  Check 8 Case A: PASS — all {len(verifiable)} verifiable "
                      f"BODY_UPDATED decision(s) have a real git-diffable body change")
            else:
                msg = (
                    f"Check 8 (Case A): {len(mislabeled)} of {len(verifiable)} page(s) recorded "
                    f"as BODY_UPDATED show NO real body diff vs {base_ref} in git. Example(s): "
                    f"{', '.join(sorted(mislabeled)[:3])}. Pass --allow-warn only after manual "
                    f"confirmation."
                )
                if allow_warn:
                    print(f"  Check 8: WARN (Case A, --allow-warn) — {msg}")
                else:
                    failures.append(msg)
                    print(f"  Check 8: FAIL (Case A, RPR-J-05) — {msg}")
        except Exception as exc:
            print(f"  Check 8 Case A: UNKNOWN — could not read page_decisions.json ({exc})")
            unknowns.append(f"Check 8 (Case A): could not read page_decisions.json: {exc}")

    # CASE B: prose stale scan
    prose_stale_path = (
        REPO_ROOT / "reports" / "gap-analysis" /
        f"{family}-{platform}-prose-stale.json"
    )
    if prose_stale_path.is_file():
        try:
            prose_data = json.loads(prose_stale_path.read_text(encoding="utf-8"))
            hits = prose_data.get("hits", [])
            hit_count = len(hits)
            if hit_count > 0:
                # RPR-F-01: stale prose referencing removed APIs is a real content
                # defect. BLOCKING by default (was WARN).
                msg = (
                    f"Check 8 (Case B): {hit_count} stale prose reference(s) to removed "
                    f"APIs in {prose_stale_path.name}. Run remediation (/page-update or "
                    f"/heal-page) to clear stale prose. Pass --allow-warn only after review."
                )
                if allow_warn:
                    print(f"  Check 8: WARN (Case B, --allow-warn) — {msg}")
                else:
                    failures.append(msg)
                    print(f"  Check 8: FAIL (Case B, RPR-F-01) — {msg}")
            else:
                print("  Check 8 Case B: PASS — prose stale scan has 0 hits")
        except Exception as exc:
            # RPR-J-06: the report file exists but failed to parse -- couldn't verify,
            # not silently fine. A bare `pass` here would make Case B vanish with no
            # signal at all.
            msg = f"Check 8 (Case B): could not read prose-stale scan report: {exc}"
            unknowns.append(msg)
            print(f"  Check 8 Case B: UNKNOWN (RPR-J-06) — {msg}")
    else:
        print("  Check 8 Case B: SKIP — no prose-stale scan report found")

    # Check 6: Coverage completeness — page_decisions.json must cover all discovered pages
    check6_passed, check6_failures = check_coverage_completeness(
        family,
        platform,
        decision_rows=run_decisions,
        scope_paths=run_scope,
        initial_hashes=run_initial_hashes,
        run_root=run_root_for_coverage,
    )
    failures.extend(check6_failures)
    if not check6_passed:
        print(f"  Check 6: FAIL — coverage completeness: {check6_failures[0] if check6_failures else '?'}")
    else:
        print("  Check 6: PASS — page_decisions.json covers all discovered pages")

    # Check 9 (RPR-F-03, S-111): Layer 2 body-prose triage confirmation.
    # Prior to RPR-F-03, triage_confirm.py/reconcile_triage.py had no CLI at all —
    # the S-92 skill's documented invocation, run literally as written, executed the
    # module top-to-bottom and no-op'd (defined functions, touched no files, exited 0)
    # with no signal to the caller. This is the first real, blocking wiring of that
    # scan into --verify. Non-zero exit from the real triage_confirm CLI blocks commit.
    triage_confirm_script = REPO_ROOT / "scripts" / "pipeline" / "lib" / "triage_confirm.py"
    if triage_confirm_script.is_file():
        # Found live 2026-08-24 (mission-plan-the-end-to-end-vast-hejlsberg.md
        # Task 14, the real upstream E2E proof run for pdf/java): run_scope can
        # now legitimately carry 1000+ paths (the G17 full-reference-scope fix),
        # and inlining every path as a literal "--files" argv token overflows
        # Windows CreateProcess's real command-line-length ceiling with
        # FileNotFoundError: [WinError 206] the filename or extension is too
        # long -- not a triage_confirm.py error at all, a process-creation
        # failure before it even runs, surfacing here as an UNKNOWN (RPR-J-06)
        # rather than the real PASS/FAIL verdict. refresh_run.py's own
        # verify_run() hit and fixed the identical class of bug for its own
        # triage_confirm/seo_stability calls via scoped_commands' 40-per-chunk
        # loop; this call site needed the same treatment separately since it's
        # a different script's own, independent invocation.
        _CHUNK_SIZE = 40
        scope_chunks: list[list[str] | None] = (
            [run_scope[i:i + _CHUNK_SIZE] for i in range(0, len(run_scope), _CHUNK_SIZE)]
            if run_scope
            else [None]
        )
        try:
            _run = _cfg_subprocess_run if _cfg_subprocess_run is not None else subprocess.run
            chunk_returncodes: list[int] = []
            total_stale_count = 0
            stale_count_known = True
            for chunk in scope_chunks:
                triage_args = [
                    sys.executable,
                    str(triage_confirm_script),
                    family,
                    platform,
                ]
                if chunk is not None:
                    triage_args.extend(["--files", *chunk])
                triage_args.append("--json")
                result = _run(
                    triage_args,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(REPO_ROOT),
                )
                chunk_returncodes.append(result.returncode)
                if result.returncode == 1:
                    try:
                        report = json.loads(result.stdout)
                        total_stale_count += report.get("stale_count", 0)
                    except json.JSONDecodeError:
                        stale_count_known = False
            # Aggregate across chunks: FAIL (any chunk found stale pages) >
            # UNKNOWN (any chunk returned an undocumented code) > SKIP (every
            # chunk says knowledge absent) > PASS.
            if any(rc == 1 for rc in chunk_returncodes):
                stale_count = total_stale_count if stale_count_known else "?"
                failures.append(
                    f"Check 9: triage_confirm reports {stale_count} stale page(s) "
                    f"(Layer 2 body-prose scan) — re-run the relevant content update "
                    f"step before committing."
                )
            elif any(rc not in (0, 1, 2) for rc in chunk_returncodes):
                # RPR-J-06: an exit code outside the documented 0/1/2 contract is a
                # contract violation by the tool, not proof of stale prose -- we
                # genuinely don't know the content state, so UNKNOWN, not a
                # fabricated "stale pages found" FAIL.
                bad = next(rc for rc in chunk_returncodes if rc not in (0, 1, 2))
                msg = f"Check 9: triage_confirm.py returned an undocumented exit code ({bad})"
                unknowns.append(msg)
                print(f"  Check 9: UNKNOWN (RPR-J-06) — {msg}")
            elif all(rc == 2 for rc in chunk_returncodes):
                # Knowledge artifacts absent — treat as non-blocking SKIP, not FAIL,
                # consistent with Check 8's SKIP-when-absent behavior elsewhere in
                # this function; a product with no knowledge bootstrap yet has
                # nothing for triage_confirm to meaningfully check.
                print(f"  Check 9: SKIP — triage_confirm.py exit 2 (knowledge artifacts absent for {family}/{platform})")
            else:
                print("  Check 9: PASS — triage_confirm Layer 2 scan found 0 stale pages")
        except subprocess.TimeoutExpired:
            msg = "Check 9: triage_confirm.py timed out — could not verify"
            unknowns.append(msg)
            print(f"  Check 9: UNKNOWN (RPR-J-06) — {msg}")
        except Exception as exc:
            msg = f"Check 9: could not run triage_confirm.py: {exc}"
            unknowns.append(msg)
            print(f"  Check 9: UNKNOWN (RPR-J-06) — {msg}")
    else:
        print(f"  Check 9: SKIP — triage_confirm.py not found at {triage_confirm_script}")

    # Check 10 (RPR-F-04): frontmatter-only-refresh grade regressions. For each page
    # this refresh recorded as updated, compare its working-tree content against HEAD;
    # a page whose BODY is byte-identical but whose evidence bumped AND grade regressed
    # is the PDF-NET-REFRESH-001 v26.7.0 defect. BLOCKING (best-effort: SKIP if not a
    # git repo / no updated pages). Wires the previously-orphaned audit_content_hash.py.
    try:
        progress_state_c10 = (
            "run_bound"
            if run_decisions is not None
            else _artifact_schema_state(
                _progress_path(family, platform), _PROGRESS_SCHEMA_VERSION
            )
        )
        if progress_state_c10 == "run_bound":
            progress_c10 = None
            pages_c10 = [
                row["page_path"]
                for row in run_decisions
                if row.get("disposition") in {"BODY_UPDATED", "GENERATED"}
            ]
        elif progress_state_c10 == "stale_or_unversioned":
            # RPR-J-08: progress.json exists but predates schema_version (or
            # doesn't match) -- its pages_updated/pages_generated shape can't be
            # trusted; reading them with .get(key, []) would read identically to
            # "genuinely nothing updated," silently skipping a check that was
            # actually applicable. UNKNOWN, not a silent SKIP.
            msg = (
                f"Check 10: progress.json predates schema_version {_PROGRESS_SCHEMA_VERSION} "
                f"(or doesn't match) — cannot trust its recorded page lists."
            )
            unknowns.append(msg)
            print(f"  Check 10: UNKNOWN (RPR-J-08) — {msg}")
            progress_c10 = None
            pages_c10 = []
        else:
            progress_c10 = _load_progress(family, platform)
            pages_c10 = (
                list(progress_c10.get("pages_updated", []))
                + list(progress_c10.get("pages_generated", []))
                if progress_c10 is not None
                else []
            )
        if progress_c10 is None and progress_state_c10 != "run_bound":
            pass  # already reported UNKNOWN above
        elif pages_c10:
            if _cfg_detect_grade_regressions is not None:
                _detect_gr = _cfg_detect_grade_regressions
            else:
                from commands.content.audit_content_hash import detect_evidence_only_grade_regressions as _detect_gr
            fm_regressions = _detect_gr(pages_c10, base_ref=base_ref)
            if fm_regressions:
                for v in fm_regressions[:5]:
                    failures.append(
                        f"Check 10: frontmatter-only grade regression on {v['path']} "
                        f"({v['grade_before']}->{v['grade_after']}; body unchanged, evidence bumped)"
                    )
                print(f"  Check 10: FAIL (RPR-F-04) — {len(fm_regressions)} frontmatter-only grade regression(s)")
            else:
                print("  Check 10: PASS — no frontmatter-only grade regressions among updated pages")
        else:
            print("  Check 10: SKIP — no updated pages recorded in progress.json")
    except Exception as exc:
        # RPR-J-06: pages WERE recorded as updated (there was something to check),
        # but the detection itself failed -- that's "couldn't verify," not "verified
        # clean." Distinct from the SKIP above, which is a genuine not-applicable case.
        msg = f"Check 10: could not run frontmatter-only detection: {exc}"
        unknowns.append(msg)
        print(f"  Check 10: UNKNOWN (RPR-J-06) — {msg}")

    # Check 11 (RPR-F-05): SEO stability. For each page this refresh recorded as
    # updated, compare title/H1/slug/canonical against HEAD. Any change not declared
    # in the run manifest's `intentional_renames` allowlist is a blocking violation —
    # the first SEO-specific gate in the pipeline. BLOCKING (best-effort: SKIP if not
    # a git repo / no updated pages).
    try:
        progress_state_c11 = (
            "run_bound"
            if run_decisions is not None
            else _artifact_schema_state(
                _progress_path(family, platform), _PROGRESS_SCHEMA_VERSION
            )
        )
        if progress_state_c11 == "run_bound":
            progress_c11 = None
            pages_c11 = [
                row["page_path"]
                for row in run_decisions
                if row.get("disposition") == "BODY_UPDATED"
            ]
        elif progress_state_c11 == "stale_or_unversioned":
            msg = (
                f"Check 11: progress.json predates schema_version {_PROGRESS_SCHEMA_VERSION} "
                f"(or doesn't match) — cannot trust its recorded page list."
            )
            unknowns.append(msg)
            print(f"  Check 11: UNKNOWN (RPR-J-08) — {msg}")
            progress_c11 = None
            pages_c11 = []
        else:
            progress_c11 = _load_progress(family, platform)
            pages_c11 = (
                list(progress_c11.get("pages_updated", []))
                if progress_c11 is not None
                else []
            )
        if progress_c11 is None and progress_state_c11 != "run_bound":
            pass  # already reported UNKNOWN above
        elif pages_c11:
            if _cfg_detect_seo_violations is not None:
                _detect_seo = _cfg_detect_seo_violations
            else:
                from commands.content.seo_stability_check import detect_seo_violations as _detect_seo
            intentional = (
                set(bound_manifest.get("intentional_renames") or [])
                if bound_manifest is not None
                else set()
            )
            seo_violations = _detect_seo(
                pages_c11, base_ref=base_ref, intentional_renames=intentional
            )
            if seo_violations:
                for v in seo_violations[:5]:
                    failures.append(
                        f"Check 11: undeclared SEO change on {v['page']} "
                        f"({v['changed_fields']}; declare in manifest.intentional_renames if intended)"
                    )
                print(f"  Check 11: FAIL (RPR-F-05) — {len(seo_violations)} undeclared SEO change(s)")
            else:
                print("  Check 11: PASS — no undeclared title/H1/slug/canonical changes")
        else:
            print("  Check 11: SKIP — no updated pages recorded in progress.json")
    except Exception as exc:
        # RPR-J-06: same distinction as Check 10 -- pages were recorded as updated,
        # so this was applicable; the detection failing is "couldn't verify."
        msg = f"Check 11: could not run SEO stability detection: {exc}"
        unknowns.append(msg)
        print(f"  Check 11: UNKNOWN (RPR-J-06) — {msg}")

    # Check 12 (MT074 B15): mass-deletion guard. See check_mass_deletion().
    try:
        if run_scope is not None:
            scope_c12 = list(run_scope)
        else:
            scope_c12 = []
            for f in _discover_content_files(family, platform):
                try:
                    scope_c12.append(str(f.relative_to(REPO_ROOT)).replace("\\", "/"))
                except ValueError:
                    scope_c12.append(str(f).replace("\\", "/"))
        delta_c12 = None
        if claim_delta_path.is_file():
            try:
                delta_c12 = json.loads(claim_delta_path.read_text(encoding="utf-8"))
                if not isinstance(delta_c12, dict):
                    delta_c12 = None
            except json.JSONDecodeError as exc:
                msg = f"Check 12: could not parse knowledge_delta.json: {exc}"
                unknowns.append(msg)
                print(f"  Check 12: UNKNOWN (RPR-J-06) — {msg}")
        c12_failures, c12_notes, c12_unknowns = check_mass_deletion(
            scope_c12,
            base_ref=base_ref,
            decision_rows=run_decisions,
            authorized_paths=set(
                (bound_manifest or {}).get("intentional_body_removals") or []
            ),
            claims_current_total=len(claims_list) if claims_list else None,
            knowledge_delta=delta_c12,
        )
        if c12_failures:
            if allow_warn:
                for msg in c12_failures:
                    print(f"  Check 12: WARN (--allow-warn) — {msg}")
            else:
                failures.extend(c12_failures)
                print(f"  Check 12: FAIL (MT074 B15) — {len(c12_failures)} mass-deletion finding(s)")
        for msg in c12_unknowns:
            unknowns.append(msg)
            print(f"  Check 12: UNKNOWN (RPR-J-06) — {msg}")
        if not c12_failures and not c12_unknowns:
            print("  Check 12: PASS — no mass body deletion"
                  + (f" ({'; '.join(c12_notes)})" if c12_notes else ""))
    except Exception as exc:
        msg = f"Check 12: could not run mass-deletion guard: {exc}"
        unknowns.append(msg)
        print(f"  Check 12: UNKNOWN (RPR-J-06) — {msg}")

    # Check 13 (MT074 B4): capability_ledger_plan. See check_capability_ledger_plan().
    try:
        c13_failures, c13_warnings, c13_note = check_capability_ledger_plan(bound_manifest)
        for w in c13_warnings:
            print(f"  Check 13: WARN (ledger plan-stage warning) — {w}")
        if c13_failures:
            if allow_warn:
                for msg in c13_failures:
                    print(f"  Check 13: WARN (--allow-warn) — {msg}")
            else:
                failures.extend(c13_failures)
                print(f"  Check 13: FAIL (MT074 B4) — {len(c13_failures)} capability-ledger finding(s)")
        else:
            print(f"  Check 13: {c13_note}")
    except Exception as exc:
        msg = f"Check 13: could not verify the capability ledger: {exc}"
        unknowns.append(msg)
        print(f"  Check 13: UNKNOWN (RPR-J-06) — {msg}")

    passed = len(failures) == 0
    return passed, failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="post_refresh_verify",
        description="Post-refresh verification gate and progress tracker.",
    )
    parser.add_argument("family", help="Product family (e.g. cells)")
    parser.add_argument("platform", help="Platform (e.g. net)")

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--step", metavar="STEP_NAME",
                      help="Record a named step as complete in progress.json")
    parser.add_argument("--updated", nargs="*", metavar="PATH",
                        help="Paths of pages whose body was updated (used with --step)")
    parser.add_argument("--generated", nargs="*", metavar="PATH",
                        help="Paths of pages that were newly generated (used with --step)")
    mode.add_argument("--verify", action="store_true",
                      help="Run post-refresh verification checklist; exits 1 if failures")
    mode.add_argument("--status", action="store_true",
                      help="Print current progress.json contents")
    mode.add_argument("--reconcile", action="store_true",
                      help="Write execution_reconciliation.json (requires content steps to have completed)")
    mode.add_argument("--reconcile-force", action="store_true",
                      help="Write execution_reconciliation.json, bypassing the content-steps precondition guard (diagnostic/test use only)")
    mode.add_argument("--assert-no-skipped", action="store_true",
                      help="(TC-14) Assert that pages_add_skipped == 0 in execution_reconciliation.json; exits 2 on violation")

    parser.add_argument("--allow-warn", action="store_true",
                        help="(RPR-F-01) Demote Check 7 'ran-and-did-nothing' and Check 8 tracking-gap/"
                             "stale-prose findings back to WARN instead of BLOCK. Opt-out only — use "
                             "solely after manually confirming the flagged condition is benign.")
    parser.add_argument("--base", metavar="REF", default=None,
                        help="Explicit Git base for forensic verification. Commit readiness uses "
                             "--run-id and the base pinned in that exact run.")
    parser.add_argument("--run-id", default=None,
                        help="Exact schema-v3 refresh run to verify for commit readiness")

    args = parser.parse_args(argv)

    if args.step:
        record_step(args.family, args.platform, args.step)
        if args.updated or args.generated:
            record_pages(
                args.family, args.platform,
                updated=args.updated or [],
                generated=args.generated or [],
            )
        return 0

    if args.status:
        print_status(args.family, args.platform)
        return 0

    if args.reconcile:
        try:
            recon_path = write_reconciliation(
                args.family, args.platform, require_content_steps=True
            )
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            print(
                "TIP: Use --reconcile-force to override the content-steps guard "
                "(diagnostic/test use only).",
                file=sys.stderr,
            )
            return 1
        print(f"Reconciliation written to: {recon_path}")
        return 0

    if args.reconcile_force:
        recon_path = write_reconciliation(
            args.family, args.platform, require_content_steps=False
        )
        print(f"Reconciliation written to: {recon_path}")
        return 0

    if args.assert_no_skipped:
        try:
            assert_no_skipped_pages(args.family, args.platform)
            return 0
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except SkippedPagesError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
        except ReconciliationSchemaUnknownError as exc:
            # RPR-J-10 follow-up: distinct from both a clean PASS (0) and a
            # confirmed FAIL (2) -- mirrors --verify's exit-3 INCONCLUSIVE
            # convention. Never silently treated as "0 skipped."
            print(f"UNKNOWN: {exc}", file=sys.stderr)
            return 3

    if args.verify:
        if not args.run_id and not args.base:
            print(
                "UNKNOWN: --verify requires --run-id for commit readiness or "
                "--base for explicit forensic use.",
                file=sys.stderr,
            )
            return 3
        # Prerequisite check — clear error messages instead of cryptic tracebacks
        try:
            from core.prereqs import require_all
            require_all(args.family, args.platform)
        except SystemExit:
            raise
        except Exception:
            pass  # prereqs is best-effort; verify() has its own checks
        print(f"Running post-refresh verification for {args.family}/{args.platform}...")
        unknowns: list = []
        passed, failures = verify(
            args.family, args.platform,
            allow_warn=getattr(args, "allow_warn", False),
            unknowns_out=unknowns,
            base_ref=getattr(args, "base", None),
            run_id=getattr(args, "run_id", None),
        )
        if not passed:
            # Real content/tracking defects — a hard failure (exit 1).
            print(f"VERIFICATION FAILED: {len(failures)} issue(s) found:")
            for f in failures:
                print(f"  - {f}")
            if unknowns:
                print(f"  (plus {len(unknowns)} UNVERIFIABLE item(s) — see UNKNOWN lines above)")
            return 1
        if unknowns:
            # RPR-J-00: nothing FAILED, but one or more checks could not be verified from
            # durable inputs. Not a content defect and no fabricated count — but a refresh
            # that cannot be verified must not be silently treated as clean. Exit 3 so the
            # commit gate can block while --verify's exit 1 stays reserved for real defects.
            print(f"VERIFICATION INCONCLUSIVE: {len(unknowns)} check(s) could not be verified "
                  f"from durable state (no content defect found):")
            for u in unknowns:
                print(f"  - {u}")
            return 3
        print("VERIFICATION PASSED: all checks clean.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
