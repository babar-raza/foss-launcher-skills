"""Code block API validation evaluator (FIX-07).

Extracts API tokens (ClassName.method_name, ClassName.property_name) from
fenced code blocks and verifies each against api_surface.json.  This closes
the biggest evaluator blind spot identified in the forensic audit: pages
graded A that contain broken code examples calling non-existent APIs.

Category: CB (Code Block API)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Import Knowledge for type checking
import sys as _sys
from pathlib import Path as _KPath
_scripts_dir = _KPath(__file__).resolve().parent.parent.parent.parent
if str(_scripts_dir) not in _sys.path:
    _sys.path.insert(0, str(_scripts_dir))
if str(_scripts_dir / 'pipeline') not in _sys.path:
    _sys.path.insert(0, str(_scripts_dir / 'pipeline'))
from knowledge_core import Knowledge  # noqa: E402


# ---------------------------------------------------------------------------
# Token extraction patterns
# ---------------------------------------------------------------------------

# Match ClassName.member_name patterns in code.
# ClassName: starts with uppercase letter, at least 2 chars.
# member_name: starts with letter or underscore, word chars.
_MEMBER_ACCESS_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9_]{1,})\s*\.\s*([a-zA-Z_]\w*)"
)

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
})


class CodeBlockApiEvaluator(BaseEvaluator):
    """Validates API tokens in code blocks against the knowledge model.

    For each fenced code block, extracts ClassName.member patterns and
    checks whether the class exists in api_surface.json and whether the
    member (method or property) exists on that class.
    """

    name = "code_block_api"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not isinstance(knowledge, Knowledge) or not knowledge.available:
            return []

        # Only evaluate pages that have code blocks
        if not page.code_blocks:
            return []

        findings: list[Finding] = []

        for block in page.code_blocks:
            # Skip blocks without a recognized language tag
            lang = _LANG_NORMALIZE.get(block.lang.lower(), "")
            if not lang:
                continue

            # Extract all ClassName.member tokens from the code block
            for match in _MEMBER_ACCESS_RE.finditer(block.content):
                class_name = match.group(1)
                member_name = match.group(2)

                # Skip known false positives
                if class_name in _IGNORE_CLASSES:
                    continue

                # Check if class exists in knowledge
                if class_name not in knowledge.classes:
                    # Don't flag unknown classes — they might be from
                    # external libraries, stdlib, or user code
                    continue

                # Class is known — check if member exists
                known_methods = knowledge.methods.get(class_name, set())
                known_props = knowledge.properties.get(class_name, set())
                known_enums = knowledge.enum_members.get(class_name, set())

                if (member_name not in known_methods
                        and member_name not in known_props
                        and member_name not in known_enums):
                    # Member doesn't exist on this class
                    line_offset = block.content[:match.start()].count("\n")
                    abs_line = block.start_line + 1 + line_offset

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

        return findings