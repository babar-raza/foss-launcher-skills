"""Integration tests for refresh_run_bind_recovery.py (ST-126 recovery).

Uses a REAL temporary git repository rather than mocking git calls: this
tool's entire job is git plumbing correctness (read-tree/write-tree/
commit-tree/merge-base against real objects), which a mocked command_runner
cannot meaningfully exercise. Mirrors the live 2026-08-31 recovery of
rf-20260830T142825Z-b6ef66497683 (cells/typescript).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))
OPS_DIR = PIPELINE_DIR / "commands" / "ops"
if str(OPS_DIR) not in sys.path:
    sys.path.insert(0, str(OPS_DIR))

import refresh_run as rr
import refresh_run_bind_recovery as recovery
from commands.content.body_refresh import _frontmatter_hash, _normalized_body_hash


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


def _init_repo(root: Path) -> None:
    _git(["init", "-q"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)


def _make_stuck_run(tmp_path: Path, *, original_already_trailed: bool = False):
    """Build a real repo with: an initial commit, a 'content commit' that
    carries real changes but (by default) lacks the required trailers, and a
    refresh_run manifest/scope/extra_allowed sitting at READY_TO_COMMIT
    referencing it. Returns (base_sha, original_sha, run_id)."""
    rr.configure(repo_root=tmp_path, source_sha_resolver=lambda _f, _p: "a" * 40)
    _init_repo(tmp_path)
    page = tmp_path / "content" / "docs.aspose.org" / "en" / "pdf" / "net" / "page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("---\ntitle: Test\n---\n\nOriginal body.\n", encoding="utf-8", newline="\n")
    _git(["add", "-f", "content/docs.aspose.org/en/pdf/net/page.md"], tmp_path)
    base_sha = _git(["commit", "-m", "base"], tmp_path) and _git(["rev-parse", "HEAD"], tmp_path)

    page.write_text("---\ntitle: Test\n---\n\nRefreshed body.\n", encoding="utf-8", newline="\n")
    _git(["add", "-f", "content/docs.aspose.org/en/pdf/net/page.md"], tmp_path)
    message = "feat(pdf/net): refresh content\n"
    if original_already_trailed:
        message += (
            "\nRefresh-Run: RUN-1\nRefresh-Base: " + base_sha
            + "\nRefresh-Source-SHA: " + ("a" * 40) + "\n"
        )
    _git(["commit", "-m", message], tmp_path)
    original_sha = _git(["rev-parse", "HEAD"], tmp_path)

    run_id = "RUN-1"
    run_root = tmp_path / "reports" / "refresh_runs" / "pdf" / "net" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    now = "2026-08-31T00:00:00Z"
    manifest = {
        "schema_version": 3,
        "run_id": run_id,
        "family": "pdf",
        "platform": "net",
        "mode": "upstream",
        "state": "READY_TO_COMMIT",
        "session_owner": "session-1",
        "created_at": now,
        "updated_at": now,
        "base_commit_sha": base_sha,
        "initial_model_sha": "a" * 40,
        "initial_source_sha": "a" * 40,
        "target_model_sha": "a" * 40,
        "target_source_sha": "a" * 40,
        "scope": {
            "paths": ["content/docs.aspose.org/en/pdf/net/page.md"],
            "digest": "sha256:scope",
            "input_digest": "sha256:input",
        },
        "stage_checkpoints": {},
        "stage_attempt_refs": [],
        "stage_attempt_digests": {},
        "validation_attempt_refs": [],
        "validation_attempt_digests": {},
        "validation": {field: "PASS" for field in rr.VALIDATION_FIELDS},
        "observed_heads": [],
        "output_digests": {},
        "receipt_refs": [],
        "page_decision_ref": None,
        "commit_sha": None,
        "failure_reason": None,
    }
    (run_root / "extra_allowed_hashes.json").write_text("{}", encoding="utf-8")

    page_path = "content/docs.aspose.org/en/pdf/net/page.md"
    initial_hash = rr._path_hash(page_path)  # current (refreshed) disk content
    scope_path = run_root / "scope.json"
    scope_path.write_text(
        json.dumps({
            "schema_version": 1,
            "run_id": run_id,
            "family": "pdf",
            "platform": "net",
            "paths": manifest["scope"]["paths"],
            "initial_hashes": {page_path: initial_hash},
        }),
        encoding="utf-8",
    )
    manifest["scope"]["digest"] = rr._scope_digest(
        manifest["scope"]["paths"], manifest["scope"]["input_digest"]
    )

    receipts_dir = run_root / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / "RCP-001.yaml"
    receipt_path.write_text(
        yaml.safe_dump({
            "content_refresh_receipt": {
                "receipt_id": "RCP-001",
                "run_id": run_id,
                "page_path": page_path,
                "old_hash": rr._path_hash(page_path),
                "new_hash": rr._path_hash(page_path),
            }
        }, sort_keys=False),
        encoding="utf-8",
    )

    content = (tmp_path / page_path).read_text(encoding="utf-8")
    decisions_path = run_root / "page_decisions.jsonl"
    decision_row = {
        "schema_version": 1,
        "run_id": run_id,
        "page_path": page_path,
        "surface": "docs",
        "locale": "en",
        "intended_action": "BODY_UPDATE",
        "disposition": "BODY_UPDATED",
        "body_hash_before": "sha256:" + "0" * 64,
        "body_hash_after": _normalized_body_hash(content),
        "frontmatter_hash_before": _frontmatter_hash(content),
        "frontmatter_hash_after": _frontmatter_hash(content),
        "receipt_ref": "receipts/RCP-001.yaml",
        "receipt_digest": rr._file_digest(receipt_path),
        "evidence_claims_checked": [],
        "evidence_apis_checked": [],
        "validator_results": {"receipt": "PASS", "forbidden_claims": "PASS", "regrounding": "PASS"},
    }
    decisions_path.write_text(json.dumps(decision_row) + "\n", encoding="utf-8")

    manifest["receipt_refs"] = [str((receipts_dir / "RCP-001.yaml").relative_to(tmp_path)).replace("\\", "/")]
    manifest["page_decision_ref"] = str(decisions_path.relative_to(tmp_path)).replace("\\", "/")
    manifest["output_digests"]["scope"] = rr._file_digest(scope_path)
    manifest["output_digests"]["page_decisions"] = rr._file_digest(decisions_path)
    manifest["output_digests"]["receipts"] = "sha256:" + hashlib.sha256(
        f"{receipt_path.name}:{rr._file_digest(receipt_path)}".encode("utf-8")
    ).hexdigest()
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rr._set_active("pdf", "net", run_id)

    model_dir = tmp_path / "knowledge" / "pdf" / "net" / "merged"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.yaml").write_text(
        yaml.safe_dump({"repo_sha": "a" * 40, "stale_since": None}), encoding="utf-8",
    )

    return base_sha, original_sha, run_id


def test_build_shadow_commit_has_correct_trailers_and_real_diff(tmp_path: Path):
    base_sha, original_sha, run_id = _make_stuck_run(tmp_path)
    shadow_sha = recovery.build_shadow_commit(
        "pdf", "net", run_id, original_sha, repo_root=tmp_path,
    )

    message = _git(["show", "-s", "--format=%B", shadow_sha], tmp_path)
    trailers = rr._commit_trailer_values(message)
    assert trailers["Refresh-Run"] == [run_id]
    assert trailers["Refresh-Base"] == [base_sha]
    assert trailers["Refresh-Source-SHA"] == ["a" * 40]

    diff = _git(["diff-tree", "--no-commit-id", "--name-only", "-r", shadow_sha], tmp_path)
    assert diff.strip() == "content/docs.aspose.org/en/pdf/net/page.md"

    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, shadow_sha],
        cwd=str(tmp_path), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    assert ancestor.returncode == 0

    parent = _git(["rev-parse", f"{shadow_sha}^"], tmp_path)
    assert parent == _git(["rev-parse", f"{original_sha}^"], tmp_path)

    content = (tmp_path / "content/docs.aspose.org/en/pdf/net/page.md").read_text(encoding="utf-8")
    shown = _git(["show", f"{shadow_sha}:content/docs.aspose.org/en/pdf/net/page.md"], tmp_path)
    assert shown + "\n" == content or shown == content.rstrip("\n")


def test_shadow_commit_self_verification_matches_bind_commit_requirements(tmp_path: Path):
    """build_shadow_commit() runs its own self-verification (trailers + non-
    empty diff) before returning -- this proves that verification agrees
    with bind_commit()'s OWN independent trailer/diff-tree checks, i.e. the
    shadow commit built here is exactly what bind_commit requires. The full
    call into bind_commit() itself additionally requires knowledge-model
    freshness/clone-cache infrastructure this fixture does not replicate;
    that final hop was independently verified against the real repo during
    the live 2026-08-31 recovery of rf-20260830T142825Z-b6ef66497683
    (cells/typescript) this tool was built to generalize -- see ST-126."""
    base_sha, original_sha, run_id = _make_stuck_run(tmp_path)

    shadow_sha = recovery.build_shadow_commit(
        "pdf", "net", run_id, original_sha, repo_root=tmp_path,
    )

    manifest = rr._load_manifest("pdf", "net", run_id)
    resolved = _git(["rev-parse", f"{shadow_sha}^{{commit}}"], tmp_path)
    message = _git(["show", "-s", "--format=%B", resolved], tmp_path)
    required = {
        "Refresh-Run": run_id,
        "Refresh-Base": manifest["base_commit_sha"],
        "Refresh-Source-SHA": manifest["target_source_sha"],
    }
    trailers = rr._commit_trailer_values(message)
    for key, expected in required.items():
        assert trailers.get(key) == [expected]

    changed = _git(["diff-tree", "--no-commit-id", "--name-only", "-r", resolved], tmp_path)
    assert changed.strip()
    decision_rows = [
        json.loads(line)
        for line in (tmp_path / manifest["page_decision_ref"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected_changed = {
        row["page_path"] for row in decision_rows
        if row.get("disposition") in {"BODY_UPDATED", "EVIDENCE_ONLY", "GENERATED", "RETIRED"}
    }
    assert expected_changed <= set(changed.splitlines())


def test_refuses_when_original_already_trailed(tmp_path: Path):
    base_sha, original_sha, run_id = _make_stuck_run(
        tmp_path, original_already_trailed=True
    )
    with pytest.raises(recovery.RecoveryError, match="already carries all 3"):
        recovery.build_shadow_commit("pdf", "net", run_id, original_sha, repo_root=tmp_path)


def test_refuses_when_run_not_ready_to_commit(tmp_path: Path):
    base_sha, original_sha, run_id = _make_stuck_run(tmp_path)
    run_root = tmp_path / "reports" / "refresh_runs" / "pdf" / "net" / run_id
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    manifest["state"] = "VALIDATING"
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(recovery.RecoveryError, match="READY_TO_COMMIT"):
        recovery.build_shadow_commit("pdf", "net", run_id, original_sha, repo_root=tmp_path)


def test_refuses_when_original_predates_base(tmp_path: Path):
    """A commit that does NOT descend from the run's own base_commit_sha is
    the wrong commit for this run entirely -- must be rejected, not silently
    'recovered' against unrelated history."""
    base_sha, original_sha, run_id = _make_stuck_run(tmp_path)
    # Point the manifest's base_commit_sha at an unrelated commit (not an
    # ancestor of original_sha) to simulate the wrong run being cited.
    other = tmp_path / "unrelated.txt"
    other.write_text("x", encoding="utf-8")
    _git(["add", "-f", "unrelated.txt"], tmp_path)
    _git(["commit", "-m", "unrelated"], tmp_path)
    bogus_base = _git(["rev-parse", "HEAD"], tmp_path)
    run_root = tmp_path / "reports" / "refresh_runs" / "pdf" / "net" / run_id
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    manifest["base_commit_sha"] = bogus_base
    (run_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(recovery.RecoveryError, match="does not descend"):
        recovery.build_shadow_commit("pdf", "net", run_id, original_sha, repo_root=tmp_path)
