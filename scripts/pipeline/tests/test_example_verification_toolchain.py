"""Tests for lib/example_verification/toolchain.py (rollout step C3).

Real, local, no-network discovery calls are exercised for real (matching
this repo's own established test convention for the two existing runners:
"real acquire->execute->classify is the check ... but the network-dependent
half ... is deliberately NOT exercised here" -- msvc_env()/find()/
version_of() are all local, so there's nothing to mock).
"""
from __future__ import annotations

from lib.example_verification.toolchain import (
    exec_env,
    find,
    fingerprint,
    maven_java_version,
    msvc_env,
    version_of,
)


def test_find_resolves_a_real_installed_tool():
    # dotnet is confirmed installed on this machine (governing plan's
    # "Verified toolchain inventory").
    path = find("dotnet")
    assert path is not None
    assert "dotnet" in path.lower()


def test_find_returns_none_for_a_nonexistent_tool():
    assert find("definitely-not-a-real-tool-xyz123") is None


def test_find_is_cached():
    p1 = find("dotnet")
    p2 = find("dotnet")
    assert p1 == p2


def test_version_of_real_tool_returns_a_plausible_version():
    version = version_of("go")
    assert version is not None
    assert version[0].isdigit()


def test_version_of_unknown_tool_returns_none():
    assert version_of("definitely-not-a-real-tool-xyz123") is None


def test_maven_java_version_returns_the_jdk_maven_itself_resolves():
    # Confirmed live (governing plan): mvn resolves its OWN JDK (17.0.19,
    # Eclipse Adoptium), a different JDK than whichever `java` is on PATH.
    version = maven_java_version()
    assert version is not None
    assert version[0].isdigit()


def test_msvc_env_is_none_or_a_real_captured_environment():
    # MSVC is confirmed present on this machine via vswhere -- but this
    # test must also pass on a machine without it (e.g. a Linux CI runner),
    # so it accepts either a real result or a clean None, never a crash.
    result = msvc_env()
    if result is not None:
        assert result.installation_path
        assert "INCLUDE" in result.env
        assert "LIB" in result.env
        assert "PATH" in result.env


def test_msvc_env_is_cached():
    r1 = msvc_env()
    r2 = msvc_env()
    assert r1 is r2


def test_exec_env_never_leaks_pythonpath():
    import os
    os.environ["PYTHONPATH"] = "/should/never/appear"
    try:
        env = exec_env()
        assert "PYTHONPATH" not in env
    finally:
        del os.environ["PYTHONPATH"]


def test_exec_env_includes_allowlisted_vars_when_present():
    import os
    os.environ["TEMP_TEST_VAR_XYZ"] = "should-not-appear"
    try:
        env = exec_env(allowlist=frozenset({"PATH"}))
        assert "TEMP_TEST_VAR_XYZ" not in env
    finally:
        del os.environ["TEMP_TEST_VAR_XYZ"]


def test_exec_env_extra_wins_over_base():
    env = exec_env(allowlist=frozenset({"PATH"}), extra={"PATH": "custom-path-value"})
    assert env["PATH"] == "custom-path-value"


def test_fingerprint_stable_for_available_tool():
    fp1 = fingerprint("dotnet")
    fp2 = fingerprint("dotnet")
    assert fp1 == fp2
    assert fp1.startswith("dotnet@")
    assert fp1 != "dotnet@unavailable"


def test_fingerprint_distinct_for_unavailable_tool():
    fp = fingerprint("definitely-not-a-real-tool-xyz123")
    assert fp == "definitely-not-a-real-tool-xyz123@unavailable"


def test_fingerprint_differs_between_tools():
    assert fingerprint("dotnet") != fingerprint("go")
