# C5 promotion gate decision — it-0012-20260906T1017Z (checkpoint 2 of N)

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C5 "Go runner from check_go_code_blocks.py + generalize pre-commit Step 18"

Builds on checkpoint 1 (`reports/plan_state/.../evidence/it-0011-.../C5_promotion_gate_decision.md`,
commit `7ff4f5ef0d`), which moved/fixed the module-resolution helpers. This
checkpoint builds the deferred piece: the actual `LanguageRunner` protocol
implementation.

## What shipped this iteration

**`GoRunner`** (new class in `runners/go.py`) -- the first concrete
implementation of `runners/base.py`'s `LanguageRunner` protocol (no prior
runner has used it; `python.py`/`typescript.py` predate it and aren't
retrofit onto it per `base.py`'s own docstring). `canonical_lang = "go"`,
`ceiling_tier = 3`. Implements:

- `starts_chain`: first non-comment line is `package`/`import`, per the
  governing plan's own Go chain-start heuristic.
- `acquire`: resolves this product's module info (fixed at construction from
  `_resolve_go_module_for_family`) and its replace path
  (`_find_module_replace_path`). Always succeeds -- unlike Python's real venv
  creation, there is no environment-setup step that can genuinely fail for
  Go; a stdlib-only block needs no replace directive at all, and
  `_write_go_module` already omits the replace block when `replace_path` is
  `None`, the same way `check_go_code_blocks.py:_vet_block` always has.
- `compile`: real `go vet` (tier 2) -- the same check `check_go_code_blocks.py`
  already runs, reusing `_wrap_fragment`/`_needs_wrap`.
- `execute`: real `go run` (tier 3) -- a genuinely NEW capability this
  taskcard adds (the CLI never executed Go code, only vetted it).
- `classify`: distinguishes UPSTREAM-BROKEN (the error output cites a path
  inside the replaced clone directory) from an ordinary COMPILE-ERROR/
  RUNTIME-ERROR in the block's own generated `main.go`.

**Design fix caught before writing tests**: my first `acquire()` draft
treated an unresolvable replace path as a hard failure
(`{"ok": False}`) -- which would have blocked EVERY stdlib-only block
(`fmt.Println`, no product import at all) from ever reaching compile/execute,
since `BaseRunner._climb` short-circuits on `acquired.get("ok")` being
falsy. Caught this while designing the test fixtures (a pure-stdlib
example legitimately has no module to resolve) and fixed `acquire()` to
always succeed, matching the real script's existing tolerance for a missing
replace path.

**No shared-global-mutation risk**: `_infer_imports`/`_wrap_fragment` gained
an additive `extra_heuristics` parameter (defaults to `None`, which falls
through to the existing `_EXTRA_IMPORT_HEURISTICS` global exactly as before
-- zero behavior change for `check_go_code_blocks.py`'s CLI or any existing
test). `GoRunner` passes its own instance-level heuristic list instead,
since one process may construct runners for more than one family (this
class's own test suite does) and must not have one instance's alias leak
into another's via a shared mutable global.

## Tests

New `scripts/pipeline/tests/test_example_verification_runners_go.py` (14
tests, skipped if `go` isn't on PATH): `starts_chain` heuristic (4),
construction fallback (1), `classify` (3), real `compile()` via real `go vet`
against stdlib-only code -- clean pass and a genuine undefined-identifier
compile error (2), real `execute()` via real `go run` -- clean pass and a
genuine integer-divide-by-zero runtime panic (2), and two full end-to-end
proofs through `BaseRunner(GoRunner(...)).run(...)` -- a clean block
reaching real `proof_tier=3`, and a broken block correctly classified
`COMPILE-ERROR` through the whole tier ladder (2). All 14 real (no mocked
subprocess calls) and green. Full regression:
`test_ci_go_code_blocks.py` (23) + this file (14) +
`test_example_verification_runners_base.py` (existing base-class suite) =
55 tests, all green. `check_monkeypatch_lint.py`: 0 violations.

Note: this file isn't in C5's literal `allowed_paths` list either (which
only names `test_ci_go_code_blocks.py`), for the same reason C6's
`test_promote_snippets.py` covered its sibling consumers -- there is no
separate slot for a new runner's own test file, and shipping `GoRunner`
with zero test coverage would be irresponsible. Named to match the existing
`test_example_verification_runners_{python,typescript,base}.py` convention.

## What remains deliberately deferred (disclosed, not silently dropped)

1. **Pre-commit Step 18 generalization** -- named in this taskcard's own
   title, but structurally blocked: `pre-commit-audit.sh` needs a
   forbidden-path override token and isn't in `allowed_paths`; the
   `smoke_test.py` flags the plan's design calls for (`--exit-codes`,
   `--blocking-platforms`) don't exist (C4's actual scope was `--max-tier`/
   `--json` only) and `smoke_test.py` isn't in `allowed_paths` either.
2. **Flipping `max_tier`/`precommit_blocking` in `registry.py` +
   `platform_capabilities.yaml`**. Neither file is in `allowed_paths`.
3. **A real pilot of `GoRunner` against actual product content**
   (cells/go, pdf/go). Every test here uses stdlib-only synthetic code
   deliberately -- a real product example (`doc.Save("output.pdf")`, reading
   an upstream test fixture file) would need the same fixture-staging
   support `acquire.stage_fixtures()` already gives Python/TypeScript, which
   `GoRunner` does not have yet. Building that is itself the substantial,
   separable piece of work the plan's own "Language runner notes" describes
   as fixture engineering following the `_v2_fixture_package` convention --
   attempting a real pilot without it would mostly surface
   FIXTURE-UNAVAILABLE-class noise, not a meaningful proof.

Items 1 and 2 are structural (outside `allowed_paths`, matching the exact
precedent C7 set when `api.py` turned out to be unassigned to any taskcard).
Item 3 is a genuinely separable follow-on, parallel to how C11-C14's own
fixture engineering is scoped as part of each of THOSE taskcards, not
smuggled into C5.

## Disposition

Given the taskcard's CORE deliverable -- a real, working, tested Go
`LanguageRunner` -- is now built and proven (tier 1/2/3, real subprocess
calls, zero regressions), and the 3 remaining gaps are either structurally
blocked outside this taskcard's `allowed_paths` or a genuinely separable
follow-on, recommending this checkpoint proceed to independent review with
a view to CLOSING C5 (disclosing all 3 gaps explicitly, the same posture
C6/C7 used for their own disclosed gaps) rather than another checkpoint --
final call deferred to the reviewer's verdict.
