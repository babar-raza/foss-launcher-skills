# TC-MT070-02: Fix ST-195 — reports/truth-audit/ report-path collision

**Root cause, now precisely confirmed** (beyond ST-195's original filing, which left
the exact producer of the colliding stub unidentified): the two real files still on
disk for imaging/net prove it directly —

- `reports/truth-audit/imaging-net-20260911.json`: keys
  `date, findings, products_checked, total_checked, total_fails, total_findings,
  total_warns` — this is `truth_audit.py`'s (S-38, member-level structural audit)
  `report_json()` shape, **not** `truth_audit_content.py`'s. S-38's own documented
  default output path is `reports/audit/`, not `reports/truth-audit/` — so something
  invoked it with an explicit `--output` redirected into S-85's directory under a
  colliding filename, on 2026-09-11 (the day of imaging/net's original launch). No git
  history exists for this file (`reports/` is gitignored) so the exact caller could not
  be traced further.
- `reports/truth-audit/imaging-net-20260912.json`: keys
  `clone_cache_sha, defect_summary, delta, family, files, findings, knowledge_version,
  platform, run_date, schema_version, summary, units` — the real
  `truth_audit_content.py` (S-85) ledger, from the H7 relaunch's first genuine semantic
  run (matches `_TRUTH_AUDIT_REQUIRED_KEYS` exactly).

`_find_latest_report`'s glob (`{family}-{platform}-*.json`) matches both filenames with
zero shape/producer check, sorting purely by mtime. Whichever file happened to be
newest was trusted outright — on 2026-09-11, before the real S-85 run existed, the
S-38 stub was "latest" and silently satisfied `review_product()`'s cross-check gate,
producing the false "16/16 PUBLISH" verdict INV-020 found. By 2026-09-12 the real
report happened to become newest by date anyway, so today's `imaging-net-net` picker
output is correct by accident of timing — the underlying defect (no shape check) was
never fixed and would misfire again for any future product where a stub-shaped file
lands after a real one, or where any other writer ever uses this naming convention.

**Fix** (`scripts/pipeline/commands/governance/publish_readiness_review_run.py`):
- New `_TRUTH_AUDIT_REQUIRED_KEYS` + `_is_valid_truth_audit_report()`: validates the
  real S-85 ledger shape (structure-based, not an exact `schema_version` pin, so a
  legitimate future schema bump keeps validating).
- `_find_latest_report()` gained an optional `validate` callable: when given, it walks
  candidates **newest-first** and returns the first one that parses AND validates,
  printing a `WARNING` to stderr and falling through to the next-newest candidate for
  anything that doesn't (unreadable JSON or wrong shape) — never silently trusting
  positional recency alone, and never losing an older-but-real report just because a
  newer stub exists.
- `review_product()`'s truth-audit call site now passes
  `validate=_is_valid_truth_audit_report`. The `gap-analysis` call site is unchanged
  (different schema, out of this fix's scope — ST-195 was specifically about the
  truth-audit collision).

**Live-verified against the real historical data** (not just synthetic fixtures):
```
imaging-net-20260911.json -> valid: False   (the S-38 stub)
imaging-net-20260912.json -> valid: True    (the real S-85 ledger)
picked: reports/truth-audit/imaging-net-20260912.json
```

**Tests** (`scripts/pipeline/tests/test_publish_readiness_review_run.py`):
- Added `_valid_truth_audit_ledger()` fixture helper (a real-shaped ledger builder) and
  migrated 3 pre-existing truth-audit fixtures from the old bare
  `{"findings": [...]}` shape to it — those tests were themselves unknowingly relying
  on the exact stub shape this fix now rejects, so they needed the realistic shape to
  keep passing (a real test-fidelity gap, not a design accommodation for the fix).
- New `TestTruthAuditReportSchemaValidation` (4 tests): stub-only → `None`; valid-only
  → picked; newer-stub-falls-back-to-older-valid (direct mechanism reproduction, mtime
  forced via `os.utime`); and `test_false_publish_prevented_end_to_end` — a full
  `review_product()` run with a real open `CONTRADICTED` finding in an older valid
  report plus a newer stub, asserting the page is correctly downgraded from `PUBLISH`
  (the exact false-verdict scenario ST-195 describes).
- Full suite: `scripts/pipeline/tests/test_publish_readiness_review_run.py` — 42/42
  passed (38 pre-existing + 4 new; 3 pre-existing migrated to the realistic fixture
  shape, zero behavior change to what they assert).

**Not implemented** (deferred, per ST-195's own two listed options — (b) implemented
here is a complete, self-contained defense regardless of what any future caller does;
(a), separating the two scripts' output paths at the source, would additionally stop
the collision from ever being *created*, but is not required to close the risk and the
exact original caller could not be traced to fix): recorded here for a future session
if the redirect-caller is ever identified.

**Skill context**: S-90 (publish-readiness-review), scope
`scripts/pipeline/commands/governance/publish_readiness_review_run.py,scripts/pipeline/tests/test_publish_readiness_review_run.py`.
Disposition `broken-dependency` per `docs/workflows/gap-escalation.md` (S-90's own
contract is fine; its cross-check dependency had a real shape-validation gap).
