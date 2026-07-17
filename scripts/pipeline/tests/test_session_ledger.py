"""Tests for session_ledger.py — session-scoped file touch ledger."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import session_ledger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_session_dir(tmp_path):
    """Redirect session state to tmp_path via configure() seam."""
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

    def test_closes_prior_session(self, isolate_session_dir):
        sid1 = session_ledger.init_session("session-1")
        sid2 = session_ledger.init_session("session-2")

        m1 = json.loads((isolate_session_dir / "session-1.json").read_text(encoding="utf-8"))
        m2 = json.loads((isolate_session_dir / "session-2.json").read_text(encoding="utf-8"))

        assert m1["status"] == "closed"
        assert "closed_at" in m1
        assert m2["status"] == "active"

    @patch.object(session_ledger, "_git_dirty_files", return_value=["file_a.md", "file_b.md"])
    def test_captures_dirty_snapshot(self, mock_dirty, isolate_session_dir):
        sid = session_ledger.init_session("snap-test")
        manifest = json.loads((isolate_session_dir / "snap-test.json").read_text(encoding="utf-8"))
        assert manifest["dirty_at_start"] == ["file_a.md", "file_b.md"]


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
    """Tests for the cross-session hand-off scenario:
    Session A records files → conversation ends → Session B inits (closes A)
    → B inherits A's work → B can commit A's files."""

    @patch.object(session_ledger, "_git_dirty_files", return_value=["content/a.md", "content/b.md"])
    def test_session_b_init_closes_a(self, mock_dirty, isolate_session_dir):
        """When Session B inits, Session A is closed and B's dirty_at_start
        includes A's touched files."""
        # Session A
        sid_a = session_ledger.init_session("session-a")
        session_ledger.record_file("content/a.md", "created", skill="S-56")
        session_ledger.record_file("content/b.md", "modified", skill="S-21")

        # Session B inits — closes A
        mock_dirty.return_value = ["content/a.md", "content/b.md", "content/c.md"]
        sid_b = session_ledger.init_session("session-b")

        # A is now closed
        manifest_a = json.loads((isolate_session_dir / "session-a.json").read_text(encoding="utf-8"))
        assert manifest_a["status"] == "closed"
        assert "content/a.md" in manifest_a["touched_files"]
        assert "content/b.md" in manifest_a["touched_files"]

        # B is active and its dirty_at_start includes A's files
        manifest_b = json.loads((isolate_session_dir / "session-b.json").read_text(encoding="utf-8"))
        assert manifest_b["status"] == "active"
        assert "content/a.md" in manifest_b["dirty_at_start"]
        assert "content/b.md" in manifest_b["dirty_at_start"]

    @patch.object(session_ledger, "_git_dirty_files", return_value=["content/a.md"])
    def test_inherit_from_prior_session(self, mock_dirty, isolate_session_dir):
        """inherit_session copies A's touched_files into B as adopted entries."""
        # Session A: record files
        sid_a = session_ledger.init_session("session-a")
        session_ledger.record_file("content/a.md", "created", skill="S-56")

        # Session B
        mock_dirty.return_value = ["content/a.md", "content/other.md"]
        sid_b = session_ledger.init_session("session-b")

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
        # Session A
        sid_a = session_ledger.init_session("session-a")
        session_ledger.record_file("content/a.md", "created")

        # Session B (closes A)
        sid_b = session_ledger.init_session("session-b")

        # Inherit without specifying session ID
        count, paths = session_ledger.inherit_session()
        assert count == 1
        assert "content/a.md" in paths

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_prior_session_manifest_survives(self, mock_dirty, isolate_session_dir):
        """A's closed manifest is still readable after B inits."""
        sid_a = session_ledger.init_session("session-a")
        session_ledger.record_file("content/a.md", "created")

        sid_b = session_ledger.init_session("session-b")

        # A's manifest file still exists and is valid
        path_a = isolate_session_dir / "session-a.json"
        assert path_a.exists()
        manifest_a = json.loads(path_a.read_text(encoding="utf-8"))
        assert manifest_a["status"] == "closed"
        assert manifest_a["session_id"] == "session-a"
        assert "content/a.md" in manifest_a["touched_files"]

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_inherit_no_prior_session_returns_zero(self, mock_dirty, isolate_session_dir):
        """inherit_session returns (0, []) when there's no prior closed session."""
        sid = session_ledger.init_session("only-session")
        count, paths = session_ledger.inherit_session()
        assert count == 0
        assert paths == []

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_cmd_init_reports_prior_session(self, mock_dirty, isolate_session_dir, capsys):
        """cmd_init output mentions prior session when one exists."""
        session_ledger.init_session("session-a")
        session_ledger.record_file("content/x.md", "created")

        # Re-init via CLI
        rc = session_ledger.main(["init", "--session-id", "session-b"])
        assert rc == 0
        output = capsys.readouterr().out
        assert "Prior session closed: session-a" in output
        assert "1 touched files" in output


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
            assert adopt_args == ["--all"]
            assert count == 2

    @patch.object(session_ledger, "_git_dirty_files", return_value=[])
    def test_log_adopt_survives_import_error(self, mock_dirty, isolate_session_dir):
        """_log_adopt silently handles missing session_logger."""
        session_ledger.init_session("test-log")
        # Call _log_adopt directly — it should not raise even if session_logger is unavailable
        session_ledger._log_adopt(["--all"], 5)  # No exception = pass
