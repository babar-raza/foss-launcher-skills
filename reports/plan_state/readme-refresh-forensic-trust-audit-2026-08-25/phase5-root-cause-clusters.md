# Phase 5 — Root-Cause Clustering (readme-refresh forensic trust audit)

## Method

Every one of the 36 defect-class rows in phase4-validator-matrix.md is classified on
three axes (finding classification / scope / root-cause stage, per the fixed vocabularies
supplied), then grouped into 8 systemic clusters (A-H) sharing one true earliest cause.
Two items are explicitly *not* clustered as defects: row 23 (check worked correctly) and
the residual of row 24 (verification-harness hygiene wrinkles with no realistic owner).
One important finding — font/python's live-README regression — has no dedicated row
number in phase4 (it surfaced inside that product's own Stage C) but is added here under
Cluster E because the task brief and Phase 6 require it, and because it is the single
clearest instance of Cluster E's mechanism.

## Per-row classification table

| # | Defect (short) | Classification | Scope | Root-cause stage | Cluster |
|---|---|---|---|---|---|
| 1 | Own package version stale in Installation vs current manifest | Factual defect | Portfolio-wide | Validator false negative | B |
| 2 | last-verified trusted despite fresher knowledge | Cache-or-invalidation defect | Portfolio-wide | Validator not registered | B |
| 3 | upstream-issues.md stale vs current clone-cache/live upstream (11/31) | Evidence defect | Portfolio-wide | Stale knowledge (escapes via Validator not registered) | B |
| 4 | Clone cache stale vs live GitHub (root architectural cause) | Cache-or-invalidation defect | Portfolio-wide (by design, offline) | Stale clone | B |
| 5 | Candidate missing new upstream content (pinned knowledge) | Factual defect | Portfolio-wide | Stale knowledge (downstream of row 4) | B |
| 6 | New candidate content has zero disposition trace (13/31) | Preservation failure | Portfolio-wide | Validator false negative (one-directional design) | A |
| 7 | Evidence-resolution proves citation exists, not that it supports claim | Factual defect | Portfolio-wide | Prompt weakness (escapes via Validator false negative) | C |
| 8 | Disposition claims excluded/corrected but content present | Preservation failure | One product (pdf/go, 3d/net) | Validator false negative | A |
| 9 | Structural-unit target_section hardcoded, weak fallback | Preservation failure | One product (pdf/cpp) | Validator false negative | A |
| 10 | Code-example mislabeled merged_verbatim despite rewrite | Preservation failure | One family (tex/python + pdf/cpp) | Validator false negative | A |
| 11 | API-table completeness defeated by shared-omission ground truth | API-reference defect | Portfolio-wide (7/31, 23%) | Incorrect fact extraction | D (D-i) |
| 12 | Diagram Outputs container omits real format | API-reference defect | One product (pdf/java) | Incorrect fact extraction | D (D-i) |
| 13 | Diagram format-claim "source" proves name exists, not wired | API-reference defect | One product (3d/net) | Incorrect fact extraction | D (D-i) |
| 14 | Namespace-disambiguation suffix fused into Class column | Rendering defect | One product (pdf/java) | Renderer behavior | D (D-i) |
| 15 | Badge-preservation compares category only, not identity | Preservation failure | One product (note/python) | Validator false negative | A |
| 16 | Badges' self-referential evidence has no backstop | Evidence defect | One product (pdf/go) | Validator not registered | A |
| 17 | No check resolves file-path/import literals in code fences | Example defect | Portfolio-wide (2 confirmed mechanisms) | Validator not registered | G |
| 18 | Structural-unit coverage only as complete as extractor's scope | Preservation failure | Portfolio-wide | Validator false negative | A |
| 19 | Disposition/prose numeric self-reports never fact-checked | Factual defect | Portfolio-wide (5-10/31) | Validator not registered | F |
| 20 | Publication-ledger completeness (17/31, 55%) | Publication blocker | Portfolio-wide | Publication mismatch | E (E1) |
| 21 | Heading-title-case checks per-word only, not word-split | Presentation inconsistency | One product (pdf/java) | Validator false negative | F |
| 22 | Nav TOC omits real `##` heading (9/31, 29%) | Presentation inconsistency | Portfolio-wide | Validator not registered | F |
| 23 | formats.md disagrees but candidate's own claim held — gate worked | N/A (control) | — | — | Not clustered |
| 24 | Misc low-severity hygiene items (residual after 35/36 promoted) | Documentation drift | Scattered | Validator not registered | Not clustered |
| 25 | EE link/anchor correctly flagged dirty, nothing re-triggers regen | Link defect | One family (page/python, tex/python) | Publication mismatch (stretch — see caveat) | E (E3) |
| 26 | content-dispositions excerpt stores post-transformation text, not true original | Preservation failure | Portfolio-wide (5-6/31) | Original-content inventory failure | A |
| 27 | badge-dispositions "preserved" when old had zero badges | Preservation failure | One family (email/cpp, email/net, tex/python) | Validator false negative | A |
| 28 | structure-dispositions tracks 1-13 entries vs 20-30+ real headings | Preservation failure | Portfolio-wide (6-7/31) | Validator false negative | A |
| 29 | merged_verbatim on substantially reworded content | Preservation failure | One family (slides/java, email/cpp) | Validator false negative | A |
| 30 | Version-bump claim unverified against live registry (mirror of #1) | Factual defect | One product so far, portfolio-wide by mechanism (cells/java) | Validator not registered | B |
| 31 | formats.md/json fabricates or drops via shallow pattern-matching | Factual defect | Portfolio-wide (shared extractor, ~14+ consumers) | Incorrect fact extraction | D (D-i) |
| 32 | C++ scout has no is_public/visibility field (100% "public") | API-reference defect | One repository archetype (C++ products) | Missing public-surface extraction | D (D-ii) |
| 33 | Member-exists check never verifies real accessibility | Factual defect | Portfolio-wide | Prompt weakness / Validator false negative (cross-ref D-ii) | C |
| 34 | Javadoc `{@code <tag>}` silently emptied by Markdown conversion | API-reference defect | One repository archetype (Javadoc-sourced products) | Incorrect fact extraction | D (D-i) |
| 35 | verified_by_run_id universally null (31/31, 100%) | Evidence defect | Portfolio-wide | Renderer behavior (refined below — not "never threaded", see Cluster H) | H |
| 36 | readme_sha256 hashed over CRLF-stripped text, not real bytes | Cache-or-invalidation defect | Portfolio-wide (any Windows-run refresh) | Renderer behavior | H |

## Cluster A — Disposition-ledger machinery validates *shape*, never *ground truth*
**Rows: 6, 8, 9, 10, 15, 16, 18, 26, 27, 28, 29 (11 of 36 rows — the single largest cluster).**
Classification: Preservation failure. Scope: Portfolio-wide (at least 20+/31 products hit
by one row or another). Root-cause stage: Validator false negative, compounded for a
confirmed subset (row 26, and font/python's instance of row 28) by an earlier
**Original-content inventory failure** — Stage C on font/python (`phase3-reviews/font-python.md:182`)
proved the "old readme" baseline fed to `check_content_unit_disposition_coverage` was
*itself* already the post-refresh text by generation time (file-timestamp evidence: all
four disposition JSONs written 2026-08-20 20:24:09, five days after PR #1 merged
2026-08-15, clone-cache HEAD already at post-merge `7971880`). This means the same check
(`readme_refresh_checks.py` — `check_content_unit_disposition_coverage` ~5892,
`check_structural_unit_disposition_coverage` ~7276, `check_badge_disposition_coverage`
~8194-8210, `check_content_unit_merged_into_target_section` ~6492,
`check_structural_unit_merged_into_target_section` ~7346,
`check_badge_preserved_or_credited_in_candidate` ~8258-8285,
`check_content_unit_excerpt_matches_extraction` ~5994) is architecturally sound in two
proven instances (rows 26, 28 — independent reviewers manually re-ran it against the true
original and got the exact failures a correctly-fed check should produce) but is either
(a) never fed a verified-correct baseline, or (b) structurally one-directional — it only
walks units the extractor already recognized from the OLD readme, never the candidate's
own real, current structure/badges/content for anything net-new (row 6: 13/31 products,
42%, mostly a "## Dependencies" / "### Native and System Requirements" subsection present
in 29/30 products' templates but tracked in almost none; row 28: entry counts 1-13 across
6 products vs 20-30+ real headings, mechanically reproduced live by slides/java's own
Stage C), or (c) validates enum-membership/field-presence only, never a literal text diff
for a claimed transformation (row 10: tex/python's from-source install command recorded
as `merged_verbatim`; row 27: badges labeled "preserved" when `old_badges == []`, a
documented vacuous-pass per the check's own docstring line 8207-8209; row 29: bold-caption
→H3-heading rewrites and bullet-consolidations labeled `merged_verbatim`; rows 8/9/15/16
are the original canary-pass instances of the same family). **This is the highest-value
cluster to fix**: two of its own component checks were proven — not theorized — to work
correctly once fed the truth, meaning part of the fix is a production-application audit,
not a redesign.

## Cluster B — Nothing re-verifies a pinned fact against a fresher, already-available version of its own source of truth
**Rows: 1, 2, 3, 4, 5, 30.** Classification: Cache-or-invalidation defect (primary) /
Factual defect (rows 1, 5, 30). Scope: Portfolio-wide — row 3 alone is 11/31 (35%), row 4
is a deliberate, disclosed offline-by-design gap that nonetheless escalated to BLOCKER on
pdf/python (clone cache ~1 week / 4+ commits stale; live HEAD's latest commit predated this
run's own `verified_at` by 6 minutes). Root-cause stage: **Stale clone** is the taproot for
rows 4 and 5 (knowledge is built from the clone cache; row 5's "candidate missing new
upstream content" is a direct, mechanical consequence of row 4, not an independent defect).
Rows 2, 3, 30 share a different but related earliest stage: **Validator not registered** —
no check of any kind exists anywhere in the 103-function battery to compare
`last-verified.json`'s own timestamp/SHA against knowledge-bundle freshness (row 2, proven
concretely on pdf/net: knowledge re-scouted to v26.8.0 a full day *before*
`verified_at`, yet the candidate stayed on v26.7.0 and the "verified" pass never flagged
the drift), to re-diff `upstream-issues.md`'s own claims/pin against current clone-cache
HEAD (row 3), or to re-confirm a claimed version bump against a live registry check (row
30 — cells/java's candidate/pom.xml/model.yaml all say `26.7.0` while the only live Maven
Central check on record, one month older, confirms only `26.5.0`). Row 1 (own-package
version stale in Installation, pdf/net BLOCKER + pdf/java MAJOR-adjacent) is the narrowest
instance of the same missing-verification shape: `check_installation_matches_package_registry`
(`readme_refresh_checks.py` ~2080) and `check_dependency_version_pin_freshness` (~8973) are
both wired hard gates that simply never read the Installation section's own version string
against the product's own current registry entry. Row 30 is explicitly the mirror image of
row 1 in the matrix's own text ("ahead" vs "behind" the last-confirmed-live version) — same
missing check-class, opposite direction.

## Cluster C — Citation-exists is conflated with claim-true, or with real accessibility
**Rows: 7, 33.** Classification: Factual defect. Scope: Portfolio-wide — row 7 is the
single largest defect class in the audit by finding count (10+ findings across 9+
products, BLOCKER to MAJOR), including cells/java's carried-forward-unchanged 44.3%-wrong
"single module" narrative (now a Tier-1 item, see Phase 6) and 3d/typescript's fabricated
Node.js CI-version claim. Root-cause stage: **Prompt weakness** is the earliest stage — the
skill doc (the only "prompt" in this system; there is no template engine, per
`docs/readme-refresh/current-operational-reference.md:61`) never requires the composing
agent to ground every factual/behavioral sentence in a literal quote from cited evidence —
compounded by **Validator false negative**: `check_content_unit_evidence_resolves`
(`readme_refresh_checks.py` ~6054) is a wired hard gate at all 4 call sites, and by its own
disclosed design "confirms a citation EXISTS, never that it SUPPORTS the claim." Row 33
(words/net's live BLOCKER: `doc.FirstSection.Body.Shapes[0].Chart` — `Shapes` is a real
member, but declared `internal` on base class `Story`, invisible to any external consumer;
a real compile produces `CS0122`, not the `CS1061` the review's own Verdict text states)
is the sharpest instance: `upstream-issues.md` explicitly claims every referenced member
was "cross-checked... and confirmed to exist" — true, and worthless, because nothing in
the verification chain distinguishes public from internal. Cross-reference: this is the
same shape as Cluster D-ii's row 32 (C++ scout has no visibility signal) one layer up the
stack — row 32 is a scout-extraction gap, row 33 is a check/evidence-resolution gap that
would exist even if the scout captured accessibility correctly, since no check consumes
that field for code-example member references today.

## Cluster D — Knowledge/scout-layer extraction is shallow pattern-matching, not verified wiring
**Sub-cluster D-i (shallow existence/pattern-matching instead of runtime-dispatch
verification). Rows: 11, 12, 13, 14, 31, 34.** Classification: API-reference defect
(11,12,13,34) / Factual defect (31) / Rendering defect (14). Scope: Portfolio-wide — the
extractor code (`scripts/pipeline/extraction/formats.py` per 3d/java's own Stage C) is
referenced from an estimated 14+ other pipeline commands, so this is shared machinery even
though only a subset of products have a directly-confirmed hit today (cells/cpp, font/python,
html/python, words/python for row 11 — 7/31, 23%; 3d/java, 3d/typescript, barcode/python,
cells/python for row 31; slides/java for row 34, confirmed pre-existing in live upstream
too, not introduced by this refresh cycle). Root-cause stage: **Incorrect fact extraction**
— row 31's own required-protection text says this explicitly: "Belongs to S-34/
knowledge-enrich, not `readme_refresh_checks.py`." The extractor confirms a class/file/enum
*exists* (or a Javadoc tag string is present) without confirming it is actually wired into
runtime dispatch (row 13: diagram format claims), actually exported/complete (row 11: API
table vs reference.aspose.org's own independently-generated index, which inherited the
identical omission — same root, two consumers), or correctly converted (row 34: a Markdown
conversion step silently empties `{@code <tag>}` spans containing raw angle-bracket XML/
HTML element names). Row 14 (pdf/java, a namespace-disambiguation suffix fused into the
Class column as a non-identifier string) is the one rendering-flavored member of this
sub-cluster — same layer of the pipeline (enrichment/table-generation), no dedicated check.

**Sub-cluster D-ii (missing public/internal visibility signal at the scout layer). Row: 32.**
Classification: API-reference defect. Scope: One repository archetype — the C++ scout
specifically; slides/cpp's own Stage C explicitly checked email/cpp and found **zero**
internal-marked entries there, so the "recurs on every C++ product" extrapolation does
**not** hold universally, even though the mechanism (a `visibility` field hardcoded to
`"public"` on literally 100% of entries) is a real, confirmed defect on 2 of the audited
C++ products (slides/cpp: 29 leaked entries; pdf/cpp: 92/340, ~27%). Root-cause stage:
**Missing public-surface extraction** — the schema has the field, but nothing populates it
correctly off `canonical_namespace`/file path; other language scouts (Python's
underscore-prefix exclusion) implement the equivalent correctly, C++'s does not.

## Cluster E — No reconciliation loop closes the gap between a detected drift and a corrective action
**Sub-tier E1 (row 20 — publication-ledger completeness, 17/31 = 55%, the single
most-recurring confirmed defect in the whole audit).** Classification: Publication
blocker. Scope: Portfolio-wide. Root-cause stage: Publication mismatch. Mechanism:
`_published_readme_current_findings` (`readme_refresh_run.py:651`) is wired but advisory
only; three distinct causal sub-mechanisms are independently confirmed across the batch —
a missed backfill-seeding sweep (most of the 14 "new batch" hits), a genuinely out-of-band
manual commit outside the pipeline entirely (barcode/python — the ledger literally cannot
ever learn about this from this repo's own recorded PR history), and the original
"published-then-edited" disclosed-but-stale case. The fix must be a periodic **live**
reconciliation job against `gh api .../commits`/`.../pulls`, not a one-time manual seeding
pass, precisely because the barcode/python mechanism defeats any seeding approach by
construction.

**Sub-tier E2 (font/python's full-regression BLOCKER — no phase4 row number, cited
directly).** Classification: Publication blocker (most severe form: total loss of
published content, not merely an untracked ledger entry). Scope: One repository archetype
— any product whose GitHub repo is a downstream mirror of an external canonical source
(explicitly hedged as "likely recurs," not proven portfolio-wide, per
`phase3-reviews/font-python.md:93,176`). Root-cause stage: **Publication mismatch**, with an
earlier contributing stage of **Incorrect source acquisition** — the GitHub repo this
pipeline pushed to is not the canonical source of truth for this product at all. Evidence
(`phase3-reviews/font-python.md:94`, independently re-verified in Stage C at line 176): PR
#1 (`7971880964143c86ffd4baa7c8ea1dd959fea04e`) was genuinely merged 2026-08-15T15:22:31Z;
on 2026-08-20T21:48:16Z the entire repo history was replaced by a zero-parent commit
`55409553328ec8baa14c47a8920f7f6e301ae488` ("Release 26.8.3", author
`AI-Agent-AsposeFontFOSS`) whose README is byte-identical to the **pre-refresh original**,
not the fix. `CHANGELOG.md`/`CODEOWNERS` at the live HEAD explicitly describe a
GitLab-canonical → GitHub-mirror architecture (`/.gitlab-ci.yml` is an owned path). Any
merge landing only on the GitHub mirror is guaranteed to be wiped on the next mirror sync
— this is architecturally different from, and worse than, E1: even a perfect ledger would
not have prevented this, because the *target repo itself* discards content the pipeline
does not control. This also compounds E1: `data/readme_published_state.json` and
`reports/repo_presenter_actions.jsonl` both have zero `font`/`python` rows despite the real
merge, so the one signal that might have prompted an early recheck was never populated
either.

**Sub-tier E3 (row 25 — EE link/anchor correctly flagged dirty, nothing re-triggers
regeneration; page/python + tex/python).** Classification: Link defect (surface) /
State-machine defect (true mechanism). Scope: One family so far (2 products, identical
mechanism, discovered by one reviewer cross-checking both). Root-cause stage: this one does
not cleanly fit the supplied taxonomy — flagged honestly rather than forced. The closest
listed label is **Publication mismatch** (the underlying override data,
`data/aspose_com_targets.json` / `platform_canonical_overrides.yaml`, is analogous to a
publication-target ground truth going stale relative to a product's last-generated
candidate), but the real gap is a missing **scheduling/orchestration** capability: no
mechanism re-queues a product for regeneration when a canonical-override target changes
after that product's candidate was last generated. `check_enterprise_edition_link_resolves`
(~1335) and `check_enterprise_edition_anchor_matches_relationship` (~1432) are proven,
by direct trace of `_classify_enterprise_relationship`, to work exactly as designed — this
is **not** a check-design gap, it is the same missing "detect → requeue" loop as E1/E2 at
smaller scale.

## Cluster F — No check verifies the candidate's own self-consistency
**Rows: 19, 21, 22.** Classification: Presentation inconsistency (21, 22) / Factual defect
(19). Scope: Portfolio-wide — row 22 (Navigation TOC omits a real `##` heading) is
confirmed on 9/31 products (29%) via a single repo-wide grep spontaneously run inside
cells/cpp's own Stage C — the cheapest fix-to-impact ratio in the entire matrix. Root-cause
stage: **Validator not registered** — no check anywhere parses Navigation's own linked
section list and diffs it against the real heading set (row 22); no check reads an
embedded numeric claim in disposition rationale or in the candidate's own prose and
cross-verifies it against the document's own actual, already-computed table/row counts
(row 19 — font/python's unreconcilable "139 public types," slides/net's false "153... 0
fabrications" claim against a real count of 129/108); `check_heading_title_case` (~4125)
verifies per-word capitalization only, never word-split correctness (row 21, pdf/java,
low-severity single instance).

## Cluster G — Executable/runnable-reference verification is stubbed or narrowly scoped
**Row 17, plus the non-matrix-row Phase 2 finding `AUD-P1-VERIFY-EXAMPLES-STUB`
(`verify_examples` 3519-3556; default stub `_default_verification_runner` 3376-3391;
real `python_verification_runner` 3474-3516, opt-in and Python-only).** Classification:
Example defect. Scope: Portfolio-wide — architectural, applies to every product in every
non-Python language, and even Python's own opt-in path only checks `ast.parse` syntax of
` ```python ` fenced blocks. Root-cause stage: **Validator bypass** for the stub
(`VERIFYING_EXAMPLES` is a real state-machine stage, but its default runner is a
documented no-op) — **Validator not registered** for row 17's two confirmed escape routes:
hardcoded fixture file paths inside Python string literals (note/python, never resolved
against the real clone-cache layout) and shell-fenced verification commands sitting
entirely outside both the Python-syntax scanner and the Java-only
`check_code_example_imports_match_source` (words/python's `python -c "import
aspose_words_foss"` — a genuine `ModuleNotFoundError`, real package is dotted
`aspose.words_foss` — confirmed via `phase3-reviews/words-python.md:149`, and confirmed
**not yet published** anywhere, per that same review's Identity table line 10, so this is a
dirty-candidate gap, not a live-production one). Cross-reference: had any real
compilation/execution runner existed for C#, it would have trivially caught Cluster C's
row-33 words/net BLOCKER (`CS0122`) with zero semantic reasoning required — this cluster
and Cluster C are two independent ways the same live defect escaped.

## Cluster H — Shared marker-writing code has two 100%-reproducible defects
**Rows: 35, 36. Both trace to the exact same function: `_write_candidate_verification_marker`,
`scripts/pipeline/commands/foss/readme_refresh_run.py:584-594`.** Classification: Evidence
defect (35) / Cache-or-invalidation defect (36). Scope: Portfolio-wide — row 35 confirmed
31/31 (100%, two independent sweeps); row 36 confirmed on 2 products, architecturally
universal on any Windows-run refresh. Root-cause stage: closest available label is
**Renderer behavior** (a plain implementation bug in shared write-path/serialization code
— none of the supplied stages name "write-path instrumentation bug" precisely, flagged
honestly). **This audit independently re-read the function and its 3 real call sites and
found a sharper root cause than phase4 row 35's own framing** ("`_write_candidate_
verification_marker` or its caller never threads a real run_id through" — only half true):
- Line 588: `hashlib.sha256(text.encode("utf-8"))`, where `text` is populated at every call
  site via `candidate_path.read_text(encoding="utf-8")` (confirmed at `ingest_candidate`,
  line 1964) — Python's `read_text()` performs universal-newline translation by default,
  so the recorded hash never matches the file's real on-disk CRLF bytes. This is row 36,
  exactly as 3d/java's Stage C root-caused it.
- Line 590: `"verified_by_run_id": run_id` — the parameter **is** threaded correctly at 2 of
  3 real call sites: `ingest_candidate` (line 1973, `run_id=run_id`) and `recheck` (line
  3087, `run_id=run_id`) both pass the real value. The 3rd call site, inside
  `audit_portfolio` (line 2951, `run_id=None`), is a **deliberate, documented** design
  choice — the code's own comment (lines 2946-2947) reads: "audit-portfolio is a real,
  independent verification pass too -- record it, same marker, run_id=None (no run owns a
  portfolio-wide audit)." Because `audit_portfolio` sweeps run far more frequently than
  bound `ingest_candidate`/`recheck` calls in practice (this very mission ran dozens of
  portfolio-wide scoped sweeps for baseline generation alone), its write **unconditionally
  overwrites** whatever real `run_id` a prior bound run had legitimately recorded. The
  practical, observed 100%-null result is therefore not "never threaded" — it is "correctly
  threaded twice out of three places, then silently clobbered by the third, dominant write
  path, by design." This changes the fix: preserve or namespace the field so a read-only
  audit sweep cannot erase a real run's provenance (see Phase 6 RC-verification-marker
  item) rather than simply "populate it, it's currently always empty."

## Not clustered
- **Row 23** — `check_diagram_verified_format_claims` correctly defended a candidate whose
  own Scope-and-Limitations text was already accurate against a landmine in `formats.json`
  (3d/net, page/python). This is a **positive control**: proof the check battery works when
  fed trustworthy input. No action item; retained as evidence that Cluster D's proposed
  fix (verify real runtime dispatch at the knowledge layer) will not regress cases like this.
- **Row 24 residual** — after promoting the CRLF item to Cluster H (row 36) and the
  `verified_by_run_id` item to Cluster H (row 35), what remains is a handful of
  by-design non-issues and verification-harness self-consistency wrinkles (a
  `diagram_hybrid_reverification` daily-by-design flag on page/python; a one-week-older
  mtime on tex/python's disposition file with no actual contradiction found; a 3-day
  publish/commit-date gap on cells/go, plausibly a push-then-merge artifact; a `model.yaml`
  repo_sha one commit behind on slides/cpp, confirmed harmless). No systemic owner, no
  material user-facing risk — explicitly not carried into Phase 6 as an action item beyond
  what Cluster H already covers.

---
