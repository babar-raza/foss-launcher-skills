"""locale_patch.py -- PKGINSTALL-LOCALE-PATCH-MODULE.

A real, tested, committed implementation of S-75's algorithm
(skills/locale-patch.md), replacing the ad hoc, write-once-delete-after-use
script ST-054 TC-07 used to propagate its 250 real locale-file fixes across
3 products -- confirmed, at the time, there was NO reusable module for this
at all; every future use would otherwise re-derive the same throwaway
script from scratch.

Core safety principle, UNCHANGED from S-75: byte-identical old_text match
or skip -- never fuzzy matching, never a partial/best-effort correction. A
locale file whose translation has diverged (e.g. the real, live
`content/docs.aspose.org/da/slides/net/_index.md` precedent, where the
Danish translation had translated the CLI command ITSELF -- "dotnet
add-pakke" instead of "dotnet add package" -- so old_text never matched
verbatim) is correctly left untouched and reported not_found, never
corrupted further.

New capability the skill's own docstring explicitly disclaimed
("Pre-condition: English source file already fixed (not this skill's
responsibility)"): is_english_source_ready() gives that responsibility a
concrete home, consulting reconciliation_store.py's durable per-page state
so a caller can't accidentally propagate from a source that's still
representation="literal" (never fixed) or carries an unresolved
COLLISION_RISK_STRUCTURAL classification.

Locale-file discovery reuses this repo's own already-known real structure
(the same two conventions package_install_migrator.py's discover_files()/
_locale_from_path() already encode as committed, tested code) rather than
re-deriving S-75's own generic "glob + walk up to 3 sibling directories"
heuristic -- that heuristic exists because an LLM agent following the skill
by hand has no cheaper way to find locale copies; a committed module
already knows the real (family, platform)-scoped layout precisely.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from lib.reconciliation_store import ReconciliationStore  # noqa: E402
from lib.install_change_budget import (  # noqa: E402
    ProposedInstallChangeVolume, check_budget, record_run,
)
from commands.content.package_install_migrator import _locale_from_path  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTENT_ROOT = _REPO_ROOT / "content"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT, _CONTENT_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTENT_ROOT = _REPO_ROOT / "content"


class PatchStatus(str, Enum):
    APPLIED = "applied"
    NOT_FOUND = "not_found"
    SKIPPED = "skipped"


@dataclass
class Patch:
    old_text: str
    new_text: str
    context: "str | None" = None


@dataclass
class PatchResult:
    filepath: Path
    patch_index: int
    status: PatchStatus
    detail: str = ""


# ---------------------------------------------------------------------------
# Locale-file discovery
# ---------------------------------------------------------------------------

def discover_locale_files(source_file: "Path | str", family: str) -> list[Path]:
    """Find every locale copy of source_file, reusing this repo's own known
    real layout: docs/kb/products.aspose.org carry the locale as a
    DIRECTORY segment (content/{site}/{locale}/{family}/{platform}/...);
    blog.aspose.org carries it as a FILENAME suffix in the SAME directory
    (index.md for English, index.{locale}.md for a translation) -- the
    identical two conventions package_install_migrator.py's own
    discover_files()/_locale_from_path() already encode."""
    source_path = Path(source_file)
    parts = source_path.parts
    try:
        content_idx = parts.index("content")
    except ValueError:
        return []
    if len(parts) <= content_idx + 2:
        return []
    site = parts[content_idx + 1]

    if site == "blog.aspose.org":
        directory = source_path.parent
        if not directory.is_dir():
            return []
        found = [
            candidate for candidate in directory.glob(f"{source_path.stem}.*{source_path.suffix}")
            if candidate.name != source_path.name
        ]
        return sorted(found)

    # docs/kb/products.aspose.org: locale is the directory segment right
    # after the site -- normally "en" for the English source itself.
    segment_idx = content_idx + 2
    locale_root = Path(*parts[:segment_idx]) if segment_idx > 0 else Path()
    rest = Path(*parts[segment_idx + 1:])
    if not locale_root.is_dir():
        return []
    found = []
    for locale_dir in locale_root.iterdir():
        if not locale_dir.is_dir():
            continue
        candidate = locale_dir / rest
        if candidate.exists() and candidate != source_path:
            found.append(candidate)
    return sorted(found)


# ---------------------------------------------------------------------------
# Patch application -- S-75's exact algorithm, unchanged
# ---------------------------------------------------------------------------

def apply_patch_to_file(filepath: Path, patch: Patch, patch_index: int = 0, *, dry_run: bool = True) -> PatchResult:
    """Byte-identical old_text match or skip -- never fuzzy. Never partially
    writes: a file is either untouched (not_found/skipped) or written with
    every application of old_text replaced (applied)."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        return PatchResult(filepath, patch_index, PatchStatus.NOT_FOUND, detail=f"read error: {exc!r}")

    if patch.old_text not in text:
        return PatchResult(filepath, patch_index, PatchStatus.NOT_FOUND, detail="old_text not present verbatim")

    if patch.context:
        lines = text.splitlines()
        context_lines = {i for i, line in enumerate(lines) if patch.context in line}
        old_text_first_line = patch.old_text.splitlines()[0] if patch.old_text else ""
        old_text_lines = {i for i, line in enumerate(lines) if old_text_first_line and old_text_first_line in line}
        # No context line at all, or no old_text line within 5 lines of one --
        # either way the proximity check cannot be satisfied. any() over an
        # empty product correctly evaluates False, so a missing context
        # string is treated the same as a too-far one: skipped, not applied.
        near = any(abs(a - b) <= 5 for a in old_text_lines for b in context_lines)
        if not near:
            return PatchResult(
                filepath, patch_index, PatchStatus.SKIPPED,
                detail="old_text found but not within 5 lines of context",
            )

    occurrences = text.count(patch.old_text)
    new_text = text.replace(patch.old_text, patch.new_text)
    if not dry_run:
        filepath.write_text(new_text, encoding="utf-8")
    return PatchResult(filepath, patch_index, PatchStatus.APPLIED, detail=f"replaced {occurrences} occurrence(s)")


def _apply_all(files: list[Path], patches: list[Patch], *, dry_run: bool) -> list[PatchResult]:
    results = []
    for fp in files:
        for i, patch in enumerate(patches):
            results.append(apply_patch_to_file(fp, patch, i, dry_run=dry_run))
    return results


# ---------------------------------------------------------------------------
# English-source readiness gate -- the responsibility the skill's own
# docstring explicitly disclaimed
# ---------------------------------------------------------------------------

def _reconciliation_key(path: "Path | str") -> str:
    """Normalize to the same repo-root-relative, forward-slash form the
    reconciliation store's rows use, regardless of whether the caller
    passed an absolute or already-relative path."""
    p = Path(path)
    try:
        p = p.relative_to(_REPO_ROOT)
    except ValueError:
        pass
    return str(p).replace("\\", "/")


def is_english_source_ready(
    family: str, platform: str, source_path: "Path | str", *, store: "ReconciliationStore | None" = None,
) -> "tuple[bool, str]":
    """Consults reconciliation_store.py's durable per-page state. Refuses
    (False) when the English source itself is still representation="literal"
    (never fixed at all) or carries an unresolved COLLISION_RISK_STRUCTURAL
    classification. A path with NO reconciliation record at all is also
    refused, fail-closed -- "never swept" is not the same as "known safe"."""
    store = store if store is not None else ReconciliationStore(repo_root=_REPO_ROOT)
    key = _reconciliation_key(source_path)
    row = store.read_latest().get(key)
    if row is None:
        return False, f"no reconciliation record found for {key!r} -- run the defect sweep first"
    representation = row.get("representation")
    if representation == "literal":
        return False, f"{key!r} is still representation=literal -- English source not yet fixed"
    classification = row.get("collision_classification")
    if classification == "COLLISION_RISK_STRUCTURAL":
        return False, f"{key!r} has an unresolved COLLISION_RISK_STRUCTURAL classification"
    return True, f"{key!r} is representation={representation!r}, collision_classification={classification!r} -- ready"


# ---------------------------------------------------------------------------
# Report generation -- same path convention S-75's own skill already uses
# ---------------------------------------------------------------------------

def _write_report(
    family: str, platform: str, source_file: str, dry_run: bool, results: list[PatchResult],
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_dir = _REPO_ROOT / "reports" / "agents" / "locale-patch" / f"{family}-{platform}-{ts}"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "patch_report.md"

    by_file: dict[Path, list[PatchResult]] = {}
    for r in results:
        by_file.setdefault(r.filepath, []).append(r)

    lines = [
        "# Locale Patch Report",
        f"**Source**: {source_file}",
        f"**Dry run**: {dry_run}",
        f"**Date**: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Locale File | Patch # | old_text (first 50 chars) | Status |",
        "|-------------|---------|--------------------------|--------|",
    ]
    applied = not_found = skipped = 0
    for fp, file_results in sorted(by_file.items()):
        for r in file_results:
            if r.status == PatchStatus.APPLIED:
                applied += 1
            elif r.status == PatchStatus.NOT_FOUND:
                not_found += 1
            else:
                skipped += 1
        lines.append(f"| {fp} | | | |")

    lines += [
        "",
        "## Summary",
        f"- Files scanned: {len(by_file)}",
        f"- Files modified: {sum(1 for rs in by_file.values() if any(r.status == PatchStatus.APPLIED for r in rs))}",
        f"- Patches applied: {applied}",
        f"- Patches not_found: {not_found}",
        f"- Patches skipped: {skipped}",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_locale_patch(
    family: str, platform: str, site: str, source_file: "Path | str", patches: list[Patch],
    *, dry_run: bool = True, respect_change_budget: bool = True, force: bool = False,
    store: "ReconciliationStore | None" = None, write_report: bool = True,
) -> dict[str, Any]:
    source_path = Path(source_file)

    if not force:
        ready, reason = is_english_source_ready(family, platform, source_path, store=store)
        if not ready:
            return {
                "family": family, "platform": platform, "site": site,
                "source_file": str(source_file), "dry_run": dry_run,
                "readiness_blocked": True, "readiness_reason": reason,
                "files_checked": 0, "files_modified": 0,
                "patches_applied": 0, "patches_not_found": 0, "patches_skipped": 0,
                "results": [], "budget_blocked": False,
                "budget_anomaly_status": None, "report_path": None,
            }

    locale_files = discover_locale_files(source_path, family)

    probe_results = _apply_all(locale_files, patches, dry_run=True)
    modified_files = sorted({r.filepath for r in probe_results if r.status == PatchStatus.APPLIED})

    budget_verdict = None
    if respect_change_budget and not force:
        files_by_locale: dict[str, int] = {}
        for fp in modified_files:
            loc = _locale_from_path(fp, family)
            files_by_locale[loc] = files_by_locale.get(loc, 0) + 1
        volume = ProposedInstallChangeVolume(total_files=len(modified_files), files_by_locale=files_by_locale)
        budget_verdict = check_budget(family, "locale_propagation", volume)
        if not budget_verdict.allowed:
            return {
                "family": family, "platform": platform, "site": site,
                "source_file": str(source_file), "dry_run": dry_run,
                "readiness_blocked": False,
                "files_checked": len(locale_files), "files_modified": 0,
                "patches_applied": 0, "patches_not_found": 0, "patches_skipped": 0,
                "results": [], "budget_blocked": True,
                "budget_reason": budget_verdict.reason,
                "budget_static_cap_violations": budget_verdict.static_cap_violations,
                "budget_anomaly_status": budget_verdict.anomaly_status,
                "report_path": None,
            }

    results = probe_results if dry_run else _apply_all(locale_files, patches, dry_run=False)

    if not dry_run and respect_change_budget and not force:
        actual_modified = len({r.filepath for r in results if r.status == PatchStatus.APPLIED})
        record_run(family, "locale_propagation", actual_modified)

    applied = sum(1 for r in results if r.status == PatchStatus.APPLIED)
    not_found = sum(1 for r in results if r.status == PatchStatus.NOT_FOUND)
    skipped = sum(1 for r in results if r.status == PatchStatus.SKIPPED)
    modified_now = sorted({r.filepath for r in results if r.status == PatchStatus.APPLIED})

    report_path = None
    if write_report:
        report_path = _write_report(family, platform, str(source_file), dry_run, results)

    return {
        "family": family, "platform": platform, "site": site,
        "source_file": str(source_file), "dry_run": dry_run,
        "readiness_blocked": False,
        "files_checked": len(locale_files), "files_modified": len(modified_now),
        "patches_applied": applied, "patches_not_found": not_found, "patches_skipped": skipped,
        "results": results, "budget_blocked": False,
        "budget_anomaly_status": budget_verdict.anomaly_status if budget_verdict else None,
        "report_path": str(report_path) if report_path else None,
    }


def main(argv: "list[str] | None" = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="locale_patch")
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("site")
    parser.add_argument("source_file")
    parser.add_argument("--patches-json", required=True, help="JSON file: list of {old_text, new_text, context?}")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    patches_data = json.loads(Path(args.patches_json).read_text(encoding="utf-8"))
    patches = [Patch(**p) for p in patches_data]
    dry_run = not args.execute

    summary = run_locale_patch(
        args.family, args.platform, args.site, args.source_file, patches,
        dry_run=dry_run, force=args.force,
    )

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"=== locale_patch [{mode}] {args.family}/{args.platform} ===")
    if summary.get("readiness_blocked"):
        print(f"BLOCKED (readiness): {summary['readiness_reason']}")
        return 1
    if summary.get("budget_blocked"):
        print(f"BLOCKED (budget): {summary['budget_reason']}")
        return 1
    print(f"files_checked: {summary['files_checked']}")
    print(f"files_modified: {summary['files_modified']}")
    print(f"patches_applied: {summary['patches_applied']}")
    print(f"patches_not_found: {summary['patches_not_found']}")
    print(f"patches_skipped: {summary['patches_skipped']}")
    if summary.get("report_path"):
        print(f"report: {summary['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
