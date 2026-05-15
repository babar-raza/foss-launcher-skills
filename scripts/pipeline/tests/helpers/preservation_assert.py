"""Preservation assertion helpers for heal-page Pass 2 and page-update preserve-first tests.

Sprint: heal-page-pass2-preserve-first
"""
from __future__ import annotations

import re


# Heading delimiter pattern — matches H2 or H3 headings
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)", re.MULTILINE)


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown text into {heading_line: body_text} sections.

    Sections are delimited by H2/H3 headings.
    Content before the first H2/H3 heading is stored under key '' (empty string).
    Each heading key includes the full heading line (e.g. '## See Also').
    Body includes everything after the heading until the next H2/H3 or end-of-text.

    Raises ValueError if the same heading line appears more than once.
    """
    sections: dict[str, str] = {}
    order: list[str] = []

    # Find all heading positions
    heading_matches = list(_HEADING_RE.finditer(text))

    # Content before first heading
    pre = text[: heading_matches[0].start()] if heading_matches else text
    sections[""] = pre
    order.append("")

    for i, m in enumerate(heading_matches):
        heading_line = m.group(0).rstrip()
        if heading_line in sections:
            raise ValueError(
                f"Duplicate heading '{heading_line}' in fixture — use unique headings"
            )
        # Body: from end of heading line to start of next heading (or end of text)
        body_start = m.end()
        body_end = heading_matches[i + 1].start() if i + 1 < len(heading_matches) else len(text)
        sections[heading_line] = text[body_start:body_end]
        order.append(heading_line)

    return sections


def _find_parent_heading(text: str, marker: str) -> str | None:
    """Return the nearest H2/H3 heading above the first occurrence of marker in text.

    Returns None if marker appears before any heading.
    Returns '' if text has no headings at all.
    """
    marker_pos = text.find(marker)
    if marker_pos == -1:
        return None

    best_heading: str | None = None
    for m in _HEADING_RE.finditer(text):
        if m.start() < marker_pos:
            best_heading = m.group(0).rstrip()
        else:
            break

    return best_heading  # None if before any heading


def assert_sections_preserved(
    before_text: str,
    after_text: str,
    protected_headings: list[str],
) -> None:
    """Assert that all protected sections are byte-for-byte identical in after_text.

    Args:
        before_text: Markdown content before mutation.
        after_text: Markdown content after mutation.
        protected_headings: List of heading lines (e.g. ['## See Also']) that must be
            preserved unchanged (heading + body).

    Raises:
        ValueError: If a protected heading appears more than once in before_text.
        AssertionError: If any protected heading is deleted, has its body changed,
            has its heading text changed, or has been reordered relative to other
            protected headings.
    """
    before_sections = _split_sections(before_text)
    after_sections = _split_sections(after_text)

    # Check each protected heading
    for heading in protected_headings:
        if heading not in before_sections:
            raise AssertionError(
                f"Protected heading '{heading}' not found in before_text"
            )
        if heading in after_sections:
            # Both present — verify body identical
            before_body = before_sections[heading]
            after_body = after_sections[heading]
            if before_body != after_body:
                raise AssertionError(
                    f"Protected section '{heading}' body changed.\n"
                    f"Before body: {before_body!r}\n"
                    f"After body: {after_body!r}"
                )
        else:
            # Heading absent from after — deletion
            raise AssertionError(
                f"Protected section '{heading}' was deleted in after_text"
            )

    # Check ordering: protected headings must appear in the same relative order
    # as in before_text
    before_heading_order = [
        h for h in _split_sections(before_text).keys()
        if h in protected_headings
    ]
    after_heading_order = [
        h for h in _split_sections(after_text).keys()
        if h in protected_headings
    ]
    if before_heading_order != after_heading_order:
        raise AssertionError(
            f"Protected headings were reordered.\n"
            f"Before order: {before_heading_order}\n"
            f"After order:  {after_heading_order}"
        )


def assert_unit_preserved(
    before_text: str,
    after_text: str,
    marker_text: str,
) -> None:
    """Assert that a unique content unit (identified by marker_text) is preserved.

    The unit must:
    - Still exist in after_text.
    - Have identical text in after_text.
    - Remain under the same nearest H2/H3 parent heading.

    Args:
        before_text: Markdown content before mutation.
        after_text: Markdown content after mutation.
        marker_text: Unique text string identifying the unit.

    Raises:
        ValueError: If marker_text appears more than once in before_text.
        AssertionError: If the unit is deleted, changed, or moved to a different parent.
    """
    # Uniqueness check
    before_count = before_text.count(marker_text)
    if before_count == 0:
        raise ValueError(f"Marker '{marker_text}' not found in before_text")
    if before_count > 1:
        raise ValueError(
            f"Marker '{marker_text}' appears {before_count} times in before_text — must be unique"
        )

    # Presence check in after
    if marker_text not in after_text:
        raise AssertionError(
            f"Unit with marker '{marker_text}' was deleted in after_text"
        )

    # Parent heading check
    before_parent = _find_parent_heading(before_text, marker_text)
    after_parent = _find_parent_heading(after_text, marker_text)

    if before_parent != after_parent:
        raise AssertionError(
            f"Unit with marker '{marker_text}' moved to different parent heading.\n"
            f"Before parent: {before_parent!r}\n"
            f"After parent:  {after_parent!r}"
        )
