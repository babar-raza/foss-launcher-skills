# MT015-2026-07-30-PACKAGE-REGISTRY — Evidence Bundle (2026-08-01)

## Baseline
- Repo root: `d:\onedrive\Documents\GitHub\aspose.org`, branch `main`
- Session-start HEAD: `cf6b23d92b`
- Pre-existing baseline test failures (both confirmed unrelated, both still present today): `test_foss_packages_data.py::test_slides_is_not_published` (stale pin), `test_metrics_autonomous_capture.py::TestAT16_DocPropagationCheckPasses::test_docs_propagation_strict_passes_live_repo`

## Commits this session (chronological)
| SHA | Subject | Taskcard |
|---|---|---|
| `2b8847ff01` | chore(governance): register MT015 package-registry mission in backlog | TC-MT015-00 |
| `4bca850b2a` | feat(pipeline): unified package-registry schema + install_recipe guard wiring | TC-MT015-01/03 |
| `1e0c51e92e` | fix(pipeline): install_recipe.py H-16 ran docs-subdomain-only, missed kb/blog/products (ST-047) | TC-MT015-13 |
| `48e03d4cf5` | feat(pipeline): pypi/npm/nuget/go package-registry adapters + debounce | TC-MT015-04 |
| `280e4c6b6d` | feat(shortcodes): repoint maven-coord/maven-gav/cargo-crate at unified package_registry.json | TC-MT015-02 |

## Taskcard store
`reports/plan_state/MT015-2026-07-30-PACKAGE-REGISTRY/taskcards.jsonl` — 15 records, all schema-5f valid (`validate_taskcard_record`).
- `INDEPENDENTLY_REVIEWED`: TC-MT015-01, -03, -04, -13
- `END_TO_END_VERIFIED`: TC-MT015-02 (Hugo binary found via winget after being marked BLOCKED_EXTERNAL; real byte-parity proof against a live Hugo build, 0/14820 file diffs; caught and fixed a real migration bug along the way)
- `IN_PROGRESS`: TC-MT015-00 (governance seed; MISSION_AUTHORITY.yaml sub-item standing-deferred, root slot held by live MT014-2026-07-29-PDF-GO-REDO)
- `TODO`: TC-MT015-05, -06, -07 (re-scoped, see below), -08, -09, -10, -11, -12, -14 (new: migrate publish_watcher.py + knowledge/index.py off the old data files, then delete them)

## Gap-escalation report
`reports/skill-gaps/2026-07-31-package-registry-identity.md` (local, gitignored per repo convention)

## Verification
- Full regression suite reruns this session: 42→2 (unrelated, pre-existing)→2 (unrelated, pre-existing) failures across 3 runs, 7979→8081→8103 passed. Zero new regressions attributable to any change made this session.
- `check_monkeypatch_lint.py`: clean on every new/modified test file.
- Independent verification pass (separate agent, did not implement any of this work): all 8 checked claims VERIFIED against primary sources (commit diffs re-read, tests independently rerun with exact count match, ST-047 fix independently exercised against a constructed test case, Hugo-unavailable claim independently confirmed, .csproj-vs-Cargo.toml root cause independently re-read from the actual cloned FOSS source). Zero refutations. Full report preserved in this conversation's transcript.

## Root causes repaired this session
1. `install_recipe.py` H-16 (package-identity check) was unreachable from the actual pre-write enforcement gate (`no_downgrade_guard.py`) — wired in (TC-MT015-01/03 commit).
2. H-16, once wired, was still only checking `docs.aspose.org` pages — ST-047, found via a concurrent session's real 3D-NET-REFRESH-002 remediation, fixed (TC-MT015-13 commit).
3. No unified package-registry schema existed (Maven/Cargo split, no owner-verification field) — `data/package_registry.json` + validator + migrated data built (TC-MT015-01).
4. No publish-detection mechanism existed for PyPI/NuGet/npm/Go Modules — 4 adapters + debounce built (TC-MT015-04); the scheduled watcher skill that calls them (TC-MT015-09) is not yet built.

## Historical outputs healed
None yet — TC-MT015-06 (slides/net content retrofit) has not been attempted (correctly sequenced after TC-MT015-05, still `TODO`).

## Resolved external blocker
TC-MT015-02: Hugo was found installed via `winget` (`Hugo.Hugo.Extended` v0.154.5) after initially being marked `BLOCKED_EXTERNAL`. Real byte-parity was proven via two back-to-back Hugo builds (git-stash sandwiched) with `HUGO_PARAMS_SEARCH_ENABLE=false` (this repo's own established convention for eliminating Hugo's independently-nondeterministic search-index fingerprint from a build comparison) — 0/14,820 file-hash differences across every product/locale/subdomain that uses these shortcodes, after fixing a real migration bug (slides/java) the check caught along the way.

## Remaining scope (not a false-complete claim)
TC-MT015-05, -06, -07 (re-scoped: needs a naming-convention-fallback design decision, not just "wiring"), -08, -09, -10, -11, -12, -14 (new, deferred old-file deletion) — all genuinely `TODO`, not started.

## Known limitations
- NuGet adapter cannot verify publisher identity (flatcontainer API doesn't expose it) — `owner_match` will remain null for NuGet entries even after TC-MT015-09 ships, unless a future pass adds NuGet Gallery search-API/scraping support.
- `data/package_registry.json`'s migrated `owner_match: null` for all 5 existing Maven/Cargo entries is an honest carry-forward of a gap the old system also had — not newly introduced, not yet closed.
- `MISSION_AUTHORITY.yaml` registration for MT015 remains deferred, not done — by design, given the live concurrent mission holding that slot.
