# Adapted from aspose.org scripts/pipeline/lib/ for standalone use
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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.pipeline.lib.knowledge_core import Knowledge


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
    "ISlideCollection",          # prs.getSlides().get(0) returns ISlide; chain can't be resolved
    "ICommentAuthorCollection",  # prs.getCommentAuthors().get(0) returns ICommentAuthor; chain can't be resolved
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
    # Python stdlib types
    "datetime",       # datetime.datetime
    "date",           # datetime.date
    "timedelta",      # datetime.timedelta
    "BytesIO",        # io.BytesIO
    "StringIO",       # io.StringIO
    "IOBase",         # io.IOBase
    "Enum",           # enum.Enum
    "ABC",            # abc.ABC
    "UUID",           # uuid.UUID
    "Decimal",        # decimal.Decimal
    "Counter",        # collections.Counter
    "OrderedDict",    # collections.OrderedDict
    "defaultdict",    # collections.defaultdict
    "Optional",       # typing.Optional
    "Union",          # typing.Union
    "Dict",           # typing.Dict
    "Tuple",          # typing.Tuple
    "Iterator",       # typing.Iterator
    "Generator",      # typing.Generator
    "Type",           # typing.Type
    "Callable",       # typing.Callable
    # Common third-party types
    "DataFrame",      # pandas.DataFrame
    "ndarray",        # numpy.ndarray
    "Series",         # pandas.Series
    "Image",          # PIL.Image (conflicts with some product types — guarded below)
    # Python built-in exceptions and common names
    "FileNotFoundError",   # builtins
    "ValueError",          # builtins
    "TypeError",           # builtins
    "RuntimeError",        # builtins
    "KeyError",            # builtins
    "IndexError",          # builtins
    "AttributeError",      # builtins
    "NotImplementedError", # builtins
    "PermissionError",     # builtins
    "IOError",             # builtins
    "OSError",             # builtins
    "StopIteration",       # builtins
    "None",                # Python keyword/singleton — never a product class
    # Aspose top-level namespace (not a class)
    "Aspose",              # Aspose.* namespace root
    # Common third-party integrations
    "MarkItDown",          # microsoft/markitdown third-party library
    # Common user-example class names in documentation
    "Program",             # C# Main class
    "App",                 # Application entrypoint
    "Main",                # Java main class
    # TypeScript / JavaScript built-ins and Node.js globals
    # These appear in TS/JS code examples but are not product API classes.
    "Error",               # JS/TS built-in Error class
    "JSON",                # JS/TS built-in JSON global object
    "Buffer",              # Node.js built-in Buffer class
    "Worker",              # Web Worker API (browser + Node.js worker_threads)
    "Promise",             # JS/TS built-in Promise
    "Map",                 # JS/TS built-in Map
    "Set",                 # JS/TS built-in Set
    "Uint8Array",          # JS/TS TypedArray
    "ArrayBuffer",         # JS/TS built-in ArrayBuffer
    "GLB",                 # glTF Binary format label — appears in code comments/strings, not a product class
    # .NET BCL types, methods, and enum values commonly appearing in code examples
    "DateTime",            # System.DateTime (.NET)
    "LocalDateTime",       # java.time.LocalDateTime (Java)
    "LocalDate",           # java.time.LocalDate (Java)
    "DateTimeKind",        # System.DateTimeKind enum (.NET)
    "Encoding",            # System.Text.Encoding (.NET)
    "UTF8",                # Encoding.UTF8 static property (.NET)
    "Unicode",             # Encoding.Unicode static property (.NET)
    "StringBuilder",       # System.Text.StringBuilder (.NET)
    "WriteLine",           # Console.WriteLine static method (.NET)
    "WriteAllBytes",       # File.WriteAllBytes static method (.NET)
    "ReadAllBytes",        # File.ReadAllBytes static method (.NET)
    "GetBytes",            # Encoding.GetBytes method (.NET)
    "GetString",           # Encoding.GetString method (.NET)
    "ToArray",             # IEnumerable.ToArray() extension method (.NET)
    # Java NIO / IO stdlib classes
    "Files",               # java.nio.file.Files (Java)
    "Paths",               # java.nio.file.Paths (Java)
    "Arrays",              # java.util.Arrays (Java)
    "FileInputStream",     # java.io.FileInputStream (Java)
    "FileOutputStream",    # java.io.FileOutputStream (Java)
    # .NET BCL static methods and types in code examples
    "Combine",             # Path.Combine (.NET)
    "AppContext",          # System.AppContext (.NET)
    "CultureInfo",         # System.Globalization.CultureInfo (.NET)
    "IsNullOrEmpty",       # String.IsNullOrEmpty (.NET)
    "IsNullOrWhiteSpace",  # String.IsNullOrWhiteSpace (.NET)
    "CopyTo",              # Stream.CopyTo (.NET)
    "Exists",              # File.Exists (.NET)
    "OpenRead",            # File.OpenRead (.NET)
    "Directory",           # System.IO.Directory (.NET)
    "GetFiles",            # Directory.GetFiles (.NET)
    "ChangeExtension",     # Path.ChangeExtension (.NET)
    "FileInfo",            # System.IO.FileInfo (.NET)
    "GetFileNameWithoutExtension",  # Path.GetFileNameWithoutExtension (.NET)
    "GetType",             # Object.GetType (.NET / Java)
    # ASP.NET framework patterns in examples
    "Ok",                  # ControllerBase.Ok() (ASP.NET MVC)
    "Upload",              # IFormFile upload pattern (ASP.NET)
    "OpenReadStream",      # IFormFile.OpenReadStream() (ASP.NET)
    # Python stdlib types
    "NamedTemporaryFile",  # tempfile.NamedTemporaryFile
    "Walk",                # os.walk
    # Common constant/formula/value names in code examples
    "SUM",                 # Excel formula function
    "Blue",                # Color.Blue enum value (.NET)
    "Copyright",           # License notice in comments (not a class)
    "EXTENSIONS",          # Constant/enum (not a product class)
    "Create",              # Factory method pattern (File.Create, etc.)
}


# EC-03 Pattern 2: Prefixes/suffixes common in user-defined example classes
# that appear in code snippets but are not part of the product API.
_USER_EXAMPLE_PREFIXES = ("My", "Custom", "Example", "Test", "Demo", "Sample")
_USER_EXAMPLE_SUFFIXES = (
    "Visitor", "Counter", "Printer", "Handler", "Listener", "Callback",
    "Builder", "Helper", "Impl", "Adapter", "Observer", "Delegate",
    "Manager", "Service", "Factory", "Provider", "Strategy",
    "Runner", "Processor", "Writer", "Reader", "Formatter",
)


def _is_user_example_class(name: str) -> bool:
    """Heuristic: return True if name looks like a user-defined example class.

    These commonly appear in documentation code snippets but are NOT product
    API classes.  Suppresses UNKNOWN_CLASS false positives (EC-03 Pattern 2).
    """
    if any(name.startswith(p) for p in _USER_EXAMPLE_PREFIXES):
        return True
    if any(name.endswith(s) for s in _USER_EXAMPLE_SUFFIXES):
        return True
    return False


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
                # Do NOT reset var_types here — variable types established in
                # earlier blocks remain visible to later blocks in the same file.
                # Resetting per-block was a bug that caused systematic
                # under-detection of API usage across multi-block pages.
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
        "net": {"csharp", "cs", "c#", ""},  # alias: content paths use "net" for .NET/C#
    }
    return code_lang in lang_map.get(platform, {"", platform})


# Python/Java/C# regex patterns (dot-separated access)
_PY_IMPORT_FROM = re.compile(r"from\s+([\w.]+)\s+import\s+(.+)")
_PY_IMPORT = re.compile(r"^import\s+([\w.]+)")
# C# using statement: "using Aspose.Slides;" or "using Aspose.ThreeD.Entities;"
_CS_USING = re.compile(r"^using\s+([\w.]+)\s*;")
# TypeScript/JavaScript ES module import: "import { Class1, Class2 } from '@aspose/3d'"
_TS_IMPORT_FROM = re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]")
# Matches: var = func( or var = ClassName( — general assignment tracking
_PY_ASSIGNMENT = re.compile(r"(\w+)\s*=\s*(\w+)\(")
# Matches: var: Type = mod.ClassName( — qualified/annotated assignment (fallback)
_PY_QUALIFIED_ASSIGNMENT = re.compile(r"(\w+)\s*(?::\s*\w+\s*)?=\s*(?:\w+\.){0,5}([A-Z]\w*)\s*\(")
# Matches: var = obj.method() — for return-type tracking
_PY_METHOD_ASSIGNMENT = re.compile(r"(\w+)\s*=\s*(\w+)\.(\w+)\s*\(")
_PY_METHOD_CHAIN_STEP = re.compile(r"\)\s*\.(\w+)\s*\(")
_PY_PROP_ASSIGNMENT = re.compile(r"(\w+)\s*=\s*(\w+)\.(\w+)(?:\s*$|\s*#)")
_PY_ENUM_ACCESS = re.compile(r"([A-Z]\w+)\.([A-Z][A-Z_0-9]+)")
_PY_METHOD_CALL = re.compile(r"(\w+)\.(\w+)\s*\(")
_PY_PROP_ACCESS = re.compile(r"(\w+)\.(\w+)")
_PY_CONSTRUCTOR = re.compile(r"(?<!\w)([A-Z][A-Za-z0-9]+)\s*\(")

# C# / Java new-keyword assignment: "var x = new ClassName(" or "Type x = new ClassName("
# The generic _PY_ASSIGNMENT misses this because "new" is not followed by "(" directly.
_CS_NEW_ASSIGNMENT = re.compile(r"(?:var\s+)?(\w+)\s*=\s*new\s+([A-Z]\w*)\s*\(")

# C++ scope-resolution enum access: ClassName::MEMBER_NAME
# C++ enums use ALL_CAPS names (e.g. NullableBool::TRUE, FillType::SOLID)
_CPP_ENUM_ACCESS = re.compile(r"([A-Z]\w+)::([A-Z][A-Z_0-9]+)")

# Java explicit type declaration: ClassName varName = expr
# Used to override the weaker _PY_METHOD_ASSIGNMENT inference for Java code.
_JAVA_TYPE_DECL = re.compile(r"(?<![\w.])([A-Z]\w*)\s+([a-z]\w*)\s*=")
_JAVA_SKIP_TYPES = frozenset({
    "String", "Integer", "Long", "Float", "Double", "Boolean",
    "Character", "Byte", "Short", "Object", "Number",
    "LocalDateTime", "LocalDate",
})

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
    # TypeScript/JavaScript ES module: "import { Class1, Class2 } from '@aspose/3d'"
    if platform in ("typescript",):
        m = _TS_IMPORT_FROM.match(stripped)
        if m:
            pkg = m.group(2)
            tokens.append(Token("import", pkg, "", line_no, stripped))
            # Track imported class names for type resolution
            for name in m.group(1).split(","):
                name = name.strip()
                if name and name[0].isupper():
                    var_types[name] = name
            return tokens

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

    # --- C# using statement ---
    m = _CS_USING.match(stripped)
    if m:
        pkg = m.group(1)
        tokens.append(Token("import", pkg, "", line_no, stripped))
        return tokens

    # Strip string literals to avoid false matches inside strings
    stripped = _strip_strings(stripped)

    # --- Variable assignments (type tracking) ---
    # C# / Java / TypeScript: "var x = new ClassName(" or "const x = new ClassName(" —
    # must run BEFORE the generic patterns because _PY_ASSIGNMENT matches "x = new(" (wrong cls).
    if platform in ("net", "dotnet", "java", "typescript"):
        mc = _CS_NEW_ASSIGNMENT.search(stripped)
        if mc:
            var_name, cls_name = mc.group(1), mc.group(2)
            if cls_name not in ("True", "False", "None"):
                var_types[var_name] = cls_name

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
            chain_parts = [obj_type, member]
            rest = stripped[m.end():]
            for step in _PY_METHOD_CHAIN_STEP.finditer(rest):
                chain_parts.append(step.group(1))
            var_types[var_name] = ".".join(chain_parts)  # Placeholder for later resolution
    # Track var = obj.prop for property type inference (no parens) — only if not already matched as method call
    elif (m := _PY_PROP_ASSIGNMENT.search(stripped)):
        var_name, obj_name, member = m.group(1), m.group(2), m.group(3)
        obj_type = var_types.get(obj_name)
        if obj_type:
            var_types[var_name] = f"{obj_type}.{member}"  # Placeholder for later resolution

    # --- Java: explicit type declaration: ClassName varName = expr ---
    # Override the weaker method-assignment inference that maps e.g. "sheet" → WorksheetCollection.
    if platform == "java":
        mj = _JAVA_TYPE_DECL.search(stripped)
        if mj:
            jt, jv = mj.group(1), mj.group(2)
            if jt not in _JAVA_SKIP_TYPES:
                var_types[jv] = jt

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

def verify_tokens(tokens: list[Token], knowledge: Knowledge, filepath: Path) -> list[Finding]:
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
            elif knowledge.platform in ("net", "dotnet") and pkg.startswith("Aspose."):
                # C# namespace verification: check against valid_imports if available.
                # valid_imports for .NET is populated from api_surface file paths.
                # Gracefully skip validation if no import data has been indexed yet.
                if knowledge.valid_imports:
                    pkg_lower = pkg.lower()
                    is_valid = any(
                        pkg_lower in vp.lower() or vp.lower() in pkg_lower
                        for vp in knowledge.valid_imports
                    )
                    if not is_valid and tier <= 2:
                        findings.append(Finding(
                            "WARN", filepath, tok.line_no,
                            f"Unrecognized C# namespace: `{pkg}`",
                            "Check merged/api_surface.json for valid namespaces",
                        ))
            continue

        # --- Enum verification ---
        if tok.kind == "enum":
            if tok.class_name not in knowledge.classes:
                # Emit WARN for unknown CamelCase classes not in SDK/stdlib allowlists
                if (tok.class_name[0].isupper()
                        and tok.class_name not in PLATFORM_SDK_CLASSES
                        and tok.class_name not in PROPERTY_CHAIN_CLASSES
                        and not _is_user_example_class(tok.class_name)):
                    is_known_member = any(
                        tok.class_name in members
                        for members in (
                            list(knowledge.methods.values())
                            + list(knowledge.properties.values())
                        )
                    )
                    if not is_known_member:
                        findings.append(Finding(
                            "WARN", filepath, tok.line_no,
                            f"UNKNOWN_CLASS: `{tok.class_name}` — not found in api_surface.json",
                            f"Verify in FOSS source. If stdlib/third-party, add to PLATFORM_SDK_CLASSES in token_ops.py."
                        ))
                continue
            if tok.class_name not in knowledge.enum_members:
                # EC-03 Pattern 1 fix: TypeScript/Python enums may store members
                # as properties (read-only) rather than enum_members.  Check
                # properties before declaring unverifiable.
                if knowledge.has_property(tok.class_name, tok.member_name):
                    continue  # Member found as property — verified
                # Class exists but no enum_members extracted and not in properties
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
                # Emit WARN for unknown CamelCase classes not in SDK/stdlib allowlists
                if (tok.class_name[0].isupper()
                        and tok.class_name not in PLATFORM_SDK_CLASSES
                        and tok.class_name not in PROPERTY_CHAIN_CLASSES
                        and not _is_user_example_class(tok.class_name)):
                    # Suppress false positives: method calls like obj.Save(...) are
                    # tokenized as constructor(class='Save') even though Save is a method.
                    # Similarly, property names used as constructor parameter names
                    # (e.g. __init__(TitleText: RichText | None)) get misidentified.
                    # If the identifier is a known method OR property name on ANY class,
                    # skip the WARN — it is a false positive from the tokenizer.
                    is_known_member = any(
                        tok.class_name in members
                        for members in (
                            list(knowledge.methods.values())
                            + list(knowledge.properties.values())
                        )
                    )
                    if not is_known_member:
                        findings.append(Finding(
                            "WARN", filepath, tok.line_no,
                            f"UNKNOWN_CLASS: `{tok.class_name}` — not found in api_surface.json",
                            f"Verify in FOSS source. If stdlib/third-party, add to PLATFORM_SDK_CLASSES in token_ops.py."
                        ))
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
                    # Emit WARN for unknown CamelCase classes not in SDK/stdlib allowlists
                    if (cls_name[0].isupper()
                            and cls_name not in PLATFORM_SDK_CLASSES
                            and cls_name not in PROPERTY_CHAIN_CLASSES
                            and not _is_user_example_class(cls_name)):
                        is_known_member = any(
                            cls_name in members
                            for members in (
                                list(knowledge.methods.values())
                                + list(knowledge.properties.values())
                            )
                        )
                        if not is_known_member:
                            findings.append(Finding(
                                "WARN", filepath, tok.line_no,
                                f"UNKNOWN_CLASS: `{cls_name}` — not found in api_surface.json",
                                f"Verify in FOSS source. If stdlib/third-party, add to PLATFORM_SDK_CLASSES in token_ops.py."
                            ))
                    continue
            if not knowledge.methods.get(cls_name) and not knowledge.properties.get(cls_name):
                # Empty class — can't verify
                continue
            if not knowledge.has_method(cls_name, tok.member_name):
                # Context-aware: detect property-as-method anti-pattern
                if knowledge.is_property_only(cls_name, tok.member_name):
                    findings.append(Finding(
                        "FAIL", filepath, tok.line_no,
                        f"`{cls_name}.{tok.member_name}()` — `{tok.member_name}` is a property, not a method (remove parentheses)",
                        f"Use `obj.{tok.member_name}` without `()`"
                    ))
                    continue
                if cls_name in PLATFORM_SDK_CLASSES or cls_name in PROPERTY_CHAIN_CLASSES:
                    continue  # Skip platform SDK types and property chain ambiguities
                if (cls_name, tok.member_name) in knowledge.workaround_members:
                    continue  # Whitelisted private-API workaround
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
                    # Emit WARN for unknown CamelCase classes not in SDK/stdlib allowlists
                    if (cls_name[0].isupper()
                            and cls_name not in PLATFORM_SDK_CLASSES
                            and cls_name not in PROPERTY_CHAIN_CLASSES
                            and not _is_user_example_class(cls_name)):
                        is_known_member = any(
                            cls_name in members
                            for members in (
                                list(knowledge.methods.values())
                                + list(knowledge.properties.values())
                            )
                        )
                        if not is_known_member:
                            findings.append(Finding(
                                "WARN", filepath, tok.line_no,
                                f"UNKNOWN_CLASS: `{cls_name}` — not found in api_surface.json",
                                f"Verify in FOSS source. If stdlib/third-party, add to PLATFORM_SDK_CLASSES in token_ops.py."
                            ))
                    continue
            if not knowledge.methods.get(cls_name) and not knowledge.properties.get(cls_name):
                continue
            if not knowledge.has_property(cls_name, tok.member_name):
                if cls_name in PLATFORM_SDK_CLASSES or cls_name in PROPERTY_CHAIN_CLASSES:
                    continue  # Skip platform SDK types and property chain ambiguities
                if (cls_name, tok.member_name) in knowledge.workaround_members:
                    continue  # Whitelisted private-API workaround
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

# ---------------------------------------------------------------------------
# Signature verifier (TC-P3-02)
# ---------------------------------------------------------------------------

# Matches method call with argument list: obj.method(arg1, arg2, ...)
_SG_METHOD_CALL_RE = re.compile(r"\b(\w+)\.(\w+)\s*\(([^)]*)\)")

# Typed assignment: "Type varName = obj.method(...)" or "var varName = obj.method(...)"
_SG_TYPED_ASSIGN_RE = re.compile(
    r"\b([A-Z]\w+)\s+\w+\s*=\s*\w+\.(\w+)\s*\("
)


def _count_args(arg_str: str) -> int:
    """Count top-level comma-separated arguments, ignoring empty parens.

    Returns -1 if the arg_str contains nested function calls (unbalanced open
    parens), indicating the count is unreliable — caller should skip the check.
    """
    stripped = arg_str.strip()
    if not stripped:
        return 0
    # Unbalanced open paren indicates nested call — count is unreliable
    if stripped.count("(") > stripped.count(")"):
        return -1
    # Count only top-level commas (depth 0)
    depth = 0
    count = 1
    for ch in stripped:
        if ch in ("(", "[", "{"):
            depth += 1
        elif ch in (")", "]", "}"):
            depth -= 1
        elif ch == "," and depth == 0:
            count += 1
    return count


def _return_types_compatible(declared: str, known: str) -> bool:
    """Heuristic: check if declared type is compatible with known return type."""
    def _base(t: str) -> str:
        return re.sub(r"<.*>", "", t).strip().lower()

    d, k = _base(declared), _base(known)
    if d == k:
        return True
    aliases = {
        ("ienumerable", "list"), ("list", "ienumerable"),
        ("icollection", "list"), ("list", "icollection"),
        ("ilist", "list"), ("list", "ilist"),
        ("object", "string"), ("string", "object"),
        ("void", ""), ("", "void"),
    }
    return (d, k) in aliases


def verify_signature(
    filepath: "Path",
    platform: str,
    knowledge: "Knowledge",
) -> "list[Finding]":
    """Verify method call-site argument counts against the knowledge model.

    Emits SG (Signature) WARN findings when the number of arguments at a call
    site does not match any known overload in api_surface.json.

    Exemptions:
    - Python: dynamic dispatch makes static param-count checking unreliable
    - Code blocks containing only '...' (intentionally truncated)
    - Code blocks shorter than 10 chars
    - Methods with multiple param counts in api_surface (overloaded)
    - Platform SDK classes (PLATFORM_SDK_CLASSES)
    """
    if platform in ("python", "py"):
        return []

    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[Finding] = []

    var_types: dict[str, str] = {}
    in_code = False
    code_lang = ""
    block_lines: list[tuple[int, str]] = []

    class_name_lower = {c.lower(): c for c in knowledge.classes}

    def _flush_block() -> None:
        if not block_lines:
            return
        block_text = "\n".join(ln for _, ln in block_lines)
        if block_text.strip() == "...":
            return
        if len(block_text.strip()) < 10:
            return

        for line_no, line in block_lines:
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            mc = _CS_NEW_ASSIGNMENT.search(stripped)
            if mc:
                vn, cn = mc.group(1), mc.group(2)
                if cn not in ("True", "False", "None"):
                    var_types[vn] = cn

            # Return-type check for typed assignment
            if platform in ("net", "dotnet", "java"):
                rt_match = _SG_TYPED_ASSIGN_RE.search(stripped)
                if rt_match:
                    declared_type = rt_match.group(1)
                    method_name = rt_match.group(2)
                    obj_match = re.search(r"\b(\w+)\." + re.escape(method_name) + r"\s*\(", stripped)
                    if obj_match:
                        obj_name = obj_match.group(1)
                        cls_name = var_types.get(obj_name, obj_name if obj_name[0].isupper() else "")
                        if cls_name and cls_name not in PLATFORM_SDK_CLASSES:
                            canonical = class_name_lower.get(cls_name.lower(), cls_name)
                            known_ret = knowledge.get_return_type(canonical, method_name)
                            if (known_ret and declared_type
                                    and declared_type not in PLATFORM_SDK_CLASSES
                                    and not _return_types_compatible(declared_type, known_ret)):
                                findings.append(Finding(
                                    "WARN", filepath, line_no,
                                    f"SG: `{canonical}.{method_name}()` returns `{known_ret}`, "
                                    f"assigned to `{declared_type}`",
                                    "Check return type in api_surface.json",
                                ))

            # Argument-count check
            for m in _SG_METHOD_CALL_RE.finditer(stripped):
                obj_name, method_name, arg_str = m.group(1), m.group(2), m.group(3)
                if obj_name in ("self", "cls", "super", "print", "len", "str", "int", "list"):
                    continue
                cls_name = var_types.get(obj_name, obj_name if obj_name[0].isupper() else "")
                if not cls_name:
                    continue
                canonical = class_name_lower.get(cls_name.lower(), cls_name)
                if canonical not in knowledge.classes:
                    continue
                if canonical in PLATFORM_SDK_CLASSES or canonical in PROPERTY_CHAIN_CLASSES:
                    continue
                if not knowledge.has_method(canonical, method_name):
                    continue

                key = (canonical, method_name)
                known_counts = knowledge.method_params.get(key)
                if not known_counts:
                    continue
                if len(known_counts) > 1:
                    continue  # Overloaded — skip

                expected = next(iter(known_counts))
                actual = _count_args(arg_str)
                if actual < 0:
                    continue  # Nested call — arg count unreliable, skip
                # EC-03 Pattern 6 fix: accept fewer args than expected
                # (optional/default params) and up to expected+1 (variadic/
                # implicit self).  Only flag when actual clearly exceeds
                # what all overloads could accept.
                if actual > expected + 1:
                    findings.append(Finding(
                        "WARN", filepath, line_no,
                        f"SG: `{canonical}.{method_name}()` expects {expected} arg(s), "
                        f"got {actual} at call site",
                        "Check api_surface.json params for this method",
                    ))

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                _flush_block()
                block_lines = []
                in_code = False
            else:
                in_code = True
                code_lang = stripped[3:].strip().lower()
        elif in_code and _is_target_lang(code_lang, platform):
            block_lines.append((line_no, line))

    return findings
