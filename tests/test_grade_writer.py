import textwrap

from scripts.pipeline.lib.grade_writer import (
    CANONICAL_FRONTMATTER_FIELDS,
    content_hash,
    read_grade,
    write_grade,
)


def _page(tmp_path, text: str):
    path = tmp_path / "page.md"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def test_content_hash_normalizes_line_endings_and_trailing_space():
    assert content_hash("Line  \r\nNext\n") == content_hash("Line\nNext")


def test_write_grade_adds_canonical_fields_only(tmp_path):
    page = _page(
        tmp_path,
        """\
        ---
        title: Test
        type: docs
        ---

        Body.
        """,
    )

    assert write_grade(page, "B", model_sha="abc123", evaluator_tier="full")
    text = page.read_text(encoding="utf-8")

    assert "grade: B" in text
    assert "graded_content_hash:" in text
    assert "graded_at:" not in text
    assert "graded_model_sha:" not in text
    assert "graded_evaluators:" not in text
    assert CANONICAL_FRONTMATTER_FIELDS == frozenset({
        "grade",
        "graded_content_hash",
        "grade_reasons",
    })


def test_write_grade_replaces_legacy_operational_block(tmp_path):
    page = _page(
        tmp_path,
        """\
        ---
        title: Test
        grade: D
        graded_at: "2025-01-01T00:00:00Z"
        graded_model_sha: old_sha
        graded_evaluators: audit
        graded_logic_version: 12
        ---

        Body.
        """,
    )

    assert write_grade(page, "A", model_sha="new_sha", evaluator_tier="full")
    text = page.read_text(encoding="utf-8")

    assert "grade: A" in text
    assert "grade: D" not in text
    assert text.count("grade:") == 1
    for operational_field in (
        "graded_at:",
        "graded_model_sha:",
        "graded_evaluators:",
        "graded_logic_version:",
    ):
        assert operational_field not in text


def test_write_grade_preserves_unrelated_frontmatter_and_body(tmp_path):
    page = _page(
        tmp_path,
        """\
        ---
        title: My Page
        description: >
          A folded description
          that spans lines.
        evidence:
          model_sha: evsha
          claims:
            - CLM-001
        weight: 5
        ---

        Body content.
        """,
    )

    assert write_grade(page, "C", grade_reasons=["api_accuracy FAIL"])
    text = page.read_text(encoding="utf-8")

    assert "title: My Page" in text
    assert "description: >" in text
    assert "evidence:" in text
    assert "model_sha: evsha" in text
    assert "CLM-001" in text
    assert "weight: 5" in text
    assert "Body content." in text
    assert "grade_reasons:" in text
    assert '  - "api_accuracy FAIL"' in text


def test_invalid_grade_returns_false(tmp_path):
    page = _page(tmp_path, "---\ntitle: T\n---\nBody.\n")

    assert write_grade(page, "X") is False
    assert "grade: X" not in page.read_text(encoding="utf-8")


def test_no_frontmatter_returns_false(tmp_path):
    page = _page(tmp_path, "Just body text, no frontmatter.\n")

    assert write_grade(page, "A") is False


def test_double_write_does_not_duplicate_grade_fields(tmp_path):
    page = _page(tmp_path, "---\ntitle: Page\n---\n\nBody.\n")

    assert write_grade(page, "A", model_sha="sha1")
    assert write_grade(page, "B", model_sha="sha2")
    text = page.read_text(encoding="utf-8")

    assert text.count("grade:") == 1
    assert text.count("graded_content_hash:") == 1
    assert "grade: B" in text
    assert "sha1" not in text
    assert "sha2" not in text


def test_read_grade_round_trip(tmp_path):
    page = _page(tmp_path, "---\ntitle: Page\n---\n\nBody.\n")

    assert write_grade(page, "D", grade_reasons=["reason X", "reason Y"])
    stored = read_grade(page)

    assert stored["grade"] == "D"
    assert len(stored["content_hash"]) == 32
    assert stored["grade_reasons"] == ["reason X", "reason Y"]
    assert stored["evaluator_versions"] == {}
    assert stored["grade_final"] is True


def test_policy_mode_skips_body_changed_when_grade_unchanged(tmp_path):
    page = _page(tmp_path, "---\ntitle: Page\n---\n\nBody.\n")
    assert write_grade(page, "A")
    original = page.read_text(encoding="utf-8")

    page.write_text(original.replace("Body.", "Body changed."), encoding="utf-8")
    assert write_grade(page, "A", write_mode="policy")
    text = page.read_text(encoding="utf-8")

    assert "Body changed." in text
    assert text.count("graded_content_hash:") == 1
