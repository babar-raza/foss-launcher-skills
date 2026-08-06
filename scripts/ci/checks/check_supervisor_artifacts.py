#!/usr/bin/env python3
"""check_supervisor_artifacts.py — do a mission's .supervisor stage artifacts satisfy
the contract its own prompts declare? (MT021 TC-MT021-07, backlog ST-060.)

Found live: every stage prompt declares an output contract under `.supervisor/schemas/`
(`stage1-issue-model.schema.json`, `stage2-taskcard-contract.schema.json`,
`stage3-quality-scoring-rubric.schema.json`, plus a `taskcard-state-machine.schema.json`
prompt2 cites for its status enum) and that directory did not exist. Every mission using
the convergence loop therefore asserted "schema-conformant" outputs against a contract
nothing could check.

Two distinct failure modes, and only one of them is a schema problem:

  * SHAPE   -- a machine-readable artifact exists but has the wrong fields. A JSON
               Schema catches this.
  * ABSENCE -- a required artifact was never produced at all. A schema CANNOT catch
               this, because there is no document to validate.

Absence is the one that actually bit. MT020's own convergence run produced 4 of the 11
stage1 artifacts prompt1 requires (MT019 produced 8/11) and nothing noticed, because no
check compared the produced set against the declared set. So this check does completeness
first and conformance second.

The required-output list is PARSED FROM THE PROMPT FILES at run time rather than copied
here. A hardcoded list would silently drift the moment a prompt is edited -- reintroducing
exactly the producer/consumer divergence class this whole mission line exists to remove.

Usage:
    python scripts/ci/checks/check_supervisor_artifacts.py                  # newest mission
    python scripts/ci/checks/check_supervisor_artifacts.py --mission MT020-...
    python scripts/ci/checks/check_supervisor_artifacts.py --all           # every mission
    python scripts/ci/checks/check_supervisor_artifacts.py --json

Exit codes:
    0  every declared artifact present and schema-conformant
    1  missing artifacts, or a schema violation
    2  configuration error (prompts or mission dir not found)

Advisory by default in the same sense as check_module_consumption.py: it is an
agent/operator-invoked tool, deliberately NOT wired into pre-commit. Wiring it in is a
governance decision (MT021 B-4), not this script's to make.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / ".supervisor" / "prompts"
SCHEMAS_DIR = REPO_ROOT / ".supervisor" / "schemas"
STATE_DIR = REPO_ROOT / ".supervisor" / "state"

_STAGE_PROMPTS = {
    1: "prompt1-post-sprint-audit.md",
    2: "prompt2-plan-hardening.md",
    3: "prompt3-controlled-execution.md",
}

# Machine-readable artifact -> the schema its prompt declares for it.
_SCHEMA_FOR = {
    "stage1-issue-model.json": "stage1-issue-model.schema.json",
    "stage2-taskcard-contract.json": "stage2-taskcard-contract.schema.json",
    "stage3-quality-scoring-rubric.json": "stage3-quality-scoring-rubric.schema.json",
}


def declared_outputs(stage: int) -> list[str]:
    """Parse a stage's required-output filenames out of its own prompt."""
    p = PROMPTS_DIR / _STAGE_PROMPTS[stage]
    if not p.is_file():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8")
    # Required Outputs sections list each file as a bullet in backticks.
    return re.findall(rf"^- `(stage{stage}-[^`]+)`", text, re.M)


def _matches(produced: set[str], required: str) -> bool:
    """A glob-ish required entry (e.g. 'stage2-taskcards/*.yaml') matches a produced path."""
    if "*" in required:
        prefix = required.split("*")[0]
        return any(name.startswith(prefix) for name in produced)
    return required in produced


def _validate_schema(instance: object, schema: dict) -> list[str]:
    """Minimal structural validation: required keys and declared types.

    Deliberately not a full JSON Schema engine -- jsonschema is not a pipeline
    dependency, and pulling one in for a P3 advisory check would be the larger change.
    Covers required/type/enum, which is what the stage schemas actually assert.
    """
    errs: list[str] = []

    def walk(node: object, sch: dict, path: str) -> None:
        t = sch.get("type")
        if t == "object":
            if not isinstance(node, dict):
                errs.append(f"{path or '<root>'}: expected object, got {type(node).__name__}")
                return
            for key in sch.get("required", []):
                if key not in node:
                    errs.append(f"{path}.{key}: required property missing")
            for key, sub in (sch.get("properties") or {}).items():
                if key in node:
                    walk(node[key], sub, f"{path}.{key}")
        elif t == "array":
            if not isinstance(node, list):
                errs.append(f"{path}: expected array, got {type(node).__name__}")
                return
            item = sch.get("items")
            if isinstance(item, dict):
                for i, v in enumerate(node):
                    walk(v, item, f"{path}[{i}]")
        elif t == "string":
            if not isinstance(node, str):
                errs.append(f"{path}: expected string, got {type(node).__name__}")
        elif t == "integer":
            if not isinstance(node, int) or isinstance(node, bool):
                errs.append(f"{path}: expected integer, got {type(node).__name__}")
        elif t == "boolean":
            if not isinstance(node, bool):
                errs.append(f"{path}: expected boolean, got {type(node).__name__}")
        enum = sch.get("enum")
        if enum is not None and node not in enum:
            errs.append(f"{path}: {node!r} not in allowed values {enum}")

    walk(instance, schema, "")
    return errs


def audit_mission(mission_dir: Path) -> dict:
    """Return a completeness + conformance report for one mission artifact dir."""
    produced = {p.name for p in mission_dir.iterdir()} if mission_dir.is_dir() else set()
    # Nested taskcard dirs count as produced entries too.
    for p in mission_dir.glob("stage2-taskcards/*"):
        produced.add(f"stage2-taskcards/{p.name}")

    stages: dict[str, dict] = {}
    total_missing = 0
    stages_attempted = 0

    for stage in (1, 2, 3):
        required = declared_outputs(stage)
        present = [r for r in required if _matches(produced, r)]
        missing = [r for r in required if not _matches(produced, r)]
        attempted = len(present) > 0
        if attempted:
            stages_attempted += 1
            total_missing += len(missing)
        stages[f"stage{stage}"] = {
            "attempted": attempted, "required": len(required),
            "present": len(present), "missing": missing,
        }

    schema_errors: dict[str, list[str]] = {}
    for artifact, schema_name in _SCHEMA_FOR.items():
        art = mission_dir / artifact
        sch = SCHEMAS_DIR / schema_name
        if not art.is_file():
            continue                      # absence is reported by the completeness pass
        if not sch.is_file():
            schema_errors[artifact] = [f"declared schema {schema_name} does not exist"]
            continue
        try:
            errs = _validate_schema(json.loads(art.read_text(encoding="utf-8")),
                                    json.loads(sch.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            errs = [f"unparseable: {exc}"]
        if errs:
            schema_errors[artifact] = errs

    return {
        "mission": mission_dir.name,
        "stages": stages,
        "stages_attempted": stages_attempted,
        "missing_total": total_missing,
        "schema_errors": schema_errors,
        "ok": total_missing == 0 and not schema_errors,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mission", help="mission id (directory under .supervisor/state/)")
    ap.add_argument("--all", action="store_true", help="audit every mission directory")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    if not PROMPTS_DIR.is_dir():
        print(f"ERROR: {PROMPTS_DIR} not found", file=sys.stderr)
        return 2
    if not STATE_DIR.is_dir():
        print(f"ERROR: {STATE_DIR} not found", file=sys.stderr)
        return 2

    missions = sorted(d for d in STATE_DIR.iterdir()
                      if d.is_dir() and d.name not in {"closures"})
    if args.mission:
        missions = [d for d in missions if d.name == args.mission]
        if not missions:
            print(f"ERROR: mission {args.mission!r} not found under {STATE_DIR}",
                  file=sys.stderr)
            return 2
    elif not args.all:
        # Default: the mission with the most recently modified artifact.
        missions = [max(missions, key=lambda d: max(
            (p.stat().st_mtime for p in d.iterdir()), default=0))] if missions else []

    reports = [audit_mission(d) for d in missions]

    if args.as_json:
        print(json.dumps(reports, indent=2))
    else:
        for r in reports:
            mark = "OK  " if r["ok"] else "FAIL"
            print(f"[{mark}] {r['mission']}")
            for name, s in r["stages"].items():
                if not s["attempted"]:
                    print(f"        {name}: not attempted (skipped)")
                    continue
                print(f"        {name}: {s['present']}/{s['required']} declared artifacts present")
                for m in s["missing"]:
                    print(f"          MISSING {m}")
            for art, errs in r["schema_errors"].items():
                for e in errs:
                    print(f"          SCHEMA  {art}: {e}")

    bad = [r for r in reports if not r["ok"]]
    if bad:
        print(f"\ncheck_supervisor_artifacts: FAIL — {len(bad)} of {len(reports)} "
              f"mission(s) incomplete or non-conformant", file=sys.stderr)
        return 1
    print(f"\ncheck_supervisor_artifacts: PASS — {len(reports)} mission(s) complete "
          f"and conformant")
    return 0


if __name__ == "__main__":
    sys.exit(main())
