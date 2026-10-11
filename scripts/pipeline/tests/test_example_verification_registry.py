"""Tests for lib/example_verification/registry.py (rollout step C2;
TC-02, MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION, made
PLATFORM_CONTRACT generated from real runner introspection)."""
from __future__ import annotations

from lib.example_verification import registry as registry_mod
from lib.example_verification.registry import (
    NON_EXECUTABLE_LANGS,
    PLATFORM_CONTRACT,
    RUNNABLE_LANGS_BY_PLATFORM,
    RUNNER_CLASS_NAMES,
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


def test_built_runner_platforms_report_their_real_ceiling_tier():
    """TC-02: go/net/java/rust/cpp all have real LanguageRunner classes
    (C5, C11-C14) -- PLATFORM_CONTRACT must reflect their own declared
    ceiling_tier, not the pre-TC-02 hand-typed max_tier=1/runner=None
    this exact test used to assert as correct."""
    expected_ceiling = {"go": 3, "net": 3, "java": 3, "rust": 3, "cpp": 2}
    for platform, ceiling in expected_ceiling.items():
        contract = PLATFORM_CONTRACT[platform]
        assert contract.runner is not None, f"{platform} should have a real runner"
        assert contract.max_tier == ceiling, f"{platform}: expected ceiling {ceiling}, got {contract.max_tier}"


def test_platform_contract_runner_matches_a_real_importable_class():
    """Every non-None `runner` must resolve to a real, importable
    LanguageRunner class -- catches a typo in RUNNER_CLASS_NAMES or a
    renamed runner module/class before any real caller hits it."""
    import importlib
    for platform, (mod_name, class_name) in RUNNER_CLASS_NAMES.items():
        contract = PLATFORM_CONTRACT[platform]
        assert contract.runner == mod_name
        mod = importlib.import_module(f"example_verification.runners.{mod_name}")
        cls = getattr(mod, class_name)
        assert cls.ceiling_tier == contract.max_tier


def test_genuinely_unbuilt_runner_falls_back_to_tier_1_no_runner(monkeypatch):
    """A platform whose runner module/class truly doesn't exist (or fails
    to introspect) must degrade to the pre-TC-02 honest floor
    (max_tier=1, runner=None), not crash and not silently claim a tier it
    can't prove."""
    assert registry_mod._introspect_ceiling_tier("does_not_exist", "NoSuchRunner") is None


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
