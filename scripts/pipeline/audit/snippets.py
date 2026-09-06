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
from lib.example_verification.code_fences import enumerate_code_blocks  # noqa: E402


def verify_snippet_coverage(filepath, knowledge) -> list:
    """Check whether code blocks in content have matching verified snippets.

    This is an advisory (INFO/WARN-level) check, off by default (see
    `audit/runner.py`'s `--check-snippets` flag). MT065-2026-09-06-EXAMPLE-
    VERIFICATION-CENTRALIZATION/C6: was a fuzzy `classes_used`/`methods_used`
    token-intersection heuristic; now an exact `sha256_norm` lookup into the
    snippet index's `code_sha256.norm` field (set by `promote.py:
    _promote_snippets`), per the governing plan's "verify at the source,
    inherit at the page" design. `code_sha256` is only populated for
    products (re)promoted after this taskcard -- until a portfolio-wide
    post-promote sweep has run, most products' indexes won't have it yet,
    so this SKIPs loudly (one INFO finding, not a silent no-op) rather than
    falling back to the old fuzzy match, which this check is meant to
    replace, not supplement.

    Only runs when the knowledge model has a populated snippet_index.
    """
    findings = []
    if not knowledge.snippet_index:
        return findings

    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError:
        return findings

    norm_hash_index: dict[str, dict] = {}
    for entry in knowledge.snippet_index:
        if not isinstance(entry, dict):
            continue
        code_sha = entry.get("code_sha256")
        if isinstance(code_sha, dict) and code_sha.get("norm"):
            norm_hash_index[code_sha["norm"]] = entry

    if not norm_hash_index:
        findings.append(Finding(
            "INFO", filepath, 0,
            "Snippet coverage check SKIPPED: this product's snippet index has no "
            "code_sha256 yet -- run the post-promote proof sweep to populate it",
            "",
        ))
        return findings

    for block in enumerate_code_blocks(text):
        if not block.content.strip():
            continue
        if block.sha256_norm in norm_hash_index:
            continue  # exact match against a verified snippet -- nothing to report
        findings.append(Finding(
            "WARN", filepath, block.start_line,
            f"Code block at line {block.start_line} has no matching verified snippet "
            "(exact-hash lookup against this product's snippet index)",
            "Consider extracting code from repo examples instead of generating"
        ))

    return findings


def _check_code_block_snippets(code_text, line_no, filepath, knowledge, findings):
    """The pre-C6 fuzzy classes_used/methods_used heuristic. No longer called by
    `verify_snippet_coverage` (replaced by the exact sha256_norm lookup above), but kept
    here -- unused -- because `audit/__init__.py` re-exports it and that file is outside
    this taskcard's allowed_paths (scripts/pipeline/audit/__init__.py is not listed for
    C6); deleting this function would break that import. A follow-on taskcard/commit that
    touches audit/__init__.py should remove both the function and the re-export together."""
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