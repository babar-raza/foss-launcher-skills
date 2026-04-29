"""provenance_backfill.py — Backfill provenance metadata for existing .md files.

Scans all content/ .md files and writes a provenance block for files that
lack one.  Idempotent — safe to re-run; files that already have provenance
are skipped.

For English files:
    content_origin: unknown
    content_created_at: <ISO-8601 UTC from git first-commit if available>
    last_mechanism: unknown
    auto_updatable: true

For locale files:
    translation_origin: unknown
    source_file: <derived from path>
    source_sha: <computed from current English source>
    last_mechanism: unknown
    auto_updatable: true

Usage:
    python scripts/pipeline/provenance_backfill.py [--dry-run] [--family FAMILY] [--platform PLATFORM]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent.parent

sys.path.insert(0, str(_HERE.parent.parent.parent.parent))  # scripts/pipeline/
_LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import provenance as _prov  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONTENT_ROOT = _REPO_ROOT / "content"

_SITES = [
    "docs.aspose.org",
    "kb.aspose.org",
    "products.aspose.org",
    "reference.aspose.org",
    "blog.aspose.org",
]

# Detect locale files: directory-based (/ar/, /bg/, etc.) or filename-based (index.fa.md)
_LOCALE_DIR_RE = re.compile(
    r"/(?:ar|bg|ca|cs|da|de|el|es|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sr|sv|th|tr|uk|vi|zh)/"
)
_LOCALE_FILE_RE = re.compile(
    r"\.(?:ar|bg|ca|cs|da|de|el|es|fa|fi|fr|he|hi|hr|hu|id|it|ja|ko|lt|lv|ms|nl|no|pl|pt|ro|ru|sk|sr|sv|th|tr|uk|vi|zh)\.md$"
)


def _is_locale_file(path: Path) -> bool:
    """Return True if the file is a locale (non-English) translation."""
    path_str = str(path).replace("\\", "/")
    return bool(_LOCALE_DIR_RE.search(path_str) or _LOCALE_FILE_RE.search(path_str))


def _derive_english_source(locale_path: Path) -> Path | None:
    """Derive the English source file from a locale file path."""
    path_str = str(locale_path).replace("\\", "/")

    # Blog: filename-based (index.fa.md → index.md)
    if "blog.aspose.org" in path_str:
        m = _LOCALE_FILE_RE.search(path_str)
        if m:
            en_str = path_str[:m.start()] + ".md"
            return Path(en_str)
        return None

    # All other sites: directory-based (/ar/ → /en/)
    m = _LOCALE_DIR_RE.search(path_str)
    if m:
        lang = m.group(0).strip("/")
        en_str = path_str.replace(f"/{lang}/", "/en/", 1)
        return Path(en_str)
    return None


def _git_first_commit_date(filepath: Path) -> str | None:
    """Return ISO-8601 UTC date of the first git commit that added *filepath*.

    Uses ``git log --diff-filter=A --follow --format="%aI"`` to find the
    commit that first introduced the file.  Returns None if git is unavailable,
    the file has no history, or any error occurs.
    """
    try:
        result = subprocess.run(
            [
                "git", "log",
                "--diff-filter=A",
                "--follow",
                "--format=%aI",
                "--",
                str(filepath),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=_REPO_ROOT,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        # Return the last line (oldest commit) in case of renames
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        return lines[-1] if lines else None
    except Exception:
        return None


def _source_rel(english_path: Path) -> str:
    """Return source_file as a content-root-relative path.

    The canonical format omits the leading ``content/`` prefix so it matches
    the format written by the translator (e.g.
    ``docs.aspose.org/en/3d/python/_index.md``).
    """
    try:
        return str(english_path.relative_to(_CONTENT_ROOT)).replace("\\", "/")
    except ValueError:
        pass
    # Fallback: strip content/ prefix if present in the absolute path
    try:
        rel = str(english_path.relative_to(_REPO_ROOT)).replace("\\", "/")
        if rel.startswith("content/"):
            return rel[len("content/"):]
        return rel
    except ValueError:
        return str(english_path).replace("\\", "/")


def backfill(
    family: str | None = None,
    platform: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Backfill provenance for all content .md files.

    Returns stats dict: {backfilled, skipped, errors, locale_no_source}.
    """
    stats = {"backfilled": 0, "skipped": 0, "errors": 0, "locale_no_source": 0}

    for site in _SITES:
        site_root = _CONTENT_ROOT / site
        if not site_root.exists():
            continue

        for md_file in sorted(site_root.rglob("*.md")):
            # Filter by family/platform if specified
            rel = str(md_file.relative_to(site_root)).replace("\\", "/")
            if family and f"/{family}/" not in f"/{rel}":
                # Check if family appears in the path
                parts = rel.split("/")
                if family not in parts:
                    continue
            if platform and f"/{platform}/" not in f"/{rel}":
                parts = rel.split("/")
                if platform not in parts:
                    continue

            # Skip if provenance already exists
            existing = _prov.read_provenance(md_file)
            if existing is not None:
                stats["skipped"] += 1
                continue

            try:
                if _is_locale_file(md_file):
                    en_source = _derive_english_source(md_file)
                    if en_source is None or not en_source.exists():
                        stats["locale_no_source"] += 1
                        prov_dict = {
                            "translation_origin": "unknown",
                            "last_mechanism": "unknown",
                            "auto_updatable": True,
                        }
                    else:
                        prov_dict = {
                            "translation_origin": "unknown",
                            "source_file": _source_rel(en_source),
                            "source_sha": _prov.compute_source_sha(en_source),
                            "last_mechanism": "unknown",
                            "auto_updatable": True,
                        }
                else:
                    # English source file
                    prov_dict = {
                        "content_origin": "unknown",
                        "last_mechanism": "unknown",
                        "auto_updatable": True,
                    }
                    # Set content_created_at from git history (write-once; only on
                    # first provenance block creation — existing blocks are skipped
                    # by the idempotency guard above).
                    created_at = _git_first_commit_date(md_file)
                    if created_at:
                        prov_dict["content_created_at"] = created_at

                if not dry_run:
                    _prov.write_provenance(md_file, prov_dict)
                stats["backfilled"] += 1

            except Exception as exc:
                print(f"  ERROR {md_file}: {exc}", file=sys.stderr)
                stats["errors"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Backfill provenance metadata for existing .md content files"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Count files without writing")
    parser.add_argument("--family", help="Filter by product family (e.g. 3d)")
    parser.add_argument("--platform", help="Filter by platform (e.g. python)")
    args = parser.parse_args()

    print(f"Provenance backfill: {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.family:
        print(f"  Family filter: {args.family}")
    if args.platform:
        print(f"  Platform filter: {args.platform}")

    stats = backfill(
        family=args.family,
        platform=args.platform,
        dry_run=args.dry_run,
    )

    print(f"\nResults:")
    print(f"  Backfilled:      {stats['backfilled']}")
    print(f"  Skipped (exists): {stats['skipped']}")
    print(f"  Locale no source: {stats['locale_no_source']}")
    print(f"  Errors:          {stats['errors']}")

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()