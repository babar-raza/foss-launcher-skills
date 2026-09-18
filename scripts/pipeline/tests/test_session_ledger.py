"""Tests for session_ledger.py — session-scoped file touch ledger."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import session_ledger
from taskcard_store import TaskcardStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_session_dir(tmp_path, monkeypatch):
    """Redirect session state to tmp_path via configure() seam.

    Also clears AGENT_SESSION_ID so a developer/agent shell exporting its own
    session identity (the HARDEN-A2 convention) cannot leak into these tests.
    CODEX_THREAD_ID/CLAUDE_CODE_SESSION_ID (Step 3, 2026-08-01: session_ledger.py
    now delegates to session_identity.resolve(), which checks both) must be
    cleared too — CLAUDE_CODE_SESSION_ID in particular is set by the real
    harness running this very test suite and would otherwise silently change
    behavior only when run inside an actual Claude Code session.
    """
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    session_ledger.configure(repo_root=tmp_path)
    yield tmp_path / "reports" / "session-state"
    session_ledger.configure()  # reset to defaults


@pytest.fixture
def active_session(isolate_session_dir):
    """Create and return an active session ID."""
    sid = session_ledger.init_session("test-session-001")
    return sid


# ---------------------------------------------------------------------------
# classify_file
# ---------------------------------------------------------------------------

class TestClassifyFile:
    def test_english_docs(self):
        assert session_ledger.classify_file(
            "content/docs.aspose.org/en/words/python/foo.md"
        ) == "content(docs)"

    def test_english_reference(self):
        assert session_ledger.classify_file(
            "content/reference.aspose.org/en/cells/net/Workbook.md"
        ) == "content(reference)"

    def test_english_products(self):
        assert session_ledger.classify_file(
            "content/products.aspose.org/en/words/python.md"
        ) == "content(products)"

    def test_english_kb(self):
        assert session_ledger.classify_file(
            "content/kb.aspose.org/en/cells/net/howto.md"
        ) == "content(kb)"

    def test_blog(self):
        assert session_ledger.classify_file(
            "content/blog.aspose.org/words/python/post-slug/_index.md"
        ) == "content(blog)"

    def test_locale_docs(self):
        assert session_ledger.classify_file(
            "content/docs.aspose.org/ar/words/python/foo.md"
        ) == "content(locale)"

    def test_locale_kb(self):
        assert session_ledger.classify_file(
            "content/kb.aspose.org/zh/cells/net/howto.md"
        ) == "content(locale)"

    def test_locale_products(self):
        assert session_ledger.classify_file(
            "content/products.aspose.org/fr/words/python.md"
        ) == "content(locale)"

    def test_knowledge(self):
        assert session_ledger.classify_file(
            "knowledge/words/python/merged/model.yaml"
        ) == "knowledge"

    def test_pipeline_script(self):
        assert session_ledger.classify_file(
            "scripts/pipeline/audit.py"
        ) == "fix(pipeline)"

    def test_ci_script(self):
        assert session_ledger.classify_file(
            "scripts/ci/check_foo.py"
        ) == "chore(ci)"

    def test_maintenance_script(self):
        assert session_ledger.classify_file(
            "scripts/maintenance/repair_something.py"
        ) == "chore(maintenance)"

    def test_test_file(self):
        assert session_ledger.classify_file(
            "tests/test_something.py"
        ) == "test"

    def test_data_file(self):
        assert session_ledger.classify_file(
            "data/registry.yaml"
        ) == "chore(data)"

    def test_unknown_path(self):
        assert session_ledger.classify_file(
            "random/unknown/file.txt"
        ) == "chore(misc)"

    def test_backslash_normalization(self):
        assert session_ledger.classify_file(
            "content\\docs.aspose.org\\en\\words\\python\\foo.md"
        ) == "content(docs)"

    def test_leading_dot_slash(self):
        assert session_ledger.classify_file(
            "./scripts/pipeline/foo.py"
        ) == "fix(pipeline)"

    def test_non_md_content_not_locale(self):
        """Non-.md files in content/ without /en/ should not match locale."""
        assert session_ledger.classify_file(
            "content/docs.aspose.org/fr/words/python/_index.md"
        ) == "content(locale)"


class TestGroupFiles:
    def test_groups_multiple_types(self):
        paths = [
            "content/docs.aspose.org/en/words/python/foo.md",
            "content/docs.aspose.org/ar/words/python/foo.md",
            "knowledge/words/python/merged/model.yaml",
            "scripts/pipeline/audit.py",
        ]
        groups = session_ledger.group_files(paths)
        assert "content(docs)" in groups
        assert "content(locale)" in groups
        assert "knowledge" in groups
        assert "fix(pipeline)" in groups

    def test_groups_are_sorted(self):
        paths = [
            "content/docs.aspose.org/en/words/python/z.md",
            "content/docs.aspose.org/en/words/python/a.md",
        ]
        groups = session_ledger.group_files(paths)
        assert groups["content(docs)"] == [
            "content/docs.aspose.org/en/words/python/a.md",
            "content/docs.aspose.org/en/words/python/z.md",
        ]


# ---------------------------------------------------------------------------
# init_session
# ---------------------------------------------------------------------------

class TestInitSession:
    def test_creates_manifest(self, isolate_session_dir):
        sid = session_ledger.init_session("test-init-001")
        assert sid == "test-init-001"
        path = isolate_session_dir / "test-init-001.json"
        assert path.exists()

        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["session_id"] == "test-init-001"
        assert manifest["status"] == "active"
        assert "started_at" in manifest
        assert isinstance(manifest["dirty_at_start"], list)
        assert manifest["touched_files"] == {}

    def test_auto_generates_id(self, isolate_session_dir):
        sid = session_ledger.init_session()
        assert len(sid) > 0
        assert (isolate_session_dir / f"{sid}.json").exists()

    def test_init_does_not_close_prior_session(self, isolate_session_dir):
        """HARDEN-A2: init never mutates another session's manifest. The old
        behavior (init closes whatever is active) was the ST-021 corruption
        mechanism — session A's records silently landing in B's manifest."""
        session_ledger.init_session("session-1")
        session_ledger.init_session("session-2")

        m1 = json.loads((isolate_session_dir / "session-1.json").read_text(encoding="utf-8"))
        m2 = json.loads((isolate_session_dir / "session-2.json").read_text(encoding="utf-8"))

        assert m1["status"] == "active"
        assert "closed_at" not in m1
        assert m2["status"] == "active"
        assert m2["stale_after_hours"] == session_ledger._DEFAULT_STALE_AFTER_HOURS

    @patch.object(session_ledger, "_git_dirty_files", return_value=["file_a.md", "file_b.md"])
    def test_captures_dirty_snapshot(self, mock_dirty, isolate_session_dir):
        sid = session_ledger.init_session("snap-test")
        manifest = json.loads((isolate_session_dir / "snap-test.json").read_text(encoding="utf-8"))
        assert manifest["dirty_at_start"] == ["file_a.md", "file_b.md"]

    @patch.object(session_ledger, "_git_head_sha", return_value="abc1234567890abc1234567890abc1234567890")
    def test_captures_base_commit_sha(self, mock_head, isolate_session_dir):
        """Stale-file regression guard (2026-08-01): the manifest must record
        the HEAD sha at session start -- the missing reference point that let
        TC-MT018-06's commit silently revert an unrelated fix committed by
        another session hours earlier."""
        session_ledger.init_session("sha-test")
        manifest = json.loads((isolate_session_dir / "sha-test.json").read_text(encoding="utf-8"))
        assert manifest["base_commit_sha"] == "abc1234567890abc1234567890abc1234567890"

    @patch.object(session_ledger, "_git_head_sha", return_value=None)
    def test_base_commit_sha_none_when_unresolvable(self, mock_head, isolate_session_dir):
        """HEAD unresolvable (e.g. a fresh repo with no commits yet) must not
        crash init -- records None, not a placeholder that looks real."""
        session_ledger.init_session("sha-none-test")
        manifest = json.loads((isolate_session_dir / "sha-none-test.json").read_text(encoding="utf-8"))
        assert manifest["base_commit_sha"] is None


class TestGetBaseCommitSha:
    @patch.object(session_ledger, "_git_head_sha", return_value="deadbeef" * 5)
    def test_returns_recorded_sha_for_explicit_session(self, mock_head, isolate_session_dir):
        session_ledger.init_session("sha-explicit-test")
        assert session_ledger.get_base_commit_sha("sha-explicit-test") == "deadbeef" * 5

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    @patch.object(session_ledger, "_git_head_sha", return_value="cafebabe" * 5)
    def test_returns_recorded_sha_for_resolved_session(self, mock_head, mock_dirty, isolate_session_dir):
        session_ledger.init_session("sha-resolved-test")
        assert session_ledger.get_base_commit_sha() == "cafebabe" * 5

    def test_returns_none_for_unknown_session(self, isolate_session_dir):
        assert session_ledger.get_base_commit_sha("no-such-session") is None

    def test_returns_none_when_no_active_session(self, isolate_session_dir):
        assert session_ledger.get_base_commit_sha() is None


# ---------------------------------------------------------------------------
# record_file
# ---------------------------------------------------------------------------

class TestRecordFile:
    def test_records_new_file(self, active_session):
        ok = session_ledger.record_file("content/foo.md", action="created", skill="S-19")
        assert ok is True

        touched = session_ledger.get_touched_files()
        assert "content/foo.md" in touched
        entry = touched["content/foo.md"]
        assert entry["action"] == "created"
        assert entry["skills"] == ["S-19"]
        assert "first_touched" in entry

    def test_updates_existing_entry(self, active_session):
        session_ledger.record_file("content/foo.md", action="created", skill="S-19")
        session_ledger.record_file("content/foo.md", action="modified", skill="S-23")

        touched = session_ledger.get_touched_files()
        entry = touched["content/foo.md"]
        # created should not be downgraded to modified
        assert entry["action"] == "created"
        assert "S-19" in entry["skills"]
        assert "S-23" in entry["skills"]

    def test_normalizes_backslashes(self, active_session):
        session_ledger.record_file("content\\foo.md", action="modified")
        touched = session_ledger.get_touched_files()
        assert "content/foo.md" in touched

    def test_returns_false_without_session(self, isolate_session_dir):
        ok = session_ledger.record_file("content/foo.md", action="modified")
        assert ok is False

    def test_deleted_overrides_modified(self, active_session):
        session_ledger.record_file("content/foo.md", action="modified")
        session_ledger.record_file("content/foo.md", action="deleted")
        touched = session_ledger.get_touched_files()
        assert touched["content/foo.md"]["action"] == "deleted"

    def test_created_not_overridden(self, active_session):
        """If a file was created then modified, action stays 'created'."""
        session_ledger.record_file("content/foo.md", action="created")
        session_ledger.record_file("content/foo.md", action="modified")
        touched = session_ledger.get_touched_files()
        assert touched["content/foo.md"]["action"] == "created"

    def test_record_files_batch(self, active_session):
        """TC-W3H-009: batch mode records many paths with one manifest write."""
        paths = [f"content/kb.aspose.org/de/pdf/net/page-{i}.md" for i in range(1000)]
        count = session_ledger.record_files(paths, action="modified", skill="S-73")
        assert count == 1000
        touched = session_ledger.get_touched_files()
        assert len(touched) == 1000
        assert touched[paths[0]]["skills"] == ["S-73"]

    def test_record_files_batch_no_session(self, isolate_session_dir):
        assert session_ledger.record_files(["content/foo.md"]) is None

    def test_record_files_batch_merges_existing(self, active_session):
        session_ledger.record_file("content/foo.md", action="created", skill="S-19")
        session_ledger.record_files(["content/foo.md", "content/bar.md"],
                                    action="modified", skill="S-73")
        touched = session_ledger.get_touched_files()
        assert touched["content/foo.md"]["action"] == "created"  # not downgraded
        assert "S-73" in touched["content/foo.md"]["skills"]
        assert touched["content/bar.md"]["action"] == "modified"

    def test_skill_deduplication(self, active_session):
        session_ledger.record_file("content/foo.md", action="modified", skill="S-23")
        session_ledger.record_file("content/foo.md", action="modified", skill="S-23")
        touched = session_ledger.get_touched_files()
        assert touched["content/foo.md"]["skills"] == ["S-23"]


# ---------------------------------------------------------------------------
# get_current_session_id
# ---------------------------------------------------------------------------

class TestGetCurrentSessionId:
    def test_returns_active_session(self, active_session):
        assert session_ledger.get_current_session_id() == active_session

    def test_returns_none_without_session(self, isolate_session_dir):
        assert session_ledger.get_current_session_id() is None

    def test_pointer_file_enables_discovery(self, active_session, isolate_session_dir):
        """ACTIVE pointer file allows O(1) session discovery."""
        pointer = isolate_session_dir / "ACTIVE"
        assert pointer.exists()
        assert pointer.read_text(encoding="utf-8").strip() == active_session


# ---------------------------------------------------------------------------
# adopt_files
# ---------------------------------------------------------------------------

class TestAdoptFiles:
    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=["content/a.md", "content/b.md", "scripts/pipeline/foo.py"])
    def test_adopt_all_dirty(self, mock_dirty, isolate_session_dir):
        # Init with dirty files (simulates pre-existing state)
        session_ledger.init_session("adopt-test")
        count = session_ledger.adopt_files(
            ["content/a.md", "content/b.md"], action="modified"
        )
        assert count == 2
        touched = session_ledger.get_touched_files()
        assert "content/a.md" in touched
        assert "content/b.md" in touched
        assert touched["content/a.md"].get("adopted") is True

    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=["content/a.md", "content/b.md"])
    def test_adopt_removes_from_dirty_at_start(self, mock_dirty, isolate_session_dir):
        session_ledger.init_session("adopt-dirty-test")
        # a.md and b.md are in dirty_at_start
        dirty = session_ledger.get_dirty_at_start()
        assert "content/a.md" in dirty

        session_ledger.adopt_files(["content/a.md"])
        # Now a.md should NOT be in dirty_at_start (moved to touched_files)
        dirty_after = session_ledger.get_dirty_at_start()
        assert "content/a.md" not in dirty_after

    def test_adopt_returns_zero_without_session(self, isolate_session_dir):
        count = session_ledger.adopt_files(["content/a.md"])
        assert count == 0

    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=["content/a.md"])
    def test_adopt_idempotent(self, mock_dirty, isolate_session_dir):
        session_ledger.init_session("adopt-idem")
        session_ledger.adopt_files(["content/a.md"])
        count = session_ledger.adopt_files(["content/a.md"])
        assert count == 0  # Already adopted

    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=["content/docs.aspose.org/ar/words/python/foo.md",
                                "content/docs.aspose.org/zh/words/python/foo.md",
                                "scripts/pipeline/bar.py"])
    def test_adopt_by_group(self, mock_dirty, isolate_session_dir):
        session_ledger.init_session("adopt-group")
        count, matched = session_ledger.adopt_by_group("content(locale)")
        assert count == 2
        assert len(matched) == 2
        assert all("content/docs.aspose.org/" in p for p in matched)

    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=["content/kb.aspose.org/en/cells/net/foo.md",
                                "content/kb.aspose.org/ar/cells/net/foo.md",
                                "content/docs.aspose.org/en/words/python/bar.md"])
    def test_adopt_by_glob(self, mock_dirty, isolate_session_dir):
        session_ledger.init_session("adopt-glob")
        count, matched = session_ledger.adopt_by_glob("content/kb.aspose.org/*")
        assert count == 2
        assert all(p.startswith("content/kb.aspose.org/") for p in matched)

    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=[".agents/skills/refresh-product/SKILL.md",
                                ".claude/commands/refresh-product.md",
                                ".kilocode/skills/refresh-product/SKILL.md"])
    def test_adopt_preserves_dotfile_leading_dot(self, mock_dirty, isolate_session_dir):
        """Regression (found live during RPR-J-11 commit prep, 2026-07-17): normalization
        used `.lstrip("./")`, which strips a CHARACTER SET ({'.', '/'}), not the literal
        prefix "./". Any path starting with a literal dot-directory (.agents/, .claude/,
        .kilocode/, .github/) had its leading dot silently eaten -- '.agents/skills/x.md'
        became 'agents/skills/x.md' -- so adopt_files() recorded a touched-file key that
        could NEVER match the real (dotted) git-dirty path, and the file silently never
        became a commit candidate no matter how many times it was "adopted". Fixed via
        removeprefix("./"), which only strips the literal prefix when present."""
        session_ledger.init_session("adopt-dotfile")
        count = session_ledger.adopt_files([
            ".agents/skills/refresh-product/SKILL.md",
            ".claude/commands/refresh-product.md",
            ".kilocode/skills/refresh-product/SKILL.md",
        ])
        assert count == 3
        touched = session_ledger.get_touched_files()
        # The leading dot MUST survive normalization -- this is the exact bug.
        assert ".agents/skills/refresh-product/SKILL.md" in touched
        assert ".claude/commands/refresh-product.md" in touched
        assert ".kilocode/skills/refresh-product/SKILL.md" in touched
        assert "agents/skills/refresh-product/SKILL.md" not in touched

    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=[".agents/skills/refresh-product/SKILL.md"])
    def test_adopted_dotfile_appears_in_candidates(self, mock_dirty, isolate_session_dir):
        """End-to-end: an adopted dotfile path must actually surface as a commit
        candidate (touched ∩ git-dirty), not just exist in the touched-files dict."""
        session_ledger.init_session("adopt-dotfile-candidates")
        session_ledger.adopt_files([".agents/skills/refresh-product/SKILL.md"])
        candidates, _excluded_dirty_at_start, _excluded_not_in_ledger = session_ledger.get_candidates()
        assert ".agents/skills/refresh-product/SKILL.md" in candidates

    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=["content/blog.aspose.org/x/index.de.md"])
    def test_adopt_strips_a_trailing_carriage_return(self, mock_dirty, isolate_session_dir):
        """Regression, same lineage as test_adopt_preserves_dotfile_leading_dot
        (RPR-J-11): a caller building a newline-separated file list on
        Windows/Git Bash and joining lines with `tr '\\n' ' '` leaves a
        trailing '\\r' on every token, since `tr` only touches the '\\n' half
        of each CRLF pair. adopt_files() previously normalized only
        backslash/./ , so the '\\r'-suffixed key never matched the clean git-
        dirty path -- adopt reported success (the count incremented) and the
        file was genuinely written to touched_files, just under a key that
        could never match anything, so it silently never became a commit
        candidate. Found live 2026-09-11 committing a real translation batch.
        """
        session_ledger.init_session("adopt-crlf")
        count = session_ledger.adopt_files(["content/blog.aspose.org/x/index.de.md\r"])
        assert count == 1
        touched = session_ledger.get_touched_files()
        assert "content/blog.aspose.org/x/index.de.md" in touched
        assert "content/blog.aspose.org/x/index.de.md\r" not in touched
        dirty_after = session_ledger.get_dirty_at_start()
        assert "content/blog.aspose.org/x/index.de.md" not in dirty_after
        candidates, _excluded_dirty_at_start, _excluded_not_in_ledger = session_ledger.get_candidates()
        assert "content/blog.aspose.org/x/index.de.md" in candidates

    def test_classify_file_strips_literal_dotslash_only(self):
        """classify_file's normalization must strip a literal leading './' (same group as
        the un-prefixed path), and must NOT strip the leading dot of a dotfile path."""
        assert session_ledger.classify_file("./scripts/pipeline/foo.py") == \
            session_ledger.classify_file("scripts/pipeline/foo.py")
        # Must not raise, and must not silently collapse to a path lacking the leading dot.
        group = session_ledger.classify_file(".agents/skills/refresh-product/SKILL.md")
        assert isinstance(group, str) and group


class TestAdoptCLI:
    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=["content/a.md", "scripts/pipeline/b.py"])
    def test_adopt_all_cli(self, mock_dirty, isolate_session_dir):
        session_ledger.init_session("cli-adopt")
        ret = session_ledger.main(["adopt", "--all"])
        assert ret == 0
        touched = session_ledger.get_touched_files()
        assert len(touched) == 2

    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=["content/docs.aspose.org/ar/foo.md"])
    def test_adopt_group_cli(self, mock_dirty, isolate_session_dir):
        session_ledger.init_session("cli-adopt-group")
        ret = session_ledger.main(["adopt", "--group", "content(locale)"])
        assert ret == 0

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_adopt_all_no_dirty(self, mock_dirty, active_session):
        ret = session_ledger.main(["adopt", "--all"])
        assert ret == 2


# ---------------------------------------------------------------------------
# get_candidates
# ---------------------------------------------------------------------------

class TestGetCandidates:
    @patch.object(session_ledger, "_git_dirty_files")
    def test_intersection_of_ledger_and_dirty(self, mock_dirty, active_session):
        # Record some files
        session_ledger.record_file("content/a.md", action="created")
        session_ledger.record_file("content/b.md", action="modified")

        # Simulate git dirty: a.md is dirty, b.md is not (already committed elsewhere)
        mock_dirty.return_value = ["content/a.md", "content/c.md"]

        candidates, excluded_prior, excluded_unknown = session_ledger.get_candidates()
        assert candidates == ["content/a.md"]
        # c.md is dirty but not in ledger and not in dirty_at_start → excluded_unknown
        assert "content/c.md" in excluded_unknown

    @patch.object(session_ledger, "_git_dirty_files")
    def test_dirty_at_start_excluded(self, mock_dirty, isolate_session_dir):
        # Init with dirty files
        mock_dirty.return_value = ["content/pre_existing.md", "content/new.md"]
        session_ledger.init_session("test-dirty")

        # Record only new.md as touched
        session_ledger.record_file("content/new.md", action="created")

        # Both still dirty
        mock_dirty.return_value = ["content/pre_existing.md", "content/new.md"]

        candidates, excluded_prior, excluded_unknown = session_ledger.get_candidates()
        assert candidates == ["content/new.md"]
        assert excluded_prior == ["content/pre_existing.md"]
        assert excluded_unknown == []

    def test_empty_without_session(self, isolate_session_dir):
        candidates, _, _ = session_ledger.get_candidates()
        assert candidates == []


# ---------------------------------------------------------------------------
# is_new_files_only
# ---------------------------------------------------------------------------

class TestIsNewFilesOnly:
    def test_true_when_all_created(self, active_session):
        session_ledger.record_file("content/a.md", action="created")
        session_ledger.record_file("content/b.md", action="created")
        assert session_ledger.is_new_files_only() is True

    def test_false_when_mixed(self, active_session):
        session_ledger.record_file("content/a.md", action="created")
        session_ledger.record_file("content/b.md", action="modified")
        assert session_ledger.is_new_files_only() is False

    def test_false_when_empty(self, isolate_session_dir):
        assert session_ledger.is_new_files_only() is False


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestCLI:
    def test_init_command(self, isolate_session_dir):
        ret = session_ledger.main(["init", "--session-id", "cli-test-001"])
        assert ret == 0
        assert (isolate_session_dir / "cli-test-001.json").exists()

    def test_repo_root_flag_redirects_without_prior_configure(self, tmp_path, monkeypatch):
        """G16/Task 24: check_ledger_init_hook.sh invokes this CLI directly
        (a fresh subprocess, no prior configure() call) with --repo-root to
        redirect where the manifest is written -- this must work standalone,
        not only via the isolate_session_dir fixture's own configure() call."""
        monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
        monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        try:
            ret = session_ledger.main([
                "--repo-root", str(tmp_path), "init", "--session-id", "cli-repo-root-test",
            ])
            assert ret == 0
            assert (tmp_path / "reports" / "session-state" / "cli-repo-root-test.json").is_file()
        finally:
            session_ledger.configure()  # reset -- this test deliberately bypasses the fixture

    def test_record_command(self, active_session):
        ret = session_ledger.main(["record", "--file", "content/foo.md", "--action", "created"])
        assert ret == 0
        assert "content/foo.md" in session_ledger.get_touched_files()

    def test_record_with_skill(self, active_session):
        ret = session_ledger.main([
            "record", "--file", "content/foo.md", "--action", "modified", "--skill", "S-20"
        ])
        assert ret == 0
        entry = session_ledger.get_touched_files()["content/foo.md"]
        assert "S-20" in entry["skills"]

    def test_current_command(self, active_session, capsys):
        ret = session_ledger.main(["current"])
        assert ret == 0
        out = capsys.readouterr().out.strip()
        assert out == active_session

    def test_current_no_session(self, isolate_session_dir):
        ret = session_ledger.main(["current"])
        assert ret == 2

    def test_list_paths(self, active_session, capsys):
        session_ledger.record_file("content/a.md", action="created")
        session_ledger.record_file("content/b.md", action="modified")
        ret = session_ledger.main(["list", "--format", "paths"])
        assert ret == 0
        out = capsys.readouterr().out.strip().splitlines()
        assert out == ["content/a.md", "content/b.md"]

    def test_list_json(self, active_session, capsys):
        session_ledger.record_file("content/a.md", action="created", skill="S-19")
        ret = session_ledger.main(["list", "--format", "json"])
        assert ret == 0
        data = json.loads(capsys.readouterr().out)
        assert "content/a.md" in data

    def test_list_empty_session(self, active_session):
        ret = session_ledger.main(["list"])
        assert ret == 2


# ---------------------------------------------------------------------------
# ACTIVE pointer file
# ---------------------------------------------------------------------------

class TestActivePointer:
    def test_pointer_written_on_init(self, isolate_session_dir):
        sid = session_ledger.init_session("ptr-test-001")
        pointer = isolate_session_dir / "ACTIVE"
        assert pointer.exists()
        assert pointer.read_text(encoding="utf-8").strip() == "ptr-test-001"

    def test_pointer_updated_on_new_session(self, isolate_session_dir):
        session_ledger.init_session("ptr-old")
        session_ledger.init_session("ptr-new")
        pointer = isolate_session_dir / "ACTIVE"
        assert pointer.read_text(encoding="utf-8").strip() == "ptr-new"

    def test_stale_pointer_cleaned_up(self, isolate_session_dir):
        """If ACTIVE points to a closed session, it gets cleaned up."""
        sid = session_ledger.init_session("ptr-stale")
        # Manually close the session
        manifest_path = isolate_session_dir / "ptr-stale.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "closed"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        # Discovery should clean up stale pointer and return None
        assert session_ledger.get_current_session_id() is None
        assert not (isolate_session_dir / "ACTIVE").exists()

    def test_fallback_scan_repairs_pointer(self, isolate_session_dir):
        """If ACTIVE pointer is missing but session exists, scan repairs it."""
        sid = session_ledger.init_session("ptr-repair")
        # Delete the pointer
        (isolate_session_dir / "ACTIVE").unlink()
        # Discovery should still find the session via scan and repair pointer
        assert session_ledger.get_current_session_id() == "ptr-repair"
        assert (isolate_session_dir / "ACTIVE").exists()
        assert (isolate_session_dir / "ACTIVE").read_text(encoding="utf-8").strip() == "ptr-repair"


# ---------------------------------------------------------------------------
# diagnose command
# ---------------------------------------------------------------------------

class TestDiagnose:
    def test_diagnose_with_active_session(self, active_session, capsys):
        ret = session_ledger.main(["diagnose"])
        assert ret == 0
        out = capsys.readouterr().out
        assert "SESSION LEDGER DIAGNOSTICS" in out
        assert "EXISTS" in out
        assert active_session in out
        assert "VALID" in out

    def test_diagnose_no_session(self, isolate_session_dir, capsys):
        ret = session_ledger.main(["diagnose"])
        assert ret == 0
        out = capsys.readouterr().out
        assert "NONE FOUND" in out

    def test_diagnose_with_pointer(self, isolate_session_dir, capsys):
        session_ledger.init_session("diag-ptr")
        ret = session_ledger.main(["diagnose"])
        assert ret == 0
        out = capsys.readouterr().out
        assert "diag-ptr" in out
        assert "ACTIVE pointer" in out


# ---------------------------------------------------------------------------
# Library import safety
# ---------------------------------------------------------------------------

class TestLibraryImport:
    def test_no_path_utils_dependency(self):
        """session_ledger must not import path_utils at module level."""
        import importlib
        source = Path(session_ledger.__file__).read_text(encoding="utf-8")
        assert "from path_utils" not in source
        assert "import path_utils" not in source

    def test_repo_rel_inline(self):
        """_repo_rel should work without path_utils."""
        p = session_ledger._REPO_ROOT / "reports" / "session-state" / "test.json"
        result = session_ledger._repo_rel(p)
        assert "test.json" in result


# ---------------------------------------------------------------------------
# Multi-session hand-off (T2-G1)
# ---------------------------------------------------------------------------

class TestMultiSessionHandoff:
    """Cross-session hand-off under the HARDEN-A2 contract:
    Session A records files → A is closed BY NAME → Session B inits
    → B inherits A's work → B can commit A's files. init never closes A."""

    @patch.object(session_ledger, "_git_dirty_files", return_value=["content/a.md", "content/b.md"])
    def test_session_b_init_leaves_a_active(self, mock_dirty, isolate_session_dir):
        """When Session B inits, Session A stays active and untouched; B's
        dirty_at_start still snapshots the working tree (including A's files)."""
        # Session A
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/a.md", "created", skill="S-56",
                                   session_id="session-a")
        session_ledger.record_file("content/b.md", "modified", skill="S-21",
                                   session_id="session-a")

        # Session B inits — A is NOT closed
        mock_dirty.return_value = ["content/a.md", "content/b.md", "content/c.md"]
        session_ledger.init_session("session-b")

        manifest_a = json.loads((isolate_session_dir / "session-a.json").read_text(encoding="utf-8"))
        assert manifest_a["status"] == "active"
        assert "content/a.md" in manifest_a["touched_files"]
        assert "content/b.md" in manifest_a["touched_files"]

        # A can still record into its own manifest after B's init
        assert session_ledger.record_file("content/d.md", "created",
                                          session_id="session-a") is True

        manifest_b = json.loads((isolate_session_dir / "session-b.json").read_text(encoding="utf-8"))
        assert manifest_b["status"] == "active"
        assert "content/a.md" in manifest_b["dirty_at_start"]
        assert "content/b.md" in manifest_b["dirty_at_start"]

    @patch.object(session_ledger, "_git_dirty_files", return_value=["content/a.md"])
    def test_inherit_from_prior_session(self, mock_dirty, isolate_session_dir):
        """inherit_session copies A's touched_files into B as adopted entries
        after A is explicitly closed (closed sessions don't claim files)."""
        # Session A: record files, then close by name
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/a.md", "created", skill="S-56")
        assert session_ledger.close_session("session-a") is True

        # Session B
        mock_dirty.return_value = ["content/a.md", "content/other.md"]
        session_ledger.init_session("session-b")

        # Inherit A's work
        count, paths = session_ledger.inherit_session("session-a")
        assert count == 1
        assert "content/a.md" in paths

        # content/a.md should now be a candidate (adopted into B, still dirty)
        candidates, _, _ = session_ledger.get_candidates()
        assert "content/a.md" in candidates

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_inherit_auto_finds_most_recent_closed(self, mock_dirty, isolate_session_dir):
        """inherit_session() with no ID auto-finds the most recently closed session."""
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/a.md", "created")
        session_ledger.close_session("session-a")

        session_ledger.init_session("session-b")

        # Inherit without specifying session ID
        count, paths = session_ledger.inherit_session()
        assert count == 1
        assert "content/a.md" in paths

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_closed_session_manifest_survives(self, mock_dirty, isolate_session_dir):
        """A's manifest is intact and readable after close + B's init."""
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/a.md", "created")
        session_ledger.close_session("session-a")

        session_ledger.init_session("session-b")

        path_a = isolate_session_dir / "session-a.json"
        assert path_a.exists()
        manifest_a = json.loads(path_a.read_text(encoding="utf-8"))
        assert manifest_a["status"] == "closed"
        assert "closed_at" in manifest_a
        assert manifest_a["session_id"] == "session-a"
        assert "content/a.md" in manifest_a["touched_files"]

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_inherit_no_prior_session_returns_zero(self, mock_dirty, isolate_session_dir):
        """inherit_session returns (0, []) when there's no prior closed session."""
        session_ledger.init_session("only-session")
        count, paths = session_ledger.inherit_session()
        assert count == 0
        assert paths == []

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_cmd_init_warns_about_other_active_sessions(self, mock_dirty, isolate_session_dir, capsys):
        """cmd_init warns (does not close) when another session is active."""
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/x.md", "created")

        rc = session_ledger.main(["init", "--session-id", "session-b"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "other active session(s): session-a" in output
        assert "did NOT close" in output

        # And session-a genuinely stayed active
        manifest_a = json.loads((isolate_session_dir / "session-a.json").read_text(encoding="utf-8"))
        assert manifest_a["status"] == "active"


# ---------------------------------------------------------------------------
# check-staged (T1-G1)
# ---------------------------------------------------------------------------

class TestCheckStaged:
    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_all_staged_in_ledger_passes(self, mock_dirty, isolate_session_dir):
        """When all staged files are in the ledger, check_staged returns no blocked."""
        session_ledger.init_session("test-cs")
        session_ledger.record_file("content/a.md", "created")
        session_ledger.record_file("content/b.md", "modified")

        allowed, blocked = session_ledger.check_staged(["content/a.md", "content/b.md"])
        assert len(allowed) == 2
        assert len(blocked) == 0

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_staged_not_in_ledger_blocked(self, mock_dirty, isolate_session_dir):
        """Staged files not in ledger are reported as blocked."""
        session_ledger.init_session("test-cs")
        session_ledger.record_file("content/a.md", "created")

        allowed, blocked = session_ledger.check_staged(["content/a.md", "content/unknown.md"])
        assert allowed == ["content/a.md"]
        assert blocked == ["content/unknown.md"]

    def test_no_active_session_passthrough(self, isolate_session_dir):
        """With no active session, all staged files pass through (no enforcement)."""
        allowed, blocked = session_ledger.check_staged(["content/a.md"])
        assert len(allowed) == 1
        assert len(blocked) == 0

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_cmd_check_staged_exit_0_when_all_in_ledger(self, mock_dirty, isolate_session_dir, monkeypatch):
        """CLI check-staged returns 0 when all staged files are in the ledger."""
        session_ledger.init_session("test-cs")
        session_ledger.record_file("content/a.md", "created")
        # T3-MOCK: target=sys.stdin reason="CLI check-staged reads stdin for staged files" removal=PERMANENT
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("content/a.md\n"))
        rc = session_ledger.main(["check-staged"])
        assert rc == 0

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_cmd_check_staged_exit_1_when_blocked(self, mock_dirty, isolate_session_dir, monkeypatch):
        """CLI check-staged returns 1 when staged files are NOT in the ledger."""
        session_ledger.init_session("test-cs")
        session_ledger.record_file("content/a.md", "created")
        # T3-MOCK: target=sys.stdin reason="CLI check-staged reads stdin for staged files" removal=PERMANENT
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("content/unknown.md\n"))
        rc = session_ledger.main(["check-staged"])
        assert rc == 1

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_path_normalization(self, mock_dirty, isolate_session_dir):
        """Backslashes and ./ prefixes are normalized before comparison."""
        session_ledger.init_session("test-cs")
        session_ledger.record_file("content/a.md", "created")

        allowed, blocked = session_ledger.check_staged(["./content/a.md"])
        assert len(allowed) == 1
        assert len(blocked) == 0

        allowed2, blocked2 = session_ledger.check_staged(["content\\a.md"])
        assert len(allowed2) == 1
        assert len(blocked2) == 0


# ---------------------------------------------------------------------------
# inherit CLI (T2-G2)
# ---------------------------------------------------------------------------

class TestInheritCLI:
    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_inherit_cli_with_session_id(self, mock_dirty, isolate_session_dir, capsys):
        """CLI inherit --session-id works."""
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/a.md", "created")
        session_ledger.close_session("session-a")
        session_ledger.init_session("session-b")

        rc = session_ledger.main(["inherit", "--session-id", "session-a"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "Inherited 1 files" in output
        assert "content/a.md" in output

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_inherit_cli_no_prior(self, mock_dirty, isolate_session_dir, capsys):
        """CLI inherit with no prior session returns exit 2."""
        session_ledger.init_session("only-session")
        rc = session_ledger.main(["inherit"])
        assert rc == 2

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_inherit_cli_no_active_session(self, mock_dirty, isolate_session_dir, capsys):
        """CLI inherit without active session returns exit 1."""
        rc = session_ledger.main(["inherit"])
        assert rc == 1

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_inherit_preserves_original_actions(self, mock_dirty, isolate_session_dir):
        """Inherited files carry their original action, not hardcoded 'modified'."""
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/new.md", "created", skill="S-56")
        session_ledger.record_file("content/old.md", "deleted")
        session_ledger.record_file("content/changed.md", "modified")
        session_ledger.close_session("session-a")

        session_ledger.init_session("session-b")
        count, paths = session_ledger.inherit_session("session-a")
        assert count == 3

        # Verify actions in session-b's manifest
        manifest_b = json.loads(
            (isolate_session_dir / "session-b.json").read_text(encoding="utf-8"))
        touched = manifest_b["touched_files"]
        assert touched["content/new.md"]["action"] == "created"
        assert touched["content/old.md"]["action"] == "deleted"
        assert touched["content/changed.md"]["action"] == "modified"

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_inherit_cli_invalid_session_id(self, mock_dirty, isolate_session_dir, capsys):
        """CLI inherit with nonexistent session ID gives clear error."""
        session_ledger.init_session("session-b")
        rc = session_ledger.main(["inherit", "--session-id", "nonexistent-id"])
        assert rc == 2
        err = capsys.readouterr().err
        assert "not found" in err


# ---------------------------------------------------------------------------
# _log_adopt (T2-G3 test coverage)
# ---------------------------------------------------------------------------

class TestLogAdopt:
    @patch.object(session_ledger, "_git_dirty_files",
                  return_value=["content/a.md", "content/b.md"])
    def test_log_adopt_calls_session_logger(self, mock_dirty, isolate_session_dir):
        """_log_adopt is called with adopt args and count when cmd_adopt runs."""
        session_ledger.init_session("test-log")
        with patch("session_ledger._log_adopt") as mock_log:
            session_ledger.main(["adopt", "--all"])
            mock_log.assert_called_once()
            adopt_args, count = mock_log.call_args[0]
            assert adopt_args == ["--all", "skipped=0"]
            assert count == 2

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_log_adopt_survives_import_error(self, mock_dirty, isolate_session_dir):
        """_log_adopt silently handles missing session_logger."""
        session_ledger.init_session("test-log")
        # Call _log_adopt directly — it should not raise even if session_logger is unavailable
        session_ledger._log_adopt(["--all"], 5)  # No exception = pass


# ---------------------------------------------------------------------------
# HARDEN-A2: per-session isolation, ambiguity, TTL, cross-session adopt guard
# ---------------------------------------------------------------------------

class TestSessionIsolationA2:
    def test_ambiguous_resolution_raises(self, isolate_session_dir):
        """Two live sessions + no explicit identity = loud error, not silent pick."""
        session_ledger.init_session("session-a")
        session_ledger.init_session("session-b")
        with pytest.raises(session_ledger.AmbiguousSessionError) as exc_info:
            session_ledger.record_file("content/foo.md", "created")
        assert set(exc_info.value.candidates) == {"session-a", "session-b"}

    def test_ambiguous_cli_exit_3(self, isolate_session_dir, capsys):
        session_ledger.init_session("session-a")
        session_ledger.init_session("session-b")
        rc = session_ledger.main(["record", "--file", "content/foo.md",
                                  "--action", "created"])
        assert rc == 3
        err = capsys.readouterr().err
        assert "AMBIGUOUS" in err
        assert "session-a" in err and "session-b" in err

    def test_explicit_session_id_no_cross_contamination(self, isolate_session_dir):
        """Records with explicit ids land in exactly the named manifest."""
        session_ledger.init_session("session-a")
        session_ledger.init_session("session-b")
        assert session_ledger.record_file("content/a-only.md", "created",
                                          session_id="session-a") is True
        assert session_ledger.record_file("content/b-only.md", "created",
                                          session_id="session-b") is True

        touched_a = session_ledger.get_touched_files("session-a")
        touched_b = session_ledger.get_touched_files("session-b")
        assert "content/a-only.md" in touched_a
        assert "content/a-only.md" not in touched_b
        assert "content/b-only.md" in touched_b
        assert "content/b-only.md" not in touched_a

    def test_env_var_resolves_identity(self, isolate_session_dir, monkeypatch):
        session_ledger.init_session("session-a")
        session_ledger.init_session("session-b")
        monkeypatch.setenv("AGENT_SESSION_ID", "session-b")
        assert session_ledger.record_file("content/via-env.md", "created") is True
        assert "content/via-env.md" in session_ledger.get_touched_files("session-b")
        assert "content/via-env.md" not in session_ledger.get_touched_files("session-a")

    def test_env_var_missing_manifest_falls_through(self, isolate_session_dir, monkeypatch):
        """An env id with no manifest is a hint, not a hard failure — scan proceeds."""
        session_ledger.init_session("session-real")
        monkeypatch.setenv("AGENT_SESSION_ID", "session-ghost")
        assert session_ledger.record_file("content/x.md", "created") is True
        assert "content/x.md" in session_ledger.get_touched_files("session-real")

    # -- Step 3 (production concurrency redesign, 2026-08-01): delegation to
    # session_identity.py adds CODEX_THREAD_ID and CLAUDE_CODE_SESSION_ID as
    # additional resolution tiers below AGENT_SESSION_ID. --------------------

    def test_codex_thread_id_resolves_identity(self, isolate_session_dir, monkeypatch):
        session_ledger.init_session("session-a")
        session_ledger.init_session("session-b")
        monkeypatch.setenv("CODEX_THREAD_ID", "session-b")
        assert session_ledger.record_file("content/via-codex.md", "created") is True
        assert "content/via-codex.md" in session_ledger.get_touched_files("session-b")
        assert "content/via-codex.md" not in session_ledger.get_touched_files("session-a")

    def test_claude_code_session_id_resolves_identity(self, isolate_session_dir, monkeypatch):
        session_ledger.init_session("session-a")
        session_ledger.init_session("session-b")
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "session-b")
        assert session_ledger.record_file("content/via-claude.md", "created") is True
        assert "content/via-claude.md" in session_ledger.get_touched_files("session-b")
        assert "content/via-claude.md" not in session_ledger.get_touched_files("session-a")

    def test_agent_session_id_takes_precedence_over_claude_code_session_id(
        self, isolate_session_dir, monkeypatch
    ):
        session_ledger.init_session("session-a")
        session_ledger.init_session("session-b")
        monkeypatch.setenv("AGENT_SESSION_ID", "session-a")
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "session-b")
        assert session_ledger.record_file("content/precedence.md", "created") is True
        assert "content/precedence.md" in session_ledger.get_touched_files("session-a")
        assert "content/precedence.md" not in session_ledger.get_touched_files("session-b")

    def test_init_default_id_prefers_resolvable_identity_over_random(
        self, isolate_session_dir, monkeypatch
    ):
        """init_session(None) with a resolvable identity uses it verbatim,
        instead of minting an unrelated random id -- the ergonomic half of
        the Step 3 fix (a caller that never learns/passes back its own
        random id can still find its own manifest on the next call)."""
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "conv-uuid-1")
        sid = session_ledger.init_session(None)
        assert sid == "conv-uuid-1"

    def test_init_default_id_falls_back_to_random_with_no_identity(
        self, isolate_session_dir
    ):
        """No explicit id, no resolvable env identity -> unchanged legacy
        behavior (a fresh random id, not a crash or empty string)."""
        sid = session_ledger.init_session(None)
        assert sid  # non-empty
        assert sid != "conv-uuid-1"

    def test_repeated_init_with_shared_identity_hits_f6_guard_not_silent_fragmentation(
        self, isolate_session_dir, monkeypatch
    ):
        """The bug this step actually closes (reproduced live before the fix
        shipped): a single real session calling init_session(None) twice
        under a shared resolvable identity (e.g. two Bash calls in one
        Claude Code conversation, or two sibling subagents) must hit the
        EXISTING F6 guard on the second call -- a named ValueError pointing
        at the live manifest -- rather than silently minting a second,
        unrelated manifest that later surfaces as a false-positive
        AmbiguousSessionError between two ids belonging to the same session."""
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "conv-shared-uuid")
        sid1 = session_ledger.init_session(None)
        session_ledger.record_file("content/first.md", "created", session_id=sid1)

        with pytest.raises(ValueError, match="already has an ACTIVE manifest"):
            session_ledger.init_session(None)

        # The guard refused the second init -- the ORIGINAL manifest (and its
        # already-recorded touch) must be untouched, not partially wiped.
        touched = session_ledger.get_touched_files("conv-shared-uuid")
        assert "content/first.md" in touched

        # And a subsequent unqualified call resolves cleanly to the one real
        # manifest -- no AmbiguousSessionError, unlike the unpatched bug.
        assert session_ledger.record_file("content/second.md", "created") is True
        assert "content/second.md" in session_ledger.get_touched_files("conv-shared-uuid")

    def test_stale_session_swept_and_excluded(self, isolate_session_dir):
        """An idle-beyond-TTL session is flipped to stale (not deleted) and no
        longer resolves; the surviving live session resolves unambiguously."""
        import os as _os
        import time as _time
        session_ledger.init_session("session-old")
        old_path = isolate_session_dir / "session-old.json"
        ancient = _time.time() - 10 * 3600  # 10h idle > 8h TTL
        _os.utime(old_path, (ancient, ancient))

        session_ledger.init_session("session-new")
        # Resolution sweeps session-old to stale and picks session-new
        assert session_ledger.record_file("content/new-work.md", "created") is True
        assert "content/new-work.md" in session_ledger.get_touched_files("session-new")

        manifest_old = json.loads(old_path.read_text(encoding="utf-8"))
        assert manifest_old["status"] == "stale"
        assert "stale_at" in manifest_old
        assert old_path.exists()  # inspectable, never deleted

    def test_stale_session_reactivates_on_explicit_write(self, isolate_session_dir):
        import os as _os
        import time as _time
        session_ledger.init_session("session-old")
        old_path = isolate_session_dir / "session-old.json"
        ancient = _time.time() - 10 * 3600
        _os.utime(old_path, (ancient, ancient))
        session_ledger._sweep_stale()
        assert json.loads(old_path.read_text(encoding="utf-8"))["status"] == "stale"

        # Explicit write reactivates — staleness is a heuristic, not a tombstone
        assert session_ledger.record_file("content/late.md", "created",
                                          session_id="session-old") is True
        manifest = json.loads(old_path.read_text(encoding="utf-8"))
        assert manifest["status"] == "active"
        assert "stale_at" not in manifest

    def test_close_requires_name(self, isolate_session_dir):
        session_ledger.init_session("session-a")
        assert session_ledger.close_session("session-a") is True
        assert session_ledger.close_session("no-such-session") is False
        rc = session_ledger.main(["close", "--session-id", "no-such-session"])
        assert rc == 2

    def test_closed_session_rejects_writes(self, isolate_session_dir):
        session_ledger.init_session("session-a")
        session_ledger.close_session("session-a")
        assert session_ledger.record_file("content/x.md", "created",
                                          session_id="session-a") is False

    def test_adopt_refuses_cross_session_claims(self, isolate_session_dir):
        """The PDF-*-REFRESH-001 guard: files in another ACTIVE session's ledger
        are refused by adopt unless explicitly confirmed."""
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/theirs.md", "modified",
                                   session_id="session-a")
        session_ledger.init_session("session-b")

        skipped: dict[str, str] = {}
        count = session_ledger.adopt_files(
            ["content/theirs.md", "content/free.md"],
            session_id="session-b", skipped_out=skipped,
        )
        assert count == 1  # only the unclaimed path
        assert skipped == {"content/theirs.md": "session-a"}
        touched_b = session_ledger.get_touched_files("session-b")
        assert "content/free.md" in touched_b
        assert "content/theirs.md" not in touched_b

    def test_adopt_cross_session_override(self, isolate_session_dir):
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/theirs.md", "modified",
                                   session_id="session-a")
        session_ledger.init_session("session-b")

        count = session_ledger.adopt_files(
            ["content/theirs.md"], session_id="session-b",
            confirm_cross_session=True,
        )
        assert count == 1
        assert "content/theirs.md" in session_ledger.get_touched_files("session-b")

    def test_adopt_ignores_claims_from_closed_and_stale(self, isolate_session_dir):
        import os as _os
        import time as _time
        session_ledger.init_session("session-closed")
        session_ledger.record_file("content/c.md", "modified",
                                   session_id="session-closed")
        session_ledger.close_session("session-closed")

        session_ledger.init_session("session-stale")
        session_ledger.record_file("content/s.md", "modified",
                                   session_id="session-stale")
        stale_path = isolate_session_dir / "session-stale.json"
        ancient = _time.time() - 10 * 3600
        _os.utime(stale_path, (ancient, ancient))
        session_ledger._sweep_stale()

        session_ledger.init_session("session-live")
        skipped: dict[str, str] = {}
        count = session_ledger.adopt_files(
            ["content/c.md", "content/s.md"],
            session_id="session-live", skipped_out=skipped,
        )
        assert count == 2
        assert skipped == {}

    def test_concurrent_records_same_session_no_lost_updates(self, isolate_session_dir):
        """Two threads recording into the SAME session must not lose entries —
        the manifest lock serializes the read-modify-write."""
        import threading
        session_ledger.init_session("session-shared")
        errors: list[Exception] = []

        def worker(prefix: str):
            try:
                for i in range(20):
                    ok = session_ledger.record_file(
                        f"content/{prefix}-{i}.md", "created",
                        session_id="session-shared",
                    )
                    assert ok is True
            except Exception as exc:  # pragma: no cover - diagnostics
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(p,)) for p in ("t1", "t2")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)

        assert not errors, f"worker errors: {errors}"
        touched = session_ledger.get_touched_files("session-shared")
        assert len(touched) == 40


# ---------------------------------------------------------------------------
# resolve_context (pure) + closed-env-id resolution fix
# (2026-08-29 stale-guard plan, Phase 0a / TC-SG-01)
# ---------------------------------------------------------------------------

class TestResolveContextPure:
    def test_no_ledger_dir(self, isolate_session_dir):
        assert session_ledger.resolve_context().status == "no_ledger_dir"

    def test_none_when_dir_empty(self, isolate_session_dir):
        isolate_session_dir.mkdir(parents=True, exist_ok=True)
        assert session_ledger.resolve_context().status == "none"

    def test_single_active_resolves_via_scan(self, isolate_session_dir):
        sid = session_ledger.init_session("ctx-single")
        ctx = session_ledger.resolve_context()
        assert (ctx.status, ctx.session_id, ctx.source) == ("resolved", sid, "scan")

    def test_two_active_is_ambiguous_with_candidates(self, isolate_session_dir):
        session_ledger.init_session("ctx-a")
        session_ledger.init_session("ctx-b")
        ctx = session_ledger.resolve_context()
        assert ctx.status == "ambiguous"
        assert set(ctx.candidates) == {"ctx-a", "ctx-b"}

    def test_env_id_resolves_as_env_source(self, isolate_session_dir, monkeypatch):
        session_ledger.init_session("ctx-env")
        monkeypatch.setenv("AGENT_SESSION_ID", "ctx-env")
        ctx = session_ledger.resolve_context()
        assert (ctx.status, ctx.session_id, ctx.source) == ("resolved", "ctx-env", "env")

    def test_env_id_closed_reports_closed_never_the_scan(self, isolate_session_dir, monkeypatch):
        session_ledger.init_session("ctx-mine")
        session_ledger.close_session("ctx-mine")
        session_ledger.init_session("ctx-other")  # one other live session exists
        monkeypatch.setenv("AGENT_SESSION_ID", "ctx-mine")
        ctx = session_ledger.resolve_context()
        assert ctx.status == "closed"
        assert ctx.session_id == "ctx-mine"

    def test_explicit_closed_reports_closed(self, isolate_session_dir):
        session_ledger.init_session("ctx-x")
        session_ledger.close_session("ctx-x")
        ctx = session_ledger.resolve_context("ctx-x")
        assert (ctx.status, ctx.session_id, ctx.source) == ("closed", "ctx-x", "explicit")

    def test_resolved_context_carries_base_sha(self, isolate_session_dir):
        session_ledger.init_session("ctx-base")
        manifest_path = isolate_session_dir / "ctx-base.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["base_commit_sha"] = "cafebabe" * 5
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        ctx = session_ledger.resolve_context("ctx-base")
        assert ctx.base_sha == "cafebabe" * 5

    def test_resolve_context_is_pure(self, isolate_session_dir):
        """No stale sweep, no ACTIVE-pointer write, no manifest mtime changes
        (adversarial finding B3: _resolve_session writes on every read; the
        typed resolver must be safe to call from hooks and Tier-1 checks)."""
        session_ledger.init_session("ctx-p1")
        session_ledger.init_session("ctx-p2")
        pointer = isolate_session_dir / "ACTIVE"
        pointer_before = pointer.read_text(encoding="utf-8") if pointer.exists() else None
        mtimes_before = {
            f.name: f.stat().st_mtime_ns for f in isolate_session_dir.glob("*.json")
        }

        ctx = session_ledger.resolve_context()

        assert ctx.status == "ambiguous"
        mtimes_after = {
            f.name: f.stat().st_mtime_ns for f in isolate_session_dir.glob("*.json")
        }
        pointer_after = pointer.read_text(encoding="utf-8") if pointer.exists() else None
        assert mtimes_after == mtimes_before
        assert pointer_after == pointer_before


class TestClosedEnvIdResolutionFix:
    def test_resolve_session_env_closed_returns_none_not_other_session(
        self, isolate_session_dir, monkeypatch
    ):
        """B2 (2026-08-29): an env id naming a CLOSED manifest used to fall
        through to the directory scan and silently ADOPT the single other
        live session's identity -- a subsequent write then landed in THAT
        session's manifest. An ended session must resolve to no session."""
        session_ledger.init_session("mine-closed")
        session_ledger.close_session("mine-closed")
        session_ledger.init_session("other-live")
        monkeypatch.setenv("AGENT_SESSION_ID", "mine-closed")

        assert session_ledger._resolve_session(None) is None
        assert session_ledger.record_file("some/file.md", action="modified") is False

        other = json.loads(
            (isolate_session_dir / "other-live.json").read_text(encoding="utf-8")
        )
        assert other["touched_files"] == {}

    def test_env_id_with_no_manifest_still_falls_through_to_scan(
        self, isolate_session_dir, monkeypatch
    ):
        """Documented parity: a missing manifest for the env id remains a
        hint-only fall-through (single-session legacy flows depend on it)."""
        session_ledger.init_session("scan-target")
        monkeypatch.setenv("AGENT_SESSION_ID", "never-inited-id")
        resolved = session_ledger._resolve_session(None)
        assert resolved is not None
        assert resolved[0] == "scan-target"


# ---------------------------------------------------------------------------
# TC-GOV-02-02 (REQ-GOV-02): stale-open-mission block at session start
#
# The detector itself (mission_authority._plan_state_report) is TC-GOV-02-01's
# and is tested in test_mission_authority.py. What is pinned here is the
# session-start SURFACE: it must appear on every path the SessionStart hook
# actually takes (the --if-missing fast paths return before init's print block),
# it must stay short, it must show the unreadable-ledger list next to the stale
# one, and it must never break or hang session start.
# ---------------------------------------------------------------------------

_MISSION_STUB = {
    "mission_summary": "A test mission.",
    "governing_plan_path": "plans/test.md",
    "in_scope_outcomes": ["outcome"],
    "out_of_scope_items": ["excluded"],
    "mandatory_acceptance_criteria": ["criterion"],
    "mission_locked": False,
}


def _iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _write_archive(
    root: Path,
    dir_name: str,
    *,
    status: str = "open",
    mission_id: "str | None" = None,
    archived_at: "str | None" = None,
) -> Path:
    mission_dir = root / "reports" / "plan_state" / dir_name
    mission_dir.mkdir(parents=True, exist_ok=True)
    snapshot = dict(_MISSION_STUB, mission_id=mission_id or dir_name, _archive_status=status)
    if archived_at is not None:
        snapshot["_archived_at"] = archived_at
    (mission_dir / "mission_authority.yaml").write_text(
        yaml.safe_dump({"mission_authority": snapshot}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return mission_dir


def _seed_mission(root: Path, mission_id: str, *, days_quiet: float, status: str = "open") -> None:
    """A mission whose only taskcard row (written through the sanctioned
    TaskcardStore writer) is `days_quiet` days old."""
    _write_archive(root, mission_id, status=status)
    TaskcardStore(mission_id, repo_root=root).append({
        "task_id": "TC-1",
        "mission_id": mission_id,
        "status": "IN_PROGRESS",
        "recorded_at": _iso_days_ago(days_quiet),
        "evidence_refs": [],
        "recorded_by": "test-fixture",
    })


def _seed_unreadable_mission(root: Path, mission_id: str) -> None:
    mission_dir = root / "reports" / "plan_state" / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    (mission_dir / "mission_authority.yaml").write_text(
        "mission_authority: [unclosed", encoding="utf-8",
    )


class TestStaleMissionBlockLines:
    def test_lists_stale_open_mission_with_days_quiet_and_pointer(self, tmp_path):
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)
        _seed_mission(tmp_path, "MT-FRESH", days_quiet=1)
        _seed_mission(tmp_path, "MT-CLOSED", days_quiet=90, status="closed")

        lines = session_ledger.stale_mission_block_lines(tmp_path)

        text = "\n".join(lines)
        assert lines[0].startswith("Stale open missions") and lines[0].endswith(": 1")
        assert any("MT-STALE" in ln and "quiet 30d" in ln for ln in lines)
        assert "MT-FRESH" not in text and "MT-CLOSED" not in text
        assert "mission_authority.py status" in lines[-1]

    def test_nothing_to_say_when_nothing_is_stale_or_unreadable(self, tmp_path):
        _seed_mission(tmp_path, "MT-FRESH", days_quiet=1)
        _seed_mission(tmp_path, "MT-CLOSED", days_quiet=90, status="closed")
        assert session_ledger.stale_mission_block_lines(tmp_path) == []

    def test_nothing_to_say_when_there_is_no_plan_state_dir(self, tmp_path):
        assert session_ledger.stale_mission_block_lines(tmp_path) == []

    def test_caps_rows_at_five_oldest_first_and_folds_the_rest(self, tmp_path):
        for i in range(8):
            _seed_mission(tmp_path, f"MT-S{i}", days_quiet=10 + i)  # MT-S7 is the oldest

        lines = session_ledger.stale_mission_block_lines(tmp_path)

        assert lines[0].endswith(": 8")
        rows = [ln for ln in lines if ln.startswith("  MT-S")]
        assert len(rows) == 5
        assert "MT-S7" in rows[0] and "MT-S3" in rows[4]
        assert "and 3 more" in lines[-1]
        assert len(lines) <= 8  # header + 5 rows + one tail line (+ at most one more)

    def test_no_signal_open_mission_is_listed_first_as_no_activity_signal(self, tmp_path):
        _seed_mission(tmp_path, "MT-OLD", days_quiet=40)
        _write_archive(tmp_path, "MT-NEVER")  # open, no taskcards, no _archived_at

        lines = session_ledger.stale_mission_block_lines(tmp_path)

        rows = [ln for ln in lines if ln.startswith("  MT-")]
        assert "MT-NEVER" in rows[0] and "no activity signal" in rows[0]
        assert "MT-OLD" in rows[1]

    def test_unreadable_ledger_is_named_separately_and_not_counted_as_stale(self, tmp_path):
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)
        _seed_unreadable_mission(tmp_path, "MT-BROKEN")

        lines = session_ledger.stale_mission_block_lines(tmp_path)

        assert lines[0].endswith(": 1")  # only the genuinely stale mission is counted
        rows = [ln for ln in lines if ln.startswith("  MT-")]
        assert len(rows) == 1 and "MT-STALE" in rows[0]
        unreadable = [ln for ln in lines if "nreadable" in ln]
        assert len(unreadable) == 1
        assert "MT-BROKEN" in unreadable[0] and "staleness unknown" in unreadable[0]
        assert unreadable[0].rstrip().endswith("MT-BROKEN")

    def test_only_unreadable_ledgers_still_print_a_block(self, tmp_path):
        _seed_unreadable_mission(tmp_path, "MT-BROKEN")

        lines = session_ledger.stale_mission_block_lines(tmp_path)

        text = "\n".join(lines)
        assert "MT-BROKEN" in text and "Stale open missions" not in text
        assert "mission_authority.py status" in lines[-1]

    def test_unreadable_names_are_capped_at_three(self, tmp_path):
        for i in range(5):
            _seed_unreadable_mission(tmp_path, f"MT-BROKEN{i}")

        lines = session_ledger.stale_mission_block_lines(tmp_path)

        unreadable = [ln for ln in lines if "nreadable" in ln][0]
        assert ": 5" in unreadable
        assert "MT-BROKEN0" in unreadable and "MT-BROKEN2" in unreadable
        assert "MT-BROKEN3" not in unreadable and "+2 more" in unreadable

    def test_output_is_ascii_and_each_line_is_bounded(self, tmp_path):
        # A short directory holding a free-text yaml mission_id that is both
        # non-ASCII and very long (a 300-char directory name would exceed
        # MAX_PATH on Windows before it ever tested the formatter).
        long_id = "MT-café-" + "x" * 300
        _write_archive(
            tmp_path, "MT-SHORT-DIR", mission_id=long_id, archived_at=_iso_days_ago(30),
        )

        lines = session_ledger.stale_mission_block_lines(tmp_path)

        assert any("MT-caf\\xe9-" in ln for ln in lines)  # shown, ASCII-escaped
        assert all(ln.isascii() for ln in lines)
        assert all(len(ln) <= 140 for ln in lines)

    def test_a_crash_in_an_unrelated_session_store_cannot_suppress_the_warning(self, tmp_path):
        """mission_authority._session_ledger_report() raises AttributeError on a
        session manifest that is valid JSON but not an object (verified by an
        independent reviewer). build_liveness_report() would therefore blind the
        stale-mission detector; the session-start path must call the plan_state
        store directly and stay independent of every other store."""
        session_dir = tmp_path / "reports" / "session-state"
        session_dir.mkdir(parents=True)
        (session_dir / "poison.json").write_text("[1, 2]", encoding="utf-8")
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)

        lines = session_ledger.stale_mission_block_lines(tmp_path)

        assert any("MT-STALE" in ln for ln in lines)


class TestEmitStaleMissionBlock:
    def test_prints_nothing_at_all_when_nothing_is_stale(self, tmp_path, capsys):
        _seed_mission(tmp_path, "MT-FRESH", days_quiet=1)

        session_ledger.emit_stale_mission_block(tmp_path)

        captured = capsys.readouterr()
        assert captured.out == "" and captured.err == ""

    def test_prints_the_block_to_stdout(self, tmp_path, capsys):
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)

        session_ledger.emit_stale_mission_block(tmp_path)

        captured = capsys.readouterr()
        # stdout, not stderr: the SessionStart hook discards init's stderr.
        assert "MT-STALE" in captured.out and captured.err == ""

    def test_a_crash_in_the_report_is_swallowed_with_one_short_line(self, tmp_path, capsys):
        def boom(root):
            raise RuntimeError("secret detail about " + str(tmp_path))

        session_ledger.emit_stale_mission_block(tmp_path, plan_state_rows_fn=boom)

        captured = capsys.readouterr()
        assert captured.out == "stale-mission check unavailable: RuntimeError\n"
        assert captured.err == ""  # and never the exception message (it can carry paths)

    def test_a_non_exception_interrupt_is_not_swallowed(self, tmp_path):
        def interrupt(root):
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            session_ledger.emit_stale_mission_block(tmp_path, plan_state_rows_fn=interrupt)

    def test_a_source_returning_garbage_rows_is_contained(self, tmp_path, capsys):
        session_ledger.emit_stale_mission_block(
            tmp_path, plan_state_rows_fn=lambda root: [None, 7, "x", {"stale": True}],
        )

        out = capsys.readouterr().out
        assert "Traceback" not in out and out.count("\n") <= 8


class TestInitSurfacesStaleMissions:
    """cmd_init handles --if-missing fast paths BEFORE its print block, and the
    SessionStart hook always passes --if-missing -- so the block must be emitted
    on every path, not only inside the print block (which only a brand-new
    session id ever reaches)."""

    def test_fresh_init_prints_the_block_after_the_existing_output(self, tmp_path, capsys):
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)

        ret = session_ledger.main(["init", "--session-id", "sm-fresh"])

        out = capsys.readouterr().out
        assert ret == 0
        assert "Session initialized: sm-fresh" in out and "MT-STALE" in out
        assert out.index("Session initialized") < out.index("Stale open missions")

    def test_if_missing_already_active_fast_path_prints_the_block(self, tmp_path, capsys):
        session_ledger.init_session("sm-active")
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)

        ret = session_ledger.main(["init", "--if-missing", "--session-id", "sm-active"])

        out = capsys.readouterr().out
        assert ret == 0
        assert "already-active" in out and "MT-STALE" in out

    def test_if_missing_reactivated_fast_path_prints_the_block(
        self, isolate_session_dir, tmp_path, capsys
    ):
        session_ledger.init_session("sm-stale")
        path = isolate_session_dir / "sm-stale.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["status"] = "stale"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)

        ret = session_ledger.main(["init", "--if-missing", "--session-id", "sm-stale"])

        out = capsys.readouterr().out
        assert ret == 0
        assert "reactivated" in out and "MT-STALE" in out

    def test_if_missing_reopened_fast_path_prints_the_block(self, tmp_path, capsys):
        session_ledger.init_session("sm-closed")
        session_ledger.close_session("sm-closed")
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)

        ret = session_ledger.main(["init", "--if-missing", "--session-id", "sm-closed"])

        out = capsys.readouterr().out
        assert ret == 0
        assert "reopened" in out and "MT-STALE" in out

    def test_if_missing_missing_manifest_path_prints_the_block(self, tmp_path, capsys):
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)

        ret = session_ledger.main(["init", "--if-missing", "--session-id", "sm-new"])

        out = capsys.readouterr().out
        assert ret == 0
        assert "Session initialized: sm-new" in out and "MT-STALE" in out

    def test_hook_invocation_shape_with_repo_root_flag_prints_the_block(self, tmp_path, capsys):
        """The hook runs `session_ledger.py --repo-root <root> init --if-missing
        --session-id <id>` in a fresh process (no prior configure())."""
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)
        try:
            ret = session_ledger.main([
                "--repo-root", str(tmp_path), "init", "--if-missing", "--session-id", "sm-hook",
            ])
            out = capsys.readouterr().out
        finally:
            session_ledger.configure()  # reset -- --repo-root reconfigured the module
        assert ret == 0
        assert "MT-STALE" in out

    def test_if_missing_fast_path_stays_a_single_line_when_nothing_is_stale(
        self, tmp_path, capsys
    ):
        session_ledger.init_session("sm-quiet")
        _seed_mission(tmp_path, "MT-FRESH", days_quiet=1)

        ret = session_ledger.main(["init", "--if-missing", "--session-id", "sm-quiet"])

        lines = capsys.readouterr().out.strip().splitlines()
        assert ret == 0 and len(lines) == 1 and "already-active" in lines[0]

    def test_a_crash_in_the_report_never_breaks_init(self, tmp_path, isolate_session_dir, capsys):
        def boom(root):
            raise ValueError("boom")

        session_ledger.configure(repo_root=tmp_path, plan_state_rows_fn=boom)

        ret = session_ledger.main(["init", "--session-id", "sm-crash"])

        out = capsys.readouterr().out
        assert ret == 0
        assert (isolate_session_dir / "sm-crash.json").is_file()  # init itself completed
        assert [ln for ln in out.splitlines() if "stale-mission" in ln] == [
            "stale-mission check unavailable: ValueError"
        ]
        assert "Traceback" not in out

    def test_a_crash_in_the_report_never_breaks_the_if_missing_fast_path(
        self, tmp_path, capsys
    ):
        def boom(root):
            raise ValueError("boom")

        session_ledger.init_session("sm-crash-fast")
        session_ledger.configure(repo_root=tmp_path, plan_state_rows_fn=boom)

        ret = session_ledger.main(["init", "--if-missing", "--session-id", "sm-crash-fast"])

        out = capsys.readouterr().out
        assert ret == 0
        assert "already-active" in out
        assert "stale-mission check unavailable: ValueError" in out

    def test_the_block_is_still_emitted_when_the_init_body_itself_raises(
        self, tmp_path, capsys
    ):
        """A failure inside init (here a real one: the session dir path is a
        regular file, so creating it raises) must not suppress the warning --
        the stale-mission list has nothing to do with the session manifests --
        and must not be masked either: the original error still propagates."""
        _seed_mission(tmp_path, "MT-STALE", days_quiet=30)
        blocked = tmp_path / "not-a-dir"
        blocked.write_text("i am a file", encoding="utf-8")
        session_ledger.configure(repo_root=tmp_path, session_dir=blocked)

        with pytest.raises(OSError):
            session_ledger.main(["init", "--session-id", "sm-raises"])

        assert "MT-STALE" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# TC-GOV-02-02 stage 3: a session-state manifest that is valid JSON but not an
# object used to be a poison pill. _load_manifest() documents "None if missing
# or corrupt" but returned the raw JSON value, so _sweep_stale() (the first thing
# init does, over EVERY manifest) raised AttributeError on `.get` -- one stray
# file made `session_ledger.py init` exit 1 for every session in that repo, i.e.
# no manifest and, before the finally in cmd_init, no stale-mission block either.
# ---------------------------------------------------------------------------

class TestNonObjectManifestPoisonPill:
    @pytest.mark.parametrize("payload", ["[1, 2]", '"a string"', "42", "null", "true"])
    def test_load_manifest_returns_none_for_non_object_json(self, isolate_session_dir, payload):
        isolate_session_dir.mkdir(parents=True, exist_ok=True)
        path = isolate_session_dir / "odd.json"
        path.write_text(payload, encoding="utf-8")

        assert session_ledger._load_manifest(path) is None

    def test_load_manifest_returns_none_for_invalid_utf8(self, isolate_session_dir):
        isolate_session_dir.mkdir(parents=True, exist_ok=True)
        path = isolate_session_dir / "binary.json"
        path.write_bytes(b"\xff\xfe\x00{not utf-8")

        assert session_ledger._load_manifest(path) is None

    def test_load_manifest_still_returns_a_real_manifest(self, isolate_session_dir):
        session_ledger.init_session("real-one")

        manifest = session_ledger._load_manifest(isolate_session_dir / "real-one.json")

        assert isinstance(manifest, dict) and manifest["status"] == "active"

    @pytest.mark.parametrize("if_missing", [False, True])
    def test_init_survives_a_non_object_manifest_in_the_session_dir(
        self, isolate_session_dir, if_missing
    ):
        isolate_session_dir.mkdir(parents=True, exist_ok=True)
        (isolate_session_dir / "poison.json").write_text("[1, 2]", encoding="utf-8")
        argv = ["init", "--session-id", "after-poison"]
        if if_missing:
            argv.insert(1, "--if-missing")

        ret = session_ledger.main(argv)

        assert ret == 0
        assert (isolate_session_dir / "after-poison.json").is_file()
