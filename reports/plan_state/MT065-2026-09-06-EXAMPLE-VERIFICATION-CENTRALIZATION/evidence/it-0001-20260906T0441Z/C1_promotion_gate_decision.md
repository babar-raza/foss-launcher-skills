# C1 promotion-gate decision

Stage matrix row (governing plan): "diff = 0, or every difference is an
explained CommonMark case, recorded as evidence" / rollback trigger
"unexplained diff → keep old regexes as the active path, package ships
unused."

## Pilot result

`c1_fence_parity_report.json`: 158,543 / 158,863 files (99.8%) identical.
320 files diverge. Root-caused precisely (see
`FINDING_orphaned_code_fence_defect.md` in this same directory): every
divergence traces to a pre-existing content defect (a code example with no
opening fence, leaving an orphaned closing fence), confirmed by direct
reads of two representative files. Zero files under `content/` use
`c#`/`c++` fence tags (RC6's previously-unmeasured half is now measured:
0/158,863).

## Decision: do NOT switch `content_eval/models.py` this iteration

The 320-file diff is **explained** (root cause identified precisely), but
it is **not a CommonMark case** — CommonMark has no defined behavior for
"a closing fence with no matching opener," because that input is simply
malformed. The promotion gate's literal wording ("explained CommonMark
case") does not cover this class, so the honest reading is that this falls
to the rollback trigger: keep the old regex-based parser as the active
path in `content_eval/models.py`, and ship `code_fences.py` as new, fully
tested, but not-yet-wired library code. `content_eval/models.py` was left
untouched in this commit (it remains in C1's `allowed_paths` for a future
iteration once the orphaned-fence defect is fixed at the content layer and
the parity diff can be re-measured at or near 0).

This is a conservative, evidence-based call, not a default: switching
would not have broken anything more than it already would have (both
parsers already resync arbitrarily on malformed input, and content_eval's
downstream Finding line numbers on these 320 files are already whatever
the old parser happens to produce today) — but there is no positive reason
to introduce a *different* arbitrary resync behavior on 320 real,
already-published pages without a human decision to do so, when the
straightforward alternative (fix the missing fence at the source, then
switch) removes the ambiguity entirely instead of trading one arbitrary
behavior for another.

## What shipped

- `scripts/pipeline/lib/example_verification/__init__.py` (new;
  `RUNNERS_MODULE_VERSION = "1"`)
- `scripts/pipeline/lib/example_verification/code_fences.py` (new;
  `enumerate_code_blocks`, `block_spans`, `CodeBlock`, `canonicalize_lang`,
  `normalize_content`)
- `scripts/pipeline/tests/test_example_verification_code_fences.py` (new;
  18 tests, all passing)
- `.github/workflows/example-verification-tests.yml` (new; ubuntu +
  windows jobs, explicit file list per this repo's CI convention)
- `scripts/pipeline/core/markdown.py`: deleted the orphaned, unimported
  `_CODE_FENCE_RE` (confirmed zero importers repo-wide before deleting)

## Explicitly deferred to later taskcards (not a gap in C1)

- `scripts/pipeline/config/registry.yaml` registration for
  `lib/example_verification/code_fences.py` — **not** done in this commit.
  Drafted, then reverted (`git checkout -- scripts/pipeline/config/registry.yaml`)
  after noticing it is outside C1's `allowed_paths` — the taskcard seed
  rows put `scripts/pipeline/config/registry.yaml` in **C4**'s
  `allowed_paths`, not C1's, so the whole package gets registered there
  in one pass alongside the S-63 CLI rebuild. A drafted entry (kind:
  library, owner_domain: content-quality, requires_test: true,
  test_targets: [test_example_verification_code_fences.py]) is preserved
  in this evidence run's git history (see the reverted diff in this
  iteration's shell transcript) for C4 to reuse verbatim.
- `backlog/inbox.md` ST-192 entry for the orphaned-fence content defect —
  drafted, then reverted for the same allowed_paths reason. Full drafted
  entry text is in `FINDING_orphaned_code_fence_defect.md` in this
  directory, ready for a session with `backlog/` in scope to file.
