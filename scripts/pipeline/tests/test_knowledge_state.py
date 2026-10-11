"""MT030-2026-08-13: knowledge_state.py -- durable per-product pipeline-state projection."""
import json

import pytest

# sys.path is set by tests/conftest.py
import knowledge_state as ks


@pytest.fixture(autouse=True)
def _isolate_state_file(tmp_path, monkeypatch):
    """Point the module at a throwaway file/lock per test -- never touch the real
    data/knowledge_state.json from the test suite."""
    state_path = tmp_path / "knowledge_state.json"
    lock_path = tmp_path / "knowledge_state.json.lock"
    monkeypatch.setattr(ks, "_STATE_PATH", state_path)
    monkeypatch.setattr(ks, "_LOCK_PATH", lock_path)
    yield state_path


class TestRecordBaselineAccepted:
    def test_writes_new_product(self, _isolate_state_file):
        ks.record_baseline_accepted(
            "pdf", "java", repo_sha="be089a7e...", sha_source="scout",
            run_id="promote-20260729T164123Z", accepted_at="2026-07-29T16:41:23Z",
        )
        state = ks.read_state("pdf", "java")
        assert state["accepted_baseline"]["repo_sha"] == "be089a7e..."
        assert state["family"] == "pdf"
        assert state["platform"] == "java"

    def test_overwrites_only_its_own_section(self, _isolate_state_file):
        ks.record_truth_audit(
            "pdf", "java", fail_count=1, warn_count=60,
            report_path="reports/audit/pdf-java-truth-20260805.md",
            recorded_at="2026-08-05T15:29:00Z",
        )
        ks.record_baseline_accepted(
            "pdf", "java", repo_sha="be089a7e...", sha_source="scout",
            run_id="promote-20260729T164123Z", accepted_at="2026-07-29T16:41:23Z",
        )
        state = ks.read_state("pdf", "java")
        assert state["truth_audit"]["fail_count"] == 1  # untouched by the baseline write
        assert state["accepted_baseline"]["repo_sha"] == "be089a7e..."

    def test_idempotent_rerun_same_content(self, _isolate_state_file):
        kwargs = dict(
            repo_sha="be089a7e...", sha_source="scout",
            run_id="promote-20260729T164123Z", accepted_at="2026-07-29T16:41:23Z",
        )
        ks.record_baseline_accepted("pdf", "java", **kwargs)
        first = _isolate_state_file.read_text(encoding="utf-8")
        ks.record_baseline_accepted("pdf", "java", **kwargs)
        second = _isolate_state_file.read_text(encoding="utf-8")
        assert first == second


class TestRecordTruthAudit:
    def test_verdict_derived_from_fail_count(self, _isolate_state_file):
        ks.record_truth_audit(
            "pdf", "java", fail_count=0, warn_count=59,
            report_path="reports/audit/pdf-java-truth-20260813.md",
            recorded_at="2026-08-13T09:49:00Z",
        )
        state = ks.read_state("pdf", "java")
        assert state["truth_audit"]["verdict"] == "PASS"

        ks.record_truth_audit(
            "pdf", "java", fail_count=3, warn_count=10,
            report_path="reports/audit/pdf-java-truth-x.md",
            recorded_at="2026-08-14T00:00:00Z",
        )
        state = ks.read_state("pdf", "java")
        assert state["truth_audit"]["verdict"] == "FAIL"
        assert state["truth_audit"]["fail_count"] == 3


class TestRecordEvidenceSkip:
    def test_records_multiple_skips_by_filepath(self, _isolate_state_file):
        ks.record_evidence_skip(
            "pdf", "java", "content/kb.aspose.org/en/pdf/java/use-cases.md",
            reason="audit_fail", recorded_at="2026-08-05T15:29:00Z",
        )
        ks.record_evidence_skip(
            "pdf", "java", "content/reference.aspose.org/en/pdf/java/SetLineJoin.md",
            reason="draft", recorded_at="2026-08-05T15:29:00Z",
        )
        state = ks.read_state("pdf", "java")
        skips = state["evidence_skips"]
        assert len(skips) == 2
        assert skips["content/kb.aspose.org/en/pdf/java/use-cases.md"]["reason"] == "audit_fail"
        assert skips["content/reference.aspose.org/en/pdf/java/SetLineJoin.md"]["reason"] == "draft"

    def test_re_recording_same_file_updates_in_place(self, _isolate_state_file):
        ks.record_evidence_skip(
            "pdf", "java", "content/kb.aspose.org/en/pdf/java/use-cases.md",
            reason="audit_fail", recorded_at="2026-08-05T15:29:00Z",
        )
        ks.record_evidence_skip(
            "pdf", "java", "content/kb.aspose.org/en/pdf/java/use-cases.md",
            reason="audit_fail", recorded_at="2026-08-13T09:40:00Z",
        )
        state = ks.read_state("pdf", "java")
        assert len(state["evidence_skips"]) == 1
        assert state["evidence_skips"]["content/kb.aspose.org/en/pdf/java/use-cases.md"]["recorded_at"] == "2026-08-13T09:40:00Z"


class TestReadHelpers:
    def test_read_state_returns_none_for_unknown_product(self, _isolate_state_file):
        assert ks.read_state("nonexistent", "platform") is None

    def test_read_all_returns_full_dict(self, _isolate_state_file):
        ks.record_baseline_accepted(
            "pdf", "java", repo_sha="sha1", sha_source="scout",
            run_id="run1", accepted_at="2026-01-01T00:00:00Z",
        )
        ks.record_baseline_accepted(
            "3d", "net", repo_sha="sha2", sha_source="scout",
            run_id="run2", accepted_at="2026-01-02T00:00:00Z",
        )
        all_state = ks.read_all()
        assert set(all_state.keys()) == {"pdf/java", "3d/net"}

    def test_read_all_tolerates_missing_file(self, _isolate_state_file):
        assert ks.read_all() == {}

    def test_read_all_tolerates_corrupt_file(self, _isolate_state_file):
        _isolate_state_file.write_text("{not valid json", encoding="utf-8")
        assert ks.read_all() == {}


class TestFileFormat:
    def test_written_file_is_pretty_printed_json(self, _isolate_state_file):
        ks.record_baseline_accepted(
            "pdf", "java", repo_sha="sha1", sha_source="scout",
            run_id="run1", accepted_at="2026-01-01T00:00:00Z",
        )
        raw = _isolate_state_file.read_text(encoding="utf-8")
        parsed = json.loads(raw)  # must be valid JSON
        assert "pdf/java" in parsed
        assert raw.endswith("\n")
