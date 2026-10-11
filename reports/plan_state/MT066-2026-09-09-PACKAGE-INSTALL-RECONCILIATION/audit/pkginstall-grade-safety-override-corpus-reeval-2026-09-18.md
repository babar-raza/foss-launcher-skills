# PKGINSTALL-GRADE-SAFETY-OVERRIDE — fresh full corpus grade-distribution shift (2026-09-18)

Mission `MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION`, taskcard `TC-PKG-07-01`
(spawned by B0 decision 1, 2026-09-17: `GRADE_CONTRACT.md` §10 sign-off APPROVED with a
scope condition — the affected pages must be fixed back to A, not left at F). This
supersedes `reports/audit/pkginstall-grade-safety-override-corpus-reeval-2026-09-10.md`
(local/uncommitted, never durably tracked, a week+ stale as of this run) with a fresh,
committed measurement against current HEAD.

**Durable-location note:** `scripts/pipeline/config/git_tracking_policy.yaml` (confirmed
live via `git_tracking_policy_sync.py --list-tracked-prefixes`) tracks only
`reports/audit/install-defect-sweep-latest/` under `reports/audit/`, not this path —
every other `reports/audit/*` file, including this one, is local-only by design (the
policy file's own comment on `reports/audit/st054/` confirms this is deliberate, not an
oversight — it explains why the 2026-09-10 predecessor was itself never committed).
Extending that policy is `TC-GOV-01`'s scope, not this taskcard's `Allowed` paths, so
this file stays local-only here for path-naming consistency with its predecessor, and
the durable, git-committed copy of this same report lives at
`reports/plan_state/MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION/audit/
pkginstall-grade-safety-override-corpus-reeval-2026-09-18.md` (that whole subtree is
already tracked, landed by this same mission's own `TC-GOV-01`).

**HEAD measured against:** `2928e45b5022cc61155d7504e96678cb19095c0d` (origin/main tip
at measurement time; re-fetched immediately before running to avoid measuring a stale
worktree — the prior fetch during this same session had already picked up one more
commit, `2928e45b50`, mid-run, and the worktree was fast-forwarded to it before the
final run below).

## Method

Read-only against `content/` (no `--write-grade`, no `content/` file was edited or
written) — this taskcard's own scope forbids any `content/` mutation; that is
TC-PKG-07-02/03/04's job.

1. Loaded every English-source page in the portfolio via
   `content_eval.loader.load_all_products()` — **9124 pages across 33 products** (up
   from 9103 pages on 2026-09-10: +21 pages, organic portfolio growth over the week,
   e.g. a newly-added font/python blog announcement post landed this same week).
2. For each page, ran `InstallRecipeEvaluator()._verify_publish_channel_claims()` and
   `._verify_no_unpublished_disclosure()` — the exact 2 checks in
   `SAFETY_OVERRIDE_FINDINGS`/`grade_config.yaml`'s `critical_categories`
   (`IR_PUBLISH_CLAIM`, `IR_UNPUBLISHED_DISCLOSURE` — confirmed unchanged in
   `content_eval/config.py`/`grade_config.yaml` at this HEAD).
3. Recorded each page's **current, stored** `grade:` frontmatter value as the "before"
   state.
4. Since both categories are `critical_categories`, `compute_grade_with_criticality()`
   still short-circuits to `F` unconditionally on any FAIL in either category (confirmed
   directly from the function body again at this HEAD, unchanged since 2026-09-10) — so
   the "after" grade for every affected page is `F` without a full re-run of every other
   evaluator.
5. **Cross-checked independently, twice:**
   - Called `install_defect_sweep.py::run_install_recipe_sweep()` directly (the actual
     registered, currently-reviewed production tool for this exact check pair,
     `PKGINSTALL-DEFECT-SWEEP-REDESIGN`) — identical totals and identical per-product
     breakdown to the ad hoc full-list script above.
   - Ran `pytest scripts/pipeline/tests/test_install_defect_sweep.py -q` fresh: **14
     passed**, confirming this HEAD's numbers match the tool's own pinned regression
     test (re-pinned 89→67 on 2026-09-17 by `TC-PKG-01-08-FIX`, commit
     `f695945946`-adjacent work).

## Result

**45 of 9124 pages** carry a FAIL in `IR_PUBLISH_CLAIM` or `IR_UNPUBLISHED_DISCLOSURE`
(all 45 are `IR_PUBLISH_CLAIM`; 0 are `IR_UNPUBLISHED_DISCLOSURE`, unchanged from
2026-09-10 — TC-16's remediation still holds). Total findings: **67**
`IR_PUBLISH_CLAIM` FAILs across those 45 pages (some pages carry more than one finding).

### Drift from the 2026-09-10 baseline

| Metric | 2026-09-10 (stale) | 2026-09-18 (this run) | Delta |
|---|---|---|---|
| Corpus size (English-source pages) | 9103 | 9124 | +21 |
| Affected pages | 58 | 45 | **-13** |
| Raw `IR_PUBLISH_CLAIM` findings | 89 | 67 | **-22** |
| Affected products | cited as 9 (see note) | 8 | -1 |

**Honesty note on the "58" figure:** this run's 45-page count is **not** a new
regression from a previously-verified 58 — it independently reconciles, exactly, with
two other numbers already on record in this same mission: (a) `backlog/BACKLOG.md`'s own
`PUBLISH-CLAIM-CONTRADICTION-001` row (written 2026-09-10, same day as the "58" report)
lists a **per-product file breakdown that itself sums to 45** (font/python 13, pdf/python
13, barcode/python 7, html/python 6, page/python 2, tex/python 2, cells/typescript 1,
3d/typescript 1 = 45), an internal inconsistency against that same row's own "58
distinct... files" headline sentence; and (b) `TC-PKG-01-08`'s independent review
(2026-09-17, this mission) re-pinned the raw finding count at exactly 67 with an
identical per-product breakdown to this run's. Given both independent cross-checks in
this run reproduce 45/67 exactly, and the *finding-count* trend (89→67, confirmed
already as a genuine organic improvement by `TC-PKG-01-08`'s own git-history check) points
the same direction as a page-count drop, the most defensible reading is that the
original "58" headline in the 2026-09-10 report did not match its own source data even
on the day it was written — not that pages regressed between then and now. This is
recorded here rather than silently reconciled, per this mission's own evidence
discipline; nothing below depends on resolving which historical number was right, only
on today's independently-double-checked 45/67 being accurate now.

### Portfolio-wide grade distribution

| Grade | Before | After | Delta |
|---|---|---|---|
| A | 8981 | 8938 | -43 |
| B | 96 | 95 | -1 |
| C | 44 | 43 | -1 |
| F | 1 | 46 | +45 |
| (missing `grade:` frontmatter) | 2 | 2 | 0 |
| **Total** | **9124** | **9124** | 0 |

### The 45 affected pages' own before-grade

| Before grade | Count |
|---|---|
| A | 43 |
| B | 1 |
| C | 1 |

All 45 move to **F** after this change (short-circuit, per Method step 4). The other
9079 pages are completely unaffected (0 findings in either category).

### Affected pages by product

| Product | Pages checked | Affected pages | `IR_PUBLISH_CLAIM` findings |
|---|---|---|---|
| 3d/typescript | 191 | 1 | 1 |
| barcode/python | 51 | 7 | 9 |
| cells/typescript | 133 | 1 | 1 |
| font/python | 302 | 13 | 21 |
| html/python | 275 | 6 | 12 |
| page/python | 167 | 2 | 2 |
| pdf/python | 293 | 13 | 19 |
| tex/python | 30 | 2 | 2 |
| **Total** | **1442** | **45** | **67** |

### Exact page list (45 pages)

#### 3d/typescript (1 page, 1 finding)
- `content/kb.aspose.org/en/3d/typescript/how-to-export-gltf-in-typescript.md` — grade A, 1 finding

#### barcode/python (7 pages, 9 findings)
- `content/blog.aspose.org/barcode/python/barcode-encode-options-python/index.md` — grade A, 1 finding
- `content/blog.aspose.org/barcode/python/barcode-rendering-svg-png-python/index.md` — grade A, 1 finding
- `content/blog.aspose.org/barcode/python/introducing-barcode-foss-python/index.md` — grade A, 1 finding
- `content/docs.aspose.org/en/barcode/python/getting-started/_index.md` — grade A, 2 findings
- `content/docs.aspose.org/en/barcode/python/getting-started/installation.md` — grade A, 2 findings
- `content/docs.aspose.org/en/barcode/python/getting-started/license.md` — grade A, 1 finding
- `content/kb.aspose.org/en/barcode/python/faq.md` — grade A, 1 finding

#### cells/typescript (1 page, 1 finding)
- `content/docs.aspose.org/en/cells/typescript/getting-started/installation.md` — grade B, 1 finding

#### font/python (13 pages, 21 findings)
- `content/blog.aspose.org/font/python/brotli-font-compression-python/index.md` — grade A, 1 finding
- `content/blog.aspose.org/font/python/eot-fonts-in-python/index.md` — grade A, 2 findings
- `content/blog.aspose.org/font/python/font-cff-in-python/index.md` — grade A, 2 findings
- `content/blog.aspose.org/font/python/font-core-management-python/index.md` — grade A, 2 findings
- `content/blog.aspose.org/font/python/font-tables-in-python/index.md` — grade A, 1 finding
- `content/blog.aspose.org/font/python/python-font-ttf-woff-library/index.md` — grade A, 3 findings
- `content/blog.aspose.org/font/python/ttf-fonts-in-python/index.md` — grade A, 2 findings
- `content/blog.aspose.org/font/python/type1-fonts-in-python/index.md` — grade A, 2 findings
- `content/blog.aspose.org/font/python/woff-fonts-in-python/index.md` — grade A, 2 findings
- `content/docs.aspose.org/en/font/python/getting-started/installation.md` — grade A, 1 finding
- `content/kb.aspose.org/en/font/python/how-to-work-with-tables-python.md` — grade A, 1 finding
- `content/kb.aspose.org/en/font/python/how-to-work-with-ttf-python.md` — grade A, 1 finding
- `content/kb.aspose.org/en/font/python/how-to-work-with-woff-python.md` — grade A, 1 finding

#### html/python (6 pages, 12 findings)
- `content/blog.aspose.org/html/python/html-cssom-in-python/index.md` — grade A, 3 findings
- `content/blog.aspose.org/html/python/html-dom-python/index.md` — grade A, 3 findings
- `content/blog.aspose.org/html/python/introducing-html-foss-python/index.md` — grade A, 3 findings
- `content/docs.aspose.org/en/html/python/_index.md` — grade A, 1 finding
- `content/docs.aspose.org/en/html/python/getting-started/installation.md` — grade A, 1 finding
- `content/kb.aspose.org/en/html/python/how-to-work-with-dom-python.md` — grade A, 1 finding

#### page/python (2 pages, 2 findings)
- `content/blog.aspose.org/page/python/introducing-page-foss-python/index.md` — grade A, 1 finding
- `content/kb.aspose.org/en/page/python/faq.md` — grade A, 1 finding

#### pdf/python (13 pages, 19 findings)
- `content/blog.aspose.org/pdf/python/pdf-document-management-python/index.md` — grade A, 1 finding
- `content/blog.aspose.org/pdf/python/pdf-engine-in-python/index.md` — grade A, 1 finding
- `content/blog.aspose.org/pdf/python/pdf-generated-in-python/index.md` — grade C, 1 finding
- `content/docs.aspose.org/en/pdf/python/getting-started/installation.md` — grade A, 1 finding
- `content/docs.aspose.org/en/pdf/python/getting-started/license.md` — grade A, 1 finding
- `content/kb.aspose.org/en/pdf/python/faq.md` — grade A, 1 finding
- `content/kb.aspose.org/en/pdf/python/how-to-add-pdf-security-signatures-python.md` — grade A, 2 findings
- `content/kb.aspose.org/en/pdf/python/how-to-create-generated-python.md` — grade A, 2 findings
- `content/kb.aspose.org/en/pdf/python/how-to-load-document-python.md` — grade A, 1 finding
- `content/kb.aspose.org/en/pdf/python/how-to-work-with-clustering-python.md` — grade A, 2 findings
- `content/kb.aspose.org/en/pdf/python/how-to-work-with-pdf-annotations-python.md` — grade A, 2 findings
- `content/kb.aspose.org/en/pdf/python/how-to-work-with-pdf-data-python.md` — grade A, 2 findings
- `content/kb.aspose.org/en/pdf/python/how-to-work-with-primitives-python.md` — grade A, 2 findings

#### tex/python (2 pages, 2 findings)
- `content/docs.aspose.org/en/tex/python/getting-started/installation.md` — grade A, 1 finding
- `content/kb.aspose.org/en/tex/python/faq.md` — grade A, 1 finding

## What this does NOT include

- This measurement covers only the 2 categories in `SAFETY_OVERRIDE_FINDINGS`. It does
  not re-run or re-score any other evaluator, and does not claim anything about grade
  drift from unrelated causes.
- No page's stored `grade:` frontmatter was modified by this measurement — `content/`
  was never written. Persisting each of these 45 pages' new `F` grade (a
  `--write-grade` pass) and, per B0 decision 1's scope condition, actually fixing the
  underlying `IR_PUBLISH_CLAIM` content defect so each page returns to its pre-override
  grade, are TC-PKG-07-02/03/04's job, not this taskcard's.
- Locale copies of these 45 English-source pages were not surveyed (matches
  `install_defect_sweep.py`'s own documented English-source-only scope) — a known,
  explicitly out-of-scope gap for a future pass, not silently expanded here.

## Reproduction

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -c "
from commands.ops.install_defect_sweep import run_install_recipe_sweep
r = run_install_recipe_sweep()
print(r['total_pages_checked'], r['total_publish_claim_contradiction_findings'], r['total_unpublished_disclosure_findings'])
"
# -> 9124 67 0
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m pytest scripts/pipeline/tests/test_install_defect_sweep.py -q
# -> 14 passed
```

Full machine-readable per-page detail (findings' exact messages/line numbers) is
available in this run's working JSON; not included verbatim here to keep this report
reviewable, but reproducible byte-for-byte from the commands above against the same
HEAD.
