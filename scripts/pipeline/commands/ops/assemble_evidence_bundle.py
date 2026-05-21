"""Assemble an evidence bundle for a product family/platform.

Usage:
    python scripts/pipeline/commands/ops/assemble_evidence_bundle.py \\
        --family FAMILY --platform PLATFORM --out-dir PATH [--dry-run]

What it does:
    1. HEAD SHA validation gate (TC-HCR-009):
       - Reads current git HEAD SHA.
       - Reads knowledge/{family}/{platform}/merged/model.yaml repo_sha.
       - Warns (does not fail) if HEAD SHA != model.yaml repo_sha (different repos expected).
       - Scans content/{blog,docs,kb,reference}.aspose.org/{family}/{platform}/ for
         evidence.model_sha in frontmatter; reports any that differ from model.yaml repo_sha
         as stale.
    2. Bundles these artifacts into {out_dir}/evidence-bundle-{family}-{platform}-{date}.zip:
       - knowledge/{family}/{platform}/merged/model.yaml
       - knowledge/{family}/{platform}/merged/api_surface.md
       - knowledge/{family}/{platform}/merged/claims.json (first 100 claims max)
       - reports/audit/batch-audit-*.md (most recent)
       - reports/content_eval/eval-*.json (most recent, if exists)
    3. Writes a manifest JSON to {out_dir}/bundle-manifest.json with file list,
       SHA256 hashes, and HEAD SHA.
    4. Prints a summary: files bundled, total size, any SHA warnings.

Exit codes:
    0  bundle created (or dry-run printed) without errors
    1  fatal error (missing required knowledge artifacts, bad arguments)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap — ensure pipeline lib/ and root are importable
# ---------------------------------------------------------------------------

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from core.env_loader import load_env  # noqa: E402
load_env()

# ---------------------------------------------------------------------------
# Repo-root derived paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, KNOWLEDGE_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _REPO_ROOT
    KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git_head_sha(repo_root: Path) -> str | None:
    """Return the current HEAD SHA of the git repo, or None on error."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_yaml_simple(path: Path) -> dict:
    """Load a YAML file.  Tries PyYAML; falls back to manual key:value parse."""
    try:
        import yaml  # type: ignore[import]
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except ImportError:
        # Manual fallback: read top-level simple key: value lines only
        data: dict = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if ":" in line and not line.startswith(" ") and not line.startswith("-"):
                    k, _, v = line.partition(":")
                    data[k.strip()] = v.strip().strip("'\"")
        return data


def _read_frontmatter_model_sha(md_path: Path) -> str | None:
    """Extract evidence.model_sha from a Markdown frontmatter block.

    Reads lines between the first two '---' delimiters and looks for
    the indented ``model_sha:`` key under an ``evidence:`` section.
    """
    try:
        with open(md_path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    if not lines or lines[0].strip() != "---":
        return None

    # Collect frontmatter lines
    fm_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        fm_lines.append(line)

    in_evidence = False
    for line in fm_lines:
        stripped = line.strip()
        if stripped.startswith("evidence:"):
            in_evidence = True
            continue
        if in_evidence:
            if stripped.startswith("model_sha:"):
                return stripped.split(":", 1)[1].strip().strip("'\"")
            # Stop if we leave the evidence block (non-indented key)
            if line and not line[0].isspace():
                break
    return None


def _collect_content_shas(family: str, platform: str) -> list[tuple[Path, str | None]]:
    """Return list of (md_file, model_sha_or_None) for content pages."""
    sites = [
        REPO_ROOT / "content" / "blog.aspose.org" / family / platform,
        REPO_ROOT / "content" / "docs.aspose.org" / "en" / family / platform,
        REPO_ROOT / "content" / "kb.aspose.org" / "en" / family / platform,
        REPO_ROOT / "content" / "reference.aspose.org" / "en" / family / platform,
    ]
    results: list[tuple[Path, str | None]] = []
    for site_dir in sites:
        if not site_dir.is_dir():
            continue
        for md in sorted(site_dir.rglob("*.md")):
            if md.name.startswith("_"):
                continue
            sha = _read_frontmatter_model_sha(md)
            results.append((md, sha))
            if len(results) >= 50:  # sample cap to avoid slowdowns on large products
                break
    return results


def _most_recent_file(directory: Path, glob_pattern: str) -> Path | None:
    """Return the most recently modified file matching glob_pattern in directory."""
    if not directory.is_dir():
        return None
    candidates = sorted(directory.glob(glob_pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _truncate_claims_json(src: Path, max_claims: int = 100) -> bytes:
    """Return serialized bytes of at most *max_claims* entries from claims.json."""
    try:
        data = json.loads(src.read_bytes())
        if isinstance(data, list) and len(data) > max_claims:
            data = data[:max_claims]
        return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    except Exception:
        return src.read_bytes()


# ---------------------------------------------------------------------------
# Core bundle logic
# ---------------------------------------------------------------------------

def assemble_bundle(
    *,
    family: str,
    platform: str,
    out_dir: Path,
    dry_run: bool = False,
) -> int:
    """Assemble evidence bundle.  Returns 0 on success, 1 on error."""

    knowledge_dir = KNOWLEDGE_ROOT / family / platform / "merged"
    model_yaml_path = knowledge_dir / "model.yaml"
    api_surface_path = knowledge_dir / "api_surface.md"
    claims_path = knowledge_dir / "claims.json"

    # Hard requirement: model.yaml must exist
    if not model_yaml_path.is_file():
        print(
            f"ERROR: knowledge/{family}/{platform}/merged/model.yaml not found. "
            "Run /repo-scout and /truth-merge first.",
            file=sys.stderr,
        )
        return 1

    # Load model.yaml
    model_data = _load_yaml_simple(model_yaml_path)
    model_repo_sha: str = model_data.get("repo_sha", "") or ""

    # -----------------------------------------------------------------------
    # HEAD SHA validation gate (TC-HCR-009)
    # -----------------------------------------------------------------------
    sha_warnings: list[str] = []

    head_sha = _git_head_sha(REPO_ROOT)
    if head_sha is None:
        sha_warnings.append("WARN: could not determine git HEAD SHA")
    else:
        if model_repo_sha and head_sha != model_repo_sha:
            sha_warnings.append(
                f"WARN: HEAD SHA ({head_sha[:12]}...) differs from model.yaml repo_sha "
                f"({model_repo_sha[:12]}...) — expected (different repos)"
            )

    # Check content page evidence.model_sha
    content_shas = _collect_content_shas(family, platform)
    stale_pages: list[Path] = []
    for md_path, page_sha in content_shas:
        if page_sha is None:
            continue  # no evidence block; not a SHA mismatch
        if model_repo_sha and page_sha != model_repo_sha:
            stale_pages.append(md_path)

    if stale_pages:
        sha_warnings.append(
            f"WARN: {len(stale_pages)} content page(s) have stale evidence.model_sha "
            f"(expected {model_repo_sha[:12] if model_repo_sha else 'N/A'}...):"
        )
        for p in stale_pages[:10]:
            sha_warnings.append(f"  stale: {p.relative_to(REPO_ROOT)}")
        if len(stale_pages) > 10:
            sha_warnings.append(f"  ... and {len(stale_pages) - 10} more")

    # -----------------------------------------------------------------------
    # Collect artifacts
    # -----------------------------------------------------------------------
    # Artifact list: (archive_name, path_or_None, raw_bytes_or_None)
    # raw_bytes is used for truncated claims.json

    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    bundle_name = f"evidence-bundle-{family}-{platform}-{today}.zip"

    artifacts: list[tuple[str, Path | None, bytes | None]] = []

    # knowledge artifacts
    artifacts.append(("knowledge/model.yaml", model_yaml_path, None))

    if api_surface_path.is_file():
        artifacts.append(("knowledge/api_surface.md", api_surface_path, None))
    else:
        sha_warnings.append(
            f"WARN: knowledge/{family}/{platform}/merged/api_surface.md not found; skipping"
        )

    if claims_path.is_file():
        artifacts.append(("knowledge/claims.json", claims_path, _truncate_claims_json(claims_path)))
    else:
        sha_warnings.append(
            f"WARN: knowledge/{family}/{platform}/merged/claims.json not found; skipping"
        )

    # most recent batch-audit report
    audit_dir = REPO_ROOT / "reports" / "audit"
    recent_audit = _most_recent_file(audit_dir, "batch-audit-*.md")
    if recent_audit:
        artifacts.append((f"reports/audit/{recent_audit.name}", recent_audit, None))
    else:
        sha_warnings.append("WARN: no batch-audit-*.md found in reports/audit/; skipping")

    # most recent content_eval report
    eval_dir = REPO_ROOT / "reports" / "content_eval"
    recent_eval = _most_recent_file(eval_dir, "eval-*.json")
    if recent_eval:
        artifacts.append((f"reports/content_eval/{recent_eval.name}", recent_eval, None))
    else:
        sha_warnings.append("INFO: no eval-*.json found in reports/content_eval/; skipping")

    # -----------------------------------------------------------------------
    # Print summary / dry-run
    # -----------------------------------------------------------------------
    print(f"Evidence bundle: {bundle_name}")
    print(f"  family={family}  platform={platform}")
    print(f"  head_sha={head_sha or 'unknown'}")
    print(f"  model_repo_sha={model_repo_sha or 'unknown'}")
    print(f"  content pages sampled: {len(content_shas)}  stale: {len(stale_pages)}")
    print()
    for w in sha_warnings:
        print(w)
    if sha_warnings:
        print()

    print(f"Artifacts to bundle ({len(artifacts)}):")
    for arc_name, path, raw in artifacts:
        size = len(raw) if raw is not None else (path.stat().st_size if path else 0)
        print(f"  {arc_name}  ({size:,} bytes)")

    if dry_run:
        print()
        print("DRY-RUN: no files written.")
        return 0

    # -----------------------------------------------------------------------
    # Write bundle
    # -----------------------------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = out_dir / bundle_name
    manifest_path = out_dir / "bundle-manifest.json"

    manifest_files: list[dict] = []
    total_bytes = 0

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc_name, path, raw in artifacts:
            if raw is not None:
                data = raw
            elif path and path.is_file():
                data = path.read_bytes()
            else:
                continue
            zf.writestr(arc_name, data)
            file_sha256 = hashlib.sha256(data).hexdigest()
            total_bytes += len(data)
            manifest_files.append(
                {
                    "name": arc_name,
                    "size_bytes": len(data),
                    "sha256": file_sha256,
                }
            )

    # Write manifest JSON
    manifest = {
        "bundle": bundle_name,
        "family": family,
        "platform": platform,
        "assembled_at": datetime.now(tz=timezone.utc).isoformat(),
        "head_sha": head_sha,
        "model_repo_sha": model_repo_sha or None,
        "sha_warnings": sha_warnings,
        "stale_content_pages": [str(p.relative_to(REPO_ROOT)) for p in stale_pages],
        "files": manifest_files,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    bundle_kb = bundle_path.stat().st_size / 1024
    print()
    print(f"OK  Wrote {bundle_path.relative_to(REPO_ROOT)}")
    print(f"    {len(manifest_files)} files  total uncompressed {total_bytes:,} bytes  "
          f"zip size {bundle_kb:.1f} KB")
    print(f"    Manifest: {manifest_path.relative_to(REPO_ROOT)}")
    if sha_warnings:
        print(f"    {len(sha_warnings)} SHA warning(s) — see manifest sha_warnings")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True, help="Product family (e.g. cells)")
    parser.add_argument("--platform", required=True, help="Platform (e.g. net)")
    parser.add_argument("--out-dir", required=True, help="Output directory for bundle and manifest")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be bundled without writing files")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir

    return assemble_bundle(
        family=args.family,
        platform=args.platform,
        out_dir=out_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
