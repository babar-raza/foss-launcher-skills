#!/usr/bin/env python3
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

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

from lib.backlink_targets import (
    FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE,
    WRONG_ANCHOR_TEXT,
    DUPLICATE_LINK,
    DUPLICATE_SUBDOMAIN,
    PageType,
    classify_compliance,
    classify_page_type,
    count_qualifying_com_links,
    extract_qualifying_com_links,
    load_target_map,
    resolve_backlink,
)
# TC14 (2026-08-21): reuse the exact same anchor-text/display-map logic the
# insertion engine itself uses, so the audit's WRONG_ANCHOR_TEXT expectation
# can never drift from what backfill would actually write -- not a second,
# independently-maintained copy of this logic. Dotted import (not a bare
# sibling import) so this works whether backlink_audit.py is run directly
# or imported as commands.ops.backlink_audit by another module/test.
from commands.ops.backlink_backfill import _expected_anchor_text, _load_display_maps  # noqa: E402

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
STATUS_FAMILY_FALLBACK = FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE
# TC14 (2026-08-21): these 3 statuses were already returned by
# classify_compliance() (added TC2/TC10) but audit_file() never surfaced
# them -- DUPLICATE_LINK/DUPLICATE_SUBDOMAIN needed no new inputs (the
# unconditional part of classify_compliance() already computes them from
# existing_urls alone); WRONG_ANCHOR_TEXT needed the opt-in
# existing_links/expected_anchor_text kwargs, which audit_file() never
# passed, so it could never fire even though the detection logic existed.
STATUS_WRONG_ANCHOR_TEXT = WRONG_ANCHOR_TEXT
STATUS_DUPLICATE_LINK    = DUPLICATE_LINK
STATUS_DUPLICATE_SUBDOMAIN = DUPLICATE_SUBDOMAIN


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
    family_fallback: int = 0
    skipped: int = 0
    errors: int = 0
    wrong_anchor_text: int = 0    # TC14 (2026-08-21)
    duplicate_link: int = 0       # TC14 (2026-08-21)
    duplicate_subdomain: int = 0  # TC14 (2026-08-21)


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
    canonical_overrides: dict | None = None,
    families_map: dict | None = None,
    platforms_map: dict | None = None,
    exact_deep_match_enabled: bool = False,
    authority: dict | None = None,
) -> AuditRecord:
    """Audit a single file and return an AuditRecord.

    families_map/platforms_map: (TC14, 2026-08-21) display-name maps from
    _load_display_maps(), used to compute the expected anchor text for
    WRONG_ANCHOR_TEXT detection. Optional -- omitting either (the prior
    call shape) disables anchor-text checking but keeps every other status
    exactly as before, matching classify_compliance()'s own opt-in contract.

    exact_deep_match_enabled/authority: (BL-AUDIT-DEEP-WIRE, 2026-08-24) the
    CLI's --deep/--authority flags were parsed but never actually threaded
    into resolve_backlink() -- this function always resolved against the
    shallow family/platform target only, so any reference.aspose.org page
    correctly deep-linked to its exact class URL (by backlink_backfill.py
    --deep, or pre-existing) was misclassified WRONG_TARGET (confirmed live:
    471 of 497 WRONG_TARGET results on a post-backfill reference.aspose.org
    audit were pages just written with a correct, deliberate deep link).
    Threading these through (matching backlink_backfill.py's own
    resolve_backlink() call) fixes it; omitting both preserves the exact
    prior (shallow-only) resolution for every existing caller.
    """
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
        canonical_overrides=canonical_overrides,
        exact_deep_match_enabled=exact_deep_match_enabled,
        authority=authority,
        source_file=rel,
    )

    # Read body text and count qualifying links
    warnings: list[str] = []
    try:
        body_text = _read_body_text(file_path, subdomain or "")
    except RuntimeError as exc:
        warnings.append(str(exc))
        body_text = ""

    link_count, link_urls = count_qualifying_com_links(body_text)

    # TC14 (2026-08-21): (anchor_text, url) pairs + the governed expected
    # anchor text, enabling WRONG_ANCHOR_TEXT detection -- both are opt-in
    # on classify_compliance() (omitting either preserves prior URL-only
    # behavior exactly), so this only activates when a real target and
    # display maps are available.
    existing_links = extract_qualifying_com_links(body_text)
    expected_anchor_text = None
    if chosen_url and family and families_map is not None and platforms_map is not None:
        try:
            expected_anchor_text = _expected_anchor_text(
                chosen_url, family, platform, families_map, platforms_map,
                target_type=chosen_type, source_subdomain=subdomain,
            )
        except Exception:
            expected_anchor_text = None

    # Determine compliance status (A2 P0: pass chosen_target_type/subdomain for FAMILY_FALLBACK detection)
    status = classify_compliance(link_count, link_urls, chosen_url,
                                  family=family, platform=platform,
                                  chosen_target_type=chosen_type,
                                  chosen_target_subdomain=chosen_sd,
                                  existing_links=existing_links,
                                  expected_anchor_text=expected_anchor_text)

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
    canonical_overrides: dict | None = None,
    exact_deep_match_enabled: bool = False,
    authority: dict | None = None,
) -> tuple[list[AuditRecord], AuditTotals]:
    """Run audit across all matching content files. Returns (records, totals)."""
    files = walk_content(repo_root, subdomains, family_filter, platform_filter)
    print(f"  Scanning {len(files)} files...", file=sys.stderr)

    # TC14 (2026-08-21): loaded once for the whole run, not per file --
    # needed for WRONG_ANCHOR_TEXT's expected-anchor-text computation.
    families_map, platforms_map = _load_display_maps(repo_root)

    records: list[AuditRecord] = []
    totals = AuditTotals(scanned=len(files))

    for fpath in files:
        try:
            rec = audit_file(
                fpath, repo_root, target_map, canonical_overrides=canonical_overrides,
                families_map=families_map, platforms_map=platforms_map,
                exact_deep_match_enabled=exact_deep_match_enabled, authority=authority,
            )
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
        elif s == STATUS_FAMILY_FALLBACK: totals.family_fallback += 1
        elif s == STATUS_SKIPPED:      totals.skipped += 1
        elif s == STATUS_WRONG_ANCHOR_TEXT: totals.wrong_anchor_text += 1
        elif s == STATUS_DUPLICATE_LINK:    totals.duplicate_link += 1
        elif s == STATUS_DUPLICATE_SUBDOMAIN: totals.duplicate_subdomain += 1

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
                "over_limit": 0, "blocked_target": 0,
                "family_fallback": 0, "skipped": 0,
                "wrong_anchor_text": 0, "duplicate_link": 0,
                "duplicate_subdomain": 0}

    key_map = {
        STATUS_MISSING: "missing", STATUS_COMPLIANT: "compliant",
        STATUS_WRONG_TARGET: "wrong_target", STATUS_OVER_LIMIT: "over_limit",
        STATUS_BLOCKED_TARGET: "blocked_target",
        STATUS_FAMILY_FALLBACK: "family_fallback",
        STATUS_SKIPPED: "skipped",
        STATUS_WRONG_ANCHOR_TEXT: "wrong_anchor_text",
        STATUS_DUPLICATE_LINK: "duplicate_link",
        STATUS_DUPLICATE_SUBDOMAIN: "duplicate_subdomain",
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
    wrong_anchor = [
        {"file": r.file, "existing_urls": r.existing_com_links, "target_url": r.chosen_target_url}
        for r in records if r.status == STATUS_WRONG_ANCHOR_TEXT
    ]
    duplicates = [
        {"file": r.file, "urls": r.existing_com_links}
        for r in records if r.status in (STATUS_DUPLICATE_LINK, STATUS_DUPLICATE_SUBDOMAIN)
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
        "wrong_anchor_text": wrong_anchor,
        "duplicates": duplicates,
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
        f"| WRONG_ANCHOR_TEXT | {t['wrong_anchor_text']} |",
        f"| DUPLICATE_LINK | {t['duplicate_link']} |",
        f"| DUPLICATE_SUBDOMAIN | {t['duplicate_subdomain']} |",
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

    if report.get("wrong_anchor_text"):
        lines += ["", "## WRONG_ANCHOR_TEXT (correct URL, wrong wording)", ""]
        for wa in report["wrong_anchor_text"]:
            existing = ", ".join(wa["existing_urls"]) if wa["existing_urls"] else "(none)"
            lines.append(f"- `{wa['file']}` existing: {existing} (target: {wa['target_url']})")

    if report.get("duplicates"):
        lines += ["", "## DUPLICATE_LINK / DUPLICATE_SUBDOMAIN", ""]
        for dup in report["duplicates"]:
            lines.append(f"- `{dup['file']}` — {', '.join(dup['urls'])}")

    lines += [
        "", "---",
        "*Gate: 0 MISSING + 0 WRONG_TARGET + 0 OVER_LIMIT + 0 BLOCKED_TARGET + "
        "0 WRONG_ANCHOR_TEXT + 0 DUPLICATE_LINK + 0 DUPLICATE_SUBDOMAIN required for push.*",
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
    parser.add_argument(
        "--deep", action="store_true", default=False,
        help="Enable deep authority lookup (reads backlink_authority.json if present)",
    )
    parser.add_argument(
        "--authority", default=None,
        help="Path to backlink_authority.json (default: data/backlinks/workspace/backlink_authority.json)",
    )
    parser.add_argument(
        "--kb-anchor-mode",
        choices=["LEGACY_COMPAT_MODE", "CANONICAL_POST_P0_MODE"],
        default="LEGACY_COMPAT_MODE",
        help="KB anchor compliance mode (default: LEGACY_COMPAT_MODE)",
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

    # Load canonical platform overrides (A2 P0 — same as backfill tool)
    canonical_overrides: dict | None = None
    _overrides_path = repo_root / "data" / "backlinks" / "platform_canonical_overrides.yaml"
    if _overrides_path.exists():
        try:
            import yaml as _yaml_ovr
            canonical_overrides = _yaml_ovr.safe_load(_overrides_path.read_text(encoding="utf-8"))
        except Exception as _exc:
            print(f"  WARN: Could not load canonical overrides: {_exc}", file=sys.stderr)

    # Determine output paths
    reports_dir = repo_root / "reports" / "backlinks"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if args.output:
        json_out = Path(args.output)
        md_out = json_out.with_suffix(".md")
    else:
        json_out = reports_dir / f"backlink_audit_{ts}.json"
        md_out = reports_dir / f"backlink_audit_{ts}.md"

    # Load deep authority if --deep (BL-AUDIT-DEEP-WIRE, 2026-08-24: mirrors
    # backlink_backfill.py's own --deep loading -- previously args.deep/
    # args.authority were parsed but never used anywhere in this file).
    authority_data = None
    if args.deep:
        authority_path = (Path(args.authority) if args.authority
                          else repo_root / "data" / "backlinks" / "workspace" / "backlink_authority.json")
        if authority_path.exists():
            authority_data = json.loads(authority_path.read_text(encoding="utf-8"))
            print(f"  --deep: loaded authority from {authority_path} "
                  f"({len(authority_data.get('authority', {}))} records)", file=sys.stderr)
        else:
            print(f"WARNING: --deep but authority not found: {authority_path}", file=sys.stderr)

    # Run audit
    print(f"Running backlink audit (generator v{SCRIPT_VERSION})...", file=sys.stderr)
    records, totals = run_audit(
        repo_root=repo_root,
        target_map=target_map,
        subdomains=args.subdomain,
        family_filter=args.family,
        platform_filter=args.platform,
        canonical_overrides=canonical_overrides,
        exact_deep_match_enabled=bool(args.deep and authority_data),
        authority=authority_data,
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
    print(f"  WRONG_ANCHOR_TEXT:   {t.wrong_anchor_text}", file=sys.stderr)
    print(f"  DUPLICATE_LINK:      {t.duplicate_link}", file=sys.stderr)
    print(f"  DUPLICATE_SUBDOMAIN: {t.duplicate_subdomain}", file=sys.stderr)
    print(f"  SKIPPED:        {t.skipped}", file=sys.stderr)
    print(f"  Errors:         {t.errors}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  JSON: {json_out}", file=sys.stderr)
    print(f"  MD:   {md_out}", file=sys.stderr)

    for rec in records:
        if rec.status in (STATUS_MISSING, STATUS_WRONG_TARGET,
                          STATUS_OVER_LIMIT, STATUS_BLOCKED_TARGET,
                          STATUS_WRONG_ANCHOR_TEXT, STATUS_DUPLICATE_LINK,
                          STATUS_DUPLICATE_SUBDOMAIN):
            print(f"  [{rec.status}] {rec.file}", file=sys.stderr)
        elif rec.status == STATUS_COMPLIANT and args.show_compliant:
            print(f"  [COMPLIANT] {rec.file}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
