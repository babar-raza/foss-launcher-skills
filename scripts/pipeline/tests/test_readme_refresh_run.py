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

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

![Test Product](https://products.aspose.org/media/testfam/testplat/banner-readme.png)

## Navigation

- [At a Glance](#at-a-glance)

## At a Glance

```mermaid
flowchart TD
  subgraph StartingPoints["Starting Points"]
    I1["An existing TXT file"]
  end
  PRODUCT["Test Product"]
  subgraph Capabilities["Core Capabilities"]
    C1["Does a thing"]
  end
  subgraph Outputs["Outputs"]
    O1["TXT files"]
  end
  StartingPoints --> PRODUCT --> Capabilities --> Outputs
```

## Key Capabilities

- Reads and writes TXT files.

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

- This is a minimal test fixture with a single limitation.

This limitation does not apply to [Test Product — Enterprise Edition](https://products.aspose.com/testfam/testplat/), which adds full production support.

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
    # MT025 (Eleventh incident): a real format vocabulary is needed for the fixture's Starting
    # Points/Outputs nodes to pass check_diagram_format_support_claims and the new
    # check_diagram_container_format_purity hard gates.
    (data_dir / "format_descriptions.json").write_text(json.dumps({"TXT": {}}), encoding="utf-8")
    knowledge_dir = repo_root / "knowledge" / "testfam" / "testplat" / "merged"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "formats.md").write_text(
        "# Format Support\n\n| Format | Import | Export |\n|--------|--------|--------|\n"
        "| TXT | Yes | Yes |\n",
        encoding="utf-8",
    )

    # Real local git repo standing in for the upstream product repo -- clone_url points here,
    # and it's ALSO what gets mirrored into runs/.clone_cache/ below (a real git clone --local
    # is genuinely exercised in the push step, not mocked).
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()
    (upstream_dir / "README.md").write_text(_OLD_UPSTREAM_README, encoding="utf-8")
    (upstream_dir / "AGENTS.md").write_text("# Contributor guide\n", encoding="utf-8")
    (upstream_dir / "LICENSE").write_text("MIT License\n\nCopyright ...\n", encoding="utf-8")
    # MT027: a real source declaration so check_api_reference_classes_exist_in_reference_site's
    # clone-cache fallback (and check_named_member_accuracy) can confirm `TestClass` is real --
    # there is no reference.aspose.org fixture for "testfam/testplat", so this is the only source.
    (upstream_dir / "test_class.py").write_text("class TestClass:\n    pass\n", encoding="utf-8")
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


# Fifteenth incident / MT030 (2026-08-09): a real, correct disposition for both of
# _OLD_UPSTREAM_README's 2 real content units (confirmed via extract_old_readme_content_units
# itself, not guessed) -- u0001 ("A test product for the round-trip state machine test.") is
# generic scene-setting narrative with nothing to verify (category 1); u0002 ("See AGENTS.md...")
# is already present verbatim in _GOOD_CANDIDATE's own Documentation & Resources section, so it's
# a real, checkable redundant-merge case, not a fresh composition. Written by _write_candidate
# below for every existing call site by default -- a test wanting to exercise a MISSING/empty
# disposition file passes dispositions=None/[] explicitly.
_CONTENT_DISPOSITIONS_FOR_SHARED_FIXTURE = [
    {
        "unit_id": "u0001",
        "source": "clone_cache/README.md",
        "excerpt": "A test product for the round-trip state machine test.",
        "salient_tokens": [],
        "classification": "1_narrative_cta",
        "classification_basis": "generic scene-setting sentence, no checkable claim",
        "verification": {"status": "not_applicable_category_1", "evidence_type": None, "evidence_ref": None},
        "disposition": "excluded",
        "target_section": None,
        "excluded_reason": "generic scene-setting narrative, superseded by the new template's own composed intro paragraph",
    },
    {
        "unit_id": "u0002",
        "source": "clone_cache/README.md",
        "excerpt": "See [AGENTS.md](AGENTS.md) for contributor guidance.",
        "salient_tokens": ["AGENTS"],
        "classification": "redundant_with_existing",
        "classification_basis": "already present verbatim in the new candidate's Documentation & Resources section",
        "verification": {
            "status": "verified_redundant",
            "evidence_type": "candidate_section_reference",
            "evidence_ref": "Documentation & Resources",
        },
        "disposition": "merged_verbatim",
        "target_section": "Documentation & Resources",
        "excluded_reason": None,
    },
]


def _write_candidate(
    repo_root, text, upstream_issues=_UPSTREAM_ISSUES_BLOCKING,
    dispositions=_CONTENT_DISPOSITIONS_FOR_SHARED_FIXTURE,
):
    candidate_dir = repo_root / "reports" / "repo-presenter" / "testfam" / "testplat"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / "readme.md").write_text(text, encoding="utf-8")
    (candidate_dir / "upstream-issues.md").write_text(upstream_issues, encoding="utf-8")
    if dispositions is not None:
        (candidate_dir / "content-dispositions.json").write_text(
            json.dumps(dispositions), encoding="utf-8"
        )


# --- _detect_dev_test_artifacts (MT029 Item 5) -------------------------------------------------


def test_detect_dev_test_artifacts_finds_real_agents_md(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Contributor guide\n", encoding="utf-8")
    detected = rr._detect_dev_test_artifacts(tmp_path)
    assert detected == [{
        "relative_path": "AGENTS.md", "kind": "agents_guide", "section": "Documentation & Resources",
    }]


def test_detect_dev_test_artifacts_no_windows_case_alias_double_count(tmp_path):
    # Regression test: found live (2026-08-09) on this Windows machine -- AGENTS.md and
    # agents.md both resolve to the same real file on a case-insensitive filesystem, so a
    # naive per-candidate is_file() check registered it twice under two different casings.
    (tmp_path / "AGENTS.md").write_text("# Contributor guide\n", encoding="utf-8")
    detected = rr._detect_dev_test_artifacts(tmp_path)
    assert len(detected) == 1


def test_detect_dev_test_artifacts_finds_third_casing_variant(tmp_path):
    # Regression test: found live during the Phase 2 portfolio rollout (2026-08-09,
    # cells/java) -- the real file is cased "Agents.md", a third variant neither of the two
    # literal candidates ("AGENTS.md"/"agents.md") string-equals, so `_add`'s own case-
    # sensitive on-disk-name verification silently rejected both lookups even though the file
    # genuinely exists. A case-insensitive directory scan finds it under any casing.
    (tmp_path / "Agents.md").write_text("# Contributor guide\n", encoding="utf-8")
    detected = rr._detect_dev_test_artifacts(tmp_path)
    assert detected == [{
        "relative_path": "Agents.md", "kind": "agents_guide", "section": "Documentation & Resources",
    }]


def test_detect_dev_test_artifacts_excludes_dotdir_pytest_cache(tmp_path):
    # Regression test: found live (2026-08-09, html/python) -- pytest itself writes a
    # boilerplate README.md into `.pytest_cache/` on every test run; "test" is a substring
    # of "pytest_cache", so the original `"test" in name.lower()` check wrongly matched it.
    cache_dir = tmp_path / ".pytest_cache"
    cache_dir.mkdir()
    (cache_dir / "README.md").write_text("This directory is for pytest's cache.\n", encoding="utf-8")
    assert rr._detect_dev_test_artifacts(tmp_path) == []


def test_detect_dev_test_artifacts_still_finds_real_test_dir_readme(tmp_path):
    # Regression guard: excluding dot-directories must never exclude a real, non-dot test
    # directory's own README.md too.
    tests_dir = tmp_path / "Aspose.Cells.Foss.Cpp.Tests"
    tests_dir.mkdir()
    (tests_dir / "README.md").write_text("# Test suite\n", encoding="utf-8")
    detected = rr._detect_dev_test_artifacts(tmp_path)
    assert any(a["relative_path"] == "Aspose.Cells.Foss.Cpp.Tests/README.md" for a in detected)


def test_detect_dev_test_artifacts_empty_for_bare_repo(tmp_path):
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    assert rr._detect_dev_test_artifacts(tmp_path) == []


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


# --- TC-HARDEN-12 (MT033): change-isolation gates wired into recheck() ---------------------
#
# check_only_mermaid_block_changed / check_only_sections_changed were real, fully-tested hard
# gates (this plan's own MT024/MT029 idempotency guarantee) that readme_refresh_run.py never
# called -- confirmed by exact-name grep, zero hits, before this fix. These tests prove the
# WIRING actually triggers the gate at the real recheck() transition against a real
# deliberately-cross-contaminated edit, not merely that the underlying functions work in
# isolation (already proven by their own dedicated tests in test_readme_refresh_checks.py).


def _ingest_good_candidate(repo_root, family="testfam", platform="testplat"):
    """Shared setup for the change-isolation tests below: start a run, plan it, ingest the
    shared _GOOD_CANDIDATE fixture -- this is what writes checkpoint 0 (the snapshot every
    recheck() change-isolation check diffs the next edit against)."""
    manifest = rr.start_run(family, platform)
    run_id = manifest["run_id"]
    rr.plan_run(family, platform, run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)
    manifest = rr.ingest_candidate(family, platform, run_id)
    assert manifest["state"] == "VERIFYING_EXAMPLES"
    return run_id


def test_recheck_change_isolation_skipped_when_not_requested(tmp_path, monkeypatch):
    # Backward-compat proof: omitting both allowed_headings and mermaid_only (every existing
    # caller, including the round-trip test above) must produce identical behavior to before
    # this change -- no new result.json keys, no crash, no snapshot-dependency at all.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-a")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    result = rr.recheck("testfam", "testplat", run_id)
    assert "change_isolation_mermaid" not in result
    assert "change_isolation_sections" not in result


def test_recheck_change_isolation_skipped_without_prior_snapshot(tmp_path, monkeypatch):
    # A caller can request change-isolation checking even when nothing has ever been ingested
    # yet (e.g. a stray recheck right after plan_run, before ingest_candidate) -- must degrade
    # gracefully (no snapshot to diff against), never crash on a missing file.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-b")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    manifest = rr.start_run("testfam", "testplat")
    run_id = manifest["run_id"]
    rr.plan_run("testfam", "testplat", run_id)
    _write_candidate(repo_root, _GOOD_CANDIDATE)

    result = rr.recheck(
        "testfam", "testplat", run_id, allowed_headings=["Key Capabilities"], mermaid_only=True,
    )
    assert "change_isolation_mermaid" not in result
    assert "change_isolation_sections" not in result


def test_recheck_mermaid_only_fires_on_real_cross_section_contamination(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-c")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    # A real cross-contamination shape: the diagram edit leaks into Key Capabilities too --
    # exactly the class of defect this plan's own MT024 "email/net snapshot contamination"
    # incident (2026-08-05) found live, the incident that originally motivated this gate.
    contaminated = _GOOD_CANDIDATE.replace(
        'C1["Does a thing"]', 'C1["Does a thing well"]',
    ).replace(
        "- Reads and writes TXT files.", "- Reads and writes TXT and CSV files.",
    )
    assert contaminated != _GOOD_CANDIDATE
    _write_candidate(repo_root, contaminated)

    result = rr.recheck("testfam", "testplat", run_id, mermaid_only=True)
    assert result["change_isolation_mermaid"]["hard_gate"] is True
    assert result["change_isolation_mermaid"]["findings"], (
        "mermaid-only claim must be rejected -- Key Capabilities changed too"
    )


def test_recheck_mermaid_only_clean_on_legitimate_diagram_only_edit(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-d")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    diagram_only_edit = _GOOD_CANDIDATE.replace(
        'C1["Does a thing"]', 'C1["Does a thing well"]',
    )
    assert diagram_only_edit != _GOOD_CANDIDATE
    _write_candidate(repo_root, diagram_only_edit)

    result = rr.recheck("testfam", "testplat", run_id, mermaid_only=True)
    assert result["change_isolation_mermaid"]["findings"] == []


def test_recheck_sections_fires_on_undeclared_section_change(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-e")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    # Caller declares this edit is scoped to Key Capabilities only, but Installation changed
    # too -- the exact undeclared-scope shape this gate exists to catch.
    contaminated = _GOOD_CANDIDATE.replace(
        "- Reads and writes TXT files.", "- Reads and writes TXT and CSV files.",
    ).replace(
        'pip install -e ".[dev]"\n```\n\n## Quick Start',
        'pip install -e ".[dev,extra]"\n```\n\n## Quick Start',
    )
    assert contaminated != _GOOD_CANDIDATE
    _write_candidate(repo_root, contaminated)

    result = rr.recheck("testfam", "testplat", run_id, allowed_headings=["Key Capabilities"])
    findings = result["change_isolation_sections"]["findings"]
    assert result["change_isolation_sections"]["hard_gate"] is True
    assert any(f["heading"] == "Installation" for f in findings)
    assert not any(f["heading"] == "Key Capabilities" for f in findings)


def test_recheck_sections_clean_on_legitimate_single_section_edit(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-f")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    single_section_edit = _GOOD_CANDIDATE.replace(
        "- Reads and writes TXT files.", "- Reads and writes TXT and CSV files.",
    )
    assert single_section_edit != _GOOD_CANDIDATE
    _write_candidate(repo_root, single_section_edit)

    result = rr.recheck("testfam", "testplat", run_id, allowed_headings=["Key Capabilities"])
    assert result["change_isolation_sections"]["findings"] == []


def test_recheck_snapshot_rolls_forward_between_calls(tmp_path, monkeypatch):
    # The snapshot is a ROLLING checkpoint (updated after every recheck), not a fixed baseline
    # frozen at first ingest -- a second, independent edit must be diffed against the first
    # edit's own result, not re-flagged against the original candidate.
    monkeypatch.setenv("AGENT_SESSION_ID", "test-session-h12-g")
    repo_root, _ = _make_scratch_repo(tmp_path)
    rr.configure(repo_root=repo_root, command_runner=_fake_gh_command_runner())
    run_id = _ingest_good_candidate(repo_root)

    first_edit = _GOOD_CANDIDATE.replace(
        "- Reads and writes TXT files.", "- Reads and writes TXT and CSV files.",
    )
    _write_candidate(repo_root, first_edit)
    result = rr.recheck("testfam", "testplat", run_id, allowed_headings=["Key Capabilities"])
    assert result["change_isolation_sections"]["findings"] == []

    # Second, independent Key-Capabilities-only edit on top of the first -- must still pass,
    # proving the snapshot advanced to first_edit rather than staying pinned to _GOOD_CANDIDATE.
    second_edit = first_edit.replace(
        "- Reads and writes TXT and CSV files.", "- Reads and writes TXT, CSV, and JSON files.",
    )
    assert second_edit != first_edit
    _write_candidate(repo_root, second_edit)
    result = rr.recheck("testfam", "testplat", run_id, allowed_headings=["Key Capabilities"])
    assert result["change_isolation_sections"]["findings"] == []


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
