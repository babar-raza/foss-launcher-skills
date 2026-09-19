# Investigation: what writes hardcoded install commands where a shortcode should be

Investigator B (read-only, 2026-09-19), base commit `c2fee380d6`. Persisted verbatim from the
agent's returned findings by the supervisor (the harness does not let subagents write report files).
Method: streamed `git log -p --unified=0 -- content/` over all 2,695 content commits through a
per-commit/per-file shortcode-vs-literal counter; a full-corpus current-state scan; a live run of the
repo's own install gate; a fixture probe of the gate's detection logic. No file under `content/`, no
sibling repo and no git index was modified.

## 1. Ranked table of processes that write hardcoded install commands

| # | Process | Evidence | How often | Replaces a shortcode? | Active today? |
|---|---|---|---|---|---|
| 1 | Locale copies frozen before the English page migrated (translation output 2026-03 to 2026-07, committed before the shortcode existed) | 4,158 of 4,168 live findings (99.8%) are locale copies; 18/18 sampled divergent pages verified frozen before their EN source migrated. e.g. `content/blog.aspose.org/font/python/eot-fonts-in-python/index.cs.md:320` (committed `b92dd6c450`, 2026-09-15) vs EN migrated `3c5b8e804e` 2026-09-18 | ~3,029 files, one-time sediment | No | Sediment is live; new creation ~stopped |
| 2 | Deferred translation adoption (`content(translation): prior translated ... batch`, "pre-existing translated content adopted into governed S-76 session", Co-authored-by Codex) | `b92dd6c450` added 72 literal lines in one commit; 25 such commits landed 2026-09-15 to 2026-09-19; 86 literal lines post-shortcode | 86 lines / 86 file-touches since 2026-08-01 | No: block shortcodes survived translation (`sc+ 1` in the same files) | Yes |
| 3 | Generation/healing skills with no shortcode instruction | 3D-NET-REFRESH-002 (`df5f430488`, `201ab32045`, `e5bf6ebf8b`, `fe4d4c598f`, all 2026-08-01) wrote `dotnet add package Aspose.3D.Converter --version 1.0.0` (a package that never existed) into 11 English pages. Still live: `content/docs.aspose.org/en/3d/net/getting-started/installation.md:108`, `content/products.aspose.org/en/3d/net/_index.md:97` | 21 English lines post-shortcode, all on 2026-08-01 | No (added to pages that had no shortcode) | Yes: 23 skills still unaware |
| 4 | `skills/new-docs-index.md:139` (+ `.claude/commands/` mirror) actively instructs writing ``Install with `dotnet add package {package_name}`.`` into `content/docs.aspose.org/en/{family}/{platform}/_index.md` | Line 139 verbatim; matches the live defects in `docs/en/3d/net/_index.md` and `docs/en/cells/net/_index.md` | Every `/new-docs-index` invocation | No, but creates new literals | Yes: live instruction |
| 5 | Locale "reviewed translation" batches landing after EN migrated | `72d00ab87e`, `e7673eabce`, `462b9c466e`, `b9dfc3c0fc`, `473438043b`, `7e486c46eb` (cells/go, 2026-09-05/06): ~24 literal lines not present in the EN source at that commit | 6 commits | No | Yes: the only repeating post-shortcode regression class |
| 6 | Translator mangling inline literals (not shortcodes) | `content/docs.aspose.org/da/slides/net/_index.md:29` became `dotnet add-pakke Aspose.Slides.Foss` (EN line 30 is now the shortcode). Also `pip install dan` (id), `pip install och` (sv); ~67 files per the `package_install_literal.py` docstring | ~67 files | No: corrupts literals; shortcodes are parser-protected | Yes (risk removed only by migrating to shortcodes) |
| 7 | ST-054/MT066 migrator residual | `65c59fbaba` left 35 leftover literals on partially-converted lines; its message discloses a 322-finding residual | 1 commit | No | Being worked |
| 8 | `install_block_updater.py` | Shortcode-aware since `4565e7d2a0` (2026-09-10, line 422 `_has_install_shortcode`), English-only | 0 observed replacements | No | Safe |
| 9 | CI automation / bots | `github-actions[bot]` `chore(package-registry)` commits touch only `data/package_registry.json`. `package_publish_watch.py` never writes `content/`. Exactly 1 bot commit ever touched content (`1e5d3b6740`, unrelated) | n/a | No | Cleared |
| 10 | Concurrent sessions' uncommitted work | 161,034 content `.md` files compared byte-for-byte vs HEAD: 168 differ, 0 changed install shape, 0 new untracked files with literals. `content/docs.aspose.org/en/page/python/getting-started/installation.md:64` still carries the `package-install` shortcode in both | n/a | No | Cleared |

## 2. Direct answer: what is causing shortcodes to be replaced

Nothing is. Across the entire history of `content/` (2,695 commits, 718 of which changed an
install-relevant line) the count of commits that removed a `package-install` / `package-install-inline` /
`maven-coord` / `maven-gav` / `cargo-crate` line and added a literal install command in the same file is
zero. Only 3 files ever lost a shortcode, all English, all whole-section removals with no literal added
(`862aa95fe3` x2 kb/pdf/python, `6b2068f11b` tex/python).

What the owner is seeing is four different things that look like replacement:

1. Locale lag. The migration was English-first and two-phase: `package-install` landed 2026-08-01
   (`68e6a36c1f`), `package-install-inline` only 2026-09-10 (`42249b40ef`). For those 40 days no
   inline-safe shortcode existed, so every ``Install with `<literal>`.`` sentence was structurally
   un-migratable. ~12,300 locale copies were frozen before their English page migrated and still carry the
   pre-migration literal. Verified exhaustively: 18/18 divergent English pages = lag, 0 = post-migration write.
2. Deferred adoption of old translations. Translations produced at time T are committed weeks later, with no
   check that the English source still looks the same.
3. Skills that never learned the shortcode exists. 6 generation skills are shortcode-aware (`launch-product`,
   `new-blog-post`, `new-docs-page`, `new-kb-faq`, `new-kb-howto`, `new-products-page`); 23 are not
   (`page-draft`, `page-update`, `page-enhance`, `heal-page`, `heal-batch`, `batch-remediate`,
   `new-reference-page`, `new-reference-index`, `new-docs-index`, `new-kb-index`, `new-blog-index`,
   `batch-reference`, `refresh-product`, `refresh-product-page`, `body-refresh`, `faq-generate`, `family-sync`,
   `content-enrich`, `ht-translate`, `ht-translate-batch`, `locale-patch`, `register-human-content`,
   `section-enhance`), and one of them tells the agent to hardcode.
4. Nothing stops any of it, because every gate is English-only, advisory, or attached to a workflow that
   structurally never fires.

Scale: ~32,000 literal install lines were written into `content/` before the shortcode existed (peaks:
11,403 in 2026-03; 10,719 in 2026-07). After it landed: 21 lines in 2026-08, 212 in 2026-09, a ~98% drop.
The shortcode program worked; the backlog is sediment, and the leak is small but real.

Live measurement (`install_literal_sweep --no-persist`): 21,041 files checked, 3,029 files with findings,
4,168 findings: 10 English (0.2%), 4,158 locale (99.8%). Divergence scan: 412 locale files have zero
shortcodes plus a literal while EN has a shortcode (18 distinct EN pages); 1,009 have fewer shortcodes than
EN; 1,631 have both a shortcode and a literal (the 40-day-gap residue); only 11 EN pages still contain a literal.

Notable still-live English defects: `Aspose.3D.Converter` (never existed; real identity `Aspose.3D.FOSS`) in
2 files, and `Aspose.Cells_FOSS` (underscore; real identity `Aspose.Cells.FOSS`) in 6 KB/docs files
(`d758724aae` fixed only `installation.md`).

## 3. Gate blind spots proven

- B-1 pre-commit install gate is English-only. `scripts/pre-commit-audit.sh:278-283` filters staged files
  through `grep -E '(/en/|^content/blog\.aspose\.org/.*/index\.md$)'`. Sandbox run against 7 simulated staged
  paths: only 2 survive; dropped were `docs/de/...`, `kb/ru/...`, `blog/**/index.cs.md`, `products/vi/...`,
  `reference/fr/...`. It cannot see 99.8% of the defect class.
- B-2 the portfolio audit is advisory and English-only. `.github/workflows/content-governance-checks.yml:142-145`
  runs `audit.py all` under `continue-on-error: true`, and its regression checker is also `continue-on-error: true`.
  `audit.py all` resolves files via `scripts/pipeline/lib/content_discovery.py:48-54` (`SITE_PATHS` all pinned to
  `.../en/...`) and `:98-101` (`if LOCALE_RE.search(f.name): continue`): locale files are never read.
- B-3 the only CI job wired to `check_install_recipe_safety_fails.py` never runs. It is invoked solely at
  `.github/workflows/content-audit.yml:194`; that workflow is `on: pull_request` and its own header (lines 3-14)
  states it "has never actually run against a real content change." Its 18 uncovered checks were migrated to
  `content-governance-checks.yml`; the install check was not among them.
- B-4 four holes in the detector itself (fixture probe of the real `verify_package_install_literals`): a literal
  inside a markdown heading or `heading:` field gives no finding (`_is_noise_line`, line 147); any package token
  without the substring "aspose" gives no finding (`_is_noise_match`, line 137), including `cells/typescript`'s
  real registry candidate `excel-cells` and any invented wrong name like `spreadsheet-toolkit`; `yarn add` /
  `pnpm add` / `uv add` / `poetry add` / `paket add` / `go install` give no finding (`_INSTALL_CMD_RE`, line 83,
  knows only 5 verbs plus `<PackageReference>`). Positive controls (prose, fenced code, YAML frontmatter,
  `python -m pip install`) all correctly FAIL.
- B-4b worst case is invisible. The translator-corrupted `dotnet add-pakke Aspose.Slides.Foss` in
  `content/docs.aspose.org/da/slides/net/_index.md:29` yields 0 findings (the regex requires the exact English
  verb). A non-runnable command passes every gate.
- B-5 `reference.aspose.org` is outside the sweep entirely. `install_literal_sweep.py:58-59` lists only
  docs/kb/products (+blog by suffix). 121 files under `content/reference.aspose.org/` contain Aspose literal
  install commands, in no sweep or report.
- B-6 the sweep is advisory and its in-repo trigger is off. It opens an issue/PR; it never fails a build. Its
  schedule was migrated to the sibling `aspose.org-workflows` repo (MT069 PHB-06) and PR-gated.
- B-7 plumbing commits fire no hooks. `git_plumb_commit.py` uses `commit-tree`/`update-ref`; even the
  English-only Step 5 gate is bypassable by construction (documented in `CLAUDE.md` itself).
- B-8 locale literals are structurally unrepairable. `install_block_updater.py` refuses non-English paths
  (`_target_locale_verdict` + path/filename fallback), and `locale_patch.py` (S-75) requires a byte-identical
  `old_text` and correctly declines on diverged translations (its docstring cites the Danish `add-pakke` case).
  The 4,158 locale findings can only go staler.

Translator verdict (cleared on shortcodes): hugo-translator's `src/translation_engine/parser/hugo_parser.py:34`
splits `{{< ... >}}` into non-translated `INLINE_HTML` nodes; line 70 declares fenced-code content passed
through untouched; `src/translation_engine/validation/shortcode_preservation_validator.py` treats any
added/removed/renamed/param-changed shortcode as a fail-closed ERROR; `src/cli.py:1502` skips already-translated
outputs unless `--force-retranslate`. Empirically confirmed (`b92dd6c450` produced locale files with `sc+ 1`).
Two real weaknesses: inline code spans are not protected like fenced blocks (the `add-pakke` corruption), and
`--force-accept` disables validation completely (`src/cli.py:239-242`, gated by `--i-understand-data-loss` at
`:3211`); the S-HT skills forbid it (`skills/ht-translate.md:57`), but the machine's operating notes historically
recommend it for a CJK/RTL false positive.

## 4. Ranked prevention list (nothing implemented)

| # | Fix | Closes | Effort | Risk |
|---|---|---|---|---|
| 1 | Delete the literal example at `skills/new-docs-index.md:139` (+ mirror) and add one shared shortcode paragraph (copy `new-kb-faq.md:108`) to all 23 unaware content-writing skills | The only live instruction to hardcode; source of new EN literals | XS (~24 text edits) | Very low |
| 2 | Extend pre-commit Step 5 to run only `verify_package_install_literals` over every staged `content/**/*.md`, all locales, all sites (the check already resolves locale paths; verified `infer_product('docs.aspose.org/da/slides/net')` gives `slides/net`) | B-1 | S | Low; needs a one-time baseline for the 3,029 existing files |
| 3 | Add a shortcode-count regression gate: staged file with `shortcodes(new) < shortcodes(old)` blocks unless the whole install section was removed | Enforces the owner's rule literally; also covers B-7 if mirrored in CI | S | Low |
| 4 | Fix the four detector holes: drop/downgrade the heading exemption; replace the "aspose" substring filter with registry-identity-aware logic; add `yarn add`/`pnpm add`/`uv add`/`poetry add`/`paket add`/`go install`; add a translated-verb detector (`dotnet add-*`, `pip instal*`) | B-4 / B-4b | M | Medium: surfaces new findings, needs baseline bump |
| 5 | Add `reference.aspose.org` to `install_literal_sweep._files_for()` | B-5 (121 invisible files) | XS | None |
| 6 | Promote a narrow install-only step to blocking in `content-governance-checks.yml` (and wire `check_install_recipe_safety_fails.py` there; it is currently attached only to the dead `content-audit.yml`) | B-2 / B-3 | S | Low if scoped |
| 7 | Translation-adoption staleness guard: refuse a locale commit whose English sibling now uses a shortcode while the locale file carries a literal | The cells/go regression class | M | Low |
| 8 | Translator: protect inline code spans like fenced blocks, or add a post-translation validator that fails when an install verb stops being recognisable | `add-pakke`, `pip install dan` | M (sibling repo) | Medium |
| 9 | Backfill the 412 divergent + 1,631 partial files via the migrators + `locale_patch.py` where byte-identical, per-locale passes otherwise | 4,168 live findings | L | Medium: pointless before 1-3 land, or the backlog refills |
| 10 | Make the sweep a ratchet: fail if `total_findings` exceeds the last committed baseline | B-6 | S | Low |
| 11 | Either allow `install_block_updater.py` to touch shortcode-bearing locale pages, or document that locale literals are unmaintainable and must be migrated, not updated | B-8 | S (doc) / L (code) | n/a |

## 5. What could not be determined, and why

1. Whether any `--force-accept` translator run ever dropped a shortcode: the validator that would catch it is
   disabled by that flag and the runs are not recorded in this repo. Zero shortcode removals in git history,
   so the risk is latent, not demonstrated.
2. Provenance of the 2026-03 (11,403 lines) and 2026-07 (10,719 lines) literal waves: classified by commit
   subject only. They predate the shortcode, so they are out of scope for "replacement".
3. Whether `reference.aspose.org` literals are English-only or locale-wide in detail: 121 files measured, but
   the gate cannot reach that site so there is no per-finding data.
4. Which of the 1,631 "shortcode + literal" locale files are 40-day-gap residue vs genuine lag: needs
   per-occurrence git archaeology; the 18 fully-divergent pages were resolved exhaustively instead.
5. Live enable/disable state of `content-governance-checks.yml`: its `on: push` trigger is present; no GitHub
   API call was made.
6. The `aspose-page-foss` 26.9.0 vs `verification.published=false` mismatch: confirmed in
   `data/package_registry.json`; PyPI was not queried (no-network rule). If real, the shortcode renders a
   GitHub-source install for a now-live package, a truthfulness regression the design anticipates (fix the
   registry, not the pages), not a literal-install risk.

Verified vs inferred. Verified by measurement or code reading: the 0 shortcode-to-literal commits; the 3
removals; all monthly counts; the 21 post-shortcode English literals; 4,168 findings and the 99.8% split;
412/1,009/1,631 divergence; 18/18 lag verdicts; the 10 live English findings; the Step 5 filter (sandbox);
the 4+1 detector holes (fixture probe + live file); `content-audit.yml`'s dead trigger; `audit.py all`'s
English-only discovery; reference's absence from the sweep; the skills matrix; `new-docs-index.md:139`; bot
commits touching only `data/`; 0 install-shape changes across 161,034 compared working-tree files; the
translator's parser, validator, fenced-code invariant, skip-existing and `--force-accept` semantics.
Inferred: that the cells/go 2026-09-05/06 batches are a repeatable class rather than one-offs (6 commits, ~24
lines); that `--force-accept` is a live risk (no observed loss); that the 2026-03/07 waves are
launch/locale-expansion generation.
