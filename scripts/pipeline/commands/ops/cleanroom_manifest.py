"""
TC-S96-007: Cleanroom Baseline Manifest Writer.

Records a sha256 snapshot of all content files in scope before
cleanroom regeneration. Writes baseline-manifest.json atomically.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_SCHEMA_PATH = _REPO_ROOT / "data" / "schemas" / "cleanroom" / "baseline-manifest.schema.json"


def sha256_text(text: str) -> str:
    """Compute sha256 of text with LF-normalized line endings."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def sha256_file(path: pathlib.Path) -> tuple[str, int]:
    """Return (sha256_hex, size_bytes) for a file. Normalizes CRLF→LF."""
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    digest = hashlib.sha256(normalized).hexdigest()
    return digest, len(raw)


def parse_frontmatter(path: pathlib.Path, errors: List[str]) -> dict:
    """Parse YAML frontmatter from a markdown file. Returns {} on missing or error."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        errors.append(f"Read error {path}: {e}")
        return {}

    if not text.startswith("---"):
        return {}

    end = text.find("\n---", 3)
    if end == -1:
        return {}

    fm_block = text[3:end].strip()
    try:
        data = yaml.safe_load(fm_block)
        if isinstance(data, dict):
            return data
        return {}
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error in {path}: {e}")
        return {}


@dataclass
class FileRecord:
    sha256: str
    size_bytes: int
    frontmatter: Dict[str, Any]


@dataclass
class BaselineManifest:
    run_id: str
    baseline_git_sha: str
    captured_at: str
    scope: Dict[str, Any]
    files: Dict[str, FileRecord]
    _errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        files_out = {}
        for rel_path, rec in self.files.items():
            fm = rec.frontmatter
            files_out[rel_path] = {
                "sha256": rec.sha256,
                "size_bytes": rec.size_bytes,
                "frontmatter": {
                    "title": fm.get("title"),
                    "slug": fm.get("slug"),
                    "grade": fm.get("grade"),
                    "auto_updatable": fm.get("auto_updatable"),
                    "content_origin": fm.get("content_origin"),
                    "layout": fm.get("layout"),
                    "type": fm.get("type"),
                    "evidence_present": "evidence" in fm,
                    "provenance_present": "provenance" in fm,
                },
            }
        return {
            "run_id": self.run_id,
            "baseline_git_sha": self.baseline_git_sha,
            "captured_at": self.captured_at,
            "scope": self.scope,
            "files": files_out,
            "_errors": self._errors,
        }


def capture_baseline(
    scope: Any,
    output: pathlib.Path,
    run_id: str,
    repo_root: Optional[pathlib.Path] = None,
) -> BaselineManifest:
    """Capture content baseline for all files in scope. Writes output atomically."""
    if repo_root is None:
        repo_root = _REPO_ROOT

    errors: List[str] = []
    files: Dict[str, FileRecord] = {}

    # Determine file list
    file_list: List[str] = list(getattr(scope, "files", []) or [])
    content_roots: Dict[str, str] = getattr(scope, "content_roots", {}) or {}

    if not file_list and content_roots:
        # Walk content_roots
        family = getattr(scope, "family", "")
        platform = getattr(scope, "platform", "") or ""
        for sub, root_tmpl in content_roots.items():
            # Substitute {family}/{platform} placeholders if present
            try:
                root_str = root_tmpl.format(family=family, platform=platform)
            except (KeyError, IndexError):
                root_str = root_tmpl
            root_dir = repo_root / root_str
            if root_dir.exists():
                for md_file in sorted(root_dir.rglob("*.md")):
                    rel = md_file.relative_to(repo_root).as_posix()
                    file_list.append(rel)

    for rel_path in file_list:
        abs_path = repo_root / rel_path
        if not abs_path.exists():
            errors.append(f"File not found: {rel_path}")
            continue
        sha, size = sha256_file(abs_path)
        fm_errors: List[str] = []
        fm = parse_frontmatter(abs_path, fm_errors)
        errors.extend(fm_errors)
        files[rel_path] = FileRecord(sha256=sha, size_bytes=size, frontmatter=fm)

    # Build scope dict
    scope_dict: Dict[str, Any] = {
        "family": getattr(scope, "family", ""),
        "platform": getattr(scope, "platform", None),
        "subdomains": list(getattr(scope, "subdomains", [])),
        "files": file_list,
    }

    # Git baseline sha
    baseline_sha = _get_git_sha(repo_root)

    manifest = BaselineManifest(
        run_id=run_id,
        baseline_git_sha=baseline_sha,
        captured_at=datetime.now(timezone.utc).isoformat(),
        scope=scope_dict,
        files=files,
        _errors=errors,
    )

    # Atomic write
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp, output)

    return manifest


def validate_manifest_file(path: pathlib.Path) -> List[str]:
    """Validate a manifest JSON file against the schema. Returns list of error strings."""
    try:
        import jsonschema
    except ImportError:
        return []

    if not _SCHEMA_PATH.exists():
        return []

    try:
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        data = json.loads(path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft7Validator(schema)
        errs = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        return [str(e.message) for e in errs]
    except Exception as e:
        return [str(e)]


def _get_git_sha(repo_root: pathlib.Path) -> str:
    """Get current HEAD SHA via subprocess."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"
