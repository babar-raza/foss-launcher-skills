"""Tests for module_compilability.py -- RC-tex-python-05
(MT037-2026-08-24-FOSS-PORTFOLIO-FORENSIC-HEAL).

Proven blind spot: no evaluator checked whether a page's cited public API
class's own source file actually compiles against the pinned clone cache.
tex/python's presentation/__init__.py (defining TeXJob, TeXOptions, and all
3 output devices) fails py_compile with IndentationError -- confirmed live,
35/45 files in the whole package fail identically -- yet every other
evaluator returned clean results for pages built entirely around this
non-importable module.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_eval.evaluators import module_compilability as _mc
from content_eval.evaluators.module_compilability import ModuleCompilabilityEvaluator
from content_eval.models import Page
from knowledge_core import Knowledge


@pytest.fixture(autouse=True)
def _reset_configure():
    """The evaluator caches compile results per (family, platform, file) --
    reset between tests since each test uses a fresh tmp_path clone dir."""
    yield
    _mc.configure(clone_cache_root=None)


def _make_page(tmp_path: Path, family: str, platform: str, filename: str,
                apis: list[str]) -> Page:
    content_dir = tmp_path / "content" / "docs.aspose.org" / "en" / family / platform
    content_dir.mkdir(parents=True, exist_ok=True)
    fm = (
        "title: test\n"
        "evidence:\n"
        f"  apis: {json.dumps(apis)}\n"
    )
    md_file = content_dir / filename
    md_file.write_text(f"---\n{fm}---\n\nBody.\n", encoding="utf-8")
    return Page.load(md_file)


def _make_knowledge(tmp_path: Path, family: str, platform: str, api_list: list[dict]) -> Knowledge:
    merged = tmp_path / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "model.yaml").write_text("version: '1.0'\nrepo_sha: abc123\n", encoding="utf-8")
    (merged / "api_surface.json").write_text(json.dumps(api_list), encoding="utf-8")
    return Knowledge(family, platform, knowledge_root=tmp_path)


def _write_clone_file(tmp_path: Path, rel_file: str, source: str) -> Path:
    clone_dir = tmp_path / "clone"
    target = clone_dir / rel_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    _mc.configure(clone_cache_root=clone_dir)
    return clone_dir


class TestModuleCompilability:

    def test_broken_module_produces_fail(self, tmp_path):
        """The exact real-world bug: a class's own file has a genuine syntax
        error (mirrors tex/python's collapsed-indent for-loop body)."""
        broken_source = (
            "class Widget:\n"
            "    def build(self):\n"
            "        for c in range(3):\n"
            "        print(c)\n"  # body not indented deeper than the for -- IndentationError
        )
        _write_clone_file(tmp_path, "src/pkg/widget.py", broken_source)
        page = _make_page(tmp_path, "acme", "python", "test.md", ["Widget"])
        knowledge = _make_knowledge(tmp_path, "acme", "python", [
            {"name": "Widget", "file": "src/pkg/widget.py", "methods": [], "properties": []},
        ])

        findings = ModuleCompilabilityEvaluator().evaluate(page, knowledge)

        assert len(findings) == 1
        assert findings[0].level == "FAIL"
        assert findings[0].category == "MC"
        assert "Widget" in findings[0].message
        assert "widget.py" in findings[0].message

    def test_clean_module_produces_no_finding(self, tmp_path):
        """Negative control: a genuinely valid module must not be flagged."""
        clean_source = (
            "class Widget:\n"
            "    def build(self):\n"
            "        for c in range(3):\n"
            "            print(c)\n"
        )
        _write_clone_file(tmp_path, "src/pkg/widget.py", clean_source)
        page = _make_page(tmp_path, "acme", "python", "test.md", ["Widget"])
        knowledge = _make_knowledge(tmp_path, "acme", "python", [
            {"name": "Widget", "file": "src/pkg/widget.py", "methods": [], "properties": []},
        ])

        findings = ModuleCompilabilityEvaluator().evaluate(page, knowledge)

        assert findings == []

    def test_non_python_platform_is_out_of_scope(self, tmp_path):
        """Deliberate scope limitation: other languages need their own real
        toolchain, not silently pretended to be covered."""
        _write_clone_file(tmp_path, "src/Widget.cs", "public class Widget {}")
        page = _make_page(tmp_path, "acme", "net", "test.md", ["Widget"])
        knowledge = _make_knowledge(tmp_path, "acme", "net", [
            {"name": "Widget", "file": "src/Widget.cs", "methods": [], "properties": []},
        ])

        findings = ModuleCompilabilityEvaluator().evaluate(page, knowledge)

        assert findings == []

    def test_missing_clone_cache_does_not_fabricate_a_failure(self, tmp_path):
        """Absence of proof is not proof of absence -- a page must never be
        penalized just because the clone cache isn't available to check."""
        _mc.configure(clone_cache_root=tmp_path / "nonexistent")
        page = _make_page(tmp_path, "acme", "python", "test.md", ["Widget"])
        knowledge = _make_knowledge(tmp_path, "acme", "python", [
            {"name": "Widget", "file": "src/pkg/widget.py", "methods": [], "properties": []},
        ])

        findings = ModuleCompilabilityEvaluator().evaluate(page, knowledge)

        assert findings == []

    def test_no_apis_cited_produces_no_finding(self, tmp_path):
        page = _make_page(tmp_path, "acme", "python", "test.md", [])
        knowledge = _make_knowledge(tmp_path, "acme", "python", [])

        findings = ModuleCompilabilityEvaluator().evaluate(page, knowledge)

        assert findings == []

    def test_duplicate_file_across_multiple_apis_reported_once(self, tmp_path):
        """Two classes defined in the same broken file must produce exactly
        one finding, not one per class."""
        broken_source = (
            "class A:\n"
            "    def m(self):\n"
            "        for c in range(3):\n"
            "        print(c)\n"
        )
        _write_clone_file(tmp_path, "src/pkg/multi.py", broken_source)
        page = _make_page(tmp_path, "acme", "python", "test.md", ["A", "B"])
        knowledge = _make_knowledge(tmp_path, "acme", "python", [
            {"name": "A", "file": "src/pkg/multi.py", "methods": [], "properties": []},
            {"name": "B", "file": "src/pkg/multi.py", "methods": [], "properties": []},
        ])

        findings = ModuleCompilabilityEvaluator().evaluate(page, knowledge)

        assert len(findings) == 1
