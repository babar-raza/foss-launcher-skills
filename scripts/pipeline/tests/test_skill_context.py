"""Tests for skill_context.py — active-skill state machine."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

# Ensure scripts/pipeline is on sys.path for imports
_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import pytest

import skill_context


@pytest.fixture(autouse=True)
def _clear_agent_session_env(monkeypatch):
    """Keep legacy-path tests hermetic: a developer/agent shell exporting
    AGENT_SESSION_ID (the HARDEN-A2 convention) must not leak in and silently
    reroute flag-less calls onto the per-session path. CLAUDE_CODE_SESSION_ID
    is set by the real harness running this very test suite (RC1/RC2
    hardening, 2026-07-31), so it must be cleared here too or every
    legacy-path test would silently flip to the per-session path only when
    run inside an actual Claude Code session."""
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)


def test_session_id_resolution_precedence(monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-thread")
    assert skill_context._derive_session_id(None) == "codex-thread"

    monkeypatch.setenv("AGENT_SESSION_ID", "agent-session")
    assert skill_context._derive_session_id(None) == "agent-session"
    assert skill_context._derive_session_id("explicit-session") == "explicit-session"


def test_codex_thread_id_is_sanitized(monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "thread/id with spaces")
    assert skill_context._derive_session_id(None) == "thread-id-with-spaces"


class TestSkillContextBeginEnd(unittest.TestCase):
    """Tests for begin/end lifecycle."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_context_dir = skill_context._CONTEXT_DIR
        self.orig_active = skill_context._ACTIVE_FILE
        self.orig_history = skill_context._HISTORY_DIR
        self.orig_active_dir = skill_context._ACTIVE_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"
        skill_context._ACTIVE_DIR = skill_context._CONTEXT_DIR / "active"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        skill_context._ACTIVE_DIR = self.orig_active_dir
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

    def test_begin_same_skill_supersedes_own_context(self):
        """HARDEN-A2: same-skill re-begin (the per-edit scope re-arm loop) still
        replaces the prior context — this is the standard single-session flow."""
        skill_context.main(["begin", "--skill", "S-20", "--scope", "*", "--skip-dar"])
        result = skill_context.main(["begin", "--skill", "S-20", "--scope", "a/*", "--skip-dar"])
        self.assertEqual(result, 0)
        with open(skill_context._ACTIVE_FILE) as f:
            data = json.load(f)
        self.assertEqual(data["skill_id"], "S-20")
        self.assertEqual(data["scope_patterns"], ["a/*"])
        history_files = list(skill_context._HISTORY_DIR.glob("*.json"))
        self.assertEqual(len(history_files), 1)
        with open(history_files[0]) as f:
            archived = json.load(f)
        self.assertEqual(archived["end_status"], "superseded_same_skill")

    def test_begin_different_skill_without_identity_conflicts(self):
        """HARDEN-A2: a live context for a DIFFERENT skill is a named conflict
        (exit 3), never a silent supersede — the old clobber let one session
        destroy another's governance state."""
        skill_context.main(["begin", "--skill", "S-20", "--scope", "*", "--skip-dar"])
        result = skill_context.main(["begin", "--skill", "S-21", "--scope", "*", "--skip-dar"])
        self.assertEqual(result, 3)
        # The original context is untouched
        with open(skill_context._ACTIVE_FILE) as f:
            data = json.load(f)
        self.assertEqual(data["skill_id"], "S-20")
        self.assertEqual(list(skill_context._HISTORY_DIR.glob("*.json"))
                         if skill_context._HISTORY_DIR.exists() else [], [])


class TestSkillContextCheck(unittest.TestCase):
    """Tests for check command."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_context_dir = skill_context._CONTEXT_DIR
        self.orig_active = skill_context._ACTIVE_FILE
        self.orig_history = skill_context._HISTORY_DIR
        self.orig_active_dir = skill_context._ACTIVE_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"
        skill_context._ACTIVE_DIR = skill_context._CONTEXT_DIR / "active"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        skill_context._ACTIVE_DIR = self.orig_active_dir
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
        self.orig_active_dir = skill_context._ACTIVE_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"
        skill_context._ACTIVE_DIR = skill_context._CONTEXT_DIR / "active"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        skill_context._ACTIVE_DIR = self.orig_active_dir
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_current_no_active_returns_2(self):
        result = skill_context.main(["current"])
        self.assertEqual(result, 2)

    def test_current_with_active_returns_0(self):
        skill_context.main(["begin", "--skill", "S-73", "--scope", "*", "--skip-dar"])
        result = skill_context.main(["current"])
        self.assertEqual(result, 0)


class TestSkillContextStatus(unittest.TestCase):
    """Tests for the read-only `status` command (RC1/RC2 hardening, 2026-07-31).

    The core property under test: status must NEVER mutate or delete
    anything on disk, unlike current/_load_active/_load_session_contexts,
    which archive-and-delete stale records as a side effect of being read.
    """

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.orig_context_dir = skill_context._CONTEXT_DIR
        self.orig_active = skill_context._ACTIVE_FILE
        self.orig_history = skill_context._HISTORY_DIR
        self.orig_active_dir = skill_context._ACTIVE_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"
        skill_context._ACTIVE_DIR = skill_context._CONTEXT_DIR / "active"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        skill_context._ACTIVE_DIR = self.orig_active_dir
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_status_empty_reports_nothing_and_exits_0(self):
        self.assertEqual(0, skill_context.main(["status"]))

    def test_status_never_mutates_a_stale_legacy_record(self):
        """THE core safety property: reading status on a stale record must
        leave the file exactly as it was -- no archive, no delete."""
        skill_context._CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        stale_time = (datetime.now(tz=timezone.utc) - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        record = {"skill_id": "S-OLD", "context_type": "skill",
                  "scope_patterns": ["*"], "started_at": stale_time}
        with open(skill_context._ACTIVE_FILE, "w") as f:
            json.dump(record, f)
        before = skill_context._ACTIVE_FILE.read_text(encoding="utf-8")

        self.assertEqual(0, skill_context.main(["status"]))

        self.assertTrue(skill_context._ACTIVE_FILE.exists(), "status must not delete the stale record")
        self.assertEqual(before, skill_context._ACTIVE_FILE.read_text(encoding="utf-8"),
                          "status must not modify the record at all")
        self.assertEqual(0, len(list(skill_context._HISTORY_DIR.glob("*.json")) if
                                 skill_context._HISTORY_DIR.exists() else []),
                          "status must not archive anything to history")

    def test_status_never_mutates_a_stale_session_record(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        p = skill_context._session_context_path("sess-A")
        rec = json.loads(p.read_text(encoding="utf-8"))
        rec["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        p.write_text(json.dumps(rec), encoding="utf-8")
        before = p.read_text(encoding="utf-8")

        self.assertEqual(0, skill_context.main(["status"]))

        self.assertTrue(p.exists(), "status must not delete the stale session record")
        self.assertEqual(before, p.read_text(encoding="utf-8"))

    def test_status_json_reports_live_and_stale_correctly(self):
        skill_context.main(["begin", "--skill", "S-73", "--scope", "content/*", "--skip-dar"])
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        p = skill_context._session_context_path("sess-A")
        rec = json.loads(p.read_text(encoding="utf-8"))
        rec["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        p.write_text(json.dumps(rec), encoding="utf-8")

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(0, skill_context.main(["status", "--json"]))
        report = json.loads(buf.getvalue())

        self.assertEqual(report["legacy"]["skill_id"], "S-73")
        self.assertFalse(report["legacy"]["would_be_stale"])
        self.assertEqual(report["sessions"]["sess-A"]["skill_id"], "S-20")
        self.assertTrue(report["sessions"]["sess-A"]["would_be_stale"])


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
        self.orig_active_dir = skill_context._ACTIVE_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"
        skill_context._ACTIVE_DIR = skill_context._CONTEXT_DIR / "active"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        skill_context._ACTIVE_DIR = self.orig_active_dir
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

    # ── heartbeat-based staleness (RC1/RC2 hardening, 2026-07-31) ──────────
    #
    # Previously staleness was measured purely from started_at: a context
    # still being actively worked could be wrongly expired after 2h, and an
    # abandoned one read as "live" for the full 2h regardless of how quickly
    # it actually went idle. last_touched_at (bumped by `check` on every
    # in-scope hit) fixes both directions.

    def test_heartbeat_keeps_long_running_context_alive_past_original_ttl(self):
        """A context begun >2h ago but touched recently must NOT expire."""
        skill_context._CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        long_ago = (datetime.now(tz=timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        recent = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        record = {
            "skill_id": "S-LONG",
            "context_type": "skill",
            "scope_patterns": ["*"],
            "started_at": long_ago,
            "last_touched_at": recent,
        }
        with open(skill_context._ACTIVE_FILE, "w") as f:
            json.dump(record, f)

        result = skill_context.main(["current"])
        self.assertEqual(result, 0)
        self.assertTrue(skill_context._ACTIVE_FILE.exists())

    def test_check_bumps_heartbeat_on_in_scope_hit(self):
        """cmd_check must persist a fresh last_touched_at when it returns 0,
        so the NEXT staleness check measures from this activity, not from
        whenever the context originally began."""
        skill_context.main(["begin", "--skill", "S-73", "--scope", "a/*.py", "--skip-dar"])
        before = json.loads(skill_context._ACTIVE_FILE.read_text(encoding="utf-8"))
        self.assertNotIn("last_touched_at", before)  # not set until first touch

        self.assertEqual(0, skill_context.main(["check", "--file", "a/x.py"]))
        after = json.loads(skill_context._ACTIVE_FILE.read_text(encoding="utf-8"))
        self.assertIn("last_touched_at", after)

    def test_quiet_context_still_expires_per_ttl_from_last_activity(self):
        """A context whose last real activity (not just its start) is more
        than one TTL ago must still expire -- the heartbeat must not be able
        to keep something alive forever once it truly goes quiet."""
        skill_context._CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        old_time = (datetime.now(tz=timezone.utc) - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        record = {
            "skill_id": "S-QUIET",
            "context_type": "skill",
            "scope_patterns": ["*"],
            "started_at": old_time,
            "last_touched_at": old_time,  # last activity was also 3h ago
        }
        with open(skill_context._ACTIVE_FILE, "w") as f:
            json.dump(record, f)

        result = skill_context.main(["current"])
        self.assertEqual(result, 2)
        self.assertFalse(skill_context._ACTIVE_FILE.exists())

    def test_legacy_record_without_last_touched_at_falls_back_to_started_at(self):
        """Backward compatibility: records written before this field existed
        (no last_touched_at at all) must behave exactly as before -- staleness
        measured from started_at alone."""
        skill_context._CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        recent = (datetime.now(tz=timezone.utc) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        record = {
            "skill_id": "S-OLD-FORMAT",
            "context_type": "skill",
            "scope_patterns": ["*"],
            "started_at": recent,
        }
        with open(skill_context._ACTIVE_FILE, "w") as f:
            json.dump(record, f)

        result = skill_context.main(["current"])
        self.assertEqual(result, 0)


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
        self.orig_active_dir = skill_context._ACTIVE_DIR
        skill_context._CONTEXT_DIR = self.tmp / "skill-context"
        skill_context._ACTIVE_FILE = skill_context._CONTEXT_DIR / "ACTIVE.json"
        skill_context._HISTORY_DIR = skill_context._CONTEXT_DIR / "history"
        skill_context._ACTIVE_DIR = skill_context._CONTEXT_DIR / "active"

    def tearDown(self):
        skill_context._CONTEXT_DIR = self.orig_context_dir
        skill_context._ACTIVE_FILE = self.orig_active
        skill_context._HISTORY_DIR = self.orig_history
        skill_context._ACTIVE_DIR = self.orig_active_dir
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

    def test_handoff_between_different_skills_links_bidirectionally(self):
        """TC-MT007-02 (backlog G-41): a re-begin under the same session_id that
        changes SKILL (the S-72 evidence-repair -> S-73 manual-edit pattern,
        forced by check_content_edit_hook.sh recognizing only S-73 for
        content/ writes) must produce a bidirectional link: the archived S-72
        record points forward (superseded_by) to the new S-73 record, and the
        new S-73 record points back (handoff_from) to the S-72 one."""
        skill_context.main(["begin", "--skill", "S-72", "--scope", "content/*",
                            "--session-id", "evidence-repair-docs-a", "--skip-dar"])
        skill_context.main(["begin", "--skill", "S-73", "--scope", "content/*",
                            "--session-id", "evidence-repair-docs-a", "--skip-dar"])

        new_record = skill_context._load_session_contexts()["evidence-repair-docs-a"]
        self.assertEqual(new_record["skill_id"], "S-73")
        self.assertIn("handoff_from", new_record)
        self.assertEqual(new_record["handoff_from"]["skill_id"], "S-72")

        history = skill_context._load_history_records()
        s72_record = next(r for r in history if r["skill_id"] == "S-72")
        self.assertEqual(s72_record["end_status"], "superseded_same_session")
        self.assertIn("superseded_by", s72_record)
        self.assertEqual(s72_record["superseded_by"]["skill_id"], "S-73")
        self.assertEqual(s72_record["superseded_by"]["started_at"], new_record["started_at"])

    def test_same_skill_rearm_gets_no_handoff_noise(self):
        """The overwhelmingly common case (a skill re-arming its OWN scope
        before every edit) must not get a handoff_from field -- only a genuine
        skill CHANGE is a handoff."""
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/y.py",
                            "--session-id", "sess-A", "--skip-dar"])
        new_record = skill_context._load_session_contexts()["sess-A"]
        self.assertNotIn("handoff_from", new_record)
        history = skill_context._load_history_records()
        self.assertNotIn("superseded_by", history[0])

    def test_trace_prints_full_handoff_chain_both_directions(self):
        skill_context.main(["begin", "--skill", "S-72", "--scope", "content/*",
                            "--session-id", "evidence-repair-docs-b", "--skip-dar"])
        skill_context.main(["begin", "--skill", "S-73", "--scope", "content/*",
                            "--session-id", "evidence-repair-docs-b", "--skip-dar"])
        skill_context.main(["end", "--skill", "S-73", "--session-id", "evidence-repair-docs-b"])

        chain = skill_context.trace_handoff_chain("evidence-repair-docs-b")
        self.assertEqual([r["skill_id"] for r in chain], ["S-72", "S-73"])
        self.assertEqual(chain[1]["end_status"], "completed")

        r = skill_context.main(["trace", "--session-id", "evidence-repair-docs-b"])
        self.assertEqual(r, 0)

    def test_trace_no_records_exits_1(self):
        r = skill_context.main(["trace", "--session-id", "no-such-session"])
        self.assertEqual(r, 1)

    def test_stale_session_context_self_expires_per_ttl(self):
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py",
                            "--session-id", "sess-A", "--skip-dar"])
        p = skill_context._session_context_path("sess-A")
        rec = json.loads(p.read_text(encoding="utf-8"))
        rec["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        p.write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(skill_context._load_session_contexts(), {})  # expired
        self.assertFalse(p.exists())

    def test_session_check_bumps_heartbeat_keeping_it_alive_past_original_ttl(self):
        """A per-session context begun >2h ago, but already touched again
        1h ago (within TTL), must still be alive -- and a fresh `check` now
        must refresh its heartbeat again, not just ride the old one."""
        skill_context.main(["begin", "--skill", "S-20", "--scope", "a/*.py",
                            "--session-id", "sess-A", "--skip-dar"])
        p = skill_context._session_context_path("sess-A")
        rec = json.loads(p.read_text(encoding="utf-8"))
        rec["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat().replace("+00:00", "Z")
        rec["last_touched_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        p.write_text(json.dumps(rec), encoding="utf-8")

        self.assertEqual(0, skill_context.main(["check", "--file", "a/x.py", "--session-id", "sess-A"]))
        touched = json.loads(p.read_text(encoding="utf-8"))
        # heartbeat refreshed to now, not left at the 1h-ago value
        touched_dt = datetime.fromisoformat(touched["last_touched_at"].replace("Z", "+00:00"))
        self.assertLess(datetime.now(timezone.utc) - touched_dt, timedelta(minutes=1))
        # still alive on a SECOND load, proving the heartbeat (not luck) is what saved it
        self.assertIn("sess-A", skill_context._load_session_contexts())

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
        """Identity-less callers keep the single-skill lifecycle working:
        begin -> ACTIVE.json written; same-skill re-begin supersedes own context;
        end archives. A DIFFERENT skill's begin now conflicts (fail-closed,
        HARDEN-A2) instead of silently superseding."""
        self.assertEqual(0, skill_context.main(["begin", "--skill", "S-20", "--scope", "a/*", "--skip-dar"]))
        self.assertTrue(skill_context._ACTIVE_FILE.exists())
        self.assertEqual(skill_context._load_active()["skill_id"], "S-20")
        # same-skill re-begin still supersedes own context (per-edit re-arm loop)
        self.assertEqual(0, skill_context.main(["begin", "--skill", "S-20", "--scope", "b/*", "--skip-dar"]))
        self.assertEqual(skill_context._load_active()["scope_patterns"], ["b/*"])
        # different-skill begin without identity is a named conflict now
        self.assertEqual(3, skill_context.main(["begin", "--skill", "S-21", "--scope", "c/*", "--skip-dar"]))
        self.assertEqual(skill_context._load_active()["skill_id"], "S-20")
        self.assertEqual(0, skill_context.main(["end", "--skill", "S-20"]))
        self.assertIsNone(skill_context._load_active())
        # no session files were created by legacy callers
        self.assertEqual(skill_context._load_session_contexts(), {})

    def test_env_session_id_routes_to_per_session_path(self):
        """HARDEN-A2: exporting AGENT_SESSION_ID flips a flag-less caller onto
        the per-session path automatically (opt-in became default)."""
        with mock.patch.dict("os.environ", {"AGENT_SESSION_ID": "env-sess-1"}):
            self.assertEqual(0, skill_context.main(
                ["begin", "--skill", "S-20", "--scope", "a/*", "--skip-dar"]))
            # No legacy ACTIVE.json — the context landed in the session file
            self.assertFalse(skill_context._ACTIVE_FILE.exists())
            contexts = skill_context._load_session_contexts()
            self.assertIn("env-sess-1", contexts)
            self.assertEqual(contexts["env-sess-1"]["skill_id"], "S-20")
            self.assertEqual(0, skill_context.main(["end", "--skill", "S-20"]))
            self.assertEqual(skill_context._load_session_contexts(), {})

    # ── CLAUDE_CODE_SESSION_ID fallback tier (RC1/RC2 hardening, 2026-07-31) ──
    #
    # An earlier design used session_ledger.py's shared reports/session-state/ACTIVE
    # pointer file as this fallback. Live testing against a genuinely concurrent
    # second session in this repo showed that design collides: both processes
    # read the same mutable file and believe it is their own identity, so a
    # scope-overlapping begin from the second process silently SUPERSEDED the
    # first process's live context instead of conflicting -- reproducing, in
    # miniature, the exact silent-clobber class this OCC mechanism exists to
    # prevent. CLAUDE_CODE_SESSION_ID is different in kind: it is inherited by
    # the harness into every tool-call subprocess of ONE conversation, not read
    # from a file any other process could overwrite. The test below is the
    # safety-property gate for that claim: two independently-set
    # CLAUDE_CODE_SESSION_ID values must behave exactly like two independent
    # --session-id values (named conflict on overlap), never a same-session supersede.

    def test_claude_code_session_id_routes_to_per_session_path(self):
        """With no explicit identity and no AGENT_SESSION_ID/CODEX_THREAD_ID,
        CLAUDE_CODE_SESSION_ID alone is enough to land on the per-session path."""
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "conv-1"}):
            self.assertEqual(0, skill_context.main(
                ["begin", "--skill", "S-20", "--scope", "a/*", "--skip-dar"]))
            self.assertFalse(skill_context._ACTIVE_FILE.exists())
            contexts = skill_context._load_session_contexts()
            self.assertIn("conv-1", contexts)
            self.assertEqual(contexts["conv-1"]["skill_id"], "S-20")

    def test_agent_session_id_takes_precedence_over_claude_code_session_id(self):
        with mock.patch.dict("os.environ", {
            "AGENT_SESSION_ID": "explicit-sess",
            "CLAUDE_CODE_SESSION_ID": "conv-1",
        }):
            self.assertEqual("explicit-sess", skill_context._derive_session_id(None))

    def test_two_independent_conversations_with_overlapping_scope_conflict_not_supersede(self):
        """THE safety-property gate: two DIFFERENT CLAUDE_CODE_SESSION_ID values
        (simulating two genuinely independent, separately-initiated Claude Code
        conversations, each with no explicit --session-id of its own -- the
        common real case, since the harness does not persist AGENT_SESSION_ID
        across tool calls) must be treated as two DISTINCT sessions: an
        overlapping-scope begin from the second one is a named conflict (exit 3),
        and the first session's context must survive completely untouched --
        never a silent same-session supersede."""
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "conversation-A"}):
            self.assertEqual(0, skill_context.main(
                ["begin", "--skill", "S-20", "--scope", "a/x.py", "--skip-dar"]))

        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "conversation-B"}):
            result = skill_context.main(
                ["begin", "--skill", "S-21", "--scope", "a/*.py", "--skip-dar"])
            self.assertEqual(result, 3, "must be a named conflict, not a silent supersede")

        live = skill_context._load_session_contexts()
        self.assertEqual(set(live), {"conversation-A"}, "conversation-A must survive untouched")
        self.assertEqual(live["conversation-A"]["skill_id"], "S-20")

    def test_two_independent_conversations_nonoverlapping_scope_coexist(self):
        """Companion to the conflict test: when the two independent conversations'
        scopes do NOT overlap, both must coexist as distinct sessions (proving
        this fallback tier does not over-block unrelated concurrent work either)."""
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "conversation-A"}):
            r1 = skill_context.main(["begin", "--skill", "S-20", "--scope", "a/x.py", "--skip-dar"])
        with mock.patch.dict("os.environ", {"CLAUDE_CODE_SESSION_ID": "conversation-B"}):
            r2 = skill_context.main(["begin", "--skill", "S-21", "--scope", "b/y.py", "--skip-dar"])
        self.assertEqual((r1, r2), (0, 0))
        live = skill_context._load_session_contexts()
        self.assertEqual(set(live), {"conversation-A", "conversation-B"})

    def test_no_identity_source_at_all_still_uses_legacy_path(self):
        """Absent-var fallback gate: when CLAUDE_CODE_SESSION_ID (and every other
        source) is unset -- e.g. a CLI/SDK invocation outside this harness --
        behavior is byte-identical to before this change: the legacy single
        ACTIVE.json path, not an error."""
        self.assertIsNone(skill_context._derive_session_id(None))
        self.assertEqual(0, skill_context.main(["begin", "--skill", "S-20", "--scope", "a/*", "--skip-dar"]))
        self.assertTrue(skill_context._ACTIVE_FILE.exists())
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
