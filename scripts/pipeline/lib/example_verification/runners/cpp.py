"""
lib/example_verification/runners/cpp.py

CONTRACT: scripts/pipeline/lib/example_verification/runners/cpp.py
  purpose: C14 (MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION) --
           the C++ `LanguageRunner` implementation on `runners/base.py`.
           Scoped, per the governing plan's own C++ section, to the
           `CMakeLists.txt`-declaring subset of cpp products (the same
           subset `dependency_extract.py::_extract_cpp_dependencies`
           already parses for manifests, though that function only reads
           `vcpkg.json`/`conanfile.txt` -- it never invokes a build, so
           there is no existing CMake-invocation code to reuse here).
  inputs:  a fenced ```cpp code block's raw text; a C++ product's family
           name
  outputs: BaseRunner(CppRunner(family)).run(...) -> list[BlockResult]
  owner_domain: content-quality

**Library-level proof, not per-block** (the plan's own explicit design,
`BUILD-VERIFIED-ONLY`): `compile()` runs the product's REAL `cmake -S . -B
build -G Ninja && cmake --build build` exactly ONCE per runner instance
(cached at the instance level -- a 20+ second real build is not something
to repeat per block), and every block in the run inherits that single
verdict. `ceiling_tier = 2` (matching the plan's own "-> 2 for C++'s
BUILD-VERIFIED-ONLY fallback"): this runner has no per-block `execute()`
capability by design, so `BaseRunner`'s own ladder (`if policy.max_tier < 3
or self.runner.ceiling_tier < 3: ... proof_tier=2`) never calls
`execute()` -- it exists only for `LanguageRunner` protocol conformance
and is unreachable in practice (documented on the method itself).

**Disclosed gap in shared, out-of-allowed-paths infrastructure** (found
live while building this taskcard, NOT introduced by it): `result.py`
already lists `BUILD-VERIFIED-ONLY` in its `REASONS` vocabulary (added by
an earlier taskcard specifically anticipating this one), but
`runners/base.py`'s own `_climb()` (out of this taskcard's `allowed_paths`
-- C3's territory) never actually constructs a `BlockResult` with
`reason="BUILD-VERIFIED-ONLY"` anywhere: a tier-2 compile() success
(`compile_failure is None`) always produces a bare `PASS, proof_tier=2`
with no reason set at all. So a real, honest library-level BUILD-VERIFIED-
ONLY compile success from this runner is, today, structurally
indistinguishable from any other runner's ordinary ("real per-block
compile") tier-2 PASS once it passes through the shared ladder -- a real,
disclosed gap in `base.py`, not something `cpp.py` alone can fix (it is
not in this taskcard's `allowed_paths`), flagged here for a future
taskcard to close by having `_climb` read an optional `reason` key back
from `compile()`'s success path (today `compile()`'s success contract is
strictly `None`, carrying no information at all).

**Local MSVC discovery, not `toolchain.msvc_env()`** (also disclosed,
also found live, also out of this taskcard's `allowed_paths` --
`toolchain.py` is not listed there): `lib.example_verification.toolchain.
msvc_env()` was tried first and found to return `None` on this exact
machine despite Visual Studio 2022 being genuinely installed. Root-caused
to TWO real, independent bugs, both confirmed live:
  1. `vswhere -latest` (no `-products *`, no `-requires
     Microsoft.VisualStudio.Component.VC.Tools.x86.x64`) resolves to
     "Visual Studio Community 2022" -- installed on this machine WITHOUT
     the C++ workload (no `VC/Auxiliary/Build/vcvarsall.bat` at all under
     that installation). A SEPARATE, real "Visual Studio Build Tools
     2022" installation on this same machine DOES have the C++ workload
     and a real `vcvarsall.bat` -- `vswhere` only surfaces it when asked
     for `-products *` (its default product filter excludes Build-Tools-
     only SKUs).
  2. Even pointed at the correct `vcvarsall.bat`, `toolchain.py`'s own
     `subprocess.run(["cmd", "/c", f'call "{vcvarsall}" x64 && set'], ...)`
     (a LIST with an embedded, already-quoted string as one element) fails
     with "... is not recognized as an internal or external command" --
     confirmed live: Python's `list2cmdline` re-quotes that whole element,
     doubling the embedded quotes, and `cmd /c` then can't parse the
     result. `subprocess.run(cmdline_string, shell=True, ...)` (a STRING,
     not a list) avoids the double-quoting entirely and was confirmed live
     to correctly capture a real `INCLUDE`/`LIB`/`VCToolsInstallDir`
     environment.
Both fixes are applied LOCALLY in this module's own `_msvc_env()` (below)
since `toolchain.py` is out of `allowed_paths`; the shared function's own
two bugs are unfixed and will silently affect any other future caller of
`toolchain.msvc_env()` on a machine shaped like this one, until a future
taskcard closes them there.

**Proven end-to-end, live, before writing the rest of this module**: a
real `cmake -S runs/.clone_cache/aspose_slides_cpp -B <tmp> -G Ninja
-DASPOSE_SLIDES_FOSS_BUILD_TESTS=OFF -DASPOSE_SLIDES_FOSS_INSTALL=OFF` (23s,
including a real FetchContent network fetch of pugixml/miniz) followed by
`cmake --build <tmp> --parallel` (21s) succeeded completely: 103/103
objects compiled, `aspose_slides_foss.lib` linked -- using exactly the
local MSVC env capture this module implements. `classify()`'s MSVC
diagnostic format (`path(line): error C####: message`, on STDOUT not
STDERR) was also confirmed live against a real `cl.exe` invocation on a
deliberately broken 3-line fragment before being encoded into a regex --
unlike C13's Rust runner, this one's error-format assumption IS
live-verified, since a real toolchain exists here.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..policy import clone_cache_path, Policy, ProductContext

_VSWHERE_STANDARD_PATH = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"

# MSVC's own, well-documented diagnostic format -- confirmed live against a
# real cl.exe invocation before writing this regex (see module docstring):
# "C:\path\to\file.cpp(2): error C2059: syntax error: ';'" -- printed to
# STDOUT, not STDERR.
_MSVC_ERROR_LOCATION_RE = re.compile(r'^(.+?\.(?:cpp|cc|cxx|h|hpp)):?\((\d+)\)\s*:\s*error', re.MULTILINE)


@dataclass(frozen=True, slots=True)
class _MsvcEnv:
    installation_path: str
    env: "dict[str, str]"


def _find_vswhere() -> "str | None":
    if Path(_VSWHERE_STANDARD_PATH).is_file():
        return _VSWHERE_STANDARD_PATH
    return shutil.which("vswhere")


def _msvc_env() -> "_MsvcEnv | None":
    """Local, fixed re-implementation of `toolchain.msvc_env()` -- see this
    module's own docstring for the two real, live-confirmed bugs in the
    shared version this works around (`-products *`/`-requires` product
    filtering, and `shell=True` instead of a pre-quoted list element).
    Not cached across calls the way the shared version is (this runner
    only ever calls it once per instance, from `acquire()`, itself already
    cached -- see `CppRunner.__init__`)."""
    vswhere = _find_vswhere()
    if vswhere is None:
        return None
    try:
        result = subprocess.run(
            [vswhere, "-products", "*",
             "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
             "-latest", "-property", "installationPath"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    installation_path = (result.stdout or "").strip()
    if not installation_path:
        return None

    vcvarsall = Path(installation_path) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if not vcvarsall.is_file():
        return None
    try:
        captured = subprocess.run(
            f'call "{vcvarsall}" x64 && set', shell=True,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if captured.returncode != 0:
        return None

    env: "dict[str, str]" = {}
    for line in (captured.stdout or "").splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key:
            env[key] = value
    if "INCLUDE" not in env or "LIB" not in env:
        return None
    return _MsvcEnv(installation_path=installation_path, env=env)


class CppRunner:
    """C14's `LanguageRunner` implementation. One instance = one product.
    `ceiling_tier = 2`: library-level `BUILD-VERIFIED-ONLY` is this
    runner's ceiling by design (see module docstring for the disclosed
    `base.py` reason-wiring gap) -- there is no per-block `execute()`
    capability, and no claim of one.

    Deliberately NOT attempted (the plan's own explicit stretch goal,
    "decide this empirically during the phase, not in advance"): per-block
    smoke compilation (a small, generated CMake target per block compiling
    a single translation unit against the already-built library). `compile()`
    ignores its own `code`/`index` parameters entirely -- every block in a
    run shares the one real library-level build. Revisiting this is a
    separate, future scope decision, not a regression against this
    taskcard's own stated floor (library-level `BUILD-VERIFIED-ONLY`),
    which is what shipped."""

    canonical_lang = "cpp"
    ceiling_tier = 2

    def __init__(self, family: str, extra_cmake_args: "list[str] | None" = None) -> None:
        self._family = family
        self._extra_cmake_args = extra_cmake_args or []
        self._build_ran = False  # the real configure+build runs at most once per instance
        self._build_failure: "dict | None" = None  # None = last (only) build was clean

    def starts_chain(self, code: str) -> bool:
        """True (fresh, self-contained example) when the block declares its
        own `#include`, `using namespace`, or `int main(`; False (continues
        the previous block's chain) otherwise. Confirmed against real
        content: every real cpp code block under `content/docs.aspose.org/
        en/slides/cpp/developer-guide/` re-declares its own `#include`
        lines rather than relying on a prior block's -- the same
        self-contained shape `GoRunner`'s heuristic confirms for Go."""
        for line in code.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "/*")):
                continue
            return stripped.startswith(("#include", "using namespace", "int main"))
        return True

    def acquire(self, work_dir: Path, policy: Policy, product: ProductContext) -> dict:
        """Real, not always-succeed (unlike Go/Rust): this taskcard's own
        scope is explicitly "the CMakeLists.txt-declaring subset" -- a
        product without one is a genuine, honest "can't do this here", not
        a per-block concern to defer to compile(). Also resolves the real
        MSVC environment once (see `_msvc_env()` above) -- both are cached
        on the instance, since neither is something to redo per block."""
        source_dir = clone_cache_path(self._family, "cpp")
        if not (source_dir / "CMakeLists.txt").is_file():
            return {"ok": False, "detail": f"no CMakeLists.txt for {self._family}/cpp -- out of this runner's scope"}
        cmake_exe = shutil.which("cmake")
        ninja_exe = shutil.which("ninja")
        if cmake_exe is None or ninja_exe is None:
            return {"ok": False, "detail": "cmake or ninja not found on PATH"}
        msvc = _msvc_env()
        if msvc is None:
            return {"ok": False, "detail": "MSVC build environment could not be captured (vswhere/vcvarsall)"}
        return {
            "ok": True, "work_dir": work_dir, "source_dir": source_dir,
            "cmake_exe": cmake_exe, "ninja_exe": ninja_exe, "msvc_env": msvc.env,
        }

    def compile(self, acquired: dict, code: str, index: int) -> "dict | None":
        """Runs the REAL library build exactly once per instance (cached);
        every block in this run inherits that single verdict -- see module
        docstring for why this is deliberately library-level, not
        per-block, and the disclosed `base.py` gap that means a success
        here surfaces as an ordinary tier-2 PASS, not a distinctly-tagged
        BUILD-VERIFIED-ONLY one."""
        if self._build_ran:
            return self._build_failure
        self._build_ran = True

        work_dir = acquired["work_dir"]
        build_dir = work_dir / "build"
        full_env = {**os.environ, **acquired["msvc_env"]}
        configure = subprocess.run(
            [acquired["cmake_exe"], "-S", str(acquired["source_dir"]), "-B", str(build_dir),
             "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", *self._extra_cmake_args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300, env=full_env,
        )
        if configure.returncode != 0:
            reason, tail = self.classify(configure.stdout + configure.stderr)
            self._build_failure = {"reason": reason, "detail": tail}
            return self._build_failure

        build = subprocess.run(
            [acquired["cmake_exe"], "--build", str(build_dir), "--parallel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=900, env=full_env,
        )
        if build.returncode != 0:
            reason, tail = self.classify(build.stdout + build.stderr)
            self._build_failure = {"reason": reason, "detail": tail}
            return self._build_failure

        self._build_failure = None
        return None

    def execute(self, acquired: dict, code: str, index: int) -> dict:
        """Unreachable in practice: `ceiling_tier = 2` makes `BaseRunner.
        _climb()` return a tier-2 PASS (or the compile failure above)
        before ever calling this. Implemented defensively, never silently
        claiming a PASS it cannot back up, in case a future caller
        constructs a `Policy(max_tier=3)` against this runner directly."""
        return {
            "status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE",
            "detail": "CppRunner has no per-block execute capability (library-level BUILD-VERIFIED-ONLY only)",
        }

    def classify(self, output: str, context: "dict | None" = None) -> "tuple[str, str]":
        """Unlike Go/.NET/Java/Rust's `classify()` (which distinguish an
        error in the block's own GENERATED wrapper from one in a real
        dependency), this runner never generates a wrapper file at all --
        it builds the product's own real source tree directly, so every
        genuine compile error necessarily cites one of that library's own
        real source files. There is no "own wrapper" basename to exclude,
        so `context` (kept only for `LanguageRunner` protocol parity) is
        unused: any MSVC-shaped file citation means UPSTREAM-BROKEN (a
        real defect in the library's own source, exactly what a real
        compile of real source is supposed to catch); no citation at all
        means an ordinary COMPILE-ERROR (e.g. a CMake configure-time
        error, never a compiler diagnostic)."""
        tail = (output or "").strip()[-4000:]
        if _MSVC_ERROR_LOCATION_RE.search(tail):
            return "UPSTREAM-BROKEN", tail
        return "COMPILE-ERROR", tail
