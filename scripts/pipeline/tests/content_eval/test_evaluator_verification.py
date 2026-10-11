"""Synthetic evaluator verification tests.

Run with: .venv/Scripts/python -m pytest scripts/pipeline/tests/content_eval/test_evaluator_verification.py -v
"""

import sys
import tempfile
import json
from pathlib import Path

from content_eval.models import Page
from content_eval.evaluators.code_plausibility import CodePlausibilityEvaluator
from content_eval.evaluators.type_accuracy import TypeAccuracyEvaluator
from content_eval.evaluators.limitations_check import ProductsFeatureLimitationsEvaluator


# ============================================================
# TEST 1: java_awt_contamination
# ============================================================
def test_java_awt_contamination(tmp_path):
    print("=" * 60)
    print("TEST 1: java_awt_contamination")
    print("=" * 60)

    content = (
        "---\n"
        "title: Test Java AWT\n"
        "---\n"
        "\n"
        "## Example\n"
        "\n"
        "```java\n"
        "import java.awt.Color;\n"
        "Color c = Color.RED;\n"
        "Presentation pres = new Presentation();\n"
        "```\n"
    )

    tmp_dir = tmp_path / "content/docs.aspose.org/en/slides/java"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, dir=str(tmp_dir), encoding="utf-8"
    ) as f:
        f.write(content)
        tmppath = Path(f.name)

    try:
        page = Page.load(tmppath)
        print(f"  family={page.family!r} platform={page.platform!r} subdomain={page.subdomain!r}")
        print(f"  code_blocks={len(page.code_blocks)}")
        e = CodePlausibilityEvaluator()
        findings = e.evaluate(page, None)
        awt_findings = [f for f in findings if "java.awt" in f.message]
        print("  Findings:")
        for f in findings:
            print(f"    [{f.level}] {f.message[:80]}")
        print()
        assert awt_findings, "no java_awt_contamination finding raised"
        assert awt_findings[0].level == "FAIL", (
            f"expected FAIL, got {awt_findings[0].level}"
        )
        print("  RESULT: PASS — java_awt_contamination correctly fires FAIL")
    finally:
        tmppath.unlink(missing_ok=True)


# ============================================================
# TEST 2: net_null_unsafe_textframe
# ============================================================
def test_net_null_unsafe_textframe(tmp_path):
    print()
    print("=" * 60)
    print("TEST 2: net_null_unsafe_textframe")
    print("=" * 60)

    content = (
        "---\n"
        "title: Test Net TextFrame\n"
        "---\n"
        "\n"
        "## Example\n"
        "\n"
        "```csharp\n"
        "IShape shape = slide.Shapes.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 100);\n"
        'shape.TextFrame.Text = "Hello world";\n'
        "```\n"
    )

    tmp_dir = tmp_path / "content/docs.aspose.org/en/slides/net"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, dir=str(tmp_dir), encoding="utf-8"
    ) as f:
        f.write(content)
        tmppath = Path(f.name)

    try:
        page = Page.load(tmppath)
        print(f"  family={page.family!r} platform={page.platform!r}")
        e = CodePlausibilityEvaluator()
        findings = e.evaluate(page, None)
        tf_findings = [f for f in findings if ".TextFrame.Text =" in f.message or "TextFrame" in f.message]
        print("  Findings:")
        for f in findings:
            print(f"    [{f.level}] {f.message[:80]}")
        print()
        # The specific FR-17a check is the one about .TextFrame.Text = without AddTextFrame
        specific = [f for f in findings if "AddTextFrame" in f.message]
        assert specific, "no net_null_unsafe_textframe finding raised"
        assert specific[0].level == "WARN", (
            f"expected WARN, got {specific[0].level}"
        )
        print("  RESULT: PASS — net_null_unsafe_textframe correctly fires WARN")
    finally:
        tmppath.unlink(missing_ok=True)


# ============================================================
# TEST 3: reference_void_mismatch
# ============================================================
def test_reference_void_mismatch(tmp_path):
    print()
    print("=" * 60)
    print("TEST 3: reference_void_mismatch")
    print("=" * 60)

    # AdjustValue.initInternal returns 'AdjustValue' in slides/java api_surface.json
    # We document it as void — should trigger FAIL
    content = (
        "---\n"
        "title: AdjustValue\n"
        "linkTitle: AdjustValue\n"
        "---\n"
        "\n"
        "## Methods\n"
        "\n"
        "| Method | Returns | Description |\n"
        "|--------|---------|-------------|\n"
        "| `initInternal()` | `void` | Initializes internal state |\n"
        "| `AdjustValue()` | `void` | Constructor |\n"
    )

    # Write to the reference path so metadata inference works
    ref_dir = tmp_path / "content/reference.aspose.org/en/slides/java"
    ref_dir.mkdir(parents=True, exist_ok=True)
    tmpfile = ref_dir / "AdjustValue_test_verify.md"
    tmpfile.write_text(content, encoding="utf-8")

    try:
        page = Page.load(tmpfile)
        print(f"  family={page.family!r} platform={page.platform!r} subdomain={page.subdomain!r}")
        print(f"  page_role={page.page_role!r}")
        e = TypeAccuracyEvaluator()
        findings = e.evaluate(page, None)
        void_mismatch = [f for f in findings if "void" in f.message.lower() and "api_surface" in f.message.lower()]
        print("  Findings:")
        for f in findings:
            print(f"    [{f.level}] {f.message[:90]}")
        print()
        assert void_mismatch, (
            "no void_mismatch finding raised; "
            "check that knowledge/slides/java/merged/api_surface.json is present and "
            "AdjustValue.initInternal has a non-void return type"
        )
        assert any(f.level == "FAIL" for f in void_mismatch), (
            f"expected FAIL in void_mismatch findings, got "
            f"{[(f.level, f.message[:50]) for f in void_mismatch]}"
        )
        print("  RESULT: PASS — reference_void_mismatch correctly fires FAIL")
    finally:
        tmpfile.unlink(missing_ok=True)


# ============================================================
# TEST 4: products_feature_violates_limitations
# ============================================================
def test_products_feature_violates_limitations(tmp_path):
    print()
    print("=" * 60)
    print("TEST 4: products_feature_violates_limitations")
    print("=" * 60)

    # The cells/python limitations.md uses table format (not bullets),
    # so we need to test with synthetic content that has bullet-format limitations.
    # We use the real products page path but with injected synthetic limitations keywords.

    # First, test with real products page to see baseline
    real_path = Path("content/products.aspose.org/en/cells/python/_index.md")
    if real_path.exists():
        page = Page.load(real_path)
        print(f"  Real page: family={page.family!r} platform={page.platform!r} subdomain={page.subdomain!r}")
        e = ProductsFeatureLimitationsEvaluator()
        findings = e.evaluate(page, None)
        print(f"  Real page findings: {len(findings)}")
        for f in findings:
            print(f"    [{f.level}] {f.message[:80]}")

    # Build synthetic test: products page content with bullet about scatter charts
    # and a synthetic limitations file with bullet matching "scatter chart"
    products_content = (
        "---\n"
        "title: Aspose.Cells FOSS for Python\n"
        "---\n"
        "\n"
        "## Features\n"
        "\n"
        "- Build scatter chart visualizations from data ranges\n"
        "- Create combo chart layouts with mixed series types\n"
        "- Export to XLSX with full fidelity\n"
    )

    tmp_products_dir = tmp_path / "content/products.aspose.org/en/cells/python"
    tmp_products_dir.mkdir(parents=True, exist_ok=True)
    tmpfile = tmp_products_dir / "_test_verify_products.md"
    tmpfile.write_text(products_content, encoding="utf-8")

    # The evaluator reads limitations.md from the real knowledge path (not via the
    # Knowledge argument). We must write the synthetic file there and restore afterward.
    lim_dir = Path("knowledge/cells/python/merged")
    lim_dir.mkdir(parents=True, exist_ok=True)
    lim_backup = lim_dir / "limitations.md"
    original_lim = lim_backup.read_text(encoding="utf-8") if lim_backup.exists() else None

    synthetic_lim = (
        "# Limitations\n\n"
        "- scatter chart: raises NotImplementedError on save\n"
        "- combo chart: not supported, raises NotImplementedError\n"
        "- standard encryption: not yet implemented\n"
    )

    try:
        lim_backup.write_text(synthetic_lim, encoding="utf-8")
        page = Page.load(tmpfile)
        print(f"\n  Synthetic test: family={page.family!r} platform={page.platform!r} subdomain={page.subdomain!r}")
        e = ProductsFeatureLimitationsEvaluator()
        findings = e.evaluate(page, None)
        print("  Findings:")
        for f in findings:
            print(f"    [{f.level}] {f.message[:90]}")
        print()
        fail_findings = [f for f in findings if f.level == "FAIL"]
        assert fail_findings, "no FAIL findings raised by products_feature_violates_limitations"
        print("  RESULT: PASS — products_feature_violates_limitations correctly fires FAIL")
    finally:
        tmpfile.unlink(missing_ok=True)
        # Restore original limitations.md
        if original_lim is not None:
            lim_backup.write_text(original_lim, encoding="utf-8")
        elif lim_backup.exists():
            lim_backup.unlink()


if __name__ == "__main__":
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-v"]))
