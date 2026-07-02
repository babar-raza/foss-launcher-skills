"""Tests for localization_incident.py — S-109 stateful incident orchestration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import localization_incident


@pytest.fixture(autouse=True)
def _isolate_repo(tmp_path):
    localization_incident.configure(repo_root=tmp_path)
    (tmp_path / "docs" / "registries").mkdir(parents=True)
    (tmp_path / "docs" / "registries" / "skills.md").write_text(
        "| Skill | ID | Purpose |\n"
        "| translate-page | S-52 | Translate page |\n"
        "| translate-batch | S-53 | Translate batch |\n"
        "| pipeline-harden | S-99 | Harden pipeline |\n",
        encoding="utf-8",
    )
    for slug in ("translate-page", "translate-batch", "pipeline-harden"):
        (tmp_path / "skills").mkdir(exist_ok=True)
        (tmp_path / "skills" / f"{slug}.md").write_text("# skill\n", encoding="utf-8")
    yield
    localization_incident.configure()


def _request(tmp_path: Path, **overrides) -> Path:
    data = {
        "incident_id": "pli-001",
        "incident_title": "Production localization incident",
        "detected_at": "2026-06-29T00:00:00Z",
        "reported_urls": ["https://products.aspose.org/pdf/net/"],
        "suspected_sites": ["products.aspose.org"],
        "suspected_families": ["pdf"],
        "suspected_platforms": ["net"],
        "suspected_locales": ["fr"],
        "incident_types": ["PARTIAL_TRANSLATION"],
        "source_repository": str(tmp_path),
        "source_revision": "abc123",
        "production_revision": None,
        "known_bad_changes": [],
        "known_good_revision": None,
        "live_verification_required": True,
        "CDN_verification_required": True,
        "human_review_required": True,
        "containment_mode": "GATE_UNVERIFIED_LOCALIZED_PAGES",
        "execution_mode": "INVESTIGATION_ONLY",
        "allowed_paths": ["reports/**", ".local/evidences/**"],
        "forbidden_paths": ["content/**"],
        "evidence_root": ".local/evidences/production-localization-incident-pli-001",
        "rollback_required": True,
        "terminal_closeout_required": True,
    }
    data.update(overrides)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _gap_report(tmp_path: Path) -> Path:
    path = tmp_path / "reports" / "skill-gaps" / "gap.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "production localization incident with live-site evidence, deployment, CDN, S-52, S-53, S-99",
        encoding="utf-8",
    )
    return path


def test_start_initializes_state_evidence_taskcards_and_result(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    source = tmp_path / "content" / "products.aspose.org" / "en" / "pdf" / "net"
    source.mkdir(parents=True)
    (source / "_index.md").write_text("---\ntitle: PDF .NET\n---\n", encoding="utf-8")

    code = localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)])

    assert code == 0
    evidence_root = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001"
    state = json.loads((evidence_root / "state.json").read_text(encoding="utf-8"))
    result = json.loads((evidence_root / "result.json").read_text(encoding="utf-8"))
    assert state["status"] == "TRIAGED"
    assert len(state["taskcards"]) == len(localization_incident.INITIAL_TASK_TYPES)
    assert result["continuation_allowed"] is True
    assert result["affected_pages"][0]["locale"] == "fr"


def test_missing_locale_identity_fails_closed(tmp_path):
    request = _request(tmp_path, suspected_locales=[])
    gap = _gap_report(tmp_path)

    code = localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)])

    assert code == 2


def test_duplicate_incident_requires_resume(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0

    code = localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)])

    assert code == 2


def test_controlled_production_requires_authority_and_rollback(tmp_path):
    request = _request(
        tmp_path,
        execution_mode="CONTROLLED_PRODUCTION_REPAIR",
        production_revision=None,
        known_good_revision=None,
    )
    gap = _gap_report(tmp_path)

    code = localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)])

    assert code == 2
    state = json.loads(
        (tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["status"] == "BLOCKED_AUTHORITY"


def test_closeout_rejects_report_only_closure(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"

    code = localization_incident.main(["close", "--state", str(state)])

    assert code == 2


def test_status_prints_existing_state(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"

    assert localization_incident.main(["status", "--state", str(state)]) == 0


def test_execute_triage_closes_first_task_and_unlocks_containment(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"

    assert localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "triage"]) == 0

    root = state.parent / "taskcards"
    triage = json.loads((root / "pli-001-TC-01.json").read_text(encoding="utf-8"))
    containment = json.loads((root / "pli-001-TC-02.json").read_text(encoding="utf-8"))
    assert triage["status"] == "CLOSED"
    assert containment["current_state"] == "READY"


def test_scope_detects_missing_locale_file_and_writes_segment_findings(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    source = tmp_path / "content" / "products.aspose.org" / "en" / "pdf" / "net"
    source.mkdir(parents=True)
    (source / "_index.md").write_text("---\ntitle: PDF\n---\nEnglish body paragraph for translation.\n", encoding="utf-8")
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"

    assert localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "scope"]) == 0

    findings = json.loads((tmp_path / "reports" / "localization" / "pli-001" / "segment-findings.json").read_text(encoding="utf-8"))
    assert findings[0]["issue_type"] == "MISSING_SEGMENT"


def test_review_packets_block_on_required_human_review(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    source = tmp_path / "content" / "products.aspose.org" / "en" / "pdf" / "net"
    source.mkdir(parents=True)
    (source / "_index.md").write_text("---\ntitle: PDF\n---\nEnglish body paragraph for translation.\n", encoding="utf-8")
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"
    assert localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "scope"]) == 0

    code = localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "review-packets"])

    assert code == 1
    packets = list((tmp_path / "reports" / "localization" / "pli-001" / "review-packets").glob("*.md"))
    assert packets


def test_blocker_challenge_reclassifies_agent_owned_review(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"
    state_data = json.loads(state.read_text(encoding="utf-8"))
    state_data["findings"] = ["human language review not recorded"]
    state.write_text(json.dumps(state_data), encoding="utf-8")

    code = localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "blocker-challenge"])

    assert code == 1
    updated = json.loads(state.read_text(encoding="utf-8"))
    artifact = json.loads((tmp_path / "reports" / "localization" / "pli-001" / "blocker-challenge.json").read_text(encoding="utf-8"))
    assert "human language review not recorded" not in updated["findings"]
    assert artifact["blocker_challenges"][0]["challenge_result"] == "OVERTURNED_AGENT_OWNED"


def test_affected_ledger_writes_canonical_yaml_and_page_taskcard(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    source = tmp_path / "content" / "products.aspose.org" / "en" / "pdf" / "net"
    source.mkdir(parents=True)
    (source / "_index.md").write_text("---\ntitle: PDF\n---\nEnglish body paragraph for translation.\n", encoding="utf-8")
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"
    assert localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "scope"]) == 0

    code = localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "affected-ledger"])

    assert code == 0
    assert (tmp_path / "reports" / "localization" / "affected-localized-pages.yaml").exists()
    validation = json.loads((tmp_path / "reports" / "localization" / "pli-001" / "affected-page-ledger-validation.json").read_text(encoding="utf-8"))
    page_tasks = list((state.parent / "taskcards" / "pages").glob("*.json"))
    assert validation["verdict"] == "AFFECTED_PAGE_LEDGER_COMPLETE_AND_EXECUTABLE"
    assert page_tasks


def test_agent_review_resolves_human_review_blocker(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    source = tmp_path / "content" / "products.aspose.org" / "en" / "pdf" / "net"
    source.mkdir(parents=True)
    (source / "_index.md").write_text("---\ntitle: PDF\n---\nEnglish body paragraph for translation.\n", encoding="utf-8")
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"
    assert localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "scope"]) == 0
    state_data = json.loads(state.read_text(encoding="utf-8"))
    state_data["findings"] = ["human language review not recorded"]
    state.write_text(json.dumps(state_data), encoding="utf-8")

    code = localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "agent-review"])

    assert code == 0
    updated = json.loads(state.read_text(encoding="utf-8"))
    review = json.loads((tmp_path / "reports" / "localization" / "pli-001" / "agent-review.json").read_text(encoding="utf-8"))
    assert "human language review not recorded" not in updated["findings"]
    assert review["repair_required_count"] == 1


def test_monitor_scan_fails_when_material_findings_exist(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    source = tmp_path / "content" / "products.aspose.org" / "en" / "pdf" / "net"
    source.mkdir(parents=True)
    (source / "_index.md").write_text("---\ntitle: PDF\n---\nEnglish body paragraph for translation.\n", encoding="utf-8")
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"
    assert localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "scope"]) == 0

    code = localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "monitor-scan"])

    assert code == 1
    monitor = json.loads((tmp_path / "reports" / "localization" / "pli-001" / "monitor-scan.json").read_text(encoding="utf-8"))
    assert monitor["verdict"] == "MONITOR_SCAN_FAIL_FINDINGS_PRESENT"


def test_containment_records_external_blocker(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"

    code = localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "containment"])

    assert code == 1
    artifact = json.loads((tmp_path / "reports" / "localization" / "pli-001" / "containment.json").read_text(encoding="utf-8"))
    assert artifact["containment_status"] == "BLOCKED_EXTERNAL"


def test_live_verify_uses_fetcher_and_blocks_on_cdn_requirement(tmp_path, monkeypatch):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"
    monkeypatch.setattr(
        localization_incident,
        "fetch_url",
        lambda url: {"url": url, "status": 200, "ok": True, "content_sha256": "abc"},
    )

    code = localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "live-verify"])

    assert code == 1
    artifact = json.loads((tmp_path / "reports" / "localization" / "pli-001" / "live-verify.json").read_text(encoding="utf-8"))
    assert artifact["snapshots"][0]["ok"] is True
    assert "CDN_BLOCKED" in artifact["verdict"]


def test_idempotency_second_run_ignores_volatile_state_timestamp(tmp_path):
    request = _request(tmp_path)
    gap = _gap_report(tmp_path)
    source = tmp_path / "content" / "products.aspose.org" / "en" / "pdf" / "net"
    source.mkdir(parents=True)
    (source / "_index.md").write_text("---\ntitle: PDF\n---\nEnglish body paragraph for translation.\n", encoding="utf-8")
    assert localization_incident.main(["start", "--request", str(request), "--gap-report", str(gap)]) == 0
    state = tmp_path / ".local" / "evidences" / "production-localization-incident-pli-001" / "state.json"
    assert localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "scope"]) == 0
    assert localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "idempotency"]) == 0

    code = localization_incident.main(["execute", "--state", str(state), "--request", str(request), "--phase", "idempotency"])

    assert code == 0
    artifact = json.loads((tmp_path / "reports" / "localization" / "pli-001" / "idempotency.json").read_text(encoding="utf-8"))
    assert artifact["idempotent"] is True
