#!/usr/bin/env python3
"""Detect pages whose evidence is stale relative to the current knowledge model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/knowledge/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from knowledge_core import Knowledge  # noqa: E402
from content_discovery import LOCALE_CODES, LOCALE_RE, _is_draft  # noqa: E402  (R-4: was knowledge_core)
from core.markdown import parse_frontmatter  # noqa: E402  (R-2a: was knowledge_core)
from commands.knowledge.promote import compute_extractor_config_sha  # noqa: E402

_SITE_PATTERNS = (
    "docs.aspose.org/en/{family}/{platform}",
    "kb.aspose.org/en/{family}/{platform}",
    "products.aspose.org/en/{family}/{platform}",
    "reference.aspose.org/en/{family}/{platform}",
    "blog.aspose.org/{family}/{platform}",
)

# Task 11d (mission-plan-the-end-to-end-vast-hejlsberg.md, §9.8, closes G8/sizes F7):
# directory-locale sites encode locale as a top-level path segment (content/{site}/{locale}/...,
# mirroring the "en" tree exactly); blog encodes locale as a filename suffix instead
# (index.{locale}.md alongside index.md in the same directory) -- same distinction
# body_refresh.py's _DIR_LOCALE_SITES/_KNOWN_CONTENT_SITES already draw for the same reason.
_DIR_LOCALE_SITE_NAMES = (
    "docs.aspose.org",
    "kb.aspose.org",
    "products.aspose.org",
    "reference.aspose.org",
)
_FILENAME_LOCALE_SITE_NAME = "blog.aspose.org"


def discover_content_files(content_root: Path, family: str, platform: str) -> list[Path]:
    files: list[Path] = []
    for pattern in _SITE_PATTERNS:
        site_root = content_root / Path(pattern.format(family=family, platform=platform))
        if site_root.exists():
            for path in sorted(site_root.rglob("*.md")):
                if LOCALE_RE.search(path.name):
                    continue
                if _is_draft(path):
                    continue
                files.append(path)
    return files


def discover_locale_content_files(
    content_root: Path, family: str, platform: str
) -> dict[str, list[Path]]:
    """Discover locale (non-English) content files for a product, grouped by surface.

    Detection-only counterpart to discover_content_files(): same site topology,
    inverted locale filter. Never invoked by the default (English-scoped) path --
    only by --include-locales / scan_product_locales(). Draft pages are still
    excluded (matches discover_content_files' own exclusion; a retired page's
    staleness isn't actionable either way).
    """
    by_surface: dict[str, list[Path]] = {}

    for site in _DIR_LOCALE_SITE_NAMES:
        surface = site.split(".", 1)[0]
        site_dir = content_root / site
        surface_files: list[Path] = []
        if site_dir.is_dir():
            for locale_dir in sorted(site_dir.iterdir()):
                if not locale_dir.is_dir() or locale_dir.name == "en":
                    continue
                if locale_dir.name not in LOCALE_CODES:
                    continue
                product_root = locale_dir / family / platform
                if not product_root.exists():
                    continue
                for path in sorted(product_root.rglob("*.md")):
                    if _is_draft(path):
                        continue
                    surface_files.append(path)
        by_surface[surface] = surface_files

    blog_files: list[Path] = []
    blog_root = content_root / _FILENAME_LOCALE_SITE_NAME / family / platform
    if blog_root.is_dir():
        for path in sorted(blog_root.rglob("*.md")):
            if not LOCALE_RE.search(path.name):
                continue
            if _is_draft(path):
                continue
            blog_files.append(path)
    by_surface["blog"] = blog_files

    return by_surface


def scan_product_locales(
    family: str,
    platform: str,
    *,
    content_root: Path = Path("content"),
    knowledge_root: Path = Path("knowledge"),
    report_root: Path = Path("reports/locale_staleness"),
    force: bool = False,
) -> dict:
    """Size locale-evidence staleness for a product (detection only, §9.8/G8/F7).

    Compares each locale file's evidence.model_sha against the current knowledge
    baseline's repo_sha -- the identical, single comparison scan_product() already
    applies to English content (line ~97 above), just widened in scope to locale
    content, which no existing staleness check covers (G8). This function never
    mutates content, never blocks anything, and is not a remediation step -- its
    sole purpose is to give every launched product an accurate, current locale-
    staleness count for the first time, so a future dedicated remediation mission
    can be sized correctly instead of discovered product-by-product (§22 scope
    decision: full remediation is explicitly out of this mission's scope).

    Performance note (found live, 2026-08-24, sizing pdf/java for real: a single
    full scan took ~35s for its ~12,300-file locale corpus, dominated by per-file
    frontmatter parses): this is cheap enough for a standalone, occasional CLI
    invocation but too expensive to re-run unconditionally on every verify_run()
    call, which can fire repeatedly across retries for the same run (observed
    directly during this mission's own Task 12 attempts). Since locale staleness
    can only change when the knowledge baseline's repo_sha advances (the sole
    comparison target) or when a locale file is actually re-stamped, the cheap,
    correct cache key is repo_sha: a previously-written report for this exact
    repo_sha is reused as-is unless force=True. Known, accepted limitation: a
    deliberate locale remediation pass that re-stamps some files WITHOUT the
    baseline's repo_sha also advancing would not be reflected until force=True
    is passed -- acceptable because no remediation is in this mission's scope
    (§22); the verify_run() call site below always passes force=False.
    """
    knowledge = Knowledge(family, platform, knowledge_root=knowledge_root)
    if not knowledge.available:
        raise FileNotFoundError(
            f"No knowledge model available at {knowledge_root / family / platform / 'merged'}"
        )

    if not force:
        cached_path = report_root / f"{family}-{platform}.json"
        if cached_path.is_file():
            try:
                cached = json.loads(cached_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cached = None
            if cached is not None and cached.get("knowledge_repo_sha") == knowledge.repo_sha:
                return cached

    by_surface = discover_locale_content_files(content_root, family, platform)
    surfaces: dict[str, dict] = {}
    total_files = 0
    total_stale = 0
    for surface in sorted(by_surface):
        stale_files: list[str] = []
        for path in by_surface[surface]:
            frontmatter = parse_frontmatter(path)
            evidence = frontmatter.get("evidence")
            model_sha = evidence.get("model_sha", "") if isinstance(evidence, dict) else ""
            if not model_sha or model_sha != knowledge.repo_sha:
                stale_files.append(str(path))
        surfaces[surface] = {
            "total": len(by_surface[surface]),
            "stale": len(stale_files),
            "files": stale_files,
        }
        total_files += len(by_surface[surface])
        total_stale += len(stale_files)

    return {
        "family": family,
        "platform": platform,
        "knowledge_repo_sha": knowledge.repo_sha,
        "total_locale_files": total_files,
        "total_stale": total_stale,
        "surfaces": surfaces,
    }


def scan_product(
    family: str,
    platform: str,
    *,
    content_root: Path = Path("content"),
    knowledge_root: Path = Path("knowledge"),
    claim_delta: bool = False,
) -> dict:
    """Scan a product for stale evidence.

    Args:
        claim_delta: When True, a stale_model_sha page is only marked stale if
            its cited claims were actually removed from the current knowledge.
            Pages whose cited claims are all still present get an INFO-level
            'stale_model_sha_no_impact' issue instead. (TC-STALE-001)
    """
    knowledge = Knowledge(family, platform, knowledge_root=knowledge_root)
    if not knowledge.available:
        raise FileNotFoundError(
            f"No knowledge model available at {knowledge_root / family / platform / 'merged'}"
        )

    enrichment_status = knowledge.enrichment_status or "full"

    # Check extractor config drift (RC-2): compare model.yaml config_sha against
    # the current hash of family-specific extractor config dicts.
    # Missing config_sha (pre-backfill models) emits INFO, not a stale flag.
    extractor_config_stale = False
    extractor_config_missing = False
    model_config_sha = knowledge.config_sha  # may be None for old models
    if model_config_sha is None:
        extractor_config_missing = True
    else:
        current_config_sha = compute_extractor_config_sha(family)
        if model_config_sha != current_config_sha:
            extractor_config_stale = True

    pages = []
    stale_sha_skipped = 0  # count of pages where SHA differs but claims are all present
    for path in discover_content_files(content_root, family, platform):
        frontmatter = parse_frontmatter(path)
        evidence = frontmatter.get("evidence")
        issues: list[str] = []
        orphaned_claims: list[str] = []

        if not evidence or not isinstance(evidence, dict):
            issues.append("missing_evidence")
        else:
            model_sha = evidence.get("model_sha", "")
            if not model_sha:
                issues.append("missing_model_sha")
            elif model_sha != knowledge.repo_sha:
                claims = evidence.get("claims") or []
                orphaned_claims = [claim for claim in claims if claim not in knowledge.claim_ids]

                if claim_delta and claims and not orphaned_claims:
                    # SHA changed but all cited claims still exist — no impact
                    issues.append("stale_model_sha_no_impact")
                    stale_sha_skipped += 1
                else:
                    issues.append("stale_model_sha")

                if orphaned_claims:
                    issues.append("orphaned_claims")
            else:
                # SHA matches — still check for orphaned claims
                claims = evidence.get("claims") or []
                orphaned_claims = [claim for claim in claims if claim not in knowledge.claim_ids]
                if orphaned_claims:
                    issues.append("orphaned_claims")

        if issues:
            pages.append({
                "file": str(path),
                "issues": issues,
                "orphaned_claims": orphaned_claims,
            })

    # Only count pages with actionable issues as stale
    actionable_issues = {"missing_evidence", "missing_model_sha", "stale_model_sha", "orphaned_claims"}
    stale_count = sum(
        1 for p in pages
        if any(i in actionable_issues for i in p["issues"])
    )

    result = {
        "family": family,
        "platform": platform,
        "knowledge_repo_sha": knowledge.repo_sha,
        "enrichment_status": enrichment_status,
        "files_scanned": len(discover_content_files(content_root, family, platform)),
        "stale_pages": stale_count,
        "pages": pages,
    }
    if claim_delta:
        result["claim_delta_skipped"] = stale_sha_skipped
    if extractor_config_stale:
        result["stale_extractor_config"] = True
        result["extractor_config_note"] = (
            "model.yaml config_sha differs from current extractor config — "
            "re-run promote.py to refresh the knowledge model"
        )
    elif extractor_config_missing:
        result["extractor_config_note"] = (
            "model.yaml has no config_sha — run promote.py to backfill"
        )
    return result


def _to_markdown(report: dict) -> str:
    enrichment_status = report.get("enrichment_status", "full")
    enrichment_note = (
        f" (**enrichment_degraded: {enrichment_status}**)" if enrichment_status != "full" else ""
    )
    config_note = report.get("extractor_config_note", "")
    config_line = ""
    if report.get("stale_extractor_config"):
        config_line = f"- **Extractor config stale**: {config_note}"
    elif config_note:
        config_line = f"- Extractor config: {config_note}"
    lines = [
        f"# Stale Detect Report: {report['family']}/{report['platform']}",
        "",
        f"- Knowledge SHA: `{report['knowledge_repo_sha']}`{enrichment_note}",
        f"- Files scanned: {report['files_scanned']}",
        f"- Stale pages: {report['stale_pages']}",
    ]
    if config_line:
        lines.append(config_line)
    lines.append("")
    if not report["pages"]:
        lines.append("No stale pages detected.")
        return "\n".join(lines)

    lines.extend([
        "| File | Issues | Orphaned Claims |",
        "|---|---|---|",
    ])
    for page in report["pages"]:
        orphaned = ", ".join(page["orphaned_claims"]) if page["orphaned_claims"] else "-"
        lines.append(
            f"| `{page['file']}` | {', '.join(page['issues'])} | {orphaned} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stale_detect",
        description="Detect content pages with stale or orphaned evidence",
    )
    parser.add_argument("family", help="Product family")
    parser.add_argument("platform", help="Platform")
    parser.add_argument("--content-root", type=Path, default=Path("content"))
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument("--output", type=Path, help="Optional report output path")
    parser.add_argument(
        "--claim-delta", action="store_true",
        help="Only mark stale if cited claims were actually removed from knowledge",
    )
    parser.add_argument(
        "--include-locales", action="store_true",
        help=(
            "Additionally size locale (non-English) evidence staleness and write "
            "reports/locale_staleness/{family}-{platform}.json (Task 11d, closes "
            "G8/sizes F7). Detection only: never blocks, never remediates, and "
            "never changes this command's exit code or its default (English-"
            "scoped) output -- purely additive."
        ),
    )
    args = parser.parse_args(argv)

    report = scan_product(
        args.family,
        args.platform,
        content_root=args.content_root,
        knowledge_root=args.knowledge_root,
        claim_delta=args.claim_delta,
    )
    output = json.dumps(report, indent=2, ensure_ascii=False) if args.json else _to_markdown(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")

    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")

    if args.include_locales:
        # An explicit CLI invocation is an operator asking for a current count --
        # always do the real scan (force=True), never silently serve a cached
        # figure from an earlier repo_sha or an earlier run. verify_run()'s own
        # automated advisory call (refresh_run.py) uses force=False instead, since
        # it can fire repeatedly per run and a same-repo_sha cache hit is correct
        # there (see scan_product_locales' own docstring for the full rationale).
        locale_report = scan_product_locales(
            args.family,
            args.platform,
            content_root=args.content_root,
            knowledge_root=args.knowledge_root,
            force=True,
        )
        locale_output_path = Path("reports/locale_staleness") / f"{args.family}-{args.platform}.json"
        locale_output_path.parent.mkdir(parents=True, exist_ok=True)
        locale_output_path.write_text(
            json.dumps(locale_report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        sys.stderr.write(
            f"Locale staleness report written to {locale_output_path} "
            f"({locale_report['total_stale']}/{locale_report['total_locale_files']} stale)\n"
        )

    return 1 if report["stale_pages"] else 0


if __name__ == "__main__":
    sys.exit(main())