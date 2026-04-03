"""Unit tests for scripts/ci/check-provenance-writes.py.

Coverage:
- _is_excluded: provenance.py exclusion, test file exclusion, tests/ dir exclusion
- check_file: clean file passes, re.sub violation, str.replace violation,
  literal YAML write without import violation, provenance-import exemption
- run: full integration over a synthetic scripts/ tree

All tests are deterministic — no network, synthetic filesystem via tmp_path.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loader — handle hyphenated filename
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parents[3]


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_provenance_writes",
        _REPO_ROOT / "scripts" / "ci" / "check-provenance-writes.py",
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


checker = _load_checker()


# ===========================================================================
# _is_excluded
# ===========================================================================

class TestIsExcluded:
    def _scripts_root(self, tmp_path: Path) -> Path:
        root = tmp_path / "scripts"
        root.mkdir()
        return root

    def test_provenance_py_excluded(self, tmp_path):
        root = self._scripts_root(tmp_path)
        p = root / "pipeline" / "provenance.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert checker._is_excluded(p, root) is True

    def test_test_prefix_excluded(self, tmp_path):
        root = self._scripts_root(tmp_path)
        p = root / "ci" / "test_my_check.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert checker._is_excluded(p, root) is True

    def test_test_suffix_excluded(self, tmp_path):
        root = self._scripts_root(tmp_path)
        p = root / "ci" / "my_check_test.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert checker._is_excluded(p, root) is True

    def test_tests_directory_excluded(self, tmp_path):
        root = self._scripts_root(tmp_path)
        p = root / "pipeline" / "tests" / "helper.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert checker._is_excluded(p, root) is True

    def test_normal_script_not_excluded(self, tmp_path):
        root = self._scripts_root(tmp_path)
        p = root / "ci" / "check_something.py"
        p.parent.mkdir(parents=True)
        p.touch()
        assert checker._is_excluded(p, root) is False


# ===========================================================================
# check_file — clean files
# ===========================================================================

class TestCheckFileClean:
    def _write(self, tmp_path: Path, name: str, content: str) -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_clean_file_no_violations(self, tmp_path):
        """A file that imports provenance and calls update_mechanism is clean."""
        p = self._write(tmp_path, "clean.py", (
            "import provenance\n"
            "\n"
            "def update(fp):\n"
            "    provenance.update_mechanism(fp, 'fixer')\n"
        ))
        assert checker.check_file(p) == []

    def test_from_import_provenance_is_clean(self, tmp_path):
        """from provenance import update_mechanism exempts the file."""
        p = self._write(tmp_path, "clean2.py", (
            "from provenance import update_mechanism, write_provenance\n"
            "\n"
            "def run(fp):\n"
            "    update_mechanism(fp, 'grade-writer')\n"
        ))
        assert checker.check_file(p) == []

    def test_docstring_mention_only_is_clean(self, tmp_path):
        """Mentioning last_mechanism in a docstring without a write call is fine."""
        p = self._write(tmp_path, "docs_only.py", (
            '"""This script does NOT update last_mechanism."""\n'
            "\n"
            "def noop():\n"
            "    pass\n"
        ))
        assert checker.check_file(p) == []

    def test_log_message_with_last_mechanism_no_write_is_clean(self, tmp_path):
        """A logging call that mentions last_mechanism without a file write is clean."""
        p = self._write(tmp_path, "logging_only.py", (
            "import logging\n"
            "\n"
            "def report(val):\n"
            "    logging.info('last_mechanism: %s', val)\n"
        ))
        assert checker.check_file(p) == []

    def test_provenance_import_with_yaml_literal_write_is_clean(self, tmp_path):
        """File that imports provenance AND writes last_mechanism: as literal is ok."""
        p = self._write(tmp_path, "safe_writer.py", (
            "import provenance as _prov\n"
            "\n"
            "def write(fp):\n"
            "    _prov.write_provenance(fp, {'last_mechanism': 'fixer'})\n"
            "    fp.write_text('last_mechanism: fixer\\n')\n"  # unusual but covered
        ))
        assert checker.check_file(p) == []


# ===========================================================================
# check_file — violations
# ===========================================================================

class TestCheckFileViolations:
    def _write(self, tmp_path: Path, name: str, content: str) -> Path:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_re_sub_last_mechanism_flagged(self, tmp_path):
        """re.sub on 'last_mechanism' string pattern is a violation."""
        p = self._write(tmp_path, "bad_resub.py", (
            "import re\n"
            "from pathlib import Path\n"
            "\n"
            "def patch(text):\n"
            "    return re.sub(r'last_mechanism: \\S+', 'last_mechanism: fixer', text)\n"
        ))
        violations = checker.check_file(p)
        assert len(violations) >= 1
        assert any("re.sub" in v for v in violations)

    def test_str_replace_last_mechanism_flagged(self, tmp_path):
        """str.replace on 'last_mechanism' is a violation."""
        p = self._write(tmp_path, "bad_replace.py", (
            "def patch(text):\n"
            "    return text.replace('last_mechanism: unknown', 'last_mechanism: fixer')\n"
        ))
        violations = checker.check_file(p)
        assert len(violations) >= 1
        assert any("str.replace" in v for v in violations)

    def test_literal_yaml_write_without_import_flagged(self, tmp_path):
        """Writing 'last_mechanism:' literal to a file without provenance import."""
        p = self._write(tmp_path, "bad_writer.py", (
            "from pathlib import Path\n"
            "\n"
            "def write_block(fp):\n"
            "    fp.write_text('provenance:\\n  last_mechanism: fixer\\n')\n"
        ))
        violations = checker.check_file(p)
        assert len(violations) >= 1
        assert any("last_mechanism:" in v for v in violations)

    def test_atomic_write_with_literal_without_import_flagged(self, tmp_path):
        """atomic_write with 'last_mechanism:' literal and no provenance import."""
        p = self._write(tmp_path, "bad_atomic.py", (
            "from core.fs import atomic_write\n"
            "from pathlib import Path\n"
            "\n"
            "def update(fp, text):\n"
            "    new_text = text + '  last_mechanism: fixer\\n'\n"
            "    atomic_write(fp, new_text)\n"
        ))
        violations = checker.check_file(p)
        assert len(violations) >= 1

    def test_re_sub_returns_line_number(self, tmp_path):
        """Violation messages include a line number."""
        p = self._write(tmp_path, "lined.py", (
            "# line 1\n"
            "# line 2\n"
            "import re\n"
            "text = re.sub('last_mechanism: x', 'last_mechanism: y', src)\n"
        ))
        violations = checker.check_file(p)
        assert violations
        assert "line 4" in violations[0]

    def test_multiple_violations_all_reported(self, tmp_path):
        """A file with both re.sub and str.replace violations reports both."""
        p = self._write(tmp_path, "two_bad.py", (
            "import re\n"
            "def a(t): return re.sub('last_mechanism: x', 'last_mechanism: y', t)\n"
            "def b(t): return t.replace('last_mechanism: x', 'last_mechanism: z')\n"
        ))
        violations = checker.check_file(p)
        assert len(violations) >= 2


# ===========================================================================
# Exclusion of provenance.py itself
# ===========================================================================

class TestProvenancePyExcluded:
    def test_provenance_py_is_excluded_before_check(self, tmp_path):
        """provenance.py must be excluded by _is_excluded, not merely tolerated."""
        root = tmp_path / "scripts"
        (root / "pipeline").mkdir(parents=True)
        prov = root / "pipeline" / "provenance.py"
        # Write content that would normally trigger a violation
        prov.write_text(
            "import re\n"
            "re.sub('last_mechanism: x', 'last_mechanism: y', text)\n",
            encoding="utf-8",
        )
        assert checker._is_excluded(prov, root) is True
        # Double-check: run on a tree containing only provenance.py — expect 0 violations
        result = checker.run(root)
        assert result == 0


# ===========================================================================
# run() integration
# ===========================================================================

class TestRunIntegration:
    def _make_scripts(self, tmp_path: Path) -> Path:
        root = tmp_path / "scripts"
        root.mkdir()
        return root

    def test_empty_scripts_dir_clean(self, tmp_path):
        root = self._make_scripts(tmp_path)
        assert checker.run(root) == 0

    def test_clean_file_exits_0(self, tmp_path):
        root = self._make_scripts(tmp_path)
        (root / "ci").mkdir()
        (root / "ci" / "myscript.py").write_text(
            "import provenance\nprovenance.update_mechanism(fp, 'fixer')\n",
            encoding="utf-8",
        )
        assert checker.run(root) == 0

    def test_violation_exits_1(self, tmp_path):
        root = self._make_scripts(tmp_path)
        (root / "ci").mkdir()
        (root / "ci" / "bad.py").write_text(
            "import re\n"
            "def patch(t): return re.sub('last_mechanism: x', 'last_mechanism: y', t)\n",
            encoding="utf-8",
        )
        assert checker.run(root) == 1

    def test_test_files_excluded_from_run(self, tmp_path):
        root = self._make_scripts(tmp_path)
        tests_dir = root / "tests" / "ci"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_bad.py").write_text(
            "import re\n"
            "re.sub('last_mechanism: x', '', text)\n",
            encoding="utf-8",
        )
        # Tests should be excluded — result should be clean
        assert checker.run(root) == 0

    def test_provenance_py_in_tree_does_not_trigger(self, tmp_path):
        root = self._make_scripts(tmp_path)
        (root / "pipeline").mkdir()
        (root / "pipeline" / "provenance.py").write_text(
            "import re\n"
            "_LAST_MECHANISM_RE = re.compile(r'last_mechanism: .*')\n",
            encoding="utf-8",
        )
        assert checker.run(root) == 0

    def test_nonexistent_root_returns_2(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        assert checker.run(missing) == 2
