import argparse
import datetime
import json
import logging
import os
import sys
import time
import yaml
from collections import deque
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
from core.env_loader import load_env  # noqa: E402
load_env()

_SEO_SCRIPTS = Path(__file__).resolve().parent
if str(_SEO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SEO_SCRIPTS))
try:
    from seo.pipeline.schema import canonical_families
except ImportError:
    from pipeline.schema import canonical_families

try:
    from seo.pipeline import autonomy_state
except ImportError:
    from pipeline import autonomy_state

try:
    from seo import llm_metrics_adapter
except ImportError:
    import llm_metrics_adapter

# SEO-LLM-METRICS-UNIFY (Finding #59): distinguishes get_keywords.py's own
# direct runs from migrate_platform_labels.py's calls through this same
# function in the shared metrics ledger, without changing
# get_keywords_from_gemini()'s call signature (many existing tests monkeypatch
# it with a narrow (title, platform="net") lambda; a new required/positional
# parameter would break every one of them). migrate_platform_labels.py calls
# set_metrics_consumer_id() once near the top of its own entry point instead.
_metrics_consumer_id = "get_keywords"


def set_metrics_consumer_id(consumer_id: str) -> str:
    """Set the consumer_id tag used for Gemini metrics events emitted by
    get_keywords_from_gemini() for the rest of this process. Returns the
    previous value."""
    global _metrics_consumer_id
    previous = _metrics_consumer_id
    _metrics_consumer_id = consumer_id
    return previous


def _emit_gemini_metrics(*args, **kwargs) -> None:
    """AGENTS.md §15: "Metrics failures must never crash or block the parent
    pipeline job" -- record_gemini_call() already never raises internally,
    but this call-site wrapper is the defense-in-depth layer for the case
    that contract is ever violated (a broken monkeypatch, a future refactor),
    so a metrics failure can never propagate into keyword generation."""
    try:
        llm_metrics_adapter.record_gemini_call(*args, **kwargs)
    except Exception:
        logging.debug("get_keywords: metrics recording failed", exc_info=True)

# google.generativeai is imported lazily, inside get_keywords_from_gemini(),
# not at module load time. This is an optional, heavy dependency ("Install
# only when SEO features are needed" per scripts/seo/requirements.txt) --
# importing it eagerly meant this module (and its DEFAULT_FAMILIES / dedup
# logic) could never be unit-tested or even imported without it installed.

# Single source of truth for "which families exist": data/family_descriptions.json,
# the same registry 4 Hugo home templates already treat as authoritative. This
# used to be a hardcoded 18-name list that had drifted from review_keywords.py's
# 13 and validate.py's 14 (Finding #32) -- all three now derive from one place.
# Falls back to the pre-fix 18-name list only if the registry can't be read at
# all (e.g. a corrupted checkout), so a missing/broken registry degrades to the
# old behavior instead of silently processing zero families.
_FALLBACK_FAMILIES = [
    "barcode", "cells", "html", "imaging", "ocr", "page", "pdf", "psd", "tasks", "tex", "words", "zip",
    "3d", "cad", "diagram", "email", "note", "slides",
]
DEFAULT_FAMILIES = canonical_families() or _FALLBACK_FAMILIES


# Extract head_title from Markdown file
def extract_head_title(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
        if content.startswith('---'):
            end = content.find('---', 3)
            if end != -1:
                front_matter = content[3:end]
                data = yaml.safe_load(front_matter)
                return data.get('title')
    return None


def _extract_platform_from_path(file_path, family_dir):
    """Derive the real platform from a file's path within its family
    directory, instead of trusting a single CLI-wide --platform flag for
    every file regardless of its actual platform (Finding #50). Content is
    laid out as {family_dir}/{platform}/... consistently across all 3 sites
    (docs/kb/products.aspose.org), confirmed directly against real content
    (cpp, go, java, net, python, rust, typescript). A file directly at
    {family_dir}/_index.md, or any file with no platform subdirectory, is
    inherently cross-platform: returns None so the caller uses
    platform-neutral prompt framing instead of defaulting to one platform.
    """
    rel_parts = Path(file_path).resolve().relative_to(Path(family_dir).resolve()).parts
    if len(rel_parts) <= 1:
        return None
    return rel_parts[0]


def rotate_families_by_iso_week(families, today=None):
    """Rotate family processing order by ISO week number so a fixed
    per-run call budget (--max-calls) doesn't always prioritize the same
    early families, starving later ones over many weekly runs (see
    SEO-SCHEMA-A-WORKFLOW-UPDATE). Deterministic given the same date --
    every run in the same ISO week produces the same order.
    """
    families = list(families)
    if not families:
        return families
    today = today or datetime.date.today()
    iso_week = today.isocalendar()[1]
    rotated = deque(families)
    rotated.rotate(-(iso_week % len(families)))
    return list(rotated)


def _find_entry(data, source_path, title):
    """Find an existing entry for this page by stable identity.

    Matches on `sourcePath` first (the file's repo-relative path -- stable
    across title renames), falling back to exact `pageTitle` match only for
    legacy entries that predate the sourcePath field. Matching on title alone
    was the root cause of Finding #32's orphaned-entry class of bug: when a
    page's head_title changed, the old title stayed in the JSON forever (no
    sourcePath to recognize it as the same page) while a new entry was
    created for the new title -- entries only ever accumulated, never healed.
    """
    for entry in data:
        if source_path and entry.get("sourcePath") == source_path:
            return entry
    for entry in data:
        if "sourcePath" not in entry and entry.get("pageTitle") == title:
            return entry
    return None


# Check if keywords for a page already exist in the JSON file; returns the
# matching entry (or None). Matches by sourcePath first, pageTitle as a
# legacy fallback -- see _find_entry().
def find_existing_entry(family, source_path, title, output_dir):
    file_path = os.path.join(output_dir, f"{family}.json")
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r', encoding='utf-8') as json_file:
        try:
            data = json.load(json_file)
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {file_path}")
            return None
    return _find_entry(data, source_path, title)


def _merge_title_ready_variants(entry, new_keywords):
    """UNION semantics (matches append_keywords_to_existing's own keyword
    union): if `new_keywords` carries `.title_variants` (a real dual-field
    Gemini call, SEO-SCHEMA-A-DUAL-FIELD-GENERATION), merge them into the
    entry's existing map and mark schema_version 2. A plain list (legacy
    caller, test mock, or a response with no parsed variants) leaves the
    entry untouched -- lazy and additive, never a forced migration.
    """
    variants = getattr(new_keywords, "title_variants", None)
    if not variants:
        return
    merged = dict(entry.get("title_ready_variants") or {})
    merged.update(variants)
    entry["title_ready_variants"] = merged
    entry["schema_version"] = 2


def _replace_title_ready_variants(entry, new_keywords):
    """REPLACE semantics (matches replace_keywords_for_entry's own
    keyword-replace, not union -- Finding #52): the entry's variants become
    exactly what this call produced. If this call produced none (legacy
    caller, test mock, or a response with no parsed variants), drop any
    stale map left over from before -- it no longer corresponds to the
    keywords that now exist on this entry.
    """
    variants = getattr(new_keywords, "title_variants", None)
    if variants:
        entry["title_ready_variants"] = dict(variants)
        entry["schema_version"] = 2
    else:
        entry.pop("title_ready_variants", None)


# Append new keywords to an existing entry, identified by sourcePath (falling
# back to pageTitle for legacy entries). If the page's title has changed
# since the entry was created, the stored pageTitle is updated in place --
# this is what actually stops a rename from producing an orphaned duplicate.
def append_keywords_to_existing(family, source_path, title, new_keywords, output_dir):
    file_path = os.path.join(output_dir, f"{family}.json")
    if not os.path.exists(file_path):
        return
    with open(file_path, 'r', encoding='utf-8') as json_file:
        try:
            data = json.load(json_file)
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {file_path}")
            return
    entry = _find_entry(data, source_path, title)
    if entry is not None:
        existing_keywords = set(entry.get("keywords", []))
        entry["keywords"] = list(existing_keywords.union(new_keywords))
        _merge_title_ready_variants(entry, new_keywords)
        if source_path:
            entry["sourcePath"] = source_path
        if entry.get("pageTitle") != title:
            logging.info(f"Title changed for {source_path}: '{entry.get('pageTitle')}' -> '{title}'")
            entry["pageTitle"] = title
    with open(file_path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4, ensure_ascii=False)
    logging.info(f"Appended keywords for {title} in {family}.json")


# Replace (not union) an existing entry's keywords, identified by sourcePath
# (falling back to pageTitle for legacy entries). Finding #52: --force was
# meant to correct entries whose platform label was wrong, but reusing
# append_keywords_to_existing() for that case unioned the freshly-generated
# (correct) keywords with the existing (contaminated, wrong-platform) ones
# instead of removing them -- producing a permanently mixed-platform list,
# not a correction. Use this instead of append_keywords_to_existing() when
# the goal is to REPLACE a known-wrong keyword set, not to accumulate
# variety across genuine re-runs (title-changed) or repeated LLM calls.
def replace_keywords_for_entry(family, source_path, title, new_keywords, output_dir):
    file_path = os.path.join(output_dir, f"{family}.json")
    if not os.path.exists(file_path):
        return
    with open(file_path, 'r', encoding='utf-8') as json_file:
        try:
            data = json.load(json_file)
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {file_path}")
            return
    entry = _find_entry(data, source_path, title)
    if entry is not None:
        entry["keywords"] = list(new_keywords)
        _replace_title_ready_variants(entry, new_keywords)
        if source_path:
            entry["sourcePath"] = source_path
        entry["pageTitle"] = title
    with open(file_path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4, ensure_ascii=False)
    logging.info(f"Replaced keywords for {title} in {family}.json")


# Save data grouped by family to JSON file
def save_family_to_json(family, data, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{family}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as json_file:
            try:
                existing_data = json.load(json_file)
                data.extend(existing_data)
                data = {json.dumps(entry, sort_keys=True): entry for entry in data}.values()
            except json.JSONDecodeError:
                logging.error(f"Invalid JSON in file: {file_path}")
    with open(file_path, 'w', encoding='utf-8') as json_file:
        json.dump(list(data), json_file, indent=4, ensure_ascii=False)
    logging.info(f"Saved {family} data to {file_path}")


class KeywordsWithVariants(list):
    """A `list[str]` of raw keyword phrases -- behaves exactly like the plain
    list every existing caller (and test) already expects `get_keywords_from_
    gemini()` to return -- that also carries `.title_variants`, a
    `{keyword_phrase: title_ready_variant}` mapping for whichever phrases the
    same Gemini call also produced a natural, Title Case variant for
    (SEO-SCHEMA-A-DUAL-FIELD-GENERATION, Finding #57 Section J). Additive and
    lazy by construction: a plain `list` (every existing test mock, and any
    future caller that doesn't opt into the new prompt format) has no
    `.title_variants` attribute at all, so `getattr(keywords, "title_variants",
    None)` cleanly distinguishes "no variants available" from "variants
    present but empty" without needing an isinstance check at every call site.
    """

    def __init__(self, keywords=(), title_variants=None):
        super().__init__(keywords)
        self.title_variants = title_variants or {}


# Must match validate.py's own _MAX_TITLE_READY_VARIANT_WORDS and the
# generation prompt's own stated "(at most 6 words...)" instruction below --
# the LLM does not reliably honor that instruction on its own (confirmed
# live, SEO-DUAL-FIELD-VARIANT-LENGTH-GATE-RESOLVER-1: 254 real variants
# across keywords/cells.json + keywords/slides.json exceeded it, up to 8
# words), so this is enforced structurally at parse time, not just asked
# for in the prompt.
_MAX_VARIANT_WORDS = 6


def _parse_gemini_keyword_response(keywords_text):
    """Parse Gemini's response into (phrases, title_variants).

    Expected line format: "<keyword phrase>|<Title Ready Variant>" -- the
    same single call now asks for both fields (SEO-SCHEMA-A-DUAL-FIELD-
    GENERATION: no new LLM call, no new cost). Tolerant of a model that drops
    the pipe/variant on a given line: the phrase is still kept, just without
    a variant for that one line, rather than the whole line being discarded --
    a formatting slip on the new, optional half of the response must never
    regress keyword generation itself. The same tolerance now also applies to
    a variant that ignores the prompt's own word-count instruction: dropped
    (never truncated -- truncation risks silently changing a phrase's
    meaning), not the whole phrase (SEO-DUAL-FIELD-VARIANT-LENGTH-GATE-
    RESOLVER-1) -- a missing variant for one phrase is already a normal,
    tolerated outcome of this same function, never a retry-worthy failure.
    """
    phrases = []
    variants = {}
    for line in keywords_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if '|' in line:
            phrase, variant = line.split('|', 1)
            phrase = phrase.strip()
            variant = variant.strip()
            if not phrase:
                continue
            phrases.append(phrase)
            if variant and len(variant.split()) <= _MAX_VARIANT_WORDS:
                variants[phrase] = variant
        else:
            phrases.append(line)
    return phrases, variants


# Free-tier Gemini rate limits are as low as 15 RPM (Google AI Studio free
# tier). Proactively pacing every call keeps us under that ceiling instead of
# relying solely on reactive 429-retry -- fewer 429s, fewer wasted retries,
# and actual behavior now matches the workflow's own documented assumption
# (90-min timeout / ~1,350 calls => ~4s/call).
_RPM_PACING_SECONDS = 4.5
# Retry-on-429 is now bounded with exponential backoff instead of an
# unbounded `while True` -- an exhausted/revoked trial key should fail this
# one call after a few minutes, not spin sleeping for the entire 90-minute
# workflow timeout.
_MAX_429_RETRIES = 5
_BACKOFF_BASE_SECONDS = 60


# Get keywords from Google Gemini using google.generativeai
def get_keywords_from_gemini(page_title, platform="net"):
    import google.generativeai as genai  # lazy: optional heavy dependency

    if platform is None:
        # Family-root pages (Finding #50) have no single real platform --
        # framing the prompt around one anyway is what produced the
        # ".NET platform" mislabeling on non-.NET pages in the first place.
        platform_phrase = "this product"
    else:
        platform_label = {
            "net": ".NET",
            "java": "Java",
            "python": "Python",
            "cpp": "C++",
            "go": "Go",
            "rust": "Rust",
            "typescript": "TypeScript",
            "nodejs": "Node.js",
            "php": "PHP",
        }.get(platform, platform)
        platform_phrase = f"the {platform_label} platform"
    # gemini-1.5-flash was retired (404 as of 2026-07-30, verified against the
    # live API); "-latest" alias tracks Google's current supported flash-lite
    # model without needing another pinned-version update when this one sunsets.
    model = genai.GenerativeModel("gemini-flash-lite-latest")
    prompt = (
        f"Generate a concise list of SEO keywords for the product page titled '{page_title}'. "
        f"Focus on long tail keywords related to {platform_phrase} having medium to high search volume, and low to medium competition. "
        f"For EACH keyword also provide a short, natural, Title Case phrase (at most 6 words, "
        f"same meaning, no invented facts) suitable for use in a page title. "
        f"Output exactly one keyword per line in this format: <keyword phrase>|<Title Case phrase>, "
        f"using a single pipe character as the separator. "
        f"Provide only the keyword lines, with each keyword on a new line, and no additional explanations."
    )
    _metrics_model_name = "gemini-flash-lite-latest"
    for attempt in range(1, _MAX_429_RETRIES + 1):
        _call_start = time.monotonic()
        try:
            response = model.generate_content(prompt)
            _latency_ms = int((time.monotonic() - _call_start) * 1000)
            keywords_text = response.text
            phrases, variants = _parse_gemini_keyword_response(keywords_text)
            _prompt_tokens, _completion_tokens = llm_metrics_adapter.extract_gemini_token_usage(response)
            _emit_gemini_metrics(
                "CS-010", _metrics_consumer_id, "success",
                model=_metrics_model_name, prompt_tokens=_prompt_tokens,
                completion_tokens=_completion_tokens, latency_ms=_latency_ms,
            )
            time.sleep(_RPM_PACING_SECONDS)
            return KeywordsWithVariants(phrases, variants)
        except Exception as e:
            _latency_ms = int((time.monotonic() - _call_start) * 1000)
            if "429" in str(e):  # Check specifically for rate limit error
                if attempt == _MAX_429_RETRIES:
                    logging.error(
                        f"Rate limit still active for page '{page_title}' after "
                        f"{_MAX_429_RETRIES} retries -- giving up on this page "
                        f"(quota may be exhausted, not just rate-limited)."
                    )
                    _emit_gemini_metrics(
                        "CS-010", _metrics_consumer_id, "failure",
                        model=_metrics_model_name, latency_ms=_latency_ms,
                        redacted_error_summary="rate_limit_exhausted",
                    )
                    return None
                backoff = _BACKOFF_BASE_SECONDS * attempt
                logging.warning(
                    f"Rate limit reached (attempt {attempt}/{_MAX_429_RETRIES}), "
                    f"pausing for {backoff}s."
                )
                _emit_gemini_metrics(
                    "CS-010", _metrics_consumer_id, "retry",
                    model=_metrics_model_name, latency_ms=_latency_ms,
                    redacted_error_summary="rate_limited_429",
                )
                time.sleep(backoff)
            else:
                # Not a rate-limit error -- e.g. a retired/renamed model (404),
                # auth failure, or malformed response. Return None (distinct
                # from [] meaning "Gemini genuinely suggested no keywords") so
                # the caller can tell a hard failure apart from a soft empty
                # result and surface a systemic problem loudly instead of
                # silently producing sparse/empty output for an entire run.
                logging.error(f"Error with Gemini API for page '{page_title}': {e}")
                _emit_gemini_metrics(
                    "CS-010", _metrics_consumer_id, "failure",
                    model=_metrics_model_name, latency_ms=_latency_ms,
                    redacted_error_summary=str(e),
                )
                return None
    return None  # unreachable, but explicit


_PLATFORM_LABELS = {
    "net": ".NET",
    "java": "Java",
    "python": "Python",
    "cpp": "C++",
    "go": "Go",
    "rust": "Rust",
    "typescript": "TypeScript",
    "nodejs": "Node.js",
    "php": "PHP",
}

# Default denylist for regenerate_grounded_keywords(): the cross-platform
# vocabulary that has now been found, twice (SEO-SCHEMA-A-GENERATION-
# CONTAMINATION-REMEDIATION, then SEO-SCHEMA-A-BARCODE-CELLS-PLATFORM-
# LICENSE-REMEDIATION), leaking onto non-.NET pages from the original
# Schema A bootstrap generation. Kept broader than the first remediation's
# ad hoc list (which missed "c#"/"windows forms"/"openxml sdk"/etc. and let
# 43 of 51 real cells.json offenders slip past its own re-review) precisely
# because a narrow, hand-picked term list is what let this recur.
_DEFAULT_PLATFORM_BANNED_TERMS = (
    ".net", "c#", "csharp", "vb.net", "asp.net", "dotnet", "winforms",
    "windows forms", "blazor", "datagridview", "gridview", "openxml sdk",
    "rdlc", "codeplex", "maui", "epplus", "closedxml", "ironxl", "syncfusion",
)


def _family_description(family):
    """Best-effort English one-line product description for `family`, read
    from data/family_descriptions.json (the same registry canonical_families()
    already treats as authoritative). Returns "" if unavailable rather than
    raising -- grounding is a quality improvement, not a hard dependency."""
    try:
        raw = json.loads((_REPO_ROOT / "data" / "family_descriptions.json").read_text(encoding="utf-8"))
        return raw.get(family, {}).get("en", "")
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""


def _passes_grounding_gate(phrases, required_terms, banned_terms, min_required_ratio):
    """The hard structural verify-and-retry check generalized from the
    rework fix in SEO-SCHEMA-A-GENERATION-CONTAMINATION-REMEDIATION: zero
    tolerance for any banned term anywhere, plus a minimum fraction of
    phrases carrying at least one required term (e.g. the real platform
    name), never a soft "should be relevant" instruction alone."""
    if not phrases:
        return False
    lowered = [p.lower() for p in phrases]
    for banned in banned_terms:
        if any(banned in p for p in lowered):
            return False
    if required_terms:
        hits = sum(1 for p in lowered if any(req in p for req in required_terms))
        if hits / len(lowered) < min_required_ratio:
            return False
    return True


def regenerate_grounded_keywords(
    page_title, platform, family, *, extra_context="", num_keywords=10,
    required_terms=None, banned_terms=None, min_required_ratio=0.7,
    max_attempts=3,
):
    """Regenerate one Schema A entry's keyword list with explicit product
    and platform grounding, verified against a hard pass/fail gate before
    being accepted (never a single ungated LLM call). Generalizes the ad hoc
    fix built for SEO-SCHEMA-A-GENERATION-CONTAMINATION-REMEDIATION
    (product-grounded prompt + competitor denylist + verify-and-retry) into
    a reusable function, per that card's own disclosed finding that the
    prompt-template gap likely affects any family, not just the two it
    covered.

    `extra_context` carries real, page-specific facts the caller wants
    grounded into the prompt (e.g. the page's actual license terms, to fix
    a misrepresentation defect) -- never invented by this function itself.
    Returns a list[str] of keyword phrases, or None if every attempt fails
    the gate (caller must not fall back to the ungated raw response).
    """
    import google.generativeai as genai  # lazy: optional heavy dependency

    platform_label = _PLATFORM_LABELS.get(platform, platform) if platform else None
    family_desc = _family_description(family)
    banned = list(banned_terms) if banned_terms is not None else list(_DEFAULT_PLATFORM_BANNED_TERMS)
    required = list(required_terms) if required_terms is not None else (
        [platform_label.lower()] if platform_label else []
    )

    grounding = []
    if family_desc:
        grounding.append(f"Product context: {family_desc}")
    if platform_label:
        grounding.append(f"This exact page is about the {platform_label} platform ONLY -- not any other platform.")
    if extra_context:
        grounding.append(extra_context)

    prompt = (
        f"Generate exactly {num_keywords} concise SEO keyword phrases for the product page "
        f"titled '{page_title}'.\n"
        + "\n".join(grounding) + "\n"
        "STRICT RULES:\n"
        "- Every phrase must be genuinely, specifically relevant to the page topic and platform above.\n"
        "- Do not invent facts beyond what is stated above.\n"
        "- Never use any of these words or phrases, in any form: " + ", ".join(banned) + ".\n"
        "Output exactly one keyword phrase per line, no numbering, no bullets, no explanations."
    )

    model = genai.GenerativeModel("gemini-flash-lite-latest")
    for attempt in range(1, max_attempts + 1):
        _call_start = time.monotonic()
        try:
            response = model.generate_content(prompt)
            _latency_ms = int((time.monotonic() - _call_start) * 1000)
            phrases = [line.strip() for line in response.text.split("\n") if line.strip()]
            _prompt_tokens, _completion_tokens = llm_metrics_adapter.extract_gemini_token_usage(response)
            passed = _passes_grounding_gate(phrases, required, banned, min_required_ratio)
            _emit_gemini_metrics(
                "CS-010", _metrics_consumer_id, "success" if passed else "retry",
                model="gemini-flash-lite-latest", prompt_tokens=_prompt_tokens,
                completion_tokens=_completion_tokens, latency_ms=_latency_ms,
            )
            time.sleep(_RPM_PACING_SECONDS)
            if passed:
                return phrases
        except Exception as e:
            _latency_ms = int((time.monotonic() - _call_start) * 1000)
            logging.error(f"regenerate_grounded_keywords: Gemini call failed for '{page_title}' (attempt {attempt}): {e}")
            _emit_gemini_metrics(
                "CS-010", _metrics_consumer_id, "failure",
                model="gemini-flash-lite-latest", latency_ms=_latency_ms,
                redacted_error_summary=str(e),
            )
            time.sleep(_RPM_PACING_SECONDS)
    return None


# Consecutive-failure circuit breaker: found live, 2026-07-31/08-01 --
# without this, a sustained quota exhaustion (not a transient blip) meant
# ~8.5 hours and 48 consecutive pages each burning their full 5-attempt,
# ~10-minute backoff before giving up, one page at a time, with zero
# successes the entire time. Per-page bounded retry (Finding #47) was never
# meant to substitute for a whole-run abort signal -- it bounds the cost of
# ONE page, not the cost of grinding through an entire remaining file list
# under a quota that has evidently not recovered.
_CIRCUIT_BREAKER_CONSECUTIVE_FAILURES = 3


# Process Markdown files grouped by families
def process_markdown_files_by_families(
    families, root_dir, output_dir, platform_override=None, force=False, max_calls=None,
):
    """
    platform_override: forces every file to this platform, bypassing
        per-file path detection (Finding #50's fix). None (default) means
        "detect from each file's real path" -- the normal, correct behavior.
        Kept only for the rare case a caller needs to force one platform.
    force: bypass skip-if-unchanged (Finding #51's fix) -- always call
        Gemini even when an existing entry's title hasn't changed. When this
        is what causes an existing entry to be re-processed (title genuinely
        unchanged), the result REPLACES the entry's keywords (Finding #52 --
        a real rename still unions, exactly as before). Useful for ad hoc
        whole-family re-generation; the persistent migration mechanism (see
        migrate_platform_labels.py / SEO-SCHEMA-A-WORKFLOW-UPDATE's Migration
        Plan v2) is the primary way the 896 already-mislabeled entries get
        corrected in production.
    max_calls: stop cleanly (not a failure) once this many real Gemini
        calls have been made this run, saving progress made so far. A
        proactive budget, independent of the reactive circuit breaker.
    """
    family_data = {}
    call_success_count = 0
    call_failure_count = 0
    consecutive_failures = 0
    calls_made = 0
    circuit_tripped = False
    budget_reached = False

    for family in families:
        if circuit_tripped or budget_reached:
            break
        family_dir = os.path.join(root_dir, family)
        if not os.path.exists(family_dir):
            logging.warning(f"Directory for family '{family}' does not exist: {family_dir}")
            continue

        # SEO-AUTONOMY-STATE-MACHINE (Contract I) read-gate: a family not yet
        # AUTONOMOUSLY_ELIGIBLE for schema_a_refresh is skipped, not silently
        # processed. data/seo_autonomy_state.json seeds every canonical
        # family AUTONOMOUSLY_ELIGIBLE for this specific mechanism at build
        # time, reconciling state with the Mission Contract's own
        # pre-existing, already-operator-authorized blanket authorization
        # for this cron (human_authority_boundaries) -- this gate is not a
        # new restriction on production behavior, it is that authorization
        # made mechanically enforceable instead of merely documented.
        if not autonomy_state.is_autonomously_eligible(family, "schema_a_refresh"):
            status = autonomy_state.get_status(family, "schema_a_refresh")
            logging.warning(
                f"Skipping family '{family}': schema_a_refresh autonomy state is "
                f"{status}, not AUTONOMOUSLY_ELIGIBLE"
            )
            continue

        logging.info(f"Processing family: {family}")
        family_data[family] = []

        for subdir, _, files in os.walk(family_dir):
            if circuit_tripped or budget_reached:
                break
            for file in files:
                if not file.endswith('.md'):
                    continue
                file_path = os.path.join(subdir, file)
                source_path = Path(file_path).resolve().relative_to(_REPO_ROOT).as_posix()
                page_title = extract_head_title(file_path)
                if not page_title:
                    continue

                existing = find_existing_entry(family, source_path, page_title, output_dir)
                title_unchanged = existing is not None and existing.get("pageTitle") == page_title
                if title_unchanged and not force:
                    logging.info(f"Skipping (title unchanged): {page_title} (Family: {family})")
                    continue

                if max_calls is not None and calls_made >= max_calls:
                    logging.info(
                        f"Call budget ({max_calls}) reached -- stopping cleanly, "
                        f"saving progress made so far."
                    )
                    budget_reached = True
                    break

                platform = (
                    platform_override
                    if platform_override is not None
                    else _extract_platform_from_path(file_path, family_dir)
                )
                calls_made += 1

                if existing is not None:
                    new_keywords = get_keywords_from_gemini(page_title, platform)
                    if new_keywords is None:
                        call_failure_count += 1
                        consecutive_failures += 1
                    else:
                        call_success_count += 1
                        consecutive_failures = 0
                        if new_keywords:
                            if title_unchanged:
                                # force=True got us here with an unchanged title -- a
                                # genuine forced correction (e.g. Finding #50's platform
                                # migration), not a rename. Replace, don't union: the
                                # existing keywords are the known-wrong ones this call
                                # exists to remove (Finding #52).
                                logging.info(f"Replacing keywords (forced): {page_title} (Family: {family})")
                                replace_keywords_for_entry(family, source_path, page_title, new_keywords, output_dir)
                            else:
                                logging.info(f"Appending keywords: {page_title} (Family: {family})")
                                append_keywords_to_existing(family, source_path, page_title, new_keywords, output_dir)
                else:
                    logging.info(f"Processing new title: {page_title} (Family: {family})")
                    keywords = get_keywords_from_gemini(page_title, platform)
                    if keywords is None:
                        call_failure_count += 1
                        consecutive_failures += 1
                    else:
                        call_success_count += 1
                        consecutive_failures = 0
                        if keywords:
                            new_entry = {
                                "pageTitle": page_title,
                                "sourcePath": source_path,
                                "keywords": keywords,
                            }
                            variants = getattr(keywords, "title_variants", None)
                            if variants:
                                new_entry["title_ready_variants"] = dict(variants)
                                new_entry["schema_version"] = 2
                            family_data[family].append(new_entry)

                if consecutive_failures >= _CIRCUIT_BREAKER_CONSECUTIVE_FAILURES:
                    logging.error(
                        f"Circuit breaker tripped: {consecutive_failures} consecutive "
                        f"page failures -- quota has evidently not recovered. Saving "
                        f"progress made so far and stopping the whole run now, rather "
                        f"than grinding through the remaining files one at a time."
                    )
                    circuit_tripped = True
                    break

        save_family_to_json(family, family_data[family], output_dir)

    total_calls = call_success_count + call_failure_count
    if total_calls:
        logging.info(
            f"Gemini calls this run: {call_success_count} succeeded, "
            f"{call_failure_count} failed ({total_calls} total)."
        )
        print(
            f"Gemini calls: {call_success_count} succeeded, "
            f"{call_failure_count} failed ({total_calls} total)."
        )
        if circuit_tripped:
            raise SystemExit(
                f"ERROR: circuit breaker tripped after "
                f"{_CIRCUIT_BREAKER_CONSECUTIVE_FAILURES} consecutive failures "
                f"({call_success_count} succeeded, {call_failure_count} failed before "
                f"stopping) -- quota is evidently exhausted for this window. Progress "
                f"made so far has been saved. Resume later once quota recovers."
            )
        if call_success_count == 0:
            # Every single call failed -- this is a systemic problem (retired
            # model, revoked key, exhausted quota), not per-page noise. Exit
            # non-zero so the workflow's existing
            # `|| echo "WARNING: $site exited non-zero"` step actually fires
            # instead of this run silently reporting "0 keyword changes" and
            # looking identical to a genuinely idempotent, healthy run.
            raise SystemExit(
                f"ERROR: all {total_calls} Gemini call(s) failed for this run -- "
                f"check for a retired model, revoked/exhausted API key, or "
                f"changed error format. Not writing this off as 'no changes'."
            )
        if budget_reached:
            msg = (
                f"Call budget ({max_calls}) reached after {calls_made} call(s) this run -- "
                f"stopping cleanly, not a failure. Progress made so far has been saved. "
                f"Resume next run to continue with the remaining files."
            )
            logging.info(msg)
            print(msg)

    return family_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Generate Schema A SEO keywords for content pages using Google Gemini.\n\n"
            "Pass the root of any content subdirectory as content_dir. Common invocations:\n"
            "  KB pages:       python get_keywords.py content/kb.aspose.org keywords/\n"
            "  Docs pages:     python get_keywords.py content/docs.aspose.org/en keywords/ --platform java\n"
            "  Products pages: python get_keywords.py content/products.aspose.org/en keywords/\n\n"
            "The script walks {content_dir}/{family}/ for each family in --families and\n"
            "appends discovered page titles + LLM-generated keywords to keywords/{family}.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "content_dir",
        help=(
            "Root content directory to scan. The script looks for "
            "{content_dir}/{family}/ subdirectories. "
            "E.g. content/kb.aspose.org, content/docs.aspose.org/en, "
            "content/products.aspose.org/en"
        ),
    )
    parser.add_argument(
        "output_dir",
        help="Directory to write per-family keyword JSON files (e.g. keywords/)",
    )
    parser.add_argument(
        "--families",
        nargs="+",
        default=DEFAULT_FAMILIES,
        help=(
            "Product families to process. "
            f"Default: {len(DEFAULT_FAMILIES)} families, from data/family_descriptions.json"
        ),
    )
    parser.add_argument(
        "--platform",
        default=None,
        help=(
            "Force this platform for every file, bypassing automatic per-file path "
            "detection (e.g. net, java, python, cpp, go, rust, typescript). Normally "
            "unnecessary -- the platform is now detected per file from its real path "
            "({family}/{platform}/...), since a single CLI-wide flag applied to every "
            "file regardless of its actual platform was itself a defect (Finding #50). "
            "Only pass this to force one platform for content that doesn't follow the "
            "usual layout."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Bypass skip-if-unchanged (Finding #51) and call Gemini for every page, "
            "even when an existing entry's title hasn't changed. Needed once for the "
            "migration pass that corrects already-mislabeled entries after the platform "
            "detection fix lands; not needed for routine weekly runs."
        ),
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help=(
            "Stop cleanly (not a failure) once this many real Gemini calls have been "
            "made this run, saving progress made so far. A proactive budget, independent "
            "of the reactive circuit breaker -- keeps a single run well inside the real, "
            "empirically-tight quota ceiling discovered in the bootstrap regeneration."
        ),
    )
    parser.add_argument(
        "--rotate-weekly",
        action="store_true",
        help=(
            "Rotate --families processing order by the current ISO week number, so a "
            "fixed per-run call budget doesn't always prioritize the same early families "
            "over many weekly runs. Intended for the scheduled weekly workflow, not "
            "one-off manual/migration invocations where explicit family order matters."
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Error: GOOGLE_API_KEY environment variable is not set.")
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    logging.basicConfig(
        filename="process_log.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    families = rotate_families_by_iso_week(args.families) if args.rotate_weekly else args.families

    process_markdown_files_by_families(
        families, args.content_dir, args.output_dir,
        platform_override=args.platform, force=args.force, max_calls=args.max_calls,
    )
    logging.info("Processing complete.")
