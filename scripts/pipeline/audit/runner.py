"""runner.py — Core audit orchestration: audit_product, audit_files, main().

Extracted from audit.py (Phase 5). Orchestrates the per-product and per-file
audit workflow, delegating to links, snippets, and report sub-modules.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# sibling-import guard: sub-packages must add the pipeline root so they can
# import sibling top-level modules (knowledge_core, token_ops, core.*).
# This is not the antipattern -- Python adds the sub-package dir to sys.path,
# not the pipeline root. This guard is the correct workaround for the flat layout.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from knowledge_core import Knowledge  # noqa: E402
from content_discovery import (  # noqa: E402  (R-1b: was knowledge_core)
    discover_content,
    discover_products,
    infer_product,
)
from evidence_verifier import verify_evidence  # noqa: E402  (R-3b: was knowledge_core)
from core.markdown import parse_frontmatter  # noqa: E402  (R-2a: was knowledge_core)
from token_ops import (  # noqa: E402
    Finding,
    extract_tokens,
    verify_tokens,
)
from audit.links import verify_internal_links  # noqa: E402
from audit.snippets import verify_snippet_coverage  # noqa: E402
from audit.formats import verify_format_direction  # noqa: E402
from audit.phantom_methods import verify_phantom_methods  # noqa: E402
from audit.maven_coordinates import verify_maven_coordinates  # noqa: E402
from audit.frontmatter_schema import (  # noqa: E402
    verify_no_explicit_url,
    verify_no_non_english_aliases,
)
from audit.reports import (  # noqa: E402
    REPORTS_DIR,
    report_text,
    report_json,
    _append_quality_trend,
    _write_quality_baseline,
    _prune_quality_trend,
)


def _log(*args, **kwargs):
    """Print to stderr so stdout stays clean for --json."""
    print(*args, file=sys.stderr, **kwargs)


def _write_content_check_marker(fp: Path) -> None:
    """Write a pass marker for fp to reports/content-check/.

    The marker is consumed by scripts/ci/hooks/check_content_write_hook.sh to confirm
    that S-23 content-check passed before allowing a Write tool call on the file.
    Encoding: path separators replaced with underscores, matching the shell hook.

    Only writes markers for files under the content/ tree (relative path starting
    with 'content/'). Absolute paths and non-content paths are silently skipped —
    the hook only guards content/ writes, so markers for other paths are unused.
    """
    normalised = str(fp).replace("\\", "/")
    if not normalised.startswith("content/"):
        return
    marker_dir = Path("reports/content-check")
    marker_dir.mkdir(parents=True, exist_ok=True)
    encoded = normalised.replace("/", "_")
    (marker_dir / f"{encoded}.pass").write_text("", encoding="utf-8")


def verify_faq_structure(fp: Path, fm: dict) -> list:
    """FAIL if faq.list is non-empty in frontmatter — invisible to Hugo renderer.

    Hugo renders .Content (markdown body) only and does not iterate frontmatter
    YAML arrays. Any FAQ entries stored in faq.list are therefore never shown to
    users. This check enforces that FAQ content lives exclusively in the body as
    ### Question headings.

    Exception: pages with layout: plugin use a Hugo shortcode template that
    iterates .Params.faq.list directly — faq.list in frontmatter is by design
    for those pages and must not be flagged.
    """
    # layout: plugin pages render faq.list via Hugo template params — exempt
    if fm.get("layout") == "plugin":
        return []
    faq_block = fm.get("faq") or {}
    faq_list = faq_block.get("list", []) if isinstance(faq_block, dict) else []
    if not faq_list:
        return []
    return [Finding(
        level="FAIL",
        filepath=str(fp),
        line_no=1,
        message=(
            f"faq.list contains {len(faq_list)} entries in frontmatter but "
            "Hugo renders .Content only — all entries are invisible to users"
        ),
        suggestion=(
            "Regenerate using /new-kb-faq to materialize faq.list entries as "
            "### headings in the markdown body; remove faq.list from frontmatter"
        ),
    )]


CONTENT_ROOT = Path("content")


def audit_product(
    family: str,
    platform: str,
    check_evidence: bool = True,
    check_snippets: bool = False,
) -> list:
    """Audit a single product. Returns list of findings."""
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
        fm = parse_frontmatter(f)
        text = f.read_text(encoding="utf-8", errors="replace")
        tokens = extract_tokens(f, platform)
        file_findings = verify_tokens(tokens, knowledge, f)
        findings.extend(file_findings)
        findings.extend(verify_faq_structure(f, fm))
        if check_evidence:
            findings.extend(verify_evidence(fm, knowledge, f))
        findings.extend(verify_internal_links(f))
        findings.extend(verify_format_direction(str(f), family, platform))
        findings.extend(verify_phantom_methods(f, text, knowledge))
        findings.extend(verify_maven_coordinates(f))
        findings.extend(verify_no_explicit_url(f))
        findings.extend(verify_no_non_english_aliases(f))
        if check_snippets:
            findings.extend(verify_snippet_coverage(f, knowledge))

    fails = sum(1 for f in findings if f.level == "FAIL")
    warns = sum(1 for f in findings if f.level == "WARN")
    _log(f"    -> {fails} FAIL, {warns} WARN")

    return findings


def audit_files(
    file_paths: list,
    check_evidence: bool = True,
    check_snippets: bool = False,
) -> list:
    """Audit specific files, inferring product from path."""
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

        fm = parse_frontmatter(fp)
        text = fp.read_text(encoding="utf-8", errors="replace")
        tokens = extract_tokens(fp, platform)
        file_findings = verify_tokens(tokens, knowledge, fp)
        findings.extend(file_findings)
        faq_findings = verify_faq_structure(fp, fm)
        file_findings.extend(faq_findings)
        findings.extend(faq_findings)
        if check_evidence:
            findings.extend(verify_evidence(fm, knowledge, fp))
        link_findings = verify_internal_links(fp)
        file_findings.extend(link_findings)
        findings.extend(link_findings)
        format_findings = verify_format_direction(str(fp), family, platform)
        file_findings.extend(format_findings)
        findings.extend(format_findings)
        phantom_findings = verify_phantom_methods(fp, text, knowledge)
        file_findings.extend(phantom_findings)
        findings.extend(phantom_findings)
        maven_findings = verify_maven_coordinates(fp)
        file_findings.extend(maven_findings)
        findings.extend(maven_findings)
        url_findings = verify_no_explicit_url(fp)
        file_findings.extend(url_findings)
        findings.extend(url_findings)
        alias_findings = verify_no_non_english_aliases(fp)
        file_findings.extend(alias_findings)
        findings.extend(alias_findings)
        if check_snippets:
            snippet_findings = verify_snippet_coverage(fp, knowledge)
            file_findings.extend(snippet_findings)
            findings.extend(snippet_findings)

        fails = sum(1 for f in file_findings if f.level == "FAIL")
        if fails:
            _log(f"  FAIL {fp}: {fails} failures")
        else:
            _write_content_check_marker(fp)

    return findings


def main():
    args = sys.argv[1:]
    json_mode = "--json" in args
    fail_fast = "--fail-fast" in args
    files_mode = "--files" in args
    files_from_mode = "--files-from" in args
    check_evidence = "--no-evidence" not in args
    check_snippets = "--check-snippets" in args

    args = [a for a in args if not a.startswith("--")]

    products_summary = None  # populated in "all" batch mode only; used for quality trend
    files_scanned = 0  # tracks actual number of files examined (not findings count)

    if files_from_mode:
        # Read file paths from a text file (one path per line); handles large file lists
        # that would exceed the OS argument-list limit if passed as CLI args.
        if not args:
            _log("ERROR: --files-from requires a file path argument")
            sys.exit(1)
        from pathlib import Path as _Path
        file_list = _Path(args[0]).read_text(encoding="utf-8").splitlines()
        file_list = [p for p in file_list if p.strip()]
        findings = audit_files(file_list, check_evidence=check_evidence,
                               check_snippets=check_snippets)
        products_checked = ["(file mode)"]
        files_scanned = len(file_list)
    elif files_mode:
        findings = audit_files(args, check_evidence=check_evidence,
                               check_snippets=check_snippets)
        products_checked = ["(file mode)"]
        files_scanned = len(args)
    elif len(args) >= 2:
        family, platform = args[0], args[1]
        _log(f"Auditing {family}/{platform}...")
        findings = audit_product(family, platform, check_evidence=check_evidence,
                                 check_snippets=check_snippets)
        products_checked = [f"{family}/{platform}"]
        files_scanned = len(set(str(f.filepath) for f in findings))
    elif len(args) == 1 and args[0] == "all":
        products = discover_products()
        _log(f"Auditing {len(products)} products...")
        findings = []
        products_checked = []
        products_summary = []  # per-product stats for quality_trend
        for family, platform in products:
            product_findings = audit_product(family, platform,
                                             check_evidence=check_evidence,
                                             check_snippets=check_snippets)
            findings.extend(product_findings)
            products_checked.append(f"{family}/{platform}")
            files_scanned += len(set(str(f.filepath) for f in product_findings))
            # Collect per-product warn breakdown for trend tracking
            warn_by_type: dict[str, int] = {}
            for f in product_findings:
                if f.level == "WARN":
                    key = (f.message.split(":")[0].strip()
                           if ":" in f.message else f.message[:40])
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
        print(report_json(findings, products_checked, files_scanned=files_scanned))
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