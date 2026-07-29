"""Tests for check_monkeypatch_lint.py (MP-SR02)."""
from __future__ import annotations

from pathlib import Path

import pytest

import sys
import os
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))
from check_monkeypatch_lint import check_file, main, analyze_python_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# check_file — clean cases (no violations)
# ---------------------------------------------------------------------------

class TestCleanCases:
    def test_empty_file(self, tmp_path):
        p = _write(tmp_path, "test_empty.py", "")
        assert check_file(p) == []

    def test_no_monkeypatch(self, tmp_path):
        p = _write(tmp_path, "test_ok.py", """\
def test_something():
    result = my_module.run()
    assert result == 42
""")
        assert check_file(p) == []

    def test_configure_seam_is_clean(self, tmp_path):
        p = _write(tmp_path, "test_seam.py", """\
def test_uses_configure(tmp_path):
    import batch_reference as br
    br.configure(repo_root=tmp_path)
    try:
        br.run("fam", "plat")
    finally:
        br.configure()
""")
        assert check_file(p) == []

    def test_monkeypatch_on_non_guarded_name(self, tmp_path):
        """monkeypatch.setattr on a non-guarded attribute is fine."""
        p = _write(tmp_path, "test_other.py", """\
def test_ok(monkeypatch):
    monkeypatch.setattr(mod, "OTHER_CONSTANT", "value")
""")
        assert check_file(p) == []

    def test_patch_object_non_guarded(self, tmp_path):
        p = _write(tmp_path, "test_patch.py", """\
from unittest.mock import patch
def test_ok():
    with patch.object(mod, "some_method", return_value=1):
        pass
""")
        assert check_file(p) == []


# ---------------------------------------------------------------------------
# check_file — violation cases
# ---------------------------------------------------------------------------

class TestViolationDetection:
    def test_monkeypatch_setattr_module_const(self, tmp_path):
        p = _write(tmp_path, "test_bad.py", """\
def test_bad(monkeypatch):
    monkeypatch.setattr(batch_reference, "REPO_ROOT", tmp_path)
""")
        violations = check_file(p)
        assert len(violations) == 1
        assert violations[0][0] == 2
        assert "monkeypatch.setattr" in violations[0][1]

    def test_monkeypatch_setattr_string_form(self, tmp_path):
        p = _write(tmp_path, "test_bad.py", """\
def test_bad(monkeypatch):
    monkeypatch.setattr("batch_reference.KNOWLEDGE_ROOT", tmp_path)
""")
        violations = check_file(p)
        assert len(violations) == 1

    def test_patch_object_guarded(self, tmp_path):
        p = _write(tmp_path, "test_bad.py", """\
from unittest.mock import patch
def test_bad():
    with patch.object(my_mod, "CONTENT_ROOT", new=tmp_path):
        pass
""")
        violations = check_file(p)
        assert len(violations) == 1
        assert "patch.object" in violations[0][1]

    def test_direct_assignment_to_guarded(self, tmp_path):
        p = _write(tmp_path, "test_bad.py", """\
def test_bad(tmp_path):
    import session_ledger
    session_ledger._SESSION_DIR = tmp_path / "sessions"
""")
        violations = check_file(p)
        assert len(violations) == 1
        assert "direct assignment" in violations[0][1]

    def test_multiple_violations_in_one_file(self, tmp_path):
        p = _write(tmp_path, "test_bad.py", """\
def test_bad1(monkeypatch):
    monkeypatch.setattr(br, "REPO_ROOT", tmp_path)

def test_bad2(monkeypatch):
    monkeypatch.setattr(br, "KNOWLEDGE_ROOT", tmp_path / "k")
""")
        violations = check_file(p)
        assert len(violations) == 2

    def test_session_dir_guarded(self, tmp_path):
        p = _write(tmp_path, "test_bad.py", """\
def test_bad(monkeypatch):
    monkeypatch.setattr(ledger, "_SESSION_DIR", tmp_path)
""")
        violations = check_file(p)
        assert len(violations) == 1

    def test_default_cache_guarded(self, tmp_path):
        p = _write(tmp_path, "test_bad.py", """\
def test_bad(monkeypatch):
    monkeypatch.setattr(cli, "_DEFAULT_CACHE", tmp_path / "test.db")
""")
        violations = check_file(p)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# classify_target — object-chain resolution (closes the bare-attribute-name
# blind spot: monkeypatch.setattr(Path, "replace", ...) must resolve via the
# patched-object's chain, not just the string "replace", or every stdlib I/O
# mock whose method name isn't in the small literal _IO_TARGETS allowlist
# falls through to the T2-banned default.)
# ---------------------------------------------------------------------------

class TestObjectChainResolution:
    def test_pathlib_method_on_path_class_is_t3(self, tmp_path):
        p = _write(tmp_path, "test_fs.py", """\
from pathlib import Path
def test_ok(monkeypatch):
    monkeypatch.setattr(Path, "replace", lambda self, other: None)
""")
        violations = analyze_python_file(p)
        assert len(violations) == 1
        assert violations[0].tier == 3

    def test_time_sleep_via_module_attribute_chain_is_t3(self, tmp_path):
        p = _write(tmp_path, "test_fs.py", """\
def test_ok(monkeypatch):
    monkeypatch.setattr(fs.time, "sleep", lambda seconds: None)
""")
        violations = analyze_python_file(p)
        assert len(violations) == 1
        assert violations[0].tier == 3

    def test_patch_object_on_io_module_attribute_is_t3(self, tmp_path):
        p = _write(tmp_path, "test_fs.py", """\
from unittest.mock import patch
def test_ok():
    with patch.object(os.path, "exists", return_value=True):
        pass
""")
        violations = analyze_python_file(p)
        assert len(violations) == 1
        assert violations[0].tier == 3

    def test_bare_name_on_internal_module_stays_t2(self, tmp_path):
        """Same bare attribute name ('verify'), but the patched object is the
        module under test itself — must stay T2, not be swept into T3 by the
        object-chain resolution."""
        p = _write(tmp_path, "test_bad.py", """\
def test_bad(monkeypatch):
    monkeypatch.setattr(post_refresh_verify, "verify", lambda *a, **k: None)
""")
        violations = analyze_python_file(p)
        assert len(violations) == 1
        assert violations[0].tier == 2


# ---------------------------------------------------------------------------
# main() CLI — warn mode (default, exit 0 even on violations)
# ---------------------------------------------------------------------------

class TestMainCLI:
    def test_clean_file_exits_0(self, tmp_path, capsys):
        p = _write(tmp_path, "test_clean.py", "def test_ok(): pass\n")
        rc = main([str(p)])
        assert rc == 0

    def test_violation_warn_mode_exits_0(self, tmp_path, capsys):
        """Default mode: violations produce WARN output but exit 0."""
        p = _write(tmp_path, "test_bad.py", """\
def test_bad(monkeypatch):
    monkeypatch.setattr(br, "REPO_ROOT", "/tmp")
""")
        rc = main([str(p)])
        assert rc == 0
        captured = capsys.readouterr()
        assert "WARN" in captured.err

    def test_violation_strict_mode_exits_1(self, tmp_path):
        """Strict mode: violations cause exit 1."""
        p = _write(tmp_path, "test_bad.py", """\
def test_bad(monkeypatch):
    monkeypatch.setattr(br, "REPO_ROOT", "/tmp")
""")
        rc = main(["--strict", str(p)])
        assert rc == 1

    def test_no_args_exits_0(self, capsys):
        rc = main([])
        assert rc == 0
