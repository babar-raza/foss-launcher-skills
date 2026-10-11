"""Tests for pre-commit-audit.sh Step 5 (content_hash normalization) and
Step 10 (graded_at reversion), sourced LIVE from the on-disk script at test
time (never hand-copied, so these tests cannot silently drift from the real
script's actual behavior -- 2026-08-20 production assessment,
reports/skill-gaps/2026-08-20-git-plumb-commit-tier1-mutation-safety.md).

Each test extracts the exact bash text for one step from
scripts/pre-commit-audit.sh, wraps it in a minimal harness (stub
_pc_step_start/_pc_step_end/_pc_exit, a manually-seeded `changed` array),
and runs it via a real, self-verified Git Bash against an isolated fixture
git repository -- GIT_DIR/GIT_WORK_TREE point the harness's git commands at
the fixture repo while the harness's own cwd stays the real repo root, so
`.venv/Scripts/python` and the real check scripts resolve normally without
ever touching this repo's own real index or working tree.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parents[2]
_PRECOMMIT_AUDIT_SH = _REPO_ROOT / "scripts" / "pre-commit-audit.sh"

sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"))
import git_plumb_commit as gpc  # noqa: E402,F401  (guard shares its resolver)

from _git_bash_guard import require_git_bash  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False,
    )


def _extract_bash_block(script_text: str, start_marker: str, end_marker: str) -> str:
    start_idx = script_text.index(start_marker)
    end_idx = script_text.index(end_marker, start_idx)
    return script_text[start_idx:end_idx]


def _bash_path() -> str:
    return require_git_bash()  # skip on POSIX, fail on Windows (TC-SG-20a)


def _absolutize_repo_relative_paths(block: str) -> str:
    """The extracted block references its own script dependencies
    (.venv/Scripts/python, check_graded_at_only.py, provenance_normalize_hash.py,
    PYTHONPATH=scripts/pipeline) via paths relative to the REAL repo root --
    correct for the real hook (which always runs with cwd=repo root), but the
    harness below must run with cwd=<fixture repo> for git's own pathspec
    resolution to behave correctly (GIT_DIR/GIT_WORK_TREE env-var overrides
    with a cwd outside the work tree entirely produced silently-wrong
    pathspec resolution -- confirmed live while writing this test: `git
    restore --staged` reported success but the real index diff was
    unchanged). Rewriting these specific path literals to absolute paths is a
    pure environment-portability adaptation -- it does not touch a single
    conditional, git command, or message in the extracted logic itself.
    """
    real_root = str(_REPO_ROOT).replace("\\", "/")
    replacements = {
        '".venv/Scripts/python"': f'"{real_root}/.venv/Scripts/python"',
        '".venv/bin/python"': f'"{real_root}/.venv/bin/python"',
        "scripts/pipeline/commands/governance/check_graded_at_only.py":
            f"{real_root}/scripts/pipeline/commands/governance/check_graded_at_only.py",
        "scripts/pipeline/commands/diagnostics/provenance_normalize_hash.py":
            f"{real_root}/scripts/pipeline/commands/diagnostics/provenance_normalize_hash.py",
        "PYTHONPATH=scripts/pipeline": f"PYTHONPATH={real_root}/scripts/pipeline",
    }
    for old, new in replacements.items():
        block = block.replace(old, new)
    return block


def _run_extracted_block(
    block: str, changed_files: list[str], *, fixture_repo: Path,
    pc_audit_no_mutate: bool, extra_env: "dict[str, str] | None" = None,
) -> subprocess.CompletedProcess:
    real_root = str(_REPO_ROOT).replace("\\", "/")
    harness = (
        "#!/bin/bash\n"
        "_pc_step_start() { :; }\n"
        "_pc_step_end() { :; }\n"
        "_pc_exit() { exit \"$1\"; }\n"
        # Step 5 depends on $_HOOK_PYTHON, resolved much earlier in the real
        # script (outside the extracted block) -- set it directly here rather
        # than also extracting that unrelated preamble.
        f'if [ -f "{real_root}/.venv/Scripts/python.exe" ]; then\n'
        f'    _HOOK_PYTHON="{real_root}/.venv/Scripts/python.exe"\n'
        f'elif [ -f "{real_root}/.venv/bin/python" ]; then\n'
        f'    _HOOK_PYTHON="{real_root}/.venv/bin/python"\n'
        "else\n"
        '    _HOOK_PYTHON=""\n'
        "fi\n"
        "changed=(" + " ".join(f'"{f}"' for f in changed_files) + ")\n"
        + _absolutize_repo_relative_paths(block)
    )
    harness_path = fixture_repo.parent / "harness.sh"
    with harness_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(harness)

    env = {**os.environ}
    env.pop("PC_AUDIT_NO_MUTATE", None)
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    if pc_audit_no_mutate:
        env["PC_AUDIT_NO_MUTATE"] = "1"
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [_bash_path(), str(harness_path)], cwd=str(fixture_repo),
        capture_output=True, text=True, env=env,
    )


# ---------------------------------------------------------------------------
# Step 10: graded_at reversion
# ---------------------------------------------------------------------------

_STEP10_REL_PATH = "content/testfamily/en/testplatform/page.md"


def _step10_block() -> str:
    text = _PRECOMMIT_AUDIT_SH.read_text(encoding="utf-8")
    return _extract_bash_block(
        text, '_pc_step_start "graded_at reversion"', '_pc_step_start "monkeypatch lint"',
    )


def _init_step10_fixture(tmp_path: Path, *, extra_unstaged_edit: bool) -> Path:
    repo = tmp_path / "fixture_repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")

    full_path = repo / _STEP10_REL_PATH
    full_path.parent.mkdir(parents=True, exist_ok=True)

    original = '---\ngraded_at: "2026-01-01"\n---\n\nOriginal prose.\n'
    full_path.write_text(original, encoding="utf-8")
    _git(repo, "add", _STEP10_REL_PATH)
    _git(repo, "commit", "-q", "-m", "seed")

    bumped = '---\ngraded_at: "2026-08-20"\n---\n\nOriginal prose.\n'
    full_path.write_text(bumped, encoding="utf-8")
    _git(repo, "add", _STEP10_REL_PATH)  # stage ONLY the graded_at bump

    if extra_unstaged_edit:
        edited = (
            '---\ngraded_at: "2026-08-20"\n---\n\n'
            "Original prose PLUS a real unstaged edit.\n"
        )
        full_path.write_text(edited, encoding="utf-8")  # unstaged -- working tree only

    return repo


class TestStep10GradedAtReversion:

    def test_full_revert_when_worktree_clean(self, tmp_path):
        """Regression guard: a fully clean graded_at-only staged file (no
        additional unstaged edits) must still be reverted exactly as before
        Track A's fix."""
        repo = _init_step10_fixture(tmp_path, extra_unstaged_edit=False)
        result = _run_extracted_block(
            _step10_block(), [_STEP10_REL_PATH], fixture_repo=repo, pc_audit_no_mutate=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "REVERT " + _STEP10_REL_PATH in result.stdout
        staged = _git(repo, "diff", "--cached", "--name-only").stdout
        assert _STEP10_REL_PATH not in staged
        worktree = (repo / _STEP10_REL_PATH).read_text(encoding="utf-8")
        assert "2026-01-01" in worktree

    def test_partial_stage_preserves_unstaged_edits(self, tmp_path):
        """Track A / Root cause 5: a partially-staged file (graded_at staged,
        real prose edit left unstaged) must survive with its unstaged edit
        completely intact -- the highest real-world-frequency finding of the
        2026-08-20 assessment."""
        repo = _init_step10_fixture(tmp_path, extra_unstaged_edit=True)
        before = (repo / _STEP10_REL_PATH).read_text(encoding="utf-8")

        result = _run_extracted_block(
            _step10_block(), [_STEP10_REL_PATH], fixture_repo=repo, pc_audit_no_mutate=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "UNSTAGE-ONLY " + _STEP10_REL_PATH in result.stdout
        assert "REVERT " + _STEP10_REL_PATH not in result.stdout
        after = (repo / _STEP10_REL_PATH).read_text(encoding="utf-8")
        assert after == before, "the unstaged edit must be byte-for-byte untouched"
        assert "PLUS a real unstaged edit" in after
        staged = _git(repo, "diff", "--cached", "--name-only").stdout
        assert _STEP10_REL_PATH not in staged  # the graded_at bump is still dropped from the commit

    def test_check_only_mode_reports_without_mutating_anything(self, tmp_path):
        """Track B: PC_AUDIT_NO_MUTATE must skip ALL mutation -- not even the
        safe index-only unstage -- and report a FINDING instead."""
        repo = _init_step10_fixture(tmp_path, extra_unstaged_edit=False)
        before = (repo / _STEP10_REL_PATH).read_text(encoding="utf-8")

        result = _run_extracted_block(
            _step10_block(), [_STEP10_REL_PATH], fixture_repo=repo, pc_audit_no_mutate=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "FINDING" in result.stdout
        assert "REVERT " + _STEP10_REL_PATH not in result.stdout
        assert "UNSTAGE-ONLY" not in result.stdout
        after = (repo / _STEP10_REL_PATH).read_text(encoding="utf-8")
        assert after == before
        staged = _git(repo, "diff", "--cached", "--name-only").stdout
        assert _STEP10_REL_PATH in staged  # still staged -- nothing was unstaged either


# ---------------------------------------------------------------------------
# Step 5: content_hash normalization
# ---------------------------------------------------------------------------

_STEP5_REL_PATH = "content/testfamily/en/testplatform/hash-page.md"


def _step5_block() -> str:
    text = _PRECOMMIT_AUDIT_SH.read_text(encoding="utf-8")
    return _extract_bash_block(
        text, '_pc_step_start "content_hash normalization"', '_pc_step_start "last_mechanism staleness"',
    )


def _init_step5_fixture(tmp_path: Path) -> Path:
    """A staged English content file with a provenance block whose
    content_hash does NOT match the body -- the exact trigger condition."""
    repo = tmp_path / "fixture_repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")

    full_path = repo / _STEP5_REL_PATH
    full_path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "---\n"
        "title: Test\n"
        "provenance:\n"
        "  content_hash: deadbeefdeadbeefdeadbeefdeadbeef\n"
        "  last_mechanism: manual\n"
        "---\n\n"
        "Real body text that does not hash to the stored value above.\n"
    )
    full_path.write_text(content, encoding="utf-8")
    _git(repo, "add", _STEP5_REL_PATH)
    _git(repo, "commit", "-q", "-m", "seed with stale content_hash")
    # Re-stage identical content so it is a real staged, tracked ACM entry
    # for `git diff --cached --name-only` to find (matches what `changed`
    # would contain for a genuinely staged English content file).
    _git(repo, "add", _STEP5_REL_PATH)
    return repo


@pytest.mark.skipif(
    not (_REPO_ROOT / ".venv" / "Scripts" / "python.exe").exists()
    and not (_REPO_ROOT / ".venv" / "Scripts" / "python").exists()
    and not (_REPO_ROOT / ".venv" / "bin" / "python").exists(),
    reason="Step 5 resolves .venv relative to this repo's real root",
)
class TestStep5ContentHashNormalization:

    def test_apply_mode_blocks_and_corrects_on_disk(self, tmp_path):
        """Unchanged real-hook behavior: a stale content_hash blocks the
        commit and is corrected on disk for the operator to review."""
        repo = _init_step5_fixture(tmp_path)
        result = _run_extracted_block(
            _step5_block(), [_STEP5_REL_PATH], fixture_repo=repo, pc_audit_no_mutate=False,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "BLOCKED" in result.stdout
        assert "corrected" in result.stdout
        after = (repo / _STEP5_REL_PATH).read_text(encoding="utf-8")
        assert "deadbeefdeadbeefdeadbeefdeadbeef" not in after

    def test_check_only_mode_blocks_without_writing_to_disk(self, tmp_path):
        """Track B / Root cause 4: PC_AUDIT_NO_MUTATE must still block a
        stale content_hash (committing one is exactly what this step exists
        to prevent) but must NEVER write the correction to the real file --
        this is the plain-Python-file-write mutation path a git-verb-based
        static check could never catch."""
        repo = _init_step5_fixture(tmp_path)
        before = (repo / _STEP5_REL_PATH).read_text(encoding="utf-8")

        result = _run_extracted_block(
            _step5_block(), [_STEP5_REL_PATH], fixture_repo=repo, pc_audit_no_mutate=True,
        )

        assert result.returncode == 1, result.stdout + result.stderr
        assert "BLOCKED" in result.stdout
        assert "check-only mode" in result.stdout
        after = (repo / _STEP5_REL_PATH).read_text(encoding="utf-8")
        assert after == before, "the real file must be completely untouched in check-only mode"
        assert "deadbeefdeadbeefdeadbeefdeadbeef" in after
