# MT070-2026-09-16-IMAGING-NET-FORENSIC-HARDEN — Final Report

## 1. Executive outcome

The thin API reference (3 detail pages + 1 index) at `reference.aspose.org/imaging/net/`
is **correct, not a defect**. It is independently reconfirmed — via a verification path
never previously used on this product (a real `dotnet build` + `System.Reflection`
dump of the compiled assembly, not just static source parsing) — to be the exact,
complete public API surface of the pinned upstream repository. Two real shared-system
defects were found and fixed as a result of this investigation (not imaging-specific,
proven against a sibling product and covered by new regression tests); one further
diagnosed-but-unfixed defect (already fully root-caused by the original launch
mission) was blocked on a governance write-permission wall and left as a ready-to-apply
diff for human action. Determinism of regeneration was proven for this product. No
content was regenerated, since no gap justifying new or changed pages was found.

## 2. Initial symptom assessment

User-reported: reference.aspose.org/imaging/net/ showed only 3 detail pages + 1 index,
and regeneration "caused the number of generated pages to change slightly" — raising
concern about both incompleteness and pipeline nondeterminism.

## 3. Canonical repository, branch, commit, package, version

- Repo: `https://github.com/aspose-imaging-foss/Aspose.Imaging-Foss-for-.NET`
- Pinned commit: `f2cf68fd64545bfb704c45ee756af3125103fd74` (clone cache HEAD confirmed
  identical, clean working tree, before and after this mission)
- Package: `Aspose.Imaging.Foss`, targets `netstandard2.0;net8.0`, MIT license, zero
  NuGet dependencies. Not yet published to NuGet (per repo convention, no publication
  status disclosed in content).

## 4. Source project and assembly inventory

1 solution (`Aspose.Imaging.Foss.sln`), 2 projects (`src/Aspose.Imaging.Foss`,
`tests/Aspose.Imaging.Foss.Tests`), 21 `.cs` files total (17 source + 4 test).
`dotnet build -c Release` succeeds with 0 errors on both target frameworks.

## 5. Verified public API counts

**Exactly 3 public types**, confirmed by two independent methods that now agree
exactly:
- Static tree-sitter extraction (`api_surface.json`, MT068 + this mission's isolated
  re-run): `ImageFormat` (enum, 12 members incl. `Unknown`), `ImageInfo` (class, 1
  ctor + 5 properties), `ImageProbe` (static class, 5 methods).
- Compiled-assembly reflection (`Assembly.GetExportedTypes()`, this mission,
  never previously done): identical set, identical members, zero discrepancy.

14 declared types total; 11 are `internal` format handlers, correctly excluded from
both extraction methods.

## 6. Expected reference-page contract

`site_planner.py`'s `plan_reference()` does not itemize per-class pages in
`site_plan.yaml` at all — it emits only the family/platform structural index entries;
actual per-class page generation is delegated to `batch_reference.py` reading
`api_surface.json` directly, one page per public type, filename = class name. For
imaging/net: 3 candidates → 3 pages, confirmed by the real run log
(`Candidates: 3, Generated: 3, Errors: 0`) on both the original launch and the H7
relaunch. Sibling contrast: `pdf/net` has 885 pages against 881 extracted classes —
same ~1:1 ratio at two orders of magnitude larger scale, proving no imaging-specific
throttle exists in the pipeline.

## 7. Explanation of the original three-page-plus-index result

Correct and complete. The upstream repo is a deliberately minimal
"format-detection/header-probing only" utility (confirmed by its own README), not a
cut-down mirror of the commercial Aspose.Imaging SDK. Its author keeps all 11 format
handlers `internal`, exposing only 3 public types.

## 8. Existing five-surface coverage assessment

All 5 surfaces manually spot-checked against pinned source this mission
(TC-MT070-06): products (2 files), docs (8 files), kb (3 files), blog (1 English
post) — **0 findings**, including deep per-format implementation claims verified
against actual handler source. Reference surface covered by item 5 above. No
commercial-capability leakage, no fabricated formats/APIs, no publication-status
disclosure, correct license/dependency claims throughout.

## 9. Regeneration-instability findings

None reproduced for this product. Two fresh, isolated `repo-scout` re-runs against
the same pinned SHA are byte-identical to each other and to the tracked committed
snapshot, for every artifact except the expected wall-clock `extracted_at` timestamp
(TC-MT070-07). Reference-page generation logged identical `Candidates: 3, Generated:
3` on both the original launch run and the later H7 relaunch. Whatever prompted the
original "count changed slightly" observation did not reproduce under controlled,
repeated, isolated extraction.

## 10. Confirmed root causes and first failing boundaries

- **ST-195** (confirmed, fixed): `publish_readiness_review_run.py::_find_latest_report()`
  trusted whichever `reports/truth-audit/{family}-{platform}-*.json` candidate had
  the newest mtime with zero shape check. Live-confirmed: `imaging-net-20260911.json`
  is actually `truth_audit.py`'s (S-38, structural) report shape, redirected by an
  untraced caller into S-85's directory — not a second run of the same script. This
  silently satisfied the cross-check gate and produced a false "16/16 PUBLISH"
  verdict during the H7 relaunch (INV-020's real CONDITIONAL findings were masked).
- **IMAGING-NET-SCORECARD-UNICODE-001** (confirmed, fixed): `readiness_scorecard.py`
  printed a literal U+26A0 glyph with no stdout encoding forced, crashing on any
  Windows cp1252 console whenever a subdomain falls >40% below peer median — not
  imaging-specific, reproducible for any small/young product.
- **IMAGING-NET-BATCHREF-HARNESS-001 direction (a)** (confirmed by MT068, diff
  prepared this mission, **not applied** — blocked): S-62's `SKILL.md` documents a
  first-launch invocation (`--run-root`) that is broken for any product with no
  prior published baseline. `.agents/skills/` is outside `path_guard.py`'s allowed
  write paths for agents; `SKIP_SKILL_CONTEXT_CHECK=1` is operator-only and was not
  used. Ready-to-apply diff recorded in
  `evidence/TC-MT070-03-batchref-harness-doc-fix.md`.

## 11. Skills and shared components hardened

`publish_readiness_review_run.py` (S-90 contract), `readiness_scorecard.py` (S-49
contract). Both fixes are general (no imaging-specific branches); both proven against
the real historical imaging/net data plus new synthetic regression fixtures.

## 12. Regression protection added

`test_publish_readiness_review_run.py`: +4 new tests
(`TestTruthAuditReportSchemaValidation`), 3 pre-existing fixtures migrated to a
realistic full-ledger shape (they had been unknowingly relying on the exact stub
shape the fix now rejects). `test_readiness_scorecard.py`: +2 new tests
(`TestParityWarningMarkerIsAsciiSafe`). Both suites: 100% pass (42/42, 44/44).

## 13. Preserved baseline location and manifest

Not applicable — no content was regenerated or modified, so no baseline snapshot was
required. Mission evidence lives at
`reports/plan_state/MT070-2026-09-16-IMAGING-NET-FORENSIC-HARDEN/` (local-only,
`reports/*` is gitignored, matching this repo's established per-mission evidence
convention).

## 14. Old-versus-new page comparison

Not applicable — zero content pages changed across any of the 5 surfaces.

## 15-19. Final inventories (Products / Docs / KB / Blog / API Reference)

Unchanged from MT068's launch, independently reconfirmed this mission: Products 2
files, Docs 8 files, KB 3 files, Blog 1 post × 25 locales, Reference 3 class pages +
1 index. All verified accurate (items 5, 6, 8).

## 20. Source-to-reference coverage result

100% bidirectional: 3/3 source public types have reference pages; 3/3 reference
pages' signatures exactly match the compiled assembly. Zero missing, zero
unexpected, zero collisions, zero orphans.

## 21. Example compilation results

All code examples across all 5 surfaces use only the 5 real `ImageProbe` methods and
5 real `ImageInfo` properties with correct signatures, verified both by direct source
comparison (TC-MT070-06) and by the fact that the underlying assembly itself compiles
cleanly (TC-MT070-01).

## 22. Determinism and no-op results

Confirmed (item 9 / TC-MT070-07): byte-identical repeat extraction; byte-identical
generation counts across two independent real runs.

## 23. Local build results

`dotnet build Aspose.Imaging.Foss.sln -c Release`: 0 errors. Python test suites for
both fixed scripts: 100% pass.

## 24. Published URLs and deployment revision

Unchanged — no publication action taken this mission (nothing to publish).

## 25. Live verification results

Not re-verified live this mission (nothing changed). Relies on MT068's own live
verification, 2026-09-14: HTTP 200 across all five imaging/net surfaces
(`backlog/REMINDERS.md` R-06).

## 26. Remaining limitations / true external blockers

- IMAGING-NET-BATCHREF-HARNESS-001 direction (a): diagnosed, diff ready, blocked on
  `.agents/skills/` write permission (governance boundary, not a technical blocker).
- INV-020's portfolio-wide systemic-exposure question (whether other products' truth-
  audit verdicts read the same stub-shaped report) — imaging/net's own instance is
  resolved by this mission's ST-195 fix; the portfolio-wide check is explicitly
  out of scope, as decided at mission start.
- The exact caller that originally redirected `truth_audit.py`'s output into
  `reports/truth-audit/imaging-net-20260911.json` could not be traced (no git
  history for gitignored `reports/`).

## 27. Exact evidence paths

`reports/plan_state/MT070-2026-09-16-IMAGING-NET-FORENSIC-HARDEN/` — `mission_authority.yaml`,
`taskcards.jsonl`, `evidence/{TC-MT070-01,02,03,04,05,06,07}-*.md`,
`evidence/reflection_api_dump.json`, this file. Governing plan:
`plans/from_backlog/2026-09-16-mt070-imaging-net-forensic-harden.md`. Pushed commit:
`393b9b32d621ee9e84cd137df0ee44ae0a573e4d`.

## 28. Final verdict

**`IMAGING_NET_SOURCE_CONFIRMS_SMALL_PUBLIC_SURFACE`**

Secondary outcome within that verdict: 2 of 3 identified shared-system defects fully
fixed with regression tests and pushed; 1 diagnosed with a ready-to-apply diff,
blocked only by a governance write-permission wall (human action, not a technical
gap).
