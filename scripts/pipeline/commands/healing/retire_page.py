"""retire_page.py — Mark content pages as retired using Hugo's draft mechanism.

Adds ``draft: true`` and ``retired_at: YYYY-MM-DD`` to page frontmatter.
Does NOT delete files — retired pages are suppressed from production builds
by Hugo's native draft filtering.

Usage:
    python scripts/pipeline/commands/healing/retire_page.py <path/to/page.md> [--dry-run]
    python scripts/pipeline/commands/healing/retire_page.py --from-plan <site_plan.yaml> [--dry-run]
    python scripts/pipeline/commands/healing/retire_page.py --un-retire --from-delta {family} {platform} [--dry-run]

Options:
    --dry-run       Print what would be changed without modifying files.
    --from-plan     Read delta.pages_to_remove from a site_plan.yaml and retire all.
    --un-retire     Reverse retirement: remove draft/retired_at from pages.
    --from-delta    Read resurrected_apis from knowledge_delta.json and un-retire matching
                    reference pages (requires --un-retire plus family and platform args).

Retirement is idempotent: pages that already have ``draft: true`` are logged
and skipped without error.  Un-retirement is likewise idempotent.

Frontmatter write is atomic: read → modify in memory → write via temp+rename.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent.parent.parent))  # scripts/pipeline/

from core.env_loader import load_env  # noqa: E402
load_env()
from core.markdown import split_frontmatter  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT

# Injectable seam for the reference-index regeneration step (Task 8, closes G5 --
# mission-plan-the-end-to-end-vast-hejlsberg.md S9.5): tests override this to a
# stub instead of exercising the real, much heavier batch_reference.py generator.
_grouped_index_generator: "Callable[[str, str], dict] | None" = None


def configure(*, repo_root: "Path | str | None" = None, grouped_index_generator=None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, _grouped_index_generator
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _grouped_index_generator = grouped_index_generator


def _real_grouped_index_generator(family: str, platform: str) -> dict:
    # Imported lazily -- batch_reference.py is a much heavier module (Knowledge,
    # evidence.runner, backlink targets, ...) that retire_page.py's other,
    # non-reference callers should never need to pay the cost of importing.
    from commands.content.batch_reference import generate_grouped_index
    return generate_grouped_index(family, platform, dry_run=False)


# ---------------------------------------------------------------------------
# Reference-page removal: retire + unlink (Task 8, closes G5)
# ---------------------------------------------------------------------------
# Per direct user instruction, superseding this section's original alias/
# redirect design (mission plan S9.5): a retired reference page is never
# linked back to. draft:true (above, unchanged) already removes it from any
# platform using the dynamic {{< children >}} shortcode -- Hugo excludes
# draft pages from that listing by construction, nothing to do. Platforms
# using batch_reference.py's static, hand-baked generate_grouped_index()
# table need that table actually regenerated, since it is baked from
# api_surface.json at generation time, not derived live at build time --
# re-invoking the same generator is the correct fix (not hand-editing the
# table), and is a no-op-safe, idempotent call already proven by every
# existing generate_grouped_index() caller.

_REFERENCE_ROOT_MARKER = "reference.aspose.org"


def _reference_family_platform(path: Path, repo_root: Path) -> "tuple[str, str] | None":
    """Return (family, platform) if path is a reference.aspose.org content page.

    Path shape: content/reference.aspose.org/en/{family}/{platform}/{Class}.md
    Returns None for anything else (family-index pages, or non-reference paths).
    """
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 6 or parts[0] != "content" or parts[1] != _REFERENCE_ROOT_MARKER:
        return None
    if parts[2] != "en":
        return None
    return parts[3], parts[4]


def _index_uses_grouped_generator(family: str, platform: str, repo_root: Path) -> bool:
    """True if this platform's reference index carries an index_generator_version
    stamp (batch_reference.py's generate_grouped_index() marker, TC-DUPIDX-02) --
    the reliable, already-existing signal distinguishing a static, hand-baked
    grouped-module table from the dynamic {{< children >}} shortcode, which
    stamps nothing because it needs no regeneration."""
    index_path = repo_root / "content" / _REFERENCE_ROOT_MARKER / "en" / family / platform / "_index.md"
    if not index_path.is_file():
        return False
    text = index_path.read_text(encoding="utf-8")
    parts = split_frontmatter(text)
    if parts is None:
        return False
    _, yaml_body, _ = parts
    try:
        data = yaml.safe_load(yaml_body) or {}
    except yaml.YAMLError:
        return False
    return "index_generator_version" in data


def maybe_refresh_reference_index(path: Path, *, dry_run: bool = False) -> "str | None":
    """After retiring a reference page, keep its platform index consistent.

    Returns one of: None (not a reference page, nothing to do),
    "children_shortcode_noop" (dynamic index, Hugo already excludes drafts),
    "regenerated" (grouped index re-run for real), "dry_run" (would regenerate),
    "generator_skipped" (regeneration ran but declined -- e.g. api_surface.json
    now has too few entries; surfaced, never silently swallowed).
    """
    fp = _reference_family_platform(path, REPO_ROOT)
    if fp is None:
        return None
    family, platform = fp

    if not _index_uses_grouped_generator(family, platform, REPO_ROOT):
        print(f"INFO: {family}/{platform} reference index uses {{{{< children >}}}} "
              f"(dynamic) -- draft:true already excludes {path.name} from it.")
        return "children_shortcode_noop"

    if dry_run:
        print(f"WOULD REGENERATE: {family}/{platform} grouped reference index "
              f"(retiring {path.name} may remove its row)")
        return "dry_run"

    generator = _grouped_index_generator or _real_grouped_index_generator
    result = generator(family, platform)
    if result.get("written"):
        print(f"REGENERATED: {family}/{platform} grouped reference index "
              f"(retired page {path.name} no longer listed if absent from api_surface.json)")
        return "regenerated"
    print(f"WARN: {family}/{platform} grouped reference index regeneration "
          f"declined: {result.get('reason')}")
    return "generator_skipped"


# ---------------------------------------------------------------------------
# Core retirement logic
# ---------------------------------------------------------------------------

def retire_page(path: Path, *, dry_run: bool = False) -> str:
    """Retire a single page by setting draft: true and retired_at in frontmatter.

    Returns one of:
      "retired"     — page successfully retired
      "skipped"     — page already has draft: true (idempotent)
      "dry_run"     — would have retired (--dry-run mode)
      "error"       — file not found or no frontmatter
    """
    if not path.is_file():
        print(f"ERROR: file not found: {path}")
        return "error"

    text = path.read_text(encoding="utf-8")
    parts = split_frontmatter(text)
    if parts is None:
        print(f"ERROR: no frontmatter found in {path}")
        return "error"

    opening, yaml_body, closing = parts
    try:
        data = yaml.safe_load(yaml_body) or {}
    except yaml.YAMLError as exc:
        print(f"ERROR: could not parse frontmatter in {path}: {exc}")
        return "error"

    if data.get("draft") is True:
        print(f"SKIP (already retired): {path}")
        return "skipped"

    if dry_run:
        print(f"WOULD RETIRE: {path}")
        maybe_refresh_reference_index(path, dry_run=True)
        return "dry_run"

    # Modify frontmatter in memory only
    data["draft"] = True
    data["retired_at"] = datetime.now(timezone.utc).date().isoformat()

    new_yaml_body = yaml.safe_dump(data, allow_unicode=True, default_flow_style=False).rstrip()
    new_text = opening + new_yaml_body + closing + text[len(opening) + len(yaml_body) + len(closing):]

    # Atomic write: temp file + rename
    tmp = path.with_suffix(".retire_tmp")
    try:
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        print(f"ERROR: could not write {path}: {exc}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return "error"

    print(f"RETIRED: {path} (retired_at={data['retired_at']})")
    maybe_refresh_reference_index(path, dry_run=False)
    return "retired"


def retire_from_plan(plan_path: Path, *, dry_run: bool = False) -> dict:
    """Retire all pages listed in delta.pages_to_remove from a site_plan.yaml."""
    if not plan_path.is_file():
        print(f"ERROR: site_plan.yaml not found: {plan_path}")
        sys.exit(1)

    try:
        plan_data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"ERROR: could not parse {plan_path}: {exc}")
        sys.exit(1)

    delta = plan_data.get("plan", plan_data).get("delta") or {}
    pages_to_remove = delta.get("pages_to_remove") or []

    if not pages_to_remove:
        print(f"INFO: no pages_to_remove in {plan_path}")
        return {"retired": 0, "skipped": 0, "errors": 0, "dry_run": dry_run}

    print(f"Retiring {len(pages_to_remove)} page(s) from plan: {plan_path}")

    counts = {"retired": 0, "skipped": 0, "errors": 0, "dry_run_count": 0}
    for page_ref in pages_to_remove:
        # page_ref may be absolute or relative to repo root
        page_path = Path(page_ref)
        if not page_path.is_absolute():
            page_path = REPO_ROOT / page_path

        result = retire_page(page_path, dry_run=dry_run)
        if result == "retired":
            counts["retired"] += 1
        elif result == "skipped":
            counts["skipped"] += 1
        elif result == "dry_run":
            counts["dry_run_count"] += 1
        else:
            counts["errors"] += 1

    summary_label = "Would retire" if dry_run else "Retired"
    print(
        f"\nPlan retirement complete: "
        f"{counts.get('dry_run_count', 0) if dry_run else counts['retired']} {summary_label.lower()}, "
        f"{counts['skipped']} already retired, "
        f"{counts['errors']} errors."
    )
    return {
        "retired": counts["retired"],
        "skipped": counts["skipped"],
        "errors": counts["errors"],
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Un-retirement logic (Fix C — healing sprint 2026-04-15)
# ---------------------------------------------------------------------------

def un_retire_page(path: Path, *, dry_run: bool = False) -> str:
    """Reverse retirement of a single page by removing draft and retired_at.

    Returns one of:
      "un_retired"   — page successfully un-retired
      "skipped"      — page is not retired (no draft: true)
      "dry_run"      — would have un-retired (--dry-run mode)
      "error"        — file not found or no frontmatter
    """
    if not path.is_file():
        print(f"ERROR: file not found: {path}")
        return "error"

    text = path.read_text(encoding="utf-8")
    parts = split_frontmatter(text)
    if parts is None:
        print(f"ERROR: no frontmatter found in {path}")
        return "error"

    opening, yaml_body, closing = parts
    try:
        data = yaml.safe_load(yaml_body) or {}
    except yaml.YAMLError as exc:
        print(f"ERROR: could not parse frontmatter in {path}: {exc}")
        return "error"

    if data.get("draft") is not True:
        print(f"SKIP (not retired): {path}")
        return "skipped"

    if dry_run:
        print(f"WOULD UN-RETIRE: {path}")
        return "dry_run"

    # Remove retirement markers
    data.pop("draft", None)
    data.pop("retired_at", None)

    new_yaml_body = yaml.safe_dump(data, allow_unicode=True, default_flow_style=False).rstrip()
    new_text = opening + new_yaml_body + closing + text[len(opening) + len(yaml_body) + len(closing):]

    # Atomic write: temp file + rename
    tmp = path.with_suffix(".unretire_tmp")
    try:
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        print(f"ERROR: could not write {path}: {exc}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return "error"

    print(f"UN-RETIRED: {path}")
    return "un_retired"


def un_retire_from_delta(family: str, platform: str, *, dry_run: bool = False) -> dict:
    """Un-retire reference pages whose API classes appear in resurrected_apis.

    Reads knowledge_delta.json for the given family/platform and un-retires
    reference pages whose stem matches a class name in the resurrected_apis list.
    """
    knowledge_root = REPO_ROOT / "knowledge"
    delta_path = knowledge_root / family / platform / "merged" / "knowledge_delta.json"
    ref_root = REPO_ROOT / "content" / "reference.aspose.org" / "en" / family / platform

    if not delta_path.is_file():
        print(f"INFO: no knowledge_delta.json found at {delta_path}")
        return {"un_retired": 0, "skipped": 0, "errors": 0, "dry_run": dry_run}

    try:
        delta = json.loads(delta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: could not parse {delta_path}: {exc}")
        return {"un_retired": 0, "skipped": 0, "errors": 1, "dry_run": dry_run}

    resurrected = delta.get("resurrected_apis") or []
    if not resurrected:
        print(f"INFO: no resurrected_apis in {delta_path}")
        return {"un_retired": 0, "skipped": 0, "errors": 0, "dry_run": dry_run}

    print(f"Un-retiring {len(resurrected)} resurrected API reference page(s) for {family}/{platform}")

    resurrected_lower = {name.lower() for name in resurrected}
    counts = {"un_retired": 0, "skipped": 0, "errors": 0, "dry_run_count": 0}

    if not ref_root.is_dir():
        print(f"WARN: reference directory not found: {ref_root}")
        return {"un_retired": 0, "skipped": 0, "errors": 0, "dry_run": dry_run}

    for ref_page in sorted(ref_root.glob("*.md")):
        if ref_page.stem.lower() in resurrected_lower:
            result = un_retire_page(ref_page, dry_run=dry_run)
            if result == "un_retired":
                counts["un_retired"] += 1
            elif result == "skipped":
                counts["skipped"] += 1
            elif result == "dry_run":
                counts["dry_run_count"] += 1
            else:
                counts["errors"] += 1

    summary_label = "Would un-retire" if dry_run else "Un-retired"
    actual = counts.get("dry_run_count", 0) if dry_run else counts["un_retired"]
    print(
        f"\nUn-retirement complete: "
        f"{actual} {summary_label.lower()}, "
        f"{counts['skipped']} not retired, "
        f"{counts['errors']} errors."
    )
    return {
        "un_retired": counts["un_retired"],
        "skipped": counts["skipped"],
        "errors": counts["errors"],
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="retire_page",
        description="Mark content pages as retired (draft: true) without deleting them.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("page", nargs="?", metavar="PAGE_PATH",
                       help="Path to a single markdown page to retire.")
    group.add_argument("--from-plan", metavar="SITE_PLAN_YAML",
                       help="Read delta.pages_to_remove from site_plan.yaml and retire all.")
    group.add_argument("--un-retire", action="store_true",
                       help="Reverse retirement: remove draft/retired_at from pages.")
    parser.add_argument("--from-delta", nargs=2, metavar=("FAMILY", "PLATFORM"),
                        help="Read resurrected_apis from knowledge_delta.json "
                             "(requires --un-retire; provide family and platform).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be changed without modifying files.")
    args = parser.parse_args(argv)

    if args.un_retire:
        if args.from_delta:
            family, platform = args.from_delta
            result = un_retire_from_delta(family, platform, dry_run=args.dry_run)
            return 1 if result["errors"] else 0
        elif args.page:
            page_path = Path(args.page)
            if not page_path.is_absolute():
                page_path = Path.cwd() / page_path
            result = un_retire_page(page_path, dry_run=args.dry_run)
            return 0 if result in ("un_retired", "skipped", "dry_run") else 1
        else:
            parser.error("--un-retire requires either a page path or --from-delta with family/platform")

    if args.from_plan:
        result = retire_from_plan(Path(args.from_plan), dry_run=args.dry_run)
        return 1 if result["errors"] else 0

    page_path = Path(args.page)
    if not page_path.is_absolute():
        page_path = Path.cwd() / page_path

    result = retire_page(page_path, dry_run=args.dry_run)
    return 0 if result in ("retired", "skipped", "dry_run") else 1


if __name__ == "__main__":
    sys.exit(main())
