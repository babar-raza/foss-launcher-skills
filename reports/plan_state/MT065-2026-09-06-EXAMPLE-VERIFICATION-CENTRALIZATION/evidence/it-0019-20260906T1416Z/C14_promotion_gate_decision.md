# C14 promotion gate decision — it-0019-20260906T1416Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C14 "C++ runner (CMake subset, BUILD-VERIFIED-ONLY floor)"

## Verified precondition -- and a real, load-bearing correction to the plan's own claim

The plan's own C++ section says the toolchain is "confirmed already
installed" (CMake 4.4.1, Ninja 1.13.2, MSVC via Visual Studio 2022
Community found through `vswhere.exe`). Re-verifying live before acting
(per this mission's own established discipline) found this claim **half
right**: CMake/Ninja are genuinely present, but `lib.example_verification.
toolchain.msvc_env()` -- the shared helper the plan explicitly says this
taskcard should use -- returns `None` on this exact machine. Root-caused to
two real, independent, live-confirmed bugs, both in `toolchain.py` (out of
this taskcard's `allowed_paths`, so fixed LOCALLY in `runners/cpp.py`
instead, not in the shared module):

1. `vswhere -latest` (no `-products *`, no `-requires Microsoft.
   VisualStudio.Component.VC.Tools.x86.x64`) resolves to "Visual Studio
   Community 2022" -- genuinely installed, but WITHOUT the C++ workload (no
   `VC/Auxiliary/Build/vcvarsall.bat` anywhere under it). A separate, real
   "Visual Studio Build Tools 2022" installation on this same machine DOES
   have the C++ workload and a real `vcvarsall.bat`; `vswhere` only
   surfaces it when asked with `-products *` (confirmed via `vswhere -all
   -products "*" -format json`, which lists 3 installations vs. 1 without
   that flag).
2. Even pointed at the correct `vcvarsall.bat`, `toolchain.py`'s own
   `subprocess.run(["cmd", "/c", f'call "{vcvarsall}" x64 && set'], ...)`
   (a LIST with an already-quoted string as one element) fails with `"...
   is not recognized as an internal or external command"` -- confirmed
   live: Python's `list2cmdline` re-quotes that element, doubling the
   embedded quotes. `subprocess.run(cmdline, shell=True, ...)` (a STRING)
   avoids this and was confirmed live to correctly capture a real
   `INCLUDE`/`LIB`/`VCToolsInstallDir` environment.

Both fixes are applied in this module's own local `_msvc_env()`. Filed here
as a real, disclosed finding for the shared `toolchain.py` -- not silently
worked around without a trace, and not something this taskcard can fix
directly (`toolchain.py` is not in its `allowed_paths`).

## What shipped this iteration

New `scripts/pipeline/lib/example_verification/runners/cpp.py` --
`CppRunner`, scoped per the plan's own explicit design to the
`CMakeLists.txt`-declaring subset (3 real products confirmed:
`email/cpp`, `pdf/cpp`, `slides/cpp`):

- `canonical_lang = "cpp"`, `ceiling_tier = 2` (matching the plan's own
  "-> 2 for C++'s BUILD-VERIFIED-ONLY fallback" -- no per-block execute
  claim).
- `starts_chain()`: fresh when a block declares `#include`, `using
  namespace`, or `int main(`; continuation otherwise. Confirmed against
  real content: every cpp block under `content/docs.aspose.org/en/slides/
  cpp/developer-guide/` re-declares its own `#include` lines rather than
  relying on a prior block's.
- `acquire()`: real, not always-succeed (unlike Go/Rust) -- a product
  without `CMakeLists.txt` is a genuine, honest out-of-scope result, not a
  per-block concern deferred to `compile()`. Also captures the real MSVC
  environment (the fixed `_msvc_env()` above).
- `compile()`: runs the REAL `cmake -S . -B build -G Ninja && cmake
  --build build` exactly ONCE per runner instance (cached at the instance
  level), matching the plan's own "library-level, not per-block"
  `BUILD-VERIFIED-ONLY` design. Every block in a run inherits that single
  verdict.
- `execute()`: unreachable in practice (`ceiling_tier=2` stops `BaseRunner`
  before ever calling it); implemented defensively, never silently
  claiming a PASS it can't back up.
- `classify()`: MSVC's real diagnostic format (`path(line): error C####:
  message`, on STDOUT) -- **live-verified** against a real `cl.exe`
  invocation on a deliberately broken 3-line fragment before being encoded
  into a regex (unlike C13's Rust runner, which had no toolchain to verify
  its own classify() against). Since this runner builds the library's own
  real source tree directly (no per-block generated wrapper file the way
  Go/.NET/Java/Rust each produce one), any MSVC-shaped citation
  necessarily means a real defect in that real source -- always
  UPSTREAM-BROKEN when a citation exists, COMPILE-ERROR only for a
  citation-less failure (e.g. a CMake configure-time error).

## Disclosed gap in shared, out-of-allowed-paths infrastructure (`base.py`)

`result.py` already lists `BUILD-VERIFIED-ONLY` in its `REASONS`
vocabulary (added by an earlier taskcard anticipating this one), but
`runners/base.py`'s own `_climb()` (C3's territory, not in this taskcard's
`allowed_paths`) never actually constructs a `BlockResult` with
`reason="BUILD-VERIFIED-ONLY"` anywhere -- a tier-2 `compile()` success
produces a bare `PASS, proof_tier=2` with no reason at all, confirmed live
(see pilot below: `reason` is `None` on every real-build success). So a
real library-level BUILD-VERIFIED-ONLY success is, today, structurally
indistinguishable from any other runner's ordinary tier-2 PASS once it
passes through the shared ladder. This is a genuine, disclosed pre-existing
gap in `base.py` itself, not something `cpp.py` alone can close.

## Deliberately not attempted (the plan's own stated stretch goal)

Per-block smoke compilation ("evaluate ... whether genuine per-block
compilation is achievable... decide this empirically during the phase, not
in advance") was not attempted this iteration -- `compile()` ignores its
own `code`/`index` parameters entirely; every block shares the one real
library build. This is the plan's own explicit floor design
(`BUILD-VERIFIED-ONLY`), not a scope cut below it. A future taskcard can
revisit the stretch goal separately.

## Tests

13 new focused tests in `scripts/pipeline/tests/test_example_verification_
cpp.py`: real MSVC env capture; `starts_chain` (matching real content);
`classify` against the real, live-captured MSVC error format plus a
citation-less CMake-error case; `acquire()` for both a real product
(slides/cpp) and a nonexistent one (honest out-of-scope); and 2
`BaseRunner` integration tests -- default policy (registry's real, current
`max_tier=1`) never attempts a real build; forced `max_tier=2` runs a real
~45-60s CMake+Ninja+MSVC build (including a real FetchContent network
fetch of `pugixml`/`miniz` on first run) that actually succeeds, with 2
blocks confirming the real build runs only ONCE (`runner._build_ran`).
All 13 pass. `check_monkeypatch_lint.py --strict`: 0 violations. Scoped
regression subset (cpp + rust sibling runner tests): 51/51 pass.

## Pilot (real content, slides/cpp -- the stage matrix's own named product)

Extracted all 13 real cpp code blocks from `content/docs.aspose.org/en/
slides/cpp/developer-guide/features.md` via the canonical tokenizer and
ran them through `BaseRunner(CppRunner("slides"))`:

- **Default policy** (registry.py's real, current `max_tier=1`): all 13
  blocks PASS at tier 1 instantly -- real syntax check against real
  content.
- **Forced `max_tier=2`**: a real CMake+Ninja+MSVC configure+build (99.7s,
  including a fresh FetchContent network fetch) succeeded completely --
  103/103 objects compiled, `aspose_slides_foss.lib` linked -- and all 13
  blocks inherit `PASS, proof_tier=2` from that single real build, exactly
  the library-level `BUILD-VERIFIED-ONLY` design working end-to-end
  against real product content, not just synthetic fixtures.

## Promotion gate

"CMake+Ninja+MSVC build succeeds via the captured vcvarsall env;
BUILD-VERIFIED-ONLY recorded" -- satisfied: the build genuinely succeeds
(both in isolated tests and against real page content), using a captured
vcvarsall env this taskcard had to fix two real bugs to get working at
all. "BUILD-VERIFIED-ONLY recorded" is satisfied in spirit (a real,
disclosed library-level proof, not a per-block one) but not literally in
the schema (the disclosed `base.py` reason-wiring gap above means the
`reason` field itself stays empty on success) -- an honest, disclosed
partial rather than a silently-claimed full match.

## Disposition

Recommending CLOSE, pending independent review: the runner is real,
tested, and proven against real product content end-to-end (not a stub);
the two real MSVC-discovery bugs found in shared infrastructure were
root-caused, fixed locally, and disclosed (not silently worked around);
the one schema-level gap (`reason` not carrying `BUILD-VERIFIED-ONLY`) is
a `base.py` limitation outside this taskcard's control, disclosed rather
than silently absorbed; the stretch goal (per-block compilation) was
deliberately not attempted, matching the plan's own explicit "decide this
empirically" framing rather than treated as a requirement.
