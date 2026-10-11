"""Tests for batch_reference.py --update mode (TC-03).

Tests cover:
- --update regenerates exactly the pages in knowledge_delta.json modified_apis
- --update skips pages not in modified_apis
- --update --dry-run reports changes without writing
- --update when knowledge_delta.json absent falls back to full re-run with warning
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "pipeline"
_CONTENT_CMD_DIR = _PIPELINE_DIR / "commands" / "content"
for _d in (_PIPELINE_DIR, _CONTENT_CMD_DIR):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_surface(names: list[str]) -> list[dict]:
    return [
        {
            "name": n,
            "kind": "class_definition",
            "doc": f"Doc for {n}",
            "file": f"src/{n}.py",
            "line": 1,
            "bases": [],
            "methods": [{"name": "do_thing", "params": [], "return_type": "None", "doc": "", "line": 5, "is_constructor": False}],
            "properties": [],
            "enum_members": [],
        }
        for n in names
    ]


def _make_model_yaml(repo_sha: str = "abc123" * 6, stale_since=None) -> str:
    import yaml
    return yaml.safe_dump({"repo_sha": repo_sha, "stale_since": stale_since, "version": "1.0"})


def _make_delta(modified_apis: list[str]) -> dict:
    return {
        "generated_at": "2026-04-07T00:00:00+00:00",
        "base_sha": "old" * 10,
        "current_sha": "new" * 10,
        "new_claims": [],
        "removed_claims": [],
        "modified_claims": [],
        "new_apis": [],
        "removed_apis": [],
        "modified_apis": modified_apis,
    }


@pytest.fixture()
def batch_env(tmp_path, monkeypatch):
    """Set up a fake knowledge + content environment for batch_reference tests."""
    import batch_reference as br

    family, platform = "testfam", "python"

    # Knowledge dirs
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)
    (merged / "model.yaml").write_text(_make_model_yaml(), encoding="utf-8")

    api_classes = ["ClassA", "ClassB", "ClassC"]
    (merged / "api_surface.json").write_text(
        json.dumps(_make_api_surface(api_classes)), encoding="utf-8"
    )
    (merged / "claims.json").write_text("[]", encoding="utf-8")

    # Content dir (output)
    output_dir = tmp_path / "content" / "reference.aspose.org" / "en" / family / platform
    output_dir.mkdir(parents=True)

    br.configure(repo_root=tmp_path)

    # Stub Knowledge and attach_evidence to avoid needing a real knowledge model
    mock_knowledge = MagicMock()
    mock_knowledge.available = True
    monkeypatch.setattr(br, "Knowledge", lambda f, p, **kw: mock_knowledge)
    monkeypatch.setattr(br, "attach_evidence", lambda *a, **kw: None)

    yield tmp_path, family, platform, merged, output_dir
    br.configure()


# ---------------------------------------------------------------------------
# Happy path: --update regenerates pages in modified_apis only
# ---------------------------------------------------------------------------

def test_update_regenerates_modified_apis_only(batch_env):
    """--update mode re-generates ClassA (in modified_apis) but skips ClassB."""
    import batch_reference as br
    tmp_path, family, platform, merged, output_dir = batch_env

    # Pre-create all pages (they already exist)
    for name in ["ClassA", "ClassB", "ClassC"]:
        (output_dir / f"{name}.md").write_text(f"old content {name}", encoding="utf-8")

    # ClassA is modified; ClassB and ClassC are unchanged
    delta = _make_delta(["ClassA"])
    (merged / "knowledge_delta.json").write_text(json.dumps(delta), encoding="utf-8")

    result = br.run(family, platform, update=True)

    # Only ClassA should be updated (regenerated)
    assert result["updated"] == 1
    assert result["skipped"] == 2  # ClassB, ClassC
    assert result["generated"] == 0

    # ClassA content should be new (not "old content ClassA")
    new_content = (output_dir / "ClassA.md").read_text(encoding="utf-8")
    assert "old content ClassA" not in new_content
    assert "ClassA" in new_content  # has new generated content

    # ClassB should be unchanged
    assert (output_dir / "ClassB.md").read_text(encoding="utf-8") == "old content ClassB"


# ---------------------------------------------------------------------------
# Happy path: --update skips pages not in modified_apis
# ---------------------------------------------------------------------------

def test_update_skips_pages_not_in_modified_apis(batch_env):
    """--update mode skips pages whose class names are not in modified_apis."""
    import batch_reference as br
    tmp_path, family, platform, merged, output_dir = batch_env

    for name in ["ClassA", "ClassB", "ClassC"]:
        (output_dir / f"{name}.md").write_text(f"original {name}", encoding="utf-8")

    # Empty modified_apis: nothing should be updated
    delta = _make_delta([])
    (merged / "knowledge_delta.json").write_text(json.dumps(delta), encoding="utf-8")

    result = br.run(family, platform, update=True)

    assert result["updated"] == 0
    assert result["skipped"] == 3
    # All files unchanged
    for name in ["ClassA", "ClassB", "ClassC"]:
        content = (output_dir / f"{name}.md").read_text(encoding="utf-8")
        assert content == f"original {name}"


# ---------------------------------------------------------------------------
# Happy path: --update --dry-run reports changes without writing
# ---------------------------------------------------------------------------

def test_update_dry_run_no_writes(batch_env):
    """--update --dry-run prints what would be updated without modifying files."""
    import batch_reference as br
    tmp_path, family, platform, merged, output_dir = batch_env

    for name in ["ClassA", "ClassB", "ClassC"]:
        (output_dir / f"{name}.md").write_text(f"original {name}", encoding="utf-8")

    delta = _make_delta(["ClassA", "ClassB"])
    (merged / "knowledge_delta.json").write_text(json.dumps(delta), encoding="utf-8")

    result = br.run(family, platform, update=True, dry_run=True)

    assert result["dry_run"] is True
    assert result["updated"] == 0  # nothing written in dry-run
    # All files must remain unchanged
    for name in ["ClassA", "ClassB", "ClassC"]:
        assert (output_dir / f"{name}.md").read_text(encoding="utf-8") == f"original {name}"


# ---------------------------------------------------------------------------
# Failing path: --update when knowledge_delta.json absent falls back to full re-run
# ---------------------------------------------------------------------------

def test_update_fallback_when_delta_absent(batch_env, capsys):
    """--update with no knowledge_delta.json degrades to full re-run with warning."""
    import batch_reference as br
    tmp_path, family, platform, merged, output_dir = batch_env

    # No delta file; ClassA and ClassB already exist, ClassC does not
    (output_dir / "ClassA.md").write_text("old ClassA", encoding="utf-8")
    (output_dir / "ClassB.md").write_text("old ClassB", encoding="utf-8")
    # ClassC does not exist → will be generated even in fallback mode

    result = br.run(family, platform, update=True)

    captured = capsys.readouterr()
    assert "WARN" in captured.out and "falling back" in captured.out.lower()

    # In fallback (no --update), existing pages ClassA+ClassB are skipped, ClassC is generated
    assert result["generated"] == 1  # ClassC
    assert result["skipped"] == 2    # ClassA, ClassB
    assert (output_dir / "ClassA.md").read_text(encoding="utf-8") == "old ClassA"


# ---------------------------------------------------------------------------
# Regression: ERC key bug fix (TC-GDF-001)
# Verifies that _build_grouped_index_body uses erc["text"] not erc["description"]
# ---------------------------------------------------------------------------

def test_build_grouped_index_uses_erc_text_not_description():
    """Bug regression (TC-GDF-001): index must use erc['text'], not erc['description'].

    Before fix: erc.get("description", "") always returned "" because ERC claims
    store the description under key "text". This caused ALL ERC-covered entries to
    fall through to the generic fallback "Class in the Pdf API.".
    After fix: erc.get("text", "") correctly retrieves the ERC description.
    """
    import batch_reference as br

    entry_no_doc = {
        "name": "GoToAction",
        "kind": "class_declaration",
        "doc": "",
        "file": "src/GoToAction.cs",
        "line": 1,
        "bases": [],
        "methods": [{"name": "Execute", "params": [], "return_type": "void",
                     "doc": "", "line": 5, "is_constructor": False}],
        "properties": [],
        "enum_members": [],
        "canonical_namespace": "Aspose.Pdf.Actions",
    }
    # ERC index stores claims under "text" key (not "description")
    erc_index = {
        "GoToAction": {
            "claim_id": "ERC-001",
            "text": "Navigates to a specified destination within the PDF document.",
            "description": "",   # old buggy code read this key — must NOT be used
            "kind": "api",
            "confidence": 0.9,
        }
    }
    body = br._build_grouped_index_body([entry_no_doc], "pdf", "net", erc_index=erc_index)
    assert "Navigates to a specified destination" in body, (
        "ERC 'text' value must appear in index table — key was wrong before fix"
    )
    assert "Class in the Pdf API." not in body, (
        "Generic fallback must not appear when ERC text is available"
    )


# ---------------------------------------------------------------------------
# Regression: synthesized fallback uses member counts (TC-GDF-002)
# ---------------------------------------------------------------------------

def test_build_grouped_index_synthesized_fallback_no_doc_no_erc():
    """TC-GDF-002: when no doc AND no ERC, description uses member counts, not generic text."""
    import batch_reference as br

    entry = {
        "name": "SomeClass",
        "kind": "class_declaration",
        "doc": "",
        "file": "src/SomeClass.cs",
        "line": 1,
        "bases": [],
        "methods": [
            {"name": "m1", "params": [], "return_type": "void",
             "doc": "", "line": 2, "is_constructor": False},
            {"name": "m2", "params": [], "return_type": "void",
             "doc": "", "line": 3, "is_constructor": False},
        ],
        "properties": [
            {"name": "Prop1", "type": "string", "doc": "", "line": 4, "writable": True}
        ],
        "enum_members": [],
        "canonical_namespace": "Aspose.Pdf",
    }
    body = br._build_grouped_index_body([entry], "pdf", "net", erc_index={})
    assert "Class in the Pdf API." not in body, (
        "Old generic text must not appear when member counts are available"
    )
    assert "method" in body.lower(), "Description must mention method count"
    assert "propert" in body.lower(), "Description must mention property count"


# ---------------------------------------------------------------------------
# Regression: empty-member fallback is more specific than old generic (TC-GDF-003)
# ---------------------------------------------------------------------------

def test_build_grouped_index_empty_entry_fallback_not_bare_generic():
    """TC-GDF-003: entry with no doc, no ERC, no members must not use bare generic.

    The old fallback was 'Class in the Pdf API.' — a string that the
    GenericDescriptionCheckEvaluator now flags as a FAIL. The new fallback
    includes the platform so it reads 'Class in the Pdf NET API.' which is
    more specific and does NOT match the banned pattern.
    """
    import batch_reference as br
    import re

    entry = {
        "name": "EmptyMarker",
        "kind": "class_declaration",
        "doc": "",
        "file": "src/EmptyMarker.cs",
        "line": 1,
        "bases": [],
        "methods": [],
        "properties": [],
        "enum_members": [],
        "canonical_namespace": "Aspose.Pdf",
    }
    body = br._build_grouped_index_body([entry], "pdf", "net", erc_index={})
    # Exact old string must NOT appear
    old_pattern = re.compile(r"Class in the Pdf API\.")
    assert not old_pattern.search(body), (
        f"Old exact generic text still present in: {body[:300]}"
    )
