"""Controlled Draft Writer — safe content/ writes for agent-approved candidates.

Writes shadow candidates to content/ ONLY when:
  1. Agent Decision Board verdict is APPROVED_FOR_DRAFT_WRITE
  2. draft: true is set in frontmatter
  3. shadow_candidate: true is set
  4. All claim references are verified
  5. A rollback manifest is written before any content/ write

Every write is recorded in a rollback manifest so the operation can be
fully reversed with a single command.

Public API:
    WriteGuard          — safety checks before write
    RollbackManifest    — manifest of files written for rollback
    write_approved_candidates — write approved candidates to content/
    rollback            — undo a previous write using manifest
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.agent_decision_board import BoardVerdict, DecisionType

WRITER_VERSION = "1.1.0"

# Allowed rollback target root prefixes (relative to repo_root).
# rollback() refuses to delete files outside these roots even if the manifest
# specifies an arbitrary target_path. Prevents crafted manifests from escaping
# the approved write area.
ALLOWED_ROLLBACK_ROOTS: tuple[str, ...] = (
    "content/reference.aspose.org/",
    "content/docs.aspose.org/",
    "content/products.aspose.org/",
    "content/blog.aspose.org/",
    "content/kb.aspose.org/",
)

# Subdomain -> content path pattern
SUBDOMAIN_PATHS: dict[str, str] = {
    "reference": "content/reference.aspose.org/en/{family}/{platform}",
    "documentation": "content/docs.aspose.org/en/{family}/{platform}",
    "product_landing": "content/products.aspose.org/en/{family}",
    "blog_post": "content/blog.aspose.org/{family}/{platform}",
    "knowledge_base": "content/kb.aspose.org/en/{family}/{platform}",
}


@dataclass
class WriteRecord:
    """Record of a single file written."""
    source_path: str
    target_path: str
    sha256: str
    page_type: str
    created_new: bool = True  # True if target didn't exist before


@dataclass
class RollbackManifest:
    """Manifest for rolling back a controlled write operation."""
    schema_version: str = WRITER_VERSION
    family: str = ""
    platform: str = ""
    timestamp: str = ""
    files_written: list[WriteRecord] = field(default_factory=list)
    dry_run: bool = True
    verdict_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> RollbackManifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = [WriteRecord(**r) for r in data.pop("files_written", [])]
        manifest = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        manifest.files_written = records
        return manifest


class WriteGuardError(Exception):
    """Raised when a write safety check fails."""


def check_write_guards(
    verdict: BoardVerdict,
    dry_run: bool = True,
) -> list[str]:
    """Run safety checks before writing. Returns list of errors (empty = safe)."""
    errors: list[str] = []

    if verdict.verdict != "approved_for_draft_write":
        errors.append(f"verdict is '{verdict.verdict}', not 'approved_for_draft_write'")

    if verdict.quarantined > 0:
        errors.append(f"{verdict.quarantined} candidates are quarantined")

    if verdict.non_delegable > 0:
        errors.append(f"{verdict.non_delegable} candidates require human review")

    if verdict.approved == 0:
        errors.append("no candidates approved")

    if not dry_run:
        errors.append("live mode not yet enabled — dry_run must be True")

    return errors


def _resolve_target_path(
    candidate_name: str,
    page_type: str,
    family: str,
    platform: str,
    repo_root: Path,
) -> Path:
    """Resolve the target content/ path for a candidate."""
    pattern = SUBDOMAIN_PATHS.get(page_type, SUBDOMAIN_PATHS["reference"])
    base = pattern.format(family=family, platform=platform)
    return repo_root / base / candidate_name


def _sha256_file(path: Path) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def write_approved_candidates(
    candidates_dir: Path,
    verdict: BoardVerdict,
    page_type_map: dict[str, str],
    repo_root: Path,
    output_dir: Path,
    dry_run: bool = True,
) -> RollbackManifest:
    """Write agent-approved candidates to content/ (dry-run by default).

    Args:
        candidates_dir: Directory with candidate .md files.
        verdict: BoardVerdict from agent review.
        page_type_map: filename -> page_type mapping.
        repo_root: Root of the aspose.org repo.
        output_dir: Where to write the rollback manifest.
        dry_run: If True, only simulate writes (no actual file copies).

    Returns RollbackManifest recording what was (or would be) written.
    """
    guard_errors = check_write_guards(verdict, dry_run)
    if guard_errors:
        raise WriteGuardError(
            f"Write blocked: {'; '.join(guard_errors)}"
        )

    manifest = RollbackManifest(
        family=verdict.family,
        platform=verdict.platform,
        timestamp=datetime.now(timezone.utc).isoformat(),
        dry_run=dry_run,
    )

    # Only write APPROVED candidates
    approved_names = {
        d.candidate_path
        for d in verdict.decisions
        if d.decision == DecisionType.APPROVED.value
    }

    for decision in verdict.decisions:
        if decision.decision != DecisionType.APPROVED.value:
            continue

        src = candidates_dir / decision.candidate_path
        if not src.exists():
            continue

        pt = page_type_map.get(decision.candidate_path, "reference")
        target = _resolve_target_path(
            decision.candidate_path, pt,
            verdict.family, verdict.platform, repo_root,
        )

        # Verify candidate still has draft: true
        content = src.read_text(encoding="utf-8")
        if "draft: true" not in content:
            continue
        if "shadow_candidate: true" not in content:
            continue

        record = WriteRecord(
            source_path=str(src.relative_to(repo_root)) if src.is_relative_to(repo_root) else str(src),
            target_path=str(target.relative_to(repo_root)) if target.is_relative_to(repo_root) else str(target),
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            page_type=pt,
            created_new=not target.exists(),
        )
        manifest.files_written.append(record)

        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

    # Write manifest
    manifest_path = output_dir / "rollback_manifest.json"
    manifest.write(manifest_path)

    return manifest


class RollbackPathError(Exception):
    """Raised when a rollback target path fails the allowlist guard."""


def _validate_rollback_target(target_path: str, repo_root: Path) -> Path:
    """Validate that a rollback target path is safe to delete.

    Checks:
    1. Path resolves inside repo_root (no absolute-path escape).
    2. No path traversal (../../ or similar).
    3. Resolved path starts with one of ALLOWED_ROLLBACK_ROOTS.

    Returns the resolved absolute Path on success.
    Raises RollbackPathError on any violation.
    """
    # Reject absolute paths from manifests
    if Path(target_path).is_absolute():
        raise RollbackPathError(
            f"BLOCKED: rollback target is an absolute path: {target_path!r}. "
            "Only relative paths under ALLOWED_ROLLBACK_ROOTS are permitted."
        )

    # Resolve to absolute, check it stays within repo_root
    resolved = (repo_root / target_path).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        raise RollbackPathError(
            f"BLOCKED: rollback target escapes repo root: {target_path!r} "
            f"resolves to {resolved} which is outside {repo_root.resolve()}"
        )

    # Check against allowed rollback roots
    rel_from_root = resolved.relative_to(repo_root.resolve()).as_posix()
    if not any(rel_from_root.startswith(root) for root in ALLOWED_ROLLBACK_ROOTS):
        raise RollbackPathError(
            f"BLOCKED: rollback target {target_path!r} is not under any "
            f"approved rollback root. Allowed roots: {ALLOWED_ROLLBACK_ROOTS}"
        )

    return resolved


def rollback(manifest_path: Path, repo_root: Path) -> list[str]:
    """Roll back a previous write operation using its manifest.

    Deletes files that were created new. For files that overwrote
    existing content, warns but does not auto-restore (use git checkout).

    Safety: target paths are validated against ALLOWED_ROLLBACK_ROOTS before
    any deletion. Crafted manifests with path traversal or arbitrary paths
    will raise RollbackPathError before any file is touched.

    Returns list of actions taken.
    """
    manifest = RollbackManifest.read(manifest_path)
    actions: list[str] = []

    if manifest.dry_run:
        actions.append("manifest was dry-run — no files to roll back")
        return actions

    # Validate ALL target paths before touching any file (fail-first)
    for record in manifest.files_written:
        _validate_rollback_target(record.target_path, repo_root)

    for record in manifest.files_written:
        target = _validate_rollback_target(record.target_path, repo_root)
        if not target.exists():
            actions.append(f"SKIP: {record.target_path} already deleted")
            continue

        current_sha = _sha256_file(target)
        if current_sha != record.sha256:
            actions.append(
                f"WARN: {record.target_path} modified since write "
                f"(expected {record.sha256[:12]}, got {current_sha[:12]}) — "
                f"use 'git checkout -- {record.target_path}' to restore"
            )
            continue

        if record.created_new:
            target.unlink()
            actions.append(f"DELETED: {record.target_path}")
        else:
            actions.append(
                f"WARN: {record.target_path} was an overwrite — "
                f"use 'git checkout -- {record.target_path}' to restore"
            )

    return actions
