"""Read and write canonical grade metadata in Markdown frontmatter.

This is a standalone-compatible port of the aspose.org grade writer behavior.
It preserves unrelated frontmatter exactly, writes only canonical grade fields,
and strips legacy operational grade metadata from the frontmatter block.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

try:
    from scripts.pipeline.core.fs import atomic_write
except ImportError:  # pragma: no cover - compatibility for direct script imports
    _ROOT = Path(__file__).resolve().parents[3]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from scripts.pipeline.core.fs import atomic_write


CURRENT_LOGIC_VERSION = "standalone"
CURRENT_EVALUATOR_VERSIONS: dict[str, str] = {}

CANONICAL_FRONTMATTER_FIELDS = frozenset({
    "grade",
    "graded_content_hash",
    "grade_reasons",
})

_FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)

_GRADE_LINE_KEYS = {
    "grade",
    "graded_at",
    "graded_model_sha",
    "graded_evaluators",
    "graded_logic_version",
    "grade_final",
    "grade_stale_reason",
    "grade_stale_targets",
    "graded_content_hash",
    "grade_reasons",
    "graded_evaluator_versions",
    "graded_enrichment_status",
}
_GRADE_BLOCK_RE = re.compile(
    r"^(?:(?:grade|graded_at|graded_model_sha|graded_evaluators|graded_logic_version"
    r"|grade_final|grade_stale_reason|grade_stale_targets|graded_content_hash|grade_reasons"
    r"|graded_evaluator_versions|graded_enrichment_status)"
    r":[ \t]*[^\n]*(?:\n|$)(?:  [^\n]*(?:\n|$))*)+",
    re.MULTILINE,
)

_GRADE_VALUE_RE = re.compile(r"^grade:\s*([A-F])\s*$", re.MULTILINE)
_GRADED_SHA_RE = re.compile(r"^graded_model_sha:\s*(\S+)", re.MULTILINE)
_GRADED_TIER_RE = re.compile(r"^graded_evaluators:\s*(\S+)", re.MULTILINE)
_LOGIC_VERSION_RE = re.compile(r"^graded_logic_version:\s*(\S+)", re.MULTILINE)
_GRADE_FINAL_RE = re.compile(r"^grade_final:\s*(\S+)", re.MULTILINE)
_GRADE_STALE_REASON_RE = re.compile(r"^grade_stale_reason:\s*(\S+)", re.MULTILINE)
_CONTENT_HASH_RE = re.compile(r'^graded_content_hash:\s*"?(\S+?)"?\s*$', re.MULTILINE)
_GRADE_REASONS_RE = re.compile(r"^grade_reasons:\s*\n((?:  - [^\n]*\n?)+)", re.MULTILINE)
_GRADED_AT_LINE_RE = re.compile(r"^graded_at:[^\n]*\n?", re.MULTILINE)
_GRADED_ENRICHMENT_STATUS_RE = re.compile(r"^graded_enrichment_status:\s*(\S+)", re.MULTILINE)
_EVALUATOR_VERSIONS_BLOCK_RE = re.compile(
    r"^graded_evaluator_versions:\s*\n((?:  \w+:[ \t]*[^\n]*\n?)+)",
    re.MULTILINE,
)
_EVALUATOR_VERSION_ENTRY_RE = re.compile(r'^\s{2}(\w+):\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)


def _normalize_body(body: str) -> str:
    """Normalize line endings and trailing whitespace for stable body hashes."""
    return "\n".join(line.rstrip() for line in body.replace("\r\n", "\n").splitlines())


def content_hash(body: str) -> str:
    """Return a stable 32-character SHA-256 prefix for Markdown body content."""
    return hashlib.sha256(_normalize_body(body).encode("utf-8")).hexdigest()[:32]


def _crosses_letter_boundary(old: str, new: str) -> bool:
    bands = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}
    return old in bands and new in bands and bands[old] != bands[new]


def _should_write_canonical_grade(
    filepath: Path,
    new_grade: str,
    new_content_hash: str,
) -> tuple[bool, str]:
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
    """Read grade metadata from frontmatter without requiring a full YAML parse."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    grade_match = _GRADE_VALUE_RE.search(text)
    if not grade_match:
        return None

    sha_match = _GRADED_SHA_RE.search(text)
    tier_match = _GRADED_TIER_RE.search(text)
    logic_match = _LOGIC_VERSION_RE.search(text)
    final_match = _GRADE_FINAL_RE.search(text)
    stale_match = _GRADE_STALE_REASON_RE.search(text)
    hash_match = _CONTENT_HASH_RE.search(text)
    reasons_match = _GRADE_REASONS_RE.search(text)
    versions_match = _EVALUATOR_VERSIONS_BLOCK_RE.search(text)
    enrichment_match = _GRADED_ENRICHMENT_STATUS_RE.search(text)

    grade_final = True
    if final_match:
        grade_final = final_match.group(1).lower() not in ("false", "0", "no")

    grade_reasons: list[str] = []
    if reasons_match:
        for line in reasons_match.group(1).strip().splitlines():
            item = line.strip()
            if item.startswith("- "):
                grade_reasons.append(item[2:].strip().strip('"'))

    evaluator_versions: dict[str, str] = {}
    if versions_match:
        for entry_match in _EVALUATOR_VERSION_ENTRY_RE.finditer(versions_match.group(1)):
            evaluator_versions[entry_match.group(1)] = entry_match.group(2)

    return {
        "grade": grade_match.group(1),
        "model_sha": sha_match.group(1) if sha_match else "",
        "tier": tier_match.group(1) if tier_match else "full",
        "logic_version": logic_match.group(1) if logic_match else "",
        "grade_final": grade_final,
        "grade_stale_reason": stale_match.group(1) if stale_match else "",
        "content_hash": hash_match.group(1) if hash_match else "",
        "grade_reasons": grade_reasons,
        "evaluator_versions": evaluator_versions,
        "enrichment_status": enrichment_match.group(1) if enrichment_match else None,
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
    """Insert or replace the canonical grade block in YAML frontmatter."""
    del model_sha, evaluator_tier, logic_version, grade_final
    del grade_stale_reason, grade_stale_targets, evaluator_versions, enrichment_status

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

    if write_mode == "policy":
        should_write, reason = _should_write_canonical_grade(filepath, grade, body_hash)
        if not should_write:
            _log(f"  POLICY-SKIP {filepath}: {reason}")
            return True

    grade_block = f"grade: {grade}\ngraded_content_hash: \"{body_hash}\""
    if grade_reasons:
        items = "\n".join(f"  - \"{reason}\"" for reason in grade_reasons[:5])
        grade_block += f"\ngrade_reasons:\n{items}"

    existing_match = _GRADE_BLOCK_RE.search(fm_text)
    if existing_match:
        existing_stripped = _GRADED_AT_LINE_RE.sub("", existing_match.group()).rstrip("\n")
        proposed_stripped = _GRADED_AT_LINE_RE.sub("", grade_block).rstrip("\n")
        if existing_stripped == proposed_stripped:
            _log(f"  SKIP {filepath}: grade block unchanged")
            return True

        outside = fm_text[: existing_match.start()] + fm_text[existing_match.end():]
        for key in _GRADE_LINE_KEYS:
            if re.search(rf"^{re.escape(key)}:", outside, re.MULTILINE):
                _log(f"  WARN {filepath}: grade key '{key}' found outside the contiguous grade block")

        trail = "\n" if existing_match.group().endswith("\n") else ""
        new_fm = _GRADE_BLOCK_RE.sub(grade_block + trail, fm_text, count=1)
    else:
        new_fm = fm_text.rstrip("\n") + "\n" + grade_block

    atomic_write(filepath, f"{open_fence}{new_fm}{close_fence}{body}")
    return True


def _log(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)
