import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.pipeline.commands.diagnostics import repo_patrol

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo(name: str, *, archived=False, pushed_days=10, description="A FOSS repo"):
    return {
        "name": name,
        "full_name": f"org/{name}",
        "html_url": f"https://github.com/org/{name}",
        "clone_url": f"https://github.com/org/{name}.git",
        "pushed_at": _ago(pushed_days),
        "archived": archived,
        "description": description,
    }


def _registry_entry(family="pdf", platform="python", **extra):
    item = {
        "family": family,
        "platform": platform,
        "repo_name": f"Aspose.{family.upper()}-FOSS-for-{platform.title()}",
        "clone_url": f"https://github.com/org/{family}-{platform}.git",
        "active": True,
        "status": "launched",
    }
    item.update(extra)
    return item


def test_score_confidence_new_convention():
    assert repo_patrol.score_confidence(_repo("Aspose.PDF-FOSS-for-Python")) >= 0.55


def test_cmd_scan_dry_run_writes_report_not_registry(tmp_path):
    repo_patrol.configure(repo_root=tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "products.json").write_text("[]", encoding="utf-8")
    try:
        report = repo_patrol.cmd_scan(orgs=["org"], repos=[_repo("Aspose.PDF-FOSS-for-Python")])
    finally:
        repo_patrol.configure()

    assert report["summary"]["new_candidates"] == 1
    assert json.loads((tmp_path / "data" / "products.json").read_text(encoding="utf-8")) == []
    assert (tmp_path / "reports" / "discovery" / "patrol_report.json").exists()


def test_cmd_scan_apply_updates_registry(tmp_path):
    repo_patrol.configure(repo_root=tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "products.json").write_text("[]", encoding="utf-8")
    try:
        repo_patrol.cmd_scan(orgs=["org"], repos=[_repo("Aspose.PDF-FOSS-for-Python")], apply=True)
    finally:
        repo_patrol.configure()

    registry = json.loads((tmp_path / "data" / "products.json").read_text(encoding="utf-8"))
    assert registry[0]["family"] == "pdf"
    assert registry[0]["platform"] == "python"


def test_cmd_sweep_uses_clone_cache_functions(tmp_path):
    repo_patrol.configure(repo_root=tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "products.json").write_text(json.dumps([_registry_entry()]), encoding="utf-8")
    try:
        with patch("core.clone_cache.clone_exists", return_value=True), \
             patch("core.clone_cache.update_clone", return_value="def456"), \
             patch("core.clone_cache.clone_head_sha", return_value="def456"):
            report = repo_patrol.cmd_sweep()
    finally:
        repo_patrol.configure()

    assert report["summary"]["changed"] == 1
    assert (tmp_path / "reports" / "discovery" / "sweep_report.json").exists()


def test_cmd_report_combines_existing_reports(tmp_path):
    repo_patrol.configure(repo_root=tmp_path)
    report_dir = tmp_path / "reports" / "discovery"
    report_dir.mkdir(parents=True)
    (report_dir / "patrol_report.json").write_text(json.dumps({"summary": {"new_candidates": 1}}), encoding="utf-8")
    (report_dir / "sweep_report.json").write_text(json.dumps({"summary": {"changed": 2}}), encoding="utf-8")
    try:
        md = repo_patrol.cmd_report()
    finally:
        repo_patrol.configure()

    assert "Patrol Scan" in md
    assert "Change Sweep" in md
    assert (report_dir / "combined_report.md").exists()


def test_legacy_wrapper_report_cli(tmp_path):
    report_dir = tmp_path / "reports" / "discovery"
    report_dir.mkdir(parents=True)
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "repo_patrol.py"),
            "report",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={},
    )

    assert result.returncode == 0, result.stderr
