"""Tests for lib/example_verification/block_matcher.py (TC-01,
MT073-2026-09-24-LOCALE-CODE-BLOCK-DEFECT-REMEDIATION).
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from example_verification.block_matcher import match_blocks  # noqa: E402
from example_verification.code_fences import CodeBlock  # noqa: E402


def _block(lang: str, content: str, line: int = 1) -> CodeBlock:
    return CodeBlock(lang=lang, content=content, start_line=line, end_line=line + 1)


def test_equal_counts_use_position_fast_path():
    en = [_block("python", "print(1)"), _block("python", "print(2)")]
    loc = [_block("python", "completely different"), _block("python", "also different")]
    matches = match_blocks(en, loc)
    assert [m.method for m in matches] == ["position", "position"]
    assert [m.locale_index for m in matches] == [0, 1]
    assert all(m.similarity == 1.0 for m in matches)


def test_unequal_counts_reorders_via_content_similarity():
    """A real, live-confirmed case (docs.aspose.org 3d/net installation.md,
    ar locale): English has 3 blocks, locale has 4 -- an extra block was
    inserted before the others, so naive positional pairing (en[0]<->loc[0])
    is wrong; content similarity correctly finds en[0]<->loc[1] etc."""
    en = [
        _block("csharp", "using Aspose.ThreeD;\nvar scene = new Scene();"),
        _block("csharp", "scene.Save(\"out.fbx\");"),
        _block("csharp", "var loaded = Scene.FromFile(\"out.fbx\");"),
    ]
    loc = [
        _block("csharp", "// an extra locale-only intro block, unrelated content"),
        _block("csharp", "using Aspose.ThreeD;\nvar scene = new Scene();"),
        _block("csharp", "scene.Save(\"out.fbx\");"),
        _block("csharp", "var loaded = Scene.FromFile(\"out.fbx\");"),
    ]
    matches = match_blocks(en, loc)
    assert [m.locale_index for m in matches] == [1, 2, 3]
    assert all(m.method == "content-similarity" for m in matches)
    assert all(m.similarity > 0.9 for m in matches)


def test_no_confident_match_reports_unmatched_not_a_guess():
    en = [_block("python", "print(1)"), _block("python", "print(2)")]
    loc = [_block("python", "totally unrelated content xyz abc def")]
    matches = match_blocks(en, loc, min_similarity=0.9)
    # Only one locale block exists; at most one English block can claim it,
    # and only if similarity clears the threshold -- here it should not.
    assert all(m.locale_index is None for m in matches)
    assert all(m.method == "unmatched" for m in matches)


def test_low_similarity_below_threshold_is_unmatched_not_forced():
    en = [_block("python", "print('hello world')")]
    loc = [_block("python", "x = 1"), _block("python", "y = 2")]
    matches = match_blocks(en, loc, min_similarity=0.95)
    assert matches[0].locale_index is None
    assert matches[0].method == "unmatched"


def test_greedy_assignment_never_reuses_a_locale_index():
    en = [_block("python", "print(1)"), _block("python", "print(1)")]  # identical content
    loc = [_block("python", "print(1)")]  # only one locale block available
    matches = match_blocks(en, loc, min_similarity=0.5)
    assigned = [m.locale_index for m in matches if m.locale_index is not None]
    assert len(assigned) == len(set(assigned))  # no duplicate assignment


def test_empty_content_blocks_do_not_crash_similarity():
    en = [_block("python", "")]
    loc = [_block("python", ""), _block("python", "print(1)")]
    matches = match_blocks(en, loc, min_similarity=0.5)
    assert matches[0].locale_index is not None
