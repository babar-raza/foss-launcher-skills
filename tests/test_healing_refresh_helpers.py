import json
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.pipeline.lib.heal_controller import HealController, resolve_hint


REPO_ROOT = Path(__file__).resolve().parent.parent
RETIRE = REPO_ROOT / "scripts" / "pipeline" / "commands" / "healing" / "retire_page.py"
REFRESH = REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "refresh_review.py"


def _page(path: Path, *, draft: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = {"title": "Sample"}
    if draft:
        frontmatter["draft"] = True
        frontmatter["retired_at"] = "2026-01-01"
    path.write_text("---\n" + yaml.safe_dump(frontmatter, sort_keys=False) + "---\nBody\n", encoding="utf-8")
    return path


def test_retire_page_dry_run_does_not_modify(tmp_path):
    page = _page(tmp_path / "content" / "docs.aspose.org" / "en" / "sample" / "python" / "guide.md")
    before = page.read_text(encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(RETIRE), str(page), "--dry-run", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == "dry_run"
    assert page.read_text(encoding="utf-8") == before


def test_retire_and_unretire_page(tmp_path):
    page = _page(tmp_path / "content" / "docs.aspose.org" / "en" / "sample" / "python" / "guide.md")

    retire = subprocess.run(
        [sys.executable, str(RETIRE), str(page), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert retire.returncode == 0, retire.stderr
    assert json.loads(retire.stdout) == "retired"
    assert "draft: true" in page.read_text(encoding="utf-8")

    unretire = subprocess.run(
        [sys.executable, str(RETIRE), str(page), "--un-retire", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert unretire.returncode == 0, unretire.stderr
    assert json.loads(unretire.stdout) == "un_retired"
    assert "draft: true" not in page.read_text(encoding="utf-8")


def test_retire_from_plan_uses_redirected_repo_root(tmp_path):
    page = _page(tmp_path / "content" / "docs.aspose.org" / "en" / "sample" / "python" / "old.md")
    plan = tmp_path / "site_plan.yaml"
    plan.write_text(
        yaml.safe_dump({"plan": {"delta": {"pages_to_remove": ["content/docs.aspose.org/en/sample/python/old.md"]}}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(RETIRE), "--from-plan", str(plan), "--repo-root", str(tmp_path), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["retired"] == 1
    assert "draft: true" in page.read_text(encoding="utf-8")


def test_refresh_review_records_and_reports(tmp_path):
    review_root = tmp_path / "refresh_review"

    record = subprocess.run(
        [
            sys.executable,
            str(REFRESH),
            "sample",
            "python",
            "--record-decision",
            "--path",
            "content/docs.aspose.org/en/sample/python/guide.md",
            "--decision",
            "BODY_UPDATED",
            "--reason",
            "fixture",
            "--body-changed",
            "--review-root",
            str(review_root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert record.returncode == 0, record.stderr

    report = subprocess.run(
        [sys.executable, str(REFRESH), "sample", "python", "--report", "--review-root", str(review_root)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert report.returncode == 0, report.stderr
    assert "| docs | 1 | 1 | 0 | 0 | 0 |" in report.stdout
    assert (review_root / "sample" / "python" / "coverage_report.md").exists()


def test_heal_controller_resolves_hints_and_groups_findings():
    resolution = resolve_hint(
        {
            "violation_type": "missing_skill_context",
            "suggested_skill": "page-enhance",
            "path": "content/docs.aspose.org/en/sample/python/guide.md",
        }
    )
    assert resolution.action == "run_command"
    assert resolution.run_argv[:3] == ["skill_context.py", "begin", "--skill"]

    plan = HealController().plan(
        [
            {"id": "F1", "category": "AA", "filepath": "a.md"},
            {"id": "F2", "category": "UPSTREAM", "filepath": "b.md"},
            {"id": "F3", "severity": "I", "filepath": "c.md"},
            {"id": "F4", "category": "AA", "heal_depth": 3, "filepath": "d.md"},
        ]
    )
    payload = plan.to_dict()
    assert payload["total_findings"] == 4
    assert payload["total_enabled"] == 2
    assert len(payload["groups"]["llm"]) == 1
    assert len(payload["groups"]["regen"]) == 1
    assert len(payload["groups"]["human"]) == 1
