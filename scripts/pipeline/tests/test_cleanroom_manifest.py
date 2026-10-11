"""
TC-S96-007: Tests for cleanroom_manifest.py baseline snapshot writer.
"""

import json
import pathlib
import shutil
import tempfile

import pytest

from commands.ops.cleanroom_manifest import (
    BaselineManifest,
    FileRecord,
    capture_baseline,
    parse_frontmatter,
    sha256_file,
    sha256_text,
    validate_manifest_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scope(family="cells", platform="java", subdomains=None, files=None, content_roots=None):
    """Create a minimal mock ScopeManifest for testing."""

    class MockScope:
        pass

    s = MockScope()
    s.family = family
    s.platform = platform
    s.subdomains = subdomains or ["reference"]
    s.files = files or []
    s.content_roots = content_roots or {}
    return s


def _write_md(directory: pathlib.Path, name: str, content: str) -> pathlib.Path:
    p = directory / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# sha256 hashing tests
# ---------------------------------------------------------------------------

def test_sha256_file_crlf_and_lf_produce_same_hash(tmp_path):
    """CRLF and LF files must produce identical sha256."""
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(b"line1\nline2\n")
    crlf.write_bytes(b"line1\r\nline2\r\n")
    digest_lf, _ = sha256_file(lf)
    digest_crlf, _ = sha256_file(crlf)
    assert digest_lf == digest_crlf


def test_sha256_text_crlf_and_lf_produce_same_hash():
    assert sha256_text("line1\nline2\n") == sha256_text("line1\r\nline2\r\n")


def test_sha256_file_different_content_different_hash(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_bytes(b"content A")
    b.write_bytes(b"content B")
    da, _ = sha256_file(a)
    db, _ = sha256_file(b)
    assert da != db


# ---------------------------------------------------------------------------
# Frontmatter parsing tests
# ---------------------------------------------------------------------------

def test_parse_frontmatter_basic(tmp_path):
    p = _write_md(tmp_path, "page.md", "---\ntitle: Hello World\nslug: hello\n---\n# Body\n")
    errors = []
    fm = parse_frontmatter(p, errors)
    assert fm["title"] == "Hello World"
    assert fm["slug"] == "hello"
    assert errors == []


def test_parse_frontmatter_missing_returns_empty(tmp_path):
    p = _write_md(tmp_path, "page.md", "# No frontmatter here\n")
    errors = []
    fm = parse_frontmatter(p, errors)
    assert fm == {}
    assert errors == []


def test_parse_frontmatter_yaml_error_recorded(tmp_path):
    p = _write_md(tmp_path, "page.md", "---\ntitle: [unclosed\n---\n# Body\n")
    errors = []
    fm = parse_frontmatter(p, errors)
    assert fm == {}
    assert len(errors) == 1
    assert "parse error" in errors[0].lower() or "yaml" in errors[0].lower()


def test_parse_frontmatter_auto_updatable_bool(tmp_path):
    p = _write_md(tmp_path, "page.md", "---\ntitle: Test\nauto_updatable: false\n---\n")
    errors = []
    fm = parse_frontmatter(p, errors)
    assert fm.get("auto_updatable") is False


# ---------------------------------------------------------------------------
# capture_baseline tests
# ---------------------------------------------------------------------------

def test_capture_baseline_roundtrip(tmp_path):
    """Write 2 md files, capture baseline, reload JSON, verify fields."""
    content_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "cells" / "java"
    content_dir.mkdir(parents=True)
    (content_dir / "Workbook.md").write_text(
        "---\ntitle: Workbook\n---\n# Body\n", encoding="utf-8"
    )
    (content_dir / "Cells.md").write_text(
        "---\ntitle: Cells\n---\n# Body\n", encoding="utf-8"
    )

    output = tmp_path / "manifest.json"
    scope = _make_scope(
        files=[
            "content/reference.aspose.org/en/cells/java/Workbook.md",
            "content/reference.aspose.org/en/cells/java/Cells.md",
        ]
    )

    manifest = capture_baseline(scope, output, run_id="test-001", repo_root=tmp_path)

    assert output.exists()
    data = json.loads(output.read_text())
    assert data["run_id"] == "test-001"
    assert "content/reference.aspose.org/en/cells/java/Workbook.md" in data["files"]
    assert "content/reference.aspose.org/en/cells/java/Cells.md" in data["files"]
    workbook = data["files"]["content/reference.aspose.org/en/cells/java/Workbook.md"]
    assert "sha256" in workbook
    assert workbook["size_bytes"] > 0
    assert workbook["frontmatter"]["title"] == "Workbook"


def test_capture_baseline_idempotent(tmp_path):
    """Two captures on unchanged files must produce identical sha256 values."""
    content_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "cells" / "java"
    content_dir.mkdir(parents=True)
    (content_dir / "Page.md").write_text("---\ntitle: Page\n---\n", encoding="utf-8")

    scope = _make_scope(
        files=["content/reference.aspose.org/en/cells/java/Page.md"]
    )
    out1 = tmp_path / "m1.json"
    out2 = tmp_path / "m2.json"

    m1 = capture_baseline(scope, out1, "run-1", repo_root=tmp_path)
    m2 = capture_baseline(scope, out2, "run-2", repo_root=tmp_path)

    path = "content/reference.aspose.org/en/cells/java/Page.md"
    assert m1.files[path].sha256 == m2.files[path].sha256


def test_capture_baseline_missing_file_recorded_in_errors(tmp_path):
    scope = _make_scope(files=["content/does-not-exist.md"])
    output = tmp_path / "manifest.json"
    manifest = capture_baseline(scope, output, "run-x", repo_root=tmp_path)
    assert len(manifest._errors) > 0
    assert "not found" in manifest._errors[0]


def test_capture_baseline_yaml_error_in_errors(tmp_path):
    content_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "cells" / "java"
    content_dir.mkdir(parents=True)
    bad = content_dir / "Bad.md"
    bad.write_text("---\ntitle: [unclosed\n---\n# Body\n", encoding="utf-8")

    scope = _make_scope(files=["content/reference.aspose.org/en/cells/java/Bad.md"])
    output = tmp_path / "manifest.json"
    manifest = capture_baseline(scope, output, "run-y", repo_root=tmp_path)
    # sha256 still captured even when frontmatter fails
    assert "content/reference.aspose.org/en/cells/java/Bad.md" in manifest.files
    # errors recorded
    assert len(manifest._errors) > 0


def test_capture_baseline_walks_content_root(tmp_path):
    """When scope.files is empty, should walk content_roots."""
    ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "cells" / "java"
    ref_dir.mkdir(parents=True)
    (ref_dir / "A.md").write_text("---\ntitle: A\n---\n", encoding="utf-8")
    (ref_dir / "B.md").write_text("---\ntitle: B\n---\n", encoding="utf-8")

    scope = _make_scope(
        files=[],  # empty → use content_roots
        content_roots={
            "reference": "content/reference.aspose.org/en/{family}/{platform}"
        },
    )
    output = tmp_path / "manifest.json"
    manifest = capture_baseline(scope, output, "run-z", repo_root=tmp_path)
    assert len(manifest.files) == 2


def test_capture_baseline_atomic_write_no_tmp_on_success(tmp_path):
    """After a successful write, the .tmp file must not exist."""
    scope = _make_scope(files=[])
    output = tmp_path / "manifest.json"
    capture_baseline(scope, output, "run-at", repo_root=tmp_path)
    assert not (tmp_path / "manifest.tmp").exists()
    assert output.exists()


def test_validate_manifest_file_passes_on_valid(tmp_path):
    """Schema validation must pass for a properly-written manifest."""
    scope = _make_scope(files=[])
    output = tmp_path / "manifest.json"
    capture_baseline(scope, output, "run-v", repo_root=tmp_path)
    errors = validate_manifest_file(output)
    assert errors == [], f"Schema errors: {errors}"
