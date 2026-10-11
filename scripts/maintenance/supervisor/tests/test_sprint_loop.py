"""
test_sprint_loop.py -- Tests for the post-sprint autonomy loop orchestrator.

Covers: state lifecycle, state resilience (checksum, backup, recovery),
validation + repair, template injection, decision + compliance scoring, bundling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUPERVISOR = _HERE.parent
sys.path.insert(0, str(_SUPERVISOR))

import sprint_loop


class _TempStateBase(unittest.TestCase):
    """Base class that redirects state and evidence to temp dirs."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_dir = Path(self.tmpdir) / "state"
        self.state_dir.mkdir()
        self.evidence_root = Path(self.tmpdir) / "evidences"
        self.evidence_root.mkdir()
        self.bundle_root = Path(self.tmpdir) / "bundles"
        self.bundle_root.mkdir()

        # Redirect module-level paths
        self._orig_state_dir = sprint_loop.STATE_DIR
        self._orig_state_file = sprint_loop.STATE_FILE
        self._orig_state_backup = sprint_loop.STATE_BACKUP
        self._orig_evidence_root = sprint_loop.EVIDENCE_ROOT
        self._orig_bundle_root = sprint_loop.BUNDLE_ROOT

        sprint_loop.STATE_DIR = self.state_dir
        sprint_loop.STATE_FILE = self.state_dir / "loop-state.json"
        sprint_loop.STATE_BACKUP = self.state_dir / "loop-state.json.bak"
        sprint_loop.EVIDENCE_ROOT = self.evidence_root
        sprint_loop.BUNDLE_ROOT = self.bundle_root

    def tearDown(self):
        sprint_loop.STATE_DIR = self._orig_state_dir
        sprint_loop.STATE_FILE = self._orig_state_file
        sprint_loop.STATE_BACKUP = self._orig_state_backup
        sprint_loop.EVIDENCE_ROOT = self._orig_evidence_root
        sprint_loop.BUNDLE_ROOT = self._orig_bundle_root
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_state(self, **overrides):
        """Create and save a valid state."""
        state = {
            "sprint_id": "test-001",
            "stage": "P1",
            "decision": None,
            "next_stage": None,
            "retry_count": 0,
            "compliance_score": None,
            "evidence_dir": str(self.evidence_root / "test-001"),
            "started": "2026-06-15T00:00:00+00:00",
            "last_updated": None,
        }
        state.update(overrides)
        (self.evidence_root / "test-001").mkdir(exist_ok=True)
        sprint_loop._save_state(state)
        return state

    def _write_all_green_evidence(self, evidence_dir: Path):
        """Write valid stage3 evidence files."""
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "stage3-execution-log.md").write_text("# Log", encoding="utf-8")
        summary = textwrap.dedent("""\
            outcome: ALL_GREEN
            retry_count: 0
            scores:
              accuracy: 5
              completeness: 5
              evidence: 5
            taskcards:
              - id: TC-001
                status: ACCEPTED
            evidence_files:
              - stage3-execution-log.md
        """)
        (evidence_dir / "stage3-final-sprint-summary.yaml").write_text(summary, encoding="utf-8")


# ---- State lifecycle tests ----

class TestInit(_TempStateBase):
    def test_init_creates_state_and_dir(self):
        args = _make_args(command="init", sprint_id="test-001")
        rc = sprint_loop.cmd_init(args)
        self.assertEqual(rc, 0)
        state = sprint_loop._load_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["sprint_id"], "test-001")
        self.assertEqual(state["stage"], "P1")
        self.assertTrue((self.evidence_root / "test-001").is_dir())

    def test_init_rejects_duplicate_sprint(self):
        self._make_state(sprint_id="test-001")
        args = _make_args(command="init", sprint_id="test-001")
        rc = sprint_loop.cmd_init(args)
        self.assertEqual(rc, 1)


class TestStatus(_TempStateBase):
    def test_status_reads_state(self):
        self._make_state()
        args = _make_args(command="status")
        rc = sprint_loop.cmd_status(args)
        self.assertEqual(rc, 0)

    def test_status_no_state_exits_clean(self):
        args = _make_args(command="status")
        rc = sprint_loop.cmd_status(args)
        self.assertEqual(rc, 0)


class TestReset(_TempStateBase):
    def test_reset_clears_state(self):
        self._make_state()
        self.assertTrue(sprint_loop.STATE_FILE.exists())
        args = _make_args(command="reset")
        rc = sprint_loop.cmd_reset(args)
        self.assertEqual(rc, 0)
        self.assertFalse(sprint_loop.STATE_FILE.exists())


# ---- State resilience tests ----

class TestStateResilience(_TempStateBase):
    def test_save_state_writes_checksum(self):
        self._make_state()
        data = json.loads(sprint_loop.STATE_FILE.read_text(encoding="utf-8"))
        self.assertIn("_checksum", data)
        expected = sprint_loop._compute_checksum(data)
        self.assertEqual(data["_checksum"], expected)

    def test_load_state_verifies_checksum(self):
        self._make_state()
        # First load creates the backup
        sprint_loop._load_state()
        self.assertTrue(sprint_loop.STATE_BACKUP.exists())
        # Now tamper with state file (change stage without updating checksum)
        data = json.loads(sprint_loop.STATE_FILE.read_text(encoding="utf-8"))
        data["stage"] = "P3"
        sprint_loop.STATE_FILE.write_text(json.dumps(data), encoding="utf-8")
        # Should fall back to backup (which has the original P1 state)
        loaded = sprint_loop._load_state()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["stage"], "P1")  # From backup

    def test_load_state_creates_backup(self):
        self._make_state()
        self.assertFalse(sprint_loop.STATE_BACKUP.exists())
        sprint_loop._load_state()
        self.assertTrue(sprint_loop.STATE_BACKUP.exists())

    def test_load_state_corrupt_primary_uses_backup(self):
        self._make_state()
        sprint_loop._load_state()  # Creates backup
        # Corrupt primary
        sprint_loop.STATE_FILE.write_text("NOT JSON", encoding="utf-8")
        loaded = sprint_loop._load_state()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["sprint_id"], "test-001")


class TestRecover(_TempStateBase):
    def test_recover_restores_from_backup(self):
        self._make_state()
        sprint_loop._load_state()  # Creates backup
        sprint_loop.STATE_FILE.write_text("CORRUPT", encoding="utf-8")
        args = _make_args(command="recover")
        rc = sprint_loop.cmd_recover(args)
        self.assertEqual(rc, 0)
        loaded = sprint_loop._load_state()
        self.assertIsNotNone(loaded)

    def test_recover_rebuilds_from_evidence(self):
        # Create evidence dir with stage1 files but no state
        ev_dir = self.evidence_root / "rebuilt-sprint"
        ev_dir.mkdir()
        (ev_dir / "stage1-sprint-audit-summary.md").write_text("# Audit", encoding="utf-8")
        args = _make_args(command="recover")
        rc = sprint_loop.cmd_recover(args)
        self.assertEqual(rc, 0)
        state = sprint_loop._load_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["sprint_id"], "rebuilt-sprint")


# ---- Validation + repair tests ----

class TestValidation(_TempStateBase):
    def test_validate_stage1_missing_files(self):
        ev_dir = self.evidence_root / "test-001"
        ev_dir.mkdir(parents=True, exist_ok=True)
        valid, issues = sprint_loop.validate_stage_outputs("P1", ev_dir)
        self.assertFalse(valid)
        missing_count = sum(1 for i in issues if i.startswith("MISSING:"))
        self.assertGreater(missing_count, 0)

    def test_validate_stage1_complete(self):
        ev_dir = self.evidence_root / "test-001"
        ev_dir.mkdir(parents=True, exist_ok=True)
        outputs = sprint_loop._get_required_outputs("P1")
        for f in outputs:
            filepath = ev_dir / f
            if f.endswith(".yaml"):
                filepath.write_text("issue_id: I-001\nissue_level: L1\nrecommendation: test\n", encoding="utf-8")
            else:
                filepath.write_text("# Content\n", encoding="utf-8")
        valid, issues = sprint_loop.validate_stage_outputs("P1", ev_dir)
        critical = [i for i in issues if i.startswith(("MISSING:", "EMPTY:", "PARSE_ERROR:", "MISSING_KEY:"))]
        self.assertEqual(len(critical), 0, f"Unexpected critical issues: {critical}")

    def test_validate_stage3_missing_yaml_keys(self):
        ev_dir = self.evidence_root / "test-001"
        ev_dir.mkdir(parents=True, exist_ok=True)
        outputs = sprint_loop._get_required_outputs("P3")
        for f in outputs:
            filepath = ev_dir / f
            if f == "stage3-final-sprint-summary.yaml":
                filepath.write_text("notes: something\n", encoding="utf-8")
            elif f.endswith(".yaml"):
                filepath.write_text("key: value\n", encoding="utf-8")
            else:
                filepath.write_text("# Content\n", encoding="utf-8")
        valid, issues = sprint_loop.validate_stage_outputs("P3", ev_dir)
        key_issues = [i for i in issues if i.startswith("MISSING_KEY:")]
        self.assertGreater(len(key_issues), 0)

    def test_validate_stage3_complete(self):
        ev_dir = self.evidence_root / "test-001"
        ev_dir.mkdir(parents=True, exist_ok=True)
        outputs = sprint_loop._get_required_outputs("P3")
        for f in outputs:
            filepath = ev_dir / f
            if f == "stage3-final-sprint-summary.yaml":
                filepath.write_text(
                    "outcome: ALL_GREEN\nscores:\n  a: 5\ntaskcards:\n  - id: TC-1\nevidence_files:\n  - log.md\n",
                    encoding="utf-8",
                )
            elif f.endswith(".yaml"):
                filepath.write_text("key: value\n", encoding="utf-8")
            else:
                filepath.write_text("# Content\n", encoding="utf-8")
        valid, issues = sprint_loop.validate_stage_outputs("P3", ev_dir)
        critical = [i for i in issues if i.startswith(("MISSING:", "EMPTY:", "PARSE_ERROR:", "MISSING_KEY:"))]
        self.assertEqual(len(critical), 0, f"Unexpected critical issues: {critical}")

    def test_validate_repair_strips_fences(self):
        ev_dir = self.evidence_root / "test-001"
        ev_dir.mkdir(parents=True, exist_ok=True)
        outputs = sprint_loop._get_required_outputs("P3")
        for f in outputs:
            filepath = ev_dir / f
            if f == "stage3-final-sprint-summary.yaml":
                filepath.write_text(
                    "```yaml\noutcome: ALL_GREEN\nscores:\n  a: 5\ntaskcards:\n  - id: TC-1\nevidence_files:\n  - log.md\n```\n",
                    encoding="utf-8",
                )
            elif f.endswith(".yaml"):
                filepath.write_text("key: value\n", encoding="utf-8")
            else:
                filepath.write_text("# Content\n", encoding="utf-8")
        valid, issues = sprint_loop.validate_stage_outputs("P3", ev_dir, repair=True)
        repaired = [i for i in issues if "REPAIRED" in i]
        self.assertGreater(len(repaired), 0)
        critical = [i for i in issues if i.startswith(("MISSING:", "EMPTY:", "PARSE_ERROR:", "MISSING_KEY:"))]
        self.assertEqual(len(critical), 0)

    def test_validate_repair_relocates_files(self):
        ev_dir = self.evidence_root / "test-001"
        ev_dir.mkdir(parents=True, exist_ok=True)
        sub = ev_dir / "subdir"
        sub.mkdir()
        outputs = sprint_loop._get_required_outputs("P1")
        if outputs:
            target_file = outputs[0]
            (sub / target_file).write_text("# Content\n", encoding="utf-8")
            for f in outputs[1:]:
                filepath = ev_dir / f
                if f.endswith(".yaml"):
                    filepath.write_text("issue_id: I-001\nissue_level: L1\nrecommendation: test\n", encoding="utf-8")
                else:
                    filepath.write_text("# Content\n", encoding="utf-8")
            valid, issues = sprint_loop.validate_stage_outputs("P1", ev_dir, repair=True)
            relocated = [i for i in issues if "relocated" in i]
            self.assertGreater(len(relocated), 0)


# ---- Template injection tests ----

class TestInjectTemplate(_TempStateBase):
    def test_inject_template_creates_skeleton_files(self):
        self._make_state()
        ev_dir = self.evidence_root / "test-001"
        args = _make_args(command="inject-template", stage="P1", evidence_dir=str(ev_dir))
        rc = sprint_loop.cmd_inject_template(args)
        self.assertEqual(rc, 0)
        outputs = sprint_loop._get_required_outputs("P1")
        for f in outputs:
            self.assertTrue((ev_dir / f).exists(), f"Template not created: {f}")

    def test_inject_template_does_not_overwrite_existing(self):
        self._make_state()
        ev_dir = self.evidence_root / "test-001"
        outputs = sprint_loop._get_required_outputs("P1")
        if outputs:
            existing = ev_dir / outputs[0]
            existing.write_text("EXISTING CONTENT", encoding="utf-8")
            args = _make_args(command="inject-template", stage="P1", evidence_dir=str(ev_dir))
            sprint_loop.cmd_inject_template(args)
            self.assertEqual(existing.read_text(encoding="utf-8"), "EXISTING CONTENT")


# ---- Decision + compliance tests ----

class TestDecide(_TempStateBase):
    def test_decide_updates_state(self):
        ev_dir = self.evidence_root / "test-001"
        self._make_state(stage="P3", evidence_dir=str(ev_dir))
        self._write_all_green_evidence(ev_dir)
        args = _make_args(command="decide", evidence_dir=str(ev_dir))
        rc = sprint_loop.cmd_decide(args)
        self.assertEqual(rc, 0)
        state = sprint_loop._load_state()
        self.assertEqual(state["stage"], "ACCEPTED")

    def test_decide_prose_only_routes_to_p2(self):
        ev_dir = self.evidence_root / "test-001"
        self._make_state(stage="P3", evidence_dir=str(ev_dir))
        ev_dir.mkdir(parents=True, exist_ok=True)
        (ev_dir / "stage3-final-sprint-summary.yaml").write_text(
            "notes: This is just prose without structure\n", encoding="utf-8"
        )
        args = _make_args(command="decide", evidence_dir=str(ev_dir))
        sprint_loop.cmd_decide(args)
        state = sprint_loop._load_state()
        self.assertEqual(state["stage"], "P2")

    def test_decide_missing_routes_to_p1(self):
        ev_dir = self.evidence_root / "test-001"
        self._make_state(stage="P3", evidence_dir=str(ev_dir))
        ev_dir.mkdir(parents=True, exist_ok=True)
        args = _make_args(command="decide", evidence_dir=str(ev_dir))
        sprint_loop.cmd_decide(args)
        state = sprint_loop._load_state()
        self.assertEqual(state["stage"], "P1")

    def test_decide_all_green_routes_to_accepted(self):
        ev_dir = self.evidence_root / "test-001"
        self._make_state(stage="P3", evidence_dir=str(ev_dir))
        self._write_all_green_evidence(ev_dir)
        args = _make_args(command="decide", evidence_dir=str(ev_dir))
        sprint_loop.cmd_decide(args)
        state = sprint_loop._load_state()
        self.assertEqual(state["stage"], "ACCEPTED")
        self.assertEqual(state["decision"], "ACCEPT")

    def test_decide_contradictory_blocks(self):
        ev_dir = self.evidence_root / "test-001"
        self._make_state(stage="P3", evidence_dir=str(ev_dir))
        ev_dir.mkdir(parents=True, exist_ok=True)
        summary = textwrap.dedent("""\
            outcome: ALL_GREEN
            scores:
              accuracy: 2
              completeness: 5
            taskcards:
              - id: TC-001
                status: ACCEPTED
            evidence_files:
              - stage3-execution-log.md
        """)
        (ev_dir / "stage3-final-sprint-summary.yaml").write_text(summary, encoding="utf-8")
        (ev_dir / "stage3-execution-log.md").write_text("# Log", encoding="utf-8")
        args = _make_args(command="decide", evidence_dir=str(ev_dir))
        rc = sprint_loop.cmd_decide(args)
        self.assertEqual(rc, 2)
        state = sprint_loop._load_state()
        self.assertEqual(state["stage"], "BLOCKED")

    def test_decide_increments_retry(self):
        ev_dir = self.evidence_root / "test-001"
        self._make_state(stage="P3", retry_count=0, evidence_dir=str(ev_dir))
        ev_dir.mkdir(parents=True, exist_ok=True)
        (ev_dir / "stage3-final-sprint-summary.yaml").write_text(
            "notes: prose only\n", encoding="utf-8"
        )
        args = _make_args(command="decide", evidence_dir=str(ev_dir))
        sprint_loop.cmd_decide(args)
        state = sprint_loop._load_state()
        self.assertEqual(state["retry_count"], 1)

    def test_decide_records_compliance_score(self):
        ev_dir = self.evidence_root / "test-001"
        self._make_state(stage="P3", evidence_dir=str(ev_dir))
        self._write_all_green_evidence(ev_dir)
        args = _make_args(command="decide", evidence_dir=str(ev_dir))
        sprint_loop.cmd_decide(args)
        state = sprint_loop._load_state()
        self.assertIsNotNone(state.get("compliance_score"))


# ---- Bundle tests ----

class TestBundle(_TempStateBase):
    def test_bundle_creates_zip(self):
        ev_dir = self.evidence_root / "test-001"
        self._make_state(stage="P3", evidence_dir=str(ev_dir))
        self._write_all_green_evidence(ev_dir)
        args = _make_args(command="bundle")
        rc = sprint_loop.cmd_bundle(args)
        self.assertEqual(rc, 0)
        zip_path = self.bundle_root / "test-001.zip"
        self.assertTrue(zip_path.exists())
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            self.assertIn("manifest.json", names)
            self.assertIn("loop-state.json", names)


# ---- Helper ----

def _make_args(**kwargs):
    """Create a namespace mimicking argparse output."""
    defaults = {
        "command": None,
        "sprint_id": None,
        "stage": None,
        "evidence_dir": None,
        "repair": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


if __name__ == "__main__":
    unittest.main()
