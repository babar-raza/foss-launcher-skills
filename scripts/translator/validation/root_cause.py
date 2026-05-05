"""Root-cause classifier for translation audit failures.

Maps failure message strings from the validation checker to a fixed set of
root-cause categories so audit reports can be grouped and triaged by cause.
"""
from __future__ import annotations

ROOT_CAUSES: dict[str, str] = {
    "structure_drift": "Translation changed document structure (headings, tables, fences)",
    "placeholder_leak": "Placeholder tokens leaked into output",
    "untranslated": "Content left in English (leakage)",
    "ratio_anomaly": "Body length ratio outside acceptable bounds",
    "evidence_tampered": "Evidence block modified during translation",
    "frontmatter_drift": "Frontmatter keys added/removed/changed",
    "parse_failure": "File could not be parsed",
    "unknown": "Failure does not match any known pattern",
}

# Ordered list of (substring-or-prefix, category) — first match wins.
_PATTERNS: list[tuple[str, str]] = [
    ("Placeholder", "placeholder_leak"),
    ("placeholder", "placeholder_leak"),
    ("Heading count", "structure_drift"),
    ("Heading level", "structure_drift"),
    ("H2 section count", "structure_drift"),
    ("Code fence", "structure_drift"),
    ("Shortcode count", "structure_drift"),
    ("Table count", "structure_drift"),
    ("table data-row", "structure_drift"),
    ("Blockquote", "structure_drift"),
    ("English leakage", "untranslated"),
    ("Untranslated", "untranslated"),
    ("untranslated paragraph", "untranslated"),
    ("suspiciously short", "ratio_anomaly"),
    ("suspiciously long", "ratio_anomaly"),
    ("Body length ratio", "ratio_anomaly"),
    ("evidence block", "evidence_tampered"),
    ("Evidence block", "evidence_tampered"),
    ("Frontmatter keys", "frontmatter_drift"),
    ("Preserved field", "frontmatter_drift"),
    ("preserved field", "frontmatter_drift"),
    ("parse", "parse_failure"),
    ("Parse", "parse_failure"),
    ("YAML", "parse_failure"),
]


def classify_failure(failure: str) -> str:
    """Return the root-cause category for a single failure message."""
    for pattern, cause in _PATTERNS:
        if pattern in failure:
            return cause
    return "unknown"


def classify_failures(failures: list[str]) -> dict[str, list[str]]:
    """Group a list of failure messages by root-cause category.

    Returns ``{cause: [failure_msg, ...]}`` with only non-empty categories.
    """
    classified: dict[str, list[str]] = {}
    for f in failures:
        cause = classify_failure(f)
        classified.setdefault(cause, []).append(f)
    return classified


def summarize_root_causes(issues: list[dict]) -> dict[str, int]:
    """Aggregate root-cause counts across all issues in an audit report.

    Each *issue* dict is expected to have a ``"root_causes"`` key produced by
    :func:`classify_failures`.  Returns ``{cause: total_count}``.
    """
    totals: dict[str, int] = {}
    for issue in issues:
        for cause, msgs in issue.get("root_causes", {}).items():
            totals[cause] = totals.get(cause, 0) + len(msgs)
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))
