"""Deterministic content-vs-knowledge API accuracy auditor.

Extracts every API token (class names, method calls, property access,
enum members, imports) from content files and verifies each against
the merged api_surface.json knowledge model. Also validates the
evidence: frontmatter block required by S-24.

Usage:
    python scripts/audit.py {family} {platform}      # Single product
    python scripts/audit.py all                        # All products
    python scripts/audit.py --files path1.md path2.md  # Specific files
    python scripts/audit.py all --json                 # Machine-readable
    python scripts/audit.py all --check-snippets       # + advisory snippet coverage
"""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Imports from extracted modules (knowledge_core, token_ops).
# All symbols re-exported here so existing "from audit import X" still works.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# --- Standalone repo path resolution via config_loader ---
_HERE = Path(__file__).resolve().parent          # scripts/pipeline/
_SCRIPTS = _HERE.parent                          # scripts/
import sys as _sys
if str(_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS))
from config_loader import (                       # noqa: E402
    ConfigError as _ConfigError,
    resolve_content_repo as _resolve_content_repo,
    resolve_reports_root as _resolve_reports_root,
    resolve_knowledge_root as _resolve_knowledge_root,
)
# --------------------------------------------------------

from knowledge_core import (  # noqa: E402
    KNOWLEDGE_ROOT,
    PLATFORM_MAP,
    PLATFORM_RMAP,
    SITE_PATHS,
    LOCALE_RE,
    Knowledge,
    discover_content,
    discover_products,
    infer_product,
    parse_frontmatter,
    verify_evidence,
    _FRONTMATTER_RE,
)
from token_ops import (  # noqa: E402
    PLATFORM_SDK_CLASSES,
    PROPERTY_CHAIN_CLASSES,
    Token,
    Finding,
    extract_tokens,
    verify_tokens,
)


def _log(*args, **kwargs):
    """Print to stderr so stdout stays clean for --json."""
    print(*args, file=sys.stderr, **kwargs)

try:
    CONTENT_ROOT = _resolve_content_repo() / "content"
except _ConfigError:
    CONTENT_ROOT = None  # content repo not configured; CLI will error if path needed
REPORTS_DIR = _resolve_reports_root() / "audit"
QUALITY_TREND_MAX_ENTRIES = 180


# ---------------------------------------------------------------------------
# Internal link validator
# ---------------------------------------------------------------------------
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

# Map from hostname to content directory patterns
_SITE_CONTENT_MAP = {
    "docs.aspose.org":      "content/docs.aspose.org/en",
    "blog.aspose.org":      "content/blog.aspose.org",
    "kb.aspose.org":        "content/kb.aspose.org/en",
    "products.aspose.org":  "content/products.aspose.org/en",
    "reference.aspose.org": "content/reference.aspose.org/en",
}

def _resolve_link_to_file(url, source_filepath):
    """Resolve an internal link URL to a content file path.

    Returns (Path, True) if link is internal and resolvable,
    (Path, False) if internal but NOT found, or (None, None) for external/skip.
    """
    url = url.split("#")[0].split("?")[0].rstrip("/")  # strip anchor/query/trailing slash
    if not url:
        return None, None

    # Absolute URL: https://site.aspose.org/path/...
    for hostname, content_dir in _SITE_CONTENT_MAP.items():
        prefix = f"https://{hostname}/"
        if url.startswith(prefix):
            rel_path = url[len(prefix):]
            return _check_content_path(Path(content_dir), rel_path), False

    # Relative URL starting with /
    if url.startswith("/"):
        # Determine which site this file belongs to
        source_str = str(source_filepath).replace("\\", "/")
        for hostname, content_dir in _SITE_CONTENT_MAP.items():
            if content_dir.replace("\\", "/") in source_str:
                return _check_content_path(Path(content_dir), url.lstrip("/")), False

    return None, None

def _check_content_path(base, rel_path):
    """Check if a content path resolves to a real file. Returns the Path if found, None if not."""
    rel_path = rel_path.strip("/")
    candidates = [
        base / rel_path / "_index.md",
        base / rel_path / "index.md",
        base / (rel_path + ".md"),
        base / rel_path,  # exact file
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def verify_internal_links(filepath):
    """Check all markdown links in a file for broken internal references.

    Returns a list of Finding objects.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return []

    # Strip frontmatter
    m = _FRONTMATTER_RE.match(text)
    body = text[m.end():] if m else text

    findings = []
    for line_no, line in enumerate(body.splitlines(), start=(text[:m.end()].count("\n") + 1 if m else 1)):
        for match in _MD_LINK_RE.finditer(line):
            link_text, url = match.group(1), match.group(2)
            # Skip external links, mailto, images, anchors-only
            if url.startswith(("mailto:", "http://", "#")):
                continue
            if url.startswith("https://") and not any(
                h in url for h in _SITE_CONTENT_MAP
            ):
                continue  # external https link

            resolved, _ = _resolve_link_to_file(url, filepath)
            if resolved is None and _ is None:
                continue  # not an internal link
            if resolved is None:
                findings.append(Finding(
                    "WARN", filepath, line_no,
                    f"Broken internal link: [{link_text}]({url})",
                    "Target page does not exist in content/",
                ))

    return findings


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------
def report_text(all_findings, products_checked):
    """Generate human-readable report."""
    lines = [
        f"# Content API Audit Report",
        f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    total_fails = sum(1 for f in all_findings if f.level == "FAIL")
    total_warns = sum(1 for f in all_findings if f.level == "WARN")
    total_infos = sum(1 for f in all_findings if f.level == "INFO")

    lines.append("## Summary")
    lines.append(f"Products checked: {len(products_checked)}")
    summary = f"**FAIL: {total_fails}** | WARN: {total_warns}"
    if total_infos:
        summary += f" | INFO: {total_infos}"
    lines.append(summary)
    lines.append("")

    if not all_findings:
        lines.append("No issues found.")
        return "\n".join(lines)

    # Group by file
    by_file = defaultdict(list)
    for f in all_findings:
        by_file[str(f.filepath)].append(f)

    fails = [f for f in all_findings if f.level == "FAIL"]
    warns = [f for f in all_findings if f.level == "WARN"]

    if fails:
        lines.append("## FAIL — Must Fix")
        lines.append("")
        for filepath in sorted(set(str(f.filepath) for f in fails)):
            lines.append(f"### {filepath}")
            for f in sorted(by_file[filepath], key=lambda x: x.line_no):
                if f.level == "FAIL":
                    line = f"- **Line {f.line_no}**: {f.message}"
                    if f.suggestion:
                        line += f" -> {f.suggestion}"
                    lines.append(line)
            lines.append("")

    if warns:
        lines.append("## WARN — Review")
        lines.append("")
        for filepath in sorted(set(str(f.filepath) for f in warns)):
            lines.append(f"### {filepath}")
            for f in sorted(by_file[filepath], key=lambda x: x.line_no):
                if f.level == "WARN":
                    line = f"- **Line {f.line_no}**: {f.message}"
                    if f.suggestion:
                        line += f" -> {f.suggestion}"
                    lines.append(line)
            lines.append("")

    infos = [f for f in all_findings if f.level == "INFO"]
    if infos:
        lines.append("## INFO — Advisory (snippet coverage)")
        lines.append("")
        for filepath in sorted(set(str(f.filepath) for f in infos)):
            lines.append(f"### {filepath}")
            for f in sorted(by_file[filepath], key=lambda x: x.line_no):
                if f.level == "INFO":
                    line = f"- **Line {f.line_no}**: {f.message}"
                    if f.suggestion:
                        line += f" -> {f.suggestion}"
                    lines.append(line)
            lines.append("")

    return "\n".join(lines)


def report_json(all_findings, products_checked):
    """Generate machine-readable JSON report."""
    return json.dumps({
        "date": datetime.now(timezone.utc).isoformat(),
        "products_checked": products_checked,
        "total_fails": sum(1 for f in all_findings if f.level == "FAIL"),
        "total_warns": sum(1 for f in all_findings if f.level == "WARN"),
        "total_checked": len(all_findings),
        "findings": [
            {
                "level": f.level,
                "file": str(f.filepath),
                "line": f.line_no,
                "message": f.message,
                "suggestion": f.suggestion,
            }
            for f in all_findings
        ],
    }, indent=2)


# ---------------------------------------------------------------------------
# Quality trend tracking (batch mode only)
# ---------------------------------------------------------------------------

def _append_quality_trend(products_summary: list) -> None:
    """Append one entry to reports/audit/quality_trend.jsonl (append-only, batch runs only)."""
    trend_path = REPORTS_DIR / "quality_trend.jsonl"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "products": products_summary,
    }
    try:
        with trend_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _log(f"  quality_trend.jsonl updated")
    except Exception as exc:
        _log(f"  WARNING: could not write quality_trend.jsonl: {exc}")


def _write_quality_baseline(products_summary: list) -> None:
    """Overwrite reports/audit/quality_baseline.json with latest run results."""
    baseline_path = REPORTS_DIR / "quality_baseline.json"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        baseline_path.write_text(
            json.dumps(
                {"updated_at": datetime.now(timezone.utc).isoformat(),
                 "products": products_summary},
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        _log(f"  WARNING: could not write quality_baseline.json: {exc}")


def _prune_quality_trend() -> None:
    """Keep only the most recent QUALITY_TREND_MAX_ENTRIES entries in quality_trend.jsonl."""
    trend_path = REPORTS_DIR / "quality_trend.jsonl"
    if not trend_path.exists():
        return
    try:
        lines = trend_path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= QUALITY_TREND_MAX_ENTRIES:
            return
        kept = lines[-QUALITY_TREND_MAX_ENTRIES:]
        trend_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        removed = len(lines) - len(kept)
        _log(f"  quality_trend.jsonl pruned: removed {removed} oldest entries, kept {len(kept)}")
    except Exception as exc:
        _log(f"  WARNING: could not prune quality_trend.jsonl: {exc}")


def verify_snippet_coverage(filepath, knowledge):
    """Check whether code blocks in content have matching verified snippets.

    This is an advisory (INFO-level) check.  For each fenced code block in
    the markdown file, it extracts class and method tokens and checks if any
    snippet in the snippet index contains the same classes/methods.  If no
    match is found, an INFO finding is emitted.

    Only runs when the knowledge model has a populated snippet_index.
    """
    findings = []
    if not knowledge.snippet_index:
        return findings

    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError:
        return findings

    lines = text.splitlines()
    in_code = False
    code_start = 0
    code_lines = []

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                # End of code block — analyze it
                code_text = "\n".join(code_lines)
                if code_text.strip():
                    _check_code_block_snippets(
                        code_text, code_start, filepath, knowledge, findings)
                in_code = False
                code_lines = []
            else:
                in_code = True
                code_start = line_no
                code_lines = []
        elif in_code:
            code_lines.append(line)

    return findings


def _check_code_block_snippets(code_text, line_no, filepath, knowledge,
                                findings):
    """Check a single code block against snippet index entries."""
    # Extract class/method references from the code block
    block_classes = set()
    block_methods = set()

    for cls_name in knowledge.classes:
        if cls_name in code_text:
            block_classes.add(cls_name)
            for mname in knowledge.methods.get(cls_name, set()):
                if (f"{cls_name}.{mname}" in code_text
                        or f".{mname}(" in code_text):
                    block_methods.add(f"{cls_name}.{mname}")

    # If no API tokens found in this code block, skip
    if not block_classes:
        return

    # Check if any snippet shares classes+methods with this block
    for entry in knowledge.snippet_index:
        if not isinstance(entry, dict):
            continue
        snip_classes = set(entry.get("classes_used", []))
        snip_methods = set(entry.get("methods_used", []))

        # Match: at least one class AND (one method in common, or no methods extracted)
        if block_classes & snip_classes:
            if not block_methods or (block_methods & snip_methods):
                return  # Found a matching snippet

    # No matching snippet found — emit advisory
    classes_str = ", ".join(sorted(block_classes)[:5])
    findings.append(Finding(
        "INFO", filepath, line_no,
        f"Code block at line {line_no} has no matching verified snippet "
        f"(uses: {classes_str})",
        "Consider extracting code from repo examples instead of generating"
    ))


def audit_product(family, platform, check_snippets=False):
    """Audit a single product. Returns list of findings.

    Evidence checking (evidence: frontmatter block) is always enabled.
    """
    knowledge = Knowledge(family, platform)
    if not knowledge.available:
        _log(f"  SKIP {family}/{platform}: no knowledge model")
        return []

    files = discover_content(family, platform)
    if not files:
        _log(f"  SKIP {family}/{platform}: no content files")
        return []

    _log(f"  {family}/{platform}: {len(files)} files, tier {knowledge.surface_tier}")

    findings = []
    for f in files:
        tokens = extract_tokens(f, platform)
        file_findings = verify_tokens(tokens, knowledge, f)
        findings.extend(file_findings)
        fm = parse_frontmatter(f)
        ev_findings = verify_evidence(fm, knowledge, f)
        findings.extend(ev_findings)
        findings.extend(verify_internal_links(f))
        if check_snippets:
            findings.extend(verify_snippet_coverage(f, knowledge))

    fails = sum(1 for f in findings if f.level == "FAIL")
    warns = sum(1 for f in findings if f.level == "WARN")
    _log(f"    -> {fails} FAIL, {warns} WARN")

    return findings


def audit_files(file_paths, check_snippets=False):
    """Audit specific files, inferring product from path.

    Evidence checking (evidence: frontmatter block) is always enabled.
    """
    findings = []
    knowledge_cache = {}

    for fp in file_paths:
        fp = Path(fp)
        if not fp.exists():
            _log(f"  SKIP {fp}: file not found")
            continue

        family, platform = infer_product(fp)
        if not family:
            _log(f"  SKIP {fp}: cannot infer product")
            continue

        key = (family, platform)
        if key not in knowledge_cache:
            knowledge_cache[key] = Knowledge(family, platform)

        knowledge = knowledge_cache[key]
        if not knowledge.available:
            _log(f"  SKIP {fp}: no knowledge for {family}/{platform}")
            continue

        tokens = extract_tokens(fp, platform)
        file_findings = verify_tokens(tokens, knowledge, fp)
        findings.extend(file_findings)
        fm = parse_frontmatter(fp)
        ev_findings = verify_evidence(fm, knowledge, fp)
        file_findings.extend(ev_findings)
        findings.extend(ev_findings)
        link_findings = verify_internal_links(fp)
        file_findings.extend(link_findings)
        findings.extend(link_findings)
        if check_snippets:
            snippet_findings = verify_snippet_coverage(fp, knowledge)
            file_findings.extend(snippet_findings)
            findings.extend(snippet_findings)

        fails = sum(1 for f in file_findings if f.level == "FAIL")
        if fails:
            _log(f"  FAIL {fp}: {fails} failures")

    return findings


def main():
    args = sys.argv[1:]
    json_mode = "--json" in args
    fail_fast = "--fail-fast" in args
    files_mode = "--files" in args
    check_snippets = "--check-snippets" in args

    args = [a for a in args if not a.startswith("--")]

    products_summary = None  # populated in "all" batch mode only; used for quality trend

    if files_mode:
        findings = audit_files(args, check_snippets=check_snippets)
        products_checked = ["(file mode)"]
    elif len(args) >= 2:
        family, platform = args[0], args[1]
        _log(f"Auditing {family}/{platform}...")
        findings = audit_product(family, platform, check_snippets=check_snippets)
        products_checked = [f"{family}/{platform}"]
    elif len(args) == 1 and args[0] == "all":
        products = discover_products()
        _log(f"Auditing {len(products)} products...")
        findings = []
        products_checked = []
        products_summary = []  # per-product stats for quality_trend
        for family, platform in products:
            product_findings = audit_product(family, platform, check_snippets=check_snippets)
            findings.extend(product_findings)
            products_checked.append(f"{family}/{platform}")
            # Collect per-product warn breakdown for trend tracking
            warn_by_type: dict[str, int] = {}
            for f in product_findings:
                if f.level == "WARN":
                    key = f.message.split(":")[0].strip() if ":" in f.message else f.message[:40]
                    warn_by_type[key] = warn_by_type.get(key, 0) + 1
            products_summary.append({
                "family": family,
                "platform": platform,
                "fail": sum(1 for f in product_findings if f.level == "FAIL"),
                "warn": sum(1 for f in product_findings if f.level == "WARN"),
                "warn_by_type": warn_by_type,
                "pages": len(set(str(f.filepath) for f in product_findings)),
            })
            if fail_fast and any(f.level == "FAIL" for f in product_findings):
                break
    else:
        print(__doc__)
        sys.exit(1)

    if json_mode:
        print(report_json(findings, products_checked))
    else:
        report = report_text(findings, products_checked)
        print()
        print(report)

        # Write report file
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        report_path = REPORTS_DIR / f"batch-audit-{date_str}.md"
        report_path.write_text(report, encoding="utf-8")
        _log(f"\nReport written to {report_path}")

    # Quality trend tracking — batch mode only
    if products_summary is not None:
        _append_quality_trend(products_summary)
        _write_quality_baseline(products_summary)
        _prune_quality_trend()

    total_fails = sum(1 for f in findings if f.level == "FAIL")
    sys.exit(1 if total_fails > 0 else 0)


if __name__ == "__main__":
    main()
