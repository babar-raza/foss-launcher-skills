"""extraction/formats.py — File-format detection from source trees.

Extracted from scout.py (step 4.4). Standalone function usable without the
Scout class.

Public API::

    detect_formats(parser, language, pkg_root, repo, family)
        -> tuple[list[dict], list[dict]]   # (formats, claims)
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from extraction.tree_helpers import (
    _CLASS_TYPES,
    _FILE_EXTENSIONS,
    _HEADER_EXTENSIONS,
    _PY_ENUM_BASES,
    _collect_source_files,
    _extract_bases,
    _extract_enum_members,
    _extract_python_enum_members,
    _node_name,
    collect_nodes,
)


def detect_formats(
    parser,
    language: str,
    pkg_root: Path,
    repo: Path,
    family: str,
) -> tuple[list[dict], list[dict]]:
    """Scan source files for format-related classes and return (formats, claims).

    Detects:
    - Enum classes whose name contains FileFormat/FormatType/etc.
    - Importer/Exporter/Reader/Writer/Loader/Saver classes.

    Returns two lists: ``formats`` (format entries) and ``claims`` (scout claims).
    """
    formats: list[dict] = []
    claims: list[dict] = []

    def _add_claim(kind: str, text: str, file: str = "", line: int = 0) -> None:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]
        cid = f"CLM-{family}-{h}"
        evidence = [{"file": file, "line": line}] if file else []
        claims.append({
            "claim_id": cid,
            "kind": kind,
            "text": text,
            "confidence": 1.0,
            "claim_source": "scout",
            "evidence": evidence,
        })

    ext = _FILE_EXTENSIONS.get(language, ".py")
    header_ext = _HEADER_EXTENSIONS.get(language, "")
    files = _collect_source_files(pkg_root, ext, header_ext)
    format_pattern = re.compile(
        r"(FileFormat|FormatType|SupportedFormat|FileType)", re.IGNORECASE)
    importer_pattern = re.compile(
        r"(Importer|Exporter|Reader|Writer|Loader|Saver)", re.IGNORECASE)

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if not format_pattern.search(text) and not importer_pattern.search(text):
            continue

        tree = parser.parse(text.encode("utf-8"))
        root = tree.root_node
        class_types = _CLASS_TYPES.get(language, set())
        class_nodes = collect_nodes(root, class_types)

        for cn in class_nodes:
            cname = _node_name(cn, language)
            if not cname:
                continue
            is_enum = cn.type in ("enum_declaration", "enum_definition",
                                  "enum_specifier")
            # Python: detect enums by base class inheritance
            if not is_enum and language == "python":
                fmt_bases = _extract_bases(cn, language)
                if set(fmt_bases) & _PY_ENUM_BASES:
                    is_enum = True

            if format_pattern.search(cname):
                if is_enum:
                    if language == "python":
                        members = _extract_python_enum_members(cn)
                    else:
                        members = _extract_enum_members(cn, language)
                    for mem in members:
                        fmt_entry = {
                            "format": mem["name"],
                            "enum": cname,
                            "value": mem.get("value", ""),
                            "file": rel,
                            "line": cn.start_point[0] + 1,
                            "direction": "both",
                        }
                        formats.append(fmt_entry)
                        _add_claim("format_support",
                                   f"Supports format {mem['name']} via {cname}",
                                   rel, cn.start_point[0] + 1)
                else:
                    formats.append({
                        "format": cname,
                        "enum": "",
                        "value": "",
                        "file": rel,
                        "line": cn.start_point[0] + 1,
                        "direction": "both",
                    })

            if importer_pattern.search(cname):
                direction = "import"
                if re.search(r"(Exporter|Writer|Saver)", cname, re.IGNORECASE):
                    direction = "export"
                fmt_name = re.sub(
                    r"(Importer|Exporter|Reader|Writer|Loader|Saver)", "",
                    cname, flags=re.IGNORECASE).strip()
                if fmt_name:
                    formats.append({
                        "format": fmt_name,
                        "enum": "",
                        "value": "",
                        "file": rel,
                        "line": cn.start_point[0] + 1,
                        "direction": direction,
                    })
                    _add_claim("format_support",
                               f"{direction} support for {fmt_name} via {cname}",
                               rel, cn.start_point[0] + 1)

    return formats, claims
