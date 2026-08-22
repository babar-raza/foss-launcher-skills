"""
Tests for commands/content/maven_shortcode_migrator.py (Mission MT008, TC-MT008-08).

The deterministic codemod that replaces literal Java-FOSS Maven-coordinate
text with the maven-coord/maven-gav shortcode calls. Covers the block pass
(fenced XML dependency blocks, including indentation preservation for
products.aspose.org's YAML-embedded content) and the inline pass (bare and
backtick-wrapped coordinate mentions), plus the structural-not-value-based
matching philosophy (already-correct literal text is migrated too).
"""

import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.content.maven_shortcode_migrator as sut


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)


def _write(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_block_pass_replaces_fenced_dependency_block(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/en/cells/java/getting-started/installation.md", (
        "## Maven Installation\n\n"
        "```xml\n"
        "<dependency>\n"
        "  <groupId>com.aspose</groupId>\n"
        "  <artifactId>cells-foss</artifactId>\n"
        "  <version>1.0.0</version>\n"
        "</dependency>\n"
        "```\n\n"
        "Then run `mvn clean install`.\n"
    ))
    res = sut.migrate_file(fp, "cells", dry_run=False)
    assert res["result"] == sut.R_MIGRATED
    assert res["block_replacements"] == 1
    text = fp.read_text(encoding="utf-8")
    assert '{{< maven-coord "cells" "java" >}}' in text
    assert "<dependency>" not in text
    assert "```xml" not in text  # whole fence removed, not just inner content


def test_block_pass_preserves_indentation_for_yaml_embedded_content(tmp_path):
    """products.aspose.org pages embed fenced blocks inside YAML `content: |-`
    frontmatter values -- the replacement line must keep the same indentation
    as the fence it replaces, or the YAML block scalar breaks."""
    fp = _write(tmp_path, "content/products.aspose.org/en/3d/java/_index.md", (
        "---\n"
        "single:\n"
        "  block:\n"
        "  - content: |-\n"
        "      Some text.\n\n"
        "      ```xml\n"
        "      <dependency>\n"
        "        <groupId>com.aspose</groupId>\n"
        "        <artifactId>aspose-3d-foss</artifactId>\n"
        "        <version>26.1.0</version>\n"
        "      </dependency>\n"
        "      ```\n"
        "---\n"
    ))
    res = sut.migrate_file(fp, "3d", dry_run=False)
    assert res["result"] == sut.R_MIGRATED
    text = fp.read_text(encoding="utf-8")
    assert '      {{< maven-coord "3d" "java" >}}' in text
    import yaml
    parts = text.split("---", 2)
    data = yaml.safe_load(parts[1])
    assert '{{< maven-coord "3d" "java" >}}' in data["single"]["block"][0]["content"]


def test_inline_pass_replaces_backtick_wrapped_mention(tmp_path):
    fp = _write(tmp_path, "content/kb.aspose.org/en/cells/java/faq.md", (
        "| Dependency | `com.aspose:aspose-cells-foss:1.0.0` |\n"
    ))
    res = sut.migrate_file(fp, "cells", dry_run=False)
    assert res["result"] == sut.R_MIGRATED
    assert res["inline_replacements"] == 1
    text = fp.read_text(encoding="utf-8")
    assert text == '| Dependency | {{< maven-gav "cells" "java" >}} |\n'
    assert "`" not in text  # backticks removed, not left double-wrapping


def test_inline_pass_replaces_bare_mention_with_version(tmp_path):
    fp = _write(tmp_path, "content/blog.aspose.org/3d/java/some-post/index.md", (
        "The package is published as com.aspose:aspose-3d-foss:26.1.0 on Maven Central.\n"
    ))
    res = sut.migrate_file(fp, "3d", dry_run=False)
    assert res["result"] == sut.R_MIGRATED
    text = fp.read_text(encoding="utf-8")
    assert '{{< maven-gav "3d" "java" >}}' in text
    assert "26.1.0" not in text


def test_already_correct_literal_text_is_still_migrated(tmp_path):
    """Structural matching, not value-based: a literal org.aspose (currently
    correct) mention is migrated exactly like a wrong com.aspose one -- a
    literal string is a staleness risk regardless of its current value."""
    fp = _write(tmp_path, "content/blog.aspose.org/3d/java/some-post/index.md", (
        "```xml\n<dependency>\n  <groupId>org.aspose</groupId>\n"
        "  <artifactId>aspose-3d-foss</artifactId>\n  <version>26.5.0</version>\n"
        "</dependency>\n```\n"
    ))
    res = sut.migrate_file(fp, "3d", dry_run=False)
    assert res["result"] == sut.R_MIGRATED
    assert res["block_replacements"] == 1


def test_noop_when_no_coordinate_present(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/en/cells/java/developer-guide/overview.md", (
        "This page has no Maven coordinate mention at all.\n"
    ))
    res = sut.migrate_file(fp, "cells", dry_run=False)
    assert res["result"] == sut.R_NOOP
    assert res["block_replacements"] == 0
    assert res["inline_replacements"] == 0


def test_no_cross_family_false_positive(tmp_path):
    """A cells-foss coordinate must not be matched while migrating the 3d family."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/cells/java/getting-started/installation.md", (
        "```xml\n<dependency>\n  <groupId>org.aspose</groupId>\n"
        "  <artifactId>aspose-cells-foss</artifactId>\n  <version>26.5.0</version>\n"
        "</dependency>\n```\n"
    ))
    res = sut.migrate_file(fp, "3d", dry_run=False)
    assert res["result"] == sut.R_NOOP


def test_dry_run_never_writes(tmp_path):
    fp = _write(tmp_path, "content/blog.aspose.org/3d/java/some-post/index.md", (
        "```xml\n<dependency>\n  <groupId>com.aspose</groupId>\n"
        "  <artifactId>aspose-3d-foss</artifactId>\n  <version>26.1.0</version>\n"
        "</dependency>\n```\n"
    ))
    original = fp.read_text(encoding="utf-8")
    res = sut.migrate_file(fp, "3d", dry_run=True)
    assert res["result"] == sut.R_DRY_RUN
    assert fp.read_text(encoding="utf-8") == original


def test_protected_page_is_skipped(tmp_path):
    fp = _write(tmp_path, "content/blog.aspose.org/3d/java/some-post/index.md", (
        "---\nprovenance:\n  auto_updatable: false\n---\n\n"
        "```xml\n<dependency>\n  <groupId>com.aspose</groupId>\n"
        "  <artifactId>aspose-3d-foss</artifactId>\n  <version>26.1.0</version>\n"
        "</dependency>\n```\n"
    ))
    original = fp.read_text(encoding="utf-8")
    res = sut.migrate_file(fp, "3d", dry_run=False)
    assert res["result"] == sut.R_SKIPPED_PROTECTED
    assert fp.read_text(encoding="utf-8") == original


def test_nonexistent_file_reports_error_not_a_crash(tmp_path):
    res = sut.migrate_file(tmp_path / "does-not-exist.md", "cells", dry_run=False)
    assert res["error"] == "file not found"


def test_discover_files_excludes_reference_aspose_org(tmp_path):
    """TC-MT008-00's determination: reference.aspose.org cites Java package
    namespaces (a different, correct fact), not Maven coordinates -- must
    never be touched by this codemod."""
    _write(tmp_path, "content/reference.aspose.org/en/cells/java/Workbook.md", "com.aspose.cells_foss.Workbook\n")
    _write(tmp_path, "content/docs.aspose.org/en/cells/java/getting-started/installation.md", "no coordinate here\n")
    files = sut.discover_files("cells")
    assert not any("reference.aspose.org" in str(f) for f in files)
    assert any("docs.aspose.org" in str(f) for f in files)


def test_discover_files_covers_all_locales(tmp_path):
    _write(tmp_path, "content/docs.aspose.org/en/3d/java/getting-started/installation.md", "x\n")
    _write(tmp_path, "content/docs.aspose.org/fr/3d/java/getting-started/installation.md", "x\n")
    _write(tmp_path, "content/docs.aspose.org/de/3d/java/getting-started/installation.md", "x\n")
    files = sut.discover_files("3d")
    locales = {f.parts[-5] if "docs.aspose.org" in str(f) else None for f in files}
    assert {"en", "fr", "de"} <= locales


# --- Legacy bare "aspose-pdf" artifactId matching (ST-090, formerly ST-041) ---
# pdf/java's earliest content was authored against a pre-publish placeholder
# artifactId ("aspose-pdf", no "-foss" suffix) that the standard substring
# match never caught by design. These tests cover the exact-match legacy
# widening added 2026-08-22, including the negative controls required before
# trusting it against the real 73-file backlog item.

def test_legacy_pdf_block_pass_replaces_bare_artifact_id(tmp_path):
    fp = _write(tmp_path, "content/docs.aspose.org/ar/pdf/java/getting-started/installation.md", (
        "## مواصلة مافن\n\n"
        "```xml\n<dependency>\n  <groupId>org.aspose</groupId>\n"
        "  <artifactId>aspose-pdf</artifactId>\n  <version>0.1.0-alpha</version>\n"
        "</dependency>\n```\n"
    ))
    res = sut.migrate_file(fp, "pdf", dry_run=False)
    assert res["result"] == sut.R_MIGRATED
    assert res["block_replacements"] == 1
    text = fp.read_text(encoding="utf-8")
    assert '{{< maven-coord "pdf" "java" >}}' in text
    assert "0.1.0-alpha" not in text
    assert "aspose-pdf<" not in text and "<artifactId>aspose-pdf</artifactId>" not in text


def test_legacy_pdf_inline_pass_replaces_bare_mention(tmp_path):
    fp = _write(tmp_path, "content/blog.aspose.org/pdf/java/some-post/index.fr.md", (
        "Le paquet est publié sous org.aspose:aspose-pdf:0.1.0-alpha sur Maven Central.\n"
    ))
    res = sut.migrate_file(fp, "pdf", dry_run=False)
    assert res["result"] == sut.R_MIGRATED
    text = fp.read_text(encoding="utf-8")
    assert '{{< maven-gav "pdf" "java" >}}' in text
    assert "0.1.0-alpha" not in text


def test_legacy_pdf_current_foss_artifact_id_still_matches(tmp_path):
    """The widening must not regress the already-correct 'pdf-foss' path."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/pdf/java/getting-started/installation.md", (
        "```xml\n<dependency>\n  <groupId>org.aspose</groupId>\n"
        "  <artifactId>aspose-pdf-foss</artifactId>\n  <version>26.8.0</version>\n"
        "</dependency>\n```\n"
    ))
    res = sut.migrate_file(fp, "pdf", dry_run=False)
    assert res["result"] == sut.R_MIGRATED
    assert res["block_replacements"] == 1


def test_legacy_pdf_negative_control_incidental_prose_mention_not_matched(tmp_path):
    """A bare prose mention of 'aspose-pdf' with no groupId:artifactId
    coordinate shape at all must not be touched -- this is the negative
    control the widening was explicitly required to pass before use."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/pdf/java/developer-guide/history.md", (
        "The project was originally named aspose-pdf before the FOSS spinoff.\n"
    ))
    res = sut.migrate_file(fp, "pdf", dry_run=False)
    assert res["result"] == sut.R_NOOP
    assert fp.read_text(encoding="utf-8") == "The project was originally named aspose-pdf before the FOSS spinoff.\n"


def test_legacy_pdf_negative_control_unrelated_family_not_affected(tmp_path):
    """The pdf-specific legacy exact-match must never leak into another
    family's migration run, even if that family's content happens to
    mention the string "aspose-pdf" incidentally."""
    fp = _write(tmp_path, "content/docs.aspose.org/en/cells/java/developer-guide/interop.md", (
        "```xml\n<dependency>\n  <groupId>org.aspose</groupId>\n"
        "  <artifactId>aspose-pdf</artifactId>\n  <version>0.1.0-alpha</version>\n"
        "</dependency>\n```\n"
    ))
    res = sut.migrate_file(fp, "cells", dry_run=False)
    assert res["result"] == sut.R_NOOP


def test_legacy_pdf_idempotent_second_run_is_noop(tmp_path):
    fp = _write(tmp_path, "content/kb.aspose.org/en/pdf/java/faq.md", (
        "```xml\n<dependency>\n  <groupId>org.aspose</groupId>\n"
        "  <artifactId>aspose-pdf</artifactId>\n  <version>0.1.0-alpha</version>\n"
        "</dependency>\n```\n"
    ))
    first = sut.migrate_file(fp, "pdf", dry_run=False)
    assert first["result"] == sut.R_MIGRATED
    second = sut.migrate_file(fp, "pdf", dry_run=False)
    assert second["result"] == sut.R_NOOP
