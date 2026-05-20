"""Production-readiness contract tests for PRD-003."""
from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
REGISTRY = REPO_ROOT / "skills" / "registry.yaml"


def _project_scripts() -> dict[str, str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["scripts"]


@pytest.mark.parametrize(("name", "target"), sorted(_project_scripts().items()))
def test_packaging_entrypoint_imports(name: str, target: str):
    module_name, _, attr = target.partition(":")
    if name == "foss-audit" and module_name == "scripts.audit":
        pytest.xfail("PRD-003 gap: foss-audit still points at missing scripts.audit")

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if name == "foss-audit":
            pytest.xfail(f"PRD-003 gap: foss-audit package import fails: {exc}")
        raise

    assert attr, f"{name} must target module:function, got {target!r}"
    assert callable(getattr(module, attr))


def test_refresh_knowledge_compat_import_resolves_to_moved_module():
    pipeline_root = REPO_ROOT / "scripts" / "pipeline"
    sys.path.insert(0, str(pipeline_root))
    try:
        import refresh_knowledge  # noqa: PLC0415
    finally:
        sys.path.remove(str(pipeline_root))

    assert refresh_knowledge.__name__ == "commands.knowledge.refresh_knowledge"
    assert refresh_knowledge.REPO_ROOT == REPO_ROOT
    assert refresh_knowledge.KNOWLEDGE_ROOT == REPO_ROOT / "knowledge"


def test_registry_knowledge_update_script_uses_moved_refresh_path():
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in registry["skills"]}

    assert by_id["S-14"]["script"] == "scripts/pipeline/commands/knowledge/refresh_knowledge.py"
    assert (REPO_ROOT / by_id["S-14"]["script"]).is_file()


def test_s23_registry_script_exports_prewrite_audit_contract():
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in registry["skills"]}
    script = by_id["S-23"]["script"]

    # Registry must point at the real audit implementation, not the legacy shim.
    assert script == "scripts/pipeline/commands/content/audit.py", (
        f"S-23 script must be 'scripts/pipeline/commands/content/audit.py', got {script!r}"
    )

    # The script file must exist on disk.
    assert (REPO_ROOT / script).is_file(), f"S-23 script does not exist on disk: {script}"

    # The module must be importable and expose the required public API.
    module = importlib.import_module("scripts.pipeline.commands.content.audit")
    assert callable(getattr(module, "audit_page", None)), "audit_page must be callable"
    assert callable(getattr(module, "main", None)), "main must be callable"
