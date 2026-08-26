"""provenance.py — Read and write provenance metadata in YAML frontmatter.

Tracks the origin, translation mechanism, and overwrite eligibility of .md
content files.  Follows the same style-preserving regex surgery pattern as
evidence/writer.py and grade_writer.py: only the provenance block is touched;
everything else is preserved byte-for-byte.

Provenance fields (all inside a ``provenance:`` YAML block):

    content_origin        How the English content was first created.
                          Values: skill-generated | agent-drafted |
                                  human-authored | unknown

    translation_origin    How the translation was produced (locale files only).
                          Values: translator-batch | translator-sync |
                                  translator-page | translator-retranslate |
                                  agent-translated | human-translated | unknown

    source_file           Relative path of the English source this was derived
                          from (locale files only).

    source_sha            First 24 hex chars of SHA-256 of the English source
                          content at time of translation.

    last_mechanism        Last tool/mechanism that modified this file.
                          Values: translator | fixer | content-fixer |
                                  metadata-fixer | skill | agent-edit |
                                  human-edit | manual-edit-skill |
                                  page-update | page-enhance | heal-page |
                                  unknown

    auto_updatable        Whether automated systems may overwrite without
                          review (true/false).

    reviewed              REMOVED. Was: whether the content has been explicitly
                          approved (true/false). No longer written by any code path.
                          Use auto_updatable: false to protect files from automated
                          overwrite.

    content_hash          First 32 hex chars of SHA-256 of the page body text
                          (everything after the closing frontmatter fence).
                          Updated whenever the content body changes.
                          Used to detect body drift from the recorded grade/evidence.

    content_created_at    ISO-8601 UTC timestamp when the page body was first created.
                          Set once by the content-creating operation (skill or agent).
                          MUST NOT be updated by grade-writer, evidence-attach, or fixer.

Lifecycle rules
---------------
- Evidence attachment and grade writing MUST NOT call ``update_mechanism()``
  and MUST NOT change ``last_mechanism``.  They have their own timestamps
  (``graded_at``, evidence ``model_sha``).  Only content-changing operations
  (``skill``, ``agent-edit``, ``human-edit``, ``translator``, ``content-fixer``)
  should call ``update_mechanism()``.
- Metadata-only fixer runs (frontmatter field corrections) use mechanism
  ``metadata-fixer`` via ``update_mechanism()`` but MUST NOT change body content.
- They MUST NOT change ``auto_updatable`` or ``translation_origin``.
- Only explicit human or agent content edits change ``auto_updatable``.
- ``source_sha`` mismatch against current English content signals staleness.
- ``content_created_at`` is set once at page creation.  MUST NOT be changed
  by any subsequent operation (grade writes, evidence attaches, fixers, translator).
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import yaml

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from core.fs import atomic_write  # noqa: E402


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ProtectedPageError(Exception):
    """Raised when a write is attempted on a page with auto_updatable: false."""

    def __init__(self, filepath: Path, mechanism: str):
        self.filepath = filepath
        self.mechanism = mechanism
        super().__init__(
            f"Blocked: {mechanism} attempted to overwrite protected page "
            f"{filepath} (auto_updatable: false)"
        )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTENT_ORIGINS = frozenset({
    "skill-generated", "agent-drafted", "human-authored", "unknown",
    # manual-remediation: content under active manual quality intervention;
    # temporarily exempt from evidence completeness checks in the validator.
    # Transient state — files should be re-graded and origin updated after remediation.
    "manual-remediation",
})

TRANSLATION_ORIGINS = frozenset({
    "translator-batch", "translator-sync", "translator-page",
    "translator-retranslate", "agent-translated", "human-translated",
    "unknown",
})

MECHANISMS = frozenset({
    "translator",
    "fixer", "content-fixer", "metadata-fixer",
    "skill", "agent-edit", "human-edit", "manual-edit-skill",
    "page-update", "page-enhance", "heal-page", "family-sync",
    "unknown",
})

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

from core.markdown import _FRONTMATTER_WRITER_RE as _FRONTMATTER_RE

# Matches the provenance: key and all its indented child lines.
_PROVENANCE_BLOCK_RE = re.compile(
    r"^provenance:[ \t]*(?:\n[ \t]+[^\n]*)*",
    re.MULTILINE,
)

# Fast field readers (no full YAML parse).
_AUTO_UPDATABLE_RE = re.compile(
    r"^[ \t]+auto_updatable:\s*(true|false)\s*$", re.MULTILINE
)
_LAST_MECHANISM_RE = re.compile(
    r"^[ \t]+last_mechanism:\s*(\S+)", re.MULTILINE
)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def read_provenance(filepath: Path) -> dict[str, Any] | None:
    """Parse the ``provenance:`` block from *filepath*'s frontmatter.

    Returns the provenance dict or *None* if the block is absent.
    Only the provenance sub-block is parsed via ``yaml.safe_load`` —
    the full frontmatter is never round-tripped.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    fm = _FRONTMATTER_RE.match(text)
    if not fm:
        return None

    fm_text = fm.group(2)
    m = _PROVENANCE_BLOCK_RE.search(fm_text)
    if not m:
        return None

    try:
        parsed = yaml.safe_load(m.group(0))
        if isinstance(parsed, dict):
            return parsed.get("provenance", parsed)
    except Exception:
        pass
    return None


def is_auto_updatable(filepath: Path) -> bool:
    """Return whether *filepath* is safe for automated overwrite.

    Reads only ``auto_updatable`` via regex — no full YAML parse.
    Returns ``True`` when:
    - ``auto_updatable: true`` is set explicitly, OR
    - no provenance block exists (migration default: overwritable).
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True  # Cannot read → assume safe (caller handles missing file)

    m = _AUTO_UPDATABLE_RE.search(text)
    if m:
        return m.group(1) == "true"

    # No provenance or no auto_updatable field → migration default
    return True


# Mechanisms that indicate human curation — batch tools should not overwrite.
_MANUAL_MECHANISMS = frozenset({"manual-edit-skill", "human-edit", "agent-edit"})


def is_manually_curated(filepath: Path) -> bool:
    """Return whether *filepath* was last modified by a human-curation mechanism.

    Reads only ``last_mechanism`` via regex — no full YAML parse.
    Returns ``True`` when ``last_mechanism`` is one of the manual-curation
    values (``manual-edit-skill``, ``human-edit``, ``agent-edit``).
    Returns ``False`` for batch/automated mechanisms or missing provenance.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    m = _LAST_MECHANISM_RE.search(text)
    if m:
        return m.group(1) in _MANUAL_MECHANISMS
    return False


# ---------------------------------------------------------------------------
# Safe content write (provenance-aware write gate)
# ---------------------------------------------------------------------------

_AUDIT_LOG_DIR: Path | None = None


def _resolve_audit_log_dir() -> Path:
    """Return the directory for the write-audit log, creating it if needed."""
    global _AUDIT_LOG_DIR
    if _AUDIT_LOG_DIR is None:
        _AUDIT_LOG_DIR = _HERE.parents[1] / "reports" / "write_audit"
    _AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _AUDIT_LOG_DIR


def safe_content_write(
    filepath: Path,
    content: str,
    mechanism: str,
    *,
    force: bool = False,
    reason: str = "",
) -> bool:
    """Write *content* to *filepath* with provenance protection.

    If the file already exists and has ``auto_updatable: false``, the write
    is blocked unless *force* is True.

    Parameters
    ----------
    filepath : Path
        Target content page path.
    content : str
        Full page content to write.
    mechanism : str
        The mechanism performing the write (e.g. ``"batch-reference"``).
    force : bool
        If True, override the protection and log an audit entry.
    reason : str
        Required when *force* is True — explains why the override was needed.

    Returns
    -------
    bool
        True if the file was written, False if skipped (non-existent files
        are always written — there is nothing to protect).

    Raises
    ------
    ProtectedPageError
        If the file is protected and *force* is False.
    """
    import json
    from datetime import datetime, timezone

    if filepath.exists() and not is_auto_updatable(filepath):
        if force:
            # Log the override for auditability
            log_dir = _resolve_audit_log_dir()
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "filepath": str(filepath),
                "mechanism": mechanism,
                "action": "force_overwrite",
                "reason": reason or "(no reason provided)",
            }
            log_file = log_dir / "overrides.jsonl"
            with open(log_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
            print(
                f"WARN: force-overwriting protected page {filepath} "
                f"(mechanism={mechanism}, reason={reason!r})"
            )
        else:
            raise ProtectedPageError(filepath, mechanism)

    # Write the file atomically
    atomic_write(filepath, content)
    return True


# ---------------------------------------------------------------------------
# Source SHA
# ---------------------------------------------------------------------------

def compute_source_sha(english_source_path: Path) -> str:
    """Return first 24 hex chars of SHA-256 of *english_source_path* content."""
    content = english_source_path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:24]


def _normalize_body(body: str) -> str:
    """Normalize body text for stable hashing: CRLF->LF, strip trailing whitespace per line."""
    return "\n".join(line.rstrip() for line in body.replace("\r\n", "\n").splitlines())


def compute_content_hash(filepath: Path) -> str:
    """Return first 32 hex chars of SHA-256 of the normalized page body (after frontmatter).

    Normalization ensures CRLF/LF differences and trailing whitespace do not
    produce different hashes for logically identical content.

    RC-tex-python-07 (MT037 blind-spot audit, adversarial review): whole-frontmatter
    page types (e.g. products.aspose.org "plugin" layout pages, whose real content --
    plugin_description, overview, content.block[], etc. -- lives entirely inside the
    frontmatter YAML with no body markdown at all) always hashed to the same constant
    value, since only the always-empty body was ever hashed. Real content edits to
    these pages were structurally undetectable by any content-hash-based staleness
    or skip check. When the normalized body is empty but a frontmatter block exists,
    fall back to hashing the frontmatter text itself, so real changes to
    whole-frontmatter pages are actually detected. Pages with real body content are
    completely unaffected -- the fallback only activates when body is empty.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    fm = _FRONTMATTER_RE.match(text)
    body = text[fm.end():] if fm else text
    normalized = _normalize_body(body)
    if fm and not normalized.strip():
        normalized = _normalize_body(fm.group(2))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def is_stale(locale_path: Path, english_path: Path) -> bool:
    """Return True if locale file's ``source_sha`` differs from English content.

    Returns True (stale) when:
    - provenance has ``source_sha`` and it doesn't match current English, OR
    - locale file has no provenance (unknown → treat as stale).
    """
    prov = read_provenance(locale_path)
    if not prov or not prov.get("source_sha"):
        return True  # No provenance → stale by default
    current = compute_source_sha(english_path)
    return prov["source_sha"] != current


# ---------------------------------------------------------------------------
# Write / Update
# ---------------------------------------------------------------------------

def _read_provenance_from_text(text: str) -> dict[str, Any] | None:
    """Parse the provenance block from an already-read file text string."""
    fm = _FRONTMATTER_RE.match(text)
    if not fm:
        return None
    fm_text = fm.group(2)
    m = _PROVENANCE_BLOCK_RE.search(fm_text)
    if not m:
        return None
    try:
        parsed = yaml.safe_load(m.group(0))
        if isinstance(parsed, dict):
            return parsed.get("provenance", parsed)
    except Exception:
        pass
    return None


def _build_provenance_yaml(prov_dict: dict[str, Any]) -> str:
    """Serialize the provenance block to YAML text."""
    return yaml.dump(
        {"provenance": prov_dict},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def write_provenance(filepath: Path, prov_dict: dict[str, Any]) -> bool:
    """Insert or replace the ``provenance:`` block in *filepath*'s frontmatter.

    Follows the same surgery pattern as evidence/writer.py.
    Returns True on success, False on error.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    # Write-once guard: preserve existing content_created_at if the caller
    # omits or changes it.  This field must never be overwritten once set.
    existing_prov = _read_provenance_from_text(text)
    if existing_prov and "content_created_at" in existing_prov:
        existing_val = existing_prov["content_created_at"]
        incoming_val = prov_dict.get("content_created_at")
        if incoming_val is None:
            prov_dict = {**prov_dict, "content_created_at": existing_val}
        elif incoming_val != existing_val:
            print(
                f"WARN: preserving existing content_created_at for {filepath} "
                f"(attempted change: {existing_val!r} → {incoming_val!r})"
            )
            prov_dict = {**prov_dict, "content_created_at": existing_val}

    prov_yaml = _build_provenance_yaml(prov_dict)
    fm_match = _FRONTMATTER_RE.match(text)

    if fm_match:
        open_fence = fm_match.group(1)
        fm_text = fm_match.group(2)
        close_fence = fm_match.group(3)
        body = text[fm_match.end():]

        if _PROVENANCE_BLOCK_RE.search(fm_text):
            # Use a lambda so the replacement string is never interpreted for
            # backreferences.  Provenance values (e.g. source_file on Windows)
            # can contain backslash sequences such as \d that Python 3.12+
            # rejects as invalid escape sequences in re.sub replacement strings.
            _prov_replacement = prov_yaml.rstrip("\n")
            new_fm = _PROVENANCE_BLOCK_RE.sub(
                lambda m: _prov_replacement, fm_text, count=1
            )
        else:
            new_fm = fm_text.rstrip("\n") + "\n" + prov_yaml
        new_text = f"{open_fence}{new_fm}{close_fence}{body}"
    else:
        # Regex did not match.  Before prepending a new block, guard against
        # the case where the file already starts with --- (valid frontmatter
        # whose closing fence lacked a trailing newline, or otherwise
        # malformed).  Prepending in that case would create double frontmatter,
        # which Hugo silently ignores — a silent data-loss corruption.
        if text.lstrip().startswith("---"):
            raise ValueError(
                f"Frontmatter regex failed on {filepath} but file starts with "
                "'---'.  The file likely has malformed frontmatter (e.g. missing "
                "trailing newline after closing fence).  Refusing to prepend a "
                "new block to avoid double-frontmatter corruption.  Fix the "
                "source file and retry."
            )
        # Genuinely no frontmatter — prepend minimal one
        new_text = f"---\n{prov_yaml}---\n\n{text}"

    atomic_write(filepath, new_text)
    return True


def update_mechanism(filepath: Path, mechanism: str, content_hash: str = "") -> bool:
    """Update only ``last_mechanism`` inside the existing provenance block.

    If no provenance block exists, creates a minimal one with
    ``last_mechanism`` and ``auto_updatable: true``.

    When *content_hash* is provided (non-empty), also stores it as
    ``content_hash`` in the provenance block.

    IMPORTANT: This function MUST NOT change ``auto_updatable``,
    ``translation_origin``, ``content_origin``, or any other field.
    """
    prov = read_provenance(filepath)
    if prov is not None:
        prov["last_mechanism"] = mechanism
        if content_hash:
            prov["content_hash"] = content_hash
    else:
        prov = {
            "last_mechanism": mechanism,
            "auto_updatable": True,
        }
        if content_hash:
            prov["content_hash"] = content_hash
    return write_provenance(filepath, prov)
