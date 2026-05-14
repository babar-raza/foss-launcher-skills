import json
import subprocess
import sys
from pathlib import Path

from scripts.pipeline.commands.content import batch_reference

REPO_ROOT = Path(__file__).resolve().parent.parent


def _api_surface(repo_root: Path) -> Path:
    target = repo_root / "knowledge" / "sample" / "python" / "merged"
    target.mkdir(parents=True, exist_ok=True)
    path = target / "api_surface.json"
    path.write_text(
        json.dumps({
            "classes": [
                {"name": "DocumentBuilder", "kind": "class_definition"},
                {"name": "SaveFormat", "kind": "enum_declaration"},
            ]
        }),
        encoding="utf-8",
    )
    return path


def test_collect_candidates_from_api_surface(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_reference, "REPO_ROOT", tmp_path)
    _api_surface(tmp_path)
    content_root = tmp_path / "content"

    candidates = batch_reference.collect_candidates("sample", "python", content_root=content_root)

    assert [item.name for item in candidates] == ["DocumentBuilder", "SaveFormat"]
    assert candidates[0].output_path == content_root / "reference.aspose.org" / "en" / "sample" / "python" / "document-builder.md"


def test_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_reference, "REPO_ROOT", tmp_path)
    _api_surface(tmp_path)
    content_root = tmp_path / "content"

    report = batch_reference.run("sample", "python", dry_run=True, content_root=content_root, limit=1)

    assert report["summary"]["generated"] == 1
    assert not (content_root / "reference.aspose.org").exists()


def test_write_uses_redirected_content_root(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_reference, "REPO_ROOT", tmp_path)
    _api_surface(tmp_path)
    content_root = tmp_path / "content"

    report = batch_reference.run("sample", "python", dry_run=False, content_root=content_root, kind="class")

    output = content_root / "reference.aspose.org" / "en" / "sample" / "python" / "document-builder.md"
    assert report["summary"]["generated"] == 1
    assert output.exists()
    assert "layout: reference-single" in output.read_text(encoding="utf-8")


def test_existing_pages_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_reference, "REPO_ROOT", tmp_path)
    _api_surface(tmp_path)
    content_root = tmp_path / "content"
    output = content_root / "reference.aspose.org" / "en" / "sample" / "python" / "document-builder.md"
    output.parent.mkdir(parents=True)
    output.write_text("existing", encoding="utf-8")

    report = batch_reference.run("sample", "python", dry_run=False, content_root=content_root, kind="class")

    assert report["summary"]["generated"] == 0
    assert report["summary"]["skipped_existing"] == 1
    assert output.read_text(encoding="utf-8") == "existing"


def test_cli_dry_run(tmp_path):
    # CLI execution uses the real repo root; create a temporary product whose
    # generated output is redirected to tmp_path and whose knowledge fixture is
    # cleaned up after the assertion.
    fixture = _api_surface(REPO_ROOT)
    content_root = tmp_path / "content"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "content" / "batch_reference.py"),
            "sample",
            "python",
            "--content-root",
            str(content_root),
            "--dry-run",
            "--limit",
            "1",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "batch-reference summary" in result.stdout
    assert not (content_root / "reference.aspose.org").exists()
    fixture.unlink(missing_ok=True)
    for parent in [fixture.parent, fixture.parent.parent, fixture.parent.parent.parent, fixture.parent.parent.parent.parent]:
        try:
            parent.rmdir()
        except OSError:
            pass
