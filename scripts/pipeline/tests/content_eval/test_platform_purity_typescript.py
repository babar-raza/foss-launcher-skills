"""Tests for G-TS-03 (MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH TC-MT040-19):
PROSE_FOREIGN_PATTERNS previously had no typescript/javascript entry, so
platform_purity.py never checked TypeScript/JavaScript page prose for
cross-platform install-command contamination (pip install, NuGet,
dotnet add package, maven, cargo add, go get) even though every other
platform already had this check.
"""
import tempfile
import textwrap
from pathlib import Path

from content_eval.models import Page


def _make_page(content: str, filepath: str) -> Page:
    """Create a Page from markdown content string (mirrors test_evaluators.py's
    own _make_page helper, duplicated here so this file has no import-order
    dependency on that module)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


class TestPlatformPurityTypeScript:
    def setup_method(self):
        from content_eval.evaluators.platform_purity import PlatformPurityEvaluator
        self.evaluator = PlatformPurityEvaluator()

    def test_pip_install_in_typescript_page_is_flagged(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Install using pip install aspose-pdf-foss.
        """), "content/docs.aspose.org/en/pdf/typescript/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert len(prose_findings) >= 1
        assert any("pip install" in f.message.lower() for f in prose_findings)

    def test_maven_reference_in_typescript_page_is_flagged(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Add the maven dependency to your build.
        """), "content/docs.aspose.org/en/pdf/typescript/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert len(prose_findings) >= 1

    def test_dotnet_add_package_in_typescript_page_is_flagged(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Run dotnet add package Aspose.Pdf.Foss to install.
        """), "content/docs.aspose.org/en/pdf/typescript/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert len(prose_findings) >= 1

    def test_cargo_add_in_typescript_page_is_flagged(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            You could also cargo add aspose-pdf-foss in a Rust project.
        """), "content/docs.aspose.org/en/pdf/typescript/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert len(prose_findings) >= 1

    def test_go_get_in_typescript_page_is_flagged(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Or go get github.com/aspose-pdf-foss/... for the Go port.
        """), "content/docs.aspose.org/en/pdf/typescript/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert len(prose_findings) >= 1

    def test_npm_install_in_typescript_page_is_native_not_flagged(self):
        """npm install is native to TypeScript/JavaScript -- must never be
        flagged as cross-platform contamination on a TS/JS page (unlike
        every other pattern above, which IS foreign to TypeScript)."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Install using npm install @asposefoss/pdf.
        """), "content/docs.aspose.org/en/pdf/typescript/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert prose_findings == []

    def test_javascript_page_mirrors_typescript(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Install using pip install aspose-pdf-foss.
        """), "content/docs.aspose.org/en/pdf/javascript/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert len(prose_findings) >= 1

    def test_clean_typescript_prose_is_not_flagged(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Aspose.PDF for TypeScript is a zero-dependency library for Node.js.
        """), "content/docs.aspose.org/en/pdf/typescript/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert prose_findings == []

    def test_rust_pattern_list_is_unchanged(self):
        """Regression pin: adding typescript/javascript entries must not
        touch the existing rust entry (byte-for-byte same list)."""
        from content_eval.config import PROSE_FOREIGN_PATTERNS
        assert PROSE_FOREIGN_PATTERNS["rust"] == [
            (r"\bpip\s+install\b", "Python pip install in Rust page"),
            (r"\bNuGet\b", "NuGet reference in Rust page"),
            (r"\bmaven\b", "Maven reference in Rust page"),
            (r"\bnpm\s+install\b", "npm install in Rust page"),
        ]

    def test_net_page_still_flags_npm_install(self):
        """Negative control: a .NET page must still flag npm install as
        foreign -- this addition does not weaken any OTHER platform's list."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Install using npm install aspose-pdf-foss.
        """), "content/docs.aspose.org/en/pdf/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert len(prose_findings) >= 1
