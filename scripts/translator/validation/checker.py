"""
Post-translation validation.

Checks that translation output is structurally valid and hasn't corrupted
any protected regions or internal metadata.
"""
from __future__ import annotations
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator.parser.document import HugoDocument
from translator.policy.loader import ContentTypePolicy


_SHORTCODE_RE = re.compile(r'\{\{[<%].*?[%>]\}\}', re.DOTALL)
_CODE_FENCE_RE = re.compile(r'```[\s\S]*?```|~~~[\s\S]*?~~~', re.DOTALL)
_PLACEHOLDER_RE = re.compile(r'⟦PH_\d{4}⟧')

_HEADING_RE = re.compile(r'^(#{1,6})\s', re.MULTILINE)
_H2_HEADING_RE = re.compile(r'^## ', re.MULTILINE)
_TABLE_LINE_RE = re.compile(r'^\|.*\|$', re.MULTILINE)
_TABLE_SEP_RE = re.compile(r'^\|[\s\-:|]+\|$', re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r'^>\s', re.MULTILINE)
_INLINE_CODE_RE = re.compile(r'`[^`\n]+`')
_LINK_URL_RE = re.compile(r'\]\([^)]+\)')

_COMMON_ENGLISH_WORDS = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "have", "will",
    "are", "not", "but", "can", "each", "which", "when", "your", "into",
    "instead", "method", "using", "below", "above", "also", "only",
    "more", "than", "some", "every", "here", "there", "about", "been",
    "does", "should", "would", "could", "after", "before", "between",
    "these", "those", "other", "such", "then", "because", "while",
})

_NON_LATIN_LOCALES = frozenset({
    "ar", "bg", "el", "fa", "he", "hi", "ja", "ko", "ru", "sr", "th", "uk", "zh",
})

# Domain terms that are never translated — product names, frameworks, standards,
# license terms, and common technical abbreviations. Case-insensitive matching.
_DOMAIN_TERMS = frozenset({
    # Product / brand names
    "aspose", "cells", "foss", "slides", "words", "email", "note",
    # Platforms / frameworks
    "net", "dotnet", "nuget", "excel", "office", "interop", "csharp",
    # Technical standards / formats
    "opc", "ooxml", "xml", "zip", "xlsx", "csv", "json", "yaml", "html",
    "pdf", "docx", "pptx", "svg", "glb", "gltf", "obj", "stl", "fbx",
    # License terms
    "mit", "license",
    # Runtime / interop concepts
    "com", "invoke", "managed",
    # Common dev terms
    "api", "sdk", "cli", "dll", "http", "https", "url", "uri",
})

def _load_quality_bounds() -> tuple[dict[str, tuple[float, float]], tuple[float, float]]:
    """Load per-language ratio bounds from policy/quality.yaml."""
    import yaml
    _yaml_path = Path(__file__).parent.parent / "policy" / "quality.yaml"
    with open(_yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    default_cfg = data.get("default", {})
    default_bounds = (
        float(default_cfg.get("min_ratio", 0.3)),
        float(default_cfg.get("max_ratio", 3.5)),
    )
    bounds: dict[str, tuple[float, float]] = {}
    for tier in data.get("language_tiers", {}).values():
        min_r = float(tier["min_ratio"])
        max_r = float(tier["max_ratio"])
        for locale in tier.get("locales", []):
            bounds[locale] = (min_r, max_r)
    return bounds, default_bounds


_LANGUAGE_RATIO_BOUNDS, _DEFAULT_RATIO_BOUNDS = _load_quality_bounds()


@dataclass
class ValidationResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_failure(self, msg: str):
        self.failures.append(msg)
        self.passed = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)


def validate_translation(
    src: HugoDocument,
    tgt: HugoDocument,
    policy: ContentTypePolicy,
    tgt_lang: str = "",
) -> ValidationResult:
    """
    Run all validation checks on a translated document.
    Returns a ValidationResult with passed=True only if all checks pass.
    """
    result = ValidationResult(passed=True)

    _check_evidence_preserved(src, tgt, result)
    _check_no_placeholder_leaks(tgt, result)
    _check_shortcode_count(src, tgt, result)
    _check_code_fence_count(src, tgt, result)
    _check_heading_structure(src, tgt, result)
    _check_h2_topology(src, tgt, result)
    _check_table_count(src, tgt, result)
    _check_blockquote_count(src, tgt, result)
    _check_english_leakage(src, tgt, tgt_lang, result)
    _check_frontmatter_keys_stable(src, tgt, result)
    _check_body_length_ratio(src, tgt, tgt_lang, result)
    _check_api_names_preserved(src, tgt, result)
    _check_preserve_fields_match_source(src, tgt, policy, result)

    return result


def _check_evidence_preserved(src: HugoDocument, tgt: HugoDocument, result: ValidationResult):
    """Evidence block must be byte-identical to source."""
    src_evidence = src.frontmatter.get("evidence")
    tgt_evidence = tgt.frontmatter.get("evidence")

    if src_evidence is None and tgt_evidence is None:
        return  # No evidence block — OK

    if src_evidence != tgt_evidence:
        result.add_failure(
            f"evidence block modified during translation: "
            f"src={str(src_evidence)[:100]} tgt={str(tgt_evidence)[:100]}"
        )


def _check_no_placeholder_leaks(tgt: HugoDocument, result: ValidationResult):
    """No placeholder tokens should remain in the output."""
    # Check body
    leaked = _PLACEHOLDER_RE.findall(tgt.body)
    if leaked:
        result.add_failure(f"Placeholder tokens leaked into body: {leaked[:3]}")

    # Check frontmatter string values
    def _check_dict(d, path=""):
        for k, v in d.items():
            p = f"{path}.{k}" if path else k
            if isinstance(v, str) and "⟦PH_" in v:
                result.add_failure(f"Placeholder token in frontmatter field '{p}'")
            elif isinstance(v, dict):
                _check_dict(v, p)
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        _check_dict(item, f"{p}[{i}]")
                    elif isinstance(item, str) and "⟦PH_" in item:
                        result.add_failure(f"Placeholder token in frontmatter list '{p}[{i}]'")

    _check_dict(tgt.frontmatter)


def _check_shortcode_count(src: HugoDocument, tgt: HugoDocument, result: ValidationResult):
    """Shortcode count in body must match source."""
    src_count = len(_SHORTCODE_RE.findall(src.body))
    tgt_count = len(_SHORTCODE_RE.findall(tgt.body))
    if src_count != tgt_count:
        result.add_failure(
            f"Shortcode count mismatch: src={src_count}, tgt={tgt_count}"
        )


def _check_code_fence_count(src: HugoDocument, tgt: HugoDocument, result: ValidationResult):
    """Code fence count in body must match source."""
    src_count = len(_CODE_FENCE_RE.findall(src.body))
    tgt_count = len(_CODE_FENCE_RE.findall(tgt.body))
    if src_count != tgt_count:
        result.add_failure(
            f"Code fence count mismatch: src={src_count}, tgt={tgt_count}"
        )


_NON_TRANSLATABLE_METADATA_KEYS = frozenset({
    "grade", "graded_at", "graded_model_sha", "graded_evaluators",
    "provenance",
})


def _check_frontmatter_keys_stable(src: HugoDocument, tgt: HugoDocument, result: ValidationResult):
    """Top-level frontmatter keys must not be added or removed.

    Excludes grading metadata keys which are added to English sources by the
    evaluation pipeline after translations are generated — their absence from
    translated files is expected, not a translation failure.
    """
    src_keys = set(src.frontmatter.keys()) - _NON_TRANSLATABLE_METADATA_KEYS
    tgt_keys = set(tgt.frontmatter.keys()) - _NON_TRANSLATABLE_METADATA_KEYS

    added = tgt_keys - src_keys
    removed = src_keys - tgt_keys

    if added:
        result.add_failure(f"Frontmatter keys added by translation: {added}")
    if removed:
        result.add_failure(f"Frontmatter keys removed by translation: {removed}")


def _check_heading_structure(src: HugoDocument, tgt: HugoDocument, result: ValidationResult):
    """Heading count and depth must match between source and target."""
    src_headings = _HEADING_RE.findall(src.body)
    tgt_headings = _HEADING_RE.findall(tgt.body)

    if len(src_headings) != len(tgt_headings):
        result.add_failure(
            f"Heading count mismatch: src={len(src_headings)}, tgt={len(tgt_headings)}"
        )
        return  # Skip level comparison if counts differ

    for i, (sh, th) in enumerate(zip(src_headings, tgt_headings)):
        if len(sh) != len(th):
            result.add_failure(
                f"Heading level mismatch at position {i}: src=h{len(sh)}, tgt=h{len(th)}"
            )


def _check_h2_topology(src: HugoDocument, tgt: HugoDocument, result: ValidationResult):
    """H2 section count must match between source and target.

    Catches H2 merging or splitting that produces the same total heading count
    but a different number of top-level sections — a pattern the total-count
    check misses when the LLM compensates at other heading levels.
    Code fences are stripped before counting to avoid matching ## inside code blocks.
    """
    src_stripped = _CODE_FENCE_RE.sub("", src.body)
    tgt_stripped = _CODE_FENCE_RE.sub("", tgt.body)
    src_h2 = len(_H2_HEADING_RE.findall(src_stripped))
    tgt_h2 = len(_H2_HEADING_RE.findall(tgt_stripped))
    if src_h2 != tgt_h2:
        result.add_failure(
            f"H2 section count mismatch: src={src_h2}, tgt={tgt_h2}"
        )


def _check_table_count(src: HugoDocument, tgt: HugoDocument, result: ValidationResult):
    """Table count and data-row counts must match between source and target."""
    src_tables = _extract_tables(src.body)
    tgt_tables = _extract_tables(tgt.body)

    if len(src_tables) != len(tgt_tables):
        result.add_failure(
            f"Table count mismatch: src={len(src_tables)}, tgt={len(tgt_tables)}"
        )
        return

    for i, (st, tt) in enumerate(zip(src_tables, tgt_tables)):
        if st != tt:
            result.add_failure(
                f"Table {i} data-row count mismatch: src={st}, tgt={tt}"
            )


def _extract_tables(body: str) -> list[int]:
    """Extract data-row counts for each markdown table in body."""
    tables: list[int] = []
    in_table = False
    data_rows = 0

    for line in body.split("\n"):
        stripped = line.strip()
        if _TABLE_LINE_RE.match(stripped):
            if not in_table:
                in_table = True
                data_rows = 0
            if not _TABLE_SEP_RE.match(stripped):
                data_rows += 1
        else:
            if in_table:
                tables.append(data_rows)
                in_table = False
                data_rows = 0

    if in_table:
        tables.append(data_rows)

    return tables


def _check_blockquote_count(src: HugoDocument, tgt: HugoDocument, result: ValidationResult):
    """Blockquote line count must match between source and target."""
    src_count = len(_BLOCKQUOTE_RE.findall(src.body))
    tgt_count = len(_BLOCKQUOTE_RE.findall(tgt.body))
    if src_count != tgt_count:
        result.add_failure(
            f"Blockquote count mismatch: src={src_count}, tgt={tgt_count}"
        )


# Only ALL_CAPS constants are detectable at the word-token level.
# Class.method and function_call() patterns are not viable here because
# words are pre-tokenized to alpha-only via \b[A-Za-z]{3,}\b — no token ever
# contains a dot or parenthesis, so those patterns would never match.
_TECHNICAL_ID_RE = re.compile(r'^[A-Z][A-Z0-9_]{2,}$')

# PascalCase class/type names: at least two capitalized segments (e.g. WorkbookSettings,
# LoadOptions, ValidationCollection). Single-segment capitalized words (e.g. "Workbook")
# are not matched — they rely on api_tokens or _DOMAIN_TERMS instead.
_PASCAL_CASE_RE = re.compile(r'^[A-Z][a-z]+(?:[A-Z][a-z]+)+$')


def _is_technical_identifier(token: str, api_tokens: frozenset) -> bool:
    """Return True if token is a technical identifier exempt from English leakage counting."""
    return (token in api_tokens
            or bool(_TECHNICAL_ID_RE.match(token))
            or token.lower() in _DOMAIN_TERMS
            or bool(_PASCAL_CASE_RE.match(token)))


def _strip_protected_regions(text: str) -> str:
    """Strip code fences, inline code, and link URLs from text for prose analysis."""
    text = _CODE_FENCE_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _LINK_URL_RE.sub("]()", text)
    text = _SHORTCODE_RE.sub("", text)
    return text


def _check_english_leakage(
    src: HugoDocument,
    tgt: HugoDocument,
    tgt_lang: str,
    result: ValidationResult,
):
    """Detect untranslated English text in the target document."""
    if not tgt_lang:
        return  # Cannot check without knowing target language

    # Build set of technical identifier fragments from evidence.apis to exempt
    api_tokens: frozenset = frozenset()
    evidence = src.frontmatter.get("evidence", {}) or {}
    raw_apis = evidence.get("apis", []) or []
    if raw_apis:
        fragments: list[str] = []
        for api in raw_apis:
            fragments.extend(re.split(r'[\.\(\)\[\],\s_]+', str(api)))
        api_tokens = frozenset(t for t in fragments if len(t) > 1)

    tgt_prose = _strip_protected_regions(tgt.body)

    if tgt_lang in _NON_LATIN_LOCALES:
        # For non-Latin scripts: check ratio of common English words
        # Exempt technical identifiers (class names, constants, API fragments)
        words = re.findall(r'\b[A-Za-z]{3,}\b', tgt_prose)
        words = [w for w in words if not _is_technical_identifier(w, api_tokens)]
        if len(words) < 10:
            return  # Too few words to judge

        english_count = sum(1 for w in words if w.lower() in _COMMON_ENGLISH_WORDS)
        ratio = english_count / len(words)

        if ratio > 0.15:
            result.add_failure(
                f"English leakage detected ({tgt_lang}): {ratio:.0%} of prose words "
                f"are common English words ({english_count}/{len(words)})"
            )

        # Per-paragraph check for fully untranslated blocks
        src_prose = _strip_protected_regions(src.body)
        for para in tgt_prose.split("\n\n"):
            para_words = re.findall(r'\b[A-Za-z]{3,}\b', para)
            if len(para_words) > 15:
                eng = sum(1 for w in para_words if w.lower() in _COMMON_ENGLISH_WORDS)
                if eng / len(para_words) > 0.6:
                    result.add_failure(
                        f"Untranslated English paragraph detected ({tgt_lang}): "
                        f"'{para[:80]}...'"
                    )
                    break  # One failure is enough
    else:
        # For Latin-script languages: compare paragraphs to source
        src_prose = _strip_protected_regions(src.body)
        src_paras = [p.strip() for p in src_prose.split("\n\n") if len(p.strip()) > 30]
        tgt_paras = [p.strip() for p in tgt_prose.split("\n\n") if len(p.strip()) > 30]

        for tp in tgt_paras:
            for sp in src_paras:
                if tp == sp and len(tp) > 50:
                    result.add_failure(
                        f"Untranslated paragraph detected ({tgt_lang}): "
                        f"target identical to English source: '{tp[:80]}...'"
                    )
                    return  # One failure is enough

        # Word-overlap check: detect partially-translated paragraphs where
        # most words are copied verbatim from the English source.
        for tp in tgt_paras:
            tgt_words = [w.lower() for w in re.findall(r'\b[A-Za-z]{3,}\b', tp)
                         if not _is_technical_identifier(w, api_tokens)]
            if len(tgt_words) < 15:
                continue
            for sp in src_paras:
                src_words = set(w.lower() for w in re.findall(r'\b[A-Za-z]{3,}\b', sp))
                if not src_words:
                    continue
                overlap = sum(1 for w in tgt_words if w in src_words)
                overlap_ratio = overlap / len(tgt_words)
                if overlap_ratio > 0.6:
                    result.add_failure(
                        f"Partially untranslated paragraph detected ({tgt_lang}): "
                        f"{overlap_ratio:.0%} word overlap with English source: "
                        f"'{tp[:80]}...'"
                    )
                    return  # One failure is enough


def _check_body_length_ratio(
    src: HugoDocument, tgt: HugoDocument, tgt_lang: str, result: ValidationResult
):
    """Translated body length should be in a reasonable ratio to source."""
    src_len = len(src.body.strip())
    tgt_len = len(tgt.body.strip())

    if src_len == 0:
        return  # Empty source — skip

    ratio = tgt_len / src_len

    # Per-language bounds (tighter than the old universal 0.2–5.0)
    bounds = _LANGUAGE_RATIO_BOUNDS.get(tgt_lang, _DEFAULT_RATIO_BOUNDS)
    ratio_min, ratio_max = bounds

    if ratio < ratio_min:
        result.add_failure(
            f"Translated body suspiciously short: {tgt_len} chars vs {src_len} source "
            f"chars (ratio={ratio:.2f}, min={ratio_min} for {tgt_lang or 'default'})"
        )
    elif ratio > ratio_max:
        result.add_failure(
            f"Translated body suspiciously long: {tgt_len} chars vs {src_len} source "
            f"chars (ratio={ratio:.2f}, max={ratio_max} for {tgt_lang or 'default'})"
        )


def _check_api_names_preserved(src: HugoDocument, tgt: HugoDocument, result: ValidationResult):
    """API names from evidence.apis should appear unchanged in the output."""
    evidence = src.frontmatter.get("evidence", {})
    if not isinstance(evidence, dict):
        return

    apis = evidence.get("apis", [])
    if not apis:
        return

    tgt_body_lower = tgt.body.lower()
    tgt_fm_str = str(tgt.frontmatter).lower()

    for api_name in apis:
        if not isinstance(api_name, str):
            continue
        # API names should appear somewhere in the output (not necessarily in body;
        # might be in a code block that was protected)
        if api_name.lower() not in tgt_body_lower and api_name.lower() not in tgt_fm_str:
            result.add_warning(
                f"API name '{api_name}' from evidence.apis not found in translated output"
            )


def _check_preserve_fields_match_source(
    src: HugoDocument,
    tgt: HugoDocument,
    policy: ContentTypePolicy,
    result: ValidationResult,
) -> None:
    """Preserved frontmatter fields in the target must be identical to the source.

    The translator's preserve list means the field is copied verbatim; if the
    source value was wrong, the target inherits the wrong value.  This check
    detects drift between source and target for every preserved field so that
    stale locale files (updated English source but locales not regenerated) are
    caught at validation time.
    """
    preserve_fields = dict.fromkeys(policy.field_policy.preserve)  # deduplicate, keep order
    for field_name in preserve_fields:
        src_val = src.frontmatter.get(field_name)
        tgt_val = tgt.frontmatter.get(field_name)

        if src_val is None and tgt_val is None:
            continue  # Field absent in both — OK

        if src_val is None:
            # Present in target but absent in source — structural oddity, warn only
            result.add_warning(
                f"Preserved field '{field_name}' present in target but absent in source"
            )
            continue

        if tgt_val is None:
            result.add_warning(
                f"Preserved field '{field_name}' present in source but absent in target"
            )
            continue

        if src_val != tgt_val:
            result.add_failure(
                f"Preserved field '{field_name}' differs: "
                f"source={src_val!r} target={tgt_val!r}"
            )
