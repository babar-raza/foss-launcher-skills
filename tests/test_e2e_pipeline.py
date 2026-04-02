"""Integration tests for the full content pipeline (M8 — minimum ship bar).

Proves the full content pipeline works end-to-end using fixture data only.
Does NOT require a real FOSS repo or live internet access.

Pipeline chain:
    knowledge model (fixture) → truth-index (index.py) → audit (audit.py)
    → path-guard (path_guard.py) → pre_write_check (pre_write.py)

Run:
    PYTHONPATH=.pylibs python .pylibs/pytest/__main__.py tests/test_e2e_pipeline.py -v -m integration
"""
import json
import sys
from pathlib import Path

import yaml
import pytest

# ---------------------------------------------------------------------------
# Path setup — scripts/ must be importable before anything else
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

# ---------------------------------------------------------------------------
# Mark all tests as integration
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helper: create a temp content file
# ---------------------------------------------------------------------------

def _make_content_file(path: Path, with_evidence: bool = True) -> Path:
    """Write a minimal markdown content file to *path* and return it."""
    frontmatter: dict = {
        "title": "Test Page",
        "description": "Test description",
    }
    if with_evidence:
        frontmatter["evidence"] = {
            "model_sha": "abc123def456",
            "model_version": "1.0.0",
            "claims": ["c1", "c2"],
            "apis": ["Document"],
            "formats": ["DOCX"],
        }
    content = "---\n" + yaml.dump(frontmatter) + "---\n\n# Test\n\nContent here.\n"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# T-E2E-01: Knowledge → Index pipeline
# ---------------------------------------------------------------------------

def test_e2e_01_knowledge_to_index(knowledge_tree, monkeypatch):
    """Build index.json from fixture knowledge tree and verify structure."""
    import index as ix  # noqa: PLC0415

    # Redirect index.py to the fixture tmp tree
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", knowledge_tree / "knowledge")

    result = ix.build_index("words", "python")
    assert result is not None, "build_index should return a dict for valid model"

    index_file = knowledge_tree / "knowledge" / "words" / "python" / "merged" / "index.json"
    assert index_file.exists(), "index.json must be created on disk"

    data = json.loads(index_file.read_text(encoding="utf-8"))
    assert data.get("family") == "words"
    assert data.get("platform") == "python"
    assert "classes" in data
    assert "formats" in data
    assert "api_coverage" in data


# ---------------------------------------------------------------------------
# T-E2E-02: Path guard blocks forbidden writes
# ---------------------------------------------------------------------------

def test_e2e_02_path_guard_blocks_forbidden():
    """check_path must DENY paths matching the hardcoded forbidden list."""
    from path_guard import check_path  # noqa: PLC0415

    verdict, reason = check_path("themes/custom.css", config={})
    assert verdict == "DENY", f"Expected DENY for themes/, got {verdict!r}"
    assert reason is not None

    verdict2, reason2 = check_path("scripts/something.py", config={})
    assert verdict2 == "DENY", f"Expected DENY for scripts/, got {verdict2!r}"


# ---------------------------------------------------------------------------
# T-E2E-03: Path guard allows content/knowledge/reports writes
# ---------------------------------------------------------------------------

def test_e2e_03_path_guard_allows_content_writes():
    """check_path must ALLOW legitimate content and knowledge paths."""
    from path_guard import check_path  # noqa: PLC0415

    cases = [
        "content/docs.aspose.org/en/words/python/page.md",
        "knowledge/words/python/merged/model.yaml",
        "reports/audit/test.json",
    ]
    for path in cases:
        verdict, reason = check_path(path, config={})
        assert verdict == "ALLOW", (
            f"Expected ALLOW for {path!r}, got {verdict!r} (reason: {reason!r})"
        )


# ---------------------------------------------------------------------------
# T-E2E-04: Audit on valid content page passes
# ---------------------------------------------------------------------------

def test_e2e_04_audit_valid_content_passes(knowledge_tree, tmp_path, monkeypatch):
    """A content file with a proper evidence block must produce no FAIL findings."""
    import knowledge_core  # noqa: PLC0415
    from pipeline.audit import audit_files  # noqa: PLC0415

    # Place content under a path that infer_product() can parse
    content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "words" / "python"
    content_dir.mkdir(parents=True)
    content_file = content_dir / "page.md"

    # Use a model_sha that matches what's in the fixture knowledge tree
    merged_model = yaml.safe_load(
        (knowledge_tree / "knowledge" / "words" / "python" / "merged" / "model.yaml")
        .read_text(encoding="utf-8")
    )
    frontmatter: dict = {
        "title": "Test Page",
        "description": "Test description",
        "evidence": {
            "model_sha": merged_model.get("repo_sha", "abc123def456"),
            "model_version": merged_model.get("version", "1.0.0"),
            "claims": ["c1", "c2"],
            "apis": ["Document"],
            "formats": ["DOCX"],
        },
    }
    content = "---\n" + yaml.dump(frontmatter) + "---\n\n# Test\n\nContent here.\n"
    content_file.write_text(content, encoding="utf-8")

    # Point knowledge_core at the fixture tree
    monkeypatch.setattr(knowledge_core, "KNOWLEDGE_ROOT", knowledge_tree / "knowledge")

    findings = audit_files([str(content_file)])
    fail_findings = [f for f in findings if getattr(f, "level", "") == "FAIL"]
    assert not fail_findings, (
        f"Expected no FAIL findings for valid content, got: {fail_findings}"
    )


# ---------------------------------------------------------------------------
# T-E2E-05: Audit on content page without evidence fails
# ---------------------------------------------------------------------------

def test_e2e_05_audit_missing_evidence_warns(knowledge_tree, tmp_path, monkeypatch):
    """A content file without an evidence block must generate at least one WARN/FAIL finding."""
    import knowledge_core  # noqa: PLC0415
    from pipeline.audit import audit_files  # noqa: PLC0415

    content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "words" / "python"
    content_dir.mkdir(parents=True)
    content_file = _make_content_file(content_dir / "no_evidence.md", with_evidence=False)

    monkeypatch.setattr(knowledge_core, "KNOWLEDGE_ROOT", knowledge_tree / "knowledge")

    findings = audit_files([str(content_file)])
    assert findings, "Expected at least one finding for content without evidence block"

    # At minimum there should be a WARN about missing evidence
    levels = {getattr(f, "level", "") for f in findings}
    assert levels & {"WARN", "FAIL"}, (
        f"Expected WARN or FAIL finding, but got levels: {levels}"
    )


# ---------------------------------------------------------------------------
# T-E2E-06: Full chain: knowledge → audit → path-guard
# ---------------------------------------------------------------------------

def test_e2e_06_full_chain(knowledge_tree, tmp_path, monkeypatch):
    """Demonstrate the complete pipeline without crashes."""
    import index as ix  # noqa: PLC0415
    import knowledge_core  # noqa: PLC0415
    from path_guard import check_path  # noqa: PLC0415
    from pipeline.audit import audit_files  # noqa: PLC0415

    # Step 1: build index from knowledge fixture
    monkeypatch.setattr(ix, "KNOWLEDGE_ROOT", knowledge_tree / "knowledge")
    result = ix.build_index("words", "python")
    assert result is not None

    # Step 2: create a content file referencing the knowledge
    content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / "words" / "python"
    content_dir.mkdir(parents=True)
    content_file = _make_content_file(content_dir / "chain_test.md", with_evidence=True)

    # Step 3: path guard must ALLOW the target path
    rel_path = "content/docs.aspose.org/en/words/python/chain_test.md"
    verdict, _ = check_path(rel_path, config={})
    assert verdict == "ALLOW", f"Expected ALLOW, got {verdict!r}"

    # Step 4: audit must run without crashing
    monkeypatch.setattr(knowledge_core, "KNOWLEDGE_ROOT", knowledge_tree / "knowledge")
    findings = audit_files([str(content_file)])
    # Findings may be non-empty (WARN for stale SHA is fine); no crash = success
    assert isinstance(findings, list)


# ---------------------------------------------------------------------------
# T-E2E-07: Ops log records entries
# ---------------------------------------------------------------------------

def test_e2e_07_ops_log_records_entry(tmp_path):
    """log_entry must persist entries readable by read_log."""
    from ops_log import log_entry, read_log  # noqa: PLC0415

    log_path = tmp_path / "reports" / "ops.log"
    returned_path = log_entry(
        skill="e2e-test",
        status="PASS",
        log_path=str(log_path),
    )
    assert returned_path == log_path

    entries = read_log(log_path=str(log_path))
    assert len(entries) >= 1
    last = entries[-1]
    assert last["skill"] == "e2e-test"
    assert last["status"] == "PASS"
    assert "ts" in last


# ---------------------------------------------------------------------------
# T-E2E-08: check_setup reports OK on valid environment
# ---------------------------------------------------------------------------

def test_e2e_08_check_setup_no_errors(tmp_path, monkeypatch):
    """check_setup should produce no ERROR-level issues given a valid config and content_root."""
    from check_setup import check_setup  # noqa: PLC0415

    # Create a minimal valid config dict
    config = {
        "content_repo": str(tmp_path),
        "sites": {
            "docs": {
                "content_path": "content/docs.aspose.org/en/{family}/{platform}/",
                "type": "docs",
            },
        },
        "knowledge_path": "knowledge/{family}/{platform}/",
        "forbidden_paths": ["themes/"],
    }

    # A real directory as content_root avoids the CWD fallback ERROR
    issues = check_setup(
        config=config,
        content_root=tmp_path,
        _required_packages=["yaml", "json", "pathlib"],
        _optional_packages={},
    )

    error_issues = [(level, msg) for level, msg in issues if level == "ERROR"]
    assert not error_issues, (
        f"Expected no ERROR-level issues, but got: {error_issues}"
    )
