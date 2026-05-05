"""Token extraction and verification against the knowledge API surface.

Extracted from audit.py. Provides Token, Finding, extract_tokens, verify_tokens.

Public API:
    Token           — extracted API token from a content file
    Finding         — verification result (FAIL/WARN/INFO)
    extract_tokens(filepath, platform) -> list[Token]
    verify_tokens(tokens, knowledge, filepath) -> list[Finding]

Constants:
    PLATFORM_SDK_CLASSES    — standard library / framework types to skip
    PROPERTY_CHAIN_CLASSES  — classes whose property chains can't be resolved
"""
from __future__ import annotations

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Token / Finding types
# ---------------------------------------------------------------------------

class Token:
    """An extracted API token from a content file."""
    __slots__ = ("kind", "class_name", "member_name", "line_no", "raw_text")

    def __init__(self, kind, class_name, member_name, line_no, raw_text):
        self.kind = kind            # "import", "enum", "method", "property", "constructor", "class"
        self.class_name = class_name
        self.member_name = member_name
        self.line_no = line_no
        self.raw_text = raw_text

    def __repr__(self):
        return f"Token({self.kind}, {self.class_name}.{self.member_name}, L{self.line_no})"


class Finding:
    __slots__ = ("level", "filepath", "line_no", "message", "suggestion")

    def __init__(self, level, filepath, line_no, message, suggestion=""):
        self.level = level  # "FAIL" or "WARN"
        self.filepath = filepath
        self.line_no = line_no
        self.message = message
        self.suggestion = suggestion


# ---------------------------------------------------------------------------
# Class constants — platform SDK and property-chain classes to skip
# ---------------------------------------------------------------------------

# Classes that are commonly accessed via property chains (e.g. prs.Images.AddImage())
# where the tokenizer can't resolve the property's return type.
PROPERTY_CHAIN_CLASSES = {
    "Images",         # prs.Images returns IImageCollection, not the Images factory class
}

PLATFORM_SDK_CLASSES = {
    "Color",          # System.Drawing.Color (.NET), java.awt.Color (Java), etc.
    "Console",        # System.Console (.NET)
    "File",           # System.IO.File (.NET), java.io.File (Java)
    "Path",           # System.IO.Path (.NET), java.nio.file.Path (Java)
    "Math",           # System.Math (.NET), java.lang.Math (Java)
    "String",         # System.String (.NET), java.lang.String (Java)
    "List",           # System.Collections.Generic.List (.NET)
    "Array",          # System.Array (.NET)
    "Stream",         # System.IO.Stream (.NET)
    "MemoryStream",   # System.IO.MemoryStream (.NET)
    "FileStream",     # System.IO.FileStream (.NET)
    "Exception",      # System.Exception (.NET), java.lang.Exception (Java)
    "System",         # System namespace (.NET)
    "Integer",        # java.lang.Integer (Java)
    "Objects",        # java.util.Objects (Java)
    "Collections",    # java.util.Collections (Java)
    "PointF",         # System.Drawing.PointF (.NET)
    "SizeF",          # System.Drawing.SizeF (.NET)
}


# ---------------------------------------------------------------------------
# Token extractor
# ---------------------------------------------------------------------------

def extract_tokens(filepath: Path, platform: str) -> list[Token]:
    """Extract API tokens from a markdown file."""
    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines()
    tokens = []

    # Track variable types within code blocks
    var_types = {}

    in_code = False
    code_lang = ""

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()

        # Detect code block boundaries
        if stripped.startswith("```"):
            if in_code:
                in_code = False
                var_types = {}
                continue
            else:
                in_code = True
                code_lang = stripped[3:].strip().lower()
                continue

        if in_code and _is_target_lang(code_lang, platform):
            tokens.extend(_extract_from_code_line(line, line_no, var_types, platform))
        elif not in_code:
            # Extract from markdown tables
            tokens.extend(_extract_from_table_line(line, line_no))

    return tokens


def _is_target_lang(code_lang: str, platform: str) -> bool:
    """Check if code block language matches the platform."""
    lang_map = {
        "python": {"python", "py", ""},
        "typescript": {"typescript", "ts", "javascript", "js", ""},
        "java": {"java", ""},
        "dotnet": {"csharp", "cs", "c#", ""},
    }
    return code_lang in lang_map.get(platform, {"", platform})


# Python/Java/C# regex patterns (dot-separated access)
_PY_IMPORT_FROM = re.compile(r"from\s+([\w.]+)\s+import\s+(.+)")
_PY_IMPORT = re.compile(r"^import\s+([\w.]+)")
# Matches: var = func( or var = ClassName( — general assignment tracking
_PY_ASSIGNMENT = re.compile(r"(\w+)\s*=\s*(\w+)\(")
# Matches: var: Type = mod.ClassName( — qualified/annotated assignment (fallback)
_PY_QUALIFIED_ASSIGNMENT = re.compile(r"(\w+)\s*(?::\s*\w+\s*)?=\s*(?:\w+\.){0,5}([A-Z]\w*)\s*\(")
# Matches: var = obj.method() — for return-type tracking
_PY_METHOD_ASSIGNMENT = re.compile(r"(\w+)\s*=\s*(\w+)\.(\w+)\s*\(")
_PY_PROP_ASSIGNMENT = re.compile(r"(\w+)\s*=\s*(\w+)\.(\w+)(?:\s*$|\s*#)")
_PY_ENUM_ACCESS = re.compile(r"([A-Z]\w+)\.([A-Z][A-Z_0-9]+)")
_PY_METHOD_CALL = re.compile(r"(\w+)\.(\w+)\s*\(")
_PY_PROP_ACCESS = re.compile(r"(\w+)\.(\w+)")
_PY_CONSTRUCTOR = re.compile(r"(?<!\w)([A-Z][A-Za-z0-9]+)\s*\(")

# C++ scope-resolution enum access: ClassName::MEMBER_NAME
# C++ enums use ALL_CAPS names (e.g. NullableBool::TRUE, FillType::SOLID)
_CPP_ENUM_ACCESS = re.compile(r"([A-Z]\w+)::([A-Z][A-Z_0-9]+)")

_STRING_LITERAL = re.compile(r"""(["'])(?:(?!\1).)*\1""")


def _strip_strings(s: str) -> str:
    """Remove string literal contents to avoid false matches inside strings."""
    return _STRING_LITERAL.sub('""', s)


def _extract_from_code_line(line: str, line_no: int, var_types: dict, platform: str) -> list[Token]:
    """Extract tokens from a single code line."""
    tokens = []
    stripped = line.strip()

    # Skip comments
    if stripped.startswith("#") or stripped.startswith("//"):
        return tokens

    # --- Imports ---
    m = _PY_IMPORT_FROM.match(stripped)
    if m:
        pkg = m.group(1)
        tokens.append(Token("import", pkg, "", line_no, stripped))
        # Track imported names for type resolution
        for name in m.group(2).split(","):
            name = name.strip()
            if name and name[0].isupper():
                var_types[name] = name
        return tokens

    m = _PY_IMPORT.match(stripped)
    if m:
        pkg = m.group(1)
        tokens.append(Token("import", pkg, "", line_no, stripped))
        return tokens

    # Strip string literals to avoid false matches inside strings
    stripped = _strip_strings(stripped)

    # --- Variable assignments (type tracking) ---
    # Try qualified regex first (handles annotations, module prefixes)
    mq = _PY_QUALIFIED_ASSIGNMENT.search(stripped)
    if mq:
        var_name, cls_name = mq.group(1), mq.group(2)
        if cls_name not in ("True", "False", "None"):
            var_types[var_name] = cls_name
    else:
        # Fallback: simple assignment (catches var = ClassName( without qualifiers)
        m = _PY_ASSIGNMENT.search(stripped)
        if m:
            var_name, cls_name = m.group(1), m.group(2)
            if cls_name[0].isupper() and cls_name not in ("True", "False", "None"):
                var_types[var_name] = cls_name

    # Track var = obj.method() for return type inference (method call assignment)
    m = _PY_METHOD_ASSIGNMENT.search(stripped)
    if m:
        var_name, obj_name, member = m.group(1), m.group(2), m.group(3)
        obj_type = var_types.get(obj_name)
        if obj_type:
            var_types[var_name] = f"{obj_type}.{member}"  # Placeholder for later resolution
    # Track var = obj.prop for property type inference (no parens) — only if not already matched as method call
    elif (m := _PY_PROP_ASSIGNMENT.search(stripped)):
        var_name, obj_name, member = m.group(1), m.group(2), m.group(3)
        obj_type = var_types.get(obj_name)
        if obj_type:
            var_types[var_name] = f"{obj_type}.{member}"  # Placeholder for later resolution

    # --- Enum access: EnumName.UPPER_MEMBER ---
    for m in _PY_ENUM_ACCESS.finditer(stripped):
        enum_name, member = m.group(1), m.group(2)
        # Skip common non-enum patterns
        if enum_name in ("True", "False", "None", "self"):
            continue
        tokens.append(Token("enum", enum_name, member, line_no, m.group(0)))

    # --- Method calls: obj.method( ---
    for m in _PY_METHOD_CALL.finditer(stripped):
        obj, method = m.group(1), m.group(2)
        if obj in ("self", "cls", "super", "print", "len", "str", "int",
                    "float", "list", "dict", "set", "type", "range",
                    "enumerate", "zip", "map", "filter", "sorted", "open",
                    "isinstance", "hasattr", "getattr"):
            continue
        # Skip enum access (already handled)
        if obj[0].isupper() and method.isupper():
            continue
        cls_name = var_types.get(obj, obj if obj[0].isupper() else "")
        if cls_name:
            tokens.append(Token("method", cls_name, method, line_no, m.group(0)))

    # --- Property access: obj.prop (not followed by parens) ---
    for m in _PY_PROP_ACCESS.finditer(stripped):
        obj, prop = m.group(1), m.group(2)
        if obj in ("self", "cls", "super", "os", "sys", "re", "json",
                    "yaml", "f", "print", "math"):
            continue
        # Skip if this is actually a method call (has parens after)
        end = m.end()
        rest = stripped[end:].lstrip()
        if rest.startswith("("):
            continue
        # Skip enum access
        if obj[0].isupper() and prop[0].isupper() and prop == prop.upper():
            continue
        cls_name = var_types.get(obj, obj if obj[0].isupper() else "")
        if cls_name:
            tokens.append(Token("property", cls_name, prop, line_no, m.group(0)))

    # --- Constructor: ClassName( ---
    for m in _PY_CONSTRUCTOR.finditer(stripped):
        cls_name = m.group(1)
        if cls_name in ("True", "False", "None", "Exception", "ValueError",
                         "TypeError", "KeyError", "RuntimeError", "Path",
                         "Color", "print"):
            continue
        tokens.append(Token("constructor", cls_name, "__init__", line_no, m.group(0)))

    # --- C++ scope-resolution enum: ClassName::MEMBER ---
    if platform == "cpp":
        for m in _CPP_ENUM_ACCESS.finditer(stripped):
            enum_name, member = m.group(1), m.group(2)
            tokens.append(Token("enum", enum_name, member, line_no, m.group(0)))

    return tokens


def _extract_from_table_line(line: str, line_no: int) -> list[Token]:
    """Extract property/method names from markdown tables."""
    tokens = []
    if "|" not in line or "---" in line:
        return tokens

    cells = [c.strip() for c in line.split("|")]
    if len(cells) < 3:
        return tokens

    first = cells[1] if len(cells) > 1 else ""
    # Property in backticks: `property_name`
    m = re.match(r"`(\w+)`", first)
    if m:
        name = m.group(1)
        # Skip header-like values
        if name.lower() not in ("property", "method", "name", "parameter",
                                 "type", "access", "description", "value"):
            tokens.append(Token("table_member", "", name, line_no, first))

    # Enum in backticks with class: `EnumName.VALUE`
    m = re.match(r"`([A-Z]\w+)\.([A-Z][A-Z_0-9]+)`", first)
    if m:
        tokens.append(Token("enum", m.group(1), m.group(2), line_no, first))

    return tokens


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

def verify_tokens(tokens: list[Token], knowledge, filepath: Path) -> list[Finding]:
    """Verify extracted tokens against knowledge model."""
    findings = []
    tier = knowledge.surface_tier
    # Case-insensitive class name lookup for var_types that may be lowercase
    class_name_lower = {c.lower(): c for c in knowledge.classes}

    for tok in tokens:
        # --- Import verification ---
        if tok.kind == "import":
            pkg = tok.class_name
            if knowledge.platform == "python" and pkg.startswith("aspose."):
                # Check if import matches any valid module path from api_surface
                is_valid = any(
                    pkg == vp or pkg.startswith(vp + ".")
                    for vp in knowledge.valid_imports
                )
                if not is_valid:
                    # Find the closest valid import prefix
                    top_level = sorted(
                        vp for vp in knowledge.valid_imports
                        if vp.startswith("aspose.") and vp.count(".") == 1
                    )
                    suggestion = f"Valid import(s): {', '.join(top_level)}" if top_level else ""
                    findings.append(Finding(
                        "FAIL", filepath, tok.line_no,
                        f"Wrong import package: `{pkg}`",
                        suggestion
                    ))
            continue

        # --- Enum verification ---
        if tok.kind == "enum":
            if tok.class_name not in knowledge.classes:
                # Enum class not found — might be from another module
                continue
            if tok.class_name not in knowledge.enum_members:
                # Class exists but no enum_members extracted
                if tier <= 2 and tok.class_name not in PLATFORM_SDK_CLASSES:
                    findings.append(Finding(
                        "WARN", filepath, tok.line_no,
                        f"`{tok.class_name}.{tok.member_name}` — enum has no members in api_surface (unverifiable)",
                    ))
                continue
            if not knowledge.has_enum_member(tok.class_name, tok.member_name):
                actual = sorted(knowledge.enum_members[tok.class_name])
                suggest = knowledge.closest_match(actual, tok.member_name)
                level = "FAIL"
                findings.append(Finding(
                    level, filepath, tok.line_no,
                    f"`{tok.class_name}.{tok.member_name}` — enum member not found",
                    f"Did you mean: {', '.join(suggest)}?" if suggest else f"Available: {actual[:10]}"
                ))
            continue

        # --- Constructor verification ---
        if tok.kind == "constructor":
            if tok.class_name not in knowledge.classes:
                # Could be a class we don't track (stdlib, etc.)
                continue
            # Constructor exists if the class exists — we just verify class name
            continue

        # --- Method verification ---
        if tok.kind == "method":
            cls_name = tok.class_name
            # Resolve chained type placeholder (e.g. "Scene.root_node")
            if "." in cls_name:
                resolved = knowledge.resolve_chain(cls_name)
                if resolved is None:
                    continue
                cls_name = resolved
            # Case-insensitive class name normalization
            if cls_name not in knowledge.classes:
                canonical = class_name_lower.get(cls_name.lower())
                if canonical:
                    cls_name = canonical
                else:
                    continue
            if not knowledge.methods.get(cls_name) and not knowledge.properties.get(cls_name):
                # Empty class — can't verify
                continue
            if not knowledge.has_method(cls_name, tok.member_name):
                # Context-aware: detect property-as-method anti-pattern
                if knowledge.is_property_only(cls_name, tok.member_name):
                    findings.append(Finding(
                        "WARN", filepath, tok.line_no,
                        f"`{cls_name}.{tok.member_name}()` — `{tok.member_name}` is a property, not a method (remove parentheses)",
                        f"Use `obj.{tok.member_name}` without `()`"
                    ))
                    continue
                if cls_name in PLATFORM_SDK_CLASSES or cls_name in PROPERTY_CHAIN_CLASSES:
                    continue  # Skip platform SDK types and property chain ambiguities
                actual_methods = sorted(knowledge.methods.get(cls_name, set()))
                suggest = knowledge.closest_match(actual_methods, tok.member_name)
                level = "FAIL"
                findings.append(Finding(
                    level, filepath, tok.line_no,
                    f"`{cls_name}.{tok.member_name}()` — method not found on {cls_name}",
                    f"Did you mean: {', '.join(suggest)}?" if suggest else ""
                ))
            continue

        # --- Property verification ---
        if tok.kind == "property":
            cls_name = tok.class_name
            if "." in cls_name:
                resolved = knowledge.resolve_chain(cls_name)
                if resolved is None:
                    continue
                cls_name = resolved
            # Case-insensitive class name normalization
            if cls_name not in knowledge.classes:
                canonical = class_name_lower.get(cls_name.lower())
                if canonical:
                    cls_name = canonical
                else:
                    continue
            if not knowledge.methods.get(cls_name) and not knowledge.properties.get(cls_name):
                continue
            if not knowledge.has_property(cls_name, tok.member_name):
                if cls_name in PLATFORM_SDK_CLASSES or cls_name in PROPERTY_CHAIN_CLASSES:
                    continue  # Skip platform SDK types and property chain ambiguities
                actual_props = sorted(knowledge.properties.get(cls_name, set()))
                suggest = knowledge.closest_match(actual_props, tok.member_name)
                level = "FAIL"
                findings.append(Finding(
                    level, filepath, tok.line_no,
                    f"`{cls_name}.{tok.member_name}` — property not found on {cls_name}",
                    f"Did you mean: {', '.join(suggest)}?" if suggest else ""
                ))
            continue

    return findings
