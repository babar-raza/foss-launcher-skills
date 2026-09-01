"""check_readme_template_contract_parity.py -- SW-F fix, TC-34
(readme-refresh-trackb-and-followon-2026-09-01).

Verifies data/readme_template_contract.json (the durable, in-repo README structure
contract) stays in real, mechanical agreement with the code and docs it describes,
instead of silently drifting the way the check-count number already did once before
this contract existed (RC-check-count-doc-drift-fix, 2026-08-30: 21 -> 105; the real
count had already moved to 109 by the time this check was written, 2026-09-01 --
confirmed live, not hypothetical).

Checks, all independent (each failure reported separately, not short-circuited):
1. required_sections in the JSON contract == _REQUIRED_SECTIONS in
   readme_refresh_checks.py (parsed via ast, never imported -- this check must never
   require a working Python environment for the pipeline package itself).
2. check_function_count.value in the JSON contract == the real, live count of
   `^def check_` functions in readme_refresh_checks.py.
3. The number embedded in registry.yaml's S-120 `change_impact` field's
   "N deterministic check_* functions" phrase == the same real, live count.

Exit codes: 0 ok; 1 any drift found (message names exactly which); 2 usage/parse error.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CONTRACT_PATH = _REPO_ROOT / "data" / "readme_template_contract.json"
_CHECKS_PATH = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "foss" / "readme_refresh_checks.py"
_REGISTRY_PATH = _REPO_ROOT / "scripts" / "pipeline" / "config" / "registry.yaml"

_CHECK_COUNT_RE = re.compile(r"(\d+)\s+deterministic\s+check_\*\s+functions")


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Test seam."""
    global _REPO_ROOT, _CONTRACT_PATH, _CHECKS_PATH, _REGISTRY_PATH
    if repo_root is None:
        return
    _REPO_ROOT = Path(repo_root)
    _CONTRACT_PATH = _REPO_ROOT / "data" / "readme_template_contract.json"
    _CHECKS_PATH = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "foss" / "readme_refresh_checks.py"
    _REGISTRY_PATH = _REPO_ROOT / "scripts" / "pipeline" / "config" / "registry.yaml"


def real_required_sections() -> "list[str] | None":
    """Parses _REQUIRED_SECTIONS out of readme_refresh_checks.py via ast -- never imports the
    module (this check must stay runnable without the pipeline package's own dependencies
    installed). Returns None if the file/name cannot be found or parsed."""
    if not _CHECKS_PATH.is_file():
        return None
    tree = ast.parse(_CHECKS_PATH.read_text(encoding="utf-8"), filename=str(_CHECKS_PATH))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_REQUIRED_SECTIONS" for t in node.targets
        ):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
            if isinstance(value, list) and all(isinstance(x, str) for x in value):
                return value
    return None


def real_check_function_count() -> "int | None":
    if not _CHECKS_PATH.is_file():
        return None
    return len(re.findall(r"^def check_\w+\(", _CHECKS_PATH.read_text(encoding="utf-8"), re.MULTILINE))


def registry_yaml_check_count() -> "int | None":
    if not _REGISTRY_PATH.is_file():
        return None
    m = _CHECK_COUNT_RE.search(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else None


def run(*, repo_root: "Path | str | None" = None) -> "list[str]":
    """Returns a list of human-readable violation strings -- empty means clean."""
    configure(repo_root=repo_root)
    violations: list[str] = []

    if not _CONTRACT_PATH.is_file():
        return [f"contract file not found: {_CONTRACT_PATH}"]
    try:
        contract = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"contract file is not valid JSON: {exc}"]

    real_sections = real_required_sections()
    if real_sections is None:
        violations.append(f"could not find/parse _REQUIRED_SECTIONS in {_CHECKS_PATH}")
    elif contract.get("required_sections") != real_sections:
        violations.append(
            f"required_sections drift: contract has {contract.get('required_sections')!r}, "
            f"code's _REQUIRED_SECTIONS has {real_sections!r}"
        )

    real_count = real_check_function_count()
    contract_count = (contract.get("check_function_count") or {}).get("value")
    if real_count is None:
        violations.append(f"could not count check_* functions in {_CHECKS_PATH}")
    elif contract_count != real_count:
        violations.append(
            f"check_function_count drift: contract says {contract_count!r}, "
            f"real grep count of '^def check_' in {_CHECKS_PATH.name} is {real_count}"
        )

    registry_count = registry_yaml_check_count()
    if real_count is not None:
        if registry_count is None:
            violations.append(
                f"registry.yaml's S-120 change_impact no longer contains an "
                "'N deterministic check_* functions' phrase to verify"
            )
        elif registry_count != real_count:
            violations.append(
                f"registry.yaml drift: change_impact says {registry_count} deterministic "
                f"check_* functions, real count is {real_count}"
            )

    return violations


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    violations = run(repo_root=args.repo_root)
    if violations:
        print(f"readme-template-contract-parity: {len(violations)} violation(s):")
        for v in violations:
            print(f"  - {v}")
        print(
            "Fix: update data/readme_template_contract.json (and docs/readme-refresh/"
            "template-contract.md, and scripts/pipeline/config/registry.yaml's change_impact "
            "if the check count moved) to match the real code -- never edit the code just to "
            "make an old number fit."
        )
        return 1
    print("readme-template-contract-parity: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
