---
name: readme-refresh
id: S-120
description: >
  Generate, verify, and (on explicit approval) push a production-grade README.md refresh for
  one FOSS product repository, through the registered run-bound readme_refresh_run.py state
  machine.
args: "{family} {platform}"
---

<!-- CONTRACT: registered-cli-wrapper
     purpose: operate one run-bound README refresh for one FOSS product repository
     preconditions: product active in data/products.json, not excluded, real push/admin access
     postcondition: run is AWAITING_REVIEW, APPROVED, PUSHED, BLOCKED, or ABANDONED
     idempotent: yes — immutable receipts, state checkpoints, single-owner-per-product locking
     verified: 2026-08-19
-->

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.
> The sibling `upstream_issue_workflow.py` module/CLI (see "Upstream issue workflow" below) is a
> separate, non-run-bound tool for verifying and drafting real upstream-repo defect reports — it
> is documented here because it's discovered during this skill's own work, not because it's part
> of this state machine.

# S-120: README Refresh

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform}`

## Official execution contract

Use only the registered control plane:

```bash
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py start FAMILY PLATFORM \
  [--run-id ID] [--session-id ID] [--skip-preflight]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py plan --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py ingest-candidate --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py verify-examples --run-id ID \
  [--python-runner | --typescript-runner] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py recheck --run-id ID \
  [--allowed-headings "A,B"] [--mermaid-only] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py status --run-id ID
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py approve --run-id ID \
  --note TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py push --run-id ID \
  --acting-model "MODEL NAME" [--acknowledge-mirror-target TEXT] [--session-id ID] [--dry-run]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py verify --run-id ID [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py abandon --run-id ID \
  --reason TEXT [--adopt-orphaned] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py recover --run-id ID \
  --reason TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py audit-portfolio \
  [--family FAMILY --platform PLATFORM] [--json] [--candidate-tree TREE]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py retention-report FAMILY PLATFORM \
  [--json] [--out PATH]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py pin-old-readme-baseline FAMILY PLATFORM \
  --commit SHA --reason TEXT [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py reconcile-publications \
  (--family FAMILY --platform PLATFORM | --all) [--apply] [--json]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py live-published-regression \
  (--family FAMILY --platform PLATFORM | --all) [--json]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py declare-scope --run-id ID \
  --issue TEXT (--areas id1,id2 | --full-rewrite) [--allowed-deps id3,id4] [--criteria TEXT] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py accept-blocks --run-id ID \
  --blocks id1,id2 [--status CONVERGED|FROZEN_ACCEPTED|ACTIVE_IMPROVEMENT|NEEDS_REVIEW|BLOCKED] \
  [--governing-rule TEXT] [--evidence-ref TEXT] [--note TEXT] [--session-id ID]
.venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py converge-verify --run-id ID \
  [--apply-invalidation] [--session-id ID]
```

**This block is mechanically checked against the real argparse surface** (`test_cli_contract_
matches_skill_doc`, `scripts/pipeline/tests/test_readme_refresh_run.py`, TC-08 of
`readme-refresh-at-a-glance-retention-hardening-2026-09-02`): every subcommand and every long
flag `readme_refresh_run.py` accepts must appear here, and nothing here may name a flag the
code lacks. Before that test existed the block had silently lost `push --acting-model` (a
*required* flag — a push built from this doc failed), `--acknowledge-mirror-target`,
`verify-examples --python-runner/--typescript-runner`, `recheck --allowed-headings/
--mermaid-only`, and three whole verbs (`pin-old-readme-baseline`, `reconcile-publications`,
`live-published-regression`) — the same "two hand-maintained homes for one fact" drift this
skill keeps finding, here about its own CLI.

**`abandon --adopt-orphaned` (TC-04, 2026-09-02).** Every mutating verb refuses a run owned by
another session — correct, and unchanged. But a run whose OWNER session has ended stayed
locked forever: `start` refuses while a non-terminal run is active, and no verb could abandon
it. Confirmed live 2026-09-02 on five products (tex/python, font/python, pdf/typescript,
slides/python owned by a session whose ledger manifest is `status: closed`; page/python owned
by the synthetic id `mt056-proof-rerun` with no ledger manifest at all, locked since
2026-08-18 — the "12-day cross-session lock with no CLI abandon override" the 2026-08-30
mission recorded as BLOCKED_EXTERNAL). `--adopt-orphaned` is gated on the session ledger's own
liveness verdict (`session_ledger.resolve_context`), never on the flag alone: owner `closed`
→ adoptable; owner manifest swept to `stale` → adoptable; owner id unknown → adoptable only
once the run's manifest has sat untouched for 24 h (a disclosed heuristic); owner live or
ambiguous → refused, naming the status. A takeover is recorded on the manifest
(`original_session_owner`, `adopted_at`, `adoption_reason`, `owner_session_status`) and as a
`RUN_ADOPTED` event that precedes the ABANDONED transition. Then `start` proceeds normally.

**`retention-report FAMILY PLATFORM` (TC-06, 2026-09-02) — read-only, no run, no lock, no
marker.** The per-unit table a reviewer reads to answer "is everything in the original README
retained": every content / structural / code / badge unit *and every H1/H2/H3 heading* of the
old README → disposition → target section → where the candidate carries it (verbatim location
or the merge gate's own traced target) → verification status, plus, for reframed prose, a
**fidelity score naming the missing content words**. "0 hard-gate findings" is a verdict; this
is the evidence behind it — confirmed necessary on tex/python, where every gate passed while a
`merged_reframed` unit had silently lost "returns a copy of the messages collected during the
most recent run" (score 0.59, missing `copy`, `collected`, `recent`), a Quick Start example had
shrunk to a 3-line fragment, and a `### PDF output` heading had vanished with no ledger entry.
`ingest-candidate` and `recheck` write the same table to `checks/retention-report.md` beside
`result.json` on every call, pass or fail, so it is per-run evidence, not an on-demand favour.
A `needs_attention` list names every `undisposed` / `not_found` / `reframed_low_fidelity` /
`api_dropped` / `absent` row; a `reframed` row with a low score and named missing words is a
review prompt, never a gate — 0.62 was a faithful reframe and 0.59 a real loss on the same file.

`audit-portfolio` (TC-HARDEN-05, MT035, 2026-08-12) is the one subcommand with no `--run-id` —
it's read-only and portfolio-wide, not run-scoped: it re-runs every deterministic check
(`_run_deterministic_checks`, the same function `ingest-candidate`/`recheck` use) against every
already-composed candidate in `reports/repo-presenter/{family}/{platform}/readme.md`, for every
`active: true`, non-excluded product in `data/products.json` (optionally narrowed to one
`family`/`platform` pair via the two flags). A product with no candidate composed yet is
skipped, never an error. This is the real, registered, tested replacement for the ad hoc,
gitignored scratch script (`reports/repo-presenter/_scratch/phase2_scan.py`) this skill's own
maintenance had to hand-write and re-derive from memory every time a "is the whole portfolio
still clean" question came up — closing the gap named in TC-HARDEN-14 (real verification work
happening outside any registered, reproducible path). `--json` prints the full structured
result (`{"products", "clean_count", "dirty_count", "total", "skipped"}`); without it, prints a
one-line summary plus one line per dirty product. **This does not run on a schedule** — it's an
on-demand capability, not a recurring job; nothing currently triggers it automatically, so
drift between two products' candidates and their real upstream reference data (e.g. a
`reference.aspose.org` regeneration) can still accumulate silently until someone runs it by
hand — a real, disclosed, still-open gap (see the skill's own governance taskcard register in
the plan file for the deferred "should this run on a schedule" decision).

**Checks-module-currency tripwire (readme-refresh-seo-deps-headings-hardening mission,
2026-08-19).** A real, distinct staleness class from the scheduling gap above: even run by hand,
on demand, `audit_portfolio → clean: true` only ever proves a candidate is clean against the
checks that existed AT THAT MOMENT. Confirmed live: `3d/net`'s own `TC-RDR-03-3D-NET` closure
(2026-08-19, earlier the same day this mission ran) legitimately produced `clean: true, {}`
hard-gate findings — true, but only against `checks.CHECKS_MODULE_VERSION == 1`; this mission's
3 new checks (version 2) had not landed yet and never ran against it. Nothing previously flagged
that a "clean" certification had gone stale relative to checks added since — the same
"documented rule, never mechanically re-verified" root-cause shape as this mission's other three
defects, one level up (about the CHECKS themselves, not the candidate).

Fixed the same way `published_readme_current` already makes republication staleness visible,
applied to this pipeline's own check coverage instead of the target repo's upstream state:
`checks.CHECKS_MODULE_VERSION` (a monotonic int, bumped whenever a `check_*` function is added
or a hard gate's pass/fail semantics change) is stamped into each candidate's own
`last-verified.json` sidecar (`checks_module_version`, alongside the existing `readme_sha256`/
`verified_at`/`verified_by_run_id`) every time `ingest-candidate`/`recheck`/`audit-portfolio`
runs verification. `_checks_currency_findings` (advisory, never a hard gate — same tier as its
sibling `_candidate_drift_findings`) compares the stored version against the live one and
reports `result["verification_currency"]` when they diverge; a marker with no
`checks_module_version` field at all (written before this mission) is treated as version 0,
always stale, the safe default. The moment ANY fresh `audit-portfolio`/`ingest-candidate`/
`recheck` call runs, the marker updates to the current version and the signal clears itself —
this is a "needs re-verification" flag, not a permanent scar.

State machine: `CREATED → INPUTS_PINNED → PLANNED → VERIFYING_EXAMPLES → AWAITING_REVIEW →
APPROVED → PUSHING → PUSHED`. `BLOCKED` is re-enterable from `INPUTS_PINNED`/`PLANNED`/
`VERIFYING_EXAMPLES`/`PUSHING`. `ABANDONED` is terminal from any non-terminal state. `PUSHED`
and `ABANDONED` are the only terminal states. Every mutating call requires a stable session
identity (`--session-id` or `AGENT_SESSION_ID`/`CODEX_THREAD_ID`/`CLAUDE_CODE_SESSION_ID`) and
is checked against the run's `session_owner` — a different session cannot touch someone else's
run. One `ACTIVE.json` per `(family, platform)` plus a `FileLock` prevents two runs owning the
same product concurrently.

## Canonical candidate store and surgical change scopes (MT056, Fifty-Sixth incident, 2026-08-18)

**One canonical mutable candidate tree: `reports/repo-presenter-regen-full/{family}/{platform}/`**
— decided by the user through MT055 TC-MICRO-03-02's human gate and recorded durably in
`data/readme_candidate_store.json` (never re-derive or re-litigate it). `reports/repo-presenter/`
and the `-regen-test`/`-regen-reproof` pilots are FROZEN archives, each carrying an
`_ARCHIVED.json` fingerprint marker; the `candidate_store_integrity` hard gate fails any run
whenever a non-archived sibling tree holds a candidate copy (>1 current candidate), an archived
tree lacks its marker, or an archived file changed after freezing (ARCHIVE VIOLATED). `start`
and `push` refuse outright on a non-canonical tree; `audit-portfolio --candidate-tree` may read
an archived tree (output tagged NON-CANONICAL); an unregistered tree name is refused everywhere
(stale-path protection). Every path in this document written as `reports/repo-presenter/...`
before this section landed now means the canonical tree. Per-product reconciliation state of
the frozen old tree (7 products NEEDS_REVIEW before their old-tree content may be promoted, by
explicit per-product human go-ahead only): `reports/_scratch/mt056_tree_reconciliation.json`.

**Surgical, convergent idempotency is mechanically enforced, not remembered.** The contract
(user mission, 2026-08-18): improving a specific README area may change only that authorized
area and its explicitly pre-declared dependents; every previously accepted, unrelated area
stays byte-identical; the targeted area may iterate until it meets its acceptance criteria;
after convergence, re-running the same regeneration produces no further diff.

- **Blocks**: stable, content-addressed identities — `##`-section slugs (e.g.
  `key-capabilities`), plus `__preamble__` (title/badges/banner/intro) and `mermaid` (the At a
  Glance diagram, addressable separately from its host section's prose). sha256 fingerprints,
  never positional counters (the R-07 drift class).
- **Before regenerating anything on a product that already has accepted content, declare the
  scope**: `declare-scope --issue ... --areas ...` snapshots the current canonical candidate as
  that scope's IMMUTABLE baseline. Dependent blocks that must legitimately move (a TOC entry,
  an anchor, a summary of the changed section) are declared in `--allowed-deps` IN ADVANCE —
  never discovered after accepting a broad diff. A whole-document regeneration must be declared
  explicitly (`--full-rewrite`); an implied full-document scope does not exist.
- **Enforcement (hard gates at both `ingest-candidate` and `recheck`)**: `scope_compliance`
  fails any block changed/added/removed outside areas+allowed-deps (out-of-scope diff gate);
  `frozen_blocks_unchanged` fails any CONVERGED/FROZEN_ACCEPTED block whose hash moved without
  an authorizing scope; `scope_required` fails undeclared drift on any product with an
  acceptance registry (an unchanged candidate always passes — stable regeneration after
  convergence stays green); `candidate_store_integrity` as above.
- **Acceptance registry** (`acceptance-registry.json`, sibling of the disposition files —
  identities/hashes/states/evidence, never content): `accept-blocks` records accepted hashes +
  the pinned clone-cache HEAD per block; CONVERGED/FROZEN_ACCEPTED can only be recorded while
  the run's latest checks are hard-gate-clean AND the candidate matches the last-checked
  snapshot. States: `ACTIVE_IMPROVEMENT`, `CONVERGED`, `FROZEN_ACCEPTED`,
  `INVALIDATED_BY_SOURCE_CHANGE`, `BLOCKED`, `NEEDS_REVIEW`.
- **Convergence**: `converge-verify` (exit 2 on drift) proves the accepted state is stable —
  zero drift on frozen blocks, document hash equal to last acceptance. Source invalidation
  (pinned clone-cache HEAD moved) is always reported and only applied with
  `--apply-invalidation` — a converged area affected by a real upstream change is reopened
  through a new explicit scope, never silently rewritten.
- **Diagram geometry is a HARD gate** (`diagram_label_geometry`): no label token >28 chars
  (mermaid#6424 unbreakable-token clipping) and no label wrapping past ~3 estimated lines at
  Mermaid's ~200px node budget (the R-01 oversized-node class). The advisory
  `diagram_label_token_length` remains as history; the hard gate subsumes it.
- **Republication debt is re-derived, never remembered** (`published_readme_current`,
  advisory): products recorded in `data/readme_published_state.json` (auto-appended by every
  real push) whose live upstream README no longer matches the canonical candidate are flagged
  "republication pending" on every audit — the mechanical fix for the lost-TC-HARDEN-47/48
  class (3d/net and 3d/python still carry live pre-MT024 clipping upstream as of 2026-08-18).

## Steps

> **Skill context gate** — run before `start`:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-120 --scope "reports/repo-presenter/{family}/{platform}/*,reports/readme_refresh_runs/{family}/{platform}/*"
> ```

1. **`start`** — resolves the product against `data/products.json` (must be `active: true`,
   not in `data/registry_exclusions.json`), runs a real `gh api repos/{org}/{repo} --jq
   .permissions` pre-flight check (refuses without real push/admin access — this is the literal
   fix for `foss-java-publish`/S-110's documented gap, which only assumed access as prose and
   never checked it), pins the clone-cache `HEAD` SHA. Transitions `CREATED → INPUTS_PINNED`.

2. **`plan`** — emits `facts/factpack.json`: real archetype classification (`data/
   diagram_archetypes.json`, defaulting to `transform` when no override entry exists), real
   capability-dependency edges (`data/diagram_capability_dependencies.json` — `None` when the
   product has never been traced, which must never be read as "confirmed independent"), real
   install/package data (`data/package_registry.json`), real case-sensitive license-file
   detection against the clone cache (widened 2026-08-12, TC-HARDEN-20, to a 200-char
   case-insensitive substring match — the old exact-20-char-prefix match missed real files
   phrased "The MIT License (MIT)..."), a real, live-verified Enterprise Edition link
   (`enterprise_link` — TC-HARDEN-19, 2026-08-12, via `scripts/pipeline/lib/backlink_targets.py`
   against `data/aspose_com_targets.json`; `url` is `None` on a genuine unresolved target, which
   the candidate must never paper over with a guessed slug — see the hard gate below), a real,
   locally-verified homepage link (`homepage` — TC-HARDEN-27, 2026-08-12, `{"url", "verified"}`;
   `verified` is True only when `content/products.aspose.org/en/{family}/{platform}/_index.md`
   genuinely exists in this repo, a first-party same-repo-deploy guarantee, deliberately not a
   live HTTP check — see that field's own docstring for the tradeoff), and the
   old upstream README's real link/heading/prose inventory (`old_readme_inventory`, including
   `content_units` — MT030, see below). Transitions `INPUTS_PINNED → PLANNED`.

   **Enterprise Edition anchor-text contract (MT043/TC-HARDEN-61-62, 2026-08-14 — CORRECTED
   same day, MT044/Thirty-Fourth incident).** `enterprise_link` also carries `relationship`
   (`"family"` | `"platform"` | `"unresolved"` | `None`) and `public_platform` (a normalized,
   implementation-neutral display name, e.g. `"Python"`, `"Go"`, `"Node.js"` — never a compound
   like `"Python via Java"`), computed by `_classify_enterprise_relationship`. Compose the anchor
   from these two fields, never freehand:
   - `relationship == "family"` → `[Aspose.{Family} — Enterprise Edition]({url})` — the anchor
     names NO platform at all, ever, even when the source product's own platform is obvious from
     context.
   - `relationship == "platform"` → `[Aspose.{Family} for {public_platform} — Enterprise
     Edition]({url})` — name the one real `public_platform`, nothing else. This applies
     identically whether the underlying resolved URL is a bare platform slug (`.../cells/java/`)
     or a compound bridge slug (`.../cells/python-java/`, `.../cells/go-cpp/`) — **the anchor
     never distinguishes the two, and must never mention the compound's own second component**
     (Java, .NET, C++ as an *implementation* detail) anywhere in the anchor or the surrounding
     prose. `resolve_backlink` may internally have chosen this URL because of implementation
     compatibility; that reasoning stays internal and is never surfaced publicly.
   - `relationship in ("unresolved", None)` → omit the Enterprise Edition link entirely. Never
     guess a platform name or fall back to a family link merely because the exact source-platform
     slug differs, the URL has a compound suffix, or a family URL is easier to write — family is
     the FINAL fallback (used only when `_detect_enterprise_link` itself could resolve no
     platform-specific target at all), never a default for an inconvenient platform match.
   - **Permanently forbidden, anywhere in the document** (anchors, prose, tables, notes,
     comparison sections, badges, installation text, architecture descriptions, related-product
     descriptions, footnotes, generated metadata) — any wording that discloses how one platform is
     implemented through another: "via Java", "via C++", "via .NET", "Python via Java",
     "implemented through X", "backed by X", "a wrapper around X", "a binding to X", "rather than
     as a native X", or any equivalent phrasing. `check_no_implementation_bridge_disclosure` (hard
     gate, portfolio-wide, not scoped to the Enterprise-link paragraph) is the mechanical backstop
     for this rule — it is not a substitute for composing correctly the first time.
   - **History, so this is never reintroduced**: MT043 originally required exactly this kind of
     "via {language}" wording plus a disclosure sentence for a compound-slug destination — a real
     policy defect discovered and reversed the same day (MT044), not a hypothetical. Do not revive
     any "bridge disclosure" requirement under a different name.

3. **Agent composes the candidate.** The script does not write README prose — the agent reads
   `facts/factpack.json` and writes `reports/repo-presenter/{family}/{platform}/readme.md`
   directly, following the Template section's standard structure (plan:
   `C:\Users\prora\.claude\plans\d-users-prora-onedrive-documents-github-humble-tome.md`). Every
   item in the factpack's `old_readme_inventory` (links, headings) must either land somewhere
   real in the candidate or be a deliberate, verified drop — `ingest-candidate`'s
   `check_dropped_content` hard gate below enforces this, it is not optional diligence.
   **MT030 (Fifteenth incident, 2026-08-09)**: the agent must ALSO write
   `reports/repo-presenter/{family}/{platform}/content-dispositions.json` — one entry per real
   prose content unit `old_readme_inventory.content_units` extracted from the old README
   (mechanism-level explanations and branding/positioning claims, verified against the real
   product repo and merged/reframed into the appropriate section; pure narrative/origin-story/
   CTA prose is explicitly out of scope, per the user's own decision, and gets an `excluded`
   disposition citing that). This is the real, working artifact `dropped_claims.json` was only
   ever a docstring aspiration for (2026-08-04 through 2026-08-09, never implemented by any
   code) — see `check_content_unit_disposition_coverage`'s own docstring for the full schema.
   **MT031 (Sixteenth incident, 2026-08-10)**: a 4th classification, `4_verifiable_history`,
   covers genuine, checkable project/format history (a past event, not a live source-checkable
   mechanism) — its `verification.status` must be `verified_by_corroboration` (internally
   consistent with, not contradicted by, real repo artifacts — never claimed "proven" the way a
   mechanism claim is). A `4_verifiable_history` unit may target a new, permanently OPTIONAL H3
   section, `### Project History`, placed after the banner and before the unheaded Intro
   paragraph (never a `##` heading — that would break `_split_into_sections`'s `"__preamble__"`
   boundary; H3 keeps it inside the same preamble region as Intro, so `check_required_sections`/
   `check_only_sections_changed` need no change and the section stays vacuously satisfied like
   `## Additional Examples` when a product has nothing real for it). A mixed unit — real,
   independently-actionable fact bundled with pure hedge/CTA tone (e.g. "...not the final
   shape... [open an issue](../../issues) and tell us about your use case...") — is reclassified
   to whichever real category the checkable fact belongs to and reframed to drop the hedge,
   never excluded wholesale; `check_content_unit_embedded_actionable_fact` (heuristic) is a
   standing, portfolio-wide tripwire for this exact pattern recurring on a future product.

   **Real screenshots/visual proof-of-capability content is preservable — never excluded on the
   stated basis that "no template section exists for this" (MT051, Forty-First incident,
   2026-08-16).** Real, confirmed defect: `page/python`'s own `content-dispositions.json`
   excluded 3 real, on-disk `## Example Results` screenshots with the fabricated reason "the
   Template's fixed section list has no image-gallery section to hold embedded result
   screenshots" — directly, empirically false, contradicted by this exact portfolio's own
   `font/python` candidate (5 real embedded local images in the body) and by `pdf/go`'s own
   `## Feature Showcase` section (a dedicated top-level section built specifically to hold one).
   The established, correct target for this content is a `### {descriptive name}` subsection
   under `## Additional Examples` (inside the `<details>` block alongside the other collapsed
   examples, since a gallery of screenshots is supplementary proof, not the one flagship example
   shown directly) — reuse this pattern, never invent a categorical "the template has no room
   for this" justification without first checking `## Additional Examples`'s own already-
   established subsection convention. `check_image_content_unit_excluded_reason_verified`
   (heuristic) is a standing tripwire: an excluded image-markdown content unit whose
   `candidate_section_reference` cites a PROSE section (its generic keyword overlap can
   coincidentally match unrelated prose regardless of whether the specific image is genuinely
   duplicated) is only trustworthy when the image's own real asset filename actually reappears
   somewhere in the candidate — never on the strength of related-but-generic vocabulary alone.

   **Already-published products bypass all 25 preservation-tracking result keys automatically
   (TC-HARDEN-115, MT053, Forty-Fourth incident, 2026-08-18).** Once a candidate has already been
   pushed and merged into the real upstream repo, the clone cache's own `README.md` becomes the
   candidate itself — extracting "content to preserve" from it and cross-checking against a
   disposition file is a pure tautology, and the real, position-based `unit_id` extractors
   produce pure false-positive noise the moment the "old" text's own structure has shifted even
   slightly since the disposition file was last authored (confirmed live: 158 false hard-gate
   failures for `pdf/cpp`, entirely this artifact, before this gate existed).
   `_run_deterministic_checks` computes `_readme_matches_published_upstream(old_readme_text,
   candidate_text)` once, fresh, immediately after `old_readme_text` is resolved — a
   deliberately narrow, whitespace-only-normalized (`.strip()`) equality check, never more
   permissive, so a false positive (silently disabling real preservation tracking for a
   genuinely still-independent old README) stays effectively impossible; a false negative just
   means the checks keep running normally, the safe default. When it returns `True`, all 25
   content/structural/code-example/badge preservation-tracking result keys report a uniform,
   disclosed `{"skipped": True, "skip_reason": "..."}` no-op instead of running position-based
   extraction against a self-referential text — `content_units`/`dispositions`, `structural_
   units`/`structure_dispositions`, `code_units`/`code_example_dispositions`, and `old_badges`/
   `new_badges`/`badge_dispositions` are never even computed. `readme_already_published` is
   itself a new, always-present result key
   (`{"detail": {"published": bool}, "hard_gate": False}`), and `audit-portfolio`'s own
   structured output surfaces the same `published` field per product for a portfolio-wide view.
   **Never do this by hand** — the disposition JSON files for an already-published product are
   never rewritten, deleted, or kept in sync; the real preservation work already happened (the
   merge itself), and the system's own detection is what neutralizes their staleness, not a
   fresh, manually-authored replacement. Candidate-quality checks that never read
   `old_readme_text` at all (`project_structure_canonical_tree_format`, `badge_static_claims_
   dynamic_fact`, `no_duplicate_badges_in_candidate`, `badge_row_meets_verified_floor`,
   `badge_available_fact_not_shown`) and every check that verifies the candidate against real,
   *current* source/registries/reference-site data (`check_named_member_accuracy`, `check_api_
   reference_table_completeness`, `check_code_example_imports_match_source`, `check_diagram_
   verified_format_claims`, the `check_dependency_*` family, `check_api_reference_class_internal_
   only`) are unaffected and keep running unconditionally, published or not — "freshness against
   the real, live repo" and "preservation of the original README's content" are two different
   questions this skill already answers with two different mechanisms, and only the second one
   is what this bypass retires once its premise is gone. A product that was published once and
   has since been further edited locally (not byte-identical to the live merged README anymore)
   is **not** detected by this narrow check and correctly falls through to ordinary preservation-
   tracking behavior — a real, disclosed, deliberately out-of-scope in-between state, not yet
   solved.

   **Prose quality (TC-HARDEN-22, MT034/Twentieth incident, 2026-08-12).** Every existing
   tone-adjacent check (`check_process_narration_smells`, `check_key_capabilities_quality`,
   `check_section_job_distinctness`) is deliberately a heuristic, never a hard gate — "does this
   read naturally" is a judgment call no regex can make. What *is* made durable is the process
   that produces natural-reading prose, not left to whichever agent happens to be composing that
   day:
   - **Mandatory tone-exemplar reading, before composing any product's prose.** Read 2–3 real,
     already-shipped sibling candidates **in full** (not skimmed) — chosen for register
     diversity: one small/simple product, one large/complex product, and, when this product's
     own archetype has a shipped sibling, one from the same archetype. This extends the existing
     "read a sibling candidate for structural reference only, never copy its content" discipline
     to explicitly cover *voice*, not just structure — a real, required step, not left to
     individual agent judgment.
   - **A positive rubric to self-check against before finalizing** (never a hard gate): state a
     fact plainly, active voice, no hedging (real, shipped example — `cells/cpp`'s *"The primary
     entry point is `Workbook`, which owns a `WorksheetCollection` of `Worksheet` objects."*); a
     backtick-quoted identifier is woven naturally into a sentence describing what it does, never
     presented as a bare, undifferentiated list; each Key Capabilities bullet reads like
     something a developer would tell a colleague, not template filler with the identifier
     swapped in; sentence length and rhythm vary across a section.
   - **Regeneration Comparison Protocol** — whenever this product already has an existing
     candidate, do not stop at `ALL HARD GATES CLEAN`. Read both files in full and classify every
     real difference into: **structural** (sections/diagram/tables — the gates below already
     force these to match; a real difference here is itself a bug worth investigating, not
     accepting), **factual** (a claim present/absent/changed — verify EVERY factual disagreement
     against real source before trusting either side; never assume the older file is right just
     because it shipped first, never assume the newer file is right just because it's freshly
     source-derived), and **wording/tone variation** (expected, not a defect — this is the rubric
     above at work). Write the comparison down per-product, alongside `content-dispositions.json`
     — not just held in the composing agent's own context. **A regenerated candidate never
     silently replaces an existing one** — replacement requires the same explicit, per-product
     human go-ahead as every other consequential action this skill takes (matching the approve/
     push/merge gates above).
   - **Honest limit, stated plainly, never smoothed over**: the skill can produce the comparison
     and apply the rubric; it cannot certify "reads naturally" on its own authority. A
     mechanically-checkable property (does a link resolve, does a member exist) is not the same
     thing as prose quality — the gates below catch factual and structural defects; final
     certification that prose reads naturally stays a human judgment call, every time.
   - **Tone-exemplar contamination guard (TC-HARDEN-44, MT039/Twenty-Ninth incident,
     2026-08-14).** Before treating a shipped sibling candidate as a genuine tone/voice
     exemplar (the mandatory reading step above), confirm it is free of live
     `check_process_narration_smells` findings first — run the check, don't assume. A
     mechanism built to spread *good* patterns is exactly as capable of spreading *bad* ones:
     the "table/index below mirrors reference.aspose.org's own structure" leak (below) shipped
     in at least 9 products with closely related wording, strong evidence it propagated via
     this exact exemplar-reading step, not 9 unrelated composition mistakes. If a chosen
     exemplar has active findings, either pick a different sibling or explicitly note the
     specific passage *not* to imitate — never read a flagged file as if it were clean.

   **No generation-mechanism / design-rationale narration in the API Reference intro sentence
   (TC-HARDEN-43/44/45, MT039/Twenty-Ninth incident, 2026-08-14).** The API Reference intro
   sentence (Rule "API reference intro sentence must name real hub classes", above) must state
   *product* facts only — real hub classes, real type/module counts. It must never describe
   *this document's own table or section* as "mirroring," "organized as," or "grouped exactly
   as" another site, document, or internal artifact's structure — named or paraphrased. This is
   a fifth, previously-unnamed narration category, distinct from the other four
   (receipts/execution-notes/provenance/confidence-language): it narrates a *composition design
   choice*, not verification activity. Confirmed live across 9 products, several without naming
   `reference.aspose.org` literally (paraphrased as "the library's reference index," "the full,
   module-grouped reference," "the same data") — a regex keyed to the literal domain name alone
   would have missed 4 of the 10 confirmed instances.
   - **BAD** (real, confirmed, since fixed): *"The library ships 96 public types, summarized in
     the module-grouped table below (mirrors [reference.aspose.org's own class index](...))."*
   - **GOOD** (real, already-shipped, the reusable template): `3d/typescript`'s Documentation &
     Resources bullet — *"the API reference section above covers the essentials."* State what
     the section covers, never why or how it was built to look the way it does.
   - The word "mirror(s)/mirroring" itself is fine — real, legitimate product facts use it
     constantly (`MirroredProfile`, "mirrors the WHATWG `window.customElements` API," "mirrors
     PDF 32000 §12.3.2.2 names," "the API shape mirrors Aspose.PDF for .NET"). The defect is
     specifically when the *subject* doing the mirroring is this document's own table, tables,
     index, or section.
   - `check_process_narration_smells` (hard gate, below) mechanically catches the structural
     shape (`table|tables|index|section ... below|above ... mirror(s|ing)?`, plus `grouped
     exactly as`) — but the written rule above is the durable defense; a regex can only ever
     chase phrasings already seen (proof: this exact defect class evaded the module's other 27+
     narration patterns for 10 real instances before being named).

   **No generation-mechanism / design-rationale narration in ANY section's own intro sentence
   (TC-HARDEN-71/72/73, MT046/Thirty-Sixth incident, 2026-08-15) — the general principle,
   generalized past API Reference alone.** `font/python`'s real Key Capabilities intro sentence
   independently reproduced the identical narration category one incident after MT039 first
   named it — different vocabulary, same underlying defect: describing this document's own
   editorial choices instead of the product. The general rule: **any section's own framing/intro
   sentence — before Key Capabilities' bullets, before Additional Examples' flagship snippet,
   before API Reference's detail, or anywhere else a short prose lead-in precedes real content —
   must describe real, verifiable PRODUCT facts: real architecture, real processing layers, real
   feature groupings that would be true independent of how this specific README document happens
   to be organized.** It must NEVER describe (a) this document's own editorial/organizational
   choices, or compare how content COULD be organized against how it happens to be organized in
   this file; (b) internal source-code structure facts with no product relevance (file names,
   file sizes, "the largest module," line counts, which functions live "below"/"above" in this
   document). **The test**: would this sentence be true of the product even if this README were
   rewritten from scratch with a completely different structure? If the sentence would become
   false or meaningless under a different document structure, it is describing the document, not
   the product, and does not belong.
   - **BAD** (real, confirmed, `font/python`): *"Here's what you get — a Capability Snapshot of
     why teams use it, grouped by real module rather than by workflow label. Python API
     Highlights and CLI Highlights are both covered inline via backtick-quoted class/command
     names below, and variable-font-first workflows remain the deepest, most actively developed
     surface area (`instancing.py` alone is the largest module in the library)."*
   - **GOOD** (real, already-shipped, `email/cpp`): *"Features are grouped below by processing
     layer, from low-level CFB container access up through the high-level `mapi_message` API."*
     Note this ALSO says "grouped below" — the distinguishing fact is "processing layer...
     low-level...high-level" is real product architecture, true regardless of this document's own
     structure, while "real module rather than by workflow label" is a claim about the DOCUMENT's
     presentation choice. A bare "grouped by" is never itself the defect.
   - **Extension to the tone-exemplar guidance (TC-HARDEN-44, above)**: when imitating a
     sibling's intro-sentence convention (per the mandatory tone-exemplar-reading step) and no
     equivalently clean, real architectural narrative exists for the current product, the safe
     fallback is to **omit the framing sentence entirely** and start directly with the first
     bullet — matching the many real, already-correct portfolio products with no intro sentence
     at all (e.g. `barcode/python`, `cells/python`). Never invent a document-structure-comparison
     sentence to fill the gap. Imitating a *clean* exemplar's *form* while silently dropping its
     *substantive constraint* is exactly as capable of shipping a defect as imitating an
     already-flagged one.
   - `check_section_intro_no_meta_narration` (hard gate, below) mechanically scans the leading
     intro prose of `## Key Capabilities` and `## Additional Examples` for three narrow,
     precision-first patterns (a rejected-alternative organizing-scheme comparison, a
     self-reference to "covered inline...below," a source-filename-plus-size-superlative leak) —
     `## API Reference`'s own intro sentence is deliberately excluded, already separately covered
     by the rule above. Same honest limit as every other fixed-pattern narration check: it cannot
     prove no instance of this class exists anywhere, only that these specific patterns don't
     match — the written rule above is the durable defense.

   **SEO keyword integration and structural variety in Key Capabilities (TC-HARDEN-39/40/41,
   MT037, Twenty-Seventh incident, 2026-08-13).** `cells/java`'s real Key Capabilities section
   was found genuinely "dry" — 8 of 10 bullets opened with a backtick-quoted identifier as their
   grammatical subject, a monotonous, API-reference-style shape distinct from the fragmentation/
   thin-bullet defects `check_key_capabilities_quality` already caught (different first words
   every time, so that check's own literal-first-word-repetition signal never fired).
   - **Real, per-page SEO keyword data exists — `keywords/{family}.json`** — read via
     `_detect_seo_keywords(family, platform)` (matches the entry whose `sourcePath` is
     `content/products.aspose.org/en/{family}/{platform}/_index.md`, falling back to the
     family-root entry) and populated into `factpack["seo_keywords"]`/`["seo_keywords_
     filtered"]`. **The raw data is confirmed unreliable — do not trust it directly.** Every
     non-`.NET` platform checked for the `cells` family (java/python/rust, across products/docs/
     kb.aspose.org's own per-page entries) carries keyword phrases naming `.NET`/`C#` instead of
     its own real platform (`cells/java`'s own real entry: 10 of 10 phrases mention `.NET`/`C#`,
     zero mention Java) — the same "even structured, checked-in data isn't infallible" lesson
     `formats.md`/`data/package_registry.json` already taught this skill, recurring here.
     `checks.filter_relevant_seo_keywords(keywords, family, platform, known_format_names)` is the
     real, mechanical defense — already applied at factpack-build time, not left to the composing
     agent's own restraint: drops any phrase naming a platform other than this product's own
     (`_SEO_KEYWORD_PLATFORM_TOKENS`), keeps only phrases grounded in the family name, a known
     real format, or this portfolio's own established capability-verb vocabulary, and caps the
     result to 6 phrases. **`seo_keywords_filtered` can legitimately be empty** (confirmed live
     for `cells/java` — all 10 raw phrases were contaminated and none survived) — when it is, do
     not invent a substitute phrase; rely on this portfolio's own already-established natural
     framing (the Intro paragraph's own "free, open-source, pure-Java spreadsheet library"
     wording is itself real, verified SEO framing) instead of forcing something ungrounded in.
   - **"Highlight properly" means placement, never typographic markup.** Weave real, filtered
     keyword language into 2–4 spots across the whole file — weighted toward the Intro paragraph
     and the first 1–2 Key Capabilities bullets, where a reader or crawler looks first — as
     natural prose using verbs/framing already native to this portfolio's own voice (`"free"`,
     `"open source"`, `"alternative"`). Never wrap a keyword phrase in backticks (reserved for
     real code identifiers) and never bold it (this portfolio's Key Capabilities/Intro prose has
     no existing bold-emphasis convention, and introducing one for keywords reads as marketing-
     copy stuffing — the same unprofessional-tone class this skill has fought since the
     2026-08-04 process-narration incident). Never force a phrase into every bullet.
   - **Vary bullet opening structure — identifier-first, action-first, benefit-first, and
     task-first, mixed across the section, not any single shape uniformly.** Swapping "every
     bullet opens with a backtick identifier" for "every bullet opens with an action verb" is the
     same monotony in a different shape — `check_key_capabilities_structural_variety` (heuristic,
     below) only flags when ≥70% of bullets share the identifier-first shape specifically; a
     genuinely mixed section (roughly a quarter to a third identifier-first, the rest varied) is
     the target, not zero.
   - **Preserve every fact and identifier exactly** when rewriting for structure/SEO — this is a
     phrasing pass, never a content pass; if a rewrite drops a word a `content-dispositions.json`
     entry's evidence trail depends on for its own `check_content_unit_merged_into_target_
     section` word-overlap proof (real incident: rewriting "applies data validation rules" to
     "Validate input..." silently dropped the literal word "data" a real disposition's own
     word-overlap check depended on), restore the dropped word naturally rather than leaving the
     gate to fail — verify with `recheck` after any Key Capabilities rewrite on a product that
     already has real dispositions on file, not just the two new heuristics.
   - **Cheap, mechanical formatting hygiene** (`check_key_capabilities_formatting`, heuristic,
     below): every bullet ends with terminal punctuation, has no unmatched backtick (an odd
     backtick count in one bullet — the same parity-count idiom already proven for
     `check_no_stripped_example_in_description`), and never opens with a lowercase letter unless
     that word is itself a backtick-quoted identifier.

   **Keyword placement plan and usage verification (readme-refresh-seo-deps-headings-hardening
   mission, 2026-08-19).** The gap the paragraphs above never closed: `filter_relevant_seo_
   keywords` only ever curates the CANDIDATE POOL of relevant phrases at factpack-build time —
   nothing recorded what section a phrase was intended for, and nothing ever cross-referenced
   the actually-composed text against it. Confirmed real, live: `3d/net`'s own real Key
   Capabilities section (composed independently of this mission) used zero of its 10 correct,
   real, `.NET`-scoped filtered phrases — a documented-but-unchecked rule, the exact recurring
   root-cause shape this whole document keeps naming.

   `checks.build_seo_keyword_placement_plan(seo_keywords_filtered, family)` turns the filtered
   pool into a typed record per phrase — `{phrase, source_registry, applicable_capability,
   intended_section, reader_search_intent, priority, max_uses}` — recorded in the factpack as
   `seo_keyword_placement_plan` and recomputed fresh (never read back) inside `_run_
   deterministic_checks`, matching this module's own established pattern for every other
   `_detect_*`-derived value. **Honest, disclosed limit**: `priority` is always `"preferred"`,
   never `"required"` — this pipeline has no reliable capability-to-keyword mapping that would
   justify a stronger claim (`filter_relevant_seo_keywords` only proves a phrase is grounded in
   the family name, a known real format, or established capability-verb vocabulary, never that
   it maps to one SPECIFIC verified capability); `applicable_capability` is `None` for the same
   reason. Inventing that mapping under this mission's own scope would have been exactly the
   kind of overclaimed determinism this document's own composition-quality sections keep
   warning against.

   `check_seo_keyword_plan_usage` (heuristic, deliberately never a hard gate — the "never turn
   subjective prose quality into a simplistic hard keyword-count gate" rule applies here
   directly) does lexical-overlap detection, not exact-phrase matching: a phrase "counts as
   used" when at least one of its own significant (4+ letter) words appears anywhere in the
   candidate text — natural paraphrase is expected and correct, matching this section's own
   anti-stuffing rules above. WARNs only when the plan is non-empty and LITERALLY ZERO phrases
   show any overlap anywhere in the document — a floor against total non-engagement, never a
   per-bullet or per-phrase count; the plan itself can legitimately be empty (confirmed live for
   `cells/java`, above) and that is not itself a finding.

   **Dependency terminology and the Claims Policy — a mandatory `## Dependencies` section
   (TC-HARDEN-49 through -56, MT041/Thirty-First incident, 2026-08-14).** The real, confirmed
   defect this mission exists to fix: `cells/rust`'s Installation section stated *"Requires a
   recent stable Rust toolchain (2021 edition) — no external runtime or Microsoft Office
   installation is needed"* while its own `Cargo.toml` declares 7 real runtime crates (`chrono`,
   `zip`, `sha2`, `base64`, `serde_json`, `roxmltree`, `getrandom`) — a same-document
   contradiction against that file's own, correct Intro paragraph, which already named all 7.
   Real, already-verified dependency data now exists in every factpack (`factpack["dependencies"]`
   — a real `DependencySnapshot` from `dependency_extract.py`'s per-ecosystem manifest parsing,
   never a guess) and must be used, never invented.

   Use these terms precisely, never interchangeably — the sub-heading nouns below match them
   verbatim:
   - **Package dependency** — a real, named entry in the product's own manifest.
   - **Direct dependency** — declared directly in that manifest's own dependency table (this
     skill's own extractors never read a lockfile, so every `DependencySnapshot` entry is, by
     construction, direct — never present a name absent from the snapshot as if it were one).
   - **Optional dependency** — gated behind a feature flag/extra; the library builds and runs
     without it.
   - **Development dependency** — used only by the test/benchmark/lint suite, never shipped or
     required by a consumer.
   - **Native/system dependency** — an OS-level library, compiler, or toolchain version floor,
     not a package-manager entry.
   - **Proprietary-runtime dependency** — a commercial/proprietary runtime this product does NOT
     need (e.g. Microsoft Office, a proprietary Aspose engine). Proving this is absent proves
     *nothing* about package/native dependencies — never conflate the two, the exact mistake the
     real `cells/rust` sentence made.

   **`## Dependencies`** is a new, mandatory `_REQUIRED_SECTIONS` entry, placed immediately after
   `## Installation`, before `## Quick Start` — the direct sequel to "how do I install this,"
   strictly before "how do I use it." Four `###` sub-headings (title case, matching Rule 6 —
   "and" stays lowercase): **Required Package Dependencies**, **Optional Dependencies**,
   **Native and System Requirements**, **Development Dependencies**. Required omits only when
   the snapshot's `required` list is genuinely empty, and even then renders the fixed sentence
   **"No required third-party package dependencies."** rather than vanishing silently (a reader
   must never confuse "verified zero" with "generation forgot this"); Optional/Development omit
   silently when empty; Native and System is present for nearly every product (a real language/
   runtime version floor almost always exists). `pdf/cpp`'s existing inline `**Requirements**:
   ...` Installation sub-line is **superseded**, not duplicated, by this section — coexistence
   would recreate the exact same-document-contradiction risk `cells/rust` already proved real.

   **Claims Policy: never write an unqualified absolute** ("No external dependencies",
   "Dependency-free", "No dependencies required", "Completely standalone", "no external
   runtime/installation/software") **unless the claim names the exact dependency class it
   excludes in the *same coordinated clause* AND that is actually proven** by the
   `DependencySnapshot` data. "No third-party runtime crate dependencies," "no native system
   libraries," and "no proprietary Aspose runtime" are each fine, independently, only when true.
   A generic mention of the words "library"/"crate"/"package" elsewhere in the sentence (e.g. "a
   pure-Rust *library* for...") never counts as scoping — the qualifier must be an actual
   dependency-class phrase (`third-party crate`, `native system library`, `proprietary Aspose
   runtime`, etc.), checked within the *same clause* as the claim, never borrowed from a
   different coordinated clause joined by "or"/"and" in a compound sentence (the real
   `cells/rust` shape: "no external runtime *or* Microsoft Office installation" — "Microsoft
   Office" legitimately scopes only the second clause, never the first).
   - **BAD** (real, confirmed, since fixed): *"Requires a recent stable Rust toolchain (2021
     edition) — no external runtime or Microsoft Office installation is needed."*
   - **GOOD** (the reusable replacement): *"Requires a recent stable Rust toolchain (2021
     edition or later). No proprietary Aspose runtime and no Microsoft Office installation is
     required."* — paired with a real `## Dependencies` section naming all 7 crates. The
     corrected sentence keeps the true, scoped part of the original claim and drops only the
     false, unscoped part.

   When `factpack["dependencies"]` is missing or carries `applicable=False` with no real
   `not_applicable_reason` (should be structurally impossible — checked anyway), **never
   substitute a dependency-free claim** — `check_dependency_snapshot_completeness` (hard gate,
   below) fails the run with a named, actionable error instead. `dependency_extract.py`'s own
   extraction failures already convert into a real `BLOCKED` run at `plan` time via the same
   `_block()`/`ReadmeRefreshRunError` mechanism already proven at `push()`'s own call site — fix
   the named manifest (or add a verified entry to `data/dependency_overrides.json`), then
   `recover` and re-run `plan`.

   **Dependencies subheading presence is now a hard gate; native-system extraction now covers
   every ecosystem (readme-refresh-seo-deps-headings-hardening mission, 2026-08-19).** Two real,
   distinct root causes, both confirmed live on `3d/net`'s own real "## Dependencies" section
   (composed 2026-08-19, the same day): (1) the four-subheading template above was documented
   but never mechanically checked — `check_dependency_section_subheadings_present` (hard gate)
   closes this: `### Required Package Dependencies` is required unconditionally (bullets or the
   fixed empty sentence, never a headingless flat paragraph — 3d/net's exact defect);
   `### Optional Dependencies`/`### Development Dependencies` omit silently only when their
   snapshot bucket is genuinely empty; `### Native and System Requirements` is required whenever
   `native_system` is non-empty. (2) `dependency_extract.py`'s `native_system` bucket — already
   modeled in the `DependencySnapshot` type and the `"native-system"` `Category` — was populated
   for exactly ONE of seven ecosystems (`go_modules`, the `go` version directive) before this
   mission; NuGet/Cargo/pypi/npm/Maven all had zero native/language-version extraction, which is
   the deeper reason "### Native and System Requirements" was silently absent across most of the
   portfolio, not a 3d/net-specific gap. Now extracted: .NET `<TargetFramework>`/
   `<TargetFrameworks>` (raw list, never computed into an "X or later" claim — a multi-target
   list can mix generations that don't compare simply, e.g. 3d/net's own real
   `net10.0;net8.0;net6.0;netcoreapp3.1`; phrasing that into prose is a composition-time
   judgment call, not an extraction fact); Rust `[package].edition`/`.rust-version` (MSRV);
   Python `requires-python` (pyproject) / `python_requires` (setup.cfg); npm `engines.node`;
   Maven `<properties>` `maven.compiler.release`/`.target`/`.source`/`java.version` (declared
   directly in the product's own pom.xml, never resolved through parent-POM inheritance — a
   disclosed narrower-but-correct scope) with a Gradle `sourceCompatibility`/
   `JavaLanguageVersion.of(N)` regex-best-effort fallback. Every field is independently optional
   — silent omission when genuinely absent, never guessed.

   **Same review pass, also fixed**: `_select_main_csproj`'s "shortest-path wins" heuristic had
   no way to prefer a real library over a same-or-shallower-depth demo/converter tool — a second,
   real instance of the exact bug class the 2026-08-17 test-project exclusion already fixed once
   (`words/net`). Confirmed live: 3d/net's own `src/converter/Converter.csproj`
   (`OutputType=Exe`, 3 path segments) sorts strictly ahead of the real library
   `src/main/Aspose.ThreeD/Aspose.ThreeD.csproj` (4 segments) — not even a depth tie, so a
   same-depth-only tiebreaker would not have fixed it. Fixed with a second filtering stage
   (applied after the existing test-name filter): prefer a non-`OutputType=Exe` project within
   whatever set survives the first filter, never excluding Exe outright (a real product could
   legitimately have only an Exe-output csproj). Silently harmless for 3d/net today (both
   projects have zero `PackageReference`s) but would have silently misattributed a demo tool's
   own dependencies to "the library's" for a product where it mattered.

   **Public-source allowlist for limitations content (2026-08-13, found live on `cells/cpp`).**
   A real Development and Testing sentence cited `upstream-issues.md` by name ("...see
   `upstream-issues.md` for the corrected commands used above") and, even once that citation is
   stripped, still narrated the underlying comparison finding in generalized prose ("...reference
   a `workspace/`-prefixed path layout that does not match a plain clone of this repository").
   Both are the same defect: a finding this pipeline's own investigation produced — by reading
   an internal, never-published artifact, or by comparing two real artifacts against each other —
   disclosed in the public README merely because the machinery discovered it. **Any public
   Scope-and-Limitations or Development-and-Testing claim must trace to one of**: the target
   repo's real, current, public source code (directly, statically observable by any external
   reader who opens the same public files — this is the established, already-hardened "verify
   against real source" discipline this whole skill relies on, and stays fully allowed), the
   target repo's existing root README, another public tracked doc in the target repo, or
   authoritative public product/package documentation. **Never allowed as the basis for a public
   claim**: `upstream-issues.md`, `content-dispositions.json`, `knowledge/{family}/{platform}/
   merged/*`, the read-only clone cache path itself, this project's own `reports/` evidence tree,
   or any other artifact that will not ship with or be reachable from the published repo — citing
   one by name, or restating its finding as unattributed prose, are the identical violation.
   Concretely: when composing Installation/Development-and-Testing instructions, give the real,
   working commands directly; never narrate *why* they differ from what a sibling doc in the repo
   says, or how this pipeline discovered the discrepancy — that narration is exactly the leak,
   independent of whether the internal filename is named. **If no limitation traces to an allowed
   source, omit the bulleted list entirely** — never invent filler such as "no known limitations"
   to satisfy the section's format contract; `check_scope_limitations_format`'s zero-bullet
   carve-out (below) makes this the valid, checked shape, not a workaround.

   **Designed limitations vs transient defects — and un-runnable examples (TC-03,
   `readme-refresh-at-a-glance-retention-hardening-2026-09-02`, user decision 2026-09-02).**
   The public-source allowlist above says *where* a limitation may come from; this says *which
   kind* belongs in the README at all. `## Scope and Limitations` carries **designed or declared
   limitations** — facts a reader of the public source would read as "this is not (yet) how the
   product works": a `NotImplementedError` stub (`\halign`), a milestone note in a docstring
   ("pass `load_format=False` until the Plain TeX cascade lands"), a data directory the package's
   own README documents as empty (hyphenation patterns), a Pre-Alpha classifier. **Transient
   defects are never narrated in the README**: a package that fails to import at this commit, a
   broken build backend, an unpublished PyPI/npm name, a test suite that cannot collect. Those
   are bugs, not product scope — they go to `upstream-issues.md` (BLOCKING/INFORMATIONAL entries,
   never shipped) and, when real, to a GitHub issue through the MT057 upstream-issue workflow
   (below), exactly as `html/python` already handles its broken build backend: the README gives
   the working path and says nothing about the defect. The examples stay the correct API usage
   per the real source signatures, **with no caveat anywhere** — not in At a Glance, not above a
   Quick Start block, not as a Scope bullet.
   - **Never write verification-status language about this document's own diagram or
     examples** — "the diagram below describes the intended API surface", "the examples above
     cannot be executed against this snapshot", "the examples are checked against the source's
     signatures so they describe the intended API correctly". That is Rule 3's confidence
     language with this document as its subject; it narrates *our* verification, not the
     product. `check_process_narration_smells` now carries a structural detector for exactly
     this subject+verb shape (README-only pattern list, advisory — see the tier note there).
   - **BAD** (real, shipped on `tex/python` until 2026-09-02, the only instance in 31 products):
     an italic *"Note: the diagram below describes the intended API surface — see Scope and
     Limitations for this snapshot's current packaging defect."* under `## At a Glance`, plus a
     Scope bullet narrating "systemic indentation corruption … none of the code examples above
     can currently be executed against this exact snapshot; the examples are checked against
     the source's class/method signatures and docstrings, so they describe the intended API
     correctly even though they cannot run until this is fixed upstream."
   - **GOOD**: `html/python`'s Installation section — the working from-source path, nothing
     about the defect; the defect lives in its `upstream-issues.md` BLOCKING entry. For
     `tex/python` after this rule: the At-a-Glance note deleted, the packaging bullet deleted,
     the `load_format=False` and hyphenation bullets kept (designed limitations, statically
     observable), and the BLOCKING import-failure entry kept in `upstream-issues.md`.
   - When `verify-examples --python-runner` reports `UPSTREAM-BROKEN` (TC-26), that label is
     **reviewer evidence** (`verification/result.json`) and the reviewer's pointer is
     `upstream-issues.md` + `upstream_issue_workflow.py` — never a sentence in the candidate.

   **At-a-Glance section shape — heading, one mermaid fence, nothing else (TC-01, same
   mission).** `## At a Glance` contains exactly one ```` ```mermaid ```` fence and no other
   content: no note, caveat, intro sentence, HTML comment or `<details>` wrapper before it, nothing
   after it. This held on 30 of 31 products for weeks by imitation only — it appeared in no
   template, contract or rule, and every one of the 17 diagram checks reads the diagram through a
   document-wide regex, never the section body, so `tex/python`'s prose note was APPROVED with 0
   hard-gate findings. The original At-a-Glance standard's `Caveat-or-omit` rule applies to
   **node labels** (an inline parenthetical on one capability) and says to *omit* the caveat
   when the limitation is documented elsewhere in the file; a whole-product limitation is a
   Scope and Limitations bullet, never prose in this section. `check_at_a_glance_section_shape`
   (hard gate, below; `data/readme_template_contract.json` → `section_shapes`) is the mechanical
   backstop, and `audit-portfolio`'s `skeleton_singletons` (TC-07) is the cross-product tripwire
   that names any section whose opening shape no other product shares — the signal that would
   have caught this without a bespoke rule, and that will surface the next unnamed shape drift.

   **At-a-Glance diagram composition — Starting Points, Outputs, and Project Structure
   (2026-08-13, `cells/java` healing pass).** The container-chain shape is fixed
   (`Product → Core Capabilities → Outputs`, with an optional `Starting Points` container ahead
   of `Product`) but two real, live defects — a wrong Starting Points node and a wrong Outputs
   node, both on `cells/java`, both already correctly caught by the hard gates below before this
   guidance existed — showed the *composition* rules that should have prevented them were never
   written down anywhere a composing agent actually reads. Corrected here, not just fixed on that
   one product.
   - **Starting Points presence, corrected** (this paragraph replaces an earlier, stale
     hybrid-only description): required and populated with the product's real, distinct input
     formats for `transform`/`compile` archetypes; forbidden entirely for `generative`; exactly
     2 lines for `hybrid` (its own established "An existing X document" / "Nothing — authored
     from scratch" shape). Never assume "hybrid-only" — that was true before 2026-08-06 and is
     no longer the real rule.
   - **A format belongs in Starting Points only if it is a genuine PRIMARY document the product
     loads/creates/saves on its own terms — not merely auxiliary material a capability happens to
     also consume.** Exclusion tests (verify against real source before drawing *or* omitting,
     same discipline as every other diagram claim):
     - *(a) Capability-path selector* — chooses which of several already-modeled Capability nodes
       runs; redundant with their own existence.
     - *(b) Access/invocation-mechanism selector* — how the caller invokes the library, not data
       it operates on.
     - *(c) Bundled/internal resource* — ships inside the package, never supplied by the caller.
     - *(d) "Build from scratch"* — absence of input data is not itself input data; model as a
       Capability, not an Input.
     - *(e) Embedded/attached auxiliary material* — real, external, caller-supplied data that
       materially shapes a capability's output, EXCLUDED anyway when BOTH hold: (i) the product
       never exposes a top-level load/parse call whose primary subject is this format — it is
       only ever accepted as a parameter while building/editing a *different* primary document;
       and (ii) the product does not decode/interpret the format's own structure, only identifies
       (sniffs) and stores it as an opaque blob. Confirmed live: `cells/java`'s
       `PictureCollection` only magic-byte-sniffs JPEG/PNG/GIF/BMP (`PictureCollection.java:
       72-75`) and never independently loads one — the format belongs in Key Capabilities prose
       ("embeds images... detecting JPEG, PNG, GIF, and BMP formats"), never Starting Points.
       Cross-checked against every sibling product with a picture-embedding capability
       (`slides/java`, `slides/net`, `cells/net`, `cells/python`, `cells/rust`, `pdf/cpp`,
       `pdf/go`) — all nine already fold this into a Capabilities node or a genuine rendering
       Output, none show it as a Starting Point; this rule makes that existing, unwritten
       convention explicit rather than inventing a new one. Contrast: if the product's own
       top-level API *does* let a caller independently load a document of format X (not merely
       embed it), X still belongs in Starting Points for that real capability — (e) excludes only
       formats with no independent top-level load path anywhere in the product.
   - **When `check_diagram_verified_format_claims` or `check_diagram_container_format_purity`
     fires, check first whether the flagged node's concept is already — or belongs — represented
     as a Capability node.** If so, delete the Starting-Points/Outputs node; that is usually the
     correct resolution, not "strengthen the evidence until the claim passes." Reserve evidence-
     strengthening for a format that genuinely is a primary document and is simply under-recorded
     in `formats.md`/source. Confirmed live: `cells/java`'s `"Load diagnostics and repair report"`
     Outputs node was pure duplication of its own `"Load diagnostics and repair reporting"`
     Capability node and Key Capabilities' own `Workbook.getLoadDiagnostics()` sentence — deleting
     it lost zero information. `check_diagram_container_duplicates_capability` (heuristic, below)
     is the standing, mechanical tripwire for this exact shape recurring on a future product.
   - **Project Structure tree format is canonical, not whatever the old README happened to use.**
     When a `## Project Structure` section is restored (structure-dispositions.json, MT030-
     sibling mechanism), its fenced tree must use box-drawing characters (`├──`/`└──`/`│`),
     matching the one real, shipped, approved precedent (`cells/go`) — never the old upstream
     README's own native style (plain indented text, YAML-like nesting, etc.) reproduced
     verbatim. `check_project_structure_canonical_tree_format` (hard gate, below) enforces this
     mechanically so the next product can't silently pick a third visual convention.

   **API Reference detail must always collapse; the Enterprise Edition paragraph must always be
   genuinely separate from the Limitations bullets (MT045, Thirty-Fifth incident, 2026-08-15,
   TC-HARDEN-67/68/70).** A real `barcode/python` regeneration independently reproduced BOTH
   defects at once, and a portfolio scan found the first defect ALSO on `3d/net`/`3d/typescript`
   (2 separate regeneration batches) — proof neither convention was ever durable, only imitated.
   - **`<details>`-collapse the API Reference detail content, unconditionally, regardless of
     row/class count.** Every real module table row and every curated `` - `ClassName` ``
     member bullet goes inside `<details><summary>View the Full API Surface</summary>...
     </details>`, the same shape `## Additional Examples`'s own exhaustive table already uses —
     size is never a threshold (`tex/python`'s real 11-class table, the smallest real API surface
     in the whole portfolio, still collapses). `check_api_reference_detail_collapsed` (hard gate,
     below) mirrors `check_examples_table_collapsed`'s design exactly.
     - **BAD** (real, confirmed on `barcode/python`): a `### Core API` table, an `#### Enumerations`
       table, and no `<details>` tag anywhere in the section — every row fully expanded above the
       fold.
     - **GOOD**: intro sentence naming real hub classes, visible → `<details><summary>View the
       Full API Surface</summary>` → every module table + curated bullet → `</details>`.
   - **Never continue a Limitations bullet's own sentence directly into the Enterprise Edition
     mention — always insert a blank line and start a genuinely separate paragraph.**
     `check_scope_limitations_format` (hard gate, unchanged design intent, bug-fixed below) had a
     real, reproducible bug that silently missed this exact shape.
     - **BAD** (real, confirmed on `barcode/python`): *"...PDF rendering is not implemented...
       For PDF rendering and additional symbologies, see the\n[Aspose.BarCode for Python —
       Enterprise Edition](...), which adds\nthe full commercial rendering pipeline..."* — no
       blank line before the Enterprise sentence; it is the same bulleted list item's own wrapped
       continuation.
     - **GOOD** (real, already-shipped — `email/python`, `3d/python`, `cells/cpp`): the bulleted
       Limitations list, a blank line, then a standalone paragraph: *"These limitations apply only
       to {Product} FOSS — they don't carry over to [{Product} — Enterprise Edition](...), which
       adds..."*

   **Additional-Example heading contract (readme-refresh-seo-deps-headings-hardening mission,
   2026-08-19) — a genuinely new rule, previously undocumented anywhere in this file.** Every
   worked example inside the "View Additional Examples" `<details>` disclosure must begin with
   its own real, non-generic, unique heading naming the actual developer task — never a plain
   sentence directly followed by a code fence. Confirmed real, live, previously-unnoticed
   portfolio-wide gap: `3d/net`'s own 5 collapsed examples (read verbatim) had zero heading
   markup of any kind, not even a generic "Example N" label — no contract or validator for this
   existed anywhere in this document before this mission.

   Deliberately scoped to the `<details>` disclosure only — the always-visible flagship example
   ahead of it is a different, already-established convention (one primary worked example,
   introduced by the section's own lead-in prose) and is not required to carry its own heading
   by this rule.

   - Heading text must name the real developer task the example performs, using applicable
     verified keywords naturally — never "Example," "Example 1," or any other numerically- or
     generically-named placeholder.
   - Every heading inside the disclosure must be unique; two examples must never share a
     heading.
   - Multiple code blocks may legitimately share one heading (a "before"/"after" pair for one
     worked task) — that is one example, not two, and the second block is never a violation of
     "every example needs a heading."
   - The heading must match the code and surrounding explanation — the same "don't rewrite an
     example's meaning to fit a keyword" discipline already established for Key Capabilities
     bullets above applies here too.
   - Never repeat the same keyword formula across every heading — vary phrasing the same way
     Key Capabilities bullets already vary opening structure.

   ```markdown
   <details>
   <summary><strong>View Additional Examples</strong></summary>

   ### Convert a 3D Scene to a Supported Format

   ...

   ### Build and Transform 3D Geometry

   ...

   </details>
   ```

   The exact headings must be derived from each product's own real, verified workflows — never
   copied from this illustration.

   `check_additional_example_headings` (hard gate, below) enforces heading presence, uniqueness,
   and non-genericness mechanically. **A deliberate design decision, not an oversight**: this
   mission does NOT add a structured JSON sidecar (e.g. `example-workflows.json`) recording each
   example's id/task/APIs/keywords separately from the rendered Markdown, even though an earlier
   draft of this mission's own governing plan considered one. Reason: this exact failure
   mode — a disposition-style JSON sidecar silently drifting out of sync with live content the
   moment either changes — is precisely what the `TC-MICRO-02`/disposition-remediation
   incident (`docs/readme-refresh/current-operational-reference.md` §11) already proved real for
   `content-dispositions.json` (0/48 sampled entries matched their live extraction on reaudit).
   The rendered heading + prose + code fence already IS the structured record this gate needs;
   a second, current-examples-specific sidecar (distinct from the EXISTING disposition files,
   which track old-README *preservation*, a different question entirely) would carry the same
   drift risk for no correctness gain the Markdown parser doesn't already provide.

4. **`ingest-candidate`** — runs the real deterministic checks module
   (`scripts/pipeline/commands/foss/readme_refresh_checks.py`, 91 `check_*` functions as of
   2026-08-16 (MT051) — re-verify against `grep -c "^def check_" readme_refresh_checks.py` before
   trusting this number again). **2026-08-08 diagram simplification (Tenth incident, MT024)**: the At-a-Glance
   diagram is now exactly `Product → Core Capabilities → Outputs` (up to 5 capabilities in one
   column, 6+ split into 2 balanced columns) — no individual per-capability edges. **Starting
   Points presence is archetype-general, not hybrid-only** (corrected 2026-08-08, Eleventh
   incident / MT025, itself corrected in this doc 2026-08-13 after a live composition mistake
   traced the error back to this exact paragraph never having been updated): required, populated
   with real input formats, for `transform`/`compile` archetypes; forbidden for `generative`;
   exactly 2 lines (unchanged shape) for `hybrid`. See the diagram-composition guidance above for
   which formats belong there. **Hard gates** (any finding blocks the transition): required
   sections present in title case, no `forum.aspose.com`/`*.aspose.app` links, license link
   target resolves case-sensitively on disk, (**TC-01**, 2026-09-02) the `## At a Glance`
   section body is exactly one mermaid fence with nothing before or after it
   (`check_at_a_glance_section_shape` — the section-shape rule above), the diagram matches
   the fixed container-chain shape and column-balance rule, the diagram's column order matches the recorded `data/
   diagram_capability_dependencies.json` entry (no-op when none exists — edges there are now
   keyed to the *current* diagram's own node IDs, re-recorded whenever a diagram is redrawn),
   `check_diagram_starting_points_presence` enforces the archetype-general presence/count rule
   above (not hybrid-only), a `Starting Points` container on a `hybrid`-archetype product must
   ADDITIONALLY have its classification freshly re-confirmed *this run*
   (`check_diagram_hybrid_reverification`; `data/diagram_archetypes.json`'s `decided_at` must
   match today — a no-op for every other archetype, since presence-appropriateness is
   `check_diagram_starting_points_presence`'s job, not this one's), a Starting-Points/Outputs
   node whose label significantly word-overlaps an existing Capabilities node's label is flagged
   for likely duplication (`check_diagram_container_duplicates_capability`, heuristic — usually
   means the node should be deleted, not evidence-strengthened; see the composition guidance
   above), a `## Project Structure` section's tree uses canonical box-drawing characters, not the
   old README's own native style (`check_project_structure_canonical_tree_format`, hard gate),
   every format named in the diagram is genuinely supported (cross-checked against
   `knowledge/{family}/{platform}/merged/formats.md`), format-name casing is internally
   consistent and matches `data/format_descriptions.json` where known, no sibling product family
   is cited inside a section that's supposed to describe only this product, the `## Additional
   Examples` exhaustive table is collapsed alongside the remaining worked examples (not always
   visible), (**TC-HARDEN-67**, MT045/Thirty-Fifth incident, 2026-08-15) the `## API Reference`
   section's own detail content — every module table row and curated `` - `ClassName` `` bullet
   — is likewise inside a `<details>` block, unconditionally, never a row-count threshold
   (`check_api_reference_detail_collapsed`; a real, confirmed regeneration-batch defect on
   `barcode/python`, `3d/net`, and `3d/typescript`, not a one-off), every heading (including
   `<summary>` text) is title case, no undisclosed BLOCKING
   command from `upstream-issues.md` is repeated as a normal install/build step, no real
   old-README link/heading/meaning was silently dropped or hidden behind an internal
   process-label like "Preserved repository details", (**2026-08-13, `cells/cpp` healing pass**)
   no internal-only artifact — `upstream-issues.md`, `content-dispositions.json`, the
   `.clone_cache` path, the `knowledge/*/merged` layer, this project's own `reports/repo-
   presenter`/`reports/readme_refresh_runs` trees — is named, linked, or cited anywhere in the
   candidate (`_INTERNAL_LABEL_PATTERNS`, folded into the same `check_dropped_content` hard gate
   as the process-label check above — it is a NEW-candidate-quality check, unconditional, not
   gated on whether an old README exists), the Scope and Limitations section never asserts "no
   known limitations" or any equivalent invented-filler phrasing (`check_scope_limitations_
   format`'s `invented_filler` finding — the section's bulleted list is simply omitted, never
   filled with a sentence about its own absence, when no limitation traces to an allowed public
   source), the closing Enterprise Edition mention is a genuinely separate paragraph, never a
   bulleted Limitation's own wrapped continuation (**TC-HARDEN-68**, MT045/Thirty-Fifth incident,
   2026-08-15 — `check_scope_limitations_format`'s own bullet/continuation classification was
   bug-fixed to route through `_iter_leak_scan_units`; the prior raw-physical-line
   classification silently missed `barcode/python`'s real defect, where the Enterprise sentence
   was the "PDF rendering is not implemented" bullet's own unbroken continuation), (**TC-HARDEN-19**, MT034/Twentieth
   incident, 2026-08-12) every `products.aspose.com` Enterprise Edition link in the candidate
   matches the factpack's own real, live-verified `enterprise_link["url"]` exactly — never a
   guessed slug (this closes a confirmed-live regression: a clean-room regeneration produced a
   real, curl-confirmed 404 that every prior gate, including the anchor-text/context check
   below, passed cleanly), (**TC-HARDEN-62**, MT043/Thirty-Third incident, 2026-08-14 —
   CORRECTED same day, MT044/Thirty-Fourth incident) the anchor's own platform claim matches
   `enterprise_link`'s real, computed `relationship`/`public_platform` — a family relationship's
   anchor names no platform at all, a platform relationship's anchor names the one real
   `public_platform` and no other (see the anchor-text contract under `plan`, above) —
   (**MT044**, Thirty-Fourth incident, 2026-08-14) and, portfolio-wide and document-wide, not
   scoped to the Enterprise-link paragraph, no implementation-bridge disclosure phrase ("via
   Java", "implemented through .NET", "backed by C++", "a wrapper around X", "a binding to X",
   "rather than as a native X") appears anywhere in the candidate at all
   (`check_no_implementation_bridge_disclosure`) — this REPLACES TC-HARDEN-62's own original
   "missing_bridge_disclosure" requirement, which had mandated exactly this wording for a
   compound-slug destination; that requirement was the actual policy defect this later gate
   reverses, not a residual bug, (**TC-HARDEN-21**, MT034, 2026-08-12) no class name appears more than
   once within the same API Reference module table (an exact duplicate row is not the same
   defect as a missing/unrecognized class, and `check_api_reference_table_completeness` has no
   concept of it), (**TC-HARDEN-26**, MT034/Twenty-First incident, 2026-08-12) the `## License`
   section's text starts with the fixed template sentence (linked or unlinked form, per whether
   a real license file was detected) rather than free-form narration — the only prior check for
   this section (`check_license_link_target`) verified the link target alone, never the prose,
   and a blind clean-room regeneration of `3d/typescript` independently reproduced the exact
   2026-08-04 narration-leak defect this rule already named, proving it had never actually been
   enforced, (**TC-HARDEN-27**, MT034/Twenty-First incident, 2026-08-12) the At-a-Glance banner
   is linked to the product's real `products.aspose.org/{family}/{platform}/` homepage whenever
   `content/products.aspose.org/en/{family}/{platform}/_index.md` genuinely exists in this repo
   (a first-party, same-repo-deploy guarantee), and stays unlinked otherwise — never a guessed or
   unconfirmed homepage URL, (**TC-HARDEN-71**, MT046/Thirty-Sixth incident, 2026-08-15) neither
   `## Key Capabilities`'s nor `## Additional Examples`'s own leading intro sentence (the text
   before the first bullet/fenced block/sub-heading) narrates this document's own editorial
   organization or leaks an internal source-filename-plus-size-superlative fact
   (`check_section_intro_no_meta_narration` — see the generalized composition rule above;
   `## API Reference`'s own intro sentence is deliberately excluded, already separately covered),
   and (**MT030**, Fifteenth incident)
   every real old-README content unit has a complete, well-formed disposition record whose
   cited evidence actually resolves against real product-repo/registry/docs data and whose
   claimed section-merge is traceable to real text in the candidate (never two disposition
   entries merging the identical excerpt into the identical section). **(Twenty-Fourth mission,
   2026-08-13, `cells/go`'s missing `Project Structure` section) — two more agent-authored
   sibling files, same tier as `content-dispositions.json`, closing what that file structurally
   can never see:**
   - `structure-dispositions.json` covers STRUCTURAL (non-prose) old-README sections — a section
     whose real content lives entirely or mostly inside a fenced code block (a directory tree, a
     pure command list) produces ZERO content units under `extract_old_readme_content_units` (it
     strips fenced code before segmenting, by design), so it was previously invisible to the
     whole verify-and-merge pipeline. `extract_old_readme_structural_units` gates on content
     SHAPE, not heading text — "Repository Layout"/"Source Layout"/"Project Structure" all
     recognize identically. Every extracted unit needs a disposition
     (`check_structural_unit_disposition_coverage`, hard gate) whose claimed merge is genuinely
     traceable into its `target_section` (`check_structural_unit_merged_into_target_section`,
     hard gate — a `target_section` may be an existing template section OR the unit's own real
     heading, e.g. a genuinely new `## Project Structure` section) with no exact-duplicate merges
     (`check_structural_unit_no_exact_duplicate_merge`, hard gate) and (heuristic)
     `check_structural_unit_tree_paths_plausible` flags a directory-tree unit whose claimed paths
     mostly don't resolve against the real clone cache anymore.
   - `badge-dispositions.json` covers badge semantic reconciliation — previously nonexistent (no
     parsing/classification/dedup mechanism anywhere in this module). `extract_badges` +
     `classify_badge` (an open-string category, never a closed enum) + `verify_badge_target`
     (tiered, network-cautious: a `#` link is a structural placeholder; a shields.io *static*
     `/badge/` URL claiming an inherently-dynamic fact like CI/coverage/downloads/contributors is
     a real, mechanically-decidable red flag, not a guess) + `reconcile_badges` (pairs by
     category + real link target, never by label similarity — the real `cells/go` case: old
     "License" and new "License: MIT" pair correctly despite different wording). Every old badge
     needs a disposition (`check_badge_disposition_coverage`, hard gate) whose
     `preserved`/`superseded_by_duplicate` claim genuinely credits a same-category badge that's
     really in the candidate (`check_badge_preserved_or_credited_in_candidate`, hard gate), plus
     two heuristics (`check_badge_probable_duplicate_disposition`,
     `check_badge_static_claims_dynamic_fact` — the latter runs against the candidate
     unconditionally, catching a freshly-composed static/fake badge, not just a carried-forward
     old one), and one more hard gate, `check_no_duplicate_badges_in_candidate`, checking the
     RENDERED candidate directly (independent of disposition-bookkeeping correctness) for two
     badges sharing a real category and real-world target — the mechanical enforcement of "must
     not display duplicate badges," since a well-formed disposition file doesn't itself guarantee
     the suppressed badge was actually removed from the text. Both files reuse `check_content_
     unit_evidence_resolves` UNCHANGED for evidence resolution — both key entries on `unit_id`,
     which is all that function ever reads.
   - `code-example-dispositions.json` (TC-HARDEN-74, MT047, 2026-08-15 — enforced by the run
     since then but never named in this document until 2026-09-02, TC-03 of
     `readme-refresh-at-a-glance-retention-hardening-2026-09-02`) covers every fenced CODE block
     of the old README (`extract_old_readme_code_units`, `c%04d` ids, unconditional — runs even
     for a section the prose/structural extractors already cover). One entry per unit:
     `disposition` ∈ `merged_verbatim` / `merged_reframed` / `relocated` / `corrected` /
     `excluded`, a real `target_section` for every merge, `excluded_reason` (≥15 chars) for an
     exclusion, `verification.status` + `evidence_ref`. Hard gates: coverage
     (`check_code_example_disposition_coverage`), exact-text survival for `merged_verbatim`
     (`check_code_example_disposition_text_diff`, TC-21), and API-call survival for every merge
     (`check_code_example_api_coverage_survives` — since TC-05, 2026-09-02, judged against the
     LIVE extractor's `api_call_fingerprint`, never the ledger's own field, which 354 of 475
     live entries omit; a `mermaid` unit is skipped). A self-contained old example that comes
     back as a fragment (imports and setup lines gone) is a real retention loss even when its
     API calls survive elsewhere — label it `merged_reframed` honestly, or better, keep it
     self-contained: the retention report shows exactly which lines survived.
   **(MT042, Thirty-Second incident, 2026-08-14) — the badge row has a verified FLOOR, not just
   reconciliation:** everything above stops a real OLD badge from being silently lost — it
   vacuously passes when the old README has zero badges, exactly the gap that let a real
   clean-room candidate ship with a single License badge while every other currently-shipped
   candidate in the portfolio has 2-5 (zero exceptions, full 30-product survey).
   `_detect_available_badges` (`readme_refresh_run.py`) computes the real, per-category
   availability from data this pipeline already has — `_detect_license_file`, `_detect_install_
   info`/`data/package_registry.json`, the real `DependencySnapshot`'s `native_system` bucket,
   `_detect_dev_test_artifacts`'s CI-workflow list, and a resolvable `repo_full_name` — into
   `factpack["available_badges"]`. `check_badge_row_meets_verified_floor` (hard gate) requires a
   License badge whenever one is genuinely available, plus at least one more badge from ANY of
   `{package_version, language_version, ci_build_status, contributor_count}` whenever at least
   one of those is genuinely available — it never mandates a SPECIFIC second category (6 of 30
   real products show CI/build in that slot instead of Contributors, a legitimate editorial
   choice). Safe as a hard gate, unlike `check_installation_matches_package_registry` below:
   `contributor_count` needs nothing but a resolvable `repo_full_name`, so the floor can always
   be satisfied by License + Contributors even when every other category is unavailable or the
   registry data is wrong. `check_badge_available_fact_not_shown` (heuristic) separately prompts
   — never mandates — adding a badge for any OTHER genuinely available category not yet shown.
   **Composition-time discipline this incident names explicitly, generalized beyond badges**:
   before adding a new visible template element sourced from external/structured data (a badge,
   a link, a claim), confirm it has BOTH (a) a `_detect_*` factpack function drawing from real,
   already-available data, and (b) a verifying check confirming the candidate reflects it
   correctly — never rely purely on reconciliation-from-old-content or unaided agent judgment
   for a fact this pipeline can verify. This is the fourth independent instance of the same gap
   found in this plan's history (the Enterprise Edition link, the banner-homepage link, the
   Installation-vs-registry match, now badges) — each time, a real, verifiable fact was left to
   unaided judgment with no `_detect_*`+check pairing until a specific product's content exposed
   it.
   **(MT041, Thirty-First incident, 2026-08-14) — dependency accuracy, hard gates:** the
   `## Dependencies` section's data must exist and be internally consistent
   (`check_dependency_snapshot_completeness`), no unqualified absolute dependency-absence claim
   anywhere in the candidate (`check_unqualified_dependency_claims` — the Claims Policy, see the
   composition guidance above), a Required-section bullet's name must be a real, direct entry in
   the manifest (`check_dependency_direct_transitive_confusion`), an optional/dev-only dependency
   must never be listed under Required (`check_dependency_optional_presented_as_required`/
   `check_dependency_dev_only_presented_as_runtime`), the Intro paragraph's own real dependency
   names must never be contradicted by an unqualified claim elsewhere in the file
   (`check_dependencies_intro_contradiction` — the exact same-document-contradiction shape the
   real `cells/rust` defect had), a Native and System Requirements bullet must never be
   duplicated verbatim in Scope and Limitations
   (`check_dependency_native_system_scope_limitations_placement`), and every `5_dependency_claim`
   disposition entry's evidence must cite the real manifest path or a real dependency name, never
   narrative-only evidence (`check_dependency_disposition_reconciliation`).
   **Heuristic checks** (surfaced for
   judgment, never auto-fail): mechanism-duplicate output nodes, process-narration smells (now
   covering internal receipts/execution notes/provenance/confidence language, not just the
   original 22 incident-specific phrases), Enterprise Edition anchor-text naming *and* context
   (must explain the broader/full functionality gained, not be a naked CTA — standard anchor text
   is `"Enterprise Edition"`, decided 2026-08-08), section-job distinctness (intro vs. Key
   Capabilities overlap), a weak API-reference intro sentence, and named-member accuracy (a
   grep-based heuristic — see that function's own docstring for its honest, stated scope limits,
   most importantly that it does not trace inheritance), and (**MT030**) content-unit
   classification plausibility (a mechanical narrative/CTA tone prefilter cross-checked against
   the agent's own stated classification), probable-duplicate content-unit merges (2+ shared
   salient tokens into the same section with a non-identical excerpt), and (**MT031**) an
   embedded-actionable-fact tripwire flagging an excluded narrative/CTA unit whose excerpt
   contains a real request/contact phrase worth re-examining, and (**TC-HARDEN-32**, MT035,
   2026-08-12) whether the `## Installation` section's real content agrees with `data/
   package_registry.json`'s own `published`/`candidate` fields for this product — deliberately
   a heuristic, not a hard gate, per direct live evidence found the moment this check first ran
   against real content: that registry file was independently wrong, in both directions, for
   real products already in this portfolio (`words/net`'s real, live NuGet package contradicts
   its own `published: false`; `email/net`'s real nuspec casing contradicts its own
   `candidate.name` casing) — the same "even structured, checked-in data isn't infallible"
   lesson `formats.md` already taught this plan. `check_diagram_
   suspicious_direct_product_edge`/`check_diagram_capability_unreachable_from_product` are
   retired — both were tripwires for a per-node-edge defect class the simplified model can no
   longer produce. (**MT041**, 2026-08-14) `check_dependency_section_manifest_corroboration` —
   cross-checks the Required-section bullets against `knowledge/{family}/{platform}/merged/
   claims.json`'s own "kind": "dependency" claims; deliberately heuristic, since those claims
   are confirmed to be a lossy, name-only re-parse of the SAME manifest at a possibly different
   revision (`scout.py` → `package_manifest.py` → `claims.py`), never independent corroborating
   data — `check_dependency_version_pin_freshness`, flagging a prose-cited version that
   doesn't match the manifest's real constraint (routinely a legitimate range-vs-point
   difference, so a prompt, never a block) — and `check_dependency_scope_claim_matches_evidence`
   (a scoped "no proprietary runtime"-shaped claim's category has real corroborating snapshot
   data), **downgraded from an originally-planned hard gate the moment it ran against real
   content**: no extractor today populates the `proprietary_runtime` category at all, so this
   check's only possible outcome is "always flag" — including against this skill's own
   sanctioned GOOD-example phrasing (composition guidance above) — the same "don't hard-gate on
   a claim category with no real verifier behind it" lesson `check_installation_matches_
   package_registry` already taught this skill (TC-HARDEN-32).
   Transitions `PLANNED → VERIFYING_EXAMPLES` only once every hard gate passes.

5. **`verify-examples`** — runs the (pluggable) per-language compile/run verification pass and
   writes `verification/result.json` plus `upstream-issues.md` (written for every run, including
   the clean case — an absent file is itself a bug). **Honest scope note**: the default runner
   reports every code block `BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE` rather than claiming a
   compile that never happened — real per-language toolchain wiring (`javac`/`javap`, `dotnet`,
   `go build`, `cargo`, `cmake`/`ninja`, a disposable Python venv, `tsc`) is separate, follow-on
   work, injectable via `configure(verification_runner=...)`. Only transitions
   `VERIFYING_EXAMPLES → AWAITING_REVIEW` once every block has a real, named status.
   `--python-runner` and `--typescript-runner` (TC-25) are the real runners that exist today;
   `--python-runner` classifies a syntax-family failure whose last traceback frame is inside
   the installed package (not the example) as `BLOCKED-WITH-REASON: UPSTREAM-BROKEN` (TC-26)
   rather than a generic `RUNTIME-ERROR`. **That label is reviewer evidence and an
   `upstream-issues.md` entry — never README content** (composition rule "Designed limitations
   vs transient defects", above): the candidate gives the correct usage per source with no
   caveat, and the defect is reported upstream through the issue workflow.

6. **`recheck`** — re-runs the deterministic checks in place after manual edits during
   `AWAITING_REVIEW`, without a state transition. Use this after applying reviewer feedback
   instead of re-planning from scratch.

7. **`approve`** — **the skill must never call this on its own initiative; only on an
   unambiguous, fresh instruction from the user in that turn.** Re-verifies the pinned clone-cache
   `HEAD` hasn't drifted since `start`; if it has, forces the run back to `PLANNED` for re-review
   rather than approving stale content — `approve` itself will raise in that case, it never
   silently substitutes a replan for an approval.

8. **`push`** — disposable-clone + branch + git-plumbing commit (`write-tree`/`commit-tree`/
   `update-ref`, never the shared clone cache) + surgical-diff check (declared file set only,
   currently just `README.md`) + push + `gh pr create` (**no `--draft`**, MT032, 2026-08-10/11 —
   none of these repos have branch protection or a second reviewer, so draft mode was pure
   friction with no offsetting safety benefit; the human review step still happens, just at
   "review the PR before merging" rather than "review, unmark draft, review again"). `--dry-run`
   rehearses every step up to (not including) the live network write, then returns the run to
   `APPROVED` — it never reaches `PUSHED` without a real push. The plumbed commit's message
   carries the real `Co-Authored-By: {real acting session's model} <noreply@anthropic.com>`
   trailer, read fresh each time, never hardcoded.

   **Merging (only on the user's explicit, this-PR-specific go-ahead after their own manual
   review — never on this skill's own initiative)**: `gh pr merge {number} --squash
   --delete-branch`, but **always with explicit `--subject`/`--body` (or `--body-file`), never
   accepting `gh`'s own default squash-message construction** (2026-08-13, cells/cpp healing
   pass — a real, confirmed defect). GitHub's default squash-commit-message builder auto-appends
   a `Co-authored-by:` trailer for the underlying plumbed commit's own git-level Author identity
   (the human operator, e.g. `babar-raza <babar-raza@users.noreply.github.com>`) **in addition
   to** correctly setting that same person as the merge commit's real Author — a redundant,
   incorrect self-citation: the primary author is already attributed via git's own Author/
   Committer metadata (which GitHub displays natively, no trailer needed); `Co-authored-by` is
   for genuinely *additional* contributors only. **The merged commit's trailer section must
   contain exactly one line**: `Co-authored-by: {real acting session's model} <noreply@
   anthropic.com>` — never the human operator's identity, in any email form, as a co-author.
   Build the `--body` text by hand from the plumbed commit's own real message plus that one
   trailer; do not let `gh pr merge` construct it.

9. **`verify`** — post-push, safely re-runnable any time: confirms the PR still exists and its
   head matches the approved candidate.

## Upstream issue workflow (MT057, Fifty-Seventh incident, 2026-08-19)

A separate, sibling module — `scripts/pipeline/commands/foss/upstream_issue_workflow.py`, its
own CLI (`PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/foss/
upstream_issue_workflow.py {command} {family} {platform} ...`) — verifies, classifies,
deduplicates, bundles, and drafts (**never silently auto-files**) real GitHub Issues for genuine
upstream defects found in a product's own `upstream-issues.md` during README-generation work.
It is deliberately NOT part of `readme_refresh_run.py`'s own state machine — a finding and a
bundle are a different entity type with a different lifecycle (real, separate `FINDING_NEXT_
STATES`/`BUNDLE_NEXT_STATES` dicts) and a different, genuinely new external side effect (a real
GitHub Issue, never a README PR) — merging the two would corrupt the README run's own,
already-proven-narrow transition dict.

**Standing rule, non-negotiable**: a real GitHub Issue is created ONLY via `create-issue --live`
(never the default), and only when a real `GH_TOKEN` is present — mirroring `push()`'s own
`GH_TOKEN`-gated, dry-run-first posture exactly. Nothing in this workflow ever creates an issue
as a side effect of any other step.

**Two-tier state machine, evidence-required on every transition**:
```
FINDING_NEXT_STATES:  DISCOVERED -> VERIFYING -> VERIFIED -> DUPLICATE_CHECKED -> BUNDLED
  (terminal for the finding; bundle_id recorded, further lifecycle on the bundle)
  Alt-terminal: REJECTED_NOT_UPSTREAM, DUPLICATE_EXISTING, FIXED_UPSTREAM,
    PRIVATE_SECURITY_ROUTE, BLOCKED_MISSING_EVIDENCE, DEFERRED_LOW_PRIORITY

BUNDLE_NEXT_STATES:   BUNDLED -> DRAFTED -> INDEPENDENTLY_REVIEWED -> READY_TO_CREATE
  -> CREATED -> REMOTE_VERIFIED
  Alt-terminal/re-enterable: BLOCKED_IDENTITY, DEFERRED_LOW_PRIORITY, and the same
    REJECTED_NOT_UPSTREAM / DUPLICATE_EXISTING / FIXED_UPSTREAM / PRIVATE_SECURITY_ROUTE set
```
`severity == "critical"` **always, unconditionally** forces `PRIVATE_SECURITY_ROUTE` at
classification time — a real, structurally-enforced rule, never left to drafting-time judgment.

**Stages and their real CLI verbs** (each requires `FAMILY PLATFORM` as the first two positional
args, matching every function's own real signature — no ID-parsing magic):

1. `inventory FAMILY PLATFORM` — real, mechanical dual-variant ingestion of the product's own,
   already-existing `upstream-issues.md` (whichever candidate tree is currently configured
   canonical). Auto-rejects a finding matching a real entry in `data/upstream_issue_false_
   positive_exclusions.json` (absent by default, same governance shape as `data/api_reference_
   class_exclusions.json`).
2. `verify-finding FAMILY PLATFORM --finding-id ID --outcome O --evidence-ref REF [...]` — always
   refreshes the real upstream clone first (`git fetch` + default-branch-detect + `git reset
   --hard`, in place, never a fresh clone). Real reproduction is Python-only
   (`disposable_python_venv`); every other language honestly records `manual_language_specific`
   with a real, named per-language procedure note — never a fabricated clean-environment claim.
   `--outcome` is one of the mission's real 14 `VerificationOutcome` values; an unrecognized value
   is rejected outright (Python `Literal` hints are never enforced at runtime).
3. `classify-finding FAMILY PLATFORM --finding-id ID --category C --severity S --priority P
   --classification-basis TEXT` — requires state VERIFIED.
4. `search-duplicates FAMILY PLATFORM --finding-id ID --disposition D --disposition-basis TEXT
   [--query Q ...]` — real, read-only search across 5 real GitHub surfaces (issues, PRs,
   cross-repo issue search, commit messages, the latest release). `disposition`/
   `disposition_basis` are real, required caller judgment — this step runs the searches and
   records the real results, it never decides what they mean.
5. `bundle FAMILY PLATFORM --finding-ids ID1,ID2 --root-cause TEXT --why-bundled TEXT
   --same-component --same-root-cause --same-maintainer-audience --same-repro-env
   --single-fix-resolves-all` — refuses unless ALL five gates are explicitly true, naming exactly
   which failed. `same_repo` is enforced structurally, never a sixth flag.
6. `prioritize FAMILY PLATFORM --bundle-id ID [--priority P --priority-basis TEXT]` — real,
   mechanical derivation (the bundle's own most urgent classified finding) when no override is
   given; an override with no stated basis is rejected.
7. `draft-issue FAMILY PLATFORM --bundle-id ID` — composes `draft.md` fresh from each finding's
   own structured, already-verified fields (`original_observation`, `raw_fields.evidence_raw`/
   `impact_raw`, `verification.*`, `classification.*`) — **never copies raw `source_excerpt`
   verbatim**, since that text could itself still carry an internal reference. Requires state
   BUNDLED.
8. `validate-draft FAMILY PLATFORM --bundle-id ID --reviewer-id ID --reviewer-verdict
   approved|confirmed [--reviewer-note TEXT]` — runs both `check_no_internal_details_leaked_
   into_issue_draft` and `check_issue_draft_rejection_list` as real, blocking hard gates; a
   real, positive independent reviewer is separately, structurally required — a bundle can never
   reach `INDEPENDENTLY_REVIEWED` on automated checks alone. On failure the bundle stays at
   `DRAFTED`; **the sanctioned repair is to hand-edit `draft.md` directly, then re-run
   `validate-draft`** — re-running `draft-issue` alone reproduces the identical composed text
   from the same underlying fields and will not fix a leak sourced from `raw_fields` itself
   (confirmed live, TC-UIW-15's own real walkthrough: the internal-only `upstream-issues.md`
   schema's own Evidence/Impact register legitimately uses audit-trail phrasing like "fails
   identically" — real, correct there, but a genuine leak once copied into a public draft; the
   fix was a direct, hand-authored reword of `draft.md`, not a re-draft).
9. `check-identity` — standalone, safely re-runnable any time, no family/platform needed. Real
   `gh api user` call; never raises on an unauthenticated/wrong account (a real, valid outcome to
   report, not a crash).
10. `create-issue FAMILY PLATFORM --bundle-id ID [--live]` — identity is re-verified on **every**
    call, dry-run or not (a dry-run whose preview doesn't reflect a real identity check would be
    a misleading rehearsal), writing a real `attribution.json` every time. A bundle at
    `INDEPENDENTLY_REVIEWED` is first queued (`-> READY_TO_CREATE`); a wrong/absent identity
    routes to the real, re-enterable `BLOCKED_IDENTITY` state and leaves the draft **completely
    untouched**. Omitting `--live` (the real, safe default) performs zero `gh issue create`/
    `gh issue view` calls and stops at `READY_TO_CREATE` with the exact real payload
    (`repo_full_name`, `title`, `body`) written to `creation-receipt.json`. `--live` additionally
    requires a real `GH_TOKEN`; on success it performs a real, read-only read-back-and-confirm
    (`gh issue view`) before promoting the bundle to the real `REMOTE_VERIFIED` terminal state — a
    read-back failure or title mismatch correctly leaves the bundle at the real, inspectable
    `CREATED` state instead.
11. `status FAMILY PLATFORM [--json]` — read-only portfolio/product view, every real finding and
    bundle grouped by state. Safe to call at any time, including against a product with no real
    inventory yet.

**Evidence layout**: `reports/upstream_issue_runs/{family}/{platform}/` — `inventory.json`,
`findings/{finding_id}/{manifest.json, verification.json, classification.json, events.jsonl}`,
`bundles/{bundle_id}/{manifest.json, duplicate-search.json, draft.md, attribution.json,
validation.json, creation-receipt.json, events.jsonl}`, `duplicate-search-ledger.json`,
`bundle-ledger.json`. Cross-run audit trail: `reports/upstream_issue_actions.jsonl` (same real
row shape as `repo_presenter_actions.jsonl`, one row per real action across every stage,
dry-run and live pushes both recorded via `details["dry_run"]`).

## Onboarding a new product, platform, or family (TC-HARDEN-35, MT035, 2026-08-12)

No such section existed anywhere in this repo before this one — confirmed by an exhaustive
search of this file, `AGENTS.md`, and `skills/registry.json`'s S-120 entry (no `dependencies`
field). This section describes the **real, current** behavior of the checked-in code as of
2026-08-12, not an aspirational future state — it will be extended as `TC-HARDEN-33` closes
(see the plan's Twenty-Second incident / MT035 section for the full evidence trail behind every
claim below: `C:\Users\prora\.claude\plans\d-users-prora-onedrive-documents-github-humble-tome.md`).

**1. The real prerequisite chain — mechanically load-bearing, not just recommended.** Run
`/repo-scout` → `/knowledge-enrich` → `/truth-merge` for the new product **before** attempting
`plan`/`ingest-candidate`. This is not a soft suggestion: `check_diagram_verified_format_claims`
(a hard gate) requires 2 of 3 independent signals (`formats.md` row / prose mention / real source
evidence) to accept any format claim in the diagram's `Starting Points`/`Outputs` containers —
with no `knowledge/{family}/{platform}/merged/formats.md` and no `api_surface.json`, only the
prose signal can ever be true (1 of 3), so **every real format claim in the diagram will
mechanically fail to verify** until the knowledge pipeline has run at least once.

**2. Which data files need a new row, and which correctly default:**

| File | New product needs an entry? |
|---|---|
| `data/products.json` | **Yes, required.** `family`, `platform`, `repo_url`, `clone_url`, `active: true` at minimum — `_resolve_product` (TC-HARDEN-30, fixed 2026-08-12) now validates `repo_url`/`clone_url` are present and raises a clean `README-REFRESH-RUN BLOCKED: ... missing required field(s): ...` message if either is missing or the file has a JSON syntax error, rather than a raw traceback. |
| `data/registry_exclusions.json` | Only if the product should be excluded from this skill's coverage. |
| `data/diagram_archetypes.json` | No entry needed by default — absence correctly defaults to `transform`. Add an entry only if the product is genuinely `hybrid`/`generative`/`compile` (Template section's 3-condition hybrid test, or the equivalent generative/compile tests). |
| `data/families.json` | **Yes, required for a genuinely new FAMILY** (not a new platform of an existing family) — see the disclosed gap in item 4 below; this is not yet mechanically enforced if forgotten. |
| `data/aspose_com_targets.json`, `content/products.aspose.org/en/{family}/{platform}/`, `content/reference.aspose.org/en/{family}/{platform}/` | No entry required before a first run — each degrades gracefully (see item 3), but the resulting candidate will carry real, visible gaps (no Enterprise link, no homepage-linked banner, no API Reference table) until the real content exists. |

**3. What to expect on a first real run, before knowledge/content exist yet:**
- The diagram's `Starting Points`/`Outputs` containers cannot carry any real format claim yet
  (item 1) — compose the rest of the candidate, but expect `diagram_verified_format_claims` to
  block until `/repo-scout` has run at least once.
- `check_api_reference_classes_exist_in_reference_site` (TC-HARDEN-31, fixed 2026-08-12) now
  **correctly blocks**, with a real named finding per cited class, rather than silently passing
  — the exact opposite of its pre-2026-08-12 behavior, which produced zero findings
  (indistinguishable from "verified clean") when neither `content/reference.aspose.org/.../
  _index.md` nor the clone cache existed yet. Do not compose the curated API Reference bullet
  detail (the `` - `ClassName` `` convention) until at least one of those two sources is real —
  the MT028 mechanically-generated table has the same real dependency anyway.
- `check_dev_test_artifacts_linked`, `check_no_undisclosed_blocking_commands`, and similar
  clone-cache-scanning checks degrade gracefully with an empty clone cache (nothing found means
  nothing is required) — safe to run before `/repo-scout`, unlike the two checks above.

**4. Fixed since this section was first written (2026-08-12):**
- **New-language source discovery (TC-HARDEN-34, fixed 2026-08-12)**: `_find_class_source_files`'s
  extension allowlist now also recognizes PHP (`.php`), Kotlin (`.kt`/`.kts`), Ruby (`.rb`), and
  Swift (`.swift`), alongside the original 10 extensions — a deliberate, bounded widening (see
  `_CLASS_SOURCE_EXTENSIONS`'s own docstring), not an open-ended "any extension" policy. A new
  language outside this set is still invisible to `check_named_member_accuracy` and to
  `check_api_reference_classes_exist_in_reference_site`'s clone-cache fallback until the
  allowlist is widened again — a real, bounded, but no longer *permanent* blind spot.
- **Installation-section verification (TC-HARDEN-32, fixed 2026-08-12)**: `check_installation_
  matches_package_registry` now cross-checks the composed `## Installation` section against
  `data/package_registry.json`'s `published`/`candidate` fields — deliberately a **heuristic**,
  not a hard gate, per direct live evidence found the moment this check first ran against real
  content: that registry file was independently confirmed wrong, in both directions, for real
  products already in this portfolio. A finding here is a prompt to check which side (the
  content or the registry) is actually stale, never an automatic "the content is wrong."

**5. Known, disclosed gaps not yet fixed — do not assume these are handled:**
- **`data/families.json` consistency (TC-HARDEN-33)**: this is a separate, hand-maintained
  registry from `data/products.json`, not derived from it. If you add a genuinely new family to
  `products.json` without also adding it to `families.json`, `check_no_cross_product_citation`'s
  family allowlist silently stops catching *any other product's* citation of the new family — no
  warning is raised. Add the new family to `data/families.json` manually; nothing currently
  reminds you if you forget.

## Post-conditions

- `AWAITING_REVIEW`: candidate has passed every hard-gate deterministic check and every code
  block has a named verification status.
- `PUSHED`: a non-draft PR is open against the product's real default branch (MT032, 2026-08-10/11
  — the `--draft` flag was removed from `_do_push`; re-confirmed live 2026-08-30), with
  `README.md` as the only changed file, evidence recorded at
  `reports/readme_refresh_runs/{family}/{platform}/{run_id}/` and
  `reports/repo_presenter_actions.jsonl` (the shared cross-run ledger — wired and live).

## Error handling

- `start`: pre-flight access failure, product not found/excluded, or an already-active run for
  the same product all raise before any state is created.
- `ingest-candidate`: any hard-gate finding raises with `checks/result.json` written first, so
  the specific failing check is always inspectable, not just a bare failure message.
- `verify-examples`: raises if any code block has no named status; never silently advances.
- `push`: any failure (clone, plumbing, surgical-diff mismatch, network push, `gh pr create`)
  transitions the run to `BLOCKED` with the failure reason recorded, rather than leaving it in
  an ambiguous `PUSHING` state — `recover` resumes from `resume_state` afterward.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-120 --status completed
> ```
