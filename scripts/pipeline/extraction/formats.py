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
    find_child_by_type,
    node_text,
)
from extraction.api_surface import _is_stub_throw


# I/O method names by direction — used to find primary methods in Exporter/Importer classes
_IO_METHOD_NAMES: dict[str, set[str]] = {
    "export": {"export", "save", "write", "serialize"},
    "import": {"import_", "load", "read", "deserialize", "parse"},
}

# Method node types per language
_METHOD_TYPES: set[str] = {
    "method_declaration",       # Java, C#
    "function_definition",      # Python, C++
    "function_declaration",     # C++
    "method_definition",        # Ruby-style (rare)
    "public_method_definition", # TypeScript
}


def _find_io_methods(class_node, direction: str, language: str) -> list:
    """Find methods in a class that match I/O naming conventions for a direction."""
    target_names = _IO_METHOD_NAMES.get(direction, set())
    methods = []
    for child in class_node.children:
        # Check class body (Java/C# wrap methods inside a body node)
        children = child.children if child.type in ("class_body", "declaration_list") else [child]
        for node in children:
            if node.type in _METHOD_TYPES:
                mname = _node_name(node, language)
                if mname and mname.lower() in target_names:
                    methods.append(node)
    return methods


def _all_io_methods_are_stubs(methods: list, language: str) -> bool:
    """True if every method in the list is a stub that throws 'not implemented'."""
    if not methods:
        return False
    for m in methods:
        body = find_child_by_type(m, "block")
        if body is None:
            body = find_child_by_type(m, "body")
        if body is None:
            return False
        stmts = [ch for ch in body.children if ch.type not in ("{", "}", "\n", "comment", ",")]
        if len(stmts) != 1:
            return False
        txt = node_text(stmts[0])
        if not _is_stub_throw(txt):
            return False
    return True


def _extract_exporter_dict_formats(class_node, language: str) -> list[str]:
    """Extract additional format names from class-level dict attributes in an I/O class.

    Handles patterns like:
        class PptxExporter(ExporterBase):
            _CONTENT_TYPES = {'Pptx': '...', 'Pptm': '...', ...}

    When an exporter class handles multiple formats via a registry dict, the
    class-name heuristic only yields one format name (e.g. 'Pptx' from
    PptxExporter). This function extracts the remaining keys so that all
    formats backed by the same exporter get I/O implementation evidence.
    """
    if language != "python":
        return []
    results: list[str] = []
    body = find_child_by_type(class_node, "block")
    if not body:
        return []
    for stmt in body.children:
        # In tree-sitter Python, class-level variable assignments appear as
        # direct 'assignment' children of the 'block' node (not wrapped in
        # 'expression_statement' like they are in some other languages).
        if stmt.type != "assignment":
            continue
        # RHS must be a dictionary literal
        rhs = find_child_by_type(stmt, "dictionary")
        if not rhs:
            continue
        # Extract string keys — accept short mixed-case alphanumeric format names
        for pair in rhs.children:
            if pair.type != "pair":
                continue
            key_node = pair.children[0] if pair.children else None
            if not key_node or key_node.type not in ("string", "concatenated_string"):
                continue
            raw = node_text(key_node).strip("'\"")
            if raw and 2 <= len(raw) <= 8 and re.match(r"^[A-Za-z][A-Za-z0-9]+$", raw):
                results.append(raw)
    return results


# H-04d: Path segments that indicate vendor/internal code.
# Files under these directories produce false-positive format names.
_VENDOR_PATH_SEGMENTS = {"vendor", "vendored", "third_party", "thirdparty"}


def _filter_vendor_paths(files: list[Path], pkg_root: Path) -> list[Path]:
    """Remove files in vendor/third-party or private bundled directories.

    Filtered directories:
    - Names in ``_VENDOR_PATH_SEGMENTS`` (vendor, vendored, third_party, etc.)
    - ``_``-prefixed directories EXCEPT ``_internal`` (which often contains
      real I/O implementations that back format enum entries).

    ``_internal`` is exempted because libraries like slides use it for actual
    exporter/importer classes, while ``_brotli``, ``_icu``, etc. contain
    transpiled or vendored code that produces false-positive format names.
    """
    _EXEMPT_PRIVATE_DIRS = {"_internal"}
    filtered: list[Path] = []
    for fpath in files:
        try:
            rel_parts = fpath.relative_to(pkg_root).parts
        except ValueError:
            filtered.append(fpath)
            continue
        skip = False
        for part in rel_parts[:-1]:
            if part.lower() in _VENDOR_PATH_SEGMENTS:
                skip = True
                break
            if (part.startswith("_") and not part.startswith("__")
                    and part not in _EXEMPT_PRIVATE_DIRS):
                skip = True
                break
        if not skip:
            filtered.append(fpath)
    return filtered


_FAMILY_PYTHON_PRIMARY_FMT: dict[str, str] = {
    # Maps family name to the specific primary file format emitted by the ctor scan
    # for Python libraries where the primary class loads one well-known format.
    # Families absent from this map fall back to family.title() (generic sentinel).
    "cells": "xlsx",  # Workbook.__init__(file_path) always loads .xlsx
}


def _scan_document_ctor_imports(
    files: list[Path],
    repo: Path,
    language: str,
    family: str,
    existing_import_fmts: set[str],
) -> list[dict]:
    """Pass 1c: Detect primary-document-class constructor import (Java/C#/Python).

    Libraries like pdf/java load files via ``new Document(path)`` without a
    dedicated ``XxxLoadOptions`` class (which Pass 1b requires).  This pass
    scans for a primary class file containing a constructor that accepts a file
    path parameter and emits one import entry for the library's primary format.

    For Python families listed in ``_FAMILY_PYTHON_PRIMARY_FMT`` the emitted
    format name is the actual file extension (e.g. ``xlsx`` for cells).  Other
    Python families fall back to ``family.title()`` as a generic sentinel.

    Java/C#: scans ``Document.java``/``Document.cs`` for constructors accepting
    ``String``, ``InputStream``, ``Path``, or ``File`` without a ``LoadOptions``
    parameter.

    Python: scans files whose stem matches common primary class names
    (``workbook``, ``document``, ``presentation``, ``spreadsheet``) for
    ``def __init__(self, file_path/filepath/path/filename=...)`` signatures.

    Does nothing when:
    - language is not Java, C#, Python, TypeScript, or JavaScript
    - an import entry for the primary format already exists (prevents duplicates
      when Pass 1b detected a ``XxxLoadOptions`` class for the same format)

    TypeScript/JavaScript: scans files whose stem matches common primary class names
    (``workbook``, ``document``, ``presentation``, ``spreadsheet``) for
    ``static [async] load(filePath/path/file...)`` signatures — the pattern used by
    libraries like cells/typescript where ``Workbook.load(filePath)`` is the import
    entry point rather than a constructor.
    """
    if language not in ("java", "csharp", "python", "typescript", "javascript", "go"):
        return []
    if language == "go":
        # Go: detect func Open(path string) or func Open(path string, ...) in *.go files
        _go_open_re = re.compile(r'^func\s+Open\s*\(\s*\w+\s+string\b')
        primary_fmt = family.title()
        if primary_fmt.lower() in existing_import_fmts:
            return []
        for fpath in files:
            if not fpath.suffix == ".go":
                continue
            rel = str(fpath.relative_to(repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if _go_open_re.match(line):
                    return [{
                        "format": primary_fmt,
                        "enum": "",
                        "value": "",
                        "file": rel,
                        "line": i,
                        "direction": "import",
                    }]
        return []
    if language in ("python", "typescript", "javascript"):
        primary_fmt = _FAMILY_PYTHON_PRIMARY_FMT.get(family, family.title())
    else:
        primary_fmt = family.title()
    if primary_fmt.lower() in existing_import_fmts:
        return []

    if language == "python":
        _py_primary_stems = frozenset({"document", "workbook", "presentation", "spreadsheet"})
        _py_ctor_re = re.compile(
            r'def\s+__init__\s*\(\s*self\s*,\s*(?:file_path|filepath|path|filename|file_name)\b',
        )
        for fpath in files:
            if fpath.stem.lower() not in _py_primary_stems:
                continue
            rel = str(fpath.relative_to(repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if _py_ctor_re.search(line):
                    return [{
                        "format": primary_fmt,
                        "enum": "",
                        "value": "",
                        "file": rel,
                        "line": i,
                        "direction": "import",
                    }]
        return []

    if language in ("typescript", "javascript"):
        _ts_primary_stems = frozenset({"document", "workbook", "presentation", "spreadsheet"})
        _ts_static_load_re = re.compile(
            r'static\s+(?:async\s+)?load\s*\(\s*(?:file[Pp]ath|filePath|path|file)\b',
        )
        for fpath in files:
            if fpath.stem.lower() not in _ts_primary_stems:
                continue
            rel = str(fpath.relative_to(repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if _ts_static_load_re.search(line):
                    return [{
                        "format": primary_fmt,
                        "enum": "",
                        "value": "",
                        "file": rel,
                        "line": i,
                        "direction": "import",
                    }]
        return []

    _ctor_path_re = re.compile(
        r'\bDocument\s*\(\s*(?:String|InputStream|Path|File)\b',
    )
    _ctor_options_re = re.compile(r'LoadOptions', re.IGNORECASE)

    for fpath in files:
        if fpath.stem != "Document":
            continue
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if _ctor_path_re.search(line) and not _ctor_options_re.search(line):
                return [{
                    "format": primary_fmt,
                    "enum": "",
                    "value": "",
                    "file": rel,
                    "line": i,
                    "direction": "import",
                }]
    return []


def _scan_ts_ooxml_writer_export(
    files: list[Path],
    repo: Path,
    family: str,
    language: str,
    existing_export_fmts: set[str],
) -> list[dict]:
    """Pass 1d: Detect TypeScript/JavaScript OOXML writer as XLSX export proof.

    Libraries like cells/typescript export XLSX via a generic ``save(filePath)``
    method that calls a ``writeToZip()``-style internal writer generating OOXML
    structure (``xl/workbook.xml``, ``[Content_Types].xml``, ``_rels/.rels``).
    No dedicated ``XlsxWriter`` class exists, so Pass 1 (I/O class detection)
    never fires.

    This pass looks for the combination of:
    1. A ``save(filePath)`` method signature on a primary-stem source file.
    2. OOXML-path string literals in the same file (e.g. ``"xl/workbook"``,
       ``"[Content_Types]"``, ``"_rels/.rels"``).

    When both signals are present the file is classified as an XLSX exporter and
    one export entry is emitted for the family's primary format.

    IMPORTANT — scope is intentionally narrow:
    - Only fires for TypeScript/JavaScript.
    - Only fires for primary-stem files (workbook, document, presentation, …).
    - Requires OOXML-specific path strings, not just any ZIP writer.
    - Does NOT emit entries for CSV/JSON/MARKDOWN even when detectFormat() dispatch
      maps those extensions to the same writeToZip() path (library bug — those
      save calls write XLSX binary with the wrong extension and are NOT functional).

    Does nothing when:
    - language is not TypeScript or JavaScript
    - an export entry for the primary format already exists
    """
    if language not in ("typescript", "javascript"):
        return []
    primary_fmt = _FAMILY_PYTHON_PRIMARY_FMT.get(family, family.title())
    if primary_fmt.lower() in existing_export_fmts:
        return []

    _ts_primary_stems = frozenset({"document", "workbook", "presentation", "spreadsheet"})
    # Signal 1: public/instance save() method accepting a file path argument
    _ts_save_re = re.compile(
        r'(?:public\s+)?(?:async\s+)?save\s*\(\s*\w',
    )
    # Signal 2: OOXML-specific path string literals (confirms the writer is xlsx)
    _ooxml_path_re = re.compile(
        r'"(?:xl/workbook|\[Content_Types\]|_rels/\.rels)',
    )

    for fpath in files:
        if fpath.stem.lower() not in _ts_primary_stems:
            continue
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _ts_save_re.search(text):
            continue
        if not _ooxml_path_re.search(text):
            continue
        # Both signals found — locate the save() line for provenance
        save_line = 0
        for i, ln in enumerate(text.splitlines(), 1):
            if _ts_save_re.search(ln):
                save_line = i
                break
        return [{
            "format": primary_fmt,
            "enum": "",
            "value": "",
            "file": rel,
            "line": save_line,
            "direction": "export",
        }]
    return []


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
    # H-04d: Filter out files in private/vendor/internal directories.
    # These contain implementation details (transpiled code, I/O helpers)
    # that produce false-positive format names.
    files = _filter_vendor_paths(files, pkg_root)
    format_pattern = re.compile(
        r"(FileFormat|FormatType|SupportedFormat|FileType|SaveFormat|ExportFormat|LoadFormat|ImportFormat|OutputFormat|InputFormat|SourceFormat|FontType)",
        re.IGNORECASE)
    # SaveFormat/ExportFormat enums indicate actual output capability
    save_format_pattern = re.compile(
        r"(SaveFormat|ExportFormat|OutputFormat)", re.IGNORECASE)
    # LoadFormat/SourceFormat enums indicate actual input capability
    # SourceFormat is used by libraries (e.g. slides/python) that detect the
    # source/input format via constructor rather than a dedicated Importer class.
    load_format_pattern = re.compile(
        r"(LoadFormat|ImportFormat|InputFormat|SourceFormat)", re.IGNORECASE)
    importer_pattern = re.compile(
        r"(Importer|Exporter|Reader|Writer|Loader|Saver|Serializer|Device)", re.IGNORECASE)
    # LoadOptions/SaveOptions classes signal constructor-based import/export
    # (e.g. HtmlLoadOptions → HTML import, PdfSaveOptions → PDF export).
    load_save_options_pattern = re.compile(
        r"^(\w+?)(Load|Save|Import|Export)Options$")

    # H-04: False-positive format names to reject after suffix stripping
    _FALSE_POSITIVE_NAMES = frozenset({
        "reader", "writer", "loader", "saver", "importer", "exporter",
        "document", "file", "stream", "base", "abstract", "default",
        "generic", "common", "internal", "helper", "utils", "factory",
        "registry",
        # H-04c: additional false positives observed in global audit (2026-05-19)
        # Note: "cfb" is kept here (blocks cells/python internal CFBWriter/CFBReader
        # encryption-impl classes); email family overrides via _allowed_fmt_overrides.
        "font", "binary", "bit", "slice", "pos", "format", "png",
        "presentation", "decode", "encode", "reserved", "difat",
        "clsid", "flags", "value", "minimal", "auto", "unknown",
        "package", "core", "data", "cfb", "xml", "message",
        "main", "col", "row", "elem", "extension", "content",
        "page", "index", "header", "table", "shape", "chart", "image",
        "geometry", "material", "matrix", "mesh", "rotation",
        "address", "storage", "black", "double", "el", "opt",
        "chars", "emu", "color", "point", "rect", "size",
        "underlying", "hex", "method", "class", "module",
        "ipackage",
    })
    # Per-family allowlist: format names that are genuine user-visible formats
    # for a specific family but are false positives everywhere else.
    # e.g. "cfb" is an internal impl detail in cells/python but a real user
    # format in email/cpp (Compound File Binary = .msg container).
    _FAMILY_FORMAT_ALLOWLISTS: dict[str, frozenset[str]] = {
        "email": frozenset({"cfb"}),
    }
    _allowed_fmt_overrides = _FAMILY_FORMAT_ALLOWLISTS.get(family, frozenset())

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if (not format_pattern.search(text)
                and not importer_pattern.search(text)
                and "LoadOptions" not in text
                and "SaveOptions" not in text):
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

            # Fallback: Python plain classes with ALLCAPS constants that
            # match format_pattern but don't inherit from enum bases.
            # Example: class SaveFormat with MARKDOWN = "markdown".
            if (not is_enum and language == "python"
                    and format_pattern.search(cname)):
                trial = _extract_python_enum_members(cn)
                if sum(1 for m in trial if m["name"].isupper()) >= 2:
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
                if re.search(r"(Exporter|Writer|Saver|Serializer|Device)", cname, re.IGNORECASE):
                    direction = "export"
                fmt_name = re.sub(
                    r"(Importer|Exporter|Reader|Writer|Loader|Saver|Serializer|Factory|Registry|Device)", "",
                    cname, flags=re.IGNORECASE).strip().strip("_")
                # H-04: reject empty, too-short, or common-word false positives
                _fmt_lower = fmt_name.lower()
                if (fmt_name and len(fmt_name) >= 2
                        and (_fmt_lower not in _FALSE_POSITIVE_NAMES
                             or _fmt_lower in _allowed_fmt_overrides)):
                    # Validate: if the primary I/O method is a stub, demote to detect-only
                    if direction in ("export", "import"):
                        io_methods = _find_io_methods(cn, direction, language)
                        if io_methods and _all_io_methods_are_stubs(io_methods, language):
                            direction = "detect"
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
                    # Also emit format names from class-level dict attributes
                    # (e.g. PptxExporter._CONTENT_TYPES has keys 'Pptm', 'Ppsx', ...)
                    for extra_fmt in _extract_exporter_dict_formats(cn, language):
                        if extra_fmt.lower() != fmt_name.lower():
                            formats.append({
                                "format": extra_fmt,
                                "enum": "",
                                "value": "",
                                "file": rel,
                                "line": cn.start_point[0] + 1,
                                "direction": direction,
                            })

            # Pass 1b: LoadOptions/SaveOptions classes indicate constructor-based
            # format support.  E.g. HtmlLoadOptions → Html import,
            # PdfSaveOptions → Pdf export.  Catches libraries (pdf/java, 3d/java)
            # where import is via `new Document(stream, loadOptions)` rather than
            # a dedicated Reader/Importer class.
            m_opts = load_save_options_pattern.match(cname)
            if m_opts and not importer_pattern.search(cname):
                fmt_name = m_opts.group(1)
                opts_type = m_opts.group(2).lower()  # "load", "save", "import", "export"
                direction = "import" if opts_type in ("load", "import") else "export"
                _fmt_lower_b = fmt_name.lower()
                if (fmt_name
                        and len(fmt_name) >= 2
                        and (_fmt_lower_b not in _FALSE_POSITIVE_NAMES
                             or _fmt_lower_b in _allowed_fmt_overrides)):
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

    # Pass 1c: primary-document-class constructor/static-load import.
    # Handles libraries like pdf/java where `new Document(path)` is the import
    # path but no dedicated PdfLoadOptions class exists for Pass 1b to detect.
    # Also handles TypeScript/JavaScript libraries like cells/typescript where
    # `static async Workbook.load(filePath)` is the import entry point.
    _existing_import_fmts = {
        f["format"].lower() for f in formats if f.get("direction") == "import"
    }
    for entry in _scan_document_ctor_imports(
        files, repo, language, family, _existing_import_fmts
    ):
        formats.append(entry)
        _add_claim(
            "format_support",
            f"import support for {entry['format']} via Document constructor",
            entry["file"], entry["line"],
        )

    # Pass 1d: TypeScript/JavaScript OOXML writer export detection.
    # Handles libraries like cells/typescript where Workbook.save(filePath) calls
    # a writeToZip()-style internal writer that generates OOXML structure
    # (xl/workbook.xml, [Content_Types].xml, _rels/.rels) — proof of XLSX export.
    # CSV/JSON/MARKDOWN are NOT upgraded even if detectFormat() dispatches them to
    # the same writeToZip() path (library bug — those paths write XLSX binary).
    _existing_export_fmts = {
        f["format"].lower() for f in formats if f.get("direction") == "export"
    }
    for entry in _scan_ts_ooxml_writer_export(
        files, repo, family, language, _existing_export_fmts
    ):
        formats.append(entry)
        _add_claim(
            "format_support",
            f"export support for {entry['format']} via OOXML writer",
            entry["file"], entry["line"],
        )

    # Second pass: scan method names for format signals embedded in naming
    # conventions (e.g., load_from_eml, save_to_eml).  Catches formats that
    # are surfaced via a high-level API method rather than a dedicated
    # Reader/Writer class — common in C++ libraries.
    _FORMAT_METHOD_SKIP = frozenset({
        "file", "stream", "bytes", "buffer", "string", "dict", "list",
        "json", "xml", "yaml", "text", "utf8", "base64", "path",
        "data", "object", "array", "value", "type", "node", "doc",
        "document", "model", "map", "tree", "memory",
        # H-04b: additional false positives observed in slides/python scout output
        "remove", "dir", "parts", "part", "argb", "name", "self",
        "args", "kwargs", "none", "true", "false", "copy", "str",
        "int", "url", "uri", "enum",
        # H-04c: additional method-name false positives from global audit
        "main", "col", "row", "elem", "extension", "content",
        "index", "header", "chart", "image", "shape", "table",
        "geometry", "material", "matrix", "mesh", "rotation",
        "address", "storage", "black", "double", "el", "opt",
        "chars", "emu", "color", "point", "rect", "size",
        "underlying", "hex",
    })
    _method_fmt_re = re.compile(
        r'\b(?:load_from|save_to|save_as|from|to)_([a-z][a-z0-9]+)\b'
    )
    # Private save method definitions: def _save_xlsx(...), def _save_csv(...)
    _save_private_re = re.compile(r'\bdef\s+_save_([a-z][a-z0-9]+)\s*\(')
    seen_mf: set[tuple[str, str]] = set()

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Scan both method-call patterns and private method definitions
        # Each match: (fmt_name, full_verb, char_offset)
        _pass2_matches: list[tuple[str, str, int]] = []
        for mfm in _method_fmt_re.finditer(text):
            _pass2_matches.append(
                (mfm.group(1).lower(), mfm.group(0), mfm.start()))
        for mfm in _save_private_re.finditer(text):
            _pass2_matches.append(
                (mfm.group(1).lower(), f"def _save_{mfm.group(1)}", mfm.start()))
        for fmt_name, full_verb, offset in _pass2_matches:
            if fmt_name in _FORMAT_METHOD_SKIP:
                continue
            if (full_verb.startswith("save_to_") or full_verb.startswith("to_")
                    or full_verb.startswith("save_as_")
                    or full_verb.startswith("def _save_")):
                direction = "export"
            else:
                direction = "import"
            key = (fmt_name, direction)
            if key in seen_mf:
                continue
            seen_mf.add(key)
            line_num = text[:offset].count("\n") + 1
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
                       f"(method name: {full_verb})",
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

    # Fourth pass: save-dispatch method scanner.  Detects inline save
    # implementations (e.g. Document._save_as_text) that are invisible to
    # the I/O class detector (Pass 1) and blocked by _FORMAT_METHOD_SKIP
    # in the method-name scanner (Pass 2).  Uses SaveFormat enum members
    # as a trusted allowlist to safely bypass the skip list.
    formats = _scan_save_dispatch(
        formats, files, repo, save_format_pattern, _add_claim,
    )

    # Cross-reference: demote SaveFormat/ExportFormat enum entries that have
    # no matching I/O class (Exporter/Writer/Saver) in the same source tree.
    formats = _cross_reference_enum_directions(
        formats, save_format_pattern, load_format_pattern,
    )

    # H-04: Post-extraction validation — remove false-positive entries and
    # normalize format names (strip trailing underscores, reject common words).
    formats = _validate_formats(formats, _FALSE_POSITIVE_NAMES, _allowed_fmt_overrides)
    return formats, claims


def _scan_save_dispatch(
    formats: list[dict],
    files: list[Path],
    repo: Path,
    save_format_pattern: re.Pattern,
    add_claim: object | None,
) -> list[dict]:
    """Pass 4: Detect inline save methods backed by SaveFormat enum dispatch.

    Scans for files where BOTH conditions are met:

    1. A ``SaveFormat.MEMBER`` constant is referenced in the file
    2. A method named ``_save_as_{member}``, ``save_as_{member}``, or
       ``_save_{member}`` is defined in the same file with a non-stub body

    When both conditions hold, emits a non-enum format entry with
    ``direction: "export"``.  The cross-reference function then sees this
    entry as backing evidence and keeps the corresponding enum member as
    ``"export"`` rather than demoting it to ``"enum_only"``.

    This handles the case where export is implemented inline in the main
    document class (e.g. ``Document._save_as_text()``) rather than via a
    dedicated Writer/Exporter class.  The SaveFormat enum acts as a trusted
    allowlist, making it safe to bypass ``_FORMAT_METHOD_SKIP``.

    Known limitation — indirect dispatch:
        Formats that save through another format's method are not detected.
        Example: ``SaveFormat.TSV`` → ``save_as_csv(path, delimiter="\\t")``.
        No ``save_as_tsv()`` exists, so the scanner finds nothing.  As of
        2026-04-16 this affects exactly 1 format (cells/python TSV) across
        all FOSS libraries.  TSV is correctly classified as ``enum_only``
        because it genuinely delegates to CSV.  A targeted detector is not
        warranted until 3+ formats across 2+ products use this pattern and
        at least one causes a content-audit FAIL.
    """
    # Collect SaveFormat/ExportFormat/OutputFormat member names from Pass 1
    save_members: set[str] = set()
    enum_names: set[str] = set()
    for f in formats:
        enum_name = f.get("enum", "")
        if not enum_name:
            continue
        if save_format_pattern.search(enum_name) and f.get("direction") == "export":
            save_members.add(f["format"].upper())
            enum_names.add(enum_name)

    if not save_members:
        return formats

    # Dynamic regex for SaveFormat/ExportFormat/OutputFormat.MEMBER references
    # (case-insensitive for libraries that use Title-case enum values)
    enum_alt = "|".join(re.escape(n) for n in sorted(enum_names))
    member_ref_re = re.compile(
        r'(?:' + enum_alt + r')\s*\.\s*('
        + "|".join(re.escape(m) for m in sorted(save_members))
        + r")\b",
        re.IGNORECASE,
    )
    # Method definition pattern: _save_as_X, save_as_X, _save_X
    save_method_re = re.compile(
        r"\bdef\s+(_?save_?(?:as_?|to_?)?)([a-z][a-z0-9_]*)\s*\("
    )

    seen: set[str] = set()
    new_entries: list[dict] = []

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Step 1: Does this file reference any SaveFormat.MEMBER?
        referenced = {m.group(1).upper() for m in member_ref_re.finditer(text)}
        if not referenced:
            continue

        # Step 2: Find save method definitions in this file
        for mm in save_method_re.finditer(text):
            method_suffix = mm.group(2).upper().strip("_")
            if method_suffix not in referenced or method_suffix in seen:
                continue

            # Step 3: Stub detection — body must have > 2 meaningful lines
            method_start = mm.start()
            next_def = text.find("\ndef ", method_start + 1)
            next_class = text.find("\nclass ", method_start + 1)
            body_end = min(
                next_def if next_def > 0 else len(text),
                next_class if next_class > 0 else len(text),
            )
            body = text[method_start:body_end]
            body_lines = [
                line.strip()
                for line in body.split("\n")
                if line.strip()
                and not line.strip().startswith("#")
                and not line.strip().startswith('"""')
                and not line.strip().startswith("'''")
            ]
            if len(body_lines) <= 2:
                continue

            seen.add(method_suffix)
            line_num = text[:method_start].count("\n") + 1
            fmt_lower = method_suffix.lower()
            new_entries.append({
                "format": fmt_lower,
                "enum": "",
                "value": "",
                "file": rel,
                "line": line_num,
                "direction": "export",
            })
            if callable(add_claim):
                add_claim(
                    "format_support",
                    f"export support for {fmt_lower} format "
                    f"(inline save dispatch: {mm.group(0).strip()})",
                    rel,
                    line_num,
                )

    formats.extend(new_entries)
    return formats


def _cross_reference_enum_directions(
    formats: list[dict],
    save_pattern: re.Pattern,
    load_pattern: re.Pattern,
) -> list[dict]:
    """Demote SaveFormat enum entries to 'detect' when no matching I/O class exists.

    After all extraction passes, enum entries from SaveFormat/ExportFormat/
    OutputFormat enums are cross-referenced against discovered I/O classes
    (Exporter, Writer, Saver) and method-name format signals.  If no matching
    implementation is found, the entry's direction is demoted from "export" to
    "detect", preventing false export-capability claims.

    FIX-13: Enhanced matching — checks suffix match, exact match, and
    method-name patterns (save_to_X, to_X, load_from_X, from_X).  Demoted
    entries also get ``functional: false`` to distinguish "enum exists but
    no I/O implementation" from entries that were never export/import.
    """
    # Build sets of format names with real implementation evidence.
    # Non-enum entries (enum == "") come from I/O class detection (Pass 1)
    # and method-name detection (Pass 2/3).
    export_impls: set[str] = set()
    import_impls: set[str] = set()
    # FIX-13: Also track method-name-derived format signals separately
    # for exact-match fallback (e.g. "eml" from save_to_eml).
    export_method_fmts: set[str] = set()
    import_method_fmts: set[str] = set()
    # FIX-13: Track formats whose I/O class exists but methods are stubs.
    stub_export_fmts: set[str] = set()
    stub_import_fmts: set[str] = set()

    for f in formats:
        if f.get("enum"):
            continue  # skip enum entries — they are what we're validating
        fmt_lower = f.get("format", "").lower()
        if not fmt_lower or len(fmt_lower) < 2:
            continue
        direction = f.get("direction", "")
        # FIX-13: stub I/O classes were demoted to "detect" in Pass 1.
        # Track original direction via the claim text if present, but
        # the simpler approach: detect-direction non-enum entries that
        # came from I/O class detection are stubs.
        if direction == "export":
            export_impls.add(fmt_lower)
            export_method_fmts.add(fmt_lower)
        elif direction == "import":
            import_impls.add(fmt_lower)
            import_method_fmts.add(fmt_lower)
        elif direction == "detect" and not f.get("enum"):
            # Non-enum detect entries are I/O classes whose methods were stubs
            stub_export_fmts.add(fmt_lower)
            stub_import_fmts.add(fmt_lower)

    # Noise suffixes that remain after Exporter/Reader stripping.
    # Patterns handle both simple cases (DocFileReader → doc) and compound
    # prefix-format naming (XlsxWorkbookWorksheetLoader → xlsx):
    #   "xlsxworkbookworksheet" → strip "workbookworksheet" → "xlsx"
    # Compound-word suffixes are stripped iteratively via the + quantifier.
    _impl_noise_re = re.compile(
        r"(?:file|document|workbook|worksheet|format|core|comments|pictures)+$",
        re.IGNORECASE,
    )

    def _has_backing(fmt_name: str, impl_set: set[str],
                     method_set: set[str]) -> bool:
        """Check if fmt_name has a backing implementation.

        FIX-13: Three-layer matching:
        1. Exact match against method-derived format names
        2. Suffix match against I/O class format names (e.g. PdfExporter → pdf)
        3. Noise-stripped suffix match (e.g. DocFileReader → doc; XlsxWorkbookWorksheet → xlsx)
           The noise regex also strips compound suffixes like "workbookworksheet" so that
           prefix-format names (cells/net: XlsxWorkbookWorksheetLoader) reduce to the
           bare format name (xlsx) and are matched by suffix in this layer.
        """
        needle = fmt_name.lower()
        # Layer 1: exact match in method-derived formats
        if needle in method_set:
            return True
        # Layer 2 + 3: suffix match, with and without noise suffix stripping
        for impl in impl_set:
            if impl.endswith(needle):
                return True
            # Layer 3: strip noise suffixes and retry suffix match
            stripped = _impl_noise_re.sub("", impl)
            if stripped and len(stripped) >= 2 and stripped.endswith(needle):
                return True
        return False

    def _is_stub_only(fmt_name: str, stub_set: set[str]) -> bool:
        """FIX-13: Check if format has only stub implementations."""
        needle = fmt_name.lower()
        return needle in stub_set

    for f in formats:
        enum_name = f.get("enum", "")
        if not enum_name:
            continue
        # Demote SaveFormat/ExportFormat/OutputFormat entries without exporters.
        # Use "enum_only" (not "detect") so audit/formats.py FD check can
        # distinguish SaveFormat stubs from generic FileFormat detection entries.
        if f.get("direction") == "export" and save_pattern.search(enum_name):
            if not _has_backing(f["format"], export_impls, export_method_fmts):
                f["direction"] = "enum_only"
                f["functional"] = False  # FIX-13: enum exists but no I/O class
            elif _is_stub_only(f["format"], stub_export_fmts):
                f["functional"] = False  # FIX-13: I/O class exists but throws
            else:
                f["functional"] = True  # has working I/O implementation
        # Demote LoadFormat/ImportFormat/InputFormat entries without readers
        elif f.get("direction") == "import" and load_pattern.search(enum_name):
            if not _has_backing(f["format"], import_impls, import_method_fmts):
                # Cross-inference: if this format has export backing it can also
                # be loaded (e.g. PPTX is loaded via OpcPackage, not a dedicated
                # importer class, so no import_impl exists — but loading is real).
                if _has_backing(f["format"], export_impls, export_method_fmts):
                    f["functional"] = True  # inferred from export backing
                else:
                    f["direction"] = "enum_only"
                    f["functional"] = False  # FIX-13: enum exists but no I/O class
            elif _is_stub_only(f["format"], stub_import_fmts):
                f["functional"] = False  # FIX-13: I/O class exists but throws
            else:
                f["functional"] = True  # has working I/O implementation

    return formats


def _validate_formats(
    formats: list[dict],
    false_positives: frozenset[str],
    allowlist: frozenset[str] = frozenset(),
) -> list[dict]:
    """Remove false-positive format entries and normalize names.

    H-04c: Enhanced validation (2026-05-19):
    - Reject entries > 12 chars (real format names are short: TTF, XLSX, PPTX)
    - Reject entries with internal underscores (compound names like decode_bit)
    - Reject entries matching compound word patterns (AutoFilterXML, etc.)
    - Enum-sourced entries (f["enum"] is set) bypass length/pattern checks
      because enum members are authoritative format identifiers.

    allowlist: per-family overrides for names that are in false_positives globally
    but are genuine user-visible formats for a specific family (e.g. "cfb" for email).
    """
    # CamelCase detection: two or more uppercase letters with lowercase between
    # them indicates a compound word (e.g. ChartXml, AutoFilterXML, MinimalCFB).
    # Real format names from suffix stripping are single words (Pptx, Xlsx, Cfb).
    _CAMELCASE_RE = re.compile(r"[a-z][A-Z]")
    valid: list[dict] = []
    for f in formats:
        name = (f.get("format") or "").strip().strip("_")
        if not name or len(name) < 2:
            continue
        if name.lower() in false_positives and name.lower() not in allowlist:
            continue
        # Enum-sourced entries are authoritative — keep them
        if not f.get("enum"):
            # Non-enum entries come from class-name suffix stripping or method
            # patterns — apply stricter validation
            if len(name) > 10:
                continue
            if "_" in name:
                continue
            # Reject CamelCase compound words (ChartXml, PictureXml, etc.)
            if _CAMELCASE_RE.search(name):
                continue
        f["format"] = name
        valid.append(f)
    return valid
