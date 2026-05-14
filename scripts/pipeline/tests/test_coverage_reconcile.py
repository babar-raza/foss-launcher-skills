"""Compatibility test surface for coverage-reconcile parity."""

from pathlib import Path


def test_coverage_reconcile_skill_contract_exists() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    skill = repo_root / "skills" / "coverage-reconcile.md"
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    assert "Coverage Reconcile" in text
    assert "evidence.claims" in text
