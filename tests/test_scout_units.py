"""Unit tests for scripts/scout.py — tree-sitter extraction.

Tree-sitter is required. Tests are skipped if it is not installed.
Integration test: runs scout.py on the minimal fixture repo and checks outputs.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_REPO = REPO_ROOT / "tests" / "fixtures" / "repo"
SCOUT_SCRIPT = REPO_ROOT / "scripts" / "scout.py"

# ---------------------------------------------------------------------------
# Check tree-sitter availability
# ---------------------------------------------------------------------------

try:
    _check = subprocess.run(
        [sys.executable, "-c",
         "import tree_sitter; import tree_sitter_language_pack"],
        capture_output=True, text=True, timeout=10,
    )
    HAS_TREE_SITTER = _check.returncode == 0
except Exception:
    HAS_TREE_SITTER = False

requires_tree_sitter = pytest.mark.skipif(
    not HAS_TREE_SITTER,
    reason="tree-sitter not installed (run: pip install -r scripts/requirements.txt)",
)

# Also mark all tree-sitter tests with @pytest.mark.scout for selective filtering
pytestmark = pytest.mark.scout


# ---------------------------------------------------------------------------
# Integration: run scout.py on fixture repo
# ---------------------------------------------------------------------------

@requires_tree_sitter
def test_scout_runs_without_error(tmp_path):
    """scout.py should exit 0 on the fixture repo."""
    result = subprocess.run(
        [sys.executable, str(SCOUT_SCRIPT), "words", "python",
         str(FIXTURE_REPO), str(tmp_path / "scout")],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"scout.py failed:\n{result.stderr}"


@requires_tree_sitter
def test_scout_creates_model_yaml(tmp_path):
    out_dir = tmp_path / "scout"
    subprocess.run(
        [sys.executable, str(SCOUT_SCRIPT), "words", "python",
         str(FIXTURE_REPO), str(out_dir)],
        capture_output=True, cwd=str(REPO_ROOT),
    )
    assert (out_dir / "model.yaml").exists()


@requires_tree_sitter
def test_scout_creates_api_surface(tmp_path):
    out_dir = tmp_path / "scout"
    subprocess.run(
        [sys.executable, str(SCOUT_SCRIPT), "words", "python",
         str(FIXTURE_REPO), str(out_dir)],
        capture_output=True, cwd=str(REPO_ROOT),
    )
    assert (out_dir / "api_surface.json").exists()


@requires_tree_sitter
def test_scout_creates_claims(tmp_path):
    out_dir = tmp_path / "scout"
    subprocess.run(
        [sys.executable, str(SCOUT_SCRIPT), "words", "python",
         str(FIXTURE_REPO), str(out_dir)],
        capture_output=True, cwd=str(REPO_ROOT),
    )
    assert (out_dir / "claims.json").exists()


@requires_tree_sitter
def test_scout_model_has_family_and_platform(tmp_path):
    import yaml
    out_dir = tmp_path / "scout"
    subprocess.run(
        [sys.executable, str(SCOUT_SCRIPT), "words", "python",
         str(FIXTURE_REPO), str(out_dir)],
        capture_output=True, cwd=str(REPO_ROOT),
    )
    model = yaml.safe_load((out_dir / "model.yaml").read_text())
    assert model.get("family") == "words"
    assert model.get("platform") == "python"


@requires_tree_sitter
def test_scout_api_surface_finds_document_class(tmp_path):
    import json
    out_dir = tmp_path / "scout"
    subprocess.run(
        [sys.executable, str(SCOUT_SCRIPT), "words", "python",
         str(FIXTURE_REPO), str(out_dir)],
        capture_output=True, cwd=str(REPO_ROOT),
    )
    api = json.loads((out_dir / "api_surface.json").read_text())
    names = [e.get("name", "") for e in api if isinstance(e, dict)]
    assert "Document" in names, f"Expected 'Document' in api_surface, got: {names}"


# ---------------------------------------------------------------------------
# Pure constants (no tree-sitter needed)
# ---------------------------------------------------------------------------

def test_platform_to_lang_has_python():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import scout
    assert "python" in scout.PLATFORM_TO_LANG
    assert scout.PLATFORM_TO_LANG["python"] == "python"


def test_platform_to_lang_has_dotnet():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import scout
    assert "dotnet" in scout.PLATFORM_TO_LANG
    assert scout.PLATFORM_TO_LANG["dotnet"] == "csharp"


# ---------------------------------------------------------------------------
# New feature tests: enums, dataclass fields, property setters, constants
# ---------------------------------------------------------------------------

def _run_scout_on_fixture(tmp_path):
    """Helper: run scout on fixture repo and return output dir."""
    out_dir = tmp_path / "scout"
    result = subprocess.run(
        [sys.executable, str(SCOUT_SCRIPT), "words", "python",
         str(FIXTURE_REPO), str(out_dir)],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"scout.py failed:\n{result.stderr}"
    return out_dir


@requires_tree_sitter
def test_scout_extracts_python_enum_members(tmp_path):
    """Enum classes with IntEnum bases should have enum_members populated."""
    import json
    out_dir = _run_scout_on_fixture(tmp_path)
    api = json.loads((out_dir / "api_surface.json").read_text())
    color = next((c for c in api if c["name"] == "Color"), None)
    assert color is not None, "Color class not found"
    members = color.get("enum_members", [])
    assert len(members) == 3
    names = {m["name"] for m in members}
    assert names == {"RED", "GREEN", "BLUE"}


@requires_tree_sitter
def test_scout_enum_count_in_model(tmp_path):
    """model.yaml enum_count should reflect Python enums."""
    import yaml
    out_dir = _run_scout_on_fixture(tmp_path)
    model = yaml.safe_load((out_dir / "model.yaml").read_text())
    assert model["stats"]["enum_count"] >= 2  # Color + FileFormat


@requires_tree_sitter
def test_scout_extracts_dataclass_fields(tmp_path):
    """Dataclass typed fields should appear as properties with kind=field."""
    import json
    out_dir = _run_scout_on_fixture(tmp_path)
    api = json.loads((out_dir / "api_surface.json").read_text())
    ps = next((c for c in api if c["name"] == "PageSettings"), None)
    assert ps is not None, "PageSettings class not found"
    props = ps.get("properties", [])
    field_names = {p["name"] for p in props}
    assert "width" in field_names
    assert "height" in field_names
    assert "margin" in field_names
    assert "orientation" in field_names


@requires_tree_sitter
def test_scout_skips_private_dataclass_fields(tmp_path):
    """Fields starting with _ should be excluded."""
    import json
    out_dir = _run_scout_on_fixture(tmp_path)
    api = json.loads((out_dir / "api_surface.json").read_text())
    meta = next((c for c in api if c["name"] == "Metadata"), None)
    assert meta is not None
    field_names = {p["name"] for p in meta.get("properties", [])}
    assert "_internal" not in field_names
    assert "title" in field_names


@requires_tree_sitter
def test_scout_detects_property_setters(tmp_path):
    """Properties with @name.setter should have read_write=True."""
    import json
    out_dir = _run_scout_on_fixture(tmp_path)
    api = json.loads((out_dir / "api_surface.json").read_text())
    st = next((c for c in api if c["name"] == "StyledText"), None)
    assert st is not None, "StyledText class not found"
    props = {p["name"]: p for p in st.get("properties", [])}
    assert props["name"]["read_write"] is True
    assert props["size"]["read_write"] is False


@requires_tree_sitter
def test_scout_extracts_module_constants(tmp_path):
    """Module-level UPPER_CASE constants should appear in constants.json."""
    import json
    out_dir = _run_scout_on_fixture(tmp_path)
    consts = json.loads((out_dir / "constants.json").read_text())
    names = {c["name"] for c in consts}
    assert "MAX_PAGES" in names
    assert "DEFAULT_ENCODING" in names
    assert "DOCX" in names
    # Private constants should be excluded
    assert "_INTERNAL_FLAG" not in names


@requires_tree_sitter
def test_scout_constants_exported_flag(tmp_path):
    """Constants in __all__ should have exported=True."""
    import json
    out_dir = _run_scout_on_fixture(tmp_path)
    consts = json.loads((out_dir / "constants.json").read_text())
    by_name = {c["name"]: c for c in consts}
    assert by_name["MAX_PAGES"]["exported"] is True
    assert by_name["DOCX"]["exported"] is False


@requires_tree_sitter
def test_scout_format_enum_detection(tmp_path):
    """FileFormat IntEnum members should appear in formats.json."""
    import json
    out_dir = _run_scout_on_fixture(tmp_path)
    fmts = json.loads((out_dir / "formats.json").read_text())
    fmt_names = {f["format"] for f in fmts}
    assert "DOCX" in fmt_names
    assert "PDF" in fmt_names


# ---------------------------------------------------------------------------
# Pipeline integration: scout → merge → index
# ---------------------------------------------------------------------------

@requires_tree_sitter
def test_pipeline_scout_merge_index(tmp_path):
    """Full pipeline: scout → merge → index preserves all new knowledge fields."""
    import json, os, yaml

    # Set up directory structure merge expects: knowledge/{family}/{platform}/scout/
    knowledge_root = tmp_path / "knowledge" / "test" / "python"
    scout_dir = knowledge_root / "scout"
    scout_dir.mkdir(parents=True)

    # Run scout
    result = subprocess.run(
        [sys.executable, str(SCOUT_SCRIPT), "test", "python",
         str(FIXTURE_REPO), str(scout_dir)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"scout failed:\n{result.stderr}"

    # Run merge (needs cwd where knowledge/ is a child)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "merge.py"), "test", "python"],
        capture_output=True, text=True, cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / ".pylibs")},
    )
    assert result.returncode == 0, f"merge failed:\n{result.stderr}\n{result.stdout}"

    merged_dir = knowledge_root / "merged"
    assert merged_dir.exists(), "merged/ directory not created"

    # G1: constants.json must be copied to merged
    constants_path = merged_dir / "constants.json"
    assert constants_path.exists(), "constants.json not in merged/"
    constants = json.loads(constants_path.read_text())
    const_names = {c["name"] for c in constants}
    assert "MAX_PAGES" in const_names
    assert "DEFAULT_ENCODING" in const_names

    # enum_members and read_write preserved in merged api_surface.json
    api = json.loads((merged_dir / "api_surface.json").read_text())
    enum_classes = [c for c in api if c.get("enum_members")]
    assert len(enum_classes) >= 2, f"Expected >=2 enum classes, got {len(enum_classes)}"
    rw_props = [
        p for c in api for p in c.get("properties", []) if p.get("read_write")
    ]
    assert len(rw_props) >= 1, "No read_write properties in merged api_surface"

    # Run index
    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(REPO_ROOT / 'scripts')!r}); "
         f"import index; from pathlib import Path; "
         f"index.KNOWLEDGE_ROOT = Path({str(tmp_path / 'knowledge')!r}); "
         f"index.build_index('test', 'python')"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / ".pylibs")},
    )
    assert result.returncode == 0, f"index failed:\n{result.stderr}\n{result.stdout}"

    # G4: index.json must have enum_classes and constants
    index = json.loads((merged_dir / "index.json").read_text())
    assert "enum_classes" in index, "enum_classes missing from index.json"
    assert len(index["enum_classes"]) >= 2
    assert "Color" in index["enum_classes"]
    assert "constants" in index, "constants missing from index.json"
    assert index["constants"]["count"] >= 3
    assert "MAX_PAGES" in index["constants"]["exported"]
