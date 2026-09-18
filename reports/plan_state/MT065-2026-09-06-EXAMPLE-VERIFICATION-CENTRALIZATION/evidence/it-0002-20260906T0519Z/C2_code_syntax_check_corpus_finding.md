# Finding: code_syntax_check.py performs ZERO real syntax parses today for
# java/typescript/cpp content, portfolio-wide

Discovered while executing taskcard C2's explicit instruction to "run a
corpus before/after" measurement before wiring `content_eval/evaluators/
code_syntax_check.py` to the new shared tree-sitter loader
(`lib/example_verification/syntax.py`).

## Measurement

Ran a read-only pilot (`_scratch_mt065_c2_code_syntax_check_corpus.py`,
this directory) over every real content page under a `java`, `typescript`,
or `cpp` platform directory (59,180 files scanned; 31,555 code blocks
actually reach the classification logic after the evaluator's own
skip-langs/short-block/noqa/declaration-only filters):

| | OLD (today's live loader) | NEW (shared syntax.py loader) |
|---|---|---|
| PASS | 0 | 30,341 |
| FAIL | 0 | 533 |
| WARN-BRACKET (heuristic fallback, no real parse) | 30,874 | 0 |

**100% of these 31,555 blocks currently fall through to the WARN-only
balanced-delimiter heuristic** — `code_syntax_check.py`'s own loader
(`code_syntax_check.py:52-127`) has never actually performed a real
tree-sitter parse for a java, typescript, or cpp block in this repo's
history, because it has no `tree_sitter_language_pack` fallback for those
three languages (only rust does) and no standalone wheel for them is
installed in this venv either (confirmed: only `tree_sitter_c_sharp` is
installed as a standalone wheel). This matches RC17's live probe exactly
(`{c#, cs, csharp, rs, rust}` are the only tags that ever got a real
parser) but this pilot is the first time the portfolio-wide consequence —
533 real syntax defects, invisible to grading for the life of this
evaluator — has been measured.

## Why this was NOT wired live in this commit

Wiring `code_syntax_check.py` to the shared loader requires bumping
`EVALUATOR_LOGIC_VERSION`/`EVALUATOR_FREEZE_VERSION` in
`scripts/pipeline/content_eval/__init__.py` (per this repo's own frozen-
canonical-evaluator discipline, `check_evaluator_freeze.py`,
`GRADE_CONTRACT.md`) — **that file is not in taskcard C2's
`allowed_paths`** (it is only in **C8**'s, per the taskcard seed rows).
Beyond the scope boundary, the measured delta itself is a real reason for
caution, not just a technicality:

## The 533-block delta is NOT a clean "these are all real bugs" set

Direct reads of two sampled "new FAIL" blocks found two DIFFERENT
false-positive root causes, not genuine syntax defects:

1. **Ellipsis placeholder convention**:
   `content/docs.aspose.org/uk/pdf/java/developer-guide/security.md:90` —
   `byte[] key = ...; // 128, 192, or 256-bit key`. This repo's content
   generator uses a literal `...` as a documentation placeholder for "some
   value here" — not valid Java syntax, but an intentional convention, not
   a defect. `_is_declaration_only_snippet` does not catch this shape (it
   is not a declaration).
2. **CMake snippets mislabeled with a `cpp` fence tag**:
   `content/kb.aspose.org/en/cells/cpp/faq.md:134` — a `` ```cpp `` block
   whose content (`cmake_minimum_required`, `project(...)`,
   `add_subdirectory(...)`) is CMakeLists.txt syntax, not C++ at all. A
   real C++ parser correctly flags this as invalid C++ — because it isn't
   C++; the fence tag is simply wrong.

Both are real, previously-invisible defects in their own right (one a
content-generation convention gap, one a fence-tag mislabeling bug), but
neither is "the example code is broken" in the sense a reader of this
canonical evaluator's FAIL would assume. Switching this evaluator live
without first separating genuine syntax defects from these (and possibly
other, unexamined) false-positive classes would produce a large batch of
misleading grade regressions across the portfolio.

## Decision

`code_syntax_check.py` and `smoke_test.py` still each define their own
`_ts_parser_for`; `smoke_test.py`'s now delegates to the shared loader
(see `C2_promotion_gate_decision.md`), but `code_syntax_check.py`'s was
deliberately left untouched — it still uses its own, narrower loader
(unaffected by this commit) — pending:
1. A session with `content_eval/__init__.py` in scope (naturally C8, which
   already touches that file) to perform the ELV bump.
2. Categorizing the 533-block delta by root cause (genuine syntax defect
   vs. ellipsis-placeholder vs. mislabeled-fence-tag vs. others not yet
   sampled) before or immediately after the switch, the same way prior
   sprints in this repo have hand-triaged large finding batches rather
   than accepting them as an undifferentiated block.

Full data: `c2_code_syntax_check_corpus_report.json` in this directory
(includes 20 sample delta files and 20 sample "new FAIL, previously
WARN-only" locations for whoever picks this up).
