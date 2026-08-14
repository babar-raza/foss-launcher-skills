"""bundle_manifest.py — provenance schema v2: generator fingerprint + bundle manifest.

CONTRACT: scripts/pipeline/lib/bundle_manifest.py
  purpose: Root-cause fix FRESH-001 (2026-08-14, cells/net stale-facts incident) needs
           two things promote.py's old model.yaml never provided: (1) a signal broad
           enough to catch real pipeline-logic drift (the old config_sha covered only
           4 narrow extractor-config dicts), and (2) an atomicity boundary tying
           model.yaml + api_surface.json + formats.md/.json + claims.json together as
           ONE bundle with one shared repo_sha/timestamp, so partial promote() failures
           can never leave siblings representing different source revisions without
           anyone noticing. This module is the pure, hash-computing half of that fix;
           promote.py (the writer) and freshness_guard.py / promote_recover.py (the
           readers) are the only intended consumers — 3, meeting PIPELINE.md's lib/
           extraction threshold.
  hashing recipe: generator_fingerprint() reuses the EXACT algorithm already proven in
           lib/freshness_manifest.py's compute_output_content_hash() (sorted relative
           path + line-ending-normalized content, sha256) rather than inventing a new
           convention — that function hashes an implicit directory walk; this one hashes
           an explicit curated file list (GENERATOR_FINGERPRINT_PATHS), so it cannot be
           the same function call, but it is the same algorithm.
  atomicity boundary: bundle_manifest.json's presence with status == "COMPLETE" is what
           promote.py (T3, staged-then-swap promotion) and freshness_guard.py (T6) treat
           as proof a bundle is self-consistent. Its absence, or any other status, means
           "treat the whole bundle as PROVENANCE_MISSING", regardless of what individual
           sibling files independently claim.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Generator fingerprint
# ---------------------------------------------------------------------------

# Explicit, versioned list of pipeline files whose changes should count as "the
# generator changed" for freshness purposes. Deliberately NOT a whole-repo dirty
# check (too broad -- unrelated pipeline work would falsely flag every product as
# stale) and NOT as narrow as the old config_sha (which missed real extraction-logic
# edits). Paths are relative to the pipeline repo root.
GENERATOR_FINGERPRINT_PATHS: tuple[str, ...] = (
    "scripts/pipeline/commands/knowledge/promote.py",
    "scripts/pipeline/commands/knowledge/scout.py",
    "scripts/pipeline/commands/knowledge/enrich.py",
    "scripts/pipeline/extraction/formats.py",
    "scripts/pipeline/extraction/scout.py",
)

# Manually-bumped, human-meaningful advisory version. Not authoritative by itself --
# generator_fingerprint() is the machine-checked signal; this exists for changelog-style
# readability in model.yaml and operator reports. Bump when GENERATOR_FINGERPRINT_PATHS
# or the bundle schema itself changes shape.
GENERATOR_SEMVER = "2.0.0"

BUNDLE_SCHEMA_VERSION = 2

# Member files a complete bundle is expected to contain, relative to merged/. Not all
# products populate every optional file (e.g. install.md/limitations.md can be nearly
# empty for a simple product) -- compute_bundle_manifest() hashes whichever of these
# exist and records which were absent, rather than failing on absence.
BUNDLE_MEMBER_FILES: tuple[str, ...] = (
    "model.yaml",
    "api_surface.json",
    "api_surface.md",
    "formats.json",
    "formats.md",
    "claims.json",
    "limitations.md",
    "install.md",
    "merge_report.md",
)


def _hash_file_list(repo_root: Path, rel_paths: "tuple[str, ...] | list[str]") -> str:
    """sha256 over sorted(rel_path) -> "<relpath>\\n<content>\\n", line-endings
    normalized. Same algorithm as freshness_manifest.compute_output_content_hash();
    applied to an explicit file list instead of a directory walk. Missing files are
    hashed as an empty byte string under their path so a deleted tracked file still
    changes the fingerprint (rather than being silently skipped)."""
    h = hashlib.sha256()
    for rel in sorted(rel_paths):
        rel_norm = rel.replace("\\", "/")
        h.update(rel_norm.encode("utf-8"))
        h.update(b"\n")
        fpath = repo_root / rel_norm
        if fpath.is_file():
            content = fpath.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        else:
            content = b""
        h.update(content)
        h.update(b"\n")
    return h.hexdigest()


def generator_fingerprint(repo_root: Path) -> str:
    """Return a sha256 hex digest over GENERATOR_FINGERPRINT_PATHS' current content.

    Changes iff a tracked pipeline file's content changes. Used as model.yaml's
    generator_fingerprint field so a bundle can prove which version of the extraction/
    enrichment/merge logic produced it, independent of which source commit was scouted.
    """
    return _hash_file_list(repo_root, GENERATOR_FINGERPRINT_PATHS)


# ---------------------------------------------------------------------------
# Bundle manifest
# ---------------------------------------------------------------------------


def compute_bundle_manifest(
    merged_dir: Path,
    *,
    family: str,
    platform: str,
    repo_sha: str,
    bundle_id: str,
    generated_at: str,
    generator_fingerprint_value: "str | None" = None,
    promote_run_id: "str | None" = None,
    repo_root: "Path | None" = None,
) -> dict[str, Any]:
    """Compute the bundle manifest dict for a promoted knowledge bundle.

    Pure function -- does not write anything. Hashes each file in BUNDLE_MEMBER_FILES
    that exists under merged_dir (plus merged/snippets/** if present, since snippets
    are part of the tracked fact bundle per AGENTS.md §11). Files that don't exist for
    this product are recorded with sha256=None so the manifest is honest about what it
    actually covers, rather than silently omitting the key.

    status is always "COMPLETE" here -- the caller (promote.py) is responsible for only
    writing this manifest to disk once every member has actually been written; an
    in-progress bundle should not have a bundle_manifest.json at all (its absence is
    itself the "not yet complete" signal consumers rely on).
    """
    members: dict[str, dict[str, Any]] = {}
    for name in BUNDLE_MEMBER_FILES:
        fpath = merged_dir / name
        if fpath.is_file():
            data = fpath.read_bytes()
            members[name] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        else:
            members[name] = {"sha256": None, "bytes": 0}

    snippets_dir = merged_dir / "snippets"
    if snippets_dir.is_dir():
        for fpath in sorted(snippets_dir.rglob("*")):
            if not fpath.is_file():
                continue
            rel = "snippets/" + str(fpath.relative_to(snippets_dir)).replace("\\", "/")
            data = fpath.read_bytes()
            members[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    if generator_fingerprint_value is None and repo_root is not None:
        generator_fingerprint_value = generator_fingerprint(repo_root)

    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "family": family,
        "platform": platform,
        "repo_sha": repo_sha,
        "generated_at": generated_at,
        "generator_fingerprint": generator_fingerprint_value,
        "generator_semver": GENERATOR_SEMVER,
        "members": members,
        "promote_run_id": promote_run_id,
        "status": "COMPLETE",
    }


def verify_bundle_manifest(merged_dir: Path, manifest: dict[str, Any]) -> list[str]:
    """Recompute member hashes from merged_dir and compare against *manifest*.

    Returns a list of mismatch descriptions (empty list = bundle is self-consistent).
    Used by promote.py's post-swap self-check and by freshness_guard.py's strict mode.
    Does not raise -- callers decide what a non-empty mismatch list means for their
    freshness state.
    """
    mismatches: list[str] = []
    recorded_members = manifest.get("members", {})
    for name, recorded in recorded_members.items():
        fpath = merged_dir / name
        recorded_sha = recorded.get("sha256")
        if not fpath.is_file():
            if recorded_sha is not None:
                mismatches.append(f"{name}: recorded sha256 but file is missing on disk")
            continue
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if recorded_sha is None:
            mismatches.append(f"{name}: file exists on disk but manifest recorded no hash")
        elif actual_sha != recorded_sha:
            mismatches.append(f"{name}: sha256 mismatch (recorded {recorded_sha[:12]}..., actual {actual_sha[:12]}...)")
    return mismatches
