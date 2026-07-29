"""
SEO-TITLE-CONSISTENCY-EVALUATOR title_consistency_evaluator.py
==================================================================
WARN-only, zero-write evaluator: checks every real docs-devguide-index and
kb-faq page's CURRENT title against title_templates.yaml's registered
pattern (scripts/seo/pipeline/title_templates.py::check_conformance).

Never writes to any content file. This is the first migration stage named
in the mission's design summary: "evaluator-first (WARN-only, zero writes)
-> 3-page pilot (frozen campaign) -> numeric non-regression gate ->
family-by-family expansion" -- SEO-TITLE-PILOT-BACKFILL-PDF-DEVGUIDE (the
next stage) selects its pilot targets from this report's WARN list, it does
not compute conformance itself.

Scope: docs_devguide_index and kb_faq page types only -- the two with a
real, planned backfill path. products_family_root is codify_only (already
conformant by definition) and reference_class is rigid-by-design (title IS
the class name, nothing to "evaluate" against a template). Checking those
here would be noise, not signal.

No LLM calls. No network calls. stdlib + pathlib + pyyaml only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_ROOT = _REPO_ROOT / "content"
REPORTS_DIR = _REPO_ROOT / "reports" / "seo"

try:
    from seo.pipeline.title_templates import check_conformance
except ImportError:
    from title_templates import check_conformance

# Platform directory slug -> display name used in real titles. Small and
# stable enough that a shared constant module would be overkill; matches
# the identical mapping in scripts/seo/get_keywords.py/review_keywords.py.
_PLATFORM_DISPLAY = {
    "net": ".NET", "java": "Java", "python": "Python",
    "cpp": "C++", "nodejs": "Node.js", "php": "PHP", "go": "Go",
}

_FAMILY_TITLE_RE = re.compile(r"^Aspose\.(\S+)\s+FOSS")


def _family_display_name(family: str) -> str:
    """Derive the correctly-cased family display name (e.g. "pdf" -> "PDF",
    "words" -> "Words") from the ALREADY-correct products.aspose.org family
    root title (title_templates.yaml's products_family_root entry: "already
    correct via the existing head_title convention -- codify, don't
    rewrite"). Falls back to family.upper() if that page is ever missing --
    every real family has one today, but this must never raise.
    """
    root_path = CONTENT_ROOT / "products.aspose.org" / "en" / family / "_index.md"
    title = _read_title(root_path)
    if title:
        match = _FAMILY_TITLE_RE.match(title)
        if match:
            return match.group(1)
    return family.upper()


def _platform_display_name(platform: str) -> str:
    return _PLATFORM_DISPLAY.get(platform, platform)


def _read_title(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    title = fm.get("title")
    return title if isinstance(title, str) else None


def _family_platform_from_devguide_path(path: Path) -> tuple[str, str] | None:
    # content/docs.aspose.org/en/{family}/{platform}/developer-guide/_index.md
    try:
        rel = path.relative_to(CONTENT_ROOT / "docs.aspose.org" / "en")
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 3 or parts[2] != "developer-guide":
        return None
    return parts[0], parts[1]


def _family_platform_from_faq_path(path: Path) -> tuple[str, str] | None:
    # content/kb.aspose.org/en/{family}/{platform}/faq.md
    try:
        rel = path.relative_to(CONTENT_ROOT / "kb.aspose.org" / "en")
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) != 3:
        return None
    return parts[0], parts[1]


def evaluate_devguide_pages() -> list[dict]:
    root = CONTENT_ROOT / "docs.aspose.org" / "en"
    results = []
    if not root.exists():
        return results
    for path in sorted(root.glob("*/*/developer-guide/_index.md")):
        fp = _family_platform_from_devguide_path(path)
        if fp is None:
            continue
        family, platform = fp
        title = _read_title(path)
        if title is None:
            continue
        rel_path = str(path.relative_to(CONTENT_ROOT.parent)).replace("\\", "/")
        conforms = check_conformance(
            title, "docs_devguide_index",
            family=_family_display_name(family), platform=_platform_display_name(platform),
        )
        results.append({
            "path": rel_path, "family": family, "platform": platform,
            "current_title": title, "page_type": "docs_devguide_index",
            "conforms": conforms,
        })
    return results


def evaluate_faq_pages() -> list[dict]:
    root = CONTENT_ROOT / "kb.aspose.org" / "en"
    results = []
    if not root.exists():
        return results
    for path in sorted(root.glob("*/*/faq.md")):
        fp = _family_platform_from_faq_path(path)
        if fp is None:
            continue
        family, platform = fp
        title = _read_title(path)
        if title is None:
            continue
        rel_path = str(path.relative_to(CONTENT_ROOT.parent)).replace("\\", "/")
        conforms = check_conformance(
            title, "kb_faq",
            family=_family_display_name(family), platform=_platform_display_name(platform),
        )
        results.append({
            "path": rel_path, "family": family, "platform": platform,
            "current_title": title, "page_type": "kb_faq",
            "conforms": conforms,
        })
    return results


def build_report() -> dict:
    devguide = evaluate_devguide_pages()
    faq = evaluate_faq_pages()
    all_pages = devguide + faq
    warn = [p for p in all_pages if not p["conforms"]]
    passed = [p for p in all_pages if p["conforms"]]

    return {
        "meta": {
            "generated_by": "title_consistency_evaluator.py",
            "total_evaluated": len(all_pages),
            "pass_count": len(passed),
            "warn_count": len(warn),
            "docs_devguide_index_total": len(devguide),
            "docs_devguide_index_warn": sum(1 for p in devguide if not p["conforms"]),
            "kb_faq_total": len(faq),
            "kb_faq_warn": sum(1 for p in faq if not p["conforms"]),
        },
        "warn": warn,
        "pass": passed,
    }


def main() -> None:
    report = build_report()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "title_consistency_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    m = report["meta"]
    print("=== Title Consistency Evaluator (WARN-only, zero content writes) ===")
    print(f"Total evaluated        : {m['total_evaluated']}")
    print(f"  PASS                 : {m['pass_count']}")
    print(f"  WARN                 : {m['warn_count']}")
    print(f"  docs_devguide_index  : {m['docs_devguide_index_warn']}/{m['docs_devguide_index_total']} WARN")
    print(f"  kb_faq               : {m['kb_faq_warn']}/{m['kb_faq_total']} WARN")
    print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    main()
