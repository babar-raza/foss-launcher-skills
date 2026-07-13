"""Tests for scripts/ci/checks/check_frontmatter_yaml.py.

Coverage:
  Unit — check_file(): valid frontmatter, folded scalar, truncated-quote
          corruption (F1 + wave-3 hint), missing terminator (F3),
          non-mapping frontmatter (F2), no-frontmatter skip
  Unit — find_unterminated_quote_line(): signature detection
  Integration — CLI staged-file mode, scan mode, exit codes
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "ci" / "checks" / "check_frontmatter_yaml.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))
from check_frontmatter_yaml import (  # noqa: E402
    check_file,
    find_unterminated_quote_line,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SIMPLE = """---
title: Sample page
description: 'A short description: with a colon inside quotes.'
weight: 10
---

Body text.
"""

VALID_FOLDED = """---
title: Sample page
description: >-
    Erste Zeile der Beschreibung,
    zweite Zeile der Beschreibung.
date: '2026-03-29'
---

Body text.
"""

VALID_MULTILINE_QUOTED = """---
title: Sample page
description: 'Overview of all major capabilities in Aspose.Cells FOSS: workbook
  I/O, cell data, styling, and worksheet management.'
weight: 10
---

Body text.
"""

# The wave-3 corruption: first line of a multi-line quoted scalar kept,
# continuation lines dropped, quote never closed until a later quoted value.
CORRUPT_TRUNCATED_QUOTE = """---
title: Sample page
description: 'Overview of all major capabilities in Aspose.Cells FOSS: workbook
weight: 10
provenance:
    content_created_at: '2026-04-07'
    auto_updatable: true
---

Body text.
"""

# The kb working-tree variant: '>-' replaced by unterminated English line,
# translated continuation line retained.
CORRUPT_KB_VARIANT = """---
title: Beispielseite
description: 'Learn how to export 3D scenes to STL from Python via Scene.save
    Erfahren Sie, wie man 3D-Szenen aus Python exportiert.
date: '2026-03-29'
lastmod: '2026-03-29'
---

Body text.
"""

NO_TERMINATOR = """---
title: Sample page
description: broken
"""

NON_MAPPING = """---
- just
- a
- list
---

Body text.
"""

NO_FRONTMATTER = "# Just a heading\n\nBody text.\n"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER)] + list(args),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


# ===========================================================================
# Unit tests — check_file()
# ===========================================================================

class TestCheckFileValid:
    def test_simple_frontmatter_passes(self, tmp_path):
        assert check_file(_write(tmp_path, "a.md", VALID_SIMPLE)) == []

    def test_folded_scalar_passes(self, tmp_path):
        assert check_file(_write(tmp_path, "b.md", VALID_FOLDED)) == []

    def test_multiline_quoted_scalar_passes(self, tmp_path):
        assert check_file(_write(tmp_path, "c.md", VALID_MULTILINE_QUOTED)) == []

    def test_no_frontmatter_skipped(self, tmp_path):
        assert check_file(_write(tmp_path, "d.md", NO_FRONTMATTER)) == []


class TestCheckFileCorrupt:
    def test_truncated_quote_fails_f1_with_hint(self, tmp_path):
        failures = check_file(_write(tmp_path, "e.md", CORRUPT_TRUNCATED_QUOTE))
        assert failures
        assert failures[0].startswith("F1 FAIL")
        assert any("wave-3" in msg for msg in failures)

    def test_kb_variant_fails_f1_with_hint(self, tmp_path):
        failures = check_file(_write(tmp_path, "f.md", CORRUPT_KB_VARIANT))
        assert failures
        assert failures[0].startswith("F1 FAIL")
        assert any("wave-3" in msg for msg in failures)

    def test_missing_terminator_fails_f3(self, tmp_path):
        failures = check_file(_write(tmp_path, "g.md", NO_TERMINATOR))
        assert len(failures) == 1
        assert failures[0].startswith("F3 FAIL")

    def test_non_mapping_fails_f2(self, tmp_path):
        failures = check_file(_write(tmp_path, "h.md", NON_MAPPING))
        assert len(failures) == 1
        assert failures[0].startswith("F2 FAIL")


# ===========================================================================
# Unit tests — find_unterminated_quote_line()
# ===========================================================================

class TestFindUnterminatedQuoteLine:
    def test_detects_truncated_description(self):
        fm = CORRUPT_TRUNCATED_QUOTE.split("---")[1]
        line = find_unterminated_quote_line(fm)
        assert line is not None
        assert "description:" in fm.splitlines()[line - 1]

    def test_valid_closed_scalar_not_flagged(self):
        fm = VALID_SIMPLE.split("---")[1]
        assert find_unterminated_quote_line(fm) is None

    def test_valid_multiline_quoted_not_flagged(self):
        # Quote closes before the next top-level key — legitimate YAML.
        fm = VALID_MULTILINE_QUOTED.split("---")[1]
        assert find_unterminated_quote_line(fm) is None

    def test_escaped_quotes_not_flagged(self):
        fm = "\ntitle: x\ndescription: 'it''s fine'\nweight: 1\n"
        assert find_unterminated_quote_line(fm) is None


# ===========================================================================
# Integration tests — CLI
# ===========================================================================

class TestCli:
    def test_all_valid_exit_0(self, tmp_path):
        a = _write(tmp_path, "a.md", VALID_SIMPLE)
        b = _write(tmp_path, "b.md", VALID_FOLDED)
        result = _run(str(a), str(b))
        assert result.returncode == 0
        assert "2 file(s) OK" in result.stdout

    def test_corrupt_file_exit_1(self, tmp_path):
        bad = _write(tmp_path, "bad.md", CORRUPT_TRUNCATED_QUOTE)
        result = _run(str(bad))
        assert result.returncode == 1
        assert "F1 FAIL" in result.stdout

    def test_mixed_reports_only_bad(self, tmp_path):
        good = _write(tmp_path, "good.md", VALID_SIMPLE)
        bad = _write(tmp_path, "bad.md", CORRUPT_KB_VARIANT)
        result = _run(str(good), str(bad))
        assert result.returncode == 1
        assert "bad.md" in result.stdout
        assert "good.md" not in result.stdout

    def test_missing_file_ignored(self, tmp_path):
        good = _write(tmp_path, "good.md", VALID_SIMPLE)
        result = _run(str(good), str(tmp_path / "gone.md"))
        assert result.returncode == 0

    def test_non_md_arg_skipped(self, tmp_path):
        bad_txt = _write(tmp_path, "notes.txt", CORRUPT_TRUNCATED_QUOTE)
        result = _run(str(bad_txt))
        # .txt is filtered out; nothing to check → usage error exit 2
        assert result.returncode in (0, 2)

    def test_no_args_exit_2(self):
        result = _run()
        assert result.returncode == 2

    def test_scan_mode(self, tmp_path):
        root = tmp_path / "content"
        sub = root / "docs.aspose.org" / "bg" / "cells" / "net"
        sub.mkdir(parents=True)
        (sub / "ok.md").write_text(VALID_FOLDED, encoding="utf-8")
        (sub / "bad.md").write_text(CORRUPT_TRUNCATED_QUOTE, encoding="utf-8")
        result = _run("--scan", "--root", str(root))
        assert result.returncode == 1
        assert "bad.md" in result.stdout

    def test_scan_missing_root_exit_2(self, tmp_path):
        result = _run("--scan", "--root", str(tmp_path / "nope"))
        assert result.returncode == 2
