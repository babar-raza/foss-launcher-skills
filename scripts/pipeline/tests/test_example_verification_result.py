"""Tests for lib/example_verification/result.py (rollout step C2): schema
round-trip and legacy-adapter equality vs. the exact dict shapes S-120's
own test suite (test_readme_refresh_run.py) and smoke_test.py assert."""
from __future__ import annotations

import pytest

from lib.example_verification.result import (
    BlockIdentity,
    BlockResult,
    VerificationReport,
)


def _identity(index: int, sha: str = "a" * 64) -> BlockIdentity:
    return BlockIdentity(code_sha256=sha, lang="python", index=index, start_line=1, end_line=3)


def test_block_result_rejects_invalid_status():
    with pytest.raises(ValueError):
        BlockResult(identity=_identity(0), status="NOT-A-REAL-STATUS")


def test_block_result_blocked_requires_valid_reason():
    with pytest.raises(ValueError):
        BlockResult(identity=_identity(0), status="BLOCKED-WITH-REASON", reason="NOT-A-REAL-REASON")


def test_block_result_blocked_with_valid_reason_constructs():
    r = BlockResult(identity=_identity(0), status="BLOCKED-WITH-REASON", reason="TOOLCHAIN-UNAVAILABLE")
    assert r.reason == "TOOLCHAIN-UNAVAILABLE"


def test_is_cacheable_true_for_pass():
    r = BlockResult(identity=_identity(0), status="PASS", proof_tier=3)
    assert r.is_cacheable() is True


def test_is_cacheable_true_for_deterministic_failure():
    r = BlockResult(identity=_identity(0), status="BLOCKED-WITH-REASON", reason="SYNTAX-ERROR")
    assert r.is_cacheable() is True


def test_is_cacheable_false_for_toolchain_unavailable():
    # A missing toolchain is a machine-dependent condition, not a
    # deterministic property of the code -- must never be cached.
    r = BlockResult(identity=_identity(0), status="BLOCKED-WITH-REASON", reason="TOOLCHAIN-UNAVAILABLE")
    assert r.is_cacheable() is False


def test_is_cacheable_false_for_timeout():
    r = BlockResult(identity=_identity(0), status="BLOCKED-WITH-REASON", reason="TIMEOUT")
    assert r.is_cacheable() is False


def test_real_s120_reasons_are_all_valid():
    # These 9 are S-120's actual reason literals, confirmed by grepping
    # readme_refresh_run.py directly -- a prior draft of REASONS
    # substituted NO-CLONE-CACHE/BUDGET-EXHAUSTED (package additions, not
    # S-120 originals) for two of these by mistake.
    for reason in (
        "TOOLCHAIN-UNAVAILABLE", "RUNTIME-ERROR", "UPSTREAM-BROKEN",
        "TYPE-CHECK-FAILED", "DEPENDS-ON-FAILED-BLOCK", "ACQUIRE-FAILED",
        "TIMEOUT", "FIXTURE-UNAVAILABLE", "NOT-A-PRODUCT-COMMAND",
    ):
        BlockResult(identity=_identity(0), status="BLOCKED-WITH-REASON", reason=reason)


def test_is_cacheable_true_for_not_a_product_command():
    # A property of the block's own content (is this a real product
    # command or not) -- deterministic, safe to cache.
    r = BlockResult(identity=_identity(0), status="BLOCKED-WITH-REASON", reason="NOT-A-PRODUCT-COMMAND")
    assert r.is_cacheable() is True


def test_is_cacheable_false_for_fixture_unavailable():
    # A property of the acquire-time workspace, not the block's content --
    # must never outlive the transient staging problem that caused it.
    r = BlockResult(identity=_identity(0), status="BLOCKED-WITH-REASON", reason="FIXTURE-UNAVAILABLE")
    assert r.is_cacheable() is False


def test_to_legacy_s120_clean_execution_matches_fixture_dict():
    # Mirrors test_readme_refresh_run.py::test_run_single_python_block_clean_execution
    report = VerificationReport(runner="python", blocks=[
        BlockResult(identity=_identity(0), status="PASS", proof_tier=3),
    ])
    legacy = report.to_legacy_s120()
    assert legacy["blocks"][0] == {"index": 0, "status": "COMPILED+RAN CLEAN"}


def test_to_legacy_s120_blocked_matches_fixture_dict():
    # Mirrors test_readme_refresh_run.py::test_run_single_python_block_runtime_error_captured
    report = VerificationReport(runner="python", blocks=[
        BlockResult(identity=_identity(1), status="BLOCKED-WITH-REASON",
                    reason="RUNTIME-ERROR", detail="boom, real traceback"),
    ])
    legacy = report.to_legacy_s120()
    assert legacy["blocks"][0] == {
        "index": 1, "status": "BLOCKED-WITH-REASON",
        "reason": "RUNTIME-ERROR", "detail": "boom, real traceback",
    }


def test_to_legacy_s120_build_verified_only_pass_keeps_its_real_reason():
    # Real bug found live via TC-13 (MT072-2026-09-23-EXAMPLE-VERIFICATION-
    # PRODUCTIONIZATION): a genuine tier-2 PASS (e.g. CppRunner's disclosed
    # BUILD-VERIFIED-ONLY ceiling) used to fall through to the generic
    # non-BLOCKED-WITH-REASON default below and get the FALSE reason
    # "TOOLCHAIN-UNAVAILABLE" -- wrong, since the toolchain plainly exists
    # and just compiled the real library cleanly.
    report = VerificationReport(runner="cpp", blocks=[
        BlockResult(identity=_identity(0), status="PASS", proof_tier=2, reason="BUILD-VERIFIED-ONLY"),
    ])
    legacy = report.to_legacy_s120()
    assert legacy["blocks"][0] == {
        "index": 0, "status": "BLOCKED-WITH-REASON",
        "reason": "BUILD-VERIFIED-ONLY", "detail": "",
    }


def test_to_legacy_s120_bare_tier2_pass_defaults_to_build_verified_only():
    # Same fix, defensive default: a PASS with no reason set at all (e.g. a
    # future runner that forgets to attach one) still never gets the false
    # TOOLCHAIN-UNAVAILABLE label.
    report = VerificationReport(runner="cpp", blocks=[
        BlockResult(identity=_identity(0), status="PASS", proof_tier=2),
    ])
    legacy = report.to_legacy_s120()
    assert legacy["blocks"][0]["reason"] == "BUILD-VERIFIED-ONLY"


def test_to_legacy_s120_stub_block_gets_toolchain_unavailable():
    # A tier-0/1 result with no execution proof degrades to the legacy
    # stub's own default reason, matching every existing stub-runner block.
    report = VerificationReport(runner="stub", blocks=[
        BlockResult(identity=_identity(0), status="NOT-VERIFIED", proof_tier=0),
    ])
    legacy = report.to_legacy_s120()
    assert legacy["blocks"][0]["status"] == "BLOCKED-WITH-REASON"
    assert legacy["blocks"][0]["reason"] == "TOOLCHAIN-UNAVAILABLE"


def test_to_legacy_s120_all_named_and_blocks_found():
    report = VerificationReport(runner="stub", blocks=[
        BlockResult(identity=_identity(0), status="PASS", proof_tier=3),
        BlockResult(identity=_identity(1), status="BLOCKED-WITH-REASON", reason="TOOLCHAIN-UNAVAILABLE"),
    ])
    legacy = report.to_legacy_s120()
    assert legacy["blocks_found"] == 2
    assert legacy["all_named"] is True
    assert legacy["runner"] == "stub"


def test_to_legacy_s120_preserves_chain_fields():
    report = VerificationReport(runner="python", blocks=[
        BlockResult(identity=_identity(1), status="PASS", proof_tier=3,
                    continues_example=True, commands_run=2),
    ])
    legacy = report.to_legacy_s120()
    assert legacy["blocks"][0]["continues_example"] is True
    assert legacy["blocks"][0]["commands_run"] == 2


def test_to_smoke_maps_pass_warn_fail():
    report = VerificationReport(runner="syntax", blocks=[
        BlockResult(identity=_identity(0), status="PASS", proof_tier=1),
        BlockResult(identity=_identity(1), status="BLOCKED-WITH-REASON", reason="GRAMMAR-UNAVAILABLE"),
        BlockResult(identity=_identity(2), status="BLOCKED-WITH-REASON", reason="SYNTAX-ERROR", detail="bad"),
    ])
    smoke = report.to_smoke()
    assert smoke["pass_count"] == 1
    assert smoke["warn_count"] == 1
    assert smoke["fail_count"] == 1
    assert smoke["blocks_checked"] == 3


def test_to_smoke_skips_not_executable_lang():
    report = VerificationReport(runner="syntax", blocks=[
        BlockResult(identity=_identity(0), status="NOT-EXECUTABLE-LANG"),
        BlockResult(identity=_identity(1), status="PASS", proof_tier=1),
    ])
    smoke = report.to_smoke()
    assert smoke["blocks_checked"] == 1
    assert smoke["pass_count"] == 1


def test_tier_histogram():
    report = VerificationReport(runner="mixed", blocks=[
        BlockResult(identity=_identity(0), status="PASS", proof_tier=1),
        BlockResult(identity=_identity(1), status="PASS", proof_tier=1),
        BlockResult(identity=_identity(2), status="PASS", proof_tier=3),
    ])
    assert report.tier_histogram == {1: 2, 3: 1}
