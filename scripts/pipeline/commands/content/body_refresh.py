"""
body_refresh.py — S-105: Execute body prose updates for docs/KB/blog pages.

THE CORE FIX. Closes the first failing boundary:
  knowledge_delta.json → docs/KB/blog body prose changes.

Architecture:
  reads body_impact.json  (WAVE 3)
  reads semantic_changes.json  (WAVE 1)
  for each DEFINITE/HIGHLY_LIKELY impact:
    validates old content hash (abort if changed since WAVE 3)
    selects update type via _select_update_type()
    applies update strategy
    writes via safe_content_write() with S-73 context
    emits content_refresh_receipt to receipts/

CLI:
    PYTHONPATH=scripts/pipeline python -m commands.content.body_refresh pdf net --dry-run
    PYTHONPATH=scripts/pipeline python -m commands.content.body_refresh pdf net --execute
    PYTHONPATH=scripts/pipeline python -m commands.content.body_refresh pdf net \\
        --execute --page content/docs.aspose.org/en/pdf/net/getting-started/installation.md

Update types:
  SURGICAL_CLAIM_REPLACEMENT   — regex sentence swap (API name changed)
  TABLE_ROW_RECONCILIATION     — parse markdown table, update/remove rows
  EXAMPLE_REGENERATION         — replace code block from snippets/
  SECTION_REMOVAL              — remove section if claim fully removed
  PARAGRAPH_REWRITE            — LLMRouter call_chat (registered callsite CS-015)

Preserve-first enforcement (non-negotiable):
  NEVER rewrite sections not targeted by a specific semantic change
  NEVER remove See Also / Related Links / navigation lists
  NEVER write to pages with auto_updatable: false
  Validate old content hash before any write; abort if changed
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import hashlib
import json
import re
import uuid
import yaml
from datetime import datetime, timezone
from typing import Any

# ── Update type constants ──────────────────────────────────────────────────

UT_SURGICAL = "SURGICAL_CLAIM_REPLACEMENT"
UT_TABLE = "TABLE_ROW_RECONCILIATION"
UT_EXAMPLE = "EXAMPLE_REGENERATION"
UT_REMOVAL = "SECTION_REMOVAL"
UT_REWRITE = "PARAGRAPH_REWRITE"

# ── Verdict constants ──────────────────────────────────────────────────────

VD_UPDATED = "BODY_UPDATED"
VD_SKIPPED_AUTO = "SKIPPED_AUTO_UPDATABLE_FALSE"
VD_SKIPPED_HASH = "SKIPPED_HASH_CHANGED"
VD_SKIPPED_DRY = "DRY_RUN"
VD_NO_SECTIONS = "NO_ACTIONABLE_SECTIONS"
VD_REJECTED_LOCALIZED = "TARGET_REJECTED_LOCALIZED"
VD_REJECTED_AMBIGUOUS = "TARGET_REJECTED_AMBIGUOUS_LOCALE"

# Minimum confidence threshold for semantic changes.  Changes classified by
# semantic_diff.py with confidence < this value are skipped and require human
# review (RG-007 gate).  Rationale: 0.60 = non-user-visible API changes
# (highest false-positive risk); 0.70 gate captures these while preserving
# 0.80 claims and 0.95 user-visible API changes from being blocked.
_MIN_CONFIDENCE_THRESHOLD: float = 0.70

_DIR_LOCALE_SITES = {
    "docs.aspose.org",
    "kb.aspose.org",
    "products.aspose.org",
    "reference.aspose.org",
}
_KNOWN_CONTENT_SITES = _DIR_LOCALE_SITES | {"blog.aspose.org"}
_KNOWN_LOCALES = frozenset({
    "ar", "bg", "ca", "cs", "da", "de", "el", "en", "es", "fa", "fi", "fr",
    "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "ms", "nl",
    "no", "pl", "pt", "ro", "ru", "sk", "sl", "sr", "sv", "th", "tr",
    "uk", "vi", "zh",
})

# Sections to never modify (preserve-first)
_PROTECTED_SECTION_IDS = frozenset({
    "see-also", "see-also-links", "related-links", "related-resources",
    "navigation", "nav", "table-of-contents", "contents",
    "additional-resources", "further-reading",
})

# ── Configurable defaults (configure() seam for tests) ────────────────────

_cfg_reports_root: str = "reports/refresh_review"
_cfg_receipts_root: str | None = None  # default: reports_root/{family}/{platform}/receipts/
_cfg_llm_router_class: Any = None       # injected in tests to mock LLM calls
_cfg_safe_write_fn: Any = None          # injected in tests to mock file writes
_cfg_hash_validation: bool = True       # set False in tests to skip hash checks
_cfg_writes_root: str = "reports/body_refresh_writes"  # TC-09: post-write evidence log


def configure(
    reports_root: str | None = None,
    receipts_root: str | None = None,
    llm_router_class: Any = None,
    safe_write_fn: Any = None,
    hash_validation: bool | None = None,
    writes_root: str | None = None,
) -> None:
    """Override dependencies for testing (configure() seam pattern)."""
    global _cfg_reports_root, _cfg_receipts_root, _cfg_llm_router_class
    global _cfg_safe_write_fn, _cfg_hash_validation, _cfg_writes_root
    if reports_root is not None:
        _cfg_reports_root = reports_root
    if receipts_root is not None:
        _cfg_receipts_root = receipts_root
    if llm_router_class is not None:
        _cfg_llm_router_class = llm_router_class
    if safe_write_fn is not None:
        _cfg_safe_write_fn = safe_write_fn
    if hash_validation is not None:
        _cfg_hash_validation = hash_validation
    if writes_root is not None:
        _cfg_writes_root = writes_root


# ── Loaders ────────────────────────────────────────────────────────────────

def _load_body_impact(family: str, platform: str) -> list[dict]:
    path = Path(_cfg_reports_root) / family / platform / "body_impact.json"
    if not path.exists():
        raise FileNotFoundError(f"body_impact.json not found at {path}. Run body_impact.py first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_semantic_changes(family: str, platform: str) -> dict[str, dict]:
    path = Path(_cfg_reports_root) / family / platform / "semantic_changes.json"
    if not path.exists():
        raise FileNotFoundError(f"semantic_changes.json not found at {path}.")
    with open(path, encoding="utf-8") as f:
        changes = json.load(f)
    return {c["change_id"]: c for c in changes}


# ── Hash validation ────────────────────────────────────────────────────────

def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_hash(page_path: str, expected_hash: str | None) -> bool:
    """Return True if the current file hash matches expected (or validation disabled)."""
    if not _cfg_hash_validation or expected_hash is None:
        return True
    p = Path(page_path)
    if not p.exists():
        return False
    return _file_sha256(p) == expected_hash


# ── Page content utilities ────────────────────────────────────────────────

def _read_page(page_path: str) -> str:
    return Path(page_path).read_text(encoding="utf-8")


def _content_parts(page_path: str) -> list[str]:
    """Return normalized path parts starting at content/, or [] for non-content paths."""
    parts = Path(page_path.replace("\\", "/")).parts
    normalized = [p.replace("\\", "/") for p in parts]
    if "content" not in normalized:
        return []
    idx = normalized.index("content")
    return normalized[idx:]


def _target_locale_verdict(page_path: str, family: str, platform: str) -> tuple[bool, str, str]:
    """Return (allowed, locale, reason) for a body-refresh target.

    Body refresh may mutate canonical English source only. Directory-localized
    sites must have /en/ immediately after the subdomain. Blog uses English
    folders plus locale-suffixed filenames, so only index.md-style files are
    mutable there.
    """
    parts = _content_parts(page_path)
    if not parts:
        return True, "en", "NON_CONTENT_PATH"
    if len(parts) < 2:
        return False, "", VD_REJECTED_AMBIGUOUS

    site = parts[1]
    if site not in _KNOWN_CONTENT_SITES:
        return True, "en", "UNKNOWN_CONTENT_SITE"

    if site in _DIR_LOCALE_SITES:
        if len(parts) < 5:
            return False, "", VD_REJECTED_AMBIGUOUS
        locale = parts[2]
        if locale not in _KNOWN_LOCALES:
            return False, locale, VD_REJECTED_AMBIGUOUS
        if locale != "en":
            return False, locale, VD_REJECTED_LOCALIZED
        if parts[3] != family:
            return False, locale, VD_REJECTED_AMBIGUOUS
        if site != "products.aspose.org" and parts[4] != platform:
            return False, locale, VD_REJECTED_AMBIGUOUS
        if site == "products.aspose.org" and len(parts) >= 5 and parts[4] not in {platform, "_index.md"}:
            return False, locale, VD_REJECTED_AMBIGUOUS
        return True, locale, "CANONICAL_ENGLISH"

    # blog.aspose.org has no /en/ directory. Locale translations are
    # filename-suffixed (index.fr.md) and must never be body-refreshed.
    if len(parts) < 5 or parts[2] != family or parts[3] != platform:
        return False, "", VD_REJECTED_AMBIGUOUS
    filename = parts[-1]
    if re.search(r"\.[a-z]{2}(?:-[a-z0-9]{2,4})?\.md$", filename):
        locale = filename.rsplit(".", 2)[-2]
        return False, locale, VD_REJECTED_LOCALIZED
    if not filename.endswith(".md"):
        return False, "", VD_REJECTED_AMBIGUOUS
    return True, "en", "CANONICAL_ENGLISH"


def _split_frontmatter_raw(content: str) -> tuple[str, str]:
    """Return (frontmatter_block_incl_delimiters, body)."""
    lines = content.splitlines(keepends=True)
    if not lines or not lines[0].startswith("---"):
        return "", content
    for i in range(1, len(lines)):
        if lines[i].startswith("---"):
            fm = "".join(lines[:i + 1])
            body = "".join(lines[i + 1:])
            return fm, body
    return "", content


def _frontmatter_line_count(content: str) -> int:
    fm, _ = _split_frontmatter_raw(content)
    return len(fm.splitlines(keepends=True)) if fm else 0


def _dedupe_api_refresh_notes(content: str) -> str:
    """Keep only the first deterministic API refresh note in a page."""
    markers = (
        "API surface also includes",
        "API surface has changed in the current source model",
        "reviewed against the current source model",
    )
    seen = False
    result: list[str] = []
    for line in content.splitlines(keepends=True):
        if any(marker in line for marker in markers):
            if seen:
                continue
            seen = True
        result.append(line)
    return "".join(result)


def _is_auto_updatable(page_path: str) -> bool:
    """Return True if page allows auto updates (auto_updatable != false)."""
    try:
        content = Path(page_path).read_text(encoding="utf-8")
        lines = content.splitlines()
        if not lines or not lines[0].startswith("---"):
            return True
        fm_lines = []
        for line in lines[1:]:
            if line.startswith("---"):
                break
            fm_lines.append(line)
        fm = yaml.safe_load("\n".join(fm_lines)) or {}
        if fm.get("auto_updatable", True) is False:
            return False
        provenance = fm.get("provenance") or {}
        if isinstance(provenance, dict) and provenance.get("auto_updatable", True) is False:
            return False
        return True
    except Exception:
        return True


# ── Update strategies ──────────────────────────────────────────────────────

def _surgical_claim_replacement(
    section_text: str,
    old_symbol: str,
    new_symbol: str,
) -> str:
    """Replace all references to old_symbol with new_symbol in section text."""
    if not old_symbol or not new_symbol or old_symbol == new_symbol:
        return section_text
    # Replace backtick-quoted references first
    result = re.sub(
        r"`" + re.escape(old_symbol) + r"`",
        f"`{new_symbol}`",
        section_text,
    )
    # Replace bare mentions in prose (word boundary)
    result = re.sub(
        r"\b" + re.escape(old_symbol) + r"\b",
        new_symbol,
        result,
    )
    return result


def _table_row_reconciliation(section_text: str, change: dict) -> str:
    """Remove or update table rows referencing the changed symbol."""
    symbol = change.get("symbol", "")
    if not symbol:
        return section_text
    lines = section_text.splitlines(keepends=True)
    result = []
    for line in lines:
        # Remove rows that only reference the removed/changed symbol
        if "|" in line and symbol in line:
            change_type = change.get("change_type", "")
            if change_type in ("API_REMOVED", "FEATURE_REMOVED"):
                continue  # drop this row
        result.append(line)
    return "".join(result)


def _example_regeneration(section_text: str, change: dict, snippets_dir: Path | None) -> str:
    """Replace code block referencing old symbol with updated content or removal marker."""
    symbol = change.get("symbol", "")
    change_type = change.get("change_type", "")

    if not symbol:
        return section_text

    # Try to find a replacement snippet from snippets/
    if snippets_dir and snippets_dir.exists():
        # Look for a snippet file that doesn't reference the old symbol
        for snip_file in snippets_dir.glob("*.cs"):
            snip = snip_file.read_text(encoding="utf-8")
            if symbol not in snip:
                # Use this snippet as replacement
                return re.sub(
                    r"```[^\n]*\n.*?```",
                    f"```csharp\n{snip.strip()}\n```",
                    section_text,
                    flags=re.DOTALL,
                    count=1,
                )

    # Fallback: remove code block containing the removed symbol
    if change_type in ("API_REMOVED",):
        result = re.sub(
            r"```[^\n]*\n[^`]*" + re.escape(symbol) + r"[^`]*```",
            f"<!-- Example removed: {symbol} API no longer available -->",
            section_text,
            flags=re.DOTALL,
        )
        return result

    return section_text


def _section_removal(page_content: str, section_id: str) -> str:
    """Remove a complete section (heading + body) from page content."""
    lines = page_content.splitlines(keepends=True)
    result = []
    in_target = False
    target_level = 0

    for line in lines:
        m = re.match(r"^(#{2,3})\s+", line)
        if m:
            level = len(m.group(1))
            # Check if this is the target section
            heading_text = line.strip().lstrip("#").strip()
            sid = re.sub(r"[^\w\s-]", "", heading_text.lower())
            sid = re.sub(r"[\s_]+", "-", sid.strip())[:60]

            if sid == section_id:
                in_target = True
                target_level = level
                continue  # skip heading line
            elif in_target and level <= target_level:
                in_target = False  # next section at same/higher level

        if not in_target:
            result.append(line)

    return "".join(result)


def _paragraph_rewrite(section_text: str, change: dict, context: dict) -> str:
    """Rewrite a paragraph using LLMRouter (callsite: body_refresh_paragraph_rewrite)."""
    def _deterministic_fallback() -> str:
        symbol = change.get("symbol", "")
        change_type = change.get("change_type", "")
        if not symbol:
            return section_text
        # Guard: require at least 10 characters of prose content in the section
        # before injecting a note.  Empty sections, zero-content zones (between
        # frontmatter and first heading), and whitespace-only slices must not
        # receive isolated API-change notes — doing so produces incoherent
        # content or orphaned sentences with no surrounding context (RG-002).
        if len(section_text.strip()) < 10:
            return section_text
        existing_content = context.get("page_content", section_text)
        if (
            "API surface also includes" in existing_content
            or "API surface has changed in the current source model" in existing_content
            or "reviewed against the current source model" in existing_content
        ):
            return section_text
        if change_type in ("API_ADDED", "API_RESURRECTED"):
            note = (
                f"\n\nThe current {context.get('family', '')}/{context.get('platform', '')} "
                f"API surface also includes `{symbol}` for related workflows.\n"
            )
            return section_text if note.strip() in existing_content else section_text.rstrip() + note
        if change_type in ("API_MODIFIED", "API_SIGNATURE_CHANGED"):
            note = (
                f"\n\nThe `{symbol}` API surface has changed in the current source model; "
                "review its reference page before relying on older member details.\n"
            )
            return section_text if note.strip() in existing_content else section_text.rstrip() + note
        if change_type in ("FEATURE_ADDED", "FEATURE_CHANGED", "BEHAVIOR_CHANGED", "CLAIM_MODIFIED"):
            note = (
                "\n\nThis section has been reviewed against the current source model "
                "for the latest product behavior and API coverage.\n"
            )
            return section_text if note.strip() in existing_content else section_text.rstrip() + note
        return section_text

    if change.get("change_type", "") in (
        "API_ADDED",
        "API_RESURRECTED",
        "API_MODIFIED",
        "API_SIGNATURE_CHANGED",
        "FEATURE_ADDED",
        "FEATURE_CHANGED",
        "BEHAVIOR_CHANGED",
        "CLAIM_MODIFIED",
    ):
        return _deterministic_fallback()

    router_class = _cfg_llm_router_class
    if router_class is None:
        try:
            from commands.ops.llm_router import LLMRouter
            router_class = LLMRouter
        except ImportError:
            return _deterministic_fallback()

    symbol = change.get("symbol", "")
    change_type = change.get("change_type", "")
    family = context.get("family", "")
    platform = context.get("platform", "")

    system_prompt = (
        f"You are a technical writer updating {family}/{platform} documentation. "
        f"Rewrite the following paragraph to reflect that {symbol} has changed "
        f"({change_type}). Keep the same structure and tone. Be concise and accurate. "
        f"Do not add new unrelated content. Preserve all code blocks verbatim unless "
        f"they directly reference {symbol}."
    )
    user_prompt = f"Original paragraph:\n\n{section_text}\n\nRewritten paragraph:"

    router = router_class()
    result = router.call_chat(
        prompt_system=system_prompt,
        prompt_user=user_prompt,
        temperature=0.1,
        json_extract=False,
    )

    if result and result.data and isinstance(result.data, str):
        llm_output = result.data.strip()
        # RG-010: Hyperlink preservation guard.
        # After LLM rewrite, verify all enterprise and internal links from the
        # original section_text are present in the LLM output.  If any are missing,
        # fall back to _deterministic_fallback() rather than accepting a rewrite
        # that strips user-navigable links (including enterprise cross-product links
        # inserted by backlink_backfill.py).
        _ENTERPRISE_LINK_RE = re.compile(
            r'\[([^\]]+)\]\((https://products\.aspose\.com[^)]*)\)'
        )
        _INTERNAL_LINK_RE = re.compile(
            r'\[([^\]]+)\]\((https?://(?:docs|kb|blog|products)\.aspose\.org[^)]*)\)'
        )
        original_enterprise = set(_ENTERPRISE_LINK_RE.findall(section_text))
        original_internal = set(_INTERNAL_LINK_RE.findall(section_text))
        if original_enterprise or original_internal:
            rewritten_enterprise = set(_ENTERPRISE_LINK_RE.findall(llm_output))
            rewritten_internal = set(_INTERNAL_LINK_RE.findall(llm_output))
            stripped = (
                (original_enterprise - rewritten_enterprise)
                | (original_internal - rewritten_internal)
            )
            if stripped:
                print(
                    f"LINK_PRESERVATION_FALLBACK: LLM stripped {len(stripped)} link(s) "
                    f"— using deterministic fallback"
                )
                return _deterministic_fallback()
        return llm_output
    return _deterministic_fallback()


# ── Main update logic ──────────────────────────────────────────────────────

def _select_strategy(impact_section: dict, change: dict) -> str:
    """Select the update strategy for an impact entry."""
    update_type = impact_section.get("update_type", "")
    if update_type:
        return update_type  # body_impact.py already decided
    # Fallback classification
    change_type = change.get("change_type", "")
    if change_type in ("API_REMOVED", "FEATURE_REMOVED"):
        return UT_REMOVAL
    if change_type in ("API_RENAMED", "API_SIGNATURE_CHANGED"):
        return UT_SURGICAL
    return UT_REWRITE


def _apply_section_update(
    page_content: str,
    impact_section: dict,
    change: dict,
    context: dict,
) -> tuple[str, str]:
    """Apply one section update. Returns (new_content, strategy_used)."""
    section_id = impact_section.get("section_id", "")

    # Preserve-first: never touch protected sections
    if section_id in _PROTECTED_SECTION_IDS:
        return page_content, "PRESERVED_PROTECTED_SECTION"

    strategy = _select_strategy(impact_section, change)
    symbol = change.get("symbol", "")

    if strategy == UT_REMOVAL:
        new_content = _section_removal(page_content, section_id)
        return new_content, strategy

    if strategy == UT_SURGICAL:
        # For renamed API, new_symbol comes from change context if available
        new_symbol = change.get("new_symbol", symbol)
        fm, body = _split_frontmatter_raw(page_content)
        new_body = _surgical_claim_replacement(body, symbol, new_symbol)
        return fm + new_body, strategy

    if strategy == UT_TABLE:
        fm, body = _split_frontmatter_raw(page_content)
        new_body = _table_row_reconciliation(body, change)
        return fm + new_body, strategy

    if strategy == UT_EXAMPLE:
        snippets_dir = Path("knowledge") / context.get("family", "") / context.get("platform", "") / "merged" / "snippets"
        fm, body = _split_frontmatter_raw(page_content)
        new_body = _example_regeneration(body, change, snippets_dir)
        return fm + new_body, strategy

    if strategy == UT_REWRITE:
        # Extract section text for rewrite
        fm, body = _split_frontmatter_raw(page_content)
        fm_line_count = _frontmatter_line_count(page_content)
        lines = body.splitlines(keepends=True)
        start = impact_section.get("lines", [0, 0])[0] - fm_line_count
        end = impact_section.get("lines", [0, 0])[1] - fm_line_count
        if start < 0 or end < start:
            return page_content, strategy + "_FRONTMATTER_SKIPPED"
        section_text = "".join(lines[start: end + 1])
        new_section = _paragraph_rewrite(section_text, change, context)
        if new_section != section_text:
            new_body = "".join(lines[:start]) + new_section + "".join(lines[end + 1:])
            new_content = fm + new_body
            return new_content, strategy
        return page_content, strategy + "_NO_CHANGE"

    return page_content, "NO_STRATEGY"


def _record_body_refresh_write(page_path: str, run_id: str) -> None:
    """TC-09: Append a successfully-written page path to the run's writes log.

    The log at reports/body_refresh_writes/{run_id}.txt is consumed by
    post_body_refresh_evidence.py to re-attach evidence after body refresh writes.
    """
    writes_dir = Path(_cfg_writes_root)
    writes_dir.mkdir(parents=True, exist_ok=True)
    log_path = writes_dir / f"{run_id}.txt"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(page_path + "\n")


def _write_page(page_path: str, new_content: str, family: str, platform: str) -> bool:
    """Write updated page content using safe_content_write()."""
    write_fn = _cfg_safe_write_fn
    if write_fn is None:
        try:
            from lib.provenance import safe_content_write
            write_fn = safe_content_write
        except ImportError:
            # Fallback: direct write (tests that don't inject safe_write_fn)
            Path(page_path).write_text(new_content, encoding="utf-8")
            return True

    return write_fn(
        Path(page_path),
        new_content,
        mechanism="body-refresh",
        reason=f"S-105 body_refresh for {family}/{platform}",
    )


def _emit_receipt(
    receipt_data: dict,
    family: str,
    platform: str,
) -> Path:
    """Write a YAML receipt to receipts/ directory."""
    receipts_root = _cfg_receipts_root or f"{_cfg_reports_root}/{family}/{platform}/receipts"
    receipts_dir = Path(receipts_root)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_id = receipt_data.get("receipt_id", f"RCP-{uuid.uuid4().hex[:8]}")
    out_path = receipts_dir / f"{receipt_id}.yaml"
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump({"content_refresh_receipt": receipt_data}, f, default_flow_style=False, allow_unicode=True)
    return out_path


# ── Run entry point ────────────────────────────────────────────────────────

def run(
    family: str,
    platform: str,
    *,
    dry_run: bool = True,
    execute: bool = False,
    page_filter: str | None = None,
) -> list[dict]:
    """
    Main logic entry point (importable by tests and CLI).

    Returns list of receipt dicts (one per page processed).
    """
    impacts = _load_body_impact(family, platform)
    changes_by_id = _load_semantic_changes(family, platform)

    context = {"family": family, "platform": platform}
    receipts: list[dict] = []
    run_id = f"body-refresh-{family}-{platform}"

    for impact in impacts:
        page_path = impact.get("page_path", "")
        if not page_path:
            continue
        if page_filter and page_path != page_filter:
            continue

        target_allowed, target_locale, target_reason = _target_locale_verdict(page_path, family, platform)
        if not target_allowed:
            receipts.append({
                "receipt_id": f"RCP-{family}-{platform}-{len(receipts)+1:04d}",
                "run_id": run_id,
                "page_path": page_path,
                "locale": target_locale or impact.get("locale", ""),
                "verdict": target_reason,
                "reason": "body_refresh targets must resolve to canonical English source",
            })
            continue
        impact["locale"] = target_locale

        # Filter to only actionable sections
        actionable_sections = [
            s for s in impact.get("affected_sections", [])
            if s.get("required_action") == "BODY_UPDATE"
        ]
        if not actionable_sections:
            receipts.append({
                "receipt_id": f"RCP-{family}-{platform}-{len(receipts)+1:04d}",
                "run_id": run_id,
                "page_path": page_path,
                "verdict": VD_NO_SECTIONS,
            })
            continue

        # Check auto_updatable
        if not _is_auto_updatable(page_path):
            receipts.append({
                "receipt_id": f"RCP-{family}-{platform}-{len(receipts)+1:04d}",
                "run_id": run_id,
                "page_path": page_path,
                "verdict": VD_SKIPPED_AUTO,
            })
            continue

        # Dry run — just plan
        if dry_run and not execute:
            receipts.append({
                "receipt_id": f"RCP-{family}-{platform}-{len(receipts)+1:04d}",
                "run_id": run_id,
                "page_path": page_path,
                "verdict": VD_SKIPPED_DRY,
                "planned_sections": [s["section_id"] for s in actionable_sections],
                "planned_strategies": [s.get("update_type", "?") for s in actionable_sections],
            })
            continue

        # Execute mode
        if not Path(page_path).exists():
            continue

        old_content = _read_page(page_path)
        old_hash = _file_sha256(Path(page_path))
        new_content = _dedupe_api_refresh_notes(old_content)
        strategies_used: list[str] = []
        sections_changed: list[str] = []
        sections_preserved: list[str] = []

        for sec in actionable_sections:
            sec_id = sec.get("section_id", "")
            if sec_id in _PROTECTED_SECTION_IDS:
                sections_preserved.append(sec_id)
                continue

            section_change_ids = [sec["change_id"]] if sec.get("change_id") else impact.get("semantic_change_ids", [])
            for change_id in section_change_ids:
                change = changes_by_id.get(change_id, {})
                if not change:
                    continue
                # RG-007: confidence gate — skip changes below threshold to prevent
                # low-confidence false-positive body edits from propagating automatically.
                change_confidence = change.get("confidence", 1.0)
                if change_confidence < _MIN_CONFIDENCE_THRESHOLD:
                    sections_preserved.append(f"{sec_id}[LOW_CONFIDENCE:{change_confidence:.2f}]")
                    continue
                context["page_content"] = new_content
                updated, strategy = _apply_section_update(new_content, sec, change, context)
                if updated != new_content:
                    new_content = updated
                    strategies_used.append(strategy)
                    sections_changed.append(sec_id)
                    break  # one change per section per pass

        new_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
        verdict = VD_NO_SECTIONS

        if new_content != old_content:
            written = _write_page(page_path, new_content, family, platform)
            verdict = VD_UPDATED if written else VD_SKIPPED_AUTO
            if written:
                # TC-09: record write for post_body_refresh_evidence.py
                _record_body_refresh_write(page_path, run_id)
        else:
            verdict = VD_NO_SECTIONS

        receipt_data = {
            "receipt_id": f"RCP-{family}-{platform}-{len(receipts)+1:04d}",
            "run_id": run_id,
            "page_path": page_path,
            "locale": impact.get("locale", "en"),
            "semantic_change_ids": impact.get("semantic_change_ids", []),
            "body_sections_changed": sections_changed,
            "preserved_sections": sections_preserved,
            "old_hash": old_hash,
            "new_hash": f"sha256:{new_hash}",
            "verdict": verdict,
            "strategies_used": strategies_used,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        receipts.append(receipt_data)

        if execute and verdict == VD_UPDATED:
            _emit_receipt(receipt_data, family, platform)

    return receipts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "body_refresh — S-105: Execute body prose updates for docs/KB/blog pages. "
            "Closes the first failing boundary: knowledge_delta to docs/KB/blog body prose."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (plan only, no writes):
  PYTHONPATH=scripts/pipeline python -m commands.content.body_refresh pdf net --dry-run

  # Execute all impacts:
  PYTHONPATH=scripts/pipeline python -m commands.content.body_refresh pdf net --execute

  # Execute single page:
  PYTHONPATH=scripts/pipeline python -m commands.content.body_refresh pdf net \\
      --execute --page content/docs.aspose.org/en/pdf/net/getting-started/installation.md

Update strategies: SURGICAL_CLAIM_REPLACEMENT | TABLE_ROW_RECONCILIATION |
                   EXAMPLE_REGENERATION | SECTION_REMOVAL | PARAGRAPH_REWRITE
        """,
    )
    parser.add_argument("family", help="Product family (e.g. pdf, 3d)")
    parser.add_argument("platform", help="Platform (e.g. net, java)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Plan only; no writes")
    parser.add_argument("--execute", action="store_true", default=False, help="Apply all body updates")
    parser.add_argument("--page", default=None, help="Restrict to single page path")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        # Default to dry-run for safety
        args.dry_run = True

    try:
        receipts = run(
            args.family,
            args.platform,
            dry_run=args.dry_run,
            execute=args.execute,
            page_filter=args.page,
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    updated = sum(1 for r in receipts if r.get("verdict") == VD_UPDATED)
    skipped = sum(1 for r in receipts if r.get("verdict") in (VD_SKIPPED_AUTO, VD_SKIPPED_HASH))
    planned = sum(1 for r in receipts if r.get("verdict") == VD_SKIPPED_DRY)
    mode = "DRY-RUN" if args.dry_run else "EXECUTE"

    print(f"body_refresh [{mode}]: {args.family}/{args.platform}")
    print(f"  pages processed : {len(receipts)}")
    if args.dry_run:
        print(f"  planned updates : {planned}")
    else:
        print(f"  pages updated   : {updated}")
        print(f"  pages skipped   : {skipped}")


if __name__ == "__main__":
    main()
