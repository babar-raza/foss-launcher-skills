"""snippets.py — Snippet coverage verification for content pages.

Extracted from audit.py (Phase 5). Advisory (INFO-level) check that verifies
code blocks in content have matching verified snippets from the knowledge model.
"""
from __future__ import annotations

import sys
from pathlib import Path

# sibling-import guard: sub-packages must add the pipeline root so they can
# import sibling top-level modules (knowledge_core, token_ops, core.*).
# This is not the antipattern -- Python adds the sub-package dir to sys.path,
# not the pipeline root. This guard is the correct workaround for the flat layout.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from token_ops import Finding  # noqa: E402


def verify_snippet_coverage(filepath, knowledge) -> list:
    """Check whether code blocks in content have matching verified snippets.

    This is an advisory (INFO-level) check.  For each fenced code block in
    the markdown file, it extracts class and method tokens and checks if any
    snippet in the snippet index contains the same classes/methods.  If no
    match is found, an INFO finding is emitted.

    Only runs when the knowledge model has a populated snippet_index.
    """
    findings = []
    if not knowledge.snippet_index:
        return findings

    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError:
        return findings

    lines = text.splitlines()
    in_code = False
    code_start = 0
    code_lines = []

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                # End of code block — analyze it
                code_text = "\n".join(code_lines)
                if code_text.strip():
                    _check_code_block_snippets(
                        code_text, code_start, filepath, knowledge, findings)
                in_code = False
                code_lines = []
            else:
                in_code = True
                code_start = line_no
                code_lines = []
        elif in_code:
            code_lines.append(line)

    return findings


def _check_code_block_snippets(code_text, line_no, filepath, knowledge, findings):
    """Check a single code block against snippet index entries."""
    # Extract class/method references from the code block
    block_classes = set()
    block_methods = set()

    for cls_name in knowledge.classes:
        if cls_name in code_text:
            block_classes.add(cls_name)
            for mname in knowledge.methods.get(cls_name, set()):
                if (f"{cls_name}.{mname}" in code_text
                        or f".{mname}(" in code_text):
                    block_methods.add(f"{cls_name}.{mname}")

    # If no API tokens found in this code block, skip
    if not block_classes:
        return

    # Check if any snippet shares classes+methods with this block
    for entry in knowledge.snippet_index:
        if not isinstance(entry, dict):
            continue
        snip_classes = set(entry.get("classes_used", []))
        snip_methods = set(entry.get("methods_used", []))

        # Match: at least one class AND (one method in common, or no methods extracted)
        if block_classes & snip_classes:
            if not block_methods or (block_methods & snip_methods):
                return  # Found a matching snippet

    # No matching snippet found — emit advisory
    classes_str = ", ".join(sorted(block_classes)[:5])
    findings.append(Finding(
        "INFO", filepath, line_no,
        f"Code block at line {line_no} has no matching verified snippet "
        f"(uses: {classes_str})",
        "Consider extracting code from repo examples instead of generating"
    ))