"""extraction/api_surface.py — API surface extraction from source trees.

Extracted from scout.py (steps 4.7). Standalone functions usable without the
Scout class.

Public API::

    extract_api_surface(parser, language, pkg_root, repo, family,
                        *, excluded_package_segments=None)
        -> tuple[list[dict], list[dict], list[str], set[str]]
        # (classes, claims, scanned_files, packages)

    _is_excluded_java_package(package, excluded_segments)
        -> bool  # True when package has an excluded segment

Constants::

    _JAVA_DEFAULT_EXCLUDED_PACKAGE_SEGMENTS  # frozenset({"internal", "impl"})
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

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
    _node_name,
    child_by_field,
    collect_nodes,
    find_child_by_type,
    is_public,
    node_text,
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
                        "optional_parameter_declaration"):
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

    # Go: bare type node after parameter_list
    if language == "go":
        found_params = False
        for ch in node.children:
            if ch.type == "parameter_list":
                found_params = True
                continue
            if found_params and ch.type not in ("{", "block"):
                return node_text(ch)
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


def _extract_doc_comment(node, language: str) -> str:
    """Extract the first sentence of a doc comment preceding *node*."""
    style = _DOC_COMMENT_STYLES.get(language, "javadoc")

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
            lines = txt.strip().splitlines()
            cleaned = " ".join(l.lstrip("/ ").strip() for l in lines)
            # strip XML tags
            cleaned = re.sub(r"<[^>]+>", "", cleaned).strip()
            return _first_sentence(cleaned)
    elif style == "godoc":
        if txt.strip().startswith("//"):
            lines = txt.strip().splitlines()
            cleaned = " ".join(l.lstrip("/ ").strip() for l in lines)
            return _first_sentence(cleaned)

    return ""


# ---------------------------------------------------------------------------
# Python property extraction
# ---------------------------------------------------------------------------

def _extract_python_properties(
    cnode, cname: str, rel: str, family: str,
) -> tuple[list[dict[str, Any]], list[dict]]:
    """Extract @property decorated methods in Python classes.

    Returns (properties, claims).
    """
    properties: list[dict[str, Any]] = []
    claims: list[dict] = []

    func_nodes = collect_nodes(cnode, {"function_definition"})
    for fn in func_nodes:
        # check for @property decorator
        dec = find_child_by_type(fn, "decorator")
        if dec is None:
            # check previous sibling
            prev = fn.prev_named_sibling
            if prev and prev.type == "decorator":
                dec = prev
        if dec is None:
            continue
        dec_text = node_text(dec)
        if "@property" not in dec_text:
            continue
        pname = _node_name(fn, "python")
        if not pname or pname.startswith("_"):
            continue
        ret = _extract_return_type(fn, "python")
        properties.append({
            "name": pname,
            "type": ret,
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

        # Skip private/protected
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


# ---------------------------------------------------------------------------
# Core API surface extraction
# ---------------------------------------------------------------------------

def extract_api_surface(
    parser,
    language: str,
    pkg_root: Path,
    repo: Path,
    family: str,
    *,
    excluded_package_segments: frozenset[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict], list[str], set[str]]:
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
        Tuple of (classes, claims, scanned_files, packages).
    """
    classes: list[dict[str, Any]] = []
    claims: list[dict] = []
    scanned_files: list[str] = []
    packages: set[str] = set()

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
    files = _collect_source_files(pkg_root, ext, header_ext)

    class_types = _CLASS_TYPES.get(language, set())
    func_types = _FUNC_TYPES.get(language, set())

    for fpath in files:
        rel = str(fpath.relative_to(repo)).replace("\\", "/")
        try:
            src = fpath.read_bytes()
        except OSError:
            continue

        tree = parser.parse(src)
        root = tree.root_node
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
                                     "enum_specifier")
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
                if not is_public(mnode, language):
                    continue
                mname = _node_name(mnode, language)
                if not mname:
                    continue

                # Skip Python @property and setter/deleter — handled by _extract_python_properties
                if language == "python" and mnode.type == "function_definition":
                    dec = find_child_by_type(mnode, "decorator")
                    if dec is None:
                        prev = mnode.prev_named_sibling
                        if prev and prev.type == "decorator":
                            dec = prev
                    if dec is not None:
                        dec_text = node_text(dec)
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
                        elif member.type == "field_declaration" and access == "public":
                            fdecl = find_child_by_type(member, "function_declarator")
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
                                    "line": member.start_point[0] + 1,
                                    "writable": True,  # public data members are read-write
                                })
                                claims.append(_make_claim(
                                    family, "api_method",
                                    f"{cname}.{fname} data member of type {ftype}",
                                    rel, member.start_point[0] + 1))

            vis = visibility_tier(
                cnode, language,
                has_docstring=bool(cdoc),
                in_module_all=(cname in module_all_names),
            )
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
            if is_enum:
                cls_record["enum_members"] = enum_members

            # FR-15: canonical_namespace (C++) and class_package (Java)
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

            classes.append({
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
            })
            claims.append(_make_claim(
                family, "api_method",
                f"Function {fname}({', '.join(p['name'] for p in params)}) -> {ret}",
                rel, fnode.start_point[0] + 1))

    return classes, claims, scanned_files, packages
