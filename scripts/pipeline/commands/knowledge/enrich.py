"""enrich.py — S-37 Knowledge Enrich: LLM-enriched semantic claims from scout artifacts.

Ports the FL Understand Worker's bounded-description extraction mode into this
repo so that semantic enrichment can be generated fresh, on-demand, from the
internal clone cache — with no FOSS Launcher dependency.

The FL Understand Worker called Claude 3.5 Sonnet with:
  - verified_facts_block: api_surface.json formatted as structured text
  - source_context_block: README + docs + example source excerpts
  - bounded-description mode: for each verified API fact, write one claim

This script reproduces that logic through the canonical ``LLMRouter``.
Endpoint, credential, model, retry, and fallback authority lives in
``scripts/pipeline/config/llm_registry.yaml``.

Reads from:
    knowledge/{family}/{platform}/scout/api_surface.json   (verified facts)
    knowledge/{family}/{platform}/scout/claims.json        (to de-duplicate)
    runs/.clone_cache/aspose_{family}_{platform}/          (source context)

Writes to:
    knowledge/{family}/{platform}/scout/enriched_claims.json

Claim IDs use prefix ERC- (Enriched Claim) to distinguish from scout claims.

Usage:
    python scripts/pipeline/commands/knowledge/enrich.py {family} {platform}
    python scripts/pipeline/commands/knowledge/enrich.py cells python
    python scripts/pipeline/commands/knowledge/enrich.py 3d net --no-llm   # dry-run without LLM

Environment:
    LLM credential aliases are resolved in registry order by LLMRouter.
    ASPOSE_CLONE_CACHE        Override clone cache root (default: runs/.clone_cache/)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import site
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_PIPELINE = Path(__file__).resolve().parents[2]  # commands/knowledge/ -> commands/ -> pipeline/
sys.path.insert(0, str(_SCRIPTS_PIPELINE))

from core.env_loader import load_env  # noqa: E402
load_env()

# Ensure user site-packages are available (needed when ENABLE_USER_SITE=False,
# e.g. system-wide Python installs on Windows).
_user_site = site.getusersitepackages()
if _user_site and os.path.isdir(_user_site) and _user_site not in sys.path:
    sys.path.insert(0, _user_site)

from core.clone_cache import clone_path as _clone_path, clone_exists
from core.fs import atomic_write

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Token budget for source context fed to LLM (chars, not tokens)
_MAX_CONTEXT_CHARS = 12_000
# Max classes to include in verified-facts block (token budget)
_MAX_FACTS_CLASSES = 80
# Minimum Jaccard overlap with an existing scout claim to be considered a duplicate
_DEDUP_OVERLAP_THRESHOLD = 0.7
# Minimum confidence to keep an enriched claim
_MIN_CONFIDENCE = 0.60
# Multi-batch enrichment defaults
_DEFAULT_BATCH_SIZE = 20   # classes per LLM call
_DEFAULT_MIN_COVERAGE = 0.0  # disable by default; use --min-coverage to enforce

_CLAIM_KINDS = {"api", "feature", "format", "install", "troubleshoot", "config",
                "license", "integration", "performance"}

_VALID_PAGE_ROLES = frozenset({"product", "docs", "kb", "reference"})

# Threshold below which a repo is considered "low-docstring"
_LOW_DOCSTRING_THRESHOLD = 0.3


# ---------------------------------------------------------------------------
# Docstring coverage detection
# ---------------------------------------------------------------------------

def _docstring_coverage(api_surface: list) -> float:
    """Fraction of public classes with non-empty docstrings."""
    classes = [c for c in api_surface if isinstance(c, dict) and c.get("name")
               and not c.get("name", "").startswith("_")]
    if not classes:
        return 0.0
    with_doc = sum(1 for c in classes if c.get("doc", "").strip())
    return with_doc / len(classes)


# ---------------------------------------------------------------------------
# Source context builder
# ---------------------------------------------------------------------------

def _rank_files(clone_dir: Path, *, include_tests: bool = False) -> list[tuple[int, Path]]:
    """Return (rank, path) pairs for text files in the clone, ranked by priority.

    When *include_tests* is True, test files are included at rank 5 instead of
    being excluded.  This is useful for low-docstring repos where tests contain
    the best usage examples.
    """
    ranked: list[tuple[int, Path]] = []
    for path in clone_dir.rglob("*"):
        if not path.is_file():
            continue
        name_lower = path.name.lower()
        rel = str(path.relative_to(clone_dir)).replace("\\", "/").lower()

        # Skip binary / vendored / generated
        if any(seg in rel for seg in ("/vendor/", "/node_modules/", "/.git/",
                                       "/dist/", "/build/", "/obj/", "/bin/")):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".gif", ".ico", ".woff",
                                    ".ttf", ".exe", ".dll", ".so", ".pyc"}:
            continue

        is_test = any(seg in rel for seg in ("/test", "test_", "conftest"))

        # Rank 1: root README
        if name_lower in ("readme.md", "readme.rst", "readme.txt") and path.parent == clone_dir:
            ranked.append((1, path))
        # Rank 2: docs folder
        elif any(seg in rel for seg in ("/docs/", "/doc/", "/documentation/")):
            ranked.append((2, path))
        # Rank 3: examples / samples
        elif any(seg in rel for seg in ("/examples/", "/example/", "/samples/", "/sample/")):
            ranked.append((3, path))
        # Rank 4: source files (non-test)
        elif path.suffix.lower() in {".py", ".java", ".cs", ".ts", ".cpp", ".h"} and not is_test:
            ranked.append((4, path))
        # Rank 5: test files (only when include_tests is enabled)
        elif include_tests and is_test and \
                path.suffix.lower() in {".py", ".java", ".cs", ".ts", ".cpp", ".h"}:
            ranked.append((5, path))

    ranked.sort(key=lambda x: x[0])
    return ranked


def _build_source_context(clone_dir: Path, *, low_docstring: bool = False) -> str:
    """Collect ranked source excerpts up to the context budget.

    When *low_docstring* is True the budget is doubled and test files are
    included (they often contain the best usage examples for repos with
    sparse docstrings).
    """
    if not clone_dir.exists():
        return ""
    ranked = _rank_files(clone_dir, include_tests=low_docstring)
    budget = _MAX_CONTEXT_CHARS * 2 if low_docstring else _MAX_CONTEXT_CHARS
    if low_docstring:
        log.info("Low-docstring mode: context budget doubled to %d chars, test files included",
                 budget)
    parts: list[str] = []

    for _rank, path in ranked:
        if budget <= 0:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Per-file cap: leave room for others
        cap = min(4000, budget)
        excerpt = text[:cap]
        rel = str(path.relative_to(clone_dir)).replace("\\", "/")
        parts.append(f"### {rel}\n{excerpt}")
        budget -= len(excerpt)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Verified-facts block builder
# ---------------------------------------------------------------------------

def _build_verified_facts(api_surface: list) -> str:
    """Format api_surface.json as a structured text block for the LLM prompt."""
    if not api_surface:
        return "(no API surface available)"

    lines: list[str] = []
    classes = [c for c in api_surface if isinstance(c, dict) and c.get("name")]
    # Sort: non-test, non-internal first
    public = [c for c in classes if not c.get("name", "").startswith("_")
              and "test" not in c.get("file", "").lower()]
    public = sorted(public, key=lambda c: c.get("name", ""))[:_MAX_FACTS_CLASSES]

    for cls in public:
        name = cls.get("name", "")
        doc = cls.get("doc", "").strip()
        lines.append(f"Class: {name}")
        if doc:
            lines.append(f"  Docstring: {doc[:200]}")

        methods = [m for m in cls.get("methods", []) if isinstance(m, dict)
                   and not m.get("name", "").startswith("_")]
        if methods:
            method_sigs = []
            for m in methods[:20]:  # cap per class
                mname = m.get("name", "")
                params = ", ".join(
                    p.get("name", "") for p in m.get("params", []) if isinstance(p, dict))
                ret = m.get("return_type", "")
                sig = f"{mname}({params})"
                if ret:
                    sig += f" -> {ret}"
                method_sigs.append(sig)
            lines.append("  Methods: " + "; ".join(method_sigs))

        props = cls.get("properties", [])
        if props:
            prop_names = [
                p.get("name", p) if isinstance(p, dict) else str(p)
                for p in props[:10]
            ]
            lines.append("  Properties: " + ", ".join(prop_names))

        enums = cls.get("enum_members", [])
        if enums:
            enum_vals = [
                e.get("name", e) if isinstance(e, dict) else str(e)
                for e in enums[:10]
            ]
            lines.append("  Enum values: " + ", ".join(enum_vals))

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Member-doc prompt helpers (used by --mode member-doc)
# ---------------------------------------------------------------------------

def _build_member_doc_facts(cls: dict) -> str:
    """Format a single class's API members for the member-doc prompt."""
    name = cls.get("name", "Unknown")
    lines = [f"Class: {name}"]

    methods = [m for m in cls.get("methods", []) if isinstance(m, dict)
               and not m.get("name", "").startswith("_")]
    for m in methods[:30]:
        mname = m.get("name", "")
        params = ", ".join(
            (f"{p.get('name', '')}:{p.get('type', '')}" if p.get("type") else p.get("name", ""))
            for p in m.get("params", []) if isinstance(p, dict)
        )
        ret = m.get("return_type", "")
        doc = m.get("doc", "").strip()
        sig = f"  method {mname}({params})"
        if ret:
            sig += f" -> {ret}"
        if doc:
            sig += f"  # {doc[:80]}"
        lines.append(sig)

    props = cls.get("properties", [])
    for p in (props[:30] if props else []):
        if isinstance(p, dict):
            pname = p.get("name", "")
            ptype = p.get("type", "")
            pdoc = p.get("doc", "").strip()
            sig = f"  property {pname}"
            if ptype:
                sig += f": {ptype}"
            if pdoc:
                sig += f"  # {pdoc[:80]}"
            lines.append(sig)
        elif isinstance(p, str):
            lines.append(f"  property {p}")

    enums = cls.get("enum_members", [])
    for e in (enums[:30] if enums else []):
        if isinstance(e, dict):
            ename = e.get("name", "")
            evalue = e.get("value", "")
            edoc = e.get("doc", "").strip()
            sig = f"  enum_value {ename}"
            if evalue:
                sig += f" = {evalue}"
            if edoc:
                sig += f"  # {edoc[:80]}"
            lines.append(sig)
        elif isinstance(e, str):
            lines.append(f"  enum_value {e}")

    return "\n".join(lines)


def _build_member_doc_prompt(
    family: str, platform: str, cls: dict, source_context: str
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for per-member description generation.

    Unlike _build_prompt (which generates semantic capability claims), this
    function asks the LLM to write one sentence per method/property, each
    starting with ClassName.MemberName so that batch_reference.py can index
    the descriptions into reference table cells via _build_erc_member_index().
    """
    cls_name = cls.get("name", "Unknown")
    facts = _build_member_doc_facts(cls)

    system = (
        "You are generating technical API documentation. "
        "You produce structured JSON only. No prose, no explanation. "
        "Descriptions must be accurate, specific, and grounded in the signatures provided."
    )

    user = f"""You are documenting the Aspose.{family.upper()} library for {platform}.

CLASS: {cls_name}

API SURFACE (only document members listed here — do NOT invent any members):
---
{facts}
---

SOURCE CONTEXT (use for grounding — excerpt from source code and README):
---
{source_context[:3000]}
---

TASK:
For EVERY method, property, and enum_value listed above, write one concise sentence describing what it does or represents.

FORMAT RULES:
- Each claim text MUST start with exactly "{cls_name}.MemberName" using the exact member name
- After the member name, describe the behavior or meaning in plain English
- Example: "{cls_name}.MethodName saves the object to the specified path."
- For enum values: "{cls_name}.VALUE_NAME represents the X format/mode/type."
- Keep each description under 120 characters
- Confidence: 0.80 if grounded in source context; 0.70 if inferred from signature/name only
- Use kind "api" for all claims
- Set claim_source to "llm_member_doc"

CONSTRAINTS:
- Do NOT invent behavior not derivable from the signature, name, or source context
- Do NOT reference classes or methods not listed in API SURFACE above
- Write exactly one claim per member

OUTPUT: JSON array only. Each element:
{{
  "claim_id": "ERC-{family}-{platform}-NNN",
  "text": "{cls_name}.MemberName description here.",
  "kind": "api",
  "confidence": 0.80,
  "claim_source": "llm_member_doc"
}}

Output the JSON array now. Nothing else."""

    return system, user


# ---------------------------------------------------------------------------
# Feature-mode prompt (S-5: knowledge model depth)
# ---------------------------------------------------------------------------

# Confidence cap for feature-mode claims (lower trust tier than API claims)
_FEATURE_CONFIDENCE_CAP = 0.70

def _build_feature_prompt(
    family: str, platform: str,
    verified_facts: str, source_context: str,
    source_files: list[str],
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for feature/install/troubleshoot extraction.

    Unlike _build_prompt (which produces per-API-member descriptions), this
    prompt asks the LLM to extract higher-level capability claims:
    - feature: What can a developer accomplish with this library?
    - install: How to install, configure, or set up the library
    - troubleshoot: Common pitfalls, limitations, or workarounds
    - format: File format support with import/export direction
    - config: Configuration patterns and options
    - integration: Integration with other systems/libraries

    Every claim MUST cite a source_file from the clone cache.
    """
    file_list = "\n".join(f"  - {f}" for f in source_files[:50])

    system = (
        "You are extracting CAPABILITY claims for API documentation. "
        "You produce structured JSON only. No prose, no explanation. "
        "Focus on WHAT developers can DO with this library, not on "
        "describing individual API members. "
        "Every claim must cite a specific source file as evidence."
    )

    user = f"""You are documenting the Aspose.{family.upper()} library for {platform}.

VERIFIED API SURFACE (reference only — do NOT write per-member descriptions):
---
{verified_facts}
---

SOURCE CONTEXT — README, docs, examples, and source code:
---
{source_context[:10000]}
---

AVAILABLE SOURCE FILES (cite one per claim):
{file_list}

TASK:
Extract HIGH-LEVEL CAPABILITY claims about what this library enables.
Do NOT write per-class or per-method descriptions (those are covered elsewhere).
Instead, focus on:

1. FEATURE claims: What workflows/tasks can a developer accomplish?
   Examples: "Convert email messages from EML to MSG format", "Parse MIME headers
   from raw email streams", "Manage Outlook PST storage files programmatically"

2. INSTALL claims: How to install, set up, or configure the library
   Examples: "Install via NuGet: Install-Package Aspose.Email.Cpp",
   "Requires C++17 or later", "Link against aspose_email_cpp.lib on Windows"

3. TROUBLESHOOT claims: Common pitfalls, limitations, or error handling
   Examples: "Large PST files (>2GB) require 64-bit builds",
   "SMTP connections require explicit TLS configuration via SecurityOptions"

4. FORMAT claims: Supported file formats with direction (read/write/convert)
   Examples: "Reads EML, MSG, MBOX, PST, OST formats",
   "Exports calendar items to ICS format"

5. CONFIG claims: Configuration patterns and notable options
   Examples: "SmtpClient supports OAuth2 authentication via AccessToken property",
   "ImapClient connection pooling configured via MaxConnectionsPerServer"

6. INTEGRATION claims: How this library works with external systems
   Examples: "Connects to Exchange Server via EWS protocol",
   "Supports IMAP, POP3, and SMTP protocols for email server communication"

RULES:
- Each claim MUST cite a source_file from the AVAILABLE SOURCE FILES list
- Claims MUST be grounded in evidence visible in SOURCE CONTEXT or API SURFACE
- Do NOT invent features, protocols, or format names not evident in the code
- Do NOT write per-member API descriptions (kind "api") — those exist already
- Keep claims concise: 1-2 sentences each
- Aim for 15-30 claims covering diverse capabilities
- Confidence: 0.65-0.70 (these are inferred from source, not verified facts)

FORBIDDEN:
- kind "api" — do not produce api-kind claims
- Claims about classes/methods not in VERIFIED API SURFACE
- Hallucinated format names, version numbers, or protocol support

OUTPUT: JSON array only. Each element:
{{
  "claim_id": "FRC-{family}-{platform}-NNN",
  "text": "...",
  "kind": "feature|install|troubleshoot|format|config|integration",
  "confidence": 0.65,
  "claim_source": "llm_feature",
  "source_file": "path/to/source.py"
}}

Output the JSON array now. Nothing else."""

    return system, user


# Common English words that match CamelCase regex but aren't API names.
# Feature-mode claims describe capabilities, so these appear naturally.
_COMMON_CAMELCASE_WORDS = frozenset({
    "read", "write", "load", "save", "build", "install", "create", "delete",
    "update", "parse", "send", "receive", "connect", "close", "open", "find",
    "search", "convert", "export", "import", "requires", "underlying",
    "validation", "compound", "file", "binary", "unicode", "mime", "smtp",
    "imap", "http", "https", "json", "html", "outlook", "exchange",
    "windows", "linux", "macos", "cmake", "nuget", "maven", "gradle",
    "python", "java", "sharp", "cplusplus", "dotnet",
})


def _validate_feature_claim(claim: dict, api_names: set[str],
                            source_files: set[str]) -> tuple[bool, str]:
    """Validate a feature-mode claim. Returns (valid, reason)."""
    if not isinstance(claim, dict):
        return False, "not a dict"
    text = claim.get("text", "")
    kind = claim.get("kind", "")
    if not text or not kind:
        return False, "missing text or kind"
    # Reject api-kind claims (feature mode should not produce these)
    if kind == "api":
        return False, "api kind not allowed in feature mode"
    if kind not in _CLAIM_KINDS:
        return False, f"unknown kind: {kind}"
    # Source file citation required
    sf = claim.get("source_file", "")
    if not sf:
        return False, "missing source_file citation"
    # Cap confidence
    conf = claim.get("confidence", 0)
    if conf < _MIN_CONFIDENCE:
        return False, f"confidence {conf} below minimum {_MIN_CONFIDENCE}"
    # Hallucination check: CamelCase words that look like API class names.
    # Use a stricter pattern: require internal uppercase (true CamelCase like
    # SmtpClient, MapiMessage) or exclude common English words.
    # \b[A-Z][a-z]+[A-Z] catches true CamelCase; \b[A-Z][A-Za-z]{3,}\b is
    # too broad (catches "When", "Read", "Compile", etc.)
    camel_words = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]*)+\b", text)
    api_like = [w for w in camel_words if w.lower() not in _COMMON_CAMELCASE_WORDS]
    if api_like:
        known_any = any(w.lower() in api_names for w in api_like)
        if not known_any:
            return False, f"hallucinated API reference: {api_like}"
    return True, "ok"


# ---------------------------------------------------------------------------
# LLM preflight health check
# ---------------------------------------------------------------------------

def _preflight_check() -> dict[str, str]:
    """Probe each LLM endpoint and return status dict for pipeline_run.json.

    Uses LLMRouter.probe() — no module-level cache needed.
    """
    try:
        from lib.llm_router import LLMRouter
        router = LLMRouter()
        raw = router.probe()
        return {name: info.get("status", "unknown") for name, info in raw.items()}
    except Exception as exc:
        log.warning("LLM preflight check failed: %s", exc)
        return {"professionalize": "unknown", "ollama": "unknown"}


# ---------------------------------------------------------------------------
# LLM call (delegates to shared LLMRouter)
# ---------------------------------------------------------------------------

_router = None  # lazy singleton — avoids YAML re-read per call
_enrich_metrics_events: list = []  # CS-001 MetricsEvent objects from LLM calls; reset per enrich() call
_enrich_run_id: str | None = None  # generated per enrich() call


def _get_router():
    """Return cached LLMRouter instance (lazy init)."""
    global _router
    if _router is None:
        from lib.llm_router import LLMRouter
        _router = LLMRouter()
    return _router


# HARDEN-A4: bump when the cached-output SCHEMA/validation contract changes in a
# way that makes old cached outputs unusable (prompt content itself is hashed
# into the key, so prompt changes invalidate automatically).
_ENRICH_CACHE_SCHEMA = "1"

# TC-MT040-25: per-call chat timeout, overridable via --llm-timeout. Default
# unchanged (90s, matching llm_registry.yaml's own professionalize.chat
# default_timeout) so this is a pure opt-in -- every existing caller/product
# behaves identically unless the new flag is passed. Added after pdf/typescript's
# real bootstrap (3602 classes, the largest enrichment target this pipeline has
# attempted) repeatedly hit "Request timed out" (not a connection failure --
# the server was reachable) at the 90s default; a larger timeout is a targeted,
# scoped fix (this module's own hardcoded call site) rather than a shared
# llm_registry.yaml change that would alter every other module's LLM calls too.
_LLM_TIMEOUT_SECONDS = 90


def _llm_call(
    prompt_system: str,
    prompt_user: str,
    cache=None,
    cache_extra: list[str] | None = None,
) -> tuple[dict | list | None, str]:
    """Call LLM with professionalize.com → Ollama fallback.

    HARDEN-A4: with a cache (lib.llm_output_cache.LLMOutputCache), the fully
    rendered prompts + caller identity parts form a content-hash key — a rerun
    against unchanged knowledge input returns the stored output byte-identically
    with zero LLM calls. Fresh successes are stored even when cache reads are
    bypassed (forced regen refreshes the cache).

    Returns (parsed_data, 'provider/model') or (None, '') on failure.
    """
    cache_key = None
    if cache is not None:
        from lib.llm_output_cache import build_cache_key, sha256_text
        cache_key = build_cache_key([
            *(cache_extra or []),
            sha256_text(prompt_system),
            sha256_text(prompt_user),
            _ENRICH_CACHE_SCHEMA,
        ])
        entry = cache.load(cache_key)
        if entry is not None:
            log.info("LLM cache HIT (%s...) — zero-call reuse via %s",
                     cache_key[:12], entry.get("model_used", "?"))
            return entry["output"], entry.get("model_used", "cache")

    try:
        from lib.llm_router import EndpointStatus
        router = _get_router()
    except (ImportError, RuntimeError) as exc:
        log.warning("LLM router unavailable: %s", exc)
        return None, ""

    from lib.llm_router import LLMCallContext
    result = router.call_chat(
        prompt_system, prompt_user,
        temperature=0.0,
        max_tokens=8000,
        timeout=_LLM_TIMEOUT_SECONDS,
        json_extract=True,
        json_array=True,
        context=LLMCallContext.create("knowledge-enrich", "knowledge-enrichment", "claims"),
    )

    # CS-001: collect MetricsEvents from this call
    if hasattr(result, 'metrics_events') and result.metrics_events:
        _enrich_metrics_events.extend(result.metrics_events)
    if result.status == EndpointStatus.OK:
        model_info = f"{result.provider}/{result.model}"
        log.info("LLM call via %s", model_info)
        if cache is not None and cache_key and _is_cacheable_payload(result.data):
            cache.save(cache_key, result.data, model_info)
        return result.data, model_info
    return None, ""


def _is_cacheable_payload(data) -> bool:
    """HARDEN-A4/R2: OK transport status is not enough — an HTTP-200 completion
    can carry a semantic error body (e.g. {"error": "rate_limited"}, the exact
    TC-2 case). Caching one would replay the failure with zero LLM calls on
    every rerun until the input changes. Cache only shapes the TC-2 validation
    downstream accepts as claim-bearing."""
    if isinstance(data, list):
        return True
    return isinstance(data, dict) and "claims" in data


# ---------------------------------------------------------------------------
# Metrics dry-run helper
# ---------------------------------------------------------------------------

def _try_write_enrich_metrics(
    family: str,
    platform: str,
    run_id: str | None,
    events: list,
    run_stats: dict,
    t0: float,
) -> None:
    """Write metrics dry-run JSON for one enrich() run. Never raises."""
    if run_id is None:
        return
    try:
        import json as _json
        from commands.ops.run_metrics import RunMetrics
        from commands.ops.metrics_schema import row_to_dict
        dry_dir = _REPO_ROOT / "reports" / "metrics" / "dry"
        dry_dir.mkdir(parents=True, exist_ok=True)
        dur_ms = max(0, int((time.monotonic() - t0) * 1000))
        disc = run_stats.get("batches_attempted", 0)
        succ = run_stats.get("batches_succeeded", 0)
        fail = run_stats.get("batches_failed", 0)
        with RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-knowledge-enrichment",
            job_type="knowledge_enrichment",
            product=family,
            platform=platform,
            website="aspose.org",
            website_section="Docs",
            ledger_root=_REPO_ROOT / "reports" / "metrics" / "events",
        ) as rm:
            if events:
                rm.record_events(events)
            row = rm.to_row(
                items_discovered=disc,
                items_failed=fail,
                items_succeeded=succ,
                run_duration_ms=dur_ms,
            )
        dry_path = dry_dir / f"{run_id}.dry.json"
        dry_path.write_text(_json.dumps(row_to_dict(row), indent=2), encoding="utf-8")
        log.info("Metrics dry-run: %s", dry_path)
        # Slice 16: production submit if AGENT_METRICS_PRODUCTION=1
        from commands.ops.metrics_submitter import try_production_submit
        try_production_submit(row)
    except Exception as exc:
        log.debug("Metrics dry-run skipped: %s", exc)


# ---------------------------------------------------------------------------
# Claim extraction prompt
# ---------------------------------------------------------------------------

def _build_prompt(family: str, platform: str,
                  verified_facts: str, source_context: str,
                  *, low_docstring: bool = False) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for enrichment extraction."""
    system = (
        "You are extracting factual claims for API documentation. "
        "You produce structured JSON only. No prose, no explanation."
    )
    if low_docstring:
        system += (
            " Source code docstrings are sparse. Derive concrete behavioral"
            " claims from source code patterns, test assertions, type"
            " signatures, and README content. Prefer specific claims with"
            " method names, parameter types, and return values over abstract"
            " summaries."
        )

    user = f"""You are documenting the Aspose.{family.upper()} library for {platform}.

VERIFIED FACTS — the ONLY APIs that exist in this library:
(Do NOT invent any class, method, property, or format name not listed here.)
---
{verified_facts}
---

SOURCE CONTEXT — documentation, README, and example code:
---
{source_context[:8000]}
---

TASK:
For the VERIFIED FACTS above, write user-facing claim statements that describe what the library does.
Focus on:
- What each class/method enables developers to do
- Supported file formats with import/export direction
- High-level feature capabilities (semantic groupings)
- Known limitations or troubleshooting hints if evident from source

RULES:
- Claims MUST only reference class/method names listed in VERIFIED FACTS
- Each claim must be factually grounded in the source context or the API surface
- Do NOT invent features, version numbers, or format names not in the evidence
- Write at the level of a developer learning the library (user-facing, not internal)
- Keep claims concise: 1–3 sentences each

CLAIM KINDS (assign exactly one per claim):
- api: Public API surface (class/method/property description)
- feature: Product capability grouping (semantic)
- format: Supported file formats with direction
- install: Installation or dependency requirements
- troubleshoot: Known limitations or workarounds

PAGE ROLE (assign exactly one per claim):
- "product": High-level capability — what the library enables (marketing-style)
- "docs": Procedural step — how to accomplish a task with this API
- "kb": Problem-solution — how to solve a specific developer problem
- "reference": API description — what a specific class/method does
Generate a mix: aim for ~30% product, ~40% docs, ~20% kb, ~10% reference.

OUTPUT: JSON array only. Each element:
{{
  "claim_id": "ERC-{family}-{platform}-NNN",
  "text": "...",
  "kind": "api|feature|format|install|troubleshoot",
  "page_role": "product|docs|kb|reference",
  "confidence": 0.75,
  "claim_source": "llm_enriched",
  "evidence": [{{"source_file": "...", "snippet": "..."}}]
}}

Output the JSON array now. Nothing else."""

    return system, user


# ---------------------------------------------------------------------------
# Tokenizer and dedup
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


# Kinds exempt from Jaccard dedup — require exact text match to avoid
# merging method overloads that share most tokens.  Mirrors the guard in
# promote.py (_semantic_dedup_claims).
_EXACT_ONLY_KINDS = frozenset({
    "api_method", "api_constructor", "api_property", "format_support",
})


def _is_duplicate(candidate: dict, existing_claims: list) -> bool:
    """Return True if candidate text overlaps with any existing claim above threshold."""
    c_tokens = _tokenize(candidate.get("text", ""))
    if not c_tokens:
        return False
    c_kind = candidate.get("kind", "")
    for ec in existing_claims:
        # For API signature claims, require exact text match (not Jaccard)
        ec_kind = ec.get("kind", "")
        if c_kind in _EXACT_ONLY_KINDS or ec_kind in _EXACT_ONLY_KINDS:
            c_text = candidate.get("text", "").strip()
            e_text = ec.get("text", "").strip()
            if c_text == e_text:
                return True
            continue
        e_tokens = _tokenize(ec.get("text", ""))
        union = c_tokens | e_tokens
        if not union:
            continue
        if len(c_tokens & e_tokens) / len(union) >= _DEDUP_OVERLAP_THRESHOLD:
            return True
    return False


# ---------------------------------------------------------------------------
# Claim validation
# ---------------------------------------------------------------------------

def _extract_api_names(api_surface: list) -> set[str]:
    """Build a flat set of all known API names for hallucination checking."""
    names: set[str] = set()
    for cls in api_surface:
        if not isinstance(cls, dict):
            continue
        cname = cls.get("name", "")
        if cname:
            names.add(cname.lower())
        for m in cls.get("methods", []):
            if isinstance(m, dict) and m.get("name"):
                names.add(m["name"].lower())
        for p in cls.get("properties", []):
            if isinstance(p, dict) and p.get("name"):
                names.add(p["name"].lower())
        for e in cls.get("enum_members", []):
            if isinstance(e, dict) and e.get("name"):
                names.add(e["name"].lower())
            elif isinstance(e, str):
                names.add(e.lower())
    return names


def _validate_claim(claim: dict, api_names: set[str]) -> bool:
    """Return True if the claim passes validation."""
    if not isinstance(claim, dict):
        return False
    if not claim.get("text") or not claim.get("kind"):
        return False
    if claim.get("kind") not in _CLAIM_KINDS:
        return False
    if claim.get("confidence", 0) < _MIN_CONFIDENCE:
        return False
    # page_role: optional, but if present must be valid
    pr = claim.get("page_role")
    if pr is not None and pr not in _VALID_PAGE_ROLES:
        log.debug("Dropping claim with invalid page_role '%s': %s",
                  pr, claim.get("text", "")[:80])
        return False
    # Light hallucination check: if claim text contains CamelCase words,
    # at least one must appear in the known API names
    camel_words = re.findall(r"\b[A-Z][A-Za-z]{3,}\b", claim.get("text", ""))
    if camel_words:
        known_any = any(w.lower() in api_names for w in camel_words)
        if not known_any:
            log.debug("Dropping claim with unknown API references: %s",
                      claim.get("text", "")[:80])
            return False
    return True


# ---------------------------------------------------------------------------
# Claim ID assignment
# ---------------------------------------------------------------------------

# RPR-J-16: member-doc claims are prompted (see _build_member_doc_prompt) to
# always start their text with the exact "ClassName.MemberName" they describe.
# That prefix is a stable anchor known before the LLM call — unlike the rest
# of the claim's wording, it does not change when a rebuild re-phrases the
# same fact. Anchoring the ID to it (instead of the full text) keeps
# citations from dangling across knowledge rebuilds.
_MEMBER_DOC_ANCHOR_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")


def _assign_ids(claims: list, family: str, platform: str) -> list:
    """Assign stable IDs to all claims.

    Member-doc claims (claim_source == "llm_member_doc") derive their ID from
    the "ClassName.MemberName" anchor parsed out of the required text prefix,
    not the exact wording — see RPR-J-16. This keeps citations from dangling
    across a knowledge rebuild that rewords the same fact.

    Overloaded members (multiple constructors, Save(path) vs Save(stream),
    etc.) all share one anchor — measured against the real corpus, this is
    common (815 of 18,969 real member-doc claims, ~4.3%), not a rare edge
    case. Only one claim per anchor may safely take the stable anchor-based
    ID (promote.py hard-fails the whole write on a duplicate ERC-* id);
    every other claim sharing that anchor keeps the prior full-text hash
    instead of being dropped, so no claim is ever silently lost — it just
    doesn't gain the new stability guarantee for that particular overload.
    The claim that "wins" the anchor is chosen by sorting the colliding
    group's text, not by generation order, so the choice doesn't depend on
    how the LLM happened to order its response.

    Every other claim — non-member-doc, or member-doc with an unparseable
    prefix (malformed LLM output) — is entirely unaffected and keeps the
    original text+kind hash scheme exactly as before. This also prevents
    sequential LLM batch IDs (001, 002, ...) from surviving across
    multi-batch runs and causing duplicate IDs for distinct claim texts.

    Known limitation (found by independent review, RPR-J-10): the anchor
    winner's ID is sha256(anchor|kind), which is byte-identical to what a
    NON-member-doc claim would get if its own full text happened to equal
    the bare anchor string with the same kind (e.g. text="Save.Load", no
    claim_source) — a cross-scheme hash collision, not a within-anchor-group
    one. This is unreached by real capability-mode prose (which describes
    behavior in sentences, never emits a bare "ClassName.MemberName" as a
    complete claim) and is backstopped even if it did occur: promote.py's
    duplicate-ERC-id check (promote.py, "FAIL: N duplicate ERC claim_id(s) -
    aborting write") hard-aborts the write rather than silently merging two
    distinct claims under one ID. No claim is silently lost; the guarantee
    that fails is "no possible input can collide," not "no data loss."
    """
    # Pass 1: compute each claim's anchor (or None), without assigning IDs.
    anchors: list = []
    for claim in claims:
        anchor = None
        if isinstance(claim, dict) and claim.get("claim_source") == "llm_member_doc":
            match = _MEMBER_DOC_ANCHOR_RE.match(claim.get("text", ""))
            if match:
                anchor = f"{match.group(1)}.{match.group(2)}"
        anchors.append(anchor)

    # Pass 2: for an anchor shared by more than one claim, only the
    # deterministically-chosen (sorted by text) claim keeps the anchor-based
    # ID; the rest fall back to the text+kind scheme so nothing collides.
    anchor_groups: dict = {}
    for idx, anchor in enumerate(anchors):
        if anchor:
            anchor_groups.setdefault(anchor, []).append(idx)
    anchor_owner: dict = {}
    for anchor, idxs in anchor_groups.items():
        winner = idxs[0] if len(idxs) == 1 else min(
            idxs, key=lambda i: claims[i].get("text", "")
        )
        anchor_owner[winner] = True

    result = []
    for idx, claim in enumerate(claims):
        c = dict(claim)
        anchor = anchors[idx]
        if anchor and anchor_owner.get(idx):
            stable = hashlib.sha256(
                (anchor + "|" + c.get("kind", "")).encode()
            ).hexdigest()[:8]
        else:
            stable = hashlib.sha256(
                (c.get("text", "") + "|" + c.get("kind", "")).encode()
            ).hexdigest()[:8]
        c["claim_id"] = f"ERC-{family}-{platform}-{stable}"
        result.append(c)
    return result


# ---------------------------------------------------------------------------
# Task 18 (mission-plan-the-end-to-end-vast-hejlsberg.md §9.13, closes G11):
# prune stale carried-forward member-doc claims
# ---------------------------------------------------------------------------

def _prune_stale_carried_forward_claims(claims: list, api_surface: list) -> list:
    """Drop carried-forward llm_member_doc claims whose target class/member
    no longer exists in the CURRENT api_surface.json.

    Root cause this fixes (G11): enrich.py's own carry-forward step
    (`all_batched_claims = list(existing_enriched)`) starts every run from
    the entire previous enriched_claims.json and never re-validates carried-
    forward claims against the current api_surface -- promote.py's own
    staleness gate only checks a whole-file config hash, which stays "fresh"
    even when one specific carried-forward claim describes a since-renamed
    or since-removed member. Mirrors the fix already applied to the sibling
    evidence.apis field's identical bug (evidence/writer.py, found live on
    3d/python's reference _index.md after Token/TokenType were removed from
    api_surface.json -- the old union-only merge kept citing them
    indefinitely since nothing ever re-derives them to trigger a natural
    drop). Same remedy here: validate against the current, authoritative
    source instead of trusting a prior snapshot forever.

    Scope, deliberately narrow (matches the same claim_source gate Task 16's
    _MEMBER_DOC_ANCHOR_RE-based logic already uses): only llm_member_doc
    claims have a single, well-defined "ClassName.MemberName" target to
    validate -- general capability-mode claims describe broader product
    behavior, not one specific member, and pruning those on this same basis
    would be a real, unjustified overreach beyond this task's own scope. A
    member-doc claim whose text doesn't parse against the anchor pattern at
    all (malformed LLM output, the same edge case _assign_ids already
    documents) is left untouched -- nothing to validate against, and
    dropping data based on an assumption would be worse than keeping it.
    """
    class_by_name = {c["name"]: c for c in api_surface if isinstance(c, dict) and "name" in c}
    result = []
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("claim_source") != "llm_member_doc":
            result.append(claim)
            continue
        match = _MEMBER_DOC_ANCHOR_RE.match(claim.get("text", ""))
        if not match:
            result.append(claim)
            continue
        class_name, member_name = match.group(1), match.group(2)
        cls = class_by_name.get(class_name)
        if cls is None:
            continue  # target class renamed/removed -- prune
        member_names = (
            {m.get("name") for m in cls.get("methods", [])}
            | {p.get("name") for p in cls.get("properties", [])}
        )
        if member_name not in member_names:
            continue  # target member renamed/removed -- prune
        result.append(claim)
    return result


# ---------------------------------------------------------------------------
# FIX-10: Post-enrichment source verification
# ---------------------------------------------------------------------------

# Patterns that indicate a claim asserts something is NOT consumed/implemented.
_STUB_CLAIM_RE = re.compile(
    r"not\s+(?:consumed|forwarded|applied|implemented|supported|used|wired)"
    r"|stub|forward.compatibility|placeholder|no.op|noop",
    re.IGNORECASE,
)

# Extract property/member name from claim text: "PropertyName is not consumed"
_PROPERTY_NAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]{2,}(?:\.[a-z_][a-z_0-9]+)?)\b")


def _post_validate_stub_claims(claims: list, clone_dir: Path) -> list:
    """Demote claims that incorrectly assert a property is a stub.

    For each claim matching stub-assertion patterns, grep the source tree
    for references to the property name.  If found in non-test source files,
    demote confidence to 0.3 and flag for review.
    """
    if not clone_dir or not clone_dir.exists():
        return claims

    # Build a simple searchable index of source content (non-test files)
    source_text = ""
    source_exts = {".py", ".java", ".cs", ".ts", ".js", ".cpp", ".h", ".hpp"}
    for fpath in clone_dir.rglob("*"):
        if not fpath.is_file() or fpath.suffix.lower() not in source_exts:
            continue
        rel = str(fpath.relative_to(clone_dir)).replace("\\", "/").lower()
        if any(seg in rel for seg in ("/test", "test_", "conftest", "/.git/")):
            continue
        try:
            source_text += fpath.read_text(encoding="utf-8", errors="replace") + "\n"
        except OSError:
            continue

    if not source_text:
        return claims

    source_lower = source_text.lower()
    demoted = 0

    for claim in claims:
        text = claim.get("text", "")
        if not _STUB_CLAIM_RE.search(text):
            continue

        # Extract property/member names from the claim
        prop_names = _PROPERTY_NAME_RE.findall(text)
        for prop in prop_names:
            # Check for the leaf member name (e.g. "export_underline_formatting"
            # from "MarkdownSaveOptions.export_underline_formatting")
            search_name = prop.split(".")[-1] if "." in prop else prop
            # Must be at least 4 chars to avoid false matches
            if len(search_name) < 4:
                continue
            if search_name.lower() in source_lower:
                claim["confidence"] = 0.3
                claim["stale_warning"] = (
                    f"Source code references '{search_name}' in non-test files — "
                    f"claim that it is not consumed may be incorrect"
                )
                demoted += 1
                break  # one match is enough to demote

    if demoted:
        log.info("FIX-10: Demoted %d stub claims whose properties appear in source code", demoted)
    return claims


# ---------------------------------------------------------------------------
# Main enrich function
# ---------------------------------------------------------------------------

def enrich(family: str, platform: str, knowledge_root=None, *,
           no_llm: bool = False, rehash_only: bool = False,
           batch_size: int = _DEFAULT_BATCH_SIZE,
           min_coverage: float = _DEFAULT_MIN_COVERAGE,
           mode: str = "capability",
           reports_root=None,
           force_llm_regen: bool = False) -> bool:
    """Run S-37 enrichment for a family/platform.

    Returns True on success (even if LLM unavailable — writes empty enriched file).
    """
    base = (Path(knowledge_root) if knowledge_root else Path("knowledge")) / family / platform
    scout_dir = base / "scout"
    out_path = scout_dir / "enriched_claims.json"

    global _enrich_metrics_events, _enrich_run_id
    _enrich_metrics_events = []
    try:
        from commands.ops.metrics_schema import generate_run_id as _gen_run_id
        _enrich_run_id = _gen_run_id()
    except Exception:
        _enrich_run_id = None
    log.info("=== S-37 knowledge-enrich: %s/%s ===", family, platform)
    t0 = time.monotonic()
    run_stats: dict[str, Any] = {
        "batches_attempted": 0, "batches_succeeded": 0, "batches_failed": 0,
        "claims_raw": 0, "claims_rejected": 0, "claims_deduplicated": 0,
        "claims_accepted": 0, "claims_stub_demoted": 0, "claims_final": 0,
        "model_used": "", "preflight": {},
        "preserved_existing": False, "preserved_stale": False,
        "duration_seconds": 0.0,
    }

    # Pre-conditions
    api_surface_path = scout_dir / "api_surface.json"
    if not api_surface_path.exists():
        log.error("scout/api_surface.json not found for %s/%s — run S-34 (repo-scout) first",
                  family, platform)
        return False

    api_surface_text = api_surface_path.read_text(encoding="utf-8")
    api_surface: list = json.loads(api_surface_text)
    if not isinstance(api_surface, list):
        log.error("api_surface.json is not a list for %s/%s", family, platform)
        return False

    # HARDEN-A4: content-hash-keyed LLM output cache. Key parts include the
    # api_surface sha so a re-scout invalidates everything; the rendered prompts
    # (hashed inside _llm_call) cover per-batch source-content changes.
    # Hermeticity: an explicit knowledge_root (tests, sandboxes) scopes the cache
    # beside it — never into the live reports/ tree from an isolated run.
    from lib.llm_output_cache import LLMOutputCache, sha256_text as _sha_text
    _cache_reports_root = reports_root
    if _cache_reports_root is None and knowledge_root is not None:
        _cache_reports_root = Path(knowledge_root) / ".llm_cache_reports"
    llm_cache = LLMOutputCache(
        family, platform, "enrich",
        reports_root=_cache_reports_root,
        enabled=not force_llm_regen,
    )
    if force_llm_regen:
        log.warning(
            "LLM_CACHE_BYPASSED: forced fresh regeneration for %s/%s "
            "(cache reads disabled; fresh outputs still stored for future runs)",
            family, platform,
        )
    _cache_extra = [family, platform, _sha_text(api_surface_text)]

    # Load existing scout claims (for de-duplication)
    # FIX-12: claims.json may be a flat list (legacy) or a wrapper dict with
    # {source_sha, claims: [...]}.  Accept both.
    scout_claims: list = []
    scout_claims_path = scout_dir / "claims.json"
    if scout_claims_path.exists():
        try:
            raw = json.loads(scout_claims_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                scout_claims = raw
            elif isinstance(raw, dict):
                scout_claims = raw.get("claims", [])
        except (json.JSONDecodeError, OSError):
            pass

    # Load existing enriched claims (for idempotent re-runs)
    existing_enriched: list = []
    if out_path.exists():
        try:
            existing_data = json.loads(out_path.read_text(encoding="utf-8"))
            existing_enriched = existing_data.get("claims", []) if isinstance(existing_data, dict) else []
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not parse existing enriched_claims.json: %s — treating as empty", exc)

    # Task 18 (§9.13, closes G11): prune carried-forward member-doc claims
    # whose target class/member no longer exists in the CURRENT api_surface
    # (just loaded above), instead of trusting the whole prior snapshot
    # forever. Placed here, before any downstream use of existing_enriched
    # (dedup, all_batched_claims, --rehash-only, --no-llm preservation),
    # so every one of those paths benefits automatically.
    if existing_enriched:
        pruned_count = len(existing_enriched)
        existing_enriched = _prune_stale_carried_forward_claims(existing_enriched, api_surface)
        pruned_count -= len(existing_enriched)
        if pruned_count:
            log.info(
                "Pruned %d stale carried-forward member-doc claim(s) whose "
                "target no longer exists in the current api_surface.json",
                pruned_count,
            )

    # Detect low-docstring repos and activate compensating measures
    doc_coverage = _docstring_coverage(api_surface)
    low_docstring = doc_coverage < _LOW_DOCSTRING_THRESHOLD
    log.info("Scout claims: %d, API classes: %d, docstring coverage: %.0f%%",
             len(scout_claims), len(api_surface), doc_coverage * 100)
    if low_docstring:
        log.info("Low-docstring mode activated (coverage %.0f%% < %.0f%% threshold) — "
                 "doubling context budget, including test files, enhancing prompt",
                 doc_coverage * 100, _LOW_DOCSTRING_THRESHOLD * 100)

    if no_llm:
        if existing_enriched:
            log.warning(
                "--no-llm: existing enriched_claims.json has %d claims — "
                "preserving existing file instead of overwriting with empty output.",
                len(existing_enriched)
            )
            run_stats["preserved_existing"] = True
            # Task 18 (§9.13): "preserving" must still reflect this run's own
            # pruning of stale carried-forward claims (done above, before this
            # branch) -- otherwise --no-llm, a common cheap re-run path, would
            # leave a pruned claim on disk forever, silently defeating the fix
            # for every product refreshed this way. Only actually re-writes
            # the file when pruning genuinely removed something, so a true
            # no-op run stays a true no-op (no timestamp/hash churn for no
            # real reason).
            if pruned_count:
                _write_output(out_path, existing_enriched, family, platform,
                              "none (--no-llm, pruned)", api_surface)
            run_stats["duration_seconds"] = round(time.monotonic() - t0, 1)
            run_stats["cache_hits"] = llm_cache.hits
            run_stats["cache_misses"] = llm_cache.misses
            _write_enrichment_report(family, platform, run_stats, "scout-only-explicit",
                                     out_path, reports_root=reports_root)
            return True
        log.info("--no-llm: writing empty enriched_claims.json (no existing claims to preserve)")
        _write_output(out_path, [], family, platform, "none (--no-llm)", api_surface)
        run_stats["duration_seconds"] = round(time.monotonic() - t0, 1)
        run_stats["cache_hits"] = llm_cache.hits
        run_stats["cache_misses"] = llm_cache.misses
        _write_enrichment_report(family, platform, run_stats, "scout-only-explicit",
                                 out_path, reports_root=reports_root)
        return True

    if rehash_only:
        log.info("--rehash-only: re-hashing %d existing enriched claims", len(existing_enriched))
        rehashed = _assign_ids(existing_enriched, family, platform)
        _write_output(out_path, rehashed, family, platform, "rehash-only", api_surface)
        run_stats["claims_final"] = len(rehashed)
        run_stats["duration_seconds"] = round(time.monotonic() - t0, 1)
        run_stats["cache_hits"] = llm_cache.hits
        run_stats["cache_misses"] = llm_cache.misses
        _write_enrichment_report(family, platform, run_stats, "rehash-only",
                                 out_path, reports_root=reports_root)
        return True

    # Preflight: verify at least one LLM endpoint is available before batching.
    preflight = _preflight_check()
    healthy = [k for k, v in preflight.items() if v == "ok"]
    if not healthy:
        log.warning("All LLM endpoints failed preflight: %s", preflight)
        run_stats["preflight"] = preflight
        if existing_enriched:
            log.info(
                "Preserving existing %d enriched claims — preflight failure is transient. "
                "Re-run when LLM is available to refresh.",
                len(existing_enriched),
            )
            run_stats["preserved_existing"] = True
            # TC-08: Check if preserved claims are stale
            if out_path.exists():
                try:
                    stored_data = json.loads(out_path.read_text(encoding="utf-8"))
                    stored_sha = stored_data.get("api_surface_sha", "")
                    current_sha = hashlib.sha256(
                        json.dumps(api_surface, sort_keys=True).encode()
                    ).hexdigest()[:16]
                    if stored_sha and stored_sha != current_sha:
                        log.warning(
                            "Preserved enriched claims are STALE (api_surface changed). "
                            "Re-run enrichment when LLM is available."
                        )
                        run_stats["preserved_stale"] = True
                except (json.JSONDecodeError, OSError):
                    pass
        else:
            log.info("No existing enriched claims to preserve.")
        run_stats["duration_seconds"] = round(time.monotonic() - t0, 1)
        run_stats["cache_hits"] = llm_cache.hits
        run_stats["cache_misses"] = llm_cache.misses
        _write_enrichment_report(family, platform, run_stats, "preflight-failed",
                                 out_path, reports_root=reports_root)
        return False

    run_stats["preflight"] = preflight
    log.info("Preflight passed — healthy endpoint(s): %s", ", ".join(healthy))

    # Build source context ONCE — same for all batches
    clone_dir = _clone_path(family, platform)
    if clone_exists(family, platform):
        log.info("Building source context from clone cache: %s", clone_dir)
        source_context = _build_source_context(clone_dir, low_docstring=low_docstring)
        log.info("Source context: %d chars", len(source_context))
    else:
        log.warning("Clone cache not found at %s — source context will be minimal", clone_dir)
        source_context = "(clone cache not available)"

    # Split classes into batches; iterate until min_coverage met or all batched
    public_classes = [c for c in api_surface if isinstance(c, dict)
                      and not c.get("name", "").startswith("_")
                      and "test" not in c.get("file", "").lower()]
    public_classes = sorted(public_classes, key=lambda c: c.get("name", ""))

    all_batched_claims: list[dict] = list(existing_enriched)  # start with existing

    batches = [public_classes[i:i + batch_size]
               for i in range(0, len(public_classes), batch_size)]

    log.info("Multi-batch enrichment: %d classes in %d batch(es) of %d",
             len(public_classes), len(batches), batch_size)

    all_existing_for_dedup = scout_claims + existing_enriched
    api_names = _extract_api_names(api_surface)
    model_used = "none"

    # --- capability mode: batch-class semantic enrichment ---
    if mode in ("capability", "both"):
        for batch_idx, batch in enumerate(batches):
            # Check if min_coverage already satisfied
            if min_coverage > 0:
                covered = len(all_batched_claims)
                needed = int(min_coverage * len(public_classes))
                if covered >= needed:
                    log.info("Min coverage %.0f%% satisfied after batch %d (%d/%d claims)",
                             min_coverage * 100, batch_idx, covered, len(public_classes))
                    break

            batch_facts = _build_verified_facts(batch)
            sys_prompt, user_prompt = _build_prompt(family, platform, batch_facts, source_context,
                                                    low_docstring=low_docstring)
            log.info("Batch %d/%d: calling LLM for %d classes...",
                     batch_idx + 1, len(batches), len(batch))
            run_stats["batches_attempted"] += 1
            raw_result, batch_model = _llm_call(sys_prompt, user_prompt, cache=llm_cache, cache_extra=_cache_extra)
            if batch_model:
                model_used = batch_model

            if raw_result is None:
                run_stats["batches_failed"] += 1
                log.warning("LLM unavailable at batch %d — stopping early", batch_idx + 1)
                break

            run_stats["batches_succeeded"] += 1
            if not isinstance(raw_result, list):
                raw_claims = raw_result.get("claims", [])
                if not raw_claims and "claims" not in raw_result:
                    # TC-2: LLM returned a non-list dict without a 'claims' key — likely an
                    # error response (e.g. {"error": "rate_limited"}). Log at ERROR so the
                    # operator can see it; do NOT silently treat this as zero claims.
                    log.error(
                        "LLM returned non-list response at batch %d (type=%s, keys=%s)"
                        " — possible rate-limit or error; no claims extracted",
                        batch_idx + 1,
                        type(raw_result).__name__,
                        list(raw_result.keys())[:5],
                    )
                    continue
            else:
                raw_claims = raw_result
            if not raw_claims:
                log.debug("Batch %d returned no claims", batch_idx + 1)
                continue

            run_stats["claims_raw"] += len(raw_claims)
            for claim in raw_claims:
                if not _validate_claim(claim, api_names):
                    run_stats["claims_rejected"] += 1
                    continue
                if _is_duplicate(claim, all_existing_for_dedup):
                    run_stats["claims_deduplicated"] += 1
                    continue
                run_stats["claims_accepted"] += 1
                claim.setdefault("page_role", None)
                all_batched_claims.append(claim)
                all_existing_for_dedup.append(claim)

    # --- member-doc mode: per-class, per-member description generation ---
    # Generates one claim per method/property starting with ClassName.MemberName
    # so that batch_reference.py _build_erc_member_index() can populate table cells.
    if mode in ("member-doc", "both"):
        log.info("Member-doc mode: generating per-member descriptions for %d classes",
                 len(public_classes))
        for cls in public_classes:
            cls_name = cls.get("name", "")
            sys_prompt, user_prompt = _build_member_doc_prompt(
                family, platform, cls, source_context
            )
            log.info("member-doc: calling LLM for class %s...", cls_name)
            run_stats["batches_attempted"] += 1
            raw_result, batch_model = _llm_call(sys_prompt, user_prompt, cache=llm_cache, cache_extra=_cache_extra)
            if batch_model:
                model_used = batch_model
            if raw_result is None:
                run_stats["batches_failed"] += 1
                log.warning("LLM unavailable for class %s — skipping", cls_name)
                continue
            run_stats["batches_succeeded"] += 1
            if not isinstance(raw_result, list):
                raw_claims = raw_result.get("claims", [])
                if not raw_claims and "claims" not in raw_result:
                    log.error(
                        "LLM returned non-list response for class %s (keys=%s)"
                        " — possible error response; no claims extracted",
                        cls_name, list(raw_result.keys())[:5],
                    )
                    continue
            else:
                raw_claims = raw_result
            for claim in raw_claims:
                if not _validate_claim(claim, api_names):
                    continue
                if _is_duplicate(claim, all_existing_for_dedup):
                    continue
                # Member-doc claims are always reference-scoped
                claim["page_role"] = "reference"
                all_batched_claims.append(claim)
                all_existing_for_dedup.append(claim)

    # --- feature mode: high-level capability/install/troubleshoot claims ---
    # Writes to a separate feature_claims.json (additive, does not touch enriched_claims.json)
    if mode == "feature":
        log.info("Feature mode: extracting capability/install/troubleshoot claims")
        feature_out_path = scout_dir / "feature_claims.json"

        # Collect source file paths from clone cache
        source_files: list[str] = []
        if clone_exists(family, platform):
            for p in clone_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in {
                    ".py", ".java", ".cs", ".ts", ".cpp", ".h", ".md", ".txt",
                    ".xml", ".json", ".toml", ".cfg", ".ini"
                }:
                    rel = str(p.relative_to(clone_dir)).replace("\\", "/")
                    if not any(seg in rel.lower() for seg in
                               ("/.git/", "/vendor/", "/node_modules/", "/dist/", "/build/")):
                        source_files.append(rel)
        source_files.sort()

        verified_facts = _build_verified_facts(public_classes)
        sys_prompt, user_prompt = _build_feature_prompt(
            family, platform, verified_facts, source_context, source_files
        )
        log.info("Feature mode: calling LLM with %d source files listed...", len(source_files))
        run_stats["batches_attempted"] += 1
        raw_result, batch_model = _llm_call(sys_prompt, user_prompt, cache=llm_cache, cache_extra=_cache_extra)
        if batch_model:
            model_used = batch_model

        feature_claims: list[dict] = []
        rejected: list[tuple[dict, str]] = []
        source_file_set = set(source_files)

        if raw_result is not None:
            run_stats["batches_succeeded"] += 1
            if not isinstance(raw_result, list):
                raw_claims = raw_result.get("claims", [])
                if not raw_claims and "claims" not in raw_result:
                    log.error(
                        "LLM returned non-list response for feature mode (keys=%s)"
                        " — possible error response; no feature claims extracted",
                        list(raw_result.keys())[:5],
                    )
            else:
                raw_claims = raw_result
            for claim in raw_claims:
                valid, reason = _validate_feature_claim(claim, api_names, source_file_set)
                if not valid:
                    rejected.append((claim, reason))
                    continue
                if _is_duplicate(claim, all_existing_for_dedup + feature_claims):
                    rejected.append((claim, "duplicate"))
                    continue
                # Cap confidence
                if claim.get("confidence", 0) > _FEATURE_CONFIDENCE_CAP:
                    claim["confidence"] = _FEATURE_CONFIDENCE_CAP
                feature_claims.append(claim)
                all_existing_for_dedup.append(claim)
        else:
            run_stats["batches_failed"] += 1
            log.warning("LLM unavailable for feature mode")

        # Assign stable IDs with FRC- prefix
        for fc in feature_claims:
            stable = hashlib.sha256(
                (fc.get("text", "") + "|" + fc.get("kind", "")).encode()
            ).hexdigest()[:8]
            fc["claim_id"] = f"FRC-{family}-{platform}-{stable}"

        # Write feature_claims.json (separate from enriched_claims.json)
        feature_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": model_used,
            "source": "enrich.py (S-37 feature mode)",
            "family": family,
            "platform": platform,
            "claim_count": len(feature_claims),
            "rejected_count": len(rejected),
            "claims": feature_claims,
            "rejected": [
                {"text": c.get("text", "")[:120], "reason": r}
                for c, r in rejected
            ],
        }
        feature_out_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(feature_out_path, json.dumps(feature_payload, indent=2, ensure_ascii=False))

        log.info("Feature mode: %d claims accepted, %d rejected → %s",
                 len(feature_claims), len(rejected), feature_out_path)
        # Feature mode is independent — return early without touching enriched_claims.json
        return True

    validated = _assign_ids(all_batched_claims, family, platform)
    # FIX-10: Post-enrichment source verification — demote claims that say
    # a property is "not consumed"/"stub"/"not forwarded" when the source
    # code actually references that property in non-test files.
    final_claims = _post_validate_stub_claims(validated, clone_dir)
    run_stats["claims_stub_demoted"] = sum(1 for c in final_claims if c.get("stale_warning"))

    # Write protection: refuse to write empty claims when LLM likely failed
    new_claims_added = len(final_claims) - len(existing_enriched)
    if not final_claims and len(batches) > 0:
        log.error(
            "WRITE PROTECTION: LLM enrichment produced 0 claims from %d batches. "
            "Both LLM endpoints may be unavailable. Refusing to write empty enriched_claims.json. "
            "Check LLM endpoint availability and retry.",
            len(batches)
        )
        run_stats["claims_final"] = 0
        run_stats["model_used"] = model_used
        run_stats["duration_seconds"] = round(time.monotonic() - t0, 1)
        run_stats["cache_hits"] = llm_cache.hits
        run_stats["cache_misses"] = llm_cache.misses
        _write_enrichment_report(family, platform, run_stats, "failed",
                                 out_path, reports_root=reports_root)
        _try_write_enrich_metrics(family, platform, _enrich_run_id, _enrich_metrics_events, run_stats, t0)
        return False  # Signal failure instead of success

    if new_claims_added <= 0 and existing_enriched and len(batches) > 0:
        log.warning(
            "LLM enrichment produced no NEW claims (%d batches attempted). "
            "Preserving existing %d claims in enriched_claims.json without metadata update.",
            len(batches), len(existing_enriched)
        )
        run_stats["claims_final"] = len(final_claims)
        run_stats["model_used"] = model_used
        run_stats["preserved_existing"] = True
        run_stats["duration_seconds"] = round(time.monotonic() - t0, 1)
        run_stats["cache_hits"] = llm_cache.hits
        run_stats["cache_misses"] = llm_cache.misses
        _write_enrichment_report(family, platform, run_stats, "partial",
                                 out_path, reports_root=reports_root)
        _try_write_enrich_metrics(family, platform, _enrich_run_id, _enrich_metrics_events, run_stats, t0)
        return True  # Existing claims preserved, skip rewrite to avoid metadata churn

    run_stats["claims_final"] = len(final_claims)
    run_stats["model_used"] = model_used
    run_stats["duration_seconds"] = round(time.monotonic() - t0, 1)
    run_stats["cache_hits"] = llm_cache.hits
    run_stats["cache_misses"] = llm_cache.misses

    coverage_ratio = len(final_claims) / len(public_classes) if public_classes else 0.0
    log.info("Wrote %d enriched claims to %s (coverage %.1f%% of %d public classes)",
             len(final_claims), out_path, coverage_ratio * 100, len(public_classes))

    enrichment_status = "success" if run_stats["batches_failed"] == 0 else "partial"
    _write_output(out_path, final_claims, family, platform, model_used, api_surface,
                  run_stats=run_stats)

    log.info(
        "=== S-37 Summary: model=%s, batches=%d/%d, raw=%d, rejected=%d, "
        "dedup=%d, final=%d, duration=%.1fs ===",
        run_stats["model_used"], run_stats["batches_succeeded"],
        run_stats["batches_attempted"], run_stats["claims_raw"],
        run_stats["claims_rejected"], run_stats["claims_deduplicated"],
        run_stats["claims_final"], run_stats["duration_seconds"],
    )
    _write_enrichment_report(family, platform, run_stats, enrichment_status,
                             out_path, reports_root=reports_root)
    _try_write_enrich_metrics(family, platform, _enrich_run_id, _enrich_metrics_events, run_stats, t0)
    return True


def _write_output(out_path: Path, claims: list, family: str, platform: str,
                  model: str, api_surface: list, *, run_stats=None) -> None:
    """Write enriched_claims.json."""
    api_sha = hashlib.sha256(
        json.dumps(api_surface, sort_keys=True).encode()
    ).hexdigest()[:16]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "source": "enrich.py (S-37)",
        "family": family,
        "platform": platform,
        "api_surface_sha": api_sha,
        "claim_count": len(claims),
        "claims": claims,
    }
    if run_stats:
        payload["run_stats"] = run_stats
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(out_path, json.dumps(payload, indent=2, ensure_ascii=False))

    # Write pipeline state
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from core.manifest import write_step_manifest
    state_path = out_path.parents[2] / ".pipeline_state.json"
    write_step_manifest(state_path, "enrich", {
        "claim_count": len(claims),
        "model": model,
        "api_surface_sha": api_sha,
        "enrichment_status": "success" if claims else "empty",
        "run_stats_summary": {
            "batches": run_stats.get("batches_attempted", 0) if run_stats else 0,
            "rejected": run_stats.get("claims_rejected", 0) if run_stats else 0,
        },
    })


def _write_enrichment_report(family, platform, run_stats, enrichment_status, out_path,
                             *, reports_root=None):
    """Write timestamped enrichment run report."""
    if reports_root is None:
        reports_dir = Path(__file__).resolve().parent.parent.parent.parent.parent / "reports" / "enrichment"
    else:
        reports_dir = Path(reports_root) / "enrichment"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = reports_dir / f"{family}-{platform}-{ts}.json"
    report = {
        "family": family,
        "platform": platform,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "enrichment_status": enrichment_status,
        "output_file": str(out_path),
        "run_stats": run_stats,
    }
    try:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log.info("Enrichment report: %s", report_path)
    except OSError as exc:
        log.warning("Could not write enrichment report: %s", exc)
        return None
    return report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    global _LLM_TIMEOUT_SECONDS
    parser = argparse.ArgumentParser(
        description="S-37 knowledge-enrich: LLM semantic enrichment from scout artifacts.")
    parser.add_argument("family", help="Product family (e.g. '3d')")
    parser.add_argument("platform", help="Platform (e.g. 'python')")
    parser.add_argument("--knowledge-root", default=None,
                        help="Override knowledge root (default: knowledge/)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM call — write empty enriched_claims.json")
    parser.add_argument("--rehash-only", action="store_true",
                        help="Re-hash existing claim IDs without calling LLM")
    parser.add_argument("--batch-size", type=int, default=_DEFAULT_BATCH_SIZE,
                        help=f"Classes per LLM batch (default {_DEFAULT_BATCH_SIZE})")
    parser.add_argument("--min-coverage", type=float, default=_DEFAULT_MIN_COVERAGE,
                        help="Target enriched/class ratio (0=disabled; e.g. 0.30 for 30%%)")
    parser.add_argument("--mode", choices=["capability", "member-doc", "both", "feature"],
                        default="capability",
                        help="capability: semantic feature claims (default); "
                             "member-doc: per-member ClassName.MemberName descriptions; "
                             "feature: high-level capability/install/troubleshoot claims "
                             "(writes to feature_claims.json); "
                             "both: run capability + member-doc modes")
    parser.add_argument("--no-llm-cache", action="store_true", dest="no_llm_cache",
                        help="HARDEN-A4: bypass the content-hash LLM output cache and force "
                             "fresh LLM calls (loudly logged; fresh outputs still refresh the cache)")
    parser.add_argument("--llm-timeout", type=int, default=_LLM_TIMEOUT_SECONDS,
                        help=f"Per-call chat timeout in seconds (default {_LLM_TIMEOUT_SECONDS}, "
                             "matching llm_registry.yaml's professionalize.chat default_timeout). "
                             "Scoped to this module's own call site only -- does not change the "
                             "shared registry default other callers use.")
    args = parser.parse_args()
    _LLM_TIMEOUT_SECONDS = args.llm_timeout

    # TC-03/G-03 (MT009 SEED-04): a require_all() precondition call previously
    # lived here, checking for knowledge/{family}/{platform}/merged/model.yaml
    # and merged/api_surface.json. Those are S-35 (truth-merge) outputs, but
    # S-37 (this script) runs BEFORE S-35 in the documented first-time bootstrap
    # chain (S-34 -> S-37 -> S-35), so on every greenfield product this check
    # unconditionally failed with sys.exit(1) via its own "except SystemExit:
    # raise" -- directly contradicting its adjacent comment ("prereqs is
    # best-effort"). enrich()'s own body (see api_surface_path check below)
    # already validates its true precondition (scout/api_surface.json), so no
    # replacement check is needed here.
    success = enrich(args.family, args.platform, args.knowledge_root,
                     no_llm=args.no_llm,
                     rehash_only=args.rehash_only,
                     batch_size=args.batch_size,
                     min_coverage=args.min_coverage,
                     mode=args.mode,
                     force_llm_regen=args.no_llm_cache)
    status = "PASS" if success else "FAIL"
    print(f"\nKNOWLEDGE-ENRICH: {status}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
