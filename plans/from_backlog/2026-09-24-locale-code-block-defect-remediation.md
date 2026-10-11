# Locale Code-Block Defect Remediation — MT073

**Mission ID:** `MT073-2026-09-24-LOCALE-CODE-BLOCK-DEFECT-REMEDIATION`
**Root slot:** held by `MT071-2026-09-17-GOVERNANCE-DURABILITY-HARDENING`
(`mission_locked: true`, `_archive_status: open`). Per that mission's own rule
("force-taking-over a locked+open root incumbent... escalate, do not auto-force"),
this mission does **not** force-take-over root — it registers directly at
`reports/plan_state/MT073-.../mission_authority.yaml`, the same
`archive_path_GOV-02` pattern MT072 itself used while MT071 held root.
**Governing source**: `MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION`'s
own TC-19 and TC-21 categorization reports (2026-09-24):
- `reports/plan_state/MT072-.../evidence/TC-19_ST-211_locale_syntax_error_categorization.md`
- `reports/plan_state/MT072-.../evidence/TC-21_ST-215_locale_drift_categorization.md`

Both closed with an explicit "categorize, don't blanket-fix" disposition and named
this exact follow-on scope. This plan executes it.

## Context

MT072 found two overlapping but distinct locale code-block defect classes across the
portfolio, and root-caused (not merely counted) each down to a small number of
mechanical patterns:

- **ST-211** (real, independently-detected syntax errors in locale code, 2,290 files /
  7,322 blocks): **88% traced to one mechanism** — a fence's language tag gets
  silently replaced during locale translation (English correctly tags non-code content
  as `text`; the locale copy of the same block gets the page's dominant programming
  language tag instead, so tree-sitter correctly flags legitimately-non-code content as
  broken code). Confirmed byte-for-byte against English on 6 real files across 4
  families. Two smaller, separately-diagnosed classes: `PLACEHOLDER_WRONG_COMMENT_SYNTAX`
  (172 blocks/files — the same `batch_gen_missing.py` placeholder shape MT072's own
  TC-10 fixed on English) and `3D_CONVERTER_MISTRANSLATION` (84 blocks/14 files — a
  systemic `using Aspose.3D.Converter;` should-be-`Aspose.ThreeD` mistranslation).
- **ST-215** (locale content differs from English, not necessarily broken, 12,513
  findings): 59% (`Bucket 1`, near-universal locale fan-out) is "English changed after
  the translation batch ran, locale never resynced" — a real content-sync gap, not
  corruption. A small isolated bucket (84 groups / 174 findings, 1.4%) is the more
  likely genuine per-locale corruption class.

**The user's ask**: continue past categorization into real remediation, following this
mission's own established discipline (root-cause before fixing, no blanket fixes
against an unclassified set, real commits with real evidence).

## Taskcards (schema 5f, `reports/plan_state/MT073-.../taskcards.jsonl`)

| Wave | ID | Title | Depends on | Source |
|---|---|---|---|---|
| 0 | TC-01 | Build a block-count-robust English↔locale code-block matcher (anchor on heading text + content similarity, not raw positional index — TC-19's own disclosed limitation: naive index comparison only caught 271 of 7,322 tag-mismatches because block counts drift between English and locale). | — | TC-19 |
| 1 | TC-02 | Using TC-01's matcher, build + dry-run a tag-only fixer for the confirmed tag-mistranslation class (locale fence tag → restore to English's tag at the matched position, ONLY when English's tag is a `NON_EXECUTABLE_LANGS` member and locale's is a real language tag on the same, matched, textually-similar content). No code content changes — the lowest-risk fix class this mission family has dealt with. Dry-run report only, no writes. | TC-01 | TC-19 |
| 2 | TC-03 | Apply TC-02's fixer for real, in reviewable batches (by site, largest first: reference.aspose.org). Real commits, real before/after re-scan reconciling against TC-19's own 7,322/2,290 baseline. | TC-02 | TC-19 |
| 1 | TC-04 | Fix the 84-block/14-file `3D_CONVERTER_MISTRANSLATION` class directly (`using Aspose.3D.Converter;` → `using Aspose.ThreeD;`, mechanical string substitution, already fully diagnosed by ST-211's original filing). | — | ST-211 |
| 1 | TC-05 | Fix the 172-block/file `PLACEHOLDER_WRONG_COMMENT_SYNTAX` class on locale pages, mirroring MT072/TC-10's own English disposition rule exactly: a real, verified example where one exists in `runs/.clone_cache/`, full section retirement where it doesn't — never a fabricated example. | — | ST-211 |
| 3 | TC-06 | Re-run TC-19's own categorization script after TC-03/04/05 land; reconcile the residual against the original 7,322/2,290 baseline; file whatever's left with a named reason (should be close to the `OTHER_UNEXPLAINED` bucket's true size once the 3 known classes are removed). | TC-03, TC-04, TC-05 | TC-19 |
| 2 | TC-07 | ST-215 Bucket 3 (isolated drift, 84 groups / 174 findings / 45 pages) — the small, high-confidence, per-locale-anomaly candidate set. Investigate and fix per-page via governed content skills; this is the bucket TC-21's own report named as the highest-value, lowest-risk starting point. | — | ST-215 |
| — | TC-08 | ST-215 Buckets 1+2 (near-universal + mid-range drift, 513 groups / 12,339 findings / ~150 pages) — **explicitly a follow-on-of-the-follow-on**: each affected family needs its own "is English the correct target to resync to" content verification before any fix, exactly the caution TC-21's own report named. Not attempted in this mission unless/until that per-family verification work is separately scoped; registered here so it isn't lost, not committed to as in-scope. | TC-07 | ST-215 |

## Mandatory acceptance criteria

- TC-01–TC-07 each reach `CLOSED` with real evidence (dry-run reports, real commits,
  before/after reconciliation counts), or an explicit `BLOCKED_EXTERNAL`/`OUT_OF_SCOPE`
  disposition with a named reason.
- No taskcard's fix introduces a dirty-set regression on any product outside its own
  scope (same rule as MT072).
- TC-03's real fix is applied in reviewable batches with a real before/after count at
  each batch, never a single unreviewable mass commit.
- TC-08 is explicitly named as out-of-scope-unless-separately-authorized, not silently
  attempted under this mission's own momentum.

## Out of scope

- ST-215 Buckets 1+2's actual resync fix (TC-08) — needs per-family content
  verification this mission does not have standing to shortcut.
- Any change to `example_verification_sweep.py`/`syntax.py`/`code_fences.py`'s own
  classification logic — this mission consumes MT072's tooling as-is; any tooling
  defect found gets filed to backlog, not silently patched mid-remediation.
- Full re-execution of locale code (still out of scope, per MT072's own original plan,
  unchanged).
