## Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
> Investigation/plan file: `C:/Users/prora/.claude/plans/do-another-round-of-indexed-graham.md`
> Status: **CLOSED** (2026-09-06)
> Mission contract: registered via the durable archive path (GOV-02 retroactive
> registration rule) — root `MISSION_AUTHORITY.yaml` was held by `MT058` at
> mission-open time.
> Durable taskcards: `reports/plan_state/MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION/taskcards.jsonl`
> (14 records, C1–C14, all CLOSED)

### Context

Example verification was a per-language stub/real split living inside
`readme-refresh` alone, absent from `launch-product` and `refresh-product`. This
mission centralized it into one shared `lib/example_verification/` package used
uniformly by S-63, S-120, S-49 Stage 7, S-84's `verify_run`, pre-commit, and
knowledge promotion — closing root causes found across 4 investigation rounds: stub
runners silently reachable, a non-enforcing gate, a lexical-only hard gate, doc/code
drift, rerun non-determinism, and no shared module across launch/refresh/readme-refresh.

### What was built (C1–C14, all closed)

- **C1**: Canonical CommonMark fence tokenizer + CI workflow.
- **C2**: result/policy/registry/syntax/cache schema + shared tree-sitter loader fix.
- **C3**: Extracted toolchain/acquire/runners-base/python/typescript from S-120
  behind a parity gate.
- **C4**: Rebuilt S-63 code-smoke CLI over the new package + capability site.
- **C5**: Go runner, extracted from `check_go_code_blocks.py`; generalized pre-commit
  Step 18.
- **C6**: Snippet `code_sha256` + post-promote proof sweep + provenance enforcement.
- **C7**: Wired S-120 dispatch/gate/report to the package.
- **C8**: `example_execution` content_eval evaluator (EXPERIMENTAL, then DEFAULT).
- **C9**: `refresh_run` advisory `example_execution` validation field.
- **C10**: `body_refresh` verified-snippet selection fix (disclosed: portfolio-wide
  inert until products are re-promoted).
- **C11**: .NET runner.
- **C12**: Java runner.
- **C13**: Rust runner — honest stub above tier 1 (rustup not installed on this
  workstation, disclosed rather than faked).
- **C14**: C++ runner (CMake subset, BUILD-VERIFIED-ONLY floor).

Each runner landed with independent-reviewer fast-follow rounds fixing real bugs the
review found (e.g. C12 had 3 rounds of fast-follow fixes; C5, C13 each had one).

### Deliberately out of scope

ST-190/ST-187 (clone-cache and `target_section` staleness) — referenced only, not
fixed, per this mission's own Decision 3. A portfolio-wide "verification" field
rename — documented only, per Decision 2.

### Commits

`7ff4f5ef0d`, `7b4b7367d6`, `cb4f1d9da0` (C5); `6cf98e6808` (C11); `8f3941a2f2`,
`fad43671a5`, `1fa2cf2205`, `4e8f4a94e2`/`c0450e8393` (C12 + 3 fast-follows);
`a77ac97740`, `a468b8c15b` (C13); `d5ffe0e17f`, `b4b200f38e` (C14); `57cdbf22e9`,
`2391394978` (C8); `ea97d15802` (C9); `f9b8bd2e2b`, `0c43674497` (C10);
`51b27751a2` (C6 fast-follow) — all pushed to `origin/main`.
