"""Tests for post_refresh_verify.py — progress tracking and verification gate.

Coverage:
- record_step(): step written to progress.json; duplicate steps not added twice
- record_step(): progress.json created on first call
- verify() check 1: model.yaml stale_since=null → passes
- verify() check 1: model.yaml stale_since set → fails
- verify() check 2: orphaned claim IDs → reported as failure
- verify() check 3: stale reference pages (API class absent) → reported
- verify() check 4: stale_detect subprocess (mocked)
- verify() returns (True, []) on all-clean state
"""
from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

import post_refresh_verify


# ---------------------------------------------------------------------------
# Path isolation fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    """Redirect all module-level paths to tmp_path for each test.

    REPORTS_ROOT is explicitly set to tmp_path/refresh_state (not
    tmp_path/reports/refresh_state) to match existing test assertions.
    _HERE is set to a non-existent sub-path so stale_detect.py is not
    found by default; override with configure(here=tmp_path) when needed.
    """
    post_refresh_verify.configure(
        repo_root=tmp_path,
        reports_root=tmp_path / "refresh_state",
        here=tmp_path / "_nonexistent_scripts",
    )
    yield
    post_refresh_verify.configure()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_knowledge(tmp_path: Path, family: str, platform: str, **kwargs) -> Path:
    """Write a minimal knowledge tree for testing. Returns merged/ dir."""
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)

    if "stale_since" in kwargs:
        model = {"stale_since": kwargs["stale_since"], "version": "1.0"}
    else:
        model = {"stale_since": None, "version": "1.0"}
    (merged / "model.yaml").write_text(yaml.dump(model), encoding="utf-8")

    claims = kwargs.get("claims", [])
    (merged / "claims.json").write_text(
        json.dumps(claims, indent=2), encoding="utf-8"
    )

    api_surface = kwargs.get("api_surface", [])
    (merged / "api_surface.json").write_text(
        json.dumps(api_surface, indent=2), encoding="utf-8"
    )
    return merged


# ---------------------------------------------------------------------------
# record_step tests
# ---------------------------------------------------------------------------

class TestRecordStep:
    def test_step_written_to_progress_json(self, tmp_path):
        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        assert p.exists()
        data = json.loads(p.read_text())
        assert "knowledge_refresh" in data["steps"]

    def test_duplicate_step_not_added_twice(self, tmp_path):
        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")
        post_refresh_verify.record_step("3d", "python", "knowledge_refresh")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        data = json.loads(p.read_text())
        assert data["steps"].count("knowledge_refresh") == 1

    def test_multiple_steps_all_recorded(self, tmp_path):
        post_refresh_verify.record_step("3d", "python", "step_a")
        post_refresh_verify.record_step("3d", "python", "step_b")
        post_refresh_verify.record_step("3d", "python", "step_c")

        p = tmp_path / "refresh_state" / "3d" / "python" / "progress.json"
        data = json.loads(p.read_text())
        assert set(data["steps"]) == {"step_a", "step_b", "step_c"}


# ---------------------------------------------------------------------------
# verify() — check 1: model.yaml stale_since
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleSince:
    def test_stale_since_null_passes(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python", stale_since=None)
        passed, failures = post_refresh_verify.verify("3d", "python")
        stale_failures = [f for f in failures if "stale_since" in f]
        assert len(stale_failures) == 0

    def test_stale_since_set_fails(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python", stale_since="2026-04-01")
        passed, failures = post_refresh_verify.verify("3d", "python")
        assert any("stale_since" in f for f in failures)

    def test_unparseable_model_yaml_is_unknown_not_fail(self, tmp_path):
        """RPR-J-06: a corrupt model.yaml proves nothing about staleness --
        UNKNOWN, not a fabricated FAIL."""
        merged = tmp_path / "knowledge" / "3d" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text("{ not: valid: yaml: [", encoding="utf-8")
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("3d", "python", unknowns_out=unknowns)
        assert not any("Check 1" in f for f in failures)
        assert any("Check 1" in u for u in unknowns)


# ---------------------------------------------------------------------------
# verify() — check 2: orphaned claims
# ---------------------------------------------------------------------------

class TestVerifyCheckOrphanedClaims:
    def test_valid_citations_pass(self, tmp_path):
        claims = [{"claim_id": "CL-001"}, {"claim_id": "CL-002"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CL-001\n    - CL-002\n---\nbody\n"
        )

        passed, failures = post_refresh_verify.verify("3d", "python")
        orphan_failures = [f for f in failures if "Orphaned" in f]
        assert len(orphan_failures) == 0

    def test_orphaned_claim_reported(self, tmp_path):
        claims = [{"claim_id": "CL-001"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CL-999\n---\nbody\n"
        )

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert any("Orphaned" in f for f in failures)

    def test_orphaned_tier1_clm_claim_still_fails(self, tmp_path):
        """RPR-J-07: a missing Tier-1 (CLM-*) claim_id is a real signal and
        must still block, unchanged."""
        claims = [{"claim_id": "CLM-3d-aaaa1111"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CLM-3d-deadbeef\n---\nbody\n"
        )

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert any("Orphaned" in f and "CLM-3d-deadbeef" in f for f in failures)

    def test_orphaned_tier2_erc_claim_does_not_fail(self, tmp_path):
        """RPR-J-07: a missing Tier-2 (ERC-*) claim_id is expected enrichment
        churn -- it must NOT appear in failures (non-blocking)."""
        claims = [{"claim_id": "CLM-3d-aaaa1111"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - ERC-3d-python-deadbeef\n---\nbody\n"
        )

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert not any("Orphaned" in f for f in failures)

    def test_mixed_tier1_and_tier2_orphaned_claims_only_tier1_fails(self, tmp_path):
        claims = [{"claim_id": "CLM-3d-aaaa1111"}]
        _setup_knowledge(tmp_path, "3d", "python", claims=claims)

        content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "3d" / "python"
        content_dir.mkdir(parents=True)
        (content_dir / "page.md").write_text(
            "---\nevidence:\n  claims:\n    - CLM-3d-deadbeef\n    - ERC-3d-python-deadbeef\n---\nbody\n"
        )

        passed, failures = post_refresh_verify.verify("3d", "python")
        orphan_failures = [f for f in failures if "Orphaned" in f]
        assert len(orphan_failures) == 1
        assert "CLM-3d-deadbeef" in orphan_failures[0]
        assert "ERC-3d-python-deadbeef" not in orphan_failures[0]


# ---------------------------------------------------------------------------
# verify() — check 4: stale_detect subprocess (mocked)
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleDetect:
    def test_stale_detect_exit_0_passes(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")

        # Create fake stale_detect.py at tmp_path and point _HERE there
        (tmp_path / "stale_detect.py").touch()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"stale_pages": 0})
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            here=tmp_path,
            subprocess_run=lambda *a, **kw: mock_result,
        )

        passed, failures = post_refresh_verify.verify("3d", "python")

        stale_failures = [f for f in failures if "stale_detect" in f.lower()]
        assert len(stale_failures) == 0

    def test_stale_detect_exit_1_reports_failure(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")

        (tmp_path / "stale_detect.py").touch()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps({"stale_pages": 3, "pages": []})
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            here=tmp_path,
            subprocess_run=lambda *a, **kw: mock_result,
        )

        passed, failures = post_refresh_verify.verify("3d", "python")

        assert any("stale_detect" in f.lower() for f in failures)

    def test_stale_detect_timeout_is_unknown_not_fail(self, tmp_path):
        """RPR-J-06: a timeout proves nothing about staleness -- UNKNOWN."""
        _setup_knowledge(tmp_path, "3d", "python")
        (tmp_path / "stale_detect.py").touch()

        def _raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="stale_detect.py", timeout=60)

        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            here=tmp_path, subprocess_run=_raise_timeout,
        )
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("3d", "python", unknowns_out=unknowns)
        assert not any("stale_detect" in f.lower() for f in failures)
        assert any("Check 4" in u for u in unknowns)

    def test_stale_detect_unparseable_output_is_unknown_not_fail(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")
        (tmp_path / "stale_detect.py").touch()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "not valid json {{{"
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            here=tmp_path, subprocess_run=lambda *a, **kw: mock_result,
        )
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("3d", "python", unknowns_out=unknowns)
        assert not any("stale_detect" in f.lower() for f in failures)
        assert any("Check 4" in u for u in unknowns)


# ---------------------------------------------------------------------------
# verify() — check 9 (RPR-F-03, S-111): triage_confirm Layer 2 scan
#
# Regression context: prior to RPR-F-03, triage_confirm.py had no CLI at all,
# so no gate anywhere in --verify could invoke it. These tests prove Check 9
# actually blocks on triage_confirm reporting stale pages, and correctly
# distinguishes "no knowledge yet" (SKIP) from "ran and found something" (FAIL)
# from "ran clean" (PASS) — mirroring TestVerifyCheckStaleDetect's mock pattern.
# ---------------------------------------------------------------------------

class TestVerifyCheck10FrontmatterOnly:
    """Check 10 (RPR-F-04): frontmatter-only grade regressions among updated pages."""

    def _write_progress(self, tmp_path, pages_updated):
        refresh_dir = tmp_path / "refresh_state" / "pdf" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"schema_version": 2, "steps": ["page_update"], "pages_updated": pages_updated}),
            encoding="utf-8",
        )

    def test_blocks_on_frontmatter_only_grade_regression(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/kb.aspose.org/en/pdf/net/faq.md"])

        fake_violation = [{"path": "content/kb.aspose.org/en/pdf/net/faq.md",
                           "grade_before": "A", "grade_after": "C"}]
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_grade_regressions=lambda *a, **kw: fake_violation,
        )
        passed, failures = post_refresh_verify.verify("pdf", "net")

        c10 = [f for f in failures if "Check 10" in f]
        assert len(c10) == 1
        assert "A->C" in c10[0]
        assert passed is False

    def test_passes_when_no_regressions(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/docs.aspose.org/en/pdf/net/p.md"])
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_grade_regressions=lambda *a, **kw: [],
        )
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 10" in f for f in failures)

    def test_skips_when_no_updated_pages(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, [])
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 10" in f for f in failures)  # SKIP, not a failure

    def test_detection_exception_is_unknown_not_silent_skip(self, tmp_path):
        """RPR-J-06: pages WERE updated (this check was applicable), but the
        detection itself raised -- UNKNOWN, not a print-only SKIP that leaves
        the caller with no signal at all."""
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/kb.aspose.org/en/pdf/net/faq.md"])

        def _raise(*a, **kw):
            raise RuntimeError("git show failed")

        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_grade_regressions=_raise,
        )
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("pdf", "net", unknowns_out=unknowns)
        assert not any("Check 10" in f for f in failures)
        assert any("Check 10" in u for u in unknowns)

    def test_old_schema_progress_is_unknown_not_silent_skip(self, tmp_path):
        """RPR-J-08: progress.json exists and parses, but predates
        schema_version -- UNKNOWN, not a silent SKIP that reads its shape as
        'nothing updated' and lets a real check quietly not run."""
        _setup_knowledge(tmp_path, "pdf", "net")
        refresh_dir = tmp_path / "refresh_state" / "pdf" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"steps": ["page_update"], "pages_updated": ["content/kb.aspose.org/en/pdf/net/faq.md"]}),
            encoding="utf-8",
        )  # deliberately no schema_version key
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("pdf", "net", unknowns_out=unknowns)
        assert not any("Check 10" in f for f in failures)
        assert any("Check 10" in u and "schema_version" in u for u in unknowns)


class TestVerifyCheck11SeoStability:
    """Check 11 (RPR-F-05): undeclared title/H1/slug/canonical changes block."""

    def _write_progress(self, tmp_path, pages_updated):
        refresh_dir = tmp_path / "refresh_state" / "pdf" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"schema_version": 2, "steps": ["page_update"], "pages_updated": pages_updated}),
            encoding="utf-8",
        )

    def test_blocks_on_undeclared_seo_change(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/docs.aspose.org/en/pdf/net/p.md"])
        fake = [{"page": "content/docs.aspose.org/en/pdf/net/p.md",
                 "changed_fields": ["slug"], "before": {"slug": "a"}, "after": {"slug": "b"}}]
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_seo_violations=lambda *a, **kw: fake,
        )
        passed, failures = post_refresh_verify.verify("pdf", "net")
        c11 = [f for f in failures if "Check 11" in f]
        assert len(c11) == 1
        assert "slug" in c11[0]
        assert passed is False

    def test_passes_when_no_seo_changes(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/docs.aspose.org/en/pdf/net/p.md"])
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_seo_violations=lambda *a, **kw: [],
        )
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 11" in f for f in failures)

    def test_skips_when_no_updated_pages(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, [])
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 11" in f for f in failures)  # SKIP, not a failure

    def test_detection_exception_is_unknown_not_silent_pass(self, tmp_path):
        """RPR-J-06: pages WERE updated (this check was applicable), but the
        detection itself raised -- that's UNKNOWN, not a silently-swallowed
        SKIP that leaves passed=True unexamined."""
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_progress(tmp_path, ["content/docs.aspose.org/en/pdf/net/p.md"])

        def _raise(*a, **kw):
            raise RuntimeError("git show failed")

        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            detect_seo_violations=_raise,
        )
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("pdf", "net", unknowns_out=unknowns)
        assert not any("Check 11" in f for f in failures)
        assert any("Check 11" in u for u in unknowns)

    def test_old_schema_progress_is_unknown_not_silent_skip(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        refresh_dir = tmp_path / "refresh_state" / "pdf" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"steps": ["page_update"], "pages_updated": ["content/docs.aspose.org/en/pdf/net/p.md"]}),
            encoding="utf-8",
        )  # deliberately no schema_version key
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("pdf", "net", unknowns_out=unknowns)
        assert not any("Check 11" in f for f in failures)
        assert any("Check 11" in u and "schema_version" in u for u in unknowns)


class TestVerifyCheck9TriageConfirm:
    def _configure_with_real_script_path(self, tmp_path, subprocess_run=None):
        """Point triage_confirm_script at a real (touched) file under tmp_path,
        matching Check 9's REPO_ROOT/scripts/pipeline/lib/triage_confirm.py
        construction so is_file() finds it under the test sandbox."""
        script_dir = tmp_path / "scripts" / "pipeline" / "lib"
        script_dir.mkdir(parents=True, exist_ok=True)
        (script_dir / "triage_confirm.py").touch()
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            here=tmp_path,
            subprocess_run=subprocess_run,
        )

    def test_exit_0_passes(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"stale_count": 0})
        self._configure_with_real_script_path(tmp_path, subprocess_run=lambda *a, **kw: mock_result)

        passed, failures = post_refresh_verify.verify("3d", "python")

        assert not any("Check 9" in f for f in failures)

    def test_run_bound_check_9_receives_exact_scope(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        captured: list[str] = []
        mock_result = MagicMock(returncode=0, stdout='{"stale_count": 0}')

        def capture(args, **_kwargs):
            captured.extend(args)
            return mock_result

        self._configure_with_real_script_path(
            tmp_path,
            subprocess_run=capture,
        )
        page = "content/docs.aspose.org/en/pdf/net/only.md"
        run_root = (
            tmp_path / "reports/refresh_runs/pdf/net/RUN-SCOPED-TRIAGE"
        )
        (run_root / "receipts").mkdir(parents=True)
        raw = yaml.safe_dump(
            {
                "content_refresh_receipt": {
                    "receipt_id": "RCP-SCOPED",
                    "run_id": "RUN-SCOPED-TRIAGE",
                    "page_path": page,
                    "locale": "en",
                    "change_ids": [],
                    "strategy_used": "SURGICAL_CLAIM_REPLACEMENT",
                    "old_hash": "sha256:" + "1" * 64,
                    "new_hash": "sha256:" + "1" * 64,
                    "verdict": "NO_ACTIONABLE_SECTIONS",
                    "generated_at": "2026-07-25T00:00:00Z",
                }
            },
            sort_keys=False,
        ).encode("utf-8")
        (run_root / "receipts/RCP-SCOPED.yaml").write_bytes(raw)
        decision = {
            "schema_version": 1,
            "run_id": "RUN-SCOPED-TRIAGE",
            "page_path": page,
            "surface": "docs",
            "locale": "en",
            "intended_action": "BODY_UPDATE",
            "disposition": "NOT_AFFECTED",
            "body_hash_before": "sha256:before",
            "body_hash_after": "sha256:before",
            "frontmatter_hash_before": "sha256:fm",
            "frontmatter_hash_after": "sha256:fm",
            "receipt_ref": "receipts/RCP-SCOPED.yaml",
            "receipt_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "evidence_claims_checked": [],
            "evidence_apis_checked": [],
            "validator_results": {
                "receipt": "PASS",
                "forbidden_claims": "PASS",
                "regrounding": "PASS",
            },
        }
        (run_root / "page_decisions.jsonl").write_text(
            json.dumps(decision) + "\n",
            encoding="utf-8",
        )
        scope_path = run_root / "scope.json"
        scope_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": "RUN-SCOPED-TRIAGE",
                    "family": "pdf",
                    "platform": "net",
                    "paths": [page],
                    "initial_hashes": {},
                }
            ),
            encoding="utf-8",
        )
        decisions_path = run_root / "page_decisions.jsonl"
        receipt_path = run_root / "receipts/RCP-SCOPED.yaml"
        file_digest = lambda path: (  # noqa: E731 - compact fixture helper
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        )
        receipts_digest = "sha256:" + hashlib.sha256(
            f"{receipt_path.name}:{file_digest(receipt_path)}".encode("utf-8")
        ).hexdigest()
        scope_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                {"paths": [page], "input_digest": None},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        sha = "a" * 40
        (run_root / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "run_id": "RUN-SCOPED-TRIAGE",
                    "family": "pdf",
                    "platform": "net",
                    "mode": "remediation",
                    "state": "VALIDATING",
                    "session_owner": "session-1",
                    "created_at": "2026-07-25T00:00:00Z",
                    "updated_at": "2026-07-25T00:01:00Z",
                    "base_commit_sha": "b" * 40,
                    "initial_model_sha": sha,
                    "initial_source_sha": sha,
                    "target_model_sha": sha,
                    "target_source_sha": sha,
                    "scope": {"digest": scope_digest, "paths": [page]},
                    "stage_checkpoints": {},
                    "validation": {
                        "post_refresh_verify": "NOT_RUN",
                        "content_audit": "NOT_RUN",
                        "link_validation": "NOT_RUN",
                        "oracle": "NOT_RUN",
                        "triage_confirm": "NOT_RUN",
                        "seo_stability": "NOT_RUN",
                    },
                    "observed_heads": ["b" * 40],
                    "receipt_refs": [
                        receipt_path.relative_to(tmp_path).as_posix()
                    ],
                    "page_decision_ref": decisions_path.relative_to(
                        tmp_path
                    ).as_posix(),
                    "output_digests": {
                        "scope": file_digest(scope_path),
                        "page_decisions": file_digest(decisions_path),
                        "receipts": receipts_digest,
                    },
                    "commit_sha": None,
                    "failure_reason": None,
                }
            ),
            encoding="utf-8",
        )

        unknowns: list[str] = []
        post_refresh_verify.verify(
            "pdf",
            "net",
            run_id="RUN-SCOPED-TRIAGE",
            unknowns_out=unknowns,
        )

        assert "--files" in captured
        assert page in captured

    def test_exit_1_blocks_with_stale_count(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps({"stale_count": 2})
        self._configure_with_real_script_path(tmp_path, subprocess_run=lambda *a, **kw: mock_result)

        passed, failures = post_refresh_verify.verify("3d", "python")

        c9_failures = [f for f in failures if "Check 9" in f]
        assert len(c9_failures) == 1
        assert "2 stale page" in c9_failures[0]

    def test_exit_2_is_skip_not_fail(self, tmp_path):
        """Knowledge-absent (exit 2) must not block — it's a precondition gap,
        not a content-quality failure; distinct from exit 1 (ran, found staleness)."""
        _setup_knowledge(tmp_path, "3d", "python")
        mock_result = MagicMock()
        mock_result.returncode = 2
        mock_result.stdout = ""
        self._configure_with_real_script_path(tmp_path, subprocess_run=lambda *a, **kw: mock_result)

        passed, failures = post_refresh_verify.verify("3d", "python")

        assert not any("Check 9" in f for f in failures)

    def test_script_missing_is_skip(self, tmp_path):
        """If triage_confirm.py genuinely doesn't exist at the resolved path,
        Check 9 must SKIP silently, not error the whole verify() call —
        this is what keeps all 32 pre-existing tests (which redirect _HERE to
        a nonexistent path and don't create scripts/pipeline/lib/) passing
        unmodified after Check 9 was added."""
        _setup_knowledge(tmp_path, "3d", "python")
        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
            here=tmp_path,
        )
        # Deliberately do NOT create scripts/pipeline/lib/triage_confirm.py

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert not any("Check 9" in f for f in failures)

    def test_unexpected_exit_code_is_unknown_not_fail(self, tmp_path):
        """RPR-J-06: an exit code outside the documented 0/1/2 contract is a
        contract violation by the tool, not proof of stale prose -- UNKNOWN,
        never a fabricated 'stale pages found' FAIL."""
        _setup_knowledge(tmp_path, "3d", "python")
        mock_result = MagicMock()
        mock_result.returncode = 3
        mock_result.stdout = ""
        self._configure_with_real_script_path(tmp_path, subprocess_run=lambda *a, **kw: mock_result)

        unknowns: list = []
        passed, failures = post_refresh_verify.verify("3d", "python", unknowns_out=unknowns)

        assert not any("Check 9" in f for f in failures)
        assert any("Check 9" in u for u in unknowns)

    def test_timeout_is_unknown_not_fail(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")

        def _raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="triage_confirm.py", timeout=120)

        self._configure_with_real_script_path(tmp_path, subprocess_run=_raise_timeout)

        unknowns: list = []
        passed, failures = post_refresh_verify.verify("3d", "python", unknowns_out=unknowns)

        assert not any("Check 9" in f for f in failures)
        assert any("Check 9" in u and "timed out" in u for u in unknowns)

    def test_subprocess_exception_is_unknown_not_fail(self, tmp_path):
        _setup_knowledge(tmp_path, "3d", "python")

        def _raise_error(*a, **kw):
            raise OSError("could not spawn process")

        self._configure_with_real_script_path(tmp_path, subprocess_run=_raise_error)

        unknowns: list = []
        passed, failures = post_refresh_verify.verify("3d", "python", unknowns_out=unknowns)

        assert not any("Check 9" in f for f in failures)
        assert any("Check 9" in u for u in unknowns)


# ---------------------------------------------------------------------------
# verify() — check 3: stale reference pages (API class absent)
# ---------------------------------------------------------------------------

class TestVerifyCheckStaleReferencePages:
    """Check 3: reference pages for API classes absent from api_surface.json."""

    def test_valid_reference_page_passes(self, tmp_path):
        """Reference page for a KNOWN class → no failure. Guard: check actually runs."""
        _setup_knowledge(tmp_path, "3d", "python", api_surface=[{"name": "PdfDocument"}])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "PdfDocument.md").write_text("---\ntitle: PdfDocument\n---\nbody\n")

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert not any("Reference page for absent" in f for f in failures)

    def test_orphaned_reference_page_reported(self, tmp_path):
        """Reference page whose stem is NOT in api_surface.json → failure reported."""
        _setup_knowledge(tmp_path, "3d", "python", api_surface=[{"name": "PdfDocument"}])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "OrphanedClass.md").write_text("---\ntitle: OrphanedClass\n---\n")

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert any("Reference page for absent" in f for f in failures)
        assert any("OrphanedClass" in f for f in failures)

    def test_index_page_not_flagged(self, tmp_path):
        """_index.md is explicitly excluded from stale detection."""
        _setup_knowledge(tmp_path, "3d", "python", api_surface=[{"name": "PdfDocument"}])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "_index.md").write_text("---\ntitle: Reference Index\n---\n")
        (ref_dir / "PdfDocument.md").write_text("---\ntitle: PdfDocument\n---\n")

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert not any("Reference page for absent" in f for f in failures)

    def test_empty_api_surface_skips_check(self, tmp_path):
        """When api_surface.json has no classes, check 3 is silently skipped."""
        _setup_knowledge(tmp_path, "3d", "python", api_surface=[])

        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "3d" / "python"
        ref_dir.mkdir(parents=True)
        (ref_dir / "SomeClass.md").write_text("---\ntitle: SomeClass\n---\n")

        passed, failures = post_refresh_verify.verify("3d", "python")
        assert not any("Reference page for absent" in f for f in failures)


# ---------------------------------------------------------------------------
# Fix E: Check 3b — incorrectly retired pages (healing sprint 2026-04-15)
# ---------------------------------------------------------------------------

class TestCheck3bIncorrectlyRetiredPages:
    """Fix E: check_incorrectly_retired_pages catches draft:true pages for live APIs."""

    def test_catches_retired_page_with_live_api(self, tmp_path):
        """A reference page with draft:true whose class IS in api_surface → FAIL."""
        api_path = tmp_path / "api_surface.json"
        api_path.write_text(json.dumps([
            {"name": "FilterColumn", "methods": [], "properties": []},
            {"name": "Workbook", "methods": [], "properties": []},
        ]), encoding="utf-8")

        ref_root = tmp_path / "ref"
        ref_root.mkdir()
        (ref_root / "FilterColumn.md").write_text(
            "---\ntitle: FilterColumn\ndraft: true\nretired_at: '2026-04-13'\n---\nBody.\n",
            encoding="utf-8",
        )
        (ref_root / "Workbook.md").write_text(
            "---\ntitle: Workbook\nlayout: reference-single\n---\nBody.\n",
            encoding="utf-8",
        )

        passed, failures = post_refresh_verify.check_incorrectly_retired_pages(api_path, ref_root)
        assert not passed, "Should FAIL — FilterColumn is retired but exists in api_surface"
        assert len(failures) == 1
        assert "FilterColumn" in failures[0]

    def test_passes_when_no_incorrectly_retired_pages(self, tmp_path):
        """All draft:true pages are for absent APIs → PASS."""
        api_path = tmp_path / "api_surface.json"
        api_path.write_text(json.dumps([
            {"name": "Workbook", "methods": [], "properties": []},
        ]), encoding="utf-8")

        ref_root = tmp_path / "ref"
        ref_root.mkdir()
        # Retired page for a class NOT in api_surface — correct retirement
        (ref_root / "OldClass.md").write_text(
            "---\ntitle: OldClass\ndraft: true\n---\nBody.\n",
            encoding="utf-8",
        )
        (ref_root / "Workbook.md").write_text(
            "---\ntitle: Workbook\n---\nBody.\n",
            encoding="utf-8",
        )

        passed, failures = post_refresh_verify.check_incorrectly_retired_pages(api_path, ref_root)
        assert passed
        assert len(failures) == 0

    def test_skips_index_page(self, tmp_path):
        """_index.md pages are never flagged even if retired."""
        api_path = tmp_path / "api_surface.json"
        api_path.write_text(json.dumps([{"name": "_index"}]), encoding="utf-8")

        ref_root = tmp_path / "ref"
        ref_root.mkdir()
        (ref_root / "_index.md").write_text(
            "---\ntitle: Index\ndraft: true\n---\nBody.\n",
            encoding="utf-8",
        )

        passed, _ = post_refresh_verify.check_incorrectly_retired_pages(api_path, ref_root)
        assert passed

    def test_empty_api_surface_is_pass(self, tmp_path):
        """No API entries → check is skipped → PASS."""
        api_path = tmp_path / "api_surface.json"
        api_path.write_text("[]", encoding="utf-8")
        ref_root = tmp_path / "ref"
        ref_root.mkdir()

        passed, _ = post_refresh_verify.check_incorrectly_retired_pages(api_path, ref_root)
        assert passed


# ---------------------------------------------------------------------------
# Check 6: check_coverage_completeness
# ---------------------------------------------------------------------------

class TestCheck6CoverageCompleteness:
    """Check 6: page_decisions.json must cover all discovered English pages."""

    def _write_page(self, dir_: Path, name: str) -> Path:
        dir_.mkdir(parents=True, exist_ok=True)
        p = dir_ / name
        p.write_text(f"---\ntitle: {name}\n---\nbody\n", encoding="utf-8")
        return p

    def _write_decisions(self, review_root: Path, family: str, platform: str, paths: list[str]) -> None:
        d = review_root / family / platform
        d.mkdir(parents=True, exist_ok=True)
        pages = {p: {"decision": "EVIDENCE_ONLY", "reason": "test"} for p in paths}
        (d / "page_decisions.json").write_text(
            json.dumps({"family": family, "platform": platform, "pages": pages}),
            encoding="utf-8",
        )

    def test_check6_fail_when_decisions_absent(self, tmp_path):
        """Check 6 FAIL when page_decisions.json does not exist."""
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page.md")

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert not passed
        assert any("page_decisions.json not found" in f for f in failures)

    def test_check6_fail_when_page_missing_from_decisions(self, tmp_path):
        """Check 6 FAIL when a discovered page is absent from page_decisions.json."""
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page1.md")
        self._write_page(d, "page2.md")

        self._write_decisions(
            tmp_path / "review", "cells", "net",
            ["content/docs.aspose.org/en/cells/net/page1.md"]
        )

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert not passed
        assert any("Missing" in f and "page2.md" in f for f in failures)

    def test_check6_pass_with_full_coverage(self, tmp_path):
        """Check 6 PASS when page_decisions.json covers all discovered files."""
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page1.md")
        self._write_page(d, "page2.md")

        self._write_decisions(
            tmp_path / "review", "cells", "net",
            [
                "content/docs.aspose.org/en/cells/net/page1.md",
                "content/docs.aspose.org/en/cells/net/page2.md",
            ]
        )

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert passed
        assert failures == []

    def test_check6_pass_no_content_pages(self, tmp_path):
        """Check 6 PASS when no content pages are discovered (product not generated yet)."""
        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )
        assert passed

    def test_check6_skips_locale_files(self, tmp_path):
        """Check 6 does not require locale (translation) files in page_decisions.json."""
        d = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "net"
        self._write_page(d, "page.md")
        (d / "page.fr.md").write_text("---\ntitle: page fr\n---\nbody\n", encoding="utf-8")

        self._write_decisions(
            tmp_path / "review", "cells", "net",
            ["content/docs.aspose.org/en/cells/net/page.md"]
        )

        passed, failures = post_refresh_verify.check_coverage_completeness(
            "cells", "net", review_root=tmp_path / "review"
        )

        assert passed


# ---------------------------------------------------------------------------
# G-12 regression: write_reconciliation reads delta from plan.delta, not sp.delta
# ---------------------------------------------------------------------------

class TestVerifyCheck5ReconciliationUnknown:
    """Check 5: reconciliation artifact shows no unreconciled planned work."""

    def test_unparseable_reconciliation_is_unknown_not_fail(self, tmp_path):
        """RPR-J-06: a corrupt execution_reconciliation.json proves nothing about
        whether planned work was reconciled -- UNKNOWN, not a fabricated FAIL."""
        _setup_knowledge(tmp_path, "cells", "net")
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "execution_reconciliation.json").write_text(
            "not valid json {{{", encoding="utf-8"
        )
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "net", unknowns_out=unknowns)
        assert not any("Reconciliation" in f or "reconciliation artifact" in f for f in failures)
        assert any("Check 5" in u for u in unknowns)

    def test_old_schema_reconciliation_is_unknown_not_silent_pass(self, tmp_path):
        """RPR-J-08: a valid, parseable execution_reconciliation.json that
        predates schema_version must not be read with its planned/executed
        .get(key, 0) defaults -- that would silently read as a fully
        reconciled (0 planned, 0 executed) run. UNKNOWN, not a silent PASS."""
        _setup_knowledge(tmp_path, "cells", "net")
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "execution_reconciliation.json").write_text(
            json.dumps({"planned": {"pages_to_update": 5}, "executed": {"pages_updated": 0}}),
            encoding="utf-8",
        )  # deliberately no schema_version key -- would otherwise silently FAIL correctly
           # by luck (5 > 0), masking the real point: an old shape can't be trusted at all
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "net", unknowns_out=unknowns)
        assert not any("Reconciliation" in f or "reconciliation artifact" in f for f in failures)
        assert any("Check 5" in u and "schema_version" in u for u in unknowns)


class TestAssertNoSkippedPages:
    """assert_no_skipped_pages() (TC-14) — had zero test coverage anywhere in
    the suite before this (found during RPR-J-10's independent Lane I
    review). Covers the pre-existing PASS/FAIL/deferral/absent behavior plus
    the new schema-version guard (RPR-J-10 follow-up): reading
    skipped.pages_add_skipped via .get(key, 0) on an old-schema artifact
    would otherwise silently read as "0 skipped" -- a false PASS this
    function must never produce."""

    def _write_recon(self, tmp_path, family, platform, skipped: dict, schema_version=2) -> None:
        refresh_dir = tmp_path / "refresh_state" / family / platform
        refresh_dir.mkdir(parents=True, exist_ok=True)
        doc = {"planned": {}, "executed": {}, "skipped": skipped}
        if schema_version is not None:
            doc["schema_version"] = schema_version
        (refresh_dir / "execution_reconciliation.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_zero_skipped_passes(self, tmp_path):
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        self._write_recon(tmp_path, "cells", "net", {"pages_add_skipped": 0})
        post_refresh_verify.assert_no_skipped_pages("cells", "net")  # must not raise

    def test_skipped_without_deferral_raises(self, tmp_path):
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        self._write_recon(tmp_path, "cells", "net", {"pages_add_skipped": 3, "skip_reason": "test"})
        with pytest.raises(post_refresh_verify.SkippedPagesError):
            post_refresh_verify.assert_no_skipped_pages("cells", "net")

    def test_skipped_with_full_deferral_passes(self, tmp_path):
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        self._write_recon(tmp_path, "cells", "net",
                          {"pages_add_skipped": 3, "pages_deferred_low_importance": 3})
        post_refresh_verify.assert_no_skipped_pages("cells", "net")  # must not raise

    def test_absent_reconciliation_raises_file_not_found(self, tmp_path):
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        with pytest.raises(FileNotFoundError):
            post_refresh_verify.assert_no_skipped_pages("cells", "net")

    def test_old_schema_raises_schema_unknown_not_silent_pass(self, tmp_path):
        """RPR-J-10 follow-up (found by independent review): an old-schema
        artifact with a genuinely nonzero pages_add_skipped under a DIFFERENT
        field name would read as 0 via .get(key, 0) -- must raise instead of
        silently passing."""
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        self._write_recon(tmp_path, "cells", "net", {"pages_add_skipped": 0}, schema_version=None)
        with pytest.raises(post_refresh_verify.ReconciliationSchemaUnknownError):
            post_refresh_verify.assert_no_skipped_pages("cells", "net")

    def test_cli_old_schema_exits_3_not_0(self, tmp_path):
        """The CLI --assert-no-skipped path must surface schema-unknown as its
        own exit code (3, mirroring --verify's INCONCLUSIVE), never exit 0
        (clean pass) or silently swallow it."""
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        self._write_recon(tmp_path, "cells", "net", {"pages_add_skipped": 0}, schema_version=None)
        exit_code = post_refresh_verify.main(["cells", "net", "--assert-no-skipped"])
        assert exit_code == 3


class TestWriteReconciliationDeltaPath:
    """G-12 regression: site_plan.yaml delta lives at plan.delta, not top-level delta."""

    def _write_site_plan(self, plans_dir: Path, pages_to_update: list) -> None:
        import yaml
        site_plan = {
            "plan": {
                "schema_version": 2,
                "plan_version": 2,
                "family": "cells",
                "platform": "net",
                "delta": {
                    "pages_to_add": [],
                    "pages_to_update": pages_to_update,  # strings (actual site_plan format)
                    "pages_to_remove": [],
                    "pages_renamed": [],
                },
            }
        }
        plans_dir.mkdir(parents=True, exist_ok=True)
        (plans_dir / "site_plan.yaml").write_text(yaml.dump(site_plan), encoding="utf-8")

    def _write_progress(self, refresh_dir: Path, steps: list) -> None:
        import json
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"steps": steps, "pages_updated": []}), encoding="utf-8"
        )

    def test_reads_planned_from_plan_delta_not_top_level(self, tmp_path):
        """write_reconciliation must read delta from plan.delta (G-12 fix)."""
        import json
        plans_dir = tmp_path / "reports" / "plans" / "cells" / "net"
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        paths = [
            "content/docs.aspose.org/en/cells/net/page1.md",
            "content/docs.aspose.org/en/cells/net/page2.md",
        ]
        self._write_site_plan(plans_dir, paths)
        self._write_progress(refresh_dir, ["page_update"])

        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
        )
        try:
            recon_path = post_refresh_verify.write_reconciliation(
                "cells", "net", require_content_steps=False
            )
            recon = json.loads(recon_path.read_text(encoding="utf-8"))
            assert recon["planned"]["pages_to_update"] == 2, (
                "G-12: planned.pages_to_update must be 2, not 0. "
                "write_reconciliation is reading from the wrong YAML key."
            )
        finally:
            post_refresh_verify.configure()

    def test_top_level_delta_key_ignored(self, tmp_path):
        """A top-level 'delta' key in site_plan.yaml must NOT be read (G-12 regression)."""
        import json, yaml
        plans_dir = tmp_path / "reports" / "plans" / "cells" / "net"
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        plans_dir.mkdir(parents=True, exist_ok=True)
        # Write site_plan with delta at the WRONG (old) location — should be ignored
        bad_plan = {
            "delta": {"pages_to_update": [{"path": "content/docs.aspose.org/en/cells/net/p.md"}]},
            "plan": {
                "schema_version": 2,
                "plan_version": 2,
                "family": "cells",
                "platform": "net",
                "delta": {"pages_to_add": [], "pages_to_update": [], "pages_to_remove": [], "pages_renamed": []},
            },
        }
        (plans_dir / "site_plan.yaml").write_text(yaml.dump(bad_plan), encoding="utf-8")
        refresh_dir.mkdir(parents=True, exist_ok=True)
        (refresh_dir / "progress.json").write_text(
            json.dumps({"steps": ["page_update"], "pages_updated": []}), encoding="utf-8"
        )

        post_refresh_verify.configure(
            repo_root=tmp_path,
            reports_root=tmp_path / "refresh_state",
        )
        try:
            recon_path = post_refresh_verify.write_reconciliation(
                "cells", "net", require_content_steps=False
            )
            recon = json.loads(recon_path.read_text(encoding="utf-8"))
            assert recon["planned"]["pages_to_update"] == 0, (
                "Top-level 'delta' key must be ignored; planned must come from plan.delta"
            )
        finally:
            post_refresh_verify.configure()


# ---------------------------------------------------------------------------
# Check 8 (G-16): Tracking-gap and stale-prose detection
# ---------------------------------------------------------------------------

class TestBaseRefResolution:
    """RPR-J-17: verify()'s base_ref resolves explicit param > newest refresh-run
    manifest's base_commit_sha > "HEAD" — fixing the confirmed-real limitation that
    diffing against a plain "HEAD" is vacuous for an already-committed refresh
    (proven against real pdf/net data: 903/903 BODY_UPDATED pages showed 0 diff from
    HEAD purely because the refresh had already landed there)."""

    def _write_manifest(self, tmp_path, family, platform, base_commit_sha):
        d = tmp_path / "reports" / "refresh_runs" / family / platform
        d.mkdir(parents=True, exist_ok=True)
        (d / "RUN-001.manifest.json").write_text(
            json.dumps({"run_id": "RUN-001", "base_commit_sha": base_commit_sha}),
            encoding="utf-8",
        )

    def test_load_base_commit_sha_none_when_no_manifest_dir(self, tmp_path):
        assert post_refresh_verify._load_base_commit_sha("cells", "net") is None

    def test_load_base_commit_sha_reads_newest_manifest(self, tmp_path):
        self._write_manifest(tmp_path, "pdf", "net", "8a3131b9a6f7e97c20214896c615dbee86272459")
        sha = post_refresh_verify._load_base_commit_sha("pdf", "net")
        assert sha == "8a3131b9a6f7e97c20214896c615dbee86272459"

    def test_load_base_commit_sha_none_when_field_absent(self, tmp_path):
        d = tmp_path / "reports" / "refresh_runs" / "pdf" / "net"
        d.mkdir(parents=True, exist_ok=True)
        (d / "RUN-001.manifest.json").write_text(json.dumps({"run_id": "RUN-001"}), encoding="utf-8")
        assert post_refresh_verify._load_base_commit_sha("pdf", "net") is None

    def test_load_base_commit_sha_none_when_empty_string(self, tmp_path):
        self._write_manifest(tmp_path, "pdf", "net", "")
        assert post_refresh_verify._load_base_commit_sha("pdf", "net") is None

    def test_verify_uses_explicit_base_ref_over_manifest(self, tmp_path):
        """An explicit base_ref param wins even when a manifest exists."""
        _setup_knowledge(tmp_path, "cells", "net")
        self._write_manifest(tmp_path, "cells", "net", "manifest-sha")
        seen_refs: list = []

        def _spy(family, platform, base_ref):
            seen_refs.append(base_ref)
            return None

        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=_spy,
        )
        post_refresh_verify.verify("cells", "net", base_ref="explicit-sha")
        assert seen_refs and all(r == "explicit-sha" for r in seen_refs)

    def test_verify_does_not_infer_newest_manifest(self, tmp_path):
        """Diagnostic API never binds an arbitrary newest local manifest."""
        _setup_knowledge(tmp_path, "pdf", "net")
        self._write_manifest(tmp_path, "pdf", "net", "8a3131b9a6f7e97c20214896c615dbee86272459")
        seen_refs: list = []

        def _spy(family, platform, base_ref):
            seen_refs.append(base_ref)
            return None

        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=_spy,
        )
        post_refresh_verify.verify("pdf", "net")
        assert seen_refs and all(r == "HEAD" for r in seen_refs)

    def test_verify_falls_back_to_head_when_nothing_else_available(self, tmp_path):
        """No explicit base_ref, no manifest -> original unchanged default, "HEAD"."""
        _setup_knowledge(tmp_path, "cells", "net")
        seen_refs: list = []

        def _spy(family, platform, base_ref):
            seen_refs.append(base_ref)
            return None

        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=_spy,
        )
        post_refresh_verify.verify("cells", "net")
        assert seen_refs and all(r == "HEAD" for r in seen_refs)

    def test_cli_base_flag_threads_through_to_verify(self, tmp_path, monkeypatch):
        """--base on the CLI reaches verify() as an explicit base_ref override."""
        _setup_knowledge(tmp_path, "cells", "net")
        captured = {}

        def _fake_verify(
            family, platform, *, allow_warn=False, unknowns_out=None,
            base_ref=None, run_id=None,
        ):
            captured["base_ref"] = base_ref
            captured["run_id"] = run_id
            return True, []

        monkeypatch.setattr(post_refresh_verify, "verify", _fake_verify)
        exit_code = post_refresh_verify.main(["cells", "net", "--verify", "--base", "cli-sha"])
        assert exit_code == 0
        assert captured["base_ref"] == "cli-sha"

    def test_cli_omitted_run_and_base_is_unknown(self, tmp_path, monkeypatch):
        """Commit readiness may not infer a base or newest local run."""
        _setup_knowledge(tmp_path, "cells", "net")
        captured = {}

        def _fake_verify(
            family, platform, *, allow_warn=False, unknowns_out=None,
            base_ref=None, run_id=None,
        ):
            captured["base_ref"] = base_ref
            return True, []

        monkeypatch.setattr(post_refresh_verify, "verify", _fake_verify)
        exit_code = post_refresh_verify.main(["cells", "net", "--verify"])
        assert exit_code == 3
        assert "base_ref" not in captured


def _fake_git_view(total, changed_paths, unchanged_paths=None):
    """Build a fake return value for the _cfg_git_body_changed seam
    (RPR-J-05), matching _git_body_changed_pages()'s real return shape."""
    changed_paths = set(changed_paths)
    unchanged_paths = set(unchanged_paths or [])
    return {
        "total": total,
        "changed": len(changed_paths),
        "changed_paths": changed_paths,
        "unchanged_paths": unchanged_paths,
    }


class TestRunBoundEvidence:
    @staticmethod
    def _write_bound_run(tmp_path: Path, *, receipt_run_id: str = "RUN-BOUND"):
        run_id = "RUN-BOUND"
        run_root = tmp_path / "reports/refresh_runs/pdf/net" / run_id
        (run_root / "receipts").mkdir(parents=True)
        page = "content/docs.aspose.org/en/pdf/net/page.md"
        receipt = {
            "receipt_id": "RCP-BOUND",
            "run_id": receipt_run_id,
            "page_path": page,
            "locale": "en",
            "change_ids": ["CHG-1"],
            "strategy_used": "SECTION_REMOVAL",
            "old_hash": "sha256:old",
            "new_hash": "sha256:new",
            "verdict": "BODY_UPDATED",
        }
        raw = yaml.safe_dump(
            {"content_refresh_receipt": receipt},
            sort_keys=False,
        ).encode("utf-8")
        (run_root / "receipts/RCP-BOUND.yaml").write_bytes(raw)
        decision = {
            "schema_version": 1,
            "run_id": run_id,
            "page_path": page,
            "surface": "docs",
            "locale": "en",
            "intended_action": "BODY_UPDATE",
            "disposition": "BODY_UPDATED",
            "body_hash_before": "sha256:before",
            "body_hash_after": "sha256:after",
            "frontmatter_hash_before": "sha256:fm-before",
            "frontmatter_hash_after": "sha256:fm-after",
            "receipt_ref": "receipts/RCP-BOUND.yaml",
            "receipt_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "evidence_claims_checked": [],
            "evidence_apis_checked": [],
            "validator_results": {
                "receipt": "PASS",
                "forbidden_claims": "PASS",
                "regrounding": "PASS",
            },
        }
        (run_root / "page_decisions.jsonl").write_text(
            json.dumps(decision) + "\n",
            encoding="utf-8",
        )
        sha = "a" * 40
        scope_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                {"paths": [page], "input_digest": None},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        manifest = {
            "schema_version": 3,
            "run_id": run_id,
            "family": "pdf",
            "platform": "net",
            "mode": "remediation",
            "state": "VALIDATING",
            "session_owner": "session-1",
            "created_at": "2026-07-25T00:00:00Z",
            "updated_at": "2026-07-25T00:01:00Z",
            "base_commit_sha": "b" * 40,
            "initial_model_sha": sha,
            "initial_source_sha": sha,
            "target_model_sha": sha,
            "target_source_sha": sha,
            "scope": {"digest": scope_digest, "paths": [page]},
            "stage_checkpoints": {},
            "validation": {
                "post_refresh_verify": "NOT_RUN",
                "content_audit": "NOT_RUN",
                "link_validation": "NOT_RUN",
                "oracle": "NOT_RUN",
                "triage_confirm": "NOT_RUN",
                "seo_stability": "NOT_RUN",
            },
            "observed_heads": ["b" * 40],
            "receipt_refs": ["receipts/RCP-BOUND.yaml"],
            "page_decision_ref": "page_decisions.jsonl",
            "commit_sha": None,
            "failure_reason": None,
        }
        (run_root / "manifest.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        return run_root, decision

    def test_exact_run_loads_and_validates_same_run_receipt(self, tmp_path):
        run_root, _ = self._write_bound_run(tmp_path)
        bound = post_refresh_verify._load_bound_run("pdf", "net", "RUN-BOUND")
        rows = post_refresh_verify._load_run_decisions(run_root, "RUN-BOUND")
        post_refresh_verify._validate_run_receipts(
            run_root, "RUN-BOUND", rows
        )
        assert bound["manifest"]["base_commit_sha"] == "b" * 40

    def test_wrong_run_receipt_is_rejected(self, tmp_path):
        run_root, _ = self._write_bound_run(
            tmp_path, receipt_run_id="OTHER-RUN"
        )
        rows = post_refresh_verify._load_run_decisions(run_root, "RUN-BOUND")
        with pytest.raises(ValueError, match="wrong-run receipt"):
            post_refresh_verify._validate_run_receipts(
                run_root, "RUN-BOUND", rows
            )

    def test_legacy_stamped_decision_is_not_a_run_ledger(self, tmp_path):
        run_root, _ = self._write_bound_run(tmp_path)
        (run_root / "page_decisions.jsonl").write_text(
            json.dumps({"schema_version": 2, "pages": {}}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="invalid page decision"):
            post_refresh_verify._load_run_decisions(
                run_root, "RUN-BOUND"
            )


class TestCheck7GitFounded:
    """Check 7 (RPR-J-05): re-founded on a real git body-diff (via the
    _cfg_git_body_changed seam, standing in for audit_content_hash's git
    show + body-hash primitives) instead of progress.json /
    execution_reconciliation.json bookkeeping. UNKNOWN when git-founded
    verification is unavailable — never a fabricated FAIL with a made-up
    count from an absent or old-schema bookkeeping file."""

    def _delta(self, tmp_path, family, platform, removed):
        merged = tmp_path / "knowledge" / family / platform / "merged"
        merged.mkdir(parents=True, exist_ok=True)
        (merged / "knowledge_delta.json").write_text(
            json.dumps({"removed_claims": [f"CLM-{i}" for i in range(removed)]}), encoding="utf-8")

    def test_check7_pass_le_50_removed_no_git_call_needed(self, tmp_path):
        _setup_knowledge(tmp_path, "cells", "java")
        self._delta(tmp_path, "cells", "java", removed=10)
        passed, failures = post_refresh_verify.verify("cells", "java")
        assert not any("Check 7" in f for f in failures)

    def test_check7_unparseable_delta_is_unknown_not_silent(self, tmp_path):
        """RPR-J-06: knowledge_delta.json exists but is corrupt -- UNKNOWN, not
        a silent `pass` that makes Check 7 vanish with no signal at all."""
        merged = tmp_path / "knowledge" / "cells" / "java" / "merged"
        merged.mkdir(parents=True, exist_ok=True)
        (merged / "knowledge_delta.json").write_text("not valid json {{{", encoding="utf-8")
        post_refresh_verify.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "java", unknowns_out=unknowns)
        assert not any("Check 7" in f for f in failures)
        assert any("Check 7" in u for u in unknowns)

    def test_check7_unknown_when_git_view_unavailable(self, tmp_path):
        """The cells/java false-block scenario, re-founded: git-founded verification
        unavailable (e.g. not a git repo, or every page is new at HEAD) must yield
        UNKNOWN, never a fabricated FAIL with a removed-claim count."""
        _setup_knowledge(tmp_path, "cells", "java")
        self._delta(tmp_path, "cells", "java", removed=1996)
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: None,
        )
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "java", unknowns_out=unknowns)
        assert not any("Check 7" in f for f in failures), f"unavailable git view must not FAIL Check 7: {failures}"
        assert any("Check 7" in u for u in unknowns)

    def test_check7_pass_when_git_shows_real_body_changes(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        self._delta(tmp_path, "pdf", "net", removed=100)
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(
                total=36, changed_paths={f"content/docs.aspose.org/en/pdf/net/p{i}.md" for i in range(36)},
            ),
        )
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 7" in f for f in failures)

    def test_check7_genuine_zero_real_changes_still_blocks(self, tmp_path):
        """The real signal Check 7 exists to catch: a significant knowledge delta but
        git shows literally 0 body diffs anywhere in the product — a genuine FAIL,
        immune to any bookkeeping schema/desync question."""
        _setup_knowledge(tmp_path, "cells", "java")
        self._delta(tmp_path, "cells", "java", removed=100)
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(
                total=5, changed_paths=set(),
                unchanged_paths={f"content/docs.aspose.org/en/cells/java/p{i}.md" for i in range(5)},
            ),
        )
        passed, failures = post_refresh_verify.verify("cells", "java")
        assert any("Check 7" in f for f in failures), "genuine 0-real-changes must still block"

    def test_check7_allow_warn_demotes_genuine_zero_to_warn(self, tmp_path):
        _setup_knowledge(tmp_path, "cells", "java")
        self._delta(tmp_path, "cells", "java", removed=100)
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(
                total=5, changed_paths=set(),
                unchanged_paths={f"content/docs.aspose.org/en/cells/java/p{i}.md" for i in range(5)},
            ),
        )
        passed, failures = post_refresh_verify.verify("cells", "java", allow_warn=True)
        assert not any("Check 7" in f for f in failures)


class TestCheck8CaseAGitFounded:
    """Check 8 Case A (RPR-J-05): cross-checks page_decisions.json's own BODY_UPDATED
    claims against a real git body diff — a decision that claims a body update but
    which git shows as byte-identical to HEAD is the literal PDF-NET-REFRESH-001
    tracking-gap shape, now caught directly instead of comparing two ephemeral
    bookkeeping files against each other."""

    def _write_decisions(self, tmp_path, family, platform, decisions: dict, schema_version=2) -> None:
        """decisions: {path: decision_string}"""
        d = tmp_path / "reports" / "refresh_review" / family / platform
        d.mkdir(parents=True, exist_ok=True)
        pages = {p: {"decision": dec, "reason": "test"} for p, dec in decisions.items()}
        doc = {"family": family, "platform": platform, "pages": pages}
        if schema_version is not None:
            doc["schema_version"] = schema_version
        (d / "page_decisions.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_check8_case_a_unknown_when_git_view_unavailable(self, tmp_path):
        _setup_knowledge(tmp_path, "cells", "net")
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: None,
        )
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "net", unknowns_out=unknowns)
        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0
        assert any("Case A" in u for u in unknowns)

    def test_check8_case_a_unknown_when_no_page_decisions(self, tmp_path):
        _setup_knowledge(tmp_path, "cells", "net")
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(total=1, changed_paths={"a.md"}),
        )
        # No page_decisions.json written
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "net", unknowns_out=unknowns)
        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0
        assert any("Case A" in u for u in unknowns)

    def test_check8_case_a_unknown_when_page_decisions_old_schema(self, tmp_path):
        """RPR-J-08: page_decisions.json exists and parses, but predates
        schema_version -- UNKNOWN, not a silent PASS reading its shape as
        'nothing recorded'."""
        _setup_knowledge(tmp_path, "pdf", "net")
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(
                total=1, changed_paths=set(),
                unchanged_paths={"content/kb.aspose.org/en/pdf/net/faq.md"},
            ),
        )
        self._write_decisions(tmp_path, "pdf", "net",
                              {"content/kb.aspose.org/en/pdf/net/faq.md": "BODY_UPDATED"},
                              schema_version=None)  # no schema_version key at all
        unknowns: list = []
        passed, failures = post_refresh_verify.verify("pdf", "net", unknowns_out=unknowns)
        assert not any("Check 8" in f and "Case A" in f for f in failures)
        assert any("Check 8" in u and "Case A" in u and "schema_version" in u for u in unknowns)

    def test_check8_case_a_pass_when_no_body_updated_claims(self, tmp_path):
        _setup_knowledge(tmp_path, "cells", "net")
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(total=1, changed_paths=set(), unchanged_paths={"a.md"}),
        )
        self._write_decisions(tmp_path, "cells", "net", {"a.md": "EVIDENCE_ONLY"})
        passed, failures = post_refresh_verify.verify("cells", "net")
        assert not any("Check 8" in f and "Case A" in f for f in failures)

    def test_check8_case_a_pass_when_body_updated_claim_verified_changed(self, tmp_path):
        """ANTI-ARTIFACT case (plan §18.5): a healthy refresh where the decision's claim
        is backed by a real git diff must PASS."""
        _setup_knowledge(tmp_path, "pdf", "net")
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(
                total=1, changed_paths={"content/kb.aspose.org/en/pdf/net/faq.md"},
            ),
        )
        self._write_decisions(tmp_path, "pdf", "net",
                              {"content/kb.aspose.org/en/pdf/net/faq.md": "BODY_UPDATED"})
        passed, failures = post_refresh_verify.verify("pdf", "net")
        assert not any("Check 8" in f and "Case A" in f for f in failures)

    def test_check8_case_a_fails_on_the_pdf_net_tracking_gap_shape(self, tmp_path):
        """The literal PDF-NET-REFRESH-001 shape: a page recorded as BODY_UPDATED whose
        body git shows as byte-identical to HEAD — must FAIL by default."""
        _setup_knowledge(tmp_path, "pdf", "net")
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(
                total=1, changed_paths=set(),
                unchanged_paths={"content/kb.aspose.org/en/pdf/net/faq.md"},
            ),
        )
        self._write_decisions(tmp_path, "pdf", "net",
                              {"content/kb.aspose.org/en/pdf/net/faq.md": "BODY_UPDATED"})
        passed, failures = post_refresh_verify.verify("pdf", "net")
        c8_failures = [f for f in failures if "Check 8" in f and "Case A" in f]
        assert len(c8_failures) == 1, f"claimed-but-unverified body update must block; failures: {failures}"
        assert "faq.md" in c8_failures[0]
        assert passed is False

    def test_check8_case_a_allow_warn_demotes_tracking_gap_to_warn(self, tmp_path):
        _setup_knowledge(tmp_path, "pdf", "net")
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(
                total=1, changed_paths=set(),
                unchanged_paths={"content/kb.aspose.org/en/pdf/net/faq.md"},
            ),
        )
        self._write_decisions(tmp_path, "pdf", "net",
                              {"content/kb.aspose.org/en/pdf/net/faq.md": "BODY_UPDATED"})
        passed, failures = post_refresh_verify.verify("pdf", "net", allow_warn=True)
        assert not any("Check 8" in f and "Case A" in f for f in failures)

    def test_check8_case_a_new_page_excluded_not_flagged(self, tmp_path):
        """A page claimed BODY_UPDATED that is neither in changed_paths nor
        unchanged_paths (a genuinely new page, no version at HEAD to diff against)
        is unverifiable by this method and must not be flagged as mislabeled."""
        _setup_knowledge(tmp_path, "cells", "net")
        post_refresh_verify.configure(
            repo_root=tmp_path, reports_root=tmp_path / "refresh_state",
            git_body_changed=lambda *a, **kw: _fake_git_view(total=0, changed_paths=set(), unchanged_paths=set()),
        )
        self._write_decisions(tmp_path, "cells", "net", {"content/docs.aspose.org/en/cells/net/new.md": "BODY_UPDATED"})
        passed, failures = post_refresh_verify.verify("cells", "net")
        assert not any("Check 8" in f and "Case A" in f for f in failures)


class TestCheck8ProseStaleWarn:
    """Check 8 Case B: prose_stale_scan JSON with hits. RPR-F-01 promoted this from
    WARN to BLOCK by default; --allow-warn demotes it back."""

    def _write_prose_stale(self, gap_dir: Path, family: str, platform: str, hits: list) -> None:
        gap_dir.mkdir(parents=True, exist_ok=True)
        report = {"family": family, "platform": platform, "hits": hits}
        (gap_dir / f"{family}-{platform}-prose-stale.json").write_text(
            json.dumps(report), encoding="utf-8"
        )

    def test_check8_case_b_blocks_by_default(self, tmp_path):
        """RPR-F-01: Case B with hits now BLOCKS."""
        _setup_knowledge(tmp_path, "cells", "net")
        gap_dir = tmp_path / "reports" / "gap-analysis"
        self._write_prose_stale(gap_dir, "cells", "net", hits=[
            {"file": "content/docs.aspose.org/en/cells/net/page1.md", "api": "OldMethod"},
            {"file": "content/docs.aspose.org/en/cells/net/page2.md", "api": "OldClass"},
        ])

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f and "Case B" in f]
        assert len(c8_failures) == 1, f"Case B must now block; failures: {failures}"
        assert passed is False

    def test_check8_case_b_allow_warn_demotes_to_warn(self, tmp_path):
        _setup_knowledge(tmp_path, "cells", "net")
        gap_dir = tmp_path / "reports" / "gap-analysis"
        self._write_prose_stale(gap_dir, "cells", "net", hits=[
            {"file": "content/docs.aspose.org/en/cells/net/page1.md", "api": "OldMethod"},
        ])

        passed, failures = post_refresh_verify.verify("cells", "net", allow_warn=True)

        c8_failures = [f for f in failures if "Check 8" in f and "Case B" in f]
        assert len(c8_failures) == 0

    def test_check8_case_b_pass_when_hits_empty(self, tmp_path):
        """Case B: prose-stale report exists but hits=[] -> PASS."""
        _setup_knowledge(tmp_path, "cells", "net")
        gap_dir = tmp_path / "reports" / "gap-analysis"
        self._write_prose_stale(gap_dir, "cells", "net", hits=[])

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0

    def test_check8_case_b_unparseable_report_is_unknown_not_silent(self, tmp_path):
        """RPR-J-06: the report exists but is corrupt -- UNKNOWN, not a silent
        `pass` that vanishes with no signal at all."""
        _setup_knowledge(tmp_path, "cells", "net")
        gap_dir = tmp_path / "reports" / "gap-analysis"
        gap_dir.mkdir(parents=True, exist_ok=True)
        (gap_dir / "cells-net-prose-stale.json").write_text("not valid json {{{", encoding="utf-8")

        unknowns: list = []
        passed, failures = post_refresh_verify.verify("cells", "net", unknowns_out=unknowns)
        assert not any("Check 8" in f and "Case B" in f for f in failures)
        assert any("Check 8" in u and "Case B" in u for u in unknowns)

    def test_check8_case_b_skip_when_no_report(self, tmp_path):
        """Case B: no prose-stale report -> SKIP (no failures)."""
        _setup_knowledge(tmp_path, "cells", "net")
        # No prose-stale report written

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0

    def test_check8_both_cases_clean_passes(self, tmp_path):
        """Both Case A and Case B clean -> overall no Check 8 failures."""
        _setup_knowledge(tmp_path, "cells", "net")
        refresh_dir = tmp_path / "refresh_state" / "cells" / "net"
        refresh_dir.mkdir(parents=True, exist_ok=True)
        recon = {
            "planned": {"pages_to_update": 2, "pages_to_add": 0, "pages_to_remove": 0},
            "executed": {"pages_updated": 2, "pages_added": 0, "pages_removed": 0},
            "skipped": {"pages_update_skipped": 0},
            "body_changes": {
                "files_with_body_diff": 2,
                "files_metadata_only": 0,
                "metadata_only_files": [],
            },
        }
        (refresh_dir / "execution_reconciliation.json").write_text(
            json.dumps(recon), encoding="utf-8"
        )
        (refresh_dir / "progress.json").write_text(
            json.dumps({
                "steps": ["page_update"],
                "pages_updated": [
                    "content/docs.aspose.org/en/cells/net/page1.md",
                    "content/docs.aspose.org/en/cells/net/page2.md",
                ],
            }),
            encoding="utf-8",
        )
        # No prose-stale report -> Case B skip

        passed, failures = post_refresh_verify.verify("cells", "net")

        c8_failures = [f for f in failures if "Check 8" in f]
        assert len(c8_failures) == 0


def _build_bound_evidence(tmp_path, run_id, scoped_page, extra_decision=None):
    """Minimal, digest-consistent run_root + manifest for
    _validate_bound_run_evidence, with one scoped page and optionally one
    extra (out-of-scope) decision row appended after digests are computed."""
    run_root = tmp_path / "reports/refresh_runs/pdf/net" / run_id
    (run_root / "receipts").mkdir(parents=True)
    page = tmp_path / scoped_page
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("original\n", encoding="utf-8")
    file_hash = "sha256:" + hashlib.sha256(page.read_bytes()).hexdigest()

    receipt_path = run_root / "receipts/RCP-001.yaml"
    raw = yaml.safe_dump({
        "content_refresh_receipt": {
            "receipt_id": "RCP-001", "run_id": run_id, "page_path": scoped_page,
            "locale": "en", "change_ids": [], "strategy_used": "SURGICAL_CLAIM_REPLACEMENT",
            "old_hash": file_hash, "new_hash": file_hash,
            "verdict": "NO_ACTIONABLE_SECTIONS", "generated_at": "2026-07-25T00:00:00Z",
        }
    }, sort_keys=False).encode("utf-8")
    receipt_path.write_bytes(raw)

    decision = {
        "schema_version": 1, "run_id": run_id, "page_path": scoped_page,
        "surface": "docs", "locale": "en", "intended_action": "BODY_UPDATE",
        "disposition": "NOT_AFFECTED",
        "body_hash_before": file_hash, "body_hash_after": file_hash,
        "frontmatter_hash_before": "sha256:fm", "frontmatter_hash_after": "sha256:fm",
        "receipt_ref": "receipts/RCP-001.yaml",
        "receipt_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "evidence_claims_checked": [], "evidence_apis_checked": [],
        "validator_results": {"receipt": "PASS", "forbidden_claims": "PASS", "regrounding": "PASS"},
    }
    decisions_path = run_root / "page_decisions.jsonl"
    lines = [json.dumps(decision)]
    if extra_decision is not None:
        # Both decisions share the same receipt file in this minimal fixture.
        extra_decision.setdefault("receipt_ref", "receipts/RCP-001.yaml")
        extra_decision["receipt_digest"] = decision["receipt_digest"]
        lines.append(json.dumps(extra_decision))
    decisions_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    scope_path = run_root / "scope.json"
    scope_path.write_text(json.dumps({
        "schema_version": 1, "run_id": run_id, "family": "pdf", "platform": "net",
        "paths": [scoped_page], "initial_hashes": {scoped_page: file_hash},
    }), encoding="utf-8")

    def _digest(path):
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    scope_digest = "sha256:" + hashlib.sha256(
        json.dumps({"paths": [scoped_page], "input_digest": None},
                    sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    receipts_digest = "sha256:" + hashlib.sha256(
        f"{receipt_path.name}:{_digest(receipt_path)}".encode("utf-8")
    ).hexdigest()
    manifest = {
        "run_id": run_id, "family": "pdf", "platform": "net",
        "scope": {"paths": [scoped_page], "digest": scope_digest, "input_digest": None},
        "output_digests": {
            "scope": _digest(scope_path),
            "page_decisions": _digest(decisions_path),
            "receipts": receipts_digest,
        },
        "receipt_refs": [receipt_path.relative_to(tmp_path).as_posix()],
        "page_decision_ref": decisions_path.relative_to(tmp_path).as_posix(),
    }
    decisions = [json.loads(line) for line in lines]
    return manifest, run_root, decisions


def test_bound_evidence_tolerates_out_of_scope_additive_generated_row(tmp_path):
    """Regression test: _validate_bound_run_evidence required an exact
    scope/decision set match -- the same bug fixed in refresh_run.py's
    apply_run()/_assert_run_evidence_ready() via _reconcile_scope_and_decisions
    (kept self-contained here since this is a separately-invoked CLI script).
    An out-of-scope GENERATED row for a provably-new page must not block."""
    from commands.content.body_refresh import _normalized_body_hash

    manifest, run_root, decisions = _build_bound_evidence(
        tmp_path, "RUN-BOUND-OK", "content/docs.aspose.org/en/pdf/net/page.md",
        extra_decision={
            "schema_version": 1, "run_id": "RUN-BOUND-OK",
            "page_path": "content/reference.aspose.org/en/pdf/net/NewClass.md",
            "surface": "reference", "locale": "en", "intended_action": "REFERENCE_GENERATE",
            "disposition": "GENERATED",
            "body_hash_before": _normalized_body_hash(""),
            "body_hash_after": _normalized_body_hash("x"),
            "frontmatter_hash_before": "sha256:fm", "frontmatter_hash_after": "sha256:fm",
            "receipt_ref": "receipts/RCP-001.yaml",
            "evidence_claims_checked": [], "evidence_apis_checked": [],
            "validator_results": {"receipt": "PASS", "forbidden_claims": "PASS", "regrounding": "PASS"},
        },
    )
    # Re-derive decisions/digests now that the extra row is in the file.
    decisions_path = run_root / "page_decisions.jsonl"
    manifest["output_digests"]["page_decisions"] = (
        "sha256:" + hashlib.sha256(decisions_path.read_bytes()).hexdigest()
    )
    decisions = [
        json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]

    post_refresh_verify.configure(repo_root=tmp_path)
    try:
        post_refresh_verify._validate_bound_run_evidence(manifest, run_root, decisions)  # must not raise
    finally:
        post_refresh_verify.configure()


def test_bound_evidence_blocks_out_of_scope_overwrite(tmp_path):
    """Negative control: an out-of-scope GENERATED row whose body_hash_before
    proves real pre-existing content must still block."""
    manifest, run_root, decisions = _build_bound_evidence(
        tmp_path, "RUN-BOUND-BAD", "content/docs.aspose.org/en/pdf/net/page.md",
        extra_decision={
            "schema_version": 1, "run_id": "RUN-BOUND-BAD",
            "page_path": "content/reference.aspose.org/en/pdf/net/Existing.md",
            "surface": "reference", "locale": "en", "intended_action": "REFERENCE_GENERATE",
            "disposition": "GENERATED",
            "body_hash_before": "sha256:" + "1" * 64,
            "body_hash_after": "sha256:" + "2" * 64,
            "frontmatter_hash_before": "sha256:fm", "frontmatter_hash_after": "sha256:fm",
            "receipt_ref": "receipts/RCP-001.yaml",
            "evidence_claims_checked": [], "evidence_apis_checked": [],
            "validator_results": {"receipt": "PASS", "forbidden_claims": "PASS", "regrounding": "PASS"},
        },
    )
    decisions_path = run_root / "page_decisions.jsonl"
    manifest["output_digests"]["page_decisions"] = (
        "sha256:" + hashlib.sha256(decisions_path.read_bytes()).hexdigest()
    )
    decisions = [
        json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]

    post_refresh_verify.configure(repo_root=tmp_path)
    try:
        with pytest.raises(ValueError, match="does not exactly reconcile"):
            post_refresh_verify._validate_bound_run_evidence(manifest, run_root, decisions)
    finally:
        post_refresh_verify.configure()
