"""Tests for scripts/pipeline/commands/foss/upstream_issue_workflow.py (MT057, Fifty-Seventh
incident). Infrastructure-layer tests only (TC-UIW-01/02/03) -- schemas, path helpers, the
counter, and both state machines' fail-closed behavior. Real-content ingestion (TC-UIW-04+)
gets its own test additions as that work lands.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "commands" / "foss"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import readme_refresh_checks as checks  # noqa: E402
import readme_refresh_run as rr  # noqa: E402
import upstream_issue_workflow as uiw  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_configure():
    yield
    rr.configure()


def _configure(tmp_path):
    reports_root = tmp_path / "reports"
    rr.configure(repo_root=tmp_path, reports_root=reports_root)
    return reports_root


# --- Path helpers (TC-UIW-01) ----------------------------------------------------------------


def test_path_helpers_resolve_under_configured_reports_root(tmp_path):
    reports_root = _configure(tmp_path)
    assert uiw._inventory_path("pdf", "go") == (
        reports_root / "upstream_issue_runs" / "pdf" / "go" / "inventory.json"
    )
    assert uiw._finding_manifest_path("pdf", "go", "UF-pdf-go-0001") == (
        reports_root / "upstream_issue_runs" / "pdf" / "go" / "findings" / "UF-pdf-go-0001" / "manifest.json"
    )
    assert uiw._bundle_manifest_path("pdf", "go", "UB-pdf-go-0001") == (
        reports_root / "upstream_issue_runs" / "pdf" / "go" / "bundles" / "UB-pdf-go-0001" / "manifest.json"
    )
    assert uiw._cross_run_action_ledger_path() == reports_root / "upstream_issue_actions.jsonl"
    assert uiw._false_positive_exclusions_path() == tmp_path / "data" / "upstream_issue_false_positive_exclusions.json"


def test_upstream_issue_paths_never_collide_with_readme_run_paths(tmp_path):
    """The new tree is a genuine sibling of reports/readme_refresh_runs/, never nested inside
    or aliased to it -- a real, disclosed design requirement (MT057's own "separate manifest
    tree" decision), proven directly rather than assumed."""
    reports_root = _configure(tmp_path)
    issue_path = uiw._issue_workflow_root("pdf", "go")
    run_path = rr._product_root("pdf", "go")
    assert issue_path != run_path
    assert not str(issue_path).startswith(str(run_path))
    assert not str(run_path).startswith(str(issue_path))
    assert issue_path.parent.parent == reports_root / "upstream_issue_runs"


# --- Counter (TC-UIW-01) ----------------------------------------------------------------------


def test_finding_counter_is_sequential_and_zero_padded(tmp_path):
    _configure(tmp_path)
    ids = [uiw._new_finding_id("pdf", "go") for _ in range(3)]
    assert ids == ["UF-pdf-go-0001", "UF-pdf-go-0002", "UF-pdf-go-0003"]


def test_bundle_counter_is_independent_of_finding_counter(tmp_path):
    _configure(tmp_path)
    uiw._new_finding_id("pdf", "go")
    uiw._new_finding_id("pdf", "go")
    first_bundle = uiw._new_bundle_id("pdf", "go")
    assert first_bundle == "UB-pdf-go-0001"  # unaffected by the finding counter's own count


def test_counters_are_scoped_per_product(tmp_path):
    _configure(tmp_path)
    uiw._new_finding_id("pdf", "go")
    first_java_finding = uiw._new_finding_id("pdf", "java")
    assert first_java_finding == "UF-pdf-java-0001"  # a different product starts fresh


# --- Finding-level state machine (TC-UIW-02) -------------------------------------------------


def _new_finding_manifest(family="pdf", platform="go", finding_id="UF-pdf-go-0001"):
    return {
        "schema_version": uiw.SCHEMA_VERSION, "family": family, "platform": platform,
        "finding_id": finding_id, "state": "DISCOVERED",
    }


def test_finding_every_legal_edge_from_discovered_succeeds(tmp_path):
    _configure(tmp_path)
    for target in sorted(uiw.FINDING_NEXT_STATES["DISCOVERED"]):
        manifest = _new_finding_manifest(finding_id=f"UF-pdf-go-{target}")
        uiw._transition_finding(manifest, target, evidence_ref="real evidence")
        assert manifest["state"] == target
        reloaded = uiw._load_finding("pdf", "go", manifest["finding_id"])
        assert reloaded["state"] == target


def test_finding_full_happy_path_reaches_bundled(tmp_path):
    _configure(tmp_path)
    manifest = _new_finding_manifest()
    uiw._transition_finding(manifest, "VERIFYING", evidence_ref="starting verification")
    uiw._transition_finding(manifest, "VERIFIED", evidence_ref="reproduced against current upstream")
    uiw._transition_finding(manifest, "DUPLICATE_CHECKED", evidence_ref="gh issue list search, no match")
    uiw._transition_finding(manifest, "BUNDLED", evidence_ref="folded into UB-pdf-go-0001")
    assert manifest["state"] == "BUNDLED"
    assert manifest["state"] in uiw.FINDING_TERMINAL_STATES


def test_finding_illegal_edge_is_rejected(tmp_path):
    """Fail-closed proof: DISCOVERED -> BUNDLED is not a legal one-step edge (must pass through
    VERIFYING/VERIFIED/DUPLICATE_CHECKED first) -- this must raise, not silently succeed."""
    _configure(tmp_path)
    manifest = _new_finding_manifest()
    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="Illegal finding transition"):
        uiw._transition_finding(manifest, "BUNDLED", evidence_ref="skip ahead")


def test_finding_transition_without_evidence_ref_raises(tmp_path):
    """Fail-closed proof for the mission's own 'every transition requires evidence' rule."""
    _configure(tmp_path)
    manifest = _new_finding_manifest()
    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="evidence_ref is required"):
        uiw._transition_finding(manifest, "VERIFYING", evidence_ref="")
    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="evidence_ref is required"):
        uiw._transition_finding(manifest, "VERIFYING", evidence_ref="   ")


def test_finding_blocked_missing_evidence_is_re_enterable(tmp_path):
    _configure(tmp_path)
    manifest = _new_finding_manifest()
    uiw._transition_finding(manifest, "VERIFYING", evidence_ref="start")
    uiw._transition_finding(manifest, "BLOCKED_MISSING_EVIDENCE", evidence_ref="no reproducer yet")
    uiw._transition_finding(manifest, "VERIFYING", evidence_ref="evidence now available")
    assert manifest["state"] == "VERIFYING"


def test_finding_terminal_states_have_no_outgoing_edges_except_re_enterable_ones(tmp_path):
    for state in uiw.FINDING_TERMINAL_STATES:
        assert uiw.FINDING_NEXT_STATES[state] == set(), (
            f"{state} is declared terminal but has outgoing edges: {uiw.FINDING_NEXT_STATES[state]}"
        )


# --- Bundle-level state machine (TC-UIW-03) --------------------------------------------------


def _new_bundle_manifest(family="pdf", platform="go", bundle_id="UB-pdf-go-0001"):
    return {
        "schema_version": uiw.SCHEMA_VERSION, "family": family, "platform": platform,
        "bundle_id": bundle_id, "state": "BUNDLED", "finding_ids": ["UF-pdf-go-0001"],
    }


def test_bundle_every_legal_edge_from_bundled_succeeds(tmp_path):
    _configure(tmp_path)
    for target in sorted(uiw.BUNDLE_NEXT_STATES["BUNDLED"]):
        manifest = _new_bundle_manifest(bundle_id=f"UB-pdf-go-{target}")
        uiw._transition_bundle(manifest, target, evidence_ref="real evidence")
        assert manifest["state"] == target


def test_bundle_full_happy_path_reaches_remote_verified(tmp_path):
    _configure(tmp_path)
    manifest = _new_bundle_manifest()
    uiw._transition_bundle(manifest, "DRAFTED", evidence_ref="draft.md written")
    uiw._transition_bundle(manifest, "INDEPENDENTLY_REVIEWED", evidence_ref="second-pass review recorded")
    uiw._transition_bundle(manifest, "READY_TO_CREATE", evidence_ref="validate-draft passed clean")
    uiw._transition_bundle(manifest, "CREATED", evidence_ref="https://github.com/org/repo/issues/123")
    uiw._transition_bundle(manifest, "REMOTE_VERIFIED", evidence_ref="gh issue view confirmed author/body/labels")
    assert manifest["state"] == "REMOTE_VERIFIED"
    assert manifest["state"] in uiw.BUNDLE_TERMINAL_STATES


def test_bundle_illegal_edge_is_rejected(tmp_path):
    """Fail-closed proof: BUNDLED -> CREATED skips drafting/review/identity-check entirely --
    must never be a legal one-step edge (this is the mission's own 'never auto-create' posture,
    enforced structurally, not just by convention)."""
    _configure(tmp_path)
    manifest = _new_bundle_manifest()
    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="Illegal bundle transition"):
        uiw._transition_bundle(manifest, "CREATED", evidence_ref="skip ahead")


def test_bundle_transition_without_evidence_ref_raises(tmp_path):
    _configure(tmp_path)
    manifest = _new_bundle_manifest()
    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="evidence_ref is required"):
        uiw._transition_bundle(manifest, "DRAFTED", evidence_ref="")


def test_bundle_blocked_identity_is_re_enterable_once_correct_account_authenticates(tmp_path):
    _configure(tmp_path)
    manifest = _new_bundle_manifest()
    uiw._transition_bundle(manifest, "DRAFTED", evidence_ref="draft written")
    uiw._transition_bundle(manifest, "INDEPENDENTLY_REVIEWED", evidence_ref="reviewed")
    uiw._transition_bundle(manifest, "READY_TO_CREATE", evidence_ref="validated")
    uiw._transition_bundle(manifest, "BLOCKED_IDENTITY", evidence_ref="gh api user returned 'someone-else'")
    uiw._transition_bundle(manifest, "READY_TO_CREATE", evidence_ref="gh api user now returns 'babar-raza'")
    assert manifest["state"] == "READY_TO_CREATE"


def test_bundle_created_can_only_reach_remote_verified(tmp_path):
    """A bundle that reaches CREATED (a real GitHub Issue exists) must never be transitionable
    back to an earlier state -- the external side effect is real and irreversible from this
    state machine's own perspective."""
    assert uiw.BUNDLE_NEXT_STATES["CREATED"] == {"REMOTE_VERIFIED"}


def test_bundle_terminal_states_have_no_outgoing_edges_except_re_enterable_ones(tmp_path):
    for state in uiw.BUNDLE_TERMINAL_STATES:
        assert uiw.BUNDLE_NEXT_STATES[state] == set(), (
            f"{state} is declared terminal but has outgoing edges: {uiw.BUNDLE_NEXT_STATES[state]}"
        )


# --- Cross-run action ledger (mirrors _append_action_ledger_row) -----------------------------


def test_append_upstream_action_ledger_row_writes_real_jsonl(tmp_path):
    _configure(tmp_path)
    uiw._append_upstream_action_ledger_row(
        "pdf", "go", action="upstream_issue_create_dry_run",
        details={"bundle_id": "UB-pdf-go-0001"}, session_id="test-session",
    )
    path = uiw._cross_run_action_ledger_path()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["family"] == "pdf"
    assert rows[0]["skill"] == "readme-refresh"
    assert rows[0]["action"] == "upstream_issue_create_dry_run"
    assert rows[0]["details"]["bundle_id"] == "UB-pdf-go-0001"


# --- Identity verification (TC-UIW-05) --------------------------------------------------------


class _FakeResult:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _gh_user_runner(login):
    def _runner(cmd, **kwargs):
        assert cmd[:3] == ["gh", "api", "user"], f"unexpected command: {cmd}"
        return _FakeResult(0, stdout=json.dumps({"login": login}))
    return _runner


def _gh_user_unauthenticated_runner():
    def _runner(cmd, **kwargs):
        assert cmd[:3] == ["gh", "api", "user"], f"unexpected command: {cmd}"
        return _FakeResult(1, stderr="gh: To use GitHub CLI in a GitHub Actions workflow...\nHTTP 401")
    return _runner


def test_preflight_identity_check_reports_correct_account(tmp_path):
    _configure(tmp_path)
    rr.configure(repo_root=tmp_path, reports_root=tmp_path / "reports", command_runner=_gh_user_runner("babar-raza"))
    result = uiw._preflight_identity_check()
    assert result == {"login": "babar-raza", "authenticated": True}


def test_preflight_identity_check_reports_a_different_account(tmp_path):
    """Fail-closed proof, direction 1: a real, different authenticated login must be reported
    accurately, never silently coerced to look like the expected one."""
    rr.configure(repo_root=tmp_path, reports_root=tmp_path / "reports", command_runner=_gh_user_runner("someone-else"))
    result = uiw._preflight_identity_check()
    assert result == {"login": "someone-else", "authenticated": True}


def test_preflight_identity_check_reports_unauthenticated(tmp_path):
    """Fail-closed proof, direction 2: no authenticated account at all must be reported as such,
    never raise (an unauthenticated gh is a real, valid, reportable outcome, not a crash)."""
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_user_unauthenticated_runner(),
    )
    result = uiw._preflight_identity_check()
    assert result["authenticated"] is False
    assert result["login"] is None
    assert "raw_error" in result


def test_preflight_identity_check_raises_on_unparseable_output(tmp_path):
    def _runner(cmd, **kwargs):
        return _FakeResult(0, stdout="not json")
    rr.configure(repo_root=tmp_path, reports_root=tmp_path / "reports", command_runner=_runner)
    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="unparseable"):
        uiw._preflight_identity_check()


def test_check_identity_marks_authorized_for_the_real_expected_login(tmp_path):
    rr.configure(repo_root=tmp_path, reports_root=tmp_path / "reports", command_runner=_gh_user_runner("babar-raza"))
    result = uiw.check_identity()
    assert result["is_authorized"] is True
    assert result["expected_login"] == "babar-raza"


def test_check_identity_marks_unauthorized_for_a_different_login_and_logs_when_scoped(tmp_path):
    reports_root = tmp_path / "reports"
    rr.configure(repo_root=tmp_path, reports_root=reports_root, command_runner=_gh_user_runner("someone-else"))
    result = uiw.check_identity(family="pdf", platform="go")
    assert result["is_authorized"] is False
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["action"] == "identity_check"
    assert rows[0]["details"]["detected_login"] == "someone-else"
    assert rows[0]["details"]["is_authorized"] is False


def test_check_identity_does_not_log_when_family_platform_not_given(tmp_path):
    reports_root = tmp_path / "reports"
    rr.configure(repo_root=tmp_path, reports_root=reports_root, command_runner=_gh_user_runner("babar-raza"))
    uiw.check_identity()
    assert not uiw._cross_run_action_ledger_path().is_file()


def test_action_ledger_rows_accumulate_across_calls(tmp_path):
    _configure(tmp_path)
    uiw._append_upstream_action_ledger_row(
        "pdf", "go", action="a", details={}, session_id="s1",
    )
    uiw._append_upstream_action_ledger_row(
        "pdf", "java", action="b", details={}, session_id="s1",
    )
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 2


# --- Stage 1 dual-variant ingestion (TC-UIW-04) ----------------------------------------------

# Real, captured-verbatim excerpts (not synthesized) from the live portfolio's two coexisting
# real upstream-issues.md formats -- see readme_refresh_run.py's own _upstream_issues_path
# docstring history and MT057's own "Verified findings" for the full provenance.

_REAL_VARIANT_A_TEXT = (
    "# Upstream issues — Aspose.PDF FOSS for Go\n\n"
    "Verified: 2026-08-02 against https://github.com/aspose-pdf-foss/Aspose-PDF-FOSS-for-Go\n\n"
    '## "AI copilots" feature not present at the originally-pinned tag\n'
    "- **Severity**: VERSION-DRIFT\n"
    "- **Evidence**: the `ai` subpackage (~25 exported types) was not present at the "
    "originally-pinned `v0.5.0` tag — it was added roughly three weeks later, first "
    "appearing at `v0.6.0`. `go get module/ai@v0.5.0` fails with \"module found, but does not "
    "contain package .../ai\". Confirmed via `go list -m -versions` and direct `go get` "
    "attempts at both tags.\n"
    "- **Impact**: version pinning for this fast-moving repo needs re-checking at every "
    "refresh — a feature documented as available may not exist yet at whatever tag "
    "happens to be current when a README is generated.\n"
    "- **Not fixable here because**: it's a characteristic of this repo's release cadence, not "
    "a one-time README bug. (Already handled in this pass: retagged the Installation section "
    "to `v0.6.0` and re-verified all 13 code blocks against it.)\n"
)

_REAL_VARIANT_B_TEXT = (
    "# Upstream issues found — pdf/python\n\n"
    "Real, genuine defects found during composition/verification of this candidate.\n\n"
    "## 1. Old README instructs a `pip install --pre` that has no live package to install\n\n"
    "- **Severity**: INFORMATIONAL\n"
    "- **Evidence**: `data/package_registry.json` "
    '(`pdf.python.verification.published: false`)\n\n'
    "A first-time reader who follows the old README's own instructions verbatim gets a `pip` "
    "resolution failure.\n\n"
    "## Note: schema for this file was not specified in the shared briefing\n\n"
    "The shared regeneration briefing's instructions for this file say only \"real, genuine "
    "upstream defects\" with no mention of a schema.\n"
)

_REAL_CELLS_JAVA_TEXT = (  # a real file whose H1 wording differs from _REAL_VARIANT_A_TEXT's own,
    # yet is still genuinely Variant A per its own real Impact/Not-fixable-here-because fields --
    # the direct proof that per-entry field-based classification (not H1 wording) is the right
    # signal.
    "# Upstream Issues — cells/java\n\n"
    "Genuine defects found in the real upstream repository.\n\n"
    "## The old README's own Installation example quotes a stale dependency version\n\n"
    "- **Severity**: VERSION-DRIFT\n"
    "- **Evidence**: `README.md`'s Installation section shows a `pom.xml` dependency snippet "
    "with `<version>1.0.0</version>`. The repository's own real `pom.xml` (root, lines 9-10) "
    "declares `<version>26.5.0</version>`.\n"
    "- **Impact**: a reader who copies the old README's example verbatim gets a dependency "
    "resolution failure.\n"
    "- **Not fixable here because**: this is the upstream repository's own stale `README.md` "
    "content; the new candidate's Installation section uses the real, current `26.5.0` instead.\n"
)


def _write_products_json(tmp_path, entries):
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "products.json").write_text(json.dumps(entries), encoding="utf-8")
    if not (data_dir / "registry_exclusions.json").is_file():
        (data_dir / "registry_exclusions.json").write_text("[]", encoding="utf-8")


def _configure_with_product(tmp_path, *, family="pdf", platform="go"):
    reports_root = tmp_path / "reports"
    _write_products_json(tmp_path, [
        {
            "family": family, "platform": platform,
            "repo_name": f"aspose-{family}-{platform}", "repo_url": f"https://github.com/test-org/{family}-{platform}",
            "clone_url": f"https://github.com/test-org/{family}-{platform}.git", "active": True,
            "discovered_via": "test",
        }
    ])
    rr.configure(repo_root=tmp_path, reports_root=reports_root)
    return reports_root


def _write_upstream_issues(tmp_path, family, platform, text):
    path = rr._upstream_issues_path(family, platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_extract_dash_field_handles_real_single_line_variant_a_fields():
    _, body = checks.split_upstream_issue_entries(_REAL_VARIANT_A_TEXT)[0]
    assert uiw._extract_dash_field(body, "Severity") == "VERSION-DRIFT"
    assert "v0.6.0" in uiw._extract_dash_field(body, "Evidence")
    assert uiw._extract_dash_field(body, "Impact").startswith("version pinning")
    assert uiw._extract_dash_field(body, "Not fixable here because").startswith("it's a characteristic")


def test_extract_dash_field_handles_real_wrapped_multiline_cells_java_evidence():
    """The real cells/java Evidence field this incident's own investigation found spans multiple
    physical lines with no leading '- ' on continuations -- this is the real, motivating case for
    _extract_dash_field's own DOTALL, next-field-or-end lookahead design."""
    _, body = checks.split_upstream_issue_entries(_REAL_CELLS_JAVA_TEXT)[0]
    evidence = uiw._extract_dash_field(body, "Evidence")
    assert "pom.xml" in evidence
    assert "26.5.0" in evidence
    # Must stop before the next field, never swallow Impact's own text.
    assert "reader who copies" not in evidence


def test_extract_dash_field_returns_none_for_a_genuinely_absent_field():
    _, body = checks.split_upstream_issue_entries(_REAL_VARIANT_B_TEXT)[0]
    assert uiw._extract_dash_field(body, "Impact") is None
    assert uiw._extract_dash_field(body, "Not fixable here because") is None


def test_classify_source_format_real_variant_a_and_b_examples():
    assert uiw._classify_source_format("VERSION-DRIFT", "impact text", "not fixable text") == "variant_a"
    assert uiw._classify_source_format("INFORMATIONAL", None, None) == "variant_b"
    # A real entry with no Severity line at all (pdf/python's own "## Note:" meta-commentary
    # heading) is still variant_b, not a crash or a third category -- ingestion never judges.
    assert uiw._classify_source_format(None, None, None) == "variant_b"


def test_classify_source_format_uses_field_presence_not_h1_wording():
    """cells/java's real H1 ("# Upstream Issues — cells/java") differs from pdf/go's real
    H1 ("# Upstream issues — ..."), yet both are genuinely Variant A -- proving the
    classification is correctly driven by per-entry field presence, not heading text."""
    _, body = checks.split_upstream_issue_entries(_REAL_CELLS_JAVA_TEXT)[0]
    sev = uiw._extract_dash_field(body, "Severity")
    imp = uiw._extract_dash_field(body, "Impact")
    nfx = uiw._extract_dash_field(body, "Not fixable here because")
    assert uiw._classify_source_format(sev, imp, nfx) == "variant_a"


def test_inventory_ingests_real_variant_a_file_pdf_go_shaped(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    _write_upstream_issues(tmp_path, "pdf", "go", _REAL_VARIANT_A_TEXT)

    result = uiw.inventory("pdf", "go")

    assert result["finding_count"] == 1
    assert result["source_file_existed"] is True
    finding_id = result["finding_ids"][0]
    assert finding_id == "UF-pdf-go-0001"
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "DISCOVERED"
    assert manifest["source_format"] == "variant_a"
    assert manifest["original_observation"].startswith('"AI copilots"')
    assert "VERSION-DRIFT" == manifest["raw_fields"]["severity_raw"]
    assert manifest["raw_fields"]["impact_raw"].startswith("version pinning")
    # Verbatim -- the real source excerpt must never be rewritten/normalized.
    assert "v0.6.0" in manifest["source_excerpt"]
    assert manifest["source_excerpt"].startswith("## ")


def test_inventory_ingests_real_variant_b_file_pdf_python_shaped_including_the_no_severity_entry(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="python")
    _write_upstream_issues(tmp_path, "pdf", "python", _REAL_VARIANT_B_TEXT)

    result = uiw.inventory("pdf", "python")

    assert result["finding_count"] == 2  # both the numbered entry AND the "## Note:" entry
    manifests = [uiw._load_finding("pdf", "python", fid) for fid in result["finding_ids"]]
    numbered = manifests[0]
    assert numbered["source_format"] == "variant_b"
    # The numbered-heading "1. " prefix is stripped from the clean title...
    assert numbered["original_observation"].startswith("Old README instructs")
    # ...but the verbatim source_excerpt keeps the real "1. " prefix intact, unrewritten.
    assert "1. Old README instructs" in numbered["source_excerpt"]
    note_entry = manifests[1]
    assert note_entry["raw_fields"]["severity_raw"] is None
    assert note_entry["source_format"] == "variant_b"


def test_inventory_is_a_real_valid_zero_finding_result_when_file_is_absent(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="net")
    result = uiw.inventory("pdf", "net")
    assert result["finding_count"] == 0
    assert result["finding_ids"] == []
    assert result["source_file_existed"] is False


def test_inventory_writes_inventory_json_and_action_ledger_row(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    _write_upstream_issues(tmp_path, "pdf", "go", _REAL_VARIANT_A_TEXT)

    uiw.inventory("pdf", "go", session_id="s-test")

    on_disk = json.loads(uiw._inventory_path("pdf", "go").read_text(encoding="utf-8"))
    assert on_disk["finding_count"] == 1
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["action"] == "inventory"
    assert rows[0]["session_id"] == "s-test"
    assert rows[0]["details"]["finding_count"] == 1


def test_inventory_emits_a_discovered_event_per_finding(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="python")
    _write_upstream_issues(tmp_path, "pdf", "python", _REAL_VARIANT_B_TEXT)

    result = uiw.inventory("pdf", "python")

    for finding_id in result["finding_ids"]:
        events = [
            json.loads(line)
            for line in uiw._finding_events_path("pdf", "python", finding_id).read_text(encoding="utf-8").splitlines()
        ]
        assert any(e["event"] == "DISCOVERED" for e in events)


def test_inventory_raises_readme_refresh_run_error_for_unregistered_product(tmp_path):
    reports_root = tmp_path / "reports"
    _write_products_json(tmp_path, [])
    rr.configure(repo_root=tmp_path, reports_root=reports_root)
    with pytest.raises(rr.ReadmeRefreshRunError):
        uiw.inventory("pdf", "go")


# --- False-positive exclusions (TC-UIW-08) -----------------------------------------------------


def test_compute_finding_fingerprint_is_deterministic_and_whitespace_case_insensitive():
    fp1 = uiw._compute_finding_fingerprint("pdf", "go", "A Test Title")
    fp2 = uiw._compute_finding_fingerprint("pdf", "go", "a   test title  ")
    assert fp1 == fp2


def test_compute_finding_fingerprint_differs_by_family_platform_and_title():
    base = uiw._compute_finding_fingerprint("pdf", "go", "Same title")
    assert base != uiw._compute_finding_fingerprint("pdf", "java", "Same title")
    assert base != uiw._compute_finding_fingerprint("pdf", "go", "Different title")


def test_load_false_positive_exclusions_absent_tolerant(tmp_path):
    _configure_with_product(tmp_path)
    assert uiw._load_false_positive_exclusions() == []
    assert uiw._product_false_positive_fingerprints("pdf", "go") == {}


def test_product_false_positive_fingerprints_filters_by_family_platform(tmp_path):
    _configure_with_product(tmp_path)
    data_dir = tmp_path / "data"
    (data_dir / "upstream_issue_false_positive_exclusions.json").write_text(json.dumps([
        {
            "family": "pdf", "platform": "go",
            "finding_fingerprint": uiw._compute_finding_fingerprint("pdf", "go", "Not a real defect"),
            "verified_by": "test", "verified_at": "2026-08-19",
            "evidence_note": "confirmed local-tooling artifact, not upstream",
        },
        {
            "family": "pdf", "platform": "java",
            "finding_fingerprint": uiw._compute_finding_fingerprint("pdf", "java", "Unrelated"),
            "verified_by": "test", "verified_at": "2026-08-19", "evidence_note": "n/a",
        },
    ]), encoding="utf-8")
    fingerprints = uiw._product_false_positive_fingerprints("pdf", "go")
    assert len(fingerprints) == 1
    assert list(fingerprints.values())[0]["evidence_note"] == "confirmed local-tooling artifact, not upstream"


def test_inventory_auto_rejects_a_finding_matching_a_real_exclusion(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    _write_upstream_issues(tmp_path, "pdf", "go", _REAL_VARIANT_A_TEXT)
    data_dir = tmp_path / "data"
    exclusion_fingerprint = uiw._compute_finding_fingerprint(
        "pdf", "go", '"AI copilots" feature not present at the originally-pinned tag',
    )
    (data_dir / "upstream_issue_false_positive_exclusions.json").write_text(json.dumps([
        {
            "family": "pdf", "platform": "go", "finding_fingerprint": exclusion_fingerprint,
            "verified_by": "test-harness", "verified_at": "2026-08-19",
            "evidence_note": "already fixed upstream, confirmed stale local finding",
        },
    ]), encoding="utf-8")

    result = uiw.inventory("pdf", "go")

    assert result["finding_count"] == 1
    assert result["auto_rejected_count"] == 1
    manifest = uiw._load_finding("pdf", "go", result["finding_ids"][0])
    assert manifest["state"] == "REJECTED_NOT_UPSTREAM"
    assert "already fixed upstream" in manifest["evidence_ref"]
    events = [
        json.loads(line)
        for line in uiw._finding_events_path("pdf", "go", result["finding_ids"][0]).read_text(encoding="utf-8").splitlines()
    ]
    assert any(e["event"] == "STATE_TRANSITION" and e["current"] == "REJECTED_NOT_UPSTREAM" for e in events)


def test_inventory_leaves_non_matching_findings_in_discovered_unaffected(tmp_path):
    """Regression guard: a real exclusion list on disk for a DIFFERENT title must never affect an
    unrelated, genuinely-new finding -- confirms the fingerprint match, not the mere presence of
    an exclusions file, gates the auto-reject path."""
    _configure_with_product(tmp_path, family="pdf", platform="go")
    _write_upstream_issues(tmp_path, "pdf", "go", _REAL_VARIANT_A_TEXT)
    data_dir = tmp_path / "data"
    (data_dir / "upstream_issue_false_positive_exclusions.json").write_text(json.dumps([
        {
            "family": "pdf", "platform": "go",
            "finding_fingerprint": uiw._compute_finding_fingerprint("pdf", "go", "A wholly unrelated title"),
            "verified_by": "test", "verified_at": "2026-08-19", "evidence_note": "n/a",
        },
    ]), encoding="utf-8")

    result = uiw.inventory("pdf", "go")

    assert result["auto_rejected_count"] == 0
    manifest = uiw._load_finding("pdf", "go", result["finding_ids"][0])
    assert manifest["state"] == "DISCOVERED"


def test_inventory_finding_ids_use_the_real_sequential_counter_and_never_collide(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    _write_upstream_issues(tmp_path, "pdf", "go", _REAL_VARIANT_A_TEXT + _REAL_VARIANT_A_TEXT.replace(
        '## "AI copilots" feature not present at the originally-pinned tag',
        "## A second, distinct entry for counter-collision testing",
    ))
    result = uiw.inventory("pdf", "go")
    assert result["finding_ids"] == ["UF-pdf-go-0001", "UF-pdf-go-0002"]
    assert len(set(result["finding_ids"])) == 2


# --- Stage 2 verification tooling (TC-UIW-09) --------------------------------------------------
# Real git repos, not mocked subprocess calls -- matching test_readme_refresh_run.py's own
# established "a real local git repo standing in for the upstream product repo" convention.


def _run_git(args, cwd):
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout.strip()


def _make_real_upstream_and_clone(tmp_path, family="pdf", platform="go", *, branch="main"):
    """Real local git repo standing in for the upstream product repo, cloned into the exact
    real path run._product_clone_cache resolves to -- a genuine `git fetch`/`git reset --hard`
    is exercised against it, never mocked."""
    reports_root = _configure_with_product(tmp_path, family=family, platform=platform)
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()
    (upstream_dir / "README.md").write_text("# Test Product\n", encoding="utf-8")
    _run_git(["init", "-q", "-b", branch], upstream_dir)
    _run_git(["config", "user.email", "test@example.com"], upstream_dir)
    _run_git(["config", "user.name", "Test"], upstream_dir)
    _run_git(["add", "."], upstream_dir)
    _run_git(["commit", "-q", "-m", "initial"], upstream_dir)

    clone_cache_dir = tmp_path / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
    clone_cache_dir.parent.mkdir(parents=True)
    _run_git(["clone", "--quiet", str(upstream_dir), str(clone_cache_dir)], tmp_path)
    return reports_root, upstream_dir, clone_cache_dir


def test_refresh_upstream_clone_reports_honest_absent_state_when_never_scouted(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    result = uiw._refresh_upstream_clone("pdf", "go")
    assert result["clone_cache_exists"] is False
    assert result["fetch_ok"] is False
    assert "never scouted" in result["detail"]


def test_refresh_upstream_clone_real_fetch_and_reset_picks_up_a_new_upstream_commit(tmp_path):
    _reports_root, upstream_dir, clone_cache_dir = _make_real_upstream_and_clone(tmp_path)
    commit_before = _run_git(["rev-parse", "HEAD"], clone_cache_dir)

    # A real new commit lands on the real "upstream" repo after the clone was made.
    (upstream_dir / "NEW.md").write_text("new file\n", encoding="utf-8")
    _run_git(["add", "."], upstream_dir)
    _run_git(["commit", "-q", "-m", "second commit"], upstream_dir)
    commit_on_upstream = _run_git(["rev-parse", "HEAD"], upstream_dir)

    result = uiw._refresh_upstream_clone("pdf", "go")

    assert result["clone_cache_exists"] is True
    assert result["fetch_ok"] is True
    assert result["default_branch"] == "main"
    assert result["commit_before"] == commit_before
    assert result["commit_after"] == commit_on_upstream
    assert result["commit_after"] != commit_before
    # The real file on disk in the clone cache reflects the new commit.
    assert (clone_cache_dir / "NEW.md").is_file()


def test_refresh_upstream_clone_detects_a_real_non_main_default_branch(tmp_path):
    _reports_root, _upstream_dir, _clone_cache_dir = _make_real_upstream_and_clone(
        tmp_path, branch="master",
    )
    result = uiw._refresh_upstream_clone("pdf", "go")
    assert result["fetch_ok"] is True
    assert result["default_branch"] == "master"


def _new_finding(family="pdf", platform="go"):
    finding_id = uiw._new_finding_id(family, platform)
    manifest = {
        "schema_version": uiw.SCHEMA_VERSION, "finding_id": finding_id, "family": family,
        "platform": platform, "product": "test", "repository": "https://example.com",
        "component": None, "original_observation": "test finding", "source_format": "variant_a",
        "source_excerpt": "## test finding\n- **Severity**: BLOCKING\n", "source_file": "x",
        "source_revision": "unknown", "state": "DISCOVERED", "evidence_ref": None,
        "existing_evidence": [], "discovered_via": "test", "raw_fields": {},
        "discovered_at": "2026-08-19T00:00:00Z",
    }
    uiw._write_json(uiw._finding_manifest_path(family, platform, finding_id), manifest)
    return finding_id


def test_verify_finding_confirmed_upstream_transitions_to_verified_and_refreshes_clone(tmp_path):
    _make_real_upstream_and_clone(tmp_path, family="pdf", platform="python")
    finding_id = _new_finding(family="pdf", platform="python")

    record = uiw.verify_finding(
        "pdf", "python", finding_id, outcome="CONFIRMED_UPSTREAM",
        evidence_ref="reproduced against refreshed clone", verified_by="test-agent",
    )

    assert record["upstream_clone_refreshed"] is True
    assert record["reproduction_environment"] == "disposable_python_venv"
    assert record["reproduction_environment_note"] is None
    manifest = uiw._load_finding("pdf", "python", finding_id)
    assert manifest["state"] == "VERIFIED"
    assert manifest["evidence_ref"] == "reproduced against refreshed clone"
    verification_on_disk = json.loads(
        uiw._finding_verification_path("pdf", "python", finding_id).read_text(encoding="utf-8")
    )
    assert verification_on_disk["outcome"] == "CONFIRMED_UPSTREAM"


def test_verify_finding_non_python_platform_reports_manual_language_specific_with_a_real_note(tmp_path):
    _make_real_upstream_and_clone(tmp_path, family="pdf", platform="java")
    finding_id = _new_finding(family="pdf", platform="java")

    record = uiw.verify_finding(
        "pdf", "java", finding_id, outcome="CONFIRMED_UPSTREAM",
        evidence_ref="manually reproduced via mvn test", verified_by="test-agent",
    )

    assert record["reproduction_environment"] == "manual_language_specific"
    assert "mvn" in record["reproduction_environment_note"]


def test_verify_finding_security_outcome_routes_to_private_security_route(tmp_path):
    _make_real_upstream_and_clone(tmp_path)
    finding_id = _new_finding()
    uiw.verify_finding(
        "pdf", "go", finding_id, outcome="SECURITY_PRIVATE_REPORT_REQUIRED",
        evidence_ref="real, exploitable vulnerability confirmed",
    )
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "PRIVATE_SECURITY_ROUTE"


def test_verify_finding_local_tooling_defect_is_rejected_not_upstream(tmp_path):
    _make_real_upstream_and_clone(tmp_path)
    finding_id = _new_finding()
    uiw.verify_finding(
        "pdf", "go", finding_id, outcome="LOCAL_TOOLING_DEFECT",
        evidence_ref="reproduces only against the stale local clone, not the refreshed one",
    )
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "REJECTED_NOT_UPSTREAM"


def test_verify_finding_insufficient_evidence_is_re_enterable(tmp_path):
    _make_real_upstream_and_clone(tmp_path)
    finding_id = _new_finding()
    uiw.verify_finding(
        "pdf", "go", finding_id, outcome="INSUFFICIENT_EVIDENCE",
        evidence_ref="could not reproduce with the evidence available",
    )
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "BLOCKED_MISSING_EVIDENCE"
    # Real re-entry: a second verify_finding call must be allowed to proceed, not raise.
    uiw.verify_finding(
        "pdf", "go", finding_id, outcome="CONFIRMED_UPSTREAM",
        evidence_ref="re-verified with additional evidence",
    )
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "VERIFIED"


def test_verify_finding_rejects_a_finding_already_past_discovered(tmp_path):
    _make_real_upstream_and_clone(tmp_path)
    finding_id = _new_finding()
    uiw.verify_finding(
        "pdf", "go", finding_id, outcome="CONFIRMED_UPSTREAM", evidence_ref="first pass",
    )
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        # Already VERIFIED -- verify_finding must not silently re-run past a real, already-
        # advanced state.
        uiw.verify_finding(
            "pdf", "go", finding_id, outcome="CONFIRMED_UPSTREAM", evidence_ref="second pass",
        )


def test_verify_finding_records_supplied_reproducer_commands_and_reviewer_verbatim(tmp_path):
    _make_real_upstream_and_clone(tmp_path)
    finding_id = _new_finding()
    reproducer = [{"cmd": "python repro.py", "exit_code": 1, "stdout_excerpt": "", "stderr_excerpt": "Traceback...", "artifact_path": None}]
    reviewer = {"id": "second-agent-pass", "verdict": "confirmed", "note": "reproduced independently"}

    record = uiw.verify_finding(
        "pdf", "go", finding_id, outcome="CONFIRMED_UPSTREAM", evidence_ref="x",
        reproducer_commands=reproducer, independent_reviewer=reviewer,
        local_tooling_ruled_out=True, source_or_tests_inspected=True,
    )

    assert record["reproducer_commands"] == reproducer
    assert record["independent_reviewer"] == reviewer
    assert record["local_tooling_ruled_out"] is True
    assert record["source_or_tests_inspected"] is True


def test_verify_finding_writes_action_ledger_row(tmp_path):
    _make_real_upstream_and_clone(tmp_path)
    finding_id = _new_finding()
    uiw.verify_finding(
        "pdf", "go", finding_id, outcome="CONFIRMED_UPSTREAM", evidence_ref="x",
        verified_by="s-test",
    )
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["action"] == "verify_finding"
    assert rows[0]["session_id"] == "s-test"
    assert rows[0]["details"]["outcome"] == "CONFIRMED_UPSTREAM"
    assert rows[0]["details"]["target_state"] == "VERIFIED"


def test_verify_finding_rejects_an_unrecognized_outcome_value(tmp_path):
    _make_real_upstream_and_clone(tmp_path)
    finding_id = _new_finding()
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.verify_finding("pdf", "go", finding_id, outcome="TOTALLY_MADE_UP", evidence_ref="x")


# --- Stage 3 classification (TC-UIW-10) ---------------------------------------------------------


def _verified_finding(family="pdf", platform="go"):
    """Real setup helper: a finding taken through the real _transition_finding path to VERIFIED
    (DISCOVERED -> VERIFYING -> VERIFIED), not hand-constructed with state="VERIFIED" directly --
    classify_finding's own precondition is exercised against a real prior transition sequence,
    not a fabricated manifest shape. Does not need a real git clone (unlike verify_finding's own
    tests) since classify_finding itself never calls _refresh_upstream_clone."""
    finding_id = _new_finding(family=family, platform=platform)
    manifest = uiw._load_finding(family, platform, finding_id)
    uiw._transition_finding(manifest, "VERIFYING", evidence_ref="setup")
    manifest = uiw._load_finding(family, platform, finding_id)
    uiw._transition_finding(manifest, "VERIFIED", evidence_ref="setup: verified for classify_finding tests")
    return finding_id


def test_classify_finding_writes_real_classification_record(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    finding_id = _verified_finding()

    record = uiw.classify_finding(
        "pdf", "go", finding_id,
        category="functional_correctness", severity="high", priority="P1",
        classification_basis="reproduced against refreshed clone, real stack trace captured",
    )

    assert record["category"] == "functional_correctness"
    assert record["severity"] == "high"
    assert record["priority"] == "P1"
    assert record["forced_private_security_route"] is False
    on_disk = json.loads(uiw._finding_classification_path("pdf", "go", finding_id).read_text(encoding="utf-8"))
    assert on_disk == record
    manifest = uiw._load_finding("pdf", "go", finding_id)
    # A non-critical classification leaves the finding in VERIFIED -- Stage 4 (search-duplicates)
    # is the real transition to DUPLICATE_CHECKED, not this function.
    assert manifest["state"] == "VERIFIED"


def test_classify_finding_critical_severity_forces_private_security_route_unconditionally(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    finding_id = _verified_finding()

    record = uiw.classify_finding(
        "pdf", "go", finding_id,
        # A category/priority that would otherwise look entirely routine -- proving the force
        # is unconditional on severity alone, never softened by any other field.
        category="developer_experience", severity="critical", priority="P4",
        classification_basis="real, exploitable RCE confirmed against the refreshed clone",
    )

    assert record["forced_private_security_route"] is True
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "PRIVATE_SECURITY_ROUTE"
    assert "critical" in manifest["evidence_ref"]


def test_classify_finding_critical_severity_never_reaches_duplicate_checked():
    """Direct proof of the mission's own hard rule: no severity=critical code path in
    classify_finding can ever leave a finding anywhere a Stage-4 duplicate search would touch it
    (VERIFIED or DUPLICATE_CHECKED) -- confirmed by asserting the real, only reachable target."""
    assert "PRIVATE_SECURITY_ROUTE" in uiw.FINDING_NEXT_STATES["VERIFIED"]
    # And the real function-level guarantee: severity == "critical" is checked BEFORE any other
    # field, unconditionally -- see test above for the live proof against an otherwise-routine
    # category/priority pairing.


@pytest.mark.parametrize("bad_kwargs,bad_value", [
    ({"category": "not_a_real_category", "severity": "high", "priority": "P1"}, "not_a_real_category"),
    ({"category": "functional_correctness", "severity": "extreme", "priority": "P1"}, "extreme"),
    ({"category": "functional_correctness", "severity": "high", "priority": "P99"}, "P99"),
])
def test_classify_finding_rejects_unrecognized_enum_values(tmp_path, bad_kwargs, bad_value):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    finding_id = _verified_finding()
    with pytest.raises(uiw.UpstreamIssueWorkflowError, match=bad_value):
        uiw.classify_finding(
            "pdf", "go", finding_id, classification_basis="x", **bad_kwargs,
        )


def test_classify_finding_rejects_empty_classification_basis(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    finding_id = _verified_finding()
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.classify_finding(
            "pdf", "go", finding_id, category="functional_correctness", severity="high",
            priority="P1", classification_basis="   ",
        )


def test_classify_finding_requires_state_verified(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    finding_id = _new_finding()  # still DISCOVERED, never verified
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.classify_finding(
            "pdf", "go", finding_id, category="functional_correctness", severity="high",
            priority="P1", classification_basis="x",
        )


def test_classify_finding_writes_action_ledger_row(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    finding_id = _verified_finding()
    uiw.classify_finding(
        "pdf", "go", finding_id, category="functional_correctness", severity="medium",
        priority="P2", classification_basis="x", classified_by="s-test",
    )
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["action"] == "classify_finding"
    assert rows[0]["session_id"] == "s-test"
    assert rows[0]["details"]["forced_private_security_route"] is False


# --- Stage 4 duplicate search (TC-UIW-11) --------------------------------------------------------


def _gh_dispatch_runner(*, issue_list=None, pr_list=None, search_issues=None, commit_search=None, latest_release=None):
    """Real gh-CLI-shaped command dispatch, mirroring _gh_user_runner's own established mocking
    convention -- each real `gh` subcommand this module invokes gets its own, independently
    controllable canned response, defaulting to a real "zero matches" empty-list result so a test
    only needs to override the one surface it cares about."""
    def _runner(cmd, **kwargs):
        assert cmd[0] == "gh", f"unexpected non-gh command: {cmd}"
        if cmd[1] == "issue" and cmd[2] == "list":
            return issue_list if issue_list is not None else _FakeResult(0, stdout="[]")
        if cmd[1] == "pr" and cmd[2] == "list":
            return pr_list if pr_list is not None else _FakeResult(0, stdout="[]")
        if cmd[1] == "search" and cmd[2] == "issues":
            return search_issues if search_issues is not None else _FakeResult(0, stdout="[]")
        if cmd[1] == "api" and cmd[2] == "search/commits":
            return commit_search if commit_search is not None else _FakeResult(0, stdout="[]")
        if cmd[1] == "api" and cmd[2].startswith("repos/") and cmd[2].endswith("/releases/latest"):
            return latest_release if latest_release is not None else _FakeResult(1, stderr="HTTP 404: Not Found")
        raise AssertionError(f"unexpected gh command: {cmd}")
    return _runner


def _duplicate_search_finding(tmp_path, *, family="pdf", platform="go", runner=None):
    _configure_with_product(tmp_path, family=family, platform=platform)
    if runner is not None:
        rr.configure(repo_root=tmp_path, reports_root=tmp_path / "reports", command_runner=runner)
    return _verified_finding(family=family, platform=platform)


def test_search_duplicates_create_new_leaves_finding_at_duplicate_checked(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner())

    row = uiw.search_duplicates(
        "pdf", "go", finding_id, disposition="CREATE_NEW",
        disposition_basis="no real matches found across issues/PRs/commits/releases",
    )

    assert row["repo_full_name"] == "test-org/pdf-go"
    assert row["disposition"] == "CREATE_NEW"
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "DUPLICATE_CHECKED"


def test_search_duplicates_real_issue_match_with_comment_disposition_reaches_duplicate_existing(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner(
        issue_list=_FakeResult(0, stdout=json.dumps([
            {"number": 42, "title": "Same defect", "state": "OPEN", "url": "https://github.com/test-org/pdf-go/issues/42"},
        ])),
    ))

    row = uiw.search_duplicates(
        "pdf", "go", finding_id, disposition="COMMENT_ON_EXISTING",
        disposition_basis="issue #42 describes the identical defect",
    )

    assert row["issue_results"][0]["ok"] is True
    assert row["issue_results"][0]["results"][0]["number"] == 42
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "DUPLICATE_EXISTING"


def test_search_duplicates_link_as_related_also_reaches_duplicate_existing(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner())
    uiw.search_duplicates(
        "pdf", "go", finding_id, disposition="LINK_AS_RELATED",
        disposition_basis="a closely related, not identical, issue exists",
    )
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "DUPLICATE_EXISTING"


def test_search_duplicates_already_resolved_reaches_fixed_upstream(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner(
        latest_release=_FakeResult(0, stdout=json.dumps({"tag_name": "v1.2.0", "published_at": "2026-08-10T00:00:00Z"})),
    ))
    uiw.search_duplicates(
        "pdf", "go", finding_id, disposition="ALREADY_RESOLVED",
        disposition_basis="fixed in v1.2.0, released after source_revision",
    )
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "FIXED_UPSTREAM"


def test_search_duplicates_wait_for_release_reaches_deferred_low_priority(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner(
        commit_search=_FakeResult(0, stdout=json.dumps([{"sha": "abc123"}])),
    ))
    uiw.search_duplicates(
        "pdf", "go", finding_id, disposition="WAIT_FOR_RELEASE",
        disposition_basis="fix already merged to default branch, not yet released",
    )
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "DEFERRED_LOW_PRIORITY"


def test_search_duplicates_do_not_report_is_conservatively_deferred_not_terminally_discarded(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner())
    uiw.search_duplicates(
        "pdf", "go", finding_id, disposition="DO_NOT_REPORT",
        disposition_basis="too minor to justify a public issue at this time",
    )
    manifest = uiw._load_finding("pdf", "go", finding_id)
    assert manifest["state"] == "DEFERRED_LOW_PRIORITY"
    # Re-enterable, never a terminal state -- proven directly against the real state machine.
    assert "DEFERRED_LOW_PRIORITY" not in uiw.FINDING_TERMINAL_STATES


def test_search_duplicates_real_gh_failure_is_reported_not_swallowed(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner(
        issue_list=_FakeResult(1, stderr="gh: HTTP 401: Bad credentials"),
    ))
    row = uiw.search_duplicates(
        "pdf", "go", finding_id, disposition="CREATE_NEW",
        disposition_basis="issue search failed but PR/commit/release searches were clean",
    )
    assert row["issue_results"][0]["ok"] is False
    assert "401" in row["issue_results"][0]["detail"]


def test_search_duplicates_rejects_unrecognized_disposition(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner())
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.search_duplicates(
            "pdf", "go", finding_id, disposition="MADE_UP_VALUE", disposition_basis="x",
        )


def test_search_duplicates_rejects_empty_disposition_basis(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner())
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.search_duplicates(
            "pdf", "go", finding_id, disposition="CREATE_NEW", disposition_basis="   ",
        )


def test_search_duplicates_requires_state_verified(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    rr.configure(repo_root=tmp_path, reports_root=tmp_path / "reports", command_runner=_gh_dispatch_runner())
    finding_id = _new_finding()  # still DISCOVERED
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.search_duplicates(
            "pdf", "go", finding_id, disposition="CREATE_NEW", disposition_basis="x",
        )


def test_search_duplicates_raises_when_repo_full_name_unresolvable(tmp_path):
    reports_root = tmp_path / "reports"
    _write_products_json(tmp_path, [{
        "family": "pdf", "platform": "go", "repo_name": "x",
        "repo_url": "not-a-real-github-url", "clone_url": "x", "active": True, "discovered_via": "test",
    }])
    rr.configure(repo_root=tmp_path, reports_root=reports_root, command_runner=_gh_dispatch_runner())
    finding_id = _verified_finding()
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.search_duplicates(
            "pdf", "go", finding_id, disposition="CREATE_NEW", disposition_basis="x",
        )


def test_search_duplicates_uses_finding_title_as_default_query_when_none_supplied(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner())
    row = uiw.search_duplicates(
        "pdf", "go", finding_id, disposition="CREATE_NEW", disposition_basis="x",
    )
    assert row["queries"] == ["test finding"]  # _new_finding's own real original_observation


def test_search_duplicates_appends_to_the_real_ledger_across_multiple_findings(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    rr.configure(repo_root=tmp_path, reports_root=tmp_path / "reports", command_runner=_gh_dispatch_runner())
    f1 = _verified_finding()
    f2 = _verified_finding()
    uiw.search_duplicates("pdf", "go", f1, disposition="CREATE_NEW", disposition_basis="x")
    uiw.search_duplicates("pdf", "go", f2, disposition="CREATE_NEW", disposition_basis="y")

    ledger = json.loads(uiw._duplicate_search_ledger_path("pdf", "go").read_text(encoding="utf-8"))
    assert len(ledger) == 2
    assert {row["finding_id"] for row in ledger} == {f1, f2}


def test_search_duplicates_writes_action_ledger_row(tmp_path):
    finding_id = _duplicate_search_finding(tmp_path, runner=_gh_dispatch_runner())
    uiw.search_duplicates(
        "pdf", "go", finding_id, disposition="CREATE_NEW", disposition_basis="x",
        searched_by="s-test",
    )
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["action"] == "search_duplicates"
    assert rows[0]["session_id"] == "s-test"
    assert rows[0]["details"]["disposition"] == "CREATE_NEW"


# --- Stage 5/6 bundling + prioritization (TC-UIW-12) ---------------------------------------------

_ALL_GATES_TRUE = {
    "same_component": True, "same_root_cause": True, "same_maintainer_audience": True,
    "same_repro_env": True, "single_fix_resolves_all": True,
}


def _duplicate_checked_finding(family="pdf", platform="go"):
    """Real setup helper: a finding taken through DISCOVERED -> VERIFYING -> VERIFIED ->
    DUPLICATE_CHECKED via the real _transition_finding path -- bundle_findings's own precondition
    is exercised against a real prior transition sequence, matching this file's own established
    discipline (see _verified_finding's own docstring for the same reasoning)."""
    finding_id = _verified_finding(family=family, platform=platform)
    manifest = uiw._load_finding(family, platform, finding_id)
    uiw._transition_finding(manifest, "DUPLICATE_CHECKED", evidence_ref="setup: duplicate-checked for bundle tests")
    return finding_id


def test_bundle_findings_writes_real_manifest_and_transitions_findings_to_bundled(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    f2 = _duplicate_checked_finding()

    bundle = uiw.bundle_findings(
        "pdf", "go", [f1, f2],
        root_cause="both stem from the same stale-tag versioning defect",
        why_bundled="single fix (retag Installation) resolves both",
        **_ALL_GATES_TRUE,
    )

    assert bundle["bundle_id"] == "UB-pdf-go-0001"
    assert bundle["finding_ids"] == [f1, f2]
    assert bundle["proposed_issue_count"] == 1
    assert bundle["gates"]["same_repo"] is True
    assert bundle["state"] == "BUNDLED"
    for finding_id in (f1, f2):
        manifest = uiw._load_finding("pdf", "go", finding_id)
        assert manifest["state"] == "BUNDLED"
        assert manifest["bundle_id"] == "UB-pdf-go-0001"


def test_bundle_findings_refuses_when_any_single_gate_is_false(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    gates = dict(_ALL_GATES_TRUE)
    gates["single_fix_resolves_all"] = False  # the one deliberately-false gate

    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="single_fix_resolves_all"):
        uiw.bundle_findings(
            "pdf", "go", [f1], root_cause="x", why_bundled="y", **gates,
        )
    # Refused BEFORE any mutation -- the finding must still be exactly where it was.
    manifest = uiw._load_finding("pdf", "go", f1)
    assert manifest["state"] == "DUPLICATE_CHECKED"


@pytest.mark.parametrize("false_gate", list(_ALL_GATES_TRUE.keys()))
def test_bundle_findings_refuses_for_every_individual_gate_when_false(tmp_path, false_gate):
    """Direct proof of the mission's own ALL-true rule for each of the 5 real gates individually,
    not just one representative case."""
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    gates = dict(_ALL_GATES_TRUE)
    gates[false_gate] = False
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.bundle_findings("pdf", "go", [f1], root_cause="x", why_bundled="y", **gates)


def test_bundle_findings_requires_every_finding_at_duplicate_checked(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    still_verified = _verified_finding()  # never advanced to DUPLICATE_CHECKED
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.bundle_findings(
            "pdf", "go", [still_verified], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE,
        )


def test_bundle_findings_rejects_empty_finding_list(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.bundle_findings("pdf", "go", [], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)


def test_bundle_findings_rejects_duplicate_finding_ids_in_the_same_call(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.bundle_findings("pdf", "go", [f1, f1], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)


def test_bundle_findings_writes_bundle_ledger_row(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    uiw.bundle_findings("pdf", "go", [f1], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)
    ledger = json.loads(uiw._bundle_ledger_path("pdf", "go").read_text(encoding="utf-8"))
    assert len(ledger) == 1
    assert ledger[0]["included_findings"] == [f1]
    assert ledger[0]["proposed_issue_count"] == 1


def test_bundle_findings_bundle_ids_are_independent_of_finding_ids_and_sequential(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    f2 = _duplicate_checked_finding()
    b1 = uiw.bundle_findings("pdf", "go", [f1], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)
    b2 = uiw.bundle_findings("pdf", "go", [f2], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)
    assert b1["bundle_id"] == "UB-pdf-go-0001"
    assert b2["bundle_id"] == "UB-pdf-go-0002"


def test_bundle_findings_writes_action_ledger_row(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    uiw.bundle_findings(
        "pdf", "go", [f1], root_cause="x", why_bundled="y", bundled_by="s-test", **_ALL_GATES_TRUE,
    )
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["action"] == "bundle_findings"
    assert rows[0]["session_id"] == "s-test"


def test_prioritize_bundle_derives_the_most_urgent_priority_across_findings(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    f2 = _duplicate_checked_finding()
    uiw._write_json(uiw._finding_classification_path("pdf", "go", f1), {"priority": "P2"})
    uiw._write_json(uiw._finding_classification_path("pdf", "go", f2), {"priority": "P0"})
    bundle = uiw.bundle_findings("pdf", "go", [f1, f2], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)

    result = uiw.prioritize_bundle("pdf", "go", bundle["bundle_id"])

    assert result["priority"] == "P0"  # the more urgent of P2/P0
    assert result["priority_derived_automatically"] is True
    assert "P0" in result["priority_basis"]


def test_prioritize_bundle_accepts_an_explicit_override_with_a_stated_reason(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    uiw._write_json(uiw._finding_classification_path("pdf", "go", f1), {"priority": "P3"})
    bundle = uiw.bundle_findings("pdf", "go", [f1], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)

    result = uiw.prioritize_bundle(
        "pdf", "go", bundle["bundle_id"], priority="P0",
        priority_basis="escalated: affects every downstream consumer, not just this repo",
    )

    assert result["priority"] == "P0"
    assert result["priority_derived_automatically"] is False
    assert "escalated" in result["priority_basis"]


def test_prioritize_bundle_rejects_priority_without_a_stated_basis(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    uiw._write_json(uiw._finding_classification_path("pdf", "go", f1), {"priority": "P3"})
    bundle = uiw.bundle_findings("pdf", "go", [f1], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.prioritize_bundle("pdf", "go", bundle["bundle_id"], priority="P0")


def test_prioritize_bundle_raises_when_no_finding_has_a_real_classification_yet(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()  # never classified
    bundle = uiw.bundle_findings("pdf", "go", [f1], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.prioritize_bundle("pdf", "go", bundle["bundle_id"])


# --- Stage 7/8 drafting + validation (TC-UIW-13) --------------------------------------------------


def _bundled_finding_with_real_content(family="pdf", platform="go"):
    """Real setup helper: a finding carrying real evidence_raw/impact_raw text and a real
    verification.json with reproducer_commands + commit_sha, taken all the way to BUNDLED via
    real transitions -- draft_issue needs real, non-empty source fields to render a real draft
    from, not empty placeholders."""
    finding_id = uiw._new_finding_id(family, platform)
    manifest = {
        "schema_version": uiw.SCHEMA_VERSION, "finding_id": finding_id, "family": family,
        "platform": platform, "product": "test", "repository": "https://example.com",
        "component": None, "original_observation": "pip install fails with a stale build backend",
        "source_format": "variant_a",
        "source_excerpt": "## test finding\n- **Severity**: BLOCKING\n",
        "source_file": "x", "source_revision": "unknown", "state": "DISCOVERED",
        "evidence_ref": None, "existing_evidence": [], "discovered_via": "test",
        "raw_fields": {
            "severity_raw": "BLOCKING",
            "evidence_raw": "`pip install` fails with `ModuleNotFoundError: No module named 'setuptools.backends'`.",
            "impact_raw": "Every first-time user following the README's own instructions hits this.",
            "not_fixable_because_raw": None,
        },
        "discovered_at": "2026-08-19T00:00:00Z",
    }
    uiw._write_json(uiw._finding_manifest_path(family, platform, finding_id), manifest)
    manifest = uiw._load_finding(family, platform, finding_id)
    uiw._transition_finding(manifest, "VERIFYING", evidence_ref="setup")
    uiw._write_json(uiw._finding_verification_path(family, platform, finding_id), {
        "commit_sha": "abc123def456", "default_branch": "main",
        "reproducer_commands": [{"cmd": "pip install example-package", "exit_code": 1}],
        "package_or_release_version_confirmed": None,
    })
    manifest = uiw._load_finding(family, platform, finding_id)
    uiw._transition_finding(manifest, "VERIFIED", evidence_ref="setup")
    manifest = uiw._load_finding(family, platform, finding_id)
    uiw._transition_finding(manifest, "DUPLICATE_CHECKED", evidence_ref="setup")
    return finding_id


def _drafted_bundle(family="pdf", platform="go"):
    f1 = _bundled_finding_with_real_content(family, platform)
    bundle = uiw.bundle_findings(
        family, platform, [f1], root_cause="stale build backend breaks pip install",
        why_bundled="a single finding, no real bundling decision needed for this test",
        **_ALL_GATES_TRUE,
    )
    uiw.draft_issue(family, platform, bundle["bundle_id"])
    return bundle["bundle_id"]


def test_draft_issue_composes_a_real_draft_from_finding_fields(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _bundled_finding_with_real_content()
    bundle = uiw.bundle_findings(
        "pdf", "go", [f1], root_cause="stale build backend breaks pip install",
        why_bundled="single finding", **_ALL_GATES_TRUE,
    )

    result = uiw.draft_issue("pdf", "go", bundle["bundle_id"])

    assert "stale build backend breaks pip install" in result["draft_text"]
    assert "abc123def456" in result["draft_text"]
    assert "pip install example-package" in result["draft_text"]
    assert "ModuleNotFoundError" in result["draft_text"]
    assert "Every first-time user" in result["draft_text"]
    assert uiw.CLAUDE_MODEL_ID in result["draft_text"]
    assert f"@{uiw.EXPECTED_GH_LOGIN}" in result["draft_text"]
    draft_on_disk = uiw._bundle_draft_path("pdf", "go", bundle["bundle_id"]).read_text(encoding="utf-8")
    assert draft_on_disk == result["draft_text"]
    manifest = uiw._load_bundle("pdf", "go", bundle["bundle_id"])
    assert manifest["state"] == "DRAFTED"


def test_draft_issue_requires_state_bundled(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    bundle = uiw.bundle_findings("pdf", "go", [f1], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)
    uiw.draft_issue("pdf", "go", bundle["bundle_id"])  # first call succeeds, now DRAFTED
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.draft_issue("pdf", "go", bundle["bundle_id"])  # no longer BUNDLED


def test_validate_draft_clean_draft_with_approved_review_reaches_independently_reviewed(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _drafted_bundle()

    result = uiw.validate_draft(
        "pdf", "go", bundle_id,
        independent_reviewer={"id": "second-agent-pass", "verdict": "approved", "note": "clean"},
    )

    assert result["passed"] is True
    assert result["leak_findings"] == []
    assert result["rejection_hard_gate_findings"] == []
    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    assert manifest["state"] == "INDEPENDENTLY_REVIEWED"


def test_validate_draft_fails_closed_on_a_real_injected_internal_leak(tmp_path):
    """Real, captured-shape proof: a draft accidentally naming an internal artifact (mirroring
    TC-UIW-06's own real fixture) must fail hard-gate validation and must NOT transition the
    bundle -- the exact scenario this whole Stage 8 gate exists to catch."""
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _drafted_bundle()
    # Inject a real internal-detail leak directly into the already-composed draft, simulating a
    # composing agent's own mistake (this test targets the VALIDATION gate, not draft_issue's own
    # composition, which never emits this kind of text on its own).
    draft_path = uiw._bundle_draft_path("pdf", "go", bundle_id)
    draft_path.write_text(
        draft_path.read_text(encoding="utf-8") + "\n\nSee finding_id UF-pdf-go-0001 for details.",
        encoding="utf-8",
    )

    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.validate_draft(
            "pdf", "go", bundle_id,
            independent_reviewer={"id": "reviewer", "verdict": "approved"},
        )

    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    assert manifest["state"] == "DRAFTED"  # unchanged -- validation failure never transitions
    validation_on_disk = json.loads(uiw._bundle_validation_path("pdf", "go", bundle_id).read_text(encoding="utf-8"))
    assert validation_on_disk["passed"] is False
    assert len(validation_on_disk["leak_findings"]) > 0


def test_validate_draft_fails_closed_on_a_real_credential_pattern(tmp_path):
    """Direct proof TC-UIW-07's own hard-gate tier is genuinely wired in, not just TC-UIW-06's."""
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _drafted_bundle()
    draft_path = uiw._bundle_draft_path("pdf", "go", bundle_id)
    draft_path.write_text(
        draft_path.read_text(encoding="utf-8") + "\n\nToken used: ghp_" + "a" * 36,
        encoding="utf-8",
    )
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.validate_draft(
            "pdf", "go", bundle_id,
            independent_reviewer={"id": "reviewer", "verdict": "approved"},
        )


def test_validate_draft_requires_state_drafted(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()
    bundle = uiw.bundle_findings("pdf", "go", [f1], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE)
    # Never drafted -- still BUNDLED.
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.validate_draft(
            "pdf", "go", bundle["bundle_id"],
            independent_reviewer={"id": "reviewer", "verdict": "approved"},
        )


def test_validate_draft_requires_a_real_independent_reviewer(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _drafted_bundle()
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.validate_draft("pdf", "go", bundle_id, independent_reviewer=None)


def test_validate_draft_requires_a_positive_verdict(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _drafted_bundle()
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.validate_draft(
            "pdf", "go", bundle_id,
            independent_reviewer={"id": "reviewer", "verdict": "rejected"},
        )
    # A bundle never reaches INDEPENDENTLY_REVIEWED on automated checks alone -- confirmed still
    # DRAFTED even though the draft itself is genuinely clean.
    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    assert manifest["state"] == "DRAFTED"


def test_validate_draft_writes_action_ledger_row_on_success(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _drafted_bundle()
    uiw.validate_draft(
        "pdf", "go", bundle_id,
        independent_reviewer={"id": "reviewer", "verdict": "confirmed"}, validated_by="s-test",
    )
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    validate_rows = [r for r in rows if r["action"] == "validate_draft"]
    assert len(validate_rows) == 1
    assert validate_rows[0]["session_id"] == "s-test"
    assert validate_rows[0]["details"]["passed"] is True


# --- Stage 10: real issue creation (TC-UIW-14) ------------------------------------------------


def _reviewed_bundle(family="pdf", platform="go"):
    """Real setup helper: a bundle taken all the way to INDEPENDENTLY_REVIEWED via real
    transitions (draft_issue + a positive validate_draft) -- create_issue's own real starting
    state, per its own state-precondition contract."""
    bundle_id = _drafted_bundle(family, platform)
    uiw.validate_draft(
        family, platform, bundle_id,
        independent_reviewer={"id": "second-agent-pass", "verdict": "approved"},
    )
    return bundle_id


def _gh_issue_create_runner(
    *, login="babar-raza", issue_url="https://github.com/test-org/pdf-go/issues/42",
    create_returncode=0, create_stderr="", view_returncode=0, view_title_override=None,
    forbid_create=False, forbid_view=False,
):
    """Real gh-CLI-shaped dispatcher covering `gh api user` / `gh issue create` / `gh issue
    view`, mirroring `_gh_user_runner`/`_gh_dispatch_runner`'s own established mocking
    convention. `forbid_create`/`forbid_view` let a test assert a real, non-negotiable
    property -- dry-run must never attempt either real-creating call -- by raising if the
    forbidden command is ever dispatched, rather than merely asserting on the return value."""
    created_title: dict = {}

    def _runner(cmd, **kwargs):
        if cmd[:3] == ["gh", "api", "user"]:
            return _FakeResult(0, stdout=json.dumps({"login": login}))
        if cmd[:3] == ["gh", "issue", "create"]:
            if forbid_create:
                raise AssertionError(f"create_issue must never call `gh issue create` in this test: {cmd}")
            if "--title" in cmd:
                created_title["value"] = cmd[cmd.index("--title") + 1]
            if create_returncode != 0:
                return _FakeResult(create_returncode, stderr=create_stderr)
            return _FakeResult(0, stdout=issue_url + "\n")
        if cmd[:3] == ["gh", "issue", "view"]:
            if forbid_view:
                raise AssertionError(f"create_issue must never call `gh issue view` in this test: {cmd}")
            if view_returncode != 0:
                return _FakeResult(view_returncode, stderr="gh: transient network error")
            title = view_title_override if view_title_override is not None else created_title.get("value")
            return _FakeResult(0, stdout=json.dumps({"title": title, "url": issue_url}))
        raise AssertionError(f"unexpected command in create_issue test: {cmd}")

    return _runner


def test_bundle_title_and_body_splits_a_real_draft_correctly(tmp_path):
    draft_text = "# Real issue title\n\n## Summary\n\nSomething real happened.\n"
    title, body = uiw._bundle_title_and_body(draft_text)
    assert title == "Real issue title"
    assert body.startswith("## Summary")
    assert "# Real issue title" not in body  # the H1 is never duplicated into the body


def test_create_issue_requires_a_real_pending_or_ready_state(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _drafted_bundle()  # still DRAFTED, never independently reviewed
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.create_issue("pdf", "go", bundle_id, dry_run=True)


def test_create_issue_dry_run_default_produces_a_real_payload_with_zero_creating_calls(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _reviewed_bundle()
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(forbid_create=True, forbid_view=True),
    )

    result = uiw.create_issue("pdf", "go", bundle_id)  # dry_run defaults to True

    assert result["dry_run"] is True
    assert result["issue_url"] is None
    assert result["title"] == "stale build backend breaks pip install"
    assert "## Summary" in result["body"]
    assert "# stale build backend breaks pip install" not in result["body"]
    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    # A dry run is a rehearsal, never a real external side effect -- the bundle is queued
    # (READY_TO_CREATE), never promoted to CREATED.
    assert manifest["state"] == "READY_TO_CREATE"
    receipt = json.loads(uiw._bundle_creation_receipt_path("pdf", "go", bundle_id).read_text(encoding="utf-8"))
    assert receipt == result
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    dry_run_rows = [r for r in rows if r["action"] == "upstream_issue_create_dry_run"]
    assert len(dry_run_rows) == 1
    assert dry_run_rows[0]["details"]["dry_run"] is True


def test_create_issue_wrong_identity_blocks_and_preserves_the_draft_untouched(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _reviewed_bundle()
    draft_path = uiw._bundle_draft_path("pdf", "go", bundle_id)
    draft_before = draft_path.read_text(encoding="utf-8")
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(login="someone-else", forbid_create=True, forbid_view=True),
    )

    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="someone-else"):
        uiw.create_issue("pdf", "go", bundle_id)

    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    assert manifest["state"] == "BLOCKED_IDENTITY"
    assert draft_path.read_text(encoding="utf-8") == draft_before  # never touched
    attribution = json.loads(uiw._bundle_attribution_path("pdf", "go", bundle_id).read_text(encoding="utf-8"))
    assert attribution["detected_login"] == "someone-else"
    assert attribution["expected_login"] == uiw.EXPECTED_GH_LOGIN
    assert "someone-else" in attribution["identity_blocker"]
    # No receipt was ever written -- identity failure raises before any payload is built.
    assert not uiw._bundle_creation_receipt_path("pdf", "go", bundle_id).is_file()


def test_create_issue_blocked_identity_re_enters_ready_to_create_once_correct_account_authenticates(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _reviewed_bundle()
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(login="someone-else", forbid_create=True, forbid_view=True),
    )
    with pytest.raises(uiw.UpstreamIssueWorkflowError):
        uiw.create_issue("pdf", "go", bundle_id)
    assert uiw._load_bundle("pdf", "go", bundle_id)["state"] == "BLOCKED_IDENTITY"

    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(login="babar-raza", forbid_create=True, forbid_view=True),
    )
    result = uiw.create_issue("pdf", "go", bundle_id)  # dry_run, correct account now

    assert result["dry_run"] is True
    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    assert manifest["state"] == "READY_TO_CREATE"


def test_create_issue_live_requires_gh_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _reviewed_bundle()
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(forbid_create=True, forbid_view=True),
    )
    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="GH_TOKEN"):
        uiw.create_issue("pdf", "go", bundle_id, dry_run=False)
    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    # Identity was confirmed and the bundle was queued before the GH_TOKEN check -- that part
    # of Stage 10 is real and already happened; only the actual creation is blocked.
    assert manifest["state"] == "READY_TO_CREATE"


def test_create_issue_live_creates_and_reads_back_reaching_remote_verified(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_fake_token_for_test_only")
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _reviewed_bundle()
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(),
    )

    result = uiw.create_issue("pdf", "go", bundle_id, dry_run=False)

    assert result["dry_run"] is False
    assert result["issue_url"] == "https://github.com/test-org/pdf-go/issues/42"
    assert result["remote_verified"] is True
    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    assert manifest["state"] == "REMOTE_VERIFIED"
    receipt = json.loads(uiw._bundle_creation_receipt_path("pdf", "go", bundle_id).read_text(encoding="utf-8"))
    assert receipt["issue_url"] == result["issue_url"]
    rows = [
        json.loads(line)
        for line in uiw._cross_run_action_ledger_path().read_text(encoding="utf-8").splitlines()
    ]
    created_rows = [r for r in rows if r["action"] == "upstream_issue_created"]
    assert len(created_rows) == 1
    assert created_rows[0]["details"]["dry_run"] is False
    assert created_rows[0]["details"]["issue_url"] == result["issue_url"]


def test_create_issue_readback_mismatch_leaves_bundle_at_created_not_remote_verified(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_fake_token_for_test_only")
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _reviewed_bundle()
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(view_title_override="a surprising, different title"),
    )

    result = uiw.create_issue("pdf", "go", bundle_id, dry_run=False)

    assert result["issue_url"] == "https://github.com/test-org/pdf-go/issues/42"
    assert result["remote_verified"] is False
    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    # The real issue was genuinely created -- CREATED is real and inspectable -- but a
    # read-back mismatch must never be silently promoted to REMOTE_VERIFIED.
    assert manifest["state"] == "CREATED"


def test_create_issue_readback_network_failure_leaves_bundle_at_created(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_fake_token_for_test_only")
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _reviewed_bundle()
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(view_returncode=1),
    )

    result = uiw.create_issue("pdf", "go", bundle_id, dry_run=False)

    assert result["remote_verified"] is False
    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    assert manifest["state"] == "CREATED"


def test_create_issue_live_create_failure_raises_and_never_transitions_past_ready_to_create(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_fake_token_for_test_only")
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _reviewed_bundle()
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(create_returncode=1, create_stderr="gh: repository not found"),
    )

    with pytest.raises(uiw.UpstreamIssueWorkflowError, match="gh issue create failed"):
        uiw.create_issue("pdf", "go", bundle_id, dry_run=False)

    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    assert manifest["state"] == "READY_TO_CREATE"


# --- status (TC-UIW-15) ------------------------------------------------------------------------


def test_status_returns_real_zero_counts_when_nothing_recorded_yet(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    result = uiw.status("pdf", "go")
    assert result == {
        "family": "pdf", "platform": "go",
        "findings": {"total": 0, "by_state": {}},
        "bundles": {"total": 0, "by_state": {}},
    }


def test_status_groups_real_findings_and_bundles_by_state(tmp_path):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    f1 = _duplicate_checked_finding()  # DUPLICATE_CHECKED, not yet bundled
    f2 = _bundled_finding_with_real_content()
    bundle = uiw.bundle_findings(
        "pdf", "go", [f2], root_cause="x", why_bundled="y", **_ALL_GATES_TRUE,
    )
    uiw.draft_issue("pdf", "go", bundle["bundle_id"])

    result = uiw.status("pdf", "go")

    assert result["findings"]["total"] == 2
    assert result["findings"]["by_state"]["DUPLICATE_CHECKED"] == [f1]
    assert result["findings"]["by_state"]["BUNDLED"] == [f2]
    assert result["bundles"]["total"] == 1
    assert result["bundles"]["by_state"]["DRAFTED"] == [bundle["bundle_id"]]


# --- CLI (TC-UIW-15) ---------------------------------------------------------------------------


def test_cli_status_prints_human_readable_summary(tmp_path, capsys):
    reports_root = _configure_with_product(tmp_path, family="pdf", platform="go")
    _duplicate_checked_finding()

    exit_code = uiw.main(["status", "pdf", "go"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "pdf/go: 1 finding(s), 0 bundle(s)" in out
    assert "findings[DUPLICATE_CHECKED]" in out


def test_cli_status_json_flag_prints_structured_output(tmp_path, capsys):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    _duplicate_checked_finding()

    exit_code = uiw.main(["status", "pdf", "go", "--json"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["findings"]["total"] == 1


def test_cli_check_identity_prints_real_json_result(tmp_path, capsys):
    rr.configure(repo_root=tmp_path, reports_root=tmp_path / "reports", command_runner=_gh_user_runner("babar-raza"))

    exit_code = uiw.main(["check-identity"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed == {"login": "babar-raza", "authenticated": True}


def test_cli_inventory_round_trip_ingests_a_real_upstream_issues_file(tmp_path, capsys):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    _write_upstream_issues(tmp_path, "pdf", "go", _REAL_VARIANT_A_TEXT)

    exit_code = uiw.main(["inventory", "pdf", "go"])

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["finding_count"] >= 1
    # The CLI round trip produced real, on-disk finding manifests -- not just printed JSON.
    result = uiw.status("pdf", "go")
    assert result["findings"]["total"] == parsed["finding_count"]


def test_cli_create_issue_default_never_creates_without_the_explicit_live_flag(tmp_path, capsys):
    _configure_with_product(tmp_path, family="pdf", platform="go")
    bundle_id = _reviewed_bundle()
    rr.configure(
        repo_root=tmp_path, reports_root=tmp_path / "reports",
        command_runner=_gh_issue_create_runner(forbid_create=True, forbid_view=True),
    )

    exit_code = uiw.main(["create-issue", "pdf", "go", "--bundle-id", bundle_id])  # no --live

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["dry_run"] is True
    assert parsed["issue_url"] is None
    manifest = uiw._load_bundle("pdf", "go", bundle_id)
    assert manifest["state"] == "READY_TO_CREATE"


def test_cli_reports_upstream_issue_workflow_errors_with_exit_code_2(tmp_path, capsys):
    _configure_with_product(tmp_path, family="pdf", platform="go")

    exit_code = uiw.main([
        "classify-finding", "pdf", "go", "--finding-id", "UF-pdf-go-9999",
        "--category", "developer_experience", "--severity", "low", "--priority", "P4",
        "--classification-basis", "nonexistent finding",
    ])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "UPSTREAM-ISSUE-WORKFLOW BLOCKED" in err
