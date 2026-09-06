# Upstream Issues — Aspose.Cells FOSS for Rust

Verified against `runs/.clone_cache/aspose_cells_rust/` (pinned SHA
`0339b7e7dcb65c3ac0f77ddbe0effb69c83f0e2e`, per `knowledge/cells/rust/merged/model.yaml`).
All items below are real, disclosed, and sourced directly from the clone cache — none
invented.

## No automated test suite ships in the repository
- **Severity**: INFORMATIONAL
- **Evidence**: `cargo test --all-targets` reports 0 tests; there is no `tests/`
  directory and no benchmark assertions. The repository's own `AGENTS.md` discloses this
  directly under its "Testing" heading and explains why: a prior test was removed because
  it depended on an `Input/roundtrip/*.xlsx` fixture file that was never committed to the
  repository, so it failed on every fresh clone.
- **Impact**: contributors cannot rely on `cargo test` to catch regressions; correctness
  is exercised only through the `samples/` programs, three of which
  (`sample_basic`/`sample_loading`/`sample_styles`) are smoke-tested in CI on Linux.
- **Not fixable here because**: rebuilding a real test suite is upstream source work, not
  something a README edit can supply; this candidate's Development and Testing section
  states the real situation plainly instead of implying an automated suite exists.

## Old README's local-build path did not match the real repository name
- **Severity**: INFORMATIONAL
- **Evidence**: the old README's Installation section instructed
  `cd "Aspose.Cells FOSS for Rust - Github"` after cloning — a directory name that does
  not match the real GitHub repository name. A literal clone of the real remote (recorded
  as `repo_url` in `knowledge/cells/rust/merged/model.yaml`) produces a directory named
  `Aspose.Cells-FOSS-for-Rust`, not the string the old text told readers to `cd` into.
- **Impact**: a reader following the old instructions verbatim would hit a "no such
  directory" error immediately after cloning.
- **Not fixable here because**: it is old README wording, not an upstream source defect;
  this candidate's own Installation section already uses the correct, repository-derived
  directory name instead of carrying the mismatch forward.

## Crate is not yet published to crates.io
- **Severity**: INFORMATIONAL
- **Evidence**: `data/package_registry.json` records `verification.published: false` for
  `aspose-cells-foss-rust`.
- **Impact**: `cargo add aspose-cells-foss-rust` does not work yet; consumers must use a
  Git or path dependency.
- **Not fixable here because**: publication timing is an upstream/maintainer decision;
  this candidate's Installation section documents the real git-dependency workaround
  rather than a live `cargo add` command, and no crates.io version badge was added for
  the same reason.
