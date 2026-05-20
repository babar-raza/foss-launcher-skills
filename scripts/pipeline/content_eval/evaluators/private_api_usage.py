# Adapted from aspose.org
"""Private API usage evaluator — detects underscore-prefixed member access in code blocks.

Python convention: identifiers starting with a single underscore (e.g. `_control_points`)
are private implementation details.  Publishing code examples that rely on private APIs:
  - Breaks with any future refactor of the library internals
  - Misleads readers into using non-public interfaces
  - Causes content to fail technical accuracy review

This evaluator reports a FAIL for each code block line that accesses a private member
via `obj._member` or `Class._member` syntax.  Double-underscore (dunder) names are
excluded because they have defined Python semantics (`__init__`, `__str__`, etc.).

Category: PA (Private API)
"""

from __future__ import annotations

import re
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Match access to a single-underscore-prefixed member via dot notation:
#   variable._member(   -- method call
#   variable._member    -- attribute access
# Excludes double-underscore (dunder) patterns.
# Group 1: receiver (variable or class name)
# Group 2: private member name (starts with exactly one _)
_PRIVATE_ACCESS_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*\.\s*(_[A-Za-z]\w*)\b"
)

# Dunder pattern -- these are standard Python protocol methods, not private
_DUNDER_RE = re.compile(r"^__[A-Za-z]+__$")

# Language tags where underscore-private convention applies
_PYTHON_LIKE_LANGS: frozenset[str] = frozenset({"python", "py"})


class PrivateApiUsageEvaluator(BaseEvaluator):
    """Detects underscore-prefixed private API member access in code blocks.

    Reports FAIL for each access to a `_member` (single leading underscore)
    in Python code blocks.  Dunder names (`__init__`, etc.) are excluded.
    Only the first occurrence per (receiver, member) pair per page is reported
    to avoid flooding the findings list.
    """

    name = "private_api_usage"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        # Only applies to Python pages (underscore convention is Python-specific)
        if page.platform not in _PYTHON_LIKE_LANGS and page.platform != "python":
            return []

        # Only evaluate pages that have code blocks
        if not page.code_blocks:
            return []

        # TC-HCR-002B: Load known workaround members from knowledge
        # knowledge.workaround_members is a dict {(class, member): reason}
        workaround_dict: dict[tuple[str, str], str] = {}
        if knowledge is not None:
            wm = getattr(knowledge, "workaround_members", None)
            if isinstance(wm, dict):
                workaround_dict = wm

        findings: list[Finding] = []
        reported: set[tuple[str, str]] = set()  # (receiver, member) dedup key

        for block in page.code_blocks:
            # Only check Python code blocks
            lang = (block.lang or "").lower().strip()
            if lang not in _PYTHON_LIKE_LANGS and lang != "":
                # For untagged blocks on Python pages, still check them
                if lang:
                    continue

            for match in _PRIVATE_ACCESS_RE.finditer(block.content):
                receiver = match.group(1)
                member = match.group(2)

                # Skip dunder names (standard Python protocol)
                if _DUNDER_RE.match(member):
                    continue

                # Skip self._member within class bodies -- this is normal
                # internal implementation, not usage of another class's private API.
                # We flag external access: obj._member where obj is not 'self'.
                if receiver in ("self", "cls"):
                    continue

                dedup_key = (receiver, member)
                if dedup_key in reported:
                    continue
                reported.add(dedup_key)

                line_offset = block.content[: match.start()].count("\n")
                abs_line = block.start_line + 1 + line_offset

                # Check if this is a known workaround — downgrade to INFO
                # Match by member name against any class in workaround_dict
                workaround_reason = None
                for (wc, wm), wr in workaround_dict.items():
                    if member == wm:
                        workaround_reason = wr
                        break
                is_workaround = workaround_reason is not None
                if is_workaround:
                    findings.append(Finding(
                        level="INFO",
                        category="PA",
                        filepath=str(page.filepath),
                        line_no=abs_line,
                        message=(
                            f"Code uses known workaround `{receiver}.{member}` "
                            f"(documented in workarounds.json). "
                            f"No public mutation API exists for this operation."
                        ),
                        suggestion=(
                            f"This is a known library limitation tracked in "
                            f"workarounds.json. No action needed unless the "
                            f"library adds a public API alternative."
                        ),
                        evaluator=self.name,
                    ))
                    continue

                findings.append(Finding(
                    level="FAIL",
                    category="PA",
                    filepath=str(page.filepath),
                    line_no=abs_line,
                    message=(
                        f"Code accesses private member `{receiver}.{member}` "
                        f"(underscore-prefixed API). "
                        f"Private members are not part of the public API contract "
                        f"and may change or be removed without notice."
                    ),
                    suggestion=(
                        f"Replace `{receiver}.{member}` with the equivalent public API. "
                        f"Check knowledge/{{family}}/{{platform}}/merged/api_surface.json "
                        f"for the correct public member name."
                    ),
                    evaluator=self.name,
                ))

        return findings
