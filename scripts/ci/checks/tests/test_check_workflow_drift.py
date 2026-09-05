"""Tests for check_workflow_drift.py (SEO-WORKFLOW-DRIFT-DETECTION, F10/Finding #64)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_workflow_drift as cwd  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_module_paths():
    yield
    cwd.configure()


def _make_workflows_dir(tmp_path: Path, files: dict[str, str]) -> Path:
    d = tmp_path / "scripts" / "seo" / "workflows"
    d.mkdir(parents=True)
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# classify() -- pure three-way logic
# ---------------------------------------------------------------------------

def test_classify_in_sync_when_all_three_shas_match():
    assert cwd.classify("a", "a", "a") == cwd.IN_SYNC


def test_classify_diverged_when_local_differs_but_deployed_matches_baseline():
    assert cwd.classify("local", "deployed", "deployed") == cwd.DIVERGED


def test_classify_deployed_unapproved_when_deployed_differs_from_baseline():
    assert cwd.classify("a", "b", "a") == cwd.DEPLOYED_UNAPPROVED


def test_classify_deployed_unapproved_takes_priority_over_incidental_local_match():
    # deployed happens to match local today, but not the approved baseline --
    # must still be flagged as the more severe governance issue, not silently IN_SYNC.
    assert cwd.classify("x", "x", "baseline-value") == cwd.DEPLOYED_UNAPPROVED


def test_classify_diverged_when_deployed_unresolved():
    assert cwd.classify("local", None, "baseline") == cwd.DIVERGED
    assert cwd.classify("local", None, None) == cwd.DIVERGED


def test_classify_in_sync_when_no_baseline_yet_but_local_matches_deployed():
    assert cwd.classify("same", "same", None) == cwd.IN_SYNC


# ---------------------------------------------------------------------------
# sha256_text
# ---------------------------------------------------------------------------

def test_sha256_text_is_deterministic_and_content_sensitive():
    assert cwd.sha256_text("hello") == cwd.sha256_text("hello")
    assert cwd.sha256_text("hello") != cwd.sha256_text("hello ")


# ---------------------------------------------------------------------------
# check_workflow_drift -- end to end over a fake fetch_fn (never shells to gh)
# ---------------------------------------------------------------------------

def test_seeds_baseline_from_deployed_on_first_run_and_reports_in_sync(tmp_path):
    wf_dir = _make_workflows_dir(tmp_path, {"a.yml": "content-A\n"})
    cwd.configure(repo_root=tmp_path)

    outcome = cwd.check_workflow_drift(
        workflows_dir=wf_dir,
        fetch_fn=lambda path: "content-A\n",
    )

    assert outcome["results"]["a.yml"]["status"] == cwd.IN_SYNC
    baseline_entry = outcome["baselines"]["a.yml"]
    assert baseline_entry["approved_baseline_sha256"] == cwd.sha256_text("content-A\n")
    assert baseline_entry["baseline_source"] == "seeded_from_deployed"
    assert baseline_entry["deployed_path"] == ".github/workflows/a.yml"


def test_seeds_baseline_from_deployed_then_reports_diverged_when_local_differs(tmp_path):
    wf_dir = _make_workflows_dir(tmp_path, {"a.yml": "local-version\n"})
    cwd.configure(repo_root=tmp_path)

    outcome = cwd.check_workflow_drift(
        workflows_dir=wf_dir,
        fetch_fn=lambda path: "deployed-version\n",
    )

    assert outcome["results"]["a.yml"]["status"] == cwd.DIVERGED
    # the freshly-seeded baseline adopts the deployed content, not local
    assert outcome["baselines"]["a.yml"]["approved_baseline_sha256"] == cwd.sha256_text("deployed-version\n")


def test_real_finding_shape_local_template_stale_relative_to_deployed(tmp_path):
    """Regression pin for the real drift this check's first live run found:
    scripts/seo/workflows/seo-keyword-refresh.yml (local, tracked) predates
    the 2026-08-26 REPO_TOKEN-primary fix already live in
    Aspose/aspose.org-workflows -- local == neither empty nor equal to
    deployed, and no baseline existed yet."""
    local_text = "# old copy, GH_TOKEN only\n"
    deployed_text = "# patched copy, REPO_TOKEN primary\n"
    wf_dir = _make_workflows_dir(tmp_path, {"seo-keyword-refresh.yml": local_text})
    cwd.configure(repo_root=tmp_path)

    outcome = cwd.check_workflow_drift(workflows_dir=wf_dir, fetch_fn=lambda path: deployed_text)

    assert outcome["results"]["seo-keyword-refresh.yml"]["status"] == cwd.DIVERGED


def test_deployed_unapproved_when_baseline_already_recorded_and_deployed_moved(tmp_path):
    wf_dir = _make_workflows_dir(tmp_path, {"a.yml": "template\n"})
    cwd.configure(repo_root=tmp_path)
    cwd.save_baselines({
        "a.yml": {
            "deployed_repo": cwd.DEPLOYED_REPO,
            "deployed_path": ".github/workflows/a.yml",
            "approved_baseline_sha256": cwd.sha256_text("template\n"),
            "baseline_source": "seeded_from_deployed",
            "baseline_recorded_at": "2026-01-01T00:00:00Z",
        }
    })

    outcome = cwd.check_workflow_drift(
        workflows_dir=wf_dir,
        fetch_fn=lambda path: "someone edited this directly in the other repo\n",
    )

    assert outcome["results"]["a.yml"]["status"] == cwd.DEPLOYED_UNAPPROVED
    # the recorded baseline itself is not silently overwritten by the unapproved change
    assert outcome["baselines"]["a.yml"]["approved_baseline_sha256"] == cwd.sha256_text("template\n")


def test_seed_missing_baselines_false_never_writes_a_baseline_entry(tmp_path):
    wf_dir = _make_workflows_dir(tmp_path, {"a.yml": "content\n"})
    cwd.configure(repo_root=tmp_path)

    outcome = cwd.check_workflow_drift(
        workflows_dir=wf_dir,
        fetch_fn=lambda path: "content\n",
        seed_missing_baselines=False,
    )

    assert "a.yml" not in outcome["baselines"]
    # no baseline recorded -> local==deployed is still reportable as IN_SYNC
    assert outcome["results"]["a.yml"]["status"] == cwd.IN_SYNC


def test_deployed_fetch_failure_is_never_reported_as_in_sync(tmp_path):
    wf_dir = _make_workflows_dir(tmp_path, {"a.yml": "content\n"})
    cwd.configure(repo_root=tmp_path)

    outcome = cwd.check_workflow_drift(workflows_dir=wf_dir, fetch_fn=lambda path: None)

    assert outcome["results"]["a.yml"]["status"] == cwd.DIVERGED
    assert outcome["results"]["a.yml"]["deployed_sha256"] is None
    assert "a.yml" not in outcome["baselines"]


def test_multiple_workflows_classified_independently(tmp_path):
    wf_dir = _make_workflows_dir(tmp_path, {
        "in-sync.yml": "same\n",
        "diverged.yml": "local\n",
    })
    cwd.configure(repo_root=tmp_path)
    deployed = {"in-sync.yml": "same\n", "diverged.yml": "different\n"}

    outcome = cwd.check_workflow_drift(workflows_dir=wf_dir, fetch_fn=lambda path: deployed[Path(path).name])

    assert outcome["results"]["in-sync.yml"]["status"] == cwd.IN_SYNC
    assert outcome["results"]["diverged.yml"]["status"] == cwd.DIVERGED


# ---------------------------------------------------------------------------
# load_baselines / save_baselines
# ---------------------------------------------------------------------------

def test_load_baselines_returns_empty_dict_when_file_absent(tmp_path):
    cwd.configure(repo_root=tmp_path)
    assert cwd.load_baselines() == {}


def test_load_baselines_returns_empty_dict_on_corrupt_json(tmp_path):
    cwd.configure(repo_root=tmp_path)
    cwd.BASELINES_PATH.parent.mkdir(parents=True, exist_ok=True)
    cwd.BASELINES_PATH.write_text("{not valid json", encoding="utf-8")
    assert cwd.load_baselines() == {}


def test_save_then_load_baselines_roundtrips(tmp_path):
    cwd.configure(repo_root=tmp_path)
    data = {"a.yml": {"approved_baseline_sha256": "deadbeef"}}
    cwd.save_baselines(data)
    assert cwd.load_baselines() == data
    on_disk = json.loads(cwd.BASELINES_PATH.read_text(encoding="utf-8"))
    assert on_disk == data


# ---------------------------------------------------------------------------
# fetch_deployed_content -- injected runner, never shells to real gh
# ---------------------------------------------------------------------------

class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str):
        self.returncode = returncode
        self.stdout = stdout


def test_fetch_deployed_content_decodes_base64_from_gh_api():
    import base64

    encoded = base64.b64encode(b"file contents\n").decode("ascii")

    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(0, encoded)

    result = cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner)
    assert result == "file contents\n"


def test_fetch_deployed_content_returns_none_on_nonzero_exit():
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(1, "")

    assert cwd.fetch_deployed_content(".github/workflows/missing.yml", runner=fake_runner) is None


def test_fetch_deployed_content_returns_none_on_timeout():
    import subprocess as sp

    def fake_runner(*args, **kwargs):
        raise sp.TimeoutExpired(cmd="gh", timeout=30)

    assert cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner) is None


def test_fetch_deployed_content_returns_none_when_gh_not_installed():
    def fake_runner(*args, **kwargs):
        raise FileNotFoundError("gh")

    assert cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner) is None


def test_fetch_deployed_content_returns_none_on_invalid_base64():
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(0, "not-valid-base64!!!")

    assert cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner) is None


# ---------------------------------------------------------------------------
# main() -- exit codes
# ---------------------------------------------------------------------------

def test_main_returns_2_when_workflows_dir_missing(tmp_path, monkeypatch):
    cwd.configure(repo_root=tmp_path)
    assert cwd.main([]) == 2


def test_main_returns_2_when_gh_not_authenticated(tmp_path, monkeypatch):
    _make_workflows_dir(tmp_path, {"a.yml": "content\n"})
    cwd.configure(repo_root=tmp_path)

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(1, "")

    monkeypatch.setattr(cwd.subprocess, "run", fake_run)
    assert cwd.main([]) == 2
