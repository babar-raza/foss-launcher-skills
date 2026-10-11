"""test_check_reference_index_structure.py — Regression tests for
check_reference_index_structure.py's Check 3 (duplicate rows, TC-DUPIDX-03, ST-059).

Covers:
- _is_manually_curated() (pre-existing, exercised as a precondition for Check 3)
- Full run() against a synthetic content tree: same-module duplicates (3a),
  cross-module collisions (3b), manually-curated pages skipped, clean pages pass
"""
import sys
from pathlib import Path

import pytest

# Bootstrap: add scripts/ci/checks/ to sys.path (matches test_check_grade_churn.py)
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from checks import check_reference_index_structure as checker


def _write_index(path: Path, body: str, *, last_mechanism: str = "skill") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nprovenance:\n"
        f"  last_mechanism: {last_mechanism}\n"
        "  auto_updatable: true\n---\n\n" + body,
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    ref_content = tmp_path / "content" / "reference.aspose.org" / "en"
    ref_content.mkdir(parents=True)
    knowledge_root = tmp_path / "knowledge"
    monkeypatch.setattr(checker, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(checker, "_REF_CONTENT", ref_content)
    monkeypatch.setattr(checker, "_KNOWLEDGE_ROOT", knowledge_root)
    yield tmp_path, ref_content


def test_is_manually_curated_detects_all_three_mechanisms():
    for mechanism in ("manual-edit-skill", "human-edit", "agent-edit"):
        assert checker._is_manually_curated(f"last_mechanism: {mechanism}\n")
    assert not checker._is_manually_curated("last_mechanism: skill\n")


def test_clean_page_passes_with_exit_zero(_isolate):
    tmp_path, ref_content = _isolate
    _write_index(
        ref_content / "fake" / "net" / "_index.md",
        "## Core API\n\n| Class | Description |\n|---|---|\n"
        "| `Alpha` | First. |\n| `Beta` | Second. |\n",
    )
    assert checker.run(check_staleness=False) == 0


def test_same_module_duplicate_is_hard_gate_failure(_isolate, capsys):
    tmp_path, ref_content = _isolate
    # Mirrors the real cells/cpp regression: exact duplicate, back-to-back, same module.
    _write_index(
        ref_content / "fake" / "cpp" / "_index.md",
        "## Enumerations\n\n| Enumeration | Description |\n|---|---|\n"
        "| `DiagnosticSeverity` | Specifies diagnostic severity. |\n"
        "| `DiagnosticSeverity` | Specifies diagnostic severity. |\n",
    )
    assert checker.run(check_staleness=False) == 2
    out = capsys.readouterr().out
    assert "DiagnosticSeverity" in out
    assert "exact duplicate row" in out


def test_cross_module_collision_is_hard_gate_failure(_isolate, capsys):
    tmp_path, ref_content = _isolate
    # Mirrors the real pdf/java regression: same bare name, two different modules.
    _write_index(
        ref_content / "fake" / "java" / "_index.md",
        "## Core API\n\n| `Rectangle` | ISO 32000 page rectangle. |\n\n"
        "## Drawing\n\n| `Rectangle` | Drawing shape rectangle. |\n",
    )
    assert checker.run(check_staleness=False) == 2
    out = capsys.readouterr().out
    assert "undisambiguated cross-module name collision" in out
    assert "Core API, Drawing" in out


def test_manually_curated_page_skips_duplicate_check(_isolate):
    tmp_path, ref_content = _isolate
    _write_index(
        ref_content / "fake" / "net" / "_index.md",
        "## Core API\n\n| `Alpha` | x. |\n| `Alpha` | x. |\n",
        last_mechanism="manual-edit-skill",
    )
    # Mirrors pdf/net's real, currently-live containment flag -- a protected page's
    # duplicates must not fail the gate until it is explicitly unprotected.
    assert checker.run(check_staleness=False) == 0


def test_different_class_names_same_description_not_flagged(_isolate):
    tmp_path, ref_content = _isolate
    _write_index(
        ref_content / "fake" / "net" / "_index.md",
        "## Core API\n\n| `Alpha` | A small class. |\n| `Beta` | A small class. |\n",
    )
    assert checker.run(check_staleness=False) == 0


def test_duplicate_names_in_two_different_pages_do_not_cross_contaminate(_isolate):
    tmp_path, ref_content = _isolate
    _write_index(
        ref_content / "fake" / "net" / "_index.md",
        "## Core API\n\n| `Shared` | x. |\n",
    )
    _write_index(
        ref_content / "fake" / "python" / "_index.md",
        "## Core API\n\n| `Shared` | y. |\n",
    )
    # Same class name legitimately reused across two different family/platform
    # API surfaces is expected, not a duplicate-row problem.
    assert checker.run(check_staleness=False) == 0


def test_see_also_section_never_parsed_for_duplicates(_isolate):
    tmp_path, ref_content = _isolate
    _write_index(
        ref_content / "fake" / "net" / "_index.md",
        "## Core API\n\n| `Alpha` | x. |\n\n"
        "## See Also\n\n| `Alpha` | Should never be parsed -- past the stop marker. |\n",
    )
    assert checker.run(check_staleness=False) == 0
