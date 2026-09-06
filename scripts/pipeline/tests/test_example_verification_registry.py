"""Tests for lib/example_verification/registry.py (rollout step C2)."""
from __future__ import annotations

from lib.example_verification.registry import (
    NON_EXECUTABLE_LANGS,
    PLATFORM_CONTRACT,
    RUNNABLE_LANGS_BY_PLATFORM,
    PlatformContract,
)


def test_every_platform_has_a_contract():
    for platform in ("python", "typescript", "go", "net", "java", "rust", "cpp"):
        assert platform in PLATFORM_CONTRACT
        contract = PLATFORM_CONTRACT[platform]
        assert isinstance(contract, PlatformContract)
        assert contract.platform == platform


def test_python_and_typescript_have_real_runners_at_tier_3():
    assert PLATFORM_CONTRACT["python"].max_tier == 3
    assert PLATFORM_CONTRACT["python"].runner == "python"
    assert PLATFORM_CONTRACT["typescript"].max_tier == 3
    assert PLATFORM_CONTRACT["typescript"].runner == "typescript"


def test_unbuilt_runner_platforms_have_no_runner_and_tier_1_ceiling():
    for platform in ("go", "net", "java", "rust", "cpp"):
        contract = PLATFORM_CONTRACT[platform]
        assert contract.runner is None
        assert contract.max_tier == 1


def test_go_is_the_only_precommit_blocking_platform_today():
    blocking = {p for p, c in PLATFORM_CONTRACT.items() if c.precommit_blocking}
    assert blocking == {"go"}


def test_runnable_langs_by_platform_mirrors_fence_tags():
    for platform, contract in PLATFORM_CONTRACT.items():
        assert RUNNABLE_LANGS_BY_PLATFORM[platform] == contract.fence_tags


def test_non_executable_langs_excludes_bash_shell_sh():
    # bash/sh/shell are runnable under the python platform (Phase 0 item 1)
    # -- they must never be classified as non-executable fences.
    assert "bash" not in NON_EXECUTABLE_LANGS
    assert "sh" not in NON_EXECUTABLE_LANGS
    assert "shell" not in NON_EXECUTABLE_LANGS


def test_non_executable_langs_includes_documentation_fences():
    for lang in ("mermaid", "json", "yaml", "xml", "text", "console"):
        assert lang in NON_EXECUTABLE_LANGS


def test_platform_contract_is_frozen():
    contract = PLATFORM_CONTRACT["python"]
    try:
        contract.max_tier = 5  # type: ignore[misc]
        assert False, "PlatformContract should be frozen"
    except AttributeError:
        pass
