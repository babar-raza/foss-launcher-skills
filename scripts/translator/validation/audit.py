"""
Translation audit: scan existing translations for quality issues.

Output JSON schema:
  [
    {
      "file": "content/docs.aspose.org/es/cells/python/...",
      "src_file": "content/docs.aspose.org/en/cells/python/...",
      "lang": "es",
      "severity": "critical | minor | missing | parse_error | warning",
      "failures": ["Heading count mismatch: src=5 tgt=3"],
      "warnings": ["Paragraph count differs by 25%"]
    }
  ]

Usage:
    python -m translator audit --family cells --platform python --site docs.aspose.org
"""
from __future__ import annotations
import json
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator import ALL_LOCALES
from translator.parser.document import parse_file, HugoDocument
from translator.policy.loader import ContentTypePolicy
from translator.validation.checker import validate_translation, ValidationResult
from translator.validation.root_cause import classify_failures, summarize_root_causes

_log = logging.getLogger("translator.audit")

_SITE_CONFIGS = {
    "docs.aspose.org": {
        "en_root": "content/docs.aspose.org/en",
    },
    "kb.aspose.org": {
        "en_root": "content/kb.aspose.org/en",
    },
    "reference.aspose.org": {
        "en_root": "content/reference.aspose.org/en",
    },
    "products.aspose.org": {
        "en_root": "content/products.aspose.org/en",
    },
    "blog.aspose.org": {
        "en_root": "content/blog.aspose.org",
    },
}


def _derive_locale_path(src_path: str, site: str, tgt_lang: str) -> str:
    """
    Derive the locale file path from the English source path.

    Blog (blog.aspose.org):
      src: content/blog.aspose.org/{family}/{platform}/{slug}/index.md
      tgt: content/blog.aspose.org/{family}/{platform}/{slug}/index.{lang}.md

    All other sites (docs, kb, reference, products):
      src: content/{site}/en/{rest...}
      tgt: content/{site}/{lang}/{rest...}
      (replaces the first /en/ segment with /{lang}/)
    """
    if "blog.aspose.org" in site or "blog.aspose.org" in src_path:
        base = src_path[: src_path.rfind(".md")]
        return f"{base}.{tgt_lang}.md"
    else:
        return src_path.replace("/en/", f"/{tgt_lang}/", 1)


def audit_translations(
    family: str,
    platform: str,
    site: str = "all",
    locales: str = "all",
    repo_root: Optional[str] = None,
) -> list[dict]:
    """
    Scan translated files for quality issues.

    Returns a list of issue dicts (see module docstring for schema).
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    sites = list(_SITE_CONFIGS.keys()) if site == "all" else [site]
    langs = list(ALL_LOCALES) if locales == "all" else [l.strip() for l in locales.split(",")]

    issues: list[dict] = []

    for site_id in sites:
        cfg = _SITE_CONFIGS.get(site_id)
        if not cfg:
            _log.warning("Unknown site: %s", site_id)
            continue

        en_root = root / cfg["en_root"]

        if site_id == "blog.aspose.org":
            en_files = sorted(en_root.glob(f"{family}/{platform}/**/index.md"))
        else:
            en_files = sorted(en_root.glob(f"{family}/{platform}/**/*.md"))

        n_src = len(en_files)
        _log.info("audit: scanning %d source files × %d locales for %s/%s (%s)",
                  n_src, len(langs), family, platform, site_id)

        n_processed = 0
        n_fail = 0

        for en_file in en_files:
            en_path_str = str(en_file).replace("\\", "/")

            try:
                policy = ContentTypePolicy.for_path(en_path_str)
            except ValueError:
                continue

            if policy.skip:
                continue

            try:
                src_doc = parse_file(en_file)
            except Exception as e:
                _log.error("audit: ERROR %s — %s", en_path_str, e)
                continue

            for lang in langs:
                locale_path_str = _derive_locale_path(en_path_str, site_id, lang)
                locale_file = Path(locale_path_str)
                n_processed += 1

                if (n_processed % 50) == 0:
                    _log.info("audit: %d pairs scanned, %d failures so far", n_processed, n_fail)

                if not locale_file.exists():
                    issues.append({
                        "file": locale_path_str,
                        "src_file": en_path_str,
                        "lang": lang,
                        "failures": ["Locale file not found"],
                        "warnings": [],
                        "severity": "missing",
                    })
                    continue

                try:
                    tgt_doc = parse_file(locale_file)
                except Exception as e:
                    msg = f"Failed to parse frontmatter: {e}"
                    _log.error("audit: ERROR %s — %s", locale_path_str, msg)
                    issues.append({
                        "file": locale_path_str,
                        "src_file": en_path_str,
                        "lang": lang,
                        "failures": [msg],
                        "warnings": [],
                        "severity": "parse_error",
                    })
                    continue

                if not tgt_doc.body.strip():
                    issues.append({
                        "file": locale_path_str,
                        "src_file": en_path_str,
                        "lang": lang,
                        "failures": [],
                        "warnings": ["Empty body"],
                        "severity": "warning",
                    })
                    continue

                try:
                    result = validate_translation(src_doc, tgt_doc, policy, lang)
                except Exception as e:
                    _log.error("audit: ERROR %s — %s: %s", locale_path_str, type(e).__name__, e)
                    issues.append({
                        "file": locale_path_str,
                        "src_file": en_path_str,
                        "lang": lang,
                        "failures": [f"Unexpected error: {type(e).__name__}: {e}"],
                        "warnings": [],
                        "severity": "parse_error",
                    })
                    continue

                if result.failures or result.warnings:
                    severity = "critical" if result.failures else "minor"
                    n_fail += 1
                    _log.warning("audit: FAIL %s [%s] — %s",
                                 locale_path_str, lang,
                                 "; ".join(result.failures[:2]))
                    issue = {
                        "file": locale_path_str,
                        "src_file": en_path_str,
                        "lang": lang,
                        "failures": result.failures,
                        "warnings": result.warnings,
                        "severity": severity,
                    }
                    if result.failures:
                        issue["root_causes"] = classify_failures(result.failures)
                    issues.append(issue)

        _log.info("audit: complete — %d pairs, %d failures", n_processed, n_fail)

    return issues


def write_audit_report(issues: list[dict], output_path: str) -> None:
    """Write audit results to a JSON file."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "total_issues": len(issues),
        "by_root_cause": summarize_root_causes(issues),
        "issues": issues,
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    _log.info("Audit report written to %s (%d issues)", p, len(issues))
