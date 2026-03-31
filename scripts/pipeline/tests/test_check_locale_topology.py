"""Unit tests for check_locale_topology.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from check_locale_topology import extract_h2s, check_locale, check_all, main  # noqa: E402


def _tmp_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


ENGLISH_SOURCE = """\
---
title: Export Formats
grade: A
---

## Save to XLSX and CSV

Example content.

## Save to Markdown

More content.

## See Also

Links.
"""

MATCHING_LOCALE = """\
---
title: Exportformate
grade: A
---

## Speichern als XLSX und CSV

Beispiel.

## Als Markdown speichern

Mehr Inhalt.

## Siehe auch

Links.
"""

MISSING_H2_LOCALE = """\
---
title: Missing section
---

## Save to XLSX and CSV

Content.

## See Also

Links.
"""

EXTRA_H2_LOCALE = """\
---
title: Extra section
---

## Save to XLSX and CSV

Content.

## Save to Markdown

Content.

## Bonus Section

Extra.

## See Also

Links.
"""

EMPTY_FILE = """\
---
title: Empty
---
"""

NO_FRONTMATTER = """\
## Save to XLSX and CSV

Content.

## Save to Markdown

Content.

## See Also

Links.
"""


class TestExtractH2s:
    def test_extracts_h2s_from_body(self):
        p = _tmp_md(ENGLISH_SOURCE)
        try:
            h2s = extract_h2s(p)
            assert h2s == ["Save to XLSX and CSV", "Save to Markdown", "See Also"]
        finally:
            p.unlink(missing_ok=True)

    def test_ignores_h3_and_deeper(self):
        content = "---\ntitle: X\n---\n## Top\n### Sub\n#### Deep\n## Second\n"
        p = _tmp_md(content)
        try:
            h2s = extract_h2s(p)
            assert h2s == ["Top", "Second"]
        finally:
            p.unlink(missing_ok=True)

    def test_no_frontmatter_still_works(self):
        p = _tmp_md(NO_FRONTMATTER)
        try:
            h2s = extract_h2s(p)
            assert h2s == ["Save to XLSX and CSV", "Save to Markdown", "See Also"]
        finally:
            p.unlink(missing_ok=True)

    def test_empty_body_returns_empty_list(self):
        p = _tmp_md(EMPTY_FILE)
        try:
            assert extract_h2s(p) == []
        finally:
            p.unlink(missing_ok=True)


class TestCheckLocale:
    def test_matching_topology_returns_none(self):
        src = _tmp_md(ENGLISH_SOURCE)
        loc = _tmp_md(MATCHING_LOCALE)
        try:
            assert check_locale(src, loc) is None
        finally:
            src.unlink(missing_ok=True)
            loc.unlink(missing_ok=True)

    def test_missing_h2_returns_mismatch(self):
        src = _tmp_md(ENGLISH_SOURCE)
        loc = _tmp_md(MISSING_H2_LOCALE)
        try:
            result = check_locale(src, loc)
            assert result is not None
            assert result["check"] == "h2_count_mismatch"
            assert "source has 3 H2(s)" in result["detail"]
            assert "locale has 2 H2(s)" in result["detail"]
        finally:
            src.unlink(missing_ok=True)
            loc.unlink(missing_ok=True)

    def test_extra_h2_returns_mismatch(self):
        src = _tmp_md(ENGLISH_SOURCE)
        loc = _tmp_md(EXTRA_H2_LOCALE)
        try:
            result = check_locale(src, loc)
            assert result is not None
            assert result["check"] == "h2_count_mismatch"
            assert "locale has 4 H2(s)" in result["detail"]
        finally:
            src.unlink(missing_ok=True)
            loc.unlink(missing_ok=True)

    def test_empty_locale_returns_mismatch(self):
        src = _tmp_md(ENGLISH_SOURCE)
        loc = _tmp_md(EMPTY_FILE)
        try:
            result = check_locale(src, loc)
            assert result is not None
            assert "locale has 0 H2(s)" in result["detail"]
        finally:
            src.unlink(missing_ok=True)
            loc.unlink(missing_ok=True)

    def test_source_only_file_no_mismatch_with_itself(self):
        src = _tmp_md(ENGLISH_SOURCE)
        try:
            assert check_locale(src, src) is None
        finally:
            src.unlink(missing_ok=True)


class TestCLI:
    def test_matching_locale_exits_0(self):
        src = _tmp_md(ENGLISH_SOURCE)
        loc = _tmp_md(MATCHING_LOCALE)
        try:
            assert main(["--source", str(src), "--locales", str(loc)]) == 0
        finally:
            src.unlink(missing_ok=True)
            loc.unlink(missing_ok=True)

    def test_missing_h2_exits_1(self):
        src = _tmp_md(ENGLISH_SOURCE)
        loc = _tmp_md(MISSING_H2_LOCALE)
        try:
            assert main(["--source", str(src), "--locales", str(loc)]) == 1
        finally:
            src.unlink(missing_ok=True)
            loc.unlink(missing_ok=True)

    def test_mixed_pass_fail_exits_1(self):
        src = _tmp_md(ENGLISH_SOURCE)
        good = _tmp_md(MATCHING_LOCALE)
        bad = _tmp_md(MISSING_H2_LOCALE)
        try:
            assert main(["--source", str(src), "--locales", str(good), str(bad)]) == 1
        finally:
            src.unlink(missing_ok=True)
            good.unlink(missing_ok=True)
            bad.unlink(missing_ok=True)

    def test_json_output_shape(self, capsys):
        import json as _json
        src = _tmp_md(ENGLISH_SOURCE)
        loc = _tmp_md(MATCHING_LOCALE)
        try:
            main(["--source", str(src), "--locales", str(loc), "--json"])
            data = _json.loads(capsys.readouterr().out)
            assert "source_h2_count" in data
            assert data["source_h2_count"] == 3
            assert data["mismatches"] == []
            assert data["locales_checked"] == 1
        finally:
            src.unlink(missing_ok=True)
            loc.unlink(missing_ok=True)
