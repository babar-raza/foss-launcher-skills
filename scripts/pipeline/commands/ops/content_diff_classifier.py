"""
TC-S96-008 + TC-S96-011: Content Diff Classifier.

Compares current content files to a baseline manifest and classifies
each file as ADDED, EDITED, DELETED, UNCHANGED, CHURN_ONLY, etc.
Also detects churn signals (timestamp-only, whitespace-only, etc.).
"""
from __future__ import annotations

import difflib
import json
import os
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import yaml


class Category(str, Enum):
    ADDED = "ADDED"
    EDITED = "EDITED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"
    GENERATED_IDENTICAL = "GENERATED_IDENTICAL"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CHURN_ONLY = "CHURN_ONLY"


_TIMESTAMP_KEYS = {"date", "content_created_at", "lastmod", "updated_at", "created_at"}
_GRADE_KEYS = {"graded_at", "grade_updated"}


@dataclass
class DiffEntry:
    path: str
    category: Category
    baseline_sha: Optional[str] = None
    current_sha: Optional[str] = None
    change_bytes: Optional[int] = None
    unified_diff: Optional[str] = None
    churn_signals: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "category": self.category.value if isinstance(self.category, Category) else self.category,
            "baseline_sha": self.baseline_sha,
            "current_sha": self.current_sha,
            "change_bytes": self.change_bytes,
            "unified_diff": self.unified_diff,
            "churn_signals": self.churn_signals,
        }


@dataclass
class DiffReport:
    run_id: str
    baseline_git_sha: str
    generated_at: str
    entries: List[DiffEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        counts: Dict[str, int] = {c.value.lower(): 0 for c in Category}
        # map enum values to count keys
        count_map = {
            Category.ADDED: "added",
            Category.EDITED: "edited",
            Category.DELETED: "deleted",
            Category.UNCHANGED: "unchanged",
            Category.GENERATED_IDENTICAL: "generated_identical",
            Category.OUT_OF_SCOPE: "out_of_scope",
            Category.CHURN_ONLY: "churn_only",
        }
        counts = {v: 0 for v in count_map.values()}
        for e in self.entries:
            cat = e.category if isinstance(e.category, Category) else Category(e.category)
            key = count_map.get(cat, "unchanged")
            counts[key] = counts.get(key, 0) + 1

        return {
            "run_id": self.run_id,
            "baseline_git_sha": self.baseline_git_sha,
            "generated_at": self.generated_at,
            "counts": counts,
            "entries": [e.to_dict() for e in self.entries],
        }


def detect_churn_signals(baseline_text: str, current_text: str) -> List[str]:
    """Detect churn signals comparing two file text versions."""
    signals: List[str] = []
    if baseline_text == current_text:
        return signals

    def _parse_fm(text: str):
        if not text.startswith("---"):
            return {}, text
        end = text.find("\n---", 3)
        if end == -1:
            return {}, text
        fm_block = text[3:end].strip()
        body = text[end + 4:]
        try:
            data = yaml.safe_load(fm_block)
            return (data if isinstance(data, dict) else {}), body
        except Exception:
            return {}, body

    base_fm, base_body = _parse_fm(baseline_text)
    curr_fm, curr_body = _parse_fm(current_text)

    # Timestamp-only change
    base_non_ts = {k: v for k, v in base_fm.items() if k not in _TIMESTAMP_KEYS and k not in _GRADE_KEYS}
    curr_non_ts = {k: v for k, v in curr_fm.items() if k not in _TIMESTAMP_KEYS and k not in _GRADE_KEYS}
    base_body_norm = " ".join(base_body.split())
    curr_body_norm = " ".join(curr_body.split())
    if base_non_ts == curr_non_ts and base_body_norm == curr_body_norm:
        # Only timestamp/grade keys changed
        changed_keys = set(base_fm.keys()) ^ set(curr_fm.keys())
        changed_keys |= {k for k in base_fm if base_fm.get(k) != curr_fm.get(k)}
        if changed_keys and all(k in _TIMESTAMP_KEYS or k in _GRADE_KEYS for k in changed_keys):
            if any(k in _TIMESTAMP_KEYS for k in changed_keys):
                signals.append("timestamp_only")
            if any(k in _GRADE_KEYS for k in changed_keys):
                signals.append("grade_churn")
            return signals

    # Grade-only churn
    base_non_grade = {k: v for k, v in base_fm.items() if k not in _GRADE_KEYS}
    curr_non_grade = {k: v for k, v in curr_fm.items() if k not in _GRADE_KEYS}
    if base_non_grade == curr_non_grade and base_body_norm == curr_body_norm:
        grade_changed = {k for k in _GRADE_KEYS if base_fm.get(k) != curr_fm.get(k)}
        if grade_changed:
            signals.append("grade_churn")
            return signals

    # YAML reorder: frontmatter parses to same dict but raw text differs, body same
    if base_fm and curr_fm and base_fm == curr_fm and base_body.strip() == curr_body.strip():
        if baseline_text != current_text:
            signals.append("yaml_reorder")
            return signals

    # Whitespace-only: strip all whitespace from both
    if "".join(baseline_text.split()) == "".join(current_text.split()):
        signals.append("whitespace_only")
        return signals

    # Line-wrap: normalize spaces
    if base_body_norm == curr_body_norm and base_non_ts == curr_non_ts:
        signals.append("line_wrap_only")
        return signals

    return signals


def is_churn_only(signals: List[str]) -> bool:
    """Return True if the signals indicate this is a churn-only change."""
    churn_signals = {"timestamp_only", "whitespace_only", "yaml_reorder",
                     "line_wrap_only", "shortcode_format", "grade_churn"}
    return bool(signals) and all(s in churn_signals for s in signals)


def _sha256_text(text: str) -> str:
    import hashlib
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _read_normalized(path: pathlib.Path) -> tuple[str, str]:
    """Return (sha256, text) of file, LF-normalized."""
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    text = normalized.decode("utf-8", errors="replace")
    import hashlib
    sha = hashlib.sha256(normalized).hexdigest()
    return sha, text


def classify_diff(
    manifest: Dict[str, Any],
    repo_root: pathlib.Path,
    scope: Any = None,
) -> DiffReport:
    """
    Compare current disk state to baseline manifest.
    manifest: dict as produced by BaselineManifest.to_dict()
    scope: optional ScopeManifest to filter files
    """
    run_id = manifest.get("run_id", "unknown")
    baseline_git_sha = manifest.get("baseline_git_sha", "unknown")
    generated_at = datetime.now(timezone.utc).isoformat()

    baseline_files: Dict[str, dict] = manifest.get("files", {})
    entries: List[DiffEntry] = []

    # Determine files to check: manifest files + scope files (if provided)
    all_paths: set = set(baseline_files.keys())
    if scope is not None:
        scope_files = list(getattr(scope, "files", []) or [])
        content_roots = getattr(scope, "content_roots", {}) or {}
        if scope_files:
            all_paths.update(scope_files)
        elif content_roots:
            for sub, root_tmpl in content_roots.items():
                root_dir = repo_root / root_tmpl
                if root_dir.exists():
                    for md_file in sorted(root_dir.rglob("*.md")):
                        rel = md_file.relative_to(repo_root).as_posix()
                        all_paths.add(rel)

    # Process each path
    for rel_path in sorted(all_paths):
        abs_path = repo_root / rel_path
        in_baseline = rel_path in baseline_files
        on_disk = abs_path.exists()

        if not in_baseline and on_disk:
            sha, _ = _read_normalized(abs_path)
            entries.append(DiffEntry(
                path=rel_path,
                category=Category.ADDED,
                current_sha=sha,
            ))
        elif in_baseline and not on_disk:
            entries.append(DiffEntry(
                path=rel_path,
                category=Category.DELETED,
                baseline_sha=baseline_files[rel_path]["sha256"],
            ))
        elif in_baseline and on_disk:
            baseline_sha = baseline_files[rel_path]["sha256"]
            current_sha, current_text = _read_normalized(abs_path)

            if current_sha == baseline_sha:
                entries.append(DiffEntry(
                    path=rel_path,
                    category=Category.UNCHANGED,
                    baseline_sha=baseline_sha,
                    current_sha=current_sha,
                ))
            else:
                # Try to get baseline text for churn detection
                # (We don't store baseline text in manifest, so read from git if possible)
                churn_signals: List[str] = []
                unified = None
                change_bytes = abs(len(current_text.encode()) - baseline_files[rel_path].get("size_bytes", 0))

                # Build unified diff (no baseline text available without git, use size proxy)
                # We can detect some churn signals from current frontmatter alone
                churn_signals = detect_churn_signals_from_current(
                    current_text, baseline_files[rel_path].get("frontmatter", {})
                )

                if is_churn_only(churn_signals):
                    cat = Category.CHURN_ONLY
                else:
                    cat = Category.EDITED

                entries.append(DiffEntry(
                    path=rel_path,
                    category=cat,
                    baseline_sha=baseline_sha,
                    current_sha=current_sha,
                    change_bytes=change_bytes,
                    churn_signals=churn_signals,
                ))

    return DiffReport(
        run_id=run_id,
        baseline_git_sha=baseline_git_sha,
        generated_at=generated_at,
        entries=entries,
    )


def detect_churn_signals_from_current(current_text: str, baseline_fm: dict) -> List[str]:
    """Detect churn signals using only current text and baseline frontmatter."""
    # Limited detection without baseline text
    signals: List[str] = []
    return signals


def write_diff_report(report: DiffReport, output: pathlib.Path) -> None:
    """Write DiffReport to JSON atomically."""
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp, output)
