"""audit/ — Content API audit package.

Extracted from audit.py (Phase 5). Each sub-module handles one responsibility:
- links.py: internal link verification
- snippets.py: snippet coverage advisory checks
- reports.py: report generation and quality trend tracking
- runner.py: orchestration (audit_product, audit_files, main)

Backward compat: when both audit.py and audit/ exist, Python imports from
this package (audit/ takes precedence over audit.py in the same directory).
All symbols that used to live in audit.py are re-exported here so existing
`from audit import X` call sites continue to work unmodified.

Architectural boundary (Phase 7 / Option A)
-------------------------------------------
``audit/`` is the **verification layer**: fast, deterministic, CI-blocking
checks that run without an LLM.  It answers: "does this file reference valid
API members?"

``content_eval/`` is the **quality evaluation layer**: holistic, rubric-driven
scoring that may call an LLM evaluator.  It answers: "is this page good enough
to ship?"

These two layers intentionally overlap on API-accuracy findings:
- ``audit/runner.py`` emits ``Finding`` objects directly from ``verify_tokens``
- ``content_eval/evaluators/api_accuracy.py`` calls ``verify_tokens`` and
  re-wraps the same findings as ``EvalFinding`` objects with a category code

The bridge in ``api_accuracy.py`` is the explicit, documented join point.
``remediate.py`` operates **only** on ``content_eval`` findings — audit-only
findings are not remediated.  This is by design: audit is a gate, not a fixer.
"""
import sys
from pathlib import Path

# sibling-import guard: sub-packages must add the pipeline root so they can
# import sibling top-level modules (knowledge_core, token_ops, core.*).
# This is not the antipattern -- Python adds the sub-package dir to sys.path,
# not the pipeline root. This guard is the correct workaround for the flat layout.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

# Re-export symbols that audit.py previously exposed.
# R-1b: discover_* sourced from content_discovery (canonical).
# R-3b: verify_evidence sourced from evidence_verifier (canonical).
# R-4: constants sourced from content_discovery (canonical).
from knowledge_core import Knowledge  # noqa: E402
from content_discovery import (  # noqa: E402  (R-1b/R-4: was knowledge_core)
    KNOWLEDGE_ROOT,
    PLATFORM_MAP,
    PLATFORM_RMAP,
    SITE_PATHS,
    LOCALE_RE,
    discover_content,
    discover_products,
    infer_product,
)
from evidence_verifier import verify_evidence  # noqa: E402  (R-3b: was knowledge_core)
from core.markdown import parse_frontmatter  # noqa: E402  (R-2b: was knowledge_core)
# _FRONTMATTER_RE removed from re-exports (R-2b): no external consumers via audit package
from token_ops import (  # noqa: E402
    PLATFORM_SDK_CLASSES,
    PROPERTY_CHAIN_CLASSES,
    Token,
    Finding,
    extract_tokens,
    verify_tokens,
)

from .links import (
    _MD_LINK_RE,
    _SITE_CONTENT_MAP,
    _resolve_link_to_file,
    _check_content_path,
    verify_internal_links,
)
from .snippets import (
    verify_snippet_coverage,
    _check_code_block_snippets,
)
from .reports import (
    REPORTS_DIR,
    QUALITY_TREND_MAX_ENTRIES,
    report_text,
    report_json,
    _load_trend_entries,
    _append_quality_trend,
    _write_quality_baseline,
    _prune_quality_trend,
)
from .runner import (
    CONTENT_ROOT,
    verify_faq_structure,
    audit_product,
    audit_files,
    main,
)
from .formats import verify_format_direction
from .frontmatter_schema import verify_no_explicit_url

__all__ = [
    # knowledge_core / content_discovery re-exports
    "KNOWLEDGE_ROOT",
    "PLATFORM_MAP",
    "PLATFORM_RMAP",
    "SITE_PATHS",
    "LOCALE_RE",
    "Knowledge",
    "discover_content",
    "discover_products",
    "infer_product",
    "parse_frontmatter",
    "verify_evidence",
    # token_ops re-exports
    "PLATFORM_SDK_CLASSES",
    "PROPERTY_CHAIN_CLASSES",
    "Token",
    "Finding",
    "extract_tokens",
    "verify_tokens",
    # audit sub-modules
    "_MD_LINK_RE",
    "_SITE_CONTENT_MAP",
    "_resolve_link_to_file",
    "_check_content_path",
    "verify_internal_links",
    "verify_snippet_coverage",
    "_check_code_block_snippets",
    "REPORTS_DIR",
    "QUALITY_TREND_MAX_ENTRIES",
    "report_text",
    "report_json",
    "_load_trend_entries",
    "_append_quality_trend",
    "_write_quality_baseline",
    "_prune_quality_trend",
    "CONTENT_ROOT",
    "verify_faq_structure",
    "audit_product",
    "audit_files",
    "main",
    "verify_format_direction",
    "verify_no_explicit_url",
]