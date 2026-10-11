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
    --pin-sha SHA       After clone/fetch, detach-checkout the clone at exactly SHA and
                        refresh against it (not origin/HEAD). Exits non-zero ("failed")
                        if the clone HEAD cannot be made equal to SHA.
    --strict-fetch      A failed upstream fetch is a hard failure ("failed") instead of
                        degrading to the stale clone HEAD.
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

# FRESH-001 (2026-08-14): this module previously had no sys.path bootstrap of its
# own (relies entirely on being invoked with PYTHONPATH=scripts/pipeline set), which
# is enough for scripts/pipeline/{core,commands,...} subpackage imports but NOT for
# bare imports of lib/ modules like knowledge_regen_lock (used in refresh() below) --
# scripts/pipeline/lib itself is never on sys.path from PYTHONPATH alone. Unconditional
# (not test-only) so this works identically under pytest (where conftest.py already
# adds lib/, making this a harmless no-op) and in real CLI/subprocess invocation.
_LIB_DIR = _DEFAULT_REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


_UNSET = object()
_cfg_hooks: dict = {}


def configure_hooks(*, run_fn=_UNSET, head_sha_fn=_UNSET, checkout_pinned_fn=_UNSET,
                    completeness_check_fn=_UNSET) -> None:
    """Test seam (configure() pattern) for the refresh chain's side-effecting steps:
    the subprocess runner, HEAD lookup, pinned checkout and completeness check.
    Passing a callable installs it; ``None`` removes that hook; calling with NO
    arguments resets every hook (autouse-fixture teardown).  Hooks are resolved at
    call time, so they compose with module-attribute patches used by older tests."""
    given = {"run": run_fn, "head_sha": head_sha_fn, "checkout_pinned": checkout_pinned_fn,
             "completeness_check": completeness_check_fn}
    if all(v is _UNSET for v in given.values()):
        _cfg_hooks.clear()
        return
    for name, fn in given.items():
        if fn is _UNSET:
            continue
        if fn is None:
            _cfg_hooks.pop(name, None)
        else:
            _cfg_hooks[name] = fn


def _hooked(name: str, default):
    return _cfg_hooks.get(name) or default


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
    checkout_pinned as _checkout_pinned,
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


def _snippet_budget_blocks(path: Path) -> dict:
    """{platform: snippet_budget block} from platform_capabilities.yaml ({} if absent)."""
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    platforms = doc.get("platforms") if isinstance(doc, dict) else None
    if not isinstance(platforms, dict):
        return {}
    return {
        str(name): row["snippet_budget"]
        for name, row in platforms.items()
        if isinstance(row, dict) and isinstance(row.get("snippet_budget"), dict)
    }


def _compute_extractor_hash() -> str:
    """Compute a hash of the extractor source files.

    When extraction or promotion logic changes, knowledge should be rebuilt
    even if the upstream repo SHA hasn't changed. Promotion changes can alter
    merged claims and deltas without changing scout output.

    D-8(d) (MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH TC-MT040-48, shared with
    MT039 TC-MT039-11): the original 4-file list (formats.py, api_surface.py,
    scout.py, promote.py) silently missed every other module in
    scripts/pipeline/extraction/ -- tree_helpers.py (per-language declaration
    maps), snippets.py (snippet selection), package_manifest.py,
    package_root.py, claims.py, validate_scout_output.py, and outputs.py all
    directly change extraction behavior but never bumped this hash, so a
    change to any of them left every product's "unchanged" no-op signal
    silently wrong. Fixed generically (not per-file) by hashing every ``.py``
    file under ``extraction/`` in sorted order, plus ``promote.py`` (outside
    that directory but still part of the extraction contract). This makes a
    new file added to ``extraction/`` automatically covered without another
    hand-maintained list -- the same "declared once, consumed everywhere"
    principle used elsewhere in this hardening pass (see D-1 in
    reports/sprint/pdf-typescript-hardening/preflight/design.md).

    MT074 R3-5 (deliberate scope widening): the canonical JSON of the per-platform
    ``snippet_budget`` blocks of config/platform_capabilities.yaml is also hashed --
    they drive snippet extraction but are not ``.py`` files under extraction/.

    One-time cost: this widens what counts as "changed" for every already-
    scouted product, so the very next ``refresh_knowledge.py`` run for a
    fleet product may report ``extractor_changed: true`` even with no
    behavior-relevant edit in its own history since promotion (e.g. a
    docstring-only change to a file it never previously watched). This is the
    correct, honest signal, not a regression -- recorded in
    docs/workflows/change-trigger-matrix.md as a fleet-wide one-time
    "extractor_hash changed" event tied to this commit.
    """
    import hashlib
    extraction_dir = REPO_ROOT / "scripts" / "pipeline" / "extraction"
    extractor_files = sorted(extraction_dir.glob("*.py")) + [
        REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "promote.py",
    ]
    h = hashlib.sha256()
    for fp in extractor_files:
        if fp.exists():
            # MT074 B13d: hash LF-normalised bytes so a CRLF checkout
            # (core.autocrlf=true) and an LF checkout of the SAME source give the
            # same hash -- raw bytes made "extractor changed" a per-machine artefact.
            # Scope is unchanged (same files, same order).
            h.update(fp.read_bytes().replace(b"\r\n", b"\n"))
    # MT074 R3-5: the per-platform `snippet_budget` blocks of
    # config/platform_capabilities.yaml DRIVE extraction (extraction/snippets.py reads
    # them) but live outside extraction/*.py, so a budget change used to leave every
    # product's "extractor unchanged" signal silently wrong.  Their canonical JSON
    # (sorted keys, parsed -- hence line-ending independent) is folded in.  This
    # DELIBERATELY WIDENS the hash scope beyond .py files: one more fleet-wide
    # one-time `extractor_changed` event, the correct and honest signal.  A repo
    # without the YAML (or without any block) hashes exactly as before.
    blocks = _snippet_budget_blocks(REPO_ROOT / "scripts" / "pipeline" / "config"
                                    / "platform_capabilities.yaml")
    if blocks:
        h.update(b"\0snippet_budget\0")
        h.update(json.dumps(blocks, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, default=str).encode("utf-8"))
    return h.hexdigest()[:16]


def _save_extractor_hash(family: str, platform: str, ext_hash: str) -> None:
    """Write extractor_hash to merged/model.yaml."""
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not path.exists():
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data["extractor_hash"] = ext_hash
        atomic_write(path, yaml.safe_dump(data, default_flow_style=False, allow_unicode=True))
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
                    # G13 (2026-08-22, mission-plan-the-end-to-end-vast-hejlsberg.md
                    # Task 20): Path.rename() raises FileExistsError on Windows when
                    # prev_path already exists -- true from the SECOND stale-detection
                    # cycle onward, since nothing else ever deletes .prev.json. The
                    # prior broad except swallowed this into a WARN and left the
                    # rotation silently stuck at whatever .prev.json held from the
                    # first cycle, freezing resurrection detection's reference point.
                    # Path.replace() uses os.replace(), an atomic overwrite on both
                    # Windows and POSIX -- the correct rotation primitive here.
                    delta_path.replace(prev_path)
                    print(f"  {family}/{platform}: rotated knowledge_delta.json → .prev.json")
                except Exception as exc:
                    print(f"  {family}/{platform}: WARN — could not rotate stale delta: {exc}")
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


def _parse_install_md(install_path: Path) -> dict[str, str]:
    """Extract identity fields from an install.md file.

    Returns a dict with keys: install_block (raw code block text), package_name,
    version, group_id, artifact_id (Java only).  All values default to "".
    """
    result: dict[str, str] = {
        "install_block": "",
        "package_name": "",
        "version": "",
        "group_id": "",
        "artifact_id": "",
    }
    if not install_path.is_file():
        return result

    text = install_path.read_text(encoding="utf-8", errors="replace")

    # Extract the first fenced code block (``` ... ```)
    code_block_match = re.search(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
    if not code_block_match:
        return result

    block = code_block_match.group(1).strip()
    result["install_block"] = block

    # Python: pip install {name}>={version} or pip install {name}=={version}
    m = re.match(r"pip install\s+([A-Za-z0-9._-]+)(?:[>=<]+([A-Za-z0-9._-]+))?", block)
    if m:
        result["package_name"] = m.group(1)
        result["version"] = m.group(2) or ""
        return result

    # .NET: dotnet add package {name} --version {version}
    m = re.match(r"dotnet add package\s+([A-Za-z0-9._-]+)(?:\s+--version\s+([A-Za-z0-9._-]+))?",
                 block)
    if m:
        result["package_name"] = m.group(1)
        result["version"] = m.group(2) or ""
        return result

    # Java Maven XML: extract groupId, artifactId, version
    gid = re.search(r"<groupId>([^<]+)</groupId>", block)
    aid = re.search(r"<artifactId>([^<]+)</artifactId>", block)
    ver = re.search(r"<version>([^<]+)</version>", block)
    if gid or aid:
        result["group_id"] = gid.group(1).strip() if gid else ""
        result["artifact_id"] = aid.group(1).strip() if aid else ""
        result["version"] = ver.group(1).strip() if ver else ""
        result["package_name"] = result["artifact_id"]
        return result

    # JavaScript/TypeScript: npm install {name}@{version}
    m = re.match(r"npm install\s+([A-Za-z0-9@._/-]+)(?:@([A-Za-z0-9._-]+))?", block)
    if m:
        result["package_name"] = m.group(1)
        result["version"] = m.group(2) or ""
        return result

    # Go: go get {module}
    m = re.match(r"go get\s+(\S+)", block)
    if m:
        result["package_name"] = m.group(1)
        return result

    return result


def _write_manifest_delta(
    family: str,
    platform: str,
    bak_dir: Path,
    merged_dir: Path,
    current_sha: str,
    base_sha: str | None,
) -> None:
    """Compute and write manifest_delta.json comparing merged.bak/install.md vs merged/install.md.

    Detects: COORDINATE_CHANGE (group_id/artifact_id changed), INSTALL_CMD_CHANGED
    (package name changed), VERSION_BUMP (version only changed), INSTALL_CMD_ADDED
    (block absent in bak, present in merged).

    The delta is written to merged/manifest_delta.json and persists after bak cleanup.
    Must be called BEFORE _cleanup_bak().
    """
    bak_install = bak_dir / "install.md"
    new_install = merged_dir / "install.md"

    old = _parse_install_md(bak_install)
    new = _parse_install_md(new_install)

    events: list[dict] = []

    no_old_block = not old["install_block"]
    no_new_block = not new["install_block"]

    if no_new_block:
        # No install info in new — nothing to report; install block may have been removed
        # (handled separately) or product has no install command yet.
        pass
    elif no_old_block:
        # Install block appeared for the first time
        events.append({
            "change_type": "INSTALL_CMD_ADDED",
            "old": None,
            "new": new["install_block"],
            "package_name_new": new["package_name"],
            "version_new": new["version"],
        })
    else:
        # Both have blocks — compare field by field
        old_gid, new_gid = old["group_id"], new["group_id"]
        old_aid, new_aid = old["artifact_id"], new["artifact_id"]
        old_pkg, new_pkg = old["package_name"].lower(), new["package_name"].lower()
        old_ver, new_ver = old["version"], new["version"]

        if (old_gid and new_gid and old_gid != new_gid) or (
            old_aid and new_aid and old_aid != new_aid
        ):
            events.append({
                "change_type": "COORDINATE_CHANGE",
                "field": "group_id" if old_gid != new_gid else "artifact_id",
                "old_group_id": old_gid,
                "new_group_id": new_gid,
                "old_artifact_id": old_aid,
                "new_artifact_id": new_aid,
                "old_version": old_ver,
                "new_version": new_ver,
                "scope": "all_code_blocks",
            })
        elif old_pkg and new_pkg and old_pkg != new_pkg:
            events.append({
                "change_type": "INSTALL_CMD_CHANGED",
                "old_package_name": old["package_name"],
                "new_package_name": new["package_name"],
                "old_version": old_ver,
                "new_version": new_ver,
                "old_install_block": old["install_block"],
                "new_install_block": new["install_block"],
            })
        elif old_ver and new_ver and old_ver != new_ver:
            events.append({
                "change_type": "VERSION_BUMP",
                "package_name": new["package_name"],
                "old_version": old_ver,
                "new_version": new_ver,
                "old_install_block": old["install_block"],
                "new_install_block": new["install_block"],
            })

    # PKGINSTALL-BLOCK-UPDATER-CALLSITE (2026-09-10): bucket by change_type into
    # 3 lists instead of one flat `events` list. Real, pre-existing schema
    # mismatch found while wiring this file's only 2 real consumers a call
    # site: both scripts/pipeline/commands/content/install_block_updater.py's
    # run_update() and coordinate_migrator.py's run_migration() read
    # delta.get("install_cmd_changes"/"coordinate_changes"/"version_changes",
    # []) -- confirmed by direct read of both modules AND their own test
    # fixtures, which already use this 3-list shape. This function had never
    # written that shape (a flat `events` list instead), so neither consumer
    # could ever see a real event regardless of content -- both modules were
    # silently, structurally orphaned since whichever one was built first,
    # not just "never given a call site." No other consumer reads the old
    # `events` key (confirmed via repo-wide grep before this change).
    install_cmd_changes = [e for e in events if e["change_type"] in ("INSTALL_CMD_CHANGED", "INSTALL_CMD_ADDED")]
    coordinate_changes = [e for e in events if e["change_type"] == "COORDINATE_CHANGE"]
    version_changes = [e for e in events if e["change_type"] == "VERSION_BUMP"]

    delta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_sha": base_sha or "",
        "current_sha": current_sha,
        "install_cmd_changes": install_cmd_changes,
        "coordinate_changes": coordinate_changes,
        "version_changes": version_changes,
    }

    target = merged_dir / "manifest_delta.json"
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
        if events:
            event_summary = ", ".join(e["change_type"] for e in events)
            print(f"  {family}/{platform}: manifest_delta.json written ({event_summary})")
        else:
            print(f"  {family}/{platform}: manifest_delta.json written (no coordinate/install changes)")
    except Exception as exc:
        print(f"  {family}/{platform}: WARN — could not write manifest_delta.json: {exc}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _maybe_run_block_updater_dry_run(family: str, platform: str, merged_dir: Path) -> "dict | None":
    """PKGINSTALL-BLOCK-UPDATER-CALLSITE (2026-09-10, governing plan section
    R.3.8): give install_block_updater.py -- correct logic, zero real callers
    anywhere in the codebase before this -- a real, dry-run-only call site.

    Never fires --execute. The actual content edit stays a distinct, explicit,
    human/agent-reviewed action (skills/refresh-product.md), consistent with
    this repo's S-73 per-file-review mandate -- this function only computes
    and records what WOULD change.

    Double-fire safety: this is called exactly once per _run_refresh_chain()
    invocation, which itself only ever runs under refresh()'s per-(family,
    platform) acquire_regen_lock() -- confirmed by reading that lock's call
    site above -- so two concurrent sessions refreshing the SAME product can
    never both be inside this function at once (the second blocks on the lock
    or gets RegenLockTimeout). Different products run fully independently
    (separate manifest_delta.json files, separate reconciliation-store rows),
    so no cross-product interference is possible either.

    Returns None (and invokes nothing) when manifest_delta.json is missing,
    unreadable, or carries no install_cmd_changes/coordinate_changes/
    version_changes event -- run_update() itself is never called in that
    case, not merely told to no-op internally, per this taskcard's own
    acceptance check.
    """
    delta_path = merged_dir / "manifest_delta.json"
    if not delta_path.is_file():
        return None
    try:
        delta = json.loads(delta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    events = (
        delta.get("install_cmd_changes", [])
        + delta.get("coordinate_changes", [])
        + delta.get("version_changes", [])
    )
    if not events:
        return None

    try:
        from commands.content.install_block_updater import run_update
        summary = run_update(family, platform, dry_run=True, manifest_delta_path=delta_path)
    except Exception as exc:
        print(f"  {family}/{platform}: WARN — install_block_updater dry-run failed: {exc}")
        return None

    print(
        f"  {family}/{platform}: install_block_updater dry-run — "
        f"{summary['files_updated']} file(s) would update, {summary['files_noop']} already current, "
        f"{len(summary['human_review_required'])} need human review"
    )

    # Fold into the reconciliation store (R.3.1) -- one aggregate row per
    # dry-run event, not one row per affected content page (a full per-page
    # representation classification for this event belongs to
    # PKGINSTALL-DEFECT-SWEEP-REDESIGN, not this call site). The full summary
    # (including per-file results and human_review_required) is embedded
    # verbatim as an extra field -- validate_reconciliation_record() only
    # requires certain fields be present, it does not reject additional ones.
    try:
        from reconciliation_store import ReconciliationStore
        # repo_root=REPO_ROOT (this module's own configure()-settable global,
        # not the store's default) so tests that call this module's own
        # configure(repo_root=tmp_path) get a fully isolated store for free,
        # with no separate reconciliation_store wiring needed.
        ReconciliationStore(repo_root=REPO_ROOT).append_batch([{
            "path": f"knowledge/{family}/{platform}/merged/install.md",
            "family": family,
            "platform": platform,
            "site": "knowledge",
            "locale": "en",
            "representation": "literal",
            "collision_classification": None,
            "sweep_run_id": f"refresh-knowledge-{family}-{platform}-{summary['generated_at']}",
            "recorded_at": summary["generated_at"],
            "block_updater_dry_run_summary": summary,
        }])
    except Exception as exc:
        print(f"  {family}/{platform}: WARN — could not record block-updater summary in reconciliation store: {exc}")

    return summary


# Directions of a real formats.json entry that count as documented FORMAT SUPPORT, mapped
# to the set of capabilities they grant. Every other direction ("detect", "enum_only", and
# anything an extractor invents later) is NOISE: it is reported in the delta's ``noise``
# list but never counted as added/removed support.
_FORMAT_SUPPORT_DIRECTIONS: "dict[str, frozenset]" = {
    "import": frozenset({"import"}),
    "export": frozenset({"export"}),
    "both": frozenset({"import", "export"}),
}
# Pre-TC-02 formats.json entries carried a ``support`` label instead of ``direction``.
_LEGACY_SUPPORT_TO_DIRECTION = {"both": "both", "import-only": "import", "export-only": "export"}


def _format_support_label(directions: "frozenset | set") -> str:
    """Map a capability set to the label vocabulary format_table_handler.py consumes."""
    if {"import", "export"} <= set(directions):
        return "both"
    if "import" in directions:
        return "import-only"
    if "export" in directions:
        return "export-only"
    return ""


def _index_formats(entries: list) -> "tuple[dict, dict]":
    """Index formats.json entries into (supported, noise).

    Real entry shape: ``{format, enum, value, file, line, direction, functional}``
    (legacy ``{name, support}`` entries are accepted too). Entries are keyed by
    ``(format.strip().casefold(), direction)``; several entries sharing a key (e.g. the
    same format listed once with an empty ``enum`` and once under its real enum) are
    de-duplicated, preferring an entry with a non-empty ``enum``, then the lowest
    ``(file, line)``. A key is SUPPORT only when its direction grants import/export
    AND at least one of its entries is not explicitly ``functional: false``; anything
    else lands in ``noise`` keyed by ``(format_key, direction, reason)``.

    Returns ``(supported, noise)``: ``supported`` maps format_key -> {name, directions,
    ext, description}; ``noise`` maps (format_key, direction, reason) -> {name,
    direction, reason}.
    """
    groups: "dict[tuple[str, str], list[dict]]" = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("format") or entry.get("name") or "").strip()
        direction = entry.get("direction")
        if not direction:
            direction = _LEGACY_SUPPORT_TO_DIRECTION.get(str(entry.get("support", "")), "")
        direction = str(direction or "").strip().casefold()
        groups.setdefault((name.casefold(), direction), []).append(entry)

    def _preference(e: dict) -> tuple:
        # MT074 R1-8: `line` is untrusted extractor output; a non-numeric value
        # ("12a", "", None, a list) must degrade to 0, never abort the delta writer
        # (and with it the whole refresh chain).
        try:
            line = int(e.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        return (0 if e.get("enum") else 1, str(e.get("file", "")), line)

    supported: dict = {}
    noise: dict = {}
    for (fkey, direction), members in groups.items():
        functional = [m for m in members if m.get("functional") is not False]
        pool = functional or members
        best = min(pool, key=_preference)
        name = str(best.get("format") or best.get("name") or "").strip()
        caps = _FORMAT_SUPPORT_DIRECTIONS.get(direction)
        if not fkey:
            reason = "empty_format_name"
        elif caps is None:
            reason = "non_support_direction"
        elif not functional:
            reason = "non_functional"
        else:
            reason = ""
        if reason:
            noise[(fkey, direction, reason)] = {"name": name, "direction": direction, "reason": reason}
            continue
        slot = supported.setdefault(fkey, {
            "name": name, "directions": set(),
            "ext": str(best.get("ext") or ""), "description": str(best.get("description") or ""),
        })
        slot["directions"] |= caps
    return supported, noise


def _compute_format_delta(old_entries: list, new_entries: list) -> dict:
    """Diff two formats.json snapshots (real schema) into added/removed/direction-changed + noise.

    CONTRACT:
      input   old_entries/new_entries: lists of formats.json entries (see _index_formats).
      output  {"formats_added": [{name, ext, support, description, directions}],
               "formats_removed": [{name, ext, support, directions}],
               "formats_direction_changed": [{name, old_support, new_support}],
               "noise": [{name, direction, reason, change: "added"|"removed"}]}
              ``name`` is the format string itself (compatible with format_table_handler.py);
              ``support`` is "both" | "import-only" | "export-only".
      rules   * identity = format string, casefolded/stripped -- no per-format alias logic.
              * a format is added/removed when it gains/loses ALL import/export support;
                a changed capability set is direction_changed.
              * detect / enum_only / non-functional / unknown directions are never support:
                they appear only in ``noise`` (changes in them are reported, never dropped).
    """
    old_sup, old_noise = _index_formats(old_entries)
    new_sup, new_noise = _index_formats(new_entries)

    added = []
    for key in sorted(set(new_sup) - set(old_sup)):
        f = new_sup[key]
        added.append({
            "name": f["name"], "ext": f["ext"], "support": _format_support_label(f["directions"]),
            "description": f["description"], "directions": sorted(f["directions"]),
        })
    removed = []
    for key in sorted(set(old_sup) - set(new_sup)):
        f = old_sup[key]
        removed.append({
            "name": f["name"], "ext": f["ext"], "support": _format_support_label(f["directions"]),
            "directions": sorted(f["directions"]),
        })
    direction_changed = []
    for key in sorted(set(old_sup) & set(new_sup)):
        if old_sup[key]["directions"] != new_sup[key]["directions"]:
            direction_changed.append({
                "name": new_sup[key]["name"],
                "old_support": _format_support_label(old_sup[key]["directions"]),
                "new_support": _format_support_label(new_sup[key]["directions"]),
            })
    noise = []
    for nkey in sorted(set(new_noise) - set(old_noise)):
        noise.append({**new_noise[nkey], "change": "added"})
    for nkey in sorted(set(old_noise) - set(new_noise)):
        noise.append({**old_noise[nkey], "change": "removed"})
    return {
        "formats_added": added,
        "formats_removed": removed,
        "formats_direction_changed": direction_changed,
        "noise": noise,
    }


def _write_format_delta(
    family: str,
    platform: str,
    bak_dir: Path,
    merged_dir: Path,
    current_sha: str,
    base_sha: str | None,
) -> None:
    """Compute and write format_delta.json comparing merged.bak/formats.json vs merged/formats.json.

    Detects: FORMAT_ADDED, FORMAT_REMOVED, FORMAT_DIRECTION_CHANGED (see _compute_format_delta
    for the real-schema keying and the ``noise`` list, MT074 B2).
    Written to merged/format_delta.json; persists after bak cleanup.
    Must be called BEFORE _cleanup_bak().
    """
    def _load_formats(path: Path) -> list:
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    computed = _compute_format_delta(
        _load_formats(bak_dir / "formats.json"), _load_formats(merged_dir / "formats.json"),
    )
    added = computed["formats_added"]
    removed = computed["formats_removed"]
    direction_changed = computed["formats_direction_changed"]

    delta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_sha": base_sha or "",
        "current_sha": current_sha,
        **computed,
    }

    target = merged_dir / "format_delta.json"
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
        print(
            f"  {family}/{platform}: format_delta.json written "
            f"(+{len(added)} added, -{len(removed)} removed, ~{len(direction_changed)} direction_changed, "
            f"{len(computed['noise'])} noise)"
        )
    except Exception as exc:
        print(f"  {family}/{platform}: WARN — could not write format_delta.json: {exc}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)


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


def _deprecated_member_keys(api_entry: dict) -> set:
    """Return 'ClassName' (for the class itself) and 'ClassName.MemberName'
    keys for every element of *api_entry* carrying deprecated: True.

    Task 15 (§9.10, closes G9): api_surface.py now threads a real deprecated
    signal through class/method/property dicts (Java @Deprecated, C#
    [Obsolete], and either language's own doc-comment-tag equivalent) --
    this reads that signal to detect newly-deprecated transitions between two
    knowledge-model snapshots. Missing keys (older, pre-Task-15 knowledge
    models) default to False/absent, never fabricated as deprecated.
    """
    name = api_entry.get("name", "")
    keys: set = set()
    if api_entry.get("deprecated"):
        keys.add(name)
    for member in api_entry.get("methods", []):
        if member.get("deprecated") and member.get("name"):
            keys.add(f"{name}.{member['name']}")
    for member in api_entry.get("properties", []):
        if member.get("deprecated") and member.get("name"):
            keys.add(f"{name}.{member['name']}")
    return keys


def _api_namespace(entry: dict) -> str:
    """The namespace/package qualifier of an api_surface entry, or "" when it has none.

    First non-empty of ``canonical_namespace`` (set by the per-language extractors), ``class_package``,
    ``namespace``, ``package``. ``module_key``/``module_label`` are deliberately NOT used:
    they are documentation groupings, not language identity.
    """
    for field in ("canonical_namespace", "class_package", "namespace", "package"):
        value = entry.get(field)
        if value:
            return str(value)
    return ""


def _api_qualified_name(entry: dict) -> str:
    """Stable qualified identity of an api_surface entry: ``<qualifier>::<name>``.

    The qualifier is the entry's namespace/package (``_api_namespace``); entries that carry
    none (older knowledge models, some extractors) fall back to their source ``file``;
    with neither, the identity is the bare simple name. ``line`` is never part of identity
    (it churns on every edit).
    """
    name = str(entry.get("name", ""))
    qualifier = _api_namespace(entry) or str(entry.get("file") or "")
    return f"{qualifier}::{name}" if qualifier else name


def _member_names(entry: dict, field: str) -> set:
    """Names of an entry's ``field`` members (dict members use ``name``; bare strings pass through)."""
    out = set()
    for m in entry.get(field, []) or []:
        if isinstance(m, dict):
            if m.get("name") is not None:
                out.add(m.get("name"))
        elif m is not None:
            out.add(str(m))
    return out


def _pair_same_name_entities(olds: list, news: list) -> "tuple[list, list, list]":
    """Match old/new entities that share a simple name; returns (pairs, removed, added).

    Passes, each greedy and order-stable: (1) same non-empty namespace; (2) neither side has a
    namespace and the file matches; (3) one side lacks a namespace (schema upgrade) and the file
    matches; (4) one side lacks a namespace. Two entities that BOTH carry a namespace and
    differ never pair -- that is a real new/removed type (or a relocation), not a no-op.
    """
    olds, news, pairs = list(olds), list(news), []

    def run(pred) -> None:
        for o in list(olds):
            for n in news:
                if pred(o, n):
                    pairs.append((o, n))
                    olds.remove(o)
                    news.remove(n)
                    break

    run(lambda o, n: bool(_api_namespace(o)) and _api_namespace(o) == _api_namespace(n))
    run(lambda o, n: not _api_namespace(o) and not _api_namespace(n)
        and str(o.get("file") or "") == str(n.get("file") or ""))
    run(lambda o, n: (not _api_namespace(o) or not _api_namespace(n))
        and bool(o.get("file")) and o.get("file") == n.get("file"))
    run(lambda o, n: not _api_namespace(o) or not _api_namespace(n))
    return pairs, olds, news


def _extractor_change_state(bak_dir: Path) -> str:
    """Did the extractor change between the previous bundle and now?  "true" | "false" | "unknown".

    Compares ``extractor_hash`` recorded in ``<bak_dir>/model.yaml`` (the previous bundle) with
    ``_compute_extractor_hash()``. A missing/unreadable previous hash is "unknown" -- never
    assumed equal, because an api_surface diff across two extractor versions can show a
    member-list drop that is extractor noise rather than an upstream removal.
    """
    path = bak_dir / "model.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    except Exception:
        return "unknown"
    previous = data.get("extractor_hash") if isinstance(data, dict) else None
    if not previous:
        return "unknown"
    try:
        return "false" if str(previous) == _compute_extractor_hash() else "true"
    except Exception:
        return "unknown"


def _diff_api_surface(old_apis: list, new_apis: list, *, extractor_changed: str = "unknown") -> dict:
    """Diff two api_surface.json snapshots on QUALIFIED identity (MT074 B2).

    CONTRACT:
      input   old_apis/new_apis: lists of api_surface entries (``name`` required; optional
              ``canonical_namespace``/``class_package``/``namespace``/``package``, ``file``,
              ``methods``, ``properties``, ``enum_members``).
      identity ``_api_qualified_name`` (``<namespace-or-file>::<name>``); same-simple-name
              entities are paired by ``_pair_same_name_entities``.
      output  new_apis / removed_apis / modified_apis: SIMPLE-name lists (compatibility).
                new_apis     = simple names of every qualified-new type (a type whose simple
                               name collides with an existing one is no longer masked);
                removed_apis = simple names of removed types whose simple name no longer
                               exists anywhere (a name still held by another type is never
                               reported removed -- the page for it must not be dropped);
                modified_apis = simple names of paired types whose method names, property
                               names or enum member names changed.
              new_apis_qualified / removed_apis_qualified / modified_apis_qualified: qualified
              identities (sorted). name_collisions: one record per simple name that is held
              by more than one type in either snapshot and is involved in a change
              ({name, old, new, added, removed, modified}). api_signature_changes (keyed by
              simple name; entries of colliding same-named modified types are merged):
              added/removed_methods/properties always, plus enum_members_added/_removed when
              the enum member set changed.
      breaking (extractor-version aware): ``extractor_changed`` is "true" | "false" | "unknown"
              (see _extractor_change_state). A member removal (methods / properties / enum
              constants) is CONFIRMED -- ``breaking_changes`` / ``breaking_apis``
              ({name: {removed_methods, removed_properties, enum_members_removed}}, non-empty
              keys only) -- ONLY when extractor_changed == "false" AND the type stayed in the
              same file. Otherwise it is ``breaking_unconfirmed`` ({name: {<removed keys>,
              reason: "extractor_changed_or_unknown", verify_against_source: True}}) because a
              member-list drop between two extractor versions is indistinguishable from a real
              removal; ``breaking_unconfirmed_apis`` lists the names. Whole-type removals are
              still in removed_apis and, when extractor_changed != "false", also in
              ``removed_apis_unconfirmed``. ``extraction_drift_suspect`` (independent of
              extractor_changed) lists paired same-file types whose member count fell by
              >= 30% and >= 5 members with no member added -- the signature of extractor drift.
    """
    olds_by_name: dict = {}
    news_by_name: dict = {}
    for e in old_apis:
        if isinstance(e, dict) and "name" in e:
            olds_by_name.setdefault(e["name"], []).append(e)
    for e in new_apis:
        if isinstance(e, dict) and "name" in e:
            news_by_name.setdefault(e["name"], []).append(e)

    added_q: list = []
    removed_q: list = []
    modified_q: list = []
    added_names: set = set()
    removed_names: set = set()
    modified_names: set = set()
    sig_by_name: dict = {}
    collisions: list = []
    file_moved: set = set()
    drift_suspect: list = []

    for name in sorted(set(olds_by_name) | set(news_by_name)):
        olds, news = olds_by_name.get(name, []), news_by_name.get(name, [])
        pairs, gone, fresh = _pair_same_name_entities(olds, news)
        grp_added = sorted(_api_qualified_name(e) for e in fresh)
        grp_removed = sorted(_api_qualified_name(e) for e in gone)
        grp_modified: list = []
        for o, n in pairs:
            om, nm = _member_names(o, "methods"), _member_names(n, "methods")
            op, np_ = _member_names(o, "properties"), _member_names(n, "properties")
            oe, ne = _member_names(o, "enum_members"), _member_names(n, "enum_members")
            if om == nm and op == np_ and oe == ne:
                continue
            of, nf = str(o.get("file") or ""), str(n.get("file") or "")
            if of and nf and of != nf:
                file_moved.add(name)
            old_count, new_count = len(om) + len(op) + len(oe), len(nm) + len(np_) + len(ne)
            dropped = old_count - new_count
            if (of == nf and dropped >= 5 and dropped >= 0.3 * old_count
                    and not (nm - om) and not (np_ - op) and not (ne - oe)):
                drift_suspect.append({
                    "name": name, "qualified": _api_qualified_name(n), "file": nf,
                    "old_member_count": old_count, "new_member_count": new_count,
                    "removed_member_count": dropped,
                })
            grp_modified.append(_api_qualified_name(n))
            sig = sig_by_name.setdefault(name, {
                "added_methods": set(), "removed_methods": set(),
                "added_properties": set(), "removed_properties": set(),
                "enum_members_added": set(), "enum_members_removed": set(),
            })
            sig["added_methods"] |= nm - om
            sig["removed_methods"] |= om - nm
            sig["added_properties"] |= np_ - op
            sig["removed_properties"] |= op - np_
            sig["enum_members_added"] |= ne - oe
            sig["enum_members_removed"] |= oe - ne
        added_q += grp_added
        removed_q += grp_removed
        modified_q += grp_modified
        if grp_added:
            added_names.add(name)
        if grp_removed:
            removed_names.add(name)
        if grp_modified:
            modified_names.add(name)
        if (len(olds) > 1 or len(news) > 1) and (grp_added or grp_removed or grp_modified):
            collisions.append({
                "name": name,
                "old": sorted(_api_qualified_name(e) for e in olds),
                "new": sorted(_api_qualified_name(e) for e in news),
                "added": grp_added, "removed": grp_removed, "modified": sorted(grp_modified),
            })

    new_names = set(news_by_name)
    api_signature_changes: dict = {}
    breaking_changes: dict = {}
    breaking_unconfirmed: dict = {}
    extractor_stable = extractor_changed == "false"
    for name, sig in sig_by_name.items():
        entry = {
            "added_methods": sorted(sig["added_methods"]),
            "removed_methods": sorted(sig["removed_methods"]),
            "added_properties": sorted(sig["added_properties"]),
            "removed_properties": sorted(sig["removed_properties"]),
        }
        if sig["enum_members_added"] or sig["enum_members_removed"]:
            entry["enum_members_added"] = sorted(sig["enum_members_added"])
            entry["enum_members_removed"] = sorted(sig["enum_members_removed"])
        api_signature_changes[name] = entry
        broken = {
            k: entry[k] for k in ("removed_methods", "removed_properties", "enum_members_removed")
            if entry.get(k)
        }
        if broken:
            if extractor_stable and name not in file_moved:
                breaking_changes[name] = broken
            else:
                breaking_unconfirmed[name] = {
                    **broken,
                    "reason": "extractor_changed_or_unknown",
                    "verify_against_source": True,
                }

    return {
        "new_apis": sorted(added_names),
        "removed_apis": sorted(removed_names - new_names),
        "modified_apis": sorted(modified_names),
        "new_apis_qualified": sorted(added_q),
        "removed_apis_qualified": sorted(removed_q),
        "modified_apis_qualified": sorted(modified_q),
        "name_collisions": collisions,
        "api_signature_changes": {k: api_signature_changes[k] for k in sorted(api_signature_changes)},
        "breaking_apis": sorted(breaking_changes),
        "breaking_changes": {k: breaking_changes[k] for k in sorted(breaking_changes)},
        "breaking_unconfirmed_apis": sorted(breaking_unconfirmed),
        "breaking_unconfirmed": {k: breaking_unconfirmed[k] for k in sorted(breaking_unconfirmed)},
        "removed_apis_unconfirmed": [] if extractor_stable else sorted(removed_names - new_names),
        "extraction_drift_suspect": sorted(drift_suspect, key=lambda d: d["qualified"]),
    }


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

    raw_added_claims = [cid for cid in new_by_id if cid not in old_by_id]
    raw_removed_claims = [cid for cid in old_by_id if cid not in new_by_id]
    modified_claims = [
        cid for cid in new_by_id
        if cid in old_by_id and (
            new_by_id[cid].get("text") != old_by_id[cid].get("text")
            or new_by_id[cid].get("confidence") != old_by_id[cid].get("confidence")
        )
    ]

    # Re-identification reconciliation (found live 2026-08-25, a residual gap in
    # G10 neither Task 16 nor Task 17 closed): a claim-ID reassignment (e.g.
    # Task 16's anchor-stable IDs for scout-derived member claims) makes a pure
    # raw claim_id set-difference report a claim as BOTH removed (old id) and
    # added (new id) even when its text is byte-identical -- nothing about the
    # claim actually changed, only its identifier. Left unreconciled, this is
    # catastrophic: semantic_diff.py's _classify_claim_change maps every
    # removed_claims entry to FEATURE_REMOVED unconditionally, and
    # body_impact.py maps FEATURE_REMOVED to UT_REMOVAL (delete the section) --
    # so a mass re-ID storm (measured live on pdf/java's first post-Task-16
    # re-scout: 11942 of 11945 raw "removed" claims had exact-text matches
    # among raw "added" claims) causes body_refresh.py to delete real, unchanged
    # content across every citing page. Reconcile by exact text match before
    # these lists reach any content-impact consumer; a claim that merely
    # changed ID is recorded separately (reidentified_claims) for evidence-
    # citation bookkeeping (stale_detect.py's orphaned_claims check is
    # independent of this list -- it compares a page's cited ID directly
    # against the current claims.json, so it still correctly flags the old ID
    # as needing a citation refresh regardless of this reconciliation).
    new_texts_by_content: dict[str, list[str]] = {}
    for cid in raw_added_claims:
        text = new_by_id[cid].get("text") or ""
        if text:
            new_texts_by_content.setdefault(text, []).append(cid)

    reidentified_claims: dict[str, str] = {}
    removed_claims: list[str] = []
    for cid in raw_removed_claims:
        text = old_by_id[cid].get("text") or ""
        candidates = new_texts_by_content.get(text) if text else None
        if candidates:
            reidentified_claims[cid] = candidates.pop(0)
            if not candidates:
                del new_texts_by_content[text]
        else:
            removed_claims.append(cid)

    reidentified_new_ids = set(reidentified_claims.values())
    added_claims = [cid for cid in raw_added_claims if cid not in reidentified_new_ids]

    # Task 17 (§9.12, closes the other half of G10): carry the real claim TEXT
    # alongside each new/removed/modified claim id, not just the opaque id
    # string. Before this, semantic_diff.py's _classify_claim_change and
    # body_impact.py's keyword tokenizer both had no choice but to pattern-
    # match against the claim_id itself (e.g. "CLM-pdf-a1b2c3") -- which can
    # never contain a real word like "deprecated"/"not supported", so the
    # keyword-based BEHAVIOR_CHANGED/LIMITATION_CHANGED/FEATURE_CHANGED
    # sub-classification was dead code in practice, always falling through to
    # the generic CLAIM_MODIFIED bucket. Keyed by claim_id for O(1) lookup;
    # additive (a new top-level field), so modified_claims/new_claims/
    # removed_claims themselves keep their existing plain-string-list shape
    # unchanged -- no existing consumer of those three fields is affected.
    claim_text_changes: dict[str, dict] = {}
    for cid in added_claims:
        claim_text_changes[cid] = {"old_text": None, "new_text": new_by_id[cid].get("text", "")}
    for cid in removed_claims:
        claim_text_changes[cid] = {"old_text": old_by_id[cid].get("text", ""), "new_text": None}
    for cid in modified_claims:
        claim_text_changes[cid] = {
            "old_text": old_by_id[cid].get("text", ""),
            "new_text": new_by_id[cid].get("text", ""),
        }

    # MT074 B2: API identity is QUALIFIED (see _diff_api_surface), not the simple class
    # name -- two different types sharing a simple name no longer mask each other, and
    # enum_members changes are diffed. Simple-name lists are kept for compatibility.
    extractor_changed = _extractor_change_state(bak_dir)
    api_diff = _diff_api_surface(old_apis, new_apis, extractor_changed=extractor_changed)
    added_apis = api_diff["new_apis"]
    removed_apis = api_diff["removed_apis"]
    api_surface_modified = api_diff["modified_apis"]
    api_signature_changes = api_diff["api_signature_changes"]

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

    # Task 15 (§9.10, closes G9): classes with a newly-deprecated class/method/
    # property (deprecated: False/absent -> True this cycle) get their own
    # additive signal, separate from modified_apis -- a deprecation is not a
    # name-set change (the member is still present, just discouraged), so it
    # would never appear in modified_apis at all otherwise. Only NEWLY
    # deprecated members count; a member that was already deprecated in the
    # prior snapshot and still is now is not re-reported every cycle.
    old_deprecated_keys: set = set()
    for entry in old_apis:
        if isinstance(entry, dict):
            old_deprecated_keys |= _deprecated_member_keys(entry)
    new_deprecated_keys: set = set()
    for entry in new_apis:
        if isinstance(entry, dict):
            new_deprecated_keys |= _deprecated_member_keys(entry)
    newly_deprecated_keys = new_deprecated_keys - old_deprecated_keys
    deprecated_apis = sorted({key.split(".")[0] for key in newly_deprecated_keys})

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
        "extractor_changed": extractor_changed,
        "new_claims": added_claims,
        "removed_claims": removed_claims,
        "modified_claims": modified_claims,
        "new_apis": added_apis,
        "removed_apis": removed_apis,
        "modified_apis": modified_apis,
        "deprecated_apis": deprecated_apis,
        "resurrected_apis": resurrected_apis,
        "claim_text_changes": claim_text_changes,
        "api_signature_changes": api_signature_changes,
        "reidentified_claims": reidentified_claims,
        # MT074 B2 additive fields (existing consumers ignore them).
        "new_apis_qualified": api_diff["new_apis_qualified"],
        "removed_apis_qualified": api_diff["removed_apis_qualified"],
        "modified_apis_qualified": api_diff["modified_apis_qualified"],
        "name_collisions": api_diff["name_collisions"],
        "breaking_apis": api_diff["breaking_apis"],
        "breaking_changes": api_diff["breaking_changes"],
        "breaking_unconfirmed_apis": api_diff["breaking_unconfirmed_apis"],
        "breaking_unconfirmed": api_diff["breaking_unconfirmed"],
        "removed_apis_unconfirmed": api_diff["removed_apis_unconfirmed"],
        "extraction_drift_suspect": api_diff["extraction_drift_suspect"],
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
            f"~{len(modified_claims)} modified, +{len(added_apis)} apis, -{len(removed_apis)} apis"
            + (f", {len(reidentified_claims)} reidentified (ID-only churn, excluded above)"
               if reidentified_claims else "")
            + ")"
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
    pin_sha: "str | None" = None,
    strict_fetch: bool = False,
    allow_drop_enrichment: bool = False,
    allow_partial_enrichment: bool = False,
) -> str:
    """Refresh knowledge for one product.

    allow_drop_enrichment (MT074 B13a): forwarded to promote.py as
    --allow-drop-enrichment. Off by default -- promote fails closed rather than
    silently dropping the tracked enriched (ERC-*) claims.

    Returns one of: "current", "refreshed", "stale", "no_clone", "failed".

    pin_sha (MT074 B1): after clone/fetch, detach-checkout the clone at exactly this
    commit and use it as HEAD for the whole refresh; "failed" if HEAD cannot be made
    equal to it. strict_fetch: a failed upstream fetch returns "failed" instead of the
    legacy degraded mode (continue on the stale clone HEAD). Defaults change nothing.

    When auto_clone=True (default), attempts to clone the repo from clone_url
    in data/products.json if the clone cache directory is missing.
    When auto_fetch=True (default), calls update_clone() before comparing SHAs
    so that change detection is not permanently blind.
    """
    clone = _clone_dir(family, platform)
    head = _hooked("head_sha", _head_sha)(clone)
    if head is None:
        if auto_clone and not check_only:
            cloned = _try_auto_clone(family, platform, clone)
            if cloned:
                head = _hooked("head_sha", _head_sha)(clone)
        if head is None:
            print(f"  {family}/{platform}: clone cache not found at {clone}")
            return "no_clone"

    # Fetch upstream to advance local HEAD before SHA comparison.
    # This fixes the permanent blind-detection problem (shallow clone never updated).
    if auto_fetch:
        if strict_fetch:
            try:
                fetched_sha = _update_clone(family, platform, strict=True)
            except RuntimeError as exc:
                print(f"  {family}/{platform}: FAILED — strict fetch error: {exc}")
                return "failed"
        else:
            fetched_sha = _update_clone(family, platform)
        if fetched_sha is not None:
            head = fetched_sha
        # If fetch fails, continue with existing clone HEAD (degraded mode)

    if pin_sha:
        try:
            pinned = _hooked("checkout_pinned", _checkout_pinned)(family, platform, pin_sha)
        except RuntimeError as exc:
            print(f"  {family}/{platform}: FAILED — cannot pin clone to {pin_sha[:10]}: {exc}")
            return "failed"
        actual = _hooked("head_sha", _head_sha)(clone)
        if actual != pinned:
            print(f"  {family}/{platform}: FAILED — pin mismatch: clone HEAD "
                  f"{(actual or 'none')[:10]} != pinned {pinned[:10]}")
            return "failed"
        head = pinned

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

    # FRESH-001 (2026-08-14, T4): the scout->enrich->promote->index chain (including
    # this function's own merged/<->merged.bak backup-restore around it) previously had
    # NO lock -- two concurrent refresh_knowledge.py invocations for the same product
    # (manual /knowledge-update, S-90's auto-refresh, and now the scheduled
    # bounded-auto-regen path) could race on the same merged/merged.bak directories.
    # Held for the whole chain, not per-step; acquired BEFORE refresh_run.py's own
    # content-refresh lock is ever taken (fixed ordering, documented in
    # knowledge_regen_lock.py, to prevent deadlock).
    from knowledge_regen_lock import acquire_regen_lock, LockTimeout as RegenLockTimeout
    try:
        with acquire_regen_lock(family, platform, owner="refresh-knowledge",
                                 knowledge_root=KNOWLEDGE_ROOT):
            _chain_kw: dict = {}
            if allow_drop_enrichment:
                _chain_kw["allow_drop_enrichment"] = True
            if allow_partial_enrichment:
                _chain_kw["allow_partial_enrichment"] = True
            if pin_sha:
                _chain_kw["pin_sha"] = pin_sha
            return _run_refresh_chain(family, platform, clone, head, current,
                                       compulsory_enrich=compulsory_enrich, skip_enrich=skip_enrich,
                                       **_chain_kw)
    except RegenLockTimeout:
        print(f"  {family}/{platform}: another process is already refreshing this "
              f"product's knowledge (regen lock busy) — skipping this run")
        return "failed"


def _run_refresh_chain(
    family: str,
    platform: str,
    clone: Path,
    head: str,
    current: "str | None",
    *,
    compulsory_enrich: bool,
    skip_enrich: bool,
    allow_drop_enrichment: bool = False,
    allow_partial_enrichment: bool = False,
    pin_sha: "str | None" = None,
) -> str:
    """The scout -> enrich -> promote -> index chain, run under refresh()'s regen
    lock. Extracted to its own function (unchanged body) purely so refresh() can wrap
    the call in a `with acquire_regen_lock(...):` block without re-indenting ~120
    lines of existing, working logic."""
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
        ok = _hooked("run", _run)(
            [sys.executable, "scripts/pipeline/commands/knowledge/scout.py",
             family, platform, str(clone), str(scout_out)],
            "scout",
        )
        if not ok:
            return "failed"
        # MT074 R1-8: the pin was verified ONCE, before the chain.  Re-verify after the
        # scout step (the one step that reads the clone) so a clone that moved under a
        # pinned refresh can never be promoted as if it were the pinned commit.
        if pin_sha:
            _after = _hooked("head_sha", _head_sha)(clone)
            if _after != head:
                print(f"  {family}/{platform}: FAILED — pinned clone HEAD moved during scout: "
                      f"{(_after or 'none')[:10]} != pinned {head[:10]}")
                return "failed"

        # Enrich: best-effort by default, hard fail with --compulsory-enrich.
        # SEAM-01: --skip-enrich bypasses LLM calls entirely (scout-only run).
        if skip_enrich:
            print(f"  {family}/{platform}: enrich skipped (--skip-enrich)")
            enrich_ok = False
            # MT074 B13a: --skip-enrich means "no LLM", not "drop the enriched claims".
            # When scout/enriched_claims.json is missing but the tracked merged claims
            # hold ERC claims, materialise them via the LLM-free carry-forward
            # (enrich.py --no-llm seeds from the tracked claims) so promote does not
            # abort or silently drop them.
            if not (scout_out / "enriched_claims.json").exists() and \
                    (merged_dir / "claims.json").exists():
                _hooked("run", _run)(
                    [sys.executable, "scripts/pipeline/commands/knowledge/enrich.py",
                     family, platform, "--no-llm"],
                    "enrich-seed",
                )
        else:
            enrich_ok = _hooked("run", _run)(
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

        # MT074 B13d: pass the current extractor hash so promote stamps it into
        # model.yaml (it used to drop the field; it was only re-saved at the very
        # end of a fully successful chain).
        _promote_cmd = [sys.executable, "scripts/pipeline/commands/knowledge/promote.py",
                        family, platform, "--extractor-hash", _compute_extractor_hash()]
        if allow_drop_enrichment:
            _promote_cmd.append("--allow-drop-enrichment")
        if allow_partial_enrichment:
            _promote_cmd.append("--allow-partial-enrichment")
        ok = _hooked("run", _run)(_promote_cmd, "promote")
        if not ok:
            return "failed"

        # Write knowledge_delta.json only after successful promote (no partial delta).
        _write_knowledge_delta(family, platform, bak_dir, merged_dir, head, current)

        # Write manifest_delta.json: coordinate/install/version changes (TC-01).
        # Must run before _cleanup_bak() in the finally block.
        _write_manifest_delta(family, platform, bak_dir, merged_dir, head, current)

        # PKGINSTALL-BLOCK-UPDATER-CALLSITE: dry-run only, folded into
        # pipeline_run.json below and into the reconciliation store.
        block_updater_summary = _maybe_run_block_updater_dry_run(family, platform, merged_dir)

        # Write format_delta.json: format support additions/removals (TC-02).
        # Must run before _cleanup_bak() in the finally block.
        _write_format_delta(family, platform, bak_dir, merged_dir, head, current)

        # Record enrichment quality in model.yaml so downstream consumers can detect
        # scout-only (degraded) refreshes vs full refreshes (TC-4).
        _write_model_field(
            family, platform, "enrichment_status", "full" if enrich_ok else "scout-only"
        )

        ok = _hooked("run", _run)(
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
            if block_updater_summary is not None:
                pipeline_run["block_updater_dry_run"] = block_updater_summary
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

        _hooked("completeness_check", _run_completeness_check)(family, platform)

        # Auto-refresh evidence after knowledge update to prevent WARN drift.
        # Non-fatal: evidence can always be re-attached manually.
        _hooked("run", _run)(
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
    parser.add_argument("--pin-sha", dest="pin_sha", default=None, metavar="SHA",
                        help="Detach-checkout the clone at exactly SHA after fetch; fail if HEAD != SHA")
    parser.add_argument("--strict-fetch", action="store_true", dest="strict_fetch",
                        help="Treat a failed upstream fetch as a hard failure (no degraded mode)")
    parser.add_argument("--compulsory-enrich", action="store_true",
                        help="Require enrichment to succeed; abort pipeline on enrich failure")
    parser.add_argument("--skip-enrich", action="store_true", dest="skip_enrich",
                        help="Skip LLM enrichment entirely; writes enrichment_status: scout-only")
    parser.add_argument("--allow-drop-enrichment", action="store_true", dest="allow_drop_enrichment",
                        help="MT074 B13a: let promote DROP the tracked enriched (ERC-*) claims when "
                             "enrichment output is absent/empty/stale. Off by default (promote aborts "
                             "instead, so enrichment is never silently lost).")
    parser.add_argument("--allow-partial-enrichment", action="store_true", dest="allow_partial_enrichment",
                        help="MT074 R1-5: let promote use an enrichment output marked PARTIAL (some "
                             "changed units failed/yielded nothing; their old claims are kept). Off by "
                             "default; the failed units are retried on the next enrich run.")
    parser.add_argument("family", nargs="?", help="Product family (e.g. 3d)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. python)")
    args = parser.parse_args()
    if args.pin_sha and args.all:
        parser.error("--pin-sha is per-product; it cannot be combined with --all")

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
                pin_sha=args.pin_sha,
                strict_fetch=args.strict_fetch,
                allow_drop_enrichment=args.allow_drop_enrichment,
                allow_partial_enrichment=args.allow_partial_enrichment,
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
        pin_sha=args.pin_sha,
        strict_fetch=args.strict_fetch,
        allow_drop_enrichment=args.allow_drop_enrichment,
        allow_partial_enrichment=args.allow_partial_enrichment,
    )
    if result in ("stale", "failed", "no_clone"):
        sys.exit(1)


if __name__ == "__main__":
    main()
