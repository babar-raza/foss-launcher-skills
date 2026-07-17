"""Tests for skill_context.py — active-skill state machine."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

# Ensure scripts/pipeline is on sys.path for imports
_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import skill_context


class TestSkillContextBeginEnd(unittest.TestCase):
    """Tests for begin/end lifecycle."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_context_dir = skill_context._CONTEXT_DIR
        self.orig_active = skill_context._ACTIVE_FILE
        self.orig_history = skill_context._HISTORY_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_begin_creates_active_json(self):
        result = skill_context.main(["begin", "--skill", "S-20", "--scope", "content/docs*", "--skip-dar"])
        self.assertEqual(result, 0)
        self.assertTrue(skill_context._ACTIVE_FILE.exists())
        with open(skill_context._ACTIVE_FILE) as f:
            data = json.load(f)
        self.assertEqual(data["skill_id"], "S-20")
        self.assertEqual(data["context_type"], "skill")
        self.assertIn("content/docs*", data["scope_patterns"])

    def test_end_removes_active_and_archives(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "*", "--skip-dar"])
        result = skill_context.main(["end", "--skill", "S-20", "--status", "completed"])
        self.assertEqual(result, 0)
        self.assertFalse(skill_context._ACTIVE_FILE.exists())
        history_files = list(skill_context._HISTORY_DIR.glob("*.json"))
        self.assertEqual(len(history_files), 1)
        with open(history_files[0]) as f:
            data = json.load(f)
        self.assertEqual(data["end_status"], "completed")

    def test_end_without_active_is_noop(self):
        result = skill_context.main(["end", "--skill", "S-20", "--status", "completed"])
        self.assertEqual(result, 0)

    def test_begin_supersedes_existing(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "*", "--skip-dar"])
        result = skill_context.main(["begin", "--skill", "S-21", "--scope", "*", "--skip-dar"])
        self.assertEqual(result, 0)
        with open(skill_context._ACTIVE_FILE) as f:
            data = json.load(f)
        self.assertEqual(data["skill_id"], "S-21")
        # Prior context archived as superseded
        history_files = list(skill_context._HISTORY_DIR.glob("*.json"))
        self.assertEqual(len(history_files), 1)


class TestSkillContextCheck(unittest.TestCase):
    """Tests for check command."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_context_dir = skill_context._CONTEXT_DIR
        self.orig_active = skill_context._ACTIVE_FILE
        self.orig_history = skill_context._HISTORY_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_check_no_active_returns_2(self):
        result = skill_context.main(["check", "--file", "content/docs/foo.md"])
        self.assertEqual(result, 2)

    def test_check_in_scope_returns_0(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "content/docs*", "--skip-dar"])
        result = skill_context.main(["check", "--file", "content/docs.aspose.org/en/foo.md"])
        self.assertEqual(result, 0)

    def test_check_out_of_scope_returns_1(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "content/docs*", "--skip-dar"])
        result = skill_context.main(["check", "--file", "scripts/ci/foo.sh"])
        self.assertEqual(result, 1)

    def test_check_wildcard_scope_allows_all(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "*", "--skip-dar"])
        result = skill_context.main(["check", "--file", "scripts/pipeline/audit.py"])
        self.assertEqual(result, 0)


class TestSkillContextCurrent(unittest.TestCase):
    """Tests for current command."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_context_dir = skill_context._CONTEXT_DIR
        self.orig_active = skill_context._ACTIVE_FILE
        self.orig_history = skill_context._HISTORY_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_current_no_active_returns_2(self):
        result = skill_context.main(["current"])
        self.assertEqual(result, 2)

    def test_current_with_active_returns_0(self):
        skill_context.main(["begin", "--skill", "S-73", "--scope", "*", "--skip-dar"])
        result = skill_context.main(["current"])
        self.assertEqual(result, 0)


class TestSkillContextGap(unittest.TestCase):
    """Tests for gap-approved context."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        skill_context.configure(repo_root=self.tmp)

    def tearDown(self):
        skill_context.configure()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gap_requires_report(self):
        result = skill_context.main(["gap", "--task", "test", "--report", "nonexistent.md"])
        self.assertEqual(result, 1)

    def test_gap_with_valid_report_creates_context(self):
        report = self.tmp / "gap-report.md"
        report.write_text("SKILL GAP ESCALATION\nTask: test")
        result = skill_context.main(["gap", "--task", "test gap", "--report", str(report)])
        self.assertEqual(result, 0)
        self.assertTrue(skill_context._ACTIVE_FILE.exists())
        with open(skill_context._ACTIVE_FILE) as f:
            data = json.load(f)
        self.assertEqual(data["context_type"], "gap_approved")
        self.assertEqual(data["skill_id"], "GAP-APPROVED")
        self.assertEqual(data["ttl_minutes"], 30)


class TestSkillContextStaleness(unittest.TestCase):
    """Tests for stale context expiry."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_context_dir = skill_context._CONTEXT_DIR
        self.orig_active = skill_context._ACTIVE_FILE
        self.orig_history = skill_context._HISTORY_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stale_context_auto_expires(self):
        """A context older than 2 hours is treated as non-existent."""
        skill_context._CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        stale_time = (datetime.now(tz=timezone.utc) - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        record = {
            "skill_id": "S-OLD",
            "context_type": "skill",
            "scope_patterns": ["*"],
            "started_at": stale_time,
        }
        with open(skill_context._ACTIVE_FILE, "w") as f:
            json.dump(record, f)

        result = skill_context.main(["current"])
        self.assertEqual(result, 2)  # No active context (expired)
        self.assertFalse(skill_context._ACTIVE_FILE.exists())  # Cleaned up

    def test_gap_context_expires_after_30_min(self):
        """Gap-approved contexts expire after 30 minutes."""
        skill_context._CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        old_time = (datetime.now(tz=timezone.utc) - timedelta(minutes=35)).isoformat().replace("+00:00", "Z")
        record = {
            "skill_id": "GAP-APPROVED",
            "context_type": "gap_approved",
            "scope_patterns": ["*"],
            "started_at": old_time,
            "ttl_minutes": 30,
        }
        with open(skill_context._ACTIVE_FILE, "w") as f:
            json.dump(record, f)

        result = skill_context.main(["current"])
        self.assertEqual(result, 2)


class TestFileInScope(unittest.TestCase):
    """Tests for _file_in_scope helper."""

    def test_exact_glob_match(self):
        self.assertTrue(skill_context._file_in_scope(
            "content/docs.aspose.org/en/words/python/foo.md",
            ["content/docs.aspose.org/en/words/python/*"]
        ))

    def test_wildcard_matches_all(self):
        self.assertTrue(skill_context._file_in_scope("scripts/ci/foo.sh", ["*"]))

    def test_no_match(self):
        self.assertFalse(skill_context._file_in_scope(
            "scripts/ci/foo.sh",
            ["content/*"]
        ))

    def test_multiple_patterns(self):
        self.assertTrue(skill_context._file_in_scope(
            "scripts/pipeline/audit.py",
            ["content/*", "scripts/pipeline/*"]
        ))


class TestDAREnforcement(unittest.TestCase):
    """Tests for default DAR prerequisite enforcement (SR-04)."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_context_dir = skill_context._CONTEXT_DIR
        self.orig_active = skill_context._ACTIVE_FILE
        self.orig_history = skill_context._HISTORY_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dar_check_runs_by_default(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            result = skill_context.main(["begin", "--skill", "S-21", "--scope", "*"])
        self.assertEqual(result, 0)
        mock_run.assert_called_once()
        self.assertIn("check_dar_prerequisites.py", str(mock_run.call_args[0][0]))

    def test_dar_block_prevents_context_open(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=1)
            result = skill_context.main(["begin", "--skill", "S-21", "--scope", "*"])
        self.assertEqual(result, 1)
        self.assertFalse(skill_context._ACTIVE_FILE.exists())

    def test_dar_pass_opens_context(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            result = skill_context.main(["begin", "--skill", "S-21", "--scope", "*"])
        self.assertEqual(result, 0)
        self.assertTrue(skill_context._ACTIVE_FILE.exists())

    def test_skip_dar_bypasses_check(self):
        with mock.patch("subprocess.run") as mock_run:
            result = skill_context.main(["begin", "--skill", "S-21", "--scope", "*", "--skip-dar"])
        self.assertEqual(result, 0)
        mock_run.assert_not_called()

    def test_dar_script_missing_is_warn_not_block(self):
        temp_root = self.tmp / "fake_repo"
        temp_root.mkdir()
        orig_root = skill_context._REPO_ROOT
        skill_context._REPO_ROOT = temp_root
        try:
            result = skill_context.main(["begin", "--skill", "S-21", "--scope", "*"])
            self.assertEqual(result, 0)
            self.assertTrue(skill_context._ACTIVE_FILE.exists())
        finally:
            skill_context._REPO_ROOT = orig_root

    def test_legacy_check_dar_flag_still_accepted(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0)
            result = skill_context.main(["begin", "--skill", "S-21", "--scope", "*", "--check-dar"])
        self.assertEqual(result, 0)
        mock_run.assert_called_once()


class TestSkillContextOCC(unittest.TestCase):
    """RPR-G-03 (§2.5 SW-1): per-session optimistic concurrency control.

    Before this, cmd_begin unconditionally archived ANY existing ACTIVE.json as
    'superseded' with no session identity — two concurrent sessions silently clobbered
    each other's governance context (reproduced first-hand 4x during session 4).
    """

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.orig = (skill_context._CONTEXT_DIR, skill_context._ACTIVE_FILE,
                     skill_context._HISTORY_DIR, skill_context._ACTIVE_DIR)
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"
        skill_context._ACTIVE_DIR = skill_context._CONTEXT_DIR / "active"

    def tearDown(self):
        (skill_context._CONTEXT_DIR, skill_context._ACTIVE_FILE,
         skill_context._HISTORY_DIR, skill_context._ACTIVE_DIR) = self.orig
        self._td.cleanup()

    # ── scope overlap primitive ──────────────────────────────────────────
    def test_scope_overlap_detects_same_and_glob_matches(self):
        self.assertTrue(skill_context.scope_overlap(["a/b.py"], ["a/b.py"]))
        self.assertTrue(skill_context.scope_overlap(["a/*.py"], ["a/b.py"]))
        self.assertTrue(skill_context.scope_overlap(["a/b.py"], ["a/*.py"]))
        self.assertTrue(skill_context.scope_overlap(["*"], ["anything/at/all.py"]))
        self.assertFalse(skill_context.scope_overlap(["a/b.py"], ["c/d.py"]))
        self.assertFalse(skill_context.scope_overlap(["a/*.py"], ["c/*.py"]))

    # ── the core OCC behaviors ───────────────────────────────────────────
    def test_two_sessions_nonoverlapping_scope_coexist(self):
        r1 = skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                                 "--session-id", "sess-A", "--skip-dar"])
        r2 = skill_context.main(["begin", "--skill", "S-21", "--scope", "b/y.py",
                                 "--session-id", "sess-B", "--skip-dar"])
        self.assertEqual((r1, r2), (0, 0))
        live = skill_context._load_session_contexts()
        self.assertEqual(set(live), {"sess-A", "sess-B"})  # neither superseded the other

    def test_two_sessions_overlapping_scope_second_begin_fails_with_named_conflict(self):
        self.assertEqual(0, skill_context.main(
            ["begin", "--skill", "S-20", "--scope", "a/x.py", "--session-id", "sess-A", "--skip-dar"]))
        result = skill_context.main(
            ["begin", "--skill", "S-21", "--scope", "a/*.py", "--session-id", "sess-B", "--skip-dar"])
        self.assertEqual(result, 3)  # named conflict, NOT a silent supersede
        live = skill_context._load_session_contexts()
        self.assertEqual(set(live), {"sess-A"})  # A survives untouched
        self.assertEqual(live["sess-A"]["skill_id"], "S-20")

    def test_session_end_only_ends_own_context(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        skill_context.main(["begin", "--skill", "S-21", "--scope", "b/y.py",
                            "--session-id", "sess-B", "--skip-dar"])
        skill_context.main(["end", "--skill", "S-20", "--session-id", "sess-A"])
        live = skill_context._load_session_contexts()
        self.assertEqual(set(live), {"sess-B"})  # B untouched by A's end

    def test_rebegin_same_session_replaces_own_context_without_conflict(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        r = skill_context.main(["begin", "--skill", "S-22", "--scope", "a/x.py",
                                "--session-id", "sess-A", "--skip-dar"])
        self.assertEqual(r, 0)  # own scope is not a conflict with itself
        self.assertEqual(skill_context._load_session_contexts()["sess-A"]["skill_id"], "S-22")

    def test_stale_session_context_self_expires_per_ttl(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        p = skill_context._session_context_path("sess-A")
        rec = json.loads(p.read_text(encoding="utf-8"))
        rec["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        p.write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(skill_context._load_session_contexts(), {})  # expired
        self.assertFalse(p.exists())

    def test_archiving_stale_session_does_not_delete_legacy_active(self):
        """Regression guard: _archive() unlinks ACTIVE.json by default. Archiving a stale
        SESSION context must never destroy an unrelated legacy context."""
        skill_context.main(["begin", "--skill", "S-30", "--scope", "legacy/*", "--skip-dar"])
        self.assertTrue(skill_context._ACTIVE_FILE.exists())
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        p = skill_context._session_context_path("sess-A")
        rec = json.loads(p.read_text(encoding="utf-8"))
        rec["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        p.write_text(json.dumps(rec), encoding="utf-8")
        skill_context._load_session_contexts()  # triggers stale archive of sess-A
        self.assertTrue(skill_context._ACTIVE_FILE.exists(), "legacy ACTIVE.json was wrongly deleted")

    # ── backward compatibility (the non-negotiable acceptance) ───────────
    def test_existing_single_session_callers_unaffected(self):
        """Every current caller omits --session-id and must behave exactly as before:
        begin -> ACTIVE.json written; a second begin supersedes it (legacy semantics)."""
        self.assertEqual(0, skill_context.main(["begin", "--skill", "S-20", "--scope", "a/*", "--skip-dar"]))
        self.assertTrue(skill_context._ACTIVE_FILE.exists())
        self.assertEqual(skill_context._load_active()["skill_id"], "S-20")
        # legacy supersede still happens (unchanged behavior)
        self.assertEqual(0, skill_context.main(["begin", "--skill", "S-21", "--scope", "b/*", "--skip-dar"]))
        self.assertEqual(skill_context._load_active()["skill_id"], "S-21")
        self.assertEqual(0, skill_context.main(["end", "--skill", "S-21"]))
        self.assertIsNone(skill_context._load_active())
        # no session files were created by legacy callers
        self.assertEqual(skill_context._load_session_contexts(), {})

    def test_check_with_session_id_isolates_to_that_session(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        self.assertEqual(0, skill_context.main(["check", "--file", "a/x.py", "--session-id", "sess-A"]))
        self.assertEqual(1, skill_context.main(["check", "--file", "b/y.py", "--session-id", "sess-A"]))
        self.assertEqual(2, skill_context.main(["check", "--file", "a/x.py", "--session-id", "sess-Z"]))

    def test_legacy_check_also_honors_session_contexts(self):
        """A session on the OCC path must not be blocked by a hook that doesn't know its id."""
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        self.assertEqual(0, skill_context.main(["check", "--file", "a/x.py"]))


if __name__ == "__main__":
    unittest.main()
