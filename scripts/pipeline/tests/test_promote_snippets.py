"""Tests for _promote_snippets' code_sha256 provenance field, and for its two page-
/launch-side consumers: audit/snippets.py's verify_snippet_coverage and
launch_gate.py's gate_l15_snippet_syntax.

MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION/C6: promote.py's snippet
promotion step gains a deterministic content-hash proof per entry -- no
execution, computed purely from the copied snippet's own text. All three pieces
of this "verify at the source, inherit at the page" design are this taskcard's
deliverable, so all three are covered here (C6's allowed_paths only carve out a
`test_promote_*.py` glob for new tests -- there is no separate slot for a
dedicated audit/snippets.py or launch_gate.py test file, and the existing
launch_gate test file, test_gate_l01_l07.py, is itself outside C6's
allowed_paths).
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

# sys.path is set by tests/conftest.py — no manual insert needed here.
import promote as promote_mod
import launch_gate as lg
from lib.example_verification.code_fences import normalize_content
from audit.snippets import verify_snippet_coverage
from launch_gate import STATUS_PASS, STATUS_WARN, gate_l15_snippet_syntax


def test_promote_snippets_adds_code_sha256_for_a_real_file(tmp_path):
    scout_dir = tmp_path / "scout"
    merged_dir = tmp_path / "merged"
    snip_dir = scout_dir / "snippets"
    snip_dir.mkdir(parents=True)

    snippet_text = "scene = Scene()\n    scene.save('out.obj')\n"
    (snip_dir / "example_001.py").write_text(snippet_text, encoding="utf-8")
    (snip_dir / "snippets_index.json").write_text(json.dumps([
        {"file": "example_001.py", "classes_used": ["Scene"], "methods_used": ["Scene.save"]},
    ]), encoding="utf-8")

    count = promote_mod._promote_snippets(scout_dir, merged_dir)
    assert count == 1

    merged_index = json.loads((merged_dir / "snippets" / "snippets_index.json").read_text(encoding="utf-8"))
    assert len(merged_index) == 1
    entry = merged_index[0]
    assert entry["id"] == "snippet_001"
    assert entry["provenance"] == "scout"

    code_sha = entry["code_sha256"]
    assert set(code_sha) == {"exact", "norm"}
    assert code_sha["exact"] == hashlib.sha256(snippet_text.encode("utf-8")).hexdigest()
    assert code_sha["norm"] == hashlib.sha256(
        normalize_content(snippet_text).encode("utf-8")).hexdigest()
    assert len(code_sha["exact"]) == 64
    assert len(code_sha["norm"]) == 64


def test_promote_snippets_norm_hash_is_stable_across_cosmetic_drift(tmp_path):
    """The whole point of sha256_norm: reindentation/CRLF must not defeat the lookup."""
    scout_dir = tmp_path / "scout"
    merged_dir = tmp_path / "merged"
    snip_dir = scout_dir / "snippets"
    snip_dir.mkdir(parents=True)

    # write_bytes (not write_text) so the CRLF bytes below are exactly what's on disk --
    # Path.write_text applies its own platform newline translation, which on Windows
    # would double-translate a string that already contains literal "\r\n".
    (snip_dir / "a.py").write_bytes(b"x = 1\ny = 2\n")
    (snip_dir / "b.py").write_bytes(b"  x = 1\r\n  y = 2\r\n")
    (snip_dir / "snippets_index.json").write_text(json.dumps([
        {"file": "a.py"}, {"file": "b.py"},
    ]), encoding="utf-8")

    promote_mod._promote_snippets(scout_dir, merged_dir)
    merged_index = json.loads((merged_dir / "snippets" / "snippets_index.json").read_text(encoding="utf-8"))

    norms = {e["code_sha256"]["norm"] for e in merged_index}
    exacts = {e["code_sha256"]["exact"] for e in merged_index}
    assert len(norms) == 1, "reindented/CRLF variant must normalize to the same hash"
    assert len(exacts) == 2, "byte-exact hash must still distinguish the two files"


def test_promote_snippets_missing_file_gets_no_code_sha256(tmp_path):
    """An index entry whose referenced file doesn't exist on disk (stale scout data)
    must not crash promotion -- it simply doesn't get a code_sha256 field."""
    scout_dir = tmp_path / "scout"
    merged_dir = tmp_path / "merged"
    snip_dir = scout_dir / "snippets"
    snip_dir.mkdir(parents=True)

    (snip_dir / "snippets_index.json").write_text(json.dumps([
        {"file": "does_not_exist.py", "classes_used": ["Ghost"]},
    ]), encoding="utf-8")

    count = promote_mod._promote_snippets(scout_dir, merged_dir)
    assert count == 1

    merged_index = json.loads((merged_dir / "snippets" / "snippets_index.json").read_text(encoding="utf-8"))
    assert "code_sha256" not in merged_index[0]


def test_promote_snippets_does_not_hash_a_stale_leftover_in_merged_dir(tmp_path):
    """Independent-reviewer finding: promote_atomic() seeds the staging merged/ dir via
    shutil.copytree of the PRIOR promotion's output before calling promote(), and
    snippet filenames are purely positional (snippet_NNN, reused run-over-run for
    different content). If this run's scout is missing a file the index still
    references, a same-named leftover from the prior run can still be sitting in
    merged_dir -- code_sha256 must be computed from THIS run's scout file only, never
    from a pre-existing merged-dir file, or the hash would silently prove content that
    was never actually re-verified this run."""
    scout_dir = tmp_path / "scout"
    merged_dir = tmp_path / "merged"
    snip_dir = scout_dir / "snippets"
    snip_dir.mkdir(parents=True)

    # Simulate promote_atomic()'s staging pre-seed: a same-named file already sitting in
    # merged_dir, left over from a prior run, with content this run's scout never provided.
    merged_snip = merged_dir / "snippets"
    merged_snip.mkdir(parents=True)
    stale_text = "# stale leftover from a prior promotion\nold_call()\n"
    (merged_snip / "reused_name.py").write_text(stale_text, encoding="utf-8")

    # This run's scout index references the same filename, but the scout file itself is
    # absent (a real write-gap) -- the copy step is a no-op, so nothing new lands there.
    (snip_dir / "snippets_index.json").write_text(json.dumps([
        {"file": "reused_name.py"},
    ]), encoding="utf-8")

    promote_mod._promote_snippets(scout_dir, merged_dir)

    merged_index = json.loads((merged_dir / "snippets" / "snippets_index.json").read_text(encoding="utf-8"))
    assert "code_sha256" not in merged_index[0], (
        "must not stamp a hash from a stale merged-dir file this run never copied"
    )
    # And the stale file itself must be left alone -- not silently adopted/renamed.
    assert (merged_snip / "reused_name.py").read_text(encoding="utf-8") == stale_text


# ---------------------------------------------------------------------------
# audit/snippets.py::verify_snippet_coverage — the field's page-side consumer
# ---------------------------------------------------------------------------

def _knowledge_with_index(snippet_index):
    return SimpleNamespace(snippet_index=snippet_index)


def test_verify_snippet_coverage_skips_loudly_when_index_has_no_code_sha256(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("```python\nprint('hi')\n```\n", encoding="utf-8")
    knowledge = _knowledge_with_index([{"id": "snippet_001", "classes_used": ["Foo"]}])

    findings = verify_snippet_coverage(page, knowledge)

    assert len(findings) == 1
    assert findings[0].level == "INFO"
    assert "SKIPPED" in findings[0].message
    assert "code_sha256" in findings[0].message


def test_verify_snippet_coverage_warns_on_a_novel_block(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("```python\nprint('totally novel')\n```\n", encoding="utf-8")
    knowledge = _knowledge_with_index([
        {"id": "snippet_001", "code_sha256": {"norm": "deadbeef" * 8, "exact": "cafebabe" * 8}},
    ])

    findings = verify_snippet_coverage(page, knowledge)

    assert len(findings) == 1
    assert findings[0].level == "WARN"
    assert "no matching verified snippet" in findings[0].message


def test_verify_snippet_coverage_silent_on_an_exact_match(tmp_path):
    block_text = "print('hi')"
    norm_hash = hashlib.sha256(normalize_content(block_text).encode("utf-8")).hexdigest()
    page = tmp_path / "page.md"
    page.write_text(f"```python\n{block_text}\n```\n", encoding="utf-8")
    knowledge = _knowledge_with_index([
        {"id": "snippet_001", "code_sha256": {"norm": norm_hash, "exact": "irrelevant"}},
    ])

    findings = verify_snippet_coverage(page, knowledge)

    assert findings == []


def test_verify_snippet_coverage_returns_nothing_for_an_empty_snippet_index(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("```python\nprint('hi')\n```\n", encoding="utf-8")
    knowledge = _knowledge_with_index([])

    assert verify_snippet_coverage(page, knowledge) == []


# ---------------------------------------------------------------------------
# launch_gate.py::gate_l15_snippet_syntax — the new execution_proof-based path.
# The pre-sweep bracket-heuristic fallback stays covered, unchanged, by
# test_gate_l01_l07.py::TestGateL15SnippetSyntax (outside C6's allowed_paths).
# ---------------------------------------------------------------------------

@pytest.fixture()
def _isolate_knowledge_root(tmp_path):
    saved = lg._KNOWLEDGE_ROOT
    lg._KNOWLEDGE_ROOT = tmp_path / "knowledge"
    yield
    lg._KNOWLEDGE_ROOT = saved


def _write_snippets_index(entries, tmp_path, family="testfam", platform="python"):
    snippets = tmp_path / "knowledge" / family / platform / "merged" / "snippets"
    snippets.mkdir(parents=True)
    (snippets / "snippets_index.json").write_text(json.dumps(entries), encoding="utf-8")


def test_gate_l15_passes_when_every_proven_snippet_meets_the_contract_tier(tmp_path, _isolate_knowledge_root):
    _write_snippets_index([
        {"id": "snippet_001", "execution_proof": {"tier": 3, "status": "PASS"}},
        {"id": "snippet_002", "execution_proof": {"tier": 3, "status": "PASS"}},
    ], tmp_path)

    result = gate_l15_snippet_syntax("testfam", "python")

    assert result.status == STATUS_PASS
    assert "2 proven" in result.detail


def test_gate_l15_warns_when_a_proven_snippet_falls_short_of_the_contract_tier(tmp_path, _isolate_knowledge_root):
    _write_snippets_index([
        {"id": "snippet_001", "execution_proof": {"tier": 3, "status": "PASS"}},
        {"id": "snippet_002", "execution_proof": {"tier": 1, "status": "COMPILE-ERROR"}},
    ], tmp_path)

    result = gate_l15_snippet_syntax("testfam", "python")

    assert result.status == STATUS_WARN
    assert "1 of 2 proven" in result.detail
    assert "snippet_002" in "\n".join(result.extra_lines)


def test_gate_l15_ignores_unproven_entries_mixed_with_proven_ones(tmp_path, _isolate_knowledge_root):
    """A partial sweep (some entries proven, some not yet) must judge only the proven
    ones -- unproven entries are pending, not failing."""
    _write_snippets_index([
        {"id": "snippet_001", "execution_proof": {"tier": 3, "status": "PASS"}},
        {"id": "snippet_002"},  # not yet swept
    ], tmp_path)

    result = gate_l15_snippet_syntax("testfam", "python")

    assert result.status == STATUS_PASS
    assert "1 proven" in result.detail
    assert "1 not yet swept" in result.detail
