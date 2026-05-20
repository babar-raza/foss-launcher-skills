# Adapted from aspose.org
"""grade_manifest.py — External grade manifest for operational pipeline state.

ARCH-01: Stores per-page operational evaluation state (evaluator versions,
model SHA, logic version, enrichment status) outside .md content files.
The manifest is committed to git with main-branch-only discipline — PR
branches use it locally but do not commit it.

The manifest eliminates frontmatter churn: ELV bumps update the manifest
(one file) instead of rewriting thousands of .md files.

Schema (per entry, keyed by relative filepath):
  {
    "content_hash": "32-char hex",
    "grade": "A|B|C|D|F",
    "grade_reasons": ["..."],
    "evaluator_versions": {"api_accuracy": "2", ...},
    "model_sha": "...",
    "logic_version": "16",
    "enrichment_status": "full|scout|none",
    "evaluated_at": "ISO-8601",
    "graded_evaluators": "full|audit|structural"
  }

Reference: curried-pondering-music.md §17.2 C-R1, §8.5
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Default manifest location (relative to repo root)
_DEFAULT_MANIFEST_PATH = Path("reports") / "grade_manifest.json"


def configure(*, manifest_path: Path | str | None = None) -> None:
    """Override the default manifest path for testing.

    Call with no arguments to reset to defaults.
    """
    global _DEFAULT_MANIFEST_PATH
    if manifest_path is not None:
        _DEFAULT_MANIFEST_PATH = Path(manifest_path)
    else:
        _DEFAULT_MANIFEST_PATH = Path("reports") / "grade_manifest.json"


def _manifest_path(override: Path | str | None = None) -> Path:
    """Resolve the manifest file path."""
    if override:
        return Path(override)
    return _DEFAULT_MANIFEST_PATH


def load_manifest(path: Path | str | None = None) -> dict[str, dict]:
    """Load the manifest from disk.  Returns empty dict if file does not exist."""
    mp = _manifest_path(path)
    if not mp.exists():
        return {}
    try:
        text = mp.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, dict):
            return data
        return {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"[grade_manifest] WARNING: cannot read {mp}: {exc}", file=sys.stderr)
        return {}


def save_manifest(manifest: dict[str, dict], path: Path | str | None = None) -> None:
    """Atomically write the manifest to disk."""
    mp = _manifest_path(path)
    mp.parent.mkdir(parents=True, exist_ok=True)
    # Write to temp file first, then rename for atomicity
    tmp = mp.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(mp)
    except OSError as exc:
        print(f"[grade_manifest] ERROR: cannot write {mp}: {exc}", file=sys.stderr)
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def read_manifest_entry(filepath: str, manifest: dict[str, dict] | None = None) -> dict | None:
    """Read a single entry from the manifest by relative filepath.

    If *manifest* is provided, reads from the in-memory dict (avoids disk I/O).
    Otherwise loads the manifest from disk.
    """
    if manifest is None:
        manifest = load_manifest()
    # Normalize path separators to forward slashes for consistent keys
    key = filepath.replace("\\", "/")
    return manifest.get(key)


def write_manifest_entry(
    filepath: str,
    *,
    content_hash: str,
    grade: str,
    grade_reasons: list[str] | None = None,
    evaluator_versions: dict[str, str] | None = None,
    model_sha: str = "",
    logic_version: str = "",
    enrichment_status: str | None = None,
    graded_evaluators: str = "full",
    manifest: dict[str, dict] | None = None,
    manifest_path: Path | str | None = None,
    save: bool = True,
) -> dict[str, dict]:
    """Write or update a single entry in the manifest.

    If *manifest* is provided, updates the in-memory dict.  When *save* is
    True (default), the manifest is persisted to disk after the update.

    Returns the updated manifest dict (for chaining or batch use).
    """
    if manifest is None:
        manifest = load_manifest(manifest_path)

    key = filepath.replace("\\", "/")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest[key] = {
        "content_hash": content_hash,
        "grade": grade,
        "grade_reasons": grade_reasons or [],
        "evaluator_versions": evaluator_versions or {},
        "model_sha": model_sha,
        "logic_version": logic_version,
        "enrichment_status": enrichment_status or "full",
        "graded_evaluators": graded_evaluators,
        "evaluated_at": now,
    }

    if save:
        save_manifest(manifest, manifest_path)

    return manifest


def manifest_skip_check(
    filepath: str,
    current_content_hash: str,
    current_evaluator_versions: dict[str, str],
    current_enrichment_status: str = "full",
    evaluator_names: list[str] | None = None,
    manifest: dict[str, dict] | None = None,
) -> tuple[bool, str]:
    """Check whether a page can be skipped based on manifest state.

    Returns (can_skip, reason).  When can_skip is True, all evaluators
    match and the content hash is unchanged — no re-evaluation needed.
    """
    entry = read_manifest_entry(filepath, manifest)
    if not entry:
        return False, "no-manifest-entry"

    # Content hash must match
    stored_hash = entry.get("content_hash", "")
    if stored_hash != current_content_hash:
        return False, "content-hash-changed"

    # Enrichment status must match
    stored_enrich = entry.get("enrichment_status") or "full"
    if stored_enrich != current_enrichment_status:
        return False, "enrichment-status-changed"

    # Per-evaluator version check (TC-5 via manifest)
    stored_ev = entry.get("evaluator_versions") or {}
    if evaluator_names:
        check_names = evaluator_names
    else:
        check_names = list(current_evaluator_versions.keys())

    for ev_name in check_names:
        current_ver = current_evaluator_versions.get(ev_name, "1")
        stored_ver = stored_ev.get(ev_name, "")
        if stored_ver != current_ver:
            return False, f"evaluator-version-changed:{ev_name}"

    return True, "manifest-match"
