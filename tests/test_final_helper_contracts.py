import json
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
PROV = REPO_ROOT / "scripts" / "pipeline" / "commands" / "migration" / "provenance_backfill.py"
PIA = REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "page_impact_assess.py"
HUGO = REPO_ROOT / "scripts" / "ci" / "hooks" / "check_hugo_build.sh"


def test_provenance_backfill_dry_run_and_apply(tmp_path):
    page = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "python" / "guide.md"
    page.parent.mkdir(parents=True)
    page.write_text("---\ntitle: Guide\n---\nBody\n", encoding="utf-8")

    dry = subprocess.run(
        [sys.executable, str(PROV), "--content-root", str(tmp_path / "content"), "--dry-run", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert dry.returncode == 0, dry.stderr
    assert json.loads(dry.stdout)["backfilled"] == 1
    assert "provenance" not in page.read_text(encoding="utf-8")

    apply = subprocess.run(
        [sys.executable, str(PROV), "--content-root", str(tmp_path / "content"), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert apply.returncode == 0, apply.stderr
    data = yaml.safe_load(page.read_text(encoding="utf-8").split("---", 2)[1])
    assert data["provenance"]["content_origin"] == "unknown"


def test_page_impact_assess_scores_fixture(tmp_path):
    page = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "python" / "guide.md"
    page.parent.mkdir(parents=True)
    page.write_text("Workbook save tutorial\n", encoding="utf-8")
    delta = tmp_path / "knowledge" / "cells" / "python" / "merged" / "knowledge_delta.json"
    delta.parent.mkdir(parents=True)
    delta.write_text(json.dumps({"modified_apis": [{"name": "Workbook"}]}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(PIA),
            "cells",
            "python",
            "--content-root",
            str(tmp_path / "content"),
            "--knowledge-root",
            str(tmp_path / "knowledge"),
            "--output-root",
            str(tmp_path / "reports"),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["pages"][0]["pia_score"] == "HIGH_IMPACT"
    assert (tmp_path / "reports" / "refresh_review" / "cells" / "python" / "page_impact.json").exists()


def test_hugo_build_hook_skips_missing_config():
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if not git_bash.exists():
        return
    result = subprocess.run(
        [str(git_bash), str(HUGO), "nonexistent.aspose.org"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "SKIP" in result.stdout
