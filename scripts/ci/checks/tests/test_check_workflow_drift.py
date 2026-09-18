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


# MT069 HC-09 (2026-09-18): the contract changed on purpose. Before, EVERY failure
# returned None and check_workflow_drift() reported it as DIVERGED -- so one
# `net/http: TLS handshake timeout` (seen live the same day) looked like real
# drift. Now: None means "definitely not there" (404); anything else that fails
# is retried and, if it keeps failing, raises TransientFetchError -> UNRESOLVED.
# sleep_fn is injected everywhere so the retry backoff never really sleeps.

_NO_SLEEP = lambda seconds: None  # noqa: E731

_404_ON_STDOUT = '{"message":"Not Found","documentation_url":"https://docs.github.com/rest","status":"404"}'


def test_fetch_definite_404_returns_none_and_is_not_retried():
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append(1)
        return _FakeCompletedProcess(1, _404_ON_STDOUT)  # gh api --jq puts the 404 body on STDOUT

    assert cwd.fetch_deployed_content(".github/workflows/missing.yml", runner=fake_runner, sleep_fn=_NO_SLEEP) is None
    assert len(calls) == 1


def test_fetch_nonzero_exit_without_404_is_retried_then_raises_transient():
    calls, sleeps = [], []

    def fake_runner(*args, **kwargs):
        calls.append(1)
        return _FakeCompletedProcess(1, "")

    with pytest.raises(cwd.TransientFetchError):
        cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner, sleep_fn=sleeps.append)
    assert len(calls) == 3
    assert sleeps == [2.0, 5.0]  # backoff between attempts, none after the last


def test_fetch_recovers_when_a_retry_succeeds():
    import base64

    encoded = base64.b64encode(b"ok\n").decode("ascii")
    outcomes = [_FakeCompletedProcess(1, ""), _FakeCompletedProcess(1, ""), _FakeCompletedProcess(0, encoded)]

    def fake_runner(*args, **kwargs):
        return outcomes.pop(0)

    assert cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner, sleep_fn=_NO_SLEEP) == "ok\n"


def test_fetch_timeout_is_transient():
    import subprocess as sp

    calls = []

    def fake_runner(*args, **kwargs):
        calls.append(1)
        raise sp.TimeoutExpired(cmd="gh", timeout=30)

    with pytest.raises(cwd.TransientFetchError):
        cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner, sleep_fn=_NO_SLEEP)
    assert len(calls) == 3


def test_fetch_gh_not_installed_raises_immediately_without_retrying():
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append(1)
        raise FileNotFoundError("gh")

    with pytest.raises(cwd.TransientFetchError):
        cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner, sleep_fn=_NO_SLEEP)
    assert len(calls) == 1  # a missing binary is configuration, not a blip


def test_fetch_invalid_base64_is_transient():
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(0, "not-valid-base64!!!")

    with pytest.raises(cwd.TransientFetchError):
        cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner, sleep_fn=_NO_SLEEP)


def test_fetch_empty_body_is_transient():
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(0, "   ")

    with pytest.raises(cwd.TransientFetchError):
        cwd.fetch_deployed_content(".github/workflows/a.yml", runner=fake_runner, sleep_fn=_NO_SLEEP)


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


# ---------------------------------------------------------------------------
# MT069 HC-09 -- UNRESOLVED, approve verb, exit codes, forced-red control.
# All through DI seams (fetch_fn / gh_auth_ok_fn / drift_fn), no monkeypatching.
# ---------------------------------------------------------------------------

def _drift_with(fetch):
    """A drift_fn for main() that uses a fake deployed-side fetch."""
    return lambda seed_missing_baselines: cwd.check_workflow_drift(
        fetch_fn=fetch, seed_missing_baselines=seed_missing_baselines)


def _blows_up(_path):
    raise cwd.TransientFetchError("net/http: TLS handshake timeout (after 3 attempt(s))")


def test_transient_fetch_failure_is_unresolved_not_diverged_and_never_seeds(tmp_path):
    _make_workflows_dir(tmp_path, {"a.yml": "content\n"})
    cwd.configure(repo_root=tmp_path)
    out = cwd.check_workflow_drift(fetch_fn=_blows_up, seed_missing_baselines=True)
    r = out["results"]["a.yml"]
    assert r["status"] == cwd.UNRESOLVED
    assert r["deployed_sha256"] is None and "TLS handshake" in r["unresolved_reason"]
    assert "a.yml" not in out["baselines"]  # a blind spot must never become the trusted baseline


def test_a_definite_missing_deployed_file_is_still_diverged(tmp_path):
    _make_workflows_dir(tmp_path, {"a.yml": "content\n"})
    cwd.configure(repo_root=tmp_path)
    out = cwd.check_workflow_drift(fetch_fn=lambda p: None, seed_missing_baselines=False)
    assert out["results"]["a.yml"]["status"] == cwd.DIVERGED


def _res(status, local="L", deployed="D", baseline="B", **extra):
    return {"status": status, "local_sha256": local, "deployed_sha256": deployed,
            "approved_baseline_sha256": baseline, **extra}


def test_approve_refuses_when_deployed_differs_from_the_reviewed_local_template():
    # deployed moved past its baseline AND differs from local: that is an unreviewed live change
    baselines = {"a.yml": {"approved_baseline_sha256": "OLD"}}
    ok, msg = cwd.approve_baseline("a.yml", "looked fine", {"a.yml": _res(cwd.DEPLOYED_UNAPPROVED, "L", "D", "OLD")}, baselines)
    assert not ok and "unreviewed live change" in msg
    assert baselines["a.yml"]["approved_baseline_sha256"] == "OLD"  # untouched


def test_approve_accepts_the_real_2026_09_18_shape_and_records_the_reason():
    # the exact state HC-08 met: deployed == local, both != the old baseline
    baselines = {"upstream-monitor.yml": {"approved_baseline_sha256": "87fd14f9", "deployed_repo": "X/Y",
                                           "deployed_path": ".github/workflows/upstream-monitor.yml"}}
    results = {"upstream-monitor.yml": _res(cwd.DEPLOYED_UNAPPROVED, "ca31bef3", "ca31bef3", "87fd14f9")}
    ok, msg = cwd.approve_baseline("upstream-monitor.yml", "comments and message strings only", results, baselines)
    e = baselines["upstream-monitor.yml"]
    assert ok and "87fd14f9" in msg
    assert e["approved_baseline_sha256"] == "ca31bef3"
    assert e["baseline_source"] == "approved_after_review: comments and message strings only"
    assert e["deployed_repo"] == "X/Y" and e["baseline_recorded_at"].endswith("Z")


@pytest.mark.parametrize("status,needle", [
    (cwd.DIVERGED, "Deploy the local template first"),
    (cwd.UNRESOLVED, "cannot approve what could not be read"),
])
def test_approve_refuses_diverged_and_unresolved(status, needle):
    ok, msg = cwd.approve_baseline("a.yml", "why", {"a.yml": _res(status, unresolved_reason="blip")}, {})
    assert not ok and needle in msg


def test_approve_requires_a_reason_and_a_known_name_and_is_a_noop_when_in_sync():
    r = {"a.yml": _res(cwd.IN_SYNC, "S", "S", "S")}
    assert not cwd.approve_baseline("a.yml", "  ", r, {})[0]
    assert "not a known template" in cwd.approve_baseline("nope.yml", "why", r, {})[1]
    ok, msg = cwd.approve_baseline("a.yml", "why", r, b := {})
    assert ok and "nothing to approve" in msg and b == {}


def test_main_exit_codes_in_sync_drift_and_unresolved(tmp_path, capsys):
    _make_workflows_dir(tmp_path, {"a.yml": "content\n"})
    cwd.configure(repo_root=tmp_path)
    cwd.save_baselines({"a.yml": {"approved_baseline_sha256": cwd.sha256_text("content\n")}})
    ok = lambda: True  # noqa: E731

    assert cwd.main(["--no-seed"], gh_auth_ok_fn=ok, drift_fn=_drift_with(lambda p: "content\n")) == 0
    assert cwd.main(["--no-seed"], gh_auth_ok_fn=ok, drift_fn=_drift_with(lambda p: "changed live\n")) == 1  # DEPLOYED_UNAPPROVED
    assert cwd.main(["--no-seed"], gh_auth_ok_fn=ok, drift_fn=_drift_with(_blows_up)) == 3
    assert "could not be checked" in capsys.readouterr().out


def test_real_drift_outranks_unresolved_in_the_exit_code(tmp_path):
    _make_workflows_dir(tmp_path, {"a.yml": "content\n", "b.yml": "b\n"})
    cwd.configure(repo_root=tmp_path)
    cwd.save_baselines({"a.yml": {"approved_baseline_sha256": cwd.sha256_text("content\n")},
                        "b.yml": {"approved_baseline_sha256": cwd.sha256_text("b\n")}})

    def fetch(path):
        if path.endswith("a.yml"):
            return "moved\n"
        raise cwd.TransientFetchError("blip")

    assert cwd.main(["--no-seed"], gh_auth_ok_fn=lambda: True, drift_fn=_drift_with(fetch)) == 1


def test_forced_red_control_against_a_scratch_baseline_never_touches_the_real_one(tmp_path):
    # Live-control mechanism: --baselines points at a scratch file whose hash is deliberately wrong.
    _make_workflows_dir(tmp_path, {"a.yml": "content\n"})
    cwd.configure(repo_root=tmp_path)
    real = tmp_path / "data" / "workflow_deploy_baselines.json"
    cwd.save_baselines({"a.yml": {"approved_baseline_sha256": cwd.sha256_text("content\n")}})
    before = real.read_text(encoding="utf-8")
    scratch = tmp_path / "scratch_baselines.json"
    scratch.write_text('{"a.yml": {"approved_baseline_sha256": "deadbeef"}}', encoding="utf-8")

    rc = cwd.main(["--baselines", str(scratch)], gh_auth_ok_fn=lambda: True,
                  drift_fn=_drift_with(lambda p: "content\n"))
    assert rc == 1                                            # red: deployed != scratch baseline
    assert real.read_text(encoding="utf-8") == before        # the real baseline was never read-modified
    assert scratch.read_text(encoding="utf-8") == '{"a.yml": {"approved_baseline_sha256": "deadbeef"}}'  # and never seeded


def test_main_approve_success_writes_and_refusal_exits_4(tmp_path, capsys):
    _make_workflows_dir(tmp_path, {"a.yml": "new\n"})
    cwd.configure(repo_root=tmp_path)
    cwd.save_baselines({"a.yml": {"approved_baseline_sha256": "old"}})
    ok = lambda: True  # noqa: E731

    assert cwd.main(["--approve", "a.yml", "--reason", "reviewed"], gh_auth_ok_fn=ok,
                    drift_fn=_drift_with(lambda p: "different live\n")) == 4          # deployed != local: refuse
    assert cwd.load_baselines()["a.yml"]["approved_baseline_sha256"] == "old"

    assert cwd.main(["--approve", "a.yml", "--reason", "reviewed"], gh_auth_ok_fn=ok,
                    drift_fn=_drift_with(lambda p: "new\n")) == 0                    # deployed == local: approve
    assert cwd.load_baselines()["a.yml"]["approved_baseline_sha256"] == cwd.sha256_text("new\n")
    assert "APPROVED" in capsys.readouterr().out


def test_approve_without_a_reason_is_a_usage_error(tmp_path):
    _make_workflows_dir(tmp_path, {"a.yml": "x\n"})
    cwd.configure(repo_root=tmp_path)
    with pytest.raises(SystemExit) as e:
        cwd.main(["--approve", "a.yml"], gh_auth_ok_fn=lambda: True, drift_fn=_drift_with(lambda p: "x\n"))
    assert e.value.code == 2
