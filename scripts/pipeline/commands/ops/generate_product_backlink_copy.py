#!/usr/bin/env python3
# Adapted from aspose.org
"""generate_product_backlink_copy.py — LLM-driven products overview backlink copy generator.

Generates a natural contextual aspose.com backlink sentence for insertion into
products.aspose.org overview.content fields. Uses LLMRouter (professionalize → Ollama
fallback) with deterministic caching so second runs are 100% cache hits.

Implements TC-BL-LLM-COPY-001 through TC-BL-LLM-COPY-004 per §S of
cuddly-pondering-whisper v5.0 canonical execution plan.

Usage (library):
    from generate_product_backlink_copy import generate_copy, BacklinkCopyRequest

Usage (CLI):
    python scripts/pipeline/commands/ops/generate_product_backlink_copy.py \\
        --family words --platform python \\
        --output reports/backlinks/products_llm_copy_generation.json

Exit codes:
    0   All pages processed (even if fallback was used)
    1   Fatal error (no products content found, metrics unavailable in live mode)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(os.environ.get("FOSS_REPO_ROOT", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))

log = logging.getLogger(__name__)

SCRIPT_VERSION = "1.0.0"
PROMPT_VERSION = "v1.0"
CALLSITE_ID = "CS-010"

# ──────────────────────────────────────────────────────────────────────────────
# Dataclasses (§S.1 / §L.3)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class BacklinkCopyRequest:
    file_path: str                # repo-relative
    family: str                   # "words"
    platform: str | None          # "python" or None (family page)
    product_display_name: str     # "Aspose.Words for Python"
    resolved_target_url: str      # "https://products.aspose.com/words/python/"
    current_overview_content: str # raw overview.content text
    page_type: str                # "plugin" | "family"
    max_allowed_com_links: int    # always 1 for overview (CTA counted separately)
    support_cta_expected: bool    # True if supportandlearning.enable: true
    prompt_version: str = PROMPT_VERSION


@dataclass
class CopyGenerationRecord:
    file_path: str
    cache_hit: bool
    model_used: str | None
    prompt_version: str
    input_hash: str          # SHA-256 of overview_content
    prompt_hash: str         # SHA-256 of rendered prompt
    response_hash: str       # SHA-256 of LLM response
    output_hash: str         # SHA-256 of accepted output
    output_text: str | None  # final accepted overview.content (None on failure)
    validation_pass: bool
    retry_count: int         # 0 or 1
    fallback_used: bool
    fallback_template: str | None
    fallback_reason: str | None
    token_count_input: int | None
    token_count_output: int | None
    before_snippet: str      # first 200 chars of original
    after_snippet: str       # first 200 chars of output
    rejected_outputs: list[str] = field(default_factory=list)
    error: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# System prompt (§S.3 — v1.0)
# ──────────────────────────────────────────────────────────────────────────────

def build_system_prompt(resolved_target_url: str) -> str:
    return f"""You are a technical copywriter for an open-source developer library.
Your task is to insert exactly one natural Markdown hyperlink into the provided product overview text.
The link must point to the commercial counterpart of the open-source library.

Rules:
- Insert exactly one Markdown link: [anchor text](target URL)
- Target URL must be exactly: {resolved_target_url}
- Place the link near the end of the overview, before the final sentence mentioning MIT license or GitHub.
- Anchor text must identify the commercial product naturally (e.g., "Aspose.Words for Python", "Aspose.Cells commercial edition").
- Do not add hype, "buy now", "click here", "best", "ultimate", or sales language.
- Do not duplicate any sentence.
- Preserve all existing text, including MIT license statements and GitHub references.
- Do not make claims not present in the original text.
- Return only the revised overview.content text. No explanation, no YAML, no markdown fences.
- If the text already contains an aspose.com link, return the original unchanged."""


def build_repair_prompt(reason: str) -> str:
    return (
        f"The previous output failed validation. Fix: {reason}. "
        f"Return only the corrected text. Same rules apply."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Cache (§S.3)
# ──────────────────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_cache_key(req: BacklinkCopyRequest, model_name: str) -> str:
    """Build deterministic cache key per §S.3."""
    overview_hash = _sha256(req.current_overview_content)
    raw = "|".join([
        req.file_path,
        overview_hash,
        req.resolved_target_url,
        req.family,
        req.platform or "",
        req.prompt_version,
        model_name,
        SCRIPT_VERSION,
    ])
    return _sha256(raw)


def cache_path(cache_dir: Path, cache_key: str) -> Path:
    prefix = cache_key[:8]
    return cache_dir / prefix / f"{cache_key}.json"


def load_cache_entry(cache_dir: Path, cache_key: str) -> dict | None:
    p = cache_path(cache_dir, cache_key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("validation_passed") and data.get("output_text"):
            return data
    except Exception:
        pass
    return None


def save_cache_entry(cache_dir: Path, cache_key: str, entry: dict) -> None:
    p = cache_path(cache_dir, cache_key)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Sanitize: remove any raw prompts / API keys from cache
    sanitized = {k: v for k, v in entry.items()
                 if k not in ("raw_prompt", "raw_response", "api_key")}
    p.write_text(json.dumps(sanitized, indent=2, ensure_ascii=False), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# Validation (§S.4 — 10 rules)
# ──────────────────────────────────────────────────────────────────────────────

_FORBIDDEN_PHRASES = ["buy now", "click here", "full-featured commercial edition"]
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
_ASPOSE_COM_URL_RE = re.compile(r'https?://[a-z0-9-]+\.aspose\.com/[^\s\)]*', re.IGNORECASE)


def validate_output(original: str, output: str, target_url: str) -> tuple[bool, str]:
    """Validate LLM output per §S.4 rules 1–8. Returns (passed, failure_reason)."""
    if not output or not output.strip():
        return False, "Output is empty"

    # Rule 1: exactly 1 Markdown link
    links = _MD_LINK_RE.findall(output)
    if len(links) != 1:
        return False, f"Expected exactly 1 Markdown link, found {len(links)}"

    # Rule 2: link URL matches target_url exactly
    link_url = links[0][1]
    if link_url.rstrip("/") != target_url.rstrip("/"):
        return False, f"Link URL mismatch: got {link_url!r}, expected {target_url!r}"

    # Rule 3: non-link text retention >= 90%
    stripped_original = _MD_LINK_RE.sub("", original).strip()
    stripped_output = _MD_LINK_RE.sub("", output).strip()
    if len(stripped_original) > 0:
        ratio = len(stripped_output) / len(stripped_original)
        if ratio < 0.90:
            return False, f"Text retention too low: {ratio:.0%} (need ≥90%)"

    # Rule 4: no forbidden phrases
    output_lower = output.lower()
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in output_lower:
            return False, f"Forbidden phrase: '{phrase}'"

    # Rule 5: no duplicate sentences (basic check — exact adjacent sentence)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', output) if s.strip()]
    seen = set()
    for s in sentences:
        if s in seen:
            return False, f"Duplicate sentence: {s[:80]!r}"
        seen.add(s)

    # Rule 6: no broken Markdown (unmatched [ or ()
    if output.count("[") != output.count("]"):
        return False, "Unmatched [ in output"
    if output.count("(") < output.count(")"):
        return False, "Unmatched ) in output"

    # Rule 7: no second aspose.com URL (only the new backlink allowed)
    all_com_urls = _ASPOSE_COM_URL_RE.findall(output)
    unique_com_urls = set(u.rstrip("/") for u in all_com_urls)
    if len(unique_com_urls) > 1:
        return False, f"Multiple aspose.com URLs found: {unique_com_urls}"

    # Rule 8: YAML round-trip (deferred — checked in backfill when writing YAML)
    # We note this as DEFERRED_TO_BACKFILL — not a failure at generation time

    return True, ""


# ──────────────────────────────────────────────────────────────────────────────
# Template fallback (§S.5 — FALLBACK ONLY)
# ──────────────────────────────────────────────────────────────────────────────

def _word_count(text: str) -> int:
    return len(text.split())


def _find_closing_sentence_boundary(text: str) -> int:
    """Find insertion point before the final MIT/GitHub closing sentence.

    Returns the character index where the backlink sentence should be inserted.
    """
    closing_patterns = [
        r'[Ii]t is MIT.?licensed',
        r'[Oo]pen.source on GitHub',
        r'MIT license',
        r'open source',
        r'GitHub',
    ]
    # Find the last sentence containing a closing pattern
    sentences = list(re.finditer(r'[A-Z][^.!?]*[.!?]', text))
    for pattern in closing_patterns:
        for sent in reversed(sentences):
            if re.search(pattern, sent.group()):
                return sent.start()
    # No closing sentence found — append at end
    return len(text.rstrip())


def apply_template_fallback(req: BacklinkCopyRequest) -> tuple[str, str]:
    """Apply template P-1 through P-5. Returns (output_text, template_id)."""
    text = req.current_overview_content
    wc = _word_count(text)
    url = req.resolved_target_url
    display = req.product_display_name  # e.g. "Aspose.Words for Python" or "Aspose.Words"

    if req.page_type == "family":
        # P-3: Family page
        sentence = f"For the complete commercial product family with dedicated support, visit [{display}]({url})."
        template_id = "P-3"
    elif wc <= 140:
        # P-4: Platform page, compact overview
        sentence = f"The commercial counterpart is [{display}]({url})."
        template_id = "P-4"
    else:
        # P-1: Platform page, API bridge (default for long overviews)
        sentence = (
            f"Developers who need the complete commercial API with full production support can use "
            f"[{display}]({url}) alongside these open-source resources."
        )
        template_id = "P-1"

    # Find insertion point (before MIT/GitHub closing sentence)
    text_stripped = text.rstrip()
    insert_at = _find_closing_sentence_boundary(text_stripped)

    if insert_at >= len(text_stripped):
        # Append at end
        output = text_stripped + " " + sentence
    else:
        # Insert before closing sentence
        before = text_stripped[:insert_at].rstrip()
        closing = text_stripped[insert_at:]
        output = before + " " + sentence + " " + closing

    return output, template_id


# ──────────────────────────────────────────────────────────────────────────────
# Core generation logic
# ──────────────────────────────────────────────────────────────────────────────

def generate_copy(
    req: BacklinkCopyRequest,
    cache_dir: Path,
    *,
    dry_run: bool = False,
    force_template: bool = False,
) -> CopyGenerationRecord:
    """Generate overview backlink copy for one products page.

    Tries LLM generation first, falls back to template on failure.
    Always returns a CopyGenerationRecord — never raises.
    """
    input_hash = _sha256(req.current_overview_content)
    before_snippet = req.current_overview_content[:200]

    # Check if page already has an aspose.com link
    existing = _ASPOSE_COM_URL_RE.findall(req.current_overview_content)
    if existing:
        # Already compliant — return unchanged
        return CopyGenerationRecord(
            file_path=req.file_path, cache_hit=True,
            model_used=None, prompt_version=req.prompt_version,
            input_hash=input_hash, prompt_hash="", response_hash="", output_hash=input_hash,
            output_text=req.current_overview_content, validation_pass=True,
            retry_count=0, fallback_used=False, fallback_template=None,
            fallback_reason="Already contains aspose.com link — no change needed",
            token_count_input=None, token_count_output=None,
            before_snippet=before_snippet, after_snippet=before_snippet,
        )

    if force_template or dry_run:
        output, tmpl = apply_template_fallback(req)
        reason = "force_template mode" if force_template else "dry_run mode"
        return CopyGenerationRecord(
            file_path=req.file_path, cache_hit=False,
            model_used=None, prompt_version=req.prompt_version,
            input_hash=input_hash, prompt_hash="", response_hash="",
            output_hash=_sha256(output), output_text=output, validation_pass=True,
            retry_count=0, fallback_used=True, fallback_template=tmpl,
            fallback_reason=reason,
            token_count_input=None, token_count_output=None,
            before_snippet=before_snippet, after_snippet=output[:200],
        )

    # Try to import LLMRouter
    try:
        from commands.ops.llm_router import LLMRouter, EndpointStatus
    except ImportError as exc:
        output, tmpl = apply_template_fallback(req)
        return CopyGenerationRecord(
            file_path=req.file_path, cache_hit=False,
            model_used=None, prompt_version=req.prompt_version,
            input_hash=input_hash, prompt_hash="", response_hash="",
            output_hash=_sha256(output), output_text=output, validation_pass=True,
            retry_count=0, fallback_used=True, fallback_template=tmpl,
            fallback_reason=f"LLMRouter import failed: {exc}",
            token_count_input=None, token_count_output=None,
            before_snippet=before_snippet, after_snippet=output[:200],
        )

    router = LLMRouter()

    # Determine model name for cache key
    try:
        from commands.ops.llm_router import _REGISTRY_PATH
        import yaml as _yaml
        _reg = _yaml.safe_load((_REGISTRY_PATH).read_text(encoding="utf-8"))
        _model = (_reg.get("providers", [{}])[0] or {}).get("model", "gpt-oss")
    except Exception:
        _model = "gpt-oss"

    cache_key = build_cache_key(req, _model)
    system_prompt = build_system_prompt(req.resolved_target_url)
    prompt_hash = _sha256(system_prompt + req.current_overview_content)

    # Check cache
    cached = load_cache_entry(cache_dir, cache_key)
    if cached:
        output = cached["output_text"]
        return CopyGenerationRecord(
            file_path=req.file_path, cache_hit=True,
            model_used=cached.get("model_used"), prompt_version=req.prompt_version,
            input_hash=input_hash, prompt_hash=prompt_hash,
            response_hash=cached.get("response_hash", ""),
            output_hash=_sha256(output), output_text=output, validation_pass=True,
            retry_count=0, fallback_used=False, fallback_template=None,
            fallback_reason=None,
            token_count_input=cached.get("token_count_input"),
            token_count_output=cached.get("token_count_output"),
            before_snippet=before_snippet, after_snippet=output[:200],
        )

    # LLM call
    metrics_events: list = []
    rejected: list[str] = []
    model_used = _model
    response_hash = ""
    token_in: int | None = None
    token_out: int | None = None

    # Attempt 1
    result = router.call_chat(
        system_prompt,
        req.current_overview_content,
        temperature=0.0,
        max_tokens=800,
        json_extract=False,
    )
    metrics_events.extend(result.metrics_events)

    if result.status.value == "ok" and isinstance(result.data, str):
        response_text = result.data.strip()
        response_hash = _sha256(response_text)
        # Extract token counts from first metrics event
        if result.metrics_events:
            ev = result.metrics_events[0]
            token_in = getattr(ev, "prompt_tokens", None)
            token_out = getattr(ev, "completion_tokens", None)

        passed, reason = validate_output(req.current_overview_content, response_text, req.resolved_target_url)
        if passed:
            # Write to cache and return
            cache_entry = {
                "cache_key": cache_key, "created_at": datetime.now(timezone.utc).isoformat(),
                "prompt_version": req.prompt_version, "model_used": model_used,
                "script_version": SCRIPT_VERSION, "output_text": response_text,
                "output_hash": _sha256(response_text), "response_hash": response_hash,
                "validation_passed": True,
                "token_counts": {"input": token_in, "output": token_out},
            }
            save_cache_entry(cache_dir, cache_key, cache_entry)
            _emit_metrics(req, metrics_events)
            return CopyGenerationRecord(
                file_path=req.file_path, cache_hit=False,
                model_used=model_used, prompt_version=req.prompt_version,
                input_hash=input_hash, prompt_hash=prompt_hash,
                response_hash=response_hash, output_hash=_sha256(response_text),
                output_text=response_text, validation_pass=True,
                retry_count=0, fallback_used=False, fallback_template=None, fallback_reason=None,
                token_count_input=token_in, token_count_output=token_out,
                before_snippet=before_snippet, after_snippet=response_text[:200],
            )
        else:
            rejected.append(response_text[:200])
            # Retry with repair prompt
            repair_result = router.call_chat(
                system_prompt,
                req.current_overview_content + "\n\n" + build_repair_prompt(reason),
                temperature=0.0,
                max_tokens=800,
                json_extract=False,
            )
            metrics_events.extend(repair_result.metrics_events)

            if repair_result.status.value == "ok" and isinstance(repair_result.data, str):
                repaired = repair_result.data.strip()
                r_passed, r_reason = validate_output(req.current_overview_content, repaired, req.resolved_target_url)
                if r_passed:
                    cache_entry = {
                        "cache_key": cache_key, "created_at": datetime.now(timezone.utc).isoformat(),
                        "prompt_version": req.prompt_version, "model_used": model_used,
                        "script_version": SCRIPT_VERSION, "output_text": repaired,
                        "output_hash": _sha256(repaired), "response_hash": _sha256(repaired),
                        "validation_passed": True,
                        "token_counts": {"input": token_in, "output": token_out},
                    }
                    save_cache_entry(cache_dir, cache_key, cache_entry)
                    _emit_metrics(req, metrics_events)
                    return CopyGenerationRecord(
                        file_path=req.file_path, cache_hit=False,
                        model_used=model_used, prompt_version=req.prompt_version,
                        input_hash=input_hash, prompt_hash=prompt_hash,
                        response_hash=_sha256(repaired), output_hash=_sha256(repaired),
                        output_text=repaired, validation_pass=True,
                        retry_count=1, fallback_used=False, fallback_template=None, fallback_reason=None,
                        token_count_input=token_in, token_count_output=token_out,
                        before_snippet=before_snippet, after_snippet=repaired[:200],
                        rejected_outputs=rejected,
                    )
                else:
                    rejected.append(repaired[:200])
                    fallback_reason = f"LLM retry failed validation: {r_reason}"
            else:
                fallback_reason = f"LLM retry failed: {repair_result.status.value}"
    else:
        fallback_reason = f"LLM call failed: {result.status.value} — {result.error or ''}"

    # Template fallback
    _emit_metrics(req, metrics_events)
    output, tmpl = apply_template_fallback(req)
    return CopyGenerationRecord(
        file_path=req.file_path, cache_hit=False,
        model_used=model_used, prompt_version=req.prompt_version,
        input_hash=input_hash, prompt_hash=prompt_hash,
        response_hash=response_hash, output_hash=_sha256(output),
        output_text=output, validation_pass=True,
        retry_count=1, fallback_used=True, fallback_template=tmpl,
        fallback_reason=fallback_reason,
        token_count_input=token_in, token_count_output=token_out,
        before_snippet=before_snippet, after_snippet=output[:200],
        rejected_outputs=rejected,
    )


def _emit_metrics(req: BacklinkCopyRequest, events: list) -> None:
    """Emit metrics events via RunMetrics context. Never raises."""
    if not events:
        return
    try:
        from commands.ops.run_metrics import RunMetrics, RunMetricsError
        with RunMetrics(
            run_id=f"backlink-copy-{req.family}-{req.platform or 'family'}",
            agent_name="aspose-backlink-copy-generator",
            job_type="backlink_copy_generation",
            product=req.family,
            platform=req.platform or "",
            website="aspose.org",
            website_section="Products",
            ledger_root=_REPO_ROOT / "reports" / "metrics" / "events",
        ) as rm:
            rm.record_events(events)
    except Exception as exc:
        log.warning("Metrics emission failed (non-fatal): %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# Products page discovery and request building
# ──────────────────────────────────────────────────────────────────────────────

def discover_products_pages(
    repo_root: Path,
    family_filter: str | None = None,
    platform_filter: str | None = None,
) -> list[tuple[Path, str, str | None]]:
    """Discover products.aspose.org plugin and family pages.

    Returns list of (file_path, family, platform_or_None).
    """
    products_root = repo_root / "content" / "products.aspose.org" / "en"
    if not products_root.exists():
        return []

    results = []
    for fpath in sorted(products_root.rglob("_index.md")):
        rel = fpath.relative_to(products_root)
        parts = rel.parts[:-1]  # exclude "_index.md"

        if len(parts) == 0:
            continue  # skip products root _index.md
        if len(parts) == 1:
            family = parts[0]
            platform = None
        elif len(parts) == 2:
            family = parts[0]
            platform = parts[1]
        else:
            continue

        if family_filter and family != family_filter:
            continue
        if platform_filter and platform != platform_filter:
            continue

        results.append((fpath, family, platform))

    return results


def build_request(
    fpath: Path,
    family: str,
    platform: str | None,
    repo_root: Path,
    families_map: dict,
    platforms_map: dict,
    target_map: dict,
) -> BacklinkCopyRequest | None:
    """Build a BacklinkCopyRequest for a products page."""
    try:
        import yaml as _yaml
        raw = fpath.read_text(encoding="utf-8")
        # Products pages are wrapped in --- frontmatter delimiters; strip them
        fm_text = raw
        if raw.startswith("---"):
            end = raw.find("---", 3)
            if end != -1:
                fm_text = raw[3:end]
        data = _yaml.safe_load(fm_text)
        if not isinstance(data, dict):
            return None
        overview_content = (data.get("overview", {}) or {}).get("content", "") or ""
        support_cta = (data.get("supportandlearning", {}) or {}).get("enable", False)
    except Exception as exc:
        log.warning("Cannot parse %s: %s", fpath, exc)
        return None

    # Resolve target
    from lib.backlink_targets import load_target_map, resolve_backlink
    chosen_url, chosen_type, chosen_sd, _ = resolve_backlink(
        family=family,
        platform=platform,
        source_subdomain="products.aspose.org",
        target_map=target_map,
    )
    if not chosen_url:
        log.warning("BLOCKED_TARGET for %s/%s — skipping", family, platform or "")
        return None

    # Build display name
    # FAMILY-ANCHOR rule: when the resolved target is a family URL (chosen_type == "family"),
    # the anchor must NOT include the platform suffix — "Aspose.Font for Python" paired with
    # products.aspose.com/font/ is misleading. Use family-level display name instead.
    # families.json values already include "Aspose." prefix (e.g., "Aspose.Words")
    fam_title = families_map.get(family, f"Aspose.{family.title()}")
    if platform and chosen_type != "family":
        plat_title = platforms_map.get(platform, platform.title())
        display_name = f"{fam_title} for {plat_title}"
    else:
        display_name = fam_title

    return BacklinkCopyRequest(
        file_path=fpath.relative_to(repo_root).as_posix(),
        family=family,
        platform=platform,
        product_display_name=display_name,
        resolved_target_url=chosen_url,
        current_overview_content=overview_content,
        page_type="plugin" if platform else "family",
        max_allowed_com_links=1,
        support_cta_expected=bool(support_cta),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Report generation (TC-BL-LLM-COPY-004)
# ──────────────────────────────────────────────────────────────────────────────

def write_report(
    records: list[CopyGenerationRecord],
    json_out: Path,
    md_out: Path,
) -> None:
    """Write JSON + Markdown generation report."""
    json_out.write_text(
        json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    total = len(records)
    cache_hits = sum(1 for r in records if r.cache_hit)
    fallbacks = sum(1 for r in records if r.fallback_used)
    retries = sum(1 for r in records if r.retry_count > 0)
    already_compliant = sum(1 for r in records if r.fallback_reason == "Already contains aspose.com link — no change needed")

    md_lines = [
        "# Products LLM Copy Generation Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Script:** generate_product_backlink_copy.py v{SCRIPT_VERSION}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Pages processed | {total} |",
        f"| Cache hits | {cache_hits} ({cache_hits/total*100:.0f}% of {total}) |" if total else "| Cache hits | 0 |",
        f"| LLM-generated (passed validation) | {total - fallbacks - cache_hits - already_compliant} |",
        f"| Fallback templates used | {fallbacks} |",
        f"| Retries (repair prompt) | {retries} |",
        f"| Already compliant (skipped) | {already_compliant} |",
        "",
        "## Fallback Details",
        "",
    ]
    for r in records:
        if r.fallback_used:
            md_lines.append(f"- `{r.file_path}` — {r.fallback_template}: {r.fallback_reason}")

    md_lines += ["", "---", ""]
    md_out.write_text("\n".join(md_lines), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Generate LLM copy for products overview backlinks."
    )
    parser.add_argument("--family", help="Restrict to a specific family")
    parser.add_argument("--platform", help="Restrict to a specific platform")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use template fallback (no LLM calls)")
    parser.add_argument("--force-template", action="store_true",
                        help="Force template fallback even if LLM is available")
    parser.add_argument(
        "--output",
        help="Output JSON path (default: reports/backlinks/products_llm_copy_generation.json)",
    )
    args = parser.parse_args()

    repo_root = _REPO_ROOT

    # Load data files
    try:
        import yaml as _yaml
        families_map = json.loads((repo_root / "data" / "families.json").read_text(encoding="utf-8"))
        try:
            platforms_data = _yaml.safe_load(
                (repo_root / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml").read_text(encoding="utf-8")
            )
            raw_plats = platforms_data.get("platforms") or {}
            # Taxonomy stores platforms as {key: "DisplayName"} strings
            platforms_map = {
                k: (v if isinstance(v, str) else v.get("display_name", k.title()))
                for k, v in raw_plats.items()
            }
        except Exception:
            platforms_map = {}
    except Exception as exc:
        log.error("Cannot load data files: %s", exc)
        return 1

    # Load target map
    try:
        from lib.backlink_targets import load_target_map
        target_map = load_target_map(repo_root)
    except Exception as exc:
        log.error("Cannot load target map: %s", exc)
        return 1

    # Set up cache dir
    cache_dir = repo_root / "reports" / "backlinks" / "llm-copy-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Discover pages
    pages = discover_products_pages(repo_root, args.family, args.platform)
    log.info("Found %d products pages to process", len(pages))

    if not pages:
        log.error("No products pages found — check content/products.aspose.org/en/")
        return 1

    # Generate copy for each page
    records: list[CopyGenerationRecord] = []
    for fpath, family, platform in pages:
        req = build_request(fpath, family, platform, repo_root,
                            families_map, platforms_map, target_map)
        if req is None:
            continue

        rec = generate_copy(
            req, cache_dir,
            dry_run=args.dry_run,
            force_template=args.force_template,
        )
        records.append(rec)
        status = "CACHE" if rec.cache_hit else ("TMPL" if rec.fallback_used else "LLM")
        log.info("[%s] %s", status, rec.file_path)

    # Write report
    reports_dir = repo_root / "reports" / "backlinks"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if args.output:
        json_out = Path(args.output)
        md_out = json_out.with_suffix(".md")
    else:
        json_out = reports_dir / "products_llm_copy_generation.json"
        md_out = reports_dir / "products_llm_copy_generation_report.md"

    write_report(records, json_out, md_out)

    cache_hits = sum(1 for r in records if r.cache_hit)
    fallbacks = sum(1 for r in records if r.fallback_used)
    log.info("Done: %d pages, %d cache hits, %d fallbacks", len(records), cache_hits, fallbacks)
    log.info("JSON: %s", json_out)
    log.info("MD:   %s", md_out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
