import subprocess
import sys
from pathlib import Path

from scripts.pipeline.commands.content.validate_plugin_structure import check_file
from scripts.pipeline.commands.migration.complete_plugin_structure import complete_file

REPO_ROOT = Path(__file__).resolve().parent.parent


def _plugin_page(tmp_path: Path, *, english=True, complete=False, body="") -> Path:
    locale = "en" if english else "fr"
    path = tmp_path / "content" / "products.aspose.org" / locale / "sample" / "python" / "_index.md"
    path.parent.mkdir(parents=True)
    optional = ""
    if complete:
        optional = (
            "supportandlearning:\n  enable: true\n"
            "more_formats:\n  enable: true\n"
            "back_to_top:\n  enable: true\n"
        )
    path.write_text(
        "---\n"
        "layout: plugin\n"
        'family_name: "Sample FOSS"\n'
        'plugin_description: "Sample desc"\n'
        'plugin_platform: "Python"\n'
        'head_title: "Sample"\n'
        'head_description: "Sample desc"\n'
        'title: "Sample"\n'
        'description: "Sample"\n'
        'github_url: "https://github.com/sample"\n'
        "submenu:\n  enable: true\n"
        "overview:\n  enable: true\n  title: Overview\n  content: Text\n"
        "content:\n  enable: true\n  block:\n  - title_left: Feature\n"
        "single:\n  enable: true\n  block:\n  - title: Example\n"
        f"{optional}"
        "provenance:\n  content_origin: skill-generated\n"
        "evidence:\n  model_sha: abc\n"
        "---\n"
        f"{body}",
        encoding="utf-8",
    )
    return path


def test_complete_plugin_structure_adds_display_sections(tmp_path):
    page = _plugin_page(tmp_path, complete=False)

    assert complete_file(page) is True
    text = page.read_text(encoding="utf-8")

    assert "supportandlearning:" in text
    assert "more_formats:" in text
    assert "back_to_top:" in text
    assert text.index("supportandlearning:") < text.index("provenance:")


def test_complete_plugin_structure_idempotent_and_dry_run(tmp_path):
    page = _plugin_page(tmp_path, complete=False)
    original = page.read_text(encoding="utf-8")

    assert complete_file(page, dry_run=True) is True
    assert page.read_text(encoding="utf-8") == original

    assert complete_file(page) is True
    after = page.read_text(encoding="utf-8")
    assert complete_file(page) is False
    assert page.read_text(encoding="utf-8") == after


def test_validate_plugin_structure_complete_english_page_passes(tmp_path):
    page = _plugin_page(tmp_path, complete=True)

    findings = check_file(page)

    assert [item for item in findings if item.severity in {"FATAL", "ERROR"}] == []


def test_validate_plugin_structure_missing_display_is_error_for_english(tmp_path):
    page = _plugin_page(tmp_path, complete=False)

    findings = check_file(page)
    errors = [item for item in findings if item.severity == "ERROR" and item.check_id == "MISSING_DISPLAY"]

    assert len(errors) == 3


def test_validate_plugin_structure_missing_display_is_warn_for_locale(tmp_path):
    page = _plugin_page(tmp_path, english=False, complete=False)

    findings = check_file(page)
    errors = [item for item in findings if item.severity == "ERROR"]
    warnings = [item for item in findings if item.severity == "WARN" and item.check_id == "MISSING_DISPLAY"]

    assert errors == []
    assert len(warnings) == 3


def test_validate_plugin_structure_body_leak_is_fatal(tmp_path):
    page = _plugin_page(tmp_path, complete=True, body="overview:\n  leaked\n")

    findings = check_file(page)

    assert any(item.severity == "FATAL" and item.check_id == "BODY_LEAK" for item in findings)


def test_legacy_wrappers_execute(tmp_path):
    page = _plugin_page(tmp_path, complete=False)

    complete = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "complete_plugin_structure.py"),
            "--files",
            str(page),
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert complete.returncode == 0, complete.stderr

    validate = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "validate_plugin_structure.py"),
            "--files",
            str(page),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert validate.returncode == 1
    assert "MISSING_DISPLAY" in validate.stdout
