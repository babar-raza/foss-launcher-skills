"""grade_writer.py — Read and write grade metadata in YAML frontmatter.

Follows the same style-preserving regex surgery pattern as evidence/writer.py:
only the grade block is touched; everything else is preserved byte-for-byte.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

try:
    import yaml as _yaml  # pyyaml -- used for post-write YAML validation
except ImportError:
    _yaml = None  # type: ignore[assignment]

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.fs import atomic_write  # noqa: E402

# Current evaluator logic version — sourced from the canonical constant in content_eval.
# Importing here keeps grade_writer in sync without requiring a manual update.
from content_eval import EVALUATOR_LOGIC_VERSION as CURRENT_LOGIC_VERSION  # noqa: E402
from content_eval import EVALUATOR_VERSIONS as CURRENT_EVALUATOR_VERSIONS  # noqa: E402  (TC-5)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

from core.markdown import _FRONTMATTER_WRITER_RE as _FRONTMATTER_RE

# Matches the grade block: grade + optional graded_at + optional graded_model_sha
# + optional graded_evaluators + optional grade_final + optional grade_stale_reason
# + optional grade_stale_targets + optional graded_content_hash, each on its own line.
# WP-03: Only these fields belong in .md frontmatter.  All others are
# operational pipeline state and belong in the external grade manifest.
CANONICAL_FRONTMATTER_FIELDS = frozenset({
    "grade", "graded_content_hash", "grade_reasons",
})

_GRADE_LINE_KEYS = {
    "grade", "graded_at", "graded_model_sha", "graded_evaluators",
    "graded_logic_version", "grade_final", "grade_stale_reason", "grade_stale_targets",
    "graded_content_hash", "grade_reasons", "graded_evaluator_versions",
    "graded_enrichment_status",
}
_GRADE_BLOCK_RE = re.compile(
    r"^(?:(?:grade|graded_at|graded_model_sha|graded_evaluators|graded_logic_version"
    r"|grade_final|grade_stale_reason|grade_stale_targets|graded_content_hash|grade_reasons"
    r"|graded_evaluator_versions|graded_enrichment_status)"
    r":[ \t]*[^\n]*(?:\n|$)(?:  [^\n]*(?:\n|$))*)+",
    re.MULTILINE,
)

# Fast single-field readers (no YAML parse needed).
_GRADE_VALUE_RE = re.compile(r"^grade:\s*([A-F])\s*$", re.MULTILINE)
_GRADED_SHA_RE = re.compile(r"^graded_model_sha:\s*(\S+)", re.MULTILINE)
_GRADED_TIER_RE = re.compile(r"^graded_evaluators:\s*(\S+)", re.MULTILINE)
_LOGIC_VERSION_RE = re.compile(r"^graded_logic_version:\s*(\S+)", re.MULTILINE)
_GRADE_FINAL_RE = re.compile(r"^grade_final:\s*(\S+)", re.MULTILINE)
_GRADE_STALE_REASON_RE = re.compile(r"^grade_stale_reason:\s*(\S+)", re.MULTILINE)
_CONTENT_HASH_RE = re.compile(r'^graded_content_hash:\s*"?(\S+?)"?\s*$', re.MULTILINE)
_GRADE_REASONS_RE = re.compile(
    r"^grade_reasons:\s*\n((?:  - [^\n]*\n?)+)", re.MULTILINE
)
_GRADED_AT_LINE_RE = re.compile(r"^graded_at:[^\n]*\n?", re.MULTILINE)
_GRADED_ENRICHMENT_STATUS_RE = re.compile(r"^graded_enrichment_status:\s*(\S+)", re.MULTILINE)
_EVALUATOR_VERSIONS_BLOCK_RE = re.compile(
    r"^graded_evaluator_versions:\s*\n((?:  \w+:[ \t]*[^\n]*\n?)+)",
    re.MULTILINE,
)
_EVALUATOR_VERSION_ENTRY_RE = re.compile(r'^\s{2}(\w+):\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)


def _strip_orphaned_list_items(text: str) -> str:
    """Strip bare root-level YAML list items that have no valid parent mapping key.

    A list item (line starting with '- ') is considered orphaned when the
    preceding non-blank line does NOT end with ':' (i.e., it is not a YAML
    mapping key that opens a sequence).  Valid list items such as those under
    'categories:' or 'tags:' are preserved.

    This replaces the previous unconditional regex approach which caused valid
    category and tag values to be stripped as a side-effect of grade-block
    cleanup (bug introduced with the bare-list-item orphan guard).
    """
    lines = text.split('\n')
    out: list[str] = []
    for line in lines:
        if re.match(r'^- ', line):
            prev_nonempty = next((ln for ln in reversed(out) if ln.strip()), '')
            if not prev_nonempty.rstrip().endswith(':'):
                continue  # genuinely orphaned — strip
        out.append(line)
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _normalize_body(body: str) -> str:
    """Normalize body text for stable hashing: CRLF→LF, strip trailing whitespace per line."""
    return "\n".join(line.rstrip() for line in body.replace("\r\n", "\n").splitlines())


def content_hash(body: str) -> str:
    """SHA-256 of normalized page body content (excludes frontmatter), truncated to 32 hex chars.

    Normalization ensures CRLF/LF differences and trailing whitespace do not
    produce different hashes for logically identical content.
    """
    return hashlib.sha256(_normalize_body(body).encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _crosses_letter_boundary(old: str, new: str) -> bool:
    """Return True if old and new are different valid grade letters."""
    bands = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}
    return old in bands and new in bands and bands[old] != bands[new]


def _should_write_canonical_grade(
    filepath: Path,
    new_grade: str,
    new_content_hash: str,
) -> tuple[bool, str]:
    """Enforce the frontmatter write policy.  Returns (should_write, reason).

    MUST write when:
      1. Page has no grade in frontmatter (first grading)
      2. Body content_hash changed AND the new grade letter differs from stored
      3. Grade crossed a letter boundary (any direction)

    MUST NOT write when:
      - Only operational metadata changed (ELV, evaluator versions, model SHA)
      - Grade letter is unchanged and body is unchanged
      - Body changed but grade letter is unchanged
    """
    stored = read_grade(filepath)
    if not stored or not stored.get("grade"):
        return True, "first-grading"
    stored_grade = stored["grade"]
    stored_hash = stored.get("content_hash", "")
    body_changed = stored_hash != new_content_hash
    grade_changed = _crosses_letter_boundary(stored_grade, new_grade)
    if body_changed and grade_changed:
        return True, f"body-changed-grade-changed:{stored_grade}->{new_grade}"
    if grade_changed:
        return True, f"grade-band-crossing:{stored_grade}->{new_grade}"
    if body_changed:
        return False, f"body-changed-grade-unchanged:{stored_grade}"
    return False, f"no-policy-trigger:stored={stored_grade},new={new_grade}"


def read_grade(filepath: Path) -> dict | None:
    """Fast regex read of grade metadata from frontmatter.

    Returns a dict with keys:
      grade, model_sha, tier, logic_version, grade_final, grade_stale_reason
    or *None* if the file has no ``grade:`` field.  No full YAML parse is performed.

    Absence of ``grade_final`` is treated as ``True`` (backward compatibility).
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    m = _GRADE_VALUE_RE.search(text)
    if not m:
        return None

    sha_m = _GRADED_SHA_RE.search(text)
    tier_m = _GRADED_TIER_RE.search(text)
    lv_m = _LOGIC_VERSION_RE.search(text)
    gf_m = _GRADE_FINAL_RE.search(text)
    gsr_m = _GRADE_STALE_REASON_RE.search(text)
    ch_m = _CONTENT_HASH_RE.search(text)
    gr_m = _GRADE_REASONS_RE.search(text)
    ev_m = _EVALUATOR_VERSIONS_BLOCK_RE.search(text)
    ges_m = _GRADED_ENRICHMENT_STATUS_RE.search(text)

    grade_final = True  # default: treat absence as final
    if gf_m:
        grade_final = gf_m.group(1).lower() not in ("false", "0", "no")

    grade_reasons: list[str] = []
    if gr_m:
        for line in gr_m.group(1).strip().splitlines():
            line = line.strip()
            if line.startswith("- "):
                grade_reasons.append(line[2:].strip().strip('"'))

    # TC-5: parse per-evaluator version mapping
    evaluator_versions: dict[str, str] = {}
    if ev_m:
        for entry_m in _EVALUATOR_VERSION_ENTRY_RE.finditer(ev_m.group(1)):
            evaluator_versions[entry_m.group(1)] = entry_m.group(2)

    return {
        "grade": m.group(1),
        "model_sha": sha_m.group(1) if sha_m else "",
        "tier": tier_m.group(1) if tier_m else "full",
        "logic_version": lv_m.group(1) if lv_m else "",
        "grade_final": grade_final,
        "grade_stale_reason": gsr_m.group(1) if gsr_m else "",
        "content_hash": ch_m.group(1) if ch_m else "",
        "grade_reasons": grade_reasons,
        "evaluator_versions": evaluator_versions,
        # None means field absent — grade predates enrichment_status tracking.
        # Callers treat None as "unknown; assume full" for backward-compat.
        "enrichment_status": ges_m.group(1) if ges_m else None,
    }


def write_grade(
    filepath: Path,
    grade: str,
    model_sha: str = "",
    evaluator_tier: str = "full",
    logic_version: str = CURRENT_LOGIC_VERSION,
    grade_final: bool = True,
    grade_stale_reason: str = "",
    grade_stale_targets: list[str] | None = None,
    grade_reasons: list[str] | None = None,
    evaluator_versions: dict[str, str] | None = None,
    enrichment_status: str | None = None,
    *,
    write_mode: str = "force",
) -> bool:
    """Insert or replace grade block in YAML frontmatter.

    Writes only canonical fields: ``grade``, ``graded_content_hash``, and
    optionally ``grade_reasons``.  All operational fields (model_sha,
    evaluator_tier, logic_version, graded_at, etc.) belong in the external
    grade manifest only.

    ``write_mode`` controls the frontmatter write policy:
      - ``"force"`` (default): write unconditionally (backward-compatible).
      - ``"policy"``: consult ``_should_write_canonical_grade()`` and skip
        the write if the policy gate returns False.

    Note: ``provenance.last_mechanism`` is NOT updated by this function.

    Returns *True* on success, *False* on skip/error.
    """
    if grade not in ("A", "B", "C", "D", "F"):
        _log(f"  SKIP {filepath}: invalid grade '{grade}'")
        return False

    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _log(f"  ERROR reading {filepath}: {exc}")
        return False

    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        _log(f"  SKIP {filepath}: no YAML frontmatter found")
        return False

    open_fence = fm_match.group(1)
    fm_text = fm_match.group(2)
    close_fence = fm_match.group(3)
    body = text[fm_match.end():]

    body_hash = content_hash(body)

    # WP-01: Write policy gate — skip frontmatter write if policy not met.
    if write_mode == "policy":
        should_write, reason = _should_write_canonical_grade(filepath, grade, body_hash)
        if not should_write:
            _log(f"  POLICY-SKIP {filepath}: {reason}")
            return True  # Not an error — policy correctly suppressed write

    # ARCH-04 + D-1: Frontmatter contains ONLY canonical fields (grade,
    # graded_content_hash, grade_reasons).  graded_at is operational and
    # belongs in the external grade manifest (reports/grade_manifest.json)
    # only — keeping it here would cause per-page churn on every write
    # (timestamp always differs).
    grade_block = f"grade: {grade}"
    grade_block += f"\ngraded_content_hash: \"{body_hash}\""
    if grade_reasons:
        items = "\n".join(f"  - \"{r}\"" for r in grade_reasons[:5])
        grade_block += f"\ngrade_reasons:\n{items}"

    m = _GRADE_BLOCK_RE.search(fm_text)
    if m:
        # Idempotency guard: strip legacy graded_at from existing block
        # before comparing — D-1 removed graded_at from new writes, but
        # pre-MIG-01 pages still carry it.
        existing_stripped = _GRADED_AT_LINE_RE.sub("", m.group()).rstrip("\n")
        proposed_stripped = _GRADED_AT_LINE_RE.sub("", grade_block).rstrip("\n")
        if existing_stripped == proposed_stripped:
            _log(f"  SKIP {filepath}: grade block unchanged except graded_at -- idempotent no-write")
            return True
        # Guard: remove orphaned grade keys and bare list items outside the matched block.
        # Non-contiguous grade keys and root-level bare "- " items (invalid in YAML mapping)
        # survive a naive replace, leaving corrupt frontmatter that Hugo cannot parse.
        outside_before = fm_text[: m.start()]
        outside_after = fm_text[m.end() :]
        # Strip stray grade-key lines (and their indented continuations)
        cleaned_before = _GRADE_BLOCK_RE.sub("", outside_before)
        cleaned_after = _GRADE_BLOCK_RE.sub("", outside_after)
        # Strip bare root-level list items that are truly orphaned (no parent YAML key).
        # Uses context-aware helper to preserve valid categories/tags list items.
        cleaned_before = _strip_orphaned_list_items(cleaned_before)
        cleaned_after = _strip_orphaned_list_items(cleaned_after)
        if cleaned_before != outside_before or cleaned_after != outside_after:
            _log(
                f"  WARN {filepath}: removed orphaned grade keys or bare list items outside "
                "grade block -- frontmatter was corrupt; investigate the source of the prior write."
            )
            fm_text = cleaned_before + m.group() + cleaned_after
        # Replace existing grade block; preserve trailing \n only if original had one
        trail = "\n" if m.group().endswith("\n") else ""
        new_fm = _GRADE_BLOCK_RE.sub(grade_block + trail, fm_text, count=1)
    else:
        # Append after frontmatter content
        new_fm = fm_text.rstrip("\n") + "\n" + grade_block

    # Post-write YAML validation: verify new frontmatter is parseable before writing.
    # Turns silent corruption into an immediate error at the write site.
    if _yaml is not None:
        try:
            _yaml.safe_load(new_fm)
        except Exception as _exc:
            _log(
                f"  ERROR {filepath}: write_grade produced invalid YAML -- aborting write.\n"
                f"    Error: {_exc}\n"
                f"    Frontmatter (first 300 chars): {new_fm[:300]!r}"
            )
            return False

    new_text = f"{open_fence}{new_fm}{close_fence}{body}"
    atomic_write(filepath, new_text)

    return True


def _log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
