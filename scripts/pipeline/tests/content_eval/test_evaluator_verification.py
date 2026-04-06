"""Synthetic evaluator verification tests.

Run with: .venv/Scripts/python scripts/tests/test_evaluator_verification.py
"""

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
def test_java_awt_contamination():
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

    tmp_dir = Path("content/docs.aspose.org/en/slides/java")
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
        if awt_findings and awt_findings[0].level == "FAIL":
            print("  RESULT: PASS — java_awt_contamination correctly fires FAIL")
            return True
        elif not awt_findings:
            print("  RESULT: FAIL — no java_awt_contamination finding raised")
            return False
        else:
            print(f"  RESULT: FAIL — finding raised but wrong level: {awt_findings[0].level}")
            return False
    finally:
        tmppath.unlink(missing_ok=True)


# ============================================================
# TEST 2: net_null_unsafe_textframe
# ============================================================
def test_net_null_unsafe_textframe():
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

    tmp_dir = Path("content/docs.aspose.org/en/slides/net")
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
        if specific and specific[0].level == "WARN":
            print("  RESULT: PASS — net_null_unsafe_textframe correctly fires WARN")
            return True
        elif not specific:
            print("  RESULT: FAIL — no net_null_unsafe_textframe finding raised")
            return False
        else:
            print(f"  RESULT: FAIL — finding raised but wrong level: {specific[0].level}")
            return False
    finally:
        tmppath.unlink(missing_ok=True)


# ============================================================
# TEST 3: reference_void_mismatch
# ============================================================
def test_reference_void_mismatch():
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
    ref_dir = Path("content/reference.aspose.org/en/slides/java")
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
        if void_mismatch and any(f.level == "FAIL" for f in void_mismatch):
            print("  RESULT: PASS — reference_void_mismatch correctly fires FAIL")
            return True
        elif not void_mismatch:
            print("  RESULT: FAIL — no void_mismatch finding raised")
            # Debug: check what api_surface has
            api_path = Path("knowledge/slides/java/merged/api_surface.json")
            if api_path.exists():
                data = json.loads(api_path.read_text())
                for entry in data:
                    if entry.get("name") == "AdjustValue":
                        print(f"  DEBUG: api_surface AdjustValue methods: {[m.get('name') + '->' + str(m.get('return_type')) for m in entry.get('methods', [])[:5]]}")
                        break
            return False
        else:
            print(f"  RESULT: PARTIAL — findings raised but no FAIL: {[(f.level, f.message[:50]) for f in void_mismatch]}")
            return False
    finally:
        tmpfile.unlink(missing_ok=True)


# ============================================================
# TEST 4: products_feature_violates_limitations
# ============================================================
def test_products_feature_violates_limitations():
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

    tmp_products_dir = Path("content/products.aspose.org/en/cells/python")
    tmp_products_dir.mkdir(parents=True, exist_ok=True)
    tmpfile = tmp_products_dir / "_test_verify_products.md"
    tmpfile.write_text(products_content, encoding="utf-8")

    # Write synthetic limitations.md with bullet format
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
    lim_backup.write_text(synthetic_lim, encoding="utf-8")

    try:
        page = Page.load(tmpfile)
        print(f"\n  Synthetic test: family={page.family!r} platform={page.platform!r} subdomain={page.subdomain!r}")
        e = ProductsFeatureLimitationsEvaluator()
        findings = e.evaluate(page, None)
        print("  Findings:")
        for f in findings:
            print(f"    [{f.level}] {f.message[:90]}")
        print()
        fail_findings = [f for f in findings if f.level == "FAIL"]
        if fail_findings:
            print("  RESULT: PASS — products_feature_violates_limitations correctly fires FAIL")
            return True
        else:
            print("  RESULT: FAIL — no FAIL findings raised")
            return False
    finally:
        tmpfile.unlink(missing_ok=True)
        # Restore original limitations.md
        if original_lim is not None:
            lim_backup.write_text(original_lim, encoding="utf-8")


if __name__ == "__main__":
    results = {}
    results["java_awt_contamination"] = test_java_awt_contamination()
    results["net_null_unsafe_textframe"] = test_net_null_unsafe_textframe()
    results["reference_void_mismatch"] = test_reference_void_mismatch()
    results["products_feature_violates_limitations"] = test_products_feature_violates_limitations()

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}  {name}")

    all_passed = all(results.values())
    print()
    print(f"Overall: {'ALL PASS' if all_passed else 'SOME FAILED'}")
    sys.exit(0 if all_passed else 1)
