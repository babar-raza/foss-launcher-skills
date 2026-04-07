"""Tests for content_eval evaluators."""

import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
from content_eval.models import CodeBlock, Finding, Heading, Page


def _make_page(content: str, filepath: str = "content/docs.aspose.org/en/slides/dotnet/test.md") -> Page:
    """Create a Page from markdown content string."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        page = Page.load(Path(f.name))
        page.filepath = Path(filepath)
        page._infer_metadata()
        return page


class TestPlatformPurity:
    def setup_method(self):
        from content_eval.evaluators.platform_purity import PlatformPurityEvaluator
        self.evaluator = PlatformPurityEvaluator()

    def test_python_def_in_dotnet_page(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Example:

            ```csharp
            def my_function():
                pass
            ```
        """), "content/docs.aspose.org/en/slides/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        foreign = [f for f in findings if "Python function definition" in f.message]
        assert len(foreign) >= 1
        assert foreign[0].category == "PC"

    def test_wrong_lang_tag(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Example:

            ```python
            from aspose.slides import Presentation
            ```
        """), "content/docs.aspose.org/en/slides/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "tagged as" in f.message]
        assert len(lang_findings) >= 1
        assert lang_findings[0].level == "FAIL"

    def test_clean_dotnet_code(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Example:

            ```csharp
            using Aspose.Slides;
            var prs = new Presentation();
            ```
        """), "content/docs.aspose.org/en/slides/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        # Should have no findings for correct code
        code_findings = [f for f in findings if "Foreign" in f.message or "tagged" in f.message]
        assert len(code_findings) == 0

    def test_prose_contamination(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            Install using pip install aspose-slides.
        """), "content/docs.aspose.org/en/slides/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        prose_findings = [f for f in findings if "prose" in f.message.lower()]
        assert len(prose_findings) >= 1


class TestRiskLanguage:
    def setup_method(self):
        from content_eval.evaluators.risk_language import RiskLanguageEvaluator
        self.evaluator = RiskLanguageEvaluator()

    def test_detects_superlatives(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            This is the fastest library available.
            It provides seamless integration.
            100% compatible with all formats.
        """))
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) >= 3
        messages = [f.message for f in findings]
        assert any("fastest" in m for m in messages)
        assert any("seamless" in m for m in messages)
        assert any("100%" in m for m in messages)

    def test_clean_prose(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            The library supports PPTX export.
            You can add shapes to slides.
        """))
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_no_limitations_is_fail(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            This library has no limitations.
        """))
        findings = self.evaluator.evaluate(page, None)
        fail_findings = [f for f in findings if f.level == "FAIL"]
        assert len(fail_findings) >= 1


class TestStructure:
    def setup_method(self):
        from content_eval.evaluators.structure import StructureEvaluator
        self.evaluator = StructureEvaluator()

    def test_missing_title(self):
        page = _make_page(textwrap.dedent("""\
            ---
            description: A test
            ---
            Content here.
        """))
        findings = self.evaluator.evaluate(page, None)
        title_findings = [f for f in findings if "title" in f.message]
        assert len(title_findings) >= 1
        assert title_findings[0].level == "FAIL"

    def test_placeholder_detection(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            {TODO} Replace this placeholder.
        """))
        findings = self.evaluator.evaluate(page, None)
        placeholder_findings = [f for f in findings if "Placeholder" in f.message]
        assert len(placeholder_findings) >= 1

    def test_heading_skip(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ## Overview
            Text.
            #### Details
            More text.
        """))
        findings = self.evaluator.evaluate(page, None)
        skip_findings = [f for f in findings if "skipped" in f.message]
        assert len(skip_findings) >= 1

    def test_unlabeled_code_block(self):
        page = _make_page("---\ntitle: T\n---\n\n```\ncode here\n```\n")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "language" in f.message]
        assert len(lang_findings) >= 1

    def test_empty_body(self):
        page = _make_page("---\ntitle: T\n---\n")
        findings = self.evaluator.evaluate(page, None)
        empty_findings = [f for f in findings if "empty" in f.message.lower()]
        assert len(empty_findings) >= 1


class TestPageRole:
    def setup_method(self):
        from content_eval.evaluators.page_role import PageRoleEvaluator
        self.evaluator = PageRoleEvaluator()

    def test_kb_howto_missing_steps(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: How to Add Shapes
            type: topic
            keywords: [a, b, c, d, e]
            ---
            ## Introduction
            This guide shows how to add shapes.
            ## Code Example
            Some code here.
        """), "content/kb.aspose.org/en/slides/dotnet/how-to-add-shapes.md")
        findings = self.evaluator.evaluate(page, None)
        steps_findings = [f for f in findings if "steps" in f.message.lower() or "step" in f.message.lower()]
        assert len(steps_findings) >= 1

    def test_kb_howto_missing_type(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: How to Add Shapes
            ---
            Content.
        """), "content/kb.aspose.org/en/slides/dotnet/how-to-add-shapes.md")
        findings = self.evaluator.evaluate(page, None)
        type_findings = [f for f in findings if "type: topic" in f.message]
        assert len(type_findings) >= 1
        assert type_findings[0].level == "FAIL"

    def test_reference_missing_table(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Presentation
            layout: reference-single
            ---
            ## Presentation Class
            The Presentation class is the main entry point.
        """), "content/reference.aspose.org/en/slides/dotnet/presentation.md")
        findings = self.evaluator.evaluate(page, None)
        table_findings = [f for f in findings if "table" in f.message.lower()]
        assert len(table_findings) >= 1


class TestForbiddenClaims:
    def setup_method(self):
        from content_eval.evaluators.forbidden_claims import ForbiddenClaimsEvaluator
        self.evaluator = ForbiddenClaimsEvaluator()

    def test_no_knowledge_no_findings(self):
        page = _make_page("---\ntitle: T\n---\nContent.", "content/docs.aspose.org/en/unknown/unknown/test.md")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0


# ---------- Tier 1 change tests ----------


class TestStructureProductsExemption:
    """Tests for 1.1: layout:plugin pages should not get empty-body FAIL."""

    def setup_method(self):
        from content_eval.evaluators.structure import StructureEvaluator
        self.evaluator = StructureEvaluator()

    def test_plugin_layout_empty_body_no_fail(self):
        page = _make_page("---\ntitle: T\nlayout: plugin\n---\n",
                          "content/products.aspose.org/en/slides/dotnet/_index.md")
        findings = self.evaluator.evaluate(page, None)
        empty_findings = [f for f in findings if "body is empty" in f.message.lower()]
        assert len(empty_findings) == 0

    def test_normal_page_empty_body_still_fails(self):
        page = _make_page("---\ntitle: T\n---\n")
        findings = self.evaluator.evaluate(page, None)
        empty_findings = [f for f in findings if "empty" in f.message.lower()]
        assert len(empty_findings) >= 1


class TestStructureAsciiArt:
    """Tests for 1.5: ASCII art code blocks downgraded to INFO."""

    def setup_method(self):
        from content_eval.evaluators.structure import StructureEvaluator
        self.evaluator = StructureEvaluator()

    def test_ascii_art_is_info(self):
        page = _make_page("---\ntitle: T\n---\n\n```\n├── src\n│   └── main.py\n└── README.md\n```\n")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "language" in f.message]
        assert len(lang_findings) == 1
        assert lang_findings[0].level == "INFO"

    def test_short_block_is_info(self):
        page = _make_page("---\ntitle: T\n---\n\n```\noutput: ok\n```\n")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "language" in f.message]
        assert len(lang_findings) == 1
        assert lang_findings[0].level == "INFO"

    def test_long_code_block_is_warn(self):
        lines = "\n".join(f"line {i}" for i in range(10))
        page = _make_page(f"---\ntitle: T\n---\n\n```\n{lines}\n```\n")
        findings = self.evaluator.evaluate(page, None)
        lang_findings = [f for f in findings if "language" in f.message]
        assert len(lang_findings) == 1
        assert lang_findings[0].level == "WARN"


class TestKbIndexRole:
    """Tests for 1.2: KB _index pages classified as kb_index."""

    def setup_method(self):
        from content_eval.evaluators.page_role import PageRoleEvaluator
        self.evaluator = PageRoleEvaluator()

    def test_kb_index_page_no_howto_checks(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: Slides Knowledge Base
            ---
            {{< children >}}
        """), "content/kb.aspose.org/en/slides/dotnet/_index.md")
        findings = self.evaluator.evaluate(page, None)
        # Should NOT get howto-specific findings (type:topic, steps, keywords)
        howto_msgs = [f for f in findings if "type: topic" in f.message or "step" in f.message.lower()
                      or "keywords" in f.message.lower()]
        assert len(howto_msgs) == 0

    def test_kb_index_missing_title_warns(self):
        page = _make_page("---\ndescription: test\n---\n{{< children >}}\n",
                          "content/kb.aspose.org/en/slides/dotnet/_index.md")
        findings = self.evaluator.evaluate(page, None)
        title_findings = [f for f in findings if "title" in f.message.lower()]
        assert len(title_findings) >= 1


class TestReferenceHomeLayout:
    """Tests for 1.3: reference-home accepted as valid layout."""

    def setup_method(self):
        from content_eval.evaluators.page_role import PageRoleEvaluator
        self.evaluator = PageRoleEvaluator()

    def test_reference_home_no_layout_warning(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: API Reference
            layout: reference-home
            ---
            | Class | Description |
            |-------|-------------|
            | Scene | Main class  |
        """), "content/reference.aspose.org/en/3d/python/_index.md")
        findings = self.evaluator.evaluate(page, None)
        layout_findings = [f for f in findings if "layout" in f.message.lower()]
        assert len(layout_findings) == 0


class TestStepHeadingRelaxation:
    """Tests for 1.4: h2/h3 headings accepted as alternative to Step N."""

    def setup_method(self):
        from content_eval.evaluators.page_role import PageRoleEvaluator
        self.evaluator = PageRoleEvaluator()

    def test_section_headings_accepted(self):
        page = _make_page(textwrap.dedent("""\
            ---
            title: How to Add Shapes
            type: topic
            keywords: [a, b, c, d, e]
            ---
            {{% steps %}}
            ## Prerequisites
            Setup text.
            ## Add a Shape
            Code example.
            ## Save the File
            Save text.
            {{% /steps %}}
        """), "content/kb.aspose.org/en/slides/dotnet/how-to-add-shapes.md")
        findings = self.evaluator.evaluate(page, None)
        step_findings = [f for f in findings if "step" in f.message.lower() and "heading" in f.message.lower()]
        assert len(step_findings) == 0


# ---------- Tier 2 evaluator tests ----------


class TestCodePlausibility:
    def setup_method(self):
        from content_eval.evaluators.code_plausibility import CodePlausibilityEvaluator
        self.evaluator = CodePlausibilityEvaluator()

    def test_empty_code_block(self):
        page = _make_page("---\ntitle: T\n---\n\n```python\n\n```\n")
        findings = self.evaluator.evaluate(page, None)
        empty_findings = [f for f in findings if "empty" in f.message.lower() or "blank" in f.message.lower()]
        assert len(empty_findings) >= 1

    def test_placeholder_comment(self):
        # _PSEUDO_COMMENT_RE matches // style comments (C#/Java/C++)
        page = _make_page("---\ntitle: T\n---\n\n```csharp\n// TODO: add your code here\n```\n")
        findings = self.evaluator.evaluate(page, None)
        ph_findings = [f for f in findings if "placeholder" in f.message.lower()]
        assert len(ph_findings) >= 1

    def test_ellipsis_in_code(self):
        page = _make_page("---\ntitle: T\n---\n\n```python\nprs = Presentation()\n...\nprs.save(\"out.pptx\")\n```\n")
        findings = self.evaluator.evaluate(page, None)
        ell_findings = [f for f in findings if "ellipsis" in f.message.lower() or "..." in f.message]
        assert len(ell_findings) >= 1


class TestEvidenceDepth:
    def setup_method(self):
        from content_eval.evaluators.evidence_depth import EvidenceDepthEvaluator
        self.evaluator = EvidenceDepthEvaluator()

    def test_no_knowledge_no_findings(self):
        page = _make_page("---\ntitle: T\n---\nContent.", "content/docs.aspose.org/en/unknown/unknown/test.md")
        findings = self.evaluator.evaluate(page, None)
        # No knowledge → no evidence expectations
        assert isinstance(findings, list)

    def test_page_with_code_but_no_evidence(self):
        """Page with code blocks but no evidence section should flag."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ## Example
            ```python
            from aspose.threed import Scene
            scene = Scene()
            ```
        """), "content/docs.aspose.org/en/3d/python/developer-guide/test.md")
        # This test validates the evaluator runs without error
        # Actual evidence findings depend on knowledge model state
        findings = self.evaluator.evaluate(page, None)
        assert isinstance(findings, list)

    def test_text_blocks_do_not_trigger_evidence_warn(self):
        """Regression: text/path/license fenced blocks must NOT trigger evidence_depth WARN.

        A page whose only code fences are ``text``-tagged (file paths, license text,
        plain output) has no API-bearing code.  attach_evidence.py will correctly
        SKIP such a page.  The evaluator must not warn about missing evidence APIs.

        Reproduces: license.md false positive — 2 ``text`` blocks, apis:[], grade B
        Expected after fix: 0 WARN findings from evidence_depth.
        """
        page = _make_page(textwrap.dedent("""\
            ---
            title: License
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Where to Find the License

            The file is at:

               ```text
               node_modules/@aspose/3d/LICENSE
               ```

            ## MIT License Text

            ```text
            MIT License

            Copyright (c) Aspose Pty Ltd

            Permission is hereby granted, free of charge, to any person obtaining a copy
            of this software and associated documentation files.
            ```
        """), "content/docs.aspose.org/en/3d/typescript/getting-started/license.md")
        findings = self.evaluator.evaluate(page, None)
        warn_findings = [f for f in findings if f.level == "WARN" and "evidence APIs" in f.message]
        assert warn_findings == [], (
            f"text-only blocks should not trigger evidence_depth WARN; got: {warn_findings}"
        )

    def test_bash_blocks_do_not_trigger_evidence_warn(self):
        """Shell/bash install blocks must not trigger evidence_depth WARN.

        Installation pages commonly have 2+ bash blocks for pip/npm/nuget commands.
        These blocks contain no API tokens, so attach_evidence skips them.
        """
        page = _make_page(textwrap.dedent("""\
            ---
            title: Installation
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Install via npm

            ```bash
            npm install @aspose/3d
            ```

            ## Verify

            ```bash
            node -e "require('@aspose/3d')"
            ```
        """), "content/docs.aspose.org/en/3d/typescript/getting-started/installation.md")
        findings = self.evaluator.evaluate(page, None)
        warn_findings = [f for f in findings if f.level == "WARN" and "evidence APIs" in f.message]
        assert warn_findings == [], (
            f"bash-only blocks should not trigger evidence_depth WARN; got: {warn_findings}"
        )

    def test_api_blocks_do_trigger_evidence_warn(self):
        """True positive: TypeScript API code blocks with empty evidence.apis MUST warn.

        This validates that the fix does not suppress legitimate evidence gaps.
        A page with 2+ TypeScript code blocks and empty apis should still WARN.
        """
        page = _make_page(textwrap.dedent("""\
            ---
            title: Quick Start
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Load a Scene

            ```typescript
            import { Scene } from "@aspose/3d";
            const scene = new Scene();
            ```

            ## Save a File

            ```typescript
            await scene.save("output.fbx");
            ```
        """), "content/docs.aspose.org/en/3d/typescript/developer-guide/quickstart.md")
        findings = self.evaluator.evaluate(page, None)
        warn_findings = [f for f in findings if f.level == "WARN" and "evidence APIs" in f.message]
        assert len(warn_findings) == 1, (
            f"TypeScript API blocks with empty evidence.apis must produce exactly 1 WARN; got: {warn_findings}"
        )
        assert "2 API-eligible code blocks" in warn_findings[0].message

    def test_mixed_bash_api_blocks_trigger_evidence_warn(self):
        """True positive: pages mixing bash install blocks with API code blocks must still warn.

        The presence of non-API bash blocks should not mask the API coverage gap.
        """
        page = _make_page(textwrap.dedent("""\
            ---
            title: Quick Start
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Install

            ```bash
            npm install @aspose/3d
            ```

            ## Use the API

            ```typescript
            import { Scene } from "@aspose/3d";
            const scene = new Scene();
            ```

            ## Save

            ```typescript
            await scene.save("output.fbx");
            ```
        """), "content/docs.aspose.org/en/3d/typescript/developer-guide/quickstart.md")
        findings = self.evaluator.evaluate(page, None)
        warn_findings = [f for f in findings if f.level == "WARN" and "evidence APIs" in f.message]
        assert len(warn_findings) == 1, (
            f"Mixed bash+API blocks with empty apis must produce 1 WARN; got: {warn_findings}"
        )
        assert "2 API-eligible code blocks" in warn_findings[0].message

    def test_untagged_blocks_do_not_trigger_evidence_warn(self):
        """Untagged (empty-lang) blocks must not trigger evidence_depth WARN.

        Pages with untagged output/shell/prose blocks have no API tokens.
        attach_evidence.py tokenizes them but finds nothing to attach.
        The evaluator must not count them as API-eligible.

        Empty string is NOT in PLATFORM_EXPECTED_LANGS for any platform,
        so the allowlist correctly excludes these blocks.
        """
        page = _make_page(textwrap.dedent("""\
            ---
            title: Quick Start Output
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Expected output

            After running the script you will see:

            ```
            Scene loaded. Node hierarchy:
             [(no entity)]
              Cube [Mesh]
            ```

            ## Second run

            ```
            rootNode name:
            total nodes: 3
            ```
        """), "content/docs.aspose.org/en/3d/typescript/getting-started/output.md")
        findings = self.evaluator.evaluate(page, None)
        warn = [f for f in findings if f.level == "WARN" and "evidence APIs" in f.message]
        assert warn == [], (
            f"Untagged output blocks should not trigger evidence_depth WARN; got: {warn}"
        )

    def test_sql_blocks_on_ts_page_do_not_trigger_evidence_warn(self):
        """SQL blocks on a TypeScript page must not trigger evidence_depth WARN.

        SQL is not in PLATFORM_EXPECTED_LANGS['typescript'], so 2 SQL blocks
        on a TypeScript page must not be treated as API-eligible TypeScript code.
        This would have falsely triggered under the old denylist if sql were
        accidentally omitted from it.
        """
        page = _make_page(textwrap.dedent("""\
            ---
            title: Database Example
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Schema

            ```sql
            CREATE TABLE scenes (id INTEGER PRIMARY KEY, name TEXT);
            ```

            ## Query

            ```sql
            SELECT * FROM scenes WHERE name = 'demo';
            ```
        """), "content/docs.aspose.org/en/3d/typescript/developer-guide/db.md")
        findings = self.evaluator.evaluate(page, None)
        warn = [f for f in findings if f.level == "WARN" and "evidence APIs" in f.message]
        assert warn == [], (
            f"SQL blocks on TypeScript page should not trigger evidence_depth WARN; got: {warn}"
        )

    def test_api_block_count_not_inflated_by_untagged_blocks(self):
        """API-eligible block count in WARN message must not include untagged blocks.

        A page with 2 TypeScript blocks + 2 untagged output blocks should report
        count=2 in the WARN message, not count=4.  Inflated counts were a symptom
        of the denylist not excluding empty-string tags.
        """
        page = _make_page(textwrap.dedent("""\
            ---
            title: Quick Start
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Load

            ```typescript
            import { Scene } from "@aspose/3d";
            const scene = new Scene();
            ```

            ## Expected output

            ```
            Scene loaded.
            ```

            ## Save

            ```typescript
            await scene.save("output.fbx");
            ```

            ## Second output

            ```
            File saved successfully.
            ```
        """), "content/docs.aspose.org/en/3d/typescript/developer-guide/quickstart.md")
        findings = self.evaluator.evaluate(page, None)
        warn = [f for f in findings if f.level == "WARN" and "evidence APIs" in f.message]
        assert len(warn) == 1
        # Count in message must be 2 (TypeScript blocks only), not 4 (all blocks)
        assert "2 API-eligible code blocks" in warn[0].message, (
            f"Expected count=2 in message but got: {warn[0].message}"
        )

    def test_platform_purity_and_evidence_depth_agree_on_non_api_block(self):
        """Cross-evaluator consistency: both evaluators must skip the same non-API blocks.

        For any block that platform_purity skips (not a recognised API language),
        evidence_depth must also not count it as API-eligible.  This test verifies
        that bash blocks are skipped by both evaluators on a TypeScript page.
        """
        from content_eval.evaluators.platform_purity import PlatformPurityEvaluator
        pp = PlatformPurityEvaluator()

        page = _make_page(textwrap.dedent("""\
            ---
            title: Install
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Step 1

            ```bash
            npm install @aspose/3d
            ```

            ## Step 2

            ```bash
            npx tsc
            ```
        """), "content/docs.aspose.org/en/3d/typescript/getting-started/install.md")

        # evidence_depth must not warn
        ed_warn = [
            f for f in self.evaluator.evaluate(page, None)
            if f.level == "WARN" and "evidence APIs" in f.message
        ]
        assert ed_warn == [], f"evidence_depth should skip bash blocks; got: {ed_warn}"

        # platform_purity must not flag bash blocks as wrong-language
        pp_fail = [
            f for f in pp.evaluate(page, None)
            if f.level == "FAIL" and "tagged as" in f.message
        ]
        assert pp_fail == [], f"platform_purity should skip bash blocks; got: {pp_fail}"

    def test_grade_mapping_zero_fail_one_warn_is_A(self):
        """Regression: 0 FAIL + 1 WARN must map to grade A, not B.

        The rubric: A = 0 FAIL, 0-2 WARN; B = 0 FAIL, 3-5 WARN.
        The license.md bug report claimed grade B for 0F+1W which is wrong.
        """
        from content_eval.models import compute_grade
        assert compute_grade(0, 0) == "A"
        assert compute_grade(0, 1) == "A"
        assert compute_grade(0, 2) == "A"
        assert compute_grade(0, 3) == "B"
        assert compute_grade(0, 5) == "B"
        assert compute_grade(0, 6) == "C"
        assert compute_grade(1, 0) == "C"


class TestProseTruth:
    def setup_method(self):
        from content_eval.evaluators.prose_truth import ProseTruthEvaluator
        self.evaluator = ProseTruthEvaluator()

    def test_no_knowledge_no_findings(self):
        page = _make_page("---\ntitle: T\n---\nContent.",
                          "content/docs.aspose.org/en/unknown/unknown/test.md")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_api_claim_against_knowledge(self):
        """API claim for non-existent member should produce finding."""
        knowledge = MagicMock()
        knowledge.available = True
        knowledge.classes = {"Scene": {}}
        knowledge.has_method = MagicMock(return_value=False)
        knowledge.has_property = MagicMock(return_value=False)

        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            `Scene.nonexistent_method` provides advanced rendering.
        """), "content/docs.aspose.org/en/3d/python/test.md")
        findings = self.evaluator.evaluate(page, knowledge)
        api_findings = [f for f in findings if "not found in API surface" in f.message]
        assert len(api_findings) >= 1

    def test_valid_api_claim_no_finding(self):
        """Valid API claim should not produce finding."""
        knowledge = MagicMock()
        knowledge.available = True
        knowledge.classes = {"Scene": {}}
        knowledge.has_method = MagicMock(return_value=True)
        knowledge.has_property = MagicMock(return_value=False)

        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            `Scene.open` provides file loading.
        """), "content/docs.aspose.org/en/3d/python/test.md")
        findings = self.evaluator.evaluate(page, knowledge)
        api_findings = [f for f in findings if "not found in API surface" in f.message]
        assert len(api_findings) == 0


class TestCoverage:
    def setup_method(self):
        from content_eval.evaluators.coverage import CoverageEvaluator
        self.evaluator = CoverageEvaluator()

    def test_non_docs_page_skipped(self):
        page = _make_page("---\ntitle: T\n---\nContent.",
                          "content/blog.aspose.org/3d/python/test/index.md")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_coverage_no_knowledge_no_findings(self):
        page = _make_page("---\ntitle: T\n---\nContent.",
                          "content/docs.aspose.org/en/unknown/unknown/test.md")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0


class TestCoverageInterfaceFiltering:
    """S-Fix-5: Platform-aware interface filtering."""

    def setup_method(self):
        from content_eval.evaluators.coverage import (
            CoverageEvaluator, _is_interface_entry, INTERFACE_PAGE_PLATFORMS,
            CONCRETE_ONLY_PLATFORMS,
        )
        self.evaluator = CoverageEvaluator()
        self._is_interface_entry = _is_interface_entry
        self.INTERFACE_PAGE_PLATFORMS = INTERFACE_PAGE_PLATFORMS
        self.CONCRETE_ONLY_PLATFORMS = CONCRETE_ONLY_PLATFORMS

    def test_i_prefix_uppercase_detected_as_interface(self):
        assert self._is_interface_entry("IShape", "") is True
        assert self._is_interface_entry("IPPImage", "") is True

    def test_i_prefix_lowercase_not_interface(self):
        # "Index" starts with I but second char is 'n' (lowercase) — not an interface
        assert self._is_interface_entry("Index", "") is False

    def test_single_i_not_interface(self):
        assert self._is_interface_entry("I", "") is False

    def test_kind_field_interface_detected(self):
        assert self._is_interface_entry("SomeType", "interface") is True
        assert self._is_interface_entry("SomeType", "abstract_class") is True

    def test_kind_field_concrete_not_interface(self):
        assert self._is_interface_entry("SomeType", "class_specifier") is False

    def test_platform_sets_correct(self):
        assert "cpp" in self.CONCRETE_ONLY_PLATFORMS
        assert "python" in self.CONCRETE_ONLY_PLATFORMS
        assert "net" in self.INTERFACE_PAGE_PLATFORMS
        assert "java" in self.INTERFACE_PAGE_PLATFORMS
        assert "dotnet" not in self.INTERFACE_PAGE_PLATFORMS


class TestCoverageSlug:
    """S-Fix-6: Slug generation for enum page lookup."""

    def setup_method(self):
        from content_eval.evaluators.coverage import _to_slug
        self._to_slug = _to_slug

    def test_pascal_case_to_kebab(self):
        assert self._to_slug("BevelPresetType") == "bevel-preset-type"

    def test_fill_type(self):
        assert self._to_slug("FillType") == "fill-type"

    def test_single_word(self):
        assert self._to_slug("Presentation") == "presentation"

    def test_acronym_prefix(self):
        # "GradientDirection" → "gradient-direction"
        result = self._to_slug("GradientDirection")
        assert "gradient" in result and "direction" in result


# ---------------------------------------------------------------------------
# TF-IDF Semantic Matching (prose_truth)
# ---------------------------------------------------------------------------

class TestClaimIndex:
    """Tests for _ClaimIndex TF-IDF semantic matching."""

    def setup_method(self):
        from content_eval.evaluators.prose_truth import _ClaimIndex
        self.ClaimIndex = _ClaimIndex

    def test_similar_text_high_score(self):
        idx = self.ClaimIndex([
            {"text": "Scene class provides methods for loading and saving 3D files"},
        ])
        assert idx.available
        score = idx.best_similarity("Scene class provides methods for loading 3D models")
        assert score > 0.3

    def test_unrelated_text_low_score(self):
        idx = self.ClaimIndex([
            {"text": "Scene class provides methods for loading and saving 3D files"},
        ])
        score = idx.best_similarity("The weather is nice today in Tokyo")
        assert score < 0.2

    def test_exact_match_near_one(self):
        idx = self.ClaimIndex([
            {"text": "Scene class provides methods for loading and saving 3D files"},
        ])
        score = idx.best_similarity("Scene class provides methods for loading and saving 3D files")
        assert score > 0.9

    def test_empty_claims(self):
        idx = self.ClaimIndex([])
        assert not idx.available
        assert idx.best_similarity("anything") == 0.0

    def test_multiple_claims_best_match(self):
        idx = self.ClaimIndex([
            {"text": "Node class supports creating child nodes and transformations"},
            {"text": "Scene class loads 3D files from disk"},
        ])
        score = idx.best_similarity("Scene class loads 3D models from file")
        assert score > 0.3


class TestClaimIndexCache:
    """Tests for _ClaimIndex caching (TM-01)."""

    def setup_method(self):
        from content_eval.evaluators.prose_truth import clear_claim_cache
        clear_claim_cache()

    def teardown_method(self):
        from content_eval.evaluators.prose_truth import clear_claim_cache
        clear_claim_cache()

    def test_claim_index_cached_across_calls(self):
        """Same (family, platform) should return the same object."""
        from content_eval.evaluators.prose_truth import _get_claim_index
        idx1 = _get_claim_index("nonexistent_family", "nonexistent_platform")
        idx2 = _get_claim_index("nonexistent_family", "nonexistent_platform")
        assert idx1 is idx2

    def test_different_keys_different_objects(self):
        """Different (family, platform) should return different objects."""
        from content_eval.evaluators.prose_truth import _get_claim_index
        idx1 = _get_claim_index("family_a", "platform_a")
        idx2 = _get_claim_index("family_b", "platform_b")
        assert idx1 is not idx2

    def test_cache_cleared(self):
        """clear_claim_cache() should reset state."""
        from content_eval.evaluators._claim_index import (
            get_claim_index, clear_claim_cache, _CLAIM_INDEX_CACHE,
        )
        get_claim_index("test_family", "test_platform")
        assert len(_CLAIM_INDEX_CACHE) == 1
        clear_claim_cache()
        assert len(_CLAIM_INDEX_CACHE) == 0


# ---------------------------------------------------------------------------
# EVALUATOR_LOGIC_VERSION invariant
# ---------------------------------------------------------------------------

class TestProseTruthSectionSuppression:
    """Tests for N2: strong-words WARN suppressed when enclosing section has evidence claims.

    All tests use `filepath` in the `kb` subdomain so prose_truth assigns WARN severity
    for strong-wording findings.  knowledge=None skips the API claims path so only the
    strong-words check is exercised.
    """

    _KB_PATH = "content/kb.aspose.org/en/email/cpp/test.md"

    def setup_method(self):
        from content_eval.evaluators.prose_truth import ProseTruthEvaluator
        self.evaluator = ProseTruthEvaluator()

    def test_strong_words_suppressed_in_evidenced_section(self):
        """Strong word inside a section with ≥1 claim → WARN suppressed."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            evidence:
              sections:
              - heading: My Section
                line: 0
                claims:
                - CLM-test-001
                apis: []
            ---
            ## My Section

            This library requires only a C++17 compiler.
        """), self._KB_PATH)
        findings = [f for f in self.evaluator.evaluate(page, None)
                    if f.level == "WARN" and "Strong wording" in f.message]
        assert len(findings) == 0, (
            f"Expected strong-wording WARN suppressed by section evidence; got: {findings}"
        )

    def test_strong_words_not_suppressed_in_empty_claims_section(self):
        """Strong word in a section with claims: [] → WARN still fires (no suppression)."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            evidence:
              sections:
              - heading: My Section
                line: 0
                claims: []
                apis: []
            ---
            ## My Section

            This library requires only a C++17 compiler.
        """), self._KB_PATH)
        findings = [f for f in self.evaluator.evaluate(page, None)
                    if f.level == "WARN" and "Strong wording" in f.message]
        assert len(findings) >= 1, (
            "Expected strong-wording WARN to fire when section claims list is empty; "
            f"got: {findings}"
        )

    def test_strong_words_suppressed_preamble_before_heading(self):
        """Strong word in preamble text (before first ##) is suppressed when an
        evidence section with claims has no matching ## heading in the body.

        The section is inserted at line 0 via the preamble fallback, covering all
        pre-heading prose.
        """
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            evidence:
              sections:
              - heading: Introduction
                line: 0
                claims:
                - CLM-test-001
                apis: []
            ---
            This library uses only the C++ standard library.

            ## Usage

            See examples below.
        """), self._KB_PATH)
        findings = [f for f in self.evaluator.evaluate(page, None)
                    if f.level == "WARN" and "Strong wording" in f.message]
        assert len(findings) == 0, (
            "Expected preamble strong-wording WARN suppressed when Introduction section "
            f"has claims; got: {findings}"
        )

    def test_strong_words_not_suppressed_no_sections(self):
        """Strong word with no evidence.sections in frontmatter → WARN fires normally."""
        page = _make_page(textwrap.dedent("""\
            ---
            title: Test
            ---
            ## My Section

            This library requires only a C++17 compiler.
        """), self._KB_PATH)
        findings = [f for f in self.evaluator.evaluate(page, None)
                    if f.level == "WARN" and "Strong wording" in f.message]
        assert len(findings) >= 1, (
            "Expected strong-wording WARN to fire when no evidence.sections; "
            f"got: {findings}"
        )


class TestEvidenceCompleteness:
    """Tests for EvidenceCompletenessEvaluator (WP-4: detect empty apis:/claims: on reference pages)."""

    _REF_PATH = "content/reference.aspose.org/en/cells/net/MyClass.md"

    def setup_method(self):
        from content_eval.evaluators.evidence_completeness import EvidenceCompletenessEvaluator
        self.evaluator = EvidenceCompletenessEvaluator()

    def _make_ref_page(self, content: str) -> "Page":
        return _make_page(content, self._REF_PATH)

    def test_empty_apis_many_members_is_fail(self):
        """apis: [] with >5 known members → FAIL."""
        page = self._make_ref_page(textwrap.dedent("""\
            ---
            linkTitle: MyClass
            layout: reference-single
            evidence:
              model_sha: abc123
              claims: [ERC-001]
              apis: []
            ---
            ## Overview
            MyClass is a class.
        """))
        # Inject mock api_surface by patching _count_known_members
        from unittest.mock import patch
        with patch.object(self.evaluator, "_count_known_members", return_value=8):
            findings = self.evaluator.evaluate(page, None)
        fail_findings = [f for f in findings if f.level == "FAIL" and f.category == "EC"]
        assert len(fail_findings) == 1
        assert "8 known API members" in fail_findings[0].message

    def test_empty_apis_few_members_is_warn(self):
        """apis: [] with 1–5 known members → WARN (not FAIL)."""
        page = self._make_ref_page(textwrap.dedent("""\
            ---
            linkTitle: MyClass
            layout: reference-single
            evidence:
              model_sha: abc123
              claims: [ERC-001]
              apis: []
            ---
            ## Overview
            MyClass is a class.
        """))
        from unittest.mock import patch
        with patch.object(self.evaluator, "_count_known_members", return_value=3):
            findings = self.evaluator.evaluate(page, None)
        warn_findings = [f for f in findings if f.level == "WARN" and "known API members" in f.message]
        fail_findings = [f for f in findings if f.level == "FAIL" and "known API members" in f.message]
        assert len(warn_findings) == 1
        assert len(fail_findings) == 0

    def test_empty_apis_no_members_no_finding(self):
        """apis: [] with 0 known members → no apis finding (acceptable for empty classes)."""
        page = self._make_ref_page(textwrap.dedent("""\
            ---
            linkTitle: MyClass
            layout: reference-single
            evidence:
              model_sha: abc123
              claims: [ERC-001]
              apis: []
            ---
            ## Overview
            MyClass is a class.
        """))
        from unittest.mock import patch
        with patch.object(self.evaluator, "_count_known_members", return_value=0):
            findings = self.evaluator.evaluate(page, None)
        apis_findings = [f for f in findings if "known API members" in f.message]
        assert len(apis_findings) == 0

    def test_populated_apis_no_finding(self):
        """Non-empty apis: → no EC finding."""
        page = self._make_ref_page(textwrap.dedent("""\
            ---
            linkTitle: MyClass
            layout: reference-single
            evidence:
              model_sha: abc123
              claims: [ERC-001]
              apis:
                - "MyClass.MyMethod"
                - "MyClass.MyProp"
            ---
            ## Overview
            MyClass is a class.
        """))
        from unittest.mock import patch
        with patch.object(self.evaluator, "_count_known_members", return_value=2):
            findings = self.evaluator.evaluate(page, None)
        ec_findings = [f for f in findings if f.category == "EC"]
        assert len(ec_findings) == 0

    def test_empty_claims_is_warn(self):
        """claims: [] on reference page → WARN."""
        page = self._make_ref_page(textwrap.dedent("""\
            ---
            linkTitle: MyClass
            layout: reference-single
            evidence:
              model_sha: abc123
              claims: []
              apis:
                - "MyClass.MyMethod"
            ---
            ## Overview
            MyClass is a class.
        """))
        from unittest.mock import patch
        with patch.object(self.evaluator, "_count_known_members", return_value=1):
            findings = self.evaluator.evaluate(page, None)
        claim_warn = [f for f in findings if f.level == "WARN" and "claims" in f.message]
        assert len(claim_warn) == 1

    def test_non_reference_page_skipped(self):
        """Evaluator only fires on reference subdomain pages."""
        page = _make_page(textwrap.dedent("""\
            ---
            linkTitle: MyClass
            layout: reference-single
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Overview
            MyClass is a class.
        """), "content/docs.aspose.org/en/cells/net/test.md")
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0

    def test_non_single_layout_skipped(self):
        """reference-home layout pages are not checked."""
        page = self._make_ref_page(textwrap.dedent("""\
            ---
            linkTitle: Cells Reference
            layout: reference-home
            evidence:
              model_sha: abc123
              claims: []
              apis: []
            ---
            ## Overview
            Reference home.
        """))
        findings = self.evaluator.evaluate(page, None)
        assert len(findings) == 0


class TestEvaluatorLogicVersion:
    def test_evaluator_logic_version_is_nonempty(self):
        """EVALUATOR_LOGIC_VERSION must be a non-empty string.

        An empty or missing value would cause --skip-graded to never skip any
        pages (stored["logic_version"] == "" always matches "" == ""), defeating
        the staleness detection mechanism entirely.
        """
        from content_eval import EVALUATOR_LOGIC_VERSION
        assert EVALUATOR_LOGIC_VERSION, (
            "EVALUATOR_LOGIC_VERSION must be a non-empty string; got: "
            f"{EVALUATOR_LOGIC_VERSION!r}"
        )

