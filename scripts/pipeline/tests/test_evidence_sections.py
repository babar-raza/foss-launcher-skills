"""Tests for evidence/sections.py (TC-22, MT072-2026-09-23-EXAMPLE-VERIFICATION-
PRODUCTIONIZATION -- root cause of ST-213).

No test file existed for this module before this taskcard, despite it feeding
every content page's evidence.sections frontmatter block.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from evidence.sections import _parse_sections  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_simple_h2_h3_split(tmp_path):
    p = tmp_path / "page.md"
    _write(p, "---\ntitle: x\n---\n## First\nbody one\n### Second\nbody two\n")
    secs = _parse_sections(p)
    headings = [s["heading"] for s in secs]
    assert headings == ["Introduction", "First", "Second"]


def test_balanced_code_fence_does_not_swallow_headings(tmp_path):
    p = tmp_path / "page.md"
    _write(
        p,
        "---\ntitle: x\n---\n"
        "## First\n```python\nprint(1)\n```\n"
        "## Second\nbody\n",
    )
    secs = _parse_sections(p)
    headings = [s["heading"] for s in secs]
    assert headings == ["Introduction", "First", "Second"]


def test_misplaced_fence_swallows_downstream_headings_and_warns(tmp_path, capsys):
    """Regression test for the exact live bug found in TC-22/ST-213: an odd
    fence count (a fence closed one line too early, stranding real code as
    plain text, followed by a stray extra closer) flips in_code parity for
    the rest of the document, silently absorbing every later heading into
    the section where the parity flip happened."""
    p = tmp_path / "page.md"
    _write(
        p,
        "---\ntitle: x\n---\n"
        "## Adding Child Nodes\n"
        "```java\n"
        "Node detached = new Node(\"standalone\");\n"
        "```\n"
        "root.addChildNode(detached);\n"
        "```\n"
        "## Querying Child Nodes\n"
        "this heading gets swallowed\n"
        "## Traversing the Full Tree\n"
        "this one too\n",
    )
    secs = _parse_sections(p)
    headings = [s["heading"] for s in secs]
    # Both real downstream headings are lost -- this IS the bug, not a
    # false negative in the test: the fix is in the CONTENT (balance the
    # fence), not in silently working around it here (see module docstring).
    assert headings == ["Introduction", "Adding Child Nodes"]
    assert "Querying Child Nodes" not in headings
    assert "Traversing the Full Tree" not in headings

    captured = capsys.readouterr()
    assert "WARNING [evidence/sections.py]" in captured.err
    assert "Querying Child Nodes" in captured.err
    assert "Traversing the Full Tree" in captured.err
    assert str(p) in captured.err


def test_fixed_fence_recovers_all_sections(tmp_path, capsys):
    """The same document with the fence correctly balanced (the real fix
    applied to scene-graph.md) parses clean, with no warning."""
    p = tmp_path / "page.md"
    _write(
        p,
        "---\ntitle: x\n---\n"
        "## Adding Child Nodes\n"
        "```java\n"
        "Node detached = new Node(\"standalone\");\n"
        "root.addChildNode(detached);\n"
        "```\n"
        "## Querying Child Nodes\n"
        "not swallowed\n"
        "## Traversing the Full Tree\n"
        "not swallowed either\n",
    )
    secs = _parse_sections(p)
    headings = [s["heading"] for s in secs]
    assert headings == [
        "Introduction",
        "Adding Child Nodes",
        "Querying Child Nodes",
        "Traversing the Full Tree",
    ]
    captured = capsys.readouterr()
    assert captured.err == ""


def test_heading_only_first_line_is_introduction(tmp_path):
    p = tmp_path / "page.md"
    _write(p, "---\ntitle: x\n---\njust prose, no headings at all\n")
    secs = _parse_sections(p)
    assert len(secs) == 1
    assert secs[0]["heading"] == "Introduction"
    assert secs[0]["line"] == 1


def test_h4_is_not_a_section_boundary(tmp_path):
    """Only H1-H3 (level <= 3) start a new section per this module's own
    docstring ("H2/H3 are section boundaries") -- H4+ stays in the parent
    section's body_lines."""
    p = tmp_path / "page.md"
    _write(p, "---\ntitle: x\n---\n## Parent\n#### Sub-detail\nbody\n")
    secs = _parse_sections(p)
    headings = [s["heading"] for s in secs]
    assert headings == ["Introduction", "Parent"]
    assert any("#### Sub-detail" in text for _, text in secs[1]["body_lines"])
