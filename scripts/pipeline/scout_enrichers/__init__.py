"""Scout enrichers — post-processing docstring extraction for extracted classes.

Each enricher reads source files and populates empty ``doc`` fields on
class/method records produced by scout.py's tree-sitter extraction.

Supported platforms:
- Java: ``/** ... */`` Javadoc blocks
- C++: ``///`` triple-slash and ``/** ... */`` Doxygen blocks
- .NET/C#: ``/// <summary>`` XML doc comments
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._javadoc import enrich_javadoc
from ._doxygen import enrich_doxygen
from ._xml_doc import enrich_xml_doc

# Map platform → enricher function
_ENRICHERS: dict[str, Any] = {
    "java": enrich_javadoc,
    "cpp": enrich_doxygen,
    "dotnet": enrich_xml_doc,
    "net": enrich_xml_doc,
}


def enrich_classes(
    classes: list[dict],
    repo_dir: Path,
    platform: str,
) -> int:
    """Enrich extracted class records with docstrings.

    Args:
        classes: Class records from scout.py extraction.
        repo_dir: Root of the source repository.
        platform: Target platform (java, cpp, dotnet, net).

    Returns:
        Number of items enriched.
    """
    enricher = _ENRICHERS.get(platform)
    if enricher is None:
        return 0
    return enricher(classes, repo_dir)
