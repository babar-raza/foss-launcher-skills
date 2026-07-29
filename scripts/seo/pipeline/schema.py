"""
SEO-000 schema.py
====================
Structural classification of keywords/*.json files as Schema A (LLM-suggested
keyword lists) or Schema B (real Google Search Console exports).

Classification is shape-based, not a filename allowlist. Before this module
existed, validate.py and map_url.py each hardcoded their own incomplete list
of "Schema B" filenames (5 and 4 entries respectively, out of 7 real Schema B
files) -- the two lists disagreed, and between them 3 of the 7 real Schema B
files (blog.aspose.org.json, kb.aspose.org.json, and inconsistently
docs.aspose.org.json) were silently dropped or misclassified as Schema A. A
filename list can drift out of sync with what's actually on disk; a shape
check on the file's own content cannot.

No LLM calls. No network calls. stdlib + pathlib only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_B = "B"
SCHEMA_A = "A"
SCHEMA_UNKNOWN = "unknown"

# How many leading entries to sample when classifying a file's payload. A
# small sample is enough to detect the file's dominant shape and keeps
# classification cheap even for large Schema A files (hundreds of entries).
_SAMPLE_SIZE = 5


def classify_entry_shape(entry: Any) -> str:
    """Classify a single decoded JSON list entry by its own keys.

    Schema B entries are GSC url records: {"url", "lang", "lastUpdated",
    "queries", "agg", ...}. Schema A entries are LLM keyword suggestions:
    {"pageTitle", "keywords"}. An entry carrying both "url" and either
    "queries" or "agg" is Schema B even if it also happens to carry a
    "keywords" key (Schema B entries have their own "keywords" dedup list
    alongside "queries" -- see keywords/docs.aspose.org.json).
    """
    if not isinstance(entry, dict):
        return SCHEMA_UNKNOWN
    has_url = isinstance(entry.get("url"), str)
    has_queries_or_agg = "queries" in entry or "agg" in entry
    has_page_title = isinstance(entry.get("pageTitle"), str)
    if has_url and (has_queries_or_agg or "lastUpdated" in entry):
        return SCHEMA_B
    if has_page_title:
        return SCHEMA_A
    return SCHEMA_UNKNOWN


def classify_keyword_file(payload: Any) -> str:
    """Classify a decoded keywords/*.json payload (the parsed JSON root).

    Returns SCHEMA_B, SCHEMA_A, or SCHEMA_UNKNOWN (empty file, malformed
    root, or entries whose shape doesn't match either known schema).

    Classification samples up to the first _SAMPLE_SIZE entries and takes a
    majority vote, so a single stray cross-schema-contaminated entry (the
    exact failure mode from the 2026-03-27 contamination incident, where a
    stray keywords/agg block leaked into a Schema A file and stray
    tags/pluginDescriptions keys leaked into a Schema B file) doesn't flip an
    otherwise-consistent file's classification.
    """
    if not isinstance(payload, list) or not payload:
        return SCHEMA_UNKNOWN
    sample = payload[:_SAMPLE_SIZE]
    votes = [classify_entry_shape(e) for e in sample]
    b_votes = votes.count(SCHEMA_B)
    a_votes = votes.count(SCHEMA_A)
    if b_votes == 0 and a_votes == 0:
        return SCHEMA_UNKNOWN
    return SCHEMA_B if b_votes >= a_votes else SCHEMA_A


def classify_keyword_path(path: Path) -> str:
    """Classify a keywords/*.json file on disk by reading and parsing it.

    Returns SCHEMA_B, SCHEMA_A, or SCHEMA_UNKNOWN (missing file, unreadable,
    unparseable, or a payload that doesn't match either schema's shape).
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return SCHEMA_UNKNOWN
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return SCHEMA_UNKNOWN
    return classify_keyword_file(payload)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_FAMILY_DESCRIPTIONS_PATH = _REPO_ROOT / "data" / "family_descriptions.json"


def canonical_families() -> list[str]:
    """The full list of Aspose product family slugs, sorted.

    Single source of truth for "which families exist" across scripts/seo/ --
    replaces three independently hand-maintained lists that had silently
    drifted out of sync with each other (get_keywords.py: 18 names,
    review_keywords.py: 13, validate.py: 14) and with data/family_descriptions.json,
    the same registry already treated as authoritative by 4 Hugo home
    templates (Finding #32). Returns [] if the registry is missing or
    unparseable rather than raising, so a stale/broken registry degrades to
    "no families" (caller falls back to an explicit --families arg) instead
    of crashing every script that imports this at module load time.
    """
    try:
        raw = json.loads(_FAMILY_DESCRIPTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, dict):
        return []
    return sorted(raw.keys())
