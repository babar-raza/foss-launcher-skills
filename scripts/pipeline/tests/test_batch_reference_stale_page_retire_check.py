"""Regression test for the stale-undisambiguated-page retirement check
(HARDEN-stale-page-retire-check, 2026-08-31, MT040 Phase I TC-56).

batch_reference.py refuses to proceed when a name collision needs
disambiguation but the old bare-name page (e.g. ``Foo.md``, superseded by
``Foo-a.md``/``Foo-b.md``) is still present, directing the operator to the
governed page-retire workflow (retire_page.py). That check used to test
only ``_old.exists()`` -- but retire_page.py never deletes or renames a
file, it only sets ``draft: true`` in frontmatter (see its own module
docstring: "without deleting them"). So a page retired through the exact
workflow the error message names still tripped the same block immediately
afterward. Confirmed live retiring 3d/typescript's BoundingBoxExtent.md (a
second upstream declaration of the same name appeared inside BoundingBox.ts,
creating a genuine new collision): RuntimeError fired again right after
retire_page.py reported RETIRED.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import batch_reference as _br
from test_batch_reference import _make_api_surface, run as _run  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    _br.configure(repo_root=tmp_path)
    yield
    _br.configure()


def _colliding_entries():
    return [
        {"name": "Foo", "kind": "class_declaration",
         "file": "src/pkg/a.ts", "visibility": "public",
         "canonical_namespace": "pkg.a",
         "methods": [{"name": "one", "params": [], "return_type": "", "doc": "", "line": 1}],
         "properties": []},
        {"name": "Foo", "kind": "class_declaration",
         "file": "src/pkg/b.ts", "visibility": "public",
         "canonical_namespace": "pkg.b",
         "methods": [{"name": "two", "params": [], "return_type": "", "doc": "", "line": 1}],
         "properties": []},
    ]


def _write_old_bare_page(out_dir: Path, *, retired: bool) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fm = {"title": "Foo", "linkTitle": "Foo"}
    if retired:
        fm["draft"] = True
        fm["retired_at"] = "2026-08-31"
    text = "---\n" + yaml.safe_dump(fm) + "---\n\nStale content.\n"
    path = out_dir / "Foo.md"
    path.write_text(text, encoding="utf-8")
    return path


class TestRetiredPageNoLongerBlocks:
    def test_retired_bare_page_does_not_block_disambiguation(self, tmp_path):
        entries = _colliding_entries()
        _make_api_surface(tmp_path, entries, "fake", "typescript")
        out_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "fake" / "typescript"
        _write_old_bare_page(out_dir, retired=True)

        result = _run("fake", "typescript")

        assert (out_dir / "Foo-a.md").exists()
        assert (out_dir / "Foo-b.md").exists()
        assert result["generated"] == 2
        # The retired stale page itself is left untouched (never deleted).
        assert (out_dir / "Foo.md").exists()

    def test_non_retired_bare_page_still_blocks(self, tmp_path):
        """Negative control: a genuinely stale, NOT-yet-retired bare page
        must still raise -- this check exists to force the governed
        page-retire workflow, not to be silently bypassed."""
        entries = _colliding_entries()
        _make_api_surface(tmp_path, entries, "fake", "typescript")
        out_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "fake" / "typescript"
        _write_old_bare_page(out_dir, retired=False)

        with pytest.raises(RuntimeError, match="stale undisambiguated page"):
            _run("fake", "typescript")
