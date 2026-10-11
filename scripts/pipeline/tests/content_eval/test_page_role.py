"""Tests for page_role evaluator — _check_docs, _check_kb_index, _check_reference."""

import tempfile
import textwrap
from pathlib import Path

# sys.path set by tests/conftest.py
from content_eval.models import Page
from content_eval.evaluators.page_role import PageRoleEvaluator


def _make_page(content: str, filepath: str) -> Page:
    """Create a Page parsed from markdown content string with a given logical filepath."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


EVALUATOR = PageRoleEvaluator()


# ---------------------------------------------------------------------------
# _check_docs — platform-level _index.md
# ---------------------------------------------------------------------------

class TestCheckDocsPlatformIndex:

    def test_complete_platform_index_no_warnings(self):
        """A fully correct platform _index.md produces 0 findings."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Email FOSS for C++
            linktitle: C++
            subtitle: Aspose.Email FOSS for C++
            description: "C++ docs"
            icon: terminal
            type: docs
            weight: 40
            ---

            Requires C++17.

            Select a section to begin:

            {{< sections >}}
        """), "content/docs.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        assert findings == [], f"Unexpected findings: {[f.message for f in findings]}"

    def test_missing_linktitle_produces_warn(self):
        """Platform _index.md without linktitle produces a WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Email FOSS for C++
            subtitle: Aspose.Email FOSS for C++
            icon: terminal
            type: docs
            weight: 40
            ---

            Requires C++17.

            {{< sections >}}
        """), "content/docs.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        assert any("linktitle" in m for m in messages), f"Expected linktitle WARN, got: {messages}"

    def test_missing_sections_shortcode_produces_warn(self):
        """Platform _index.md without {{< sections >}} produces a WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Email FOSS for C++
            linktitle: C++
            subtitle: Aspose.Email FOSS for C++
            icon: terminal
            type: docs
            weight: 40
            ---

            Requires C++17.
        """), "content/docs.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        assert any("sections" in m for m in messages), f"Expected sections shortcode WARN, got: {messages}"

    def test_missing_icon_and_subtitle_produces_warns(self):
        """Platform _index.md missing both icon and subtitle produces 2 WARNs for those fields."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Email FOSS for C++
            linktitle: C++
            type: docs
            weight: 40
            ---

            Requires C++17.

            {{< sections >}}
        """), "content/docs.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        assert any("subtitle" in m for m in messages), f"Expected subtitle WARN, got: {messages}"
        assert any("icon" in m for m in messages), f"Expected icon WARN, got: {messages}"


# ---------------------------------------------------------------------------
# _check_docs — section-level _index.md must NOT get false-positive warnings
# ---------------------------------------------------------------------------

class TestCheckDocsSectionIndexNoFalsePositive:

    def test_section_index_no_false_positive_linktitle(self):
        """getting-started/_index.md without linktitle must NOT warn about linktitle."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Getting Started
            type: docs
            weight: 10
            ---

            Welcome to the getting started section.
        """), "content/docs.aspose.org/en/email/cpp/getting-started/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        linktitle_warns = [m for m in messages if "linktitle" in m]
        assert linktitle_warns == [], f"False-positive linktitle WARN on section index: {linktitle_warns}"

    def test_section_index_no_false_positive_sections_shortcode(self):
        """getting-started/_index.md without {{< sections >}} must NOT warn about shortcode."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Getting Started
            type: docs
            weight: 10
            ---

            Welcome to the getting started section.
        """), "content/docs.aspose.org/en/email/cpp/getting-started/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        sections_warns = [m for m in messages if "sections" in m and "shortcode" in m]
        assert sections_warns == [], f"False-positive sections WARN on section index: {sections_warns}"

    def test_developer_guide_index_no_false_positive(self):
        """developer-guide/_index.md must not get platform-level index warnings."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Developer Guide
            type: docs
            weight: 20
            ---

            Developer guide overview.
        """), "content/docs.aspose.org/en/email/cpp/developer-guide/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        platform_warns = [m for m in messages if "linktitle" in m or "subtitle" in m or "sections" in m]
        assert platform_warns == [], f"False-positive platform WARN on developer-guide index: {platform_warns}"


# ---------------------------------------------------------------------------
# _check_kb_index — platform-level KB _index.md
# ---------------------------------------------------------------------------

class TestCheckKbIndex:

    def test_complete_kb_index_no_warnings(self):
        """A fully correct KB _index.md produces 0 findings."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Email FOSS for C++
            linkTitle: C++
            subtitle: Aspose.Email FOSS for C++
            description: "C++ how-to guides"
            icon: terminal
            weight: 30
            ---

            Free library for reading email files.

            Browse how-to guides:

            {{< children >}}
        """), "content/kb.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        assert findings == [], f"Unexpected findings: {[f.message for f in findings]}"

    def test_missing_children_shortcode_produces_warn(self):
        """KB _index.md without {{< children >}} produces a WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Email FOSS for C++
            linkTitle: C++
            subtitle: Aspose.Email FOSS for C++
            icon: terminal
            weight: 30
            ---

            Free library for reading email files.
        """), "content/kb.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        assert any("children" in m for m in messages), f"Expected children shortcode WARN, got: {messages}"

    def test_missing_linkTitle_produces_warn(self):
        """KB _index.md without linkTitle produces a WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Aspose.Email FOSS for C++
            subtitle: Aspose.Email FOSS for C++
            icon: terminal
            weight: 30
            ---

            Free library.

            {{< children >}}
        """), "content/kb.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        assert any("linkTitle" in m for m in messages), f"Expected linkTitle WARN, got: {messages}"


# ---------------------------------------------------------------------------
# _check_reference — reference-home _index.md
# ---------------------------------------------------------------------------

class TestCheckReferenceHome:

    def test_complete_reference_home_no_warnings(self):
        """A fully correct reference _index.md produces 0 findings."""
        page = _make_page(textwrap.dedent("""\
            ---
            linkTitle: C++
            title: Aspose.Email FOSS for C++
            weight: 40
            description: Complete API reference.
            summary: Public API reference v0.1.0
            layout: reference-home
            type: reference_home
            categories:
            - API Reference
            ---

            Browse all public types.

            {{< children >}}
        """), "content/reference.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        assert findings == [], f"Unexpected findings: {[f.message for f in findings]}"

    def test_reference_home_missing_children_shortcode_produces_warn(self):
        """Reference _index.md without {{< children >}} produces a WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            linkTitle: C++
            title: Aspose.Email FOSS for C++
            weight: 40
            description: Complete API reference.
            summary: Public API reference v0.1.0
            layout: reference-home
            type: reference_home
            categories:
            - API Reference
            ---

            Browse all public types.
        """), "content/reference.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        assert any("children" in m for m in messages), f"Expected children shortcode WARN, got: {messages}"

    def test_reference_home_missing_summary_produces_warn(self):
        """Reference _index.md without summary produces a WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            linkTitle: C++
            title: Aspose.Email FOSS for C++
            weight: 40
            description: Complete API reference.
            layout: reference-home
            type: reference_home
            categories:
            - API Reference
            ---

            Browse all public types.

            {{< children >}}
        """), "content/reference.aspose.org/en/email/cpp/_index.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        assert any("summary" in m for m in messages), f"Expected summary WARN, got: {messages}"

    def test_reference_class_page_no_false_positive_children(self):
        """A reference class page (reference-single) must not get children shortcode WARN."""
        page = _make_page(textwrap.dedent("""\
            ---
            linkTitle: MapiMessage
            title: MapiMessage
            description: Represents an MSG message.
            summary: Represents an MSG message.
            layout: reference-single
            categories:
            - Class
            ---

            ## Properties

            | Name | Type | Description |
            |---|---|---|
            | Subject | string | The email subject |

            ## Usage

            ```cpp
            auto msg = mapi_message::create("Test", "Hello");
            ```
        """), "content/reference.aspose.org/en/email/cpp/mapi-message.md")
        findings = EVALUATOR.evaluate(page, None)
        messages = [f.message for f in findings]
        children_warns = [m for m in messages if "children" in m]
        assert children_warns == [], f"False-positive children WARN on class page: {children_warns}"
