"""
TC-S96-005: Tests for all 16 cleanroom JSON schemas.
Each schema must:
  - validate a nominal (correct) artifact (positive test)
  - reject an artifact missing required fields (negative test)
  - reject an artifact with an invalid enum value where applicable
"""

import json
import pathlib
import pytest

try:
    import jsonschema
    from jsonschema import validate, ValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_DIR = pathlib.Path(__file__).parent.parent.parent.parent / "data" / "schemas" / "cleanroom"

pytestmark = pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")


def load_schema(name: str) -> dict:
    path = SCHEMA_DIR / name
    assert path.exists(), f"Schema not found: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Nominal artifacts (valid instances)
# ---------------------------------------------------------------------------

NOMINAL = {
    "scope-manifest.schema.json": {
        "family": "cells",
        "subdomains": ["reference"],
        "locale": "en",
        "content_roots": {"reference": "content/reference.aspose.org/en/cells/java"},
        "_errors": []
    },
    "inspect-report.schema.json": {
        "run_id": "test-run-001",
        "family": "cells",
        "platform": "java",
        "subdomains": ["reference"],
        "ready": True,
        "blockers": [],
        "warnings": [],
        "generated_at": "2026-01-01T00:00:00Z"
    },
    "git-baseline.schema.json": {
        "run_id": "test-run-001",
        "baseline_git_sha": "abcdef1234567",
        "branch": "test/s96-pilot",
        "captured_at": "2026-01-01T00:00:00Z",
        "status_short": ""
    },
    "baseline-manifest.schema.json": {
        "run_id": "test-run-001",
        "baseline_git_sha": "abcdef1234567",
        "captured_at": "2026-01-01T00:00:00Z",
        "scope": {"family": "cells"},
        "files": {
            "content/reference.aspose.org/en/cells/java/Workbook.md": {
                "sha256": "abc123",
                "size_bytes": 1024
            }
        },
        "_errors": []
    },
    "run-state.schema.json": {
        "run_id": "test-run-001",
        "target": {"family": "cells", "platform": "java", "subdomains": ["reference"]},
        "baseline_git_sha": "abcdef1234567",
        "isolated_branch": "test/s96-pilot",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_modes": ["snapshot"],
        "resumable": True,
        "lock_status": "LOCKED"
    },
    "regeneration-log.schema.json": {
        "run_id": "test-run-001",
        "baseline_git_sha": "abcdef1234567",
        "generated_at": "2026-01-01T00:00:00Z",
        "replay_level": 1,
        "subdomain": "reference",
        "entries": [
            {
                "path": "content/reference.aspose.org/en/cells/java/Workbook.md",
                "outcome": "WRITTEN"
            }
        ]
    },
    "regeneration-plan.schema.json": {
        "run_id": "test-run-001",
        "baseline_git_sha": "abcdef1234567",
        "phase_a_complete": True,
        "entries": [
            {
                "planned_task_id": "task-001",
                "subdomain": "blog",
                "skill_id": "S-57",
                "target_path": "content/blog.aspose.org/cells/java/my-post/index.md",
                "skill_args": {},
                "status": "PLANNED"
            }
        ]
    },
    "agent-execution-ledger.schema.json": {
        "run_id": "test-run-001",
        "phase_a_complete": True,
        "phase_b_complete": True,
        "entries": [
            {
                "planned_task_id": "task-001",
                "subdomain": "blog",
                "skill_id": "S-57",
                "target_path": "content/blog.aspose.org/cells/java/my-post/index.md",
                "status": "COMPLETED",
                "output_files": ["content/blog.aspose.org/cells/java/my-post/index.md"],
                "verification_status": "VERIFIED"
            }
        ]
    },
    "agent-page-results.schema.json": {
        "run_id": "test-run-001",
        "results": [
            {
                "planned_task_id": "task-001",
                "target_path": "content/blog.aspose.org/cells/java/my-post/index.md",
                "status": "COMPLETED",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:01:00Z"
            }
        ]
    },
    "agent-failures.schema.json": {
        "run_id": "test-run-001",
        "failures": [
            {
                "planned_task_id": "task-002",
                "target_path": "content/blog.aspose.org/cells/java/other-post/index.md",
                "error": "Skill invocation timed out",
                "retry_hint": "Re-invoke S-57 with the same slug"
            }
        ]
    },
    "diff-report.schema.json": {
        "run_id": "test-run-001",
        "baseline_git_sha": "abcdef1234567",
        "generated_at": "2026-01-01T00:00:00Z",
        "counts": {"added": 0, "edited": 1, "deleted": 0, "unchanged": 5, "generated_identical": 0, "out_of_scope": 0, "churn_only": 0},
        "entries": [
            {
                "path": "content/reference.aspose.org/en/cells/java/Workbook.md",
                "category": "EDITED"
            }
        ]
    },
    "review-report.schema.json": {
        "run_id": "test-run-001",
        "baseline_git_sha": "abcdef1234567",
        "generated_at": "2026-01-01T00:00:00Z",
        "llm_review_used": False,
        "counts": {"good_keep": 1, "bad_revert": 0, "risky_review": 0, "unclear_needs_evidence": 0},
        "entries": [
            {
                "path": "content/reference.aspose.org/en/cells/java/Workbook.md",
                "verdict": "GOOD_KEEP",
                "reason": "All checks passed",
                "profile_used": "reference_page"
            }
        ]
    },
    "decision-ledger.schema.json": {
        "run_id": "test-run-001",
        "baseline_git_sha": "abcdef1234567",
        "generated_at": "2026-01-01T00:00:00Z",
        "counts": {"kept": 1, "reverted": 0, "deleted": 0, "pending_risky": 0, "pending_unclear": 0},
        "entries": [
            {
                "path": "content/reference.aspose.org/en/cells/java/Workbook.md",
                "verdict": "GOOD_KEEP",
                "action_taken": "KEPT",
                "result": "SUCCESS"
            }
        ]
    },
    "validator-report.schema.json": {
        "run_id": "test-run-001",
        "generated_at": "2026-01-01T00:00:00Z",
        "overall_passed": True,
        "validators": {
            "validate_frontmatter": {"passed": True, "exit_code": 0, "files_checked": 1, "failures": []},
            "audit": {"passed": True, "exit_code": 0, "files_checked": 1, "failures": []},
            "pytest": {"passed": True, "exit_code": 0}
        }
    },
    "test-report.schema.json": {
        "run_id": "test-run-001",
        "generated_at": "2026-01-01T00:00:00Z",
        "passed": True,
        "exit_code": 0,
        "summary": {"total": 100, "passed": 100, "failed": 0, "errors": 0, "skipped": 2}
    },
    "commit-readiness-report.schema.json": {
        "run_id": "test-run-001",
        "baseline_git_sha": "abcdef1234567",
        "generated_at": "2026-01-01T00:00:00Z",
        "status": "PASS",
        "checks": {
            "baseline_manifest_valid": True,
            "diff_report_valid": True,
            "review_report_complete": True,
            "no_bad_revert_on_disk": True,
            "no_unresolved_risky": True,
            "no_unresolved_unclear": True,
            "content_scope_clean": True,
            "frontmatter_valid": True,
            "audit_passed": True,
            "pytest_passed": True,
            "skill_run_record_exists": True,
            "no_out_of_scope_changes": True,
            "no_unaccepted_churn": True
        },
        "failed_checks": [],
        "scope": "cells/java [reference]",
        "n_kept": 5, "n_reverted": 1, "n_pending": 0,
        "n_added": 0, "n_edited": 5, "n_deleted": 1,
        "subdomains": ["reference"],
        "replay_level": 1,
        "skills_invoked": ["S-96", "S-62"],
        "commit_message_template": None
    },
}

ALL_SCHEMAS = list(SCHEMA_DIR.glob("*.schema.json")) if SCHEMA_DIR.exists() else []


@pytest.mark.parametrize("schema_name", [s.name for s in ALL_SCHEMAS])
def test_schema_file_exists_and_is_valid_json(schema_name):
    """Every schema file must be parseable as JSON."""
    schema = load_schema(schema_name)
    assert "$schema" in schema
    assert "type" in schema or "properties" in schema or "$ref" in schema


@pytest.mark.parametrize("schema_name,artifact", list(NOMINAL.items()))
def test_nominal_artifact_validates(schema_name, artifact):
    """Each schema must accept its nominal valid artifact."""
    schema = load_schema(schema_name)
    validate(instance=artifact, schema=schema)  # raises if invalid


@pytest.mark.parametrize("schema_name,artifact", list(NOMINAL.items()))
def test_missing_run_id_rejected(schema_name, artifact):
    """Each schema must reject an artifact missing run_id (where run_id is required)."""
    schema = load_schema(schema_name)
    required = schema.get("required", [])
    if "run_id" not in required:
        pytest.skip(f"{schema_name} does not require run_id")
    bad = dict(artifact)
    del bad["run_id"]
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=schema)


def test_diff_report_rejects_invalid_category():
    schema = load_schema("diff-report.schema.json")
    artifact = dict(NOMINAL["diff-report.schema.json"])
    artifact["entries"] = [{"path": "foo.md", "category": "INVALID_CATEGORY"}]
    with pytest.raises(ValidationError):
        validate(instance=artifact, schema=schema)


def test_review_report_rejects_invalid_verdict():
    schema = load_schema("review-report.schema.json")
    artifact = dict(NOMINAL["review-report.schema.json"])
    artifact["entries"] = [
        {"path": "foo.md", "verdict": "NOT_A_VERDICT", "reason": "x", "profile_used": "p"}
    ]
    with pytest.raises(ValidationError):
        validate(instance=artifact, schema=schema)


def test_decision_ledger_rejects_invalid_action():
    schema = load_schema("decision-ledger.schema.json")
    artifact = dict(NOMINAL["decision-ledger.schema.json"])
    artifact["entries"] = [
        {
            "path": "foo.md",
            "verdict": "GOOD_KEEP",
            "action_taken": "INVENTED_ACTION",
            "result": "SUCCESS"
        }
    ]
    with pytest.raises(ValidationError):
        validate(instance=artifact, schema=schema)


def test_commit_readiness_status_enum():
    schema = load_schema("commit-readiness-report.schema.json")
    artifact = dict(NOMINAL["commit-readiness-report.schema.json"])
    artifact["status"] = "MAYBE"
    with pytest.raises(ValidationError):
        validate(instance=artifact, schema=schema)


def test_run_state_lock_status_enum():
    schema = load_schema("run-state.schema.json")
    artifact = dict(NOMINAL["run-state.schema.json"])
    artifact["lock_status"] = "OPEN"
    with pytest.raises(ValidationError):
        validate(instance=artifact, schema=schema)


def test_regeneration_log_replay_level_enum():
    schema = load_schema("regeneration-log.schema.json")
    artifact = dict(NOMINAL["regeneration-log.schema.json"])
    artifact["replay_level"] = 3
    with pytest.raises(ValidationError):
        validate(instance=artifact, schema=schema)


def test_agent_execution_ledger_completed_requires_output_files():
    """COMPLETED status must have non-empty output_files."""
    schema = load_schema("agent-execution-ledger.schema.json")
    artifact = dict(NOMINAL["agent-execution-ledger.schema.json"])
    # COMPLETED with empty output_files should fail
    artifact["entries"] = [
        {
            "planned_task_id": "task-001",
            "subdomain": "blog",
            "skill_id": "S-57",
            "target_path": "content/blog.aspose.org/cells/java/my-post/index.md",
            "status": "COMPLETED",
            "output_files": [],
            "verification_status": "VERIFIED"
        }
    ]
    with pytest.raises(ValidationError):
        validate(instance=artifact, schema=schema)


def test_regeneration_plan_subdomain_reference_not_allowed():
    """regeneration-plan entries must not have subdomain=reference (reference runs via script, not agent plan)."""
    schema = load_schema("regeneration-plan.schema.json")
    artifact = dict(NOMINAL["regeneration-plan.schema.json"])
    artifact["entries"] = [
        {
            "planned_task_id": "task-001",
            "subdomain": "reference",
            "skill_id": "S-62",
            "target_path": "content/reference.aspose.org/en/cells/java/Workbook.md",
            "skill_args": {},
            "status": "PLANNED"
        }
    ]
    with pytest.raises(ValidationError):
        validate(instance=artifact, schema=schema)
