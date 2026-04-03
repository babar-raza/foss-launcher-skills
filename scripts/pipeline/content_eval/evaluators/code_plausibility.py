"""Code plausibility evaluator — validates code structure beyond token presence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

KNOWLEDGE_ROOT = Path("knowledge")

# C-1: detect Python calls to properties as methods — e.g. obj.width() where width is a property
_PYTHON_METHOD_CALL_RE = re.compile(r"\.\s*(\w+)\s*\(\s*\)", re.MULTILINE)

# Common patterns that indicate implausible code
_EMPTY_BLOCK_RE = re.compile(r"^\s*$")
_UNCLOSED_STRING_RE = re.compile(r'(?<![\\])\"[^\"]*$|(?<![\\])\'[^\']*$')
_MULTIPLE_DOTS_RE = re.compile(r"\.\.\.")  # Ellipsis in code (placeholder)
_PSEUDO_COMMENT_RE = re.compile(
    r"//\s*(?:TODO|FIXME|HACK|add\s+your|replace\s+with|your\s+code\s+here)",
    re.IGNORECASE,
)

# Null-unsafe text-frame access: code reads/sets .text_frame or .TextFrame without
# first capturing the return value of add_text_frame()/AddTextFrame().
# Pattern: code contains text_frame access BUT no add_text_frame() assignment.
_TEXT_FRAME_ACCESS_RE = re.compile(
    r"\.(?:text_frame|TextFrame)\s*[.=]",
    re.MULTILINE,
)
_TEXT_FRAME_INIT_RE = re.compile(
    r"=\s*\w+\.(?:add_text_frame|AddTextFrame)\s*\(",
    re.MULTILINE,
)

# FR-17a: java_awt_contamination — import java.awt.* in Java code
_JAVA_AWT_IMPORT_RE = re.compile(
    r"import\s+java\.awt\b",
    re.MULTILINE,
)

# FR-17a: net_null_unsafe_textframe — .TextFrame.Text = without preceding .AddTextFrame(
_NET_TEXTFRAME_TEXT_SET_RE = re.compile(
    r"\.TextFrame\.Text\s*=",
    re.MULTILINE,
)
_NET_ADD_TEXTFRAME_RE = re.compile(
    r"\.AddTextFrame\s*\(",
    re.MULTILINE,
)

# FR-17a: java_null_unsafe_gettextframe — .getTextFrame(). after addAutoShape/addConnector
_JAVA_GET_TEXTFRAME_RE = re.compile(
    r"\.getTextFrame\s*\(\s*\)\.",
    re.MULTILINE,
)
_JAVA_ADD_SHAPE_RE = re.compile(
    r"\.(?:addAutoShape|addConnector)\s*\(",
    re.MULTILINE,
)
_JAVA_ADD_TEXTFRAME_RE = re.compile(
    r"\.addTextFrame\s*\(",
    re.MULTILINE,
)

# FR-17a: python_wrong_saveformat — {alias}.export.SaveFormat in Python
# Matches patterns like: slides.export.SaveFormat  or  aspose.export.SaveFormat
_PY_WRONG_SAVEFORMAT_RE = re.compile(
    r"\b(\w+)\.export\.SaveFormat\b",
    re.MULTILINE,
)


class CodePlausibilityEvaluator(BaseEvaluator):
    """Validates that code examples are structurally plausible.

    Checks:
    - Code blocks are not empty
    - No pseudo-code placeholder comments
    - No obviously truncated code (ellipsis as content)
    - Code blocks have reasonable length for their context
    """

    name = "code_plausibility"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        findings: list[Finding] = []

        for block in page.code_blocks:
            # Skip non-code blocks
            if block.lang in ("bash", "shell", "sh", "xml", "json", "yaml",
                              "toml", "text", "plain", "html", "css", "sql",
                              "gradle", "groovy", "powershell", "bat", "cmd",
                              "console", "markdown", "md"):
                continue

            content = block.content.strip()

            # Empty code block
            if not content:
                findings.append(Finding(
                    level="WARN",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message="Empty code block",
                    suggestion="Add code content or remove the block",
                    evaluator=self.name,
                ))
                continue

            lines = content.splitlines()

            # Check for pseudo-code placeholders
            for i, line in enumerate(lines):
                if _PSEUDO_COMMENT_RE.search(line):
                    findings.append(Finding(
                        level="WARN",
                        category="CP",
                        filepath=str(page.filepath),
                        line_no=block.start_line + 1 + i,
                        message="Placeholder comment in code example",
                        suggestion="Replace with actual working code",
                        evaluator=self.name,
                    ))

            # Check for ellipsis-as-code (truncated examples)
            ellipsis_lines = [i for i, line in enumerate(lines)
                              if line.strip() == "..." or line.strip() == "// ..."]
            if len(ellipsis_lines) > 0:
                findings.append(Finding(
                    level="INFO",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line + 1 + ellipsis_lines[0],
                    message="Ellipsis in code example (truncated/incomplete)",
                    suggestion="Provide a complete, runnable example",
                    evaluator=self.name,
                ))

            # Very short code blocks in docs (not reference — reference commonly
            # has single-line signatures which are fine)
            if len(lines) == 1 and page.page_role == "docs":
                findings.append(Finding(
                    level="INFO",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message="Single-line code example in docs page",
                    suggestion="Consider expanding to a more complete example",
                    evaluator=self.name,
                ))

            # Null-unsafe text-frame access: shape.TextFrame.Text or
            # shape.text_frame.text used without capturing AddTextFrame() return.
            if (block.lang in ("java", "csharp", "python", "kotlin")
                    and _TEXT_FRAME_ACCESS_RE.search(content)
                    and not _TEXT_FRAME_INIT_RE.search(content)):
                findings.append(Finding(
                    level="WARN",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message=(
                        "Null-unsafe text frame access: `.text_frame` or `.TextFrame` "
                        "used without capturing `add_text_frame()` / `AddTextFrame()` return value"
                    ),
                    suggestion=(
                        "Assign the return value: `tf = shape.add_text_frame(\"\")` "
                        "before accessing `shape.text_frame`"
                    ),
                    evaluator=self.name,
                ))

            # C-1: Python property-as-method — obj.prop() where prop is a property
            if (block.lang == "python"
                    and page.page_role == "reference"
                    and page.platform == "python"):
                findings.extend(
                    self._check_python_property_as_method(page, block.content, block.start_line)
                )

            # FR-17a: java_awt_contamination — FAIL when java.awt imported in Java code
            if block.lang in ("java",) and _JAVA_AWT_IMPORT_RE.search(content):
                findings.append(Finding(
                    level="FAIL",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message=(
                        "Java code imports `java.awt.*` — Aspose products use their "
                        "own Color/Drawing classes, not java.awt"
                    ),
                    suggestion=(
                        "Replace `import java.awt.Color` with the product's own Color class "
                        "(e.g. `com.aspose.slides.Color` or the FOSS equivalent)"
                    ),
                    evaluator=self.name,
                ))

            # FR-17a: net_null_unsafe_textframe — WARN for .TextFrame.Text = without AddTextFrame
            if (block.lang in ("csharp", "cs")
                    and _NET_TEXTFRAME_TEXT_SET_RE.search(content)
                    and not _NET_ADD_TEXTFRAME_RE.search(content)):
                findings.append(Finding(
                    level="WARN",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message=(
                        "Null-unsafe: `.TextFrame.Text =` used without a preceding "
                        "`.AddTextFrame(` — TextFrame may be null on a new shape"
                    ),
                    suggestion=(
                        "Call `shape.AddTextFrame(\"\")` first and assign the returned "
                        "ITextFrame before accessing `.Text`"
                    ),
                    evaluator=self.name,
                ))

            # FR-17a: java_null_unsafe_gettextframe — WARN for .getTextFrame(). after add shape
            if (block.lang in ("java",)
                    and _JAVA_GET_TEXTFRAME_RE.search(content)
                    and _JAVA_ADD_SHAPE_RE.search(content)
                    and not _JAVA_ADD_TEXTFRAME_RE.search(content)):
                findings.append(Finding(
                    level="WARN",
                    category="CP",
                    filepath=str(page.filepath),
                    line_no=block.start_line,
                    message=(
                        "Null-unsafe: `.getTextFrame().` used after `addAutoShape`/"
                        "`addConnector` without calling `addTextFrame()` first — "
                        "getTextFrame() will throw NullPointerException"
                    ),
                    suggestion=(
                        "Call `shape.addTextFrame(\"\")` on the new shape before "
                        "accessing `.getTextFrame()`"
                    ),
                    evaluator=self.name,
                ))

            # FR-17a: python_wrong_saveformat — WARN for {alias}.export.SaveFormat in Python
            if block.lang in ("python", "py"):
                for m in _PY_WRONG_SAVEFORMAT_RE.finditer(content):
                    alias = m.group(1)
                    line_no = block.start_line + content[: m.start()].count("\n")
                    findings.append(Finding(
                        level="WARN",
                        category="CP",
                        filepath=str(page.filepath),
                        line_no=line_no,
                        message=(
                            f"`{alias}.export.SaveFormat` — SaveFormat is not accessed "
                            f"via `.export.` in Python; use the correct import path for "
                            f"the SaveFormat enum"
                        ),
                        suggestion=(
                            "Import SaveFormat directly, e.g. "
                            "`from aspose.slides.export import SaveFormat` "
                            "then use `SaveFormat.PPTX` directly"
                        ),
                        evaluator=self.name,
                    ))

        return findings

    def _load_api_surface(self, page: Page) -> list[dict]:
        """Load api_surface.json for this page's family/platform."""
        if not page.family or not page.platform:
            return []
        api_path = KNOWLEDGE_ROOT / page.family / page.platform / "merged" / "api_surface.json"
        if not api_path.exists():
            return []
        try:
            return json.loads(api_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _check_python_property_as_method(
        self, page: Page, code: str, start_line: int
    ) -> list[Finding]:
        """Emit WARN when Python code calls a known property as a method: obj.prop()."""
        api_surface = self._load_api_surface(page)
        if not api_surface:
            return []

        # Get class name from linkTitle frontmatter (reference pages)
        class_name = page.frontmatter.get("linkTitle", "") or page.filepath.stem
        if not class_name:
            return []

        # Find matching class in api_surface
        cls_entry = next(
            (c for c in api_surface if c.get("name") == class_name), None
        )
        if not cls_entry:
            return []

        # Build property name set for this class
        property_names = {
            p.get("name", "")
            for p in cls_entry.get("properties", [])
            if p.get("name")
        }
        if not property_names:
            return []

        findings: list[Finding] = []
        for i, line in enumerate(code.splitlines()):
            for match in _PYTHON_METHOD_CALL_RE.finditer(line):
                name = match.group(1)
                if name in property_names:
                    findings.append(Finding(
                        level="WARN",
                        category="CP",
                        filepath=str(page.filepath),
                        line_no=start_line + i,
                        message=(
                            f"Property `{name}` of `{class_name}` called as a method "
                            f"`{name}()` — properties are accessed without parentheses in Python"
                        ),
                        suggestion=f"Use `obj.{name}` instead of `obj.{name}()`",
                        evaluator=self.name,
                    ))
        return findings
