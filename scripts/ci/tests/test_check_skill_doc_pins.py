"""Tests for check_skill_doc_pins.py (D-8a, MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH
TC-MT040-47).

Coverage:
- no pins at all -> 0 findings
- matching pin (module.ATTR) -> 0 findings
- mismatching pin (module.ATTR) -> 1 mismatch finding
- matching pin (module.len(ATTR)) -> 0 findings, proving the len() form works
  against a real list attribute
- mismatching pin (module.len(ATTR)) -> 1 mismatch finding
- unresolvable module -> 1 unresolvable_pin finding (never a crash)
- unresolvable attribute -> 1 unresolvable_pin finding
- pin with no integer literal on the same line -> 1 no_stated_value finding
- live proof against the REAL site_planner.TROUBLE_HOWTO_MIN and
  launch_gate.py's real len(_ALL_GATES) == 16 (the two concrete drifts this
  card's own docstring cites)
- main()'s exit code reflects findings presence
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_CHECKS_DIR = Path(__file__).resolve().parents[1] / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))

import check_skill_doc_pins as pins


@pytest.fixture(autouse=True)
def _reset_pins():
    yield
    pins.configure()


def _write_fixture_module(tmp_path, subdir, name, content):
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.py").write_text(content, encoding="utf-8")


def _write_skill_doc(tmp_path, name, content):
    d = tmp_path / "skills"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(content, encoding="utf-8")


class TestNoPins:
    def test_doc_with_no_pins_has_no_findings(self, tmp_path):
        _write_skill_doc(tmp_path, "example", "# A skill doc\n\nSome prose with no pins at all.\n")
        pins.configure(repo_root=tmp_path)
        assert pins.check_all() == []


class TestBareAttrPin:
    def test_matching_pin_has_no_findings(self, tmp_path):
        _write_fixture_module(tmp_path, "scripts/pipeline/lib", "fake_module", "MIN_COUNT = 3\n")
        _write_skill_doc(
            tmp_path, "example",
            "at least 3 items required <!-- pin: fake_module.MIN_COUNT -->\n",
        )
        pins.configure(repo_root=tmp_path)
        assert pins.check_all() == []

    def test_mismatching_pin_is_a_finding(self, tmp_path):
        _write_fixture_module(tmp_path, "scripts/pipeline/lib", "fake_module", "MIN_COUNT = 3\n")
        _write_skill_doc(
            tmp_path, "example",
            "at least 6 items required <!-- pin: fake_module.MIN_COUNT -->\n",
        )
        pins.configure(repo_root=tmp_path)
        findings = pins.check_all()
        assert len(findings) == 1
        assert findings[0]["kind"] == "mismatch"
        assert "6" in findings[0]["detail"] and "3" in findings[0]["detail"]


class TestLenAttrPin:
    def test_matching_len_pin_has_no_findings(self, tmp_path):
        _write_fixture_module(tmp_path, "scripts/pipeline/commands/launch", "fake_gates",
                               "_ALL_GATES = ['a', 'b', 'c', 'd']\n")
        _write_skill_doc(
            tmp_path, "example",
            "runs 4 automated gates <!-- pin: fake_gates.len(_ALL_GATES) -->\n",
        )
        pins.configure(repo_root=tmp_path)
        assert pins.check_all() == []

    def test_mismatching_len_pin_is_a_finding(self, tmp_path):
        _write_fixture_module(tmp_path, "scripts/pipeline/commands/launch", "fake_gates",
                               "_ALL_GATES = ['a', 'b', 'c', 'd']\n")
        _write_skill_doc(
            tmp_path, "example",
            "runs 15 automated gates <!-- pin: fake_gates.len(_ALL_GATES) -->\n",
        )
        pins.configure(repo_root=tmp_path)
        findings = pins.check_all()
        assert len(findings) == 1
        assert findings[0]["kind"] == "mismatch"
        assert "15" in findings[0]["detail"] and "4" in findings[0]["detail"]


class TestUnresolvable:
    def test_unresolvable_module_is_a_finding_not_a_crash(self, tmp_path):
        _write_skill_doc(
            tmp_path, "example",
            "at least 3 items <!-- pin: totally_nonexistent_module.MIN_COUNT -->\n",
        )
        pins.configure(repo_root=tmp_path)
        findings = pins.check_all()
        assert len(findings) == 1
        assert findings[0]["kind"] == "unresolvable_pin"

    def test_unresolvable_attribute_is_a_finding_not_a_crash(self, tmp_path):
        _write_fixture_module(tmp_path, "scripts/pipeline/lib", "fake_module", "MIN_COUNT = 3\n")
        _write_skill_doc(
            tmp_path, "example",
            "at least 3 items <!-- pin: fake_module.NONEXISTENT_ATTR -->\n",
        )
        pins.configure(repo_root=tmp_path)
        findings = pins.check_all()
        assert len(findings) == 1
        assert findings[0]["kind"] == "unresolvable_pin"

    def test_no_integer_on_line_is_a_finding(self, tmp_path):
        _write_fixture_module(tmp_path, "scripts/pipeline/lib", "fake_module", "MIN_COUNT = 3\n")
        _write_skill_doc(
            tmp_path, "example",
            "several items required <!-- pin: fake_module.MIN_COUNT -->\n",
        )
        pins.configure(repo_root=tmp_path)
        findings = pins.check_all()
        assert len(findings) == 1
        assert findings[0]["kind"] == "no_stated_value"

    def test_non_int_attribute_is_a_finding_not_a_crash(self, tmp_path):
        _write_fixture_module(tmp_path, "scripts/pipeline/lib", "fake_module", 'MIN_COUNT = "three"\n')
        _write_skill_doc(
            tmp_path, "example",
            "at least 3 items <!-- pin: fake_module.MIN_COUNT -->\n",
        )
        pins.configure(repo_root=tmp_path)
        findings = pins.check_all()
        assert len(findings) == 1
        assert findings[0]["kind"] == "unresolvable_pin"


class TestLiveRealCode:
    """Live proof against the two REAL drift instances this card's own
    docstring cites -- not synthetic fixtures."""

    def test_real_trouble_howto_min_is_pinnable_and_correct(self, tmp_path):
        _write_skill_doc(
            tmp_path, "example",
            "a troubleshooting page is generated once a product has 3 or more "
            "how-to articles <!-- pin: site_planner.TROUBLE_HOWTO_MIN -->\n",
        )
        pins.configure(repo_root=Path(__file__).resolve().parents[3], skills_dir=tmp_path / "skills")
        findings = pins.check_all()
        assert findings == []

    def test_real_trouble_howto_min_stale_six_is_caught(self, tmp_path):
        """Reproduces the EXACT real drift found live this session: the old
        doc text said 6, the real code says 3."""
        _write_skill_doc(
            tmp_path, "example",
            "a troubleshooting page is generated once a product has 6 or more "
            "how-to articles <!-- pin: site_planner.TROUBLE_HOWTO_MIN -->\n",
        )
        pins.configure(repo_root=Path(__file__).resolve().parents[3], skills_dir=tmp_path / "skills")
        findings = pins.check_all()
        assert len(findings) == 1
        assert findings[0]["kind"] == "mismatch"

    def test_real_launch_gate_count_is_pinnable_and_correct(self, tmp_path):
        _write_skill_doc(
            tmp_path, "example",
            "launch_gate.py runs 16 automated gates <!-- pin: launch_gate.len(_ALL_GATES) -->\n",
        )
        pins.configure(repo_root=Path(__file__).resolve().parents[3], skills_dir=tmp_path / "skills")
        findings = pins.check_all()
        assert findings == []

    def test_real_launch_gate_count_stale_fifteen_is_caught(self, tmp_path):
        """Reproduces the EXACT real drift found live this session:
        skills/launch-product.md said 15 gates; the real code has 16."""
        _write_skill_doc(
            tmp_path, "example",
            "launch_gate.py runs 15 automated gates <!-- pin: launch_gate.len(_ALL_GATES) -->\n",
        )
        pins.configure(repo_root=Path(__file__).resolve().parents[3], skills_dir=tmp_path / "skills")
        findings = pins.check_all()
        assert len(findings) == 1
        assert findings[0]["kind"] == "mismatch"


class TestMainExitCode:
    def test_exit_0_when_no_findings(self, tmp_path, monkeypatch):
        _write_skill_doc(tmp_path, "example", "no pins here\n")
        pins.configure(repo_root=tmp_path)
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["check_skill_doc_pins.py"])
        with pytest.raises(SystemExit) as exc:
            pins.main()
        assert exc.value.code == 0

    def test_exit_1_when_findings_exist(self, tmp_path, monkeypatch):
        _write_fixture_module(tmp_path, "scripts/pipeline/lib", "fake_module", "MIN_COUNT = 3\n")
        _write_skill_doc(
            tmp_path, "example",
            "at least 6 items <!-- pin: fake_module.MIN_COUNT -->\n",
        )
        pins.configure(repo_root=tmp_path)
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["check_skill_doc_pins.py"])
        with pytest.raises(SystemExit) as exc:
            pins.main()
        assert exc.value.code == 1
