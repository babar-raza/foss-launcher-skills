"""
TC-S96-013: Tests for --rebuild-all safety guards in batch_reference.py.
"""

import json
import hashlib
import pathlib
from unittest.mock import patch, MagicMock

import pytest
import yaml

from commands.content.batch_reference import (
    REBUILD_CONFIRM_THRESHOLD,
    configure,
    run as _production_run,
)


def run(*args, **kwargs):
    kwargs.setdefault("run_id", "TEST-RUN")
    return _production_run(*args, **kwargs)


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
        repo_root=tmp_path,
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
        repo_root=tmp_path,
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
        repo_root=tmp_path,
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
        repo_root=tmp_path,
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    written_paths = []

    def spy_write(path, content, **kwargs):
        written_paths.append(pathlib.Path(path).name)
        pathlib.Path(path).write_text(content, encoding="utf-8")

    with patch("commands.content.batch_reference._build_page", return_value="# content"):
        with patch("commands.content.batch_reference.safe_content_write", side_effect=spy_write):
            with patch("commands.content.batch_reference.attach_evidence"):
                with patch("commands.content.batch_reference._has_meaningful_change", return_value=True):
                    run("cells", "java", rebuild_all=True, confirm_rebuild=True)

    assert "Class0.md" not in written_paths, "Protected page must not be rewritten"
    assert "Class1.md" in written_paths, "Updatable page must be rewritten"
    decision_path = (
        tmp_path
        / "reports/refresh_runs/cells/java/TEST-RUN/page_decisions.jsonl"
    )
    decisions = [
        json.loads(line)
        for line in decision_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    protected = next(
        row for row in decisions if row["page_path"].endswith("/Class0.md")
    )
    assert protected["run_id"] == "TEST-RUN"
    assert protected["disposition"] == "BLOCKED"
    receipt = yaml.safe_load(
        (
            tmp_path
            / "reports/refresh_runs/cells/java/TEST-RUN"
            / protected["receipt_ref"]
        ).read_text(encoding="utf-8")
    )["content_refresh_receipt"]
    assert receipt["verdict"] == "REFERENCE_BLOCKED"
    assert receipt["reason"] == "AUTO_UPDATABLE_FALSE"


def test_rebuild_all_emits_noop_decision_for_unchanged_page(tmp_path):
    _setup_knowledge(tmp_path, n_entries=1)
    cdir = _content_dir(tmp_path)
    _make_pages(cdir, ["Class0"], auto_updatable=True)
    configure(
        repo_root=tmp_path,
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    with patch("commands.content.batch_reference._build_page", return_value="# content"):
        with patch(
            "commands.content.batch_reference._has_meaningful_change",
            return_value=False,
        ):
            result = run(
                "cells",
                "java",
                rebuild_all=True,
                confirm_rebuild=True,
            )

    assert result["unchanged"] == 1
    rows = [
        json.loads(line)
        for line in (
            tmp_path
            / "reports/refresh_runs/cells/java/TEST-RUN/page_decisions.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(rows) == 1
    assert rows[0]["disposition"] == "NOT_AFFECTED"
    receipt = yaml.safe_load(
        (
            tmp_path
            / "reports/refresh_runs/cells/java/TEST-RUN"
            / rows[0]["receipt_ref"]
        ).read_text(encoding="utf-8")
    )["content_refresh_receipt"]
    assert receipt["verdict"] == "REFERENCE_UNCHANGED"
    receipt_path = (
        tmp_path
        / "reports/refresh_runs/cells/java/TEST-RUN"
        / rows[0]["receipt_ref"]
    )
    import hashlib
    assert rows[0]["receipt_digest"] == (
        "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    )


# ---------------------------------------------------------------------------
# TC5: --update + --rebuild-all → exit 2 (mutual exclusion guard)
# ---------------------------------------------------------------------------

def test_update_and_rebuild_all_exits_2(tmp_path):
    """--update and --rebuild-all must be mutually exclusive (exit 2)."""
    _setup_knowledge(tmp_path, n_entries=1)

    configure(
        repo_root=tmp_path,
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
        repo_root=tmp_path,
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


def test_scoped_run_ignores_unrelated_stale_collision(tmp_path):
    kb_dir = _setup_knowledge(tmp_path, n_entries=1)
    api_surface = json.loads(
        (kb_dir / "api_surface.json").read_text(encoding="utf-8")
    )
    api_surface.extend(
        [
            {
                "name": "Duplicate",
                "kind": "class_declaration",
                "visibility": "public",
                "file": "one/Duplicate.java",
                "canonical_namespace": "com.aspose.one",
            },
            {
                "name": "Duplicate",
                "kind": "class_declaration",
                "visibility": "public",
                "file": "two/Duplicate.java",
                "canonical_namespace": "com.aspose.two",
            },
        ]
    )
    (kb_dir / "api_surface.json").write_text(
        json.dumps(api_surface),
        encoding="utf-8",
    )
    cdir = _content_dir(tmp_path)
    _make_pages(cdir, ["Class0", "Duplicate"])
    run_root = tmp_path / "reports/refresh_runs/cells/java/SCOPED-RUN"
    run_root.mkdir(parents=True)
    scope_path = run_root / "scope.json"
    scoped_paths = [
        "content/reference.aspose.org/en/cells/java/Class0.md"
    ]
    scope_path.write_text(
        json.dumps(
            {
                "run_id": "SCOPED-RUN",
                "family": "cells",
                "platform": "java",
                "paths": scoped_paths,
            }
        ),
        encoding="utf-8",
    )
    logical = json.dumps(
        {"paths": scoped_paths, "input_digest": None},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "SCOPED-RUN",
                "family": "cells",
                "platform": "java",
                "created_at": "2026-07-26T00:00:00Z",
                "scope": {
                    "paths": scoped_paths,
                    "input_digest": None,
                    "digest": "sha256:" + hashlib.sha256(logical).hexdigest(),
                },
                "output_digests": {
                    "scope": "sha256:" + hashlib.sha256(
                        scope_path.read_bytes()
                    ).hexdigest()
                },
            }
        ),
        encoding="utf-8",
    )
    configure(
        repo_root=tmp_path,
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    with patch("commands.content.batch_reference._build_page", return_value="# content"):
        with patch(
            "commands.content.batch_reference._has_meaningful_change",
            return_value=False,
        ):
            result = run(
                "cells",
                "java",
                rebuild_all=True,
                confirm_rebuild=True,
                run_id="SCOPED-RUN",
                run_root=run_root,
            )

    assert result["unchanged"] == 1
    rows = [
        json.loads(line)
        for line in (run_root / "page_decisions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert [row["page_path"] for row in rows] == [
        "content/reference.aspose.org/en/cells/java/Class0.md"
    ]


def test_scoped_run_matches_candidate_despite_tracked_casing_mismatch(tmp_path):
    """HARDEN-BR-01 (2026-07-29): a scope manifest built from a file listing
    (e.g. `find`) captures whatever casing is actually tracked on disk. A
    candidate's target filename is always computed from api_surface.json's
    PascalCase class name, so a class whose existing page happens to be
    tracked under different casing (a legacy artifact, not a naming choice
    the current pipeline would make) must not silently drop out of a scoped
    run just because "Material.md" != "material.md" as byte strings -- they
    name the same file on a case-insensitive filesystem. Found live: 8
    pre-existing 3d/java pages (camera/entity/light/material/mesh/node/
    scene/transform) were silently excluded from two full ST-013-remediation
    regeneration passes this way."""
    kb_dir = _setup_knowledge(tmp_path, n_entries=0)
    api_surface = [{
        "name": "Material", "kind": "class_declaration", "visibility": "public",
        "file": "Material.java", "namespace": "com.aspose.cells",
    }]
    (kb_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
    cdir = _content_dir(tmp_path)
    # The tracked page uses legacy lowercase casing, not "Material.md".
    _make_pages(cdir, ["material"])

    run_root = tmp_path / "reports/refresh_runs/cells/java/CASE-RUN"
    run_root.mkdir(parents=True)
    scope_path = run_root / "scope.json"
    # A file-listing tool (e.g. `find`) reports the casing actually on disk.
    scoped_paths = ["content/reference.aspose.org/en/cells/java/material.md"]
    scope_path.write_text(
        json.dumps({
            "run_id": "CASE-RUN", "family": "cells", "platform": "java",
            "paths": scoped_paths,
        }),
        encoding="utf-8",
    )
    logical = json.dumps(
        {"paths": scoped_paths, "input_digest": None},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    (run_root / "manifest.json").write_text(
        json.dumps({
            "run_id": "CASE-RUN", "family": "cells", "platform": "java",
            "created_at": "2026-07-26T00:00:00Z",
            "scope": {
                "paths": scoped_paths, "input_digest": None,
                "digest": "sha256:" + hashlib.sha256(logical).hexdigest(),
            },
            "output_digests": {
                "scope": "sha256:" + hashlib.sha256(scope_path.read_bytes()).hexdigest()
            },
        }),
        encoding="utf-8",
    )
    configure(
        repo_root=tmp_path,
        knowledge_root=tmp_path / "knowledge",
        content_root=tmp_path / "content" / "reference.aspose.org" / "en",
    )

    with patch("commands.content.batch_reference._build_page", return_value="# content"):
        result = run(
            "cells", "java",
            rebuild_all=True, confirm_rebuild=True,
            run_id="CASE-RUN", run_root=run_root,
        )

    # Before the fix this candidate silently vanished (updated == 0, no error).
    assert result["updated"] == 1
