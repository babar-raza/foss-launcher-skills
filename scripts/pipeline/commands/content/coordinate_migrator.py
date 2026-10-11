"""
coordinate_migrator.py — TC-04: Apply coordinate changes to English content pages.

Handles COORDINATE_CHANGE events from manifest_delta.json by locating and replacing
package coordinates (groupId, artifactId, package_name, canonical_import) inside
fenced code blocks only.

Prose mentions of old coordinates: emitted as HUMAN_REVIEW_REQUIRED (historical
references in prose may be valid and require human judgement).

English-only enforcement: uses _target_locale_verdict() from body_refresh.py.

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.content.coordinate_migrator cells java
    PYTHONPATH=scripts/pipeline python -m commands.content.coordinate_migrator cells java --dry-run
    PYTHONPATH=scripts/pipeline python -m commands.content.coordinate_migrator cells java --execute
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import json
import re
from datetime import datetime, timezone
from typing import Any

# ── Path constants ─────────────────────────────────────────────────────────

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
_CONTENT_ROOT = _REPO_ROOT / "content"
_REPORTS_ROOT = _REPO_ROOT / "reports"

# ── Configuration seam ─────────────────────────────────────────────────────


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Reconfigure module paths (used by tests)."""
    global _REPO_ROOT, _KNOWLEDGE_ROOT, _CONTENT_ROOT, _REPORTS_ROOT
    if repo_root is not None:
        _REPO_ROOT = Path(repo_root)
        _KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
        _CONTENT_ROOT = _REPO_ROOT / "content"
        _REPORTS_ROOT = _REPO_ROOT / "reports"


# ── Result constants ────────────────────────────────────────────────────────

R_MIGRATED = "COORDINATE_MIGRATED"
R_NOOP = "NOOP_NO_OLD_COORDINATE"
R_SKIPPED_LOCALE = "SKIPPED_LOCALE"
R_SKIPPED_NO_CHANGE = "SKIPPED_NO_CHANGE_IN_BLOCKS"
R_HUMAN_REVIEW = "HUMAN_REVIEW_REQUIRED"
R_DRY_RUN = "DRY_RUN"
R_NO_MANIFEST_DELTA = "NO_MANIFEST_DELTA"
R_NO_COORDINATE_EVENTS = "NO_COORDINATE_EVENTS"


# ── Fenced code block extraction ────────────────────────────────────────────


def _extract_fenced_ranges(content: str) -> list[tuple[int, int]]:
    """Return list of (start, end) character ranges for all fenced code blocks.

    Both ``` and ~~~ fences are recognised.
    """
    ranges: list[tuple[int, int]] = []
    pattern = re.compile(r"(```[^\n]*\n.*?```|~~~[^\n]*\n.*?~~~)", re.DOTALL)
    for m in pattern.finditer(content):
        ranges.append((m.start(), m.end()))
    return ranges


def _replace_in_code_blocks(content: str, old: str, new: str) -> tuple[str, int]:
    """Replace *old* with *new* inside every fenced code block.

    Returns (updated_content, replacement_count).
    Code-blocks-only: prose between blocks is never touched.
    """
    if not old or old == new:
        return content, 0

    fenced_ranges = _extract_fenced_ranges(content)
    if not fenced_ranges:
        return content, 0

    # Build updated content segment by segment (last-to-first to preserve offsets)
    result = content
    count = 0
    for start, end in reversed(fenced_ranges):
        block = result[start:end]
        if old in block:
            new_block = block.replace(old, new)
            result = result[:start] + new_block + result[end:]
            count += block.count(old)
    return result, count


def _find_prose_mentions(content: str, old: str) -> list[tuple[int, str]]:
    """Find lines containing *old* that are OUTSIDE fenced code blocks.

    Returns list of (line_number, line_text).
    Inline code spans (backtick-wrapped) are stripped before checking
    to avoid false positives, but the raw line is returned for display.
    """
    if not old:
        return []

    fenced_ranges = _extract_fenced_ranges(content)

    def _in_fence(char_pos: int) -> bool:
        return any(s <= char_pos < e for s, e in fenced_ranges)

    lines = content.splitlines()
    char_pos = 0
    findings: list[tuple[int, str]] = []

    for ln_idx, line in enumerate(lines, start=1):
        line_start = char_pos
        if not _in_fence(line_start):
            # Strip inline code before checking to avoid backtick false-positives
            stripped = re.sub(r"`[^`]*`", "", line)
            if old in stripped:
                findings.append((ln_idx, line))
        char_pos += len(line) + 1

    return findings


# ── Single-file migrator ────────────────────────────────────────────────────


def migrate_coordinates(
    page_path: Path,
    changes: list[dict[str, str]],
    *,
    dry_run: bool = True,
    family: str = "",
    platform: str = "",
) -> dict[str, Any]:
    """Apply coordinate changes to a single content file.

    *changes* is a list of ``{"old": "...", "new": "...", "field": "..."}`` dicts
    derived from manifest_delta.json coordinate_changes events.

    Returns a result dict.
    """
    result: dict[str, Any] = {
        "path": str(page_path),
        "result": R_NOOP,
        "replacements": 0,
        "prose_mentions": 0,
        "prose_lines": [],
        "error": "",
    }

    if not page_path.is_file():
        result["error"] = "file not found"
        return result

    # English-only guard
    if family and platform:
        try:
            from commands.content.body_refresh import _target_locale_verdict

            allowed, locale, reason = _target_locale_verdict(str(page_path), family, platform)
            if not allowed:
                result["result"] = R_SKIPPED_LOCALE
                result["error"] = f"{reason} (locale={locale})"
                return result
        except ImportError:
            fname = page_path.name
            if re.search(r"\.[a-z]{2}(?:-[a-z0-9]{2,4})?\.md$", fname):
                result["result"] = R_SKIPPED_LOCALE
                result["error"] = "locale-suffixed filename"
                return result
            path_str = str(page_path)
            if (
                "/docs.aspose.org/" in path_str
                or "/kb.aspose.org/" in path_str
                or "/reference.aspose.org/" in path_str
                or "/products.aspose.org/" in path_str
            ) and "/en/" not in path_str:
                result["result"] = R_SKIPPED_LOCALE
                result["error"] = "not under /en/ directory"
                return result

    content = page_path.read_text(encoding="utf-8", errors="replace")

    # Quick pre-check: does the file contain any of the old values at all?
    old_values = [c["old"] for c in changes if c.get("old") and c["old"] != c.get("new", "")]
    if not any(v in content for v in old_values):
        result["result"] = R_NOOP
        return result

    # Apply all changes to code blocks
    updated = content
    total_replacements = 0
    for change in changes:
        old = change.get("old", "")
        new = change.get("new", "")
        if not old or old == new:
            continue
        updated, count = _replace_in_code_blocks(updated, old, new)
        total_replacements += count

    result["replacements"] = total_replacements

    if total_replacements == 0:
        # Old values were present but only in prose (not in code blocks)
        # Still need to flag prose
        pass

    # Scan for prose mentions of the old values (outside code blocks)
    all_prose_mentions: list[tuple[int, str]] = []
    for old_val in old_values:
        mentions = _find_prose_mentions(updated, old_val)
        # Deduplicate by line number
        for ln, line in mentions:
            if not any(ln == existing_ln for existing_ln, _ in all_prose_mentions):
                all_prose_mentions.append((ln, line))

    result["prose_mentions"] = len(all_prose_mentions)
    result["prose_lines"] = [
        {"line": ln, "text": text} for ln, text in all_prose_mentions
    ]

    # Determine final result code
    if total_replacements > 0 and all_prose_mentions:
        final_result = R_HUMAN_REVIEW
    elif total_replacements > 0:
        final_result = R_MIGRATED
    elif all_prose_mentions:
        # Only prose mentions, no code blocks to fix
        final_result = R_HUMAN_REVIEW
    else:
        final_result = R_SKIPPED_NO_CHANGE

    if dry_run:
        result["result"] = R_DRY_RUN if total_replacements > 0 else final_result
        return result

    # Write updated content
    if total_replacements > 0 and updated != content:
        try:
            from lib.provenance import safe_content_write

            safe_content_write(page_path, updated, mechanism="coordinate-migrator")
        except ImportError:
            page_path.write_text(updated, encoding="utf-8")
        except Exception as exc:
            if "ProtectedPageError" in type(exc).__name__:
                result["result"] = "SKIPPED_PROTECTED"
                result["error"] = str(exc)
                return result
            raise

    result["result"] = final_result
    return result


# ── Region-indexed migration runner ─────────────────────────────────────────


def run_migration(
    family: str,
    platform: str,
    *,
    dry_run: bool = True,
    manifest_delta_path: "Path | None" = None,
) -> dict[str, Any]:
    """Run coordinate migration for a product using the region index and manifest delta.

    Returns a summary dict with per-file results.
    """
    summary: dict[str, Any] = {
        "family": family,
        "platform": platform,
        "dry_run": dry_run,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "changes": [],
        "files_checked": 0,
        "files_migrated": 0,
        "files_noop": 0,
        "files_skipped": 0,
        "human_review_required": [],
        "results": [],
    }

    # 1. Load manifest_delta.json
    if manifest_delta_path is None:
        manifest_delta_path = (
            _KNOWLEDGE_ROOT / family / platform / "merged" / "manifest_delta.json"
        )

    if not manifest_delta_path.is_file():
        summary["changes"] = [{"error": R_NO_MANIFEST_DELTA}]
        return summary

    delta = json.loads(manifest_delta_path.read_text(encoding="utf-8"))
    coord_events = delta.get("coordinate_changes", [])

    if not coord_events:
        summary["changes"] = [{"info": R_NO_COORDINATE_EVENTS}]
        return summary

    # Build list of old→new substitutions
    changes: list[dict[str, str]] = []
    for event in coord_events:
        old_val = event.get("old", "")
        new_val = event.get("new", "")
        field = event.get("field", "")
        if old_val and new_val and old_val != new_val:
            changes.append({"old": old_val, "new": new_val, "field": field})

    summary["changes"] = changes

    if not changes:
        summary["changes"] = [{"info": "no actionable old→new pairs"}]
        return summary

    # 2. Load content region index to find candidate files
    region_index_path = (
        _REPORTS_ROOT / "content_region_index" / f"{family}_{platform}.json"
    )

    if region_index_path.is_file():
        region_data = json.loads(region_index_path.read_text(encoding="utf-8"))
        # Use code_blocks_with_coordinate if available; else fall back to all pages
        coord_map = region_data.get("code_blocks_with_coordinate", {})
        candidate_paths: set[str] = set()
        for old_val_key, file_list in coord_map.items():
            # Match if any of our old values is a substring of the key
            if any(c["old"] in old_val_key or old_val_key in c["old"] for c in changes):
                candidate_paths.update(file_list)
        # If the region index didn't have coordinate-indexed entries, scan install pages too
        if not candidate_paths:
            candidate_paths.update(region_data.get("install_command_blocks", []))
        target_files = [_REPO_ROOT / p for p in candidate_paths]
    else:
        # Fallback: full scan of English content for this product
        target_files = []
        for subsite in ("docs.aspose.org", "kb.aspose.org", "blog.aspose.org"):
            base = _CONTENT_ROOT / subsite
            # docs and kb have /en/ prefix; blog does not
            if subsite == "blog.aspose.org":
                base = base / family / platform
            else:
                base = base / "en" / family / platform
            if base.is_dir():
                target_files.extend(base.rglob("*.md"))

    # 3. Filter to English-only files (belt-and-suspenders, locale guard also in migrate_coordinates)
    def _is_english(p: Path) -> bool:
        # Reject locale-suffixed files: index.fr.md, index.ar.md etc.
        if re.search(r"\.[a-z]{2}(?:-[a-z0-9]{2,4})?\.md$", p.name):
            return False
        return True

    target_files = [Path(p) for p in target_files if _is_english(Path(p))]

    # 4. Apply migration to each file
    for page_path in sorted(target_files):
        page_path = Path(page_path)
        if not page_path.exists():
            continue

        summary["files_checked"] += 1
        res = migrate_coordinates(
            page_path,
            changes,
            dry_run=dry_run,
            family=family,
            platform=platform,
        )
        summary["results"].append(res)

        r = res["result"]
        if r in (R_MIGRATED, R_HUMAN_REVIEW, R_DRY_RUN):
            summary["files_migrated"] += 1
            if r == R_HUMAN_REVIEW:
                summary["human_review_required"].append(str(page_path))
        elif r == R_NOOP:
            summary["files_noop"] += 1
        else:
            summary["files_skipped"] += 1

    return summary


# ── CLI ────────────────────────────────────────────────────────────────────


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="coordinate_migrator",
        description=(
            "Migrate package coordinates (groupId, artifactId, package_name, "
            "canonical_import) in English content code blocks from manifest_delta.json."
        ),
    )
    parser.add_argument("family", nargs="?", help="Product family (e.g. cells)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. java)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without writing (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write changes to disk",
    )
    parser.add_argument(
        "--manifest-delta",
        metavar="PATH",
        help="Override path to manifest_delta.json",
    )
    args = parser.parse_args(argv)

    if not args.family or not args.platform:
        parser.print_help()
        return 1

    dry_run = not args.execute
    manifest_delta_path = Path(args.manifest_delta) if args.manifest_delta else None

    summary = run_migration(
        args.family,
        args.platform,
        dry_run=dry_run,
        manifest_delta_path=manifest_delta_path,
    )

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"\ncoordinate_migrator [{mode}] {args.family}/{args.platform}")
    for c in summary["changes"]:
        if "old" in c:
            print(f"  change: {c['field']} {c['old']!r} -> {c['new']!r}")
        elif "error" in c:
            print(f"  {c['error']}")
        elif "info" in c:
            print(f"  {c['info']}")
    print(f"  files_checked:  {summary['files_checked']}")
    print(f"  files_migrated: {summary['files_migrated']}")
    print(f"  files_noop:     {summary['files_noop']}")
    print(f"  files_skipped:  {summary['files_skipped']}")

    if summary.get("human_review_required"):
        print(
            f"  HUMAN_REVIEW_REQUIRED ({len(summary['human_review_required'])} files):"
        )
        for p in summary["human_review_required"]:
            print(f"    {p}")

    for res in summary["results"]:
        status = res["result"]
        reps = res.get("replacements", 0)
        prose = res.get("prose_mentions", 0)
        if status not in (R_NOOP, "NOOP_NO_OLD_COORDINATE"):
            path_short = Path(res["path"]).name
            detail = f"replacements={reps}"
            if prose:
                detail += f" prose_mentions={prose}"
            if res.get("error"):
                detail += f" err={res['error']}"
            print(f"    {status}: {path_short} ({detail})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
