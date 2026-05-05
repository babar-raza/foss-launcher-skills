"""
HugoDocument: parse Hugo .md files into (frontmatter, body) pairs.
Uses pyyaml + regex for frontmatter extraction.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml
import sys
import os

# Add translator to path if needed
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator import FrontmatterParseError


_FRONTMATTER_DELIMITER = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


@dataclass
class HugoDocument:
    """Parsed representation of a Hugo markdown file."""
    frontmatter: dict          # Parsed YAML frontmatter as dict
    body: str                  # Markdown body content (after frontmatter)
    source_path: Optional[Path] = None

    def has_evidence(self) -> bool:
        return "evidence" in self.frontmatter

    def get_evidence(self) -> dict:
        return self.frontmatter.get("evidence", {})


def parse_file(path: str | Path) -> HugoDocument:
    """
    Parse a Hugo .md file into a HugoDocument.
    Raises FrontmatterParseError if YAML frontmatter is malformed.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return parse_string(text, source_path=path)


def parse_string(text: str, source_path: Optional[Path] = None) -> HugoDocument:
    """
    Parse a Hugo .md string into a HugoDocument.
    """
    try:
        m = _FRONTMATTER_DELIMITER.match(text)
        if m:
            frontmatter_dict = yaml.safe_load(m.group(1)) or {}
            body = text[m.end():]
        else:
            frontmatter_dict = {}
            body = text
        if not isinstance(frontmatter_dict, dict):
            raise ValueError(f"Frontmatter parsed to {type(frontmatter_dict).__name__}, expected dict")
        return HugoDocument(
            frontmatter=frontmatter_dict,
            body=body,
            source_path=source_path,
        )
    except FrontmatterParseError:
        raise
    except Exception as e:
        raise FrontmatterParseError(
            f"Failed to parse frontmatter{f' in {source_path}' if source_path else ''}: {e}"
        ) from e
