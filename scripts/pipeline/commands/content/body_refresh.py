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
    PYTHONPATH=scripts/pipeline python -m commands.content.body_refresh pdf net \\
        --execute --run-id ID --run-root reports/refresh_runs/pdf/net/ID
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

from core.fs import atomic_write

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
VD_FORBIDDEN_BLOCKED = "BLOCKED_FORBIDDEN_CLAIM"  # RPR-E-02: candidate introduced a forbidden-claim violation
VD_REGROUNDING_BLOCKED = "BLOCKED_TEMPLATE_PROPAGATION"  # RPR-E-03: reused a distinctive span without shared grounding

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

# ── Configurable defaults (configure() seam for tests) ──────────────────────
_UNSET = object()  # sentinel for configure() parameters where None is a valid value

_cfg_reports_root: str = "reports/refresh_review"
_cfg_receipts_root: str | None = None  # default: reports_root/{family}/{platform}/receipts/
_cfg_llm_router_class: Any = None       # injected in tests to mock LLM calls
_cfg_safe_write_fn: Any = None          # injected in tests to mock file writes
_cfg_hash_validation: bool = True       # set False in tests to skip hash checks
_cfg_writes_root: str = "reports/body_refresh_writes"  # TC-09: post-write evidence log
_cfg_forbidden_claims: "list[str] | None" = None  # RPR-E-02: injected in tests; None = load from index.json


def configure(
    reports_root: str | None = None,
    receipts_root: str | None = None,
    llm_router_class: Any = None,
    safe_write_fn: Any = None,
    hash_validation: bool | None = None,
    writes_root: str | None = None,
    forbidden_claims: "list[str] | None | object" = _UNSET,
) -> None:
    """Override dependencies for testing (configure() seam pattern)."""
    global _cfg_reports_root, _cfg_receipts_root, _cfg_llm_router_class
    global _cfg_safe_write_fn, _cfg_hash_validation, _cfg_writes_root
    global _cfg_forbidden_claims
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
    if forbidden_claims is not _UNSET:
        _cfg_forbidden_claims = forbidden_claims  # type: ignore[assignment]


# ── RPR-E-04: surface-differentiated update-strategy policy ──────────────────
#
# Each of the five content surfaces has a DIFFERENT editing contract. Reference
# pages are deterministically regenerated from api_surface.json by batch_reference
# (S-62) and must never be LLM-rewritten in place; products/docs/kb/blog carry
# hand/LLM-authored prose that the full strategy set may touch (safely, post
# RPR-E-01/02/03). Every surface has an EXPLICIT policy entry — nothing falls
# through to a silent default (plan §2.1: Amendment-009 punted docs/kb/blog with
# zero deterministic backing; this makes the routing explicit and testable).

# Deterministic, citation-backed strategies (grounded in a specific claim/API).
_CITATION_BACKED_STRATEGIES = frozenset({UT_SURGICAL, UT_TABLE, UT_EXAMPLE, UT_REMOVAL})
# The full set additionally permits the LLM PARAGRAPH_REWRITE.
_ALL_STRATEGIES = _CITATION_BACKED_STRATEGIES | frozenset({UT_REWRITE})

_SURFACE_POLICY: dict[str, dict] = {
    # surface   allowed strategies                     handoff for a disallowed strategy
    "reference": {"allowed": _CITATION_BACKED_STRATEGIES, "handoff": "batch-reference (S-62)"},
    "products":  {"allowed": _ALL_STRATEGIES,             "handoff": None},
    "docs":      {"allowed": _ALL_STRATEGIES,             "handoff": None},
    "kb":        {"allowed": _ALL_STRATEGIES,             "handoff": None},
    "blog":      {"allowed": _ALL_STRATEGIES,             "handoff": None},
    # A page we cannot classify is treated conservatively: deterministic strategies
    # only, LLM rewrites deferred to the S-20 (page-update) manual/agent path.
    "unknown":   {"allowed": _CITATION_BACKED_STRATEGIES, "handoff": "page-update (S-20)"},
}

_SURFACE_SITE_MAP = {
    "docs.aspose.org": "docs",
    "kb.aspose.org": "kb",
    "blog.aspose.org": "blog",
    "products.aspose.org": "products",
    "reference.aspose.org": "reference",
}


def _surface_for_page(page_path: str) -> str:
    """Infer the content surface (docs/kb/blog/products/reference) from a page path,
    or 'unknown' when the path names no known site."""
    normalized = str(page_path).replace("\\", "/")
    for site, surface in _SURFACE_SITE_MAP.items():
        if site in normalized:
            return surface
    return "unknown"


def _surface_allows_strategy(surface: str, update_type: str) -> tuple[bool, str | None]:
    """Return (allowed, handoff_target) for a strategy on a surface, per the
    explicit _SURFACE_POLICY. An unrecognized surface is treated as 'unknown'
    (never silently permissive)."""
    policy = _SURFACE_POLICY.get(surface, _SURFACE_POLICY["unknown"])
    allowed = update_type in policy["allowed"]
    return allowed, (None if allowed else policy["handoff"])


def _read_cited_evidence(page_content: str) -> list[str]:
    """RPR-E-03: return a page's cited evidence IDs (evidence.apis + evidence.claims)
    from its frontmatter, for the re-grounding shared-grounding check. Returns [] on
    no/malformed frontmatter."""
    if not page_content.startswith("---"):
        return []
    end = page_content.find("\n---", 3)
    if end == -1:
        return []
    try:
        import yaml
        fm = yaml.safe_load(page_content[3:end]) or {}
    except Exception:
        return []
    if not isinstance(fm, dict):
        return []
    ev = fm.get("evidence") or {}
    if not isinstance(ev, dict):
        return []
    ids = [str(a) for a in (ev.get("apis") or []) if a]
    ids += [str(c) for c in (ev.get("claims") or []) if c]
    return ids


# ── RPR-E-05: run-scoped LLM circuit breaker ─────────────────────────────────

_CIRCUIT_FAILURE_THRESHOLD = 3  # consecutive LLM failures in one run before the circuit opens
                                # NOTE: an untuned initial value (the LLM path was dead code until
                                # RPR-E-01, so no real failure-rate data exists yet). Documented,
                                # easily changed; RPR-H-01/pilots are the first chance to tune it.


class _LLMCircuit:
    """Run-scoped, in-process circuit breaker over the aggregate LLM.

    Not persisted, not shared across runs (deliberately simple — avoids inventing a
    second stateful subsystem). After _CIRCUIT_FAILURE_THRESHOLD consecutive
    call_chat() failures within one body_refresh run, the circuit OPENS and every
    remaining PARAGRAPH_REWRITE skips the LLM and goes straight to the deterministic
    template (fallback_reason=CIRCUIT_OPEN) — so a degraded-LLM window does not make
    every page pay the full provider-timeout chain (plan §2.5 SW-3).
    """

    def __init__(self, threshold: int = _CIRCUIT_FAILURE_THRESHOLD):
        self.threshold = threshold
        self.consecutive_failures = 0
        self.is_open = False

    def should_attempt(self) -> bool:
        return not self.is_open

    def record_success(self) -> None:
        self.consecutive_failures = 0  # a success resets the streak (circuit stays as-is)

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold:
            self.is_open = True


# HARDEN-A4: bump when the cached-output contract changes (prompt content is
# hashed into the key, so prompt template changes invalidate automatically).
_BODY_REFRESH_CACHE_SCHEMA = "1"

# RG-010 link-preservation guard patterns (hoisted module-level for A4/R4: the
# cache key folds these pattern strings in, so TIGHTENING the guard mechanically
# invalidates every entry validated under the looser guard — no schema-bump
# discipline required).
_ENTERPRISE_LINK_RE = re.compile(
    r'\[([^\]]+)\]\((https://products\.aspose\.com[^)]*)\)'
)
_INTERNAL_LINK_RE = re.compile(
    r'\[([^\]]+)\]\((https?://(?:docs|kb|blog|products)\.aspose\.org[^)]*)\)'
)


def run_is_llm_degraded(receipts: list[dict]) -> bool:
    """RPR-E-05: a run is 'LLM degraded' if any page's fallback_reason names a cause
    other than a link-preservation violation (which reflects LLM output quality, not
    an outage). This is the signal a manifest writer maps to manifest.llm_degraded."""
    for r in receipts:
        fr = r.get("fallback_reason")
        if fr not in (None, "NONE", "LINK_PRESERVATION_VIOLATION"):
            return True
    return False


def _scan_forbidden_claims(
    old_content: str, new_content: str, family: str, platform: str
) -> tuple[list[dict], bool, str]:
    """RPR-E-02: return forbidden-claim violations NEWLY introduced by new_content.

    Uses the injected _cfg_forbidden_claims when set (tests); otherwise loads the
    product's forbidden_claims from merged/index.json.

    HARDEN-A7: returns (violations, scan_ok, error). A load/scan failure is still
    non-fatal for THE RUN (the gate must not crash a whole refresh over a scanner
    bug) but is no longer silent: scan_ok=False propagates into the page receipt,
    and run_has_unverified_forbidden_claims_scans() lets the launch/readiness
    gate refuse to ship a page whose scan never actually ran. The old return
    ([] on error) was indistinguishable from "scanned clean".
    """
    try:
        from lib.forbidden_claims_check import load_forbidden_claims, newly_introduced
        if _cfg_forbidden_claims is not None:
            forbidden = _cfg_forbidden_claims
        else:
            forbidden = load_forbidden_claims(family, platform)
        if not forbidden:
            return [], True, ""
        return newly_introduced(old_content, new_content, forbidden), True, ""
    except Exception as exc:  # noqa: BLE001 — fail-open for the run, loud in the receipt
        print(f"FORBIDDEN_SCAN_UNVERIFIED: forbidden-claims scan failed for "
              f"{family}/{platform} — page will carry scan_ok=false and must be "
              f"re-scanned before launch: {exc}")
        return [], False, f"{type(exc).__name__}: {exc}"


def run_has_unverified_forbidden_claims_scans(receipts: list[dict]) -> bool:
    """HARDEN-A7: True if any page in this run wrote content whose forbidden-claims
    scan cannot be shown to have completed. Launch gate L-03 / readiness must
    treat such pages as unscanned, not clean.

    Two trigger conditions (R5):
      - scan_ok is explicitly False (scan raised — fail-open-but-loud), OR
      - the receipt says content was WRITTEN (verdict BODY_UPDATED) but carries
        no forbidden_claims_scan record at all (pre-A7 receipt shape, or a
        future regression that drops the field). "No scan record" must read as
        unverifiable — the exact ambiguity A7 exists to kill.
    """
    for r in receipts:
        scan = r.get("forbidden_claims_scan")
        if isinstance(scan, dict):
            if scan.get("ok") is False:
                return True
        elif r.get("verdict") == VD_UPDATED:
            return True
    return False


def find_unverified_forbidden_claims_receipts(
    family: str, platform: str, *, repo_root: Path
) -> list[str]:
    """HARDEN-A7 finding-1: scan ON-DISK refresh receipts (not an in-memory
    run's list — this reads reports/refresh_review/{family}/{platform}/receipts/
    directly) and return the names of any whose forbidden-claims scan did not
    verifiably complete: scan_ok=False, or a written page (verdict BODY_UPDATED)
    with no forbidden_claims_scan record at all.

    This is the single source of truth for that check — launch_gate.py's L-03
    gate and readiness_scorecard.py's verdict both call this instead of each
    re-implementing the same YAML-scanning logic, which is exactly the kind of
    drift-prone duplication root cause #7 (docs/logic asserting a protection
    that isn't actually wired everywhere it needs to be) exists to catch.
    """
    receipts_dir = Path(repo_root) / "reports" / "refresh_review" / family / platform / "receipts"
    if not receipts_dir.is_dir():
        return []
    unverified: list[str] = []
    for receipt_path in sorted(receipts_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(receipt_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 — an unreadable receipt is unverifiable, not clean
            unverified.append(f"{receipt_path.name} (unreadable: {type(exc).__name__}: {exc})")
            continue
        receipt = data.get("content_refresh_receipt", data)
        scan = receipt.get("forbidden_claims_scan")
        if isinstance(scan, dict):
            if scan.get("ok") is False:
                unverified.append(receipt_path.name)
        elif receipt.get("verdict") == VD_UPDATED:
            unverified.append(f"{receipt_path.name} (no scan record)")
    return unverified


# ── Loaders ────────────────────────────────────────────────────────────────

def _load_body_impact(
    family: str,
    platform: str,
    *,
    product_root: Path | None = None,
) -> list[dict]:
    path = (
        product_root / "body_impact.json"
        if product_root is not None
        else Path(_cfg_reports_root) / family / platform / "body_impact.json"
    )
    if not path.exists():
        raise FileNotFoundError(f"body_impact.json not found at {path}. Run body_impact.py first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_traffic_tiers(
    family: str,
    platform: str,
    *,
    product_root: Path | None = None,
) -> dict[str, str]:
    """Return {page_path: traffic_tier} from a sibling page_impact.json, or {}
    if it doesn't exist -- SEO-BODY-REFRESH-ORDER-BY-TRAFFIC reads this purely
    to choose PROCESSING ORDER in the loop below; a missing file (a dry-run,
    a unit test, or any body_refresh invocation without a full PIA pass) must
    never block or change which impacts get processed, only leave their
    original order untouched. Never raises.
    """
    path = (
        product_root / "page_impact.json"
        if product_root is not None
        else Path(_cfg_reports_root) / family / platform / "page_impact.json"
    )
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    tiers: dict[str, str] = {}
    for row in data.get("pages", []):
        if not isinstance(row, dict):
            continue
        page_path = row.get("path")
        tier = row.get("traffic_tier")
        if page_path and tier:
            tiers[Path(page_path).as_posix()] = tier
    return tiers


_TRAFFIC_TIER_SORT_RANK = {"high": 0, "medium": 1, "no-data": 2}


def _sort_impacts_by_traffic_tier(impacts: list[dict], tiers: dict[str, str]) -> list[dict]:
    """Stable-sort `impacts` so higher-traffic pages process first.

    Order-only: the returned list contains exactly the same impact entries
    as the input, in a different order -- never adds, drops, or filters any
    entry. A page absent from `tiers` (no page_impact.json, or that page not
    present in it) sorts as "no-data", matching the same default every page
    gets from page_impact_assess.py itself when it has no real GSC signal.
    Python's sort is stable, so within a tier, original relative order
    (whatever _load_body_impact/body_impact.py produced) is preserved.
    """
    def _rank(impact: dict) -> int:
        page_path = Path(str(impact.get("page_path", ""))).as_posix()
        tier = tiers.get(page_path, "no-data")
        return _TRAFFIC_TIER_SORT_RANK.get(tier, 2)

    return sorted(impacts, key=_rank)


def _load_semantic_changes(
    family: str,
    platform: str,
    *,
    product_root: Path | None = None,
) -> dict[str, dict]:
    path = (
        product_root / "semantic_changes.json"
        if product_root is not None
        else Path(_cfg_reports_root) / family / platform / "semantic_changes.json"
    )
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


# ── TC-08: Claim grounding helpers ─────────────────────────────────────────

def _load_claim_text(claim_id: str, claims_path: Path) -> str:
    """Load a single claim's text from claims.json. Returns empty string if absent."""
    if not claim_id or not claims_path.exists():
        return ""
    try:
        data = json.loads(claims_path.read_text(encoding="utf-8"))
        claims = data if isinstance(data, list) else data.get("claims", [])
        for c in claims:
            if isinstance(c, dict) and c.get("claim_id") == claim_id:
                return c.get("claim_text") or c.get("text") or ""
    except (json.JSONDecodeError, OSError):
        pass
    return ""


def _get_claim_grounding(change: dict, context: dict) -> tuple[str, str]:
    """
    Return (old_claim_text, new_claim_text) for TC-08 grounded prompt.

    Sources:
      old_claim_text: knowledge/{family}/{platform}/merged.bak/claims.json
      new_claim_text: knowledge/{family}/{platform}/merged/claims.json
    Falls back to empty strings when bak is absent (first run / no prior state).
    """
    claim_id = change.get("claim_id", "")
    if not claim_id:
        return "", ""

    family = context.get("family", "")
    platform = context.get("platform", "")
    if not family or not platform:
        return "", ""

    # BUGFIX (session 2, found while building RPR-F-03): parents[3] from this file's
    # path (scripts/pipeline/commands/content/body_refresh.py) resolves to scripts/,
    # not the repo root — parents[4] is correct. With the old off-by-one, bak_claims/
    # new_claims.exists() were always False, so every PARAGRAPH_REWRITE call has been
    # running in degraded (ungrounded) mode in production regardless of whether real
    # claim-grounding data was available, since RPR-E-01's routing fix made this
    # branch reachable. Verified empirically: parents[3] == .../scripts (no knowledge/
    # subdir there), parents[4] == the real repo root (has knowledge/).
    repo_root = Path(__file__).resolve().parents[4]
    base = repo_root / "knowledge" / family / platform
    bak_claims = base / "merged.bak" / "claims.json"
    new_claims = base / "merged" / "claims.json"

    old_text = _load_claim_text(claim_id, bak_claims)
    new_text = _load_claim_text(claim_id, new_claims)

    if not old_text and not bak_claims.exists():
        print(f"WARNING: merged.bak/claims.json absent for {family}/{platform} — "
              f"using degraded (ungrounded) prompt for claim {claim_id}")

    return old_text, new_text


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

    # RPR-E-01 (aspose-org-foss-refresh-tidy-lightning): this block used to
    # short-circuit to _deterministic_fallback() for every change_type that
    # body_impact.py's _select_update_type() ever routes to PARAGRAPH_REWRITE
    # (API_ADDED/API_RESURRECTED/API_MODIFIED/API_SIGNATURE_CHANGED/
    # FEATURE_ADDED/BEHAVIOR_CHANGED/CLAIM_MODIFIED — see body_impact.py
    # lines 169-176), which made the LLM callsite below permanently
    # unreachable in production regardless of whether an LLM router was
    # configured. The LLM attempt now always runs first for every change
    # type; failure at any stage (missing router, exception, timeout, empty
    # response, or a link-preservation violation) falls back to the same
    # _deterministic_fallback() template as before — this is a pure
    # reachability fix, not a change to fallback content or triggers.

    # RPR-E-05: record why we fell back (if we do). The caller reads
    # context["_fallback_reason"] after this returns.
    def _fallback(reason: str) -> str:
        context["_fallback_reason"] = reason
        return _deterministic_fallback()

    symbol = change.get("symbol", "")
    change_type = change.get("change_type", "")
    family = context.get("family", "")
    platform = context.get("platform", "")

    # TC-08: Load claim grounding from bak/claims.json → merged/claims.json.
    # When available, the prompt anchors the LLM to the exact old→new claim
    # text, preventing hallucination of unverified capabilities.
    old_claim_text, new_claim_text = _get_claim_grounding(change, context)
    grounded = bool(old_claim_text or new_claim_text)

    if grounded:
        system_prompt = (
            f"You are a technical writer maintaining {family}/{platform} documentation.\n"
            f"A specific claim has changed. Update ONLY the affected sentence or sentences.\n"
            f"Do not modify surrounding context. Do not introduce any capability, behavior, "
            f"or limitation that is not explicitly stated in the knowledge provided below.\n"
            f"If you are uncertain, preserve the original text.\n\n"
            f"Knowledge (authoritative):\n"
            f"  Old claim: {old_claim_text or '(not available)'}\n"
            f"  New claim: {new_claim_text or '(not available)'}\n"
            f"  Change type: {change_type}\n\n"
            f"Rules:\n"
            f"  - Preserve all code blocks verbatim unless they reference {symbol!r} directly.\n"
            f"  - Do not remove links.\n"
            f"  - Match the register of adjacent sentences.\n"
            f"  - Output only the rewritten paragraph, nothing else."
        )
        user_prompt = (
            f"Original section:\n\n{section_text}\n\nRewritten section:"
        )
    else:
        # Degraded (ungrounded) mode — merged.bak absent or no claim_id
        system_prompt = (
            f"You are a technical writer updating {family}/{platform} documentation. "
            f"Rewrite the following paragraph to reflect that {symbol} has changed "
            f"({change_type}). Keep the same structure and tone. Be concise and accurate. "
            f"Do not add new unrelated content. Preserve all code blocks verbatim unless "
            f"they directly reference {symbol}."
        )
        user_prompt = f"Original paragraph:\n\n{section_text}\n\nRewritten paragraph:"

    # HARDEN-A4: content-hash cache. The rendered prompts embed the section text,
    # claim grounding, symbol, and change type, so the key invalidates exactly
    # when the input actually changed. Checked BEFORE the circuit breaker — a hit
    # needs no LLM, so a degraded-LLM window must not block it. Only outputs that
    # passed RG-010 link preservation are ever stored (see save site below); the
    # page-level forbidden-claims gate still runs downstream on every path, cache
    # hit or miss, so caching never weakens enforcement.
    llm_cache = context.get("_llm_cache")
    cache_key = None
    if llm_cache is not None:
        from lib.llm_output_cache import build_cache_key, sha256_text
        cache_key = build_cache_key([
            family, platform, change_type,
            sha256_text(system_prompt), sha256_text(user_prompt),
            sha256_text(_ENTERPRISE_LINK_RE.pattern + _INTERNAL_LINK_RE.pattern),
            _BODY_REFRESH_CACHE_SCHEMA,
        ])
        entry = llm_cache.load(cache_key)
        if entry is not None and isinstance(entry.get("output"), str):
            print(f"LLM_CACHE_HIT: body-refresh rewrite reused ({cache_key[:12]}...) "
                  f"via {entry.get('model_used', '?')}")
            context["_fallback_reason"] = "NONE"
            return entry["output"]

    circuit = context.get("_llm_circuit")
    # If the run-scoped circuit is already open, skip the LLM entirely.
    if circuit is not None and not circuit.should_attempt():
        return _fallback("CIRCUIT_OPEN")

    router_class = _cfg_llm_router_class
    if router_class is None:
        try:
            from commands.ops.llm_router import LLMRouter
            router_class = LLMRouter
        except ImportError:
            return _fallback("LLM_UNAVAILABLE")

    try:
        router = router_class()
        from commands.ops.llm_router import LLMCallContext
        result = router.call_chat(
            prompt_system=system_prompt,
            prompt_user=user_prompt,
            temperature=0.1,
            json_extract=False,
            context=LLMCallContext.create("body-refresh", "body-refresh", "paragraph-rewrite"),
        )
    except Exception as exc:  # noqa: BLE001 — any router failure must fail safe, not crash the refresh run
        print(
            f"LLM_CALL_FAILED: {type(exc).__name__}: {exc} "
            f"— using deterministic fallback"
        )
        if circuit is not None:
            circuit.record_failure()
        return _fallback("LLM_ERROR")

    if result and result.data and isinstance(result.data, str):
        if circuit is not None:
            circuit.record_success()
        llm_output = result.data.strip()
        # RG-010: Hyperlink preservation guard.
        # After LLM rewrite, verify all enterprise and internal links from the
        # original section_text are present in the LLM output.  If any are missing,
        # fall back to _deterministic_fallback() rather than accepting a rewrite
        # that strips user-navigable links (including enterprise cross-product links
        # inserted by backlink_backfill.py). Patterns are module constants (R4) —
        # their text participates in the A4 cache key.
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
                # A link violation is NOT a circuit failure — the LLM was reachable
                # and responded; its output was just rejected for quality.
                return _fallback("LINK_PRESERVATION_VIOLATION")
        context["_fallback_reason"] = "NONE"
        # HARDEN-A4: store only RG-010-passing LLM output — a fallback/template
        # result must never masquerade as a cached LLM rewrite.
        if llm_cache is not None and cache_key:
            model_used = f"{getattr(result, 'provider', '?')}/{getattr(result, 'model', '?')}"
            llm_cache.save(cache_key, llm_output, model_used)
        return llm_output
    # Empty / non-string response.
    if circuit is not None:
        circuit.record_failure()
    return _fallback("LLM_EMPTY_RESPONSE")


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
    *,
    run_root: "Path | None" = None,
) -> tuple[Path, str]:
    """Validate and atomically write one immutable YAML receipt.

    A repeated emission is accepted only when the bytes are identical. Reusing a
    receipt ID for different evidence is a hard error instead of an overwrite.
    """
    # A run-scoped root is the production authority.  Test/legacy dependency
    # injection must never redirect receipts out of that run after another
    # caller configured this module in the same process.
    receipts_root = (
        run_root / "receipts"
        if run_root is not None
        else Path(_cfg_receipts_root)
        if _cfg_receipts_root is not None
        else Path(f"{_cfg_reports_root}/{family}/{platform}/receipts")
    )
    receipts_dir = Path(receipts_root)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_id = receipt_data.get("receipt_id", f"RCP-{uuid.uuid4().hex[:8]}")
    out_path = receipts_dir / f"{receipt_id}.yaml"
    from lib.schema_validators import validate_page_patch_receipt

    errors = validate_page_patch_receipt(receipt_data)
    if errors:
        raise ValueError(
            f"Refusing to write invalid body-refresh receipt {receipt_id}: {errors}"
        )
    rendered = yaml.safe_dump(
        {"content_refresh_receipt": receipt_data},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    if out_path.is_file():
        existing_text = out_path.read_text(encoding="utf-8")
        if existing_text != rendered:
            existing_doc = yaml.safe_load(existing_text) or {}
            existing_receipt = existing_doc.get("content_refresh_receipt") or {}
            comparable_existing = {
                key: value
                for key, value in existing_receipt.items()
                if key != "generated_at"
            }
            comparable_new = {
                key: value
                for key, value in receipt_data.items()
                if key != "generated_at"
            }
            if comparable_existing == comparable_new:
                receipt_data["generated_at"] = existing_receipt.get(
                    "generated_at", receipt_data.get("generated_at")
                )
                rendered = existing_text
            else:
                raise FileExistsError(
                    f"Receipt ID collision: {out_path} already exists with different evidence"
                )
    else:
        atomic_write(out_path, rendered)
    digest = "sha256:" + hashlib.sha256(out_path.read_bytes()).hexdigest()
    return out_path, digest


def _normalized_body_hash(text: str) -> str:
    from commands.content.audit_content_hash import _body_hash

    return "sha256:" + _body_hash(text)


def _frontmatter_hash(text: str) -> str:
    from commands.content.audit_content_hash import _split_frontmatter_body

    frontmatter, _ = _split_frontmatter_body(text)
    return "sha256:" + hashlib.sha256(frontmatter.encode("utf-8")).hexdigest()


def _frontmatter_evidence_ids(text: str) -> tuple[list[str], list[str]]:
    from commands.content.audit_content_hash import _split_frontmatter_body

    frontmatter, _ = _split_frontmatter_body(text)
    try:
        data = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError:
        return [], []
    evidence = data.get("evidence") or {}
    return (
        [str(value) for value in evidence.get("claims", []) if value],
        [str(value) for value in evidence.get("apis", []) if value],
    )


def _run_recorded_at(run_root: Path) -> str:
    """Return the immutable run timestamp when a manifest is available."""
    manifest_path = run_root / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            created_at = manifest.get("created_at")
            if isinstance(created_at, str) and created_at:
                return created_at
        except (OSError, json.JSONDecodeError):
            pass
    return datetime.now(timezone.utc).isoformat()


def _validated_run_scope(
    run_root: Path,
    *,
    run_id: str,
    family: str,
    platform: str,
) -> dict:
    """Load a pinned run scope only when its manifest binding is intact.

    Writers call this immediately before selecting pages.  This closes the
    mutation-time gap where a locally edited scope.json could otherwise broaden
    a run after PLANNED but before final verification.
    """
    manifest_path = run_root / "manifest.json"
    scope_path = run_root / "scope.json"
    if not manifest_path.is_file() or not scope_path.is_file():
        raise ValueError("run manifest and pinned scope.json are required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scope_bytes = scope_path.read_bytes()
    scope = json.loads(scope_bytes.decode("utf-8"))
    actual_scope_digest = "sha256:" + hashlib.sha256(scope_bytes).hexdigest()
    expected_file_digest = (manifest.get("output_digests") or {}).get("scope")
    manifest_scope = manifest.get("scope") or {}
    paths = scope.get("paths")
    logical_payload = json.dumps(
        {
            "paths": sorted(paths if isinstance(paths, list) else []),
            "input_digest": manifest_scope.get("input_digest"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    logical_digest = "sha256:" + hashlib.sha256(logical_payload).hexdigest()
    if (
        manifest.get("run_id") != run_id
        or manifest.get("family") != family
        or manifest.get("platform") != platform
        or scope.get("run_id") != run_id
        or scope.get("family") != family
        or scope.get("platform") != platform
        or not isinstance(paths, list)
        or paths != manifest_scope.get("paths")
        or actual_scope_digest != expected_file_digest
        or logical_digest != manifest_scope.get("digest")
    ):
        raise ValueError("run scope does not match its pinned manifest contract")
    unsafe_paths = [
        value
        for value in paths
        if Path(str(value)).is_absolute() or ".." in Path(str(value)).parts
    ]
    if unsafe_paths and _cfg_safe_write_fn is None:
        raise ValueError(f"run scope contains unsafe content paths: {unsafe_paths[:3]}")
    return scope


def _existing_run_receipts(run_root: Path, run_id: str) -> dict[str, dict]:
    """Return validated, same-run receipts keyed by canonical page path."""
    from lib.schema_validators import validate_page_patch_receipt

    rows: dict[str, dict] = {}
    for path in sorted((run_root / "receipts").glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        receipt = document.get("content_refresh_receipt") or {}
        errors = validate_page_patch_receipt(receipt)
        if errors or receipt.get("run_id") != run_id:
            raise ValueError(f"invalid existing run receipt {path.name}: {errors}")
        page_path = Path(str(receipt.get("page_path", ""))).as_posix()
        if page_path in rows and rows[page_path] != receipt:
            raise ValueError(f"duplicate run receipt ownership for {page_path}")
        rows[page_path] = receipt
    return rows


def _emit_run_decision(
    *,
    run_root: Path,
    receipt: dict,
    receipt_path: Path,
    receipt_digest: str,
    old_content: str,
    new_content: str,
    impact: dict,
    intended_action: str = "BODY_UPDATE",
    disposition: str = "BODY_UPDATED",
) -> None:
    """Append one validated run-scoped page decision without overwriting rows."""
    from lib.schema_validators import validate_refresh_page_decision

    before = _normalized_body_hash(old_content)
    after = _normalized_body_hash(new_content)
    page_claims, page_apis = _frontmatter_evidence_ids(new_content)
    try:
        receipt_ref = receipt_path.relative_to(run_root).as_posix()
    except ValueError:
        # Tests and compatibility callers may configure a separate receipt root.
        # Never persist an absolute workstation path in the run decision.
        receipt_ref = f"receipts/{receipt_path.name}"
    row = {
        "schema_version": 1,
        "run_id": receipt["run_id"],
        "page_path": receipt["page_path"],
        "surface": receipt.get("surface", _surface_for_page(receipt["page_path"])),
        "locale": receipt.get("locale", "en"),
        "intended_action": intended_action,
        "disposition": disposition,
        "body_hash_before": before,
        "body_hash_after": after,
        "frontmatter_hash_before": _frontmatter_hash(old_content),
        "frontmatter_hash_after": _frontmatter_hash(new_content),
        "receipt_ref": receipt_ref,
        "receipt_digest": receipt_digest,
        "evidence_claims_checked": (
            impact.get("evidence_claims_checked") or page_claims
        ),
        "evidence_apis_checked": (
            impact.get("evidence_apis_checked") or page_apis
        ),
        "validator_results": {
            "receipt": "PASS",
            "forbidden_claims": (
                "PASS"
                if receipt.get("forbidden_claims_scan", {}).get("ok") is True
                else "UNKNOWN"
            ),
            "regrounding": (
                "FAIL"
                if receipt.get("regrounding_violations")
                else "PASS"
                if receipt.get("regrounding_scan", {}).get("ok") is True
                else "UNKNOWN"
            ),
        },
        "recorded_at": receipt["generated_at"],
    }
    errors = validate_refresh_page_decision(row)
    if errors:
        raise ValueError(
            f"Refusing to write invalid page decision for {receipt['page_path']}: {errors}"
        )

    decisions_path = run_root / "page_decisions.jsonl"
    existing_rows: list[dict] = []
    if decisions_path.is_file():
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing_rows.append(json.loads(line))
    matching = [
        prior
        for prior in existing_rows
        if prior.get("run_id") == row["run_id"]
        and prior.get("page_path") == row["page_path"]
    ]
    if matching:
        if matching[-1] != row:
            raise FileExistsError(
                f"Page decision collision for {row['run_id']} {row['page_path']}"
            )
        return
    rendered = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
        for item in [*existing_rows, row]
    )
    atomic_write(decisions_path, rendered)


# ── Run entry point ────────────────────────────────────────────────────────

def run(
    family: str,
    platform: str,
    *,
    dry_run: bool = True,
    execute: bool = False,
    page_filter: str | None = None,
    force_llm_regen: bool = False,
    run_id: str | None = None,
    run_root: "str | Path | None" = None,
) -> list[dict]:
    """
    Main logic entry point (importable by tests and CLI).

    Returns list of receipt dicts (one per page processed).
    """
    if execute and not run_id:
        raise ValueError("execute=True requires an explicit run_id")
    explicit_run_root = run_root is not None
    resolved_run_root = Path(run_root) if run_root is not None else (
        Path("reports") / "refresh_runs" / family / platform / str(run_id)
        if run_id
        else None
    )
    run_product_root = (
        resolved_run_root / "planning" / family / platform
        if resolved_run_root is not None
        else None
    )
    if (
        run_product_root is not None
        and not (run_product_root / "body_impact.json").is_file()
    ):
        run_product_root = None
    impacts = _load_body_impact(
        family, platform, product_root=run_product_root
    )
    existing_run_receipts: dict[str, dict] = {}
    if explicit_run_root and resolved_run_root is not None:
        if not run_id:
            raise ValueError("an explicit run_root requires run_id")
        scope_data = _validated_run_scope(
            resolved_run_root,
            run_id=run_id,
            family=family,
            platform=platform,
        )
        scoped_paths = {
            Path(str(value)).as_posix()
            for value in scope_data.get("paths", [])
        }
        impacts = [
            impact
            for impact in impacts
            if Path(str(impact.get("page_path", ""))).as_posix()
            in scoped_paths
        ]
        existing_run_receipts = _existing_run_receipts(
            resolved_run_root, run_id
        )

    # SEO-BODY-REFRESH-ORDER-BY-TRAFFIC: order-only reprioritization -- the
    # set of impacts processed is completely unchanged above this point;
    # this only changes the ORDER in which the loop below visits them.
    _traffic_tiers = _load_traffic_tiers(family, platform, product_root=run_product_root)
    if _traffic_tiers:
        impacts = _sort_impacts_by_traffic_tier(impacts, _traffic_tiers)

    changes_by_id = _load_semantic_changes(
        family, platform, product_root=run_product_root
    )
    context = {"family": family, "platform": platform}
    receipts: list[dict] = []
    effective_run_id = run_id or f"dry-run-{family}-{platform}"

    # HARDEN-A4: run-scoped LLM output cache for PARAGRAPH_REWRITE. Lives under
    # the configured reports root, so tests/sandboxes are hermetic automatically.
    try:
        from lib.llm_output_cache import LLMOutputCache
        context["_llm_cache"] = LLMOutputCache(
            family, platform, "body_refresh",
            reports_root=Path(_cfg_reports_root),
            enabled=not force_llm_regen,
        )
        if force_llm_regen:
            print(f"LLM_CACHE_BYPASSED: forced fresh rewrites for {family}/{platform} "
                  f"(cache reads disabled; fresh RG-010-passing outputs still stored)")
    except Exception as exc:  # pragma: no cover — lib always importable
        print(f"WARNING: LLM output cache unavailable (non-fatal): {exc}")
        context["_llm_cache"] = None

    # RPR-E-03: per-run re-grounding cache, shared across every page in this run,
    # so a distinctive code/claim span reused verbatim on a later page (without
    # that page sharing the originating page's grounding) is caught.
    try:
        from lib.regrounding_check import RegroundingCache
        _regrounding_cache = RegroundingCache()
        _regrounding_init_error = ""
    except Exception as exc:  # pragma: no cover — defensive dependency boundary
        _regrounding_cache = None
        _regrounding_init_error = f"{type(exc).__name__}: {exc}"

    # RPR-E-05: one circuit per run, shared across all pages via context.
    _llm_circuit = _LLMCircuit()
    context["_llm_circuit"] = _llm_circuit

    for source_impact in impacts:
        impact = dict(source_impact)
        page_path = Path(str(impact.get("page_path", ""))).as_posix()
        existing_receipt = existing_run_receipts.get(page_path)
        if execute and existing_receipt and Path(page_path).is_file():
            current_digest = _file_sha256(Path(page_path))
            if current_digest == existing_receipt.get("new_hash"):
                # A prior attempt completed this page and crashed later.  Its
                # immutable receipt/decision remain authoritative; do not
                # generate a second identity or rewrite the page.
                receipts.append(existing_receipt)
                continue
        if not page_path:
            continue
        impact["page_path"] = page_path
        if page_filter and page_path != page_filter:
            continue

        target_allowed, target_locale, target_reason = _target_locale_verdict(page_path, family, platform)
        if not target_allowed:
            receipts.append({
                "receipt_id": f"RCP-{family}-{platform}-{len(receipts)+1:04d}",
                "run_id": effective_run_id,
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
                "run_id": effective_run_id,
                "page_path": page_path,
                "verdict": VD_NO_SECTIONS,
            })
            continue

        # Check auto_updatable
        if not _is_auto_updatable(page_path):
            receipts.append({
                "receipt_id": f"RCP-{family}-{platform}-{len(receipts)+1:04d}",
                "run_id": effective_run_id,
                "page_path": page_path,
                "verdict": VD_SKIPPED_AUTO,
            })
            continue

        # Dry run — just plan
        if dry_run and not execute:
            receipts.append({
                "receipt_id": f"RCP-{family}-{platform}-{len(receipts)+1:04d}",
                "run_id": effective_run_id,
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
        surface_deferrals: list[dict] = []
        surface = _surface_for_page(page_path)  # RPR-E-04
        page_fallback_reason = "NONE"  # RPR-E-05: worst fallback reason seen on this page

        for sec in actionable_sections:
            sec_id = sec.get("section_id", "")
            if sec_id in _PROTECTED_SECTION_IDS:
                sections_preserved.append(sec_id)
                continue

            # RPR-E-04: enforce the per-surface strategy policy BEFORE applying.
            # A strategy disallowed for this surface (e.g. an LLM PARAGRAPH_REWRITE
            # on a reference page, which must be regenerated by batch-reference) is
            # deferred to its explicit handoff target, never silently applied.
            sec_update_type = sec.get("update_type", "")
            allowed, handoff = _surface_allows_strategy(surface, sec_update_type)
            if not allowed:
                surface_deferrals.append({
                    "section_id": sec_id,
                    "surface": surface,
                    "strategy": sec_update_type,
                    "handoff": handoff,
                })
                sections_preserved.append(f"{sec_id}[SURFACE_DEFER:{surface}->{handoff}]")
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
                context.pop("_fallback_reason", None)  # RPR-E-05: reset per section-change
                updated, strategy = _apply_section_update(new_content, sec, change, context)
                # RPR-E-05: capture the LLM fallback reason (set by _paragraph_rewrite
                # when a PARAGRAPH_REWRITE ran). Keep the most informative one per page —
                # any real fallback reason outranks NONE.
                sec_reason = context.get("_fallback_reason")
                if sec_reason and sec_reason != "NONE" and page_fallback_reason == "NONE":
                    page_fallback_reason = sec_reason
                if updated != new_content:
                    new_content = updated
                    strategies_used.append(strategy)
                    sections_changed.append(sec_id)
                    break  # one change per section per pass

        new_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
        verdict = VD_NO_SECTIONS
        forbidden_violations: list[dict] = []
        regrounding_violations: list[dict] = []
        forbidden_scan_ok = True
        forbidden_scan_error = ""
        regrounding_scan_ok = new_content == old_content
        regrounding_scan_error = (
            "" if regrounding_scan_ok else _regrounding_init_error
        )

        if new_content != old_content:
            # RPR-E-02: generation-time forbidden-claims gate. If this edit
            # INTRODUCES an affirmative claim about a forbidden API (one whose
            # methods throw NotImplementedException), refuse to write the
            # candidate — preserve the original content and surface the violation.
            # This is the pre-write enforcement absent when 3d/net's "3MF"
            # fabrication landed across 13 files (plan §2.4). Only newly-introduced
            # violations block; a pre-existing one this edit didn't touch is a
            # separate remediation concern, not a reason to abort this edit.
            forbidden_violations, forbidden_scan_ok, forbidden_scan_error = \
                _scan_forbidden_claims(old_content, new_content, family, platform)
            if _regrounding_cache is not None:
                try:
                    rg = _regrounding_cache.check_page(
                        page_path, new_content, _read_cited_evidence(old_content))
                    regrounding_violations = [v.to_dict() for v in rg]
                    regrounding_scan_ok = True
                    regrounding_scan_error = ""
                except Exception as exc:  # noqa: BLE001 — evidence records UNKNOWN
                    regrounding_scan_ok = False
                    regrounding_scan_error = f"{type(exc).__name__}: {exc}"
                    print(f"WARNING: re-grounding check failed: {exc}")
            if forbidden_violations:
                verdict = VD_FORBIDDEN_BLOCKED
                print(
                    f"FORBIDDEN_CLAIM_BLOCKED: {page_path} — candidate introduced "
                    f"{len(forbidden_violations)} forbidden-claim violation(s): "
                    f"{[v['matched_symbol'] for v in forbidden_violations][:3]}; "
                    f"original content preserved, routed for review"
                )
                new_content = old_content  # do not write the violating candidate
                new_hash = old_hash.replace("sha256:", "")
            elif regrounding_violations:
                verdict = VD_REGROUNDING_BLOCKED
                print(
                    f"TEMPLATE_PROPAGATION_BLOCKED: {page_path} — candidate reused "
                    f"{len(regrounding_violations)} distinctive span(s) first seen on "
                    f"{regrounding_violations[0]['first_page']} without shared grounding; "
                    f"original content preserved, routed for fresh generation"
                )
                new_content = old_content  # do not propagate the ungrounded reuse
                new_hash = old_hash.replace("sha256:", "")
            else:
                # The receipt and page decision are emitted before the content
                # mutation below.  A crash can therefore be resumed or
                # hash-gated-recovered without an unowned working-tree write.
                verdict = VD_UPDATED
        else:
            verdict = VD_NO_SECTIONS

        strategy_used = (
            UT_REWRITE if UT_REWRITE in strategies_used
            else strategies_used[0] if strategies_used
            else UT_SURGICAL
        )
        staged_path: Path | None = None
        if verdict == VD_UPDATED:
            if resolved_run_root is None:
                raise ValueError("run_root could not be resolved")
            relative_page = Path(page_path)
            if relative_page.is_absolute() or ".." in relative_page.parts:
                if _cfg_safe_write_fn is None:
                    raise ValueError(f"unsafe scoped page path: {page_path}")
                relative_page = (
                    Path("test-fixture")
                    / f"{hashlib.sha256(page_path.encode('utf-8')).hexdigest()}.md"
                )
            staged_path = resolved_run_root / "staging" / relative_page
            atomic_write(staged_path, new_content)
            staged_bytes = staged_path.read_bytes()
            receipt_new_hash = (
                "sha256:" + hashlib.sha256(staged_bytes).hexdigest()
            )
        else:
            receipt_new_hash = old_hash
        receipt_seed = (
            f"{effective_run_id}\0{page_path}\0{old_hash}\0{receipt_new_hash}"
        ).encode("utf-8")
        receipt_data = {
            "receipt_id": f"RCP-{hashlib.sha256(receipt_seed).hexdigest()[:20]}",
            "run_id": effective_run_id,
            "page_path": page_path,
            "locale": impact.get("locale", "en"),
            "change_ids": impact.get("semantic_change_ids", []),
            "semantic_change_ids": impact.get("semantic_change_ids", []),
            "strategy_used": strategy_used,
            "body_sections_changed": sections_changed,
            "preserved_sections": sections_preserved,
            "old_hash": old_hash,
            "new_hash": receipt_new_hash,
            "verdict": verdict,
            "strategies_used": strategies_used,
            "forbidden_violations": forbidden_violations,
            "forbidden_claims_scan": {"ok": forbidden_scan_ok, "error": forbidden_scan_error},
            "regrounding_violations": regrounding_violations,
            "regrounding_scan": {
                "ok": regrounding_scan_ok,
                "error": regrounding_scan_error,
            },
            "surface": surface,
            "surface_deferrals": surface_deferrals,
            "fallback_reason": page_fallback_reason,
            "llm_invoked": (
                strategy_used == UT_REWRITE and page_fallback_reason == "NONE"
            ),
            "template_fallback_used": (
                strategy_used == UT_REWRITE and page_fallback_reason != "NONE"
            ),
            "generated_at": (
                _run_recorded_at(resolved_run_root)
                if resolved_run_root is not None
                else datetime.now(timezone.utc).isoformat()
            ),
        }
        receipts.append(receipt_data)

        if execute:
            if resolved_run_root is None:  # defensive; execute already requires run_id
                raise ValueError("run_root could not be resolved")
            receipt_path, receipt_digest = _emit_receipt(
                receipt_data,
                family,
                platform,
                run_root=resolved_run_root,
            )
            _emit_run_decision(
                run_root=resolved_run_root,
                receipt=receipt_data,
                receipt_path=receipt_path,
                receipt_digest=receipt_digest,
                old_content=old_content,
                new_content=new_content,
                impact=impact,
                disposition=(
                    "BODY_UPDATED"
                    if verdict == VD_UPDATED
                    else "NOT_AFFECTED"
                    if verdict == VD_NO_SECTIONS
                    else "SKIPPED"
                    if verdict in {VD_SKIPPED_AUTO, VD_SKIPPED_HASH}
                    else "BLOCKED"
                ),
            )
            if verdict == VD_UPDATED:
                written = _write_page(page_path, new_content, family, platform)
                if not written:
                    raise RuntimeError(
                        f"validated write was refused for {page_path}"
                    )
                if (
                    _cfg_safe_write_fn is None
                    and _file_sha256(Path(page_path)) != receipt_new_hash
                ):
                    raise RuntimeError(
                        f"content write hash mismatch for {page_path}"
                    )
                _record_body_refresh_write(page_path, effective_run_id)

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
  PYTHONPATH=scripts/pipeline python -m commands.content.body_refresh pdf net \\
      --execute --run-id ID --run-root reports/refresh_runs/pdf/net/ID

  # Execute single page:
  PYTHONPATH=scripts/pipeline python -m commands.content.body_refresh pdf net \\
      --execute --run-id ID --run-root reports/refresh_runs/pdf/net/ID \\
      --page content/docs.aspose.org/en/pdf/net/getting-started/installation.md

Update strategies: SURGICAL_CLAIM_REPLACEMENT | TABLE_ROW_RECONCILIATION |
                   EXAMPLE_REGENERATION | SECTION_REMOVAL | PARAGRAPH_REWRITE
        """,
    )
    parser.add_argument("family", help="Product family (e.g. pdf, 3d)")
    parser.add_argument("platform", help="Platform (e.g. net, java)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Plan only; no writes")
    parser.add_argument("--execute", action="store_true", default=False, help="Apply all body updates")
    parser.add_argument("--page", default=None, help="Restrict to single page path")
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run-bound refresh ID; required with --execute",
    )
    parser.add_argument(
        "--run-root",
        default=None,
        help="Run artifact directory (default: reports/refresh_runs/{family}/{platform}/{run_id})",
    )
    parser.add_argument("--no-llm-cache", action="store_true", dest="no_llm_cache",
                        help="HARDEN-A4: bypass the content-hash LLM rewrite cache and force "
                             "fresh LLM calls (loudly logged; fresh outputs still refresh the cache)")
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
            force_llm_regen=args.no_llm_cache,
            run_id=args.run_id,
            run_root=args.run_root,
        )
    except (FileNotFoundError, ValueError, FileExistsError) as e:
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
