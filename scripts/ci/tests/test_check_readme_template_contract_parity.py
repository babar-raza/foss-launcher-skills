"""Tests for check_readme_template_contract_parity.py (TC-34,
readme-refresh-trackb-and-followon-2026-09-01, SW-F fix)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from checks import check_readme_template_contract_parity as parity  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    yield
    parity.configure()


_REAL_CHECKS_SNIPPET = (
    '_REQUIRED_SECTIONS = [\n'
    '    "At a Glance",\n'
    '    "Key Capabilities",\n'
    ']\n'
    '\n'
    'def check_one(x):\n'
    '    pass\n'
    '\n'
    'def check_two(x):\n'
    '    pass\n'
)


def _fixture_repo(tmp_path: Path, *, contract: dict, checks_src: str = _REAL_CHECKS_SNIPPET,
                   registry_count: "int | None" = 2) -> Path:
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "readme_template_contract.json").write_text(
        json.dumps(contract), encoding="utf-8",
    )
    checks_dir = tmp_path / "scripts" / "pipeline" / "commands" / "foss"
    checks_dir.mkdir(parents=True)
    (checks_dir / "readme_refresh_checks.py").write_text(checks_src, encoding="utf-8")
    registry_dir = tmp_path / "scripts" / "pipeline" / "config"
    registry_dir.mkdir(parents=True)
    registry_text = (
        f'    change_impact: "{registry_count} deterministic check_* functions blah blah"\n'
        if registry_count is not None else '    change_impact: "no count phrase here"\n'
    )
    (registry_dir / "registry.yaml").write_text(registry_text, encoding="utf-8")
    return tmp_path


_GOOD_CONTRACT = {
    "required_sections": ["At a Glance", "Key Capabilities"],
    "check_function_count": {"value": 2},
}


def test_clean_repo_has_zero_violations(tmp_path):
    root = _fixture_repo(tmp_path, contract=_GOOD_CONTRACT)
    assert parity.run(repo_root=root) == []


def test_required_sections_drift_is_reported(tmp_path):
    bad_contract = {**_GOOD_CONTRACT, "required_sections": ["At a Glance", "Wrong Section"]}
    root = _fixture_repo(tmp_path, contract=bad_contract)
    violations = parity.run(repo_root=root)
    assert any("required_sections drift" in v for v in violations)


def test_check_function_count_drift_is_reported(tmp_path):
    bad_contract = {**_GOOD_CONTRACT, "check_function_count": {"value": 99}}
    root = _fixture_repo(tmp_path, contract=bad_contract)
    violations = parity.run(repo_root=root)
    assert any("check_function_count drift" in v for v in violations)


def test_registry_yaml_count_drift_is_reported(tmp_path):
    root = _fixture_repo(tmp_path, contract=_GOOD_CONTRACT, registry_count=105)
    violations = parity.run(repo_root=root)
    assert any("registry.yaml drift" in v for v in violations)


def test_registry_yaml_missing_count_phrase_is_reported(tmp_path):
    root = _fixture_repo(tmp_path, contract=_GOOD_CONTRACT, registry_count=None)
    violations = parity.run(repo_root=root)
    assert any("no longer contains" in v for v in violations)


def test_missing_contract_file_is_reported(tmp_path):
    (tmp_path / "data").mkdir(parents=True)
    violations = parity.run(repo_root=tmp_path)
    assert any("not found" in v for v in violations)


def test_malformed_contract_json_is_reported(tmp_path):
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "readme_template_contract.json").write_text("{not json", encoding="utf-8")
    violations = parity.run(repo_root=tmp_path)
    assert any("not valid JSON" in v for v in violations)


def test_main_exits_nonzero_on_violation(tmp_path, capsys):
    bad_contract = {**_GOOD_CONTRACT, "check_function_count": {"value": 99}}
    root = _fixture_repo(tmp_path, contract=bad_contract)
    code = parity.main(["--repo-root", str(root)])
    assert code == 1
    out = capsys.readouterr().out
    assert "violation" in out


def test_main_exits_zero_when_clean(tmp_path, capsys):
    root = _fixture_repo(tmp_path, contract=_GOOD_CONTRACT)
    code = parity.main(["--repo-root", str(root)])
    assert code == 0
    assert "OK" in capsys.readouterr().out


def test_real_repo_is_currently_clean():
    """The real, live check against this repo's own actual files -- proves the fix that was
    applied (registry.yaml 105->109) actually landed, not just the synthetic fixture tests."""
    assert parity.run() == []
