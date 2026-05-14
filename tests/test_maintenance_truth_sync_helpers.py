import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
REBUILD = REPO_ROOT / "scripts" / "maintenance" / "rebuild_snippet_index.py"
TRUTH = REPO_ROOT / "scripts" / "pipeline" / "commands" / "diagnostics" / "truth_audit_content.py"
SYNC = REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "sync_skills.py"
BOOTSTRAP = REPO_ROOT / "scripts" / "ci" / "hooks" / "bootstrap_session_gate.sh"


def test_rebuild_snippet_index_from_fixture(tmp_path):
    knowledge = tmp_path / "knowledge"
    snippets = knowledge / "cells" / "python" / "scout" / "snippets"
    snippets.mkdir(parents=True)
    (snippets / "snippet_0001_demo.py").write_text("book = Workbook()\nbook.save('out.xlsx')\n", encoding="utf-8")
    merged = knowledge / "cells" / "python" / "merged"
    merged.mkdir(parents=True)
    (merged / "api_surface.json").write_text(
        json.dumps([{"name": "Workbook", "methods": [{"name": "save"}]}]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(REBUILD), "cells", "python", "--knowledge-root", str(knowledge)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    index = json.loads((snippets / "snippets_index.json").read_text(encoding="utf-8"))
    assert index[0]["classes_used"] == ["Workbook"]
    assert index[0]["methods_used"] == ["Workbook.save"]


def _content_fixture(tmp_path: Path) -> Path:
    page = tmp_path / "content" / "docs.aspose.org" / "en" / "cells" / "python" / "guide.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Guide\n\nAspose supports `Workbook.save()`.\n\n```python\nprint('x')\n```\n", encoding="utf-8")
    return tmp_path / "content"


def test_truth_audit_content_dry_run_and_output(tmp_path):
    content = _content_fixture(tmp_path)
    dry = subprocess.run(
        [sys.executable, str(TRUTH), "cells", "python", "--scope", "docs", "--content-root", str(content), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert dry.returncode == 0, dry.stderr
    payload = json.loads(dry.stdout)
    assert payload["read_only"] is True
    assert payload["unit_count"] == 3

    out = tmp_path / "reports"
    write = subprocess.run(
        [sys.executable, str(TRUTH), "cells", "python", "--scope", "docs", "--content-root", str(content), "--output-root", str(out)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert write.returncode == 0, write.stderr
    assert any((out / "truth-audit").glob("cells-python-*.json"))
    assert (out / "truth-audit" / "state" / "cells-python.json").exists()


def test_sync_skills_wrapper_check_passes():
    result = subprocess.run(
        [sys.executable, str(SYNC), "--check", "--repo-root", str(REPO_ROOT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_bootstrap_session_gate_fixture(tmp_path):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if not git_bash.exists():
        pytest.skip("Git for Windows bash is not available")
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (tmp_path / "skills").mkdir()
    result = subprocess.run(
        [str(git_bash), str(BOOTSTRAP), str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
