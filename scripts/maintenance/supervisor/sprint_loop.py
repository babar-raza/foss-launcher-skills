"""
sprint_loop.py -- Post-sprint autonomy loop orchestrator.

Connects loop_controller.py (classifier + decision engine) to file-based
cross-session state, stage output validation with repair, evidence bundling,
and CLI automation for both interactive and unattended modes.

Subcommands:
  init            Create evidence dir + state file for a new sprint loop
  status          Print current loop state
  inject-template Write skeleton YAML outputs for a stage
  validate        Check stage outputs exist and conform (--repair mode)
  decide          Run loop_controller, update state with decision
  bundle          Package evidence into ZIP with manifest
  recover         Restore state from backup or rebuild from evidence
  reset           Clear state file
  run-stage       Execute one stage (for scheduled/unattended mode)
  run-loop        Execute full P1->P2->P3 cycle unattended
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT
from loop_controller import (
    LoopClassification,
    classify_summary,
    compute_decision,
    check_quality_scores,
    validate_evidence_bundle,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_DIR = REPO_ROOT / ".supervisor" / "state"
STATE_FILE = STATE_DIR / "loop-state.json"
STATE_BACKUP = STATE_DIR / "loop-state.json.bak"
EVIDENCE_ROOT = REPO_ROOT / ".local" / "evidences"
BUNDLE_ROOT = REPO_ROOT / ".local" / "evidence-bundles"
PROMPT_DIR = _HERE / "prompts"
REGISTRY_PATH = PROMPT_DIR / "prompt-registry.yaml"

MAX_RETRIES = 3

# Stage mapping
STAGE_TO_PROMPT = {
    "P1": "PSL-P1",
    "P2": "PSL-P2",
    "P3": "PSL-P3",
}

# Required YAML keys per stage (for key-level validation)
STAGE_YAML_KEYS = {
    "stage1": {
        "stage1-l1-execution-issues.yaml": ["issue_id", "issue_level"],
        "stage1-l2-integration-issues.yaml": ["issue_id", "issue_level"],
        "stage1-l3-system-weaknesses.yaml": ["issue_id", "issue_level"],
        "stage1-next-stage-recommendation.yaml": ["recommendation"],
    },
    "stage3": {
        "stage3-final-sprint-summary.yaml": ["outcome", "scores", "taskcards", "evidence_files"],
        "stage3-lane-status.yaml": [],
        "stage3-taskcard-status.yaml": [],
        "stage3-quality-evaluations.yaml": [],
        "stage3-reroute-log.yaml": [],
        "stage3-evidence-manifest.yaml": [],
        "stage3-self-review-l1-execution-issues.yaml": [],
        "stage3-self-review-l2-integration-issues.yaml": [],
        "stage3-self-review-l3-system-weaknesses.yaml": [],
    },
}


# ---------------------------------------------------------------------------
# State management (atomic writes, checksums, backup-on-read)
# ---------------------------------------------------------------------------

def _compute_checksum(data: dict) -> str:
    """Compute SHA-256 checksum of state data (excluding _checksum field)."""
    clean = {k: v for k, v in data.items() if k != "_checksum"}
    canonical = json.dumps(clean, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_state_schema(data: dict) -> list[str]:
    """Validate state file has required keys and correct types."""
    errors = []
    required_keys = ["sprint_id", "stage", "retry_count", "evidence_dir", "started", "last_updated"]
    for key in required_keys:
        if key not in data:
            errors.append(f"missing required key: {key}")
    if "retry_count" in data and not isinstance(data["retry_count"], int):
        errors.append("retry_count must be an integer")
    if "stage" in data:
        valid_stages = {"P1", "P2", "P3", "ACCEPTED", "BLOCKED", "ESCALATED"}
        if data["stage"] not in valid_stages:
            errors.append(f"invalid stage: {data['stage']}")
    return errors


def _save_state(state: dict) -> None:
    """Write state atomically: compute checksum, write tmp, fsync, os.replace."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    state["_checksum"] = _compute_checksum(state)

    fd, tmp_path = tempfile.mkstemp(dir=str(STATE_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(STATE_FILE))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _load_state() -> dict | None:
    """Load state with checksum verification and backup-on-read."""
    if not STATE_FILE.exists():
        return None

    try:
        text = STATE_FILE.read_text(encoding="utf-8")
        data = json.loads(text)
    except (json.JSONDecodeError, OSError):
        # Primary corrupt — try backup
        return _load_backup()

    # Verify checksum
    stored_checksum = data.get("_checksum")
    if stored_checksum and stored_checksum != _compute_checksum(data):
        print("WARNING: State file checksum mismatch — loading backup", file=sys.stderr)
        return _load_backup()

    # Validate schema
    errors = _validate_state_schema(data)
    if errors:
        print(f"WARNING: State file schema errors: {errors} — loading backup", file=sys.stderr)
        return _load_backup()

    # Backup-on-read: copy current valid state to .bak
    try:
        shutil.copy2(str(STATE_FILE), str(STATE_BACKUP))
    except OSError:
        pass

    return data


def _load_backup() -> dict | None:
    """Load state from backup file."""
    if not STATE_BACKUP.exists():
        return None
    try:
        text = STATE_BACKUP.read_text(encoding="utf-8")
        data = json.loads(text)
        errors = _validate_state_schema(data)
        if errors:
            return None
        print("INFO: Restored state from backup", file=sys.stderr)
        return data
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Prompt registry loader
# ---------------------------------------------------------------------------

def _load_prompt_registry() -> dict:
    """Load prompt-registry.yaml and return the prompts dict."""
    if not REGISTRY_PATH.exists():
        return {}
    try:
        import yaml
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("prompts", {}) if isinstance(data, dict) else {}
    except ImportError:
        # Minimal fallback parse
        return _fallback_parse_registry()
    except Exception:
        return {}


def _fallback_parse_registry() -> dict:
    """Minimal registry parse without PyYAML — extracts required_outputs per stage."""
    result = {}
    if not REGISTRY_PATH.exists():
        return result
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    current_id = None
    in_outputs = False
    outputs = []

    for line in text.splitlines():
        stripped = line.strip()
        if line.startswith("  PSL-"):
            if current_id and outputs:
                result[current_id] = {"required_outputs": outputs}
            current_id = stripped.rstrip(":")
            outputs = []
            in_outputs = False
        elif stripped == "required_outputs:":
            in_outputs = True
        elif in_outputs and stripped.startswith("- "):
            outputs.append(stripped[2:].strip())
        elif in_outputs and not stripped.startswith("- ") and ":" in stripped:
            in_outputs = False

    if current_id and outputs:
        result[current_id] = {"required_outputs": outputs}
    return result


def _get_required_outputs(stage: str) -> list[str]:
    """Get required output files for a given stage (P1/P2/P3)."""
    registry = _load_prompt_registry()
    prompt_id = STAGE_TO_PROMPT.get(stage.upper())
    if not prompt_id:
        return []
    entry = registry.get(prompt_id, {})
    return entry.get("required_outputs", [])


# ---------------------------------------------------------------------------
# Subcommand: init
# ---------------------------------------------------------------------------

def cmd_init(args) -> int:
    """Initialize a new sprint loop."""
    sprint_id = args.sprint_id
    evidence_dir = EVIDENCE_ROOT / sprint_id

    # Check for duplicate
    state = _load_state()
    if state and state.get("sprint_id") == sprint_id:
        print(f"ERROR: Sprint loop '{sprint_id}' already exists. Use 'reset' first.", file=sys.stderr)
        return 1

    evidence_dir.mkdir(parents=True, exist_ok=True)

    new_state = {
        "sprint_id": sprint_id,
        "stage": "P1",
        "decision": None,
        "next_stage": None,
        "retry_count": 0,
        "compliance_score": None,
        "evidence_dir": str(evidence_dir),
        "started": datetime.now(timezone.utc).isoformat(),
        "last_updated": None,
    }
    _save_state(new_state)
    print(f"Initialized sprint loop: {sprint_id}")
    print(f"Evidence dir: {evidence_dir}")
    print(f"State file: {STATE_FILE}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status(args) -> int:
    """Print current loop state."""
    state = _load_state()
    if not state:
        print("No active sprint loop. Run 'init --sprint-id <id>' to start.")
        return 0

    print(json.dumps(state, indent=2, default=str))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: inject-template
# ---------------------------------------------------------------------------

def cmd_inject_template(args) -> int:
    """Write skeleton YAML files for a stage into the evidence dir."""
    state = _load_state()
    if not state:
        print("ERROR: No active sprint loop.", file=sys.stderr)
        return 1

    stage = args.stage.upper()
    evidence_dir = Path(args.evidence_dir) if args.evidence_dir else Path(state["evidence_dir"])

    outputs = _get_required_outputs(stage)
    if not outputs:
        print(f"ERROR: No required outputs found for stage {stage}", file=sys.stderr)
        return 1

    created = 0
    for filename in outputs:
        filepath = evidence_dir / filename
        if filepath.exists():
            continue  # Don't overwrite existing files
        if filename.endswith(".yaml"):
            _write_skeleton_yaml(filepath, stage, filename)
            created += 1
        elif filename.endswith(".md"):
            filepath.write_text(f"# {filename}\n\nTODO: Fill in content for {stage}\n", encoding="utf-8")
            created += 1
        elif filename.endswith(".csv"):
            filepath.write_text("# TODO: Fill in CSV content\n", encoding="utf-8")
            created += 1

    print(f"Injected {created} template files for stage {stage} into {evidence_dir}")
    return 0


def _write_skeleton_yaml(filepath: Path, stage: str, filename: str) -> None:
    """Write a skeleton YAML file with required keys as null/TODO."""
    stage_lower = stage.lower().replace("p", "stage")
    keys = STAGE_YAML_KEYS.get(stage_lower, {}).get(filename, [])
    lines = [f"# Skeleton template for {filename}", f"# Stage: {stage}", ""]
    if keys:
        for key in keys:
            lines.append(f"{key}: null  # TODO")
    else:
        lines.append("# TODO: Fill in required fields")
    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Subcommand: validate
# ---------------------------------------------------------------------------

def cmd_validate(args) -> int:
    """Validate stage outputs exist and conform."""
    state = _load_state()
    if not state:
        print("ERROR: No active sprint loop.", file=sys.stderr)
        return 1

    stage = args.stage.upper()
    evidence_dir = Path(args.evidence_dir) if args.evidence_dir else Path(state["evidence_dir"])
    repair = getattr(args, "repair", False)

    valid, issues = validate_stage_outputs(stage, evidence_dir, repair=repair)

    if valid:
        print(f"PASS: All required outputs for {stage} are valid.")
        return 0
    else:
        print(f"FAIL: {len(issues)} issue(s) found for {stage}:")
        for issue in issues:
            print(f"  - {issue}")
        return 1


def validate_stage_outputs(
    stage: str, evidence_dir: Path, repair: bool = False
) -> tuple[bool, list[str]]:
    """Check required outputs exist and conform. Returns (valid, issues)."""
    issues = []
    outputs = _get_required_outputs(stage)
    if not outputs:
        return False, [f"No required outputs defined for stage {stage}"]

    for filename in outputs:
        filepath = evidence_dir / filename

        # If file missing, try to find it in subdirectories (repair mode)
        if not filepath.exists() and repair:
            found = _try_relocate(evidence_dir, filename)
            if found:
                issues.append(f"REPAIRED: relocated {filename} from {found.parent.name}/")
                filepath = evidence_dir / filename

        if not filepath.exists():
            issues.append(f"MISSING: {filename}")
            continue

        if filepath.stat().st_size == 0:
            issues.append(f"EMPTY: {filename}")
            continue

        # YAML-specific validation
        if filename.endswith(".yaml"):
            yaml_issues = _validate_yaml_file(filepath, stage, filename, repair)
            issues.extend(yaml_issues)

    valid = not any(i.startswith("MISSING:") or i.startswith("EMPTY:") or i.startswith("PARSE_ERROR:") or i.startswith("MISSING_KEY:") for i in issues)
    return valid, issues


def _validate_yaml_file(
    filepath: Path, stage: str, filename: str, repair: bool
) -> list[str]:
    """Validate a YAML file: parse, check keys."""
    issues = []
    text = filepath.read_text(encoding="utf-8")

    # Repair: strip markdown code fences
    if repair and ("```yaml" in text or "```yml" in text or "```" in text):
        cleaned = _strip_markdown_fences(text)
        if cleaned != text:
            filepath.write_text(cleaned, encoding="utf-8")
            text = cleaned
            issues.append(f"REPAIRED: stripped markdown fences from {filename}")

    # Try to parse
    data = _try_parse_yaml_text(text)
    if data is None:
        issues.append(f"PARSE_ERROR: {filename}")
        return issues

    # Check required keys
    stage_lower = stage.lower().replace("p", "stage")
    required_keys = STAGE_YAML_KEYS.get(stage_lower, {}).get(filename, [])
    for key in required_keys:
        if key not in data:
            issues.append(f"MISSING_KEY: {filename} is missing '{key}'")

    return issues


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences wrapping YAML content."""
    lines = text.splitlines()
    result = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") and not in_fence:
            in_fence = True
            continue
        if stripped == "```" and in_fence:
            in_fence = False
            continue
        result.append(line)
    return "\n".join(result)


def _try_relocate(evidence_dir: Path, filename: str) -> Path | None:
    """Search evidence dir subdirectories for a misplaced file and relocate it."""
    for child in evidence_dir.rglob(filename):
        if child.parent != evidence_dir:
            target = evidence_dir / filename
            shutil.move(str(child), str(target))
            return child
    return None


def _try_parse_yaml_text(text: str) -> dict | None:
    """Parse YAML text into a dict."""
    text = text.strip()
    if not text:
        return None
    try:
        import yaml
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else None
    except ImportError:
        pass
    except Exception:
        return None
    # Minimal fallback
    try:
        from loop_controller import _minimal_yaml_parse
        return _minimal_yaml_parse(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Subcommand: decide
# ---------------------------------------------------------------------------

def cmd_decide(args) -> int:
    """Run loop_controller, update state with decision."""
    state = _load_state()
    if not state:
        print("ERROR: No active sprint loop.", file=sys.stderr)
        return 1

    evidence_dir = Path(args.evidence_dir) if args.evidence_dir else Path(state["evidence_dir"])

    # Classify
    classification, details = classify_summary(evidence_dir, quality_threshold=4)

    # Check evidence + scores
    parsed = details.get("parsed_data", {}) or {}
    scores = parsed.get("scores") if isinstance(parsed, dict) else None
    ev_files = parsed.get("evidence_files") if isinstance(parsed, dict) else None
    ev_complete, _ = validate_evidence_bundle(evidence_dir, ev_files)
    scores_pass, _ = check_quality_scores(scores, threshold=4)

    # Compute decision
    decision = compute_decision(
        classification, ev_complete, scores_pass,
        retry_count=state["retry_count"],
        max_retries=MAX_RETRIES,
    )

    # Compute compliance score
    required = _get_required_outputs(state["stage"])
    if required:
        existing = sum(1 for f in required if (evidence_dir / f).exists())
        compliance_score = round(existing / len(required), 2)
    else:
        compliance_score = None

    # Map decision to next stage
    action = decision["action"]
    if action == "ACCEPT":
        next_stage = "ACCEPTED"
    elif action == "BLOCK":
        next_stage = "BLOCKED"
    elif action == "ESCALATE":
        next_stage = "ESCALATED"
    elif action == "RETRY":
        # Determine which stage to retry/advance to
        ns = decision.get("next_stage", "")
        if "prompt1" in str(ns).lower():
            next_stage = "P1"
        elif "prompt2" in str(ns).lower():
            next_stage = "P2"
        elif "prompt3" in str(ns).lower():
            next_stage = "P3"
        else:
            # Default: advance from current stage
            stage_order = ["P1", "P2", "P3"]
            current_idx = stage_order.index(state["stage"]) if state["stage"] in stage_order else 0
            next_stage = stage_order[min(current_idx + 1, len(stage_order) - 1)]
    else:
        next_stage = state["stage"]

    # Update state
    state["decision"] = action
    state["next_stage"] = next_stage
    state["stage"] = next_stage
    state["compliance_score"] = compliance_score
    if action == "RETRY":
        state["retry_count"] = state["retry_count"] + 1
    _save_state(state)

    result = {
        "classification": classification.value,
        "action": action,
        "reason": decision["reason"],
        "next_stage": next_stage,
        "retry_count": state["retry_count"],
        "compliance_score": compliance_score,
    }
    print(json.dumps(result, indent=2))
    return 2 if classification == LoopClassification.CONTRADICTORY else 0


# ---------------------------------------------------------------------------
# Subcommand: bundle
# ---------------------------------------------------------------------------

def cmd_bundle(args) -> int:
    """Package evidence into ZIP with manifest."""
    state = _load_state()
    if not state:
        print("ERROR: No active sprint loop.", file=sys.stderr)
        return 1

    evidence_dir = Path(state["evidence_dir"])
    sprint_id = state["sprint_id"]

    if not evidence_dir.exists() or not any(evidence_dir.iterdir()):
        print("ERROR: Evidence directory is empty or missing.", file=sys.stderr)
        return 1

    return build_evidence_bundle(evidence_dir, sprint_id, state)


def build_evidence_bundle(evidence_dir: Path, sprint_id: str, state: dict) -> int:
    """Create ZIP bundle with manifest."""
    BUNDLE_ROOT.mkdir(parents=True, exist_ok=True)
    zip_path = BUNDLE_ROOT / f"{sprint_id}.zip"

    manifest = {"sprint_id": sprint_id, "created": datetime.now(timezone.utc).isoformat(), "files": []}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add all evidence files
        for filepath in sorted(evidence_dir.rglob("*")):
            if filepath.is_file():
                arcname = filepath.relative_to(evidence_dir)
                zf.write(filepath, str(arcname))
                manifest["files"].append({
                    "name": str(arcname),
                    "size": filepath.stat().st_size,
                })

        # Add state snapshot
        state_json = json.dumps(state, indent=2, default=str)
        zf.writestr("loop-state.json", state_json)
        manifest["files"].append({"name": "loop-state.json", "size": len(state_json)})

        # Add manifest
        manifest_json = json.dumps(manifest, indent=2, default=str)
        zf.writestr("manifest.json", manifest_json)

    print(f"Evidence bundle created: {zip_path}")
    print(f"Files: {len(manifest['files'])}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: recover
# ---------------------------------------------------------------------------

def cmd_recover(args) -> int:
    """Inspect state file + backup, report status, restore if needed."""
    primary_ok = False
    backup_ok = False

    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            checksum = data.get("_checksum")
            if checksum and checksum == _compute_checksum(data):
                errors = _validate_state_schema(data)
                primary_ok = len(errors) == 0
                if errors:
                    print(f"Primary state: INVALID (schema errors: {errors})")
                else:
                    print(f"Primary state: OK (sprint={data.get('sprint_id')}, stage={data.get('stage')})")
            else:
                print("Primary state: CORRUPT (checksum mismatch)")
        except (json.JSONDecodeError, OSError) as e:
            print(f"Primary state: CORRUPT ({e})")
    else:
        print("Primary state: MISSING")

    if STATE_BACKUP.exists():
        try:
            data = json.loads(STATE_BACKUP.read_text(encoding="utf-8"))
            errors = _validate_state_schema(data)
            backup_ok = len(errors) == 0
            if errors:
                print(f"Backup state: INVALID (schema errors: {errors})")
            else:
                print(f"Backup state: OK (sprint={data.get('sprint_id')}, stage={data.get('stage')})")
        except (json.JSONDecodeError, OSError) as e:
            print(f"Backup state: CORRUPT ({e})")
    else:
        print("Backup state: MISSING")

    if primary_ok:
        print("\nRecovery: Primary state is valid. No action needed.")
        return 0
    elif backup_ok:
        print("\nRecovery: Restoring from backup...")
        shutil.copy2(str(STATE_BACKUP), str(STATE_FILE))
        print("Done. Primary state restored from backup.")
        return 0
    else:
        # Try to rebuild from evidence
        print("\nRecovery: Both primary and backup are missing/corrupt.")
        print("Attempting to rebuild from evidence files...")
        rebuilt = _rebuild_state_from_evidence()
        if rebuilt:
            _save_state(rebuilt)
            print(f"Rebuilt state: sprint={rebuilt['sprint_id']}, stage={rebuilt['stage']}")
            return 0
        else:
            print("Cannot rebuild state. Run 'init --sprint-id <id>' to start fresh.")
            return 1


def _rebuild_state_from_evidence() -> dict | None:
    """Attempt to infer state from evidence files on disk."""
    if not EVIDENCE_ROOT.exists():
        return None

    # Find the most recent evidence directory
    candidates = [d for d in EVIDENCE_ROOT.iterdir() if d.is_dir()]
    if not candidates:
        return None

    latest = max(candidates, key=lambda d: d.stat().st_mtime)
    sprint_id = latest.name

    # Determine stage from what files exist
    has_stage3 = any(f.name.startswith("stage3-") for f in latest.iterdir())
    has_stage2 = any(f.name.startswith("stage2-") for f in latest.iterdir())
    has_stage1 = any(f.name.startswith("stage1-") for f in latest.iterdir())

    if has_stage3:
        stage = "P3"
    elif has_stage2:
        stage = "P3"  # Stage 2 done, should be on P3
    elif has_stage1:
        stage = "P2"  # Stage 1 done, should be on P2
    else:
        stage = "P1"

    return {
        "sprint_id": sprint_id,
        "stage": stage,
        "decision": None,
        "next_stage": None,
        "retry_count": 0,
        "compliance_score": None,
        "evidence_dir": str(latest),
        "started": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Subcommand: reset
# ---------------------------------------------------------------------------

def cmd_reset(args) -> int:
    """Clear state file."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    if STATE_BACKUP.exists():
        STATE_BACKUP.unlink()
    print("Sprint loop state cleared.")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: run-stage (single stage for scheduled mode)
# ---------------------------------------------------------------------------

def cmd_run_stage(args) -> int:
    """Execute one stage via claude CLI subprocess."""
    state = _load_state()
    if not state:
        print("ERROR: No active sprint loop. Run 'init' first.", file=sys.stderr)
        return 1

    stage = state["stage"]
    if stage in ("ACCEPTED", "BLOCKED", "ESCALATED"):
        print(f"Loop is in terminal state: {stage}. Nothing to do.")
        return 0

    evidence_dir = Path(state["evidence_dir"])
    prompt_id = STAGE_TO_PROMPT.get(stage)
    if not prompt_id:
        print(f"ERROR: Unknown stage {stage}", file=sys.stderr)
        return 1

    # Build the prompt message for claude CLI
    registry = _load_prompt_registry()
    entry = registry.get(prompt_id, {})
    prompt_file = entry.get("file", "")
    prompt_path = PROMPT_DIR / prompt_file

    if not prompt_path.exists():
        print(f"ERROR: Prompt file not found: {prompt_path}", file=sys.stderr)
        return 1

    retry_context = ""
    if state["retry_count"] > 0:
        retry_context = _build_retry_context(stage, evidence_dir, state["retry_count"])

    prompt_content = prompt_path.read_text(encoding="utf-8")
    cli_message = (
        f"Execute the following post-sprint loop stage: {stage}\n\n"
        f"Evidence directory: {evidence_dir}\n"
        f"Write all outputs to: {evidence_dir}\n\n"
        f"--- PROMPT START ---\n{prompt_content}\n--- PROMPT END ---\n"
    )
    if retry_context:
        cli_message += f"\n--- RETRY CONTEXT ---\n{retry_context}\n--- END RETRY CONTEXT ---\n"

    cli_message += (
        f"\n\nAfter producing outputs, run:\n"
        f"  .venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py validate {stage} --evidence-dir {evidence_dir}\n"
        f"  .venv/Scripts/python scripts/maintenance/supervisor/sprint_loop.py decide --evidence-dir {evidence_dir}\n"
    )

    print(f"Stage: {stage}")
    print(f"Prompt: {prompt_path}")
    print(f"Evidence dir: {evidence_dir}")
    print(f"Retry count: {state['retry_count']}")
    print(f"\n--- CLI Message (for claude --print) ---")
    print(cli_message)
    return 0


def _build_retry_context(stage: str, evidence_dir: Path, retry_count: int) -> str:
    """Build retry context with prior validation failures."""
    lines = [
        f"RETRY #{retry_count}: Previous attempt for stage {stage} produced non-conforming output.",
        "",
        "Required output files:",
    ]
    outputs = _get_required_outputs(stage)
    for f in outputs:
        exists = (evidence_dir / f).exists()
        status = "EXISTS" if exists else "MISSING"
        lines.append(f"  [{status}] {f}")

    if retry_count >= 2:
        lines.append("")
        lines.append("IMPORTANT: This is retry #2+. Produce ONLY the most critical missing files.")
        lines.append("You MUST produce YAML files, not prose. Use the skeleton templates if present.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subcommand: run-loop (full P1->P2->P3 unattended)
# ---------------------------------------------------------------------------

def cmd_run_loop(args) -> int:
    """Execute full P1->P2->P3 loop. Prints CLI invocation plan."""
    sprint_id = args.sprint_id
    if not sprint_id:
        state = _load_state()
        if state:
            sprint_id = state["sprint_id"]
        else:
            print("ERROR: No sprint-id provided and no active loop.", file=sys.stderr)
            return 1

    print(f"Full loop plan for sprint: {sprint_id}")
    print()
    print("The following commands should be executed in sequence:")
    print(f"  1. sprint_loop.py init --sprint-id {sprint_id}")
    print(f"  2. claude --print --dangerously-skip-permissions 'Run /post-sprint-loop for sprint {sprint_id}'")
    print(f"  3. sprint_loop.py validate P1")
    print(f"  4. sprint_loop.py decide")
    print(f"  5. claude --print --dangerously-skip-permissions 'Run /post-sprint-loop'  # picks up P2")
    print(f"  6. sprint_loop.py validate P2")
    print(f"  7. sprint_loop.py decide")
    print(f"  8. claude --print --dangerously-skip-permissions 'Run /post-sprint-loop'  # picks up P3")
    print(f"  9. sprint_loop.py validate P3 --repair")
    print(f" 10. sprint_loop.py decide")
    print(f" 11. sprint_loop.py bundle")
    print()
    print("Each 'decide' step updates state. If RETRY, repeat the claude step.")
    print("If ACCEPTED, the loop is complete. If BLOCKED, investigate.")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Post-sprint autonomy loop orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new sprint loop")
    p_init.add_argument("--sprint-id", required=True, help="Sprint identifier")

    # status
    subparsers.add_parser("status", help="Print current loop state")

    # inject-template
    p_inject = subparsers.add_parser("inject-template", help="Write skeleton YAML outputs for a stage")
    p_inject.add_argument("stage", help="Stage to inject templates for (P1/P2/P3)")
    p_inject.add_argument("--evidence-dir", default=None, help="Override evidence directory")

    # validate
    p_validate = subparsers.add_parser("validate", help="Check stage outputs exist and conform")
    p_validate.add_argument("stage", help="Stage to validate (P1/P2/P3)")
    p_validate.add_argument("--evidence-dir", default=None, help="Override evidence directory")
    p_validate.add_argument("--repair", action="store_true", help="Attempt auto-repair of common issues")

    # decide
    p_decide = subparsers.add_parser("decide", help="Run loop_controller and update state")
    p_decide.add_argument("--evidence-dir", default=None, help="Override evidence directory")

    # bundle
    subparsers.add_parser("bundle", help="Package evidence into ZIP")

    # recover
    subparsers.add_parser("recover", help="Restore state from backup or rebuild from evidence")

    # reset
    subparsers.add_parser("reset", help="Clear state file")

    # run-stage
    subparsers.add_parser("run-stage", help="Print single-stage CLI invocation for scheduled mode")

    # run-loop
    p_loop = subparsers.add_parser("run-loop", help="Print full loop CLI invocation plan")
    p_loop.add_argument("--sprint-id", default=None, help="Sprint identifier")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    cmd_map = {
        "init": cmd_init,
        "status": cmd_status,
        "inject-template": cmd_inject_template,
        "validate": cmd_validate,
        "decide": cmd_decide,
        "bundle": cmd_bundle,
        "recover": cmd_recover,
        "reset": cmd_reset,
        "run-stage": cmd_run_stage,
        "run-loop": cmd_run_loop,
    }
    handler = cmd_map.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
