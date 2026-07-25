"""extraction/api_surface.py — API surface extraction from source trees.

Extracted from scout.py (steps 4.7). Standalone functions usable without the
Scout class.

Public API::

    extract_api_surface(parser, language, pkg_root, repo, family,
                        *, excluded_package_segments=None)
        -> tuple[list[dict], list[dict], list[str], set[str], dict]
        # (classes, claims, scanned_files, packages, scout_report)

    _is_excluded_java_package(package, excluded_segments)
        -> bool  # True when package has an excluded segment

Constants::

    _JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS  # frozenset({"internal", "impl"})
"""
from __future__ import annotations

import copy
import hashlib
import logging
import re
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)

from extraction.tree_helpers import (
    _CLASS_TYPES,
    _DOC_COMMENT_STYLES,
    _FILE_EXTENSIONS,
    _FUNC_TYPES,
    _HEADER_EXTENSIONS,
    _MODULE_TYPES,
    _PY_ENUM_BASES,
    _collect_source_files,
    _extract_bases,
    _extract_enum_members,
    _extract_python_enum_members,
    _in_excluded_preproc_branch,
    _node_name,
    child_by_field,
    collect_nodes,
    find_child_by_type,
    find_children_by_type,
    is_public,
    node_text,
    synthesize_interface_members,
    visibility_tier,
)


# ---------------------------------------------------------------------------
# SYS-PKG-001: Java internal-package exclusion filter
# ---------------------------------------------------------------------------

#: Default package segments excluded for Java at the scout/extraction layer.
#: Classes whose ``class_package`` contains any of these as a dot-separated
#: segment are not emitted to api_surface.json, preventing them from ever
#: reaching batch_reference, enrichment, or site-plan steps.
#:
#: Segment matching is exact (split on ".") — "international" is NOT matched
#: by "internal".  To disable filtering pass
#: ``excluded_package_segments=frozenset()`` to ``extract_api_surface()``.
_JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS: frozenset[str] = frozenset({"internal", "impl"})

# H-04d: Path segments that indicate vendor/internal code for Python/C++.
_VENDOR_PATH_SEGMENTS: frozenset[str] = frozenset({
    "vendor", "vendored", "third_party", "thirdparty",
})

# Private directory names that are exempt from filtering (contain real implementations)
_EXEMPT_PRIVATE_DIRS: frozenset[str] = frozenset({"_internal"})


def _detect_vendor_files(files: list[Path], pkg_root: Path) -> set[Path]:
    """Return the subset of files that are inside vendor/private directories.

    A directory is considered vendor if its name is in ``_VENDOR_PATH_SEGMENTS``.
    A directory is considered private if its name starts with ``_`` (but not ``__``)
    and is not in ``_EXEMPT_PRIVATE_DIRS``.

    These files will still be scanned (so class names appear in api_surface.json
    for diagnostic purposes) but their entries will have ``visibility: "internal"``.
    """
    vendor: set[Path] = set()
    for fpath in files:
        try:
            rel_parts = fpath.relative_to(pkg_root).parts
        except ValueError:
            continue
        for part in rel_parts[:-1]:
            if part.lower() in _VENDOR_PATH_SEGMENTS:
                vendor.add(fpath)
                break
            if (part.startswith("_") and not part.startswith("__")
                    and part not in _EXEMPT_PRIVATE_DIRS):
                vendor.add(fpath)
                break
    return vendor


def _is_excluded_java_package(package: str, excluded_segments: frozenset[str]) -> bool:
    """Return True if any dot-separated segment of *package* is in *excluded_segments*.

    Uses exact segment matching so that "international" is NOT excluded by the
    "internal" rule.

    Args:
        package: Fully-qualified Java package string, e.g. "com.aspose.slides.internal.dx".
        excluded_segments: Set of segment strings to block, e.g. frozenset({"internal"}).

    Returns:
        True when the package should be excluded; False otherwise.
    """
    if not package or not excluded_segments:
        return False
    return any(seg in excluded_segments for seg in package.split("."))


# ---------------------------------------------------------------------------
# Internal claim helper
# ---------------------------------------------------------------------------

def _make_claim(family: str, kind: str, text: str,
                file: str = "", line: int = 0) -> dict:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]
    evidence = [{"file": file, "line": line}] if file else []
    return {
        "claim_id": f"CLM-{family}-{h}",
        "kind": kind,
        "text": text,
        "confidence": 1.0,
        "claim_source": "scout",
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# Method parameter extraction
# ---------------------------------------------------------------------------

def _extract_method_params(node, language: str) -> list[dict[str, str]]:
    """Extract parameters from a method/function node."""
    params: list[dict[str, str]] = []
    param_list = (child_by_field(node, "parameters")
                  or find_child_by_type(node, "formal_parameters")
                  or find_child_by_type(node, "parameter_list")
                  or find_child_by_type(node, "parameters"))
    if param_list is None:
        return params

    for ch in param_list.children:
        if ch.type in ("formal_parameter", "parameter", "required_parameter",
                        "optional_parameter", "typed_parameter",
                        "default_parameter", "typed_default_parameter",
                        "identifier", "parameter_declaration",
                        "optional_parameter_declaration",
                        "variadic_parameter_declaration"):
            pname = ""
            ptype = ""

            name_node = child_by_field(ch, "name")
            if name_node:
                pname = node_text(name_node)
            elif ch.type == "identifier":
                pname = node_text(ch)
            else:
                for sub in ch.children:
                    if sub.type == "identifier":
                        pname = node_text(sub)
                        break

            # C++: parameter_declaration uses a "declarator" field for the name.
            # Handles default-arg forms: std::string x = {}, const T& y = T()
            if not pname and ch.type == "parameter_declaration":
                decl = child_by_field(ch, "declarator")
                if decl is not None:
                    cur = decl
                    while cur is not None and cur.type != "identifier":
                        inner = child_by_field(cur, "declarator")
                        if inner is not None:
                            cur = inner
                        else:
                            found = None
                            for gc in cur.children:
                                if gc.type == "identifier":
                                    found = gc
                                    break
                            cur = found
                    if cur is not None and cur.type == "identifier":
                        pname = node_text(cur)

            if pname in ("self", "this", "cls"):
                continue

            type_node = (child_by_field(ch, "type")
                         or find_child_by_type(ch, "type_annotation")
                         or find_child_by_type(ch, "type_identifier")
                         or find_child_by_type(ch, "predefined_type"))
            if type_node:
                ptype = node_text(type_node).lstrip(":").strip()

            if pname:
                # TC-SYS-005: Go variadic params — preserve ... prefix in type
                if ch.type == "variadic_parameter_declaration" and ptype:
                    ptype = f"...{ptype}"
                params.append({"name": pname, "type": ptype})
    return params


# ---------------------------------------------------------------------------
# Return type extraction
# ---------------------------------------------------------------------------

def _extract_return_type(node, language: str) -> str:
    """Extract the return type from a method/function node."""
    rt = child_by_field(node, "return_type")
    if rt:
        txt = node_text(rt).lstrip(":").strip()
        if txt.startswith("->"):
            txt = txt[2:].strip()
        return txt

    # type annotation after parameters (TS/Python)
    ta = find_child_by_type(node, "type_annotation")
    if ta:
        return node_text(ta).lstrip(":").strip()

    # C#/Java/C++: type before method name
    if language in ("csharp", "java", "cpp"):
        type_node = child_by_field(node, "type")
        if type_node:
            return node_text(type_node)

    # Go: use "result" field for method_declaration / function_declaration
    if language == "go":
        result = child_by_field(node, "result")
        if result:
            return node_text(result)
    return ""


def _extract_go_receiver_type(fnode) -> str:
    """Extract the receiver type name from a Go method_declaration node.

    Returns the bare type name (without pointer prefix) or "" if none.
    E.g. for ``func (d *Document) Save(...)``, returns ``"Document"``.
    """
    if fnode.type != "method_declaration":
        return ""
    # The receiver is the first parameter_list child of the method node.
    # tree-sitter-go field name is "receiver".
    recv_list = child_by_field(fnode, "receiver")
    if recv_list is None:
        # Fallback: first parameter_list child
        for ch in fnode.children:
            if ch.type == "parameter_list":
                recv_list = ch
                break
    if recv_list is None:
        return ""
    for ch in recv_list.children:
        if ch.type == "parameter_declaration":
            for pch in ch.children:
                if pch.type == "pointer_type":
                    for ppch in pch.children:
                        if ppch.type == "type_identifier":
                            return node_text(ppch)
                elif pch.type == "type_identifier":
                    return node_text(pch)
    return ""


# ---------------------------------------------------------------------------
# Doc comment extraction
# ---------------------------------------------------------------------------

def _first_sentence(text: str) -> str:
    """Return the first sentence (up to first period-space or newline)."""
    text = text.strip()
    m = re.match(r"^(.+?[.!?])(?:\s|$)", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # no sentence-ending punctuation; return first line
    return text.split("\n")[0].strip()[:200]


def _extract_rustdoc_comment(node) -> str:
    """Extract the first sentence of a Rust `///` doc comment preceding *node*.

    Rust doc comments are per-line ``line_comment`` nodes preceding the item,
    optionally separated from it by ``attribute_item`` nodes
    (``#[derive(...)]``, ``#[doc = "..."]``). Walk back over attributes first
    (collecting any ``#[doc = "..."]`` text as a fallback doc source), then
    gather the contiguous run of ``///`` line-comment nodes using the same
    line-adjacency rule as the godoc/xml_doc extractors. ``//!`` inner docs
    document the *enclosing* module, never the following item, and are
    excluded by the ``///`` prefix check.
    """
    attr_doc_parts: list[str] = []
    cur = node.prev_named_sibling
    while cur is not None and cur.type == "attribute_item":
        m = re.search(r'#\s*\[\s*doc\s*=\s*"([^"]*)"\s*\]', node_text(cur))
        if m:
            attr_doc_parts.insert(0, m.group(1))
        cur = cur.prev_named_sibling

    lines_with_row: list[tuple[int, str]] = []
    while cur is not None and cur.type == "line_comment":
        cur_txt = node_text(cur)
        if not cur_txt.lstrip().startswith("///"):
            break
        cur_row = cur.start_point[0]
        if lines_with_row and lines_with_row[0][0] - cur_row > 1:
            break  # line gap — belongs to a different comment block
        lines_with_row.insert(0, (cur_row, cur_txt))
        cur = cur.prev_named_sibling

    para_lines: list[str] = []
    for _, ln in lines_with_row:
        bare = ln.strip()
        if bare.startswith("///"):
            bare = bare[3:]
        bare = bare.strip()
        if not bare and para_lines:
            break  # blank `///` line ends the summary paragraph
        if bare:
            para_lines.append(bare)

    cleaned = " ".join(para_lines) or " ".join(attr_doc_parts)
    if cleaned:
        return _first_sentence(cleaned)
    return ""


def _extract_doc_comment(node, language: str) -> str:
    """Extract the first sentence of a doc comment preceding *node*."""
    style = _DOC_COMMENT_STYLES.get(language, "javadoc")

    if style == "rustdoc":
        return _extract_rustdoc_comment(node)

    if style == "docstring" and language == "python":
        body = child_by_field(node, "body") or find_child_by_type(node, "block")
        if body:
            for child in body.children:
                if not child.is_named:
                    continue  # skip anonymous tokens (newlines, indent, etc.)
                if child.type == "expression_statement":
                    # Some tree-sitter-python versions wrap the docstring
                    if child.children:
                        s = child.children[0]
                        if s.type in ("string", "concatenated_string"):
                            raw = node_text(s).strip("\"' \n\r")
                            return _first_sentence(raw)
                    break  # first named statement isn't a docstring
                elif child.type in ("string", "concatenated_string"):
                    # Other versions expose the docstring as a bare string node
                    raw = node_text(child).strip("\"' \n\r")
                    return _first_sentence(raw)
                else:
                    break  # first named child is not a docstring
        return ""

    # Look at previous sibling for comment
    prev = node.prev_named_sibling
    if prev is None:
        prev = node.prev_sibling
    if prev is None:
        return ""

    txt = node_text(prev)
    if style == "javadoc" or style == "jsdoc":
        if txt.startswith("/**"):
            cleaned = re.sub(r"/\*\*|\*/|\n\s*\*\s?", " ", txt).strip()
            return _first_sentence(cleaned)
    elif style == "xml_doc":
        if txt.strip().startswith("///"):
            # C# XML doc comments are per-line nodes in tree-sitter-c-sharp.
            # Walk back through consecutive adjacent-line comment nodes to
            # collect the full doc block (same pattern as godoc below).
            xml_lines_with_row: list[tuple[int, str]] = [(prev.start_point[0], txt)]
            cur = prev.prev_named_sibling
            while cur is not None and cur.type == "comment":
                cur_txt = node_text(cur)
                if not cur_txt.strip().startswith("///"):
                    break  # not an XML doc comment line
                cur_row = cur.start_point[0]
                last_row = xml_lines_with_row[0][0]
                if last_row - cur_row > 1:
                    break  # line gap — belongs to a different comment block
                xml_lines_with_row.insert(0, (cur_row, cur_txt))
                cur = cur.prev_named_sibling
            # Verify the comment block is immediately above the node
            # (last comment line must be on the line before the declaration).
            last_comment_row = xml_lines_with_row[-1][0]
            if node.start_point[0] - last_comment_row > 1:
                return ""  # gap between comment and declaration — not our doc
            xml_comment_lines = [ln for _, ln in xml_lines_with_row]
            cleaned = " ".join(l.lstrip("/ ").strip() for l in xml_comment_lines)
            # TC-SYS-007: preserve names from <paramref>, <typeparamref>,
            # and <see> tags before stripping remaining XML markup.
            cleaned = re.sub(
                r'<(?:paramref|typeparamref)\s+name="([^"]+)"\s*/?>',
                r"\1", cleaned)
            cleaned = re.sub(
                r'<see\s+cref="([^"]+)"\s*/?>',
                lambda m: m.group(1).rsplit(".", 1)[-1], cleaned)
            # strip remaining XML tags
            cleaned = re.sub(r"<[^>]+>", "", cleaned).strip()
            return _first_sentence(cleaned)
    elif style == "godoc":
        if txt.strip().startswith("//"):
            # Go doc comments are per-line nodes in tree-sitter-go.
            # Walk back through consecutive adjacent-line comment nodes to collect
            # the full doc block (stop at a gap indicating a different comment block).
            lines_with_row: list[tuple[int, str]] = [(prev.start_point[0], txt)]
            cur = prev.prev_named_sibling
            while cur is not None and cur.type == "comment":
                cur_row = cur.start_point[0]
                last_row = lines_with_row[0][0]
                if last_row - cur_row > 1:
                    break  # line gap — belongs to a different comment block
                lines_with_row.insert(0, (cur_row, node_text(cur)))
                cur = cur.prev_named_sibling
            comment_lines = [ln for _, ln in lines_with_row]
            # Extract the summary paragraph: lines before the first blank `//`
            para_lines: list[str] = []
            for ln in comment_lines:
                bare = ln.strip().lstrip("/").strip()
                if not bare:  # blank `//` line ends the summary paragraph
                    break
                para_lines.append(bare)
            cleaned = " ".join(para_lines)
            if cleaned:
                return _first_sentence(cleaned)

    return ""


# ---------------------------------------------------------------------------
# Python property extraction
# ---------------------------------------------------------------------------

def _all_decorator_text(fn) -> str:
    """Return the combined text of every decorator attached to *fn*.

    A Python function can carry multiple stacked decorators, e.g.::

        @property
        @abstractmethod
        def font_name(self) -> str: ...

    Checking only the single nearest decorator (a direct child of *fn*, or
    its one immediate previous sibling) misses this: ``@abstractmethod`` is
    the nearest sibling to the function, so a check for ``@property`` alone
    against that one node never finds it. This walks the full run of
    consecutive ``decorator`` nodes — as direct children of *fn* (some
    tree-sitter grammars attach them there) and as consecutive preceding
    siblings (the more common form) — and returns their concatenated text
    so callers can search across the whole stack, not just one layer of it.

    Root cause of ST-014 (font/python truth audit, 2026-07-24): 56 of 57
    FAILs traced to this single-decorator blind spot classifying stacked
    ``@property @abstractmethod`` members as plain callable methods.
    """
    parts = [node_text(d) for d in find_children_by_type(fn, "decorator")]

    node = fn.prev_named_sibling
    while node is not None and node.type == "decorator":
        parts.append(node_text(node))
        node = node.prev_named_sibling

    return " ".join(parts)


def _extract_python_properties(
    cnode, cname: str, rel: str, family: str,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Extract @property decorated methods in Python classes.

    Returns (properties, claims).
    """
    properties: list[dict[str, Any]] = []
    claims: list[dict] = []

    func_nodes = collect_nodes(cnode, {"function_definition"})

    # TC-SYS-019: pre-scan for @name.setter decorators to detect writable properties.
    setter_names: set[str] = set()
    for fn in func_nodes:
        dec_text = _all_decorator_text(fn)
        # Match @prop_name.setter patterns
        if ".setter" in dec_text:
            fn_name = _node_name(fn, "python")
            if fn_name:
                setter_names.add(fn_name)

    for fn in func_nodes:
        # check for @property anywhere in the decorator stack (e.g. stacked
        # with @abstractmethod — see _all_decorator_text)
        dec_text = _all_decorator_text(fn)
        if "@property" not in dec_text:
            continue
        pname = _node_name(fn, "python")
        if not pname or pname.startswith("_"):
            continue
        ret = _extract_return_type(fn, "python")
        properties.append({
            "name": pname,
            "type": ret,
            "writable": pname in setter_names,
            "doc": _extract_doc_comment(fn, "python"),
            "line": fn.start_point[0] + 1,
        })
        claims.append(_make_claim(
            family, "api_method",
            f"{cname}.{pname} property of type {ret}",
            rel, fn.start_point[0] + 1))

    return properties, claims


# ---------------------------------------------------------------------------
# Python annotated field extraction (dataclass fields, TypedDict members, etc.)
# ---------------------------------------------------------------------------

def _extract_python_annotated_fields(
    cnode, cname: str, rel: str, family: str,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Extract annotated class-level field declarations from Python classes.

    Captures plain annotated assignments in the class body such as::

        name: str
        count: int = 0
        items: list[str] = field(default_factory=list)

    These patterns are common in ``@dataclass``, ``TypedDict``, ``NamedTuple``,
    and similar declarations.  The function inspects only **direct children**
    of the class body block so that assignments inside method bodies are never
    collected by accident.

    Returns (fields, claims).
    """
    fields: list[dict[str, Any]] = []
    claims: list[dict] = []

    body = child_by_field(cnode, "body") or find_child_by_type(cnode, "block")
    if body is None:
        return fields, claims

    # TC-SYS-019: detect @dataclass decorator on the class — if present and not
    # frozen=True, all annotated fields are writable by default.
    is_dataclass = False
    is_frozen = False
    dec = find_child_by_type(cnode, "decorator")
    if dec is None:
        prev = cnode.prev_named_sibling
        if prev and prev.type == "decorator":
            dec = prev
    if dec is not None:
        dec_text = node_text(dec)
        if "dataclass" in dec_text:
            is_dataclass = True
            if "frozen=True" in dec_text or "frozen = True" in dec_text:
                is_frozen = True

    for stmt in body.children:
        if stmt.type != "assignment":
            continue

        # Annotated assignments carry a named "type" child (the annotation after
        # the colon).  Plain assignments  (x = 5)  have no such child.
        type_node = child_by_field(stmt, "type")
        if type_node is None:
            continue

        # Field name comes from the first identifier child of the assignment.
        fname = ""
        for ch in stmt.children:
            if ch.type == "identifier":
                fname = node_text(ch)
                break
        if not fname or fname.startswith("_"):
            continue

        ftype = node_text(type_node).strip()

        # ClassVar annotations mark class-level variables, not instance fields.
        if ftype.startswith("ClassVar"):
            continue

        fields.append({
            "name": fname,
            "type": ftype,
            "writable": is_dataclass and not is_frozen,
            "doc": "",
            "line": stmt.start_point[0] + 1,
        })
        claims.append(_make_claim(
            family, "api_method",
            f"{cname}.{fname} field of type {ftype}",
            rel, stmt.start_point[0] + 1))

    return fields, claims


# ---------------------------------------------------------------------------
# Python __init__ instance attribute extraction
# ---------------------------------------------------------------------------

def _extract_python_init_attributes(
    cnode, cname: str, rel: str, family: str,
    existing_names: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Extract instance attributes assigned in ``__init__`` from Python classes.

    Captures patterns like::

        def __init__(self):
            self.jpeg_quality: int = 100
            self.compliance = PdfCompliance.PDF17

    Only public attributes (not starting with ``_``) are captured.
    Attributes whose names already appear in *existing_names* (from
    ``@property`` or class-level fields) are skipped to avoid duplication.

    Returns (properties, claims).
    """
    props: list[dict[str, Any]] = []
    claims: list[dict] = []
    seen = set(existing_names or ())

    body = child_by_field(cnode, "body") or find_child_by_type(cnode, "block")
    if body is None:
        return props, claims

    # Find the __init__ method
    init_fn = None
    for child in body.children:
        if child.type == "function_definition":
            fn_name = _node_name(child, "python")
            if fn_name == "__init__":
                init_fn = child
                break
    if init_fn is None:
        return props, claims

    init_body = child_by_field(init_fn, "body") or find_child_by_type(init_fn, "block")
    if init_body is None:
        return props, claims

    # Walk all statements (including nested in if/else/try blocks)
    stmts = collect_nodes(init_body, {"assignment", "expression_statement"})
    for stmt in stmts:
        # Handle expression_statement wrapping an assignment
        target = stmt
        if stmt.type == "expression_statement":
            inner = find_child_by_type(stmt, "assignment")
            if inner is None:
                continue
            target = inner

        if target.type != "assignment":
            continue

        # Left side must be an attribute access on self: self.xxx
        left = child_by_field(target, "left")
        if left is None:
            # For some tree-sitter representations, iterate children
            for ch in target.children:
                if ch.type == "attribute":
                    left = ch
                    break
            if left is None:
                continue

        if left.type != "attribute":
            continue

        # Object must be "self"
        obj = child_by_field(left, "object")
        if obj is None or node_text(obj) != "self":
            continue

        # Attribute name
        attr_node = child_by_field(left, "attribute")
        if attr_node is None:
            continue
        attr_name = node_text(attr_node)

        # Skip private/protected attributes — underscore-prefixed backing fields
        # must not appear in the public API surface even when a matching
        # @property exists (private fields are implementation detail, not API).
        if attr_name.startswith("_"):
            continue

        # Skip duplicates (already found via @property or class-level annotation)
        if attr_name in seen:
            continue
        seen.add(attr_name)

        # Try to get type annotation
        type_node = child_by_field(target, "type")
        attr_type = node_text(type_node).strip() if type_node else ""

        props.append({
            "name": attr_name,
            "type": attr_type,
            "doc": "",
            "line": target.start_point[0] + 1,
        })
        claims.append(_make_claim(
            family, "api_method",
            f"{cname}.{attr_name} field of type {attr_type or 'unknown'}",
            rel, target.start_point[0] + 1))

    return props, claims


# ---------------------------------------------------------------------------
# Java property synthesis
# ---------------------------------------------------------------------------

_JAVA_OBJECT_METHODS: frozenset[str] = frozenset({
    "getClass", "hashCode", "equals", "toString",
    "notify", "notifyAll", "wait", "clone", "finalize",
})


def _synthesize_java_properties(
    methods: list[dict[str, Any]], cname: str, rel: str, family: str,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Synthesize property entries from Java getter/setter method pairs.

    Returns (properties, claims).
    """
    properties: list[dict[str, Any]] = []
    claims: list[dict] = []

    getters: dict[str, dict[str, Any]] = {}
    for m in methods:
        name = m["name"]
        if name in _JAVA_OBJECT_METHODS:
            continue
        params = m.get("params", [])
        if (name.startswith("get") and len(name) > 3
                and name[3].isupper() and len(params) == 0):
            prop_name = name[3].lower() + name[4:]
            getters[prop_name] = m
        elif (name.startswith("is") and len(name) > 2
              and name[2].isupper() and len(params) == 0):
            prop_name = name[2].lower() + name[3:]
            getters[prop_name] = m

    for prop_name, getter in getters.items():
        ptype = getter.get("return_type", "")
        properties.append({
            "name": prop_name,
            "type": ptype,
            "doc": getter.get("doc", ""),
            "line": getter["line"],
        })
        claims.append(_make_claim(
            family, "api_method",
            f"{cname}.{prop_name} property of type {ptype}",
            rel, getter["line"]))

    return properties, claims


# ---------------------------------------------------------------------------
# C# / Java const and static-final field extraction (Track A-1)
# ---------------------------------------------------------------------------

def _extract_const_fields(
    cnode, cname: str, rel: str, family: str, language: str,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Extract public const/static-readonly (C#) and public static final (Java) fields.

    These are accessed in content like properties (``CfbConstants.RootStreamId``)
    but are field_declaration nodes, not method_declaration or property_declaration
    nodes, so they are missed by the main extraction pass.

    Returns (properties, claims).
    """
    fields: list[dict[str, Any]] = []
    claims: list[dict] = []

    # C# class body is a declaration_list; Java class body is a class_body
    body = (find_child_by_type(cnode, "declaration_list")
            or find_child_by_type(cnode, "class_body"))
    if body is None:
        return fields, claims

    for member in body.children:
        if member.type != "field_declaration":
            continue

        # Gather ALL modifier texts (C# has one `modifier` node per keyword)
        mod_parts: list[str] = []
        var_decl_node = None
        for ch in member.children:
            if ch.type in ("modifiers", "modifier"):
                mod_parts.append(node_text(ch))
            elif ch.type == "variable_declaration":
                var_decl_node = ch
        mods = " ".join(mod_parts)

        if "public" not in mods:
            continue

        # C#: must have `const` or `readonly` (catches `static readonly`)
        if language == "csharp" and "const" not in mods and "readonly" not in mods:
            continue
        # Java: must have `final` (catches `static final`)
        if language == "java" and "final" not in mods:
            continue

        # Extract field type — C# puts it inside variable_declaration
        ftype = ""
        if var_decl_node is not None:
            type_node = child_by_field(var_decl_node, "type")
            if type_node is None:
                # fallback: first non-declarator child
                for sub in var_decl_node.children:
                    if sub.type not in ("variable_declarator", ",", ";"):
                        ftype = node_text(sub)
                        break
            else:
                ftype = node_text(type_node)
        else:
            type_node = child_by_field(member, "type")
            if type_node:
                ftype = node_text(type_node)

        # Find variable_declarator nodes — C# nests them inside variable_declaration
        declarator_parent = var_decl_node if var_decl_node is not None else member
        for ch in declarator_parent.children:
            if ch.type == "variable_declarator":
                fname_node = child_by_field(ch, "name")
                fname = node_text(fname_node) if fname_node else ""
                if not fname:
                    # fallback: first identifier in the declarator
                    for sub in ch.children:
                        if sub.type == "identifier":
                            fname = node_text(sub)
                            break
                if not fname:
                    continue

                kind = "constant" if "const" in mods else "static_field"
                fields.append({
                    "name": fname,
                    "type": ftype,
                    "kind": kind,
                    "doc": _extract_doc_comment(member, language),
                    "line": member.start_point[0] + 1,
                    "writable": False,
                })
                claims.append(_make_claim(
                    family, "api_field",
                    f"{cname}.{fname} {kind} of type {ftype}",
                    rel, member.start_point[0] + 1,
                ))

    return fields, claims


# ---------------------------------------------------------------------------
# C++ property synthesis
# ---------------------------------------------------------------------------

def _synthesize_cpp_properties(
    methods: list[dict[str, Any]], cname: str, rel: str, family: str,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Synthesize property entries from C++ getter/setter method pairs.

    The Aspose FOSS C++ headers use snake_case conventions:
      - Getter: a public method ``<name>(...)`` with 0 params and a non-void
        return type that does NOT begin with ``set_``.
      - Setter: a public method ``set_<name>(T val)`` with exactly 1 param.

    A virtual property ``<name>`` is emitted for every getter.  If a matching
    ``set_<name>`` setter exists the property is considered read-write;
    otherwise it is read-only (no effect on the emitted record — callers can
    inspect the setter list if needed).

    Returns (properties, claims).
    """
    properties: list[dict[str, Any]] = []
    claims: list[dict] = []

    # Collect setters first so we can annotate read-write properties.
    setter_names: set[str] = set()
    for m in methods:
        name = m["name"]
        params = m.get("params", [])
        if name.startswith("set_") and len(name) > 4 and len(params) == 1:
            setter_names.add(name[4:])  # strip "set_" prefix

    seen: set[str] = set()
    for m in methods:
        name = m["name"]
        params = m.get("params", [])
        ret = m.get("return_type", "")

        # Skip setters (they are not independent properties)
        if name.startswith("set_"):
            continue
        # Must have 0 parameters and a non-empty, non-void return type
        if len(params) != 0:
            continue
        if not ret or ret.strip() in ("void", ""):
            continue
        # Skip private/internal helpers (leading underscore convention)
        if name.startswith("_"):
            continue
        # De-duplicate (e.g. const and non-const overloads share the same name)
        if name in seen:
            continue
        seen.add(name)

        properties.append({
            "name": name,
            "type": ret,
            "doc": m.get("doc", ""),
            "line": m["line"],
            "writable": name in setter_names,
        })
        claims.append(_make_claim(
            family, "api_method",
            f"{cname}.{name} property of type {ret}",
            rel, m["line"]))

    return properties, claims


# ---------------------------------------------------------------------------
# FR-16: Stub method detection helpers
# ---------------------------------------------------------------------------

def _is_python_stub(mnode) -> bool:
    """Return True if a Python function body is a single raise NotImplementedError."""
    body = child_by_field(mnode, "body") or find_child_by_type(mnode, "block")
    if body is None:
        return False
    stmts = [ch for ch in body.children if ch.type not in (",", "\n", "comment")]
    if len(stmts) != 1:
        return False
    stmt = stmts[0]
    # Allow docstring + raise pattern: 2 children where first is expression_statement(string)
    if stmt.type == "expression_statement" and stmt.children:
        s = stmt.children[0]
        if s.type in ("string", "concatenated_string"):
            # This is a docstring — not a raise; look at siblings
            return False
    # raise_statement: raise NotImplementedError / raise NotImplementedError(...)
    if stmt.type == "raise_statement":
        txt = node_text(stmt)
        return "NotImplementedError" in txt
    # expression_statement containing raise: not common, but skip
    return False


def _is_python_stub_with_docstring(mnode) -> bool:
    """Return True if a Python function body is docstring + raise NotImplementedError."""
    body = child_by_field(mnode, "body") or find_child_by_type(mnode, "block")
    if body is None:
        return False
    stmts = [ch for ch in body.children if ch.type not in (",", "\n", "comment")]
    # pattern: expression_statement(string), raise_statement
    if len(stmts) == 2:
        first, second = stmts
        if (first.type == "expression_statement"
                and second.type == "raise_statement"
                and "NotImplementedError" in node_text(second)):
            return True
    return False


def _is_python_stub_any(mnode) -> bool:
    """Check both pure-raise and docstring+raise stub patterns for Python."""
    return _is_python_stub(mnode) or _is_python_stub_with_docstring(mnode)


# ---------------------------------------------------------------------------
# Generalized stub detection: catches both well-known exception types AND
# domain-specific exceptions with "not implemented"/"not supported" messages
# (e.g. ExportException("FBX export is not implemented in FOSS version")).
# ---------------------------------------------------------------------------

_STUB_EXCEPTION_RE = re.compile(
    r"(UnsupportedOperationException|NotImplementedException"
    r"|NotSupportedOperationException|NotSupportedException)",
    re.IGNORECASE,
)
_STUB_MESSAGE_RE = re.compile(
    r"not\s+(implemented|supported)|is\s+not\s+(implemented|supported)",
    re.IGNORECASE,
)


def _is_stub_throw(txt: str) -> bool:
    """True if a throw statement indicates unimplemented functionality.

    Matches both well-known exception types (UnsupportedOperationException,
    NotImplementedException) and domain-specific exceptions whose message
    contains "not implemented" or "not supported".
    """
    return bool(_STUB_EXCEPTION_RE.search(txt) or _STUB_MESSAGE_RE.search(txt))


def _is_csharp_stub(mnode) -> bool:
    """Return True if a C# method body is a single throw indicating unimplemented."""
    body = find_child_by_type(mnode, "block")
    if body is None:
        return False
    stmts = [ch for ch in body.children if ch.type not in ("{", "}", "\n", "comment")]
    if len(stmts) != 1:
        return False
    stmt = stmts[0]
    if stmt.type == "throw_statement":
        txt = node_text(stmt)
        return _is_stub_throw(txt)
    return False


def _is_java_stub(mnode) -> bool:
    """Return True if a Java method body is a single throw indicating unimplemented."""
    body = find_child_by_type(mnode, "block")
    if body is None:
        return False
    stmts = [ch for ch in body.children if ch.type not in ("{", "}", "\n", "comment")]
    if len(stmts) != 1:
        return False
    stmt = stmts[0]
    if stmt.type in ("throw_statement", "expression_statement"):
        txt = node_text(stmt)
        return _is_stub_throw(txt)
    return False


def _is_typescript_stub(mnode) -> bool:
    """Return True if a TypeScript/JavaScript method body is a single throw indicating unimplemented."""
    body = find_child_by_type(mnode, "statement_block")
    if body is None:
        return False
    stmts = [ch for ch in body.children if ch.type not in ("{", "}", "\n", "comment")]
    if len(stmts) != 1:
        return False
    stmt = stmts[0]
    if stmt.type in ("throw_statement", "expression_statement"):
        txt = node_text(stmt)
        return _is_stub_throw(txt)
    return False


def _is_cpp_stub(mnode) -> bool:
    """Return True if a C++ function body is a single throw indicating unimplemented."""
    body = find_child_by_type(mnode, "compound_statement")
    if body is None:
        body = find_child_by_type(mnode, "field_declaration_list")
    if body is None:
        return False
    stmts = [ch for ch in body.children if ch.type not in ("{", "}", "\n", "comment")]
    if len(stmts) != 1:
        return False
    stmt = stmts[0]
    if stmt.type in ("throw_statement", "expression_statement"):
        txt = node_text(stmt)
        return _is_stub_throw(txt)
    return False


# ---------------------------------------------------------------------------
# FR-15: C++ canonical namespace helper
# ---------------------------------------------------------------------------

def _cpp_canonical_namespace(cnode) -> str:
    """Walk up the AST from a C++ class node to collect all enclosing namespace names.

    Returns namespace names joined with '::' in outermost-to-innermost order.
    Example: class inside 'namespace Aspose { namespace Slides { ... } }' returns
    'Aspose::Slides'.
    """
    parts: list[str] = []
    parent = cnode.parent
    while parent is not None:
        if parent.type == "namespace_definition":
            name_node = child_by_field(parent, "name")
            if name_node:
                parts.append(node_text(name_node))
        parent = parent.parent
    parts.reverse()
    return "::".join(parts)


def _csharp_canonical_namespace(cnode) -> str:
    """Walk up from a C# class node to find the enclosing namespace.

    Handles block-scoped (``namespace X { class Y {} }``) and file-scoped
    (``namespace X; class Y {}``) forms.
    """
    # Block-scoped: walk up through namespace_declaration ancestors
    parts: list[str] = []
    parent = cnode.parent
    while parent is not None:
        if parent.type == "namespace_declaration":
            for ch in parent.children:
                if ch.type in ("qualified_name", "identifier"):
                    parts.append(node_text(ch))
                    break
        parent = parent.parent
    if parts:
        parts.reverse()
        return ".".join(parts)
    # File-scoped: find sibling file_scoped_namespace_declaration at root
    cu = cnode
    while cu.parent is not None:
        cu = cu.parent
    for ch in cu.children:
        if ch.type == "file_scoped_namespace_declaration":
            for sub in ch.children:
                if sub.type in ("qualified_name", "identifier"):
                    return node_text(sub)
    return ""


# ---------------------------------------------------------------------------
# Go struct field extraction (GO-011)
# ---------------------------------------------------------------------------


def _extract_go_struct_fields(
    cnode,
    cname: str,
    rel: str,
    family: str,
) -> tuple[list[dict], list[dict]]:
    """Extract exported fields from a Go struct type_spec node.

    Walks type_spec → struct_type → field_declaration_list → field_declaration
    and captures field_identifier nodes whose name begins with an uppercase letter
    (Go convention for exported identifiers).

    Returns (properties, claims).
    """
    properties: list[dict] = []
    claims: list[dict] = []

    # Go struct body: struct_type → field_declaration_list → field_declaration*
    struct_body = find_child_by_type(cnode, "struct_type")
    if struct_body is None:
        return properties, claims
    field_list = find_child_by_type(struct_body, "field_declaration_list")
    if field_list is None:
        return properties, claims

    for field_decl in field_list.children:
        if field_decl.type != "field_declaration":
            continue
        # field_declaration children: field_identifier* type_node
        field_names: list[str] = []
        type_node = None
        for ch in field_decl.children:
            if ch.type == "field_identifier":
                field_names.append(node_text(ch))
            else:
                # Last non-identifier child is the type
                type_node = ch

        ftype = node_text(type_node) if type_node else ""
        for fname in field_names:
            if not fname or not fname[0].isupper():
                continue  # skip unexported fields
            properties.append({
                "name": fname,
                "type": ftype,
                "kind": "property",
                "access_mode": "readwrite",
                "doc": "",
                "line": field_decl.start_point[0] + 1,
            })
            claims.append(_make_claim(
                family, "api_method",
                f"{cname}.{fname} field of type {ftype}",
                rel, field_decl.start_point[0] + 1,
            ))

    return properties, claims


# ---------------------------------------------------------------------------
# Rust struct field extraction + impl-block method association
# ---------------------------------------------------------------------------


def _extract_rust_struct_fields(
    cnode,
    cname: str,
    rel: str,
    family: str,
) -> tuple[list[dict], list[dict]]:
    """Extract `pub` fields from a Rust struct_item node.

    Walks struct_item → field_declaration_list → field_declaration and keeps
    only fields carrying a bare ``pub`` visibility modifier — private and
    ``pub(crate)``/``pub(super)`` fields are implementation detail, not public
    API. Tuple structs (ordered_field_declaration_list) and unit structs have
    no named fields and yield nothing.

    Returns (properties, claims).
    """
    properties: list[dict] = []
    claims: list[dict] = []

    body = child_by_field(cnode, "body")
    if body is None or body.type != "field_declaration_list":
        return properties, claims

    for field_decl in body.children:
        if field_decl.type != "field_declaration":
            continue
        vis = [node_text(c).strip() for c in field_decl.children
               if c.type == "visibility_modifier"]
        if "pub" not in vis:
            continue
        name_node = child_by_field(field_decl, "name")
        fname = node_text(name_node) if name_node else ""
        if not fname:
            continue
        type_node = child_by_field(field_decl, "type")
        ftype = node_text(type_node) if type_node else ""
        properties.append({
            "name": fname,
            "type": ftype,
            "kind": "property",
            "access_mode": "readwrite",
            "doc": _extract_rustdoc_comment(field_decl),
            "line": field_decl.start_point[0] + 1,
        })
        claims.append(_make_claim(
            family, "api_method",
            f"{cname}.{fname} field of type {ftype}",
            rel, field_decl.start_point[0] + 1,
        ))

    return properties, claims


def _extract_rust_impl_context(fnode) -> tuple[str, str]:
    """Return (implementing_type, trait_name) for a Rust function_item.

    Walks up from *fnode* to the enclosing ``impl_item`` (if any) and reads
    its ``type`` field (the implementing type) and optional ``trait`` field.
    Generic arguments and reference sigils are stripped so the bare type name
    matches the extracted struct/enum entry (``Workbook<'a, T>`` → ``Workbook``).
    Returns ("", "") for functions not inside an impl block.
    """
    parent = fnode.parent
    while parent is not None and parent.type != "impl_item":
        parent = parent.parent
    if parent is None:
        return "", ""

    def _bare(n) -> str:
        if n is None:
            return ""
        txt = node_text(n)
        return txt.split("<", 1)[0].strip().lstrip("&").strip()

    return (_bare(child_by_field(parent, "type")),
            _bare(child_by_field(parent, "trait")))


_RUST_TYPE_KINDS: frozenset[str] = frozenset({
    "struct_item", "enum_item", "union_item", "trait_item",
})


def _associate_rust_impl_methods(classes: list[dict]) -> list[dict]:
    """Post-process Rust entries: move impl-block methods into their type.

    Rust methods live in ``impl Type { ... }`` / ``impl Trait for Type { ... }``
    blocks, which are top-level AST nodes — the same shape as Go receiver
    methods (SFX-1). The main extraction loop records them as
    ``kind="function"`` entries carrying ``receiver_type`` (the impl target
    type) and ``trait_impl`` (the trait name, for trait impls). This pass
    relocates each such entry into the matching type's ``methods[]`` list and
    records implemented traits in the type's ``bases``. Functions whose
    receiver type was not extracted (e.g. an impl for a private type) are
    left in place, matching the Go behavior.
    """
    type_map: dict[str, int] = {}
    for i, entry in enumerate(classes):
        if entry.get("kind") in _RUST_TYPE_KINDS:
            type_map.setdefault(entry["name"], i)

    to_remove: set[int] = set()
    moved = 0
    for i, entry in enumerate(classes):
        if entry.get("kind") != "function":
            continue
        receiver = entry.get("receiver_type", "")
        if not receiver:
            continue
        idx = type_map.get(receiver)
        if idx is None:
            continue
        parent = classes[idx]
        method_entry = {
            "name": entry["name"],
            "doc": entry.get("doc", ""),
            "params": entry.get("params", []),
            "return_type": entry.get("return_type", ""),
            "line": entry.get("line", 0),
            "file": entry.get("file", ""),
            # Rust convention: `new` is the canonical associated constructor.
            "is_constructor": entry["name"] == "new",
        }
        if not isinstance(parent.get("methods"), list):
            parent["methods"] = []
        parent["methods"].append(method_entry)
        trait_name = entry.get("trait_impl", "")
        if trait_name and trait_name not in parent.get("bases", []):
            parent.setdefault("bases", []).append(trait_name)
        to_remove.add(i)
        moved += 1

    LOG.debug("Rust impl association: moved %d impl methods into %d types",
              moved, len(type_map))
    return [e for i, e in enumerate(classes) if i not in to_remove]


# ---------------------------------------------------------------------------
# Go receiver method association (SFX-1)
# ---------------------------------------------------------------------------


def _associate_go_methods(classes: list[dict]) -> list[dict]:
    """Post-process Go entries: move receiver methods into their parent type.

    In Go, method declarations are top-level AST nodes with a receiver
    parameter that names the type they belong to (e.g. ``func (d *Document)
    Save(...) error``).  The main extraction loop cannot find them as children
    of the type node, so it records them as ``kind="function"`` entries with
    a ``receiver_type`` field.  This pass relocates each such entry into the
    ``methods[]`` list of the matching type entry and removes it from the
    top-level list.
    """
    # Map type name → index in classes list
    type_map: dict[str, int] = {}
    for i, entry in enumerate(classes):
        if entry.get("kind") in ("type_spec", "type_declaration"):
            type_map[entry["name"]] = i

    to_remove: set[int] = set()
    for i, entry in enumerate(classes):
        if entry.get("kind") != "function":
            continue
        receiver = entry.get("receiver_type", "")
        if not receiver:
            continue
        recv_name = receiver.lstrip("*").strip()
        if recv_name not in type_map:
            continue
        parent = classes[type_map[recv_name]]
        method_entry = {
            "name": entry["name"],
            "doc": entry.get("doc", ""),
            "params": entry.get("params", []),
            "return_type": entry.get("return_type", ""),
            "line": entry.get("line", 0),
            "file": entry.get("file", ""),
            "is_constructor": False,
        }
        if not isinstance(parent.get("methods"), list):
            parent["methods"] = []
        parent["methods"].append(method_entry)
        to_remove.add(i)

    LOG.debug("SFX-1: moved %d receiver methods into %d Go types",
              len(to_remove), len(type_map))
    return [e for i, e in enumerate(classes) if i not in to_remove]


# ---------------------------------------------------------------------------
# Partial-class consolidation
# ---------------------------------------------------------------------------


_VIS_RANK = {"exported": 3, "public": 2, "conventional": 1, "internal": 0}


def _merge_members(target: dict, source: dict) -> None:
    """Merge methods, properties, and bases from *source* into *target*.

    HARDEN-A11 (2026-07-22): members are deepcopy'd before appending, matching
    the ST-013 fix in _flatten_inheritance(). This wasn't exploitable as a live
    bug today ONLY because every `source` merged here is unconditionally
    discarded by the caller (consolidate_classes()) right after — no other
    surviving class holds the same object. That invariant lives entirely in
    caller discipline, not in this function's own contract, and is exactly the
    shape of assumption ST-013 violated once already. Copying here removes the
    dependency on that invariant rather than trusting it to hold forever.
    """
    # Methods: dedup by (name, params_str)
    existing_sigs: set[tuple[str, str]] = {
        (m.get("name", ""), str(m.get("params", "")))
        for m in target.get("methods", [])
    }
    for m in source.get("methods", []):
        sig = (m.get("name", ""), str(m.get("params", "")))
        if sig not in existing_sigs:
            target.setdefault("methods", []).append(copy.deepcopy(m))
            existing_sigs.add(sig)
    # Properties: dedup by name
    existing_pnames: set[str] = {p.get("name", "") for p in target.get("properties", [])}
    for p in source.get("properties", []):
        if p.get("name", "") not in existing_pnames:
            target.setdefault("properties", []).append(copy.deepcopy(p))
            existing_pnames.add(p.get("name", ""))
    # Bases: dedup
    existing_bases = set(target.get("bases", []))
    for b in source.get("bases", []):
        if b not in existing_bases:
            target.setdefault("bases", []).append(b)
            existing_bases.add(b)
    # Doc: prefer entry with more content
    if not target.get("doc") and source.get("doc"):
        target["doc"] = source["doc"]
    # Provenance
    src_file = source.get("file", "")
    if src_file:
        target.setdefault("_merged_files", [target.get("file", "")])
        if src_file not in target["_merged_files"]:
            target["_merged_files"].append(src_file)
    # Class-level modifiers: union (e.g., is_static from one fragment)
    for mod_key in ("is_static", "is_abstract", "is_sealed", "is_partial"):
        if source.get(mod_key):
            target[mod_key] = True


def consolidate_classes(classes: list[dict], language: str) -> list[dict]:
    """Merge partial classes, disambiguate same-name-different-namespace, dedup enums.

    Must run BEFORE ``_flatten_inheritance`` so the by-name dict used for
    inheritance resolution is correct.

    Categories handled:
      1. Same namespace + ``is_partial`` → MERGE members
      2. Same namespace + stub (no bases, fewer members) → KEEP full, discard stub
      3. Same namespace + compat shim (bases reference the other) → DISCARD shim
      4. Different namespace → KEEP BOTH (distinct ``class_import``)
      5. Identical enums (same enum_members or both empty) → DEDUP
      6. Fallback (no namespace, same visibility) → MERGE (backward compat)

    Returns a new list.
    """
    from collections import Counter, defaultdict

    name_counts = Counter(c.get("name", "") for c in classes)
    # Fast path: if no duplicates at all, return as-is
    dup_names = {n for n, cnt in name_counts.items() if cnt > 1 and n}
    if not dup_names:
        return list(classes)

    groups: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(classes):
        n = c.get("name", "")
        if n in dup_names:
            groups[n].append(i)

    discard: set[int] = set()
    merge_count = 0

    for name, indices in groups.items():
        entries = [classes[i] for i in indices]

        # Sub-group by canonical_namespace (or class_import minus name)
        ns_groups: dict[str, list[int]] = defaultdict(list)
        for idx in indices:
            e = classes[idx]
            ns = e.get("canonical_namespace", "")
            if not ns:
                ci = e.get("class_import", "")
                if ci and ci != e.get("name", ""):
                    ns = ci.rsplit(".", 1)[0] if "." in ci else ""
            ns_groups[ns].append(idx)

        # If all entries share the same namespace (or all empty), handle as same-ns
        # If they differ, keep all (different namespaces = different types)
        for ns, ns_indices in ns_groups.items():
            if len(ns_indices) < 2:
                continue

            ns_entries = [classes[i] for i in ns_indices]
            kinds = [e.get("kind", "") for e in ns_entries]

            # Category 5: identical enums
            if all("enum" in k for k in kinds):
                # Keep first, discard rest
                for i in ns_indices[1:]:
                    discard.add(i)
                continue

            # Category 1: partial classes (at least one has is_partial)
            any_partial = any(e.get("is_partial") for e in ns_entries)
            if any_partial:
                # Pick the entry with the most total members as primary
                def _member_count(e: dict) -> int:
                    return len(e.get("methods", [])) + len(e.get("properties", []))
                primary_idx = max(ns_indices, key=lambda i: _member_count(classes[i]))
                primary = classes[primary_idx]
                for i in ns_indices:
                    if i == primary_idx:
                        continue
                    _merge_members(primary, classes[i])
                    discard.add(i)
                    merge_count += 1
                LOG.debug("MERGE-PARTIAL: %s — %d fragments → 1",
                          name, len(ns_indices))
                continue

            # Category 3: compat shim (one's bases list references the other by name)
            # Must run BEFORE stub-discard: a shim has bases (referencing the
            # real class), so the stub heuristic would wrongly keep the shim.
            shim_found = False
            for i in ns_indices:
                bases = classes[i].get("bases", [])
                for b in bases:
                    short_base = b.rsplit(".", 1)[-1] if "." in b else b
                    if short_base == name:
                        discard.add(i)
                        shim_found = True
                        LOG.debug("DISCARD-SHIM: %s — %s inherits from same-name type",
                                  name, classes[i].get("file", ""))
                        break
            if shim_found:
                continue

            # Category 2: stub vs full (one has bases, others don't)
            with_bases = [i for i in ns_indices if classes[i].get("bases")]
            without_bases = [i for i in ns_indices if not classes[i].get("bases")]
            if with_bases and without_bases:
                for i in without_bases:
                    discard.add(i)
                LOG.debug("DISCARD-STUB: %s — kept %d with bases, discarded %d stubs",
                          name, len(with_bases), len(without_bases))
                continue

            # Category 6: fallback — merge on same visibility (backward compat)
            vis_groups: dict[int, list[int]] = defaultdict(list)
            for i in ns_indices:
                rank = _VIS_RANK.get(classes[i].get("visibility", "conventional"), 1)
                vis_groups[rank].append(i)
            for rank, vis_indices in vis_groups.items():
                if len(vis_indices) < 2:
                    continue
                primary_idx = max(vis_indices,
                                  key=lambda i: (len(classes[i].get("methods", []))
                                                 + len(classes[i].get("properties", []))))
                primary = classes[primary_idx]
                for i in vis_indices:
                    if i == primary_idx:
                        continue
                    _merge_members(primary, classes[i])
                    discard.add(i)
                    merge_count += 1
                LOG.debug("MERGE-FALLBACK: %s — %d entries with rank %d → 1",
                          name, len(vis_indices), rank)

    if merge_count:
        LOG.info("consolidate_classes: merged %d partial-class fragment(s)", merge_count)
    if discard:
        LOG.info("consolidate_classes: discarded %d duplicate(s)", len(discard) - merge_count)

    return [c for i, c in enumerate(classes) if i not in discard]


# ---------------------------------------------------------------------------
# Core API surface extraction
# ---------------------------------------------------------------------------


def _flatten_inheritance(classes: list[dict]) -> None:
    """Copy inherited methods/properties into child classes (in-place).

    Walks the full inheritance tree (not just direct parents) by resolving
    classes in topological order so parents are populated before children.
    Child definitions take precedence over inherited ones.
    Handles cycles via visited-set guard.
    """
    # Use class_import as key when available for namespace-aware resolution;
    # also index by short name as fallback for base-class lookup.
    by_name: dict[str, dict] = {}
    for c in classes:
        key = c.get("class_import") or c.get("name", "")
        if key:
            by_name[key] = c
        short = c.get("name", "")
        if short and short not in by_name:
            by_name[short] = c

    resolved: set[str] = set()

    def _resolve(cls_name: str, visiting: set[str]) -> None:
        if cls_name in resolved or cls_name not in by_name:
            return
        if cls_name in visiting:  # cycle guard
            return
        visiting.add(cls_name)
        cls = by_name[cls_name]
        # Resolve parents first so their inherited members are populated
        for base_name in cls.get("bases", []):
            _resolve(base_name, visiting)
        # Copy from each parent (now includes grandparent members)
        for base_name in cls.get("bases", []):
            parent = by_name.get(base_name)
            if parent is None:
                continue
            # Deep-copy each inherited member — the parent's method/property
            # dicts must never be shared by reference across classes. Without
            # this, any later pass that mutates one class's copy of an
            # inherited member (e.g. a doc backfill) silently corrupts the
            # parent's own entry and every other class that inherited the
            # same member, since they all pointed at the identical object.
            # Confirmed root cause of ST-013 (3d/java truth audit 2026-07-14):
            # identical wrong doc text appeared on ~37 unrelated pages because
            # they all rendered the same shared, mutated dict.
            child_method_names = {m["name"] for m in cls.get("methods", [])}
            for m in parent.get("methods", []):
                if m["name"] not in child_method_names:
                    cls.setdefault("methods", []).append(copy.deepcopy(m))
                    child_method_names.add(m["name"])
            child_prop_names = {p["name"] for p in cls.get("properties", [])}
            for p in parent.get("properties", []):
                if p["name"] not in child_prop_names:
                    cls.setdefault("properties", []).append(copy.deepcopy(p))
                    child_prop_names.add(p["name"])
        visiting.discard(cls_name)
        resolved.add(cls_name)

    for cls in classes:
        name = cls.get("name")
        if name:
            _resolve(name, set())


def _mark_package_init_exports(classes: list[dict], source_files: list[Path]) -> None:
    """Mark Python classes re-exported via any package __init__.py.__all__.

    PY-INIT-001: Packages that define classes in _internal/ and re-export them
    from __init__.py use a legitimate "implementation hiding" pattern.  The
    per-file __all__ extraction (S-1) only sets visibility="exported" when the
    class definition and __all__ are in the SAME file.  Cross-file re-exports
    from __init__.py are invisible to that check.

    This post-pass unions all __all__ names from every __init__.py in the
    source tree and sets exported_via_package_init=True on matching classes.
    index.py._is_public_api_entry() checks this flag before applying the
    /_internal/ path filter, so re-exported classes are counted as public API.
    """
    package_all_names: set[str] = set()
    for src_file in source_files:
        if src_file.name != "__init__.py":
            continue
        # Only read __init__.py files that are NOT inside a private implementation
        # subtree (a directory starting with a single "_", e.g. _internal/).
        # This ensures we only aggregate exports from the package's public interface
        # modules, not from internal subpackage init files.
        if any(p.startswith("_") and not p.startswith("__")
               for p in src_file.parts):
            continue
        try:
            content = src_file.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"__all__\s*=\s*\[([^\]]*)\]", content, re.DOTALL)
            if match:
                package_all_names.update(re.findall(r'["\'](\w+)["\']', match.group(1)))
        except OSError:
            pass

    if not package_all_names:
        return

    for entry in classes:
        if entry.get("name") in package_all_names:
            entry["exported_via_package_init"] = True


def extract_api_surface(
    parser,
    language: str,
    pkg_root: Path,
    repo: Path,
    family: str,
    *,
    excluded_package_segments: frozenset[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[str], set[str], dict[str, Any]]:
    """Extract API classes, methods, and properties from source files.

    Args:
        parser: tree-sitter parser for *language*.
        language: Language key (e.g. "java", "python").
        pkg_root: Root directory of the package source tree.
        repo: Root of the FOSS repository clone.
        family: Product family identifier (e.g. "slides").
        excluded_package_segments: For Java, a frozenset of dot-separated
            package segment strings whose matching classes should be excluded
            from the output.  When ``None`` (default) the Java-specific
            defaults :data:`_JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS` are used
            (``{"internal", "impl"}``).  Pass ``frozenset()`` to disable all
            package filtering.  Ignored for non-Java languages.

    Returns:
        Tuple of (classes, claims, scanned_files, packages, scout_report).
        *scout_report* is a dict with keys ``files_attempted``,
        ``files_parsed``, ``files_skipped``, and ``skip_reasons``.
    """
    classes: list[dict[str, Any]] = []
    claims: list[dict] = []
    scanned_files: list[str] = []
    packages: set[str] = set()

    # Completeness tracking (S1-6)
    files_attempted: int = 0
    files_skipped: list[str] = []
    skip_reasons: dict[str, int] = {}
    parse_errors: list[str] = []

    # SYS-PKG-001: resolve effective Java package exclusion segments once.
    # None → apply language default; frozenset() → disable filtering.
    if language == "java":
        _effective_excluded_segments: frozenset[str] = (
            _JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS
            if excluded_package_segments is None
            else excluded_package_segments
        )
    else:
        _effective_excluded_segments = frozenset()

    ext = _FILE_EXTENSIONS.get(language, ".py")
    header_ext = _HEADER_EXTENSIONS.get(language, "")
    _collection_stats: dict[str, Any] = {}
    files = _collect_source_files(pkg_root, ext, header_ext, stats=_collection_stats)

    # H-04d: Pre-compute set of files in vendor/private directories.
    # Classes from these files will be marked visibility="internal".
    _vendor_files = _detect_vendor_files(files, pkg_root)

    class_types = _CLASS_TYPES.get(language, set())
    func_types = _FUNC_TYPES.get(language, set())

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        files_attempted += 1
        try:
            src = fpath.read_bytes()
        except OSError as e:
            files_skipped.append(rel)
            reason = type(e).__name__
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue

        tree = parser.parse(src)
        root = tree.root_node
        if root.has_error:
            parse_errors.append(rel)
            LOG.debug("tree-sitter parse error in %s — extraction may be incomplete", rel)
        scanned_files.append(rel)

        # Track packages/namespaces
        module_types = _MODULE_TYPES.get(language, set())
        for mnode in collect_nodes(root, module_types):
            # C++ namespace_definition: extract name field instead of full text
            if language == "cpp" and mnode.type == "namespace_definition":
                name_node = child_by_field(mnode, "name")
                if name_node:
                    packages.add(node_text(name_node))
                continue
            # Rust mod_item: extract the name field — the node text of an
            # inline module (`mod foo { ... }`) spans the entire module body.
            if language == "rust" and mnode.type == "mod_item":
                name_node = child_by_field(mnode, "name")
                if name_node:
                    packages.add(node_text(name_node))
                continue
            pkg_text = node_text(mnode).strip().rstrip(";").rstrip("{").strip()
            for kw in ("package", "namespace"):
                if pkg_text.startswith(kw):
                    pkg_text = pkg_text[len(kw):].strip()
            if pkg_text:
                packages.add(pkg_text)

        # FR-15: capture Java file-level package declaration once per file
        java_file_package = ""
        if language == "java":
            for pkg_node in collect_nodes(root, {"package_declaration"}):
                pkg_txt = node_text(pkg_node).strip().rstrip(";")
                if pkg_txt.startswith("package"):
                    java_file_package = pkg_txt[len("package"):].strip()
                break

        class_nodes = collect_nodes(root, class_types)

        # S-1: Extract __all__ names for Python visibility tier.
        # Only handles simple top-level assignment (`__all__ = [...]`).
        # Intentionally does NOT handle `__all__ += [...]`, conditional
        # assignments, or __init__.py re-export aggregation — these are
        # rare in the Aspose FOSS repos and would require control-flow
        # analysis.  Unrecognized patterns fall back gracefully to
        # "public" or "conventional" visibility, which is safe.
        module_all_names: set[str] = set()
        if language == "python":
            for stmt in root.children:
                if stmt.type == "assignment":
                    lhs = child_by_field(stmt, "left")
                    rhs = child_by_field(stmt, "right")
                    if lhs and node_text(lhs).strip() == "__all__" and rhs:
                        rhs_text = node_text(rhs)
                        module_all_names = set(
                            re.findall(r'["\'](\w+)["\']', rhs_text)
                        )
                        break

        for cnode in class_nodes:
            if not is_public(cnode, language):
                continue

            cname = _node_name(cnode, language)
            if not cname:
                continue

            # SYS-PKG-001: exclude Java classes in internal/impl packages.
            # Check uses the file-level java_file_package captured above the loop.
            if (language == "java"
                    and _effective_excluded_segments
                    and _is_excluded_java_package(java_file_package, _effective_excluded_segments)):
                continue

            # Skip C++ forward declarations (class Foo;) — no body
            if (language == "cpp"
                    and cnode.type in ("class_specifier", "struct_specifier")
                    and find_child_by_type(cnode, "field_declaration_list") is None):
                continue

            is_enum = cnode.type in ("enum_declaration", "enum_definition",
                                     "enum_specifier", "enum_item")
            # SFX-2: For Go type_spec nodes, the godoc comment precedes the
            # parent type_declaration node, not the type_spec itself.  Pass
            # the parent when available so _extract_doc_comment can find it.
            if language == "go" and cnode.type == "type_spec" and cnode.parent is not None:
                cdoc = _extract_doc_comment(cnode.parent, language)
            else:
                cdoc = _extract_doc_comment(cnode, language)
            bases = _extract_bases(cnode, language)

            # Python: detect enums by base class inheritance
            if not is_enum and language == "python":
                if set(bases) & _PY_ENUM_BASES:
                    is_enum = True

            if is_enum:
                if language == "python":
                    enum_members = _extract_python_enum_members(cnode)
                else:
                    enum_members = _extract_enum_members(cnode, language)
            elif language == "python":
                # Convention-based enum detection: plain classes whose
                # body consists entirely of ALL_CAPS assignments are
                # treated as enum-like (common in 3D/Python libraries).
                candidates = _extract_python_enum_members(cnode)
                if candidates and all(
                    m["name"].replace("_", "").isupper()
                    for m in candidates
                ):
                    enum_members = candidates
                    is_enum = True
                else:
                    enum_members = []
            else:
                enum_members = []

            methods: list[dict[str, Any]] = []
            properties: list[dict[str, Any]] = []

            method_nodes = collect_nodes(cnode, func_types)
            for mnode in method_nodes:
                # Skip members whose declaration lives inside a C#
                # `#if DEBUG` / `#elif JAVA` / `#if CPLUSPLUS` / etc. branch
                # that is unreachable in a real .NET Release build -- this
                # source is shared across the Java/C++/Python ports of the
                # same product, and Debug-only helpers or other-language-only
                # overrides were leaking into api_surface.json and being
                # rendered as real public .NET API. Found 2026-07-23 via an
                # independent review of the words/net launch (Node.cs's
                # `dd()` and its `#elif JAVA`-only `ToString()` override).
                if _in_excluded_preproc_branch(mnode, language):
                    continue
                if not is_public(mnode, language):
                    continue
                mname = _node_name(mnode, language)
                if not mname:
                    continue

                # FIX-02: Skip methods that belong to nested classes.
                # collect_nodes does a deep DFS, so methods inside nested
                # private/internal classes appear in the parent's list.
                # Check if mnode has a class ancestor that is NOT cnode itself.
                if language in ("csharp", "java"):
                    _parent = mnode.parent
                    _in_nested = False
                    while _parent is not None and _parent != cnode:
                        if _parent.type in class_types:
                            _in_nested = True
                            break
                        _parent = _parent.parent
                    if _in_nested:
                        continue

                # Skip Python @property and setter/deleter — handled by _extract_python_properties.
                # Checks the full decorator stack (see _all_decorator_text), not just the
                # single nearest decorator — a bare @abstractmethod check would otherwise
                # miss @property stacked with another decorator (root cause of ST-014).
                if language == "python" and mnode.type == "function_definition":
                    dec_text = _all_decorator_text(mnode)
                    if "@property" in dec_text or ".setter" in dec_text or ".deleter" in dec_text:
                        continue

                # FR-14: TypeScript getter/setter accessors → kind: property, not callable
                if language in ("typescript", "javascript"):
                    if mnode.type in ("get_signature", "set_signature"):
                        # Explicit TS accessor signature nodes
                        acc_mode = "readonly" if mnode.type == "get_signature" else "writeonly"
                        ptype = ""
                        type_node = (child_by_field(mnode, "return_type")
                                     or find_child_by_type(mnode, "type_annotation"))
                        if type_node:
                            ptype = node_text(type_node).lstrip(":").strip()
                        # Merge with existing same-name property if present
                        existing_prop = next(
                            (p for p in properties
                             if p.get("name") == mname and p.get("kind") == "property"),
                            None,
                        )
                        if existing_prop is not None:
                            existing_prop["access_mode"] = "readwrite"
                        else:
                            properties.append({
                                "name": mname,
                                "type": ptype,
                                "kind": "property",
                                "access_mode": acc_mode,
                                "doc": "",
                                "line": mnode.start_point[0] + 1,
                            })
                            claims.append(_make_claim(
                                family, "api_method",
                                f"{cname}.{mname} property of type {ptype}",
                                rel, mnode.start_point[0] + 1))
                        continue
                    # method_definition that begins with 'get ' or 'set '
                    if mnode.type == "method_definition":
                        raw_txt = node_text(mnode).lstrip()
                        is_getter = raw_txt.startswith("get ")
                        is_setter = raw_txt.startswith("set ")
                        if is_getter or is_setter:
                            acc_mode = "readonly" if is_getter else "writeonly"
                            ptype = ""
                            if is_getter:
                                type_node = (child_by_field(mnode, "return_type")
                                             or find_child_by_type(mnode, "type_annotation"))
                                if type_node:
                                    ptype = node_text(type_node).lstrip(":").strip()
                            existing_prop = next(
                                (p for p in properties
                                 if p.get("name") == mname and p.get("kind") == "property"),
                                None,
                            )
                            if existing_prop is not None:
                                existing_prop["access_mode"] = "readwrite"
                                if is_getter and ptype and not existing_prop.get("type"):
                                    existing_prop["type"] = ptype
                            else:
                                properties.append({
                                    "name": mname,
                                    "type": ptype,
                                    "kind": "property",
                                    "access_mode": acc_mode,
                                    "doc": "",
                                    "line": mnode.start_point[0] + 1,
                                })
                                claims.append(_make_claim(
                                    family, "api_method",
                                    f"{cname}.{mname} property of type {ptype}",
                                    rel, mnode.start_point[0] + 1))
                            continue

                if mnode.type in ("property_declaration",
                                  "public_field_definition",
                                  "property_signature"):
                    ptype = ""
                    type_node = child_by_field(mnode, "type")
                    if type_node:
                        ptype = node_text(type_node)
                    # Detect setter — C# accessor_list with "set" or "init"
                    writable = False
                    acc_list = find_child_by_type(mnode, "accessor_list")
                    if acc_list is not None:
                        for acc in acc_list.children:
                            if acc.type == "accessor_declaration":
                                acc_text = node_text(acc).lstrip()
                                if acc_text.startswith(("set", "init")):
                                    writable = True
                                    break
                    properties.append({
                        "name": mname,
                        "type": ptype,
                        "doc": _extract_doc_comment(mnode, language),
                        "line": mnode.start_point[0] + 1,
                        "writable": writable,
                    })
                    claims.append(_make_claim(
                        family, "api_method",
                        f"{cname}.{mname} property of type {ptype}",
                        rel, mnode.start_point[0] + 1))
                    continue

                params = _extract_method_params(mnode, language)
                ret = _extract_return_type(mnode, language)
                mdoc = _extract_doc_comment(mnode, language)

                is_ctor = (mnode.type == "constructor_declaration"
                           or (language == "python" and mname == "__init__")
                           or (language in ("typescript", "javascript")
                               and mname == "constructor"))

                # FR-16: stub detection — methods that only raise/throw NotImplemented*
                method_entry: dict[str, Any] = {
                    "name": mname,
                    "params": params,
                    "return_type": ret,
                    "doc": mdoc,
                    "line": mnode.start_point[0] + 1,
                    "is_constructor": is_ctor,
                }
                if language == "python" and _is_python_stub_any(mnode):
                    method_entry["stub"] = True
                elif language == "csharp" and _is_csharp_stub(mnode):
                    method_entry["stub"] = True
                elif language == "java" and _is_java_stub(mnode):
                    method_entry["stub"] = True
                elif language in ("typescript", "javascript") and _is_typescript_stub(mnode):
                    method_entry["stub"] = True
                elif language == "cpp" and _is_cpp_stub(mnode):
                    method_entry["stub"] = True

                methods.append(method_entry)
                claims.append(_make_claim(
                    family, "api_method",
                    f"{cname}.{mname}({', '.join(p['name'] for p in params)}) -> {ret}",
                    rel, mnode.start_point[0] + 1))

            # Python properties via decorators
            if language == "python":
                extra_props, extra_claims = _extract_python_properties(
                    cnode, cname, rel, family)
                properties.extend(extra_props)
                claims.extend(extra_claims)

            # Python annotated fields (dataclass fields, TypedDict members, etc.)
            if language == "python":
                extra_fields, extra_claims = _extract_python_annotated_fields(
                    cnode, cname, rel, family)
                properties.extend(extra_fields)
                claims.extend(extra_claims)

            # Python __init__ instance attributes (self.xxx = value)
            if language == "python":
                existing_prop_names = {p["name"] for p in properties}
                init_props, init_claims = _extract_python_init_attributes(
                    cnode, cname, rel, family, existing_prop_names)
                properties.extend(init_props)
                claims.extend(init_claims)

            # Java properties via getter/setter synthesis
            if language == "java":
                extra_props, extra_claims = _synthesize_java_properties(
                    methods, cname, rel, family)
                properties.extend(extra_props)
                claims.extend(extra_claims)

            # C++ properties via getter/setter synthesis
            if language == "cpp":
                extra_props, extra_claims = _synthesize_cpp_properties(
                    methods, cname, rel, family)
                properties.extend(extra_props)
                claims.extend(extra_claims)

            # C# public const / static readonly fields + Java public static final fields
            # These are accessed like properties in content (e.g. CfbConstants.RootStreamId)
            # but are NOT captured by the method/property_declaration pass above.
            if language in ("csharp", "java"):
                extra_props, extra_claims = _extract_const_fields(
                    cnode, cname, rel, family, language)
                properties.extend(extra_props)
                claims.extend(extra_claims)

            # C++ field_declaration: method declarations (no body) AND public data members
            if language == "cpp":
                body = find_child_by_type(cnode, "field_declaration_list")
                if body:
                    access = "public" if cnode.type == "struct_specifier" else "private"
                    for member in body.children:
                        if member.type == "access_specifier":
                            access = node_text(member).strip().rstrip(":")
                        elif member.type == "function_definition" and access == "public":
                            # Inline method definition (has body): void SetBold(bool v) { ... }
                            fdecl = find_child_by_type(member, "function_declarator")
                            if fdecl is None:
                                for _wrapper_type in ("reference_declarator", "pointer_declarator"):
                                    _wrapper = find_child_by_type(member, _wrapper_type)
                                    if _wrapper:
                                        fdecl = find_child_by_type(_wrapper, "function_declarator")
                                        if fdecl:
                                            break
                            if fdecl is not None:
                                mname = ""
                                for ch in fdecl.children:
                                    if ch.type in ("identifier", "field_identifier", "destructor_name"):
                                        mname = node_text(ch)
                                        break
                                if mname and not mname.startswith("_"):
                                    params = _extract_method_params(fdecl, language)
                                    ret = _extract_return_type(member, language)
                                    mdoc = _extract_doc_comment(member, language)
                                    methods.append({
                                        "name": mname,
                                        "params": params,
                                        "return_type": ret,
                                        "doc": mdoc,
                                        "line": member.start_point[0] + 1,
                                        "is_constructor": False,
                                    })
                                    claims.append(_make_claim(
                                        family, "api_method",
                                        f"{cname}.{mname}({', '.join(p['name'] for p in params)}) -> {ret}",
                                        rel, member.start_point[0] + 1))
                        elif member.type == "field_declaration" and access == "public":
                            fdecl = find_child_by_type(member, "function_declarator")
                            # Support reference/pointer return types: T& GetFoo() or T* GetFoo()
                            # tree-sitter wraps function_declarator inside reference_declarator
                            # or pointer_declarator in these cases, so direct search misses them.
                            if fdecl is None:
                                for _wrapper_type in ("reference_declarator", "pointer_declarator"):
                                    _wrapper = find_child_by_type(member, _wrapper_type)
                                    if _wrapper:
                                        fdecl = find_child_by_type(_wrapper, "function_declarator")
                                        if fdecl:
                                            break
                            if fdecl is not None:
                                # Method declaration (no body) — common in header files
                                mname = ""
                                for ch in fdecl.children:
                                    if ch.type in ("identifier", "field_identifier"):
                                        mname = node_text(ch)
                                        break
                                if not mname:
                                    continue
                                params = _extract_method_params(fdecl, language)
                                ret = _extract_return_type(member, language)
                                mdoc = _extract_doc_comment(member, language)
                                methods.append({
                                    "name": mname,
                                    "params": params,
                                    "return_type": ret,
                                    "doc": mdoc,
                                    "line": member.start_point[0] + 1,
                                    "is_constructor": False,
                                })
                                claims.append(_make_claim(
                                    family, "api_method",
                                    f"{cname}.{mname}({', '.join(p['name'] for p in params)}) -> {ret}",
                                    rel, member.start_point[0] + 1))
                            else:
                                # Public data member (e.g., std::string name;)
                                fname = ""
                                for ch in member.children:
                                    if ch.type in ("identifier", "field_identifier"):
                                        fname = node_text(ch)
                                        break
                                if not fname or fname.startswith("_"):
                                    continue
                                ftype = ""
                                type_node = child_by_field(member, "type")
                                if type_node:
                                    ftype = node_text(type_node)
                                mdoc = _extract_doc_comment(member, language)
                                properties.append({
                                    "name": fname,
                                    "type": ftype,
                                    "doc": mdoc,
                                    "line": member.start_point[0] + 1,
                                    "writable": True,  # public data members are read-write
                                })
                                claims.append(_make_claim(
                                    family, "api_method",
                                    f"{cname}.{fname} data member of type {ftype}",
                                    rel, member.start_point[0] + 1))

            # Go exported struct fields (e.g. RenderOptions.DPI, Rectangle.LLX)
            if language == "go":
                extra_props, extra_claims = _extract_go_struct_fields(
                    cnode, cname, rel, family)
                properties.extend(extra_props)
                claims.extend(extra_claims)

            # Rust pub struct fields (e.g. Workbook.path)
            if language == "rust":
                extra_props, extra_claims = _extract_rust_struct_fields(
                    cnode, cname, rel, family)
                properties.extend(extra_props)
                claims.extend(extra_claims)

            vis = visibility_tier(
                cnode, language,
                has_docstring=bool(cdoc),
                in_module_all=(cname in module_all_names),
            )
            # H-04d: Override visibility for vendor/private directory classes
            if fpath in _vendor_files:
                vis = "internal"
            # OBS-03: Remove self-referential bases (tree-sitter extraction bug)
            bases = [b for b in bases if b != cname]

            # TC-MT007-01 (G-40): synthesize standard interface-contract members
            # (Dispose, MoveNext/Reset/Current, GetEnumerator, CompareTo) for
            # classes implementing a known BCL interface without an explicit
            # same-file override. C#-only; see synthesize_interface_members's
            # own docstring for the full finding and scope rationale.
            _synth_methods, _synth_properties = synthesize_interface_members(
                bases, methods, properties, language)
            methods = methods + _synth_methods
            properties = properties + _synth_properties

            # Extract class-level modifiers (C#/Java: static, abstract, sealed)
            # Uses the same tree-sitter pattern as _extract_const_fields (L664).
            _cls_mods: set[str] = set()
            if language in ("csharp", "java"):
                for _ch in cnode.children:
                    if _ch.type in ("modifiers", "modifier"):
                        _cls_mods.update(node_text(_ch).lower().split())

            cls_record: dict[str, Any] = {
                "name": cname,
                "kind": cnode.type,
                "doc": cdoc,
                "file": rel,
                "line": cnode.start_point[0] + 1,
                "bases": bases,
                "methods": methods,
                "properties": properties,
                "visibility": vis,
            }
            if "static" in _cls_mods:
                cls_record["is_static"] = True
            if "abstract" in _cls_mods:
                cls_record["is_abstract"] = True
            if "sealed" in _cls_mods:
                cls_record["is_sealed"] = True
            if "partial" in _cls_mods:
                cls_record["is_partial"] = True
            if is_enum:
                cls_record["enum_members"] = enum_members

            # FR-15: canonical_namespace (C++, C#) and class_package (Java)
            if language == "cpp":
                canonical_ns = _cpp_canonical_namespace(cnode)
                if canonical_ns:
                    cls_record["canonical_namespace"] = canonical_ns
                    cls_record["class_import"] = f"{canonical_ns}::{cname}"
                else:
                    cls_record["class_import"] = cname
            elif language == "java":
                # java_file_package is captured at file level above the class loop
                if java_file_package:
                    cls_record["class_package"] = java_file_package
                    cls_record["class_import"] = f"{java_file_package}.{cname}"
                else:
                    cls_record["class_import"] = cname
            elif language == "csharp":
                canonical_ns = _csharp_canonical_namespace(cnode)
                if canonical_ns:
                    cls_record["canonical_namespace"] = canonical_ns
                    cls_record["class_import"] = f"{canonical_ns}.{cname}"
                else:
                    cls_record["class_import"] = cname
            elif language == "python":
                # Derive from file path relative to pkg_root
                try:
                    py_rel = fpath.relative_to(pkg_root)
                    parts = list(py_rel.parts)
                    if parts and parts[-1].endswith(".py"):
                        parts[-1] = parts[-1][:-3]
                    if parts and parts[-1] == "__init__":
                        parts = parts[:-1]
                    if parts:
                        module_path = ".".join(parts)
                        cls_record["class_import"] = f"{module_path}.{cname}"
                except ValueError:
                    pass
            elif language == "rust":
                # Module path derived from file location relative to pkg_root
                # (src/): src/worksheet.rs → "worksheet", src/foo/mod.rs →
                # "foo", src/lib.rs → crate root (no module segment).
                # Segments that are not valid Rust module identifiers are
                # dropped: crates like Aspose.Cells-FOSS-for-Rust keep source
                # under a dotted directory (src/Aspose.Cells_FOSS/) wired via
                # `#[path = "..."] mod api;` and re-export every type at the
                # crate root — a path like `Aspose.Cells_FOSS::Workbook` is
                # not a real Rust path, so such types get the bare type name
                # (crate-root import), the Rust analog of PY-INIT-001.
                try:
                    rs_rel = fpath.relative_to(pkg_root)
                    parts = list(rs_rel.parts)
                    if parts and parts[-1].endswith(".rs"):
                        parts[-1] = parts[-1][:-3]
                    if parts and parts[-1] in ("lib", "main", "mod"):
                        parts = parts[:-1]
                    # ANY invalid segment means the layout is #[path]-mapped —
                    # the whole derived path is unreliable, not just that
                    # segment (the file-stem "module" under a dotted dir is
                    # not a real module either).
                    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p)
                           for p in parts):
                        parts = []
                    if parts:
                        module_path = "::".join(parts)
                        cls_record["canonical_namespace"] = module_path
                        cls_record["class_import"] = f"{module_path}::{cname}"
                    else:
                        cls_record["class_import"] = cname
                except ValueError:
                    cls_record["class_import"] = cname

            classes.append(cls_record)
            claims.append(_make_claim(
                family, "api_class",
                f"Class {cname} defined in {rel}",
                rel, cnode.start_point[0] + 1))

        # top-level functions (not inside classes)
        top_funcs = collect_nodes(root, func_types)
        for fnode in top_funcs:
            # skip if nested inside a class
            parent = fnode.parent
            in_class = False
            while parent:
                if parent.type in class_types:
                    in_class = True
                    break
                parent = parent.parent
            if in_class:
                continue
            if not is_public(fnode, language):
                continue
            fname = _node_name(fnode, language)
            if not fname:
                continue
            params = _extract_method_params(fnode, language)
            ret = _extract_return_type(fnode, language)
            fdoc = _extract_doc_comment(fnode, language)

            # SFX-1: For Go methods, capture receiver type so _associate_go_methods
            # can move them into their parent type's methods[] list later.
            receiver_type = ""
            rust_trait = ""
            if language == "go":
                receiver_type = _extract_go_receiver_type(fnode)
            elif language == "rust":
                # Rust impl-block methods surface here (impl_item is not a
                # class-type node); capture the impl target + trait so
                # _associate_rust_impl_methods can relocate them.
                receiver_type, rust_trait = _extract_rust_impl_context(fnode)

            func_entry: dict[str, Any] = {
                "name": fname,
                "kind": "function",
                "doc": fdoc,
                "file": rel,
                "line": fnode.start_point[0] + 1,
                "bases": [],
                "methods": [],
                "properties": [],
                "params": params,
                "return_type": ret,
            }
            if receiver_type:
                func_entry["receiver_type"] = receiver_type
            if rust_trait:
                func_entry["trait_impl"] = rust_trait
            classes.append(func_entry)
            claims.append(_make_claim(
                family, "api_method",
                f"Function {fname}({', '.join(p['name'] for p in params)}) -> {ret}",
                rel, fnode.start_point[0] + 1))

    # SFX-1: Associate Go receiver methods with their parent type entries.
    # Go methods are top-level nodes (not children of type nodes), so the
    # collect_nodes pass inside the class loop finds 0 methods. This pass
    # moves them into the correct type's methods[] list.
    if language == "go":
        classes = _associate_go_methods(classes)

    # Rust: same shape as Go — impl-block methods are top-level nodes, so
    # relocate them into their owning struct/enum/trait entries.
    if language == "rust":
        classes = _associate_rust_impl_methods(classes)

    # Consolidate partial classes, deduplicate enums, disambiguate same-name
    # types in different namespaces.  Must run BEFORE _flatten_inheritance so
    # the by-name dict used for inheritance resolution is correct.
    classes = consolidate_classes(classes, language)

    # TC-HCR-001: Flatten inherited methods/properties into child classes
    # so that evaluators can verify inherited member access without walking
    # the inheritance chain at evaluation time.
    _flatten_inheritance(classes)

    # PY-INIT-001: Mark classes re-exported via any package __init__.py.__all__.
    # The per-file __all__ extraction (S-1) only fires when __all__ and class
    # definitions share the same file.  Packages that define classes in _internal/
    # and re-export them from __init__.py have their public API understated by
    # _is_public_api_entry() in index.py.  This post-pass adds the field
    # exported_via_package_init: true so index.py can override the path filter.
    if language == "python":
        _mark_package_init_exports(classes, files)

    scout_report: dict[str, Any] = {
        "files_attempted": files_attempted,
        "files_parsed": files_attempted - len(files_skipped),
        "files_skipped": files_skipped,
        "skip_reasons": skip_reasons,
        "parse_errors": parse_errors,
        "parse_error_rate": len(parse_errors) / max(files_attempted, 1),
        # HARDEN-words-net: files_attempted above already reflects the
        # post-MAX_FILES-cap count, so it alone can't reveal truncation (a
        # capped product and one that fit comfortably look identical). These
        # two fields make that fact durable in the artifact itself.
        "total_source_files_found": _collection_stats.get("candidates_found", files_attempted),
        "files_capped": _collection_stats.get("files_capped", False),
    }
    return classes, claims, scanned_files, packages, scout_report
