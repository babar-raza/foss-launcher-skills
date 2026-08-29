"""llms_stale.py -- detect stale/missing llms-output pages via a content-hash manifest.

Generalized from aspose.org's S-LG-05 llms-stale skill (ported as
TASK_BACKLOG.md SYNC-7). Compares each eligible source .md page's sha256
hash against a provenance manifest to detect STALE (source changed since
last generation) or MISSING (output .txt deleted) pages.

Manifest location: config.yaml's reports_path (default "reports/") +
"llms-manifest.json". No new config key needed -- reuses the existing
reports_path resolution already used across this repo.

Usage:
    .venv/bin/python scripts/llms_generate.py --output llms-output
    .venv/bin/python scripts/llms_stale.py --output llms-output --update-manifest
    .venv/bin/python scripts/llms_stale.py --output llms-output --check-only

Exit codes (--check-only):
  0 -- no stale or missing pages
  1 -- at least one stale or missing page
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config, resolve_content_repo, resolve_reports_root, ConfigError
from llms_common import is_eligible_page, iter_site_pages, parse_frontmatter


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest_path(reports_root: Path) -> Path:
    return reports_root / "llms-manifest.json"


def load_manifest(reports_root: Path) -> dict:
    path = manifest_path(reports_root)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_current_hashes(content_root: Path, sites: dict) -> dict:
    """Return {site_type: {relative_source_path: sha256}} for every eligible page."""
    current: dict = {}
    for site_type, site_cfg in sorted(sites.items()):
        if "content_path" not in site_cfg:
            continue
        hashes = {}
        for source_path in iter_site_pages(content_root, site_cfg["content_path"]):
            text = source_path.read_text(encoding="utf-8", errors="replace")
            frontmatter, _ = parse_frontmatter(text)
            if not is_eligible_page(frontmatter):
                continue
            rel = source_path.relative_to(content_root).as_posix()
            hashes[rel] = _sha256(text)
        current[site_type] = hashes
    return current


def diff_against_manifest(current_hashes: dict, manifest: dict, output_root: Path) -> dict:
    """Returns {site_type: {"stale": [...], "missing": [...], "new": [...]}}."""
    result = {}
    for site_type, hashes in current_hashes.items():
        prior = manifest.get(site_type, {})
        stale = []
        missing = []
        new = []
        for rel, sha in hashes.items():
            prior_sha = prior.get(rel)
            output_file = output_root / site_type / Path(rel).with_suffix(".txt")
            if prior_sha is None:
                new.append(rel)
            elif prior_sha != sha:
                stale.append(rel)
            if prior_sha is not None and not output_file.is_file():
                missing.append(rel)
        result[site_type] = {"stale": sorted(stale), "missing": sorted(set(missing)), "new": sorted(new)}
    return result


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="llms-output", help="llms-output directory")
    parser.add_argument("--update-manifest", action="store_true", help="Write the current-state manifest")
    parser.add_argument("--check-only", action="store_true", help="Compare against the existing manifest; exit 1 on issues")
    parser.add_argument("--content-root", default=None, help="Override content root")
    args = parser.parse_args(argv)

    try:
        config = load_config()
        content_root = Path(args.content_root) if args.content_root else resolve_content_repo()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    sites = config.get("sites", {})
    reports_root = resolve_reports_root()
    output_root = Path(args.output)

    current_hashes = build_current_hashes(content_root, sites)

    # Compute the check ONCE, against the manifest as it stood BEFORE any
    # update below -- "check + update in one pass" means "report what was
    # stale THIS run, then refresh the manifest for next time", not
    # "compare the manifest against itself after updating it" (which would
    # trivially always report clean).
    any_issue = False
    if args.check_only:
        prior_manifest = load_manifest(reports_root)
        diff = diff_against_manifest(current_hashes, prior_manifest, output_root)
        for site_type, d in diff.items():
            if d["stale"] or d["missing"]:
                any_issue = True
            print(f"{site_type}: {len(d['stale'])} stale, {len(d['missing'])} missing, {len(d['new'])} new")
            for rel in d["stale"]:
                print(f"  STALE:   {rel}")
            for rel in d["missing"]:
                print(f"  MISSING: {rel}")
        if not any_issue:
            print("Clean: no stale or missing pages.")

    if args.update_manifest:
        path = manifest_path(reports_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current_hashes, indent=2), encoding="utf-8")
        print(f"Manifest updated: {path}")

    if args.check_only:
        return 1 if any_issue else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
