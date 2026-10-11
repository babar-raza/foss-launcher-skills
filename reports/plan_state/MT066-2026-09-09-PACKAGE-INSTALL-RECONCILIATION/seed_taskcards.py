"""One-time seed of the MT066 taskcard DAG (schema 5f). Run once; TaskcardStore.append()
is itself append-only and will error loudly on a duplicate/conflicting mission_id, not
silently double-write status history for the same task_id."""
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts/pipeline")
from lib.taskcard_store import TaskcardStore  # noqa: E402

MISSION = "MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION"
RECORDED_BY = "agent-session-b2a5f5f7"
NOW = datetime.now(timezone.utc).isoformat()

store = TaskcardStore(MISSION)

CARDS = [
    dict(
        task_id="PKGINSTALL-REPAIR-PLAN-DOCUMENT",
        status="IN_PROGRESS",
        title="Repair the plan document per its own PLAN_NEEDS_REPAIR self-review",
        objective=(
            "Fix the concrete defects found in the plan-review pass: move "
            "observation-only fields (last_observed_at/reconciliation_state) out of "
            "data/package_registry.json into a reports/ ledger; resolve the Phase 3/4 "
            "numbering inconsistency between sections H/N and section P; add "
            "override-token references for every protected path the plan touches "
            "(layouts/shortcodes/, .github/workflows/); reinstate git_plumb_commit.py's "
            "_file_skill_run_record() wiring that the pre-healing draft had; re-verify "
            "the section-A content-census counts against current HEAD and cite the SHA."
        ),
        why_it_matters=(
            "Every downstream taskcard in this mission depends on the plan itself being "
            "executable, not just architecturally sound -- the control-plane/render-truth "
            "bug specifically would cause daily spurious full-portfolio rebuilds if built "
            "as originally drafted."
        ),
        allowed_paths=["<local-plan-cache>/this-chat-is-about-polymorphic-brook.md"],
        forbidden_paths=["content/", "data/", "layouts/", ".github/workflows/"],
        dependencies=[],
        acceptance_checks=[
            "Plan's Design/Data-model section no longer places per-run observation "
            "fields inside data/package_registry.json",
            "Phase numbering is internally consistent across all cross-references",
            "Every protected-path edit in the plan cites the override-token step",
            "_file_skill_run_record()/--skills/--plan wiring is present for every "
            "auto-commit path described",
            "Section A counts carry an explicit baseline commit SHA",
        ],
        evidence_refs=[],
        recorded_at=NOW,
        recorded_by=RECORDED_BY,
    ),
    dict(
        task_id="PKGINSTALL-SCHEMA-ADAPTER-VERSION-EXTENSION",
        status="TODO",
        title="Extend registry schema + 4 adapters with live version extraction",
        objective=(
            "Add version extraction to pypi/nuget/npm/go_modules adapters (mirroring "
            "Maven's maven-metadata.xml <release> pattern); confirm/extend "
            "data/schemas/package-registry-schema.json's candidate sub-schema to "
            "formally allow a version field for every registry_type including "
            "go_modules; add crates.io yanked-version awareness."
        ),
        why_it_matters=(
            "No registry besides Maven currently extracts a live version at all -- this "
            "is the prerequisite fact-gathering capability every later version-propagation "
            "stage in this mission depends on."
        ),
        allowed_paths=[
            "scripts/pipeline/lib/package_registries/pypi.py",
            "scripts/pipeline/lib/package_registries/nuget.py",
            "scripts/pipeline/lib/package_registries/npm.py",
            "scripts/pipeline/lib/package_registries/go.py",
            "scripts/pipeline/lib/package_registries/cargo.py",
            "data/schemas/package-registry-schema.json",
            "scripts/pipeline/tests/test_package_registries.py",
        ],
        forbidden_paths=["content/", "data/package_registry.json"],
        dependencies=["PKGINSTALL-REPAIR-PLAN-DOCUMENT"],
        acceptance_checks=[
            "Each of the 4 adapters' check_published() returns a populated version "
            "field from fixture responses (no live network calls in tests)",
            "validate_package_registry() accepts a go_modules entry with a version key",
            "crates.io adapter surfaces yanked:true distinctly from published:false",
        ],
        evidence_refs=[],
        recorded_at=NOW,
        recorded_by=RECORDED_BY,
    ),
    dict(
        task_id="PKGINSTALL-UNIVERSAL-STATE-MACHINE-DETECTION",
        status="TODO",
        title="Wire is_corroborated_match into scheduled watchers; generalize version-drift detection to all 6 registries",
        objective=(
            "Wire is_corroborated_match() into check_unpublished_entries() and "
            "check_unpublished_families() as a required precondition before a proposal "
            "is generated; generalize publish_watcher.py's "
            "check_published_families_for_new_version() pattern to pypi/nuget/npm/"
            "go_modules/cargo; implement Stage D's pure desired-state function and the "
            "new IDENTITY_CONFLICT/CANDIDATE_UNCORROBORATED states. Detection only -- "
            "no auto-write yet."
        ),
        why_it_matters=(
            "This closes the two real gaps found during investigation: the riskier "
            "unpublished->published transition currently has no identity-corroboration "
            "gate in its live scheduled path, and 5 of 6 registries have no steady-state "
            "version-drift detection at all."
        ),
        allowed_paths=[
            "scripts/pipeline/commands/ops/publish_watcher.py",
            "scripts/pipeline/commands/ops/package_publish_watch.py",
            "scripts/pipeline/tests/test_publish_watcher.py",
            "scripts/pipeline/tests/test_package_publish_watch.py",
        ],
        forbidden_paths=["content/", "data/package_registry.json"],
        dependencies=["PKGINSTALL-SCHEMA-ADAPTER-VERSION-EXTENSION"],
        acceptance_checks=[
            "A fixture-driven test proves an uncorroborated candidate never produces a "
            "publish proposal from the scheduled path",
            "A version-drift proposal is produced for a fixture pypi/nuget/npm/"
            "go_modules/cargo entry whose live version differs from recorded",
            "Dry run against real current registry data produces the same proposals as "
            "today for Maven, plus new version-drift proposals where applicable",
        ],
        evidence_refs=[],
        recorded_at=NOW,
        recorded_by=RECORDED_BY,
    ),
    dict(
        task_id="PKGINSTALL-REGISTRY-AUTOAPPLY-COMMIT",
        status="TODO",
        title="Auto-apply registry-state transitions and commit, all 6 registries",
        objective=(
            "Add --auto-apply to both watcher scripts; atomic write (temp file -> "
            "reparse -> revalidate -> os.replace); registry-level circuit breaker "
            "(~5 identity transitions/run); wire git_plumb_commit.py with bot identity "
            "and _file_skill_run_record(); override-token step for the "
            ".github/workflows/*.yml permission changes this requires."
        ),
        why_it_matters=(
            "This is the actual automation the mission was originally asked for: "
            "removing the human-run /package-publish-watch (S-118) step from the "
            "normal path for both unpublished->published and version-update "
            "transitions, across all 6 registries, not just Maven+Cargo."
        ),
        allowed_paths=[
            "scripts/pipeline/commands/ops/publish_watcher.py",
            "scripts/pipeline/commands/ops/package_publish_watch.py",
            ".github/workflows/maven-publish-watcher.yml",
            ".github/workflows/package-publish-watch.yml",
            "data/package_registry.json",
        ],
        forbidden_paths=["content/"],
        dependencies=["PKGINSTALL-UNIVERSAL-STATE-MACHINE-DETECTION"],
        acceptance_checks=[
            "Dry run against real current data/package_registry.json produces zero "
            "spurious writes when nothing has actually changed upstream",
            "A live cron cycle produces a real, validated, idempotent commit or a "
            "correct no-op",
            "Override token created and consumed for the two .github/workflows/*.yml edits",
            "Retroactive skill-run record exists for every auto-commit made",
        ],
        evidence_refs=[],
        recorded_at=NOW,
        recorded_by=RECORDED_BY,
    ),
    dict(
        task_id="PKGINSTALL-EXECUTE-ST054-MIGRATION",
        status="TODO",
        title="Execute the existing, already-designed ST-054 plan (TC-01..TC-11)",
        objective=(
            "Execute plans/from_backlog/2026-08-16-st-054-inline-install-command-"
            "remediation.md's own taskcards TC-01 through TC-11 under this mission's "
            "tracking, without duplicating or re-numbering them: new "
            "package-install-inline shortcode, _INSTALL_CMD_RE regex fix, "
            "install_block_updater.py durability fix, fresh sweep + collision "
            "classification, mechanical migration + locale propagation, manual "
            "fallback for collision-risk cases, recurring sweep, verification, "
            "closeout. Fold the newly-found live defects (cells/net identifier "
            "collision, HR cross-contamination, ZH stale-package-instruction) into "
            "TC-04's fresh sweep and TC-08's manual bucket as concrete instances."
        ),
        why_it_matters=(
            "This is the single largest piece of unexecuted, already-designed work in "
            "the portfolio (6,364 inline occurrences) and the plan's own gap-matrix "
            "identified it as required, not optional cleanup."
        ),
        allowed_paths=[
            "layouts/shortcodes/package-install-inline.html",
            "scripts/pipeline/audit/package_install_literal.py",
            "scripts/pipeline/commands/content/install_block_updater.py",
            "scripts/pipeline/commands/content/package_install_inline_migrator.py",
            "content/{docs,blog,kb,products}.aspose.org/**",
        ],
        forbidden_paths=["scripts/pipeline/lib/package_registries/"],
        dependencies=["PKGINSTALL-REPAIR-PLAN-DOCUMENT"],
        acceptance_checks=[
            "ST-054's own TC-10 acceptance checks pass: 0 FAIL on "
            "verify_package_install_literals(), real Hugo build across all 4 "
            "affected sites, full test suite green",
            "The 3 newly-found live defects are confirmed remediated by name",
        ],
        evidence_refs=[],
        recorded_at=NOW,
        recorded_by=RECORDED_BY,
    ),
    dict(
        task_id="PKGINSTALL-PERMANENT-RECONCILIATION-LOOP",
        status="TODO",
        title="Generalize page inventory/change-proposal/validation into a permanent, recurring stage",
        objective=(
            "Build the Stage E/F/G page-inventory join (install_recipe.py eligibility "
            "+ shortcode-invocation scan + package_install_literal.py detector) as a "
            "reusable artifact under reports/, and wire it to fire from any live "
            "Stage-D transition going forward -- not just the one-time ST-054 "
            "migration -- with its own content-level circuit breaker distinct from "
            "the registry-level one."
        ),
        why_it_matters=(
            "Without this, new products/registries added after ST-054 closes would "
            "start accumulating the exact same literal-text debt again; this is what "
            "makes the reconciliation genuinely continuous rather than a one-time cleanup."
        ),
        allowed_paths=[
            "scripts/pipeline/commands/content/",
            "reports/package-reconciliation/",
        ],
        forbidden_paths=["data/package_registry.json"],
        dependencies=[
            "PKGINSTALL-REGISTRY-AUTOAPPLY-COMMIT",
            "PKGINSTALL-EXECUTE-ST054-MIGRATION",
        ],
        acceptance_checks=[
            "A simulated new-publish event for a test product produces a correctly "
            "bounded, validated, locale-propagated content change with zero manual "
            "skill invocation",
            "A fixture proposal set that would exceed the content-level threshold is "
            "proven to abort-and-defer rather than partially apply",
        ],
        evidence_refs=[],
        recorded_at=NOW,
        recorded_by=RECORDED_BY,
    ),
    dict(
        task_id="PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX",
        status="TODO",
        title="Deploy-trigger 3-layer fix: this repo's poll + Aspose/aspose.org-workflows PR",
        objective=(
            "Layer 3 (this repo): poll the sibling repo's scan_state.json/"
            "deploy_manifest.json to confirm an auto-commit's SHA actually surfaced, "
            "filing an issue if not. Layer 2 (sibling repo, SEPARATE reviewed PR, "
            "human-authority-gated per MISSION_AUTHORITY.yaml -- never agent auto-"
            "merge): add SHARED_DATA_CONSUMERS to detect_changes.py's "
            "map_path_to_workflow() plus a loud unmapped-path warning fallback."
        ),
        why_it_matters=(
            "Confirmed by direct reading of the full chain: a commit touching only "
            "data/package_registry.json is invisible to the sibling repo's daily "
            "scanner today -- without this, none of the automation above ever "
            "actually reaches a real site rebuild."
        ),
        allowed_paths=[
            "scripts/ci/checks/verify_deploy_trigger.py",
            "Aspose/aspose.org-workflows:scripts/deploy/detect_changes.py",
        ],
        forbidden_paths=["Aspose/aspose.org-workflows:.github/workflows/"],
        dependencies=["PKGINSTALL-REGISTRY-AUTOAPPLY-COMMIT"],
        acceptance_checks=[
            "Layer 3 poll correctly distinguishes 'recognized and deployed' from "
            "'silently dropped' against two real historical SHA pairs",
            "Layer 2 PR merge has an explicit, recorded operator go-ahead (never "
            "agent-initiated merge) per MISSION_AUTHORITY.yaml human_authority_boundaries",
        ],
        evidence_refs=[],
        recorded_at=NOW,
        recorded_by=RECORDED_BY,
    ),
    dict(
        task_id="PKGINSTALL-OPERATIONAL-ROLLOUT-MONITORING",
        status="TODO",
        title="Operational rollout: cadence, logging, alerting, first live cycle",
        objective=(
            "Wire final cadence (daily detection/auto-apply, weekly full-corpus "
            "literal sweep), reports/package-reconciliation/ logging, two new "
            "GitHub-issue alert types (circuit-breaker trip, post-deploy content-"
            "verification mismatch), repurpose S-118 as the manual-override console "
            "for DRIFT_SUSPECTED/IDENTITY_CONFLICT. First live unattended production "
            "cycle requires explicit operator authorization per "
            "MISSION_AUTHORITY.yaml -- not agent-initiated."
        ),
        why_it_matters=(
            "This is the mission's actual closing acceptance boundary: proving the "
            "normal path needs zero human action while every deliberately human-gated "
            "case still correctly escalates."
        ),
        allowed_paths=[".github/workflows/", "reports/package-reconciliation/"],
        forbidden_paths=["content/"],
        dependencies=[
            "PKGINSTALL-DEPLOY-TRIGGER-3LAYER-FIX",
            "PKGINSTALL-PERMANENT-RECONCILIATION-LOOP",
        ],
        acceptance_checks=[
            "One full real week of unattended operation with zero required human "
            "action for the normal path",
            "Correct issue-filing for every deliberately-human-gated case that arises",
            "First live production deploy cycle has an explicit, recorded operator "
            "go-ahead",
        ],
        evidence_refs=[],
        recorded_at=NOW,
        recorded_by=RECORDED_BY,
    ),
]

for card in CARDS:
    store.append(card)
    print(f"appended {card['task_id']} ({card['status']})")

print(f"\ntaskcards.jsonl -> {store.path}")
