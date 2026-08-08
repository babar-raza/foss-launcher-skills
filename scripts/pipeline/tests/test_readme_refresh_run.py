"""Round-trip state-machine test for readme_refresh_run.py, against a scratch fixture --
never a real GitHub repo. Per the plan's own requirement: the fixture deliberately includes
one instance of each of the three real incident classes this plan's checks exist to catch
(a dropped real link, an undisclosed BLOCKING command, a hedging/process-narration sentence)
so this test proves the gates actually fire, not just that the happy path completes.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "foss"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import readme_refresh_run as rr  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    rr.configure()


def _run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


_OLD_UPSTREAM_README = """# Test Product

A test product for the round-trip state machine test.

See [AGENTS.md](AGENTS.md) for contributor guidance.

## Installation

```bash
pip install -e .
```
"""

_GOOD_CANDIDATE = """# Test Product

## Navigation

- [At a Glance](#at-a-glance)

## At a Glance

```mermaid
flowchart TD
  PRODUCT["Test Product"]
  subgraph Capabilities["Core Capabilities"]
    C1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    O1["A result"]
  end
  PRODUCT --> Capabilities --> Outputs
```

## Key Capabilities

- Does a thing.

## Installation

A PyPI package has not been published yet. Install from source:

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
import testproduct
```

## API Reference

The primary entry point is `TestClass`.

## Documentation & Resources

See [AGENTS.md](AGENTS.md) for contributor guidance.

- Found a bug? [Open an issue](https://github.com/test-org/test-repo/issues).

## Scope and Limitations

This is a minimal test fixture.

## Development and Testing

```bash
pip install -e ".[dev]"
pytest
```

## License

This project is licensed under the [MIT License](LICENSE).
"""

# Deliberately defective: (1) drops the AGENTS.md link the old upstream README had, (2) repeats
# the exact command upstream-issues.md marks BLOCKING, (3) includes a process-narration smell.
_BAD_CANDIDATE = _GOOD_CANDIDATE.replace(
    "See [AGENTS.md](AGENTS.md) for contributor guidance.\n\n- Found a bug?",
    "- Found a bug?",
).replace(
    'pip install -e ".[dev]"\n```\n\n## Quick Start',
    'pip install -e .\n```\n\nThis was verified against the published package.\n\n## Quick Start',
)
assert _BAD_CANDIDATE != _GOOD_CANDIDATE, "fixture construction must actually apply both replacements"

_UPSTREAM_ISSUES_BLOCKING = """# Upstream issues — testfam/testplat

Verified: 2026-08-06 against https://github.com/test-org/test-repo @ main

## Broken source install

- **Severity**: BLOCKING (install/build/import fails for any user)
- **Evidence**: `pip install -e .`
- **Impact**: every user hits this
- **Not fixable here because**: upstream packaging bug
"""


def _make_scratch_repo(tmp_path):
    """Build a full scratch environment: data files, a real local git repo standing in for
    both the clone cache AND the external push target, and the report tree readme_refresh_run.py
    writes into. Returns (repo_root, upstream_repo_dir)."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    data_dir = repo_root / "data"
    data_dir.mkdir()

    (data_dir / "products.json").write_text(json.dumps([
        {
            "family": "testfam", "platform": "testplat",
            "repo_name": "test-repo", "repo_url": "https://github.com/test-org/test-repo",
            "clone_url": str(tmp_path / "upstream"), "active": True, "discovered_via": "test",
        }
    ]), encoding="utf-8")
    (data_dir / "registry_exclusions.json").write_text("[]", encoding="utf-8")
    (data_dir / "package_registry.json").write_text("{}", encoding="utf-8")
    (data_dir / "diagram_archetypes.json").write_text("[]", encoding="utf-8")
    (data_dir / "diagram_capability_dependencies.json").write_text("[]", encoding="utf-8")

    # Real local git repo standing in for the upstream product repo -- clone_url points here,
    # and it's ALSO what gets mirrored into runs/.clone_cache/ below (a real git clone --local
    # is genuinely exercised in the push step, not mocked).
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()
    (upstream_dir / "README.md").write_text(_OLD_UPSTREAM_README, encoding="utf-8")
    (upstream_dir / "AGENTS.md").write_text("# Contributor guide\n", encoding="utf-8")
    (upstream_dir / "LICENSE").write_text("MIT License\n\nCopyright ...\n", encoding="utf-8")
    _run_git(["init", "-q", "-b", "main"], upstream_dir)
    _run_git(["config", "user.email", "test@example.com"], upstream_dir)
    _run_git(["config", "user.name", "Test"], upstream_dir)
    _run_git(["add", "."], upstream_dir)
    _run_git(["commit", "-q", "-m", "initial"], upstream_dir)

    clone_cache_dir = repo_root / "runs" / ".clone_cache" / "aspose_testfam_testplat"
    clone_cache_dir.parent.mkdir(parents=True)
    _run_git(["clone", "--quiet", str(upstream_dir), str(clone_cache_dir)], tmp_path)

    return repo_root, upstream_dir


def _fake_gh_command_runner(preflight_push=True):
    def _runner(cmd, **kwargs):
        if cmd[0] == "git":
            return subprocess.run(cmd, **kwargs)
        if cmd[:2] == ["gh", "api"]:
            class _Result:
                returncode = 0
                stdout = json.dumps({
                    "permissions": {"push": preflight_push, "admin": False},
                    "default_branch": "main", "archived": False, "disabled": False,
                })
                stderr = ""
            return _Result()
        raise AssertionError(f"unexpected command in test: {cmd}")
    return _runner


def _write_candidate(repo_root, text, upstream_issues=_UPSTREAM_ISSUES_BLOCKING):
    candidate_dir = repo_root / "reports" / "repo-presenter" / "testfam" / "testplat"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "readme.md").write_text(text, encoding="utf-8")
    (candidate_dir / "upstream-issues.md").write_text(upstream_issues, encoding="utf-8")


# --- Full round-trip happy path ---------------------------------------------------------------


def test_full_round_trip_start_through_push_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-001")
    repo_root, upstream_dir = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    assert manifest["state"] == "INPUTS_PINNED"
    run_id = manifest["run_id"]

    manifest = rr.plan_run("testfam", "testplat", run_id)
    assert manifest["state"] == "PLANNED"
    factpack_path = rr._run_root("testfam", "testplat", run_id) / "facts" / "factpack.json"
    assert factpack_path.is_file()
    factpack = json.loads(factpack_path.read_text(encoding="utf-8"))
    assert factpack["archetype"] == "transform"
    assert factpack["license_file"]["relative_path"] == "LICENSE"
    assert "AGENTS.md" in factpack["old_readme_inventory"]["links"]

    _write_candidate(repo_root, _GOOD_CANDIDATE)
    manifest = rr.ingest_candidate("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"

    manifest = rr.verify_examples("testfam", "testplat", run_id)
    assert manifest["state"] == "AWAITING_REVIEW"
    upstream_path = rr._upstream_issues_path("testfam", "testplat")
    assert upstream_path.is_file()  # written for every run, even the clean case

    result = rr.recheck("testfam", "testplat", run_id)
    assert result["required_sections"]["findings"] == []

    manifest = rr.approve("testfam", "testplat", run_id, note="looks good")
    assert manifest["state"] == "APPROVED"

    manifest = rr.push("testfam", "testplat", run_id, dry_run=True)
    # --dry-run rehearses everything up to (not including) the live write, then returns to
    # APPROVED -- it must never reach PUSHED without a real push.
    assert manifest["state"] == "APPROVED"
    receipt_path = rr._run_root("testfam", "testplat", run_id) / "push" / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["dry_run"] is True
    assert receipt["pr_url"] is None
    assert receipt["declared_files"] == ["README.md"]
    # Confirm the disposable clone genuinely happened and produced a real commit (git plumbing
    # actually exercised, not mocked) -- the branch exists in the LOCAL disposable clone with a
    # real README.md change, but --dry-run means it was deliberately never pushed to the
    # upstream remote (the whole point of dry-run is that upstream_dir must NOT see it).
    work_dir = repo_root / "reports" / "readme_refresh_runs" / "_scratch" / f"testfam-testplat-{run_id}"
    assert _run_git(["rev-parse", "--verify", receipt["branch"]], work_dir)
    diff_stat = _run_git(["diff", "--stat", "main", receipt["branch"]], work_dir)
    assert "README.md" in diff_stat
    branches_on_upstream = _run_git(["branch", "-a"], upstream_dir)
    assert receipt["branch"] not in branches_on_upstream


# --- Gate-firing proof: the three real incident classes -----------------------------------


def test_ingest_candidate_blocks_on_all_three_incident_classes(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-002")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    _write_candidate(repo_root, _BAD_CANDIDATE)
    with pytest.raises(rr.ReadmeRefreshRunError, match="hard-gate"):
        rr.ingest_candidate("testfam", "testplat", run_id)

    # Must still be PLANNED -- a failed ingest-candidate must not silently advance.
    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "PLANNED"

    result_path = rr._run_root("testfam", "testplat", run_id) / "checks" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    # 1. Dropped link (AGENTS.md).
    assert "AGENTS.md" in result["dropped_content"]["findings"]
    # 2. Undisclosed BLOCKING command.
    assert any(f["command"] == "pip install -e ." for f in result["no_undisclosed_blocking_commands"]["findings"])
    # 3. Process-narration smell (heuristic, does not block, but must be surfaced for review).
    assert result["process_narration_smells"]["findings"]

    # Fix the two hard-gate issues (restore the link, remove the blocking command) but
    # deliberately LEAVE the hedging sentence -- it's heuristic, so ingest-candidate must
    # still succeed with it present.
    fixed = _GOOD_CANDIDATE.replace(
        "## Quick start", "This was verified against the published package.\n\n## Quick start"
    )
    _write_candidate(repo_root, fixed)
    manifest = rr.ingest_candidate("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"


# --- Illegal transition rejection -----------------------------------------------------------


def test_illegal_transition_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-003")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    assert manifest["state"] == "INPUTS_PINNED"

    # approve() requires AWAITING_REVIEW; calling it straight after start (INPUTS_PINNED) must
    # be rejected by the state machine, not silently succeed.
    with pytest.raises(rr.ReadmeRefreshRunError, match="Illegal"):
        rr._transition(manifest, "APPROVED")


# --- Locking: a second run for the same product while one is active must refuse -----------


def test_second_run_for_same_product_refused_while_active(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-004")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    rr.start_run("testfam", "testplat")
    with pytest.raises(rr.ReadmeRefreshRunError, match="already has active run"):
        rr.start_run("testfam", "testplat")


# --- Pre-flight access check: real refusal on push: false ----------------------------------


def test_preflight_refuses_without_push_access(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-005")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner(preflight_push=False))

    with pytest.raises(rr.ReadmeRefreshRunError, match="No push/admin access"):
        rr.start_run("testfam", "testplat")


# --- BLOCKED -> recover ----------------------------------------------------------------------


def test_blocked_run_recovers_to_resume_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-006")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)

    manifest = rr.status("testfam", "testplat", run_id)
    rr._block(manifest, "simulated failure for recovery test")
    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "BLOCKED"
    assert manifest["resume_state"] == "PLANNED"

    manifest = rr.recover_run("testfam", "testplat", run_id, reason="retrying after simulated failure")
    assert manifest["state"] == "PLANNED"


# --- verify-examples gates on all_named -----------------------------------------------------


def test_verify_examples_refuses_when_not_all_named(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-007")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(
        repo_root=repo_root, command_runner=_fake_gh_command_runner(),
        verification_runner=lambda candidate_path, factpack: {"runner": "incomplete", "all_named": False},
    )

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    rr.ingest_candidate("testfam", "testplat", run_id)

    with pytest.raises(rr.ReadmeRefreshRunError, match="no named status"):
        rr.verify_examples("testfam", "testplat", run_id)

    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"  # must not have advanced


# --- Stale-input-forces-replan at approve ---------------------------------------------------


def test_approve_forces_replan_on_pinned_input_drift(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-008")
    repo_root, upstream_dir = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())

    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    rr.ingest_candidate("testfam", "testplat", run_id)
    rr.verify_examples("testfam", "testplat", run_id)

    # Simulate real drift: the clone cache's HEAD moves after inputs were pinned.
    clone_cache = rr._product_clone_cache("testfam", "testplat")
    (clone_cache / "extra-file.txt").write_text("new content\n", encoding="utf-8")
    _run_git(["add", "."], clone_cache)
    _run_git(["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "-m", "drift"], clone_cache)

    with pytest.raises(rr.ReadmeRefreshRunError, match="drifted"):
        rr.approve("testfam", "testplat", run_id, note="approving despite drift")

    manifest = rr.status("testfam", "testplat", run_id)
    assert manifest["state"] == "PLANNED"  # forced back, never silently approved
