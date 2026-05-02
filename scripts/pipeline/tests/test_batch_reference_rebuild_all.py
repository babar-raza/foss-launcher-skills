"""
TC-S96-013: Tests for --rebuild-all safety guards in batch_reference.py.
"""

import json
import pathlib
from unittest.mock import patch, MagicMock

import pytest
import yaml

from commands.content.batch_reference import (
    REBUILD_CONFIRM_THRESHOLD,
    configure,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_knowledge(tmp_path, family="cells", platform="java", n_entries=3):
    """Write minimal knowledge artifacts needed by run()."""
    kb_dir = tmp_path / "knowledge" / family / platform / "merged"
    kb_dir.mkdir(parents=True)

    api_surface = [
        {"name": f"Class{i}", "kind": "class_declaration", "visibility": "public",
         "file": f"Class{i}.java", "namespace": f"com.aspose.{family}"}
        for i in range(n_entries)
    ]
    (kb_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
    (kb_dir / "model.yaml").write_text(
        yaml.dump({"repo_sha": "abc1234", "version": "1", "stale_since": None}),
        encoding="utf-8",
    )
    return kb_dir


def _make_pages(content_dir, names, auto_updatable=True):
    """Write minimal reference pages with provenance block (required for is_auto_updatable())."""
    content_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        flag = "true" if auto_updatable else "false"
        # auto_updatable must be indented inside provenance block for the regex to match
        (content_dir / f"{name}.md").write_text(
            f"---\ntitle: {name}\nprovenance:\n  auto_updatable: {flag}\n---\n# {name}\n",
            encoding="utf-8",
        )


def _content_dir(tmp_path, family="cells", platform="java"):
    return tmp_path / "content" / "reference.aspose.org" / "en" / family / platform


# ---------------------------------------------------------------------------
# TC1: --rebuild-all dry-run — no files written, candidates listed
# ---------------------------------------------------------------------------

def test_rebuild_all_dry_run_no_files_written(tmp_path):
    """--rebuild-all --dry-run must not write any files."""
    _setup_knowledge(tmp_path, n_entries=2)
    cdir = _content_dir(tmp_path)
    _make_pages(cdir, ["Class0", "Class1"])

    configure(
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    written = []

    def spy_write(path, content, **kwargs):
        written.append(path)

    with patch("commands.content.batch_reference.safe_content_write", side_effect=spy_write):
        result = run("cells", "java", dry_run=True, rebuild_all=True, confirm_rebuild=True)

    assert result.get("dry_run") is True
    assert written == [], "dry-run must not call safe_content_write"


# ---------------------------------------------------------------------------
# TC2: --rebuild-all with N > threshold without --confirm-rebuild → exits
# ---------------------------------------------------------------------------

def test_rebuild_all_requires_confirm_rebuild_above_threshold(tmp_path):
    """--rebuild-all without --confirm-rebuild when eligible pages > threshold must exit."""
    n = REBUILD_CONFIRM_THRESHOLD + 5
    _setup_knowledge(tmp_path, n_entries=n)
    cdir = _content_dir(tmp_path)
    _make_pages(cdir, [f"Class{i}" for i in range(n)])

    configure(
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    with pytest.raises(SystemExit) as exc_info:
        run("cells", "java", rebuild_all=True, confirm_rebuild=False)

    # SystemExit code is non-zero (the error message string or integer)
    assert exc_info.value.code not in (0, None)


# ---------------------------------------------------------------------------
# TC3: --rebuild-all WITH --confirm-rebuild above threshold → proceeds
# ---------------------------------------------------------------------------

def test_rebuild_all_with_confirm_rebuild_proceeds(tmp_path):
    """--rebuild-all with --confirm-rebuild above threshold must not exit early."""
    n = REBUILD_CONFIRM_THRESHOLD + 5
    _setup_knowledge(tmp_path, n_entries=n)
    cdir = _content_dir(tmp_path)
    _make_pages(cdir, [f"Class{i}" for i in range(n)])

    configure(
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    # Patch the page builder and writer to avoid full generation
    with patch("commands.content.batch_reference._build_page", return_value="# content"):
        with patch("commands.content.batch_reference.safe_content_write"):
            with patch("commands.content.batch_reference.attach_evidence"):
                with patch("commands.content.batch_reference._has_meaningful_change", return_value=True):
                    result = run("cells", "java", rebuild_all=True, confirm_rebuild=True)

    assert isinstance(result, dict)
    assert "generated" in result or "updated" in result


# ---------------------------------------------------------------------------
# TC4: auto_updatable:false pages skipped in --rebuild-all
# ---------------------------------------------------------------------------

def test_rebuild_all_skips_protected_pages(tmp_path):
    """Pages with auto_updatable: false must be skipped in --rebuild-all mode."""
    _setup_knowledge(tmp_path, n_entries=2)
    cdir = _content_dir(tmp_path)
    # Class0 protected, Class1 updatable
    _make_pages(cdir, ["Class0"], auto_updatable=False)
    _make_pages(cdir, ["Class1"], auto_updatable=True)

    configure(
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    written_paths = []

    def spy_write(path, content, **kwargs):
        written_paths.append(pathlib.Path(path).name)

    with patch("commands.content.batch_reference._build_page", return_value="# content"):
        with patch("commands.content.batch_reference.safe_content_write", side_effect=spy_write):
            with patch("commands.content.batch_reference.attach_evidence"):
                with patch("commands.content.batch_reference._has_meaningful_change", return_value=True):
                    run("cells", "java", rebuild_all=True, confirm_rebuild=True)

    assert "Class0.md" not in written_paths, "Protected page must not be rewritten"
    assert "Class1.md" in written_paths, "Updatable page must be rewritten"


# ---------------------------------------------------------------------------
# TC5: --update + --rebuild-all → exit 2 (mutual exclusion guard)
# ---------------------------------------------------------------------------

def test_update_and_rebuild_all_exits_2(tmp_path):
    """--update and --rebuild-all must be mutually exclusive (exit 2)."""
    _setup_knowledge(tmp_path, n_entries=1)

    configure(
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    with pytest.raises(SystemExit) as exc_info:
        run("cells", "java", update=True, rebuild_all=True)

    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# TC6: --rebuild-all without knowledge_delta.json → proceeds (no delta required)
# ---------------------------------------------------------------------------

def test_rebuild_all_proceeds_without_knowledge_delta(tmp_path):
    """--rebuild-all must not require knowledge_delta.json."""
    _setup_knowledge(tmp_path, n_entries=2)
    cdir = _content_dir(tmp_path)
    _make_pages(cdir, ["Class0"])  # 1 existing page

    configure(
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    # Confirm knowledge_delta.json does NOT exist
    delta_path = tmp_path / "knowledge" / "cells" / "java" / "merged" / "knowledge_delta.json"
    assert not delta_path.exists()

    with patch("commands.content.batch_reference._build_page", return_value="# content"):
        with patch("commands.content.batch_reference.safe_content_write"):
            with patch("commands.content.batch_reference.attach_evidence"):
                with patch("commands.content.batch_reference._has_meaningful_change", return_value=True):
                    result = run("cells", "java", rebuild_all=True, confirm_rebuild=True)

    assert isinstance(result, dict)
