import json
import subprocess
import sys
from pathlib import Path

from scripts.pipeline.commands.content.cross_platform_audit import compare_family, to_markdown

REPO_ROOT = Path(__file__).resolve().parent.parent


def _formats(root: Path, family: str, platform: str, rows: list[dict]):
    target = root / family / platform / "merged"
    target.mkdir(parents=True)
    (target / "formats.json").write_text(json.dumps(rows), encoding="utf-8")


def test_compare_family_detects_format_mismatch(tmp_path):
    _formats(tmp_path, "slides", "python", [{"format": "pdf", "support": "export"}])
    _formats(tmp_path, "slides", "java", [{"format": "pdf", "support": "both"}])

    report = compare_family("slides", knowledge_root=tmp_path)

    assert report["issue_count"] == 1
    assert report["issues"][0]["format"] == "pdf"


def test_compare_family_no_issues_when_support_matches(tmp_path):
    _formats(tmp_path, "slides", "python", [{"ext": "pdf", "support": "export"}])
    _formats(tmp_path, "slides", "java", [{"ext": "pdf", "support": "export"}])

    assert compare_family("slides", knowledge_root=tmp_path)["issue_count"] == 0


def test_markdown_contains_issue_table(tmp_path):
    report = {
        "family": "slides",
        "platforms_scanned": ["java", "python"],
        "issue_count": 1,
        "issues": [{"format": "pdf", "platforms": {"java": "both", "python": "export"}}],
    }

    md = to_markdown(report)

    assert "| `pdf` |" in md


def test_cli_json_writes_output_and_returns_one_on_issue(tmp_path):
    _formats(tmp_path, "slides", "python", [{"format": "pdf", "support": "export"}])
    _formats(tmp_path, "slides", "java", [{"format": "pdf", "support": "both"}])
    output = tmp_path / "report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "content" / "cross_platform_audit.py"),
            "slides",
            "--knowledge-root",
            str(tmp_path),
            "--json",
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["issue_count"] == 1
