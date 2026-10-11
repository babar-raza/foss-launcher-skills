# font/python — upstream README / history / candidate assessment (2026-09-02)

## 1. What actually happened upstream (verified live, disposable clone in scratchpad)

- `aspose-font-foss/Aspose.Font-FOSS-for-Python` `main` is a single **orphan** commit
  `c6d82093` "Release 26.8.4" (AI-Agent-AsposeFontFOSS, 2026-08-27, no parents). The repo has
  **22 orphan roots** — one per weekly release since "chore: sync clean library mirror from
  GitLab 8a43bd99" (2026-05-12). Every release is a fresh snapshot; nothing merged on GitHub
  survives the next Wednesday 21:48 UTC sync. `classify_target_authority` → `mirror` is correct.
- Our PR #1 (`fix(readme): restore preserved-but-lost content …`, head `061e7603`, merged
  2026-08-15T15:22Z onto the 26.8.2 root `136b6e20`) has **no common ancestor** with `main`
  (GitHub compare → 404). It was not edited or reverted — it was discarded by the 26.8.3
  re-snapshot on 2026-08-20.
- **The live README is byte-identical to the pre-PR README** (sha `3de44e20…`, 486 lines,
  21 994 bytes) — the product agent did NOT change or add anything to the README.
- **The source tree is byte-identical since Release 26.6.4 (2026-06-25)**: tree `75a0b491` for
  10 consecutive weekly releases (26.7.1 … 26.8.4), 0 files changed each week. The clone cache
  and the knowledge model (`repo_sha 136b6e20`, same tree) are current; nothing to re-scout.

## 2. Our candidate vs the real old README (skill retention machinery, real extraction)

Real old README: 50 prose units, 2 structural units, 40 code blocks, 0 badges, 20 headings.

- **Prose**: 6 units verbatim (all 5 embedded PNGs + one API bullet); the other 44 carried at
  document scope with fidelity 0.5–1.0 (details in `retention-report.md`). Retained in
  substance; the ledger does not account for any of them (see §3).
- **Code — real losses** (not fingerprint noise; each verified by direct grep of the candidate):
  - Python API demos absent: `font.smart_instancer.instantiate(...)` (+ `ttf_tables.name.get`),
    `axis.localized_labels(...)`, `font.variable_presentation(...)`, `qa_report.write_html(...)`.
  - **CLI**: the real source registers **39** subcommands; the old README demonstrates **26**;
    the candidate demonstrates **9**. 17 real subcommands the old README showed are gone:
    `preview preview-compare preview-family-board preview-family-export preview-grid-sheet
    preview-matrix preview-waterfall var-delta var-delta-compare var-delta-text
    var-delta-text-compare var-delta-text-compare-board var-info var-naming-preview
    web-family web-grid web-grid-family`. `check_cli_category_representation` (advisory)
    reported `[]` — it checks category presence, not subcommand coverage (gap to file).
- **Candidate-quality**: `api_reference_public_type_count_matches_table` (hard): prose claims
  139 public types, table lists 136. At-a-Glance shape, narration, badges-in-candidate: clean.

## 3. Why the audit says dirty — our own ledgers are circular

All four disposition files were written **2026-08-20 15:24 local**, five days after PR #1
merged and six hours before the re-snapshot wiped it: at that moment the clone cache's README
*was our candidate*, so the ledgers describe our candidate to itself — 131 `merged_verbatim`
prose entries (u0001 = our own intro, u0002 = our own TOC), 32 code entries, 3 "preserved"
badges from a README that has none. Against the real old README they produce
`content_unit_disposition_coverage 81`, `excerpt_matches_extraction 50`,
`code_example_disposition_coverage 36`, `code_example_disposition_text_diff 10`,
`badge_disposition_coverage 3`, `structural_* 1+1`. Ingest under checks v4
(run `rr-20260902T104838Z-d00e617b6702`) blocks on exactly these 8 gates — correctly.

## 4. Verdict

- **Do not open a PR as things stand.** Two independent reasons: (a) the target is a weekly
  re-snapshotted mirror — a GitHub PR is wiped on the next sync exactly as PR #1 was; the
  README must be adopted at the GitLab source of truth (or the sync job must preserve
  `README.md`) — a human/upstream decision, the standing hard rule; (b) the candidate itself
  is not shippable: circular ledgers, 17 real CLI subcommands and 4 API demos dropped, one
  hard-gate count mismatch.
- **The candidate needs regeneration, not just hardening**: rebuild the four ledgers against
  the real old README, restore the CLI and API demonstrations, fix the 139/136 count, then
  re-verify (S-120 ingest → verify-examples --python-runner → recheck). Prose can largely be
  kept; the retention report gives the per-unit fidelity to work from.
- Skill capability shown by this pass: it found the circular ledger, the count mismatch, and
  every retention loss mechanically; it cannot compose (agent-authored by design) and its CLI
  heuristic cannot see subcommand-level drops (follow-up).
