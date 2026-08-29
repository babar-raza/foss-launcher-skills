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

    delta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_sha": base_sha or "",
        "current_sha": current_sha,
        "events": events,
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


def _write_format_delta(
    family: str,
    platform: str,
    bak_dir: Path,
    merged_dir: Path,
    current_sha: str,
    base_sha: str | None,
) -> None:
    """Compute and write format_delta.json comparing merged.bak/formats.json vs merged/formats.json.

    Detects: FORMAT_ADDED, FORMAT_REMOVED, FORMAT_DIRECTION_CHANGED.
    Written to merged/format_delta.json; persists after bak cleanup.
    Must be called BEFORE _cleanup_bak().
    """
    bak_fmt_path = bak_dir / "formats.json"
    new_fmt_path = merged_dir / "formats.json"

    def _load_formats(path: Path) -> dict[str, dict]:
        """Load formats.json as a dict keyed by format name (uppercase)."""
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if not isinstance(data, list):
                return {}
            return {str(f.get("name", "")).upper(): f for f in data if isinstance(f, dict)}
        except Exception:
            return {}

    old_formats = _load_formats(bak_fmt_path)
    new_formats = _load_formats(new_fmt_path)

    added: list[dict] = []
    removed: list[dict] = []
    direction_changed: list[dict] = []

    old_names = set(old_formats)
    new_names = set(new_formats)

    for name in sorted(new_names - old_names):
        f = new_formats[name]
        added.append({
            "name": f.get("name", name),
            "ext": f.get("ext", ""),
            "support": f.get("support", ""),
            "description": f.get("description", ""),
        })

    for name in sorted(old_names - new_names):
        f = old_formats[name]
        removed.append({
            "name": f.get("name", name),
            "ext": f.get("ext", ""),
            "support": f.get("support", ""),
        })

    for name in sorted(old_names & new_names):
        old_sup = old_formats[name].get("support", "")
        new_sup = new_formats[name].get("support", "")
        if old_sup != new_sup:
            direction_changed.append({
                "name": new_formats[name].get("name", name),
                "old_support": old_sup,
                "new_support": new_sup,
            })

    delta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_sha": base_sha or "",
        "current_sha": current_sha,
        "formats_added": added,
        "formats_removed": removed,
        "formats_direction_changed": direction_changed,
    }

    target = merged_dir / "format_delta.json"
    tmp = target.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
        print(
            f"  {family}/{platform}: format_delta.json written "
            f"(+{len(added)} added, -{len(removed)} removed, ~{len(direction_changed)} direction_changed)"
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

    # Task 17 (§9.12): a short, structured signature-diff summary for each
    # name-set-changed class -- alongside modified_apis, not a replacement
    # for it. Only api_surface_modified (a real method/property name-set
    # change) gets one; erc_changed_classes (doc-coverage only, no signature
    # change) correctly does not.
    api_signature_changes: dict[str, dict] = {}
    for name in api_surface_modified:
        old_methods = {m.get("name") for m in old_api_by_name[name].get("methods", [])}
        new_methods = {m.get("name") for m in new_api_by_name[name].get("methods", [])}
        old_props = {p.get("name") for p in old_api_by_name[name].get("properties", [])}
        new_props = {p.get("name") for p in new_api_by_name[name].get("properties", [])}
        api_signature_changes[name] = {
            "added_methods": sorted(new_methods - old_methods),
            "removed_methods": sorted(old_methods - new_methods),
            "added_properties": sorted(new_props - old_props),
            "removed_properties": sorted(old_props - new_props),
        }

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
            return _run_refresh_chain(family, platform, clone, head, current,
                                       compulsory_enrich=compulsory_enrich, skip_enrich=skip_enrich)
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

        # Write manifest_delta.json: coordinate/install/version changes (TC-01).
        # Must run before _cleanup_bak() in the finally block.
        _write_manifest_delta(family, platform, bak_dir, merged_dir, head, current)

        # Write format_delta.json: format support additions/removals (TC-02).
        # Must run before _cleanup_bak() in the finally block.
        _write_format_delta(family, platform, bak_dir, merged_dir, head, current)

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
