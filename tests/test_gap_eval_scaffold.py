import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "scripts" / "gap-eval" / "src" / "run.py"
VALIDATOR = REPO_ROOT / "scripts" / "gap-eval" / "src" / "validate_profile.py"


def _content_root(tmp_path: Path) -> Path:
    root = tmp_path / "content"
    page = root / "docs.aspose.org" / "en" / "sample" / "python" / "intro.md"
    page.parent.mkdir(parents=True)
    page.write_text("---\ntitle: Intro\n---\n\nBody\n", encoding="utf-8")
    return root


def test_validate_profile_sample():
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "sample", "python", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_gap_eval_dry_run_discovers_content_without_writes(tmp_path):
    content_root = _content_root(tmp_path)
    output_root = tmp_path / "reports"

    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "sample",
            "python",
            "--scope",
            "docs",
            "--content-root",
            str(content_root),
            "--output-root",
            str(output_root),
            "--no-llm",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["discovered_counts"]["docs"] == 1
    assert payload["tier_3_llm"] == "disabled"
    assert not output_root.exists()


def test_gap_eval_writes_to_redirected_output_root(tmp_path):
    content_root = _content_root(tmp_path)
    output_root = tmp_path / "reports"

    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "sample",
            "python",
            "--scope",
            "docs",
            "--content-root",
            str(content_root),
            "--output-root",
            str(output_root),
            "--no-llm",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = output_root / "gap-analysis" / "sample-python.json"
    markdown = output_root / "gap-analysis" / "sample-python.md"
    assert report.exists()
    assert markdown.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["discovered_counts"]["docs"] == 1
    assert "Gap Eval Report" in markdown.read_text(encoding="utf-8")


def test_top_level_compatibility_wrappers(tmp_path):
    content_root = _content_root(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "gap-eval" / "run.py"),
            "sample",
            "python",
            "--scope",
            "docs",
            "--content-root",
            str(content_root),
            "--no-llm",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["runner"] == "standalone-gap-eval-scaffold"
