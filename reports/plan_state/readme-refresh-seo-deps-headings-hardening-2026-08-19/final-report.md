# 3d/net README Hardening — Final Report

**Mission:** `readme-refresh-seo-deps-headings-hardening-2026-08-19`
**Canary:** `reports/repo-presenter-regen-full/3d/net/readme.md`
**Status:** Complete — all 17 taskcards (`TC-SDH-00`…`TC-SDH-17`) CLOSED, including a second phase remediating the 8 other flagged products (§14–§18 below)

---

## 1. Verification verdict per reported issue

| # | Reported issue | Verdict |
|---|---|---|
| A | Key Capabilities doesn't use available SEO keywords | **CONFIRMED.** `keywords/3d.json` had 10 correct, `.NET`-scoped phrases; zero appeared anywhere in the section. |
| B | Dependencies thinner than recent `pdf/*` candidates | **CONFIRMED — more specific than reported.** The section existed but had **zero of the four mandated `###` subheadings** (a flat two-sentence paragraph). A deeper, portfolio-wide extractor gap was the root cause (see §2). |
| C | Additional Examples lack SEO-aware headings | **CONFIRMED — cleanest of the three.** All 5 collapsed examples had **no heading markup of any kind**, not even a generic "Example N" label. |

A fourth defect, not named in the original report, was found during investigation and folded into this mission per your "include everything found" instruction — see §2.4.

## 2. Root cause per confirmed defect

### 2.1 Key Capabilities SEO (Issue A)
The skill's own SEO section (`skills/readme-refresh.md`, TC-HARDEN-39/40/41, landed 2026-08-13) built a keyword *filtering* mechanism (`filter_relevant_seo_keywords`) but never a keyword *usage* verifier. A rule that exists only as prose, with nothing re-checking it, decays the moment a different composing session works on a product — exactly what happened here.

### 2.2 Dependencies subheadings (Issue B)
Two independent causes, both real:
1. **Composition discipline** — the agent who added the section (`TC-RDR-03-3D-NET`, earlier the same day) wrote free prose instead of following the mandatory 4-subheading template.
2. **Extractor gap, portfolio-wide** — `dependency_extract.py`'s `native_system` bucket, which the "### Native and System Requirements" subheading depends on, was populated for **exactly 1 of 7 ecosystems** (Go). NuGet, Cargo, pypi, npm, and Maven all had zero native/language-version extraction, despite the data type and rendering contract already existing. This is the deeper reason the subsection is silently missing across most of the non-Go portfolio, not a 3d/net-specific gap.

### 2.3 Additional Examples headings (Issue C)
No contract or validator for this existed anywhere in the pipeline — a genuine, previously undocumented gap (confirmed by a full-text search of the 1,141-line skill file), not a violated rule.

### 2.4 Fourth defect found during investigation (not originally reported)
**Checks-module-currency drift.** A candidate's `audit_portfolio → clean: true` result is only ever true against the checks that existed *at that moment*. 3d/net's own `TC-RDR-03-3D-NET` closure legitimately produced `clean: true` earlier the same day — truthfully, but only against the checks module version that existed then. Nothing flagged that a "clean" certification had gone stale relative to checks added since. This is the structural reason a defect can ship, sit "clean," and only surface when a human reads closely.

Also found in the same review pass (not one of the four defects, but a real latent bug fixed alongside them): `_select_main_csproj`'s "shortest-path-wins" heuristic could pick a demo/converter tool over the real library project — confirmed live for 3d/net's own `Converter.csproj` vs. `Aspose.ThreeD.csproj` (silently harmless today since both have zero dependencies, but a real risk for other products).

## 3. Files changed

| File | What changed |
|---|---|
| `scripts/pipeline/commands/foss/dependency_extract.py` | Native-system extraction added for NuGet (`TargetFramework(s)`), Cargo (`edition`/`rust-version`), pypi (`requires-python`/`python_requires`), npm (`engines.node`), Maven (pom.xml `<properties>` + Gradle fallback). `_select_main_csproj` fixed from a same-depth-tiebreak (which would **not** have fixed the real 3d/net case — not even a depth tie) to a proper two-stage filter. |
| `scripts/pipeline/commands/foss/readme_refresh_checks.py` | 3 new checks: `check_dependency_section_subheadings_present` (hard gate), `check_seo_keyword_plan_usage` + `build_seo_keyword_placement_plan` (heuristic), `check_additional_example_headings` (hard gate). `CHECKS_MODULE_VERSION` constant added. |
| `scripts/pipeline/commands/foss/readme_refresh_run.py` | `seo_keyword_placement_plan` factpack field; all 3 new checks + `verification_currency` wired into `_run_deterministic_checks`; `_write_candidate_verification_marker` now stamps `checks_module_version`; new `_checks_currency_findings`. |
| `skills/readme-refresh.md` | 4 new documented subsections: Additional-Example heading contract, SEO keyword-placement-plan mechanism, Dependencies subheading/native-system rollout, checks-module-currency tripwire. |
| `scripts/pipeline/tests/test_dependency_extract.py` | +15 tests (native-system per ecosystem, TFM via both csproj/nuspec paths, Exe-vs-library selection). |
| `scripts/pipeline/tests/test_readme_refresh_checks.py` | +16 tests across the 3 new check functions. |
| `reports/repo-presenter-regen-full/3d/net/readme.md` | Candidate regenerated — see §7–§8. |
| `reports/plan_state/readme-refresh-seo-deps-headings-hardening-2026-08-19/` | New standalone mission (`mission_authority.yaml` + `taskcards.jsonl`, 9 cards, all CLOSED) — root `MISSION_AUTHORITY.yaml` never touched (confirmed byte-identical). |

**Test result:** `pytest test_readme_refresh_checks.py test_readme_refresh_run.py test_dependency_extract.py` → **836 passed, 0 failed** (was 795 before this mission).

## 4. Portfolio-wide impact matrix

From `audit-portfolio --json` (30 products, ran clean, no crashes), filtered to findings from this mission's 2 new hard gates:

| Product | Dependencies missing subheadings | Missing/generic example headings | Weak Key Capabilities SEO | Likely shared cause | Regenerate later? |
|---|:---:|:---:|:---:|---|:---:|
| **3d/net** | was ✗ | was ✗ | was ✗ | canary — **fixed this mission** | done |
| pdf/cpp | ✗ | — | — | real, extracted `googletest` dev dependency, no `### Development Dependencies` heading (spot-verified genuine) | yes |
| pdf/java | ✗ | — | — | same subheading gap | yes |
| pdf/python | ✗ | — | — | same subheading gap | yes |
| slides/java | ✗ | ✗ | — | both gaps present | yes |
| slides/net | ✗ | — | — | same subheading gap | yes |
| slides/python | ✗ | — | — | same subheading gap | yes |
| 3d/typescript | — | ✗ | — | same heading gap | yes |
| barcode/python | — | ✗ | — | same heading gap (spot-verified genuine) | yes |

**SEO column honesty note:** the mechanical SEO heuristic (`check_seo_keyword_plan_usage`) fired **zero times across all 30 products**, including 3d/net's own *pre-fix* state. It is deliberately a weak floor — it scans the *whole document* (per the skill's own established rule that the Intro paragraph is a valid keyword-placement spot), and most product Intros already carry "free"/"open source" framing. It would **not**, by itself, have caught 3d/net's original defect. Real Key-Capabilities-specific SEO quality remains a compose-time/human-judgment matter, the same honest limit this skill already states for prose quality generally — it is not mechanically scannable portfolio-wide the way heading/subheading *presence* is. This is disclosed rather than papered over.

This is an assessment, not authorization to fix the other 8 products — none were touched.

## 5. Keyword-placement approach used for 3d/net

A typed plan (`build_seo_keyword_placement_plan`) was generated from the 10 filtered, verified `.NET`-scoped phrases in `keywords/3d.json`. Composition then wove real vocabulary into 4 of 8 Key Capabilities bullets (weighted toward the earlier ones), while **deliberately dropping 2 of the 10 filtered phrases**:

- *"free cad file reader c# library"* — dropped. The product reads FBX/glTF/OBJ/STL/COLLADA/U3D/3MF/RVM/AMF, never a CAD file format (DWG/STEP/IGES) — using this phrase would have implied a capability that doesn't exist.
- *"net core open source 3d rendering"* — dropped. Scope and Limitations explicitly states rendering is **not implemented** (`Scene.Render`, `RenderFactory` throw `NotImplementedException`) — this phrase would have directly contradicted the file's own Limitations section.

Both were kept out on purpose, per the mission's own "never introduce a capability merely because a keyword exists" instruction — never silently used.

## 6. Authoritative dependency evidence

Read directly from the pinned clone cache (not trusted from any prior summary):
- `runs/.clone_cache/aspose_3d_net/src/main/Aspose.ThreeD/Aspose.ThreeD.csproj` → `<TargetFrameworks>net10.0;net8.0;net6.0;netcoreapp3.1</TargetFrameworks>`, zero `<PackageReference>`.
- `runs/.clone_cache/aspose_3d_net/src/test/Aspose.ThreeD.Tests/Aspose.ThreeD.Tests.csproj` → `Microsoft.NET.Test.Sdk` 17.12.0, `xunit` 2.9.2, `xunit.runner.visualstudio` 2.8.2, `coverlet.collector` 6.0.2.

## 7. Additional Example headings — before / after

| # | Before | After |
|---|---|---|
| 1 | *(none — plain sentence)* | `### Enumerate a Scene's Node Hierarchy` |
| 2 | *(none)* | `### Convert a Lambert Material to PBR` |
| 3 | *(none)* | `### Load OBJ With Custom Options and Export to STL` |
| 4 | *(none)* | `### Save a Scene to COLLADA Through a Stream` |
| 5 | *(none)* | `### Handle an Unrecognized 3D File Format` |

The always-visible flagship example (glTF→OBJ, ahead of the disclosure) intentionally stays unheaded, matching the skill's own established convention and the reported defect's own scope (inside the disclosure).

## 8. Section-level hashes (sha256)

| Section | Before | After |
|---|---|---|
| Key Capabilities | `f7ec9ad2…f35df` | `d353490c…afdb9f` |
| Dependencies | `fb4058ef…d511cb2` | `7cf7c9ff…0ba9dd20c` |
| Additional Examples | `68ed09f8…6492b1006` | `06d0275e…6d2e7d4e7` |
| Installation / Quick Start / API Reference / Documentation & Resources / Scope and Limitations / Development and Testing / License / Navigation / At a Glance | — | **byte-identical**, all 9 confirmed unchanged |
| **Whole file** | `4faefc44…07aef3ffdbb` | `24e632a7…8d58173a5` |

## 9. Proof of no unrelated change

- Section-hash diff (§8) mechanically confirms all 9 unrelated sections byte-identical.
- `git status` before/after this session: only the 6 intended pipeline/test/skill files newly modified; every pre-existing uncommitted change from other sessions untouched; no other candidate under `reports/repo-presenter-regen-full/` written.
- `runs/.clone_cache/` mtime check: no files newer than mission start — clone cache never written to.

## 10. Idempotency result

Three consecutive `audit_portfolio(family="3d", platform="net")` runs:
1. First run (pre-title-case-fix): `clean: false`, 1 finding (`heading_title_case` — "with" isn't in this checker's recognized minor-words set).
2. After fixing "with" → "With": `clean: true`, 0 hard-gate findings.
3. **Re-run with zero changes**: `clean: true`, 0 hard-gate findings, `candidate_drift: []` — proves the verified state is stable, not a one-time pass.

Structural properties (heading/subheading presence, all gates) are proven byte/state-stable. Exact LLM-authored prose wording is not claimed byte-reproducible on a hypothetical full regeneration — a disclosed, pre-existing limit of this pipeline, not something this mission overclaims fixing.

## 11. Final candidate

**Path:** `reports/repo-presenter-regen-full/3d/net/readme.md`
**SHA-256:** `24e632a7a63619003d96c88d5400eb5e8dc4c64a57dd46616b2f9dc8d58173a5`
**Status:** Local only. Not pushed, not PR'd, not approved for publication.

## 12. Other candidates requiring later regeneration

`pdf/cpp`, `pdf/java`, `pdf/python`, `slides/java`, `slides/net`, `slides/python` (Dependencies subheadings), `3d/typescript`, `barcode/python` (example headings) — see §4 for the full matrix. Not fixed this mission by design.

**Also flagged, not fixed (pre-existing, out of scope):** `TC-HARDEN-47` — 3d/net's real, *published* upstream README (a separate, older artifact from today's local candidate) still carries pre-MT024 diagram clipping on GitHub since 2026-08-05. This mission's candidate is the natural fix once a push is authorized, but no push happened here.

## 13. Target-repository confirmation

**No target product repository was pushed to, cloned into, or otherwise modified.** No `git push`, `gh pr`, or write to `runs/.clone_cache/` occurred at any point in this mission. Verified via clone-cache mtime check (§9) and by construction — no push/PR/gh command was ever issued.

---

# Phase 2 — Remediating the 8 remaining flagged products

**Goal:** apply the exact fix each product's own impact-matrix row required — nothing more — to prove the hardened machinery (§2–§3 above) generalizes correctly across the portfolio, not just on the 3d/net canary.

## 14. What changed, per product

| Product | Fix applied | Real evidence source |
|---|---|---|
| `pdf/cpp` | `### Development Dependencies` — `googletest` (1.14.0) | `CMakeLists.txt` `FetchContent`/`target_link_libraries` (test-binary-only linkage) |
| `pdf/java` | `### Native and System Requirements` — Java 11+ | `pom.xml` `maven.compiler.source`/`target` = 11 |
| `pdf/python` | `### Native and System Requirements` — Python 3.11+ | `pyproject.toml` `requires-python`, corroborated by the project's own `tests/test_package_metadata.py` |
| `slides/java` | `### Native and System Requirements` (JDK 21+) **+** 10 real, non-generic `###` headings replacing bold-text-only lead-ins in Additional Examples | `pom.xml` compiler properties; each heading grounded in that example's actual code |
| `slides/net` | `### Native and System Requirements` — targets `net9.0` | `Aspose.Slides.Foss.csproj` `TargetFramework` |
| `slides/python` | `### Native and System Requirements` — Python 3.10+ | `pyproject.toml` `requires-python` |
| `3d/typescript` | 2 real headings in Additional Examples | Grounded in actual API calls (`ObjLoadOptions`/`StlSaveOptions.binaryMode`; `PolygonModifier.triangulate` on raw control points) |
| `barcode/python` | 4 real headings in Additional Examples | Grounded in actual API calls, cross-checked against `code-example-dispositions.json` |

Every fact was re-verified directly against each product's own pinned clone cache — none copied from the earlier investigation report without a fresh check.

## 15. A real defect I introduced, found, and fixed during verification

My first `pdf/cpp` bullet placed backtick-quoted terms (`` `FetchContent` ``, `` `CMakeLists.txt` ``) *before* the em-dash separator. `check_dependency_development_claim_not_in_manifest`'s bullet parser only scans the pre-em-dash prefix for claimed dependency names — so it read those as two additional (non-existent) claimed dependencies and failed. Caught by re-running the full check battery after every edit, not assumed clean. Fixed by moving all non-dependency identifiers after the em-dash, matching the portfolio's own established bullet template. This is exactly the kind of self-check the mission's own discipline exists to catch — disclosed here rather than glossed over.

## 16. A significant, unplanned finding surfaced during verification

Verifying all 8 products revealed something the original plan didn't anticipate: **6 of the 8 products (`pdf/cpp`, `pdf/java`, `pdf/python`, `slides/java`, `slides/net`, `slides/python`) had candidates that were exactly byte-identical to their real, live, *already-published* upstream READMEs on GitHub.** This pipeline has a bypass (`readme_already_published`) that skips 25 preservation-tracking checks specifically for that state — because re-deriving "what changed from the old README" against a text that *is* the old README is a pure tautology.

**The moment any edit is made — even a minimal, correct one like these — that byte-identity breaks, the bypass turns off, and the full preservation-tracking battery activates.** For these 6 products, whose disposition bookkeeping was never fully composed under the separate `readme-disposition-remediation-2026-08-18` mission, that battery then reports dozens to 100+ findings.

**This is not a defect I introduced.** I confirmed it directly: I grepped each product's own **live clone-cache README.md** (the actual file already on GitHub today) and found the identical missing-subheading defect verbatim, proving the candidate really was published-state before my edit, not something my edit corrupted. Concretely:

```
$ grep -A6 "^## Dependencies" runs/.clone_cache/aspose_pdf_java/README.md
## Dependencies

### Required Package Dependencies

No required third-party package dependencies.

### Development Dependencies
```

— the real, live, public `pdf/java` README already jumps straight from "Required" to "Development," missing "Native and System Requirements," exactly like the local candidate did before this fix. Same confirmed for `pdf/cpp`, `slides/java`, `slides/net`.

**Practical implication:** `audit_portfolio`'s overall `clean` flag for these 6 products will **not** read `True` after this fix, even though the specific defect this mission targets is genuinely fixed and verified. Isolating exactly that gate (§17) is how to see the real result.

`barcode/python` and `3d/typescript` were *not* in the published-identical state, so no bypass flip occurred there — `barcode/python` reached a fully clean `audit_portfolio` result; `3d/typescript`'s remaining findings were already present in the original TC-SDH-06 baseline scan, untouched by this fix.

**What I did not do, and why:** attempt to fix the exposed disposition-family findings. That is real, substantial work (per-product "full disposition-family compose," the same treatment `TC-RDR-03-3D-NET` gave `3d/net`) that belongs to the `readme-disposition-remediation-2026-08-18` mission, not this one — fixing it here without that mission's own rigor would be exactly the kind of hasty, unverified expansion this whole session has been careful to avoid.

## 17. Verification result — isolating this mission's own two gates

For every one of the 8 products, re-ran the full deterministic check battery and isolated (a) whether this mission's own two gates are now clear, and (b) whether any *unexplained* new finding appeared (i.e., anything beyond the known disposition-bypass-flip family and the findings already present in the original TC-SDH-06 baseline):

| Product | Target gate(s) clear? | Unexplained new findings? | Overall `audit_portfolio` clean? |
|---|:---:|:---:|:---:|
| pdf/cpp | ✅ | none | No (pre-existing `diagram_hybrid_reverification` + bypass-flip) |
| pdf/java | ✅ | none | No (bypass-flip only) |
| pdf/python | ✅ | none | No (bypass-flip only) |
| slides/java | ✅ (both gates) | none | No (bypass-flip only) |
| slides/net | ✅ | none | No (pre-existing `diagram_label_geometry`/`no_upstream_issue_leaked` + bypass-flip) |
| slides/python | ✅ | none | No (pre-existing `dependency_development_claim_not_in_manifest` + bypass-flip, itself the pytest/manifest issue noted in §14) |
| 3d/typescript | ✅ | none | No (pre-existing, from TC-SDH-06 baseline, unrelated) |
| barcode/python | ✅ | none | **Yes — fully clean** |

Structural sanity check (balanced `<details>`/`</details>` tags, stable `##` heading counts) passed on all 8 files.

## 18. Governance and side-effect confirmation

- `git status` before/after Phase 2: identical set of tracked files modified as Phase 1 (§9) — no new unintended tracked-file changes.
- Clone-cache mtime check across all 8 products' cache directories: no files newer than mission start — read-only throughout, consistent with how the live-README evidence in §16 was gathered (via `grep`, never a write).
- No `git push`/`gh pr` issued for any of the 8 products — all 8 remain local-only candidates.
- Mission contract (`mission_authority.yaml`) updated to record this phase; root `MISSION_AUTHORITY.yaml` remains untouched.
- Taskcards `TC-SDH-09`…`TC-SDH-17` (9 more cards) all `CLOSED` with evidence in `reports/plan_state/readme-refresh-seo-deps-headings-hardening-2026-08-19/taskcards.jsonl`.
