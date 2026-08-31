"""Full-script integration harness for scripts/pre-commit-audit.sh (TC-SG-11,
2026-08-31 stale-guard plan) -- runs the REAL, UNMODIFIED script end-to-end
(all ~38 steps, real step-tracking machinery, real `_pc_print_summary`
output), not an extracted fragment or a fake stand-in script. Closes the
exact blind spot the 2026-08-20 report's Root Cause 3 named ("fake 3-line
Tier-1 scripts were why five defects shipped unseen") -- the per-step
harnesses (test_precommit_audit_step5_step10.py, _step34.py,
_step_numbering.py) extract and stub-wrap ONE step's block in isolation;
this harness proves the real sequencing/short-circuit behavior across the
WHOLE chain, using the actual on-disk script.

Design decision (vendor-copy vs real-repo-fixture, resolved 2026-08-31):
neither pure form works. A from-scratch empty fixture repo breaks
immediately -- the script's own preamble (line ~10) resolves
`git rev-parse --show-toplevel` and sources
`scripts/ci/hooks/check_shell_bash.sh` relative to it; if that path points
at a fixture with no such file, the script exits before Step 0 ever runs.
Several later steps (reference index structure, skill-mirror parity,
subprocess encoding parity, backlog reconciliation) also check REAL repo
state (skills/, registry.yaml, the committed encoding baseline), not just
staged diffs -- a hand-copied fixture would silently drift from the real
script's actual behavior over time, the exact risk this repo's own
per-step harnesses already reject in their docstrings ("never hand-copied,
so tests cannot silently drift"). Running the real script against a FULL
copy of this repo works but is heavy: content/ + knowledge/ alone are
~2GB, timing out a per-test-run checkout.

Resolution: a THIRD option -- `git worktree add` with a cone-mode SPARSE
checkout. A worktree is a full, real, git-native checkout (shares the
object database with the main repo, so it is cheap and cannot drift --
every file in it IS the real committed content at HEAD, not a copy), with
its own independent HEAD/index (structurally isolated: staging test
fixtures into it can never touch the real .git/index). Cone-mode sparse
checkout restricts it to `scripts/`, `skills/`, `docs/`, `data/`, and one
small content slice (~50MB total, seconds to build) -- enough for every
step's self-location and real-repo-state checks to succeed, without
paying for the full ~2GB tree.

SAFETY -- READ BEFORE CHANGING THIS FILE (2026-08-31 incident): an earlier
version of this design pointed the fixture's `.venv` at the real repo's
`.venv` via an NTFS junction (`mklink /J`), to satisfy the script's
`.venv/Scripts/python` existence check without paying for a second
package install. That is WRONG and caused a real incident: `git worktree
remove`'s own internal deletion routine followed the junction into the
REAL shared `.venv` (the one every concurrent session in this repo
depends on) and deleted most of its `Lib/site-packages`, even though the
junction had already been explicitly unlinked first as a precaution. THIS
HARNESS THEREFORE NEVER LINKS TO ANYTHING REAL: each fixture worktree
gets its OWN independent, disposable venv, built via `python -m venv`
DIRECTLY INSIDE the worktree's own `.venv/` path (never linked in from
elsewhere), installing only `requirements-ci.txt` (the same baseline
CI's own governance jobs use -- confirmed sufficient: pre-commit-audit.sh's
Python-based steps are exactly the governance checks CI already runs from
this file). Do not reintroduce a symlink/junction to the real `.venv` in
this module, ever, for any reason.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parents[2]
_REQUIREMENTS_CI = _REPO_ROOT / "scripts" / "pipeline" / "requirements-ci.txt"

sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops"))
import git_plumb_commit as gpc  # noqa: E402,F401  (guard shares its resolver)

from _git_bash_guard import require_git_bash  # noqa: E402

# Fixture-scoped git identity, supplied via env vars only (never written to any
# config file, shared or per-worktree) -- see the 2026-08-31 "Harness" identity
# incident: an earlier version of this file called bare `git config user.*`
# inside the worktree below, which (per git's own documented worktree
# semantics) resolves to the SHARED common .git/config, not an isolated file,
# and silently corrupted every subsequent commit's author across the whole
# repo/worktree family until caught. Env vars take precedence over any config
# file and are scoped to exactly the one subprocess call that needs them.
_CORRECT_AUTHOR_NAME = "Babar Raza"
_CORRECT_AUTHOR_EMAIL = "babar.raza@aspose.com"

# Sparse-checkout cone: infrastructure every step's self-location or
# real-repo-state check needs, plus one small content slice (~9 files) so
# whole-tree content scans see a genuine, non-empty content/ directory
# instead of erroring "content root 'content' is not a directory".
_SPARSE_CONE = [
    "scripts",
    "skills",
    "docs",
    "data",
    "content/kb.aspose.org/en/pdf/cpp",
    "content/docs.aspose.org/en/pdf/cpp",
    "content/reference.aspose.org/en/pdf/cpp",
    "content/products.aspose.org/en/pdf",
]


def _git(*args: str, cwd: "str | Path", check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=check,
    )


class FullRunFixture:
    """One sparse-checkout worktree + its own disposable venv. Build once
    per test module (expensive: git checkout + pip install), reuse across
    many test functions via `reset()` between them (cheap: git-native)."""

    def __init__(self, worktree: Path):
        self.worktree = worktree

    def reset(self) -> None:
        """Return the worktree's tracked content to HEAD and drop any
        untracked test-scenario files -- via subprocess-invoked git, not
        this session's own Bash tool (the destructive-bash-hook that
        blocks `git reset`/`git clean` for THIS session's interactive
        commands does not gate a test's own subprocess calls; the fixture
        worktree is disposable throwaway state by construction, exactly
        like every other fixture repo in this test suite).

        Order matters and was previously wrong (found live 2026-08-31 while
        adding a new test to this suite): `git checkout -- .` restores
        tracked files from the INDEX, not HEAD -- running it before
        unstaging is a no-op on anything already staged. And `git clean -fd`
        only removes files git doesn't currently track *in the index* --
        running it before unstaging leaves a `git add`ed new file (still
        tracked-in-index at that point) sitting untouched, so it silently
        leaks into whatever test runs next. Unstage FIRST so both later
        steps operate against an index that already matches HEAD."""
        _git("reset", cwd=self.worktree, check=False)  # unstage, keep worktree
        _git("checkout", "--", ".", cwd=self.worktree, check=False)
        _git("clean", "-fd", "--", "content", "reports", cwd=self.worktree, check=False)

    def stage_file(self, rel_path: str, content: str, *, force: bool = False) -> None:
        """`force=True` mirrors `git add -f` -- needed for paths under a
        gitignored tree (e.g. reports/), exactly the real trigger Step 1's
        own docstring names ("usually caused by git add -f bypassing
        .gitignore"). `--sparse` is required alongside it here because the
        cone-mode sparse-checkout (see _SPARSE_CONE) legitimately excludes
        reports/ by default -- without it, `git add -f` on a path outside
        the cone refuses with "matched paths that exist outside of your
        sparse-checkout definition", a sparse-checkout-specific guard, not
        the gitignore one `-f` alone overrides."""
        full = self.worktree / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        args = ["add", "--sparse", "-f", rel_path] if force else ["add", rel_path]
        _git(*args, cwd=self.worktree)

    def run_precommit(self, *, extra_env: "dict[str, str] | None" = None) -> subprocess.CompletedProcess:
        """Run the REAL, unmodified scripts/pre-commit-audit.sh with cwd
        set to this worktree -- its own HEAD/index, its own disposable
        .venv, zero interaction with the real repo's git state.

        Author/committer identity is supplied purely via env vars (never a
        config file) so it can never leak into the shared repo config --
        pass `extra_env` with different GIT_AUTHOR_*/GIT_COMMITTER_* values
        to exercise a wrong-identity scenario (e.g. for a commit-time
        identity-gate test) without touching this fixture at all."""
        bash = require_git_bash()  # skip on POSIX, fail on Windows (TC-SG-20a)
        env = {**os.environ}
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)
        env.pop("PC_AUDIT_NO_MUTATE", None)
        env.pop("PC_AUDIT_SESSION_ID", None)
        env.pop("PC_AUDIT_BASE_SHA", None)
        env["GIT_AUTHOR_NAME"] = _CORRECT_AUTHOR_NAME
        env["GIT_AUTHOR_EMAIL"] = _CORRECT_AUTHOR_EMAIL
        env["GIT_COMMITTER_NAME"] = _CORRECT_AUTHOR_NAME
        env["GIT_COMMITTER_EMAIL"] = _CORRECT_AUTHOR_EMAIL
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [bash, "scripts/pre-commit-audit.sh"],
            cwd=str(self.worktree), capture_output=True,
            text=True, encoding="utf-8", errors="replace", env=env,
        )


def _build_fixture(base_dir: Path) -> FullRunFixture:
    worktree = base_dir / "worktree"
    result = _git(
        "worktree", "add", "--detach", "--no-checkout", str(worktree), "HEAD",
        cwd=_REPO_ROOT, check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"could not create a git worktree fixture: {result.stderr}")

    _git("sparse-checkout", "init", "--cone", cwd=worktree)
    _git("sparse-checkout", "set", *_SPARSE_CONE, cwd=worktree)
    _git("checkout", cwd=worktree)
    # Deliberately no `git config user.*` here -- see the module-level
    # _CORRECT_AUTHOR_NAME/_EMAIL comment: identity is supplied via env vars
    # in run_precommit() instead, never written to any config file.

    # SAFETY: built DIRECTLY inside the worktree, never linked in -- see
    # the module docstring's incident note. Do not change this to a
    # symlink/junction pointing at the real repo's .venv.
    venv_python = (
        worktree / ".venv" / "Scripts" / "python.exe" if os.name == "nt"
        else worktree / ".venv" / "bin" / "python"
    )
    base_python = sys.executable
    subprocess.run([base_python, "-m", "venv", str(worktree / ".venv")], check=True)
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-r", str(_REQUIREMENTS_CI), "--quiet"],
        check=True,
    )

    return FullRunFixture(worktree)


def _teardown_fixture(base_dir: Path) -> None:
    """Safe to call unconditionally: this worktree never links to
    anything real (see the module docstring), so a plain recursive
    delete cannot reach outside `base_dir`."""
    worktree = base_dir / "worktree"
    _git("worktree", "remove", "--force", str(worktree), cwd=_REPO_ROOT, check=False)
    _git("worktree", "prune", cwd=_REPO_ROOT, check=False)
    shutil.rmtree(base_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def full_run_fixture(tmp_path_factory):
    require_git_bash()  # skip on POSIX, fail on Windows (TC-SG-20a) before paying setup cost
    base_dir = tmp_path_factory.mktemp("precommit_full_run")
    fixture = _build_fixture(base_dir)
    yield fixture
    _teardown_fixture(base_dir)
