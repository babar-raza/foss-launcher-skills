"""Tests for check_module_consumption.py (backlog G-48, MT019 follow-up).

Uses a synthetic scan_root (not the real repo) for the core find_real_consumers
tests, so this test suite's correctness never depends on the real repo's own
current contents. A couple of sanity-check tests do run against the REAL repo,
against taskcard_store.py and master_plan_index.py specifically -- both of
which this session gave real, non-test consumers to as part of closing the
exact gap this check exists to catch -- to prove the check reports clean on
files it should.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
_REPO_ROOT = _HERE.parent.parent

from checks import check_module_consumption as cmc  # noqa: E402


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# find_real_consumers -- synthetic repo tree
# ---------------------------------------------------------------------------

def test_no_consumer_found_when_only_tests_reference_it(tmp_path):
    _write(tmp_path, "lib/lonely.py", "def do_thing():\n    pass\n")
    _write(tmp_path, "tests/test_lonely.py", "import lonely\n\nlonely.do_thing()\n")

    consumers = cmc.find_real_consumers("lib/lonely.py", scan_root=tmp_path, repo_root=tmp_path)

    assert consumers == []


def test_finds_a_real_import_consumer(tmp_path):
    _write(tmp_path, "lib/helper.py", "def do_thing():\n    pass\n")
    _write(tmp_path, "cli/runner.py", "import helper\n\nhelper.do_thing()\n")

    consumers = cmc.find_real_consumers("lib/helper.py", scan_root=tmp_path, repo_root=tmp_path)

    assert len(consumers) == 1
    assert consumers[0].name == "runner.py"


def test_finds_a_from_import_consumer(tmp_path):
    _write(tmp_path, "lib/helper.py", "def do_thing():\n    pass\n")
    _write(tmp_path, "cli/runner.py", "from lib.helper import do_thing\n\ndo_thing()\n")

    consumers = cmc.find_real_consumers("lib/helper.py", scan_root=tmp_path, repo_root=tmp_path)

    assert len(consumers) == 1


def test_ignores_the_modules_own_file(tmp_path):
    _write(tmp_path, "lib/helper.py", "import helper\n\n# self-reference only\n")

    consumers = cmc.find_real_consumers("lib/helper.py", scan_root=tmp_path, repo_root=tmp_path)

    assert consumers == []


def test_ignores_files_under_a_tests_directory(tmp_path):
    _write(tmp_path, "lib/helper.py", "def do_thing():\n    pass\n")
    _write(tmp_path, "some/tests/fixture_helper.py", "import helper\n")

    consumers = cmc.find_real_consumers("lib/helper.py", scan_root=tmp_path, repo_root=tmp_path)

    assert consumers == []


def test_ignores_test_prefixed_files_outside_a_tests_dir(tmp_path):
    _write(tmp_path, "lib/helper.py", "def do_thing():\n    pass\n")
    _write(tmp_path, "cli/test_helper_smoke.py", "import helper\n")

    consumers = cmc.find_real_consumers("lib/helper.py", scan_root=tmp_path, repo_root=tmp_path)

    assert consumers == []


def test_does_not_false_positive_on_unrelated_substring(tmp_path):
    _write(tmp_path, "lib/run.py", "def do_thing():\n    pass\n")
    _write(tmp_path, "cli/runner.py", "import runner_utils\n\nrunner_utils.execute()\n")

    consumers = cmc.find_real_consumers("lib/run.py", scan_root=tmp_path, repo_root=tmp_path)

    assert consumers == []


def test_multiple_real_consumers_all_found(tmp_path):
    _write(tmp_path, "lib/helper.py", "def do_thing():\n    pass\n")
    _write(tmp_path, "cli/a.py", "import helper\n")
    _write(tmp_path, "cli/b.py", "from lib.helper import do_thing\n")

    consumers = cmc.find_real_consumers("lib/helper.py", scan_root=tmp_path, repo_root=tmp_path)

    assert {c.name for c in consumers} == {"a.py", "b.py"}


# ---------------------------------------------------------------------------
# CLI / exit codes
# ---------------------------------------------------------------------------

def test_main_exits_2_for_missing_module(tmp_path, monkeypatch):
    monkeypatch.setattr(cmc, "_REPO_ROOT", tmp_path)
    rc = cmc.main(["--module", "does/not/exist.py"])
    assert rc == 2


def test_main_exits_1_when_no_consumer_found(tmp_path, monkeypatch):
    monkeypatch.setattr(cmc, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cmc, "_SCAN_ROOT", tmp_path)
    _write(tmp_path, "lonely.py", "pass\n")

    rc = cmc.main(["--module", "lonely.py"])
    assert rc == 1


def test_main_exits_0_when_consumer_found(tmp_path, monkeypatch):
    monkeypatch.setattr(cmc, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cmc, "_SCAN_ROOT", tmp_path)
    _write(tmp_path, "helper.py", "pass\n")
    _write(tmp_path, "caller.py", "import helper\n")

    rc = cmc.main(["--module", "helper.py"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Real-repo sanity checks -- proving the actual gap this check exists for is
# now closed for the two modules it was found on.
# ---------------------------------------------------------------------------

def test_real_repo_taskcard_store_has_a_real_consumer():
    consumers = cmc.find_real_consumers("scripts/pipeline/lib/taskcard_store.py")
    assert consumers, "taskcard_store.py should have a real consumer (git_plumb_commit.py / skill_run_manager usage this session)"


def test_real_repo_master_plan_index_has_a_real_consumer():
    consumers = cmc.find_real_consumers("scripts/pipeline/lib/master_plan_index.py")
    assert consumers, "master_plan_index.py should have a real consumer after this session's own dogfood use"
