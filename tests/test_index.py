"""Tests for scripts/index.py — knowledge index generation."""
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import index as ix  # noqa: E402

FIXTURE_KNOWLEDGE = REPO_ROOT / "tests" / "fixtures" / "knowledge"


# ---------------------------------------------------------------------------
# Helper: copy fixture merged/ into tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture()
def knowledge_root(tmp_path):
    """Copy fixture knowledge dir into a fresh tmp_path for each test.

    FIXTURE_KNOWLEDGE = tests/fixtures/knowledge/
      └── words/python/merged/   ← already at correct depth

    After copy: tmp_path/words/python/merged/
    monkeypatching KNOWLEDGE_ROOT → tmp_path makes build_index resolve correctly.
    """
    shutil.copytree(FIXTURE_KNOWLEDGE, tmp_path, dirs_exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# _install_command
# ---------------------------------------------------------------------------

def test_install_command_python():
    cmd = ix._install_command("words", "python")
    assert cmd.startswith("pip install")
    assert "words" in cmd


def test_install_command_typescript():
    cmd = ix._install_command("cells", "typescript")
    assert cmd.startswith("npm install")


def test_install_command_dotnet():
    cmd = ix._install_command("pdf", "dotnet")
    assert "dotnet add package" in cmd


# ---------------------------------------------------------------------------
# _display_name
# ---------------------------------------------------------------------------

def test_display_name_words():
    assert ix._display_name("words") == "Aspose.Words"


def test_display_name_3d():
    assert ix._display_name("3d") == "Aspose.3D"


def test_display_name_pdf():
    assert ix._display_name("pdf") == "Aspose.Pdf"


# ---------------------------------------------------------------------------
# build_index
# ---------------------------------------------------------------------------

def test_build_index_writes_index_json(knowledge_root, monkeypatch):
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", knowledge_root)
    result = ix.build_index("words", "python")
    index_file = knowledge_root / "words" / "python" / "merged" / "index.json"
    assert index_file.exists(), "index.json should be created"


def test_build_index_returns_dict(knowledge_root, monkeypatch):
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", knowledge_root)
    result = ix.build_index("words", "python")
    assert isinstance(result, dict)


def test_build_index_required_fields(knowledge_root, monkeypatch):
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", knowledge_root)
    result = ix.build_index("words", "python")
    for key in ("family", "platform", "display_name", "api_confidence"):
        assert key in result, f"Missing field: {key}"


def test_build_index_family_platform(knowledge_root, monkeypatch):
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", knowledge_root)
    result = ix.build_index("words", "python")
    assert result["family"] == "words"
    assert result["platform"] == "python"


def test_build_index_json_is_valid(knowledge_root, monkeypatch):
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", knowledge_root)
    ix.build_index("words", "python")
    index_file = knowledge_root / "words" / "python" / "merged" / "index.json"
    data = json.loads(index_file.read_text())
    assert "family" in data
    assert "platform" in data
    assert "classes" in data
    assert "formats" in data


def test_build_index_skips_missing_model(tmp_path, monkeypatch):
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", tmp_path)
    result = ix.build_index("nonexistent", "python")
    assert result is None


def test_build_index_classes_list(knowledge_root, monkeypatch):
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", knowledge_root)
    ix.build_index("words", "python")
    index_file = knowledge_root / "words" / "python" / "merged" / "index.json"
    data = json.loads(index_file.read_text())
    assert "Document" in data["classes"]


# ---------------------------------------------------------------------------
# discover_products
# ---------------------------------------------------------------------------

def test_discover_products_finds_fixture(knowledge_root, monkeypatch):
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", knowledge_root)
    products = ix.discover_products()
    assert ("words", "python") in products


def test_discover_products_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", tmp_path)
    products = ix.discover_products()
    assert products == []
