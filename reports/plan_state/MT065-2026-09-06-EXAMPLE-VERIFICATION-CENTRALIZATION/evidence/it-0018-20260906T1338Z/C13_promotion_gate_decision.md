# C13 promotion gate decision — it-0018-20260906T1338Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C13 "Rust runner (rustup not installed here — honest stub above tier 1)"

## Verified precondition

Live, unmocked: `shutil.which("cargo")`, `shutil.which("rustc")`,
`shutil.which("rustup")` all return `None` on this machine — the one real,
confirmed toolchain gap this taskcard's own title names.

## What shipped this iteration

New `scripts/pipeline/lib/example_verification/runners/rust.py` -- `RustRunner`,
the `LanguageRunner` implementation for Rust, mirroring `GoRunner` (C5)'s
already-reviewed shape exactly:

- `canonical_lang = "rust"`, `ceiling_tier = 3` (architectural ceiling this
  code is designed to prove, matching python/typescript/go/.NET/Java --
  NOT a claim that tier 3 is reachable today; the live toolchain check
  happens inside `compile()`/`execute()`, not the class attribute).
- `starts_chain()`: True (fresh example) when a block declares its own
  `fn main(` or leading `use`; False (continues the previous block's local
  variables) otherwise. Confirmed against real content before finalizing
  (same discipline the plan requires for Go's own heuristic): a real pilot
  page (`working-with-spreadsheet-management.md`) has a block declaring
  `let mut workbook = Workbook::new(); { ...; let sheet = worksheets.get(0)?;
  sheet.set_name(...)?; }` immediately followed by a LATER block using
  `sheet.get_cells_mut()` with no `fn main`/`use` of its own -- a genuine
  chain continuation this heuristic correctly detects (see pilot below).
- `acquire()`: mirrors `GoRunner.acquire()` exactly -- always succeeds
  (pure staging: resolves `crate_name`/`lib_ident`/`replace_path`, no
  subprocess call that could fail on its own).
- `compile()`/`execute()`: the ONLY methods that discover the real,
  live toolchain state, via `shutil.which("cargo")` -- returns
  `{"reason": "TOOLCHAIN-UNAVAILABLE", "detail": "cargo not found on PATH"}`
  when absent (today, always, on this machine) -- real, unmocked, tested
  live. `CARGO_NET_OFFLINE=true` (cargo's own real, documented offline env
  var) mirrors `GoRunner`'s `GOPROXY=off` safety rationale for the
  identical reason.
- `classify()`: the same file-citation-basename pattern as Go/.NET/Java's
  `classify()`, applied to rustc's `--> file:line:col` diagnostic format.
  **Disclosed, honest limit**: unlike every prior runner's `classify()`,
  this one was NOT live-verified against a real rustc failure -- no
  toolchain exists on this machine to produce one. Built defensively:
  no file citation at all defaults to ordinary `COMPILE-ERROR`, never a
  false `UPSTREAM-BROKEN` (tested explicitly).
- `_resolve_rust_crate_for_family`/`_lib_ident_for_crate`: derive the real
  Cargo crate name from `merged/model.yaml`'s `product_name` field (merged
  preferred over gitignored `scout`, same tier preference as Go's own
  `_resolve_go_module_for_family`), and the crate's `[lib]` identifier via
  Cargo's own universal hyphen-to-underscore convention. **Verified live,
  not assumed**: `cells/rust`'s `product_name: aspose-cells-foss-rust`
  matches the real `runs/.clone_cache/aspose_cells_rust/Cargo.toml`'s own
  `[package] name` byte-for-byte, and the derived lib ident
  `aspose_cells_foss_rust` matches that same file's `[lib] name` exactly
  -- checked directly against the real clone before writing this module,
  pinned as a test (`test_real_cells_rust_product_name_matches_the_real_
  clone_cache_crate`).
- `_wrap_fragment()`: wraps a bare statement fragment (real docs pages
  frequently have these, confirmed live) in a `Result`-returning `main`,
  injecting at most one wildcard `use {lib_ident}::*;` -- deliberately
  simpler than Go's per-symbol `_infer_imports` heuristic, since there is
  no live toolchain here to iterate a more precise one against (disclosed
  in the module's own docstring).

## Disclosed, deliberate scope reduction (matching Go's own precedent exactly)

Only the unpublished/local-clone acquire path (a Cargo.toml `path = "..."`
dependency against `runs/.clone_cache/`) is implemented. The plan's
`published: cargo add {crate}@{version}` branch (a real crates.io resolve)
is NOT built -- the one real Rust product (cells/rust) isn't published to
crates.io today, and there is no toolchain here to prove that branch
against even if it were. This is the identical shape and identical
justification `GoRunner`'s own docstring already discloses for its
`go get {module}@{version}` branch.

## Disclosed: registry.py / platform_capabilities.yaml NOT flipped

`scripts/pipeline/lib/example_verification/registry.py` is **not** in this
taskcard's `allowed_paths` (only `runners/rust.py`,
`config/platform_capabilities.yaml`, and this taskcard's own test file
are) -- the same structural gap already found and disclosed for C5/C11/C12
(none of those taskcards' `allowed_paths` include `registry.py` either).
`check_platform_capabilities.py:check_example_verification()` diffs
`platform_capabilities.yaml`'s `example_verification` block against
`registry.PLATFORM_CONTRACT` field-for-field and FAILs on any mismatch --
so flipping `platform_capabilities.yaml`'s `runner_module: null -> rust`
alone, without also touching `registry.py` (out of scope here), would
introduce a new, real CI failure rather than fix anything. Verified this
check currently passes cleanly (`check_platform_capabilities.py: PASS -- 0
findings`) and left both files untouched to keep it that way. Honestly,
`max_tier`/`offline_tier` staying at 1 is also CORRECT today regardless --
this machine cannot prove tier 2/3 -- so the only field that's arguably
stale is `runner_module`, and it can't be fixed without a `registry.py`
change no C5/C11/C12/C13/C14 taskcard row is scoped to make.

## Tests

30 new focused tests in `scripts/pipeline/tests/test_example_verification_
rust.py`: crate-name/lib-ident resolution (including a live check against
the real cells/rust product), main-detection/wrap/needs-wrap, wrapped-
fragment syntax validity (via the shared, already-verified tree-sitter
loader), replace-path resolution, `starts_chain` (matching real content),
`classify` (synthetic rustc-shaped output, both directions plus a safe-
default-when-no-citation case), acquire/compile/execute (real, unmocked
TOOLCHAIN-UNAVAILABLE), and 3 full `BaseRunner` integration tests (default
policy tier-1-only PASS and SYNTAX-ERROR; forced max_tier=3 producing the
honest TOOLCHAIN-UNAVAILABLE the promotion gate itself asks for). All 30
pass. Scoped regression subset (all 4 sibling runner test files: rust, go,
dotnet, java) — 87/87 pass, no regressions.

## Pilot (real content, cells/rust — the only real Rust product)

Extracted the 3 real rust code blocks from `content/docs.aspose.org/en/
cells/rust/developer-guide/working-with-spreadsheet-management.md` via the
canonical tokenizer and ran them through `BaseRunner(RustRunner("cells"))`:

- **Default policy** (registry.py's real, current `max_tier=1`): all 3
  blocks PASS at tier 1 — real syntax check against real content, matching
  "tier 1 green without rustup" exactly.
- **Forced `max_tier=3`** (simulating what a rustup-equipped machine's
  policy would request): block 0 gets an honest
  `BLOCKED-WITH-REASON / TOOLCHAIN-UNAVAILABLE`, detail "cargo not found on
  PATH", proof_tier 2 (a real attempt was made and honestly failed); blocks
  1-2 correctly resolve as `DEPENDS-ON-FAILED-BLOCK` — the SAME real
  chain-continuation relationship confirmed by reading the page's own prose
  (block 1/2 use `sheet.get_cells_mut()`, a variable block 0 declares),
  proving `starts_chain()`'s heuristic is correct against real, not just
  synthetic, content.

## Promotion gate

"tier 1 green without rustup; tier >= 2 an honest TOOLCHAIN-UNAVAILABLE
until rustup is installed" — satisfied, both empirically (real pilot
above) and structurally (the `BaseRunner` integration tests pin this
exactly). Rollback trigger is explicitly "none — toolchain absence is
expected, not a failure," so there is nothing to roll back.

## Disposition

Recommending CLOSE, pending independent review: the runner is a faithful,
structurally-consistent port of the already-reviewed `GoRunner` design for
the one real toolchain-gap language in this rollout: tier 1 is real and
proven on real content; tier 2/3 honestly and correctly report toolchain
absence rather than a silent pass or a crash; every part that COULD be
verified without a toolchain (crate-name/lib-ident resolution, wrap
correctness, chain heuristic, classify's defensive default) was verified
against real repository data, not left as an unverified guess; every part
that genuinely cannot be verified without cargo (a real successful
compile/execute, and classify()'s real-vs-synthetic accuracy) is disclosed
honestly, not silently presented as proven.
