import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
DAR = REPO_ROOT / "scripts" / "ci" / "checks" / "check_dar_coverage.py"
DISPLAY = REPO_ROOT / "scripts" / "ci" / "checks" / "check_family_display_names.py"
BLOG = REPO_ROOT / "check-blog-slugs.py"


def test_family_display_names_pass_and_fail(tmp_path):
    taxonomy = tmp_path / "taxonomy.yaml"
    taxonomy.write_text(yaml.safe_dump({"products": {"cells": "Aspose.Cells"}}), encoding="utf-8")
    index = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "_index.md"
    index.parent.mkdir(parents=True)
    index.write_text("---\ntitle: Aspose.Cells FOSS\n---\n", encoding="utf-8")

    ok = subprocess.run(
        [sys.executable, str(DISPLAY), "--content-root", str(tmp_path / "content"), "--taxonomy", str(taxonomy)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr

    index.write_text("---\ntitle: Cells\nlinkTitle: Cells\n---\n", encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, str(DISPLAY), "--content-root", str(tmp_path / "content"), "--taxonomy", str(taxonomy)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1
    assert "V-01" in bad.stdout
    assert "V-02" in bad.stdout


def test_blog_slug_checker_pass_and_fail(tmp_path):
    good = tmp_path / "content" / "blog.aspose.org" / "cells" / "python" / "post" / "index.md"
    good.parent.mkdir(parents=True)
    good.write_text(
        "---\ntitle: Good\nevidence:\n  claims: [CLM-1]\n  apis: [Workbook]\n---\n",
        encoding="utf-8",
    )
    ok = subprocess.run(
        [sys.executable, str(BLOG), "--content-root", str(tmp_path / "content")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr

    bad = tmp_path / "content" / "blog.aspose.org" / "cells" / "python" / "bad.md"
    bad.write_text("---\ntitle: Bad\naliases: [/test/path]\nevidence:\n  claims: []\n  apis: []\n---\n", encoding="utf-8")
    fail = subprocess.run(
        [sys.executable, str(BLOG), "--content-root", str(tmp_path / "content")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert fail.returncode == 1
    assert "P-05" in fail.stdout
    assert "P-06" in fail.stdout
    assert "P-03" in fail.stdout
    assert "P-04" in fail.stdout


def test_dar_coverage_detects_unregistered_skill(tmp_path):
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "needs-bootstrap.md").write_text("Run /knowledge-bootstrap first.\n", encoding="utf-8")
    (tmp_path / "skills" / "registry.yaml").write_text("skills: []\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Governance\nNo DAR table here.\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(DAR), "--repo-root", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "MISSING_DAR_ENTRY" in result.stdout
    assert "SKILL_NOT_IN_REGISTRY" in result.stdout
