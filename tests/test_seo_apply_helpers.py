import json
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
APPLY = REPO_ROOT / "scripts" / "seo" / "pipeline" / "apply.py"
SAFETY = REPO_ROOT / "scripts" / "seo" / "pipeline" / "safety.py"


def _page(tmp_path: Path) -> Path:
    page = tmp_path / "content" / "products.aspose.org" / "en" / "cells" / "_index.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "---\ntitle: Cells\nevidence:\n  claims: [CLM-1]\n  apis: [Workbook]\ntags: [existing]\n---\nBody\n",
        encoding="utf-8",
    )
    return page


def _manifest(tmp_path: Path, page: Path, *, bad: bool = False) -> Path:
    manifest = tmp_path / "patches" / "seo" / "patch_manifest.json"
    manifest.parent.mkdir(parents=True)
    fields = {
        "seoTitle": "Aspose.Cells FOSS for Python",
        "description": "Learn how Aspose.Cells FOSS for Python helps inspect spreadsheets, work with workbook data, and automate document workflows safely.",
        "tags_to_add": ["aspose cells"],
    }
    if bad:
        fields["evidence"] = {"claims": []}
    manifest.write_text(
        json.dumps(
            {
                "batch_id": "test",
                "total_patches": 1,
                "patches": [
                    {
                        "page_path": str(page.relative_to(tmp_path)).replace("\\", "/"),
                        "fields_to_update": fields,
                        "requires_human_review": False,
                        "safety_checks_passed": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_seo_apply_dry_run_does_not_modify(tmp_path):
    page = _page(tmp_path)
    manifest = _manifest(tmp_path, page)
    before = page.read_text(encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(APPLY), "--manifest", str(manifest), "--repo-root", str(tmp_path), "--dry-run", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["changed"] == 1
    assert page.read_text(encoding="utf-8") == before


def test_seo_apply_explicit_apply_updates_frontmatter(tmp_path):
    page = _page(tmp_path)
    manifest = _manifest(tmp_path, page)

    result = subprocess.run(
        [sys.executable, str(APPLY), "--manifest", str(manifest), "--repo-root", str(tmp_path), "--apply", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    text = page.read_text(encoding="utf-8")
    data = yaml.safe_load(text.split("---", 2)[1])
    assert data["seoTitle"] == "Aspose.Cells FOSS for Python"
    assert "aspose cells" in data["tags"]
    assert data["evidence"]["claims"] == ["CLM-1"]


def test_seo_safety_rejects_protected_fields(tmp_path):
    page = _page(tmp_path)
    manifest = _manifest(tmp_path, page, bad=True)

    result = subprocess.run(
        [sys.executable, str(SAFETY), str(manifest)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "unknown fields" in payload["issues"][0]["error"] or "protected fields" in payload["issues"][0]["error"]


def test_root_apply_wrapper_runs(tmp_path):
    page = _page(tmp_path)
    manifest = _manifest(tmp_path, page)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "apply.py"), "--manifest", str(manifest), "--repo-root", str(tmp_path), "--dry-run", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["total"] == 1
