"""Tests for check_family_registry_drift.py (SEO-FAMILY-REGISTRY-DRIFT-DETECTION, Finding #70)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_family_registry_drift as cfrd  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_module_paths():
    yield
    cfrd.configure()


def _make_repo(tmp_path: Path, *, registry: dict, content: dict[str, list[str]]) -> Path:
    """content: {site_name: [family_dir_names]} -- each gets a real family dir with _index.md."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "family_descriptions.json").write_text(
        json.dumps(registry), encoding="utf-8"
    )
    for site, families in content.items():
        en_dir = tmp_path / "content" / site / "en"
        en_dir.mkdir(parents=True, exist_ok=True)
        for fam in families:
            fam_dir = en_dir / fam
            fam_dir.mkdir(parents=True, exist_ok=True)
            (fam_dir / "_index.md").write_text("---\ntitle: x\n---\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# find_launched_families()
# ---------------------------------------------------------------------------

def test_find_launched_families_across_all_3_sites(tmp_path):
    _make_repo(
        tmp_path, registry={},
        content={
            "docs.aspose.org": ["cells", "pdf"],
            "kb.aspose.org": ["cells"],
            "products.aspose.org": ["cells", "medical"],
        },
    )
    launched = cfrd.find_launched_families(content_root=tmp_path / "content")
    assert launched == {"cells", "pdf", "medical"}


def test_find_launched_families_skips_underscore_and_dot_dirs(tmp_path):
    en_dir = tmp_path / "content" / "docs.aspose.org" / "en"
    en_dir.mkdir(parents=True)
    (en_dir / "_shared").mkdir()
    (en_dir / ".hidden").mkdir()
    (en_dir / "cells").mkdir()
    (en_dir / "_index.md").write_text("x", encoding="utf-8")
    launched = cfrd.find_launched_families(content_root=tmp_path / "content", sites=("docs.aspose.org",))
    assert launched == {"cells"}


def test_find_launched_families_missing_site_dir_is_not_an_error(tmp_path):
    (tmp_path / "content").mkdir()
    launched = cfrd.find_launched_families(content_root=tmp_path / "content", sites=("docs.aspose.org",))
    assert launched == set()


# ---------------------------------------------------------------------------
# load_registered_families() / find_registry_gaps()
# ---------------------------------------------------------------------------

def test_load_registered_families_reads_real_keys(tmp_path):
    repo = _make_repo(tmp_path, registry={"cells": {"en": "x"}, "pdf": {"en": "y"}}, content={})
    cfrd.configure(repo_root=repo)
    assert cfrd.load_registered_families() == {"cells", "pdf"}


def test_load_registered_families_raises_on_missing_file(tmp_path):
    cfrd.configure(repo_root=tmp_path)
    with pytest.raises(FileNotFoundError):
        cfrd.load_registered_families()


def test_load_registered_families_raises_on_non_object_json(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "family_descriptions.json").write_text("[1, 2, 3]", encoding="utf-8")
    cfrd.configure(repo_root=tmp_path)
    with pytest.raises(ValueError):
        cfrd.load_registered_families()


def test_find_registry_gaps_real_finding_shape(tmp_path):
    """Reproduces the real live finding this check found against the actual
    repo (medical: launched under products.aspose.org, unregistered)."""
    repo = _make_repo(
        tmp_path,
        registry={"cells": {"en": "x"}, "pdf": {"en": "y"}},
        content={
            "docs.aspose.org": ["cells", "pdf"],
            "products.aspose.org": ["cells", "pdf", "medical"],
        },
    )
    cfrd.configure(repo_root=repo)
    assert cfrd.find_registry_gaps(content_root=repo / "content") == ["medical"]


def test_find_registry_gaps_empty_when_everything_registered(tmp_path):
    repo = _make_repo(
        tmp_path, registry={"cells": {"en": "x"}},
        content={"docs.aspose.org": ["cells"]},
    )
    cfrd.configure(repo_root=repo)
    assert cfrd.find_registry_gaps(content_root=repo / "content") == []


def test_find_registry_gaps_registered_but_not_launched_is_not_a_gap(tmp_path):
    """Stub-tier families (registered, no content yet) are expected and must
    never be reported as a gap -- the gap direction is launched-without-
    registry-entry only, never the reverse."""
    repo = _make_repo(
        tmp_path, registry={"cells": {"en": "x"}, "cad": {"en": "y"}},
        content={"docs.aspose.org": ["cells"]},
    )
    cfrd.configure(repo_root=repo)
    assert cfrd.find_registry_gaps(content_root=repo / "content") == []


# ---------------------------------------------------------------------------
# find_existing_issue() / file_or_update_issue() -- injectable runner, no real gh calls
# ---------------------------------------------------------------------------

class _FakeRunner:
    """Records every gh invocation and returns a scripted CompletedProcess."""

    def __init__(self, responses):
        self.calls = []
        self._responses = list(responses)

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if not self._responses:
            raise AssertionError(f"no scripted response left for call: {cmd}")
        rc, stdout = self._responses.pop(0)
        return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")


def test_find_existing_issue_returns_number_when_found():
    runner = _FakeRunner([(0, json.dumps([{"number": 42}]))])
    result = cfrd.find_existing_issue("medical", repo="Aspose/aspose.org", runner=runner)
    assert result == 42
    assert "--label" in runner.calls[0]
    assert "family-registry-gap" in runner.calls[0]
    assert "family:medical" in runner.calls[0]


def test_find_existing_issue_returns_none_when_no_open_issue():
    runner = _FakeRunner([(0, "[]")])
    assert cfrd.find_existing_issue("medical", repo="Aspose/aspose.org", runner=runner) is None


def test_find_existing_issue_returns_none_on_gh_failure():
    runner = _FakeRunner([(1, "")])
    assert cfrd.find_existing_issue("medical", repo="Aspose/aspose.org", runner=runner) is None


def test_find_existing_issue_returns_none_on_malformed_json():
    runner = _FakeRunner([(0, "not json")])
    assert cfrd.find_existing_issue("medical", repo="Aspose/aspose.org", runner=runner) is None


def test_file_or_update_issue_creates_when_none_exists():
    runner = _FakeRunner([
        (0, "[]"),  # find_existing_issue -> none
        (0, "https://github.com/Aspose/aspose.org/issues/99\n"),  # gh issue create
    ])
    result = cfrd.file_or_update_issue(
        "medical", sites_present=["products.aspose.org"], repo="Aspose/aspose.org", runner=runner,
    )
    assert result == {"action": "created", "issue_number": 99}
    create_call = runner.calls[1]
    assert "create" in create_call
    assert "medical" in " ".join(create_call)


def test_file_or_update_issue_comments_when_already_open():
    runner = _FakeRunner([
        (0, json.dumps([{"number": 7}])),  # find_existing_issue -> 7
        (0, ""),  # gh issue comment
    ])
    result = cfrd.file_or_update_issue(
        "medical", sites_present=["products.aspose.org"], repo="Aspose/aspose.org", runner=runner,
    )
    assert result == {"action": "commented", "issue_number": 7}
    comment_call = runner.calls[1]
    assert "comment" in comment_call
    assert "7" in comment_call


def test_file_or_update_issue_reports_failed_on_comment_error():
    runner = _FakeRunner([
        (0, json.dumps([{"number": 7}])),
        (1, ""),  # comment fails
    ])
    result = cfrd.file_or_update_issue(
        "medical", sites_present=["products.aspose.org"], repo="Aspose/aspose.org", runner=runner,
    )
    assert result == {"action": "failed", "issue_number": 7}


def test_file_or_update_issue_reports_failed_on_create_error():
    runner = _FakeRunner([
        (0, "[]"),
        (1, ""),  # create fails
    ])
    result = cfrd.file_or_update_issue(
        "medical", sites_present=["products.aspose.org"], repo="Aspose/aspose.org", runner=runner,
    )
    assert result == {"action": "failed", "issue_number": None}


def test_issue_body_never_invents_a_description():
    """The body must explain the gap and point at the real fix location, but
    must never itself propose descriptive text for the family -- that
    judgment call is explicitly out of scope for this check (boundary
    violation risk against the repo-wide family_descriptions.json file)."""
    body = cfrd._issue_body("medical", sites_present=["products.aspose.org"], run_url=None)
    assert "medical" in body
    assert "data/family_descriptions.json" in body
    assert "does not write" in body or "does not itself" in body or "deliberately" in body


# ---------------------------------------------------------------------------
# check_family_registry_drift() orchestration
# ---------------------------------------------------------------------------

def test_check_without_file_issues_reports_gaps_but_calls_no_gh(tmp_path):
    repo = _make_repo(
        tmp_path, registry={"cells": {"en": "x"}},
        content={"products.aspose.org": ["cells", "medical"]},
    )
    cfrd.configure(repo_root=repo)
    runner = _FakeRunner([])
    report = cfrd.check_family_registry_drift(file_issues=False, runner=runner, content_root=repo / "content")
    assert report["gaps"] == ["medical"]
    assert report["issue_actions"] == {}
    assert runner.calls == []


def test_check_with_file_issues_files_one_issue_per_gap(tmp_path):
    repo = _make_repo(
        tmp_path, registry={"cells": {"en": "x"}},
        content={"products.aspose.org": ["cells", "medical"]},
    )
    cfrd.configure(repo_root=repo)
    runner = _FakeRunner([
        (0, "[]"),
        (0, "https://github.com/Aspose/aspose.org/issues/1\n"),
    ])
    report = cfrd.check_family_registry_drift(
        file_issues=True, repo="Aspose/aspose.org", runner=runner, content_root=repo / "content",
    )
    assert report["gaps"] == ["medical"]
    assert report["issue_actions"]["medical"]["action"] == "created"


def test_check_no_gaps_no_gh_calls_even_with_file_issues_true(tmp_path):
    repo = _make_repo(
        tmp_path, registry={"cells": {"en": "x"}},
        content={"products.aspose.org": ["cells"]},
    )
    cfrd.configure(repo_root=repo)
    runner = _FakeRunner([])
    report = cfrd.check_family_registry_drift(file_issues=True, runner=runner, content_root=repo / "content")
    assert report["gaps"] == []
    assert runner.calls == []


# ---------------------------------------------------------------------------
# main() -- exit codes
# ---------------------------------------------------------------------------

def test_main_exit_0_when_no_gaps(tmp_path, capsys):
    repo = _make_repo(
        tmp_path, registry={"cells": {"en": "x"}},
        content={"products.aspose.org": ["cells"]},
    )
    cfrd.configure(repo_root=repo)
    assert cfrd.main([]) == 0
    assert "OK" in capsys.readouterr().out


def test_main_exit_1_when_gap_found(tmp_path, capsys):
    repo = _make_repo(
        tmp_path, registry={"cells": {"en": "x"}},
        content={"products.aspose.org": ["cells", "medical"]},
    )
    cfrd.configure(repo_root=repo)
    assert cfrd.main([]) == 1
    assert "medical" in capsys.readouterr().out


def test_main_exit_2_on_missing_registry(tmp_path, capsys):
    (tmp_path / "content").mkdir()
    cfrd.configure(repo_root=tmp_path)
    assert cfrd.main([]) == 2
    assert "error" in capsys.readouterr().err.lower()


def test_main_never_calls_gh_without_file_issues_flag(tmp_path, monkeypatch):
    repo = _make_repo(
        tmp_path, registry={"cells": {"en": "x"}},
        content={"products.aspose.org": ["cells", "medical"]},
    )
    cfrd.configure(repo_root=repo)

    def _boom(*a, **kw):
        raise AssertionError("gh must not be invoked when --file-issues is absent")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert cfrd.main([]) == 1
