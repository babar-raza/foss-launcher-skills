import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE_STORE = REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "project_phase_store.py"
LINK_VALIDATOR = REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "link_validator.py"
READINESS = REPO_ROOT / "scripts" / "pipeline" / "commands" / "launch" / "readiness_scorecard.py"
ROLLBACK = REPO_ROOT / "scripts" / "pipeline" / "commands" / "launch" / "launch_rollback.py"


def test_project_phase_store_set_get_clear(tmp_path):
    state_file = tmp_path / "phase_state.json"

    set_result = subprocess.run(
        [sys.executable, str(PHASE_STORE), "set", "sample", "python", "truth_audit_done", "true", "--state-file", str(state_file), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert set_result.returncode == 0, set_result.stderr
    assert json.loads(set_result.stdout)["value"] is True

    get_result = subprocess.run(
        [sys.executable, str(PHASE_STORE), "get", "sample", "python", "truth_audit_done", "--state-file", str(state_file), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert get_result.returncode == 0, get_result.stderr
    assert json.loads(get_result.stdout)["value"] is True

    clear_result = subprocess.run(
        [sys.executable, str(PHASE_STORE), "clear", "sample", "python", "truth_audit_done", "--state-file", str(state_file), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert clear_result.returncode == 0, clear_result.stderr
    assert json.loads(clear_result.stdout)["changed"] is True


def _content_fixture(tmp_path: Path) -> Path:
    content = tmp_path / "content"
    target = content / "docs.aspose.org" / "en" / "sample" / "python" / "guide.md"
    target.parent.mkdir(parents=True)
    target.write_text("---\ntitle: Guide\ngrade: A\n---\n", encoding="utf-8")
    source = content / "kb.aspose.org" / "en" / "sample" / "python" / "article.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\ntitle: Article\ngrade: A\n---\n\n"
        "[good](https://docs.aspose.org/sample/python/guide/) "
        "[bad](https://docs.aspose.org/sample/python/missing/)",
        encoding="utf-8",
    )
    return content


def test_link_validator_reports_broken_cross_subdomain_links(tmp_path):
    content = _content_fixture(tmp_path)
    source = content / "kb.aspose.org" / "en" / "sample" / "python" / "article.md"

    result = subprocess.run(
        [sys.executable, str(LINK_VALIDATOR), "--files", str(source), "--content-root", str(content), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["files_scanned"] == 1
    assert payload["broken"] == 1
    assert payload["findings"][0]["slug"] == "/sample/python/missing"


def test_readiness_scorecard_uses_fixture_state_and_hgates(tmp_path):
    content = _content_fixture(tmp_path)
    del content  # fixture is rooted under tmp_path/content
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase_state.json").write_text(
        json.dumps({"sample/python": {"values": {"truth_audit_done": True}}}),
        encoding="utf-8",
    )
    review = reports / "human-review"
    review.mkdir()
    for gate in ("h01", "h02", "h03", "h04", "h05"):
        (review / f"sample-python-{gate}-sample.md").write_text("result: PASS\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(READINESS), "--family", "sample", "--platform", "python", "--repo-root", str(tmp_path), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert payload["grades"]["A"] == 2


def test_launch_rollback_dry_run_writes_manifest_and_does_not_delete(tmp_path):
    plan_dir = tmp_path / "reports" / "plans" / "sample" / "python"
    plan_dir.mkdir(parents=True)
    plan_dir.joinpath("site_plan.json").write_text(
        json.dumps({"sections": {"docs": {"pages": [{"path": "content/docs.aspose.org/en/sample/python/guide.md"}]}}}),
        encoding="utf-8",
    )
    page = tmp_path / "content" / "docs.aspose.org" / "en" / "sample" / "python" / "guide.md"
    page.parent.mkdir(parents=True)
    page.write_text("body", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ROLLBACK), "sample", "python", "--repo-root", str(tmp_path), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert page.exists()
    manifest_dir = tmp_path / "reports" / "rollback" / "sample" / "python"
    assert any(manifest_dir.glob("*.md"))


def test_launch_rollback_refuses_protected_paths(tmp_path):
    plan_dir = tmp_path / "reports" / "plans" / "sample" / "python"
    plan_dir.mkdir(parents=True)
    plan_dir.joinpath("site_plan.json").write_text(
        json.dumps({"sections": {"docs": {"pages": [{"path": "scripts/pipeline/bad.py"}]}}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(ROLLBACK), "sample", "python", "--repo-root", str(tmp_path), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "protected paths" in result.stderr
