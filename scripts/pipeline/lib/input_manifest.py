"""input_manifest.py -- resolve/hash/diff generation inputs.

CONTRACT: scripts/pipeline/lib/input_manifest.py
  purpose: TC-13 slice (readme-refresh-trackb-and-followon-2026-09-01). RC-2 in the
           governing plan: "No fact carries an as-of that travels with it -- start()
           pins exactly one input (clone_cache_head). The factpack then reads 8 side
           registries... each at a different, unrecorded moment, with no recorded
           identity." tex/python's real, documented BLOCKER (this mission's own
           canary, TC-27a) was exactly this gap: data/aspose_com_targets.json was
           corrected 2026-08-24, four days after the candidate was composed, and
           nothing re-resolved or invalidated the stale Enterprise-Edition link claim.

  scope, deliberately narrow (not the full 12-input design in the governing plan's
  Target Design section): clone_cache (commit + tree SHA, generalizing the existing
  clone_cache_head-only pin) + the ONE registry with a real, documented incident,
  data/aspose_com_targets.json's own per-product entry (never the whole file -- a
  whole-file hash would make every product's approve() sensitive to every OTHER
  product's registry edit, a real false-positive-drift risk this module deliberately
  avoids). The other 7 side registries, reference_index, and banner_asset from the
  plan's full design are NOT covered here -- a disclosed, real follow-on, not silently
  assumed done. Building all 8 registries' per-product entry extraction in one pass
  was assessed as materially higher-risk (8 different real schemas, no live-verified
  extraction logic for 7 of them) than the value of doing so in this same pass,
  mirroring TC-17's own "verify before generalizing" lesson on this exact mission.

  writes: nothing on its own -- pure resolve/hash functions. The caller (readme_
          refresh_run.py's start_run()/approve()) decides what to do with the result.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/ -> pipeline/ -> scripts/ -> repo root
_cfg_repo_root = _REPO_ROOT
_cfg_command_runner: Callable[..., "subprocess.CompletedProcess[str]"] = subprocess.run


def configure(*, repo_root: "Path | str | None" = None,
              command_runner: "Callable[..., subprocess.CompletedProcess[str]] | None" = None) -> None:
    """Test seam."""
    global _cfg_repo_root, _cfg_command_runner
    _cfg_repo_root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    _cfg_command_runner = command_runner or subprocess.run


def _git(*args: str, cwd: Path) -> "str | None":
    result = _cfg_command_runner(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _resolve_ee_target_entry(family: str, platform: str) -> "dict | None":
    """The raw data/aspose_com_targets.json entry for this exact product (products.aspose.com
    platform key `{family}/{platform}`) -- deliberately the RAW registry row, not the resolved
    output of _detect_enterprise_link's own (separately, already more complex) resolution
    algorithm. This module's job is detecting whether the INPUT changed, not replicating how
    it gets consumed."""
    path = _cfg_repo_root / "data" / "aspose_com_targets.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    platforms = (data.get("targets") or {}).get("products.aspose.com", {}).get("platforms", {})
    return platforms.get(f"{family}/{platform}")


def resolve_input_manifest(family: str, platform: str, clone_cache: Path) -> dict:
    """Resolves and hashes this pass's in-scope input set. Returns a JSON-serializable dict;
    never raises -- a missing/unreadable input resolves to None fields rather than blocking
    resolution (the caller decides whether an all-None manifest is itself a problem)."""
    commit = _git("rev-parse", "HEAD", cwd=clone_cache) if clone_cache.is_dir() else None
    tree = _git("rev-parse", "HEAD^{tree}", cwd=clone_cache) if clone_cache.is_dir() else None
    ee_entry = _resolve_ee_target_entry(family, platform)
    ee_entry_json = json.dumps(ee_entry, sort_keys=True) if ee_entry is not None else None

    manifest = {
        "clone_cache": {"commit": commit, "tree": tree},
        "enterprise_edition_target": {
            "entry": ee_entry,
            "entry_sha256": hashlib.sha256(ee_entry_json.encode("utf-8")).hexdigest() if ee_entry_json else None,
        },
    }
    canonical = json.dumps(manifest, sort_keys=True)
    manifest["manifest_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return manifest


def diff_manifests(pinned: dict, current: dict) -> "list[str]":
    """Returns a list of human-readable descriptions of every field that differs -- empty
    means no drift. Named per-field (not just 'manifest_hash differs') so a drift error can
    tell the reader WHICH input moved, matching this mission's own 'named evidence' standard."""
    diffs: list[str] = []
    pinned_clone = pinned.get("clone_cache") or {}
    current_clone = current.get("clone_cache") or {}
    if pinned_clone.get("commit") != current_clone.get("commit"):
        diffs.append(
            f"clone_cache.commit: {pinned_clone.get('commit')} -> {current_clone.get('commit')}"
        )
    if pinned_clone.get("tree") != current_clone.get("tree"):
        diffs.append(
            f"clone_cache.tree: {pinned_clone.get('tree')} -> {current_clone.get('tree')}"
        )
    pinned_ee = (pinned.get("enterprise_edition_target") or {}).get("entry_sha256")
    current_ee = (current.get("enterprise_edition_target") or {}).get("entry_sha256")
    if pinned_ee != current_ee:
        diffs.append(
            "enterprise_edition_target: data/aspose_com_targets.json's entry for this product "
            f"changed (sha256 {pinned_ee} -> {current_ee})"
        )
    return diffs
