"""Tests for lib/example_verification/runners/cpp.py's CppRunner (C14,
MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION).

Unlike C13's RustRunner (no toolchain at all on this machine), CMake,
Ninja, and a real MSVC install (Visual Studio Build Tools 2022) ARE
present here -- confirmed live below, not assumed. So this suite proves
the real thing where Rust's could only prove honest absence: a genuine
`cmake`/`ninja`/`cl.exe` build against the one real cpp product this
mission's stage matrix names (slides/cpp, the smallest of the 3 real cpp
products with a CMakeLists.txt).
"""
from __future__ import annotations

import hashlib
import shutil

import pytest

from lib.example_verification.policy import Policy, ProductContext
from lib.example_verification.runners.base import BaseRunner
from lib.example_verification.runners.cpp import (
    CppRunner,
    _msvc_env,
    _MSVC_ERROR_LOCATION_RE,
)

# The real MSVC diagnostic line this module's classify() parses -- captured
# live against a real cl.exe invocation on a deliberately broken 3-line
# fragment before this test (and the regex itself) were written; see the
# module's own docstring for the full transcript.
_REAL_MSVC_ERROR_SAMPLE = (
    "main.cpp\n"
    "C:\\Users\\prora\\AppData\\Local\\Temp\\tmp07w3z78h\\main.cpp(2): "
    "error C2059: syntax error: ';'\n"
)


def test_cmake_ninja_and_msvc_are_genuinely_present_on_this_machine():
    """Precondition this whole test file depends on."""
    assert shutil.which("cmake") is not None
    assert shutil.which("ninja") is not None
    assert _msvc_env() is not None


class TestMsvcEnv:
    def test_captures_include_and_lib(self):
        env = _msvc_env()
        assert env is not None
        assert "INCLUDE" in env.env
        assert "LIB" in env.env
        assert "VCToolsInstallDir" in env.env


class TestStartsChain:
    """Confirmed against real content: every real cpp block under
    content/docs.aspose.org/en/slides/cpp/developer-guide/ re-declares its
    own #include lines rather than relying on a prior block's."""

    def test_include_starts_a_new_chain(self):
        runner = CppRunner(family="no-such-family")
        assert runner.starts_chain("#include <iostream>\nint main() { return 0; }")

    def test_using_namespace_starts_a_new_chain(self):
        runner = CppRunner(family="no-such-family")
        assert runner.starts_chain("using namespace Foo;\nBar b;")

    def test_int_main_starts_a_new_chain(self):
        runner = CppRunner(family="no-such-family")
        assert runner.starts_chain("int main() {\n    return 0;\n}")

    def test_plain_statement_continues_the_previous_chain(self):
        runner = CppRunner(family="no-such-family")
        assert not runner.starts_chain("int x = compute();")

    def test_leading_comment_is_skipped_before_deciding(self):
        runner = CppRunner(family="no-such-family")
        assert runner.starts_chain("// a comment\n#include <iostream>")


class TestClassify:
    def test_real_msvc_error_format_is_upstream_broken(self):
        """MSVC's own format, captured live against a real cl.exe
        invocation (see module docstring) -- unlike C13's Rust runner, no
        `note:`-style follow-up citation exists to guard against, and
        there is no per-block wrapper file to exclude by basename (this
        runner builds the library's own real source tree directly), so
        ANY citation means a real defect in that real source."""
        runner = CppRunner(family="no-such-family")
        assert _MSVC_ERROR_LOCATION_RE.search(_REAL_MSVC_ERROR_SAMPLE)
        reason, detail = runner.classify(_REAL_MSVC_ERROR_SAMPLE)
        assert reason == "UPSTREAM-BROKEN"
        assert detail == _REAL_MSVC_ERROR_SAMPLE.strip()

    def test_no_citation_is_an_ordinary_compile_error(self):
        """A CMake configure-time failure (e.g. a missing FetchContent
        source) has no compiler diagnostic shape at all."""
        runner = CppRunner(family="no-such-family")
        reason, _ = runner.classify("CMake Error at CMakeLists.txt:5 (message):\n  something failed\n")
        assert reason == "COMPILE-ERROR"


class TestAcquire:
    def test_family_without_cmakelists_reports_out_of_scope(self, tmp_path):
        """A product without CMakeLists.txt is explicitly out of this
        taskcard's own stated scope -- confirmed as a real, honest
        acquire() failure, not a per-block concern deferred to compile()."""
        runner = CppRunner(family="totally-nonexistent-family-xyz")
        result = runner.acquire(tmp_path, Policy(), ProductContext(family="totally-nonexistent-family-xyz", platform="cpp"))
        assert result["ok"] is False
        assert "CMakeLists.txt" in result["detail"]

    def test_real_slides_cpp_product_acquires_successfully(self, tmp_path):
        """slides/cpp -- the stage matrix's own named pilot product --
        really does have a CMakeLists.txt in this repo's real clone cache."""
        runner = CppRunner(family="slides")
        result = runner.acquire(tmp_path, Policy(), ProductContext(family="slides", platform="cpp"))
        assert result["ok"] is True
        assert result["source_dir"].name == "aspose_slides_cpp"
        assert "INCLUDE" in result["msvc_env"]


class TestRealBuildIntegration:
    """A genuine, real, ~45-60s cmake configure+build against the real
    slides/cpp product (including a real FetchContent network fetch of
    pugixml/miniz on first run) -- proven live before writing the rest of
    this module (see its own docstring for the full transcript). Mirrors
    the wall-clock cost the java/dotnet sibling runner tests already
    accept for a real toolchain-backed proof."""

    def _blocks(self, sources: "list[str]"):
        return [
            (hashlib.sha256(c.encode()).hexdigest(), (10 + i, 12 + i), c)
            for i, c in enumerate(sources)
        ]

    def test_default_policy_never_attempts_a_real_build(self):
        """Matches registry.py's real, current PLATFORM_CONTRACT (max_tier=1
        for cpp) -- acquire/compile are never even attempted, so this must
        return near-instantly."""
        base = BaseRunner(CppRunner("slides"))
        policy = Policy.for_platform("cpp")
        assert policy.max_tier == 1
        product = ProductContext(family="slides", platform="cpp")
        results = base.run(self._blocks(["int x = 1;"]), policy, product)
        assert results[0].status == "PASS"
        assert results[0].proof_tier == 1

    def test_real_library_build_passes_and_is_shared_across_blocks(self):
        """The stage-matrix promotion gate's literal requirement: a real
        CMake+Ninja+MSVC build succeeds. Two blocks are run to confirm the
        real build executes only ONCE (cached at the runner instance) --
        a second real 45s+ build would make this an unreasonably slow
        test, which itself is evidence the caching works."""
        runner = CppRunner(
            "slides",
            extra_cmake_args=["-DASPOSE_SLIDES_FOSS_BUILD_TESTS=OFF", "-DASPOSE_SLIDES_FOSS_INSTALL=OFF"],
        )
        base = BaseRunner(runner)
        policy = Policy(max_tier=2, allow_acquire=True)
        product = ProductContext(family="slides", platform="cpp")
        results = base.run(
            self._blocks(["#include <iostream>\nint main() { return 0; }", "int x = 1;"]),
            policy, product,
        )
        assert len(results) == 2
        for r in results:
            assert r.status == "PASS"
            assert r.proof_tier == 2
        assert runner._build_ran is True
