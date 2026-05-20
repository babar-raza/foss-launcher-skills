#!/usr/bin/env python3
# Adapted from aspose.org
"""backlink_audit.py — Full English content backlink compliance audit (TC-BL-003).

Walks all in-scope English content across docs, kb, reference, products, and blog
subdomains. For each file: classifies page type, resolves expected backlink target,
counts existing qualifying aspose.com links, and emits a compliance status.

Usage:
    python scripts/pipeline/commands/ops/backlink_audit.py
    python scripts/pipeline/commands/ops/backlink_audit.py --subdomain docs.aspose.org
    python scripts/pipeline/commands/ops/backlink_audit.py --family words
    python scripts/pipeline/commands/ops/backlink_audit.py --family words --platform python
    python scripts/pipeline/commands/ops/backlink_audit.py --output reports/backlinks/my_audit.json

Exit codes:
    0   Audit complete (report written, even if compliance issues found)
    1   Fatal error (target map missing, content root not found, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import os

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import (
    PageType,
    classify_compliance,
    classify_page_type,
    count_qualifying_com_links,
    load_target_map,
    resolve_backlink,
)

SCRIPT_VERSION = "1.0.0"

# Subdomains with their content roots relative to repo root
SUBDOMAIN_ROOTS: dict[str, str] = {
    "docs.aspose.org":      "content/docs.aspose.org/en",
    "kb.aspose.org":        "content/kb.aspose.org/en",
    "reference.aspose.org": "content/reference.aspose.org/en",
    "products.aspose.org":  "content/products.aspose.org/en",
    "blog.aspose.org":      "content/blog.aspose.org",
}

# Page types that are out-of-scope (skip without penalty)
OUT_OF_SCOPE_TYPES = {
    PageType.PRODUCTS_ROOT,
    PageType.BLOG_ARCHIVE,
    PageType.BLOG_UTILITY,
    PageType.SUBDOMAIN_ROOT,
    PageType.LOCALE_FILE,
    PageType.LOCALE_DIR,
    PageType.UNKNOWN_PATTERN,
}

STATUS_MISSING        = "MISSING"
STATUS_COMPLIANT      = "COMPLIANT"
STATUS_WRONG_TARGET   = "WRONG_TARGET"
STATUS_OVER_LIMIT     = "OVER_LIMIT"
STATUS_BLOCKED_TARGET = "BLOCKED_TARGET"
STATUS_SKIPPED        = "SKIPPED"


@dataclass
class AuditRecord:
    file: str
    subdomain: str
    family: str | None
    platform: str | None
    page_type: str
    status: str
    existing_com_link_count: int
    existing_com_links: list[str]
    chosen_target_url: str | None
    chosen_target_type: str | None
    chosen_target_subdomain: str | None
    fallback_reason: str | None
    resolution_evidence: str
    warning_messages: list[str] = field(default_factory=list)


@dataclass
class AuditTotals:
    scanned: int = 0
    missing: int = 0
    compliant: int = 0
    wrong_target: int = 0
    over_limit: int = 0
    blocked_target: int = 0
    skipped: int = 0
    errors: int = 0


def _read_body_text(file_path: Path, subdomain: str) -> str:
    """Read the content text for link-counting purposes.

    For products pages (YAML-only): extract overview.content value.
    For all others: return markdown body (after frontmatter).
    """
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Cannot read {file_path}: {exc}") from exc

    if subdomain == "products.aspose.org":
        return _extract_yaml_overview_content(raw)

    # For markdown pages: skip frontmatter block
    if raw.startswith("---"):
        second = raw.find("---", 3)
        if second != -1:
            return raw[second + 3:]
    return raw


def _extract_yaml_overview_content(raw: str) -> str:
    """Extract overview.content value from YAML frontmatter as plain text."""
    try:
        import yaml  # type: ignore
        # Products files have ---...--- frontmatter; extract just the YAML block
        fm_text = raw
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                fm_text = raw[3:end]
        data = yaml.safe_load(fm_text)
        if isinstance(data, dict):
            overview = data.get("overview", {})
            if isinstance(overview, dict):
                content = overview.get("content", "")
                return content if isinstance(content, str) else ""
    except Exception:
        pass
    # Fallback: simple regex
    match = re.search(
        r"overview:\s*\n(?:.*\n)*?\s+content:\s*[|>]?\s*\n((?:\s+.+\n?)*)", raw
    )
    return match.group(1) if match else ""


def _page_type_is_in_scope(pt: PageType) -> bool:
    return pt not in OUT_OF_SCOPE_TYPES


def audit_file(
    file_path: Path,
    repo_root: Path,
    target_map: dict,
) -> AuditRecord:
    """Audit a single file and return an AuditRecord."""
    rel = file_path.relative_to(repo_root).as_posix()

    # Classify page type
    try:
        pt, family, platform, subdomain = classify_page_type(file_path, repo_root)
    except Exception as exc:
        return AuditRecord(
            file=rel, subdomain="unknown", family=None, platform=None,
            page_type="ERROR", status=STATUS_SKIPPED,
            existing_com_link_count=0, existing_com_links=[],
            chosen_target_url=None, chosen_target_type=None,
            chosen_target_subdomain=None, fallback_reason=None,
            resolution_evidence=f"classify_page_type raised: {exc}",
            warning_messages=[str(exc)],
        )

    # Skip out-of-scope types
    if not _page_type_is_in_scope(pt):
        return AuditRecord(
            file=rel, subdomain=subdomain or "unknown", family=family, platform=platform,
            page_type=pt.value, status=STATUS_SKIPPED,
            existing_com_link_count=0, existing_com_links=[],
            chosen_target_url=None, chosen_target_type=None,
            chosen_target_subdomain=None, fallback_reason=None,
            resolution_evidence=f"Page type {pt.value} is out of scope",
        )

    # Resolve backlink target
    chosen_url, chosen_type, chosen_sd, fallback_reason = resolve_backlink(
        family=family or "",
        platform=platform,
        source_subdomain=subdomain or "",
        target_map=target_map,
    )

    # Read body text and count qualifying links
    warnings: list[str] = []
    try:
        body_text = _read_body_text(file_path, subdomain or "")
    except RuntimeError as exc:
        warnings.append(str(exc))
        body_text = ""

    link_count, link_urls = count_qualifying_com_links(body_text)

    # Determine compliance status (pass family/platform for full fallback chain check)
    status = classify_compliance(link_count, link_urls, chosen_url,
                                  family=family, platform=platform)

    # Build resolution evidence string
    if chosen_url:
        evidence = f"Target: {chosen_url} ({chosen_type} on {chosen_sd})"
        if fallback_reason:
            evidence += f" [fallback: {fallback_reason}]"
    else:
        evidence = "No safe target found after full fallback chain"
        if fallback_reason:
            evidence += f" — {fallback_reason}"

    return AuditRecord(
        file=rel, subdomain=subdomain or "unknown", family=family, platform=platform,
        page_type=pt.value, status=status,
        existing_com_link_count=link_count, existing_com_links=link_urls,
        chosen_target_url=chosen_url, chosen_target_type=chosen_type,
        chosen_target_subdomain=chosen_sd, fallback_reason=fallback_reason,
        resolution_evidence=evidence, warning_messages=warnings,
    )


def walk_content(
    repo_root: Path,
    subdomains: list[str] | None = None,
    family_filter: str | None = None,
    platform_filter: str | None = None,
) -> list[Path]:
    """Collect all .md files in the in-scope English content roots."""
    results: list[Path] = []
    target_subdomains = subdomains or list(SUBDOMAIN_ROOTS.keys())

    for sd in target_subdomains:
        if sd not in SUBDOMAIN_ROOTS:
            print(f"  WARN: Unknown subdomain '{sd}', skipping", file=sys.stderr)
            continue
        root = repo_root / SUBDOMAIN_ROOTS[sd]
        if not root.exists():
            print(f"  WARN: Content root not found: {root}", file=sys.stderr)
            continue

        for f in sorted(root.rglob("*.md")):
            if family_filter or platform_filter:
                rel = f.relative_to(root).as_posix()
                parts = rel.split("/")
                if family_filter and (len(parts) < 1 or parts[0] != family_filter):
                    continue
                if platform_filter and (len(parts) < 2 or parts[1] != platform_filter):
                    continue
            results.append(f)

    return results


def run_audit(
    repo_root: Path,
    target_map: dict,
    subdomains: list[str] | None = None,
    family_filter: str | None = None,
    platform_filter: str | None = None,
) -> tuple[list[AuditRecord], AuditTotals]:
    """Run audit across all matching content files. Returns (records, totals)."""
    files = walk_content(repo_root, subdomains, family_filter, platform_filter)
    print(f"  Scanning {len(files)} files...", file=sys.stderr)

    records: list[AuditRecord] = []
    totals = AuditTotals(scanned=len(files))

    for fpath in files:
        try:
            rec = audit_file(fpath, repo_root, target_map)
        except Exception as exc:
            rel = fpath.relative_to(repo_root).as_posix()
            rec = AuditRecord(
                file=rel, subdomain="unknown", family=None, platform=None,
                page_type="ERROR", status=STATUS_SKIPPED,
                existing_com_link_count=0, existing_com_links=[],
                chosen_target_url=None, chosen_target_type=None,
                chosen_target_subdomain=None, fallback_reason=None,
                resolution_evidence=f"Unhandled error: {exc}",
                warning_messages=[str(exc)],
            )
            totals.errors += 1

        records.append(rec)
        s = rec.status
        if s == STATUS_MISSING:        totals.missing += 1
        elif s == STATUS_COMPLIANT:    totals.compliant += 1
        elif s == STATUS_WRONG_TARGET: totals.wrong_target += 1
        elif s == STATUS_OVER_LIMIT:   totals.over_limit += 1
        elif s == STATUS_BLOCKED_TARGET: totals.blocked_target += 1
        elif s == STATUS_SKIPPED:      totals.skipped += 1

    return records, totals


def build_report(
    records: list[AuditRecord],
    totals: AuditTotals,
    target_map_hash: str,
) -> dict:
    """Build the full JSON report structure."""
    by_subdomain: dict[str, dict] = {}
    by_family: dict[str, dict] = {}

    def _counter() -> dict:
        return {"missing": 0, "compliant": 0, "wrong_target": 0,
                "over_limit": 0, "blocked_target": 0, "skipped": 0}

    key_map = {
        STATUS_MISSING: "missing", STATUS_COMPLIANT: "compliant",
        STATUS_WRONG_TARGET: "wrong_target", STATUS_OVER_LIMIT: "over_limit",
        STATUS_BLOCKED_TARGET: "blocked_target", STATUS_SKIPPED: "skipped",
    }

    for rec in records:
        sd = rec.subdomain
        fam = rec.family or "_unknown"
        if sd not in by_subdomain:
            by_subdomain[sd] = _counter()
        if fam not in by_family:
            by_family[fam] = _counter()
        if rec.status in key_map:
            by_subdomain[sd][key_map[rec.status]] += 1
            by_family[fam][key_map[rec.status]] += 1

    blocked = [
        {"file": r.file, "family": r.family, "platform": r.platform, "reason": r.resolution_evidence}
        for r in records if r.status == STATUS_BLOCKED_TARGET
    ]
    wrong = [
        {"file": r.file, "existing_urls": r.existing_com_links, "expected_url": r.chosen_target_url}
        for r in records if r.status == STATUS_WRONG_TARGET
    ]
    over = [
        {"file": r.file, "count": r.existing_com_link_count, "urls": r.existing_com_links}
        for r in records if r.status == STATUS_OVER_LIMIT
    ]

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": f"backlink_audit.py v{SCRIPT_VERSION}",
        "target_map_version": target_map_hash,
        "totals": asdict(totals),
        "by_subdomain": by_subdomain,
        "by_family": by_family,
        "blocked_targets": blocked,
        "wrong_targets": wrong,
        "over_limit": over,
        "records": [asdict(r) for r in records],
    }


def write_markdown_summary(report: dict, out_path: Path) -> None:
    """Write a human-readable Markdown summary."""
    t = report["totals"]
    lines = [
        "# Backlink Audit Summary",
        "",
        f"**Generated:** {report['generated_at']}",
        f"**Generator:** {report['generator']}",
        f"**Target map:** `{report['target_map_version'][:16]}...`",
        "",
        "## Overall Totals",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| Scanned | {t['scanned']} |",
        f"| COMPLIANT | {t['compliant']} |",
        f"| MISSING | {t['missing']} |",
        f"| WRONG_TARGET | {t['wrong_target']} |",
        f"| OVER_LIMIT | {t['over_limit']} |",
        f"| BLOCKED_TARGET | {t['blocked_target']} |",
        f"| SKIPPED | {t['skipped']} |",
        f"| Errors | {t['errors']} |",
        "",
        "## By Subdomain",
        "",
        "| Subdomain | COMPLIANT | MISSING | WRONG_TARGET | OVER_LIMIT | BLOCKED | SKIPPED |",
        "|-----------|-----------|---------|--------------|------------|---------|---------|",
    ]
    for sd, counts in sorted(report["by_subdomain"].items()):
        lines.append(
            f"| {sd} | {counts['compliant']} | {counts['missing']} | "
            f"{counts['wrong_target']} | {counts['over_limit']} | "
            f"{counts['blocked_target']} | {counts['skipped']} |"
        )

    lines += [
        "", "## By Family", "",
        "| Family | COMPLIANT | MISSING | WRONG_TARGET | OVER_LIMIT | BLOCKED | SKIPPED |",
        "|--------|-----------|---------|--------------|------------|---------|---------|",
    ]
    for fam, counts in sorted(report["by_family"].items()):
        lines.append(
            f"| {fam} | {counts['compliant']} | {counts['missing']} | "
            f"{counts['wrong_target']} | {counts['over_limit']} | "
            f"{counts['blocked_target']} | {counts['skipped']} |"
        )

    if report["blocked_targets"]:
        lines += ["", "## BLOCKED_TARGET (must resolve before push)", ""]
        for bt in report["blocked_targets"]:
            lines.append(f"- `{bt['file']}` — {bt['reason']}")

    if report["wrong_targets"]:
        lines += ["", "## WRONG_TARGET", ""]
        for wt in report["wrong_targets"]:
            existing = ", ".join(wt["existing_urls"]) if wt["existing_urls"] else "(none)"
            lines.append(f"- `{wt['file']}` existing: {existing} → expected: {wt['expected_url']}")

    if report["over_limit"]:
        lines += ["", "## OVER_LIMIT (manual review required)", ""]
        for ol in report["over_limit"]:
            lines.append(f"- `{ol['file']}` — {ol['count']} qualifying links")

    lines += [
        "", "---",
        "*Gate: 0 MISSING + 0 WRONG_TARGET + 0 OVER_LIMIT + 0 BLOCKED_TARGET required for push.*",
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backlink compliance audit for aspose.org content."
    )
    parser.add_argument(
        "--subdomain", nargs="+", choices=list(SUBDOMAIN_ROOTS.keys()),
        help="Restrict audit to specific subdomain(s)",
    )
    parser.add_argument("--family", help="Restrict audit to a specific product family")
    parser.add_argument(
        "--platform", help="Restrict audit to a specific platform (requires --family)"
    )
    parser.add_argument(
        "--output",
        help="Output JSON path (default: reports/backlinks/backlink_audit_{ts}.json)",
    )
    parser.add_argument(
        "--target-map", help="Path to data/aspose_com_targets.json (default: auto-discover)"
    )
    parser.add_argument(
        "--show-compliant", action="store_true",
        help="Include COMPLIANT records in console output (verbose)",
    )
    args = parser.parse_args()

    repo_root = _REPO_ROOT
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    # Load target map
    print(f"Loading target map...", file=sys.stderr)
    try:
        if args.target_map:
            target_map = json.loads(Path(args.target_map).read_text(encoding="utf-8"))
        else:
            target_map = load_target_map(repo_root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FATAL: Cannot load target map — {exc}", file=sys.stderr)
        return 1

    target_map_hash = target_map.get("provenance", {}).get("output_hash", "unknown")

    # Determine output paths
    reports_dir = repo_root / "reports" / "backlinks"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if args.output:
        json_out = Path(args.output)
        md_out = json_out.with_suffix(".md")
    else:
        json_out = reports_dir / f"backlink_audit_{ts}.json"
        md_out = reports_dir / f"backlink_audit_{ts}.md"

    # Run audit
    print(f"Running backlink audit (generator v{SCRIPT_VERSION})...", file=sys.stderr)
    records, totals = run_audit(
        repo_root=repo_root,
        target_map=target_map,
        subdomains=args.subdomain,
        family_filter=args.family,
        platform_filter=args.platform,
    )

    # Build and write report
    report = build_report(records, totals, target_map_hash)
    json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown_summary(report, md_out)

    # Console summary
    t = totals
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Backlink Audit Complete", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Scanned:        {t.scanned}", file=sys.stderr)
    print(f"  COMPLIANT:      {t.compliant}", file=sys.stderr)
    print(f"  MISSING:        {t.missing}", file=sys.stderr)
    print(f"  WRONG_TARGET:   {t.wrong_target}", file=sys.stderr)
    print(f"  OVER_LIMIT:     {t.over_limit}", file=sys.stderr)
    print(f"  BLOCKED_TARGET: {t.blocked_target}", file=sys.stderr)
    print(f"  SKIPPED:        {t.skipped}", file=sys.stderr)
    print(f"  Errors:         {t.errors}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  JSON: {json_out}", file=sys.stderr)
    print(f"  MD:   {md_out}", file=sys.stderr)

    for rec in records:
        if rec.status in (STATUS_MISSING, STATUS_WRONG_TARGET,
                          STATUS_OVER_LIMIT, STATUS_BLOCKED_TARGET):
            print(f"  [{rec.status}] {rec.file}", file=sys.stderr)
        elif rec.status == STATUS_COMPLIANT and args.show_compliant:
            print(f"  [COMPLIANT] {rec.file}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
