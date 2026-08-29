"""Tests for scripts/ci/checks/check_module_consumption.py (ported 2026-08-29)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci" / "checks"))

import check_module_consumption as cmc  # noqa: E402


def test_find_module_name_strips_extension():
    assert cmc.find_module_name(Path("scripts/pipeline/lib/session_identity.py")) == "session_identity"


def test_is_test_path_detects_test_prefixed_files():
    assert cmc._is_test_path(Path("tests/test_foo.py")) is True
    assert cmc._is_test_path(Path("scripts/foo.py")) is False


def test_is_test_path_detects_tests_directory():
    assert cmc._is_test_path(Path("scripts/pipeline/tests/helper.py")) is True


def test_find_real_consumers_finds_import_statement(tmp_path):
    scan_root = tmp_path / "scripts"
    scan_root.mkdir()
    module = scan_root / "my_module.py"
    module.write_text("x = 1\n", encoding="utf-8")
    consumer = scan_root / "caller.py"
    consumer.write_text("from my_module import x\n", encoding="utf-8")

    consumers = cmc.find_real_consumers("scripts/my_module.py", scan_root=scan_root, repo_root=tmp_path)
    assert consumer in consumers


def test_find_real_consumers_excludes_test_files(tmp_path):
    scan_root = tmp_path / "scripts"
    scan_root.mkdir()
    module = scan_root / "my_module.py"
    module.write_text("x = 1\n", encoding="utf-8")
    test_file = scan_root / "test_my_module.py"
    test_file.write_text("import my_module\n", encoding="utf-8")

    consumers = cmc.find_real_consumers("scripts/my_module.py", scan_root=scan_root, repo_root=tmp_path)
    assert consumers == []


def test_find_real_consumers_excludes_the_module_itself(tmp_path):
    scan_root = tmp_path / "scripts"
    scan_root.mkdir()
    module = scan_root / "my_module.py"
    module.write_text("# my_module self-reference in a comment\n", encoding="utf-8")

    consumers = cmc.find_real_consumers("scripts/my_module.py", scan_root=scan_root, repo_root=tmp_path)
    assert consumers == []


def test_find_real_consumers_returns_empty_when_no_consumer(tmp_path):
    scan_root = tmp_path / "scripts"
    scan_root.mkdir()
    module = scan_root / "orphan_module.py"
    module.write_text("x = 1\n", encoding="utf-8")
    unrelated = scan_root / "other.py"
    unrelated.write_text("y = 2\n", encoding="utf-8")

    consumers = cmc.find_real_consumers("scripts/orphan_module.py", scan_root=scan_root, repo_root=tmp_path)
    assert consumers == []


def test_main_exit_code_2_for_missing_module(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cmc, "_REPO_ROOT", tmp_path)
    code = cmc.main(["--module", "scripts/does_not_exist.py"])
    assert code == 2


def test_session_identity_has_a_real_consumer_in_this_repo():
    """Regression proof for the actual reason this check was ported: it
    must positively confirm session_identity.py (ported alongside it) has a
    real consumer, not just exercise the mechanism on synthetic fixtures."""
    consumers = cmc.find_real_consumers("scripts/pipeline/lib/session_identity.py")
    names = {c.name for c in consumers}
    assert "session_ledger.py" in names
