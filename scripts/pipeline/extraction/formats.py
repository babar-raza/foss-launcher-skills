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
    "export": {"export", "save", "write", "serialize", "render"},
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


_CPP_ONLY_VENDOR_SEGMENTS = {"internal"}


def _filter_vendor_paths(
    files: list[Path], pkg_root: Path, language: str = "",
) -> list[Path]:
    """Remove files in vendor/third-party or private bundled directories.

    Filtered directories:
    - Names in ``_VENDOR_PATH_SEGMENTS`` (vendor, vendored, third_party, etc.)
    - When *language* is ``"cpp"``, also names in ``_CPP_ONLY_VENDOR_SEGMENTS``
      (``internal``) -- mirrors ``api_surface.py``'s ``_detect_vendor_files``
      (HARDEN-cpp-internal-collision, 2026-07-28): pdf/cpp's real
      ``include/internal/`` header tree is unreachable from the library's
      public ``#include <aspose/pdf/...>`` surface. Confirmed (PDFPY-FORMATSGAP-001
      follow-on): without this, `scratch`/`unicode` -- entries from
      ``include/internal/...`` sources -- leaked into pdf/cpp's formats.json
      even though ``api_surface.json`` already correctly excludes them. Gated
      strictly to ``language == "cpp"`` so Java/.NET's own "internal"
      *package*-segment handling (a separate, unrelated mechanism) is
      untouched.
    - ``_``-prefixed directories EXCEPT ``_internal`` (which often contains
      real I/O implementations that back format enum entries).

    ``_internal`` is exempted because libraries like slides use it for actual
    exporter/importer classes, while ``_brotli``, ``_icu``, etc. contain
    transpiled or vendored code that produces false-positive format names.
    """
    _EXEMPT_PRIVATE_DIRS = {"_internal"}
    vendor_segments = _VENDOR_PATH_SEGMENTS
    if language == "cpp":
        vendor_segments = vendor_segments | _CPP_ONLY_VENDOR_SEGMENTS
    filtered: list[Path] = []
    for fpath in files:
        try:
            rel_parts = fpath.relative_to(pkg_root).parts
        except ValueError:
            filtered.append(fpath)
            continue
        skip = False
        for part in rel_parts[:-1]:
            if part.lower() in vendor_segments:
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

# Per-family allowlist: format names that are genuine user-visible formats for a
# specific family but would be false positives everywhere else.
# e.g. "cfb" is an internal impl detail in cells/python but a real user format in
# email/cpp (Compound File Binary = .msg container).
# Promoted to module level (was a local in detect_formats) so promote.py can hash it
# for extractor config provenance (config_sha in model.yaml).
_FAMILY_FORMAT_ALLOWLISTS: dict[str, frozenset[str]] = {
    "email": frozenset({"cfb"}),
    "barcode": frozenset({"png"}),
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
    if language not in ("java", "csharp", "python", "typescript", "javascript",
                        "go", "rust", "cpp"):
        return []
    if language == "cpp":
        # C++ (PDFPY-FORMATSGAP-001 follow-on): header-declared constructors,
        # e.g. `explicit Document(const std::string& filename);` in
        # document.hpp. Two things the java/csharp generic fallback below
        # doesn't handle: (1) C++ header file stems are conventionally
        # lowercase (document.hpp, not Document.hpp) -- case-insensitive
        # match required, matching _cpp_primary_stems' own lowercase set;
        # (2) C++ parameter types (const std::string&, std::filesystem::path,
        # const char*) don't match the Java/C# String|InputStream|Path|File
        # alternation. Confirmed live against pdf/cpp's real
        # include/aspose/pdf/document.hpp.
        _cpp_primary_stems = frozenset({"document", "workbook", "presentation", "spreadsheet"})
        _cpp_ctor_re = re.compile(
            r'\bDocument\s*\(\s*(?:const\s+)?(?:std::)?'
            r'(?:string|filesystem::path|char\s*\*)\b',
        )
        primary_fmt = family.title()
        if primary_fmt.lower() in existing_import_fmts:
            return []
        for fpath in files:
            if fpath.stem.lower() not in _cpp_primary_stems:
                continue
            rel = str(fpath.relative_to(repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = _cpp_ctor_re.search(text)
            if match:
                line_no = text.count("\n", 0, match.start()) + 1
                return [{
                    "format": primary_fmt,
                    "enum": "",
                    "value": "",
                    "file": rel,
                    "line": line_no,
                    "direction": "import",
                }]
        return []
    if language == "rust":
        # Rust: primary-type files expose `pub fn open/load/from_file(path ...)`
        # associated functions (e.g. Workbook::open("book.xlsx")).
        _rs_open_re = re.compile(
            r"pub\s+fn\s+(?:open|load|from_file|from_path)\s*\(")
        _rs_primary_stems = frozenset(
            {"workbook", "document", "presentation", "spreadsheet", "lib"})
        primary_fmt = _FAMILY_PYTHON_PRIMARY_FMT.get(family, family.title())
        if primary_fmt.lower() in existing_import_fmts:
            return []
        for fpath in files:
            if fpath.suffix != ".rs" or fpath.stem.lower() not in _rs_primary_stems:
                continue
            rel = str(fpath.relative_to(repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if _rs_open_re.search(line):
                    return [{
                        "format": primary_fmt,
                        "enum": "",
                        "value": "",
                        "file": rel,
                        "line": i,
                        "direction": "import",
                    }]
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
        # Matches the `def __init__(` opener through its first parameter name.
        # `\s` already spans real newlines with no flags needed, but this regex
        # was previously applied per-line via text.splitlines() (see below) --
        # that made newline-spanning `\s*` moot, since `def __init__(`, `self,`,
        # and the parameter name were never in the same `line` string for a
        # multi-line, type-hinted signature. Confirmed live: pdf/python's real
        # Document.__init__ spans 3 lines (`def __init__(` / `self,` /
        # `source: str | Path | ... = None,`) and was invisible to the old
        # per-line search regardless of which parameter names were accepted.
        # Fixed by matching against the whole file text instead of per-line.
        _py_ctor_re = re.compile(
            r'def\s+__init__\s*\(\s*self\s*,\s*'
            r'(?:file_path|filepath|path|filename|file_name|source)\b',
        )
        for fpath in files:
            if fpath.stem.lower() not in _py_primary_stems:
                continue
            rel = str(fpath.relative_to(repo)).replace("\\", "/")
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = _py_ctor_re.search(text)
            if match:
                line_no = text.count("\n", 0, match.start()) + 1
                return [{
                    "format": primary_fmt,
                    "enum": "",
                    "value": "",
                    "file": rel,
                    "line": line_no,
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


def _scan_helper_delegated_save_format(
    files: list[Path],
    repo: Path,
    language: str,
    family: str,
    existing_export_fmts: set[str],
) -> list[dict]:
    """Pass 1f (PDFPY-FORMATSGAP-001): detect a save()/load() method whose
    format-validity check is delegated to a helper function imported from a
    sibling module, rather than referencing a literal ``SaveFormat.MEMBER``
    token in the same file. `_scan_save_dispatch` (Pass 4) cannot see this
    idiom at all -- it only fires when an already-confirmed enum export
    member seeds its search (``if not save_members: return formats``), and
    for this exact idiom the enum member is precisely what's under-detected.

    Confirmed live: pdf/python's ``Document.save()`` validates
    ``save_format`` via ``_require_pdf_save_format()``, aliased from
    ``from aspose_pdf._compat_surface import require_pdf_save_format as
    _require_pdf_save_format`` -- the accepted-format token ("PDF") lives in
    a frozenset inside ``_compat_surface.py``, never in ``document.py``
    itself. Every existing pass requires the format token and the save/load
    method in the SAME file; none can see this.

    Scope: Python only. The aliased-import syntax this heuristic parses is
    Python-specific -- extending to other languages needs its own verified
    evidence, not assumed here.
    """
    if language != "python":
        return []
    primary_fmt = _FAMILY_PYTHON_PRIMARY_FMT.get(family, family.title())
    if primary_fmt.lower() in existing_export_fmts:
        return []

    _primary_stems = frozenset({"document", "workbook", "presentation", "spreadsheet"})
    # A save/load method with a parameter name containing "format".
    _save_method_re = re.compile(
        r'def\s+(?:save|load)\w*\s*\([^)]*\b\w*format\w*\s*[:=)]',
        re.IGNORECASE | re.DOTALL,
    )
    # A relative-package import statement's module path (the parenthesized
    # or trailing name list is checked separately, in a bounded window --
    # not captured here, since it may span multiple physical lines).
    _import_module_re = re.compile(r'from\s+\.?([\w.]+)\s+import\b')
    _format_name_re = re.compile(r'\w*format\w*', re.IGNORECASE)

    for fpath in files:
        if fpath.stem.lower() not in _primary_stems:
            continue
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        method_match = _save_method_re.search(text)
        if not method_match:
            continue

        for imp_match in _import_module_re.finditer(text):
            window = text[imp_match.end():imp_match.end() + 300]
            if not _format_name_re.search(window):
                continue
            module_name = imp_match.group(1).rsplit(".", 1)[-1]
            sibling = fpath.parent / f"{module_name}.py"
            if not sibling.is_file():
                continue
            try:
                sibling_text = sibling.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Confirm the sibling module actually references the family's
            # own primary format name as a quoted string -- avoids firing on
            # an unrelated "format"-named helper (e.g. a date/log formatter).
            if not re.search(
                r'["\']' + re.escape(primary_fmt) + r'["\']',
                sibling_text, re.IGNORECASE,
            ):
                continue
            line_no = text.count("\n", 0, method_match.start()) + 1
            return [{
                "format": primary_fmt,
                "enum": "",
                "value": "",
                "file": rel,
                "line": line_no,
                "direction": "export",
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


# ---------------------------------------------------------------------------
# Pass 1e (ST-022, 2026-07-30): PascalCase verb+format-token method names.
#
# Root cause: every prior pass ties format detection to either (a) an enum
# class name (FileFormat/SaveFormat/...), (b) a class NAME matching
# Importer/Exporter/Reader/Writer/Loader/Saver/Serializer/Device/Renderer, or
# (c) a snake_case method-name convention (load_from_x/save_to_x/from_x/to_x)
# meant for Python/C++. None of these fire for a language like Go, where a
# secondary format's real I/O methods live directly on the library's own
# primary document/page types with ordinary PascalCase names -- e.g. pdf/go's
# `Page.AddSVG`, `Page.AddSVGFromStream`, `Page.AddSVGObject`,
# `Document.LoadSVG`, `Document.LoadSVGFromStream` (verified against
# runs/.clone_cache/aspose_pdf_go/svg.go and knowledge/pdf/go/merged/
# api_surface.json). `Page`/`Document` are not Importer/Exporter-named, SVG
# is not this library's primary/constructor format (Pass 1c only credits
# ONE primary format per product), and the method names use no underscores
# so Pass 2's snake_case regex never matches them either. The result:
# formats.json recorded `svg: export` (from the unrelated `svgDevice` HTML
# backend, matched via the "Device" substring in the class-name pass) but
# never `svg: import`, even though the import methods are real and verified
# -- producing a false format_truth FAIL against Page.md's accurate prose.
#
# Fix: scan for `<Verb><FormatToken>(` identifiers directly (Go/Java/C# all
# use this PascalCase convention), independent of the enclosing class's name
# or its constructor-based primary format. This is deliberately an ALLOWLIST
# (_KNOWN_FORMAT_TOKENS), not a denylist, because "Add"/"Insert" in
# particular are used constantly for non-format operations in these APIs
# (AddPage, AddAnnotation, AddWatermark, InsertField, ...) -- accepting any
# capitalized suffix the way the class-name pass does would flood every
# product with false positives. Restricting the verb-prefixed suffix to
# recognized format abbreviations keeps this pass safe to run unconditionally
# across every language and family.
_PASCAL_IO_VERB_RE = re.compile(
    r"\b(Add|Insert|Load|Read|Import|Open|Parse|Save|Write|Export|Serialize)"
    r"([A-Z][A-Za-z0-9]*)\s*\(",
)
_PASCAL_IMPORT_VERBS: frozenset[str] = frozenset(
    {"add", "insert", "load", "read", "import", "open", "parse"})
_PASCAL_EXPORT_VERBS: frozenset[str] = frozenset(
    {"save", "write", "export", "serialize"})

# Known short file-format tokens recognized when they appear as the immediate
# suffix of a PascalCase I/O verb. Deliberately broad (spans the format
# vocabulary of the Aspose product families this pipeline covers: pdf,
# cells, slides, words, email, 3d, note, page, font, html, barcode, tex) --
# a generic fix must not be tuned to pdf/go specifically.
_KNOWN_FORMAT_TOKENS: frozenset[str] = frozenset({
    "svg", "pdf", "html", "htm", "xml", "json", "csv", "tsv",
    "xls", "xlsx", "xlsm", "xlsb", "ods", "doc", "docx", "docm", "odt",
    "ppt", "pptx", "pptm", "odp", "rtf", "txt", "md", "yaml", "yml",
    "png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif", "ico", "webp",
    "emf", "wmf", "eps", "ps", "svgz", "cgm", "cdr",
    "zip", "tar", "gz",
    "eml", "msg", "mbox", "vcf", "ics",
    "fbx", "obj", "gltf", "glb", "stl", "dae", "3ds", "u3d", "amf",
    "ply", "x3d", "dxf",
    "mp3", "mp4", "wav", "avi", "mov", "webm",
    "ttf", "otf", "woff", "woff2",
    "cfb", "jbig2", "epub", "mobi", "azw3", "mhtml", "chm", "xps", "djvu",
    "markdown", "latex", "tex",
})


def _split_pascal_format_token(remainder: str) -> str:
    """Extract the first camelCase/acronym word from a PascalCase identifier
    remainder (the portion of a method name right after its verb prefix).

    Applies the standard acronym-boundary rule used by camelCase splitters: a
    run of leading uppercase letters that is followed by a lowercase letter
    treats the LAST uppercase letter of that run as the start of the next
    word -- the same rule that splits "HTTPServer" into "HTTP" + "Server",
    not "HTTPS" + "erver". This lets a single, simple function correctly
    reduce every one of pdf/go's real SVG method names to the bare token
    "SVG": "AddSVG" (nothing follows -- the whole remainder is the acronym),
    "AddSVGFromStream" / "AddSVGObject" / "LoadSVGFromStream" (the acronym
    run ends because a lowercase letter follows, so the last uppercase
    letter -- "G" -- starts the next word: "SVG" + "FromStream"/"Object").
    Ordinary single-capital words (e.g. "Watermark" in "AddWatermark") take
    the other branch: consume the trailing lowercase/digit run as-is.
    """
    if not remainder:
        return ""
    j = 1
    while j < len(remainder) and remainder[j].isupper():
        j += 1
    if j == 1:
        # Ordinary capitalized word (Svg, Watermark, ...).
        k = 1
        while k < len(remainder) and (remainder[k].islower() or remainder[k].isdigit()):
            k += 1
        return remainder[:k]
    if j == len(remainder):
        # Whole remainder is one acronym run (AddSVG -> "SVG").
        return remainder
    # Acronym run ends because a lowercase letter follows -- the last
    # uppercase letter belongs to the next word (AddSVGFromStream -> "SVG").
    return remainder[: j - 1]


def _scan_pascal_verb_format_methods(
    files: list[Path],
    repo: Path,
    add_claim: object | None,
) -> list[dict]:
    """Pass 1e: detect PascalCase verb+format-token method names.

    See the module comment above _PASCAL_IO_VERB_RE for the full root-cause
    analysis (ST-022). Text-based (like Pass 2/3/4), not tree-sitter-node-
    based: Go methods use receiver syntax (`func (p *Page) AddSVG(...)`) and
    are never nested inside the struct's own type declaration the way
    Java/C# class bodies nest their methods, so a class-node-scoped scan
    (the way Pass 1's I/O-class detection works) cannot see them at all --
    a plain regex over the raw file text sidesteps that structural mismatch
    entirely and works uniformly across Go/Java/C#.
    """
    seen: set[tuple[str, str]] = set()
    new_entries: list[dict] = []

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for m in _PASCAL_IO_VERB_RE.finditer(text):
            verb = m.group(1)
            remainder = m.group(2)
            verb_lower = verb.lower()
            token = _split_pascal_format_token(remainder)
            token_lower = token.lower()
            if token_lower not in _KNOWN_FORMAT_TOKENS:
                continue
            if verb_lower in _PASCAL_IMPORT_VERBS:
                direction = "import"
            elif verb_lower in _PASCAL_EXPORT_VERBS:
                direction = "export"
            else:
                continue
            key = (token_lower, direction)
            if key in seen:
                continue
            seen.add(key)
            line_num = text[: m.start()].count("\n") + 1
            new_entries.append({
                "format": token,
                "enum": "",
                "value": "",
                "file": rel,
                "line": line_num,
                "direction": direction,
            })
            if callable(add_claim):
                add_claim(
                    "format_support",
                    f"{direction} support for {token} format "
                    f"(method name: {verb}{remainder})",
                    rel, line_num,
                )

    return new_entries


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
    files = _filter_vendor_paths(files, pkg_root, language)
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
        r"(Importer|Exporter|Reader|Writer|Loader|Saver|Serializer|Device|Renderer)", re.IGNORECASE)
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
        # H-04e: 3d/net false positives identified during TC-R05 cross-product audit
        # (2026-07-12): "basic" comes from internal class BasicLoadOptions (not a
        # user-facing format); "entity" comes from EntityRenderer (rendering framework
        # abstract class in Render/ namespace, not a file-format handler).
        "basic", "entity",
    })
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
                                  "enum_specifier", "enum_item")
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
                if re.search(r"(Exporter|Writer|Saver|Serializer|Device|Renderer)", cname, re.IGNORECASE):
                    direction = "export"
                fmt_name = re.sub(
                    r"(Importer|Exporter|Reader|Writer|Loader|Saver|Serializer|Factory|Registry|Device|Renderer)", "",
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

    # Pass 1f (PDFPY-FORMATSGAP-001): save()/load() method whose format
    # validity check is delegated to a helper imported from a sibling
    # module (no in-file SaveFormat.MEMBER token for any pass to match).
    _existing_export_fmts_1f = {
        f["format"].lower() for f in formats if f.get("direction") == "export"
    }
    for entry in _scan_helper_delegated_save_format(
        files, repo, language, family, _existing_export_fmts_1f
    ):
        formats.append(entry)
        _add_claim(
            "format_support",
            f"export support for {entry['format']} via helper-delegated "
            f"format validation",
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

    # Pass 1e (ST-022): PascalCase verb+format-token method names (Go/Java/C#
    # methods like Page.AddSVG / Document.LoadSVG that name a secondary
    # format directly, independent of class-name or primary-format ties).
    formats.extend(_scan_pascal_verb_format_methods(files, repo, _add_claim))

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
    # Rust: bare `to_x`/`from_x` are the language's TYPE-conversion idiom
    # (to_lowercase, to_vec, from_bits, to_rfc3339, ...), not format I/O —
    # found live on cells/rust (11 fake formats from one scout run). Only the
    # explicit I/O verb forms count there; every other language keeps the
    # broad pattern that C++/Python libraries rely on.
    if language == "rust":
        _method_fmt_re = re.compile(
            r'\b(?:load_from|save_to|save_as)_([a-z][a-z0-9]+)\b'
        )
    else:
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

    # HARDEN-words-net (2026-07-22): a format can have a fully-implemented,
    # non-stub reader/writer class (so the checks above conclude
    # functional=True) while STILL being unreachable because a central
    # factory/dispatcher explicitly blocks it — a known FOSS-edition pattern
    # (keep the code, gate access to it). Confirmed on words/net: HTML has a
    # complete HtmlSaveOptions/HtmlReader implementation, but
    # WriterFactory.cs/ReaderFactory.cs both throw
    # `NotSupportedException("FOSS")` for SaveFormat.Html/LoadFormat.Html
    # before ever reaching that code. This pass overrides functional=True
    # back to False whenever the format's own enum member is gated this way,
    # regardless of what the per-class stub detection above concluded.
    formats = _apply_foss_gate_overrides(formats, files, repo, _add_claim)

    # HARDEN-words-net (2026-07-23): the complementary case — a format whose
    # enum member shares a switch-dispatch fallthrough group with a confirmed
    # real I/O construction (not a NotSupportedException gate) is genuinely
    # functional even when no separately-named reader/writer class exists for
    # that specific member (e.g. words/net's Docm/Dotx/Dotm/FlatOpc variants
    # all share Docx's OpenXmlDocumentReader; only "Docx" has a name-matched
    # DocxReader.cs/DocxWriter.cs, so the naming heuristic above left the
    # other 7 as enum_only/functional=False despite identical real dispatch).
    formats = _apply_dispatch_fallthrough_overrides(formats, files, repo, _add_claim)

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
    # (case-insensitive for libraries that use Title-case enum values).
    # `::` separator covers Rust/C++ enum paths (SaveFormat::Xlsx) — found
    # live on cells/rust (2026-07-25): Workbook.rs dispatches SaveFormat::Xlsx
    # into pub fn save_xlsx(), but the dot-only pattern never matched, so the
    # real Xlsx export was demoted to enum_only.
    enum_alt = "|".join(re.escape(n) for n in sorted(enum_names))
    member_ref_re = re.compile(
        r'(?:' + enum_alt + r')\s*(?:::|\.)\s*('
        + "|".join(re.escape(m) for m in sorted(save_members))
        + r")\b",
        re.IGNORECASE,
    )
    # Method definition pattern: _save_as_X, save_as_X, _save_X.
    # `fn` keyword covers Rust (pub fn save_xlsx) — no other supported
    # language declares functions with a bare `fn`, so this stays inert
    # elsewhere.
    save_method_re = re.compile(
        r"\b(?:def|fn)\s+(_?save_?(?:as_?|to_?)?)([a-z][a-z0-9_]*)\s*\("
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


# Central-dispatch gate detection (HARDEN-words-net, 2026-07-22): a
# `case <EnumFamily>.<Member>:` switch label immediately followed (before the
# next `case`) by a throw/raise of a "this isn't supported" exception means
# that format is blocked at the dispatcher, regardless of whether a complete
# implementation class exists for it elsewhere in the source tree.
_CASE_LABEL_RE = re.compile(
    r"case\s+(SaveFormat|ExportFormat|OutputFormat|LoadFormat|ImportFormat|InputFormat|SourceFormat)"
    r"\s*\.\s*(\w+)\s*:",
    re.IGNORECASE,
)
_UNSUPPORTED_THROW_RE = re.compile(
    r"\b(?:throw\s+new\s+(?:NotSupportedException|UnsupportedOperationException)"
    r"|raise\s+NotImplementedError)\b",
    re.IGNORECASE,
)
_EXPORT_ENUM_NAMES = frozenset({"saveformat", "exportformat", "outputformat"})

# Dispatch-fallthrough functional detection (HARDEN-words-net, 2026-07-23):
# the complementary signal to the gate detection above. A `case` label group
# that falls through (no throw of its own) to a shared terminal action
# constructing and returning a real reader/writer object proves every format
# in that group is genuinely dispatched to I/O logic — even when no
# separately-named class exists for that SPECIFIC enum member. Confirmed
# live on words/net: ReaderFactory.cs's LoadFormat switch falls through
# Docx/Docm/Dotx/Dotm/FlatOpc(+3 template/macro variants) to a single
# `return new OpenXmlDocumentReader(...)` — but _cross_reference_enum_directions
# only credits "Docx" (the only member with a name-matched DocxReader.cs/
# DocxWriter.cs), demoting the other 7 to enum_only/functional=False despite
# them sharing the exact same working code path.
#
# TC-FMT-030 (2026-07-23, adversarial-review follow-up): the constructor name
# may be namespace-qualified (`return new Docx.Writer.DocxWriter(...)`), so
# the class-name group allows dots, not just \w.
_DISPATCH_RETURN_RE = re.compile(r"\breturn\s+new\s+[\w.]+\s*\(", re.IGNORECASE)

# TC-FMT-030 (2026-07-23): restrict gate/fallthrough-functional scanning to
# files that are plausibly the ACTUAL I/O dispatch layer (reader/writer/
# factory/loader/saver-named) — not just any file that happens to switch on
# the same format enum for an unrelated purpose. Confirmed live:
# DigitalSignatureUtil.cs's SignStreams() gates Docx/Dotx/Docm/Dotm because
# *signing* isn't supported for them in this FOSS edition — independent of
# whether loading/saving those same formats works, which is genuinely
# functional via the real dispatcher (ReaderFactory.cs). Without this
# filter, that unrelated switch's gate evidence wrongly suppresses the
# correct positive dispatch evidence for the same enum members. Mirrors the
# `importer_pattern` naming convention already used elsewhere in this file
# for I/O class detection (see detect_formats()).
_DISPATCH_FILE_NAME_RE = re.compile(
    r"(Factory|Reader|Writer|Loader|Saver|Importer|Exporter)", re.IGNORECASE)
_CS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CS_LINE_COMMENT_RE = re.compile(r"//[^\n]*")


def _strip_code_comments(text: str) -> str:
    """Strip C-style block and line comments (best-effort, regex-based)."""
    text = _CS_BLOCK_COMMENT_RE.sub("", text)
    text = _CS_LINE_COMMENT_RE.sub("", text)
    return text


def _find_switch_bodies(text: str) -> list[tuple[int, int]]:
    """Find (start, end) char-offset spans of each `switch (...) { ... }`
    body in text, via balanced-brace counting from the opening brace to its
    matching close.

    TC-FMT-030 (2026-07-23): case-label scans must be scoped to a single
    switch statement's own body. Without this, a "next case label" window
    computed against the whole file can span past this switch's closing
    brace into an unrelated later switch or method in the same file,
    misattributing evidence (confirmed live: a match's window jumped ~50
    lines past its own switch into an unrelated method's `return new X()`).
    Best-effort regex + brace counting, not a real parser — consistent with
    the rest of this file's C# source scanning.
    """
    bodies: list[tuple[int, int]] = []
    for m in re.finditer(r"\bswitch\s*\([^)]*\)\s*\{", text):
        depth = 0
        start = m.end() - 1  # position of the opening '{'
        i = start
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    bodies.append((start, i + 1))
                    break
            i += 1
    return bodies


def _iter_switch_case_groups(text: str):
    """Yield (group, window) for every fallthrough group of consecutive
    `case <Enum>.<Member>:` labels within each switch statement body found
    in text, where `window` is the shared terminal action text following
    the group's last label — bounded by the NEXT case label or this switch
    body's own closing brace, whichever comes first, so it can never span
    into a different switch statement or past this one's own end.

    group: list of (enum_name_lower, format_name_lower, line_number).

    TC-FMT-030 (2026-07-23): shared by both _scan_foss_gate_exceptions and
    _scan_dispatch_fallthrough_functional so a fix to the grouping/scoping
    logic (e.g. this switch-body bounding) automatically applies to both —
    an earlier version of this file had each scanner keep its own copy of
    similar logic, and one of the two had a still-unfixed bug the other one
    had already worked around, which is exactly the kind of drift a shared
    implementation prevents.
    """
    bodies = _find_switch_bodies(text)
    if not bodies:
        return
    all_matches = list(_CASE_LABEL_RE.finditer(text))
    if not all_matches:
        return
    for body_start, body_end in bodies:
        body_matches = [m for m in all_matches if body_start <= m.start() < body_end]
        group: list[tuple[str, str, int]] = []
        for i, m in enumerate(body_matches):
            enum_name = m.group(1).lower()
            fmt_lower = m.group(2).lower()
            line_num = text[:m.start()].count("\n") + 1
            window_end = body_matches[i + 1].start() if i + 1 < len(body_matches) else body_end
            window = text[m.end():window_end]
            group.append((enum_name, fmt_lower, line_num))
            if not _strip_code_comments(window).strip():
                continue  # pure fallthrough -- keep accumulating the group
            yield group, window
            group = []


def _scan_foss_gate_exceptions(
    files: list[Path], repo: Path,
) -> tuple[dict[str, tuple[str, int]], dict[str, tuple[str, int]]]:
    """Scan for `case <Enum>.<Member>:` fallthrough groups whose shared
    terminal action throws an explicit "unsupported" exception — a format
    gated this way is unreachable no matter how complete its own I/O class
    looks. Every member of the fallthrough group is attributed the gate,
    not just the one immediately preceding the throw (TC-FMT-030 fix,
    2026-07-23: a version of this function that only checked each label's
    own immediate window — empty for every label but the group's last —
    silently missed all-but-the-last member of a >1-label gated group).

    Returns (gated_export, gated_import): dicts mapping lowercase format name
    to (file, line) evidence for the FIRST gate found for that format.
    """
    gated_export: dict[str, tuple[str, int]] = {}
    gated_import: dict[str, tuple[str, int]] = {}
    for fpath in files:
        if not _DISPATCH_FILE_NAME_RE.search(fpath.name):
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "case" not in text.lower():
            continue
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        for group, window in _iter_switch_case_groups(text):
            if not _UNSUPPORTED_THROW_RE.search(window):
                continue
            for enum_name, fmt_lower, line_num in group:
                target = gated_export if enum_name in _EXPORT_ENUM_NAMES else gated_import
                if fmt_lower not in target:
                    target[fmt_lower] = (rel, line_num)
    return gated_export, gated_import


def _apply_foss_gate_overrides(
    formats: list[dict], files: list[Path], repo: Path, add_claim: object | None,
) -> list[dict]:
    """Force functional=False for any format whose enum member is gated by
    an explicit unsupported-exception dispatch (see _scan_foss_gate_exceptions).
    This is a final override — it can only tighten toward False, never the
    reverse, and only touches formats actually found gated.

    Applies regardless of the entry's PRIOR functional value — including
    absent entirely. Non-enum entries (e.g. a raw class-detection hit like
    HtmlSaveOptions.cs, direction="export") never get a `functional` key set
    by any earlier pass, so `f.get("functional", False)` alone can't
    distinguish "already correctly False" from "never set" — both must be
    forced to False here if gated, or downstream consumers (e.g.
    promote.py's format-claims reconciliation) that DO check `functional`
    would still misclassify them."""
    gated_export, gated_import = _scan_foss_gate_exceptions(files, repo)
    if not gated_export and not gated_import:
        return formats

    for f in formats:
        fmt_lower = f.get("format", "").lower()
        direction = f.get("direction", "")
        gate = gated_export.get(fmt_lower) if direction == "export" else (
            gated_import.get(fmt_lower) if direction == "import" else None)
        if gate is None:
            continue
        was_functional = f.get("functional", False)
        f["functional"] = False
        if not was_functional:
            continue  # already False (or never set) -- no claim needed, just ensure the key is set
        gate_file, gate_line = gate
        if callable(add_claim):
            add_claim(
                "format_support",
                f"{f.get('format')} {direction} is BLOCKED by an explicit "
                f"unsupported-format exception in the dispatch switch, despite "
                f"a complete implementation class existing elsewhere",
                gate_file, gate_line,
            )
    return formats


def _scan_dispatch_fallthrough_functional(
    files: list[Path], repo: Path,
) -> tuple[dict[str, tuple[str, int]], dict[str, tuple[str, int]]]:
    """Scan for `case <Enum>.<Member>:` switch-fallthrough groups whose
    shared terminal action constructs and returns a real object (e.g.
    `return new OpenXmlDocumentReader(...)`) rather than throwing an
    unsupported-format exception — proof every member of that fallthrough
    group is dispatched to genuine I/O logic. This is the complementary
    signal to _scan_foss_gate_exceptions.

    A single format is NOT guaranteed to appear in only one of this
    function's results or _scan_foss_gate_exceptions's — a codebase can
    have more than one switch on the same enum for different purposes
    (confirmed live: a digital-signature-signing helper gates the same
    enum members a totally separate, unrelated load dispatcher does not) —
    so callers that need to decide "is this format really usable" must
    apply their own precedence (see _apply_dispatch_fallthrough_overrides,
    which lets a confirmed gate win).

    Returns (functional_export, functional_import): dicts mapping lowercase
    format name to (file, line) evidence for the confirmed dispatch.
    """
    functional_export: dict[str, tuple[str, int]] = {}
    functional_import: dict[str, tuple[str, int]] = {}
    for fpath in files:
        if not _DISPATCH_FILE_NAME_RE.search(fpath.name):
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "case" not in text.lower():
            continue
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        for group, window in _iter_switch_case_groups(text):
            if not _DISPATCH_RETURN_RE.search(window):
                continue
            for enum_name, fmt_lower, line_num in group:
                target = (functional_export if enum_name in _EXPORT_ENUM_NAMES
                          else functional_import)
                if fmt_lower not in target:
                    target[fmt_lower] = (rel, line_num)
    return functional_export, functional_import


def _apply_dispatch_fallthrough_overrides(
    formats: list[dict], files: list[Path], repo: Path, add_claim: object | None,
) -> list[dict]:
    """Restore functional=True (and direction) for any enum-derived format
    entry whose member shares a switch-dispatch fallthrough group (see
    _scan_dispatch_fallthrough_functional) with a confirmed real I/O action,
    even when _cross_reference_enum_directions found no separately-named
    class for that SPECIFIC member (e.g. Docm/Dotx/Dotm sharing Docx's
    OpenXmlDocumentReader).

    This is a final, additive override — it can only loosen an
    enum_only/functional=False entry toward export/import + functional=True,
    and is scoped to enum-derived entries only (`f.get("enum")` truthy, the
    same class of entry _cross_reference_enum_directions demotes).

    A confirmed gate always wins over a fallthrough-functional match, even
    for the SAME format: they are NOT mutually exclusive by construction,
    because a codebase can have more than one switch on the same enum for
    different purposes. Confirmed live on words/net: WriterFactory.cs (the
    real save dispatcher) gates Html/Mhtml/Epub/Azw3/Mobi with
    `throw new NotSupportedException("FOSS")`, while a SEPARATE, unrelated
    switch in SaveOptions.CreateSaveOptions() (a settings-object factory,
    not the actual writer) falls through those same five members to
    `return new HtmlSaveOptions(saveFormat)` — constructing a configuration
    object is not the same as being able to actually save the format. This
    function therefore re-checks _scan_foss_gate_exceptions and skips any
    format+direction already confirmed gated, regardless of what its own
    scan found elsewhere.
    """
    functional_export, functional_import = _scan_dispatch_fallthrough_functional(files, repo)
    if not functional_export and not functional_import:
        return formats
    gated_export, gated_import = _scan_foss_gate_exceptions(files, repo)

    for f in formats:
        enum_name = f.get("enum", "")
        if not enum_name:
            continue
        if f.get("functional"):
            continue  # already confirmed functional -- nothing to add
        fmt_lower = f.get("format", "").lower()
        # The entry's OWN enum type decides which dict to consult -- a
        # format name can legitimately have evidence in BOTH dicts (e.g.
        # "docm" appears in both a LoadFormat switch and a SaveFormat
        # switch), so this must not just prefer whichever is non-empty.
        is_export_enum = enum_name.lower() in _EXPORT_ENUM_NAMES
        target_direction = "export" if is_export_enum else "import"
        if fmt_lower in (gated_export if is_export_enum else gated_import):
            continue  # a confirmed gate elsewhere always wins
        evidence = (functional_export if is_export_enum else functional_import).get(
            fmt_lower
        )
        if evidence is None:
            continue
        f["functional"] = True
        f["direction"] = target_direction
        ev_file, ev_line = evidence
        if callable(add_claim):
            add_claim(
                "format_support",
                f"{f.get('format')} {target_direction} is functional via a "
                f"shared dispatch fallthrough (confirmed: this format's "
                f"switch-case group routes to real I/O construction, not a "
                f"NotSupportedException gate)",
                ev_file, ev_line,
            )
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
