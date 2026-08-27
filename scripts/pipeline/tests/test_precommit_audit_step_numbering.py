"""Regression coverage for pre-commit-audit.sh's step-tracking/numbering
invariants, sourced LIVE from the on-disk script at test time (never
hand-copied, so these tests cannot silently drift from the real script's
actual behavior -- 2026-08-26 pipeline reliability hardening pass,
reports/skill-gaps/2026-08-26-pipeline-reliability-hardening.md,
plan C:\\Users\\prora\\.claude\\plans\\deep-popping-bumblebee.md).

This closes two related defects found live in that session:

1. Every hand-written diagnostic label (``[Step N]`` in echo/sed output,
   ``# Step N: ...`` header comments) had drifted out of sync with the
   runtime array-index numbering ``_pc_print_summary()`` actually uses --
   two independent numbering schemes for the same checks, confirmed by
   comparing hook output against the summary table.
2. A structural bug, found while fixing (1): the "Docs developer-guide slug
   quality" check (added by commit a439199f8f) had no ``_pc_step_start`` of
   its own -- it ran silently inside the preceding step's slot but still
   called ``_pc_step_end`` unconditionally, pushing one extra entry onto
   ``_PC_RESULTS``/``_PC_TIMES`` with no matching ``_PC_NAMES`` entry. That
   silently shifted every subsequent step's displayed PASS/FAIL/timing by
   one position in the summary table (row *labels* stayed correct since
   they come from ``_PC_NAMES`` directly; only the *result*/*timing*
   columns for every step from that point on were wrong).

These tests operate purely on the script's source text (no bash execution
needed) -- they verify structural invariants that must hold for the runtime
numbering scheme to stay self-consistent.
"""
from __future__ import annotations

import re
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parents[2]
_PRECOMMIT_AUDIT_SH = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"

_START_RE = re.compile(r'^\s*_pc_step_start\s+"')
_END_RE = re.compile(r'^_pc_step_end\s+"(PASS|FAIL|WARN|SKIP)"')  # column-0 only
_LABEL_RE = re.compile(r"\[Step\s+(\d+)\]")
_COMMENT_RE = re.compile(r"^#\s+Step\s+(\d+)[a-z]?(?:\.\d+)?:")


def _read_lines() -> list[str]:
    return _PRECOMMIT_AUDIT_SH.read_text(encoding="utf-8").splitlines(keepends=True)


def _step_start_line_indices(lines: list[str]) -> list[int]:
    return [i for i, line in enumerate(lines) if _START_RE.match(line)]


def _block_of(line_i: int, starts: list[int]) -> int:
    """Which _PC_NAMES array index does source line `line_i` belong to?"""
    best = 0
    for b, s in enumerate(starts):
        if s <= line_i:
            best = b
        else:
            break
    return best


def test_every_top_level_step_end_has_a_preceding_step_start_in_its_own_slot():
    """No column-0 (unconditional) `_pc_step_end` may fire twice for the same
    `_pc_step_start` slot. This is the exact shape of the orphaned-block bug:
    two unconditional, top-level `_pc_step_end` calls with no
    `_pc_step_start` between them silently desynchronizes `_PC_RESULTS` from
    `_PC_NAMES` for every step after that point.
    """
    lines = _read_lines()
    starts = _step_start_line_indices(lines)
    assert starts, "no _pc_step_start calls found -- did the tracking mechanism get removed?"

    # Column-0 (unconditional/top-level) _pc_step_end calls, in source order.
    toplevel_ends = [i for i, line in enumerate(lines) if _END_RE.match(line)]

    # Each block spans [starts[b], starts[b+1]) (or to EOF for the last block).
    # A well-formed script has AT MOST one top-level, unconditional PASS-shaped
    # _pc_step_end per block (additional FAIL-path _pc_step_end calls are fine
    # as long as they're inside a conditional, i.e. not column-0 -- those were
    # already excluded by _END_RE only matching column-0 lines).
    per_block_toplevel_ends: dict[int, list[int]] = {}
    for end_line in toplevel_ends:
        b = _block_of(end_line, starts)
        per_block_toplevel_ends.setdefault(b, []).append(end_line)

    offenders = {
        b: lns for b, lns in per_block_toplevel_ends.items() if len(lns) > 1
    }
    assert not offenders, (
        "Found block(s) with more than one unconditional, top-level "
        "_pc_step_end call -- this is the orphaned-block bug class (a check "
        "running without its own _pc_step_start, sharing another step's "
        "slot while still closing it out): "
        f"{ {b: [ln + 1 for ln in lns] for b, lns in offenders.items()} }"
    )


def test_pc_names_and_pc_step_end_totals_are_consistent_with_control_flow():
    """`_pc_step_start` is called exactly once per logical step. `_pc_step_end`
    may be called more than once per step (FAIL-then-exit branch vs.
    PASS-at-completion branch are mutually exclusive at runtime), but every
    `_pc_step_end` call site -- conditional or not -- must fall within some
    block's span (i.e. after a `_pc_step_start` has already fired for it).
    """
    lines = _read_lines()
    starts = _step_start_line_indices(lines)
    first_start = starts[0]

    end_re_any_indent = re.compile(r"_pc_step_end\s+\"(PASS|FAIL|WARN|SKIP)\"")
    orphaned_before_any_start = [
        i + 1
        for i, line in enumerate(lines[:first_start])
        if end_re_any_indent.search(line)
    ]
    assert not orphaned_before_any_start, (
        "_pc_step_end called before the first _pc_step_start on line(s): "
        f"{orphaned_before_any_start}"
    )


def test_inline_step_labels_match_their_true_block_index():
    """Every hand-written `[Step N]` occurrence in echo/sed output must equal
    the real, current `_PC_NAMES` array index of the block it lives inside --
    i.e. the number a person reading live hook output sees must match the
    number the same check gets in `_pc_print_summary()`'s final table.
    """
    lines = _read_lines()
    starts = _step_start_line_indices(lines)

    mismatches = []
    for i, line in enumerate(lines):
        if _START_RE.match(line):
            continue
        for m in _LABEL_RE.finditer(line):
            labeled = int(m.group(1))
            actual = _block_of(i, starts)
            if labeled != actual:
                mismatches.append((i + 1, labeled, actual, line.strip()[:80]))

    assert not mismatches, (
        "Inline [Step N] label(s) drifted out of sync with their real "
        "summary-table position:\n"
        + "\n".join(
            f"  L{ln}: labeled [Step {labeled}] but lives in block {actual}: {text!r}"
            for ln, labeled, actual, text in mismatches
        )
    )


def test_step_header_comments_match_their_true_block_index():
    """Same invariant as the inline-label test, for the `# Step N: ...`
    documentation comments that introduce (or immediately follow) each
    block's `_pc_step_start` call.
    """
    lines = _read_lines()
    starts = _step_start_line_indices(lines)
    start_set = set(starts)

    mismatches = []
    for i, line in enumerate(lines):
        m = _COMMENT_RE.match(line)
        if not m:
            continue
        labeled = int(m.group(1))
        # nearest _pc_step_start within a small window, either direction
        best_block = None
        best_dist = None
        for d in range(0, 6):
            for j in (i - d, i + d):
                if 0 <= j < len(lines) and j in start_set:
                    dist = abs(j - i)
                    if best_dist is None or dist < best_dist:
                        best_dist = dist
                        best_block = starts.index(j)
            if best_block is not None:
                break
        if best_block is None:
            best_block = _block_of(i, starts)
        if labeled != best_block:
            mismatches.append((i + 1, labeled, best_block, line.strip()[:80]))

    assert not mismatches, (
        "Step header comment(s) drifted out of sync with their real "
        "summary-table position:\n"
        + "\n".join(
            f"  L{ln}: labeled 'Step {labeled}:' but nearest block is {actual}: {text!r}"
            for ln, labeled, actual, text in mismatches
        )
    )


def test_summary_uses_array_index_not_a_hand_maintained_counter():
    """Guard the mechanism itself: `_pc_print_summary()` must derive its
    displayed step number from the live `_PC_NAMES` array index (`$i` in the
    `for i in "${!_PC_NAMES[@]}"` loop), not a separately hand-maintained
    counter -- otherwise this whole test module is only checking today's
    snapshot, not the actual source of truth.
    """
    text = _PRECOMMIT_AUDIT_SH.read_text(encoding="utf-8")
    assert 'for i in "${!_PC_NAMES[@]}"' in text
    assert '"Step $i"' in text
