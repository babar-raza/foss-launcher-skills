"""snapshot_guard.py — Pre-write snapshot and rollback guard for update_existing.

TC-CE-023: Captures file state before content updates, enables safe rollback
if validation fails. Does NOT use git operations — works on untracked/unstaged
files via file-copy mechanism.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[3]


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _extract_frontmatter(text: str) -> str | None:
    """Extract YAML frontmatter block (between --- delimiters)."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return text[3:end].strip()


def take_snapshot(
    family: str,
    platform: str,
    target_paths: list[str],
    *,
    trigger: str = "execute_one",
    candidate_ref: dict | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Capture pre-write snapshot for one or more content files.

    Returns path to the snapshot directory containing manifest.json + .snapshot files.
    Raises FileNotFoundError if target doesn't exist, ValueError for bad paths.
    """
    root = repo_root or _REPO_ROOT

    if not target_paths:
        raise ValueError("target_paths must not be empty")

    for p in target_paths:
        normalized = p.replace("\\", "/")
        if not normalized.startswith("content/"):
            raise ValueError(f"Path guard: only content/ paths allowed, got: {p}")
        if ".." in normalized:
            raise ValueError(f"Path guard: path traversal not allowed: {p}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    snap_dir = root / "reports" / "snapshots" / family / platform / ts
    snap_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []

    for rel_path in target_paths:
        abs_path = root / rel_path
        if not abs_path.exists():
            raise FileNotFoundError(f"Target file not found: {rel_path}")

        content_bytes = abs_path.read_bytes()
        content_text = content_bytes.decode("utf-8", errors="replace")
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        fm_text = _extract_frontmatter(content_text)
        fm_hash = hashlib.sha256(fm_text.encode()).hexdigest() if fm_text else ""

        slug = abs_path.stem
        snap_file = snap_dir / f"{slug}.md.snapshot"
        shutil.copy2(str(abs_path), str(snap_file))

        records.append({
            "file_path": rel_path,
            "content_sha256": content_hash,
            "frontmatter_hash": fm_hash,
            "file_size": len(content_bytes),
            "snapshot_file": snap_file.name,
            "existed_before": True,
        })

    manifest = {
        "snapshot_version": "1.0",
        "family": family,
        "platform": platform,
        "trigger": trigger,
        "candidate_ref": candidate_ref or {},
        "snapshot_time": datetime.now(timezone.utc).isoformat(),
        "files": records,
    }

    manifest_path = snap_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    return snap_dir


def restore_snapshot(
    snapshot_dir: Path,
    *,
    dry_run: bool = False,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Restore files from a snapshot directory.

    Returns dict with keys: restored, skipped, errors, dry_run.
    """
    root = repo_root or _REPO_ROOT
    manifest_path = snapshot_dir / "manifest.json"

    if not manifest_path.exists():
        return {"restored": [], "skipped": [], "errors": ["manifest.json not found"], "dry_run": dry_run}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result: dict[str, Any] = {"restored": [], "skipped": [], "errors": [], "dry_run": dry_run}

    for rec in manifest.get("files", []):
        rel_path = rec["file_path"]
        snap_file = snapshot_dir / rec["snapshot_file"]
        target = root / rel_path

        if not snap_file.exists():
            result["errors"].append(f"Snapshot file missing: {rec['snapshot_file']}")
            continue

        if target.exists():
            current_hash = _sha256(target)
            if current_hash == rec["content_sha256"]:
                result["skipped"].append(f"{rel_path} (unchanged)")
                continue

        if dry_run:
            result["restored"].append(f"{rel_path} (would restore)")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(snap_file), str(target))
            if _sha256(target) == rec["content_sha256"]:
                result["restored"].append(rel_path)
            else:
                result["errors"].append(f"Hash mismatch after restore: {rel_path}")

    return result


def diff_summary(
    snapshot_dir: Path,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Compare current files against snapshot, return list of change summaries."""
    root = repo_root or _REPO_ROOT
    manifest_path = snapshot_dir / "manifest.json"

    if not manifest_path.exists():
        return []

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    diffs = []

    for rec in manifest.get("files", []):
        rel_path = rec["file_path"]
        target = root / rel_path
        entry: dict[str, Any] = {
            "file_path": rel_path,
            "before_sha256": rec["content_sha256"],
            "before_size": rec["file_size"],
        }

        if not target.exists():
            entry.update(status="missing", after_sha256="", after_size=0,
                         size_delta=-rec["file_size"])
        else:
            after_hash = _sha256(target)
            after_size = target.stat().st_size
            entry.update(
                after_sha256=after_hash, after_size=after_size,
                size_delta=after_size - rec["file_size"],
                status="unchanged" if after_hash == rec["content_sha256"] else "modified",
            )
        diffs.append(entry)

    return diffs
