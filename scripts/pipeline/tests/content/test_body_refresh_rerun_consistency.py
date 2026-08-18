"""HARDEN-A6: rerun-consistency harness for body_refresh's PARAGRAPH_REWRITE.

Pre-existing tests (test_body_refresh.py's RPR-E-01 guards) already reach the
LLM branch for single runs; what was missing — and what this file adds — is the
RERUN dimension: cache-hit reuse, cache invalidation, forced-fresh variance
bounded by the no-downgrade oracle, and never-cache-fallback. Driven through
the real _paragraph_rewrite path with a call-counting fake router:

  Case A — cache enabled: run twice on identical input; the second run makes
           ZERO LLM calls and writes byte-identical content.
  Case B — forced fresh with a wording-varying fake (simulating legitimate
           provider nondeterminism): outputs may differ in text, but both must
           pass no_downgrade_guard.compare_content with no DECISION_BLOCK —
           grade/structural non-regression is the consistency contract, not
           text equality.
"""
from __future__ import annotations

import json
import hashlib
import shutil
import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import commands.content.body_refresh as br  # noqa: E402

_FIXTURES_DIR = _PIPELINE_DIR / "tests" / "fixtures"


@pytest.fixture(autouse=True)
def reset_config():
    # RPR-ST082-01: default every test to a permissive api_fact_summary_fn stub
    # so tests exercising _paragraph_rewrite's LLM branch for fixture-only
    # symbols (not present in this repo's real knowledge/ data) still reach
    # the LLM call they're actually testing, rather than short-circuiting to
    # NO_GROUNDING_AVAILABLE.
    br.configure(api_fact_summary_fn=lambda symbol, family, platform: f"`{symbol}` (class): stub grounding fact for tests")
    yield
    br.configure(
        reports_root="reports/refresh_review",
        receipts_root=None,
        llm_router_class=None,
        safe_write_fn=None,
        hash_validation=True,
        forbidden_claims=None,
    )


class _FakeResult:
    def __init__(self, text):
        self.data = text
        self.provider = "fake"
        self.model = "fake-model-1"


class _CountingRouter:
    """Class-level counter — body_refresh instantiates the class per call."""
    calls = 0
    vary_output = False

    def call_chat(self, prompt_system, prompt_user, **kwargs):
        cls = type(self)
        cls.calls += 1
        if cls.vary_output:
            return _FakeResult(
                f"This section covers loading documents (wording variant {cls.calls}). "
                f"Use the current API surface for conversions."
            )
        return _FakeResult(
            "This section covers loading documents with the current API surface. "
            "Use the documented members for conversions."
        )


_PAGE_BODY = (
    "---\ntitle: Test\nauto_updatable: true\n---\n\n"
    "## overview\n\n"
    "Use the library to load documents. The legacy notes here describe "
    "OldBehavior in detail and should be refreshed for accuracy.\n"
)


def _setup(tmp_path: Path, *, family="pdf", platform="net"):
    page = tmp_path / f"content/docs.aspose.org/en/{family}/{platform}/page.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(_PAGE_BODY, encoding="utf-8")

    change = {
        "change_id": "CHG-100",
        "change_type": "BEHAVIOR_CHANGED",
        "symbol": "OldBehavior",
        "symbol_kind": "class",
        "public_impact": "USER_VISIBLE",
        "content_impact": "BODY_UPDATE",
        "confidence": 0.95,
        "family": family,
        "platform": platform,
        "base_sha": "abc",
        "current_sha": "def",
        "evidence_paths": [],
    }
    impact = {
        "impact_id": "IMP-0100",
        "page_path": str(page),
        "locale": "en",
        "semantic_change_ids": ["CHG-100"],
        "affected_sections": [{
            "section_id": "overview",
            "heading": "## overview",
            "lines": [5, 8],
            "reason": "test",
            "impact_level": "DEFINITE",
            "required_action": "BODY_UPDATE",
            "update_type": br.UT_REWRITE,
        }],
        "planner_signal": False,
    }
    reports = tmp_path / "reports" / family / platform
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "body_impact.json").write_text(json.dumps([impact]), encoding="utf-8")
    (reports / "semantic_changes.json").write_text(json.dumps([change]), encoding="utf-8")
    br.configure(
        reports_root=str(tmp_path / "reports"),
        receipts_root=str(reports / "receipts"),
        hash_validation=False,
        llm_router_class=_CountingRouter,
    )
    return page


def _execute(
    tmp_path: Path,
    family: str,
    platform: str,
    run_tag: str,
    **kwargs,
):
    """Exercise mutation through a distinct run while sharing the LLM cache."""
    run_root = tmp_path / "run-artifacts" / run_tag
    run_root.mkdir(parents=True, exist_ok=True)
    impact_path = (
        Path(br._cfg_reports_root) / family / platform / "body_impact.json"
    )
    impacts = json.loads(impact_path.read_text(encoding="utf-8"))
    paths = [item["page_path"] for item in impacts]
    scope_path = run_root / "scope.json"
    scope_path.write_text(
        json.dumps(
            {
                "run_id": f"TEST-{run_tag}",
                "family": family,
                "platform": platform,
                "paths": paths,
            }
        ),
        encoding="utf-8",
    )
    logical = json.dumps(
        {"paths": sorted(paths), "input_digest": None},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": f"TEST-{run_tag}",
                "family": family,
                "platform": platform,
                "created_at": "2026-07-26T00:00:00Z",
                "scope": {
                    "paths": paths,
                    "input_digest": None,
                    "digest": "sha256:" + hashlib.sha256(logical).hexdigest(),
                },
                "output_digests": {
                    "scope": "sha256:" + hashlib.sha256(
                        scope_path.read_bytes()
                    ).hexdigest()
                },
            }
        ),
        encoding="utf-8",
    )
    return br.run(
        family,
        platform,
        execute=True,
        run_id=f"TEST-{run_tag}",
        run_root=run_root,
        **kwargs,
    )


def test_case_a_cache_enabled_second_run_zero_calls_byte_identical(tmp_path):
    _CountingRouter.calls = 0
    _CountingRouter.vary_output = False
    page = _setup(tmp_path)

    writes: list[str] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append(c) or True)

    receipts1 = _execute(tmp_path, "pdf", "net", "cache-first")
    assert _CountingRouter.calls == 1, "first run must make one real LLM call"
    assert len(writes) == 1
    first_output = writes[0]
    assert receipts1[0]["fallback_reason"] == "NONE"

    # Reset the page to its original content — identical input, second run
    page.write_text(_PAGE_BODY, encoding="utf-8")
    receipts2 = _execute(tmp_path, "pdf", "net", "cache-second")
    assert _CountingRouter.calls == 1, "second identical run must be served from cache"
    assert len(writes) == 2
    assert writes[1] == first_output, "cache hit must be byte-identical"
    assert receipts2[0]["fallback_reason"] == "NONE"


def test_case_a_changed_input_misses_cache(tmp_path):
    _CountingRouter.calls = 0
    _CountingRouter.vary_output = False
    page = _setup(tmp_path)
    br.configure(safe_write_fn=lambda p, c, **kw: True)

    _execute(tmp_path, "pdf", "net", "changed-first")
    assert _CountingRouter.calls == 1

    # Different section text -> different prompt -> different key -> real call
    page.write_text(_PAGE_BODY.replace("in detail", "at length"), encoding="utf-8")
    _execute(tmp_path, "pdf", "net", "changed-second")
    assert _CountingRouter.calls == 2


def test_case_b_forced_fresh_varies_but_never_regresses(tmp_path):
    """Forced-fresh reruns simulate provider nondeterminism: wording may vary,
    but both candidates must clear the no-downgrade oracle (no DECISION_BLOCK,
    no structural regression) against the original page."""
    _CountingRouter.calls = 0
    _CountingRouter.vary_output = True
    # Use the 'fake' family so no_downgrade_guard grades against the committed
    # test knowledge fixtures (same pattern as test_project_phase_store.py).
    page = _setup(tmp_path, family="fake", platform="python")

    writes: list[str] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append(c) or True)

    receipts1 = _execute(
        tmp_path, "fake", "python", "fresh-first", force_llm_regen=True
    )
    page.write_text(_PAGE_BODY, encoding="utf-8")
    receipts2 = _execute(
        tmp_path, "fake", "python", "fresh-second", force_llm_regen=True
    )

    assert _CountingRouter.calls == 2, "forced fresh must call the LLM every run"
    assert len(writes) == 2
    assert writes[0] != writes[1], "varying fake proves genuinely fresh outputs"

    # Oracle: grade/structural non-regression via the existing guard
    import no_downgrade_guard
    from commands.knowledge import knowledge_core

    knowledge_root = tmp_path / "knowledge"
    merged = knowledge_root / "fake" / "python" / "merged"
    merged.mkdir(parents=True)
    for fname in ("fake_api_surface.json", "fake_model.yaml", "fake_claims.json",
                  "fake_formats.json", "fake_index.json"):
        shutil.copy(_FIXTURES_DIR / fname, merged / fname.replace("fake_", ""))
    (merged / "install.md").write_text("pip install aspose-fake-foss\n", encoding="utf-8")

    original_root = knowledge_core._KNOWLEDGE_ROOT
    knowledge_core._KNOWLEDGE_ROOT = knowledge_root
    try:
        for candidate in writes:
            result = no_downgrade_guard.compare_content(
                page, candidate, family="fake", platform="python",
            )
            assert result["decision"] != no_downgrade_guard.DECISION_BLOCK, (
                f"forced-fresh candidate regressed: {result}"
            )
    finally:
        knowledge_core._KNOWLEDGE_ROOT = original_root


def test_forbidden_scan_failure_marks_receipt_unverified(tmp_path):
    """HARDEN-A7: a scan that raises internally fails open for the run but the
    receipt carries scan_ok=false and the run-level helper flags it."""
    _CountingRouter.calls = 0
    _CountingRouter.vary_output = False
    _setup(tmp_path)
    # Truthy non-iterable forbidden config -> newly_introduced raises inside
    # the scan -> caught -> (violations=[], scan_ok=False, error=...)
    br.configure(forbidden_claims=42,
                 safe_write_fn=lambda p, c, **kw: True)

    receipts = _execute(tmp_path, "pdf", "net", "scan-failure")
    updated = [r for r in receipts if r.get("verdict") == br.VD_UPDATED]
    assert updated, f"expected a written page, got {receipts}"
    scan = updated[0].get("forbidden_claims_scan")
    assert scan is not None and scan["ok"] is False and scan["error"]
    assert br.run_has_unverified_forbidden_claims_scans(receipts) is True


def test_forbidden_scan_ok_on_normal_run(tmp_path):
    _CountingRouter.calls = 0
    _CountingRouter.vary_output = False
    _setup(tmp_path)
    br.configure(safe_write_fn=lambda p, c, **kw: True)

    receipts = _execute(tmp_path, "pdf", "net", "scan-normal")
    updated = [r for r in receipts if r.get("verdict") == br.VD_UPDATED]
    assert updated
    assert updated[0]["forbidden_claims_scan"] == {"ok": True, "error": ""}
    assert br.run_has_unverified_forbidden_claims_scans(receipts) is False


def test_unverified_helper_flags_old_shape_written_receipts():
    """R5: a BODY_UPDATED receipt with NO scan record (pre-A7 shape or a field
    regression) reads as unverifiable, never as clean."""
    assert br.run_has_unverified_forbidden_claims_scans(
        [{"verdict": br.VD_UPDATED}]) is True
    assert br.run_has_unverified_forbidden_claims_scans(
        [{"verdict": br.VD_SKIPPED_DRY}]) is False
    assert br.run_has_unverified_forbidden_claims_scans(
        [{"verdict": br.VD_UPDATED,
          "forbidden_claims_scan": {"ok": True, "error": ""}}]) is False


def test_find_unverified_forbidden_claims_receipts_on_disk(tmp_path):
    """HARDEN-A7/finding-1: the ON-DISK variant (reads reports/refresh_review/
    {family}/{platform}/receipts/*.yaml directly) that launch_gate.py's L-03
    gate and readiness_scorecard.py's verdict both now call, replacing two
    separate untested re-implementations of the same scan."""
    import yaml as _yaml

    receipts_dir = tmp_path / "reports" / "refresh_review" / "pdf" / "net" / "receipts"
    receipts_dir.mkdir(parents=True)

    # 1. scan_ok explicitly False -> flagged
    (receipts_dir / "unverified.yaml").write_text(
        _yaml.safe_dump({"verdict": br.VD_UPDATED,
                         "forbidden_claims_scan": {"ok": False, "error": "boom"}}),
        encoding="utf-8",
    )
    # 2. BODY_UPDATED with no scan record at all (pre-A7 shape) -> flagged
    (receipts_dir / "old_shape.yaml").write_text(
        _yaml.safe_dump({"verdict": br.VD_UPDATED}), encoding="utf-8",
    )
    # 3. clean, verified receipt -> NOT flagged
    (receipts_dir / "clean.yaml").write_text(
        _yaml.safe_dump({"verdict": br.VD_UPDATED,
                         "forbidden_claims_scan": {"ok": True, "error": ""}}),
        encoding="utf-8",
    )
    # 4. skipped page (no write happened) with no scan record -> NOT flagged
    (receipts_dir / "skipped.yaml").write_text(
        _yaml.safe_dump({"verdict": br.VD_SKIPPED_DRY}), encoding="utf-8",
    )
    # 5. unreadable/corrupt YAML -> flagged as unreadable, never silently skipped
    (receipts_dir / "corrupt.yaml").write_text("{not: valid: yaml: [", encoding="utf-8")

    unverified = br.find_unverified_forbidden_claims_receipts(
        "pdf", "net", repo_root=tmp_path)

    names = {u.split(" ")[0] for u in unverified}
    assert "unverified.yaml" in names
    assert "old_shape.yaml" in names
    assert "corrupt.yaml" in names
    assert "clean.yaml" not in names
    assert "skipped.yaml" not in names
    assert len(unverified) == 3


def test_find_unverified_forbidden_claims_receipts_no_receipts_dir(tmp_path):
    """No receipts directory at all (product never refreshed) -> empty, not an error."""
    assert br.find_unverified_forbidden_claims_receipts(
        "words", "net", repo_root=tmp_path) == []


def test_cache_never_stores_fallback_output(tmp_path):
    """A router failure falls back to the deterministic template — that output
    must NOT be cached as if it were an LLM rewrite."""

    class _FailingRouter:
        calls = 0

        def call_chat(self, *a, **k):
            type(self).calls += 1
            raise RuntimeError("provider down")

    _FailingRouter.calls = 0
    page = _setup(tmp_path)
    br.configure(llm_router_class=_FailingRouter,
                 safe_write_fn=lambda p, c, **kw: True)

    receipts1 = _execute(tmp_path, "pdf", "net", "fallback")
    assert _FailingRouter.calls == 1
    assert receipts1[0]["fallback_reason"] == "LLM_ERROR"

    # cache dir must contain no entries (only possibly the namespace dir)
    cache_dir = tmp_path / "reports" / "pdf" / "net" / "llm_cache" / "body_refresh"
    entries = list(cache_dir.rglob("*.json")) if cache_dir.exists() else []
    entries = [e for e in entries if e.name != "_model_marker.json"]
    assert entries == [], f"fallback output must never be cached: {entries}"
