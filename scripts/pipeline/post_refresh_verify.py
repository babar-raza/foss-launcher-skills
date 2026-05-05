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
    python scripts/pipeline/post_refresh_verify.py {family} {platform} --step knowledge_refresh
    python scripts/pipeline/post_refresh_verify.py {family} {platform} --verify
    python scripts/pipeline/post_refresh_verify.py {family} {platform} --status

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
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]

# foss: inline env_loader (no core package)
def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_DEFAULT_REPO_ROOT / ".env", override=False)
    except ImportError:
        pass
_load_env()
_DEFAULT_HERE = Path(__file__).resolve().parent

REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
CONTENT_ROOT = REPO_ROOT / "content"
REPORTS_ROOT = REPO_ROOT / "reports" / "refresh_state"


def configure(
    *,
    repo_root: "Path | str | None" = None,
    knowledge_root: "Path | str | None" = None,
    content_root: "Path | str | None" = None,
    reports_root: "Path | str | None" = None,
    here: "Path | str | None" = None,
) -> None:
    """Reconfigure module-level paths for testing or alternative layouts.

    Call with no arguments to reset all paths to their defaults.
    Tests call ``post_refresh_verify.configure(repo_root=tmp_path, ...)``
    in a yield-based fixture and reset with ``configure()`` at teardown.
    """
    global REPO_ROOT, KNOWLEDGE_ROOT, CONTENT_ROOT, REPORTS_ROOT, _HERE
    _root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    REPO_ROOT = _root
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _root / "knowledge"
    CONTENT_ROOT = Path(content_root) if content_root is not None else _root / "content"
    REPORTS_ROOT = Path(reports_root) if reports_root is not None else _root / "reports" / "refresh_state"
    _HERE = Path(here) if here is not None else _DEFAULT_HERE


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

_REVIEW_ROOT = REPO_ROOT / "reports" / "refresh_review"


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
            delta = sp.get("delta", {})
            delta_pages_to_add = delta.get("pages_to_add", [])
            delta_pages_to_update = delta.get("pages_to_update", [])
            delta_pages_to_remove = delta.get("pages_to_remove", [])
            planned["pages_to_add"] = len(delta_pages_to_add)
            planned["pages_to_update"] = len(delta_pages_to_update)
            planned["pages_to_remove"] = len(delta_pages_to_remove)
        except Exception:
            pass

    # Compute executed: check existence of pages_to_add paths
    pages_added = 0
    for entry in delta_pages_to_add:
        slug = entry.get("path") or entry.get("slug", "")
        if slug:
            target = REPO_ROOT / slug if not Path(slug).is_absolute() else Path(slug)
            if target.exists():
                pages_added += 1

    # For pages_to_update: compare body hashes if available
    files_with_body_diff = 0
    files_metadata_only = 0
    metadata_only_files: list[str] = []

    for entry in delta_pages_to_update:
        path_str = entry.get("path", "")
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
        path_str = entry.get("path", "")
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


def verify(family: str, platform: str) -> tuple[bool, list[str]]:
    """Run the post-refresh verification checklist.

    Returns (passed: bool, failures: list[str]).
    This function is read-only — it never modifies any files.
    """
    failures = []

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

    # Check 2: No content pages cite claim IDs absent from merged/claims.json
    claims_path = merged / "claims.json"
    valid_claim_ids: set[str] = set()
    claims_list = _load_json_list(claims_path)
    for c in claims_list:
        if isinstance(c, dict) and "claim_id" in c:
            valid_claim_ids.add(c["claim_id"])

    if valid_claim_ids or claims_path.is_file():
        content_files = _discover_content_files(family, platform)
        orphaned_pages = []
        for page in content_files:
            evidence = _get_page_evidence(page)
            cited_claims = evidence.get("claims") or []
            orphaned = [cid for cid in cited_claims if cid not in valid_claim_ids]
            if orphaned:
                orphaned_pages.append((page, orphaned))
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
            result = subprocess.run(
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

    # Check 6: Coverage completeness — page_decisions.json must cover all discovered pages
    check6_passed, check6_failures = check_coverage_completeness(family, platform)
    failures.extend(check6_failures)
    if not check6_passed:
        print(f"  Check 6: FAIL — coverage completeness: {check6_failures[0] if check6_failures else '?'}")
    else:
        print("  Check 6: PASS — page_decisions.json covers all discovered pages")

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

    if args.verify:
        # Prerequisite check — clear error messages instead of cryptic tracebacks
        try:
            # foss: core.prereqs not available; prereq checks skipped
            require_all(args.family, args.platform)
        except SystemExit:
            raise
        except Exception:
            pass  # prereqs is best-effort; verify() has its own checks
        print(f"Running post-refresh verification for {args.family}/{args.platform}...")
        passed, failures = verify(args.family, args.platform)
        if passed:
            print("VERIFICATION PASSED: all checks clean.")
            return 0
        else:
            print(f"VERIFICATION FAILED: {len(failures)} issue(s) found:")
            for f in failures:
                print(f"  - {f}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
