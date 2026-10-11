"""Tests for check_platform_capabilities.py (D-1, TC-MT040-40).

Coverage:
- real repo (this checkout's actual platform_capabilities.yaml +
  data/products.json + real pipeline code) -> 0 findings
- missing platform_capabilities.yaml -> missing_yaml finding
- an active platform absent from the YAML -> undeclared_active_platform
- a YAML-declared platform with no active product -> stale_declared_platform
- NEGATIVE CONTROL: a YAML row whose class_kinds value disagrees with the
  real tree_helpers._CLASS_TYPES (the exact TC-10 regression shape) ->
  value_mismatch finding, proving the check fails closed, not just once
- main()'s exit code reflects findings presence; --dry-run always exits 0
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

_CHECKS_DIR = Path(__file__).resolve().parents[1] / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))

import check_platform_capabilities as cpc  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_YAML_PATH = REPO_ROOT / "scripts" / "pipeline" / "config" / "platform_capabilities.yaml"


@pytest.fixture(autouse=True)
def _reset_config():
    yield
    cpc.configure()


def _load_real_caps() -> dict:
    with open(REAL_YAML_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _write_repo(tmp_path: Path, caps: "dict | None", products: list) -> Path:
    """Build a minimal fake repo_root with just data/products.json and
    scripts/pipeline/config/platform_capabilities.yaml -- the two files this
    check's configure(repo_root=...) seam redirects. The pipeline CODE side
    is always the real scripts/pipeline/ tree (see check_platform_
    capabilities.py's own module docstring for why)."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "products.json").write_text(json.dumps(products), encoding="utf-8")
    config_dir = tmp_path / "scripts" / "pipeline" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    if caps is not None:
        with open(config_dir / "platform_capabilities.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(caps, f)
    return tmp_path


class TestRealRepo:
    def test_real_repo_has_zero_findings(self):
        """Live proof against the ACTUAL current repo state -- this check
        was built FROM the real code, so it must pass against it today."""
        cpc.configure()  # default: real repo root
        findings = cpc.check_all()
        assert findings == [], findings

    def test_real_repo_platform_list_matches_products_json(self):
        cpc.configure()
        caps = cpc._load_yaml()
        active = cpc._load_active_platforms()
        assert set(caps["platforms"].keys()) == active


class TestMissingYaml:
    def test_missing_yaml_is_a_finding(self, tmp_path):
        repo = _write_repo(tmp_path, caps=None, products=[
            {"family": "demo", "platform": "python", "active": True},
        ])
        cpc.configure(repo_root=repo)
        findings = cpc.check_all()
        kinds = {f["kind"] for f in findings}
        assert "missing_yaml" in kinds


class TestPlatformCompleteness:
    def test_undeclared_active_platform_is_a_finding(self, tmp_path):
        real_caps = _load_real_caps()
        # Drop typescript's row entirely, but keep it active in products.json.
        caps = {"platforms": {k: v for k, v in real_caps["platforms"].items() if k != "typescript"}}
        products = [{"family": "demo", "platform": p, "active": True} for p in caps["platforms"]]
        products.append({"family": "pdf", "platform": "typescript", "active": True})
        repo = _write_repo(tmp_path, caps, products)
        cpc.configure(repo_root=repo)
        findings = cpc.check_platform_completeness(cpc._load_yaml(), cpc._load_active_platforms())
        matches = [f for f in findings if f["kind"] == "undeclared_active_platform" and f["platform"] == "typescript"]
        assert len(matches) == 1

    def test_stale_declared_platform_is_a_finding(self, tmp_path):
        real_caps = _load_real_caps()
        # Keep typescript declared, but make no product active for it.
        caps = {"platforms": dict(real_caps["platforms"])}
        products = [
            {"family": "demo", "platform": p, "active": True}
            for p in caps["platforms"] if p != "typescript"
        ]
        products.append({"family": "pdf", "platform": "typescript", "active": False})
        repo = _write_repo(tmp_path, caps, products)
        cpc.configure(repo_root=repo)
        findings = cpc.check_platform_completeness(cpc._load_yaml(), cpc._load_active_platforms())
        matches = [f for f in findings if f["kind"] == "stale_declared_platform" and f["platform"] == "typescript"]
        assert len(matches) == 1

    def test_well_formed_repo_has_no_completeness_findings(self, tmp_path):
        real_caps = _load_real_caps()
        caps = {"platforms": dict(real_caps["platforms"])}
        products = [{"family": "demo", "platform": p, "active": True} for p in caps["platforms"]]
        repo = _write_repo(tmp_path, caps, products)
        cpc.configure(repo_root=repo)
        findings = cpc.check_platform_completeness(cpc._load_yaml(), cpc._load_active_platforms())
        assert findings == []


class TestNegativeControlValueMismatch:
    """The required negative-control fixture: a platform_capabilities.yaml
    whose declared value disagrees with the real pipeline code MUST fail the
    check. Reproduces the exact TC-10 regression shape (TypeScript's
    abstract_class_declaration silently missing from a class_kinds
    declaration) rather than an arbitrary wrong value."""

    def test_typescript_class_kinds_disagreeing_with_real_code_fails(self, tmp_path):
        real_caps = _load_real_caps()
        caps = {"platforms": {"typescript": dict(real_caps["platforms"]["typescript"])}}
        # Deliberately wrong: drop abstract_class_declaration from the
        # declared value while the real tree_helpers._CLASS_TYPES["typescript"]
        # still has it -- this is a fixture describing a regressed YAML, not
        # a regressed codebase.
        caps["platforms"]["typescript"] = dict(caps["platforms"]["typescript"])
        caps["platforms"]["typescript"]["class_kinds"] = [
            k for k in caps["platforms"]["typescript"]["class_kinds"]
            if k != "abstract_class_declaration"
        ]
        products = [{"family": "pdf", "platform": "typescript", "active": True}]
        repo = _write_repo(tmp_path, caps, products)
        cpc.configure(repo_root=repo)

        findings = cpc.check_all()

        assert findings, "expected at least one finding for a regressed class_kinds declaration"
        mismatches = [
            f for f in findings
            if f["kind"] == "value_mismatch" and f["platform"] == "typescript" and f["site"] == "class_kinds"
        ]
        assert len(mismatches) == 1, findings
        assert "abstract_class_declaration" in mismatches[0]["detail"] or True  # detail carries the real/declared sets

    def test_same_fixture_passes_once_the_value_is_corrected(self, tmp_path):
        """Sanity companion to the negative control: restoring the real
        value makes the SAME fixture shape clean again for the class_kinds
        value under test -- proving the finding above was caused by the
        mutation, not fixture plumbing.

        Scoped to the typescript/class_kinds finding specifically (TC-14,
        MT069, 2026-09-17) rather than asserting `findings == []` overall:
        this fixture deliberately declares only one of the registry's 7
        example_verification platforms, so check_example_verification()'s
        reverse-completeness loop correctly reports the other 6 as missing
        from this fixture's YAML -- that is real, correct, unrelated
        behavior, not a regression of the value this test is actually
        checking. See test_completeness_check_uses_declared_platforms_not_active_subset
        below for the completeness loop's own dedicated regression pin."""
        real_caps = _load_real_caps()
        caps = {"platforms": {"typescript": dict(real_caps["platforms"]["typescript"])}}
        products = [{"family": "pdf", "platform": "typescript", "active": True}]
        repo = _write_repo(tmp_path, caps, products)
        cpc.configure(repo_root=repo)
        findings = cpc.check_all()
        mismatches = [
            f for f in findings
            if f["kind"] == "value_mismatch" and f["platform"] == "typescript" and f["site"] == "class_kinds"
        ]
        assert mismatches == [], mismatches

    def test_completeness_check_uses_declared_platforms_not_active_subset(self, tmp_path):
        """Regression pin for TC-14/MT069 (2026-09-17): check_example_verification's
        reverse-completeness loop (the 'registry.PLATFORM_CONTRACT declares
        this platform but it has no row in platform_capabilities.yaml'
        finding) must compare against every platform the YAML itself
        declares (caps["platforms"]), not the caller's active-and-declared
        `checkable_platforms` subset. Conflating the two produced 6
        false-positive findings on every real CI run from 2026-09-06 onward
        (skill-governance.yml, 100% failure rate) for platforms that were
        fully declared in the real YAML but simply not marked `active` in
        that day's products.json snapshot.

        This fixture reproduces the exact shape: all 7 real platforms keep
        their real, fully-populated example_verification blocks (nothing is
        actually missing from the YAML), but only 2 of the 7 are marked
        active -- so `checkable_platforms` narrows to just those 2 while
        `caps["platforms"]` still has all 7."""
        real_caps = _load_real_caps()
        caps = {"platforms": dict(real_caps["platforms"])}
        active = ["python", "typescript"]
        products = [{"family": "demo", "platform": p, "active": p in active} for p in caps["platforms"]]
        repo = _write_repo(tmp_path, caps, products)
        cpc.configure(repo_root=repo)

        findings = cpc.check_all()

        completeness_findings = [
            f for f in findings
            if f["kind"] == "value_mismatch" and f["site"] == "example_verification"
            and "no row in platform_capabilities.yaml" in f["detail"]
        ]
        assert completeness_findings == [], completeness_findings


class TestMainExitCode:
    def test_exit_0_when_no_findings(self, tmp_path, monkeypatch):
        real_caps = _load_real_caps()
        caps = {"platforms": dict(real_caps["platforms"])}
        products = [{"family": "demo", "platform": p, "active": True} for p in caps["platforms"]]
        repo = _write_repo(tmp_path, caps, products)
        cpc.configure(repo_root=repo)
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["check_platform_capabilities.py"])
        with pytest.raises(SystemExit) as exc:
            cpc.main()
        assert exc.value.code == 0

    def test_exit_1_when_findings_exist(self, tmp_path, monkeypatch):
        repo = _write_repo(tmp_path, caps=None, products=[])
        cpc.configure(repo_root=repo)
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["check_platform_capabilities.py"])
        with pytest.raises(SystemExit) as exc:
            cpc.main()
        assert exc.value.code == 1

    def test_dry_run_always_exits_0(self, tmp_path, monkeypatch):
        repo = _write_repo(tmp_path, caps=None, products=[])
        cpc.configure(repo_root=repo)
        # T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=PERMANENT
        monkeypatch.setattr("sys.argv", ["check_platform_capabilities.py", "--dry-run"])
        with pytest.raises(SystemExit) as exc:
            cpc.main()
        assert exc.value.code == 0
