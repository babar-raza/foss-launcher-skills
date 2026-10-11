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


def test_section_shape_enforcer_resolves_to_a_real_check(tmp_path):
    # TC-01 (readme-refresh-at-a-glance-retention-hardening-2026-09-02): check 4.
    contract = {
        **_GOOD_CONTRACT,
        "section_shapes": {"invariants": [
            {"section": "At a Glance", "invariant": "one fence", "enforced_by": "check_one"},
        ]},
    }
    root = _fixture_repo(tmp_path, contract=contract)
    assert parity.run(repo_root=root) == []


def test_section_shape_enforcer_missing_from_code_is_reported(tmp_path):
    contract = {
        **_GOOD_CONTRACT,
        "section_shapes": {"invariants": [
            {"section": "At a Glance", "invariant": "one fence", "enforced_by": "check_renamed_away"},
        ]},
    }
    root = _fixture_repo(tmp_path, contract=contract)
    violations = parity.run(repo_root=root)
    assert any("section_shapes drift" in v and "check_renamed_away" in v for v in violations)


def test_section_shape_enforcer_must_be_a_check_function_name(tmp_path):
    contract = {
        **_GOOD_CONTRACT,
        "section_shapes": {"invariants": [
            {"section": "License", "invariant": "fixed sentence", "enforced_by": "documented in prose only"},
        ]},
    }
    root = _fixture_repo(tmp_path, contract=contract)
    violations = parity.run(repo_root=root)
    assert any("not a check_* function name" in v for v in violations)


def test_contract_without_section_shapes_is_still_clean(tmp_path):
    # schema_version 1 contracts (no section_shapes) stay valid -- check 4 is additive.
    root = _fixture_repo(tmp_path, contract=_GOOD_CONTRACT)
    assert parity.contract_section_shape_enforcers(_GOOD_CONTRACT) == []
    assert parity.run(repo_root=root) == []


def test_real_repo_is_currently_clean():
    """The real, live check against this repo's own actual files -- proves the fix that was
    applied (registry.yaml 105->109) actually landed, not just the synthetic fixture tests."""
    assert parity.run() == []


def test_real_repo_contract_declares_at_a_glance_shape_with_live_enforcer():
    """TC-01: the live contract must carry the At-a-Glance section-body invariant and its
    enforcer must be a real function -- the invariant that was missing for 30 products."""
    contract = json.loads(parity._CONTRACT_PATH.read_text(encoding="utf-8"))
    pairs = dict(parity.contract_section_shape_enforcers(contract))
    assert pairs.get("At a Glance") == "check_at_a_glance_section_shape"
    assert "check_at_a_glance_section_shape" in (parity.real_check_function_names() or set())
