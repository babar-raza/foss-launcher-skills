"""MT056 (Fifty-Sixth incident, 2026-08-18): scoped, convergent idempotency -- regression tests.

Covers the MT056 machinery end to end at the unit/wiring level, in a NEW file (deliberately not
test_readme_refresh_run.py / test_readme_refresh_checks.py, which a parallel session was
actively editing the evening this landed -- file-level isolation was a real concurrency
requirement, not style):

  - block model: split_into_scope_blocks / compute_block_fingerprints (content-addressed
    identity -- the anti-R-07 design; see reports/_scratch/mt056_regression_ledger.md)
  - out-of-scope diff gate: check_scope_compliance (fail-closed, negative controls included)
  - frozen-block gate: check_frozen_blocks_unchanged
  - Mermaid geometry HARD gate: check_diagram_label_geometry (both clauses, real corpus labels)
  - canonical candidate store: _candidate_store_findings / _require_canonical_tree /
    _validate_candidate_tree_for_audit (single-current-candidate enforcement, archive
    integrity, stale-path protection)
  - workflow wiring: declare-scope -> _apply_scope_enforcement -> accept-blocks ->
    converge-verify, including scope_required fail-closed and source invalidation
  - republication-debt tripwire: _published_readme_current_findings (the TC-HARDEN-47/48
    lost-taskcard class)

Every new gate gets at least one fixture proving it FIRES on the defect and one proving it
stays SILENT on correct content (this plan's own prove-it-in-both-directions discipline).
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "foss"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import readme_refresh_checks as checks  # noqa: E402
import readme_refresh_run as rr  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    rr.configure()


SAMPLE = """# Aspose.Test FOSS for Python

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An intro paragraph about the product.

## At a Glance

```mermaid
flowchart LR
  PRODUCT["Aspose.Test"]
  subgraph Capabilities["Core Capabilities"]
    c1["Read spreadsheets"]
  end
  subgraph Outputs["Outputs"]
    o1[".xlsx workbook"]
  end
```

Some prose after the diagram.

## Key Capabilities

- Reads `Workbook` files.

## Installation

```bash
pip install aspose-test
```

## License

MIT.
"""


# --- A. Block model --------------------------------------------------------------------------


def test_split_into_scope_blocks_ids_and_mermaid_extraction():
    blocks = checks.split_into_scope_blocks(SAMPLE)
    assert "__preamble__" in blocks
    assert "mermaid" in blocks
    assert "at-a-glance" in blocks
    assert "key-capabilities" in blocks
    assert "installation" in blocks
    assert "license" in blocks
    # the mermaid block is the full fenced text...
    assert blocks["mermaid"].startswith("```mermaid")
    assert blocks["mermaid"].rstrip().endswith("```")
    # ...and the host section holds the placeholder, not the diagram
    assert "<MERMAID_BLOCK_CHECKED_SEPARATELY>" in blocks["at-a-glance"]
    assert "flowchart LR" not in blocks["at-a-glance"]
    # prose around the diagram stays attributed to the host section
    assert "Some prose after the diagram." in blocks["at-a-glance"]


def test_slugify_is_case_insensitive_but_rename_changes_identity():
    assert checks._slugify_block_heading("Key Capabilities") == "key-capabilities"
    assert checks._slugify_block_heading("Key capabilities") == "key-capabilities"
    assert checks._slugify_block_heading("Scope and Limitations") != checks._slugify_block_heading("Key Capabilities")


def test_fingerprints_change_only_for_edited_block():
    before = checks.compute_block_fingerprints(SAMPLE)
    edited = SAMPLE.replace("- Reads `Workbook` files.", "- Reads `Workbook` and `Cell` objects.")
    after = checks.compute_block_fingerprints(edited)
    assert before["key-capabilities"] != after["key-capabilities"]
    for block_id in before:
        if block_id != "key-capabilities":
            assert before[block_id] == after[block_id], block_id


def test_fingerprint_of_mermaid_independent_of_host_prose():
    before = checks.compute_block_fingerprints(SAMPLE)
    edited = SAMPLE.replace("Some prose after the diagram.", "Different prose after the diagram.")
    after = checks.compute_block_fingerprints(edited)
    assert before["mermaid"] == after["mermaid"]
    assert before["at-a-glance"] != after["at-a-glance"]


# --- B. Out-of-scope diff gate ----------------------------------------------------------------


def test_scope_compliance_authorized_change_passes():
    edited = SAMPLE.replace("- Reads `Workbook` files.", "- Reads `Workbook` sheets.")
    assert checks.check_scope_compliance(SAMPLE, edited, ["key-capabilities"]) == []


def test_scope_compliance_unauthorized_modification_fails():
    edited = SAMPLE.replace("MIT.", "MIT license text reworded.")
    findings = checks.check_scope_compliance(SAMPLE, edited, ["key-capabilities"])
    assert len(findings) == 1
    assert findings[0]["block_id"] == "license"
    assert findings[0]["change"] == "modified"


def test_scope_compliance_unauthorized_addition_and_removal_fail():
    # append with no leading newline so the preceding (license) block's own trailing bytes are
    # genuinely untouched -- the gate is byte-exact, and that strictness is the point
    added = SAMPLE + "## Dependencies\n\nNone.\n"
    findings = checks.check_scope_compliance(SAMPLE, added, ["key-capabilities"])
    assert [f["change"] for f in findings] == ["added"]
    removed = SAMPLE.replace("## Installation\n\n```bash\npip install aspose-test\n```\n\n", "")
    findings = checks.check_scope_compliance(SAMPLE, removed, ["key-capabilities"])
    assert [f["change"] for f in findings] == ["removed"]
    assert findings[0]["block_id"] == "installation"


def test_scope_compliance_mermaid_scope_allows_diagram_but_not_host_prose():
    diagram_only = SAMPLE.replace('c1["Read spreadsheets"]', 'c1["Read workbooks"]')
    assert checks.check_scope_compliance(SAMPLE, diagram_only, ["mermaid"]) == []
    prose_too = diagram_only.replace("Some prose after the diagram.", "Sneaky prose edit.")
    findings = checks.check_scope_compliance(SAMPLE, prose_too, ["mermaid"])
    assert [f["block_id"] for f in findings] == ["at-a-glance"]


def test_scope_compliance_allowed_dependency_is_authorized():
    edited = SAMPLE.replace("- Reads `Workbook` files.", "- Reads `Workbook` sheets.") \
                   .replace("An intro paragraph about the product.",
                            "An intro paragraph describing sheet reading.")
    findings = checks.check_scope_compliance(SAMPLE, edited, ["key-capabilities", "__preamble__"])
    assert findings == []


# --- C. Frozen-block gate ---------------------------------------------------------------------


def _entry(block_id, status, text_source=SAMPLE):
    return {
        "block_id": block_id,
        "status": status,
        "accepted_sha256": checks.compute_block_fingerprints(text_source).get(block_id),
    }


def test_frozen_block_unchanged_passes():
    entries = [_entry("license", "CONVERGED"), _entry("installation", "FROZEN_ACCEPTED")]
    assert checks.check_frozen_blocks_unchanged(SAMPLE, entries) == []


def test_frozen_block_changed_without_scope_fails():
    entries = [_entry("license", "CONVERGED")]
    edited = SAMPLE.replace("MIT.", "Apache.")
    findings = checks.check_frozen_blocks_unchanged(edited, entries)
    assert len(findings) == 1 and findings[0]["block_id"] == "license"


def test_frozen_block_changed_with_authorization_passes():
    entries = [_entry("license", "CONVERGED")]
    edited = SAMPLE.replace("MIT.", "Apache.")
    assert checks.check_frozen_blocks_unchanged(edited, entries, ["license"]) == []


def test_frozen_block_deleted_fails_and_active_statuses_are_ignored():
    entries = [_entry("installation", "CONVERGED"), _entry("license", "ACTIVE_IMPROVEMENT")]
    removed = SAMPLE.replace("## Installation\n\n```bash\npip install aspose-test\n```\n\n", "")
    edited = removed.replace("MIT.", "Apache.")  # license may change: not frozen
    findings = checks.check_frozen_blocks_unchanged(edited, entries)
    assert [f["block_id"] for f in findings] == ["installation"]


def test_frozen_block_malformed_entry_fails_closed():
    findings = checks.check_frozen_blocks_unchanged(
        SAMPLE, [{"block_id": "license", "status": "CONVERGED"}]  # no accepted_sha256
    )
    assert len(findings) == 1 and "accepted_sha256" in findings[0]["reason"]
    findings = checks.check_frozen_blocks_unchanged(
        SAMPLE, [{"block_id": "license", "status": "SHIPPED"}]  # unknown status
    )
    assert len(findings) == 1 and "not one of the defined states" in findings[0]["reason"]


# --- D. Mermaid geometry HARD gate --------------------------------------------------------------


def _diagram_readme(label):
    return f"""# T

## At a Glance

```mermaid
flowchart LR
  PRODUCT["Aspose.Test"]
  subgraph Capabilities["Core Capabilities"]
    c1["{label}"]
  end
  subgraph Outputs["Outputs"]
    o1[".xlsx workbook"]
  end
```
"""


def test_geometry_clean_label_passes():
    assert checks.check_diagram_label_geometry(_diagram_readme("Read spreadsheets quickly")) == []


def test_geometry_real_safe_corpus_tokens_pass():
    # The two longest render-verified-safe tokens (21/20 chars) and the corpus's longest real
    # token (24 chars) must all stay clean -- the hard gate must not fail known-good content.
    for label in ("Named ranges (DefinedNameCollection)",
                  "Text search (TextFragmentAbsorber)",
                  "PPTM/PPSX/PPSM/POTX/POTM variants"):
        assert checks.check_diagram_label_geometry(_diagram_readme(label)) == [], label


def test_geometry_token_overflow_fails():
    label = "Uses SpreadsheetProcessingConfigurationFactory here"  # 44-char token
    findings = checks.check_diagram_label_geometry(_diagram_readme(label))
    assert any(f["kind"] == "token_overflow" for f in findings)


def test_geometry_real_oversized_corpus_label_fails():
    # page/python c5 -- the real, 90-char worst label in the live corpus (R-01 class).
    label = ("Low-level PostScript/EPS interpretation (PsInterpreter, OperatorRegistry, "
             "font resolution)")
    findings = checks.check_diagram_label_geometry(_diagram_readme(label))
    assert any(f["kind"] == "label_too_tall" for f in findings)
    tall = [f for f in findings if f["kind"] == "label_too_tall"][0]
    assert tall["estimated_lines"] > 3


def test_geometry_three_line_label_passes_four_line_fails():
    ok = "Cell and range styling with fonts borders and fills"  # 51 chars ~ 2-3 lines
    assert checks.check_diagram_label_geometry(_diagram_readme(ok)) == []
    tall = ("Author PS, EPS, and XPS documents from scratch with builders, "
            "graphics state, and text runs")  # ~93 chars ~ 4 lines
    findings = checks.check_diagram_label_geometry(_diagram_readme(tall))
    assert any(f["kind"] == "label_too_tall" for f in findings)


def test_geometry_checks_container_titles_too():
    text = _diagram_readme("Short").replace(
        'Outputs["Outputs"]',
        'Outputs["Outputs and every accessible artifact this library can possibly produce '
        'for downstream consumers"]',
    )
    findings = checks.check_diagram_label_geometry(text)
    assert any(f["kind"] == "label_too_tall" for f in findings)


def test_geometry_no_mermaid_block_is_silent():
    assert checks.check_diagram_label_geometry("# T\n\nNo diagram here.\n") == []


def test_estimate_wrapped_lines_never_splits_tokens():
    assert checks._estimate_wrapped_lines("a" * 60, 26) == 1  # one unbreakable token, one line
    assert checks._estimate_wrapped_lines("aaaa bbbb cccc", 26) == 1
    assert checks._estimate_wrapped_lines("aaaaaaaaaaaa bbbbbbbbbbbb cccccccccccc", 26) == 2


# --- E. Canonical candidate store ---------------------------------------------------------------


def _store_repo(tmp_path, *, canonical="repo-presenter-regen-full",
                archived=("repo-presenter",)):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    (repo_root / "data" / "readme_candidate_store.json").write_text(json.dumps({
        "schema_version": 1,
        "canonical_tree": canonical,
        "archived_trees": list(archived),
    }), encoding="utf-8")
    (repo_root / "reports").mkdir()
    return repo_root


def _write_tree_candidate(repo_root, tree, family, platform, text):
    d = repo_root / "reports" / tree / family / platform
    d.mkdir(parents=True, exist_ok=True)
    (d / "readme.md").write_text(text, encoding="utf-8")
    return d / "readme.md"


def test_store_findings_clean_when_only_canonical_holds_candidate(tmp_path):
    repo_root = _store_repo(tmp_path)
    _write_tree_candidate(repo_root, "repo-presenter-regen-full", "f", "p", SAMPLE)
    rr.configure(repo_root=repo_root)
    assert rr._candidate_store_findings("f", "p") == []


def test_store_findings_unregistered_sibling_tree_fails(tmp_path):
    repo_root = _store_repo(tmp_path)
    _write_tree_candidate(repo_root, "repo-presenter-regen-full", "f", "p", SAMPLE)
    _write_tree_candidate(repo_root, "repo-presenter-sneaky-copy", "f", "p", SAMPLE + "x")
    rr.configure(repo_root=repo_root)
    findings = rr._candidate_store_findings("f", "p")
    assert len(findings) == 1
    assert "more than one current candidate" in findings[0]["reason"]


def test_store_findings_archived_without_marker_is_incomplete(tmp_path):
    repo_root = _store_repo(tmp_path)
    _write_tree_candidate(repo_root, "repo-presenter-regen-full", "f", "p", SAMPLE)
    _write_tree_candidate(repo_root, "repo-presenter", "f", "p", SAMPLE)
    rr.configure(repo_root=repo_root)
    findings = rr._candidate_store_findings("f", "p")
    assert len(findings) == 1 and "archival incomplete" in findings[0]["reason"]


def test_store_findings_archive_marker_matching_passes_violation_fails(tmp_path):
    repo_root = _store_repo(tmp_path)
    _write_tree_candidate(repo_root, "repo-presenter-regen-full", "f", "p", SAMPLE)
    old = _write_tree_candidate(repo_root, "repo-presenter", "f", "p", "old frozen text\n")
    marker = repo_root / "reports" / "repo-presenter" / "_ARCHIVED.json"
    marker.write_text(json.dumps({
        "readme_sha256": {
            "f/p/readme.md": hashlib.sha256(old.read_bytes()).hexdigest(),
        },
    }), encoding="utf-8")
    rr.configure(repo_root=repo_root)
    assert rr._candidate_store_findings("f", "p") == []
    # violate the archive
    old.write_text("someone edited the frozen tree\n", encoding="utf-8")
    findings = rr._candidate_store_findings("f", "p")
    assert len(findings) == 1 and "ARCHIVE VIOLATED" in findings[0]["reason"]


def test_require_canonical_tree_refuses_non_canonical_and_validator_tags_archived(tmp_path):
    repo_root = _store_repo(tmp_path)
    rr.configure(repo_root=repo_root, candidate_tree_name="repo-presenter")
    with pytest.raises(rr.ReadmeRefreshRunError, match="not the canonical tree"):
        rr._require_canonical_tree("start")
    tag = rr._validate_candidate_tree_for_audit()
    assert tag and "NON-CANONICAL" in tag
    rr.configure(repo_root=repo_root, candidate_tree_name="repo-presenter-regen-full")
    rr._require_canonical_tree("start")  # canonical: no raise
    assert rr._validate_candidate_tree_for_audit() is None
    rr.configure(repo_root=repo_root, candidate_tree_name="repo-presenter-unknown")
    with pytest.raises(rr.ReadmeRefreshRunError, match="neither the canonical tree"):
        rr._validate_candidate_tree_for_audit()


def test_store_absent_is_backward_compatible_no_op(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "reports").mkdir(parents=True)
    rr.configure(repo_root=repo_root, candidate_tree_name="anything-at-all")
    rr._require_canonical_tree("start")
    assert rr._validate_candidate_tree_for_audit() is None
    assert rr._candidate_store_findings("f", "p") == []


# --- F. Workflow wiring: declare-scope -> enforcement -> accept -> converge --------------------


def _workflow_repo(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    (repo_root / "data" / "products.json").write_text(json.dumps([{
        "family": "testfam", "platform": "testplat", "active": True,
        "repo_url": "https://github.com/test-org/test-repo",
        "clone_url": "https://github.com/test-org/test-repo.git",
    }]), encoding="utf-8")
    (repo_root / "reports").mkdir()
    rr.configure(repo_root=repo_root)
    candidate = rr._candidate_readme_path("testfam", "testplat")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(SAMPLE, encoding="utf-8")
    manifest = rr.start_run("testfam", "testplat", session_id="sess-a", skip_preflight=True)
    return repo_root, candidate, manifest


def test_start_pins_candidate_tree_and_mid_run_flip_is_refused(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    assert manifest["candidate_tree"] == rr._DEFAULT_CANDIDATE_TREE_NAME
    rr.configure(repo_root=repo_root, candidate_tree_name="repo-presenter")
    with pytest.raises(rr.ReadmeRefreshRunError, match="refusing to mix trees mid-run"):
        rr.declare_scope("testfam", "testplat", manifest["run_id"],
                         issue="x", areas=["license"], session_id="sess-a")


def test_declare_scope_writes_immutable_baseline_and_enforcement_fails_out_of_scope(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    run_id = manifest["run_id"]
    record = rr.declare_scope(
        "testfam", "testplat", run_id, issue="mermaid-node-text-clipping",
        areas=["mermaid"], session_id="sess-a",
    )
    assert record["areas"] == ["mermaid"] and record["baseline_sha256"]
    assert rr._scope_baseline_path("testfam", "testplat", run_id).is_file()

    # in-scope edit -> scope_compliance clean
    candidate.write_text(
        SAMPLE.replace('c1["Read spreadsheets"]', 'c1["Read workbooks"]'), encoding="utf-8")
    result: dict = {}
    rr._apply_scope_enforcement(result, "testfam", "testplat", run_id,
                                candidate.read_text(encoding="utf-8"))
    assert result["scope_compliance"]["findings"] == []
    assert result["candidate_store_integrity"]["hard_gate"] is True

    # out-of-scope collateral edit -> hard finding naming the block
    candidate.write_text(
        SAMPLE.replace("MIT.", "Apache."), encoding="utf-8")
    result = {}
    rr._apply_scope_enforcement(result, "testfam", "testplat", run_id,
                                candidate.read_text(encoding="utf-8"))
    assert [f["block_id"] for f in result["scope_compliance"]["findings"]] == ["license"]

    # iterating the in-scope area repeatedly still compares against the ORIGINAL baseline
    candidate.write_text(
        SAMPLE.replace('c1["Read spreadsheets"]', 'c1["Read sheets fast"]'), encoding="utf-8")
    result = {}
    rr._apply_scope_enforcement(result, "testfam", "testplat", run_id,
                                candidate.read_text(encoding="utf-8"))
    assert result["scope_compliance"]["findings"] == []


def test_accept_blocks_requires_clean_checks_and_checked_snapshot(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    run_id = manifest["run_id"]
    run_root = rr._run_root("testfam", "testplat", run_id)
    (run_root / "checks").mkdir(parents=True, exist_ok=True)

    # no result.json yet -> refused
    with pytest.raises(rr.ReadmeRefreshRunError, match="no checks/result.json"):
        rr.accept_blocks("testfam", "testplat", run_id, blocks=["license"], session_id="sess-a")

    # failing hard gate -> refused
    (run_root / "checks" / "result.json").write_text(json.dumps(
        {"required_sections": {"hard_gate": True, "findings": [{"reason": "x"}]}}
    ), encoding="utf-8")
    with pytest.raises(rr.ReadmeRefreshRunError, match="while hard gates fail"):
        rr.accept_blocks("testfam", "testplat", run_id, blocks=["license"], session_id="sess-a")

    # clean result but candidate != snapshot -> refused (accepting unchecked edits forbidden)
    (run_root / "checks" / "result.json").write_text(json.dumps(
        {"required_sections": {"hard_gate": True, "findings": []}}
    ), encoding="utf-8")
    (run_root / "checks" / "last_checked_candidate.md").write_text(SAMPLE + "stale",
                                                                   encoding="utf-8")
    with pytest.raises(rr.ReadmeRefreshRunError, match="recheck first"):
        rr.accept_blocks("testfam", "testplat", run_id, blocks=["license"], session_id="sess-a")

    # snapshot matches -> accepted, registry written with content hash + pinned source
    (run_root / "checks" / "last_checked_candidate.md").write_text(SAMPLE, encoding="utf-8")
    registry = rr.accept_blocks("testfam", "testplat", run_id,
                                blocks=["license", "installation"], status="CONVERGED",
                                note="pilot", session_id="sess-a")
    ids = {e["block_id"]: e for e in registry["blocks"]}
    assert set(ids) == {"license", "installation"}
    assert ids["license"]["accepted_sha256"] == checks.compute_block_fingerprints(SAMPLE)["license"]
    assert registry["document_sha256"] == hashlib.sha256(SAMPLE.encode("utf-8")).hexdigest()
    assert rr._acceptance_registry_path("testfam", "testplat").is_file()


def test_scope_required_fails_closed_on_undeclared_drift_and_passes_when_stable(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    run_id = manifest["run_id"]
    run_root = rr._run_root("testfam", "testplat", run_id)
    (run_root / "checks").mkdir(parents=True, exist_ok=True)
    (run_root / "checks" / "result.json").write_text(json.dumps({}), encoding="utf-8")
    (run_root / "checks" / "last_checked_candidate.md").write_text(SAMPLE, encoding="utf-8")
    rr.accept_blocks("testfam", "testplat", run_id, blocks=["license"], session_id="sess-a")

    # unchanged candidate, no scope -> everything green (stable regeneration after convergence)
    result: dict = {}
    rr._apply_scope_enforcement(result, "testfam", "testplat", run_id, SAMPLE)
    assert result["scope_required"]["findings"] == []
    assert result["frozen_blocks_unchanged"]["findings"] == []

    # drifted candidate, no scope -> scope_required fires naming the changed blocks
    drifted = SAMPLE.replace("- Reads `Workbook` files.", "- Reads everything.")
    result = {}
    rr._apply_scope_enforcement(result, "testfam", "testplat", run_id, drifted)
    assert len(result["scope_required"]["findings"]) == 1
    assert "key-capabilities" in result["scope_required"]["findings"][0]["changed_blocks"]

    # frozen-block edit is separately named by the frozen gate
    frozen_drift = SAMPLE.replace("MIT.", "Apache.")
    result = {}
    rr._apply_scope_enforcement(result, "testfam", "testplat", run_id, frozen_drift)
    assert [f["block_id"] for f in result["frozen_blocks_unchanged"]["findings"]] == ["license"]


def test_converge_verify_stable_then_drift_then_source_invalidation(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    run_id = manifest["run_id"]
    run_root = rr._run_root("testfam", "testplat", run_id)
    (run_root / "checks").mkdir(parents=True, exist_ok=True)
    (run_root / "checks" / "result.json").write_text(json.dumps({}), encoding="utf-8")
    (run_root / "checks" / "last_checked_candidate.md").write_text(SAMPLE, encoding="utf-8")
    rr.accept_blocks("testfam", "testplat", run_id, blocks=["license"], session_id="sess-a")

    verdict = rr.converge_verify("testfam", "testplat", run_id, session_id="sess-a")
    assert verdict["converged"] is True and verdict["drift_findings"] == []

    candidate.write_text(SAMPLE.replace("MIT.", "Apache."), encoding="utf-8")
    verdict = rr.converge_verify("testfam", "testplat", run_id, session_id="sess-a")
    assert verdict["converged"] is False
    assert [f["block_id"] for f in verdict["drift_findings"]] == ["license"]

    # source invalidation: registry pinned a clone head; the live cache moved on
    candidate.write_text(SAMPLE, encoding="utf-8")
    registry_path = rr._acceptance_registry_path("testfam", "testplat")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["blocks"][0]["source_fingerprint"] = {"clone_cache_head": "oldhead"}
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    clone_dir = rr._product_clone_cache("testfam", "testplat")
    clone_dir.mkdir(parents=True, exist_ok=True)

    class _FakeGit:
        def __call__(self, cmd, **kwargs):
            class R:
                returncode = 0
                stdout = "newhead\n"
                stderr = ""
            return R()
    rr.configure(repo_root=repo_root, command_runner=_FakeGit())

    verdict = rr.converge_verify("testfam", "testplat", run_id, session_id="sess-a")
    assert verdict["source_invalidated_blocks"] == ["license"]
    assert verdict["invalidation_applied"] is False  # report-only by default
    verdict = rr.converge_verify("testfam", "testplat", run_id,
                                 apply_invalidation=True, session_id="sess-a")
    assert verdict["invalidation_applied"] is True
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["blocks"][0]["status"] == "INVALIDATED_BY_SOURCE_CHANGE"


def test_declare_scope_requires_areas_or_full_rewrite_and_archives_prior_scope(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    run_id = manifest["run_id"]
    with pytest.raises(rr.ReadmeRefreshRunError, match="requires --areas"):
        rr.declare_scope("testfam", "testplat", run_id, issue="x", session_id="sess-a")
    rr.declare_scope("testfam", "testplat", run_id, issue="first",
                     areas=["license"], session_id="sess-a")
    rr.declare_scope("testfam", "testplat", run_id, issue="second",
                     areas=["mermaid"], session_id="sess-a")
    history = list((rr._scope_root("testfam", "testplat", run_id) / "history").glob("*.json"))
    assert len(history) == 1  # the first scope was archived, not clobbered
    current = json.loads(rr._change_scope_path("testfam", "testplat", run_id)
                         .read_text(encoding="utf-8"))
    assert current["issue"] == "second"


def test_full_rewrite_scope_authorizes_everything_but_must_be_explicit(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    run_id = manifest["run_id"]
    rr.declare_scope("testfam", "testplat", run_id, issue="total regen",
                     full_rewrite=True, session_id="sess-a")
    rewritten = SAMPLE.replace("MIT.", "Apache.").replace(
        "- Reads `Workbook` files.", "- Everything changed.")
    result: dict = {}
    rr._apply_scope_enforcement(result, "testfam", "testplat", run_id, rewritten)
    assert result["scope_compliance"]["findings"] == []
    assert result["scope_compliance"]["detail"]["full_rewrite"] is True


# --- G. Republication-debt tripwire -------------------------------------------------------------


def test_published_readme_current_fires_for_recorded_publication_with_drift(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "data").mkdir(parents=True)
    (repo_root / "data" / "readme_published_state.json").write_text(json.dumps({
        "schema_version": 1,
        "products": [{"family": "3d", "platform": "net",
                      "last_known_publication": "2026-08-05", "evidence": "PR #1"}],
    }), encoding="utf-8")
    rr.configure(repo_root=repo_root)
    findings = rr._published_readme_current_findings("3d", "net", False)
    assert len(findings) == 1 and "republication pending" in findings[0]["reason"]
    # published-and-current (readme_already_published True) -> silent
    assert rr._published_readme_current_findings("3d", "net", True) == []
    # unlisted product -> silent
    assert rr._published_readme_current_findings("cells", "rust", False) == []


# NOTE (TC-27, MT061-2026-09-01-TRACKB-FOLLOWON-2): `_record_publication()` -- the function
# this test used to cover -- was deleted. It let push()'s own success write "published" to
# data/readme_published_state.json with zero verification anyone ever merged the PR (the exact
# anti-pattern phase6b-production-hardening-design.md S3.VII warns against: an agent completing
# its own approval loop end-to-end). That responsibility now belongs exclusively to
# publication_reconciler.apply_reconciliation(), driven by a real, externally-confirmed PR merge
# event -- see test_readme_refresh_run.py's
# test_push_success_does_not_record_publication_only_reconciler_does for the regression proof,
# and test_publication_reconciler.py for the reconciler's own coverage.


# --- H. TC-M56-09: candidate-write staleness detection ------------------------------------------
#
# GAP-M56-09 (found live during the MT056 proof pass, 2026-08-18): 3 real candidate files
# (pdf/cpp, pdf/java, pdf/python) were edited directly on disk by an untraced concurrent
# session -- invisible to git (reports/ is gitignored), invisible to every MT056 gate (no run
# was ever started for the edit). candidate_store_integrity only detects >1 TREE holding a
# candidate; nothing detected a write to the SAME file in the SAME tree outside any tracked
# run. These tests reproduce that exact scenario: audit clean -> raw filesystem write bypassing
# every CLI path -> re-audit -> the drift must be visible, by name, without assuming who wrote it.


def test_candidate_drift_first_ever_check_has_no_marker_and_no_finding(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    assert rr._load_candidate_last_verified("testfam", "testplat") is None
    findings = rr._candidate_drift_findings("testfam", "testplat")
    assert findings == []


def test_candidate_drift_silent_when_unchanged_since_last_verified(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    text = candidate.read_text(encoding="utf-8")
    rr._write_candidate_verification_marker("testfam", "testplat", text, run_id="run-1")
    assert rr._candidate_drift_findings("testfam", "testplat") == []


def test_candidate_drift_fires_on_change_since_last_verified_and_names_the_prior_verification(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    original = candidate.read_text(encoding="utf-8")
    rr._write_candidate_verification_marker("testfam", "testplat", original, run_id="run-1")

    edited = original.replace("MIT.", "Apache.")
    candidate.write_text(edited, encoding="utf-8")
    findings = rr._candidate_drift_findings("testfam", "testplat")
    assert len(findings) == 1
    assert findings[0]["last_verified_by_run_id"] == "run-1"
    assert findings[0]["last_verified_at"] is not None


def test_candidate_drift_never_a_hard_gate(tmp_path):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    original = candidate.read_text(encoding="utf-8")
    rr._write_candidate_verification_marker("testfam", "testplat", original, run_id="run-1")
    candidate.write_text(original.replace("MIT.", "Apache."), encoding="utf-8")
    result: dict = {}
    result["candidate_drift_since_last_verified"] = {
        "hard_gate": False,
        "findings": rr._candidate_drift_findings("testfam", "testplat"),
    }
    assert result["candidate_drift_since_last_verified"]["hard_gate"] is False
    assert result["candidate_drift_since_last_verified"]["findings"]


def test_candidate_drift_end_to_end_reproduces_the_real_pdf_cpp_incident(tmp_path):
    """The real scenario, reproduced exactly: (1) audit a product clean via the real
    ingest-candidate call, which stamps the verification marker; (2) an untracked writer edits
    the candidate directly on disk -- no CLI path, no lock, exactly what happened to pdf/cpp/
    java/python during the MT056 proof pass; (3) re-run the real deterministic check battery
    (as audit-portfolio would) and confirm the drift finding fires, naming the prior
    verification; (4) negative control -- a second immediate re-check with no intervening
    write produces no finding."""
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    run_id = manifest["run_id"]
    original = candidate.read_text(encoding="utf-8")

    # Step 1: a real, tracked verification (matches what ingest_candidate/recheck/audit_portfolio
    # all now do at the end of _run_deterministic_checks + their own marker write).
    clone_cache = rr._product_clone_cache("testfam", "testplat")
    result1 = rr._run_deterministic_checks("testfam", "testplat", original, clone_cache)
    assert result1["candidate_drift_since_last_verified"]["findings"] == []  # first-ever check
    rr._write_candidate_verification_marker("testfam", "testplat", original, run_id=run_id)

    # Step 2: untracked writer -- a raw filesystem write, no lock acquired, no CLI path used.
    candidate.write_text(original.replace("MIT.", "Apache."), encoding="utf-8")

    # Step 3: the next real check battery (e.g. a later audit-portfolio) must surface it.
    edited = candidate.read_text(encoding="utf-8")
    result2 = rr._run_deterministic_checks("testfam", "testplat", edited, clone_cache)
    drift = result2["candidate_drift_since_last_verified"]
    assert drift["hard_gate"] is False
    assert len(drift["findings"]) == 1
    assert drift["findings"][0]["last_verified_by_run_id"] == run_id
    rr._write_candidate_verification_marker("testfam", "testplat", edited, run_id=None)

    # Step 4 (negative control): re-checking the SAME content immediately after must be silent.
    result3 = rr._run_deterministic_checks("testfam", "testplat", edited, clone_cache)
    assert result3["candidate_drift_since_last_verified"]["findings"] == []


def test_audit_portfolio_writes_verification_marker_and_surfaces_drift_across_calls(tmp_path):
    """Proves the real, registered audit-portfolio entry point end to end -- not just the
    helper functions, and not just _run_deterministic_checks's raw result (which is what the
    first draft of this test checked, and which silently masked a real bug: audit_portfolio's
    own per-product summary previously reported ONLY hard-gate findings, so this advisory
    (hard_gate=False, by deliberate design) signal never reached actual CLI/JSON output despite
    firing correctly one layer down -- caught only by asserting through audit_portfolio()
    itself, exactly as a real caller would, then fixed by adding a dedicated `candidate_drift`
    field to the per-product result)."""
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    rr.abandon_run("testfam", "testplat", manifest["run_id"], reason="not needed for this test",
                   session_id="sess-a")

    result1 = rr.audit_portfolio()
    assert result1["products"][0]["candidate_drift"] == []  # first-ever check: no prior marker
    marker = rr._load_candidate_last_verified("testfam", "testplat")
    assert marker is not None and marker["verified_by_run_id"] is None

    # Untracked write between two audits -- exactly the real pdf/cpp/java/python incident.
    original = candidate.read_text(encoding="utf-8")
    candidate.write_text(original + "\n<!-- untracked edit -->\n", encoding="utf-8")

    result2 = rr.audit_portfolio()
    assert len(result2["products"][0]["candidate_drift"]) == 1
    assert result2["products"][0]["candidate_drift"][0]["last_verified_by_run_id"] is None

    # Self-clearing behavior (a real, documented nuance, not a bug): audit_portfolio's own
    # marker write means the finding is visible for exactly ONE subsequent call -- the very
    # next unrelated audit (no further edit) already sees the drift as resolved, since the
    # marker now matches. Confirmed here so this behavior is proven, not just asserted in prose.
    result3 = rr.audit_portfolio()
    assert result3["products"][0]["candidate_drift"] == []


def test_audit_portfolio_cli_text_output_shows_drift_tag(tmp_path, capsys):
    repo_root, candidate, manifest = _workflow_repo(tmp_path)
    rr.abandon_run("testfam", "testplat", manifest["run_id"], reason="not needed for this test",
                   session_id="sess-a")
    rr.audit_portfolio()  # first-ever check, establishes the marker
    original = candidate.read_text(encoding="utf-8")
    candidate.write_text(original.replace("MIT.", "Apache."), encoding="utf-8")  # also DIRTY

    exit_code = rr.main(["audit-portfolio"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Changed since last verified (1): testfam/testplat" in out
    assert "[drift]" in out
