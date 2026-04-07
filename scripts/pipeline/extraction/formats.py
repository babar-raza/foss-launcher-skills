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
        r"(FileFormat|FormatType|SupportedFormat|FileType|SaveFormat|ExportFormat|LoadFormat|ImportFormat|OutputFormat|InputFormat)",
        re.IGNORECASE)
    # SaveFormat/ExportFormat enums indicate actual output capability
    save_format_pattern = re.compile(
        r"(SaveFormat|ExportFormat|OutputFormat)", re.IGNORECASE)
    # LoadFormat enums indicate actual input capability
    load_format_pattern = re.compile(
        r"(LoadFormat|ImportFormat|InputFormat)", re.IGNORECASE)
    importer_pattern = re.compile(
        r"(Importer|Exporter|Reader|Writer|Loader|Saver)", re.IGNORECASE)

    # H-04: False-positive format names to reject after suffix stripping
    _FALSE_POSITIVE_NAMES = frozenset({
        "reader", "writer", "loader", "saver", "importer", "exporter",
        "document", "file", "stream", "base", "abstract", "default",
        "generic", "common", "internal", "helper", "utils", "factory",
    })

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
                # Determine direction from enum name semantics:
                # - SaveFormat/ExportFormat → export only
                # - LoadFormat/ImportFormat → import only
                # - FileFormat/FormatType  → detect only (NOT both)
                # Content generators must not treat "detect" as I/O capability.
                if save_format_pattern.search(cname):
                    enum_direction = "export"
                elif load_format_pattern.search(cname):
                    enum_direction = "import"
                else:
                    enum_direction = "detect"

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
                            "direction": enum_direction,
                        }
                        formats.append(fmt_entry)
                        direction_desc = (
                            f"Detects format {mem['name']} via {cname}"
                            if enum_direction == "detect"
                            else f"{enum_direction} support for {mem['name']} via {cname}"
                        )
                        _add_claim("format_support", direction_desc,
                                   rel, cn.start_point[0] + 1)
                # Non-enum format-pattern classes (e.g. FileFormat, FileFormatType,
                # InvalidFileFormatException) are NOT format identifiers — they are
                # class/interface definitions.  Do NOT emit the class name as a format
                # entry; only enum *members* are valid format names.

            if importer_pattern.search(cname):
                direction = "import"
                if re.search(r"(Exporter|Writer|Saver)", cname, re.IGNORECASE):
                    direction = "export"
                fmt_name = re.sub(
                    r"(Importer|Exporter|Reader|Writer|Loader|Saver)", "",
                    cname, flags=re.IGNORECASE).strip().strip("_")
                # H-04: reject empty, too-short, or common-word false positives
                if fmt_name and len(fmt_name) >= 2 and fmt_name.lower() not in _FALSE_POSITIVE_NAMES:
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

    # Second pass: scan method names for format signals embedded in naming
    # conventions (e.g., load_from_eml, save_to_eml).  Catches formats that
    # are surfaced via a high-level API method rather than a dedicated
    # Reader/Writer class — common in C++ libraries.
    _FORMAT_METHOD_SKIP = frozenset({
        "file", "stream", "bytes", "buffer", "string", "dict", "list",
        "json", "xml", "yaml", "text", "utf8", "base64", "path",
        "data", "object", "array", "value", "type", "node", "doc",
        "document", "model", "map", "tree", "memory",
    })
    _method_fmt_re = re.compile(r'\b(?:load_from|save_to|from|to)_([a-z][a-z0-9]+)\b')
    seen_mf: set[tuple[str, str]] = set()

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for mfm in _method_fmt_re.finditer(text):
            fmt_name = mfm.group(1).lower()
            if fmt_name in _FORMAT_METHOD_SKIP:
                continue
            full_verb = mfm.group(0)
            if full_verb.startswith("save_to_") or full_verb.startswith("to_"):
                direction = "export"
            else:
                direction = "import"
            key = (fmt_name, direction)
            if key in seen_mf:
                continue
            seen_mf.add(key)
            line_num = text[:mfm.start()].count("\n") + 1
            formats.append({
                "format": fmt_name,
                "enum": "",
                "value": "",
                "file": rel,
                "line": line_num,
                "direction": direction,
            })
            _add_claim("format_support",
                       f"{direction} support for {fmt_name} format "
                       f"(method name: {mfm.group(0)})",
                       rel, line_num)

    # Third pass: Python-specific EmailMessage interop detection.
    # Methods like from_email_message / to_email_message / to_email_string /
    # to_email_bytes are semantic signals for EML / RFC 5322 support that the
    # generic method-name regex above does not capture (it stops at "email").
    _eml_import_re = re.compile(r'\bdef\s+from_email_(?:message|string|bytes)\b')
    _eml_export_re = re.compile(r'\bdef\s+to_email_(?:message|string|bytes)\b')
    seen_eml: set[str] = set()

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for direction, pattern in (("import", _eml_import_re),
                                   ("export", _eml_export_re)):
            if direction in seen_eml:
                continue
            m = pattern.search(text)
            if m:
                seen_eml.add(direction)
                line_num = text[:m.start()].count("\n") + 1
                formats.append({
                    "format": "eml",
                    "enum": "",
                    "value": "",
                    "file": rel,
                    "line": line_num,
                    "direction": direction,
                })
                _add_claim("format_support",
                           f"{direction} support for eml/RFC-5322 format "
                           f"(method: {m.group(0)})",
                           rel, line_num)

    # H-04: Post-extraction validation — remove false-positive entries and
    # normalize format names (strip trailing underscores, reject common words).
    formats = _validate_formats(formats, _FALSE_POSITIVE_NAMES)
    return formats, claims


def _validate_formats(
    formats: list[dict],
    false_positives: frozenset[str],
) -> list[dict]:
    """Remove false-positive format entries and normalize names."""
    valid: list[dict] = []
    for f in formats:
        name = (f.get("format") or "").strip().strip("_")
        if not name or len(name) < 2 or name.lower() in false_positives:
            continue
        f["format"] = name
        valid.append(f)
    return valid
