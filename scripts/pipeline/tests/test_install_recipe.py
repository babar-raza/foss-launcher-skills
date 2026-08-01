"""
Tests for content_eval/evaluators/install_recipe.py (H-16 + ST-047 fix).

No test file previously existed for this evaluator (confirmed via repo-wide
search this session) despite it backing a real production gate. ST-047,
filed 2026-08-01 during the 3D-NET-REFRESH-002 remediation, found that H-16's
install-command accuracy check ran ONLY on docs.aspose.org pages -- the
19-file wrong-NuGet-command defect it should have caught spanned docs, kb,
blog, and products, so content_eval had zero visibility into 3 of the 4
surfaces. This file proves the fix: H-16 now runs on every subdomain, while
the separate "missing install instructions" INFO suggestion stays scoped to
docs/howto pages only (unchanged regression coverage).
"""

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIB_DIR = _REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from content_eval.evaluators.install_recipe import InstallRecipeEvaluator  # noqa: E402
from content_eval.models import Page  # noqa: E402
import content_eval.evaluators.install_recipe as _ir_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _knowledge_root(tmp_path):
    root = tmp_path / "knowledge"
    merged = root / "3d" / "net" / "merged"
    merged.mkdir(parents=True)
    (merged / "install.md").write_text(
        "Install via NuGet: dotnet add package Aspose.3D.Converter\n",
        encoding="utf-8",
    )
    _ir_mod.configure(knowledge_root=root)
    yield root
    _ir_mod.configure()  # reset to the real default


def _write_page(tmp_path, rel_path: str, body: str) -> Path:
    path = tmp_path / "content" / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


_WRONG_CMD_BODY = (
    "---\ntitle: Test\n---\n\n"
    "## Example\n\n"
    "```bash\n"
    "dotnet add package Aspose.3D.Foss\n"
    "```\n"
)

_CORRECT_CMD_BODY = (
    "---\ntitle: Test\n---\n\n"
    "## Example\n\n"
    "```bash\n"
    "dotnet add package Aspose.3D.Converter\n"
    "```\n"
)

_NO_INSTALL_BODY = (
    "---\ntitle: Test\n---\n\n"
    "## Example\n\n"
    "Use `Scene.Load` to open a file, then `Scene.Save` to write it, "
    "and `Node.CreateChildNode` to build the hierarchy.\n"
)


class TestH16RunsOnEverySubdomain:
    """ST-047: install-command accuracy must fire on kb/blog/products, not just docs."""

    def test_kb_page_wrong_command_flagged(self, tmp_path):
        path = _write_page(tmp_path, "kb.aspose.org/en/3d/net/how-to-install.md", _WRONG_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert len(ir) >= 1, "kb page with wrong install command should be flagged (was silently skipped pre-ST-047-fix)"

    def test_blog_page_wrong_command_flagged(self, tmp_path):
        path = _write_page(tmp_path, "blog.aspose.org/3d/net/some-post/index.md", _WRONG_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert len(ir) >= 1, "blog page with wrong install command should be flagged (was silently skipped pre-ST-047-fix)"

    def test_products_page_wrong_command_flagged(self, tmp_path):
        path = _write_page(tmp_path, "products.aspose.org/en/3d/net/_index.md", _WRONG_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert len(ir) >= 1, "products page with wrong install command should be flagged (was silently skipped pre-ST-047-fix)"

    def test_docs_page_wrong_command_still_flagged(self, tmp_path):
        """Regression: docs coverage (the only surface that worked before) must be unchanged."""
        path = _write_page(tmp_path, "docs.aspose.org/en/3d/net/developer-guide/usage.md", _WRONG_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert len(ir) >= 1

    def test_kb_page_correct_command_not_flagged(self, tmp_path):
        path = _write_page(tmp_path, "kb.aspose.org/en/3d/net/how-to-install.md", _CORRECT_CMD_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        ir = [f for f in findings if f.category == "IR"]
        assert ir == []


class TestMissingInstructionsSuggestionStaysDocsOnly:
    """Regression: the separate 'no install instructions' INFO suggestion must
    NOT start firing on kb/blog/products just because H-16 now runs there too."""

    def test_kb_page_no_install_no_missing_instructions_finding(self, tmp_path):
        path = _write_page(tmp_path, "kb.aspose.org/en/3d/net/use-cases.md", _NO_INSTALL_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        info = [f for f in findings if f.level == "INFO"]
        assert info == [], (
            "the missing-install-instructions suggestion must stay docs-only; "
            f"got INFO findings on a kb page: {info}"
        )

    def test_docs_page_no_install_still_gets_missing_instructions_finding(self, tmp_path):
        """Regression: docs/howto pages must still get the INFO suggestion, unchanged."""
        path = _write_page(tmp_path, "docs.aspose.org/en/3d/net/developer-guide/usage.md", _NO_INSTALL_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        info = [f for f in findings if f.level == "INFO"]
        assert len(info) == 1
        assert "no installation instructions" in info[0].message.lower()

    def test_docs_index_page_still_skipped_for_missing_instructions(self, tmp_path):
        path = _write_page(tmp_path, "docs.aspose.org/en/3d/net/_index.md", _NO_INSTALL_BODY)
        page = Page.load(path)
        findings = InstallRecipeEvaluator().evaluate(page, None)
        assert findings == []
