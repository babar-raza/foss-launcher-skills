# C11 promotion gate decision — it-0013-20260906T1044Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C11 ".NET runner"

## What shipped this iteration

New `scripts/pipeline/lib/example_verification/runners/dotnet.py`:
`DotNetRunner`, the second concrete `runners/base.py` `LanguageRunner`
implementation after C5's `GoRunner`, applying the same design lessons C5's
independent review already surfaced (built in from the start, not
discovered again):

- `canonical_lang = "csharp"` (matching `code_fences.py`'s canonical
  lang-tag mapping), `ceiling_tier = 3`.
- `starts_chain`: first non-comment line is `using` -- this repo's real
  Quick Start snippets are top-level-statement C# programs.
- `acquire`: real `dotnet new console --no-restore` scaffold (a genuinely
  fallible step, unlike Go's acquire, which never creates anything --
  reports `{"ok": False}` when the toolchain is missing or scaffolding
  fails). Attempts `dotnet add reference` against this product's own main
  `.csproj` (resolved via a locally-ported `_select_main_csproj` -- see
  below) when a real clone exists; a missing/failed reference is NOT an
  acquire failure, matching `GoRunner`'s "a missing dependency isn't fatal"
  posture -- a pure-BCL block needs no reference at all.
- `compile`/`execute`: real `dotnet build`/`dotnet run --no-build`.
- `classify`: a file-citation-basename check (does the error/exception cite
  a `.cs` file other than `Program.cs`) -- built this way FROM THE START
  based on `GoRunner`'s own independent-review finding that a raw
  replace/reference-path substring match never appears verbatim in real
  compiler output. Verified against two REAL, distinct .NET diagnostic
  formats (confirmed via a manual probe before writing any code):
  MSBuild build errors (`Program.cs(1,19): error CS0103: ...`) and
  unhandled-exception stack traces (`... in Program.cs:line 2`) -- genuinely
  different citation syntax from each other AND from Go's.

**`_select_main_csproj`**: ported (not imported) from
`dependency_extract.py`, matching that module's own documented convention
("reimplemented locally, not imported") and the plan's own fallback
instruction ("port its logic locally if [importing is] not [safe]"). Same
shortest-path/exclude-test-projects/prefer-non-Exe heuristic, verbatim.

## Tests

New `scripts/pipeline/tests/test_example_verification_dotnet.py` (15 tests,
skipped if `dotnet` isn't on PATH, real subprocess calls throughout, ~26s
total): `starts_chain` (3), `classify` (4, including two built from the
real-format probe above), real `acquire()` -- a real scaffold with no
reference for an unknown family, and a genuine `{"ok": False}` when `dotnet`
is removed from `PATH` for the duration of one call (restored via
try/finally, never leaves the env mutated) (2), real `compile()` via real
`dotnet build` -- clean pass + a genuine undefined-identifier error (2),
real `execute()` via real `dotnet run` -- clean pass + a genuine
divide-by-zero runtime exception (2), and two full
`BaseRunner(DotNetRunner(...)).run(...)` end-to-end proofs -- a clean block
reaching real `proof_tier=3`, and a broken block correctly classified
`COMPILE-ERROR` through the whole tier ladder (2). Full regression:
this file (15) + `test_example_verification_runners_base.py` +
`test_platform_capability_matrix.py` = 311 passed, 7 skipped (pre-existing
skips unrelated to this change), 0 failed. `check_monkeypatch_lint.py`:
0 violations.

## Deliberately deferred / not touched (disclosed)

1. **`platform_capabilities.yaml`'s "net" `example_verification` site**
   (`max_tier: 1`, `runner_module: null`) is in C11's `allowed_paths` but
   left UNTOUCHED: `check_platform_capabilities.py:check_example_verification`
   does an exact-value diff of the YAML against
   `lib.example_verification.registry.PLATFORM_CONTRACT["net"]` (confirmed
   by reading the check's own source) -- flipping only the YAML side
   without also flipping `registry.py`'s `PLATFORM_CONTRACT["net"].max_tier`/
   `.runner` would immediately fail that check with a real
   `value_mismatch` finding. `registry.py` is NOT in C11's `allowed_paths`.
   The same structural gap C5 disclosed (registry.py flip blocked), just
   surfacing differently here: a file being nominally in `allowed_paths`
   doesn't make changing it safe when the change requires another,
   out-of-scope file to move in lockstep.
2. **The `published: dotnet add package {name} --version {v}` (real NuGet
   resolve) acquire branch.** Not built: no real product in this portfolio
   needs it for offline test coverage, and there's no fixture to prove it
   against without inventing one -- same disclosed limit `GoRunner`'s
   published/`go get` branch carries.
3. **A real pilot against actual product content** (`words/net`,
   `email/net`, per the stage matrix). Every test here uses BCL-only
   synthetic code deliberately -- a real product example would need the
   same fixture-staging support Python/TypeScript already have and Go
   doesn't either yet; building that is a separable piece of work, not
   smuggled into this taskcard.

## Disposition

Recommending CLOSE, pending independent review: the taskcard's core
deliverable (a real, working, tested .NET `LanguageRunner`, tier 1-3) is
built with the design lessons from C5's own review already applied, and
the 3 remaining items are either structurally blocked outside
`allowed_paths` (matching C5's own precedent) or a genuinely separable
follow-on.
