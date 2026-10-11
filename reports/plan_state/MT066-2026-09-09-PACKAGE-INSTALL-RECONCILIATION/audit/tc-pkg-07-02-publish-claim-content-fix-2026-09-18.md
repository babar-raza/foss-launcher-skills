# TC-PKG-07-02 -- IR_PUBLISH_CLAIM content correction for 45 English-source pages (2026-09-18)

Mission `MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION`, taskcard `TC-PKG-07-02` (grade
lane, worktree `agent-a4d252e82ff92bf75`). Follows `TC-PKG-07-01`'s fresh re-eval
(`pkginstall-grade-safety-override-corpus-reeval-2026-09-18.md`, same directory).

## Result

| | Start (fresh re-run, HEAD `be25deeeed`) | End |
|---|---|---|
| Pages with an `IR_PUBLISH_CLAIM` FAIL | **45** | **0** |
| Raw `IR_PUBLISH_CLAIM` findings | **67** | **0** |
| `IR_UNPUBLISHED_DISCLOSURE` findings | 0 | 0 (no disclosure introduced) |
| Portfolio pages checked | 9124 | 9124 |

All 45 pages / 67 findings are fixed -- nothing is deferred from this pass. Scope: English
source only (see "Not done").

## Standing rule honoured: fresh recon first

The 45/67 figure from `TC-PKG-07-01` was NOT trusted. Before any edit,
`install_defect_sweep.run_install_recipe_sweep()` was re-run at HEAD `be25deeeed` (the
worktree was confirmed equal to `origin/main` after a fresh fetch): **9124 / 67 / 0**,
identical. A second, per-page dump (full path + quoted sentence per finding) reproduced
the same 45 pages. One thing DID drift between the dump and the edits: line numbers in one
file (tex/python `kb/faq.md`) moved from 80 to 110 (an unrelated evidence-block change
landed underneath). Every edit was therefore located by the finding's quoted sentence, never
by line number, and each product was re-swept fresh after editing.

## Policy handling (registry authoritative, no disclosure)

`data/package_registry.json` records `verification.published=false` for all 8 products
(pypi: barcode/font/html/page/pdf/tex python; npm: 3d/cells typescript). Per the
2026-09-03/09-10 no-publication-disclosure policy, no edit says "not yet published",
"coming soon", "unpublished", or names any publication state -- `IR_UNPUBLISHED_DISCLOSURE`
stays 0. Edit patterns used (body prose, plus the 4 code-block install commands of
pattern 5):

1. **Channel claim removed, true content kept** (majority, ~40 sentences): "published on
   PyPI as `X`" -> "distributed as `X`" / "packaged as `X`"; "Install from PyPI using
   pip:" -> "Install it with the command below:" (the line below is already the
   `package-install` shortcode, which renders a real GitHub-source install command for an
   unpublished package).
2. **Literal inline `pip install X` prose -> `{{< package-install-inline "family"
   "platform" >}}`** (3 sentences: html/python `_index.md`, font `font-cff` and
   `font-core-management`).
3. **Dead PyPI project-page links -> the product's real GitHub repository** (3, all
   barcode/python; the PyPI pages do not exist).
4. **pdf/python `license.md`**: "currently published at Alpha ... on PyPI" -> "currently at
   Alpha development status" (kept the true status and the pin-a-version advice).
5. **Four literal `pip install` code-block commands -> `package-install` shortcode**
   (font/python blog `eot-fonts-in-python`, `ttf-fonts-in-python`, `type1-fonts-in-python`:
   a one-line `.venv/bin/pip install aspose-font` block; html/python `kb/how-to-work-with-dom-
   python`: `pip install` + `pip show` block, `pip show` kept). Strictly these sit outside the
   flagged prose lines (`IR_PUBLISH_CLAIM` does not scan code blocks) and are `code-snippet`
   scope rather than `body-wording`; they were done because they are the same defect (the
   page still tells readers to install from a registry the package is not on) on pages this
   taskcard owns, AND because the Tier-1 pre-commit API audit (`audit.py`, "Specific install
   command found for an UNPUBLISHED package") blocks the entire commit while they remain.
6. **Two checker false positives, fixed by wording only** (3d/typescript kb page,
   cells/typescript installation page): both sentences were ALREADY honest (an `npm ls` /
   `npm install` step inside a build-from-source flow), but `_NOT_PUBLISHED_NEGATION_RE`
   recognises only `build`/`building from source` (not `built from source`) and only
   looks back one physical line. Reworded to "after building from source" / "when building
   from source via the `npm install` step above". The check logic was NOT touched
   (taskcard's Forbidden clause). Observation for a future card, not acted on here: that
   regex would be more robust if it also accepted `built from source`.

## Per-product

| Product | Pages | Findings | Result |
|---|---|---|---|
| 3d/typescript | 1 | 1 | 0 remaining |
| barcode/python | 7 | 9 | 0 |
| cells/typescript | 1 | 1 | 0 |
| font/python | 13 | 21 | 0 |
| html/python | 6 | 12 | 0 |
| page/python | 2 | 2 | 0 |
| pdf/python | 13 | 19 | 0 |
| tex/python | 2 | 2 | 0 |
| **Total** | **45** | **67** | **0** |

## Verification (independent of the edit process)

- `run_install_recipe_sweep()` full portfolio: **9124 pages / 0 publish-claim / 0 disclosure**.
- `scripts/ci/checks/check_install_recipe_safety_fails.py` over the 45 files: `OK: 0
  install_recipe safety FAIL(s)` (the PR-gate that would otherwise block any later PR
  touching these pages).
- `validate_frontmatter` over the 45 files: no errors.
- `pytest scripts/pipeline/tests/test_install_defect_sweep.py`: 14 passed after re-pinning
  `test_real_regression_pin_against_current_content` from `== 67` to `== 0` (its own
  docstring/failure message require the pin to move with a genuine count change;
  `TC-PKG-01-08-FIX` set the precedent 89 -> 67). Now a zero-tolerance guard.
- `git diff` confined to: the one prose sentence(s) per file, `provenance.last_mechanism`
  (-> `manual-edit-skill`), the regenerated `evidence:` block (deterministic
  `attach_evidence.py`, S-73 Step 13), and the `grade:`/`graded_*` block.

## Grade movement -- read this before interpreting "back to pre-override grade"

`content_eval evaluate --write-grade` (all 35 evaluators) was run on the 45 pages against
the committed (HEAD) knowledge. Pre -> post: **A->A 10, A->B 31, A->C 2, B->B 1, C->C 1,
F 0** (post distribution 10 A / 32 B / 3 C). The override F is gone everywhere, but most
pages do NOT land back on the stored "A", and that is NOT caused by this taskcard:

- **Control experiment.** The A->C pages (page/python `kb/faq.md`, tex/python `kb/faq.md`;
  and, before its evidence refresh, pdf/python `kb/how-to-create-generated-python.md`, now
  B) were re-evaluated as their unedited HEAD copies with the same evaluators (no write):
  they carry the SAME non-install findings (e.g. tex `format_truth` FAIL x2 at line 105;
  page `consumer_usefulness` x4, `format_truth`, `prose_truth`; pdf `api_accuracy`,
  `evidence_depth` x2, `format_truth` x2) PLUS the `install_recipe` FAIL this taskcard
  removed. An untouched sibling page (`font/python kb/how-to-work-with-cff-python.md`,
  stored `A`) also evaluates with 2 `consumer_usefulness` + `page_role` WARNs today.
  Conclusion: the stored `A` on these pages was stale relative to current evaluators
  ("No findings -> grade A" from an older evaluation), and the override F short-circuit had
  hidden that. The dominant residual WARN classes are `consumer_usefulness` ("No purpose
  framing in opening section" x22 pages; "code block has only N prose words of context"
  x33), which are unrelated to package-install claims.
- **Implication for `TC-PKG-07-04` / the parent acceptance line** ("back at its
  pre-override grade"): literal A on every page is not reachable through publish-claim
  fixes alone; it would need a separate, much larger grade-remediation pass over
  `consumer_usefulness`/`format_truth`/`prose_truth`/`api_accuracy` findings. "Not F /
  no longer override-forced" is what this taskcard delivers. Flagged for the
  supervisor/user to decide which reading the acceptance line intends.
- S-73's no-downgrade rule (>1 letter needs a justification): the 2 A->C pages are
  JUSTIFIED by the control experiment above (pre-existing, unrelated findings; nothing
  introduced by the edit).

## Incident found and reverted -- S-73 Step 5 is not a read-only check

S-73 Step 5 runs `refresh_knowledge.py {family} {platform}` as a "knowledge freshness
check". For font/python, pdf/python and tex/python it found upstream had advanced and did
a REAL re-extraction: it rewrote 31 tracked files under `knowledge/**` plus
`data/knowledge_state.json` / `data/upstream_baselines.json`, then ran a WHOLE-PRODUCT
`attach_evidence.py`, re-stamping evidence on **595 unrelated pages** (292 pdf, 30 tex, 301
font incl. reference.aspose.org) outside this taskcard's 45. (page/python and html/python
attempted the same and failed on a 300 s git-clone timeout; barcode/3d/cells reported
"current".) None of that was intended or committed: the 595 pages and all 31
knowledge/data files were restored with `git checkout HEAD --pathspec-from-file`
(sanctioned restore; no `git reset`), and the 28 font/pdf/tex target pages' evidence was
regenerated against the restored HEAD knowledge. It also invalidated two early
conclusions (an apparent "pre-existing broken evidence + API drift" F on two pdf pages
was an artifact of the stray refresh; against HEAD knowledge they grade C and B, with no
unknown claim IDs). **Recommendation (skill improvement, not done here):** S-73 Step 5 should use
a check-only mode (`knowledge-diff`), not `refresh_knowledge.py`; any lane that owns only
specific pages is exposed to this blast radius. Any refresh of these three products'
knowledge belongs to a proper `/refresh-product` (S-84) pass.

## Not done / residual (not hidden)

1. **Locale copies** of the 45 pages were not surveyed or edited (matches the sweep's
   documented English-source-only scope; `TC-PKG-03-02` territory). They almost certainly
   still carry the translated false claims.
2. **`audit.py` on the 45 files: 0 FAIL, 9 WARN** (all 9 pre-existing: `UNKNOWN_CLASS`
   `CompatDocument` / `SimpleNamespace` -- stdlib/third-party names the API audit does not
   know; untouched). The 4 literal-`pip install` code-block FAILs that existed at HEAD were
   fixed here (edit pattern 5) only because they block the commit; they are a different
   check category (`package_install_literal`, not `IR_PUBLISH_CLAIM`) and the html/python
   one is the "legitimate multi-command block" class `TC-PKG-02` deliberately refuses to
   auto-migrate -- so any OTHER product with the same pattern still needs that card.
3. `backlog/BACKLOG.md` row `PUBLISH-CLAIM-CONTRADICTION-001` (still says 89 findings / 58
   files, unchanged since before `TC-PKG-01-08-FIX`) was not edited; should read "English
   source fixed by TC-PKG-07-02; locale copies not surveyed; TC-PKG-07-04 pending" on the
   next `/backlog` pass.
4. `TC-PKG-07-03` (disclosure pages) has nothing to do: 0 `IR_UNPUBLISHED_DISCLOSURE`
   pages exist. `TC-PKG-07-04` (portfolio re-verification) still owns the official
   before/after distribution record.

## Appendix -- 45 pages, grade before -> after (findings fixed)

3d/typescript: kb/how-to-export-gltf-in-typescript A->A (1)
barcode/python: docs getting-started/_index A->A (2); installation A->B (2); license A->B (1);
  blog barcode-encode-options-python A->B (1); barcode-rendering-svg-png-python A->B (1);
  introducing-barcode-foss-python A->A (1); kb faq A->B (1)
cells/typescript: docs getting-started/installation B->B (1)
font/python: docs installation A->B (1); blog brotli-font-compression A->B (1);
  eot-fonts A->B (2); font-cff A->B (2); font-core-management A->B (2); font-tables A->B (1);
  python-font-ttf-woff-library A->A (3); ttf-fonts A->B (2); type1-fonts A->B (2);
  woff-fonts A->B (2); kb how-to-work-with-tables A->A (1); -ttf A->A (1); -woff A->A (1)
html/python: docs _index A->A (1); installation A->B (1); blog html-cssom A->B (3);
  html-dom A->B (3); introducing-html-foss A->A (3); kb how-to-work-with-dom A->B (1)
page/python: blog introducing-page-foss A->A (1); kb faq A->C (1)
pdf/python: docs installation A->B (1); license A->B (1); blog pdf-document-management A->B (1);
  pdf-engine A->B (1); pdf-generated C->C (1); kb faq A->B (1); how-to-add-pdf-security-signatures
  A->B (2); how-to-create-generated A->B (2); how-to-load-document A->B (1);
  how-to-work-with-clustering A->B (2); -pdf-annotations A->B (2); -pdf-data A->B (2);
  -primitives A->B (2)
tex/python: docs installation A->B (1); kb faq A->C (1)

## Reproduction

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -c "
from commands.ops.install_defect_sweep import run_install_recipe_sweep
r = run_install_recipe_sweep()
print(r['total_pages_checked'], r['total_publish_claim_contradiction_findings'], r['total_unpublished_disclosure_findings'])
"
# -> 9124 0 0
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m pytest scripts/pipeline/tests/test_install_defect_sweep.py -q
# -> 14 passed
```
