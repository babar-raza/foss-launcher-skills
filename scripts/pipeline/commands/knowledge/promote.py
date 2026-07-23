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
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.constants import _TEST_PATH_PATTERNS, _INTERNAL_PATH_PATTERNS
from extraction.formats import _FAMILY_FORMAT_ALLOWLISTS, _FAMILY_PYTHON_PRIMARY_FMT
from commands.launch.site_planner import _FAMILY_SUBPKG_LABELS, _ROOT_LABELS


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
            if name_lower not in claim_lower:
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
    # Platforms that use snake_case accessors (Python)
    _SNAKE_PLATFORMS = {"python"}

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
    print(f"  api_surface.md: {len(classes)} classes, {len(md_text)} bytes")


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
        if src_file and (scout_snip / src_file).exists():
            shutil.copy2(scout_snip / src_file, merged_snip / src_file)

        merged_entry = dict(entry)
        merged_entry["id"] = f"snippet_{i:03d}"
        merged_entry["provenance"] = "scout"
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


def promote(family: str, platform: str, knowledge_root=None) -> bool:
    """Promote scout/ knowledge to merged/ with optional enriched/supplemental claims.

    Returns True on success, False on failure.
    """
    base = (Path(knowledge_root) if knowledge_root else Path("knowledge")) / family / platform
    scout_dir = base / "scout"
    fl_dir = base / "fl"
    merged_dir = base / "merged"

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

    # RPR-C-02: capture the OLD repo_sha (if any) BEFORE this function's later
    # full-dict rewrite of model.yaml destroys it. Prior to this fix, that prior
    # value was unrecoverable after promote() ran -- model.yaml.repo_sha is a
    # single scalar, always fully overwritten, with no history retained anywhere
    # (confirmed empirically pre-fix: knowledge/3d/net/merged/model.yaml had no
    # previous_repo_sha key despite refresh_knowledge.py's intent to write one).
    _prior_repo_sha_for_ledger: str | None = None
    _existing_model_path = merged_dir / "model.yaml"
    if _existing_model_path.exists():
        try:
            _existing_model = yaml.safe_load(_existing_model_path.read_text(encoding="utf-8")) or {}
            _prior_repo_sha_for_ledger = _existing_model.get("repo_sha") or None
        except Exception:
            _prior_repo_sha_for_ledger = None  # corrupt/unreadable prior model.yaml; ledger will record prior=null, not fabricate a value

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
    print(f"  Scout: {len(scout_claims)} claims, {len(scout_api)} classes")

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
            if isinstance(enriched_data, dict):
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
    (merged_dir / "api_surface.json").write_text(
        json.dumps(scout_api, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  API surface: {len(scout_api)} classes")
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

        fmt_lines = ["# Format Support\n",
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
    merged_model = {
        "family": family,
        "platform": platform,
        "product_name": scout_model.get("product_name", ""),
        "version": scout_model.get("version", ""),
        "license": scout_model.get("license", ""),
        "repo_url": scout_model.get("repo_url", ""),
        "repo_sha": scout_model.get("repo_sha", ""),
        "config_sha": compute_extractor_config_sha(family),
        "stale_since": None,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "source": "scout_and_enriched" if enriched_count > 0 else "scout_only",
        "enrichment_status": "full" if enriched_count > 0 else "scout-only",
        "has_conflicts": False,
        "stats": {
            "scout_claims": len(scout_claims),
            "enriched_claims": enriched_count,
            "supplemental_claims": supplemental_count,
            "total_claims": len(merged_claims),
            # TC-SYS-015: match outputs.py formula — exclude "function" entries
            "class_count": sum(1 for c in scout_api if c.get("kind") != "function"),
            "forbidden_count": len(forbidden),
            "snippet_count": snippet_count,
        },
    }
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
        _ledger = BaselineLedger(family, platform, merged_dir=merged_dir)
        _ledger.append(
            new_repo_sha=merged_model.get("repo_sha", ""),
            sha_source="scout",
            run_id=f"promote-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            status="accepted",
            accepted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            prior_repo_sha=_prior_repo_sha_for_ledger,
        )
    except Exception as _ledger_exc:
        print(f"WARNING: baseline_ledger append failed (non-fatal): {_ledger_exc}")

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
        f"| Classes | {len(scout_api)} |",
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
        # TC-SYS-015: match outputs.py formula — exclude "function" entries
        "class_count": sum(1 for c in scout_api if c.get("kind") != "function"),
    })

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
    args = parser.parse_args()

    # Thread flags into the promote function via function attributes.
    # This avoids changing the promote() signature (which may be called from tests).
    promote._skip_validation = args.skip_validation  # type: ignore[attr-defined]
    promote._semantic_dedup = args.semantic_dedup  # type: ignore[attr-defined]
    try:
        success = promote(args.family, args.platform, args.knowledge_root)
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
