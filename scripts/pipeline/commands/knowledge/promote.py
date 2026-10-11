"""promote.py — Scout-only knowledge promotion: scout/ → merged/ with optional enrichment.

Replaces merge.py.  The dual-source FL merge architecture has been removed.
Knowledge is now produced entirely from within this repo:

    scout/              deterministic tree-sitter extraction (S-34)
    scout/enriched_claims.json   LLM enrichment grounded in api_surface.json (S-37, optional)
    scout/supplemental_claims.json  temporary bridge (one-time FL absorption, delete after S-37 run)

Reads from:
    knowledge/{family}/{platform}/scout/

Writes to:
    knowledge/{family}/{platform}/merged/

Provenance values in merged/claims.json:
    scout         — deterministic tree-sitter extraction (confidence 1.0)
    enriched      — LLM-generated, grounded in api_surface.json (S-37)
    supplemental  — temporary bridge from one-time FL absorption (delete after S-37 runs)

Guard: exits 1 if knowledge/{family}/{platform}/fl/ exists.
The fl/ layer has been removed.  If it reappears, something is wrong.

Usage:
    python scripts/pipeline/commands/knowledge/promote.py {family} {platform}
    python scripts/pipeline/commands/knowledge/promote.py 3d python
    python scripts/pipeline/commands/knowledge/promote.py cells python --knowledge-root /alt/path
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.constants import _TEST_PATH_PATTERNS, _INTERNAL_PATH_PATTERNS
from extraction.formats import _FAMILY_FORMAT_ALLOWLISTS, _FAMILY_PYTHON_PRIMARY_FMT
from lib.class_stats import compute_class_stats
from commands.launch.site_planner import _FAMILY_SUBPKG_LABELS, _ROOT_LABELS
from lib.example_verification.code_fences import normalize_content
from lib.bundle_manifest import (
    BUNDLE_SCHEMA_VERSION,
    GENERATOR_SEMVER,
    compute_bundle_manifest,
    generator_fingerprint,
    verify_bundle_manifest,
)

# scripts/pipeline/commands/knowledge/promote.py -> ... -> repo root (4 parents up)
_PROMOTE_REPO_ROOT = Path(__file__).resolve().parents[4]

# MT074 B13a / R1-6: promote aborts (fails closed) when the enrichment it is about to merge
# retains fewer than this fraction of the enriched (ERC-*) claims already tracked in
# merged/claims.json -- 0 claims (absent/empty/stale input) is the extreme case, a stale
# partial file (1500 -> 100) the sneaky one.  --allow-drop-enrichment overrides.
ENRICHMENT_MIN_RETAINED_RATIO = 0.5


def compute_extractor_config_sha(family: str) -> str:
    """Return a 16-hex-char hash of the family-specific extractor configuration.

    Covers the four per-family dicts that directly affect knowledge model output:
    - _FAMILY_FORMAT_ALLOWLISTS  (formats.py)
    - _FAMILY_PYTHON_PRIMARY_FMT (formats.py)
    - _FAMILY_SUBPKG_LABELS      (site_planner.py)
    - _ROOT_LABELS               (site_planner.py)

    When any of these change for a family, the hash changes.  promote.py writes
    this to model.yaml as ``config_sha``.  stale_detect.py compares it to the
    current hash to detect extractor-config drift (RC-2 fix).

    Limitation: covers only these four dicts, not extraction logic changes.
    """
    config = {
        "format_allowlist": sorted(_FAMILY_FORMAT_ALLOWLISTS.get(family, frozenset())),
        "python_primary_fmt": _FAMILY_PYTHON_PRIMARY_FMT.get(family),
        "subpkg_labels": _FAMILY_SUBPKG_LABELS.get(family, {}),
        "root_label": _ROOT_LABELS.get(family, "core-management"),
    }
    return hashlib.sha256(
        json.dumps(config, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# TF-IDF semantic dedup helpers (TC-KNOW-001)
# ---------------------------------------------------------------------------

_TFIDF_STOPWORDS = frozenset(
    "a about above after again against all am an and any are as at be because "
    "been before being below between both but by can could did do does doing "
    "down during each few for from further get got had has have having he her "
    "here hers herself him himself his how i if in into is it its itself just "
    "let like me might more most my myself no nor not now of off on once only "
    "or other our ours ourselves out over own re same shall she should so some "
    "such than that the their theirs them themselves then there these they this "
    "those through to too under until up us very was we were what when where "
    "which while who whom why will with you your yours yourself yourselves".split()
)

_SEMANTIC_DEDUP_THRESHOLD = 0.90  # cosine > 0.90 → merge


def _tfidf_tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in _TFIDF_STOPWORDS]


def _tfidf_cosine(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    keys = set(vec1) & set(vec2)
    if not keys:
        return 0.0
    dot = sum(vec1[k] * vec2[k] for k in keys)
    mag1 = math.sqrt(sum(v * v for v in vec1.values()))
    mag2 = math.sqrt(sum(v * v for v in vec2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def _semantic_dedup_claims(claims: list[dict]) -> list[dict]:
    """Remove semantically duplicate claims using TF-IDF cosine similarity.

    For pairs with cosine > _SEMANTIC_DEDUP_THRESHOLD (0.90), keeps the claim
    with higher confidence and attaches the other's claim_id as merged_from.
    """
    if len(claims) < 2:
        return claims

    # Build TF-IDF vectors
    texts = [c.get("text", "") for c in claims]
    tokenized = [_tfidf_tokenize(t) for t in texts]

    # IDF
    n = len(tokenized)
    df: dict[str, int] = {}
    for doc in tokenized:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1
    idf = {term: math.log(1 + n / count) for term, count in df.items()}

    # TF-IDF vectors (sparse)
    vectors: list[dict[str, float]] = []
    for doc in tokenized:
        tf = Counter(doc)
        total = len(doc) or 1
        vec = {t: (c / total) * idf.get(t, 0.0) for t, c in tf.items()}
        vectors.append(vec)

    # Kinds exempt from semantic dedup (TF-IDF can't distinguish overloads)
    _EXACT_ONLY_KINDS = frozenset({"api_method", "api_constructor", "api_property",
                                    "format_support"})

    # Find pairs to merge (greedy: higher-confidence claim absorbs lower)
    merged_into: dict[int, int] = {}  # loser_idx -> winner_idx
    for i in range(len(claims)):
        if i in merged_into:
            continue
        for j in range(i + 1, len(claims)):
            if j in merged_into:
                continue
            # Skip semantic dedup for API signature claims — require exact text match
            kind_i = claims[i].get("kind", "")
            kind_j = claims[j].get("kind", "")
            if kind_i in _EXACT_ONLY_KINDS or kind_j in _EXACT_ONLY_KINDS:
                text_i = (claims[i].get("text", "") or claims[i].get("description", "")).strip()
                text_j = (claims[j].get("text", "") or claims[j].get("description", "")).strip()
                if text_i != text_j:
                    continue
            sim = _tfidf_cosine(vectors[i], vectors[j])
            if sim > _SEMANTIC_DEDUP_THRESHOLD:
                ci = claims[i].get("confidence", 0)
                cj = claims[j].get("confidence", 0)
                if ci >= cj:
                    winner, loser = i, j
                else:
                    winner, loser = j, i
                merged_into[loser] = winner

    # Build result
    result: list[dict] = []
    merge_log: list[str] = []
    for idx, claim in enumerate(claims):
        if idx in merged_into:
            winner_idx = merged_into[idx]
            loser_id = claim.get("claim_id", "?")
            winner_id = claims[winner_idx].get("claim_id", "?")
            merge_log.append(f"    {loser_id} -> {winner_id}")
            # Attach merged_from to winner
            winner = claims[winner_idx]
            existing = winner.get("merged_from", [])
            if not isinstance(existing, list):
                existing = [existing]
            if loser_id not in existing:
                existing.append(loser_id)
            winner["merged_from"] = existing
        else:
            result.append(claim)

    if merge_log:
        print(f"  Semantic dedup: merged {len(merge_log)} near-duplicate claim(s) "
              f"(threshold={_SEMANTIC_DEDUP_THRESHOLD})")
        for line in merge_log[:10]:
            print(line)
        if len(merge_log) > 10:
            print(f"    ... and {len(merge_log) - 10} more")

    return result


# ---------------------------------------------------------------------------
# Claim validation (identical to merge.py — kept for safety)
# ---------------------------------------------------------------------------

def _validate_claims(claims, source_label: str) -> list:
    """Validate and filter a claims list. Warns on bad entries.

    HARDEN-words-net (2026-07-22): 6 rounds of adversarial review on
    downstream claim-consuming logic (the claim_id uniqueness/collision
    resolver, and separately the opt-in --semantic-dedup path) found 9 real
    crashes/bugs in total, all tracing to the same root cause — this
    function, the ONE choke point every claims source (scout/enriched/
    supplemental) passes through before entering merged_claims, checked only
    that required KEYS were present, never that VALUES had a sane type:
      - claim_id / text: a non-str value crashed `.startswith()`, `sorted()`
        comparisons, and string slicing in the collision resolver.
      - evidence: a non-list value, or a list containing non-dict elements,
        crashed indexing/`.get()` calls in the same resolver.
      - kind / confidence / description: a non-str `kind` crashed a frozenset
        membership check (unhashable type) in `_semantic_dedup_claims`; a
        non-numeric `confidence` crashed a `>=` comparison there; a non-str
        `description` (reached via the `text or description` fallback when
        `text` is legitimately `""`) crashed `.strip()`.
    Per the review chain's explicit recommendation after round 5 (stop
    patching individual downstream access sites one at a time): every field
    a claim dict carries that ANY downstream consumer assumes a type for is
    now validated or normalized ONCE, here. claim_id/text are identity-
    critical — a malformed value quarantines the whole claim (with a loud
    warning). kind/confidence/description/evidence are supplementary
    quality signals, not identity-critical — a malformed value is coerced to
    a safe default (with a loud warning) rather than discarding the claim.
    """
    if not isinstance(claims, list):
        print(f"  WARNING: {source_label} claims is not a list, skipping")
        return []
    valid = []
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            print(f"  WARNING: {source_label} claim #{i} is not a dict, skipping")
            continue
        if "text" not in c or "kind" not in c:
            print(f"  WARNING: {source_label} claim #{i} missing 'text' or 'kind', skipping")
            continue
        if not isinstance(c.get("text"), str):
            print(f"  WARNING: {source_label} claim #{i} has non-string 'text' "
                  f"({type(c.get('text')).__name__}), skipping")
            continue
        cid = c.get("claim_id")
        if cid is not None and not isinstance(cid, str):
            print(f"  WARNING: {source_label} claim #{i} has non-string claim_id "
                  f"({cid!r}), skipping")
            continue

        c = dict(c)  # normalize on a copy — never mutate the caller's dict
        kind_val = c.get("kind")
        if not isinstance(kind_val, str):
            print(f"  WARNING: {source_label} claim #{i} has non-string 'kind' "
                  f"({type(kind_val).__name__}), normalizing to ''")
            c["kind"] = ""
        # Note: confidence/description use "key in c" (not "value is not
        # None") as the trigger — unlike evidence below, an EXPLICIT
        # `None` value for these two is itself the crash (`None >= 0.95`,
        # `None.strip()`); downstream's `.get("confidence", 0)` only
        # supplies its default when the key is ABSENT, not when it's
        # present-but-None, so a present-None value must be normalized too.
        if "confidence" in c and not isinstance(c.get("confidence"), (int, float)):
            print(f"  WARNING: {source_label} claim #{i} has non-numeric 'confidence' "
                  f"({c.get('confidence')!r}), normalizing to 0")
            c["confidence"] = 0
        if "description" in c and not isinstance(c.get("description"), str):
            print(f"  WARNING: {source_label} claim #{i} has non-string 'description' "
                  f"({type(c.get('description')).__name__}), normalizing to ''")
            c["description"] = ""
        ev = c.get("evidence")
        if ev is not None and not isinstance(ev, list):
            print(f"  WARNING: {source_label} claim #{i} has non-list evidence "
                  f"({type(ev).__name__}), normalizing to []")
            c["evidence"] = []
        elif isinstance(ev, list):
            clean_ev = [e for e in ev if isinstance(e, dict)]
            if len(clean_ev) != len(ev):
                c["evidence"] = clean_ev
        valid.append(c)
    if len(valid) < len(claims):
        print(f"  WARNING: {source_label} {len(claims) - len(valid)} invalid claims filtered")
    return valid


# ---------------------------------------------------------------------------
# Format-claims reconciliation (A-01 + A-02)
# ---------------------------------------------------------------------------

_CONTRADICTION_PHRASES = (
    "read-only",
    "detect-only",
    "not supported",
    "cannot write",
    "cannot export",
    "no write",
    "no export",
)

# G25: ASCII hyphen plus the Unicode hyphen/dash variants seen in real
# enriched claim text (e.g. NON-BREAKING HYPHEN in "open\u2011source"),
# treated as word-continuation characters so a format name is not matched
# as a false substring inside a hyphenated compound word.
_HYPHEN_CHARS = "\\-\u2010\u2011\u2012\u2013\u2014"

_WRITE_DIRECTIONS = frozenset({"export", "both", "readwrite"})


def _reconcile_formats_claims(
    formats_data: list,
    claims: list,
    family: str,
    platform: str,
) -> list:
    """Check for contradictions between formats.json directions and claims text.

    For every format whose direction implies write capability (export / both /
    readwrite), scan the claims list for any claim whose text mentions the
    format name AND one of the contradiction phrases (e.g. "read-only",
    "cannot export").

    Returns a list of dicts::

        {"format": name, "direction": direction, "contradicting_claim": claim_text}

    An empty list means no contradictions were detected.
    Handles a missing / malformed formats_data gracefully (returns []).
    """
    if not isinstance(formats_data, list):
        return []

    contradictions: list = []

    for fmt in formats_data:
        if not isinstance(fmt, dict):
            continue
        raw_name = fmt.get("name", fmt.get("format", ""))
        if not raw_name:
            continue
        direction = fmt.get("direction", "both")
        if direction not in _WRITE_DIRECTIONS:
            continue
        # HARDEN-words-net (2026-07-22): a format already known non-functional
        # (e.g. gated by _apply_foss_gate_overrides in extraction/formats.py)
        # matching a claim that says it's "not supported" is CONFIRMATION,
        # not a contradiction — direction alone (an enum-level signal) can't
        # tell the two cases apart, but functional can.
        if fmt.get("functional") is False:
            continue

        name_lower = raw_name.lower().rstrip("_")

        for claim in claims:
            if not isinstance(claim, dict):
                continue
            claim_text = claim.get("text", "")
            if not isinstance(claim_text, str):
                continue
            claim_lower = claim_text.lower()
            # G25: was a plain substring test (`name_lower in claim_lower`),
            # which false-matched e.g. format "Source" inside the unrelated
            # word "open-source" (or, as confirmed against the real live
            # claims.json that surfaced this bug, "open\u2011source" using a
            # Unicode NON-BREAKING HYPHEN, not ASCII '-'). A plain \b
            # word-boundary regex is NOT enough on its own -- regex \b
            # treats hyphen characters as non-word, so "source" still
            # matches inside a hyphenated compound (the boundary falls at
            # the hyphen). Treat common ASCII and Unicode hyphen/dash
            # variants as word-continuation characters via lookaround so
            # hyphenated compounds are not split into their parts.
            if not re.search(
                rf"(?<![\w{_HYPHEN_CHARS}]){re.escape(name_lower)}(?![\w{_HYPHEN_CHARS}])",
                claim_lower,
            ):
                continue
            for phrase in _CONTRADICTION_PHRASES:
                if phrase in claim_lower:
                    contradictions.append({
                        "format": raw_name,
                        "direction": direction,
                        "contradicting_claim": claim_text,
                    })
                    break  # one match per claim is enough

    return contradictions


# ---------------------------------------------------------------------------
# Artifact validation (FR-13)
# ---------------------------------------------------------------------------

class PromotionValidationError(Exception):
    """Raised when promoted artifacts fail structural validation."""


# Known class/interface names that the scout extractor mistakenly captures as
# format entries.  These are Java class names, not 3D file format identifiers.
_FORMAT_CLASS_ARTIFACTS = frozenset({
    "FILEFORMAT", "FILEFORMATTYPE",
    # Single-letter entries are always interface-name fragments (e.g. IExporter → "I")
})

# Heuristic: a single uppercase letter is never a real format identifier.
_FORMAT_SINGLE_LETTER = re.compile(r"^[A-Z]$")


# ---------------------------------------------------------------------------
# Multi-platform doc fallback: name-inference for trivial getters/setters
# Originally GODOC-GO-001 (Go only); extended to Python/Java/C#/C++.
# ---------------------------------------------------------------------------

def _camel_to_words(name: str) -> str:
    """Split a CamelCase identifier into space-separated lowercase words.

    Examples::

        TextStyle   → text style
        URL         → url
        ReadOnly    → read only
        DefaultCell → default cell
    """
    # Insert space before uppercase letters that follow lowercase/digit
    result = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    # Insert space in runs like 'URLPath' → 'URL Path'
    result = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", result)
    return result.lower()


def _snake_to_words(name: str) -> str:
    """Convert a snake_case identifier to space-separated lowercase words.

    Examples::

        font_name   → font name
        is_bold     → is bold
        get_glyphs  → get glyphs
    """
    return name.replace("_", " ").lower()


def _apply_godoc_fallback(api_surface: list, platform: str) -> int:
    """Infer docstrings for empty-doc methods and properties (in-place).

    Applies deterministic name-based inference for trivial accessor/setter
    patterns so that reference pages no longer render empty description rows.
    Originally Go-only (GODOC-GO-001); extended to Python, Java, C#, C++.

    **Method patterns by platform:**

    Go / C# (net) / C++ (cpp):
    * ``Set{Name}(val)``   → "Sets the {name} value."
    * ``Is{Name}() bool``  → "Returns true if {name} is set."
    * ``Has{Name}() bool`` → "Returns true if {name} is present."
    * ``Get{Name}()``      → "Returns the {name}."
    * ``{Name}() T``       → "Returns the {name}."  (generic Go getter)

    Java (camelCase prefixes):
    * ``set{Name}(val)``   → "Sets the {name} value."
    * ``is{Name}()``       → "Returns true if {name} is set."
    * ``has{Name}()``      → "Returns true if {name} is present."
    * ``get{Name}()``      → "Returns the {name}."

    Python (snake_case prefixes):
    * ``set_{name}(val)``  → "Sets the {name} value."
    * ``is_{name}()``      → "Returns true if {name} is set."
    * ``has_{name}()``     → "Returns true if {name} is present."
    * ``get_{name}()``     → "Returns the {name}."

    **Property inference (all platforms):**
    * writable=True  → "Gets or sets the {name}."
    * writable=False → "Gets the {name}."

    All inferred entries are tagged ``doc_source: "name_inference"`` for
    auditability.  Existing non-empty ``doc`` fields are **never** overwritten.

    Returns the number of members (methods + properties) that received
    inferred documentation.
    """
    # Platforms that use PascalCase accessors (same as original Go logic)
    _PASCAL_PLATFORMS = {"go", "net", "cpp"}
    # Platforms that use camelCase accessors (Java, TypeScript)
    _CAMEL_PLATFORMS = {"java", "typescript"}
    # Platforms that use snake_case accessors (Python, Rust — note Rust
    # getters are bare `name()` without a get_ prefix, so only set_/is_
    # inference applies)
    _SNAKE_PLATFORMS = {"python", "rust"}

    if platform not in _PASCAL_PLATFORMS | _CAMEL_PLATFORMS | _SNAKE_PLATFORMS:
        return 0

    count = 0

    for cls in api_surface:
        # ------------------------------------------------------------------
        # Method inference
        # ------------------------------------------------------------------
        for method in cls.get("methods", []):
            if method.get("doc"):
                continue  # Never overwrite existing docs

            name = method.get("name", "")
            return_type = (method.get("return_type") or "").strip()
            n_params = len(method.get("params") or [])

            inferred: str | None = None

            if platform in _PASCAL_PLATFORMS:
                # PascalCase: Go / C# / C++
                if name.startswith("Set") and len(name) > 3 and n_params >= 1:
                    words = _camel_to_words(name[3:])
                    inferred = f"Sets the {words} value."
                elif name.startswith("Get") and len(name) > 3 and n_params == 0 and return_type:
                    words = _camel_to_words(name[3:])
                    inferred = f"Returns the {words}."
                elif name.startswith("Is") and len(name) > 2 and n_params == 0:
                    words = _camel_to_words(name[2:])
                    inferred = f"Returns true if {words} is set."
                elif name.startswith("Has") and len(name) > 3 and n_params == 0:
                    words = _camel_to_words(name[3:])
                    inferred = f"Returns true if {words} is present."
                elif (platform == "go" and n_params == 0
                      and return_type and return_type not in ("void", "error")):
                    # Generic Go getter: Name() T (no Get prefix needed)
                    words = _camel_to_words(name)
                    inferred = f"Returns the {words}."

            elif platform in _CAMEL_PLATFORMS:
                # camelCase: Java
                if name.startswith("set") and len(name) > 3 and name[3].isupper() and n_params >= 1:
                    words = _camel_to_words(name[3:])
                    inferred = f"Sets the {words} value."
                elif name.startswith("get") and len(name) > 3 and name[3].isupper() and n_params == 0:
                    words = _camel_to_words(name[3:])
                    inferred = f"Returns the {words}."
                elif name.startswith("is") and len(name) > 2 and name[2].isupper() and n_params == 0:
                    words = _camel_to_words(name[2:])
                    inferred = f"Returns true if {words} is set."
                elif name.startswith("has") and len(name) > 3 and name[3].isupper() and n_params == 0:
                    words = _camel_to_words(name[3:])
                    inferred = f"Returns true if {words} is present."

            elif platform in _SNAKE_PLATFORMS:
                # snake_case: Python
                if name.startswith("set_") and len(name) > 4 and n_params >= 1:
                    words = _snake_to_words(name[4:])
                    inferred = f"Sets the {words} value."
                elif name.startswith("get_") and len(name) > 4 and n_params == 0:
                    words = _snake_to_words(name[4:])
                    inferred = f"Returns the {words}."
                elif name.startswith("is_") and len(name) > 3 and n_params == 0:
                    words = _snake_to_words(name[3:])
                    inferred = f"Returns true if {words} is set."
                elif name.startswith("has_") and len(name) > 4 and n_params == 0:
                    words = _snake_to_words(name[4:])
                    inferred = f"Returns true if {words} is present."

            if inferred:
                method["doc"] = inferred
                method["doc_source"] = "name_inference"
                count += 1

        # ------------------------------------------------------------------
        # Property inference (all platforms)
        # ------------------------------------------------------------------
        for prop in cls.get("properties", []):
            if prop.get("doc"):
                continue  # Never overwrite existing docs

            pname = prop.get("name", "")
            if not pname:
                continue

            # Convert property name to human-readable words
            if "_" in pname:
                words = _snake_to_words(pname)
            else:
                words = _camel_to_words(pname)

            if prop.get("writable"):
                inferred = f"Gets or sets the {words}."
            else:
                inferred = f"Gets the {words}."

            prop["doc"] = inferred
            prop["doc_source"] = "name_inference"
            count += 1

    return count


def _is_invalid_format_entry(name: str) -> bool:
    """Return True if a formats.md row name looks like a class artifact, not a format."""
    upper = name.strip().upper()
    if upper in _FORMAT_CLASS_ARTIFACTS:
        return True
    if _FORMAT_SINGLE_LETTER.match(upper):
        return True
    return False


# Java: import lines must not have hyphens between package components
_JAVA_IMPORT_HYPHEN = re.compile(r"^\s*import\s+[\w.]*-[\w.*]+")
# .NET: using lines should not contain hyphens (hyphens are illegal in C# namespaces)
_DOTNET_USING_HYPHEN = re.compile(r"^\s*using\s+[\w.]*-[\w.]+")
# Python: import/from lines with hyphens in module names
_PYTHON_IMPORT_HYPHEN = re.compile(r"^\s*(?:import|from)\s+[\w.]*-[\w.]+")


def validate_promoted_artifacts(family: str, platform: str, merged_dir: Path) -> list[str]:
    """Validate formats.md and install.md in merged_dir.

    Returns a list of human-readable error strings.  An empty list means all
    validations passed.  Callers should raise PromotionValidationError if the
    list is non-empty.
    """
    errors: list[str] = []

    # --- formats.md ---
    fmt_path = merged_dir / "formats.md"
    if fmt_path.exists():
        for lineno, raw_line in enumerate(fmt_path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            # Skip header, separator, and empty lines
            if not line or line.startswith("#") or line.startswith("|---") or "Format" in line:
                continue
            if not line.startswith("|"):
                continue
            parts = [p.strip() for p in line.split("|")]
            # Table row: | Format | Import | Export |  -> parts[1] is the format name
            if len(parts) < 2:
                continue
            entry_name = parts[1].strip()
            if not entry_name:
                continue
            if _is_invalid_format_entry(entry_name):
                errors.append(
                    f"formats.md:{lineno}: invalid format entry '{entry_name}' "
                    f"(looks like a class/interface name, not a file format identifier) "
                    f"in {fmt_path}"
                )

    # --- install.md ---
    install_path = merged_dir / "install.md"
    if install_path.exists():
        content = install_path.read_text(encoding="utf-8")
        for lineno, raw_line in enumerate(content.splitlines(), 1):
            if platform == "java":
                if _JAVA_IMPORT_HYPHEN.match(raw_line):
                    errors.append(
                        f"install.md:{lineno}: invalid Java import (hyphens are illegal "
                        f"in Java package names): '{raw_line.strip()}' in {install_path}"
                    )
            elif platform in ("net", "dotnet"):
                if _DOTNET_USING_HYPHEN.match(raw_line):
                    errors.append(
                        f"install.md:{lineno}: invalid .NET using directive (hyphens are "
                        f"illegal in C# namespace names): '{raw_line.strip()}' in {install_path}"
                    )
            elif platform == "python":
                if _PYTHON_IMPORT_HYPHEN.match(raw_line):
                    errors.append(
                        f"install.md:{lineno}: invalid Python import (hyphens are illegal "
                        f"in Python module names): '{raw_line.strip()}' in {install_path}"
                    )

    return errors


# ---------------------------------------------------------------------------
# Module/topic assignment (D-4 / TC-MT040-43)
# ---------------------------------------------------------------------------
#
# batch_reference.py's _derive_group_key() (the grouped reference index) and
# site_planner.py's detect_clusters() (the docs/KB capability clusters) each
# independently derived a class's "topic" from its file's directory path --
# two separately-maintained implementations of the same underlying question,
# both an accident of repo layout rather than a real signal. For a flat-src
# repo with no subdirectories at all (e.g. pdf/typescript's ~300 files
# directly under src/) that path signal doesn't exist, so both consumers
# collapsed everything into one group ("Core API" / a single degenerate
# cluster) -- G-TS-01.
#
# This section computes ONE answer at promote time -- module_key (a stable
# lowercase identifier) and module_label (a human display label) -- written
# onto every merged api_surface.json entry, via compute_module_assignment(),
# using an ordered strategy:
#
#   (a) informative directory segment relative to the package's own common
#       root, derived from the api_surface data itself (the longest shared
#       directory prefix across every entry's file path) rather than a
#       hard-coded per-platform path pattern. Today's working behavior for
#       nested layouts (e.g. 3d/typescript's .../formats/collada/*.ts ->
#       module_key "formats").
#   (b) export-group named by the entry-point/barrel language adapter (e.g.
#       a TypeScript `export * as Forms from './forms.js'`), via
#       lang.<language>.export_groups() when that (optional) adapter
#       capability is implemented.
#   (c) a family-agnostic file-stem/identifier keyword table for flat
#       layouts (G-TS-01 / TC-MT040-18) -- presentational vocabulary, never
#       a claim about what a class does; an unmatched identifier degrades
#       to (d), never to a fabricated group.
#   (d) "core" / "Core API" -- the fallback when nothing above matches.
#
# batch_reference._derive_group_key() and site_planner.detect_clusters()
# both read module_key/module_label when present and fall back to their own
# existing directory-path logic when absent (older knowledge that has not
# been re-promoted through this code) -- so no shipped product's grouped
# index or site plan changes until its own next knowledge promotion.
MODULE_ASSIGNMENT_VERSION = 1

# (c) G-TS-01 / TC-MT040-18: WHOLE-WORD tokens checked (in this priority
# order, first match wins) against every camelCase/snake/kebab-tokenized
# word of an entry's own name and its source file's stem (see
# _tokenize_identifier() below) -- never a raw substring-of-string test.
# Substring matching was tried first and rejected: it false-matched, e.g.,
# "form" inside "FileFormat"/"registerFormat" (a real, live false positive
# against 3d/typescript's actual classes -- "form" is literally the first
# four characters of "format"), the same class of mid-word substring-
# collision bug already fixed elsewhere in this repo (body_impact's
# keyword matcher, commit c95b448811). Deliberately narrow and specific
# (compound PDF-domain terms rather than bare generic English words like
# "form"/"image"/"table"/"cell"/"text") for the same reason: a generic
# word is far more likely to coincidentally match an unrelated product's
# class name (verified live against cells/typescript's real spreadsheet
# classes -- "Cell", "Font", "ImageInfo" -- which must NOT be swept into
# PDF-flavored groups just because they share a common English word). This
# is display vocabulary for otherwise-ungroupable flat layouts, not a
# claim about behavior -- an identifier that matches nothing degrades to
# (d), never to a fabricated group. A few narrow, genuinely cross-domain
# terms (e.g. "hyperlink", "encrypt") may still coincidentally match an
# unrelated product's class; that residual is an accepted, documented
# tradeoff of a family-agnostic table, not a claim of perfect precision.
_STEM_KEYWORD_GROUPS: "list[tuple[str, tuple[str, ...]]]" = [
    ("forms", ("acroform", "formfield", "xfa")),
    ("annotations", ("annotation", "annotations", "annot", "markup", "stamp", "stamps")),
    ("compliance", ("pdfa", "pdfua", "compliance", "verapdf")),
    ("conversion", ("docx", "epub", "markdown", "tiff", "raster", "fdf", "xfdf",
                     "exporter", "importer", "converter", "conversion")),
    ("images", ("jpeg", "jpg")),
    ("text", ("glyph", "glyphs")),
    ("structure", ("outline", "outlines", "bookmark", "bookmarks", "toc")),
    ("security", ("encrypt", "encryption", "decrypt", "decryption", "signature",
                   "permission", "permissions")),
    ("navigation", ("hyperlink", "hyperlinks", "destination", "destinations")),
    ("tables", ("tableabsorber",)),
    ("attachments", ("attachment", "attachments", "fileattach")),
    ("redaction", ("redact", "redaction", "redactions")),
]

_STEM_GROUP_LABELS: dict[str, str] = {
    "forms": "Forms",
    "annotations": "Annotations",
    "compliance": "Compliance",
    "conversion": "Conversion",
    "images": "Images",
    "text": "Text",
    "structure": "Structure",
    "security": "Security",
    "navigation": "Navigation",
    "tables": "Tables",
    "attachments": "Attachments",
    "redaction": "Redaction",
}


def _title_case_module_key(key: str) -> str:
    """Human display label for a raw module key, e.g. 'annotations' -> 'Annotations',
    'javascript-extensions' -> 'Javascript Extensions'.

    MT074-2026-09-25-GIS-NET-LAUNCH-AND-READINESS-GATE-HARDENING: this used to be a
    naive replace-separators-then-.title() with no camelCase-boundary splitting, so a
    multi-word key with NO separator at all (e.g. gis/net's real "spatialreferencing"
    subpackage, extracted via _dir_segment_module_key's `.lower()`) produced the
    unsplit "Spatialreferencing" instead of "Spatial Referencing" -- confirmed live
    bootstrapping gis/net's site plan, which crashed on it downstream (a different,
    already-camelCase-aware splitter in site_planner.py never got a chance to run,
    because this already-lowercased module_label took priority as a
    class_label_override). Delegates to the same _tokenize_identifier() this module
    already uses for keyword matching (strategy (c) below) -- it splits camelCase
    boundaries AND separators uniformly, so this fix also applies to any future
    single-word-no-separator directory name, not just this one case.
    """
    words = _tokenize_identifier(key)
    return " ".join(w.capitalize() for w in words) if words else "Core API"


def _common_dir_prefix(file_paths: list) -> str:
    """Return the longest common DIRECTORY prefix shared by every non-empty
    path in *file_paths* (segment-wise, never a partial segment), or "" if
    there is none (including a genuinely flat layout, or empty input). The
    file's own basename is never considered part of the prefix.
    """
    dir_parts = []
    for fp in file_paths:
        if not fp:
            continue
        norm = str(fp).replace("\\", "/")
        parts = norm.split("/")[:-1]
        dir_parts.append(parts)
    if not dir_parts:
        return ""
    common: list = []
    for seg_group in zip(*dir_parts):
        if len(set(seg_group)) == 1:
            common.append(seg_group[0])
        else:
            break
    return "/".join(common)


def _dir_segment_module_key(file_path: str, common_prefix: str) -> "str | None":
    """(a) Return the first informative directory segment of *file_path*
    once *common_prefix* (see _common_dir_prefix) is stripped, or None when
    the file sits directly at (or above) that common root -- callers must
    cascade to the next strategy in that case, never default to "core"
    here directly (a class under a keyword-matchable flat file still
    deserves a chance at strategy (c) first).
    """
    if not file_path:
        return None
    norm = str(file_path).replace("\\", "/")
    if common_prefix:
        prefix = common_prefix + "/"
        if norm.startswith(prefix):
            norm = norm[len(prefix):]
    parts = norm.split("/")
    if len(parts) < 2:
        return None
    segment = parts[0]
    if not segment or "." in segment:
        return None
    # Flatten format-detector sub-sub-packages (fbx/, obj/, stl/, collada/,
    # ...) under one "formats" group -- mirrors site_planner's existing
    # "formats" ancestor-flattening for nested per-format directories.
    if segment.lower() == "formats" and len(parts) > 2:
        return "formats"
    return segment.lower()


def _dir_segment_original_case(file_path: str, common_prefix: str) -> "str | None":
    """MT074-2026-09-25: identical extraction to _dir_segment_module_key() above,
    but WITHOUT the final `.lower()` -- used only for label generation, so
    _title_case_module_key()'s camelCase-boundary splitting (via
    _tokenize_identifier) has real case information to work with. module_key
    itself must stay a stable lowercase identifier (its own docstring); this
    sibling function exists so the label path isn't forced to derive words
    from an already-lowercased string that has lost its word boundaries."""
    if not file_path:
        return None
    norm = str(file_path).replace("\\", "/")
    if common_prefix:
        prefix = common_prefix + "/"
        if norm.startswith(prefix):
            norm = norm[len(prefix):]
    parts = norm.split("/")
    if len(parts) < 2:
        return None
    segment = parts[0]
    if not segment or "." in segment:
        return None
    if segment.lower() == "formats" and len(parts) > 2:
        return "formats"
    return segment


_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WORD_SEP_RE = re.compile(r"[_\-\s]+")


def _tokenize_identifier(text: str) -> "list[str]":
    """Split an identifier or file stem into lowercase WHOLE words on
    camelCase boundaries and ``_``/``-``/whitespace separators, e.g.
    ``"registerFormat"`` -> ``["register", "format"]``,
    ``"docx-export"`` -> ``["docx", "export"]``. Used so keyword matching
    below compares whole words, never a substring spanning part of one word
    (see _STEM_KEYWORD_GROUPS' docstring for why that distinction matters).
    """
    if not text:
        return []
    spaced = _CAMEL_BOUNDARY_RE.sub(" ", text)
    spaced = _WORD_SEP_RE.sub(" ", spaced)
    return [w.lower() for w in spaced.split() if w]


def _keyword_group_for_stem(*texts: str) -> "str | None":
    """(c) Return the first matching G-TS-01/TC-MT040-18 keyword group for
    any of *texts* (checked in _STEM_KEYWORD_GROUPS priority order), by
    exact whole-word match against each text's tokenized words (see
    _tokenize_identifier()), or None if nothing matches -- callers must
    then fall back to (d), never guess.
    """
    tokens: set = set()
    for t in texts:
        tokens.update(_tokenize_identifier(t))
    if not tokens:
        return None
    for group, keywords in _STEM_KEYWORD_GROUPS:
        if tokens.intersection(keywords):
            return group
    return None


def _barrel_export_groups(family: str, platform: str) -> "dict[str, str] | None":
    """(b) Best-effort {exported_name: group_label} map from the language
    adapter's barrel/entry-point (e.g. TypeScript's `export * as Forms from
    './forms.js'`), or None when unavailable -- no local clone, the
    platform's adapter doesn't implement this optional capability, or the
    adapter found no grouped re-exports at all (the common case). Never
    raises; never returns partial/fabricated data.
    """
    try:
        from extraction import lang
        from extraction.tree_helpers import PLATFORM_TO_LANG
        from extraction.package_root import detect_package_root
        from core.clone_cache import clone_path, clone_exists
    except Exception:
        return None

    language = PLATFORM_TO_LANG.get(platform, platform)
    # "javascript" has no dedicated adapter module -- scout-time code
    # (extraction/api_surface.py) already treats typescript/javascript
    # identically via lang.typescript; mirror that here.
    lang_mod = lang.get("typescript") if language == "javascript" else lang.get(language)
    export_groups_fn = getattr(lang_mod, "export_groups", None) if lang_mod else None
    if export_groups_fn is None:
        return None

    try:
        if not clone_exists(family, platform):
            return None
        repo = clone_path(family, platform)
        pkg_root = detect_package_root(repo, platform)
        return export_groups_fn(repo, pkg_root)
    except Exception:
        return None


def compute_module_assignment(api_surface: list, family: str, platform: str) -> None:
    """Write module_key/module_label onto every entry in *api_surface*, in
    place, using the ordered (a)/(b)/(c)/(d) strategy documented above.
    Safe to call on any list (including an empty one); never raises.
    """
    if not isinstance(api_surface, list):
        return

    file_paths = [e.get("file", "") for e in api_surface if isinstance(e, dict)]
    common_prefix = _common_dir_prefix(file_paths)
    export_groups = _barrel_export_groups(family, platform)  # (b), computed once

    for entry in api_surface:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "") or ""
        file_path = entry.get("file", "") or ""

        subpkg = _dir_segment_module_key(file_path, common_prefix)  # (a)
        if subpkg:
            entry["module_key"] = subpkg
            # MT074: label from the ORIGINAL-cased segment, not the already-
            # lowercased module_key -- see _dir_segment_original_case()'s docstring.
            subpkg_raw = _dir_segment_original_case(file_path, common_prefix) or subpkg
            entry["module_label"] = _title_case_module_key(subpkg_raw)
            continue

        if export_groups and name in export_groups:  # (b)
            group = export_groups[name]
            entry["module_key"] = group.lower()
            entry["module_label"] = _title_case_module_key(group)
            continue

        stem = Path(file_path).stem if file_path else ""
        keyword_group = _keyword_group_for_stem(name, stem)  # (c)
        if keyword_group:
            entry["module_key"] = keyword_group
            entry["module_label"] = _STEM_GROUP_LABELS[keyword_group]
            continue

        entry["module_key"] = "core"  # (d)
        entry["module_label"] = "Core API"


# ---------------------------------------------------------------------------
# api_surface.md generator (ported from merge.py unchanged)
# ---------------------------------------------------------------------------

def _generate_api_surface_md(api_list, family: str, model: dict, out_dir: Path) -> None:
    """Generate human-readable api_surface.md from merged/api_surface.json."""
    special = {"3d": "3D"}
    display = special.get(family, family.title())
    lines = [
        f"# API Surface — Aspose.{display}",
        f"<!-- Generated by promote.py from merged/api_surface.json -->",
        f"<!-- repo_sha: {model.get('repo_sha', 'unknown')} -->",
        f"<!-- bundle_id: {model.get('bundle_id', 'unknown')} -->",
        "",
    ]

    classes = sorted(api_list, key=lambda c: c.get("name", "")) if isinstance(api_list, list) else []

    for cls in classes:
        name = cls.get("name", "")
        if not name:
            continue
        kind = cls.get("kind", "class_definition")
        if kind == "function" or name.startswith("test_"):
            continue

        doc = cls.get("doc", "").strip()
        bases = cls.get("bases", [])

        lines.append(f"## {name}")
        modifiers = []
        if cls.get("is_static"):
            modifiers.append("static")
        if cls.get("is_abstract"):
            modifiers.append("abstract")
        if cls.get("is_sealed"):
            modifiers.append("sealed")
        if modifiers:
            lines.append(f"**Modifiers**: {', '.join(modifiers)}")
        if doc:
            lines.append(f"**Docstring**: {doc}")
        if bases:
            lines.append(f"**Bases**: {', '.join(bases)}")

        methods = [m for m in cls.get("methods", [])
                   if isinstance(m, dict) and not m.get("name", "").startswith("_")]
        if methods:
            lines.append("**Methods**:")
            for m in methods:
                mname = m.get("name", "")
                params = ", ".join(p.get("name", "") for p in m.get("params", [])
                                  if isinstance(p, dict))
                ret = m.get("return_type", "")
                sig = f"{mname}({params})"
                if ret:
                    sig += f" -> {ret}"
                lines.append(f"- `{sig}`")
        else:
            lines.append("**Methods**: _none_")

        props = cls.get("properties", [])
        if props:
            lines.append("**Properties**:")
            for p in props:
                if not isinstance(p, dict):
                    continue
                pname = p.get("name", "")
                ptype = p.get("type", "Any")
                lines.append(f"- `{pname}: {ptype}`")

        enums = cls.get("enum_members", [])
        if enums:
            lines.append("**Enum values**:")
            for e in enums:
                ename = e.get("name", e) if isinstance(e, dict) else str(e)
                lines.append(f"- `{ename}`")

        lines.append("")

    md_text = "\n".join(lines) + "\n"
    (out_dir / "api_surface.md").write_text(md_text, encoding="utf-8")
    # MT067-2026-09-10 TC-03/TC-07 (found while pilot-verifying on barcode/python):
    # `classes` here is the full sorted api_list including function-kind entries --
    # the "kind == function" skip happens per-entry inside the loop above, after this
    # count would otherwise be taken. Same RC3 mislabeling class as merge_report.md.
    print(f"  api_surface.md: {compute_class_stats(api_list)['total_declared']} classes, {len(md_text)} bytes")


# ---------------------------------------------------------------------------
# Snippet promotion (scout-only, no FL merging)
# ---------------------------------------------------------------------------

def _promote_snippets(scout_dir: Path, merged_dir: Path) -> int:
    """Copy scout/snippets/ to merged/snippets/, filtering to public API classes only."""
    scout_snip = scout_dir / "snippets"
    merged_snip = merged_dir / "snippets"

    if not (scout_snip / "snippets_index.json").exists():
        print("  Snippets: none available")
        return 0

    # Build public class name set for filtering
    _public_class_names: set = set()
    api_surface_path = merged_dir / "api_surface.json"
    if api_surface_path.exists():
        try:
            _api_list = json.loads(api_surface_path.read_text(encoding="utf-8"))
            for _c in _api_list:
                if not isinstance(_c, dict) or _c.get("kind") == "function":
                    continue
                _name = _c.get("name", "")
                if not _name or _name.startswith("_"):
                    continue
                _file = _c.get("file", "")
                if any(p in _file for p in _TEST_PATH_PATTERNS):
                    continue
                if any(p in _file for p in _INTERNAL_PATH_PATTERNS):
                    continue
                _public_class_names.add(_name)
        except (json.JSONDecodeError, OSError):
            pass

    merged_snip.mkdir(parents=True, exist_ok=True)

    try:
        scout_index: list = json.loads(
            (scout_snip / "snippets_index.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        scout_index = []

    merged_index = []
    for i, entry in enumerate(scout_index, 1):
        if not isinstance(entry, dict):
            continue
        src_file = entry.get("file", "")
        merged_entry = dict(entry)
        merged_entry["id"] = f"snippet_{i:03d}"
        merged_entry["provenance"] = "scout"
        # C6 (MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION): "verify at the
        # source" -- a deterministic content-hash proof, computed here (no execution --
        # promote() runs under acquire_regen_lock with an atomic staging swap, and 6
        # test_promote_*.py suites call it for real). sha256_norm lets a page's own code
        # block inherit this snippet's proof via an exact-hash lookup even after cosmetic
        # drift (indentation, line endings) -- see lib/example_verification/code_fences.py
        # and audit/snippets.py's rewritten verify_snippet_coverage.
        #
        # Independent-reviewer finding, fixed here: this must hash THIS run's scout file
        # (`scout_snip / src_file`), gated on the exact same condition that triggers the
        # copy below -- never the merged-dir copy target. promote_atomic() seeds the
        # staging merged/ dir via shutil.copytree of the PRIOR promotion's output before
        # calling promote() (a stale-but-still-present file), and snippet filenames are
        # purely positional (snippet_{n:03d}, reused run-over-run for different content)
        # -- so checking `(merged_snip / src_file).exists()` could stamp a hash for
        # leftover content this run never actually copied, if this run's scout is
        # missing a file the index still references.
        if src_file and (scout_snip / src_file).exists():
            shutil.copy2(scout_snip / src_file, merged_snip / src_file)
            try:
                _snippet_text = (scout_snip / src_file).read_text(encoding="utf-8")
                merged_entry["code_sha256"] = {
                    "exact": hashlib.sha256(_snippet_text.encode("utf-8")).hexdigest(),
                    "norm": hashlib.sha256(
                        normalize_content(_snippet_text).encode("utf-8")).hexdigest(),
                }
            except (OSError, UnicodeDecodeError):
                pass
        if _public_class_names:
            merged_entry["classes_used"] = [
                c for c in merged_entry.get("classes_used", [])
                if c in _public_class_names
            ]
        merged_index.append(merged_entry)

    (merged_snip / "snippets_index.json").write_text(
        json.dumps(merged_index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Snippets: {len(merged_index)} (from scout)")
    return len(merged_index)


# ---------------------------------------------------------------------------
# Post-promote execution-proof sweep
# (MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION/TC-06)
# ---------------------------------------------------------------------------

# platform -> a fence-tag spelling that is (a) in
# lib.example_verification.registry.PLATFORM_CONTRACT[platform].fence_tags and
# (b) canonicalizes to a tag that is ALSO in that same set, so
# verify_markdown()'s own `own_blocks` filter (api.py: `(b.canonical_lang or
# b.lang) in own_tags`) accepts the single synthetic block this sweep builds.
# Kept as an explicit table rather than `sorted(contract.fence_tags)[0]` --
# alphabetical-first happens to work for all five today (confirmed by hand:
# "c#" for net, "rs" for rust, "c++" for cpp all canonicalize back into their
# own fence_tags set) but is an accident of spelling, not a guarantee; a
# future sixth fence-tag spelling added to registry.py could silently pick a
# tag api.py's own canonicalizer maps to something outside the set. An
# explicit table makes that failure mode structurally impossible to hit by
# accident.
_SWEEP_FENCE_TAG: dict[str, str] = {
    "go": "go", "net": "csharp", "java": "java", "rust": "rust", "cpp": "cpp",
}


def sweep_snippet_execution_proof(
    family: str, platform: str, knowledge_root=None, *, allow_acquire: bool = False,
) -> dict:
    """Verify every already-hashed entry in this product's merged
    snippets_index.json through lib/example_verification and stamp a real
    ``execution_proof`` onto each entry it can honestly verify -- closing the
    "post-promote proof sweep" MT065's own C6 taskcard disclosed as "deferred,
    no sweep mechanism exists yet" (0 of the portfolio's 2,559 snippet-index
    entries had ``execution_proof`` before this function existed).

    DESIGN DECISION (disclosed, per this taskcard's own instructions): this is
    a SEPARATE, explicitly-invoked sweep -- ``promote.py --verify-snippets``
    below -- not wired into the tail of ``_promote_snippets()``/``promote()``
    itself. Real verification above tier 1 (compile/execute) is slow and
    toolchain-dependent (a real go/dotnet/java/rust/cpp toolchain, or a real
    python/typescript package install); ``promote()`` runs on every knowledge
    regeneration, portfolio-wide, in CI, so folding a slow/flaky acquire step
    into its default path would make ordinary knowledge promotion slow and
    non-deterministic. An explicit, opt-in sweep can be run once, on its own
    schedule, with its own time budget -- the same "opt-in acquire" posture
    ``Policy.allow_acquire`` already encodes for the rest of this package.

    SCOPE (disclosed limitation, not silently hidden): only the five
    LanguageRunner-protocol platforms (go/net/java/rust/cpp --
    ``lib.example_verification.registry.RUNNER_CLASS_NAMES``) are swept here,
    at tier 1 (syntax-only, ``allow_acquire=False`` by default -- matches
    every one of those five platforms' ``PLATFORM_CONTRACT.offline_tier``
    today, so this never silently blocks on a missing toolchain or reaches
    the network). python/typescript are skipped with an honest note, never a
    fabricated proof: their runners are whole-candidate S-120-ported
    functions (``runners/python.py``/``runners/typescript.py``) that read a
    real file and always attempt to acquire/execute a real environment
    regardless of ``Policy`` -- ``api.py``'s own ``WHOLE_CANDIDATE_PLATFORMS``
    docstring already reserves retrofitting those two onto ``BaseRunner``
    (the change that would let them honor ``allow_acquire=False``) for a
    later taskcard. Sweeping them today would mean either fabricating a tier
    for verification never actually performed, or silently installing
    packages during what this function's own default promises is an offline,
    syntax-only sweep -- both violate this package's "never fabricate proof"
    contract (result.py's own status vocabulary has no "unverified but
    reported as passing" state for exactly this reason), so they are skipped
    with `skipped_no_runner` and a `note` in the returned summary instead.

    IDEMPOTENT: recomputes the same ``execution_proof`` dict for unchanged
    inputs (same snippet file content, same knowledge clone_head, same
    ``RUNNERS_MODULE_VERSION``) and only rewrites the index file when at
    least one entry's stamped proof actually changed -- running this twice in
    a row is a guaranteed no-op on disk, never a duplicate or corrupted entry.

    Returns a summary dict: ``{"family", "platform", "total", "swept",
    "skipped_no_runner", "skipped_no_hash", "note"?, "error"?}``.
    """
    from lib.example_verification.api import verify_markdown
    from lib.example_verification.policy import Policy, ProductContext
    from lib.example_verification.registry import RUNNER_CLASS_NAMES

    base = (Path(knowledge_root) if knowledge_root else Path("knowledge")) / family / platform
    index_path = base / "merged" / "snippets" / "snippets_index.json"

    summary: dict = {
        "family": family, "platform": platform,
        "total": 0, "swept": 0, "skipped_no_runner": 0, "skipped_no_hash": 0,
    }

    if not index_path.exists():
        summary["error"] = f"no snippets_index.json at {index_path}"
        return summary

    try:
        entries = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        summary["error"] = f"could not read snippets_index.json: {exc}"
        return summary

    if not isinstance(entries, list):
        summary["error"] = "snippets_index.json is not a list"
        return summary

    summary["total"] = len(entries)

    if platform not in RUNNER_CLASS_NAMES:
        # python/typescript (whole-candidate) or a platform with no runner at
        # all -- an honest, disclosed skip, never a fabricated proof. See
        # this function's own docstring ("SCOPE") for why.
        summary["skipped_no_runner"] = len(entries)
        summary["note"] = (
            f"platform {platform!r} has no LanguageRunner-protocol runner this "
            "sweep can drive offline (see sweep_snippet_execution_proof's own "
            "docstring, section SCOPE) -- skipped, not fabricated"
        )
        return summary

    fence_tag = _SWEEP_FENCE_TAG.get(platform, platform)
    policy = Policy.for_platform(platform, allow_acquire=allow_acquire)
    product = ProductContext.from_knowledge(family, platform)
    snippets_dir = index_path.parent

    changed = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code_sha = entry.get("code_sha256")
        if not isinstance(code_sha, dict) or not code_sha.get("norm"):
            # Not yet hashed by _promote_snippets (e.g. the scout file was
            # missing at promote time) -- nothing to verify against.
            summary["skipped_no_hash"] += 1
            continue

        src_file = entry.get("file", "")
        snippet_path = snippets_dir / src_file if src_file else None
        if snippet_path is None or not snippet_path.is_file():
            summary["skipped_no_hash"] += 1
            continue
        try:
            content = snippet_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            summary["skipped_no_hash"] += 1
            continue

        # Wrap the bare snippet source in a synthetic one-block markdown
        # fence so the shared code_fences.py tokenizer -- and therefore
        # verify_markdown()'s own fence-tag filtering -- sees exactly the
        # same content _promote_snippets already hashed into code_sha256.
        synthetic_md = f"```{fence_tag}\n{content}\n```\n"
        report = verify_markdown(
            synthetic_md, family=family, platform=platform, policy=policy, product=product)
        if not report.blocks:
            # A snippet file that is empty/whitespace-only, or one whose own
            # content happens to defeat the fence tokenizer (e.g. an
            # embedded ``` sequence) -- honest skip, not a fabricated proof.
            summary["skipped_no_hash"] += 1
            continue
        block = report.blocks[0]

        proof: dict = {
            "tier": block.proof_tier,
            "status": block.status,
            "clone_head": report.clone_head,
            "runner_version": report.runners_module_version,
        }
        if block.reason:
            proof["reason"] = block.reason
        if block.detail:
            proof["detail"] = block.detail

        if entry.get("execution_proof") != proof:
            entry["execution_proof"] = proof
            changed = True
        summary["swept"] += 1

    if changed:
        index_path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

    return summary


# ---------------------------------------------------------------------------
# Main promote function
# ---------------------------------------------------------------------------

def _overrides_dir(family: str, platform: str, knowledge_root=None) -> Path:
    """knowledge/_overrides/{family}/{platform}/ — RPR-J-03 (rescues SW-11).

    Unlike the rest of knowledge/, this subtree is explicitly un-ignored
    (.gitignore: `/knowledge/*` + `!/knowledge/_overrides`) so manually-curated
    format notes and "Known Documentation Errors" survive a fresh clone or a
    knowledge/ rebuild, instead of silently vanishing because they previously
    lived only in the gitignored merged/ copy.
    """
    root = Path(knowledge_root) if knowledge_root else Path("knowledge")
    return root / "_overrides" / family / platform


def _load_format_overrides(family: str, platform: str, knowledge_root=None) -> list[dict]:
    """Read committed note/manual formats.json entries, or [] if none exist yet."""
    path = _overrides_dir(family, platform, knowledge_root) / "formats_overrides.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_format_overrides(entries: list[dict], family: str, platform: str, knowledge_root=None) -> None:
    """Write the committed note/manual formats.json entries (git-durable)."""
    if not entries:
        return
    path = _overrides_dir(family, platform, knowledge_root) / "formats_overrides.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_known_errors_override(family: str, platform: str, knowledge_root=None) -> str:
    """Read the committed 'Known Documentation Errors' block, or '' if none yet."""
    path = _overrides_dir(family, platform, knowledge_root) / "known_errors.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _save_known_errors_override(block: str, family: str, platform: str, knowledge_root=None) -> None:
    """Write the committed 'Known Documentation Errors' block (git-durable)."""
    if not block:
        return
    path = _overrides_dir(family, platform, knowledge_root) / "known_errors.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(block, encoding="utf-8")


def _count_tracked_enriched_claims(claims_path: Path) -> int:
    """Number of enriched (ERC-*) claims in a tracked merged/claims.json (0 if unreadable)."""
    try:
        data = json.loads(Path(claims_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    claims = data if isinstance(data, list) else (data.get("claims", []) if isinstance(data, dict) else [])
    return sum(
        1 for c in claims
        if isinstance(c, dict) and isinstance(c.get("claim_id"), str)
        and c["claim_id"].startswith("ERC-")
        and c.get("provenance", "enriched") == "enriched"
    )


def promote(family: str, platform: str, knowledge_root=None, *, merged_dir_override=None,
            allow_drop_enrichment: bool = False, extractor_hash: "str | None" = None,
            allow_partial_enrichment: bool = False) -> bool:
    """Promote scout/ knowledge to merged/ with optional enriched/supplemental claims.

    merged_dir_override (FRESH-001, T3): when given, all merged/ reads AND writes go
    to this path instead of base/"merged". promote_atomic() uses this to run the
    unmodified promotion logic against an isolated staging directory (seeded with a
    copy of the current merged/ so "read prior state" logic below still works
    correctly), then atomically swaps the result into place -- so a crash or a raised
    PromotionValidationError partway through this function never leaves the real
    merged/ in a mixed/partial state. New keyword-only param, defaults to None
    (identical behaviour to before this change) so no existing caller is affected.

    allow_drop_enrichment (MT074 B13a): promote FAILS CLOSED -- hard abort, nothing
    written -- when the enrichment input is absent, empty or stale while the tracked
    merged/claims.json already holds enriched (ERC-*) claims, because proceeding would
    silently drop every one of them and the next delta would report them as mass
    removal (observed live: -1,542 claims on pdf/java).  Pass True (CLI:
    --allow-drop-enrichment) ONLY for a deliberate decision to discard enrichment.
    The abort also trips on PARTIAL loss: fewer than ENRICHMENT_MIN_RETAINED_RATIO
    (50%) of the tracked ERC claims surviving in the enrichment input.

    allow_partial_enrichment (MT074 R1-5): enrich marks an output ``enrichment_status:
    partial`` when a changed unit failed/yielded nothing; promote aborts on it unless
    this is True (CLI: --allow-partial-enrichment).

    extractor_hash (MT074 B13d): the current extractor hash, passed by
    refresh_knowledge so a promote running inside a refresh stamps it into
    model.yaml.  When None, any extractor_hash already present in model.yaml is
    PRESERVED (promote rewrites model.yaml wholesale and used to drop it).

    Returns True on success, False on failure.
    """
    base = (Path(knowledge_root) if knowledge_root else Path("knowledge")) / family / platform
    scout_dir = base / "scout"
    fl_dir = base / "fl"
    merged_dir = Path(merged_dir_override) if merged_dir_override is not None else (base / "merged")

    # Hard guard: fl/ must not exist
    if fl_dir.exists():
        print(
            f"ERROR: fl/ directory found at {fl_dir}\n"
            "  The FL knowledge layer has been removed from this repo.\n"
            "  Delete the fl/ directory and re-run promote.py.\n"
            "  If you need to re-import external knowledge, use enrich.py (S-37) instead."
        )
        return False

    if not (scout_dir / "claims.json").exists():
        print(f"ERROR: No scout knowledge found for {family}/{platform} "
              f"(missing {scout_dir / 'claims.json'})")
        return False

    merged_dir.mkdir(parents=True, exist_ok=True)

    # FRESH-001 schema v2: one bundle_id/timestamp shared by every artifact this
    # promotion writes (model.yaml, bundle_manifest.json, formats.md, api_surface.md)
    # -- the atomicity boundary that lets a consumer prove all sibling facts came
    # from the same promotion event, not a partial mix of two.
    _bundle_id = str(uuid.uuid4())
    _bundle_generated_at = datetime.now(timezone.utc).isoformat()

    # RPR-C-02: capture the OLD repo_sha (if any) BEFORE this function's later
    # full-dict rewrite of model.yaml destroys it. Prior to this fix, that prior
    # value was unrecoverable after promote() ran -- model.yaml.repo_sha is a
    # single scalar, always fully overwritten, with no history retained anywhere
    # (confirmed empirically pre-fix: knowledge/3d/net/merged/model.yaml had no
    # previous_repo_sha key despite refresh_knowledge.py's intent to write one).
    _prior_repo_sha_for_ledger: str | None = None
    _prior_extractor_hash: "str | None" = None
    _existing_model_path = merged_dir / "model.yaml"
    if _existing_model_path.exists():
        try:
            _existing_model = yaml.safe_load(_existing_model_path.read_text(encoding="utf-8")) or {}
            _prior_repo_sha_for_ledger = _existing_model.get("repo_sha") or None
            _prior_extractor_hash = _existing_model.get("extractor_hash") or None
        except Exception:
            _prior_repo_sha_for_ledger = None  # corrupt/unreadable prior model.yaml; ledger will record prior=null, not fabricate a value

    # MT074 B13a: how many enriched (ERC-*) claims does the TRACKED merged/claims.json
    # already hold?  Read BEFORE this function overwrites claims.json below.
    _tracked_erc_count = _count_tracked_enriched_claims(merged_dir / "claims.json")

    # Load scout data
    # FIX-12: claims.json may be a flat list (legacy) or a wrapper dict with
    # {source_sha, claims: [...]}.  Accept both.
    _raw_claims = json.loads(
        (scout_dir / "claims.json").read_text(encoding="utf-8"))
    if isinstance(_raw_claims, dict):
        scout_claims_raw = _raw_claims.get("claims", [])
    else:
        scout_claims_raw = _raw_claims if isinstance(_raw_claims, list) else []
    scout_claims = _validate_claims(scout_claims_raw, "scout")
    scout_model: dict = {}
    if (scout_dir / "model.yaml").exists():
        scout_model = yaml.safe_load(
            (scout_dir / "model.yaml").read_text(encoding="utf-8")) or {}

    scout_api: list = []
    if (scout_dir / "api_surface.json").exists():
        scout_api = json.loads(
            (scout_dir / "api_surface.json").read_text(encoding="utf-8"))
        if not isinstance(scout_api, list):
            scout_api = []

    print(f"Promote: {family}/{platform}")
    # MT067-2026-09-10 TC-03: was "{len(scout_api)} classes" -- len(scout_api) is every
    # api_surface.json entry including free functions (the raw "146"-style total), not a
    # class count. See lib/class_stats.py for the actual class_stats.total_declared/
    # public_documented/raw_entries_including_non_class breakdown.
    print(f"  Scout: {len(scout_claims)} claims, {len(scout_api)} api_surface entries")

    # -----------------------------------------------------------------------
    # Build merged claims: scout + enriched (S-37) + supplemental (bridge)
    # -----------------------------------------------------------------------
    merged_claims = [{**sc, "provenance": "scout"} for sc in scout_claims]
    enriched_count = 0
    supplemental_count = 0

    enriched_path = scout_dir / "enriched_claims.json"
    if enriched_path.exists():
        try:
            enriched_data = json.loads(enriched_path.read_text(encoding="utf-8"))
            # Staleness check: enriched_claims.json records the api_surface SHA it was
            # generated from.  If that SHA differs from the current scout api_surface,
            # the enrichment is stale and claims may reference removed/renamed members.
            _partial_enrichment = (isinstance(enriched_data, dict)
                                   and enriched_data.get("enrichment_status") == "partial")
            if _partial_enrichment:
                # MT074 R1-5: enrich marks an output PARTIAL when some changed unit failed or
                # yielded nothing acceptable (their OLD claims are kept, sha NOT refreshed).
                if not allow_partial_enrichment:
                    print(
                        f"  FAIL: {family}/{platform}: enriched_claims.json is marked PARTIAL "
                        f"({len(enriched_data.get('incomplete_units', []))} unit(s) not enriched for "
                        f"the current api_surface) -- aborting before anything is written.\n"
                        f"  Fix: re-run enrich.py {family} {platform} (retries exactly those units), "
                        f"or pass --allow-partial-enrichment to promote the old claims of the "
                        f"incomplete units anyway."
                    )
                    return False
                print(f"  WARNING: --allow-partial-enrichment: promoting a PARTIAL enrichment "
                      f"({len(enriched_data.get('incomplete_units', []))} incomplete unit(s) keep old claims)")
            if isinstance(enriched_data, dict) and not _partial_enrichment:
                stored_sha = enriched_data.get("api_surface_sha", "")
                if stored_sha:
                    import hashlib as _hashlib
                    current_sha = _hashlib.sha256(
                        json.dumps(scout_api, sort_keys=True).encode()
                    ).hexdigest()[:16]
                    if stored_sha != current_sha:
                        print(
                            f"  WARNING: enriched_claims.json is stale — generated from "
                            f"api_surface SHA {stored_sha!r}, current is {current_sha!r}.\n"
                            f"  Run /knowledge-enrich {family} {platform} to regenerate. "
                            "Ignoring stale enriched claims for this promotion."
                        )
                        enriched_data = {"claims": []}
            enriched_raw = enriched_data.get("claims", []) if isinstance(enriched_data, dict) else enriched_data
            enriched = _validate_claims(enriched_raw, "enriched")
            for c in enriched:
                merged_claims.append({**c, "provenance": "enriched"})
            enriched_count = len(enriched)
            print(f"  Enriched: {enriched_count} claims (from enrich.py)")
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARNING: could not read enriched_claims.json: {exc}")

    supplemental_path = scout_dir / "supplemental_claims.json"
    if supplemental_path.exists():
        try:
            supp_data = json.loads(supplemental_path.read_text(encoding="utf-8"))
            supp_raw = supp_data.get("claims", []) if isinstance(supp_data, dict) else supp_data
            supplemental = _validate_claims(supp_raw, "supplemental")
            for c in supplemental:
                merged_claims.append({**c, "provenance": "supplemental"})
            supplemental_count = len(supplemental)
            print(f"  Supplemental: {supplemental_count} claims (temporary bridge - delete after enrich.py runs)")
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARNING: could not read supplemental_claims.json: {exc}")

    if _tracked_erc_count and enriched_count < ENRICHMENT_MIN_RETAINED_RATIO * _tracked_erc_count:
        if not allow_drop_enrichment:
            print(
                f"  FAIL: {family}/{platform}: the tracked merged/claims.json holds "
                f"{_tracked_erc_count} enriched (ERC-*) claim(s) but the enrichment input "
                f"({enriched_path}) yields only {enriched_count} (absent, empty, stale or "
                f"truncated; minimum retained ratio {ENRICHMENT_MIN_RETAINED_RATIO:.0%}) -- aborting "
                f"before anything is written, because promoting now would silently DROP "
                f"{_tracked_erc_count - enriched_count} of them "
                f"(the next delta would report mass removal).\n"
                f"  Fix: run enrich.py {family} {platform} (it seeds from the tracked claims "
                f"when scout/enriched_claims.json is missing; add --no-llm to do so without "
                f"any LLM call), or pass --allow-drop-enrichment to discard enrichment on purpose."
            )
            return False
        print(
            f"  WARNING: --allow-drop-enrichment: dropping "
            f"{_tracked_erc_count - enriched_count} of {_tracked_erc_count} tracked "
            f"enriched (ERC-*) claim(s) -- enrichment input is absent, empty, stale or truncated"
        )

    print(f"  Total claims: {len(merged_claims)}")

    # Claim ID uniqueness check — hard-gate ERC dupes, warn-only for CLM dupes
    from collections import Counter as _Counter
    _id_counts = _Counter(c.get("claim_id") for c in merged_claims
                          if isinstance(c, dict) and c.get("claim_id"))
    _dupes = {cid: cnt for cid, cnt in _id_counts.items() if cnt > 1}
    _erc_dupes = {cid: cnt for cid, cnt in _dupes.items() if cid.startswith("ERC-")}
    _clm_dupes = {cid: cnt for cid, cnt in _dupes.items() if not cid.startswith("ERC-")}

    if _erc_dupes:
        print(f"  FAIL: {len(_erc_dupes)} duplicate ERC claim_id(s) - aborting write")
        for _cid, _cnt in sorted(_erc_dupes.items(), key=lambda x: -x[1])[:5]:
            print(f"    {_cid}: {_cnt} occurrences")
        return False

    if _clm_dupes:
        # HARDEN-words-net (2026-07-22): a claim_id collision between claims
        # with DIFFERENT text is NOT a safe dedup target — CLM ids are a
        # 6-hex-char (24-bit) hash of the claim text (extraction/api_surface.py
        # _make_claim), and a product with several thousand claims carries
        # real birthday-paradox collision risk in that space. Silently keeping
        # only the first of two DIFFERENT claims that happen to share an id
        # discards real data with no trace — confirmed already happening in a
        # SHIPPED product (pdf/net: a "Heading.Top property" claim was
        # silently dropped in favor of an unrelated "Form.SetXfaFieldValues"
        # claim that happened to hash to the same id).
        #
        # An initial version of this fix hard-failed promote() on any real
        # collision — technically correct (never silently lose data) but an
        # adversarial review found it would retroactively turn "silently
        # succeeds" into "hard blocks" for 7 already-shipped products the next
        # time any of them refreshes (3d/java, 3d/net, pdf/java, pdf/net,
        # slides/java, slides/net, slides/python), with no forewarning and no
        # path forward short of manual code changes. That is a worse
        # production outcome than the bug it fixes.
        #
        # Instead: re-hash the SECOND (and later) distinct-text claim under a
        # colliding id using more entropy (text + evidence file + line, plus a
        # salt as an extreme-case tie-breaker), so BOTH claims survive under
        # distinct, still-validly-shaped CLM ids. Loud WARNING either way —
        # this must never be silent — but it can never regress a passing
        # promote() into a failing one purely because of a hash collision;
        # identical-text duplicates (the common, harmless case — e.g. a C#
        # partial class scanned across multiple files producing the same
        # descriptive claim text each time) still dedupe exactly as before.
        _real_collisions: dict[str, set[str]] = {}
        for _cid in _clm_dupes:
            _texts = {c.get("text", "") for c in merged_claims if c.get("claim_id") == _cid}
            if len(_texts) > 1:
                _real_collisions[_cid] = _texts

        if _real_collisions:
            print(f"  WARNING: {len(_real_collisions)} claim_id hash COLLISION(s) between "
                  f"DIFFERENT claim texts — re-hashing with more context so both survive "
                  f"under distinct ids (never silently dropping real data):")
            for _cid, _texts in sorted(_real_collisions.items())[:5]:
                print(f"    {_cid}:")
                for _t in sorted(_texts)[:3]:
                    print(f"      - {_t[:120]}")

            # HARDEN-words-net finding-1 (2026-07-22, adversarial re-review):
            # tracking only the FIRST-seen text per colliding id meant a
            # LATER repeat of an already-rehashed (non-first) text got its
            # own fresh id instead of reusing the sibling's — e.g.
            # [A, B, B, C] sharing one id produced 2 different ids for the
            # two "B" copies instead of collapsing them to 1. Fixed by
            # tracking EVERY distinct text seen per group, mapping each to
            # whichever id (original or freshly re-hashed) it was first
            # assigned, so any later exact-text repeat reuses that same id
            # regardless of which occurrence (first or not) introduced it.
            _all_ids = {c.get("claim_id") for c in merged_claims
                       if isinstance(c, dict) and c.get("claim_id")}
            _text_to_id_by_group: dict[str, dict[str, str]] = {}
            for _c in merged_claims:
                _cid = _c.get("claim_id")
                if _cid not in _real_collisions:
                    continue
                _text = _c.get("text", "")
                _group = _text_to_id_by_group.setdefault(_cid, {})
                if _text in _group:
                    _c["claim_id"] = _group[_text]  # reuse this text's already-assigned id
                    continue
                if not _group:
                    _group[_text] = _cid  # first-seen text in this group keeps the original id
                    continue
                # HARDEN-words-net finding-2 (2 rounds — an earlier fix here
                # only validated evidence[0], not the evidence CONTAINER
                # itself, so a scalar/dict `evidence` value — e.g. a
                # hand-authored supplemental_claims.json entry that wrote
                # {"file": ..., "line": ...} instead of [{"file": ...,
                # "line": ...}] — still raised TypeError/KeyError on
                # subscripting or indexing a non-list. Evidence entries are
                # untrusted; nothing about their shape can crash promote().
                _ev_raw = _c.get("evidence")
                _ev = _ev_raw if isinstance(_ev_raw, list) else []
                _ev0 = _ev[0] if _ev and isinstance(_ev[0], dict) else {}
                _file = _ev0.get("file", "")
                _line = _ev0.get("line", "")
                _family_part = _cid.split("-", 2)[1] if _cid.count("-") >= 2 else "x"
                _salt = 0
                while True:
                    _new_hash = hashlib.sha256(
                        f"{_text}|{_file}|{_line}|{_salt}".encode("utf-8")
                    ).hexdigest()[:8]
                    _new_id = f"CLM-{_family_part}-{_new_hash}"
                    if _new_id not in _all_ids:
                        break
                    _salt += 1
                print(f"    re-hashed {_cid} -> {_new_id}: {_text[:100]}")
                _c["claim_id"] = _new_id
                _all_ids.add(_new_id)
                _group[_text] = _new_id

            # Recompute duplicate groups now that real collisions have distinct ids.
            _id_counts = _Counter(c.get("claim_id") for c in merged_claims
                                  if isinstance(c, dict) and c.get("claim_id"))
            _clm_dupes = {cid: cnt for cid, cnt in _id_counts.items()
                         if cnt > 1 and not cid.startswith("ERC-")}

    if _clm_dupes:
        _excess = sum(v - 1 for v in _clm_dupes.values())
        print(f"  WARNING: {len(_clm_dupes)} duplicate CLM claim_id(s) (identical text, "
              f"safe to dedupe) — deduplicating ({_excess} excess removed)")
        for _cid, _cnt in sorted(_clm_dupes.items(), key=lambda x: -x[1])[:5]:
            print(f"    {_cid}: {_cnt} occurrences")
        _seen_ids: set[str] = set()
        _deduped: list[dict] = []
        for _c in merged_claims:
            _cid = _c.get("claim_id")
            if _cid not in _seen_ids:
                _deduped.append(_c)
                _seen_ids.add(_cid)
        merged_claims = _deduped
    else:
        print(f"  Claim ID uniqueness: PASS ({len(_id_counts)} unique IDs)")

    # Optional semantic dedup: merge near-duplicate claims by TF-IDF cosine similarity.
    # Gated behind promote._semantic_dedup flag (set via --semantic-dedup CLI arg).
    if getattr(promote, "_semantic_dedup", False):
        _pre_count = len(merged_claims)
        merged_claims = _semantic_dedup_claims(merged_claims)
        _post_count = len(merged_claims)
        if _pre_count != _post_count:
            print(f"  Semantic dedup: {_pre_count} -> {_post_count} claims "
                  f"({_pre_count - _post_count} removed)")
    else:
        print("  Semantic dedup: skipped (use --semantic-dedup to enable)")

    (merged_dir / "claims.json").write_text(
        json.dumps(merged_claims, indent=2, ensure_ascii=False), encoding="utf-8")

    # -----------------------------------------------------------------------
    # Copy API surface from scout (always authoritative)
    # Apply Go name-inference fallback for undocumented trivial accessors
    # -----------------------------------------------------------------------
    _godoc_inferred = _apply_godoc_fallback(scout_api, platform)
    if _godoc_inferred:
        print(f"  GoDoc fallback: {_godoc_inferred} method(s) inferred from name patterns (doc_source: name_inference)")
    # D-4 / TC-MT040-43: write module_key/module_label onto every entry
    # before this authoritative copy is written -- see the "Module/topic
    # assignment" section above for the ordered strategy.
    compute_module_assignment(scout_api, family, platform)
    (merged_dir / "api_surface.json").write_text(
        json.dumps(scout_api, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  API surface: {len(scout_api)} entries ({compute_class_stats(scout_api)['total_declared']} classes)")
    # Validate: warn about remaining same-name entries without distinct class_import
    from collections import Counter as _Counter
    _name_counts = _Counter(c.get("name", "") for c in scout_api if isinstance(c, dict))
    for _dup_name, _dup_cnt in sorted(_name_counts.items()):
        if _dup_cnt <= 1:
            continue
        _dup_entries = [c for c in scout_api if isinstance(c, dict) and c.get("name") == _dup_name]
        _dup_imports = {c.get("class_import", "") for c in _dup_entries}
        if len(_dup_imports) < _dup_cnt:
            print(f"  WARNING: {_dup_name} has {_dup_cnt} entries but only "
                  f"{len(_dup_imports)} distinct class_import values")

    # -----------------------------------------------------------------------
    # Copy scout artifacts
    # -----------------------------------------------------------------------
    # For formats.json: preserve manually-annotated entries (those with a
    # "note" field OR "manual": true) that the scout cannot detect (e.g.
    # file-extension aliases, method-based imports).  These are merged back
    # after the scout copy so that a plain promote.py run does not silently
    # erase them.
    #
    # RPR-J-03 (rescues SW-11): the previous-run merged/formats.json this used
    # to read from lives under gitignored knowledge/ and does not survive a
    # fresh clone or a knowledge/ rebuild -- manually-curated entries would be
    # silently lost forever. The committed knowledge/_overrides/{family}/{platform}/
    # store (see _load_format_overrides/_save_format_overrides) is now the
    # durable source: read from it first, union with whatever the ephemeral
    # merged/ copy still has (covers products not yet migrated), then write
    # the union back to the override store so it is rescued going forward.
    _fmt_dst = merged_dir / "formats.json"
    _fmt_preserved: list[dict] = list(
        _load_format_overrides(family, platform, knowledge_root)
    )
    _preserved_keys = {
        (e.get("format"), e.get("enum")) for e in _fmt_preserved
        if e.get("format") is not None or e.get("enum") is not None
    }
    if _fmt_dst.exists():
        try:
            _existing = json.loads(_fmt_dst.read_text(encoding="utf-8"))
            for e in _existing:
                if not (e.get("note") or e.get("manual") is True):
                    continue
                key = (e.get("format"), e.get("enum"))
                if key not in _preserved_keys and (key[0] is not None or key[1] is not None):
                    _fmt_preserved.append(e)
                    _preserved_keys.add(key)
        except Exception as exc:
            import sys as _sys
            print(f"[promote] WARNING: could not load {_fmt_dst} for note preservation: {exc}",
                  file=_sys.stderr)
    _save_format_overrides(_fmt_preserved, family, platform, knowledge_root)

    for fname in ["formats.json", "class_graph.json", "coverage_matrix.json",
                  "install.md"]:
        src = scout_dir / fname
        if src.exists():
            shutil.copy2(src, merged_dir / fname)

    # Re-inject preserved note/manual entries that are absent from the scout output.
    if _fmt_preserved and _fmt_dst.exists():
        try:
            _new = json.loads(_fmt_dst.read_text(encoding="utf-8"))
            # Guard: skip entries where format or enum key is missing/None to
            # prevent (None, None) false-match collisions in the key set.
            _existing_keys = {
                (e.get("format"), e.get("enum")) for e in _new
                if e.get("format") is not None or e.get("enum") is not None
            }
            _added = [
                e for e in _fmt_preserved
                if (e.get("format"), e.get("enum")) not in _existing_keys
                and (e.get("format") is not None or e.get("enum") is not None)
            ]
            if _added:
                _new.extend(_added)
                _fmt_dst.write_text(
                    json.dumps(_new, indent=2, ensure_ascii=False),
                    encoding="utf-8")
                import sys as _sys
                print(f"[promote] Preserved {len(_added)} note/manual format "
                      f"entries not present in scout output ({_fmt_dst.name}).",
                      file=_sys.stderr)
        except Exception as exc:
            import sys as _sys
            print(f"[promote] WARNING: could not re-inject preserved entries "
                  f"into {_fmt_dst}: {exc}", file=_sys.stderr)

    # Copy limitations.md from scout, then re-append any "Known Documentation
    # Errors" section that was manually maintained.  That section survives
    # repeated promote runs; the auto-detected stub table at the top is always
    # refreshed from the latest scout output.
    #
    # RPR-J-03 (rescues SW-11): same durability gap as formats.json above --
    # read the committed override first (survives a fresh clone), fall back to
    # the ephemeral merged/limitations.md for not-yet-migrated products, and
    # rescue whatever is found back into the committed override store.
    lim_src = scout_dir / "limitations.md"
    lim_dst = merged_dir / "limitations.md"
    marker = "## Known Documentation Errors"
    known_errors_block = _load_known_errors_override(family, platform, knowledge_root)
    if not known_errors_block and lim_dst.exists():
        existing = lim_dst.read_text(encoding="utf-8")
        idx = existing.find(marker)
        if idx != -1:
            known_errors_block = "\n" + existing[idx:]
    _save_known_errors_override(known_errors_block, family, platform, knowledge_root)
    if lim_src.exists():
        scout_lim = lim_src.read_text(encoding="utf-8")
        lim_dst.write_text(scout_lim.rstrip() + known_errors_block + "\n",
                           encoding="utf-8")

    # -----------------------------------------------------------------------
    # Promote snippets
    # -----------------------------------------------------------------------
    snippet_count = _promote_snippets(scout_dir, merged_dir)

    # -----------------------------------------------------------------------
    # Cross-reference formats with not_implemented (KG-S06-1 fix)
    # -----------------------------------------------------------------------
    # If a format's primary render/export method is in the not_implemented
    # list (raises NotImplementedError), annotate the format entry with a
    # caveat so downstream content generation knows the format is declared
    # but not functional.
    _fmt_xref_path = merged_dir / "formats.json"
    if _fmt_xref_path.exists() and lim_dst.exists():
        try:
            _xref_formats = json.loads(
                _fmt_xref_path.read_text(encoding="utf-8"))
            _xref_lim = lim_dst.read_text(encoding="utf-8")
            # Extract not-implemented method names (e.g., "PdfRenderer.render")
            _not_impl: set[str] = set()
            for _lim_line in _xref_lim.splitlines():
                if "|" not in _lim_line or "---" in _lim_line:
                    continue
                _lim_parts = [p.strip() for p in _lim_line.split("|")]
                if len(_lim_parts) >= 5 and _lim_parts[1] != "File":
                    _cls = _lim_parts[3].strip() if len(_lim_parts) > 3 else ""
                    _meth = _lim_parts[4].strip() if len(_lim_parts) > 4 else ""
                    if _cls and _meth:
                        _not_impl.add(f"{_cls}.{_meth}")
                    elif _cls:
                        _not_impl.add(_cls)

            # Match format names to renderer class names
            # e.g., format "pdf" -> "PdfRenderer.render"
            _xref_changed = False
            for _xfmt in _xref_formats:
                _fname = (_xfmt.get("format") or _xfmt.get("name") or "").lower()
                if not _fname:
                    continue
                # Check for {Format}Renderer.render or Barcode.to_{format}
                _renderer_key = f"{_fname.capitalize()}Renderer.render"
                _method_key = f"Barcode.to_{_fname}"
                _matching = [k for k in _not_impl
                             if k.lower() == _renderer_key.lower()
                             or k.lower() == _method_key.lower()]
                if _matching and not _xfmt.get("caveat"):
                    _xfmt["caveat"] = (
                        f"NotImplementedError — {', '.join(_matching)} "
                        f"raise NotImplementedError"
                    )
                    _xref_changed = True
                    import sys as _sys
                    print(f"[promote] Annotated format '{_fname}' with "
                          f"not-implemented caveat: {_matching}",
                          file=_sys.stderr)

            if _xref_changed:
                _fmt_xref_path.write_text(
                    json.dumps(_xref_formats, indent=2, ensure_ascii=False),
                    encoding="utf-8")
        except Exception as exc:
            import sys as _sys
            print(f"[promote] WARNING: format/not_implemented cross-ref "
                  f"failed: {exc}", file=_sys.stderr)

    # -----------------------------------------------------------------------
    # formats.md
    # -----------------------------------------------------------------------
    fmt_path = merged_dir / "formats.json"
    if fmt_path.exists():
        formats_raw = json.loads(fmt_path.read_text(encoding="utf-8"))
        # Normalise display names: strip trailing underscore and capitalise.
        # e.g. "cfb_" -> "CFB", "msg_" -> "MSG", "eml" -> "EML"
        _DISPLAY_NAMES: dict[str, str] = {
            "cfb": "CFB (Compound File Binary)",
            "cfb_": "CFB (Compound File Binary)",
            "msg": "MSG (Outlook Message)",
            "msg_": "MSG (Outlook Message)",
            "eml": "EML (RFC 5322 / MIME)",
        }

        def _display(raw: str) -> str:
            stripped = raw.rstrip("_").lower()
            return _DISPLAY_NAMES.get(raw.lower(),
                   _DISPLAY_NAMES.get(stripped, stripped.upper()))

        # Merge per-direction rows: one row per display name with Im/Ex flags.
        # HARDEN-words-net (2026-07-23): must respect the `functional` flag,
        # not just `direction` -- an entry can have direction="import"/"export"
        # while functional=False (FOSS-gated, e.g. HTML/EPUB import/export are
        # explicitly blocked by WriterFactory.cs/ReaderFactory.cs in words/net,
        # yet formats.md previously showed them as "Yes" regardless, since this
        # loop never checked `functional` at all). The row itself is still
        # created (consistent with how a non-directional entry already got a
        # "-/-" row before this fix) -- only a functional=False entry is
        # prevented from flipping its own flag to "Yes". Entries with no
        # `functional` key at all (legacy/non-enum entries some older passes
        # never set it for) default to counted, preserving prior behavior.
        fmt_rows: dict[str, dict[str, bool]] = {}
        for fmt in formats_raw:
            raw_name = fmt.get("name", fmt.get("format", ""))
            if not raw_name:
                continue
            display_name = _display(raw_name)
            row = fmt_rows.setdefault(display_name, {"import": False, "export": False})
            if fmt.get("functional") is False:
                continue  # confirmed unreachable -- row exists, but stays "-"
            direction = fmt.get("direction", "both")
            if direction in ("import", "both"):
                row["import"] = True
            if direction in ("export", "both"):
                row["export"] = True
            # Treat legacy can_import / can_export fields if present
            if fmt.get("can_import"):
                row["import"] = True
            if fmt.get("can_export"):
                row["export"] = True

        # FRESH-001: provenance header mirroring api_surface.md's existing
        # <!-- repo_sha: ... --> pattern -- formats.md previously carried no
        # provenance marker at all, unlike api_surface.md, which is exactly the
        # asymmetry that let it drift silently in the cells/net incident.
        fmt_lines = [
                     "<!-- Generated by promote.py from merged/formats.json -->",
                     f"<!-- repo_sha: {scout_model.get('repo_sha', '')} -->",
                     f"<!-- bundle_id: {_bundle_id} -->",
                     "# Format Support\n",
                     "| Format | Import | Export |",
                     "|--------|--------|--------|"]
        for display_name, flags in sorted(fmt_rows.items()):
            imp = "Yes" if flags["import"] else "-"
            exp = "Yes" if flags["export"] else "-"
            fmt_lines.append(f"| {display_name} | {imp} | {exp} |")
        (merged_dir / "formats.md").write_text("\n".join(fmt_lines) + "\n", encoding="utf-8")

    # -----------------------------------------------------------------------
    # forbidden_claims list from limitations.md
    # -----------------------------------------------------------------------
    forbidden: list[str] = []
    lim_path = merged_dir / "limitations.md"
    if lim_path.exists():
        for line in lim_path.read_text(encoding="utf-8").splitlines():
            if "|" not in line or "---" in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 5 and parts[1] == "File":
                continue
            if len(parts) >= 5 and (parts[3] or parts[4]):
                cls = parts[3].strip()
                meth = parts[4].strip()
                if cls and meth:
                    forbidden.append(f"{cls}.{meth}")
                elif meth:
                    forbidden.append(meth)   # class-level stub (e.g. C++ empty-body class)
                elif cls:
                    forbidden.append(cls)

    # -----------------------------------------------------------------------
    # model.yaml
    # -----------------------------------------------------------------------
    # FRESH-001 schema v2: input_hashes expands the old single narrow config_sha
    # (covers only 4 extractor-config dicts) into named per-input hashes, so a
    # freshness check can point at exactly which input changed. extractor_config_sha
    # is the renamed continuation of the old value; config_sha key is kept verbatim
    # for back-compat (stale_detect.py and others still read it directly).
    _extractor_config_sha = compute_extractor_config_sha(family)
    _scout_claims_sha = hashlib.sha256(
        json.dumps(scout_claims_raw, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    _scout_api_surface_sha = hashlib.sha256(
        json.dumps(scout_api, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    _enriched_claims_sha = None
    if enriched_path.exists():
        try:
            _enriched_claims_sha = hashlib.sha256(enriched_path.read_bytes()).hexdigest()
        except OSError:
            _enriched_claims_sha = None
    _products_json_entry_sha = None
    try:
        _products_path = _PROMOTE_REPO_ROOT / "data" / "products.json"
        _products = json.loads(_products_path.read_text(encoding="utf-8"))
        for _entry in _products:
            if _entry.get("family") == family and _entry.get("platform") == platform:
                _products_json_entry_sha = hashlib.sha256(
                    json.dumps(_entry, sort_keys=True).encode("utf-8")
                ).hexdigest()
                break
    except (OSError, json.JSONDecodeError):
        _products_json_entry_sha = None

    merged_model = {
        "family": family,
        "platform": platform,
        "product_name": scout_model.get("product_name", ""),
        "version": scout_model.get("version", ""),
        "license": scout_model.get("license", ""),
        "repo_url": scout_model.get("repo_url", ""),
        "repo_sha": scout_model.get("repo_sha", ""),
        "config_sha": _extractor_config_sha,
        "stale_since": None,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "source": "scout_and_enriched" if enriched_count > 0 else "scout_only",
        "enrichment_status": "full" if enriched_count > 0 else "scout-only",
        "has_conflicts": False,
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "generator_fingerprint": generator_fingerprint(_PROMOTE_REPO_ROOT),
        "generator_semver": GENERATOR_SEMVER,
        "bundle_id": _bundle_id,
        "bundle_generated_at": _bundle_generated_at,
        "module_assignment_version": MODULE_ASSIGNMENT_VERSION,
        "input_hashes": {
            "extractor_config_sha": _extractor_config_sha,
            "scout_claims_sha": _scout_claims_sha,
            "scout_api_surface_sha": _scout_api_surface_sha,
            "enriched_claims_sha": _enriched_claims_sha,
            "products_json_entry_sha": _products_json_entry_sha,
        },
        "stats": {
            "scout_claims": len(scout_claims),
            "enriched_claims": enriched_count,
            "supplemental_claims": supplemental_count,
            "total_claims": len(merged_claims),
            # MT067-2026-09-10 TC-03: class_count is deprecated (alias of
            # classes.total_declared, matching the original TC-SYS-015 formula exactly —
            # see lib/class_stats.py for why this now comes from one shared function
            # instead of being reimplemented per pipeline stage).
            "class_count": compute_class_stats(scout_api)["total_declared"],
            "classes": compute_class_stats(scout_api),
            "forbidden_count": len(forbidden),
            "snippet_count": snippet_count,
        },
    }
    # MT074 B13d: stamp the current extractor hash when running inside a refresh,
    # otherwise preserve whatever model.yaml already carried (never drop it).
    _eh = extractor_hash or _prior_extractor_hash
    if _eh:
        merged_model["extractor_hash"] = _eh
    (merged_dir / "model.yaml").write_text(
        yaml.dump(merged_model, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    # RPR-C-02: record this promotion in the append-only baseline ledger, using
    # the prior_repo_sha captured before the write above destroyed it. This
    # entry is intentionally recorded as "accepted" here (promote() succeeding
    # to this point is treated as the acceptance event) even though a handful
    # of non-critical steps remain below (api_surface.md, merge_report.md,
    # snippet promotion) -- full transactional rollback across the whole
    # promote() function is out of scope for this fix; the property this fix
    # guarantees is that repo_sha HISTORY is never silently lost, which held
    # with zero exceptions before this change (a single scalar, always fully
    # overwritten). A ledger write failure here is logged but does not fail
    # promote() itself -- knowledge promotion succeeding must not become
    # contingent on ledger-write availability.
    try:
        from lib.baseline_ledger import BaselineLedger
        # RC-baseline-tree-identity (readme-refresh-hardening-and-regen-2026-08-30, TC-10): the
        # git TREE sha (content-addressed, independent of history/parentage) at the accepted
        # commit -- see BaselineLedger.append's own docstring for why this matters (a GitLab-
        # mirror-style history rewrite with byte-identical content vs. a genuine content change
        # both currently look identical to a commit-SHA-only ledger). Best-effort: a repo_sha
        # with no reachable clone cache, or a git failure, records repo_tree_sha=None rather
        # than failing the whole (already-non-fatal) ledger write.
        _repo_tree_sha = None
        try:
            import subprocess
            from core.clone_cache import clone_path, clone_exists
            _accepted_repo_sha = merged_model.get("repo_sha", "")
            if _accepted_repo_sha and clone_exists(family, platform):
                _tree_result = subprocess.run(
                    ["git", "rev-parse", f"{_accepted_repo_sha}^{{tree}}"],
                    cwd=str(clone_path(family, platform)),
                    capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                )
                if _tree_result.returncode == 0:
                    _repo_tree_sha = _tree_result.stdout.strip() or None
        except Exception:
            _repo_tree_sha = None
        _ledger = BaselineLedger(family, platform, merged_dir=merged_dir)
        _ledger.append(
            new_repo_sha=merged_model.get("repo_sha", ""),
            sha_source="scout",
            run_id=f"promote-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            status="accepted",
            accepted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            prior_repo_sha=_prior_repo_sha_for_ledger,
            repo_tree_sha=_repo_tree_sha,
        )
    except Exception as _ledger_exc:
        print(f"WARNING: baseline_ledger append failed (non-fatal): {_ledger_exc}")

    # FRESH-001 (2026-08-14): merged/model.yaml is now git-tracked (T0), so it is the
    # one canonical writer of "accepted baseline SHA" -- data/upstream_baselines.json
    # and data/knowledge_state.json are DERIVED, REGENERATED projections, not
    # independent beliefs (replaces the MT030-2026-08-13 ad hoc dual-write, which fixed
    # the symptom -- upstream_baselines.json having zero writers -- without fixing the
    # structural problem of having 3 independently-writable stores at all). Same
    # non-fatal philosophy as before: a projection-rebuild failure must not fail
    # promote() itself.
    try:
        from commands.ops.regen_baseline_projections import rebuild_one
        _rebuild_ok = rebuild_one(
            family, platform, merged_model,
            run_id=f"promote-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        )
        if not _rebuild_ok:
            # ST-188 follow-on (2026-09-06): rebuild_one's own bool result was previously
            # discarded here -- a regen failure was silently invisible to anyone not reading
            # stderr line-by-line. This does not fail promote() (same non-fatal philosophy as
            # above), but a discarded projection rebuild leaves model.yaml and its projections
            # disagreeing -- exactly the CORRUPT-eligible condition audit_portfolio's
            # `corrupt_disagreement` advisory field now surfaces on the next portfolio sweep, so
            # this failure will not stay invisible indefinitely even without a dedicated marker.
            print(
                f"ERROR: baseline projection rebuild returned False for {family}/{platform} -- "
                f"data/upstream_baselines.json / data/knowledge_state.json were NOT updated to "
                f"match the just-written merged/model.yaml. This will show up as "
                f"corrupt_disagreement on the next `audit-portfolio` run; consider re-running "
                f"`regen_baseline_projections.py rebuild-all` now instead of waiting for it."
            )
    except Exception as _ks_exc:
        print(f"WARNING: baseline projection rebuild failed (non-fatal): {_ks_exc}")

    # -----------------------------------------------------------------------
    # api_surface.md
    # -----------------------------------------------------------------------
    _generate_api_surface_md(scout_api, family, merged_model, merged_dir)

    # -----------------------------------------------------------------------
    # merge_report.md (kept for compatibility — rename eventually to promote_report.md)
    # -----------------------------------------------------------------------
    report_lines = [
        f"# Promote Report: {family}/{platform}",
        f"Date: {datetime.now(timezone.utc).isoformat()}",
        f"Scout SHA: {scout_model.get('repo_sha', 'n/a')}",
        "Source: scout-only (standalone pipeline, no FL dependency)",
        "",
        "## Statistics",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Scout claims | {len(scout_claims)} |",
        f"| Enriched claims (S-37) | {enriched_count} |",
        f"| Supplemental claims (bridge) | {supplemental_count} |",
        f"| Total claims | {len(merged_claims)} |",
        # MT067-2026-09-10 TC-03 (RC3): was len(scout_api) -- every api_surface.json entry
        # including free functions, not a class count. This row silently reported e.g.
        # 3604 "Classes" for pdf/typescript (true count ~1055) and 146 for barcode/python
        # (true count 79) for every product with any function-kind entries at all.
        f"| Classes | {merged_model['stats']['classes']['total_declared']} |",
        f"| API surface entries (incl. functions) | {len(scout_api)} |",
        f"| Forbidden claims | {len(forbidden)} |",
        f"| Snippets | {snippet_count} |",
        "",
        "All claims have `provenance: scout | enriched | supplemental` — no FL dependency.",
    ]
    if supplemental_count > 0:
        report_lines.append(
            f"\nNOTE: {supplemental_count} supplemental claims are a temporary bridge. "
            "Run enrich.py (S-37) then delete scout/supplemental_claims.json."
        )
    (merged_dir / "merge_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    # Remove legacy merge_conflicts.md if present
    conflicts_path = merged_dir / "merge_conflicts.md"
    if conflicts_path.exists():
        conflicts_path.unlink()

    print(f"  Forbidden claims: {len(forbidden)}")
    print(f"  All artifacts written to {merged_dir}")

    # -----------------------------------------------------------------------
    # Format-claims reconciliation (A-01 + A-02)
    # -----------------------------------------------------------------------
    _formats_for_reconcile: list = []
    _fmt_json_path = merged_dir / "formats.json"
    if _fmt_json_path.exists():
        try:
            _formats_for_reconcile = json.loads(
                _fmt_json_path.read_text(encoding="utf-8"))
            if not isinstance(_formats_for_reconcile, list):
                _formats_for_reconcile = []
        except (json.JSONDecodeError, OSError):
            _formats_for_reconcile = []

    _contradictions = _reconcile_formats_claims(
        _formats_for_reconcile, merged_claims, family, platform)

    if _contradictions:
        for _c in _contradictions:
            _msg = (
                f"  WARNING: format-claims contradiction: "
                f"format={_c['format']!r} direction={_c['direction']!r} "
                f"claim={_c['contradicting_claim']!r}"
            )
            print(_msg.encode("ascii", "replace").decode("ascii"))
        _recon_dir = Path("reports") / "knowledge-reconciliation"
        _recon_dir.mkdir(parents=True, exist_ok=True)
        _recon_lines = [
            f"# Format-Claims Reconciliation: {family}/{platform}",
            f"Date: {datetime.now(timezone.utc).isoformat()}",
            "",
            f"Total contradictions detected: {len(_contradictions)}",
            "",
            "## Contradictions",
            "",
        ]
        for _idx, _c in enumerate(_contradictions, 1):
            _recon_lines += [
                f"### {_idx}. Format `{_c['format']}`",
                f"- **Direction in formats.json**: `{_c['direction']}`",
                f"- **Contradicting claim**: {_c['contradicting_claim']}",
                "",
            ]
        _recon_lines += [
            "---",
            "_This report is a detection signal only. No claims were removed._",
            "_Review each contradiction and update formats.json or claims manually._",
        ]
        _recon_path = _recon_dir / f"{family}-{platform}.md"
        _recon_path.write_text("\n".join(_recon_lines) + "\n", encoding="utf-8")
        print(f"  Reconciliation report written to {_recon_path}")
    else:
        _checked = len([f for f in _formats_for_reconcile
                        if isinstance(f, dict)
                        and f.get("direction", "both") in _WRITE_DIRECTIONS])
        print(f"  Format-claims reconciliation: PASS ({_checked} formats checked)")

    # -----------------------------------------------------------------------
    # Artifact validation (FR-13) — runs after all merged/ writes are complete
    # -----------------------------------------------------------------------
    if not getattr(promote, "_skip_validation", False):
        validation_errors = validate_promoted_artifacts(family, platform, merged_dir)
        if validation_errors:
            for err in validation_errors:
                print(f"  VALIDATION ERROR: {err}")
            raise PromotionValidationError(
                f"Promotion of {family}/{platform} failed artifact validation "
                f"({len(validation_errors)} error(s)). "
                "Fix the scout extractor or the knowledge artifacts, then re-run promote.py. "
                "Pass --skip-validation to bypass (not recommended)."
            )
        print(f"  Artifact validation: PASS")

    # -----------------------------------------------------------------------
    # bundle_manifest.json (FRESH-001) — the atomicity boundary. Written LAST,
    # after every sibling artifact above is confirmed on disk, so its member
    # hashes describe the complete, validated bundle. Its presence with
    # status == "COMPLETE" is what promote_atomic()'s post-swap check and
    # freshness_guard.py's strict mode treat as proof this bundle is
    # self-consistent; absence or any other status means PROVENANCE_MISSING.
    # -----------------------------------------------------------------------
    _bundle_manifest = compute_bundle_manifest(
        merged_dir, family=family, platform=platform,
        repo_sha=merged_model.get("repo_sha", ""), bundle_id=_bundle_id,
        generated_at=_bundle_generated_at,
        generator_fingerprint_value=merged_model.get("generator_fingerprint"),
        promote_run_id=f"promote-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    )
    (merged_dir / "bundle_manifest.json").write_text(
        json.dumps(_bundle_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    _self_check = verify_bundle_manifest(merged_dir, _bundle_manifest)
    if _self_check:
        # Should be unreachable (we just wrote every member file above) --
        # if it happens, something else is racing this promotion (e.g. a
        # concurrent unlocked writer). Loud, not fatal: the swap/lock layers
        # (T3/T4) are what actually prevent this; this is a tripwire.
        print(f"  WARNING: bundle self-check found {len(_self_check)} mismatch(es) "
              f"immediately after writing — possible concurrent writer: {_self_check}")

    # Ordering guard: warn if enriched_claims.json now exists but contributed 0
    # claims.  This happens when enrich.py ran AFTER promote.py (wrong order).
    if enriched_count == 0 and (scout_dir / "enriched_claims.json").exists():
        print(
            "\n  WARNING: enriched_claims.json exists in scout/ but contributed 0 claims.\n"
            "  This usually means enrich.py ran AFTER promote.py.\n"
            "  Correct order: scout -> enrich -> promote\n"
            f"  Re-run: python scripts/pipeline/commands/knowledge/promote.py {family} {platform}"
        )

    # -----------------------------------------------------------------------
    # Pipeline state manifest
    # -----------------------------------------------------------------------
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> pipeline/
    from core.manifest import write_step_manifest
    state_path = base / ".pipeline_state.json"
    write_step_manifest(state_path, "promote", {
        "scout_claims": len(scout_claims),
        "enriched_claims": enriched_count,
        "supplemental_claims": supplemental_count,
        "total_claims": len(merged_claims),
        # MT067-2026-09-10 TC-03: was a third inline copy of the TC-SYS-015 formula.
        "class_count": compute_class_stats(scout_api)["total_declared"],
    })

    return True


# ---------------------------------------------------------------------------
# Atomic promotion (FRESH-001 T3)
# ---------------------------------------------------------------------------
# promote() above writes directly into whatever merged_dir it is given -- correct,
# but non-atomic when that is the real merged/: a crash or a raised
# PromotionValidationError partway through can leave real merged/ with siblings from
# two different revisions. promote_atomic() gets atomicity for free, without touching
# any of promote()'s internal write logic, by giving it an ISOLATED staging directory
# (seeded with a copy of the current merged/, so promote()'s own "read prior state"
# logic sees the same values it would reading the real merged/) and only swapping the
# result into place after promote() succeeds and the bundle self-verifies.
#
# Portable by design: os.rename() is atomic for same-volume renames of both files and
# directories on POSIX AND on Windows (NTFS) -- there is no real platform difference
# at the syscall level to branch on. The actual risk on any OS is TRANSIENT HANDLE
# CONTENTION (AV scanners / search indexers / backup agents holding a brief open
# handle -- more common on Windows but not exclusive to it), which is why both renames
# go through the same retry-with-backoff-on-OSError loop core/fs.py's atomic_write()
# already uses in production, rather than an OS-conditional branch.

PROMOTE_ATOMIC_ENV = "PROMOTE_ATOMIC_BUNDLE"


def _rename_with_retry(src: Path, dst: Path, attempts: int = 5) -> None:
    """os.rename with retry-with-backoff on OSError (transient handle contention).

    Same policy as core/fs.py's atomic_write(): up to 5 attempts, 0.2s * attempt
    backoff. Generic -- no OS branch -- since the retry is cheap and harmless on
    POSIX even though the contention it guards against is more common on Windows.
    """
    last_exc: OSError | None = None
    for attempt in range(attempts):
        try:
            os.rename(str(src), str(dst))
            return
        except OSError as exc:
            last_exc = exc
            time.sleep(0.2 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _atomic_swap(real_merged: Path, staging_dir: Path, bak_dir: Path) -> "list[str]":
    """Swap staging_dir into real_merged's place via a merged.atomic-bak/ intermediate.

    Returns a list of problem descriptions (empty = success). Any failure during
    the renames themselves is left exactly as promote_recover.py's documented
    STATE_A/STATE_B/STATE_C decision table expects -- this function does not try
    to unwind a partially-completed swap itself; that is promote_recover.py's job,
    run as promote_atomic()'s own next-attempt precondition.
    """
    problems: list[str] = []
    try:
        if real_merged.exists():
            _rename_with_retry(real_merged, bak_dir)
        _rename_with_retry(staging_dir, real_merged)
    except OSError as exc:
        return [f"rename failed during swap: {exc}"]

    manifest_path = real_merged / "bundle_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "COMPLETE":
            problems.append(f"post-swap manifest status={manifest.get('status')!r}, expected COMPLETE")
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"post-swap manifest unreadable: {exc}")

    if problems:
        # Do NOT delete bak_dir or attempt further mutation -- leave the exact
        # state for promote_recover.py to classify and report on the next run.
        return problems

    if bak_dir.exists():
        shutil.rmtree(bak_dir, ignore_errors=True)
    return []


def promote_atomic(family: str, platform: str, knowledge_root=None, *,
                   allow_drop_enrichment: bool = False,
                   extractor_hash: "str | None" = None,
                   allow_partial_enrichment: bool = False) -> bool:
    """Promote scout/ -> merged/ atomically: stage the full bundle in an isolated
    directory, validate it, then swap it into place all-or-nothing.

    Runs promote_recover.recover() as its own first step (self-healing precondition)
    so a prior interrupted swap never blocks a fresh attempt. Refuses to start a new
    swap if merged.atomic-bak/ still exists after recovery (AMBIGUOUS state) -- surfaces the
    problem instead of guessing.

    Returns True only if the complete, self-verified bundle was promoted.
    """
    from commands.ops.promote_recover import recover

    base = (Path(knowledge_root) if knowledge_root else Path("knowledge")) / family / platform
    real_merged = base / "merged"

    recovery = recover(base)
    if not recovery["ok"]:
        print(f"PROMOTE_ATOMIC: pre-flight recovery check failed for {family}/{platform}: "
              f"{recovery['state']} — {recovery['action_taken']}. "
              f"Run `python scripts/pipeline/commands/ops/promote_recover.py {family} {platform}` "
              f"to inspect and repair before retrying.")
        return False
    if recovery["action_taken"] != "none":
        print(f"PROMOTE_ATOMIC: pre-flight recovery: {recovery['state']} — {recovery['action_taken']}")

    bak_dir = base / "merged.atomic-bak"
    if bak_dir.exists():
        print(f"PROMOTE_ATOMIC: {bak_dir} still present after recovery — refusing to start a new swap "
              f"for {family}/{platform}.")
        return False

    bundle_id = str(uuid.uuid4())
    staging_dir = base / f"merged.staging.{bundle_id}"
    staging_dir.parent.mkdir(parents=True, exist_ok=True)
    if real_merged.is_dir():
        shutil.copytree(real_merged, staging_dir)
    else:
        staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        _extra_kw: dict = {}
        if allow_drop_enrichment:
            _extra_kw["allow_drop_enrichment"] = True
        if extractor_hash:
            _extra_kw["extractor_hash"] = extractor_hash
        if allow_partial_enrichment:
            _extra_kw["allow_partial_enrichment"] = True
        success = promote(family, platform, knowledge_root, merged_dir_override=staging_dir,
                          **_extra_kw)
    except Exception as exc:
        print(f"PROMOTE_ATOMIC: promote() raised, discarding staging bundle ({exc})")
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    if not success:
        print(f"PROMOTE_ATOMIC: promote() returned False, discarding staging bundle — real merged/ untouched")
        shutil.rmtree(staging_dir, ignore_errors=True)
        return False

    manifest_path = staging_dir / "bundle_manifest.json"
    if not manifest_path.is_file():
        print("PROMOTE_ATOMIC: staged bundle has no bundle_manifest.json — refusing to swap")
        shutil.rmtree(staging_dir, ignore_errors=True)
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"PROMOTE_ATOMIC: staged bundle_manifest.json unreadable ({exc}) — refusing to swap")
        shutil.rmtree(staging_dir, ignore_errors=True)
        return False
    if manifest.get("status") != "COMPLETE":
        print(f"PROMOTE_ATOMIC: staged bundle_manifest.json status={manifest.get('status')!r} — refusing to swap")
        shutil.rmtree(staging_dir, ignore_errors=True)
        return False
    mismatches = verify_bundle_manifest(staging_dir, manifest)
    if mismatches:
        print(f"PROMOTE_ATOMIC: staged bundle failed self-verify — refusing to swap: {mismatches}")
        shutil.rmtree(staging_dir, ignore_errors=True)
        return False

    problems = _atomic_swap(real_merged, staging_dir, bak_dir)
    if problems:
        print(f"PROMOTE_ATOMIC: swap did not complete cleanly for {family}/{platform}: {problems}\n"
              f"  Run `python scripts/pipeline/commands/ops/promote_recover.py {family} {platform}` "
              f"to inspect and repair.")
        return False

    print(f"PROMOTE_ATOMIC: bundle {bundle_id} promoted for {family}/{platform}")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Scout-only knowledge promotion (replaces merge.py).")
    parser.add_argument("family", help="Product family (e.g. '3d')")
    parser.add_argument("platform", help="Platform (e.g. 'python')")
    parser.add_argument("--knowledge-root", default=None,
                        help="Override knowledge root directory (default: knowledge/)")
    parser.add_argument("--skip-validation", action="store_true", default=False,
                        help="Skip artifact validation checks (not recommended)")
    parser.add_argument("--semantic-dedup", action="store_true", default=False,
                        help="Enable TF-IDF semantic dedup of near-duplicate claims (cosine > 0.90)")
    parser.add_argument("--no-semantic-dedup", dest="semantic_dedup", action="store_false",
                        help="Explicitly disable semantic dedup (default)")
    parser.add_argument("--atomic", dest="atomic", action="store_true", default=None,
                        help=f"Force atomic staged-then-swap promotion (default: read "
                             f"{PROMOTE_ATOMIC_ENV} env var, defaults to on)")
    parser.add_argument("--no-atomic", dest="atomic", action="store_false",
                        help="Force the legacy direct-write promotion path (no staging/swap)")
    parser.add_argument("--allow-drop-enrichment", action="store_true", default=False,
                        help="MT074 B13a: permit promote to proceed when enrichment is absent, "
                             "empty or stale although the tracked merged/claims.json holds "
                             "enriched (ERC-*) claims -- they are DROPPED. Off by default: promote "
                             "otherwise aborts (fails closed) so enriched claims are never "
                             "silently lost.")
    parser.add_argument("--allow-partial-enrichment", action="store_true", default=False,
                        help="MT074 R1-5: permit promote to use an enriched_claims.json marked "
                             "PARTIAL (some changed units failed/yielded nothing; their OLD claims "
                             "are kept). Off by default: promote aborts instead. Re-running "
                             "enrich.py retries exactly the incomplete units.")
    parser.add_argument("--extractor-hash", default=None, metavar="HASH",
                        help="MT074 B13d: stamp this extractor hash into model.yaml (passed by "
                             "refresh_knowledge when promote runs inside a refresh). Without it "
                             "an existing extractor_hash is preserved.")
    parser.add_argument("--verify-snippets", action="store_true", default=False,
                        help="Run ONLY the post-promote execution-proof sweep "
                             "(sweep_snippet_execution_proof, MT072 TC-06) over this "
                             "product's existing merged snippets_index.json -- skips "
                             "promotion entirely. Tier-1/offline by default, idempotent, "
                             "safe to run repeatedly or once across the whole portfolio "
                             "without re-running promote().")
    args = parser.parse_args()

    if args.verify_snippets:
        summary = sweep_snippet_execution_proof(args.family, args.platform, args.knowledge_root)
        print(json.dumps(summary, indent=2))
        sys.exit(1 if summary.get("error") else 0)

    # Thread flags into the promote function via function attributes.
    # This avoids changing the promote() signature (which may be called from tests).
    promote._skip_validation = args.skip_validation  # type: ignore[attr-defined]
    promote._semantic_dedup = args.semantic_dedup  # type: ignore[attr-defined]
    if args.atomic is None:
        use_atomic = os.environ.get(PROMOTE_ATOMIC_ENV, "1").strip().lower() not in ("0", "false", "no")
    else:
        use_atomic = args.atomic
    _kw: dict = {}
    if args.allow_drop_enrichment:
        _kw["allow_drop_enrichment"] = True
    if args.extractor_hash:
        _kw["extractor_hash"] = args.extractor_hash
    if args.allow_partial_enrichment:
        _kw["allow_partial_enrichment"] = True
    try:
        if use_atomic:
            success = promote_atomic(args.family, args.platform, args.knowledge_root, **_kw)
        else:
            success = promote(args.family, args.platform, args.knowledge_root, **_kw)
    except PromotionValidationError as exc:
        print(f"\nPROMOTE: FAIL\n{exc}")
        sys.exit(1)
    finally:
        promote._skip_validation = False  # type: ignore[attr-defined]
        promote._semantic_dedup = False  # type: ignore[attr-defined]
    print(f"\nPROMOTE: {'PASS' if success else 'FAIL'}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
