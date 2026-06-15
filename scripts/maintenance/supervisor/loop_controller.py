"""
loop_controller.py -- Post-sprint autonomy loop controller.

Reads stage outputs from an evidence directory, classifies the Prompt 3
summary, validates evidence bundle completeness, checks quality scores,
and produces a loop decision (ACCEPT / RETRY / BLOCK / ESCALATE).

Exit codes:
  0  Decision computed successfully (any classification)
  1  Fatal error (missing evidence-dir, parse failure, internal exception)
  2  Contradictory evidence detected (fail-closed sentinel)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _common import REPO_ROOT, base_args, safe_emit


# ---------------------------------------------------------------------------
# Classification enum
# ---------------------------------------------------------------------------

class LoopClassification(str, Enum):
    STRUCTURED_ALL_GREEN = "STRUCTURED_ALL_GREEN"
    STRUCTURED_NOT_GREEN = "STRUCTURED_NOT_GREEN"
    PROSE_ONLY = "PROSE_ONLY"
    MISSING = "MISSING"
    CONTRADICTORY = "CONTRADICTORY"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    SCORES_MISSING = "SCORES_MISSING"
    TASKCARDS_INCOMPLETE = "TASKCARDS_INCOMPLETE"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"


# ---------------------------------------------------------------------------
# YAML parser (minimal, no PyYAML dependency required)
# ---------------------------------------------------------------------------

def _try_parse_yaml(path: Path) -> dict | None:
    """Parse a YAML file into a dict. Returns None on failure."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        import yaml
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
        return None
    except ImportError:
        pass
    except Exception:
        return None
    try:
        return _minimal_yaml_parse(text)
    except Exception:
        return None


def _minimal_yaml_parse(text: str) -> dict | None:
    """Minimal YAML parser for the expected summary schema."""
    result = {}
    current_key = None
    current_list = None
    current_dict = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        if indent == 0 and ":" in stripped:
            if current_key and current_list is not None:
                result[current_key] = current_list
            elif current_key and current_dict is not None:
                result[current_key] = current_dict
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            current_list = None
            current_dict = None
            if val:
                result[key] = _parse_scalar(val)
                current_key = None
            else:
                current_key = key
        elif current_key and stripped.startswith("- "):
            if current_list is None:
                current_list = []
            item_text = stripped[2:].strip()
            if ":" in item_text:
                item_dict = {}
                k, _, v = item_text.partition(":")
                item_dict[k.strip()] = _parse_scalar(v.strip())
                current_list.append(item_dict)
            else:
                current_list.append(_parse_scalar(item_text))
        elif current_key and ":" in stripped and indent > 0:
            if current_dict is None:
                current_dict = {}
            k, _, v = stripped.partition(":")
            current_dict[k.strip()] = _parse_scalar(v.strip())

    if current_key:
        if current_list is not None:
            result[current_key] = current_list
        elif current_dict is not None:
            result[current_key] = current_dict

    return result if result else None


def _parse_scalar(val: str):
    """Parse a YAML scalar value."""
    if not val or val == "~" or val.lower() == "null":
        return None
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    try:
        return int(val)
    except ValueError:
        pass
    if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
        return val[1:-1]
    return val


# ---------------------------------------------------------------------------
# Summary classifier
# ---------------------------------------------------------------------------

def classify_summary(
    evidence_dir: Path,
    quality_threshold: int = 4,
) -> tuple[LoopClassification, dict]:
    """Parse stage3-final-sprint-summary.yaml and classify it."""
    summary_path = evidence_dir / "stage3-final-sprint-summary.yaml"
    details: dict = {"summary_path": str(summary_path), "warnings": []}

    data = _try_parse_yaml(summary_path)
    if data is None:
        return LoopClassification.MISSING, details

    details["parsed_data"] = data

    if "outcome" not in data:
        return LoopClassification.PROSE_ONLY, details

    outcome = str(data["outcome"]).upper()
    details["outcome"] = outcome

    scores = data.get("scores")
    if not scores or not isinstance(scores, dict) or len(scores) == 0:
        return LoopClassification.SCORES_MISSING, details
    details["scores"] = scores

    evidence_files = data.get("evidence_files")
    if not evidence_files or not isinstance(evidence_files, list) or len(evidence_files) == 0:
        return LoopClassification.EVIDENCE_MISSING, details

    missing_files = []
    for ef in evidence_files:
        if not (evidence_dir / ef).exists():
            missing_files.append(str(ef))
    if missing_files:
        details["missing_evidence_files"] = missing_files
        return LoopClassification.EVIDENCE_MISSING, details
    details["evidence_files_verified"] = True

    taskcards = data.get("taskcards")
    if not taskcards or not isinstance(taskcards, list):
        return LoopClassification.TASKCARDS_INCOMPLETE, details
    for tc in taskcards:
        if not isinstance(tc, dict) or "status" not in tc:
            return LoopClassification.TASKCARDS_INCOMPLETE, details
    details["taskcards"] = taskcards

    if outcome == "BLOCKED":
        return LoopClassification.BLOCKED_EXTERNAL, details

    if outcome == "ALL_GREEN":
        failing_scores = {
            k: v for k, v in scores.items()
            if isinstance(v, (int, float)) and v < quality_threshold
        }
        if failing_scores:
            details["contradictory_scores"] = failing_scores
            return LoopClassification.CONTRADICTORY, details

        failed_taskcards = [
            tc for tc in taskcards
            if isinstance(tc, dict) and str(tc.get("status", "")).upper()
            in ("REROUTED", "BLOCKED_EXTERNAL", "FAILED")
        ]
        if failed_taskcards:
            details["contradictory_taskcards"] = failed_taskcards
            return LoopClassification.CONTRADICTORY, details

    if outcome == "ALL_GREEN":
        all_pass = all(
            isinstance(v, (int, float)) and v >= quality_threshold
            for v in scores.values()
        )
        if all_pass:
            return LoopClassification.STRUCTURED_ALL_GREEN, details

    return LoopClassification.STRUCTURED_NOT_GREEN, details


# ---------------------------------------------------------------------------
# Evidence bundle validator
# ---------------------------------------------------------------------------

def validate_evidence_bundle(
    evidence_dir: Path,
    evidence_files: list[str] | None,
) -> tuple[bool, list[str]]:
    """Check that every declared evidence file exists on disk."""
    if not evidence_files:
        return False, ["no_evidence_declared"]
    missing = []
    for ef in evidence_files:
        if not (evidence_dir / ef).exists():
            missing.append(ef)
    return len(missing) == 0, missing


# ---------------------------------------------------------------------------
# Quality score checker
# ---------------------------------------------------------------------------

def check_quality_scores(
    scores: dict | None,
    threshold: int = 4,
) -> tuple[bool, list[str]]:
    """Validate all dimension scores meet the threshold."""
    if not scores or not isinstance(scores, dict) or len(scores) == 0:
        return False, ["no_scores_provided"]
    failing = []
    for dim, score in scores.items():
        if not isinstance(score, (int, float)) or score < threshold:
            failing.append(dim)
    return len(failing) == 0, failing


# ---------------------------------------------------------------------------
# Decision engine (rule-based)
# ---------------------------------------------------------------------------

_NEXT_STAGE = {
    LoopClassification.MISSING: "prompt1 -> prompt2 -> prompt3",
    LoopClassification.PROSE_ONLY: "prompt2 -> prompt3",
    LoopClassification.SCORES_MISSING: "quality_scoring",
    LoopClassification.EVIDENCE_MISSING: "evidence_collection",
    LoopClassification.TASKCARDS_INCOMPLETE: "prompt2",
    LoopClassification.BLOCKED_EXTERNAL: "blocker_packaging",
    LoopClassification.CONTRADICTORY: None,
    LoopClassification.STRUCTURED_NOT_GREEN: "prompt2 -> prompt3",
}

_DEFAULT_MAX_RETRIES = 2


def compute_decision(
    classification: LoopClassification,
    evidence_complete: bool,
    scores_pass: bool,
    retry_count: int = 0,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> dict:
    """Map classification + checks to a loop decision."""

    if classification == LoopClassification.CONTRADICTORY:
        return {
            "action": "BLOCK",
            "reason": "Evidence contradicts claimed outcome",
            "next_stage": None,
            "retry_count": retry_count,
            "max_retries": max_retries,
        }

    if classification == LoopClassification.BLOCKED_EXTERNAL:
        return {
            "action": "BLOCK",
            "reason": "External dependency prevents progress",
            "next_stage": "blocker_packaging",
            "retry_count": retry_count,
            "max_retries": max_retries,
        }

    if classification == LoopClassification.STRUCTURED_ALL_GREEN:
        if evidence_complete and scores_pass:
            return {
                "action": "ACCEPT",
                "reason": "All quality dimensions pass, evidence bundle complete",
                "next_stage": "adversarial_review",
                "retry_count": retry_count,
                "max_retries": max_retries,
            }
        if not evidence_complete:
            ns, reason = "evidence_collection", "Outcome green but evidence incomplete"
        else:
            ns, reason = "prompt3_rework", "Outcome green but scores below threshold"
        action = "RETRY" if retry_count < max_retries else "ESCALATE"
        return {
            "action": action,
            "reason": reason + (" (retry limit exceeded)" if action == "ESCALATE" else ""),
            "next_stage": ns if action == "RETRY" else None,
            "retry_count": retry_count,
            "max_retries": max_retries,
        }

    action = "RETRY" if retry_count < max_retries else "ESCALATE"
    next_stage = _NEXT_STAGE.get(classification, "prompt2 -> prompt3")
    reason = f"Classification: {classification.value}"
    return {
        "action": action,
        "reason": reason + (" (retry limit exceeded)" if action == "ESCALATE" else ""),
        "next_stage": next_stage if action == "RETRY" else None,
        "retry_count": retry_count,
        "max_retries": max_retries,
    }


# ---------------------------------------------------------------------------
# Top-level function
# ---------------------------------------------------------------------------

def loop_control(
    evidence_dir: str | Path,
    run_id: str | None = None,
    quality_threshold: int = 4,
    dry_run: bool = True,
    repo_root: str | Path | None = None,
) -> tuple[dict, int]:
    """Post-sprint autonomy loop controller.

    Returns (trace_dict, exit_code).
    """
    evidence_path = Path(evidence_dir).resolve()
    if not evidence_path.exists():
        return {
            "status": "FATAL_ERROR",
            "error": f"Evidence directory does not exist: {evidence_path}",
            "warnings": [],
        }, 1

    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    rr = Path(repo_root) if repo_root else REPO_ROOT

    classification, details = classify_summary(evidence_path, quality_threshold)

    parsed = details.get("parsed_data", {}) or {}
    scores = parsed.get("scores") if isinstance(parsed, dict) else None
    ev_files = parsed.get("evidence_files") if isinstance(parsed, dict) else None

    ev_complete, ev_missing = validate_evidence_bundle(evidence_path, ev_files)
    scores_pass, failing_dims = check_quality_scores(scores, quality_threshold)

    retry_count = int(parsed.get("retry_count", 0)) if isinstance(parsed, dict) else 0

    decision = compute_decision(
        classification, ev_complete, scores_pass,
        retry_count=retry_count, max_retries=_DEFAULT_MAX_RETRIES,
    )

    yaml_path = None
    if not dry_run:
        output_dir = rr / "reports" / "supervisor"
        output_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = output_dir / f"loop-decision-{run_id}.yaml"
        content = json.dumps({
            "loop_decision": {
                "classification": classification.value,
                "action": decision["action"],
                "reason": decision["reason"],
                "next_stage": decision["next_stage"],
                "retry_count": decision["retry_count"],
                "max_retries": decision["max_retries"],
                "evidence_dir": str(evidence_path),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "evidence_validation": {"complete": ev_complete, "missing": ev_missing},
            "quality_check": {"all_pass": scores_pass, "failing_dimensions": failing_dims},
        }, indent=2, default=str)
        yaml_path.write_text(content, encoding="utf-8")

    trace = {
        "run_id": run_id,
        "classification": classification.value,
        "decision": decision,
        "evidence_validation": {"complete": ev_complete, "missing": ev_missing},
        "quality_check": {"all_pass": scores_pass, "failing_dimensions": failing_dims},
        "warnings": details.get("warnings", []),
        "status": "LOOP_COMPLETE" if decision["action"] != "BLOCK" else "LOOP_BLOCKED",
        "yaml_path": str(yaml_path) if yaml_path else None,
    }

    exit_code = 2 if classification == LoopClassification.CONTRADICTORY else 0
    return trace, exit_code


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = base_args("Post-sprint autonomy loop controller")
    parser.add_argument("--evidence-dir", type=str, required=True,
                        help="Path to evidence directory containing stage outputs")
    parser.add_argument("--run-id", type=str, default=None,
                        help="Run ID (default: auto-generated timestamp)")
    parser.add_argument("--quality-threshold", type=int, default=4,
                        help="Min required score per dimension (1-5, default: 4)")
    args = parser.parse_args()

    dry_run = not args.execute
    trace, exit_code = loop_control(
        evidence_dir=args.evidence_dir,
        run_id=args.run_id,
        quality_threshold=args.quality_threshold,
        dry_run=dry_run,
    )

    if args.output:
        safe_emit(trace, args.output, dry_run=False)
    else:
        print(json.dumps(trace, indent=2, default=str))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
