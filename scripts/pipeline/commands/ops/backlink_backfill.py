#!/usr/bin/env python3
"""backlink_backfill.py — Backlink insertion engine for aspose.org English content (TC-BL-005/006).

Reads the backlink audit report and inserts missing backlinks into in-scope English
content files. Operates in dry-run mode by default (no file writes).

Supports:
  - products.aspose.org: YAML overview.content insertion (PyYAML round-trip)
  - docs.aspose.org: Markdown See Also section insertion
  - kb.aspose.org: Markdown See Also section insertion
  - reference.aspose.org: Markdown See Also section insertion
  - blog.aspose.org: Markdown Related Resources section insertion

Usage:
    python scripts/pipeline/commands/ops/backlink_backfill.py           # dry-run all
    python scripts/pipeline/commands/ops/backlink_backfill.py --write   # apply writes
    python scripts/pipeline/commands/ops/backlink_backfill.py --family words --platform python
    python scripts/pipeline/commands/ops/backlink_backfill.py --subdomain docs.aspose.org
    python scripts/pipeline/commands/ops/backlink_backfill.py --family words --write

Exit codes:
    0   Success (dry-run or write complete)
    1   Fatal error (target map missing, products YAML round-trip failure, etc.)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
sys.path.insert(0, str(_DEFAULT_REPO_ROOT / "scripts" / "pipeline"))


def configure(*, repo_root: Path | str | None = None) -> None:
    """Test seam: override _REPO_ROOT (AGENTS.md §16 configure() pattern).

    Call with no arguments to reset to the default.
    """
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT

from lib.backlink_targets import (
    COMPLIANT,
    FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE,
    HOST_MAP,
    PageType,
    classify_compliance,
    classify_page_type,
    count_qualifying_com_links,
    get_max_enterprise_links_per_page as _lib_get_max_enterprise_links_per_page,
    load_anchor_registry,
    load_target_map,
    resolve_backlink,
    select_anchor_template_id,
)

SCRIPT_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# YAML literal block scalar dumper — forces | style for multi-line strings.
# Plain yaml.dump converts | blocks to single-quoted flow scalars or
# double-quoted \n-escaped strings, breaking Hugo rendering of code blocks.
# Matches the approach in normalize_yaml_style.py.
# ---------------------------------------------------------------------------

import yaml as _yaml_module


class _LiteralDumper(_yaml_module.Dumper):
    """YAML dumper that serializes all multi-line strings as | literal block scalars."""
    pass


def _literal_str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_LiteralDumper.add_representer(str, _literal_str_representer)


def _anchor_suffix_for(target_url: str, target_type: str, source_subdomain: str | None = None) -> str:
    """Return the enterprise suffix string for the given target URL and type.

    Uses the anchor registry via select_anchor_template_id + registry suffix lookup.
    Replaces the deprecated build_enterprise_anchor_suffix() in insertion paths (V21).

    source_subdomain: (TC14, 2026-08-21) optional, forwarded to
    select_anchor_template_id() -- required to correctly distinguish a
    blog.aspose.org source's legacy blog-products-* templates (deprecated,
    still present on some live pages) from an ordinary products-* template
    for the same target_url. Omitting it (the original call shape) preserves
    exact prior behavior for the products.aspose.org-only call site below.
    """
    registry = load_anchor_registry()
    tid = select_anchor_template_id(target_url, target_type, source_subdomain=source_subdomain)
    return registry.get("templates", {}).get(tid, {}).get("suffix", "Enterprise Product")


def _expected_anchor_text(
    target_url: str,
    family: str,
    platform: str | None,
    families_map: dict,
    platforms_map: dict,
    target_type: str | None = None,
    source_subdomain: str | None = None,
) -> str:
    """Return the exact governed anchor text (bracket contents, no URL) for a
    products.aspose.org link -- the single source of truth for both the
    template fallback below and the validator gating any candidate text
    against it (TC1, 2026-08-21). Extracted from _apply_overview_template()
    so template generation and validation can never drift from each other.

    source_subdomain: (TC14, 2026-08-21) see _anchor_suffix_for() -- pass the
    audited/inserted page's own source subdomain (e.g. "blog.aspose.org")
    when calling this for a non-products source, so a legacy blog-products-*
    template is correctly distinguished from an ordinary one for the same URL.
    """
    fam_title = families_map.get(family, f"Aspose.{family.title()}")
    # FAMILY-ANCHOR rule: if resolved target is a family URL, never include "for {Platform}"
    if platform and target_type != "family":
        plat_title = platforms_map.get(platform, platform.title())
        display = f"{fam_title} for {plat_title}"
    else:
        display = fam_title
    enterprise_suffix = _anchor_suffix_for(target_url, target_type or "platform", source_subdomain=source_subdomain)
    return f"{display} — {enterprise_suffix}"


# ──────────────────────────────────────────────────────────────────────────────
# Safety constants (§8.3)
# ──────────────────────────────────────────────────────────────────────────────

def _max_qualifying_links(registry_path: Path | None = None) -> int:
    """TC9 (2026-08-21): single source of truth, read from
    data/backlinks/link_slot_registry.yaml's global.max_enterprise_links_per_page
    -- was previously a hardcoded module constant here, independently
    duplicated (and never wired to the registry file that claimed to
    "enforce" it) in backlink_targets.py's classify_compliance() and
    backlink_html_audit.py. A function call (not a constant) so a changed
    YAML value takes effect immediately, including in tests that point at a
    different registry file -- a plain constant, evaluated once at import,
    could never support that. registry_path is a straight passthrough to
    backlink_targets.get_max_enterprise_links_per_page(), which owns the
    actual read+cache; kept optional so production call sites (below) never
    need to pass it.
    """
    return _lib_get_max_enterprise_links_per_page(registry_path)


# Process MISSING and WRONG_TARGET (has aspose.com links but none match accepted targets).
# For WRONG_TARGET: add correct target link if existing_count < max qualifying links.
BACKFILL_STATUSES = frozenset({"MISSING", "WRONG_TARGET"})

# Sections to create for each subdomain
SEE_ALSO_HEADER = "## See Also"
RELATED_RESOURCES_HEADER = "## Related Resources"


@dataclass
class BackfillChange:
    file: str             # repo-relative path
    subdomain: str
    family: str | None
    platform: str | None
    page_type: str
    target_url: str
    action: str           # "yaml_overview" | "md_see_also" | "md_related_resources"
    before_snippet: str   # first 200 chars of original content
    after_snippet: str    # first 200 chars of new content
    skipped: bool = False
    skip_reason: str = ""
    dry_run: bool = True
    warning_messages: list = field(default_factory=list)


@dataclass
class BackfillManifest:
    generated_at: str
    generator: str
    dry_run: bool
    total_candidates: int
    total_modified: int
    total_skipped: int
    total_errors: int
    changes: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    rollback_commands: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Products YAML insertion (§5.1 / TC-BL-005)
# ──────────────────────────────────────────────────────────────────────────────

def backfill_products_yaml(
    file_path: Path,
    target_url: str,
    family: str,
    platform: str | None,
    families_map: dict,
    platforms_map: dict,
    *,
    dry_run: bool = True,
    target_type: str | None = None,
) -> BackfillChange:
    """Insert backlink into products.aspose.org YAML overview.content.

    target_type: "platform" or "family" — controls anchor text generation.
    """
    rel = file_path.relative_to(_REPO_ROOT).as_posix()
    raw = file_path.read_text(encoding="utf-8")

    # Parse frontmatter
    fm_text = raw
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end != -1:
            fm_text = raw[3:end]

    try:
        import yaml as _yaml
        data = _yaml.safe_load(fm_text)
    except Exception as exc:
        return BackfillChange(
            file=rel, subdomain="products.aspose.org", family=family, platform=platform,
            page_type="products-plugin" if platform else "products-family",
            target_url=target_url, action="yaml_overview",
            before_snippet=raw[:200], after_snippet="",
            skipped=True, skip_reason=f"YAML parse failed: {exc}", dry_run=dry_run,
        )

    if not isinstance(data, dict):
        return BackfillChange(
            file=rel, subdomain="products.aspose.org", family=family, platform=platform,
            page_type="products-plugin" if platform else "products-family",
            target_url=target_url, action="yaml_overview",
            before_snippet=raw[:200], after_snippet="",
            skipped=True, skip_reason="YAML did not parse to dict", dry_run=dry_run,
        )

    # Get existing overview.content
    overview = data.get("overview", {}) or {}
    current_content = overview.get("content", "") or ""

    # Oscillation guard: detect if link was previously injected (frontmatter field set)
    # but was externally removed from content. WARN and skip rather than silently re-injecting.
    # The guard uses the `enterprise_backlink_injected` YAML frontmatter field (not an HTML comment
    # in content) so rendered pages stay clean.
    _injected_marker_url = (data.get("enterprise_backlink_injected") or "").rstrip("/")
    if _injected_marker_url and target_url.rstrip("/") not in current_content:
        import logging as _log_osc
        _log_osc.getLogger(__name__).warning(
            "OSCILLATION_GUARD: %s — enterprise_backlink_injected frontmatter field present but "
            "link removed externally from content. Skipping re-injection. "
            "Inspect and manually restore if intended.",
            rel,
        )
        return BackfillChange(
            file=rel, subdomain="products.aspose.org", family=family, platform=platform,
            page_type="products-plugin" if platform else "products-family",
            target_url=target_url, action="yaml_overview",
            before_snippet=current_content[:200], after_snippet="",
            skipped=True, skip_reason="oscillation_guard", dry_run=dry_run,
        )

    # Idempotency: check if target URL already present in content
    if target_url.rstrip("/") in current_content:
        return BackfillChange(
            file=rel, subdomain="products.aspose.org", family=family, platform=platform,
            page_type="products-plugin" if platform else "products-family",
            target_url=target_url, action="yaml_overview",
            before_snippet=current_content[:200], after_snippet=current_content[:200],
            skipped=True, skip_reason="Already contains target URL (idempotent)", dry_run=dry_run,
        )

    # Max-link guard
    link_count, _ = count_qualifying_com_links(current_content)
    if link_count >= _max_qualifying_links():
        return BackfillChange(
            file=rel, subdomain="products.aspose.org", family=family, platform=platform,
            page_type="products-plugin" if platform else "products-family",
            target_url=target_url, action="yaml_overview",
            before_snippet=current_content[:200], after_snippet="",
            skipped=True, skip_reason=f"Already at max links ({link_count})", dry_run=dry_run,
        )

    # TC1 (2026-08-21): the single governed anchor-text gate. Any candidate
    # text -- whether from the LLM-copy cache or freshly templated -- must
    # pass this check before being accepted; it is the ONLY validator this
    # function trusts. Previously, _validate_overview_update() (URL presence
    # + 80% retention only, no anchor-text check) was the actual gate, which
    # is why the LLM-copy cache's stale "Aspose.Cells commercial edition"
    # text passed straight through onto the live cells page -- the URL was
    # correct, so the wording-blind check never caught it.
    expected_anchor_text = _expected_anchor_text(
        target_url, family, platform, families_map, platforms_map, target_type
    )

    # Try to get LLM-generated copy first
    new_content = _get_llm_copy_for_file(rel, current_content, target_url,
                                          family, platform, families_map, platforms_map,
                                          target_type=target_type)

    # Validate new_content has the correct anchor text (not just URL presence)
    if _validate_llm_output(current_content, new_content, target_url, expected_anchor_text):
        # Generate fresh template sentence as fallback
        new_content = _apply_overview_template(current_content, target_url,
                                                family, platform, families_map, platforms_map,
                                                target_type=target_type)

    if not dry_run:
        # Set oscillation guard in frontmatter (NOT as HTML comment in content)
        data["enterprise_backlink_injected"] = target_url.rstrip("/") + "/"
        # Modify data dict with clean content (no HTML comment appended)
        if "overview" not in data or not isinstance(data.get("overview"), dict):
            data["overview"] = {}
        data["overview"]["content"] = new_content

        # Round-trip through PyYAML to preserve style
        new_raw = _rewrite_yaml_file(raw, data, fm_text)
        if new_raw is None:
            return BackfillChange(
                file=rel, subdomain="products.aspose.org", family=family, platform=platform,
                page_type="products-plugin" if platform else "products-family",
                target_url=target_url, action="yaml_overview",
                before_snippet=current_content[:200], after_snippet="",
                skipped=True, skip_reason="YAML round-trip failed", dry_run=dry_run,
            )
        file_path.write_text(new_raw, encoding="utf-8")

    return BackfillChange(
        file=rel, subdomain="products.aspose.org", family=family, platform=platform,
        page_type="products-plugin" if platform else "products-family",
        target_url=target_url, action="yaml_overview",
        before_snippet=current_content[:200], after_snippet=new_content[:200],
        dry_run=dry_run,
    )


def _get_llm_copy_for_file(
    rel_path: str,
    current_content: str,
    target_url: str,
    family: str,
    platform: str | None,
    families_map: dict,
    platforms_map: dict,
    target_type: str | None = None,
) -> str:
    """Get LLM-generated copy for a specific file from the generation report."""
    report_path = _REPO_ROOT / "reports" / "backlinks" / "products_llm_copy_generation.json"
    if report_path.exists():
        try:
            records = json.loads(report_path.read_text(encoding="utf-8"))
            for rec in records:
                if rec.get("file_path") == rel_path:
                    output = rec.get("output_text")
                    if output and output != current_content:
                        return output
        except Exception:
            pass
    return _apply_overview_template(current_content, target_url, family, platform, families_map, platforms_map,
                                    target_type=target_type)


def _validate_overview_update(original: str, updated: str, target_url: str) -> bool:
    """Validate that the updated text contains the target URL and is reasonable."""
    if not updated or updated == original:
        return False
    if target_url.rstrip("/") not in updated:
        return False
    # Check non-link retention >= 80% (permissive for backfill)
    stripped_orig = re.sub(r'\[[^\]]+\]\([^)]+\)', '', original).strip()
    stripped_upd = re.sub(r'\[[^\]]+\]\([^)]+\)', '', updated).strip()
    if len(stripped_orig) > 0:
        ratio = len(stripped_upd) / len(stripped_orig)
        if ratio < 0.80:
            return False
    return True


# ── Prose Integration Machinery (Phase 4 — TC-BL-005) ────────────────────────

# Jaccard near-duplicate detection threshold (module-level for easy adjustment)
_NEAR_DUPLICATE_THRESHOLD = 0.65
# At or above this similarity, injection is hard-blocked (not just warned)
_NEAR_DUPLICATE_HARD_BLOCK_THRESHOLD = 0.90

# Tokens too common to be discriminating for Jaccard similarity
_JACCARD_NOISE_WORDS = frozenset({
    "the", "a", "an", "and", "or", "for", "to", "in", "of", "on", "with",
    "see", "use", "can", "is", "are", "this", "that", "these", "those",
    "from", "at", "by", "as", "it", "its", "be", "was", "were", "have",
    "has", "had", "not", "but", "also", "more", "may",
})

# Prohibited marketing claims in LLM-generated text
_PROHIBITED_PHRASES = [
    "industry-leading", "best-in-class", "only solution",
    "guarantee", "guaranteed", "unparalleled", "world-class",
    # TC1 (2026-08-21): the "commercial X" family -- the exact wording that
    # leaked into products.aspose.org/cells ("Aspose.Cells commercial
    # edition") via the ungoverned LLM-copy cache this fix retires. These are
    # the phrases from generate_product_backlink_copy.py's _FORBIDDEN_PHRASES
    # that are universally wrong regardless of source (LLM or template) --
    # deliberately NOT importing that file's full list: several of its other
    # entries ("for the enterprise product family, see", "alongside these
    # open-source libraries") are LLM-variety-nudging rules that the
    # deterministic _apply_overview_template() fallback below legitimately
    # generates as its own governed, reviewed template text -- importing
    # those too would make the safe fallback reject its own output.
    "buy now", "click here",
    "full-featured commercial edition", "commercial edition",
    "commercial product family", "commercial counterpart",
    "commercial licensing", "commercial support", "commercial version",
]


def _tokenize_sentence(text: str) -> set[str]:
    """Tokenize sentence into a word set for Jaccard comparison.
    Strips URLs first, then excludes Aspose.*, Enterprise* tokens and noise words.
    URL tokens (https, com, etc.) are excluded to avoid inflating the denominator.
    """
    # Strip URLs before tokenizing so URL components don't affect similarity
    text_no_urls = re.sub(r'https?://\S+', '', text)
    words = re.findall(r"[a-zA-Z]+", text_no_urls.lower())
    return {
        w for w in words
        if w not in _JACCARD_NOISE_WORDS
        and not w.startswith("aspose")
        and not w.startswith("enterprise")
        and len(w) > 2
    }


def _detect_near_duplicate(existing_text: str, candidate_sentence: str) -> list[str]:
    """Return list of existing sentences with Jaccard similarity >= threshold.

    Tokenizes each sentence in existing_text and computes Jaccard similarity
    against candidate_sentence. Excludes URL tokens and Aspose.*/Enterprise*
    tokens from the comparison (too common to be discriminating).

    Returns list of near-duplicate sentence strings (empty = no duplicates found).
    """
    candidate_tokens = _tokenize_sentence(candidate_sentence)
    if not candidate_tokens:
        return []

    # Split existing text into sentences by '. ', '\n', or bullet markers
    sentence_parts = re.split(r'(?<=[.!?])\s+|\n+|(?=^- )', existing_text, flags=re.MULTILINE)
    duplicates = []
    for part in sentence_parts:
        part = part.strip()
        if len(part) < 10:
            continue
        part_tokens = _tokenize_sentence(part)
        if not part_tokens:
            continue
        intersection = candidate_tokens & part_tokens
        union = candidate_tokens | part_tokens
        if union and (len(intersection) / len(union)) >= _NEAR_DUPLICATE_THRESHOLD:
            duplicates.append(part)
    return duplicates


def _near_dup_max_score(existing_text: str, candidate_sentence: str) -> float:
    """Return the maximum Jaccard similarity between candidate and any sentence in existing_text.

    Uses the same tokenization as _detect_near_duplicate. Returns 0.0 if no
    comparison is possible (empty tokens or text).
    """
    candidate_tokens = _tokenize_sentence(candidate_sentence)
    if not candidate_tokens:
        return 0.0
    sentence_parts = re.split(r'(?<=[.!?])\s+|\n+|(?=^- )', existing_text, flags=re.MULTILINE)
    max_score = 0.0
    for part in sentence_parts:
        part = part.strip()
        if len(part) < 10:
            continue
        part_tokens = _tokenize_sentence(part)
        if not part_tokens:
            continue
        intersection = candidate_tokens & part_tokens
        union = candidate_tokens | part_tokens
        if union:
            max_score = max(max_score, len(intersection) / len(union))
    return max_score


def _extract_affected_section(body: str, section_header: str) -> str:
    """Extract section body from header to next ## heading or EOF."""
    escaped = re.escape(section_header)
    result = _find_section(body, rf"^{escaped}\s*$")
    if result is None:
        return ""
    _, content_start = result
    # Find next ## heading (any level >= 2) after content_start
    next_heading = re.search(r'^#{2,}\s', body[content_start:], re.MULTILINE)
    if next_heading:
        return body[content_start: content_start + next_heading.start()]
    return body[content_start:]


def _validate_prose(section_text: str, entry: str, target_url: str) -> list[str]:
    """Validate that injected entry appears correctly in section_text.

    Checks:
    1. entry string (or its bullet form) is present in section_text
    2. target_url is present unchanged in section_text
    3. No duplicate bullets for target_url

    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []
    normalized_entry = entry.strip().lstrip("- ").strip()

    if normalized_entry and normalized_entry not in section_text:
        errors.append(
            f"PROSE_ANCHOR_MISSING: entry anchor not found in section after injection"
        )
    if target_url.rstrip("/") not in section_text:
        errors.append(
            f"PROSE_URL_MISSING: target URL {target_url!r} not found in section after injection"
        )
    # Count bullet occurrences for this URL
    url_count = section_text.count(target_url.rstrip("/"))
    if url_count > 1:
        errors.append(
            f"PROSE_DUPLICATE: target URL appears {url_count} times in section"
        )
    return errors


def _validate_llm_output(
    original: str, updated: str, target_url: str, anchor_text: str
) -> list[str]:
    """Validate LLM-generated overview.content update.

    Checks:
    1. anchor_text is present as a substring in updated
    2. target_url is present (unchanged) in updated
    3. No prohibited marketing phrases
    4. Retained prose ratio >= 0.80

    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []

    if anchor_text not in updated:
        errors.append(
            f"LLM_ANCHOR_MISSING: anchor text {anchor_text!r} not found in updated content"
        )
    if target_url.rstrip("/") not in updated:
        errors.append(
            f"LLM_URL_MISSING: target URL {target_url!r} not found in updated content"
        )
    for phrase in _PROHIBITED_PHRASES:
        if phrase.lower() in updated.lower():
            errors.append(
                f"LLM_UNSUPPORTED_CLAIM: prohibited phrase {phrase!r} found in updated content"
            )
    # Retained prose ratio check (reuses _validate_overview_update logic)
    stripped_orig = re.sub(r'\[[^\]]+\]\([^)]+\)', '', original).strip()
    stripped_upd = re.sub(r'\[[^\]]+\]\([^)]+\)', '', updated).strip()
    if stripped_orig and len(stripped_upd) / len(stripped_orig) < 0.80:
        errors.append(
            f"LLM_LOW_RETENTION: retained prose ratio {len(stripped_upd)/len(stripped_orig):.2f} < 0.80"
        )
    return errors


def _apply_overview_template(
    current_content: str,
    target_url: str,
    family: str,
    platform: str | None,
    families_map: dict,
    platforms_map: dict,
    target_type: str | None = None,
) -> str:
    """Apply template fallback to generate updated overview.content.

    target_type: "platform" or "family". When "family", anchor omits platform suffix.
    """
    expected_anchor_text = _expected_anchor_text(
        target_url, family, platform, families_map, platforms_map, target_type
    )
    enterprise_suffix = _anchor_suffix_for(target_url, target_type or "platform")

    # Measure word count
    wc = len(current_content.split())

    anchor = f"[{expected_anchor_text}]({target_url})"

    if enterprise_suffix == "Enterprise Product Family":
        sentence = f"For the enterprise product family, see {anchor}."
    elif enterprise_suffix == "Enterprise Documentation":
        if wc <= 140:
            sentence = f"For enterprise documentation, see {anchor}."
        else:
            sentence = (
                f"Developers requiring enterprise documentation and production support can reference "
                f"{anchor} alongside these open-source libraries."
            )
    elif enterprise_suffix == "Enterprise API Reference":
        if wc <= 140:
            sentence = f"For the enterprise API reference, see {anchor}."
        else:
            sentence = (
                f"Developers requiring the enterprise API reference can use "
                f"{anchor} alongside these open-source libraries."
            )
    elif enterprise_suffix == "Enterprise Knowledge Base":
        if wc <= 140:
            sentence = f"For the enterprise knowledge base, see {anchor}."
        else:
            sentence = (
                f"Developers requiring enterprise knowledge base resources can reference "
                f"{anchor} alongside these open-source libraries."
            )
    elif enterprise_suffix == "Enterprise Blog":
        sentence = f"For enterprise tutorials, see {anchor}."
    else:  # Enterprise Product (products.aspose.com platform target)
        if wc <= 140:
            sentence = f"For enterprise features and support, see {anchor}."
        else:
            sentence = (
                f"Developers requiring enterprise features and production support can use "
                f"{anchor} alongside these open-source libraries."
            )

    text = current_content.rstrip()

    # Phase 4: near-duplicate suppression for YAML overview
    dups = _detect_near_duplicate(text, sentence)
    if dups:
        return text + f"\n<!-- NEAR_DUPLICATE_SUPPRESSED: {dups[0][:60]} -->"

    # CTA must be the final sentence — always append unconditionally.
    # Never insert mid-text: license/FOSS-closing sentences must precede the CTA, not follow it.
    return text + " " + sentence


def _rewrite_yaml_file(raw: str, data: dict, fm_text: str) -> str | None:
    """Rewrite the raw file preserving frontmatter structure.

    Uses _LiteralDumper to force | block scalar style for all multi-line
    strings.  Plain yaml.dump destroys block scalar styles — converting them
    to single-quoted flow scalars or double-quoted \\n-escaped strings — which
    breaks Hugo rendering of code blocks in product page content fields.
    """
    try:
        import yaml as _yaml

        # Dump modified data back to YAML with literal block scalar style
        new_fm = _yaml.dump(
            data,
            Dumper=_LiteralDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=10000,
        )

        # Reconstruct file: --- + new_fm + --- + (body if any)
        if raw.startswith("---"):
            end_idx = raw.find("---", 3)
            if end_idx != -1:
                body = raw[end_idx + 3:]  # everything after closing ---
                return f"---\n{new_fm}---{body}"

        return f"---\n{new_fm}---\n"
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Markdown section insertion (§5.2/5.3/5.4/5.5 / TC-BL-006)
# ──────────────────────────────────────────────────────────────────────────────

def _build_see_also_entry(
    target_url: str,
    family: str,
    platform: str | None,
    subdomain: str,
    families_map: dict,
    platforms_map: dict,
    target_type: str | None = None,
) -> str:
    """Build the See Also / Related Resources list entry.

    target_type: "platform" (use family+platform anchor) or "family" (use family-only anchor).
    When target_type is "family", platform is omitted from anchor text regardless of source platform.
    """
    fam_title = families_map.get(family, f"Aspose.{family.title()}")
    # FAMILY-ANCHOR rule: if resolved target is a family URL, never include "for {Platform}"
    if platform and target_type != "family":
        plat_title = platforms_map.get(platform, platform.title())
        display = f"{fam_title} for {plat_title}"
    else:
        display = fam_title

    # TC14 (2026-08-21): pass the real source subdomain so a legacy
    # blog-products-* template is correctly distinguished from an ordinary
    # products-* one for the same target_url -- in practice fresh
    # resolve_backlink() calls never route a blog source to a products.aspose.com
    # target, so this only matters for defensive consistency with
    # _expected_anchor_text()'s own now-identical parameter.
    enterprise_suffix = _anchor_suffix_for(target_url, target_type or "platform", source_subdomain=subdomain)
    link_text = f"{display} \u2014 {enterprise_suffix}"
    return f"- [{link_text}]({target_url})"


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split file into (frontmatter_block, body). frontmatter_block includes delimiters."""
    if not text.startswith("---"):
        return "", text
    end = text.find("---", 3)
    if end == -1:
        return "", text
    fm = text[:end + 3]
    body = text[end + 3:]
    return fm, body


def _is_inside_code_fence(text: str, pos: int) -> bool:
    """Check if position is inside a ``` code fence."""
    prefix = text[:pos]
    fence_count = len(re.findall(r'```', prefix))
    return fence_count % 2 == 1


def _find_section(body: str, header_re: str) -> tuple[int, int] | None:
    """Find a section by header regex. Returns (start, content_start) or None."""
    m = re.search(header_re, body, re.MULTILINE)
    if m:
        return m.start(), m.end()
    return None


def _get_section_header(subdomain: str) -> str:
    """Get the appropriate section header for this subdomain."""
    if subdomain == "blog.aspose.org":
        return RELATED_RESOURCES_HEADER
    return SEE_ALSO_HEADER


def _scrub_wrong_section_links(body: str, section_header: str, wrong_domain: str) -> tuple[str, int]:
    """Remove bullet entries linking to wrong_domain from a named section.

    Used to scrub stale products.aspose.com links from blog Related Resources
    sections before inserting the correct blog.aspose.com link (Phase 6.3 / F4).

    Returns (new_body, count_removed).
    """
    header_pattern = rf"^{re.escape(section_header)}\s*$"
    existing = _find_section(body, header_pattern)
    if not existing:
        return body, 0

    _, content_start = existing
    next_heading = re.search(r'^\s*##', body[content_start:], re.MULTILINE)
    section_end = content_start + next_heading.start() if next_heading else len(body)

    section_text = body[content_start:section_end]
    bullet_re = re.compile(
        r'^- \[.*?\]\(https?://' + re.escape(wrong_domain) + r'[^\)]*\)\n?',
        re.MULTILINE,
    )
    new_section, count = bullet_re.subn('', section_text)
    if count == 0:
        return body, 0

    return body[:content_start] + new_section + body[section_end:], count


def backfill_markdown(
    file_path: Path,
    target_url: str,
    family: str,
    platform: str | None,
    subdomain: str,
    page_type: str,
    families_map: dict,
    platforms_map: dict,
    *,
    dry_run: bool = True,
    target_type: str | None = None,
) -> BackfillChange:
    """Insert backlink into a Markdown page (docs/kb/reference/blog).

    target_type: "platform" or "family" — controls anchor text generation.
    """
    rel = file_path.relative_to(_REPO_ROOT).as_posix()
    raw = file_path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(raw)

    # TC4 (2026-08-21): computed early so it's available both for the
    # already-duplicated cleanup path below AND the fresh-insertion path
    # further down (same value either way).
    family_url_to_replace: str | None = None
    if target_type != "family" and platform:
        candidate = target_url.rstrip("/").rsplit("/", 1)[0] + "/"
        if candidate.rstrip("/") != target_url.rstrip("/"):
            family_url_to_replace = candidate

    # TC10 (2026-08-21): also computed early (moved up from further below) so
    # the idempotency-path DUPLICATE_SUBDOMAIN cleanup can re-insert the
    # target's own bullet after scrubbing same-host siblings, without
    # duplicating _build_see_also_entry()'s call or its formatting logic.
    section_header = _get_section_header(subdomain)
    entry = _build_see_also_entry(target_url, family, platform, subdomain, families_map, platforms_map,
                                   target_type=target_type)

    # Idempotency: check if target URL already in body
    if target_url.rstrip("/") in body:
        # TC4 (2026-08-21): the platform link is already present, but if a
        # STALE family-level bullet is ALSO still present, this page is one
        # of the confirmed-live duplicate-link cases (64 kb.aspose.org pages)
        # -- clean it up now instead of treating "target already present" as
        # fully idempotent. This is the retroactive half of the fix; the
        # insertion-time half further down prevents NEW duplicates.
        if family_url_to_replace and family_url_to_replace.rstrip("/") in body:
            new_body = _remove_stale_family_bullet(body, section_header, family_url_to_replace)
            if new_body != body:
                if not dry_run:
                    new_raw = fm + new_body
                    file_path.write_text(new_raw, encoding="utf-8")
                return BackfillChange(
                    file=rel, subdomain=subdomain, family=family, platform=platform,
                    page_type=page_type, target_url=target_url,
                    action="md_see_also" if subdomain != "blog.aspose.org" else "md_related_resources",
                    before_snippet=body[:200], after_snippet=new_body[:200],
                    dry_run=dry_run,
                    warning_messages=[
                        f"REPLACED_FAMILY_LINK: removed stale existing family-level bullet "
                        f"({family_url_to_replace}) -- platform-level link was already present"
                    ],
                )
        # TC10 (2026-08-21): the target link is already present, but some
        # OTHER bullet on the same aspose.com host is also still in the
        # section (a DUPLICATE_SUBDOMAIN case not covered by the
        # family-bullet-specific cleanup above, e.g. a leftover WRONG_TARGET
        # link that was never part of the family/platform fallback chain).
        # Retroactive counterpart to _insert_see_also()'s new_target_url scrub,
        # which only runs on the fresh-insertion path.
        target_host = target_url.split("://", 1)[-1].split("/", 1)[0].lower()
        section_before = _extract_affected_section(body, section_header)
        other_same_host = [
            u for u in count_qualifying_com_links(section_before)[1]
            if u.split("://", 1)[-1].split("/", 1)[0].lower() == target_host
            and u.rstrip("/") != target_url.rstrip("/")
        ]
        if other_same_host:
            new_body, _ = _scrub_wrong_section_links(body, section_header, target_host)
            # _scrub_wrong_section_links would also strip the target bullet itself
            # (it matches on host, not on the full URL) -- re-insert it if so.
            if target_url.rstrip("/") not in new_body:
                new_body = _insert_see_also(
                    new_body, section_header, entry, subdomain,
                )
            if new_body != body:
                if not dry_run:
                    new_raw = fm + new_body
                    file_path.write_text(new_raw, encoding="utf-8")
                return BackfillChange(
                    file=rel, subdomain=subdomain, family=family, platform=platform,
                    page_type=page_type, target_url=target_url,
                    action="md_see_also" if subdomain != "blog.aspose.org" else "md_related_resources",
                    before_snippet=body[:200], after_snippet=new_body[:200],
                    dry_run=dry_run,
                    warning_messages=[
                        f"REMOVED_DUPLICATE_SUBDOMAIN_LINK: removed {len(other_same_host)} other "
                        f"{target_host} bullet(s) -- target link was already present"
                    ],
                )
        return BackfillChange(
            file=rel, subdomain=subdomain, family=family, platform=platform,
            page_type=page_type, target_url=target_url,
            action="md_see_also" if subdomain != "blog.aspose.org" else "md_related_resources",
            before_snippet=body[:200], after_snippet=body[:200],
            skipped=True, skip_reason="Already contains target URL (idempotent)", dry_run=dry_run,
        )

    # Phase 6.3: For blog posts, scrub stale wrong-section products.aspose.com links
    # before the max-link guard. Without this, blog posts at the max qualifying
    # link count would be blocked even though all their links are wrong-section (F4).
    warnings_acc: list[str] = []
    if subdomain == "blog.aspose.org":
        body, scrubbed = _scrub_wrong_section_links(
            body, RELATED_RESOURCES_HEADER, "products.aspose.com/"
        )
        if scrubbed > 0:
            warnings_acc.append(
                f"SCRUBBED_WRONG_SECTION: removed {scrubbed} products.aspose.com link(s) before insertion"
            )

    # Max-link guard
    link_count, _ = count_qualifying_com_links(body)
    if link_count >= _max_qualifying_links():
        return BackfillChange(
            file=rel, subdomain=subdomain, family=family, platform=platform,
            page_type=page_type, target_url=target_url,
            action="md_see_also" if subdomain != "blog.aspose.org" else "md_related_resources",
            before_snippet=body[:200], after_snippet="",
            skipped=True, skip_reason=f"Already at max links ({link_count})", dry_run=dry_run,
        )

    # section_header/entry/family_url_to_replace were already computed above
    # (TC4/TC10, 2026-08-21) -- reused here for the fresh-insertion path's
    # replace-not-append behavior.

    # Phase 4: near-duplicate detection before injection (accumulator pattern, F5-safe)
    # Hard-block at high similarity — prevents duplicate anchor text with different URL.
    _nd_score = _near_dup_max_score(body, entry)
    if _nd_score >= _NEAR_DUPLICATE_HARD_BLOCK_THRESHOLD:
        action = "md_see_also" if subdomain != "blog.aspose.org" else "md_related_resources"
        return BackfillChange(
            file=rel, subdomain=subdomain, family=family, platform=platform,
            page_type=page_type, target_url=target_url,
            action=action, before_snippet=body[:200], after_snippet="",
            skipped=True,
            skip_reason=f"NEAR_DUPLICATE_HARD_BLOCK: sim={_nd_score:.3f}",
            dry_run=dry_run,
        )
    dups = _detect_near_duplicate(body, entry)
    if dups:
        warnings_acc.append(
            f"NEAR_DUPLICATE_DETECTED: similarity>={_NEAR_DUPLICATE_THRESHOLD} with: {dups[0][:80]}"
        )

    # Build the new body
    if family_url_to_replace and family_url_to_replace.rstrip("/") in body:
        warnings_acc.append(
            f"REPLACED_FAMILY_LINK: removed stale family-level bullet "
            f"({family_url_to_replace}) in favor of the platform-level link"
        )
    # TC10 (2026-08-21): warn when insertion is about to remove some OTHER
    # (non-family-fallback) same-host bullet too -- see _insert_see_also()'s
    # new_target_url param, which does the actual removal.
    _target_host = target_url.split("://", 1)[-1].split("/", 1)[0].lower()
    _section_before = _extract_affected_section(body, section_header) or ""
    _other_same_host = [
        u for u in count_qualifying_com_links(_section_before)[1]
        if u.split("://", 1)[-1].split("/", 1)[0].lower() == _target_host
        and (not family_url_to_replace or u.rstrip("/") != family_url_to_replace.rstrip("/"))
    ]
    if _other_same_host:
        warnings_acc.append(
            f"REMOVED_DUPLICATE_SUBDOMAIN_LINK: removed {len(_other_same_host)} other "
            f"{_target_host} bullet(s) already in this section to keep the page's "
            f"aspose.com links on distinct hosts"
        )
    new_body = _insert_see_also(
        body, section_header, entry, subdomain,
        family_url_to_replace=family_url_to_replace,
        new_target_url=target_url,
    )

    # Phase 4: prose validation after injection
    section_after = _extract_affected_section(new_body, section_header)
    prose_errors = _validate_prose(section_after, entry, target_url)
    if prose_errors:
        warnings_acc.extend(prose_errors)

    if not dry_run:
        new_raw = fm + new_body
        file_path.write_text(new_raw, encoding="utf-8")

    return BackfillChange(
        file=rel, subdomain=subdomain, family=family, platform=platform,
        page_type=page_type, target_url=target_url,
        action="md_see_also" if subdomain != "blog.aspose.org" else "md_related_resources",
        before_snippet=body[:200], after_snippet=new_body[:200],
        dry_run=dry_run,
        warning_messages=warnings_acc,
    )


def _remove_stale_family_bullet(body: str, section_header: str, family_url: str) -> str:
    """Remove a bullet line linking to family_url from the named section, if
    present (TC4, 2026-08-21). Returns body unchanged if the section or the
    bullet doesn't exist. Shared by _insert_see_also() (prevents new
    duplicates at insertion time) and backfill_markdown()'s idempotency path
    (retroactively cleans up an already-existing duplicate).
    """
    header_pattern = rf"^{re.escape(section_header)}\s*$"
    existing = _find_section(body, header_pattern)
    if not existing:
        return body
    _, content_start = existing
    next_heading = re.search(r'^\s*##', body[content_start:], re.MULTILINE)
    section_end = content_start + next_heading.start() if next_heading else len(body)

    stale_bullet_re = re.compile(
        r'^- \[.*?\]\(' + re.escape(family_url.rstrip("/")) + r'/?\)\n?',
        re.MULTILINE,
    )
    section_text = body[content_start:section_end]
    new_section_text, removed = stale_bullet_re.subn('', section_text)
    if not removed:
        return body
    return body[:content_start] + new_section_text + body[section_end:]


def _insert_see_also(
    body: str,
    section_header: str,
    entry: str,
    subdomain: str,
    *,
    family_url_to_replace: str | None = None,
    new_target_url: str | None = None,
) -> str:
    """Insert or append to See Also / Related Resources section.

    family_url_to_replace: (TC4, 2026-08-21) when set, any existing bullet
    line in the section whose URL matches this family-level URL is removed
    before the new (platform-level) entry is inserted -- previously this
    function only ever appended, silently leaving a stale family-level
    bullet alongside the new platform-level one (confirmed live on 64
    kb.aspose.org pages).

    new_target_url: (TC10, 2026-08-21) when set, any OTHER pre-existing
    bullet in the section that shares the new target's aspose.com host is
    also removed before insertion -- prevents insertion from creating a
    fresh DUPLICATE_SUBDOMAIN instance (the user's own diversity
    requirement: "those links must be from different subdomains on
    aspose.com"). family_url_to_replace already covers the specific
    family-vs-platform case above; this catches any other same-host bullet
    a WRONG_TARGET resolution left behind (e.g. a stale link that was never
    part of the family/platform fallback chain at all). Reuses the same
    scrub mechanism already proven for blog's wrong-section cleanup
    (Phase 6.3) rather than a new regex.
    """
    if family_url_to_replace:
        body = _remove_stale_family_bullet(body, section_header, family_url_to_replace)

    if new_target_url:
        host = new_target_url.split("://", 1)[-1].split("/", 1)[0].lower()
        body, _ = _scrub_wrong_section_links(body, section_header, host)

    # Check if section already exists
    header_pattern = rf"^{re.escape(section_header)}\s*$"
    existing = _find_section(body, header_pattern)

    if existing:
        # Append to existing section
        section_start, content_start = existing
        # Find end of section (next ## heading or end of file)
        next_heading = re.search(r'^\s*##', body[content_start:], re.MULTILINE)
        section_end = content_start + next_heading.start() if next_heading else len(body)

        if next_heading:
            return body[:section_end].rstrip() + "\n" + entry + "\n\n" + body[section_end:]
        else:
            # Append at end of section
            return body.rstrip() + "\n" + entry + "\n"
    else:
        # Create new section at end of body
        # Make sure we're not inside a code fence
        body_stripped = body.rstrip()

        # Close any unterminated code fence (safety guard)
        fence_count = len(re.findall(r'```', body_stripped))
        if fence_count % 2 == 1:
            body_stripped += "\n```"

        return body_stripped + f"\n\n{section_header}\n\n{entry}\n"


# ──────────────────────────────────────────────────────────────────────────────
# Main backfill runner
# ──────────────────────────────────────────────────────────────────────────────

SUBDOMAIN_ROOTS = {
    "docs.aspose.org":      "content/docs.aspose.org/en",
    "kb.aspose.org":        "content/kb.aspose.org/en",
    "reference.aspose.org": "content/reference.aspose.org/en",
    "products.aspose.org":  "content/products.aspose.org/en",
    "blog.aspose.org":      "content/blog.aspose.org",
}

OUT_OF_SCOPE_TYPES = {
    PageType.PRODUCTS_ROOT, PageType.BLOG_ARCHIVE, PageType.BLOG_UTILITY,
    PageType.SUBDOMAIN_ROOT, PageType.LOCALE_FILE, PageType.LOCALE_DIR,
    PageType.UNKNOWN_PATTERN,
}


def _load_display_maps(repo_root: Path) -> tuple[dict, dict]:
    """Load families and platforms display name maps."""
    try:
        families_map = json.loads((repo_root / "data" / "families.json").read_text(encoding="utf-8"))
    except Exception:
        families_map = {}

    try:
        import yaml as _yaml
        taxonomy = _yaml.safe_load(
            (repo_root / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml")
            .read_text(encoding="utf-8")
        )
        raw_plats = taxonomy.get("platforms") or {}
        platforms_map = {
            k: (v if isinstance(v, str) else v.get("display_name", k.title()))
            for k, v in raw_plats.items()
        }
    except Exception:
        platforms_map = {}

    return families_map, platforms_map


_BACKLINK_SCOPE_EXEMPT_RE = re.compile(r'backlink_scope:\s*["\']?exempt["\']?\s*$', re.MULTILINE)
_BACKLINK_EXEMPT_REASON_RE = re.compile(r'backlink_exempt_reason:\s*["\']?([^\n"\']+)["\']?\s*$', re.MULTILINE)
_BACKLINK_EXEMPT_EXPIRES_RE = re.compile(r'backlink_exempt_expires:\s*["\']?([0-9-]{10})["\']?\s*$', re.MULTILINE)


def _check_backlink_exemption(raw: str) -> str | None:
    """TC3 (2026-08-21): return a skip reason if this page has a valid,
    unexpired backlink_scope: exempt marker in its frontmatter -- otherwise
    None (proceed with reconciliation). Requires a real, non-frivolous
    exemption: entering EXEMPT is meant to require S-90 governed inspection
    per this mission's design (the CLI layer here can't enforce that gate
    itself, but it can and does refuse to honor an exemption that has no
    stated reason, and refuses to honor one whose expiry has passed rather
    than treating a stale marker as permanent).
    """
    if not _BACKLINK_SCOPE_EXEMPT_RE.search(raw):
        return None
    reason_match = _BACKLINK_EXEMPT_REASON_RE.search(raw)
    reason = reason_match.group(1).strip() if reason_match else None
    expires_match = _BACKLINK_EXEMPT_EXPIRES_RE.search(raw)
    if expires_match:
        try:
            expires_date = datetime.fromisoformat(expires_match.group(1)).date()
            if expires_date < datetime.now(timezone.utc).date():
                # Expired exemption auto-degrades back to normal reconciliation
                # rather than silently staying exempt forever.
                return None
        except ValueError:
            pass  # unparseable date -- fail closed to "not exempt", not "exempt forever"
    if not reason:
        # No stated reason -- refuse to honor a frivolous/incomplete exemption.
        return None
    return f"backlink_scope: exempt ({reason})"


def run_backfill(
    repo_root: Path,
    target_map: dict,
    *,
    subdomains: list[str] | None = None,
    family_filter: str | None = None,
    platform_filter: str | None = None,
    dry_run: bool = True,
    include_protected: bool = False,
    files_filter: set[str] | None = None,
    exact_deep_match_enabled: bool = False,
    authority: dict | None = None,
) -> BackfillManifest:
    """Run backfill across all matching content. Returns a BackfillManifest."""
    ts = datetime.now(timezone.utc).isoformat()
    families_map, platforms_map = _load_display_maps(repo_root)
    target_subdomains = subdomains or list(SUBDOMAIN_ROOTS.keys())

    # Load canonical platform overrides (A2 P0 — only http_verified: true entries applied)
    canonical_overrides: dict | None = None
    _overrides_path = repo_root / "data" / "backlinks" / "platform_canonical_overrides.yaml"
    if _overrides_path.exists():
        try:
            import yaml as _yaml_ovr
            canonical_overrides = _yaml_ovr.safe_load(_overrides_path.read_text(encoding="utf-8"))
        except Exception as _exc:
            print(f"  WARN: Could not load canonical overrides: {_exc}", file=sys.stderr)

    changes: list[BackfillChange] = []
    errors: list[dict] = []
    candidates = 0

    for sd in target_subdomains:
        if sd not in SUBDOMAIN_ROOTS:
            continue
        root = repo_root / SUBDOMAIN_ROOTS[sd]
        if not root.exists():
            print(f"  WARN: Content root not found: {root}", file=sys.stderr)
            continue

        for fpath in sorted(root.rglob("*.md")):
            # --files-from filter (canary/scoped apply)
            if files_filter is not None:
                rel_repo = fpath.relative_to(repo_root).as_posix()
                if rel_repo not in files_filter:
                    continue

            # Family/platform filter
            if family_filter or platform_filter:
                rel = fpath.relative_to(root).as_posix()
                parts = rel.split("/")
                if family_filter and (len(parts) < 1 or parts[0] != family_filter):
                    continue
                if platform_filter and (len(parts) < 2 or parts[1] != platform_filter):
                    continue

            candidates += 1

            try:
                pt, family, platform, subdomain = classify_page_type(fpath, repo_root)
            except Exception as exc:
                errors.append({"file": str(fpath), "error": f"classify: {exc}"})
                continue

            if pt in OUT_OF_SCOPE_TYPES:
                continue

            # TC3 (2026-08-21): auto_updatable: false no longer blocks backlink
            # reconciliation. Root cause of the original behavior: this flag
            # was designed to protect hand-authored PROSE from bot rewrites,
            # but the check treated the mandatory backlink CTA as part of that
            # protected prose too -- even though the write functions below
            # (backfill_products_yaml/backfill_markdown) were already narrowly
            # scoped to just the CTA sentence/See-Also section, never a
            # full-prose rewrite. Confirmed live: commit 3729d558a6 (2026-06-06)
            # used this exact flag to justify DELETING the CTA from 22 pages
            # including products.aspose.org/words, which then carried zero
            # backlink for 2.5+ months because nothing could ever touch it
            # again. The only thing that should still block reconciliation is
            # an EXPLICIT, reasoned, time-bounded exemption -- not the blanket
            # content-protection flag, which was never meant to govern this.
            if sd != "blog.aspose.org":
                try:
                    raw = fpath.read_text(encoding="utf-8")
                except Exception:
                    raw = ""
                exempt_reason = _check_backlink_exemption(raw)
                if exempt_reason:
                    changes.append(BackfillChange(
                        file=fpath.relative_to(repo_root).as_posix(),
                        subdomain=sd, family=family, platform=platform,
                        page_type=pt.value, target_url="",
                        action="skip", before_snippet="", after_snippet="",
                        skipped=True, skip_reason=exempt_reason,
                        dry_run=dry_run,
                    ))
                    continue
                # --include-protected retains its original meaning: a full,
                # unscoped write (used by TC15's canary/staged content backfill
                # when a page genuinely needs more than the CTA touched). The
                # narrow CTA-only reconciliation above proceeds regardless.
                _ = include_protected  # still consumed by callers expecting it; no longer a skip gate here

            # Resolve target
            chosen_url, chosen_type, chosen_sd, fallback_reason = resolve_backlink(
                family=family or "",
                platform=platform,
                source_subdomain=sd,
                target_map=target_map,
                exact_deep_match_enabled=exact_deep_match_enabled,
                canonical_overrides=canonical_overrides,
                authority=authority,
                source_file=fpath.relative_to(repo_root).as_posix(),
            )
            if not chosen_url:
                changes.append(BackfillChange(
                    file=fpath.relative_to(repo_root).as_posix(),
                    subdomain=sd, family=family, platform=platform,
                    page_type=pt.value, target_url="",
                    action="skip", before_snippet="", after_snippet="",
                    skipped=True, skip_reason=f"BLOCKED_TARGET: {fallback_reason}",
                    dry_run=dry_run,
                ))
                continue

            # Check existing link count
            try:
                if sd == "products.aspose.org":
                    raw_text = fpath.read_text(encoding="utf-8")
                    fm_text = raw_text
                    if raw_text.startswith("---"):
                        end = raw_text.find("---", 3)
                        if end != -1:
                            fm_text = raw_text[3:end]
                    import yaml as _yaml
                    data = _yaml.safe_load(fm_text)
                    overview_content = (data.get("overview", {}) or {}).get("content", "") or ""
                    link_count, _ = count_qualifying_com_links(overview_content)
                else:
                    raw_text = fpath.read_text(encoding="utf-8")
                    _, body = _split_frontmatter(raw_text)
                    link_count, _ = count_qualifying_com_links(body)
            except Exception:
                link_count = 0

            # Phase 6.3 (outer loop): For blog posts, if ALL qualifying links are wrong-section
            # products.aspose.com links, they will be scrubbed by backfill_markdown(). Reset
            # link_count so the max-link guard doesn't block before scrubbing can run (F4).
            if sd == "blog.aspose.org" and link_count >= _max_qualifying_links():
                try:
                    _, _existing_urls = count_qualifying_com_links(body)
                    if _existing_urls and all("products.aspose.com/" in u for u in _existing_urls):
                        link_count = 0  # all wrong-section; backfill_markdown() will scrub them
                except Exception:
                    pass

            # TC4 (2026-08-21): this outer max-link guard runs BEFORE
            # backfill_markdown()/backfill_products_yaml() is ever called, so
            # their own retroactive duplicate-cleanup never got a chance to
            # run -- confirmed live: content/kb.aspose.org/en/pdf/cpp/_index.md
            # stayed skipped ("2 existing links >= max 2") even after that fix
            # landed, because this earlier gate intercepted it first. Original
            # carve-out covered only the exact {family_url, chosen_url}
            # pairing on non-products subdomains. TC10 (2026-08-21) generalizes
            # this to any subdomain, and to any case where the correct
            # (chosen) target is already present alongside >=1 other distinct
            # link sharing its host -- the general DUPLICATE_SUBDOMAIN
            # precursor, not just the family-vs-platform special case.
            # products.aspose.org is included because backfill_products_yaml()
            # always fully regenerates overview.content when it proceeds
            # (never partial-appends), so letting a duplicate-subdomain
            # products page through is safe -- it self-heals via that
            # regeneration rather than needing its own bullet-level cleanup.
            if sd != "blog.aspose.org" and link_count >= _max_qualifying_links() and family and chosen_url:
                try:
                    _existing_text = overview_content if sd == "products.aspose.org" else body
                    _, _existing_urls = count_qualifying_com_links(_existing_text)
                    _distinct_existing = {u.rstrip("/").lower() for u in _existing_urls}
                    _chosen_norm = chosen_url.rstrip("/").lower()
                    _chosen_host = chosen_url.split("://", 1)[-1].split("/", 1)[0].lower()
                    _is_same_host_dup = (
                        _chosen_norm in _distinct_existing
                        and len(_distinct_existing) > 1
                        and any(
                            u != _chosen_norm and u.split("://", 1)[-1].split("/", 1)[0] == _chosen_host
                            for u in _distinct_existing
                        )
                    )
                    if _is_same_host_dup:
                        link_count = 0  # genuine duplicate-subdomain case; downstream backfill will dedup
                except Exception:
                    pass

            if link_count > 0:
                # Page already has aspose.com links — check compliance:
                # If links are in the acceptable fallback chain → COMPLIANT, skip.
                # If links are WRONG_TARGET and count < MAX → add correct link.
                # If OVER_LIMIT (>= MAX) → skip without touching.
                if link_count >= _max_qualifying_links():
                    changes.append(BackfillChange(
                        file=fpath.relative_to(repo_root).as_posix(),
                        subdomain=sd, family=family, platform=platform,
                        page_type=pt.value, target_url=chosen_url,
                        action="skip", before_snippet="", after_snippet="",
                        skipped=True, skip_reason=f"Has {link_count} existing aspose.com link(s) >= max {_max_qualifying_links()}",
                        dry_run=dry_run,
                    ))
                    continue
                # link_count == 1: check if it already matches acceptable chain
                try:
                    if sd == "products.aspose.org":
                        raw_text2 = fpath.read_text(encoding="utf-8")
                        fm_text2 = raw_text2
                        if raw_text2.startswith("---"):
                            end2 = raw_text2.find("---", 3)
                            if end2 != -1:
                                fm_text2 = raw_text2[3:end2]
                        import yaml as _yaml2
                        data2 = _yaml2.safe_load(fm_text2)
                        ov2 = (data2.get("overview", {}) or {}).get("content", "") or ""
                        _, existing_urls = count_qualifying_com_links(ov2)
                    else:
                        raw_text2 = fpath.read_text(encoding="utf-8")
                        _, body2 = _split_frontmatter(raw_text2)
                        _, existing_urls = count_qualifying_com_links(body2)
                except Exception:
                    existing_urls = []
                compliance = classify_compliance(
                    link_count, existing_urls, chosen_url,
                    family=family, platform=platform,
                    chosen_target_type=chosen_type,
                    chosen_target_subdomain=chosen_sd,
                )
                if compliance == FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE:
                    # Page has family-level link but platform-level is available.
                    # Replace the family link with the platform link.
                    pass  # fall through to backfill
                elif compliance == COMPLIANT:
                    # Deep upgrade: if --deep provides a more specific URL than what's
                    # already on the page, replace the existing landing link with the deep link.
                    deep_upgrade = (
                        exact_deep_match_enabled
                        and chosen_url
                        and chosen_url not in existing_urls
                        and any(chosen_url.startswith(u.rstrip("/")) or u.rstrip("/") in chosen_url
                                for u in existing_urls)
                    )
                    if not deep_upgrade:
                        changes.append(BackfillChange(
                            file=fpath.relative_to(repo_root).as_posix(),
                            subdomain=sd, family=family, platform=platform,
                            page_type=pt.value, target_url=chosen_url,
                            action="skip", before_snippet="", after_snippet="",
                            skipped=True, skip_reason="Already COMPLIANT",
                            dry_run=dry_run,
                        ))
                        continue
                    # Fall through to backfill — will replace existing link with deep link
                # WRONG_TARGET with room to add — fall through to backfill

            # Apply backfill
            try:
                if sd == "products.aspose.org":
                    change = backfill_products_yaml(
                        fpath, chosen_url, family or "", platform,
                        families_map, platforms_map, dry_run=dry_run,
                        target_type=chosen_type,
                    )
                else:
                    change = backfill_markdown(
                        fpath, chosen_url, family or "", platform,
                        sd, pt.value, families_map, platforms_map, dry_run=dry_run,
                        target_type=chosen_type,
                    )
                changes.append(change)
            except Exception as exc:
                rel = fpath.relative_to(repo_root).as_posix()
                errors.append({"file": rel, "error": str(exc)})

    # Build manifest
    modified = sum(1 for c in changes if not c.skipped)
    skipped = sum(1 for c in changes if c.skipped)

    manifest = BackfillManifest(
        generated_at=ts,
        generator=f"backlink_backfill.py v{SCRIPT_VERSION}",
        dry_run=dry_run,
        total_candidates=candidates,
        total_modified=modified,
        total_skipped=skipped,
        total_errors=len(errors),
        changes=[asdict(c) for c in changes],
        errors=errors,
        rollback_commands=[
            f"git checkout HEAD -- {c.file}"
            for c in changes if not c.skipped and not dry_run
        ],
    )
    return manifest


# ──────────────────────────────────────────────────────────────────────────────
# KB Upgrade — replace docs.aspose.com links with kb.aspose.com in KB pages
# ──────────────────────────────────────────────────────────────────────────────

_DOCS_LINK_RE = re.compile(
    r"- \[([^\]]*?Enterprise Documentation[^\]]*?)\]\(https://docs\.aspose\.com/([^)]+)\)"
)


def run_kb_upgrade(
    repo_root: Path,
    target_map: dict,
    *,
    dry_run: bool = True,
    family_filter: str | None = None,
    platform_filter: str | None = None,
) -> BackfillManifest:
    """Replace docs.aspose.com enterprise links with kb.aspose.com in KB pages.

    Two cases:
    1. Page has BOTH docs.aspose.com + kb.aspose.com links → remove docs line.
    2. Page has ONLY docs.aspose.com link → replace URL + anchor text with kb equivalent.
    Only replaces if kb.aspose.com/{family}/{platform}/ is verified HTTP 200 in target map.
    """
    ts = datetime.now(timezone.utc).isoformat()
    families_map, platforms_map = _load_display_maps(repo_root)
    all_urls = target_map.get("all_urls", {})
    kb_root = repo_root / SUBDOMAIN_ROOTS["kb.aspose.org"]

    changes: list[BackfillChange] = []
    errors: list[dict] = []
    candidates = 0

    for fpath in sorted(kb_root.rglob("*.md")):
        # Family/platform filter
        rel = fpath.relative_to(kb_root).as_posix()
        parts = rel.split("/")
        if family_filter and (len(parts) < 1 or parts[0] != family_filter):
            continue
        if platform_filter and (len(parts) < 2 or parts[1] != platform_filter):
            continue

        candidates += 1
        rel_repo = fpath.relative_to(repo_root).as_posix()

        try:
            raw = fpath.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append({"file": rel_repo, "error": str(exc)})
            continue

        # Only process files with docs.aspose.com enterprise links
        if "docs.aspose.com" not in raw:
            continue

        fm, body = _split_frontmatter(raw)
        docs_matches = list(_DOCS_LINK_RE.finditer(body))
        if not docs_matches:
            continue

        has_kb_link = bool(re.search(r"https://kb\.aspose\.com/", body))
        new_body = body

        for match in reversed(docs_matches):  # reverse to preserve offsets
            docs_path = match.group(2).rstrip("/")  # e.g. "3d/java"
            docs_path_parts = docs_path.split("/")
            if len(docs_path_parts) < 1:
                continue
            fam = docs_path_parts[0]
            plat = docs_path_parts[1] if len(docs_path_parts) > 1 else None

            # Check if kb.aspose.com equivalent is verified
            kb_host = HOST_MAP["kb"]
            if plat:
                kb_url = f"https://{kb_host}/{fam}/{plat}/"
            else:
                kb_url = f"https://{kb_host}/{fam}/"
            kb_entry = all_urls.get(kb_url)
            kb_verified = kb_entry and kb_entry.get("http_status") == 200

            if has_kb_link:
                # Case 1: both links exist — remove the docs.aspose.com line
                line_start = body.rfind("\n", 0, match.start())
                line_end = body.find("\n", match.end())
                if line_start == -1:
                    line_start = 0
                if line_end == -1:
                    line_end = len(body)
                # Remove the entire line (including leading newline)
                before_snippet = body[max(0, line_start):line_end + 1]
                new_body = new_body[:line_start] + new_body[line_end:]
                changes.append(BackfillChange(
                    file=rel_repo, subdomain="kb.aspose.org",
                    family=fam, platform=plat, page_type="kb_upgrade",
                    target_url=kb_url,
                    action="kb_upgrade_remove_docs_line",
                    before_snippet=before_snippet.strip()[:200],
                    after_snippet="(line removed)",
                    skipped=False, skip_reason="", dry_run=dry_run,
                ))
            elif kb_verified:
                # Case 2: only docs link — replace URL + anchor text
                fam_title = families_map.get(fam, f"Aspose.{fam.title()}")
                if plat:
                    plat_title = platforms_map.get(plat, plat.title())
                    display = f"{fam_title} for {plat_title}"
                else:
                    display = fam_title
                new_link_text = f"{display} \u2014 Enterprise Knowledge Base"
                new_entry = f"- [{new_link_text}]({kb_url})"
                before_snippet = match.group(0)[:200]
                new_body = new_body[:match.start()] + new_entry + new_body[match.end():]
                changes.append(BackfillChange(
                    file=rel_repo, subdomain="kb.aspose.org",
                    family=fam, platform=plat, page_type="kb_upgrade",
                    target_url=kb_url,
                    action="kb_upgrade_replace_docs_with_kb",
                    before_snippet=before_snippet,
                    after_snippet=new_entry[:200],
                    skipped=False, skip_reason="", dry_run=dry_run,
                ))
            else:
                # KB URL not verified — keep docs link as-is
                changes.append(BackfillChange(
                    file=rel_repo, subdomain="kb.aspose.org",
                    family=fam, platform=plat, page_type="kb_upgrade",
                    target_url=kb_url,
                    action="skip", before_snippet=match.group(0)[:200],
                    after_snippet="",
                    skipped=True,
                    skip_reason=f"kb.aspose.com equivalent not verified: {kb_url}",
                    dry_run=dry_run,
                ))

        if new_body != body and not dry_run:
            fpath.write_text(fm + new_body, encoding="utf-8")

    modified = sum(1 for c in changes if not c.skipped)
    skipped = sum(1 for c in changes if c.skipped)
    return BackfillManifest(
        generated_at=ts,
        generator=f"backlink_backfill.py v{SCRIPT_VERSION} --kb-upgrade",
        dry_run=dry_run,
        total_candidates=candidates,
        total_modified=modified,
        total_skipped=skipped,
        total_errors=len(errors),
        changes=[asdict(c) for c in changes],
        errors=errors,
        rollback_commands=[
            f"git checkout HEAD -- {c.file}"
            for c in changes if not c.skipped and not dry_run
        ],
    )


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backlink insertion engine for aspose.org English content."
    )
    parser.add_argument("--write", action="store_true",
                        help="Apply writes (default is dry-run)")
    parser.add_argument("--subdomain", nargs="+", choices=list(SUBDOMAIN_ROOTS.keys()),
                        help="Restrict to specific subdomain(s)")
    parser.add_argument("--family", help="Restrict to a specific family")
    parser.add_argument("--platform", help="Restrict to a specific platform")
    parser.add_argument("--include-protected", action="store_true",
                        help="Include auto_updatable: false pages")
    parser.add_argument("--output",
                        help="Output manifest JSON path (default: reports/backlinks/backfill_...)")
    parser.add_argument("--target-map", help="Path to data/aspose_com_targets.json")
    parser.add_argument(
        "--deep", action="store_true", default=False,
        help="Enable deep authority lookup (reads backlink_authority.json if present)",
    )
    parser.add_argument(
        "--authority", default=None,
        help="Path to backlink_authority.json (default: data/backlinks/workspace/backlink_authority.json)",
    )
    parser.add_argument(
        "--files-from", default=None,
        help="Path to a text file listing repo-relative content paths (one per line). "
             "When set, only those files are processed (canary/scoped apply).",
    )
    parser.add_argument(
        "--kb-upgrade", action="store_true", default=False,
        help="Upgrade KB pages: replace docs.aspose.com enterprise links with "
             "kb.aspose.com equivalents (or remove docs.aspose.com line when "
             "kb.aspose.com link already present).",
    )
    args = parser.parse_args()

    repo_root = _REPO_ROOT
    dry_run = not args.write
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

    mode = "DRY-RUN" if dry_run else "WRITE"
    print(f"Running backfill [{mode}]...", file=sys.stderr)

    # Load --files-from if provided
    files_filter: set[str] | None = None
    if args.files_from:
        ff_path = Path(args.files_from)
        if not ff_path.exists():
            print(f"FATAL: --files-from path not found: {ff_path}", file=sys.stderr)
            return 1
        lines = ff_path.read_text(encoding="utf-8").splitlines()
        files_filter = {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}
        print(f"  --files-from: {len(files_filter)} files scoped", file=sys.stderr)

    # Load deep authority if --deep
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

    if args.kb_upgrade:
        print(f"Running KB upgrade [{mode}]...", file=sys.stderr)
        manifest = run_kb_upgrade(
            repo_root=repo_root,
            target_map=target_map,
            dry_run=dry_run,
            family_filter=args.family,
            platform_filter=args.platform,
        )
    else:
        manifest = run_backfill(
            repo_root=repo_root,
            target_map=target_map,
            subdomains=args.subdomain,
            family_filter=args.family,
            platform_filter=args.platform,
            dry_run=dry_run,
            include_protected=args.include_protected,
            files_filter=files_filter,
            exact_deep_match_enabled=bool(args.deep and authority_data),
            authority=authority_data,
        )

    # Write manifest
    reports_dir = repo_root / "reports" / "backlinks"
    reports_dir.mkdir(parents=True, exist_ok=True)

    prefix = "kb_upgrade_dry_run" if args.kb_upgrade and dry_run else \
             "kb_upgrade_write" if args.kb_upgrade else \
             "backfill_dry_run" if dry_run else "backfill_write"
    if args.output:
        json_out = Path(args.output)
    else:
        json_out = reports_dir / f"{prefix}_{ts}.json"

    json_out.write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Write rollback script (write mode only)
    if not dry_run and manifest.rollback_commands:
        rollback_path = reports_dir / f"backfill_rollback_{ts}.sh"
        rollback_path.write_text(
            "#!/bin/bash\n# Auto-generated rollback script\n" +
            "\n".join(manifest.rollback_commands) + "\n",
            encoding="utf-8",
        )
        print(f"  Rollback: {rollback_path}", file=sys.stderr)

    # Console summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Backfill [{mode}] Complete", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Candidates: {manifest.total_candidates}", file=sys.stderr)
    print(f"  Modified:   {manifest.total_modified}", file=sys.stderr)
    print(f"  Skipped:    {manifest.total_skipped}", file=sys.stderr)
    print(f"  Errors:     {manifest.total_errors}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Manifest: {json_out}", file=sys.stderr)

    if manifest.errors:
        print(f"\nErrors:", file=sys.stderr)
        for err in manifest.errors:
            print(f"  [{err.get('file', '?')}] {err.get('error', '')}", file=sys.stderr)

    # Show sample of what would be written (dry-run preview)
    if dry_run:
        modified_changes = [c for c in manifest.changes if not c.get("skipped")]
        shown = 0
        for change in modified_changes[:5]:
            if shown == 0:
                print(f"\nSample diffs (first {min(5, len(modified_changes))}):", file=sys.stderr)
            print(f"\n  [{change['action']}] {change['file']}", file=sys.stderr)
            print(f"    Target: {change['target_url']}", file=sys.stderr)
            after = change.get("after_snippet", "")
            if after:
                print(f"    After:  ...{after[-100:]}", file=sys.stderr)
            shown += 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
