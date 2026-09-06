"""Tests for lib/example_verification/policy.py (rollout step C2)."""
from __future__ import annotations

import pytest

from lib.example_verification.policy import Policy, ProductContext, Timeouts


def test_policy_defaults():
    p = Policy()
    assert p.max_tier == 2
    assert p.allow_acquire is False
    assert p.chain_mode == "single"


def test_policy_rejects_invalid_chain_mode():
    with pytest.raises(ValueError):
        Policy(chain_mode="parallel")


def test_policy_rejects_out_of_range_max_tier():
    with pytest.raises(ValueError):
        Policy(max_tier=99)


def test_policy_env_allowlist_never_includes_pythonpath():
    p = Policy()
    assert "PYTHONPATH" not in p.env_allowlist


def test_policy_for_platform_python_offline_caps_at_offline_tier():
    p = Policy.for_platform("python", allow_acquire=False)
    assert p.max_tier == 1  # offline_tier for python


def test_policy_for_platform_python_with_acquire_reaches_full_ceiling():
    p = Policy.for_platform("python", allow_acquire=True)
    assert p.max_tier == 3


def test_policy_for_platform_explicit_max_tier_overrides():
    p = Policy.for_platform("python", max_tier=2, allow_acquire=True)
    assert p.max_tier == 2


def test_policy_for_platform_unknown_platform_defaults_to_tier_1():
    p = Policy.for_platform("cobol")
    assert p.max_tier == 1


def test_timeouts_for_platform_uses_per_platform_default():
    assert Timeouts.for_platform("java").seconds == 180.0
    assert Timeouts.for_platform("python").seconds == 60.0


def test_timeouts_for_unknown_platform_falls_back_to_60s():
    assert Timeouts.for_platform("cobol").seconds == 60.0


def test_product_context_from_factpack():
    pc = ProductContext.from_factpack(
        {"published": True, "candidate": {"name": "aspose-pdf-foss", "version": "26.9.0"}},
        family="pdf", platform="python",
    )
    assert pc.published is True
    assert pc.package_name == "aspose-pdf-foss"
    assert pc.manifest_version == "26.9.0"
    assert pc.family == "pdf"


def test_product_context_from_factpack_missing_candidate_defaults_empty():
    pc = ProductContext.from_factpack({"published": False})
    assert pc.package_name == ""
    assert pc.manifest_version is None


def test_product_context_from_knowledge_reads_real_repo_sha():
    pc = ProductContext.from_knowledge("pdf", "python")
    assert pc.family == "pdf"
    assert pc.platform == "python"
    assert pc.clone_head  # real repo_sha from knowledge/pdf/python/merged/model.yaml


def test_product_context_from_knowledge_missing_product_is_honest_none():
    pc = ProductContext.from_knowledge("doesnotexist", "doesnotexist")
    assert pc.clone_head is None
