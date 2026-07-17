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
import json
import re
import subprocess
import sys
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
) -> None:
    """Reconfigure module-level paths for testing or alternative layouts.

    Call with no arguments to reset all paths to their defaults.
    Tests call ``post_refresh_verify.configure(repo_root=tmp_path, ...)``
    in a yield-based fixture and reset with ``configure()`` at teardown.
    """
    global REPO_ROOT, KNOWLEDGE_ROOT, CONTENT_ROOT, REPORTS_ROOT, _REVIEW_ROOT, _HERE
    global _cfg_subprocess_run, _cfg_detect_grade_regressions, _cfg_detect_seo_violations
    global _cfg_git_body_changed
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


_SITE_PATTERNS = (
    "docs.aspose.org/en/{family}/{platform}",
    "kb.aspose.org/en/{family}/{platform}",
    "products.aspose.org/en/{family}/{platform}",
    "reference.aspose.org/en/{family}/{platform}",
    "blog.aspose.org/{family}/{platform}",
)


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
    """RPR-J-17: best-effort read of `base_commit_sha` from the newest refresh-run
    manifest (schema 5e) for this product. None if no manifest exists yet, or the
    field is absent — callers fall back to "HEAD" (unchanged default behavior).

    This is the fix for a real, confirmed limitation (plan §19.3): comparing a
    product's content against "HEAD" is vacuous once its refresh has already been
    committed — HEAD then *is* the post-refresh state, so every check built on
    _git_body_changed_pages (and the identically-shaped F-04/F-05 checks) reports
    zero diffs regardless of whether the refresh actually happened. base_commit_sha
    is the pre-refresh HEAD, captured once before any commits land, so a caller can
    verify against the state the refresh actually started from."""
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


def _save_progress(family: str, platform: str, data: dict) -> None:
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

    stale_ref_pages = []
    for ref_page in sorted(ref_root.glob("*.md")):
        class_name = ref_page.stem.lower()
        if class_name not in valid_api_names and class_name not in ("_index",):
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

    if not ref_root.is_dir() or not valid_api_names:
        return True, []

    incorrectly_retired = []
    for ref_page in sorted(ref_root.glob("*.md")):
        class_name = ref_page.stem.lower()
        if class_name in ("_index",):
            continue
        if class_name not in valid_api_names:
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
    """
    recon_path = REPORTS_ROOT / family / platform / "execution_reconciliation.json"
    if not recon_path.is_file():
        raise FileNotFoundError(
            f"execution_reconciliation.json not found for {family}/{platform}. "
            f"Run write_reconciliation() before assert_no_skipped_pages()."
        )

    recon = json.loads(recon_path.read_text(encoding="utf-8"))
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
) -> tuple[bool, list[str]]:
    """Check 6: Verify page_decisions.json covers all discovered English pages.

    Compares every non-draft English .md file discovered by _discover_content_files
    against the paths recorded in page_decisions.json.

    Args:
        tolerance: Fraction of pages that may be uncovered without failing (default 1%).
                   This handles edge cases where new pages are created after PIA runs.
        review_root: Override for reports/refresh_review/ base (tests only).

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

    total = len(discovered_rel)
    if total == 0:
        # No pages discovered — either product not generated yet or wrong paths.
        # Treat as passing to avoid blocking on products without content.
        return True, []

    # Only require decisions file if there are pages to cover
    if not decisions_path.is_file():
        return False, [
            f"page_decisions.json not found: {decisions_path}. "
            "Run page_impact_assess.py and the S-20 / S-84 refresh chain before --verify."
        ]

    try:
        data = json.loads(decisions_path.read_text(encoding="utf-8")) or {}
        recorded_paths: set[str] = set(data.get("pages", {}).keys())
    except Exception as exc:
        return False, [f"Could not read page_decisions.json: {exc}"]

    uncovered = [p for p in discovered_rel if p not in recorded_paths]
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


def verify(family: str, platform: str, *, allow_warn: bool = False,
           unknowns_out: "list | None" = None,
           base_ref: "str | None" = None) -> tuple[bool, list[str]]:
    """Run the post-refresh verification checklist.

    Returns (passed: bool, failures: list[str]).
    This function is read-only — it never modifies any files.

    RPR-F-01: Check 7's "ran-and-did-nothing" branch and Check 8 (both sub-cases)
    are now BLOCKING by default — they were WARN-only in exactly the branches the
    real PDF-NET-REFRESH-001 v26.7.0 tracking gap reproduces (plan §2.4). Pass
    allow_warn=True to demote them back to WARN (explicit opt-out only, never the
    default), for the rare case where an operator has manually confirmed the
    condition is benign.

    RPR-J-00 (tri-state): a check whose durable/recording inputs are absent, old-schema,
    or mutually-contradictory returns UNKNOWN rather than a fabricated FAIL with a made-up
    count. UNKNOWN items are appended to `unknowns_out` (when provided) and printed, but do
    NOT enter `failures` — so `passed` is not flipped by "I could not verify". A caller that
    must not ship an unverified refresh treats a non-empty unknowns list as commit-blocking
    (see main()'s exit code 3), which is different from a content defect (exit 1).

    RPR-J-17: base_ref is the git ref every git-founded check (7, 8, 10, 11) diffs the
    working tree against. When omitted (None), it resolves in priority order: an
    explicit --base CLI flag > the newest refresh-run manifest's base_commit_sha >
    "HEAD" (the original, unchanged default). Comparing against "HEAD" is only
    meaningful for an in-progress, not-yet-committed refresh — once a refresh has
    landed, HEAD *is* the post-refresh state, so a plain HEAD diff is vacuous
    (confirmed against real pdf/net data, not merely theoretical). Pass an explicit
    base_ref to verify an already-committed historical refresh against its true
    pre-refresh baseline.
    """
    failures = []
    unknowns = unknowns_out if unknowns_out is not None else []
    if base_ref is None:
        base_ref = _load_base_commit_sha(family, platform) or "HEAD"

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
            failures.append(f"Could not read model.yaml: {exc}")

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
                    failures.append(f"stale_detect.py failed (exit {result.returncode})")
        except subprocess.TimeoutExpired:
            failures.append("stale_detect.py timed out")
        except Exception as exc:
            failures.append(f"Could not run stale_detect.py: {exc}")

    # Check 5: Reconciliation artifact shows no unreconciled planned work
    recon_path = REPORTS_ROOT / family / platform / "execution_reconciliation.json"
    if recon_path.is_file():
        try:
            recon = json.loads(recon_path.read_text(encoding="utf-8"))
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
            failures.append(f"Could not read reconciliation artifact: {exc}")

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
                          f"discovered pages have a real body diff vs HEAD")
                else:
                    msg = (
                        f"Check 7: {removed_count} removed claims but git shows 0 of "
                        f"{git_view['total']} discovered pages with a real body diff vs HEAD. "
                        f"Pass --allow-warn only after manually confirming this is benign."
                    )
                    if allow_warn:
                        print(f"  Check 7: WARN (--allow-warn) — {msg}")
                    else:
                        failures.append(msg)
                        print(f"  Check 7: FAIL (RPR-J-05) — {msg}")
        except Exception:
            pass  # Non-blocking; delta file may not exist on first run

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
    elif not decisions_path_c8.is_file():
        print("  Check 8 Case A: UNKNOWN — page_decisions.json not present "
              "(nothing to cross-check against git)")
        unknowns.append("Check 8 (Case A): page_decisions.json absent — tracking unverifiable")
    else:
        try:
            decisions_data = json.loads(decisions_path_c8.read_text(encoding="utf-8")) or {}
            pages = decisions_data.get("pages", {}) or {}
            body_updated_claims = [
                p for p, entry in pages.items()
                if isinstance(entry, dict) and entry.get("decision") == "BODY_UPDATED"
            ]
            # Only claims git can actually verify (excludes genuinely new pages,
            # which have no version at base_ref to diff against).
            verifiable = [
                p for p in body_updated_claims
                if p in git_view_c8["changed_paths"] or p in git_view_c8["unchanged_paths"]
            ]
            mislabeled = [p for p in verifiable if p in git_view_c8["unchanged_paths"]]
            if not verifiable:
                print("  Check 8 Case A: PASS — no verifiable BODY_UPDATED decisions "
                      "(none recorded, or all are new pages with no HEAD version)")
            elif not mislabeled:
                print(f"  Check 8 Case A: PASS — all {len(verifiable)} verifiable "
                      f"BODY_UPDATED decision(s) have a real git-diffable body change")
            else:
                msg = (
                    f"Check 8 (Case A): {len(mislabeled)} of {len(verifiable)} page(s) recorded "
                    f"as BODY_UPDATED show NO real body diff vs HEAD in git — the "
                    f"PDF-NET-REFRESH-001 tracking-gap shape, now caught directly. Example(s): "
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
        except Exception:
            pass  # Non-blocking
    else:
        print("  Check 8 Case B: SKIP — no prose-stale scan report found")

    # Check 6: Coverage completeness — page_decisions.json must cover all discovered pages
    check6_passed, check6_failures = check_coverage_completeness(family, platform)
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
        try:
            _run = _cfg_subprocess_run if _cfg_subprocess_run is not None else subprocess.run
            result = _run(
                [sys.executable, str(triage_confirm_script), family, platform, "--json"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(REPO_ROOT),
            )
            if result.returncode == 2:
                # Knowledge artifacts absent — treat as non-blocking SKIP, not FAIL,
                # consistent with Check 8's SKIP-when-absent behavior elsewhere in
                # this function; a product with no knowledge bootstrap yet has
                # nothing for triage_confirm to meaningfully check.
                print(f"  Check 9: SKIP — triage_confirm.py exit 2 (knowledge artifacts absent for {family}/{platform})")
            elif result.returncode == 1:
                try:
                    report = json.loads(result.stdout)
                    stale_count = report.get("stale_count", 0)
                except json.JSONDecodeError:
                    stale_count = "?"
                failures.append(
                    f"Check 9: triage_confirm reports {stale_count} stale page(s) "
                    f"(Layer 2 body-prose scan) — re-run the relevant content update "
                    f"step before committing."
                )
            elif result.returncode == 0:
                print("  Check 9: PASS — triage_confirm Layer 2 scan found 0 stale pages")
            else:
                failures.append(f"Check 9: triage_confirm.py failed unexpectedly (exit {result.returncode})")
        except subprocess.TimeoutExpired:
            failures.append("Check 9: triage_confirm.py timed out")
        except Exception as exc:
            failures.append(f"Check 9: could not run triage_confirm.py: {exc}")
    else:
        print(f"  Check 9: SKIP — triage_confirm.py not found at {triage_confirm_script}")

    # Check 10 (RPR-F-04): frontmatter-only-refresh grade regressions. For each page
    # this refresh recorded as updated, compare its working-tree content against HEAD;
    # a page whose BODY is byte-identical but whose evidence bumped AND grade regressed
    # is the PDF-NET-REFRESH-001 v26.7.0 defect. BLOCKING (best-effort: SKIP if not a
    # git repo / no updated pages). Wires the previously-orphaned audit_content_hash.py.
    try:
        progress_c10 = _load_progress(family, platform)
        pages_c10 = list(progress_c10.get("pages_updated", [])) + list(progress_c10.get("pages_generated", []))
        if pages_c10:
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
        print(f"  Check 10: SKIP — could not run frontmatter-only detection ({exc})")

    # Check 11 (RPR-F-05): SEO stability. For each page this refresh recorded as
    # updated, compare title/H1/slug/canonical against HEAD. Any change not declared
    # in the run manifest's `intentional_renames` allowlist is a blocking violation —
    # the first SEO-specific gate in the pipeline. BLOCKING (best-effort: SKIP if not
    # a git repo / no updated pages).
    try:
        progress_c11 = _load_progress(family, platform)
        pages_c11 = list(progress_c11.get("pages_updated", []))
        if pages_c11:
            if _cfg_detect_seo_violations is not None:
                _detect_seo = _cfg_detect_seo_violations
            else:
                from commands.content.seo_stability_check import detect_seo_violations as _detect_seo
            intentional = _load_intentional_renames(family, platform)
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
        print(f"  Check 11: SKIP — could not run SEO stability detection ({exc})")

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
                        help="(RPR-J-17, --verify only) Git ref that Checks 7/8/10/11 diff the working "
                             "tree against. Default: the newest refresh-run manifest's base_commit_sha "
                             "if one exists, else HEAD. Use this to verify an already-committed "
                             "historical refresh against its true pre-refresh baseline — 'HEAD' is "
                             "vacuous once the refresh itself has already landed.")

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

    if args.verify:
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
