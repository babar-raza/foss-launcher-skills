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


# ---------------------------------------------------------------------------
# sweep_snippet_execution_proof — MT072-2026-09-23-EXAMPLE-VERIFICATION-
# PRODUCTIONIZATION/TC-06: the post-promote proof sweep this whole file's
# module docstring (and audit/snippets.py's own SKIP message, and
# gate_l15_snippet_syntax's own docstring above) all describe as "not built
# yet" / "deferred". These tests cover the real writer this taskcard adds.
# ---------------------------------------------------------------------------

def _build_merged_snippets(tmp_path, family, platform, files: dict):
    """Build a real merged/snippets/snippets_index.json via the same
    _promote_snippets() path production uses (so code_sha256 is real, not
    hand-typed), under tmp_path/knowledge/{family}/{platform}/merged/. `files`
    maps a scout filename to its source text. Returns the knowledge_root."""
    knowledge_root = tmp_path / "knowledge"
    base = knowledge_root / family / platform
    scout_dir = base / "scout"
    merged_dir = base / "merged"
    snip_dir = scout_dir / "snippets"
    snip_dir.mkdir(parents=True)
    for fname, text in files.items():
        (snip_dir / fname).write_text(text, encoding="utf-8")
    (snip_dir / "snippets_index.json").write_text(
        json.dumps([{"file": fname} for fname in files]), encoding="utf-8")
    promote_mod._promote_snippets(scout_dir, merged_dir)
    return knowledge_root


def _read_index(knowledge_root, family, platform):
    path = knowledge_root / family / platform / "merged" / "snippets" / "snippets_index.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_sweep_writes_the_correct_execution_proof_shape_for_a_real_pass(tmp_path):
    """A genuinely valid go snippet gets a real tier-1 PASS -- the exact shape
    _stale_component/_lookup_proof (content_eval/evaluators/example_execution.py)
    and gate_l15_snippet_syntax (launch_gate.py) already read: tier/status/
    clone_head/runner_version."""
    knowledge_root = _build_merged_snippets(
        tmp_path, "testfam", "go", {"a.go": "package main\n\nfunc main() {}\n"})

    summary = promote_mod.sweep_snippet_execution_proof(
        "testfam", "go", knowledge_root=knowledge_root)

    assert summary == {
        "family": "testfam", "platform": "go",
        "total": 1, "swept": 1, "skipped_no_runner": 0, "skipped_no_hash": 0,
    }
    entry = _read_index(knowledge_root, "testfam", "go")[0]
    proof = entry["execution_proof"]
    assert proof["tier"] == 1
    assert proof["status"] == "PASS"
    assert proof["runner_version"] == "1"
    assert "clone_head" in proof
    assert "reason" not in proof  # no reason key on a clean PASS


def test_sweep_never_fabricates_a_pass_on_a_real_syntax_error(tmp_path):
    """A genuinely broken go snippet must be reported as a real, tier-1
    SYNTAX-ERROR -- never silently upgraded to PASS just because it has a
    code_sha256 on file."""
    broken = "package main\n\nfunc main( {\n"  # missing closing paren
    knowledge_root = _build_merged_snippets(tmp_path, "testfam", "go", {"a.go": broken})

    summary = promote_mod.sweep_snippet_execution_proof(
        "testfam", "go", knowledge_root=knowledge_root)
    assert summary["swept"] == 1

    entry = _read_index(knowledge_root, "testfam", "go")[0]
    proof = entry["execution_proof"]
    assert proof["status"] == "BLOCKED-WITH-REASON"
    assert proof["reason"] == "SYNTAX-ERROR"
    assert proof["tier"] == 1  # a real parse DID run -- tier 1, not tier 0
    assert proof["status"] != "PASS"


def test_sweep_is_idempotent_across_two_runs(tmp_path):
    """Running the sweep twice in a row must not duplicate entries, change
    their count, or produce a different execution_proof (same content, same
    clone_head, same runner_version in -> same proof out)."""
    knowledge_root = _build_merged_snippets(
        tmp_path, "testfam", "go", {
            "a.go": "package main\n\nfunc main() {}\n",
            "b.go": "package main\n\nfunc broken( {\n",
        })
    index_path = knowledge_root / "testfam" / "go" / "merged" / "snippets" / "snippets_index.json"

    first_summary = promote_mod.sweep_snippet_execution_proof(
        "testfam", "go", knowledge_root=knowledge_root)
    first_bytes = index_path.read_bytes()
    first_index = _read_index(knowledge_root, "testfam", "go")

    second_summary = promote_mod.sweep_snippet_execution_proof(
        "testfam", "go", knowledge_root=knowledge_root)
    second_bytes = index_path.read_bytes()
    second_index = _read_index(knowledge_root, "testfam", "go")

    assert first_summary == second_summary
    assert len(second_index) == len(first_index) == 2
    assert second_bytes == first_bytes, "re-running the sweep must be a byte-for-byte no-op"
    assert [e["execution_proof"] for e in second_index] == [e["execution_proof"] for e in first_index]


def test_sweep_honestly_skips_a_language_this_package_cannot_verify_offline(tmp_path):
    """python/typescript are whole-candidate runners that always attempt a real
    acquire/execute regardless of Policy (see this function's own docstring) --
    the sweep must skip them with a disclosed note, never crash, and never
    stamp a fabricated execution_proof."""
    knowledge_root = _build_merged_snippets(
        tmp_path, "testfam", "python", {"a.py": "print('hello')\n"})

    summary = promote_mod.sweep_snippet_execution_proof(
        "testfam", "python", knowledge_root=knowledge_root)

    assert summary["swept"] == 0
    assert summary["skipped_no_runner"] == 1
    assert "note" in summary
    entry = _read_index(knowledge_root, "testfam", "python")[0]
    assert "execution_proof" not in entry


def test_sweep_skips_an_entry_with_no_code_sha256_without_crashing(tmp_path):
    """An index entry whose scout file never got hashed (e.g. the file was
    missing at promote time -- see the sibling _promote_snippets tests above)
    has nothing to verify against; the sweep must skip it honestly, not crash
    and not fabricate a proof."""
    knowledge_root = tmp_path / "knowledge"
    base = knowledge_root / "testfam" / "go" / "merged" / "snippets"
    base.mkdir(parents=True)
    (base / "snippets_index.json").write_text(json.dumps([
        {"id": "snippet_001", "file": "ghost.go"},  # no code_sha256 at all
    ]), encoding="utf-8")

    summary = promote_mod.sweep_snippet_execution_proof(
        "testfam", "go", knowledge_root=knowledge_root)

    assert summary == {
        "family": "testfam", "platform": "go",
        "total": 1, "swept": 0, "skipped_no_runner": 0, "skipped_no_hash": 1,
    }
    entry = _read_index(knowledge_root, "testfam", "go")[0]
    assert "execution_proof" not in entry


def test_sweep_reports_an_error_for_a_product_with_no_snippet_index(tmp_path):
    """No snippets_index.json at all (product never promoted, or has no
    snippets) -- honest error in the summary, not a crash."""
    knowledge_root = tmp_path / "knowledge"

    summary = promote_mod.sweep_snippet_execution_proof(
        "testfam", "go", knowledge_root=knowledge_root)

    assert "error" in summary
    assert summary["swept"] == 0
