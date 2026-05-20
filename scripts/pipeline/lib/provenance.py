"""provenance.py — Read and write provenance metadata in YAML frontmatter.

Ported from aspose.org scripts/pipeline/lib/provenance.py.
Tracks the origin, translation mechanism, and overwrite eligibility of .md
content files. Only the provenance block is touched; everything else is
preserved byte-for-byte.

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

    content_hash          First 32 hex chars of SHA-256 of the page body text
                          (everything after the closing frontmatter fence).
                          Updated whenever the content body changes.

    content_created_at    ISO-8601 UTC timestamp when the page body was first created.
                          Set once; MUST NOT be updated by grade-writer, evidence-attach,
                          or fixer.

Lifecycle rules
---------------
- Evidence attachment and grade writing MUST NOT call ``update_mechanism()``
  and MUST NOT change ``last_mechanism``. Only content-changing operations
  should call ``update_mechanism()``.
- Metadata-only fixer runs (frontmatter field corrections) use mechanism
  ``metadata-fixer`` but MUST NOT change body content.
- Only explicit human or agent content edits change ``auto_updatable``.
- ``content_created_at`` is set once at page creation. MUST NOT be changed
  by any subsequent operation.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Dependency resolution (handles both package and direct-script imports)
# ---------------------------------------------------------------------------

try:
    from scripts.pipeline.core.fs import atomic_write
except ImportError:  # pragma: no cover
    _ROOT = Path(__file__).resolve().parents[3]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from scripts.pipeline.core.fs import atomic_write  # type: ignore[no-redef]


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

# Captures: group(1)=opening fence "---\n", group(2)=frontmatter content,
# group(3)=closing fence "\n---\n"
_FRONTMATTER_WRITER_RE = re.compile(r"^(---\n)(.*?)(\n---\n)", re.DOTALL)

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
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    fm = _FRONTMATTER_WRITER_RE.match(text)
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

    Returns ``True`` when:
    - ``auto_updatable: true`` is set explicitly, OR
    - no provenance block exists (migration default: overwritable).
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True  # Cannot read → assume safe

    m = _AUTO_UPDATABLE_RE.search(text)
    if m:
        return m.group(1) == "true"

    # No provenance or no auto_updatable field → migration default
    return True


# Mechanisms that indicate human curation — batch tools should not overwrite.
_MANUAL_MECHANISMS = frozenset({"manual-edit-skill", "human-edit", "agent-edit"})


def is_manually_curated(filepath: Path) -> bool:
    """Return whether *filepath* was last modified by a human-curation mechanism."""
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
        _AUDIT_LOG_DIR = Path(__file__).resolve().parents[3] / "reports" / "write_audit"
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

    Returns True if the file was written.
    Raises ProtectedPageError if the file is protected and *force* is False.
    """
    import json
    from datetime import datetime, timezone

    if filepath.exists() and not is_auto_updatable(filepath):
        if force:
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

    atomic_write(filepath, content)
    return True


# ---------------------------------------------------------------------------
# Source SHA / Content Hash
# ---------------------------------------------------------------------------

def compute_source_sha(english_source_path: Path) -> str:
    """Return first 24 hex chars of SHA-256 of *english_source_path* content."""
    content = english_source_path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:24]


def _normalize_body(body: str) -> str:
    """Normalize body text for stable hashing: CRLF->LF, strip trailing whitespace per line."""
    return "\n".join(line.rstrip() for line in body.replace("\r\n", "\n").splitlines())


def compute_content_hash(filepath: Path) -> str:
    """Return first 32 hex chars of SHA-256 of the normalized page body (after frontmatter)."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    fm = _FRONTMATTER_WRITER_RE.match(text)
    body = text[fm.end():] if fm else text
    return hashlib.sha256(_normalize_body(body).encode("utf-8")).hexdigest()[:32]


def is_stale(locale_path: Path, english_path: Path) -> bool:
    """Return True if locale file's ``source_sha`` differs from English content."""
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
    fm = _FRONTMATTER_WRITER_RE.match(text)
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

    Returns True on success, False on error.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    # Write-once guard: preserve existing content_created_at
    existing_prov = _read_provenance_from_text(text)
    if existing_prov and "content_created_at" in existing_prov:
        existing_val = existing_prov["content_created_at"]
        incoming_val = prov_dict.get("content_created_at")
        if incoming_val is None:
            prov_dict = {**prov_dict, "content_created_at": existing_val}
        elif incoming_val != existing_val:
            print(
                f"WARN: preserving existing content_created_at for {filepath} "
                f"(attempted change: {existing_val!r} -> {incoming_val!r})"
            )
            prov_dict = {**prov_dict, "content_created_at": existing_val}

    prov_yaml = _build_provenance_yaml(prov_dict)
    fm_match = _FRONTMATTER_WRITER_RE.match(text)

    if fm_match:
        open_fence = fm_match.group(1)
        fm_text = fm_match.group(2)
        close_fence = fm_match.group(3)
        body = text[fm_match.end():]

        if _PROVENANCE_BLOCK_RE.search(fm_text):
            _prov_replacement = prov_yaml.rstrip("\n")
            new_fm = _PROVENANCE_BLOCK_RE.sub(
                lambda m: _prov_replacement, fm_text, count=1
            )
        else:
            new_fm = fm_text.rstrip("\n") + "\n" + prov_yaml
        new_text = f"{open_fence}{new_fm}{close_fence}{body}"
    else:
        # Guard against malformed frontmatter
        if text.lstrip().startswith("---"):
            raise ValueError(
                f"Frontmatter regex failed on {filepath} but file starts with "
                "'---'. The file likely has malformed frontmatter. "
                "Fix the source file and retry."
            )
        # Genuinely no frontmatter — prepend minimal one
        new_text = f"---\n{prov_yaml}---\n\n{text}"

    atomic_write(filepath, new_text)
    return True


def update_mechanism(filepath: Path, mechanism: str, content_hash: str = "") -> bool:
    """Update only ``last_mechanism`` inside the existing provenance block.

    If no provenance block exists, creates a minimal one with
    ``last_mechanism`` and ``auto_updatable: true``.

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
