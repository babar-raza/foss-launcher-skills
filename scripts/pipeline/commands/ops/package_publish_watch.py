"""package_publish_watch.py — Mission MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-09.
Extended Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-09: this
watcher originally only ever checked `verification.published: false` entries
(the false->true direction) -- meaning once an entry flipped to `published:
true`, nothing ever looked at it again. Two gaps followed directly from that:
(1) if a package were later pulled/renamed/deleted upstream, or a `false-
positive` publish confirmation had been applied in error, this watcher had no
way to ever notice -- drift only in one direction was detectable. (2)
`data/registry_exclusions.json` (the BLOCKED_REPO_NOT_LAUNCHABLE mechanism)
and live launched `content/` were never reconciled by anything running on a
schedule -- `update_product_registry.py`'s `_enforce_exclusions()` only ever
sets a flag on `data/products.json`, never touches `content/`, which is
exactly how `cells/typescript` shipped fabricated content despite being
excluded (see INV-004, backlog/inbox.md). TC-MT018-09 adds both closures:
`check_published_entries_for_drift()` (symmetric counterpart to
`check_unpublished_entries()`, its own debounce counter
`consecutive_checks_absent` so it never shares state with the
publish-confirmation counter) and `check_exclusion_reconciliation()` (thin
wrapper around `registry_coverage_scan.scan_coverage()`'s
`excluded_but_still_live`, reused rather than reimplemented).

Multi-registry sibling of publish_watcher.py (Mission MT008 D-03, Maven-only).
Covers the 5 registries publish_watcher.py deliberately excludes (pypi, nuget,
npm, go_modules, cargo) via the TC-MT015-04/09 adapters in
scripts/pipeline/lib/package_registries/. Maven keeps its own watcher --
maven-metadata.xml presence is a strong single-check signal (the file cannot
exist unless a real release build completed), unlike a bare HTTP 200 from a
generic package-index API, which is why THIS watcher applies the 2-consecutive-
check debounce (apply_debounce, TC-MT015-04) that publish_watcher.py doesn't
need.

Same detection-only discipline as publish_watcher.py: a confirmed publish
(should_flip=True) is reported as a PROPOSAL, never auto-applied to
verification.published. A human reviews the finding (GitHub issue, same
check_upstream_drift.py precedent) before apply_proposal() lands it.

One deliberate, narrower exception to "never mutates": the debounce COUNTER
(verification.consecutive_checks_agreeing) IS persisted automatically by the
scheduled run. This is bookkeeping, not a customer-facing state change -- without
persisting it across runs, the 2-consecutive-check requirement could never be
satisfied by a periodic cron (every run would see counter=0 and start over).
Only the published:true flip itself waits for a human.

When a proposal is confirmed and applied, and the family/platform's content
still contains literal (non-shortcode) install text, this module also reports
whether scripts/pipeline/commands/content/package_install_migrator.py has
eligible work for it (TC-MT015-09's "shared content-healing library" --
factored as a existing, reusable tool rather than new one-off healing code,
since the migrator + verify_package_install_literals audit (TC-MT015-05)
already cover exactly this need). The migrator itself is never invoked
automatically -- same operator-confirmation gate as S-110 Phase B.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.package_publish_watch
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.package_publish_watch --issue-body-out path.md

Exit codes:
    0  no unpublished entry newly confirmed published (nothing to report)
    1  at least one entry now confirmed published (report to stdout / issue body)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from package_registries import apply_debounce, is_corroborated_match, REQUIRED_CONSECUTIVE_CHECKS  # noqa: E402
from package_registries import pypi, nuget, npm, go, cargo  # noqa: E402
from audit.package_install_literal import verify_package_install_literals  # noqa: E402
from commands.ops import registry_coverage_scan  # noqa: E402
from package_registry_data import validate_package_registry, set_content_healing_status  # noqa: E402

DEFAULT_MAX_AUTO_APPLY = 5


def _write_github_output(key: str, value: str) -> None:
    """Best-effort write to $GITHUB_OUTPUT if running inside a GitHub Actions
    step; a no-op (never raises) outside that environment."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_DATA_PATH = _DEFAULT_REPO_ROOT / "data" / "package_registry.json"
DATA_PATH = _DEFAULT_DATA_PATH
_CONTENT_ROOT = _DEFAULT_REPO_ROOT / "content"
_DEFAULT_PRODUCTS_PATH = _DEFAULT_REPO_ROOT / "data" / "products.json"
PRODUCTS_PATH = _DEFAULT_PRODUCTS_PATH

_ADAPTERS: dict[str, Any] = {
    "pypi": pypi,
    "nuget": nuget,
    "npm": npm,
    "go_modules": go,
    "cargo": cargo,
}


def configure(
    *,
    data_path: "Path | str | None" = None,
    content_root: "Path | str | None" = None,
    products_path: "Path | str | None" = None,
) -> None:
    """configure() seam (AGENTS.md 16) -- override DATA_PATH/_CONTENT_ROOT/PRODUCTS_PATH for testing."""
    global DATA_PATH, _CONTENT_ROOT, PRODUCTS_PATH
    DATA_PATH = Path(data_path) if data_path is not None else _DEFAULT_DATA_PATH
    _CONTENT_ROOT = Path(content_root) if content_root is not None else (_DEFAULT_REPO_ROOT / "content")
    PRODUCTS_PATH = Path(products_path) if products_path is not None else _DEFAULT_PRODUCTS_PATH


def _expected_repo_fragment(family: str) -> str:
    """Return the family's known FOSS GitHub org (e.g. "aspose-cells-foss"),
    extracted from data/products.json's repo_url -- the identifying substring
    is_corroborated_match() checks a live registry's project_url against
    (Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2).

    Returns "" if products.json is missing or the family has no entry (e.g.
    under test isolation, or a brand-new family not yet in that file) --
    callers must treat "" as "cannot corroborate by URL for this family", not
    as a wildcard: is_corroborated_match() itself guards against treating an
    empty fragment as matching everything, for exactly this reason."""
    if not PRODUCTS_PATH.is_file():
        return ""
    try:
        products = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    for entry in products:
        if entry.get("family") != family:
            continue
        repo_url = entry.get("repo_url") or ""
        if "github.com" not in repo_url:
            continue
        parts = repo_url.rstrip("/").split("/")
        if len(parts) >= 2:
            return parts[-2]
    return ""


def check_unpublished_entries(
    data: dict[str, Any],
    *,
    adapters: "dict[str, Any] | None" = None,
) -> "tuple[list[dict[str, Any]], list[dict[str, Any]]]":
    """Check every non-Maven, verification.published:false entry via its
    registry adapter. Mutates `data` in place ONLY for the debounce counter
    (see module docstring) -- never for `verification.published` itself.

    Returns (proposals, uncorroborated). Mission
    MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2: once the
    debounce threshold is reached, a SECOND gate applies before a proposal is
    generated -- is_corroborated_match() must confirm the candidate's identity
    (a "foss" substring, or the live result's project_url matching the
    family's known FOSS GitHub org). This is the riskier of the two
    transitions this mission automates (it asserts a brand-new public
    identity), so it gets the tighter gate. A debounce-satisfied hit that
    fails corroboration is never included in `proposals` -- it is returned
    separately in `uncorroborated` so an operator still sees it (plan section
    F: CANDIDATE_UNCORROBORATED is "flagged distinctly for operator
    visibility", not silently dropped) without it being mistaken for a
    normal, ready-to-apply proposal.
    """
    adapters = adapters if adapters is not None else _ADAPTERS
    proposals: list[dict[str, Any]] = []
    uncorroborated: list[dict[str, Any]] = []

    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            registry_type = entry.get("registry_type")
            adapter = adapters.get(registry_type)
            if adapter is None:
                continue  # maven (own watcher) or an unrecognized type
            verification = entry.setdefault("verification", {})
            if verification.get("published"):
                continue

            candidate = entry.get("candidate") or {}
            if not candidate:
                continue

            result = adapter.check_published(candidate)
            current_counter = verification.get("consecutive_checks_agreeing", 0) or 0
            new_counter, should_flip = apply_debounce(current_counter, result)
            verification["consecutive_checks_agreeing"] = new_counter

            if not should_flip:
                continue

            candidate_name = candidate.get("name") or candidate.get("module_path") or ""
            expected_fragment = _expected_repo_fragment(family)
            if not is_corroborated_match(candidate_name, result.project_url, expected_fragment):
                uncorroborated.append({
                    "family": family,
                    "platform": platform,
                    "registry_type": registry_type,
                    "candidate": candidate,
                    "evidence_url": result.evidence_url,
                    "project_url": result.project_url,
                    "reason": (
                        "debounce threshold reached but identity could not be corroborated "
                        "(candidate name has no 'foss' substring and its live project_url does "
                        "not match the family's known FOSS GitHub org) -- needs manual identity "
                        "review before this can be treated as a confirmed publish"
                    ),
                })
                continue

            proposal = {
                "family": family,
                "platform": platform,
                "registry_type": registry_type,
                "candidate": candidate,
                "evidence_url": result.evidence_url,
                "method": result.method,
                "verified_owner": result.verified_owner,
            }
            findings_files = _literal_content_scope(family, platform, entry)
            if findings_files:
                proposal["content_healing_needed"] = True
                proposal["literal_content_files_flagged"] = findings_files
            else:
                proposal["content_healing_needed"] = False
            proposals.append(proposal)

    return proposals, uncorroborated


def apply_drift_debounce(current_consecutive_absent: int, result: Any) -> tuple[int, bool]:
    """Symmetric counterpart to package_registries.apply_debounce, for the
    opposite direction: a currently-published:true entry that no longer
    resolves live. Same fail-closed philosophy -- an ambiguous result never
    advances the counter and never proposes a drift flip (a transient network
    hiccup must never cause a live, working package to be proposed as gone);
    a result that DOES still resolve resets the counter to 0 immediately.
    Uses its own counter (consecutive_checks_absent) so it never shares state
    with the false->true debounce counter (consecutive_checks_agreeing) --
    the two are tracking opposite hypotheses and must not interfere.
    """
    if result.ambiguous:
        return current_consecutive_absent, False
    if result.published:
        return 0, False
    new_counter = current_consecutive_absent + 1
    return new_counter, new_counter >= REQUIRED_CONSECUTIVE_CHECKS


def check_published_entries_for_drift(
    data: dict[str, Any],
    *,
    adapters: "dict[str, Any] | None" = None,
) -> list[dict[str, Any]]:
    """Re-check every non-Maven, verification.published:true entry via its
    registry adapter -- the direction check_unpublished_entries() never
    covers. Mutates `data` in place ONLY for the debounce counter
    (consecutive_checks_absent), exactly mirroring check_unpublished_entries's
    own mutation discipline -- never flips verification.published itself.

    Returns drift proposals for entries whose absence was just confirmed
    across REQUIRED_CONSECUTIVE_CHECKS consecutive runs. A drift proposal is a
    human-review item (the package may have been renamed, pulled, or the
    prior published:true was itself a false positive) -- never auto-applied.
    """
    adapters = adapters if adapters is not None else _ADAPTERS
    drift_proposals: list[dict[str, Any]] = []

    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            registry_type = entry.get("registry_type")
            adapter = adapters.get(registry_type)
            if adapter is None:
                continue  # maven (own watcher) or an unrecognized type
            verification = entry.setdefault("verification", {})
            if not verification.get("published"):
                continue  # only the published:true direction is this function's job

            candidate = entry.get("candidate") or {}
            if not candidate:
                continue

            result = adapter.check_published(candidate)
            current_counter = verification.get("consecutive_checks_absent", 0) or 0
            new_counter, should_flip = apply_drift_debounce(current_counter, result)
            verification["consecutive_checks_absent"] = new_counter

            if not should_flip:
                continue

            drift_proposals.append({
                "family": family,
                "platform": platform,
                "registry_type": registry_type,
                "candidate": candidate,
                "previous_evidence_url": entry.get("verification", {}).get("evidence_url"),
            })

    return drift_proposals


def check_exclusion_reconciliation(
    *,
    scan_fn: "Callable[[], dict[str, Any]] | None" = None,
) -> list[str]:
    """Reconciliation check between data/registry_exclusions.json and live
    launched content -- closes the cells/typescript-style gap where
    _enforce_exclusions() (update_product_registry.py) only ever sets a flag
    on data/products.json and never touches content/. Reuses
    registry_coverage_scan.scan_coverage()'s excluded_but_still_live rather
    than reimplementing the same directory-vs-exclusions cross-reference.

    `scan_fn` is dependency injection (defaults to the real scan_coverage) --
    lets tests exercise this without needing a full repo checkout.
    """
    scan_fn = scan_fn if scan_fn is not None else registry_coverage_scan.scan_coverage
    report = scan_fn()
    return report.get("excluded_but_still_live", [])


def apply_version_debounce(current_counter: int, result: Any, recorded_version: "str | None") -> tuple[int, bool]:
    """Debounce for the steady-state version-update direction (Mission
    MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 2). Deliberately
    its OWN counter semantics, never shared with apply_debounce/
    apply_drift_debounce's counters -- this is tracking a third, independent
    hypothesis ("the live version has moved past what's recorded"), not
    existence.

    An ambiguous result, or a result with no version at all, never advances
    the counter (fail closed, same philosophy as every other check in this
    module). A live version equal to what's already recorded resets the
    counter to 0 (nothing has changed). Only a live version that DIFFERS from
    the recorded one advances the counter, proposing an update once it
    reaches REQUIRED_CONSECUTIVE_CHECKS -- unlike publish_watcher.py's
    Maven-only equivalent (which proposes on a single check, since
    maven-metadata.xml presence is already a strong signal), the other 5
    registries get the same debounce discipline their existence checks
    already use, since a single fetch could reflect a stale CDN edge rather
    than a genuine new release.
    """
    if result.ambiguous or not result.version:
        return current_counter, False
    if result.version == recorded_version:
        return 0, False
    new_counter = current_counter + 1
    return new_counter, new_counter >= REQUIRED_CONSECUTIVE_CHECKS


def check_published_entries_for_version_update(
    data: dict[str, Any],
    *,
    adapters: "dict[str, Any] | None" = None,
) -> list[dict[str, Any]]:
    """Steady-state version-drift detection for the 5 non-Maven registries --
    generalizes publish_watcher.py's Maven-only
    check_published_families_for_new_version() (added by Mission MT036) now
    that every adapter populates CheckResult.version (Phase 1 of this
    mission). Mutates `data` in place ONLY for the new
    consecutive_version_checks_agreeing counter -- never for `candidate`/
    `verification.published` themselves; same mutation discipline as every
    other check_* function in this module.

    A live version that is specifically yanked (currently only crates.io ever
    sets this) is never proposed as an update -- recommending a yanked
    version in install instructions would be actively harmful, not merely
    stale (plan section E: "a yanked version is discouraged, not gone").
    """
    adapters = adapters if adapters is not None else _ADAPTERS
    proposals: list[dict[str, Any]] = []

    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            registry_type = entry.get("registry_type")
            adapter = adapters.get(registry_type)
            if adapter is None:
                continue  # maven (own watcher) or an unrecognized type
            verification = entry.setdefault("verification", {})
            if not verification.get("published"):
                continue  # unpublished entries are check_unpublished_entries's job

            candidate = entry.get("candidate") or {}
            if not candidate:
                continue
            recorded_version = candidate.get("version")

            result = adapter.check_published(candidate)
            if result.yanked:
                continue
            current_counter = verification.get("consecutive_version_checks_agreeing", 0) or 0
            new_counter, should_propose = apply_version_debounce(current_counter, result, recorded_version)
            verification["consecutive_version_checks_agreeing"] = new_counter

            if not should_propose:
                continue

            proposals.append({
                "family": family,
                "platform": platform,
                "registry_type": registry_type,
                "candidate": candidate,
                "recorded_version": recorded_version,
                "live_version": result.version,
                "evidence_url": result.evidence_url,
                "method": result.method,
            })

    return proposals


def apply_version_update_proposal(
    data: dict[str, Any], proposal: dict[str, Any], *, checked_at: "str | None" = None
) -> dict[str, Any]:
    """Mutate `data` in place to reflect a confirmed steady-state version
    update, for the 5 non-Maven registries -- mirrors publish_watcher.py's
    apply_version_update_proposal(). Called automatically by run_auto_apply()
    (Phase 3) when --auto-apply is set; otherwise a human-reviewed follow-up
    action via the issue this module files, same as apply_proposal()."""
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    entry = data[proposal["family"]][proposal["platform"]]
    entry["candidate"] = {**entry.get("candidate", {}), "version": proposal["live_version"]}
    entry["verification"] = {
        **entry.get("verification", {}),
        "published": True,
        "verified_at": checked_at,
        "evidence_url": proposal["evidence_url"],
        "evidence_note": f"package-publish-watch steady-state version-update check, {checked_at}: "
                          f"{proposal['recorded_version']} -> {proposal['live_version']}",
        "method": proposal["method"],
    }
    return entry


def format_version_update_issue_body(proposals: list[dict[str, Any]]) -> str:
    """Issue body for steady-state version-update proposals, mirroring
    publish_watcher.py's format_version_update_issue_body() for the 5
    non-Maven registries."""
    lines = [
        "## FOSS Package(s) With a Newer Version (non-Maven registries)",
        "",
        "The scheduled package-publish-watch found that one or more already-published "
        "FOSS packages now resolve a NEWER version than what's recorded in "
        "`data/package_registry.json`, confirmed across 2 consecutive checks.",
        "",
        "### Action Required",
        "1. Verify each finding below independently before applying it (this issue "
        "is a proposal, not an auto-applied change).",
        "2. Update `data/package_registry.json` for each confirmed family (see "
        "`package_publish_watch.apply_version_update_proposal` for the exact shape).",
        "",
        "### Findings",
        "",
    ]
    for p in proposals:
        lines.append(
            f"- **{p['family']}/{p['platform']}** ({p['registry_type']}): "
            f"recorded `{p['recorded_version']}`, live is `{p['live_version']}` — {p['evidence_url']}"
        )
    return "\n".join(lines)


def format_uncorroborated_body(uncorroborated: list[dict[str, Any]]) -> str:
    """Issue body for debounce-satisfied hits that failed identity
    corroboration (Phase 2) -- kept as its own section, distinct from the
    normal publish-confirmation and drift/reconciliation bodies, since the
    action needed here is different from either: a human must independently
    verify whether the live hit genuinely is the FOSS product before this
    can ever become a normal proposal."""
    if not uncorroborated:
        return ""
    lines = [
        "## Package Identity Needs Manual Review",
        "",
        "The scheduled package-publish-watch found a live registry hit for one or "
        "more currently-unpublished entries, but could not confirm it is genuinely "
        "the FOSS product (no 'foss' substring in the candidate name, and the live "
        "project_url does not match the family's known FOSS GitHub org). This is "
        "NOT a proposal -- it is flagged so a human can investigate the identity "
        "before any further action.",
        "",
        "### Findings",
        "",
    ]
    for u in uncorroborated:
        lines.append(
            f"- **{u['family']}/{u['platform']}** ({u['registry_type']}): candidate "
            f"{u['candidate']!r} resolved at {u['evidence_url']} (project_url: "
            f"{u.get('project_url')!r}) — {u['reason']}"
        )
    return "\n".join(lines)


def format_drift_and_reconciliation_body(
    drift_proposals: list[dict[str, Any]],
    excluded_but_still_live: list[str],
) -> str:
    """Second issue-body formatter, kept separate from format_issue_body()
    (the original false->true proposal report) since these are a different
    audience/action (drift needs re-verification, not a registry flip;
    reconciliation needs either content removal or an exclusions update) --
    combining all three into one wall of text would bury the distinct
    actions needed under one another."""
    lines = [
        "## Package Registry Drift / Exclusion Reconciliation",
        "",
    ]
    if drift_proposals:
        lines += [
            "### Previously-published entries that no longer resolve",
            "",
            "Each of these was `verification.published: true` but has now failed "
            f"{REQUIRED_CONSECUTIVE_CHECKS} consecutive live checks. Investigate "
            "before flipping back to `published: false` -- this could be a genuine "
            "removal/rename upstream, or a transient adapter/registry-API issue.",
            "",
        ]
        for p in drift_proposals:
            lines.append(
                f"- **{p['family']}/{p['platform']}** ({p['registry_type']}): "
                f"candidate {p['candidate']!r} no longer resolves "
                f"(previously verified via {p.get('previous_evidence_url')})"
            )
        lines.append("")
    if excluded_but_still_live:
        lines += [
            "### Excluded products with live content",
            "",
            "Each of these is flagged in `data/registry_exclusions.json` (not "
            "launchable) but still has live content under `content/`. Either the "
            "exclusion is stale (repo was fixed upstream -- re-verify and remove "
            "the exclusion) or the content needs to be retired/corrected.",
            "",
        ]
        for pair in excluded_but_still_live:
            lines.append(f"- **{pair}**")
        lines.append("")
    return "\n".join(lines)


def _literal_content_scope(family: str, platform: str, entry: dict[str, Any]) -> int:
    """Best-effort count of how many real content files still carry literal
    (non-shortcode) install text for this family/platform, via the same
    audit function package_install_literal.py uses (TC-MT015-05). Returns 0
    if the content root doesn't exist in this environment (e.g. under test)
    rather than raising -- this is an informational hint for the proposal,
    not a hard dependency of the detection logic above."""
    if not _CONTENT_ROOT.is_dir():
        return 0
    registry_snapshot = {family: {platform: entry}}
    count = 0
    for site in ("docs.aspose.org", "blog.aspose.org", "kb.aspose.org", "products.aspose.org"):
        base = _CONTENT_ROOT / site
        if not base.is_dir():
            continue
        candidates = base.rglob("*.md")
        for fp in candidates:
            parts = fp.parts
            if family not in parts or platform not in parts:
                continue
            if verify_package_install_literals(fp, family, platform, registry=registry_snapshot):
                count += 1
    return count


def apply_proposal(data: dict[str, Any], proposal: dict[str, Any], *, checked_at: "str | None" = None) -> dict[str, Any]:
    """Mutate `data` in place to reflect a confirmed proposal. Called
    automatically by run_auto_apply() (Phase 3) when --auto-apply is set;
    otherwise the pure state-transition function for the human-reviewed
    follow-up via the issue this module files, mirroring publish_watcher.py's
    apply_proposal()."""
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    entry = data[proposal["family"]][proposal["platform"]]
    entry["candidate"] = proposal["candidate"]
    entry["verification"] = {
        **entry.get("verification", {}),
        "published": True,
        "verified_at": checked_at,
        "verified_owner": proposal.get("verified_owner"),
        "evidence_url": proposal["evidence_url"],
        "evidence_note": f"package-publish-watch live check confirmed via {proposal['method']}, {checked_at}",
        "method": proposal["method"],
    }
    # Durable remediation-state tracking (2026-09-07, watcher-fleet reliability
    # hardening, Phase 3): the registry previously recorded only DETECTION state
    # (published True/False) -- the moment a proposal was applied, whether content
    # healing was still owed existed only as prose in the triggering GitHub issue,
    # which is exactly why 3d/python's 392-file/509-mention content healing sat
    # untracked after its own registry flip (confirmed live 2026-09-02 -> still
    # pending 2026-09-07 with zero durable record of that fact anywhere but a
    # closed issue's comment). Setting this here, in the same atomic write as the
    # publish-state flip, means the two can never diverge silently again.
    # PKGINSTALL-CONTENT-HEALING-STATUS-WRITEBACK (2026-09-10): factored into
    # the shared set_content_healing_status() helper (package_registry_data.py)
    # so this writer and reconcile_content_healing_status.py's pending->healed
    # transition can never diverge on field shape -- behavior unchanged.
    set_content_healing_status(
        entry,
        "pending" if proposal.get("content_healing_needed") else "not_needed",
        checked_at=checked_at,
        reason=f"package-publish-watch proposal applied, content_healing_needed={proposal.get('content_healing_needed')!r}",
    )
    return entry


def format_issue_body(proposals: list[dict[str, Any]]) -> str:
    lines = [
        "## FOSS Package(s) Now Live (non-Maven registries)",
        "",
        "The scheduled package-publish-watch found that one or more FOSS packages "
        "previously marked `verification.published: false` in `data/package_registry.json` "
        "now resolve live, confirmed across 2 consecutive checks.",
        "",
        "### Action Required",
        "1. Verify each finding below independently before applying it (this issue "
        "is a proposal, not an auto-applied change).",
        "2. Update `data/package_registry.json` for each confirmed family (see "
        "`package_publish_watch.apply_proposal` for the exact shape).",
        "3. If `content_healing_needed` is true, run "
        "`package_install_migrator.py {family} {platform} --dry-run` first, review, then "
        "`--execute` (operator confirmation required, same gate as S-110 Phase B) -- "
        "families already using the package-install/cargo-crate/maven-coord shortcode "
        "need no content edit at all; the registry flip alone fixes their rendered output.",
        "4. Run the full test suite before committing.",
        "",
        "### Findings",
        "",
    ]
    for p in proposals:
        healing = (
            f"— content healing needed, {p['literal_content_files_flagged']} file(s) flagged"
            if p.get("content_healing_needed") else "— no literal content healing needed (shortcode-only or none flagged)"
        )
        lines.append(
            f"- **{p['family']}/{p['platform']}** ({p['registry_type']}): "
            f"{p['evidence_url']} {healing}"
        )
    return "\n".join(lines)


def run_watch(
    *, adapters: "dict[str, Any] | None" = None,
) -> "tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]":
    """Load DATA_PATH, run every check direction this module owns, return
    (proposals, uncorroborated, version_proposals, drift_proposals,
    updated_data). The caller is responsible for persisting updated_data's
    debounce counters (see module docstring) -- this function itself does
    not write to disk, matching publish_watcher.py's I/O separation and
    keeping this function trivially testable.

    All checks mutate the SAME `data` dict (different counter fields, see
    each check_* function's own docstring) so a single persisted write covers
    every direction's bookkeeping.

    `adapters` is dependency injection (defaults to the real _ADAPTERS) --
    lets tests exercise main()'s full wiring with fake, network-free adapters
    instead of monkeypatching run_watch/check_unpublished_entries themselves
    (this mission's established DI-over-monkeypatch convention, AGENTS.md 16)."""
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    proposals, uncorroborated = check_unpublished_entries(data, adapters=adapters)
    version_proposals = check_published_entries_for_version_update(data, adapters=adapters)
    drift_proposals = check_published_entries_for_drift(data, adapters=adapters)
    return proposals, uncorroborated, version_proposals, drift_proposals, data


def run_auto_apply(
    *, adapters: "dict[str, Any] | None" = None, max_apply: int = DEFAULT_MAX_AUTO_APPLY,
    scan_fn: "Callable[[], dict[str, Any]] | None" = None,
) -> dict[str, Any]:
    """Detect and apply eligible proposals for the 5 non-Maven registries
    (Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 3),
    against a single in-memory copy of the registry, then atomically write it.

    Only two of the five check directions are ever eligible for auto-apply:
    `proposals` (from check_unpublished_entries -- already gated by both
    debounce AND identity corroboration) and `version_proposals` (from
    check_published_entries_for_version_update). The other three --
    `uncorroborated`, `drift_proposals`, and `excluded_but_still_live` -- are
    NEVER auto-applied regardless of this flag, matching the plan's explicit,
    already-justified safety design ("never auto-flip published back to
    false", and an uncorroborated identity always needs a human). They are
    always returned for the caller to report via the existing issue-filing
    path, unchanged.

    Debounce/version counters are persisted as part of the SAME atomic write
    as any applied proposal (superseding --no-persist-counters, which has no
    meaning once --auto-apply's own validate-then-write discipline governs
    what gets persisted) -- this mirrors Maven's run_auto_apply() exactly.
    """
    adapters = adapters if adapters is not None else _ADAPTERS
    original_bytes = DATA_PATH.read_text(encoding="utf-8")
    original_data = json.loads(original_bytes)
    data = json.loads(original_bytes)

    proposals, uncorroborated = check_unpublished_entries(data, adapters=adapters)
    version_proposals = check_published_entries_for_version_update(data, adapters=adapters)
    drift_proposals = check_published_entries_for_drift(data, adapters=adapters)
    excluded_but_still_live = check_exclusion_reconciliation(scan_fn=scan_fn)

    tagged = [("publish", p) for p in proposals] + [("version", p) for p in version_proposals]
    applied: list[dict[str, Any]] = []
    skipped_capped: list[dict[str, Any]] = []
    for kind, proposal in tagged:
        if len(applied) >= max_apply:
            skipped_capped.append(proposal)
            continue
        if kind == "publish":
            apply_proposal(data, proposal)
        else:
            apply_version_update_proposal(data, proposal)
        applied.append(proposal)

    result: dict[str, Any] = {
        "applied": applied,
        "skipped_capped": skipped_capped,
        "proposals": proposals,
        "uncorroborated": uncorroborated,
        "version_proposals": version_proposals,
        "drift_proposals": drift_proposals,
        "excluded_but_still_live": excluded_but_still_live,
        "wrote_changes": False,
        "validation_errors": [],
    }

    # Even with nothing applied, the debounce-counter mutations above (from all
    # four check_* calls) still need persisting -- same as the non-auto-apply
    # default (persist-counters) path. Validate-then-write covers this too.
    errors = validate_package_registry(data)
    if errors:
        result["applied"] = []
        result["validation_errors"] = errors
        return result

    if data == original_data:
        # Structural (parsed) comparison, deliberately not a raw-bytes compare:
        # the on-disk file's existing formatting is not guaranteed to match
        # json.dumps(..., indent=2)'s exact output (key order aside, dict
        # equality ignores it; whitespace/newline conventions do not survive a
        # byte compare) -- a byte-level check would report "changed" for a
        # purely cosmetic reformatting with zero semantic difference, causing a
        # spurious commit. Real content equality is what actually matters here.
        return result
    new_bytes = json.dumps(data, indent=2) + "\n"

    tmp_path = DATA_PATH.with_name(DATA_PATH.name + ".tmp")
    tmp_path.write_text(new_bytes, encoding="utf-8")
    reparsed = json.loads(tmp_path.read_text(encoding="utf-8"))
    reparse_errors = validate_package_registry(reparsed)
    if reparse_errors:
        tmp_path.unlink(missing_ok=True)
        result["applied"] = []
        result["validation_errors"] = reparse_errors
        return result
    os.replace(tmp_path, DATA_PATH)
    final_errors = validate_package_registry(json.loads(DATA_PATH.read_text(encoding="utf-8")))
    if final_errors:
        result["applied"] = []
        result["validation_errors"] = final_errors
        return result

    result["wrote_changes"] = True
    return result


def main(
    argv: "list[str] | None" = None, *, adapters: "dict[str, Any] | None" = None,
    scan_fn: "Callable[[], dict[str, Any]] | None" = None,
) -> int:
    """`adapters`/`scan_fn` are not CLI flags (objects can't cross the command
    line) -- test-only injection points mirroring run_watch's own `adapters`
    parameter, so CLI-wiring tests never need to monkeypatch run_watch or hit
    a live network call to exercise main()'s persist/no-persist/exit-code
    branches."""
    import argparse

    parser = argparse.ArgumentParser(prog="package_publish_watch")
    parser.add_argument("--issue-body-out", metavar="PATH", help="Write the GitHub issue body to this path if any proposals are found")
    parser.add_argument("--no-persist-counters", action="store_true",
                         help="Skip writing updated debounce counters back to DATA_PATH (dry-run/test use)")
    parser.add_argument("--auto-apply", action="store_true",
                         help="Apply eligible publish/version-update proposals and atomically write "
                              "data/package_registry.json instead of only reporting them (Mission "
                              "MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 3). Identity-"
                              "uncorroborated findings, drift, and exclusion reconciliation are NEVER "
                              "auto-applied regardless of this flag -- always issue-only. Supersedes "
                              "--no-persist-counters (counters persist as part of the same atomic write).")
    parser.add_argument("--max-auto-apply", type=int, default=DEFAULT_MAX_AUTO_APPLY, metavar="N",
                         help=f"Registry-level circuit breaker: at most N proposals applied per run (default {DEFAULT_MAX_AUTO_APPLY})")
    args = parser.parse_args(argv)

    if args.auto_apply:
        result = run_auto_apply(adapters=adapters, max_apply=args.max_auto_apply, scan_fn=scan_fn)
        _write_github_output("wrote_changes", "true" if result["wrote_changes"] else "false")

        if result["validation_errors"]:
            print("package_publish_watch --auto-apply: validation FAILED after applying proposals -- "
                  "the entire write was aborted, data/package_registry.json is untouched.")
            for err in result["validation_errors"]:
                print(f"  - {err}")
            return 1

        applied_keys = {(p["family"], p["platform"]) for p in result["applied"]}
        remaining_proposals = [p for p in result["proposals"] if (p["family"], p["platform"]) not in applied_keys]
        remaining_version = [p for p in result["version_proposals"] if (p["family"], p["platform"]) not in applied_keys]

        if result["applied"]:
            print(f"package_publish_watch --auto-apply: applied {len(result['applied'])} proposal(s); "
                  f"wrote_changes={result['wrote_changes']}")
        if result["skipped_capped"]:
            print(f"package_publish_watch --auto-apply: circuit breaker reached -- "
                  f"{len(result['skipped_capped'])} proposal(s) deferred to issue-filing below")

        bodies = []
        if remaining_proposals:
            bodies.append(format_issue_body(remaining_proposals))
        if remaining_version:
            bodies.append(format_version_update_issue_body(remaining_version))
        if result["uncorroborated"]:
            bodies.append(format_uncorroborated_body(result["uncorroborated"]))
        if result["drift_proposals"] or result["excluded_but_still_live"]:
            bodies.append(format_drift_and_reconciliation_body(result["drift_proposals"], result["excluded_but_still_live"]))

        if bodies:
            body = "\n\n".join(bodies)
            print(body)
            if args.issue_body_out:
                Path(args.issue_body_out).write_text(body, encoding="utf-8")
            return 1

        if result["applied"]:
            return 1  # applied changes are still worth surfacing in workflow logs/exit code

        print("package_publish_watch: no unpublished entry resolves live (with debounce satisfied) yet, "
              "no already-published entry has a newer live version, no unconfirmed identity findings, "
              "no published entry has drifted away, no exclusion/content reconciliation findings. "
              "Nothing to report.")
        return 0

    proposals, uncorroborated, version_proposals, drift_proposals, updated_data = run_watch(adapters=adapters)
    excluded_but_still_live = check_exclusion_reconciliation(scan_fn=scan_fn)

    if not args.no_persist_counters:
        DATA_PATH.write_text(json.dumps(updated_data, indent=2) + "\n", encoding="utf-8")

    bodies = []
    if proposals:
        bodies.append(format_issue_body(proposals))
    if version_proposals:
        bodies.append(format_version_update_issue_body(version_proposals))
    if uncorroborated:
        bodies.append(format_uncorroborated_body(uncorroborated))
    if drift_proposals or excluded_but_still_live:
        bodies.append(format_drift_and_reconciliation_body(drift_proposals, excluded_but_still_live))

    if not bodies:
        print("package_publish_watch: no unpublished entry resolves live (with debounce satisfied) yet, "
              "no already-published entry has a newer live version, no unconfirmed identity findings, "
              "no published entry has drifted away, no exclusion/content reconciliation findings. "
              "Nothing to report.")
        return 0

    body = "\n\n".join(bodies)
    print(body)
    if args.issue_body_out:
        Path(args.issue_body_out).write_text(body, encoding="utf-8")

    return 1


if __name__ == "__main__":
    sys.exit(main())
