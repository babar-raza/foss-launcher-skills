"""
Tests for audit/maven_coordinates.py (Mission MT008, TC-MT008-07).

The regression gate that catches raw literal Java-FOSS Maven coordinate text
reintroduced anywhere in content -- defense-in-depth behind the shortcode
(D-02) being the actual primary defense. See Findings F-01/F-08 and Risk R-04
in plans/master-plan.md.
"""

import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from audit.maven_coordinates import verify_maven_coordinates


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test-page.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_negative_control_wrong_groupid_literal_is_flagged(tmp_path):
    fp = _write(tmp_path, "Install with `com.aspose:aspose-cells-foss:1.0.0`.\n")
    findings = verify_maven_coordinates(fp)
    assert len(findings) == 1
    assert findings[0].level == "FAIL"
    assert "com.aspose:aspose-cells-foss" in findings[0].message


def test_negative_control_correct_groupid_literal_is_ALSO_flagged(tmp_path):
    """Even the currently-correct org.aspose coordinate is banned as raw text --
    the whole point is nothing renders this fact except the shortcode, so a
    'currently correct' literal is exactly as much a latent staleness risk as
    a wrong one (Mission MT008 module docstring)."""
    fp = _write(tmp_path, "Install with `org.aspose:aspose-cells-foss:26.5.0`.\n")
    findings = verify_maven_coordinates(fp)
    assert len(findings) == 1
    assert findings[0].level == "FAIL"


def test_negative_control_groupid_xml_tag_is_flagged(tmp_path):
    fp = _write(tmp_path, "```xml\n<groupId>com.aspose</groupId>\n```\n")
    findings = verify_maven_coordinates(fp)
    assert len(findings) == 1
    assert "groupId" in findings[0].message


def test_positive_control_shortcode_usage_is_not_flagged(tmp_path):
    fp = _write(tmp_path, (
        'Block form:\n\n{{< maven-coord "cells" "java" >}}\n\n'
        'Inline: installs with a single Maven dependency ({{< maven-gav "cells" "java" >}}).\n'
    ))
    findings = verify_maven_coordinates(fp)
    assert findings == []


def test_no_false_positive_on_package_namespace_mentions(tmp_path):
    """reference.aspose.org-style content citing the real Java package namespace
    (com.aspose.cells_foss.ClassName) must NOT be flagged -- it's a different,
    correct fact (see TC-MT008-00's determination), not a Maven coordinate."""
    fp = _write(tmp_path, "See `com.aspose.cells_foss.AutoFilterSupport` for details.\n")
    findings = verify_maven_coordinates(fp)
    assert findings == []


def test_no_false_positive_on_import_statements(tmp_path):
    fp = _write(tmp_path, "```java\nimport com.aspose.threed.*;\n```\n")
    findings = verify_maven_coordinates(fp)
    assert findings == []


def test_no_false_positive_on_frontmatter_model_sha(tmp_path):
    """A model_sha or similar frontmatter field must never accidentally match --
    exercised here with a realistic frontmatter block, not just 'no frontmatter
    at all' (which the other tests already implicitly cover)."""
    fp = _write(tmp_path, (
        "---\n"
        "title: Test\n"
        'evidence:\n  model_sha: "9274b621ebd30f2aca692851bea29ff343a019d8"\n'
        "---\n\n"
        "Normal body text with no coordinate mentions.\n"
    ))
    findings = verify_maven_coordinates(fp)
    assert findings == []


def test_multiple_findings_on_separate_lines_all_reported(tmp_path):
    fp = _write(tmp_path, (
        "First mention: `com.aspose:aspose-3d-foss:26.1.0`\n"
        "\n"
        "Second mention:\n\n```xml\n<groupId>com.aspose</groupId>\n```\n"
    ))
    findings = verify_maven_coordinates(fp)
    assert len(findings) == 2
    assert findings[0].line_no == 1
    assert findings[1].line_no == 6


def test_nonexistent_file_returns_empty_not_a_crash(tmp_path):
    findings = verify_maven_coordinates(tmp_path / "does-not-exist.md")
    assert findings == []


def test_products_plugin_layout_page_content_inside_frontmatter_is_scanned(tmp_path):
    """Regression pin for a real bug caught via end-to-end testing against the
    actual content/products.aspose.org/en/3d/java/_index.md this taskcard: an
    earlier version of this module stripped frontmatter before scanning
    (correct for docs/kb/blog markdown bodies, via links.py's convention) --
    but products.aspose.org 'plugin' layout pages embed their entire visible
    content INSIDE YAML frontmatter (`content: |` block scalars), so
    frontmatter-stripping silently scanned nothing and missed the defect on
    the exact site the original bug report was about. This fixture reproduces
    that page shape directly."""
    fp = _write(tmp_path, (
        "---\n"
        "layout: plugin\n"
        "single:\n"
        "  block:\n"
        "  - title: Load an OBJ Scene\n"
        "    content: |\n"
        "      ```xml\n"
        "      <dependency>\n"
        "        <groupId>com.aspose</groupId>\n"
        "        <artifactId>aspose-3d-foss</artifactId>\n"
        "      </dependency>\n"
        "      ```\n"
        "---\n"
    ))
    findings = verify_maven_coordinates(fp)
    assert len(findings) == 1
    assert "groupId" in findings[0].message
