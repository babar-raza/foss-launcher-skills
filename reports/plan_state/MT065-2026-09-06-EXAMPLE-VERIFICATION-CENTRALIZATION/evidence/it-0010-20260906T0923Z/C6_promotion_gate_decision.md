# C6 promotion gate decision — it-0010-20260906T0923Z

Mission: MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION
Taskcard: C6 "Snippet code_sha256 + post-promote proof sweep + provenance enforcement"

## What shipped this iteration

1. **`promote.py:_promote_snippets`** — every promoted snippet entry gains a
   deterministic `code_sha256: {exact, norm}` field, computed from the just-copied
   snippet file's own text (no execution; `norm` uses
   `lib.example_verification.code_fences.normalize_content`, the same normalization the
   central package's `CodeBlock.sha256_norm` uses). Gracefully omits the field (never
   crashes) when an index entry's referenced file is missing on disk.
2. **`audit/snippets.py:verify_snippet_coverage`** — rewritten from a fuzzy
   `classes_used`/`methods_used` token-intersection heuristic to an exact `sha256_norm`
   lookup into the snippet index's new `code_sha256.norm` field, using
   `lib.example_verification.code_fences.enumerate_code_blocks` (the canonical
   tokenizer, replacing this file's own ad hoc `` ``` ``-toggle state machine — one of
   the ~40 duplicate fence parsers RC19 catalogued). SKIPs loudly (one INFO finding, not
   silent) when a product's index has no `code_sha256` anywhere yet, per the plan's
   explicit design ("before that it SKIPs loudly"), rather than falling back to the old
   fuzzy heuristic it replaces. Still default-off (`audit/runner.py --check-snippets`,
   unchanged) — the plan is explicit that this should flip on only after a portfolio-wide
   sweep has populated `code_sha256`, which hasn't happened yet (see deferred items
   below).
3. **`launch_gate.py:gate_l15_snippet_syntax`** — now reads each snippet's
   `execution_proof.tier` (from `PLATFORM_CONTRACT[platform].max_tier`) when present,
   WARNing on any *proven* snippet below the contract tier and ignoring unproven entries
   (a partial sweep is progress, not failure). Falls back **unchanged** to the original
   +/-2 bracket-balance heuristic when no entry in a product's index has
   `execution_proof` yet — which is every product today, since the sweep hasn't run
   anywhere. This is a deliberate deviation from the plan's literal "SKIP if the field is
   absent" wording: L-15 is a real, currently-active launch gate for already-launched
   products, and a blanket SKIP portfolio-wide (today's actual state) would silently
   weaken a live gate rather than rewrite it — the same "keep old and new, no regression"
   posture C3 used. The bracket-heuristic path's own tests
   (`test_gate_l01_l07.py::TestGateL15SnippetSyntax`, outside this taskcard's
   `allowed_paths`) pass unchanged.
4. Preserved `audit/snippets.py:_check_code_block_snippets` (the old heuristic function),
   unused by the rewritten `verify_snippet_coverage` but still present, because
   `audit/__init__.py` re-exports it by name and that file is **outside C6's
   `allowed_paths`** — deleting the function would break that import.
5. Tests: new `scripts/pipeline/tests/test_promote_snippets.py` (10 tests) covering all
   three pieces above with real hashing, real file I/O, and real edge cases (missing
   snippet file, CRLF/reindent-drift hash stability, mixed proven/unproven entries).
   Full regression: all 6 pre-existing `test_promote_*.py` suites +
   `test_gate_l01_l07.py` + `test_launch_gate.py` = 190 tests, all green, plus 96 more
   passing in the broader `audit`-adjacent test files
   (`test_audit.py`, `test_audit_frontmatter_schema.py`, `test_audit_faq_structure.py`,
   `content_eval/test_audit_chains.py`) as a sanity check on the shared `audit` package.
   `check_monkeypatch_lint.py` run directly against every changed file: 0 violations.

## What was deliberately deferred (and why)

1. **`refresh_knowledge.py`'s post-promote sweep call** (the plan's
   `_run([python, smoke_test.py, family, platform, "--snippets", "--max-tier", "auto",
   "--stamp-index", "--json"], "verify-snippets")`). Not built: `smoke_test.py` has no
   `--snippets`/`--stamp-index`/`--max-tier auto` flags today (C4's own actual delivered
   scope, per `C4_promotion_gate_decision.md`, was `--max-tier {1,2}` and `--json` only —
   nothing else from the plan's fuller flag list). `smoke_test.py` is also **not in C6's
   `allowed_paths`**, so even if I wanted to add those flags I could not do so from this
   taskcard. Building the actual index-stamping logic additionally needs
   `lib/example_verification/api.py`'s `stamp_snippets_index`, which — like C7's `api.py`
   gap — exists only in the plan's aspirational module tree and is assigned to **no
   taskcard** in the current C1-C14 rollout. `refresh_knowledge.py` itself was left
   completely untouched this iteration (allowed but not required to touch every file the
   taskcard lists).
2. **`execution_proof` population** (the actual "post-promote proof sweep"). Since the
   sweep mechanism (item 1) doesn't exist, no product's `snippets_index.json` carries
   `execution_proof` yet anywhere in the real portfolio — both new consumers
   (`audit/snippets.py`, `launch_gate.py`) are written to use it correctly once it
   exists, and both degrade honestly (loud SKIP / unchanged bracket fallback,
   respectively) in its absence.
3. **The `tex/python` real pilot + portfolio inheritance-rate measurement** the stage
   matrix describes. Not run: `_promote_snippets` is a pure function of
   `(scout_dir, merged_dir)` with no product-specific state, and is proven directly via
   10 focused unit tests with real hashing and real edge cases (this is a stronger,
   faster proof than one product run). Running the real `promote("tex", "python")`
   against the actual repo would write to **git-tracked** files under
   `knowledge/tex/python/merged/` (confirmed via `git ls-files` —
   `merged/snippets/snippets_index.json` is tracked, unlike most of `knowledge/`), and
   `knowledge/**` is **not in C6's `allowed_paths`**. Building a safe isolated-copy
   harness to pilot without touching the real tracked tree was judged out of scope for a
   single iteration given the risk of a rushed harness introducing its own bugs. A real
   portfolio sweep is, in any case, described in the plan itself as a multi-hour
   operational activity ("portfolio ~3-5 h serial once"), not a single code-taskcard
   deliverable.

## Disposition

Checkpointing C6 as `IMPLEMENTED` → `FOCUSED_VERIFIED` this iteration (not closing) —
an independent reviewer should confirm the L-15 fallback design and the `api.py`/
`allowed_paths` deferrals are sound, and a later taskcard/session should either (a) get
`allowed_paths` amended (or a new taskcard opened) to add the `smoke_test.py` flags +
`api.py`'s `stamp_snippets_index` + run the real portfolio sweep, or (b) explicitly
accept the current state (code_sha256 always populated going forward at promote time;
execution_proof-based checks ready but dormant) as sufficient for now.
