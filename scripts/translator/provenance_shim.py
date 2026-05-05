"""provenance_shim.py — Minimal provenance helpers for the foss translator.

Provides the three functions used by translator/cli.py:
  - write_provenance(filepath, prov_dict)
  - compute_source_sha(english_source_path)
  - is_auto_updatable(filepath)

This is a lightweight, self-contained shim adapted from
aspose.org/scripts/pipeline/provenance.py (reference implementation).
"""
from __future__ import annotations
import hashlib
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("translator.provenance_shim")

_FRONTMATTER_RE = re.compile(
    r"^(---[ \t]*\n)(.*?)(\n---[ \t]*\n)", re.DOTALL
)
_PROVENANCE_BLOCK_RE = re.compile(
    r"^provenance:\n(?:[ \t]+.*\n)*", re.MULTILINE
)
_AUTO_UPDATABLE_RE = re.compile(
    r"^  auto_updatable:\s*(true|false)\s*$", re.MULTILINE
)


def compute_source_sha(english_source_path: Path) -> str:
    """Return first 24 hex chars of SHA-256 of the source file content."""
    content = english_source_path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:24]


def is_auto_updatable(filepath: Path) -> bool:
    """Return whether filepath is safe for automated overwrite.

    Returns True when auto_updatable: true is set, or when no provenance block
    exists (migration default: overwritable).
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True

    m = _AUTO_UPDATABLE_RE.search(text)
    if m:
        return m.group(1).strip().lower() == "true"
    return True  # no provenance block -> assume auto-updatable


def _build_provenance_yaml(prov_dict: dict) -> str:
    """Render prov_dict as a YAML provenance: block."""
    lines = ["provenance:"]
    for k, v in prov_dict.items():
        if isinstance(v, bool):
            lines.append("  " + k + ": " + ("true" if v else "false"))
        elif v is None:
            lines.append("  " + k + ": null")
        else:
            safe = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append('  ' + k + ': "' + safe + '"')
    return "\n".join(lines) + "\n"


def write_provenance(filepath: Path, prov_dict: "dict[str, Any]") -> bool:
    """Insert or replace the provenance: block in filepath YAML frontmatter.

    Returns True on success, False on error.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    prov_yaml = _build_provenance_yaml(prov_dict)
    fm_match = _FRONTMATTER_RE.match(text)

    if fm_match:
        open_fence = fm_match.group(1)
        fm_text = fm_match.group(2)
        close_fence = fm_match.group(3)
        body = text[fm_match.end():]

        if _PROVENANCE_BLOCK_RE.search(fm_text):
            prov_repl = prov_yaml.rstrip("\n")
            new_fm = _PROVENANCE_BLOCK_RE.sub(lambda m: prov_repl, fm_text, count=1)
        else:
            new_fm = fm_text.rstrip("\n") + "\n" + prov_yaml
        new_text = open_fence + new_fm + close_fence + body
    else:
        new_text = "---\n" + prov_yaml + "---\n" + text

    try:
        filepath.write_text(new_text, encoding="utf-8")
        return True
    except OSError as e:
        logger.error("Failed to write provenance to %s: %s", filepath, e)
        return False
