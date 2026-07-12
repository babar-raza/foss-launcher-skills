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
from content_discovery import LOCALE_RE, _is_draft  # noqa: E402  (R-4: was knowledge_core)
from core.markdown import parse_frontmatter  # noqa: E402  (R-2a: was knowledge_core)
from commands.knowledge.promote import compute_extractor_config_sha  # noqa: E402

_SITE_PATTERNS = (
    "docs.aspose.org/en/{family}/{platform}",
    "kb.aspose.org/en/{family}/{platform}",
    "products.aspose.org/en/{family}/{platform}",
    "reference.aspose.org/en/{family}/{platform}",
    "blog.aspose.org/{family}/{platform}",
)


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
    return 1 if report["stale_pages"] else 0


if __name__ == "__main__":
    sys.exit(main())