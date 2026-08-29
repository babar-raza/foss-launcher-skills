"""Code block API validation evaluator (FIX-07).

Extracts API tokens (ClassName.method_name, ClassName.property_name) from
fenced code blocks and verifies each against api_surface.json.  This closes
the biggest evaluator blind spot identified in the forensic audit: pages
graded A that contain broken code examples calling non-existent APIs.

RC-W1-004 (MT026 blind-spot audit): the original version of this evaluator
only checked whether a class NAME existed somewhere in api_surface.json --
never whether it was actually reachable/public for its language. Two gaps
this version closes:

  1. Bare type references (``catch (XmlParsingException ex)``, ``new
     SomeType(...)``, Python ``from pkg import Name``) carry no ``.member``
     access, so the original ``_MEMBER_ACCESS_RE`` never saw them at all.
  2. Even for ``.member`` accesses, a class whose api_surface.json entry now
     carries ``reachable: false`` (see extraction/api_surface.py) — or that
     is entirely absent from api_surface.json because is_public() excluded
     it at scout time (C#/Java `internal` types) — was silently treated as
     "might be external, don't flag." See ``_reachability.py`` for the full
     three-language rationale and the primary/live-fallback signal design.

Category: CB (Code Block API)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator
from . import _reachability

# Import Knowledge for type checking
_HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_HERE))
_LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from knowledge_core import Knowledge  # noqa: E402


# ---------------------------------------------------------------------------
# Token extraction patterns
# ---------------------------------------------------------------------------

# Match ClassName.member_name patterns in code.
# ClassName: starts with uppercase letter, at least 2 chars.
# member_name: starts with letter or underscore, word chars.
# ST-104: excludes matches where ClassName is itself immediately preceded by
# a `.` -- that shape is the TAIL of a longer chain (`doc.Pages.map`, where
# `Pages` is an instance property, not a standalone type reference), not a
# top-level class reference.
_MEMBER_ACCESS_RE = re.compile(
    r"(?<!\.)\b([A-Z][A-Za-z0-9_]{1,})\s*\.\s*([a-zA-Z_]\w*)"
)

# ST-104: string/template literals and comments are never real code
# identifiers -- `'Hello from Aspose.PDF FOSS!'` and `// ...not
# SearchAnnotations.` both false-positive-matched _MEMBER_ACCESS_RE before
# this sanitization pass existed. Blanked spans keep their newlines so line
# numbers computed from character offsets stay accurate.
_STRING_LITERAL_RE = re.compile(
    r"""('(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`)""",
    re.DOTALL,
)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_PY_COMMENT_RE = re.compile(r"#[^\n]*")


def _blank_span(match: "re.Match[str]") -> str:
    return "".join(ch if ch == "\n" else " " for ch in match.group(0))


def _sanitize_for_token_scan(content: str, lang: str) -> str:
    """Blank string/template literals and comments before token scanning so
    prose or literal text shaped like `Capitalized.member` is never mistaken
    for a real code reference. Strings are blanked first so a `//` or `#`
    inside a string literal is never mistaken for a comment start.
    """
    result = _STRING_LITERAL_RE.sub(_blank_span, content)
    if lang == "python":
        result = _PY_COMMENT_RE.sub(_blank_span, result)
    else:
        result = _BLOCK_COMMENT_RE.sub(_blank_span, result)
        result = _LINE_COMMENT_RE.sub(_blank_span, result)
    return result

# RC-W1-004: bare type references — no `.member` involved, so
# _MEMBER_ACCESS_RE never sees these. This is exactly the shape of the
# confirmed cells/net defect: `catch (XmlParsingException ex)`.
_CATCH_CLAUSE_RE = re.compile(r"\bcatch\s*\(\s*([A-Z][A-Za-z0-9_]*)\s+\w+\s*\)")
_NEW_CONSTRUCTOR_RE = re.compile(r"\bnew\s+([A-Z][A-Za-z0-9_]*)\s*[\(<]")
_PY_IMPORT_FROM_RE = re.compile(r"^[ \t]*from\s+[\w.]+\s+import\s+(.+)$", re.MULTILINE)

# Language tag normalization
_LANG_NORMALIZE: dict[str, str] = {
    "python": "python",
    "py": "python",
    "csharp": "csharp",
    "cs": "csharp",
    "c#": "csharp",
    "java": "java",
    "cpp": "cpp",
    "c++": "cpp",
    "typescript": "typescript",
    "ts": "typescript",
    "javascript": "javascript",
    "js": "javascript",
}

# Common false-positive class names that appear in code but aren't API classes
_IGNORE_CLASSES: frozenset[str] = frozenset({
    "System", "Console", "String", "Integer", "Boolean", "Object",
    "File", "Path", "List", "Dict", "Set", "Tuple", "Optional",
    "Type", "None", "True", "False", "Math", "Arrays", "Collections",
    "Exception", "Error", "RuntimeError", "ValueError", "TypeError",
    "IO", "OS", "Re", "Json", "Yaml",
    # ST-104(b): TypeScript/JavaScript global builtins -- the sibling Java
    # identifier "Arrays" (plural) was already present, but no JS/TS globals
    # were, so idiomatic code like `Array.from(...)` or `new Uint8Array(...)`
    # false-positived as unknown/unreachable classes.
    "Array", "Promise", "Map", "Date", "RegExp", "JSON", "Number",
    "Uint8Array", "Buffer", "Symbol", "WeakMap", "WeakSet",
})


def _extract_bare_type_names(content: str, lang: str) -> list[tuple[str, int]]:
    """Return [(class_name, char_offset), ...] for bare type references that
    carry no `.member` access and so are invisible to _MEMBER_ACCESS_RE.
    """
    hits: list[tuple[str, int]] = []
    if lang in ("csharp", "java"):
        for m in _CATCH_CLAUSE_RE.finditer(content):
            hits.append((m.group(1), m.start(1)))
        for m in _NEW_CONSTRUCTOR_RE.finditer(content):
            hits.append((m.group(1), m.start(1)))
    elif lang == "python":
        for m in _PY_IMPORT_FROM_RE.finditer(content):
            # All names on one `from pkg import A, B, C` line report the
            # same offset (the line's own start) — precise enough for the
            # line number a Finding needs; the message names the identifier.
            line_start = m.start(1)
            for raw in m.group(1).split(","):
                name = raw.strip()
                if " as " in name:
                    name = name.split(" as ")[0].strip()
                if name and name[0].isupper():
                    hits.append((name, line_start))
    return hits


class CodeBlockApiEvaluator(BaseEvaluator):
    """Validates API tokens in code blocks against the knowledge model.

    For each fenced code block, extracts ClassName.member patterns and
    checks whether the class exists in api_surface.json and whether the
    member (method or property) exists on that class (WARN if not).

    RC-W1-004: also extracts bare type references (catch clauses,
    `new X(...)`, Python `from pkg import Name`) and, for every class
    reference regardless of shape, checks whether the class is actually
    reachable/public — not merely present in api_surface.json (FAIL if
    confirmed unreachable; see module docstring and `_reachability.py`).
    """

    name = "code_block_api"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not isinstance(knowledge, Knowledge) or not knowledge.available:
            return [Finding(
                level="WARN",
                category="CB",
                filepath=str(page.filepath),
                line_no=0,
                message=(
                    f"UNVERIFIED: knowledge artifacts not available for "
                    f"{page.family}/{page.platform}. Claims cannot be validated."
                ),
                evaluator=self.name,
            )]

        # Only evaluate pages that have code blocks
        if not page.code_blocks:
            return []

        findings: list[Finding] = []
        # RC-W1-004: avoid emitting the same (class_name, line) reachability
        # finding twice when a class turns up via both the member-access loop
        # and the bare-type loop on the same line (e.g. an import line reused
        # later as `Class.member`).
        seen_reachability: set[tuple[str, int]] = set()

        for block in page.code_blocks:
            # Skip blocks without a recognized language tag
            lang = _LANG_NORMALIZE.get(block.lang.lower(), "")
            if not lang:
                continue

            # ST-104: blank string/template literals and comments so their
            # text is never mistaken for a code identifier. Character
            # offsets and line counts stay valid against the original
            # `block.content` since only non-newline characters are blanked.
            scan_content = _sanitize_for_token_scan(block.content, lang)

            # Extract all ClassName.member tokens from the code block
            for match in _MEMBER_ACCESS_RE.finditer(scan_content):
                class_name = match.group(1)
                member_name = match.group(2)

                # Skip known false positives
                if class_name in _IGNORE_CLASSES:
                    continue

                line_offset = scan_content[:match.start()].count("\n")
                abs_line = block.start_line + 1 + line_offset

                # RC-W1-004: reachability check runs regardless of whether the
                # class is known — a class entirely absent from
                # api_surface.json (e.g. a C# `internal` type, excluded by
                # is_public() at scout time) still deserves the live fallback
                # before this evaluator falls back to its long-standing
                # "might be external, don't flag" default.
                rf = self._reachability_finding(
                    class_name, page, knowledge, lang, abs_line, seen_reachability)
                if rf is not None:
                    findings.append(rf)

                # Check if class exists in knowledge
                if class_name not in knowledge.classes:
                    # Don't flag unknown classes — they might be from
                    # external libraries, stdlib, or user code
                    continue

                # Class is known — check if member exists (inheritance-aware)
                if (not knowledge.has_method(class_name, member_name)
                        and not knowledge.has_property(class_name, member_name)
                        and not knowledge.has_enum_member(class_name, member_name)):
                    # Member doesn't exist on this class
                    findings.append(Finding(
                        level="WARN",
                        category="CB",
                        filepath=str(page.filepath),
                        line_no=abs_line,
                        message=(
                            f"Code uses `{class_name}.{member_name}` but "
                            f"`{member_name}` is not a known method or property "
                            f"of `{class_name}` in api_surface.json"
                        ),
                        suggestion=(
                            f"Verify that `{class_name}.{member_name}` exists "
                            f"in the FOSS API. If not, fix the code example or "
                            f"remove the reference."
                        ),
                        evaluator=self.name,
                    ))

            # RC-W1-004: bare type references (catch clauses, `new X(...)`,
            # Python `from pkg import X`) carry no `.member` access, so the
            # loop above never sees them.
            for class_name, offset in _extract_bare_type_names(scan_content, lang):
                if class_name in _IGNORE_CLASSES:
                    continue
                line_offset = scan_content[:offset].count("\n")
                abs_line = block.start_line + 1 + line_offset
                rf = self._reachability_finding(
                    class_name, page, knowledge, lang, abs_line, seen_reachability)
                if rf is not None:
                    findings.append(rf)

        return findings

    def _reachability_finding(
        self,
        class_name: str,
        page: Page,
        knowledge: Any,
        lang: str,
        abs_line: int,
        seen: set[tuple[str, int]],
    ) -> "Finding | None":
        """RC-W1-004: FAIL when *class_name* is confirmed unreachable/non-public.

        Primary signal: the `reachable` field on the api_surface.json class
        entry (set by extraction/api_surface.py). Fallback: a best-effort
        live clone-cache check (_reachability.live_unreachable) used when the
        class has no `reachable` key yet, or is absent from api_surface.json
        entirely (e.g. a C# `internal` type, excluded at scout time).
        """
        key = (class_name, abs_line)
        if key in seen:
            return None

        class_entry = knowledge.classes.get(class_name)
        primary = _reachability.class_reachability(class_entry)
        if primary is False:
            seen.add(key)
            return Finding(
                level="FAIL",
                category="CB",
                filepath=str(page.filepath),
                line_no=abs_line,
                message=(
                    f"Code references `{class_name}`, which api_surface.json "
                    f"marks `reachable: false` — not part of the public API "
                    f"a real consumer of this package can reach"
                ),
                suggestion=(
                    f"Replace `{class_name}` with a publicly reachable class, "
                    f"or verify the exact import/usage path a real consumer "
                    f"would need and document that instead."
                ),
                evaluator=self.name,
            )
        if primary is True:
            return None  # explicit positive primary signal — trust it

        # primary is None here: either the class is entirely absent from
        # api_surface.json (e.g. a C# `internal` type, excluded at scout
        # time), or it IS present but has no `reachable` key yet (knowledge
        # not re-scouted since Part 1 landed) — try the live fallback either
        # way; a class merely existing in api_surface.json is not itself
        # proof of reachability.
        is_unreachable, reason = _reachability.live_unreachable(
            class_name, page.family, page.platform, lang)
        if is_unreachable:
            seen.add(key)
            return Finding(
                level="FAIL",
                category="CB",
                filepath=str(page.filepath),
                line_no=abs_line,
                message=f"Code references `{class_name}` — {reason}",
                suggestion=(
                    f"Replace `{class_name}` with a publicly reachable class, "
                    f"or verify the exact import/usage path a real consumer "
                    f"would need and document that instead."
                ),
                evaluator=self.name,
            )
        return None
