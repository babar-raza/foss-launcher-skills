"""Structure + behaviour tests for the two deployed-workflow templates rewired by MT074 (W1-W5).

Templates under test (deployed by hand into Aspose/aspose.org-workflows, run in production):
  scripts/ci/deployed-workflows/upstream-monitor.yml   (weekly, clone-free fleet drift)
  scripts/ci/deployed-workflows/registry-watch.yml     (6-hourly, + release-trigger step)

Nothing here deploys, dispatches or calls GitHub. The two inline python snippets embedded in the
upstream-monitor template (state-diff + blast-radius gate) are extracted from the YAML and executed
against temp files, so the logic that decides "open a PR?" and "fail the job?" is really exercised.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOYED_DIR = REPO_ROOT / "scripts" / "ci" / "deployed-workflows"
UPSTREAM = DEPLOYED_DIR / "upstream-monitor.yml"
REGISTRY = DEPLOYED_DIR / "registry-watch.yml"

UPSTREAM_CRON = "0 8 * * 1"
REGISTRY_CRON = "17 */6 * * *"

# Verbatim from the pre-MT074 registry-watch.yml: the registry update + push logic must not change.
ORIGINAL_WATCH_RUN = """\
# set -o pipefail is load-bearing, not defensive boilerplate: the
# first real pilot run of this workflow (2026-09-29) found that
# `python ... | tee ...` without it reports THIS step's outcome as
# 'success' even when the python command genuinely fails (its exit
# code is masked by tee's own success) -- the exact incident this
# closes: a missing commands.ops.registry_watch module (a real
# commit-scoping gap, fixed the same day) failed silently for
# every run since first deploy, and the downstream commit step's
# `if: steps.watch.outcome == 'success'` check never caught it.
set -o pipefail
PYTHONPATH=scripts/pipeline python -m commands.ops.registry_watch \\
  --auto-apply --held-report-out /tmp/held-report.json \\
  | tee /tmp/watch-stdout.txt
"""
ORIGINAL_PUSH_RUN = """\
if git diff --quiet -- data/package_registry.json; then
  echo "No changes to commit."
  exit 0
fi
git config user.name "registry-watch-bot"
git config user.email "noreply@anthropic.com"
git add data/package_registry.json
git commit -m "chore(package-registry): automated registry-watch update (MT075-T7/T9/T10)"
git push origin HEAD:main
"""


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(doc: dict) -> dict:
    # PyYAML (YAML 1.1) parses the bare key `on` as boolean True.
    return doc.get("on") if "on" in doc else doc[True]


def _job(doc: dict) -> dict:
    assert len(doc["jobs"]) == 1, "each template has exactly one job"
    return next(iter(doc["jobs"].values()))


def _steps(doc: dict) -> list:
    return _job(doc)["steps"]


def _code_text(path: Path) -> str:
    """File text with comment-only lines removed (headers/bash comments may legitimately say
    'never auto-merged', 'SKIP_' ...; only executable text is policed)."""
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")
    )


def _runs(doc: dict) -> list:
    return [(i, s) for i, s in enumerate(_steps(doc)) if "run" in s]


def _index(doc: dict, predicate) -> int:
    for i, s in enumerate(_steps(doc)):
        if predicate(s):
            return i
    raise AssertionError("no step matches the predicate")


def _norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def _is_pr_step(s: dict) -> bool:
    return str(s.get("uses", "")).startswith("peter-evans/create-pull-request")


def _is_issue_write(s: dict) -> bool:
    return bool(re.search(r"gh issue (create|comment|close|edit)", s.get("run", "")))


def _heredoc(step: dict) -> str:
    m = re.search(r"python -[^\n]*<<'PYEOF'\n(.*?)\nPYEOF", step["run"], re.S)
    assert m, f"step {step.get('name')!r} has no PYEOF heredoc"
    return m.group(1)


@pytest.fixture(scope="module")
def up() -> dict:
    return _load(UPSTREAM)


@pytest.fixture(scope="module")
def rw() -> dict:
    return _load(REGISTRY)


# --------------------------------------------------------------------------- upstream-monitor


class TestUpstreamMonitorStructure:
    def test_schedule_unchanged(self, up):
        assert _on(up)["schedule"] == [{"cron": UPSTREAM_CRON}]

    def test_step_order_token_checkout_venv_fleet_before_writes(self, up):
        steps = _steps(up)
        token = _index(up, lambda s: s.get("id") == "token_check")
        checkout = _index(up, lambda s: str(s.get("uses", "")).startswith("actions/checkout"))
        venv = _index(up, lambda s: "venv" in s.get("name", "").lower() and "run" in s)
        fleet = _index(up, lambda s: "fleet_drift.py" in s.get("run", ""))
        assert token < checkout < venv < fleet
        for i, s in enumerate(steps):
            if _is_pr_step(s) or _is_issue_write(s):
                assert i > fleet, f"step {s.get('name')!r} writes before fleet_drift ran"

    def test_fleet_drift_is_default_path_with_required_flags(self, up):
        step = next(s for s in _steps(up) if "fleet_drift.py" in s.get("run", ""))
        assert "if" not in step, "the fleet_drift step must run on every trigger"
        run = step["run"]
        for flag in ("--update-state", "--file-issues", "--repo Aspose/aspose.org",
                     "--max-issues-per-run 10", "--json-out", "--md-out", "--sweep-out"):
            assert flag in run, flag
        assert "RUNNER_TEMP" in run, "ledger outputs belong under the runner temp dir"
        assert step["env"]["GH_TOKEN"] == "${{ secrets.REPO_TOKEN || secrets.GH_TOKEN }}"

    def test_default_path_has_no_repo_patrol_sweep(self, up):
        sweeps = [s for s in _steps(up) if "repo_patrol.py sweep" in s.get("run", "")]
        assert sweeps, "the deep sweep must remain available behind deep_sweep"
        for s in sweeps:
            assert "deep_sweep" in str(s.get("if", "")), f"unguarded sweep: {s.get('name')!r}"
        # nothing else may clone: no bounded regen / legacy sweep on the default path
        for s in _steps(up):
            if "deep_sweep" in str(s.get("if", "")):
                continue
            assert "repo_patrol" not in s.get("run", "")

    def test_deep_sweep_input_exists_and_defaults_false(self, up):
        inp = _on(up)["workflow_dispatch"]["inputs"]["deep_sweep"]
        assert inp["type"] == "boolean"
        assert inp["default"] is False

    def test_legacy_issue_filer_is_gone(self, up):
        code = _code_text(UPSTREAM)
        assert "check_upstream_drift" not in code, "fleet_drift is the single issue source"
        assert "bounded_auto_regen" not in code
        assert "fleet_freshness_snapshot" not in code and "upstream_drift_state" not in code

    def test_job_no_longer_fails_just_because_drift_exists(self, up):
        for _, s in _runs(up):
            assert s["run"].strip() != "exit 1"
        assert not any("Fail the job if drift" in s.get("name", "") for s in _steps(up))

    def test_pr_add_paths_exact_set(self, up):
        pr = next(s for s in _steps(up) if _is_pr_step(s))
        paths = {p.strip() for p in pr["with"]["add-paths"].splitlines() if p.strip()}
        assert paths == {"data/content_propagation_state.json"}
        assert pr["with"]["branch"] == "automated/upstream-monitor-freshness-snapshot"
        assert pr["with"]["title"].startswith("chore(freshness): weekly upstream drift snapshot")
        assert "state_diff.outputs.changed == 'true'" in str(pr["if"])

    def test_pr_is_never_combined_with_auto_merge(self, up):
        code = _code_text(UPSTREAM).lower()
        for needle in ("auto-merge", "automerge", "gh pr merge", "enable-pull-request-automerge", "merge_method"):
            assert needle not in code, needle
        pr = next(s for s in _steps(up) if _is_pr_step(s))
        assert pr["uses"].startswith("peter-evans/create-pull-request@")
        assert not any(k for k in pr["with"] if "merge" in k.lower())

    def test_no_hook_bypass_and_no_skip_vars(self, up):
        for path in (UPSTREAM,):
            code = _code_text(path)
            assert "--no-verify" not in code
            assert "SKIP_" not in code

    def test_permissions_present_and_minimal(self, up):
        perms = up.get("permissions") or _job(up).get("permissions")
        assert perms, "permissions must be declared explicitly"
        assert perms.get("contents") == "read"
        assert all(v in ("read", "none") for v in perms.values()), perms

    def test_concurrency_timeout_present(self, up):
        conc = up["concurrency"]
        assert conc["group"] and conc["cancel-in-progress"] is False
        assert isinstance(_job(up)["timeout-minutes"], int) and _job(up)["timeout-minutes"] > 0

    def test_no_secret_printed(self, up):
        code = _code_text(UPSTREAM)
        assert not re.search(r"echo[^\n]*\$\{\{\s*secrets", code)
        for _, s in _runs(up):
            assert "secrets." not in s["run"], f"secret expanded inside a run block: {s.get('name')!r}"

    def test_unknown_share_threshold_default(self, up):
        gate = next(s for s in _steps(up) if s.get("id") == "gate")
        assert str(up["env"]["MAX_UNKNOWN_SHARE"]) == "0.25"  # workflow-level env, inherited by the gate step
        assert "FLEET_EXIT" in gate["env"] and "FLEET_JSON" in gate["env"]

    def test_ledger_summary_and_artifact(self, up):
        steps = _steps(up)
        assert any("GITHUB_STEP_SUMMARY" in s.get("run", "") and "ledger.md" in s.get("run", "") for s in steps)
        up_step = next(s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact@"))
        assert "fleet-drift" in up_step["with"]["path"]
        assert "!cancelled()" in str(up_step["if"])

    def test_failure_tracking_issue_pattern_preserved(self, up):
        text = UPSTREAM.read_text(encoding="utf-8")
        for needle in ("upstream-monitor-failure", "upstream-monitor.yml is failing",
                       "gh issue close", "gh label create upstream-monitor-failure"):
            assert needle in text, needle
        fail = next(s for s in _steps(up) if "upstream-monitor.yml is failing" in s.get("run", ""))
        assert fail["if"] == "failure()"
        ok = next(s for s in _steps(up) if "gh issue close" in s.get("run", ""))
        assert ok["if"] == "success()"

    def test_actions_pinned_in_file_style_and_not_downgraded(self, up):
        floor = {"actions/checkout": 4, "actions/setup-python": 5, "peter-evans/create-pull-request": 6,
                 "actions/upload-artifact": 4}
        for s in _steps(up):
            if "uses" not in s:
                continue
            m = re.fullmatch(r"([\w.-]+/[\w.-]+)@v(\d+)", s["uses"])
            assert m, f"unpinned/odd action ref {s['uses']}"
            assert int(m.group(2)) >= floor[m.group(1)], s["uses"]


# --------------------------------------------------------------------------- upstream-monitor inline logic


def _run_snippet(code: str, env: dict) -> subprocess.CompletedProcess:
    full_env = {**os.environ, "PYTHONIOENCODING": "utf-8", **env}
    return subprocess.run([sys.executable, "-I", "-c", code], cwd=REPO_ROOT, env=full_env,
                          capture_output=True, text=True, encoding="utf-8")


class TestStateDiffSnippet:
    @pytest.fixture()
    def code(self, up):
        return _heredoc(next(s for s in _steps(up) if s.get("id") == "state_diff"))

    def _state(self, tmp_path, name, **per_product):
        p = tmp_path / name
        p.write_text(json.dumps({"schema_version": 1, "products": per_product}), encoding="utf-8")
        return p

    def _go(self, code, tmp_path, committed, new):
        out = tmp_path / "gh_out.txt"
        out.write_text("", encoding="utf-8")
        res = _run_snippet(code, {"COMMITTED_STATE": str(committed), "NEW_STATE": str(new),
                                  "GITHUB_OUTPUT": str(out)})
        assert res.returncode == 0, res.stderr
        return dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines() if "=" in line)

    def test_volatile_only_difference_does_not_open_a_pr(self, code, tmp_path):
        a = self._state(tmp_path, "a.json", **{"f/p": {"tier": "SOURCE", "volatile": {"observed_at": "2026-10-01T00:00:00Z"}}})
        b = self._state(tmp_path, "b.json", **{"f/p": {"tier": "SOURCE", "volatile": {"observed_at": "2026-10-08T00:00:00Z",
                                                                                        "last_issue_number": 7}}})
        assert self._go(code, tmp_path, a, b)["changed"] == "false"

    def test_non_volatile_difference_opens_a_pr(self, code, tmp_path):
        a = self._state(tmp_path, "a.json", **{"f/p": {"tier": "SOURCE", "volatile": {"observed_at": "x"}}})
        b = self._state(tmp_path, "b.json", **{"f/p": {"tier": "API_TOUCHED", "volatile": {"observed_at": "x"}}})
        assert self._go(code, tmp_path, a, b)["changed"] == "true"

    def test_missing_committed_state_and_new_products_opens_a_pr(self, code, tmp_path):
        b = self._state(tmp_path, "b.json", **{"f/p": {"tier": "SOURCE"}})
        assert self._go(code, tmp_path, tmp_path / "absent.json", b)["changed"] == "true"

    def test_missing_both_is_no_change(self, code, tmp_path):
        assert self._go(code, tmp_path, tmp_path / "x.json", tmp_path / "y.json")["changed"] == "false"


class TestGateSnippet:
    @pytest.fixture()
    def code(self, up):
        return _heredoc(next(s for s in _steps(up) if s.get("id") == "gate"))

    def _ledger(self, tmp_path, total, unknown):
        p = tmp_path / "ledger.json"
        p.write_text(json.dumps({"summary": {"total": total, "by_tier": {"UNKNOWN": unknown, "SOURCE": total - unknown}}}),
                     encoding="utf-8")
        return p

    def _go(self, code, tmp_path, *, exit_code="0", ledger=None, share="0.25"):
        out = tmp_path / "gh_out.txt"
        out.write_text("", encoding="utf-8")
        env = {"FLEET_EXIT": exit_code, "FLEET_JSON": str(ledger or tmp_path / "none.json"),
               "MAX_UNKNOWN_SHARE": share, "GITHUB_OUTPUT": str(out)}
        res = _run_snippet(code, env)
        return res, out.read_text(encoding="utf-8")

    def test_drift_alone_passes(self, code, tmp_path):
        res, _ = self._go(code, tmp_path, ledger=self._ledger(tmp_path, 36, 0))
        assert res.returncode == 0, res.stdout + res.stderr

    def test_unknown_share_at_threshold_passes_and_above_fails(self, code, tmp_path):
        ok, _ = self._go(code, tmp_path, ledger=self._ledger(tmp_path, 36, 9))  # exactly 0.25
        assert ok.returncode == 0
        bad, out = self._go(code, tmp_path, ledger=self._ledger(tmp_path, 36, 10))
        assert bad.returncode == 1 and "reason=" in out and "UNKNOWN" in out

    def test_threshold_is_configurable(self, code, tmp_path):
        res, _ = self._go(code, tmp_path, ledger=self._ledger(tmp_path, 10, 5), share="0.6")
        assert res.returncode == 0

    @pytest.mark.parametrize("rc", ["1", "2", ""])
    def test_fleet_exit_nonzero_fails(self, code, tmp_path, rc):
        res, out = self._go(code, tmp_path, exit_code=rc, ledger=self._ledger(tmp_path, 36, 0))
        assert res.returncode == 1 and "reason=" in out

    def test_missing_or_empty_ledger_fails(self, code, tmp_path):
        assert self._go(code, tmp_path)[0].returncode == 1
        assert self._go(code, tmp_path, ledger=self._ledger(tmp_path, 0, 0))[0].returncode == 1


# --------------------------------------------------------------------------- registry-watch


class TestRegistryWatch:
    def test_schedule_unchanged(self, rw):
        assert _on(rw)["schedule"] == [{"cron": REGISTRY_CRON}]

    def test_registry_update_and_push_logic_unchanged(self, rw):
        watch = next(s for s in _steps(rw) if s.get("id") == "watch")
        assert _norm(watch["run"]) == _norm(ORIGINAL_WATCH_RUN)
        assert watch["continue-on-error"] is True
        push = next(s for s in _steps(rw) if s.get("name", "").startswith("Commit and push directly"))
        assert _norm(push["run"]) == _norm(ORIGINAL_PUSH_RUN)
        assert push["if"] == "steps.watch.outcome == 'success'"

    def test_release_trigger_is_nonblocking_and_after_push(self, rw):
        steps = _steps(rw)
        push = _index(rw, lambda s: s.get("name", "").startswith("Commit and push directly"))
        rel = _index(rw, lambda s: "--release-trigger" in s.get("run", ""))
        assert rel > push
        step = steps[rel]
        assert step["continue-on-error"] is True
        assert step["id"] == "release_trigger"
        assert step["env"]["GH_TOKEN"] == "${{ secrets.REPO_TOKEN || secrets.GH_TOKEN }}"
        assert "steps.watch.outcome == 'success'" in str(step["if"])
        # a visible note when it fails
        note = next(s for s in steps if "steps.release_trigger.outcome == 'failure'" in str(s.get("if", "")))
        assert "GITHUB_STEP_SUMMARY" in note["run"]

    def test_release_trigger_is_issue_only(self, rw):
        step = next(s for s in _steps(rw) if "--release-trigger" in s.get("run", ""))
        run = step["run"]
        assert "--repo Aspose/aspose.org" in run
        for forbidden in ("git add", "git commit", "git push", "--auto-apply", "registry_watch",
                          "content/", "git config", "--no-verify"):
            assert forbidden not in run, forbidden
        assert "package_registry.before.json" in run, "change list derived from the pre-watch snapshot"

    def test_registry_snapshot_taken_before_watch(self, rw):
        snap = _index(rw, lambda s: "package_registry.before.json" in s.get("run", "") and "--release-trigger" not in s["run"])
        watch = _index(rw, lambda s: s.get("id") == "watch")
        assert snap < watch

    def test_permissions_concurrency_timeout(self, rw):
        perms = rw.get("permissions") or _job(rw).get("permissions")
        assert perms and perms.get("contents") == "read"
        assert all(v in ("read", "none") for v in perms.values()), perms
        assert rw["concurrency"]["group"] and rw["concurrency"]["cancel-in-progress"] is False
        assert isinstance(_job(rw)["timeout-minutes"], int)

    def test_no_secret_printed_no_hook_bypass(self, rw):
        code = _code_text(REGISTRY)
        assert not re.search(r"echo[^\n]*\$\{\{\s*secrets", code)
        assert "--no-verify" not in code and "SKIP_" not in code
        for _, s in _runs(rw):
            assert "secrets." not in s["run"]

    def test_failure_issue_pattern_preserved(self, rw):
        text = REGISTRY.read_text(encoding="utf-8")
        for needle in ("registry-watch-failure", "registry-watch.yml is failing", "registry-watch-held",
                       "gh issue close"):
            assert needle in text, needle

    def test_token_check_first_then_checkout(self, rw):
        token = _index(rw, lambda s: s.get("id") == "token_check")
        checkout = _index(rw, lambda s: str(s.get("uses", "")).startswith("actions/checkout"))
        watch = _index(rw, lambda s: s.get("id") == "watch")
        assert token == 0 and token < checkout < watch


class TestReleaseTriggerChangeList:
    """The change-list python in the release-trigger step: which products did the watcher change?"""

    @pytest.fixture()
    def code(self, rw):
        return _heredoc(next(s for s in _steps(rw) if "--release-trigger" in s.get("run", "")))

    def test_lists_only_changed_entries(self, code, tmp_path):
        before = {"pdf": {"java": {"v": 1}, "net": {"v": 1}}, "cells": {"go": {"v": 1}}}
        after = {"pdf": {"java": {"v": 2}, "net": {"v": 1}}, "cells": {"go": {"v": 1}}, "words": {"rust": {"v": 1}}}
        b, a = tmp_path / "b.json", tmp_path / "a.json"
        b.write_text(json.dumps(before), encoding="utf-8")
        a.write_text(json.dumps(after), encoding="utf-8")
        res = subprocess.run([sys.executable, "-I", "-", str(b), str(a)], input=code, capture_output=True,
                             text=True, encoding="utf-8")
        assert res.returncode == 0, res.stderr
        assert res.stdout.split() == ["pdf/java", "words/rust"]

    def test_no_change_lists_nothing(self, code, tmp_path):
        d = {"pdf": {"java": {"v": 1}}}
        b = tmp_path / "b.json"
        b.write_text(json.dumps(d), encoding="utf-8")
        res = subprocess.run([sys.executable, "-I", "-", str(b), str(b)], input=code, capture_output=True,
                             text=True, encoding="utf-8")
        assert res.returncode == 0 and res.stdout.strip() == ""


# --------------------------------------------------------------------------- shared


_SCRIPT_REF = re.compile(r"(?<![\w./-])((?:scripts|data)/[\w./-]+\.(?:py|sh|txt|json|yaml|yml))")
# Written by fleet_drift on first run (content_propagation_state creates it on first write), so a
# fresh checkout may legitimately not contain it yet; asserted separately below.
_CREATED_AT_RUNTIME = {"data/content_propagation_state.json"}
_MODULE_REF = re.compile(r"python -m ((?:commands|lib)(?:\.\w+)+)")


@pytest.mark.parametrize("path", [UPSTREAM, REGISTRY], ids=lambda p: p.name)
def test_every_repo_path_referenced_by_a_run_block_exists(path):
    doc = _load(path)
    missing = []
    for _, step in _runs(doc):
        run = "\n".join(l for l in step["run"].splitlines() if not l.lstrip().startswith("#"))
        for ref in _SCRIPT_REF.findall(run):
            if "*" in ref or "{" in ref:
                continue
            if ref.endswith(".before.json") or ref in _CREATED_AT_RUNTIME:
                continue
            if not (REPO_ROOT / ref).exists():
                missing.append(ref)
        for mod in _MODULE_REF.findall(run):
            rel = Path("scripts/pipeline", *mod.split(".")).with_suffix(".py")
            if not (REPO_ROOT / rel).exists():
                missing.append(str(rel))
    # requirements files named in setup-python's cache key / pip install lines are covered by the regex too
    for step in _steps(doc):
        dep = (step.get("with") or {}).get("cache-dependency-path")
        if dep and not (REPO_ROOT / dep).exists():
            missing.append(dep)
    assert not missing, f"{path.name} references missing repo paths: {sorted(set(missing))}"


def test_runtime_created_state_path_matches_the_state_module():
    src = (REPO_ROOT / "scripts" / "pipeline" / "lib" / "content_propagation_state.py").read_text(encoding="utf-8")
    for rel in _CREATED_AT_RUNTIME:
        assert rel.split("/", 1)[1] in src, f"{rel} is not the state module's default path"


# =========================================================================== review R4 additions
# Each guard is a function over a parsed template so the SAME check can be run against the real file
# (must pass) and against a deliberately broken copy (must fail) -- the mutant tests prove the guards bite.

import copy  # noqa: E402


def _step_by_id(doc: dict, sid: str) -> dict:
    return next(s for s in _steps(doc) if s.get("id") == sid)


def _ledger_artifact_step(doc: dict) -> dict:
    return next(s for s in _steps(doc) if str(s.get("uses", "")).startswith("actions/upload-artifact")
                and s["with"]["name"] == "fleet-drift-ledger")


def guard_cancel_safe_publishing(doc: dict) -> None:
    """M1: the steps that must still run after an earlier failure use `!cancelled()`, not success()."""
    for name, step in (("gate", _step_by_id(doc, "gate")),
                       ("public", _step_by_id(doc, "public")),
                       ("artifact", _ledger_artifact_step(doc))):
        cond = str(step.get("if", ""))
        assert "!cancelled()" in cond, f"{name} step must carry !cancelled() (got {cond!r})"
        assert cond.strip() != "success()", name


def guard_pipestatus(doc: dict) -> None:
    """M3: fleet_drift's own exit status is captured (not tee's), so exit 1 with a ledger present is still red."""
    run = _step_by_id(doc, "drift")["run"]
    assert "RC=${PIPESTATUS[0]}" in run, "the drift step must capture fleet_drift's status via PIPESTATUS[0]"
    assert "RC=$?" not in run
    assert "fleet_exit=$RC" in run


def guard_pr_condition(doc: dict) -> None:
    """M4: the state PR opens only on a non-volatile change and never on always()."""
    pr = next(s for s in _steps(doc) if _is_pr_step(s))
    cond = str(pr.get("if", ""))
    assert "always()" not in cond, cond
    assert "!cancelled()" in cond and "state_diff.outputs.changed == 'true'" in cond, cond
    assert "||" not in cond, "an OR could open a PR without the non-volatile change"


def _mutate_if(doc: dict, step_pred, new_if: str) -> dict:
    d = copy.deepcopy(doc)
    step = next(s for s in _steps(d) if step_pred(s))
    step["if"] = new_if
    return d


class TestReviewR4Guards:
    def test_real_template_passes_every_guard(self, up):
        guard_cancel_safe_publishing(up)
        guard_pipestatus(up)
        guard_pr_condition(up)

    def test_M1_gate_if_success_is_caught(self, up):
        bad = _mutate_if(up, lambda s: s.get("id") == "gate", "success()")
        with pytest.raises(AssertionError):
            guard_cancel_safe_publishing(bad)

    def test_M1_artifact_if_success_is_caught(self, up):
        bad = _mutate_if(up, lambda s: str(s.get("uses", "")).startswith("actions/upload-artifact")
                         and s["with"]["name"] == "fleet-drift-ledger", "success()")
        with pytest.raises(AssertionError):
            guard_cancel_safe_publishing(bad)

    def test_M3_rc_dollar_question_is_caught(self, up):
        bad = copy.deepcopy(up)
        drift = _step_by_id(bad, "drift")
        drift["run"] = drift["run"].replace("RC=${PIPESTATUS[0]}", "RC=$?")
        with pytest.raises(AssertionError):
            guard_pipestatus(bad)

    def test_M4_pr_always_is_caught(self, up):
        bad = _mutate_if(up, _is_pr_step, "${{ always() || steps.state_diff.outputs.changed == 'true' }}")
        with pytest.raises(AssertionError):
            guard_pr_condition(bad)
        bad2 = _mutate_if(up, _is_pr_step,
                          "${{ !cancelled() && steps.state_diff.outputs.changed == 'true' || always() }}")
        with pytest.raises(AssertionError):
            guard_pr_condition(bad2)

    def test_state_diff_is_independent_of_summary_and_upload_steps(self, up):
        """item 2: a failed summary/upload step must not skip the state PR."""
        sd = str(_step_by_id(up, "state_diff")["if"])
        assert "!cancelled()" in sd and "steps.drift.outcome == 'success'" in sd
        for forbidden in ("steps.public", "upload", "summary"):
            assert forbidden not in sd

    def test_deep_sweep_steps_run_before_the_gate_with_explicit_conditions(self, up):
        steps = _steps(up)
        gate = _index(up, lambda s: s.get("id") == "gate")
        deep = [i for i, s in enumerate(steps) if "deep_sweep" in str(s.get("if", ""))]
        assert len(deep) == 3, "install + sweep + report upload"
        for i in deep:
            assert i < gate, "deep-sweep steps must precede the gate so a red gate cannot skip a requested sweep"
            cond = str(steps[i]["if"])
            assert "!cancelled()" in cond and "inputs.deep_sweep == true" in cond
            assert "steps.venv.outcome == 'success'" in cond
        assert any("repo_patrol.py sweep" in steps[i].get("run", "") for i in deep)


# --------------------------------------------------------------------------- M5: injection lint

_UNTRUSTED = re.compile(
    r"github\.event\.|github\.head_ref|github\.base_ref|github\.ref_name|github\.event_path"
    r"|(?<![\w.])inputs\.|github\.actor|github\.triggering_actor")
_EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)


def find_injections(run_text: str) -> list:
    """Expressions interpolated straight into a shell script that carry attacker-influenced text.
    Untrusted values must reach a script through `env:` (a shell variable), never through ${{ }} in `run:`."""
    return [m.strip() for m in _EXPR.findall(run_text) if _UNTRUSTED.search(m)]


class TestInjectionLint:
    @pytest.mark.parametrize("injected", [
        'echo "${{ github.event.pull_request.title }}"',
        'git checkout ${{ github.head_ref }}',
        'echo ${{ github.event.head_commit.message }}',
        'if [ "${{ inputs.deep_sweep }}" = true ]; then :; fi',
        'echo "${{github.event.issue.body}}"',
    ])
    def test_lint_catches_the_injected_form(self, injected):
        assert find_injections(injected), injected

    @pytest.mark.parametrize("safe", [
        'echo "$TITLE"',
        'RUN_URL="${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"',
        'echo "Trigger: ${{ github.event_name }}"',
        'echo ${{ steps.token_check.outputs.reason }}',
    ])
    def test_lint_leaves_the_safe_forms_alone(self, safe):
        assert find_injections(safe) == []

    @pytest.mark.parametrize("path", [UPSTREAM, REGISTRY], ids=lambda p: p.name)
    def test_no_untrusted_expression_inside_any_run_block(self, path):
        offenders = []
        for _, step in _runs(_load(path)):
            offenders += [(step.get("name"), e) for e in find_injections(step["run"])]
        assert not offenders, offenders


# --------------------------------------------------------------------------- public-visibility scrub

SECRET_SHAPES = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|x-access-token:[^@\s]+@"
    r"|://[^/\s:@]+:[^/\s@]+@|Bearer\s+[A-Za-z0-9._~+/=-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")


def _synthetic_ledger(tmp_path: Path):
    """A real fleet_drift ledger + markdown over synthetic rows (uses the module's own builders)."""
    import importlib

    sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
    fd = importlib.import_module("commands.diagnostics.fleet_drift")
    base = {"family": "fam", "platform": "plat", "repo": "o/r", "knowledge_sha": "a" * 40, "baselines_sha": "b" * 40,
            "baseline_assumed": False, "baseline_stores_disagree": True, "upstream_head": "c" * 40, "status": "ok",
            "tier": "SOURCE", "tier_reason": "source_files_changed", "transient": False, "compare_status": "ahead",
            "ahead_by": 3, "files_seen": 5, "source_files": 2, "api_surface_touched": False, "truncated": False,
            "api_files": [], "release_state": "released", "release_state_reason": "registry",
            "ground_truth_tier": "GT-2", "propagation_status": "UNRECORDED"}
    rows = [{**base, "product": "fam/plat"},
            {**base, "product": "other/disagreeing", "family": "other", "platform": "disagreeing"},
            {**base, "product": "calm/agree", "family": "calm", "platform": "agree",
             "baseline_stores_disagree": False, "tier": "NO_CHANGE", "tier_reason": None}]
    ledger = fd.build_ledger(rows, now="2026-10-07T00:00:00Z")
    raw = tmp_path / "fleet-drift"
    raw.mkdir()
    (raw / "ledger.json").write_text(fd.dumps(ledger), encoding="utf-8")
    (raw / "ledger.md").write_text(fd.render_markdown(ledger), encoding="utf-8")
    (raw / "sweep_report.json").write_text("{}", encoding="utf-8")
    (raw / "fleet_drift.log").write_text(
        "fleet_drift: ok\nremote: https://x-access-token:ghp_" + "A" * 36 + "@github.com/o/r\nBearer " + "z" * 30 + "\n",
        encoding="utf-8")
    return ledger


class TestPublicLedger:
    @pytest.fixture()
    def published(self, up, tmp_path):
        ledger = _synthetic_ledger(tmp_path)
        code = _heredoc(_step_by_id(up, "public"))
        res = _run_snippet(code, {"RUNNER_TEMP": str(tmp_path)})
        assert res.returncode == 0, res.stdout + res.stderr
        return ledger, tmp_path / "fleet-drift-public"

    def test_secret_shape_scanner_catches_credentials(self):
        for sample in ("https://x-access-token:abc123@github.com/o/r", "ghp_" + "A" * 36, "github_pat_" + "B" * 40,
                       "https://user:pw@host/x", "Bearer " + "q" * 30, "-----BEGIN RSA PRIVATE KEY-----"):
            assert SECRET_SHAPES.search(sample), sample
        assert not SECRET_SHAPES.search("https://github.com/Aspose/aspose.org/actions/runs/1 sha " + "a" * 40)

    def test_public_outputs_have_no_secret_shaped_content(self, published):
        _, pub = published
        assert {p.name for p in pub.iterdir()} >= {"ledger.json", "ledger.md", "sweep_report.json", "fleet_drift.log"}
        for f in pub.iterdir():
            assert not SECRET_SHAPES.search(f.read_text(encoding="utf-8")), f"{f.name} leaks a credential-shaped string"
        assert "[redacted]" in (pub / "fleet_drift.log").read_text(encoding="utf-8")

    def test_baseline_disagreement_detail_is_reduced_to_counts(self, published):
        ledger, pub = published
        md = (pub / "ledger.md").read_text(encoding="utf-8")
        js = json.loads((pub / "ledger.json").read_text(encoding="utf-8"))
        assert "Stores disagree" not in md
        assert "Disagree: 2 | Missing in baselines store: 0" in md
        assert "(fam/plat" not in md and "(other/disagreeing" not in md, "no disagreement name list"
        assert js["baseline_stores"] == {"disagree_count": 2, "missing_baseline_count": 0, "projection_stale_count": None}
        for row in js["products"].values():
            assert "baselines_sha" not in row and "baseline_stores_disagree" not in row
        # table rows keep a consistent column count after dropping the last column
        counts = {line.count("|") for line in md.splitlines() if line.startswith("|")}
        assert len(counts) == 1, counts
        assert js["summary"] == ledger["summary"], "gate-relevant summary is untouched"

    def test_raw_ledger_stays_out_of_the_published_directory_and_gate_reads_it(self, up):
        assert _ledger_artifact_step(up)["with"]["path"].rstrip("/").endswith("fleet-drift-public")
        assert _step_by_id(up, "gate")["env"]["FLEET_JSON"].endswith("/fleet-drift/ledger.json")
        summary = next(s for s in _steps(up) if "GITHUB_STEP_SUMMARY" in s.get("run", "") and "ledger.md" in s["run"])
        assert "fleet-drift-public" in summary["run"]

    def test_no_run_block_writing_the_summary_references_a_token(self, up, rw):
        for doc in (up, rw):
            for _, s in _runs(doc):
                if "GITHUB_STEP_SUMMARY" in s["run"]:
                    assert not re.search(r"GH_TOKEN|GITHUB_TOKEN|secrets\.|REPO_TOKEN", s["run"]), s.get("name")
                    assert not SECRET_SHAPES.search(s["run"])
