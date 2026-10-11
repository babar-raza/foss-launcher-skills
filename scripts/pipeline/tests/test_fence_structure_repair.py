"""Tests for fence_structure_repair.py (MT073 TC-09).

Fixtures mirror the two real corruption shapes confirmed live this mission
(content/blog.aspose.org/3d/net/3d-utilities-net/index.tr.md for
missing_opener; content/docs.aspose.org/sv/cells/net/developer-guide/
features.md for duplicate_block) in miniature, plus regression cases for
two real bugs caught while building this module: a mid-identifier
false-positive substring match, and CRLF-vs-LF comparison silently failing
every match.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from example_verification.fence_structure_repair import (  # noqa: E402
    _blocks_of,
    apply_repairs,
    detect_duplicate_block,
    detect_missing_opener,
    repair_file,
)

EN_MISSING_OPENER = """---
title: X
---

## Setup

```csharp
using Aspose.ThreeD;

var scene = new Scene();
```

---

## Transform

```csharp
using Aspose.ThreeD.Utilities;

var builder = new TransformBuilder();
builder.Translate(1, 0, 0);
```
"""

LOC_MISSING_OPENER = """---
title: Y
---

## Kurulum

```csharp
using Aspose.ThreeD;

var scene = new Scene();
```

---

## Donusum

var builder = new TransformBuilder();
builder.Translate(1, 0, 0);
```
"""

EN_DUPLICATE = """---
title: X
---

## Setup

```csharp
using Aspose.Cells_FOSS;

var wb = new Workbook();
```

---

## Cells

```csharp
using Aspose.Cells_FOSS;

var ws = wb.Worksheets[0];
ws.Cells["A1"].PutValue("Hello");
```
"""

LOC_DUPLICATE = """---
title: Y
---

## Installation

```csharp
using Aspose.Cells_FOSS;

var wb = new Workbook();
```

---

## Celler

var ws = wb.Worksheets[0];
ws.Cells["A1"].PutValue("Hello");

```

---

```csharp
using Aspose.Cells_FOSS;

var ws = wb.Worksheets[0];
ws.Cells["A1"].PutValue("Hello");
```
## Next Section
More prose here.
"""


def _write(tmp_path: Path, name: str, content: str, newline: str = "\n") -> Path:
    p = tmp_path / name
    p.write_bytes(content.replace("\n", newline).encode("utf-8"))
    return p


def test_missing_opener_repair_matches_english(tmp_path):
    en = _write(tmp_path, "en.md", EN_MISSING_OPENER)
    loc = _write(tmp_path, "loc.md", LOC_MISSING_OPENER)
    result = repair_file(en, loc)
    assert result.status == "ok"
    assert result.kind == "missing_opener"
    en_blocks = _blocks_of(EN_MISSING_OPENER)
    new_blocks = _blocks_of(result.new_text)
    assert len(new_blocks) == len(en_blocks) == 2
    for a, b in zip(new_blocks, en_blocks):
        assert (a.canonical_lang or a.lang) == (b.canonical_lang or b.lang)
        assert a.sha256_norm == b.sha256_norm
    # the translated heading/prose must survive untouched
    assert "## Donusum" in result.new_text


def test_duplicate_block_repair_matches_english(tmp_path):
    en = _write(tmp_path, "en.md", EN_DUPLICATE)
    loc = _write(tmp_path, "loc.md", LOC_DUPLICATE)
    result = repair_file(en, loc)
    assert result.status == "ok"
    assert result.kind == "duplicate_block"
    en_blocks = _blocks_of(EN_DUPLICATE)
    new_blocks = _blocks_of(result.new_text)
    assert len(new_blocks) == len(en_blocks) == 2
    for a, b in zip(new_blocks, en_blocks):
        assert (a.canonical_lang or a.lang) == (b.canonical_lang or b.lang)
        assert a.sha256_norm == b.sha256_norm
    # the unfenced duplicate must be gone, the next heading preserved and
    # properly separated
    assert result.new_text.count('var ws = wb.Worksheets[0];') == 1
    assert "## Next Section" in result.new_text


def test_already_correct_file_returns_no_repair_needed(tmp_path):
    en = _write(tmp_path, "en.md", EN_MISSING_OPENER)
    loc = _write(tmp_path, "loc.md", EN_MISSING_OPENER.replace("## Setup", "## Instellen"))
    result = repair_file(en, loc)
    assert result.status == "no_repair_needed"
    assert result.new_text is None
    assert result.repairs == []


def test_unrelated_content_drift_is_unresolved_not_guessed(tmp_path):
    """A locale whose code genuinely differs from English (not a fence
    defect at all) must be refused, never silently 'fixed' by overwriting
    real content -- this mission's own standing discipline."""
    en = _write(tmp_path, "en.md", EN_MISSING_OPENER)
    drifted = LOC_MISSING_OPENER.replace(
        'builder.Translate(1, 0, 0);', 'builder.Translate(9, 9, 9);  // genuinely different'
    )
    loc = _write(tmp_path, "loc.md", drifted)
    result = repair_file(en, loc)
    assert result.status == "unresolved"
    assert result.new_text is None


def test_mid_identifier_substring_is_not_a_false_match(tmp_path):
    """Regression: content/blog.aspose.org/3d/net/3d-utilities-net/index.tr.md
    real bug -- a suffix like 'Vector3 min = ...' must not match INSIDE an
    unrelated locale line 'FVector3 min = ...'. The line-boundary requirement
    in _find_unique must reject that and the file must come back unresolved
    (or matched at a real line boundary elsewhere), never with a fence
    spliced into the middle of a word."""
    en = EN_MISSING_OPENER.replace(
        "var builder = new TransformBuilder();",
        "Vector3 min = bounds.Minimum;",
    )
    loc = LOC_MISSING_OPENER.replace(
        "var builder = new TransformBuilder();",
        "FVector3 min = bounds.Minimum;",
    )
    en_path = _write(tmp_path, "en2.md", en)
    loc_path = _write(tmp_path, "loc2.md", loc)
    result = repair_file(en_path, loc_path)
    if result.status == "ok":
        assert "```csharp\nFVector3" not in result.new_text
        assert "F```csharp" not in result.new_text
    else:
        assert result.status == "unresolved"


def test_crlf_locale_produces_crlf_output(tmp_path):
    en = _write(tmp_path, "en.md", EN_MISSING_OPENER, newline="\n")
    loc = _write(tmp_path, "loc.md", LOC_MISSING_OPENER, newline="\r\n")
    result = repair_file(en, loc)
    assert result.status == "ok"
    raw = result.new_text
    assert "\r\n" in raw
    # every line ending must be CRLF, not a mix
    assert raw.replace("\r\n", "").count("\n") == 0


def test_duplicate_block_separator_has_no_doubled_blank_line(tmp_path):
    """Regression: an earlier version of _canonical_separator produced
    "```\\n\\n---\\n\\n\\n### Heading" (one extra blank line) instead of the
    correct "```\\n\\n---\\n\\n### Heading" -- caught by direct inspection
    of a real repaired file, not by the block-level verification gate
    (which only checks fenced code content, not the prose/separator text
    around it)."""
    en = _write(tmp_path, "en.md", EN_DUPLICATE)
    loc = _write(tmp_path, "loc.md", LOC_DUPLICATE)
    result = repair_file(en, loc)
    assert result.status == "ok"
    assert "```\n\n---\n\n## Next Section" in result.new_text
    assert "---\n\n\n" not in result.new_text


def test_apply_repairs_handles_multiple_insertions_in_one_pass():
    text = "AAAA BBBB CCCC"
    from example_verification.fence_structure_repair import FenceRepair

    repairs = [
        FenceRepair("missing_opener", "insert1", 5, 5, "[X]"),
        FenceRepair("missing_opener", "insert2", 10, 10, "[Y]"),
    ]
    out = apply_repairs(text, repairs)
    assert out == "AAAA [X]BBBB [Y]CCCC"


def test_detect_missing_opener_none_when_block_unmatchable():
    en_blocks = _blocks_of(EN_MISSING_OPENER)
    result = detect_missing_opener(en_blocks, "completely unrelated text with no code at all")
    assert result is None


def test_detect_duplicate_block_none_when_block_unmatchable():
    en_blocks = _blocks_of(EN_DUPLICATE)
    result = detect_duplicate_block(en_blocks, "completely unrelated text with no code at all")
    assert result is None
