#!/usr/bin/env python3
"""check_skill_doc_pins.py — skill-doc↔code constant pin gate (D-8a).

Mission MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH, TC-MT040-47. Root problem:
skill docs (skills/*.md) restate numeric/gate-count constants from real
pipeline code in prose (e.g. "howto_count >= 6", "15 automated gates"), and
that prose silently drifts from the code it describes. Two real, confirmed
instances found live this session:
  - skills/site-plan.md said "howto_count >= 6"; the real code
    (site_planner.py) uses ">= 3".
  - skills/launch-product.md's Stage 8.5 said launch_gate.py runs "15"
    gates; the real code (launch_gate.py::_ALL_GATES) has 16.
Neither drift was caught mechanically until a human happened to compare doc
text to source by hand.

Mechanism: a skill doc may annotate one prose line with a trailing HTML
comment `<!-- pin: <module>.<ATTR> -->` (or `<!-- pin: <module>.len(<ATTR>) -->`
for a list/collection whose LENGTH is the pinned value). This check:
  1. finds every such comment in every skills/*.md file,
  2. resolves <module> to a real importable pipeline module (searched under
     scripts/pipeline/commands/*/, scripts/pipeline/lib/,
     scripts/pipeline/content_eval/),
  3. imports it and reads the named attribute (or len() of it),
  4. extracts the first integer literal on the SAME line, before the pin
     comment, as the doc's own stated value,
  5. fails if the two disagree.

A skill doc with NO pin comments is unaffected (this is an opt-in
annotation, not a retroactive requirement -- landing this checker does not
require every existing skill doc to be edited in the same pass; see
TC-MT040-23 for where real pins get added to the docs that need them).

Usage:
    python scripts/ci/checks/check_skill_doc_pins.py
    python scripts/ci/checks/check_skill_doc_pins.py --skills-dir path/to/skills

Exit codes:
    0 — every pin found matches the real code value (including zero pins found)
    1 — at least one pin mismatches, or a pin's module/attribute cannot be resolved
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_DEFAULT_SKILLS_DIR = _DEFAULT_REPO_ROOT / "skills"
_SKILLS_DIR = _DEFAULT_SKILLS_DIR

_SEARCH_SUBDIRS = (
    "scripts/pipeline/commands/content",
    "scripts/pipeline/commands/diagnostics",
    "scripts/pipeline/commands/governance",
    "scripts/pipeline/commands/healing",
    "scripts/pipeline/commands/knowledge",
    "scripts/pipeline/commands/launch",
    "scripts/pipeline/commands/migration",
    "scripts/pipeline/commands/ops",
    "scripts/pipeline/lib",
    "scripts/pipeline/content_eval",
    "scripts/pipeline/content_eval/evaluators",
    "scripts/pipeline/extraction",
)

# <!-- pin: module.ATTR --> or <!-- pin: module.len(ATTR) -->
_PIN_RE = re.compile(
    r"<!--\s*pin:\s*(?P<module>[A-Za-z_][A-Za-z0-9_]*)\.(?:len\((?P<len_attr>[A-Za-z_][A-Za-z0-9_]*)\)|(?P<attr>[A-Za-z_][A-Za-z0-9_]*))\s*-->"
)
# First bare integer literal on the line (the doc's own stated value).
_FIRST_INT_RE = re.compile(r"(?<![\w.])(\d+)(?![\w.])")


def configure(*, repo_root: "Path | str | None" = None, skills_dir: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, _SKILLS_DIR
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _SKILLS_DIR = Path(skills_dir) if skills_dir is not None else (_REPO_ROOT / "skills")


class PinError(Exception):
    """Raised when a pin's module/attribute cannot be resolved at all
    (distinct from a value MISMATCH, which is reported as a finding, not an
    exception -- an unresolvable pin is a broken annotation, always an error)."""


def _resolve_module_file(module_name: str) -> "Path | None":
    for sub in _SEARCH_SUBDIRS:
        candidate = _REPO_ROOT / Path(sub) / f"{module_name}.py"
        if candidate.is_file():
            return candidate
    return None


def _import_module(module_name: str):
    module_file = _resolve_module_file(module_name)
    if module_file is None:
        raise PinError(f"pin module '{module_name}' not found under any of {_SEARCH_SUBDIRS}")
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"_pindoc_{module_name}", module_file)
    if spec is None or spec.loader is None:
        raise PinError(f"could not build an import spec for {module_file}")
    module = importlib.util.module_from_spec(spec)
    # Pipeline modules commonly import sibling top-level modules (e.g.
    # `from tree_helpers import ...`) assuming scripts/pipeline/ and
    # scripts/pipeline/lib/ are already on sys.path -- match the same
    # convention every other pipeline entrypoint/test relies on.
    pipeline_root = str(_REPO_ROOT / "scripts" / "pipeline")
    lib_dir = str(_REPO_ROOT / "scripts" / "pipeline" / "lib")
    for p in (pipeline_root, lib_dir):
        if p not in sys.path:
            sys.path.insert(0, p)
    # Register in sys.modules BEFORE exec_module, matching what the normal
    # `import` statement machinery does -- some pipeline modules (e.g.
    # launch_gate.py) define @dataclass classes, and dataclasses.dataclass()
    # looks the defining module up via sys.modules[cls.__module__] DURING
    # class creation; skipping this step (the bug this comment documents,
    # found live while testing this checker against launch_gate.py) makes
    # exec_module crash with a confusing AttributeError on any such module,
    # not a clean, checkable pin failure.
    previously_registered = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 -- surfaced as a PinError, not a crash
        raise PinError(f"failed to import pin module '{module_name}' ({module_file}): {exc}") from exc
    finally:
        if previously_registered is not None:
            sys.modules[spec.name] = previously_registered
        else:
            sys.modules.pop(spec.name, None)
    return module


def _resolve_pin_value(module_name: str, attr: "str | None", len_attr: "str | None") -> int:
    module = _import_module(module_name)
    target_attr = attr or len_attr
    if not hasattr(module, target_attr):
        raise PinError(f"module '{module_name}' has no attribute '{target_attr}'")
    value = getattr(module, target_attr)
    if len_attr:
        try:
            return len(value)
        except TypeError as exc:
            raise PinError(
                f"module '{module_name}'.{len_attr} is not len()-able ({type(value).__name__})"
            ) from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise PinError(
            f"module '{module_name}'.{attr} is not an int (got {type(value).__name__}={value!r}) -- "
            f"only integer pins are supported"
        )
    return value


def check_file(path: Path) -> list[dict]:
    """Check one skill doc file. Returns a list of finding dicts (empty if
    the file has no pins, or all pins match)."""
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [{"file": str(path), "line": 0, "kind": "read_error", "detail": str(exc)}]

    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _PIN_RE.search(line)
        if not m:
            continue
        module_name = m.group("module")
        attr = m.group("attr")
        len_attr = m.group("len_attr")
        prose_before_pin = line[: m.start()]
        int_m = _FIRST_INT_RE.search(prose_before_pin)
        if not int_m:
            findings.append({
                "file": str(path), "line": lineno, "kind": "no_stated_value",
                "detail": f"pin found (module={module_name}) but no integer literal "
                          f"precedes it on the same line: {line.strip()!r}",
            })
            continue
        stated_value = int(int_m.group(1))
        try:
            real_value = _resolve_pin_value(module_name, attr, len_attr)
        except PinError as exc:
            findings.append({
                "file": str(path), "line": lineno, "kind": "unresolvable_pin",
                "detail": str(exc),
            })
            continue
        if stated_value != real_value:
            attr_desc = f"len({len_attr})" if len_attr else attr
            findings.append({
                "file": str(path), "line": lineno, "kind": "mismatch",
                "detail": f"doc states {stated_value}, but {module_name}.{attr_desc} == {real_value}: "
                          f"{line.strip()!r}",
            })
    return findings


def check_all() -> list[dict]:
    if not _SKILLS_DIR.is_dir():
        return []
    findings: list[dict] = []
    for path in sorted(_SKILLS_DIR.glob("*.md")):
        findings.extend(check_file(path))
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="Check skill-doc <!-- pin: --> comments against real code constants")
    parser.add_argument("--skills-dir", default=None, help="Override skills/ directory (default: repo skills/)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.skills_dir:
        configure(skills_dir=args.skills_dir)

    findings = check_all()

    if args.json:
        import json
        print(json.dumps(findings, indent=2))
    else:
        if not findings:
            print("check_skill_doc_pins: 0 pin(s) checked with a mismatch (or 0 pins found).")
        for f in findings:
            print(f"[{f['kind'].upper()}] {f['file']}:{f['line']}: {f['detail']}")
        print(f"\n{len(findings)} finding(s).")

    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
