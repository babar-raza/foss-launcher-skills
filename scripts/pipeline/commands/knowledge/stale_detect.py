# Adapted from aspose.org
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
try:
    from content_discovery import LOCALE_RE, _is_draft  # noqa: E402  (R-4: was knowledge_core)
except ImportError:
    import re as _re
    LOCALE_RE = _re.compile(r'\.[a-z]{2}(-[a-z]{2})?\.md$')
    def _is_draft(path):
        """Fallback draft detector when content_discovery is unavailable."""
        try:
            text = path.read_text(encoding='utf-8', errors='replace')[:500]
            return 'draft: true' in text.lower()
        except Exception:
            return False
from core.markdown import parse_frontmatter  # noqa: E402  (R-2a: was knowledge_core)

# Configurable site patterns -- override via SITE_PATTERNS env var (JSON list)
# or by calling configure_site_patterns() before scan_product().
_DEFAULT_SITE_PATTERNS = (
    "docs.aspose.org/en/{family}/{platform}",
    "kb.aspose.org/en/{family}/{platform}",
    "products.aspose.org/en/{family}/{platform}",
    "reference.aspose.org/en/{family}/{platform}",
    "blog.aspose.org/{family}/{platform}",
)

_SITE_PATTERNS = _DEFAULT_SITE_PATTERNS

def configure_site_patterns(patterns: tuple[str, ...] | list[str]) -> None:
    """Override site patterns for non-aspose.org deployments."""
    global _SITE_PATTERNS
    _SITE_PATTERNS = tuple(patterns)


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
) -> dict:
    knowledge = Knowledge(family, platform, knowledge_root=knowledge_root)
    if not knowledge.available:
        raise FileNotFoundError(
            f"No knowledge model available at {knowledge_root / family / platform / 'merged'}"
        )

    enrichment_status = knowledge.enrichment_status or "full"

    pages = []
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
                issues.append("stale_model_sha")

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

    return {
        "family": family,
        "platform": platform,
        "knowledge_repo_sha": knowledge.repo_sha,
        "enrichment_status": enrichment_status,
        "files_scanned": len(discover_content_files(content_root, family, platform)),
        "stale_pages": len(pages),
        "pages": pages,
    }


def _to_markdown(report: dict) -> str:
    enrichment_status = report.get("enrichment_status", "full")
    enrichment_note = (
        f" (**enrichment_degraded: {enrichment_status}**)" if enrichment_status != "full" else ""
    )
    lines = [
        f"# Stale Detect Report: {report['family']}/{report['platform']}",
        "",
        f"- Knowledge SHA: `{report['knowledge_repo_sha']}`{enrichment_note}",
        f"- Files scanned: {report['files_scanned']}",
        f"- Stale pages: {report['stale_pages']}",
        "",
    ]
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
    args = parser.parse_args(argv)

    report = scan_product(
        args.family,
        args.platform,
        content_root=args.content_root,
        knowledge_root=args.knowledge_root,
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