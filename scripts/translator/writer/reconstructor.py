"""
Document reconstructor: rebuild a Hugo .md file from a HugoDocument.
Uses pyyaml for frontmatter serialization.
Atomic writes via temp file + os.replace().
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator.parser.document import HugoDocument


def reconstruct_document(doc: HugoDocument) -> str:
    """
    Serialize a HugoDocument back to a Hugo .md string.
    Returns the full file content with frontmatter delimiters.
    """
    # Serialize frontmatter
    fm_str = _serialize_frontmatter(doc.frontmatter)

    # Build full document
    body = doc.body
    if not body.startswith("\n"):
        body = "\n" + body
    if not body.endswith("\n"):
        body = body + "\n"

    return f"---\n{fm_str}---\n{body}"


def reconstruct_and_write(doc: HugoDocument, output_path: Path) -> None:
    """
    Reconstruct a HugoDocument and write to output_path atomically.
    Uses temp file + os.replace() to prevent partial writes on crash.
    """
    content = reconstruct_document(doc)
    _atomic_write(output_path, content)


def _serialize_frontmatter(frontmatter: dict) -> str:
    """
    Serialize frontmatter dict to YAML string.
    Uses pyyaml with allow_unicode=True and no line wrapping.
    """
    result = yaml.dump(
        frontmatter,
        allow_unicode=True,
        default_flow_style=False,
        width=4096,
        sort_keys=False,
    )
    if not result.endswith("\n"):
        result += "\n"
    return result


def _atomic_write(path: Path, content: str) -> None:
    """
    Write content to path atomically via a temporary file.
    If the write fails, the original file is not modified.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file in the same directory (same filesystem = atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.tmp.",
        suffix=".md",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(path))  # Atomic on POSIX and Windows (Python 3.3+)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
