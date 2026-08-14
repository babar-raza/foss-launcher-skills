"""Regression tests for RC-W1-004 (MT026 blind-spot audit, taskcard
TC-BSA-bsa-20260809T044618Z-5891c467551a-04): code-example and reference-page
identifier reachability checks.

Proven blind spot: no evaluator checked whether an identifier used in a code
example (or documented as "part of the public API" on a reference page) was
actually reachable/public for its language, as opposed to merely existing
somewhere in ``knowledge/{family}/{platform}/merged/api_surface.json``.
Confirmed real instances (one per language, all reproduced here):

  C#     cells/net docs do ``catch (XmlParsingException ex)`` --
         ``XmlParsingException`` is declared ``internal class`` in the FOSS
         source and never appears in api_surface.json at all.
  Python words/python docs do ``from aspose.words_foss import DocumentReader,
         LdmDocxWriter`` -- neither name is in the package's top-level
         ``__all__``.
  Rust   cells/rust's WorkbookModel.md reference page documents a ``pub
         struct`` wired only via a private ``mod api;``, never re-exported
         via lib.rs's ``pub use``.

Two evaluators are covered:
  - code_block_api.py (C# and Python code-block cases)
  - member_validity.py (Rust reference-page case -- WorkbookModel.md has no
    code blocks at all; the defect is the page's own subject-class claim)

Coverage:
1. C#     `reachable: false` primary signal on a `.member` access -> FAIL [CB]
2. C#     internal class in a bare `catch (Type ex)` clause (live fallback,
          no api_surface.json entry at all) -> FAIL [CB]
3. C#     public class in a `catch` clause -> no finding (negative control)
4. Python `from pkg import Name` where Name is absent from `__all__` (live
          fallback) -> FAIL [CB]
5. Python `from pkg import Name` where Name IS in `__all__` -> no finding
          (negative control)
6. Rust   reference page documenting an unreachable struct (live fallback)
          -> FAIL [MV]
7. Rust   reference page documenting a reachable struct -> no finding
          (negative control)
8. CB/MV FAILs from these checks do not force grade F (both evaluators are
   EXPERIMENTAL; only category-ceiling capping applies once canonical)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_eval.evaluators import _reachability
from content_eval.evaluators.code_block_api import CodeBlockApiEvaluator
from content_eval.evaluators.member_validity import MemberValidityEvaluator
from content_eval.models import Page
from knowledge_core import Knowledge


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_reachability_caches():
    """The live-fallback checks are lru_cache-memoized per (family, platform).
    Different tests reuse the same synthetic family/platform names against
    different fake clone-cache content, so the cache must be reset every test.
    """
    _reachability.clear_caches()
    yield
    _reachability.clear_caches()


def _make_page(tmp_path: Path, subdomain: str, family: str, platform: str,
                filename: str, body: str, frontmatter: str = "") -> Page:
    content_dir = tmp_path / "content" / f"{subdomain}.aspose.org" / "en" / family / platform
    content_dir.mkdir(parents=True, exist_ok=True)
    fm = frontmatter or "title: test\n"
    md_file = content_dir / filename
    md_file.write_text(f"---\n{fm}---\n\n{body}", encoding="utf-8")
    return Page.load(md_file)


def _make_knowledge(tmp_path: Path, family: str, platform: str, api_list: list[dict]) -> Knowledge:
    merged = tmp_path / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "model.yaml").write_text("version: '1.0'\nrepo_sha: abc123\n", encoding="utf-8")
    (merged / "api_surface.json").write_text(json.dumps(api_list), encoding="utf-8")
    return Knowledge(family, platform, knowledge_root=tmp_path)


def _fake_clone(monkeypatch, tmp_path: Path, family: str, platform: str) -> Path:
    """Redirect core.clone_cache.clone_path(family, platform) to a scratch dir
    under tmp_path, so live-fallback tests never touch the real clone cache.
    """
    repo_dir = tmp_path / "clone" / f"aspose_{family}_{platform}"
    repo_dir.mkdir(parents=True, exist_ok=True)

    import core.clone_cache as clone_cache_mod

    def _fake_path(fam: str, plat: str) -> Path:
        if fam == family and plat == platform:
            return repo_dir
        return Path("/nonexistent")

    monkeypatch.setattr(clone_cache_mod, "clone_path", _fake_path)
    return repo_dir


# ---------------------------------------------------------------------------
# 1-3: C# (catch clause, internal class, live-fallback + primary-signal)
# ---------------------------------------------------------------------------

class TestCSharpReachability:

    def test_primary_signal_reachable_false_on_member_access_fails(self, tmp_path):
        """A class explicitly tagged `reachable: false` in api_surface.json
        must FAIL even for an ordinary `.member` access (Part 1 field driving
        Part 2, no clone cache involved)."""
        body = (
            "```csharp\n"
            "var x = InternalHelper.DoWork();\n"
            "```\n"
        )
        page = _make_page(tmp_path, "docs", "cells", "net", "test.md", body)
        knowledge = _make_knowledge(tmp_path, "cells", "net", [
            {"name": "InternalHelper", "methods": [{"name": "DoWork"}],
             "properties": [], "enum_members": [], "reachable": False},
        ])

        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        assert len(fails) == 1
        assert "InternalHelper" in fails[0].message
        assert "reachable" in fails[0].message.lower()

    def test_internal_class_in_catch_clause_fails_via_live_fallback(self, tmp_path, monkeypatch):
        """Reproduces the confirmed cells/net defect exactly: `catch (Type ex)`
        referencing a class that is entirely absent from api_surface.json
        (is_public() excludes `internal` classes at scout time) -- only the
        live clone-cache fallback can catch this."""
        repo = _fake_clone(monkeypatch, tmp_path, "cells", "net")
        (repo / "XmlParsingException.cs").write_text(
            "namespace Aspose.Cells_FOSS.Xml\n"
            "{\n"
            "    internal class XmlParsingException : Exception\n"
            "    {\n"
            "        public XmlParsingException(string message) : base(message) { }\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        body = (
            "```csharp\n"
            "try\n"
            "{\n"
            "    var wb = new Workbook(\"malformed.xlsx\");\n"
            "}\n"
            "catch (XmlParsingException ex)\n"
            "{\n"
            "    Console.WriteLine(ex.Message);\n"
            "}\n"
            "```\n"
        )
        page = _make_page(tmp_path, "docs", "cells", "net", "test.md", body)
        # Workbook exists and is reachable; XmlParsingException is absent
        # entirely (mirrors the real api_surface.json for cells/net).
        knowledge = _make_knowledge(tmp_path, "cells", "net", [
            {"name": "Workbook", "methods": [], "properties": [],
             "enum_members": [], "reachable": True},
        ])

        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        assert len(fails) == 1, f"expected exactly 1 FAIL, got: {findings}"
        assert "XmlParsingException" in fails[0].message
        assert "internal" in fails[0].message.lower()

    def test_public_class_in_catch_clause_is_negative_control(self, tmp_path, monkeypatch):
        """A genuinely public exception class in the same `catch (Type ex)`
        shape must produce no reachability finding."""
        repo = _fake_clone(monkeypatch, tmp_path, "cells", "net")
        (repo / "WorkbookLoadException.cs").write_text(
            "namespace Aspose.Cells_FOSS\n"
            "{\n"
            "    public class WorkbookLoadException : Exception\n"
            "    {\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
        body = (
            "```csharp\n"
            "try\n"
            "{\n"
            "    var wb = new Workbook(\"file.xlsx\");\n"
            "}\n"
            "catch (WorkbookLoadException ex)\n"
            "{\n"
            "    Console.WriteLine(ex.Message);\n"
            "}\n"
            "```\n"
        )
        page = _make_page(tmp_path, "docs", "cells", "net", "test.md", body)
        knowledge = _make_knowledge(tmp_path, "cells", "net", [
            {"name": "Workbook", "methods": [], "properties": [],
             "enum_members": [], "reachable": True},
        ])

        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        assert fails == [], f"expected no FAIL findings, got: {fails}"


# ---------------------------------------------------------------------------
# 4-5: Python (from-import list, live fallback via __all__)
# ---------------------------------------------------------------------------

class TestPythonReachability:

    def test_non_exported_class_in_import_fails_via_live_fallback(self, tmp_path, monkeypatch):
        """Reproduces the confirmed words/python defect exactly: `from pkg
        import Name` where Name is a real, documented class in
        api_surface.json but is absent from the package's top-level
        `__all__` -- ImportError for a real reader."""
        repo = _fake_clone(monkeypatch, tmp_path, "words", "python")
        pkg_dir = repo / "aspose" / "words_foss"
        pkg_dir.mkdir(parents=True)
        (repo / "aspose" / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "__init__.py").write_text(
            "from .document import Document\n"
            "__all__ = ['Document']\n",
            encoding="utf-8",
        )
        body = (
            "```python\n"
            "from aspose.words_foss import DocumentReader, LdmDocxWriter\n"
            "\n"
            "reader = DocumentReader()\n"
            "```\n"
        )
        # No `reachable` key -- represents knowledge that hasn't been
        # re-scouted since Part 1 landed, so the primary signal is absent
        # and the evaluator must fall through to the live clone-cache check.
        page = _make_page(tmp_path, "docs", "words", "python", "test.md", body)
        knowledge = _make_knowledge(tmp_path, "words", "python", [
            {"name": "DocumentReader", "methods": [], "properties": [], "enum_members": []},
            {"name": "LdmDocxWriter", "methods": [], "properties": [], "enum_members": []},
        ])

        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        fail_classes = {f.message.split("`")[1] for f in fails}
        assert fail_classes == {"DocumentReader", "LdmDocxWriter"}, findings
        assert all("__all__" in f.message or "ImportError" in f.message for f in fails)

    def test_exported_class_in_import_is_negative_control(self, tmp_path, monkeypatch):
        """A class that IS in the package's `__all__` must produce no finding."""
        repo = _fake_clone(monkeypatch, tmp_path, "words", "python")
        pkg_dir = repo / "aspose" / "words_foss"
        pkg_dir.mkdir(parents=True)
        (repo / "aspose" / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "__init__.py").write_text(
            "from .document import Document\n"
            "__all__ = ['Document']\n",
            encoding="utf-8",
        )
        body = (
            "```python\n"
            "from aspose.words_foss import Document\n"
            "\n"
            "doc = Document()\n"
            "```\n"
        )
        page = _make_page(tmp_path, "docs", "words", "python", "test.md", body)
        knowledge = _make_knowledge(tmp_path, "words", "python", [
            {"name": "Document", "methods": [], "properties": [],
             "enum_members": [], "reachable": True},
        ])

        findings = CodeBlockApiEvaluator().evaluate(page, knowledge)
        fails = [f for f in findings if f.level == "FAIL" and f.category == "CB"]
        assert fails == [], f"expected no FAIL findings, got: {fails}"


# ---------------------------------------------------------------------------
# 6-7: Rust (reference page subject-class reachability, live fallback via
# lib.rs `pub use`)
# ---------------------------------------------------------------------------

class TestRustReachability:

    def _make_ref_page(self, tmp_path: Path, class_name: str) -> Page:
        ref_dir = tmp_path / "content" / "reference.aspose.org" / "en" / "cells" / "rust"
        ref_dir.mkdir(parents=True, exist_ok=True)
        md_file = ref_dir / f"{class_name}.md"
        frontmatter = (
            f"linktitle: {class_name}\ntitle: {class_name}\n"
            "provenance:\n  content_origin: skill-generated\n"
            "  last_mechanism: skill\n  auto_updatable: true\n"
        )
        body = (
            f"## Overview\n\n`{class_name}` is a struct in Aspose.Cells FOSS "
            f"for Rust.\nThis struct is part of the public API.\n"
        )
        md_file.write_text(f"---\n{frontmatter}---\n\n{body}", encoding="utf-8")
        return Page.load(md_file)

    def test_unreachable_struct_reference_page_fails_via_live_fallback(self, tmp_path, monkeypatch):
        """Reproduces the confirmed cells/rust defect exactly: a reference
        page documents a `pub struct` that is wired only via a private `mod
        api;` and never re-exported by lib.rs's `pub use` block."""
        repo = _fake_clone(monkeypatch, tmp_path, "cells", "rust")
        (repo / "lib.rs").write_text(
            '#[path = "Aspose.Cells_FOSS/api.rs"]\n'
            "mod api;\n"
            "\n"
            "pub use api::{\n"
            "    Workbook, Worksheet, Cell,\n"
            "};\n",
            encoding="utf-8",
        )
        page = self._make_ref_page(tmp_path, "WorkbookModel")
        knowledge_dir = tmp_path / "cells" / "rust" / "merged"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        (knowledge_dir / "api_surface.json").write_text(json.dumps([
            {"name": "WorkbookModel", "properties": [{"name": "sheet_count"}],
             "methods": [], "enum_members": []},
        ]), encoding="utf-8")

        findings = MemberValidityEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL" and f.line_no == 0]
        assert len(fails) == 1, f"expected exactly 1 class-reachability FAIL, got: {findings}"
        assert "WorkbookModel" in fails[0].message
        assert "pub use" in fails[0].message

    def test_reachable_struct_reference_page_is_negative_control(self, tmp_path, monkeypatch):
        """A struct that IS re-exported via `pub use` must produce no
        class-reachability finding."""
        repo = _fake_clone(monkeypatch, tmp_path, "cells", "rust")
        (repo / "lib.rs").write_text(
            '#[path = "Aspose.Cells_FOSS/api.rs"]\n'
            "mod api;\n"
            "\n"
            "pub use api::{\n"
            "    Workbook, Worksheet, Cell,\n"
            "};\n",
            encoding="utf-8",
        )
        page = self._make_ref_page(tmp_path, "Workbook")
        knowledge_dir = tmp_path / "cells" / "rust" / "merged"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        (knowledge_dir / "api_surface.json").write_text(json.dumps([
            {"name": "Workbook", "properties": [{"name": "sheet_count"}],
             "methods": [], "enum_members": []},
        ]), encoding="utf-8")

        findings = MemberValidityEvaluator().evaluate(page, None)
        fails = [f for f in findings if f.level == "FAIL" and f.line_no == 0]
        assert fails == [], f"expected no class-reachability FAIL, got: {fails}"


# ---------------------------------------------------------------------------
# 8: Grade-ceiling behavior (both evaluators are EXPERIMENTAL)
# ---------------------------------------------------------------------------

class TestReachabilityGradeCeiling:

    def test_cb_reachability_fail_does_not_force_grade_f(self):
        from content_eval.models import Finding, compute_grade_with_criticality

        findings = [Finding(
            level="FAIL", category="CB", filepath="test.md", line_no=10,
            message="Code references `XmlParsingException` — declared `internal`",
            evaluator="code_block_api",
        )]
        grade = compute_grade_with_criticality(findings)
        assert grade == "A", (
            f"code_block_api is EXPERIMENTAL — its FAIL must not affect the "
            f"canonical grade; got {grade}"
        )

    def test_mv_reachability_fail_does_not_force_grade_f(self):
        from content_eval.models import Finding, compute_grade_with_criticality

        findings = [Finding(
            level="FAIL", category="MV", filepath="test.md", line_no=0,
            message="This page documents `WorkbookModel` as public API, but "
                    "it is not re-exported",
            evaluator="member_validity",
        )]
        grade = compute_grade_with_criticality(findings)
        assert grade == "A", (
            f"member_validity is EXPERIMENTAL — its FAIL must not affect the "
            f"canonical grade; got {grade}"
        )
