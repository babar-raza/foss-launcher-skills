"""
Tests for commands/ops/batch_gen_missing.py's Java install-command generation
(Mission MT008, TC-MT008-03).

Regression pin: PACKAGE_NAMES hardcoded `com.aspose:aspose-{family}-foss` for
3d/cells/slides (pdf was never in this file's FAMILY_FOSS at all) and fed it
directly into generated docs/kb/blog pages via `pc["install_cmd"] + " " + pkg`.
Fixed to emit the maven-coord/maven-gav Hugo shortcodes for platform=="java"
instead -- see plans/master-plan.md Mission MT008 D-04. These tests cover
every one of the 6 call sites this fix touched, plus a non-java regression
sweep across every other platform this module supports, since the fix must
not change behavior for python/typescript/net/cpp.
"""

import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.batch_gen_missing as sut

_API = {"Workbook": {"docstring": "Represents a document.", "methods": ["save"]}}
_SHA = "deadbeef"


def _assert_shortcode_present_no_literal_coordinate(text: str, family: str):
    assert "com.aspose" not in text
    assert '{{< maven-coord "' + family + '" "java" >}}' in text


def test_gen_docs_howto_page_uses_shortcode():
    pi = {"family": "cells", "platform": "java", "slug": "developer-guide/working-with-cells", "weight": 10}
    _assert_shortcode_present_no_literal_coordinate(sut.gen_docs(pi, _API, _SHA), "cells")


def test_gen_docs_license_page_uses_shortcode():
    pi = {"family": "cells", "platform": "java", "slug": "getting-started/license", "weight": 1}
    _assert_shortcode_present_no_literal_coordinate(sut.gen_docs(pi, _API, _SHA), "cells")


def test_gen_docs_features_page_has_no_hardcoded_coordinate():
    # features page doesn't render an install block at all -- just must not leak com.aspose
    pi = {"family": "cells", "platform": "java", "slug": "getting-started/features", "weight": 1}
    assert "com.aspose" not in sut.gen_docs(pi, _API, _SHA)


def test_gen_kb_howto_uses_both_shortcodes_no_double_backtick_wrap():
    pi = {"family": "slides", "platform": "java", "slug": "how-to-do-a-thing", "weight": 5}
    out = sut.gen_kb(pi, _API, _SHA)
    _assert_shortcode_present_no_literal_coordinate(out, "slides")
    assert '{{< maven-gav "slides" "java" >}}' in out
    # the inline table-cell usage must NOT be backtick-wrapped (would double-wrap
    # in <code><code>, confirmed via a real Hugo build during this mission)
    assert '`{{< maven-gav "slides" "java" >}}`' not in out


def test_gen_kb_use_cases_uses_shortcode():
    pi = {"family": "3d", "platform": "java", "slug": "use-cases", "weight": 5}
    _assert_shortcode_present_no_literal_coordinate(sut.gen_kb(pi, _API, _SHA), "3d")


def test_gen_kb_troubleshooting_uses_shortcode():
    pi = {"family": "3d", "platform": "java", "slug": "troubleshooting", "weight": 2}
    _assert_shortcode_present_no_literal_coordinate(sut.gen_kb(pi, _API, _SHA), "3d")


def test_gen_blog_uses_shortcode():
    pi = {"family": "cells", "platform": "java", "slug": "my-post"}
    _assert_shortcode_present_no_literal_coordinate(sut.gen_blog(pi, _API, _SHA), "cells")


def test_package_names_dict_has_no_java_entries():
    """Direct regression pin: PACKAGE_NAMES must never carry a ("family","java")
    key again -- the whole point of this fix is that java is handled exclusively
    by the shortcode helpers, never a static lookup table."""
    java_keys = [k for k in sut.PACKAGE_NAMES if k[1] == "java"]
    assert java_keys == [], f"PACKAGE_NAMES must have no java entries, found: {java_keys}"


def test_no_hardcoded_com_aspose_groupid_literal_in_source():
    src = (_PIPELINE_ROOT / "commands" / "ops" / "batch_gen_missing.py").read_text(encoding="utf-8")
    for pattern in ('"com.aspose', "'com.aspose"):
        assert pattern not in src, f"a hardcoded com.aspose literal ({pattern!r}) has crept back in"


def test_non_java_platforms_unaffected():
    """Regression control: the java fix must not touch any other platform's
    output at all.

    NOTE (TC-MT040-46): the original ("cells", "typescript",
    "npm install @aspose/cells") row was removed from this table -- see
    test_typescript_platform_is_registry_backed_not_hardcoded below for its
    direct replacement. That hardcoded expectation was itself the bug this
    taskcard fixes: PACKAGE_NAMES[("cells","typescript")] carried a guessed
    override display name ("@aspose/cells") that disagreed with
    data/package_registry.json's own scouted candidate ("excel-cells" --
    see data/registry_exclusions.json's cells/typescript entry, which
    documents package.json's real name is "excel-cells", not an official
    Aspose identifier). typescript now resolves through
    lib/product_registry.py instead of this dict, so it needs its own
    registry fixture rather than fitting this dict-only assertion table.
    """
    cases = [
        ("cells", "python", "pip install aspose-cells"),
        ("cells", "net", "dotnet add package Aspose.Cells.Foss"),
        ("email", "cpp", "aspose-email-cpp"),
    ]
    for family, platform, expected_substring in cases:
        pi = {"family": family, "platform": platform, "slug": "developer-guide/working-with-x", "weight": 10}
        out = sut.gen_docs(pi, _API, _SHA)
        assert expected_substring in out, f"{family}/{platform}: expected {expected_substring!r} in output"
        assert "maven-coord" not in out and "maven-gav" not in out


def test_typescript_platform_is_registry_backed_not_hardcoded(tmp_path):
    """TC-MT040-46: replaces the removed ("cells", "typescript",
    "npm install @aspose/cells") row above with the new, registry-backed
    behavior, using a fixture registry entry this test controls (NOT the
    real repo's cells entry, which may change independently). Full
    coverage (including the "no PACKAGE_NAMES fallback ever fires for
    typescript" anti-regression check) lives in
    test_typescript_install_command.py; this is the direct row-for-row
    replacement colocated with test_non_java_platforms_unaffected above."""
    import json
    from lib import product_registry

    registry_path = tmp_path / "package_registry.json"
    registry_path.write_text(json.dumps({
        "cells": {"typescript": {
            "registry_type": "npm",
            "candidate": {"name": "excel-cells"},
            "verification": {"published": False},
        }}
    }), encoding="utf-8")
    product_registry.configure(package_registry_path=registry_path)
    try:
        pi = {"family": "cells", "platform": "typescript", "slug": "developer-guide/working-with-x", "weight": 10}
        out = sut.gen_docs(pi, _API, _SHA)
        assert "npm install excel-cells" in out
        assert "@aspose/cells" not in out
    finally:
        product_registry.configure(package_registry_path=None)
