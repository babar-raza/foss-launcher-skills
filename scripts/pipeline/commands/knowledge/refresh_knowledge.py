"""Auto-refresh knowledge from clone cache when stale.

Compares repo HEAD in the clone cache against the repo_sha recorded in
knowledge/{family}/{platform}/merged/model.yaml.  When they differ (or
merged/ does not exist yet), runs scout.py then promote.py to rebuild.

Usage:
    python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform}
    python scripts/pipeline/commands/knowledge/refresh_knowledge.py --all
    python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform} --check-only
    python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform} --no-auto-fetch

Flags:
    --check-only        Detect staleness (fetch upstream) but do not run pipeline.
                        Returns "stale" if SHA mismatch, "current" otherwise.
                        Alias: --check (legacy)
    --no-auto-fetch     Skip update_clone() before SHA comparison.  Useful for
                        offline or CI environments where network is unavailable.
    --no-auto-clone     Disable automatic cloning from clone_url in products.json.
    --all               Refresh all products found in registry or clone cache.

Environment:
    ASPOSE_CLONE_CACHE  Override the default clone-cache location.
                        Defaults to runs/.clone_cache inside this repo.

After a successful refresh, knowledge_delta.json is written to
knowledge/{family}/{platform}/merged/ describing what changed:
  base_sha, current_sha, new_claims, removed_claims, modified_claims,
  new_apis, removed_apis.
"""
import argparse
import json
import os
import re
import shutil
import site
import subprocess
import sys
from datetime import datetime, timezone
import yaml
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
_REGISTRY_PATH = REPO_ROOT / "data" / "products.json"


def configure(
    *,
    repo_root: "Path | str | None" = None,
    knowledge_root: "Path | str | None" = None,
) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, KNOWLEDGE_ROOT, _REGISTRY_PATH
    _root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    REPO_ROOT = _root
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _root / "knowledge"
    _REGISTRY_PATH = _root / "data" / "products.json"


# Clone-cache management delegated to core.clone_cache.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # commands/knowledge/ -> commands/ -> pipeline/
from core.env_loader import load_env  # noqa: E402
load_env()
from core.clone_cache import (  # noqa: E402
    cache_root as _clone_cache_root,
    clone_path as _clone_dir_fn,
    clone_head_sha as _clone_head_sha_fn,
    ensure_clone as _ensure_clone,
    update_clone as _update_clone,
)
from core.fs import atomic_write  # noqa: E402


def _run_completeness_check(family: str, platform: str) -> None:
    """Run completeness gate after refresh. Logs result but does not block refresh."""
    check_script = Path(__file__).resolve().parent / "check_knowledge_completeness.py"
    if not check_script.exists():
        return
    try:
        result = subprocess.run(
            [sys.executable, str(check_script), family, platform],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.strip().splitlines():
            print(f"  [completeness] {line}")
        if result.returncode != 0:
            print(f"  [completeness] WARN: completeness check exited {result.returncode}")
    except Exception as exc:
        print(f"  [completeness] WARNING: could not run check: {exc}")


def _clone_dir(family: str, platform: str) -> Path:
    return _clone_dir_fn(family, platform)


def _head_sha(clone_path: Path) -> str | None:
    """Return the full HEAD sha of the cloned repo, or None."""
    if not clone_path.is_dir():
        return None
    # Derive family/platform from directory name for the delegate call.
    name = clone_path.name
    if name.startswith("aspose_"):
        parts = name.removeprefix("aspose_").split("_", 1)
        if len(parts) == 2:
            return _clone_head_sha_fn(parts[0], parts[1])
    # Fallback: run git directly
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(clone_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _model_sha(family: str, platform: str) -> str | None:
    """Return repo_sha from merged/model.yaml, falling back to scout/."""
    for layer in ("merged", "scout"):
        path = KNOWLEDGE_ROOT / family / platform / layer / "model.yaml"
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if data and data.get("repo_sha"):
                    return data["repo_sha"]
            except Exception:
                pass
    return None


def _stored_extractor_hash(family: str, platform: str) -> str | None:
    """Return extractor_hash from merged/model.yaml if present."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if data:
                return data.get("extractor_hash")
        except Exception:
            pass
    return None


def _compute_extractor_hash() -> str:
    """Compute a hash of the extractor source files.

    When extractors change (formats.py, api_surface.py, scout.py),
    knowledge should be re-extracted even if the upstream repo SHA
    hasn't changed. This hash detects extractor code changes.
    """
    import hashlib
    extraction_dir = REPO_ROOT / "scripts" / "pipeline" / "extraction"
    extractor_files = sorted([
        extraction_dir / "formats.py",
        extraction_dir / "api_surface.py",
        extraction_dir / "scout.py",
    ])
    h = hashlib.sha256()
    for fp in extractor_files:
        if fp.exists():
            h.update(fp.read_bytes())
    return h.hexdigest()[:16]


def _save_extractor_hash(family: str, platform: str, ext_hash: str) -> None:
    """Write extractor_hash to merged/model.yaml."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not path.exists():
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data["extractor_hash"] = ext_hash
        with atomic_write(path) as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    except Exception as exc:
        print(f"  {family}/{platform}: WARN — could not save extractor_hash: {exc}")


def _run(cmd: list[str], label: str) -> bool:
    print(f"  [{label}] {' '.join(cmd)}")
    env = os.environ.copy()
    # Always include scripts/pipeline so sub-scripts (promote.py, index.py) can import
    # core.* and other pipeline modules regardless of how the parent was invoked.
    pipeline_root = str(REPO_ROOT / "scripts" / "pipeline")
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p] if existing else []
    if pipeline_root not in parts:
        parts.insert(0, pipeline_root)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    user_site = site.getusersitepackages()
    if user_site and os.path.isdir(user_site) and user_site not in parts:
        env["PYTHONPATH"] = env["PYTHONPATH"] + os.pathsep + user_site
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    if result.returncode != 0:
        print(f"  [{label}] FAILED (exit {result.returncode})")
        return False
    return True


def _try_auto_clone(family: str, platform: str, clone_dir: Path) -> bool:
    """Clone the product repo into clone_dir if clone_url is available."""
    print(f"  {family}/{platform}: auto-cloning via core.clone_cache ...")
    try:
        _ensure_clone(family, platform)
        return True
    except RuntimeError as exc:
        print(f"  {family}/{platform}: auto-clone failed — {exc}")
        return False


def _set_stale_since(family: str, platform: str) -> None:
    """Set stale_since = today in merged/model.yaml if not already set.

    Also renames an existing knowledge_delta.json to knowledge_delta.prev.json
    so that downstream skills do not consume a stale delta from a prior refresh
    cycle, and the previous delta's removed_apis list is available for
    resurrection detection during the next _write_knowledge_delta() call.
    """
    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return
    try:
        data = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
        if data.get("stale_since") is None:
            data["stale_since"] = datetime.now(timezone.utc).date().isoformat()
            atomic_write(model_path, yaml.safe_dump(data, allow_unicode=True))

            # Invalidate stale delta from prior refresh cycle only when
            # freshly detecting staleness (Fix A — healing sprint 2026-04-15)
            delta_path = KNOWLEDGE_ROOT / family / platform / "merged" / "knowledge_delta.json"
            if delta_path.exists():
                prev_path = delta_path.with_suffix(".prev.json")
                try:
                    delta_path.rename(prev_path)
                    print(f"  {family}/{platform}: renamed stale knowledge_delta.json → .prev.json")
                except Exception as exc:
                    print(f"  {family}/{platform}: WARN — could not rename stale delta: {exc}")
    except Exception:
        raise  # TC-2: do not swallow; caller decides whether to halt or continue


def _clear_stale_since(family: str, platform: str) -> None:
    """Clear stale_since in merged/model.yaml (and scout/model.yaml if present).

    Called when the clone SHA already matches the knowledge model SHA — the
    knowledge is current but stale_since may have been left set by a prior
    failed refresh run.  Also called after a successful full refresh.
    """
    for layer in ("merged", "scout"):
        model_path = KNOWLEDGE_ROOT / family / platform / layer / "model.yaml"
        if model_path.exists():
            try:
                data = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
                if data.get("stale_since") is not None:
                    data["stale_since"] = None
                    data["last_refreshed"] = datetime.now(timezone.utc).date().isoformat()
                    atomic_write(model_path, yaml.safe_dump(data, allow_unicode=True))
                    print(f"  {family}/{platform}: cleared stale_since in {layer}/model.yaml")
            except Exception:
                raise  # TC-2: do not swallow; caller decides whether to halt or continue


def _write_model_field(family: str, platform: str, field: str, value: object) -> None:
    """Atomically update a single field in merged/model.yaml.

    Loads the existing YAML, sets the field, and writes back using atomic_write
    so that a crash mid-write never leaves a partially-written model.yaml.
    Silent if the file does not yet exist (the field will be written on the next
    run that creates the file).
    """
    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return
    try:
        data = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
        data[field] = value
        atomic_write(model_path, yaml.safe_dump(data, allow_unicode=True))
    except Exception as exc:
        print(f"  {family}/{platform}: WARN — could not write {field} to model.yaml: {exc}")


def _backup_merged(merged_dir: Path, bak_dir: Path) -> None:
    """Copy merged/ to merged.bak/ for delta computation."""
    if bak_dir.exists():
        shutil.rmtree(bak_dir)
    if merged_dir.is_dir():
        try:
            shutil.copytree(str(merged_dir), str(bak_dir))
        except Exception as exc:
            print(f"  WARN — could not create merged.bak: {exc}")


def _cleanup_bak(bak_dir: Path) -> None:
    """Remove merged.bak/ silently."""
    try:
        if bak_dir.exists():
            shutil.rmtree(bak_dir)
    except Exception:
        pass


def _load_knowledge_delta(family: str, platform: str) -> dict | None:
    """Load knowledge_delta.json for the given product, or None if absent/invalid.

    Used by downstream planners (refresh-product skill, batch_reference) to read
    the semantic change delta without re-running the full refresh pipeline.
    """
    delta_path = KNOWLEDGE_ROOT / family / platform / "merged" / "knowledge_delta.json"
    if not delta_path.is_file():
        return None
    try:
        data = json.loads(delta_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _has_pending_delta(family: str, platform: str) -> bool:
    """Return True if knowledge_delta.json has non-empty semantic changes.

    Allows downstream planners to detect pending API/claim changes even when
    the repo SHA has not changed (no new refresh needed) — for example, when a
    prior refresh produced a delta that downstream processing did not fully consume.
    """
    delta = _load_knowledge_delta(family, platform)
    if delta is None:
        return False
    return bool(
        delta.get("new_apis")
        or delta.get("removed_apis")
        or delta.get("modified_apis")
        or delta.get("new_claims")
        or delta.get("removed_claims")
        or delta.get("modified_claims")
        or delta.get("resurrected_apis")
    )


def _load_json_list(path: Path) -> list:
    """Load a JSON file as a list; return [] on any error."""
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _build_erc_member_set(claims: list) -> set:
    """Extract 'ClassName.MemberName' keys from ERC api-kind claims.

    Used to detect when member-doc enrichment adds new per-member descriptions
    so those classes can be included in modified_apis for batch_reference --update.
    Only considers claims with claim_id starting 'ERC-' and kind == 'api'.
    """
    pattern = re.compile(r"^`?([A-Z]\w+)\.([A-Za-z]\w*)\b")
    result: set = set()
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if not claim.get("claim_id", "").startswith("ERC-"):
            continue
        if claim.get("kind", "") != "api":
            continue
        text = (claim.get("text") or "").strip().lstrip("`")
        m = pattern.match(text)
        if m:
            result.add(f"{m.group(1)}.{m.group(2)}")
    return result


def _write_knowledge_delta(
    family: str,
    platform: str,
    bak_dir: Path,
    merged_dir: Path,
    current_sha: str,
    base_sha: str | None,
) -> None:
    """Compute and write knowledge_delta.json from merged.bak vs merged."""
    old_claims = _load_json_list(bak_dir / "claims.json")
    new_claims = _load_json_list(merged_dir / "claims.json")
    old_apis = _load_json_list(bak_dir / "api_surface.json")
    new_apis = _load_json_list(merged_dir / "api_surface.json")

    # Build claim dicts keyed by claim_id
    old_by_id = {c["claim_id"]: c for c in old_claims if isinstance(c, dict) and "claim_id" in c}
    new_by_id = {c["claim_id"]: c for c in new_claims if isinstance(c, dict) and "claim_id" in c}

    added_claims = [cid for cid in new_by_id if cid not in old_by_id]
    removed_claims = [cid for cid in old_by_id if cid not in new_by_id]
    modified_claims = [
        cid for cid in new_by_id
        if cid in old_by_id and (
            new_by_id[cid].get("text") != old_by_id[cid].get("text")
            or new_by_id[cid].get("confidence") != old_by_id[cid].get("confidence")
        )
    ]

    # Build API dicts keyed by class name
    old_api_by_name = {e["name"]: e for e in old_apis if isinstance(e, dict) and "name" in e}
    new_api_by_name = {e["name"]: e for e in new_apis if isinstance(e, dict) and "name" in e}
    old_api_names = set(old_api_by_name)
    new_api_names = set(new_api_by_name)

    added_apis = sorted(new_api_names - old_api_names)
    removed_apis = sorted(old_api_names - new_api_names)

    # Classes in both old and new but with changed members (methods or properties)
    api_surface_modified = sorted(
        name for name in new_api_names & old_api_names
        if (
            {m.get("name") for m in new_api_by_name[name].get("methods", [])}
            != {m.get("name") for m in old_api_by_name[name].get("methods", [])}
        ) or (
            {p.get("name") for p in new_api_by_name[name].get("properties", [])}
            != {p.get("name") for p in old_api_by_name[name].get("properties", [])}
        )
    )

    # Classes whose ERC member descriptions changed (e.g. after --mode member-doc run).
    # When enrich.py adds new ClassName.MemberName api-kind claims, those classes should
    # appear in modified_apis so that batch_reference --update regenerates their pages.
    old_erc_members = _build_erc_member_set(old_claims)
    new_erc_members = _build_erc_member_set(new_claims)
    erc_changed_classes = sorted({
        key.split(".")[0]
        for key in (new_erc_members ^ old_erc_members)  # symmetric difference
    })

    # Merge api_surface changes + ERC coverage changes (no duplicates)
    modified_apis = sorted(set(api_surface_modified) | set(erc_changed_classes))

    # Detect resurrected APIs: classes in new_apis that were listed as removed
    # in the previous refresh cycle's delta (Fix B — healing sprint 2026-04-15).
    resurrected_apis: list[str] = []
    prev_delta_path = merged_dir / "knowledge_delta.prev.json"
    if prev_delta_path.exists():
        try:
            prev_delta = json.loads(prev_delta_path.read_text(encoding="utf-8"))
            prev_removed = set(prev_delta.get("removed_apis", []))
            resurrected_apis = sorted(set(added_apis) & prev_removed)
            if resurrected_apis:
                print(f"  Resurrection detected: {len(resurrected_apis)} APIs re-added "
                      f"that were removed in prior refresh")
        except Exception:
            pass  # Non-fatal — resurrection detection is best-effort

    delta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_sha": base_sha or "",
        "current_sha": current_sha,
        "new_claims": added_claims,
        "removed_claims": removed_claims,
        "modified_claims": modified_claims,
        "new_apis": added_apis,
        "removed_apis": removed_apis,
        "modified_apis": modified_apis,
        "resurrected_apis": resurrected_apis,
    }

    # Atomic write via temp file + rename
    target = merged_dir / "knowledge_delta.json"
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
        print(
            f"  {family}/{platform}: knowledge_delta.json written "
            f"(+{len(added_claims)} claims, -{len(removed_claims)} claims, "
            f"~{len(modified_claims)} modified, +{len(added_apis)} apis, -{len(removed_apis)} apis)"
        )
    except Exception as exc:
        print(f"  {family}/{platform}: WARN — could not write knowledge_delta.json: {exc}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def refresh(
    family: str,
    platform: str,
    *,
    check_only: bool = False,
    auto_clone: bool = True,
    auto_fetch: bool = True,
    compulsory_enrich: bool = False,
    skip_enrich: bool = False,
) -> str:
    """Refresh knowledge for one product.

    Returns one of: "current", "refreshed", "stale", "no_clone", "failed".

    When auto_clone=True (default), attempts to clone the repo from clone_url
    in data/products.json if the clone cache directory is missing.
    When auto_fetch=True (default), calls update_clone() before comparing SHAs
    so that change detection is not permanently blind.
    """
    clone = _clone_dir(family, platform)
    head = _head_sha(clone)
    if head is None:
        if auto_clone and not check_only:
            cloned = _try_auto_clone(family, platform, clone)
            if cloned:
                head = _head_sha(clone)
        if head is None:
            print(f"  {family}/{platform}: clone cache not found at {clone}")
            return "no_clone"

    # Fetch upstream to advance local HEAD before SHA comparison.
    # This fixes the permanent blind-detection problem (shallow clone never updated).
    if auto_fetch:
        fetched_sha = _update_clone(family, platform)
        if fetched_sha is not None:
            head = fetched_sha
        # If fetch fails, continue with existing clone HEAD (degraded mode)

    current = _model_sha(family, platform)

    # TC-DAG-001: Also detect extractor code changes. When extractors are
    # modified (formats.py, api_surface.py, scout.py), re-extraction is needed
    # even if the upstream repo SHA is unchanged.
    ext_hash = _compute_extractor_hash()
    stored_ext_hash = _stored_extractor_hash(family, platform)
    extractor_changed = stored_ext_hash is not None and stored_ext_hash != ext_hash

    if current == head and not extractor_changed:
        # RH-202: Check for pending delta — downstream planners (refresh-product,
        # batch_reference) should read knowledge_delta.json directly to detect
        # unconsumed semantic changes even when no new refresh is needed.
        if _has_pending_delta(family, platform):
            delta = _load_knowledge_delta(family, platform)
            n_api = (len(delta.get("new_apis", [])) + len(delta.get("removed_apis", []))
                     + len(delta.get("modified_apis", []))
                     + len(delta.get("resurrected_apis", [])))
            n_claim = (len(delta.get("new_claims", [])) + len(delta.get("removed_claims", []))
                       + len(delta.get("modified_claims", [])))
            print(
                f"  {family}/{platform}: knowledge is current ({head[:10]}) "
                f"[pending delta: {n_api} API changes, {n_claim} claim changes — "
                f"read knowledge_delta.json for details]"
            )
        else:
            print(f"  {family}/{platform}: knowledge is current ({head[:10]})")
        # GOV-01 fix: clear any stale_since left by a prior failed refresh run
        # (SHA now matches, so the flag is stale itself).
        # SR-01: _clear_stale_since is cleanup; a failure must NOT abort the "current" return.
        try:
            _clear_stale_since(family, platform)
        except Exception as exc:
            print(f"  {family}/{platform}: WARN — could not clear stale_since (current path): {exc}")
        return "current"

    if extractor_changed and current == head:
        print(
            f"  {family}/{platform}: EXTRACTOR CHANGED — "
            f"stored={stored_ext_hash} vs current={ext_hash} "
            f"(repo SHA unchanged: {head[:10]})"
        )

    print(f"  {family}/{platform}: STALE — model={current and current[:10]} vs clone={head[:10]}")

    if check_only:
        return "stale"

    # Auto-set stale_since before running the pipeline (records when refresh started).
    _set_stale_since(family, platform)

    merged_dir = KNOWLEDGE_ROOT / family / platform / "merged"
    bak_dir = KNOWLEDGE_ROOT / family / platform / "merged.bak"

    # Backup merged/ so we can compute a semantic delta after refresh.
    _backup_merged(merged_dir, bak_dir)

    # Preserve current model SHA as previous_repo_sha for source-diff support.
    # This must happen before promote.py overwrites repo_sha with the new HEAD.
    if current:
        _write_model_field(family, platform, "previous_repo_sha", current)

    try:
        scout_out = KNOWLEDGE_ROOT / family / platform / "scout"
        ok = _run(
            [sys.executable, "scripts/pipeline/commands/knowledge/scout.py",
             family, platform, str(clone), str(scout_out)],
            "scout",
        )
        if not ok:
            return "failed"

        # Enrich: best-effort by default, hard fail with --compulsory-enrich.
        # SEAM-01: --skip-enrich bypasses LLM calls entirely (scout-only run).
        if skip_enrich:
            print(f"  {family}/{platform}: enrich skipped (--skip-enrich)")
            enrich_ok = False
        else:
            enrich_ok = _run(
                [sys.executable, "scripts/pipeline/commands/knowledge/enrich.py", family, platform],
                "enrich",
            )
        if not enrich_ok:
            # TC-11: Preserve valid prior enrichment on transient LLM failure.
            # promote.py handles staleness (SHA mismatch warning) and missing-file (0 enriched claims)
            # gracefully. Deleting valid claims on a transient failure causes permanent data loss
            # that requires a successful LLM re-run to recover.
            stale_enriched = scout_out / "enriched_claims.json"
            if stale_enriched.exists():
                print(f"  {family}/{platform}: enrich failed — preserving existing "
                      f"enriched_claims.json ({stale_enriched.stat().st_size} bytes). "
                      f"promote.py will merge existing claims with staleness warning.")
            else:
                print(f"  {family}/{platform}: enrich failed — no prior enriched_claims.json to preserve")
            if compulsory_enrich:
                print(f"  {family}/{platform}: ENRICH FAILED and --compulsory-enrich is set — aborting")
                return "failed"

        ok = _run(
            [sys.executable, "scripts/pipeline/commands/knowledge/promote.py", family, platform],
            "promote",
        )
        if not ok:
            return "failed"

        # Write knowledge_delta.json only after successful promote (no partial delta).
        _write_knowledge_delta(family, platform, bak_dir, merged_dir, head, current)

        # Record enrichment quality in model.yaml so downstream consumers can detect
        # scout-only (degraded) refreshes vs full refreshes (TC-4).
        _write_model_field(
            family, platform, "enrichment_status", "full" if enrich_ok else "scout-only"
        )

        ok = _run(
            [sys.executable, "scripts/pipeline/commands/knowledge/index.py", family, platform],
            "index",
        )
        if not ok:
            print(f"  {family}/{platform}: WARN — index.py failed; knowledge is usable but index is stale")
            # index failure is non-fatal: knowledge model is complete; index can be re-run manually

        # Write pipeline_run.json artifact confirming all 4 steps ran
        if merged_dir.is_dir():
            pipeline_run = {
                "ran_at": datetime.now(timezone.utc).isoformat(),
                "steps": ["scout", "enrich", "promote", "index"],
                "enrichment_status": "success" if enrich_ok else "failed",
                "index_succeeded": ok,
                "repo_sha": head,
            }
            try:
                atomic_write(
                    merged_dir / "pipeline_run.json",
                    json.dumps(pipeline_run, indent=2),
                )
            except OSError as exc:
                print(f"  {family}/{platform}: WARN — could not write pipeline_run.json: {exc}")

        # Auto-clear stale_since after successful refresh.
        # SR-01: knowledge is fully written; a clear failure must NOT abort "refreshed" return.
        try:
            _clear_stale_since(family, platform)
        except Exception as exc:
            print(f"  {family}/{platform}: WARN — could not clear stale_since after refresh: {exc}")

        _run_completeness_check(family, platform)

        # Auto-refresh evidence after knowledge update to prevent WARN drift.
        # Non-fatal: evidence can always be re-attached manually.
        _run(
            [sys.executable, "scripts/pipeline/commands/healing/attach_evidence.py",
             family, platform],
            "attach-evidence",
        )

        # TC-DAG-001: Save current extractor hash so future runs detect changes.
        try:
            _save_extractor_hash(family, platform, _compute_extractor_hash())
        except Exception as exc:
            print(f"  {family}/{platform}: WARN — could not save extractor_hash: {exc}")

        print(f"  {family}/{platform}: refreshed to {head[:10]}")
        return "refreshed"
    finally:
        # Always clean up merged.bak/ regardless of success or failure.
        _cleanup_bak(bak_dir)


def discover_products() -> list[tuple[str, str]]:
    """Return (family, platform) pairs from registry, clone cache, or knowledge dirs.

    Priority order:
    1. data/products.json registry (active=true entries) — preferred source
    2. Clone-cache directory scan — fallback for cloned repos not yet in registry
    3. Returns empty list only when all sources are unavailable
    """
    seen: set[tuple[str, str]] = set()
    products: list[tuple[str, str]] = []

    # Source 1: product registry
    if _REGISTRY_PATH.is_file():
        try:
            registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
            for entry in registry:
                if entry.get("active", True):
                    pair = (entry["family"], entry["platform"])
                    if pair not in seen:
                        seen.add(pair)
                        products.append(pair)
        except (json.JSONDecodeError, KeyError, OSError):
            pass  # fall through to clone-cache scan

    # Source 2: clone-cache directory scan (adds any cloned repos not in registry)
    cache = _clone_cache_root()
    if cache.is_dir():
        for d in sorted(cache.iterdir()):
            if d.is_dir() and d.name.startswith("aspose_"):
                parts = d.name.removeprefix("aspose_").split("_", 1)
                if len(parts) == 2:
                    pair = (parts[0], parts[1])
                    if pair not in seen:
                        seen.add(pair)
                        products.append(pair)

    return products


def main():
    parser = argparse.ArgumentParser(
        description="Auto-refresh knowledge from clone cache")
    parser.add_argument("--all", action="store_true",
                        help="Refresh all products found in clone cache")
    parser.add_argument("--check", action="store_true",
                        help="Check only (legacy alias for --check-only)")
    parser.add_argument("--check-only", action="store_true", dest="check_only",
                        help="Detect staleness but do not run pipeline; exits 1 if stale")
    parser.add_argument("--no-auto-clone", action="store_true",
                        help="Disable automatic cloning from clone_url in products.json")
    parser.add_argument("--no-auto-fetch", action="store_true",
                        help="Skip upstream fetch before SHA comparison (offline/CI mode)")
    parser.add_argument("--compulsory-enrich", action="store_true",
                        help="Require enrichment to succeed; abort pipeline on enrich failure")
    parser.add_argument("--skip-enrich", action="store_true", dest="skip_enrich",
                        help="Skip LLM enrichment entirely; writes enrichment_status: scout-only")
    parser.add_argument("family", nargs="?", help="Product family (e.g. 3d)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. python)")
    args = parser.parse_args()

    # --check is a legacy alias for --check-only
    check_only = args.check_only or args.check
    auto_fetch = not args.no_auto_fetch

    if args.all:
        products = discover_products()
        if not products:
            print("No products found in registry or clone cache")
            sys.exit(1)
        results = {}
        for family, platform in products:
            results[(family, platform)] = refresh(
                family, platform,
                check_only=check_only,
                auto_clone=not args.no_auto_clone,
                auto_fetch=auto_fetch,
                compulsory_enrich=args.compulsory_enrich,
                skip_enrich=args.skip_enrich,
            )
        stale = [k for k, v in results.items() if v in ("stale", "failed")]
        no_clone = [k for k, v in results.items() if v == "no_clone"]
        if no_clone:
            print(f"\n{len(no_clone)} product(s) have no local clone — "
                  f"clone repos to runs/.clone_cache/ or run repo-scout in pip-install mode")
        if stale:
            print(f"\n{len(stale)} product(s) stale or failed")
            sys.exit(1)
        current = len(products) - len(stale) - len(no_clone)
        print(f"\n{current} current, {len(no_clone)} no-clone, {len(stale)} stale")
        sys.exit(0)

    if not args.family or not args.platform:
        parser.error("Provide family and platform, or use --all")

    result = refresh(
        args.family, args.platform,
        check_only=check_only,
        auto_clone=not args.no_auto_clone,
        auto_fetch=auto_fetch,
        compulsory_enrich=args.compulsory_enrich,
        skip_enrich=args.skip_enrich,
    )
    if result in ("stale", "failed", "no_clone"):
        sys.exit(1)


if __name__ == "__main__":
    main()
