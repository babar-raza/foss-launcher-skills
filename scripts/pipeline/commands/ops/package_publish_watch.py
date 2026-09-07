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

from package_registries import apply_debounce, REQUIRED_CONSECUTIVE_CHECKS  # noqa: E402
from package_registries import pypi, nuget, npm, go, cargo  # noqa: E402
from audit.package_install_literal import verify_package_install_literals  # noqa: E402
from commands.ops import registry_coverage_scan  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_DATA_PATH = _DEFAULT_REPO_ROOT / "data" / "package_registry.json"
DATA_PATH = _DEFAULT_DATA_PATH
_CONTENT_ROOT = _DEFAULT_REPO_ROOT / "content"

_ADAPTERS: dict[str, Any] = {
    "pypi": pypi,
    "nuget": nuget,
    "npm": npm,
    "go_modules": go,
    "cargo": cargo,
}


def configure(*, data_path: "Path | str | None" = None, content_root: "Path | str | None" = None) -> None:
    """configure() seam (AGENTS.md 16) -- override DATA_PATH/_CONTENT_ROOT for testing."""
    global DATA_PATH, _CONTENT_ROOT
    DATA_PATH = Path(data_path) if data_path is not None else _DEFAULT_DATA_PATH
    _CONTENT_ROOT = Path(content_root) if content_root is not None else (_DEFAULT_REPO_ROOT / "content")


def check_unpublished_entries(
    data: dict[str, Any],
    *,
    adapters: "dict[str, Any] | None" = None,
) -> list[dict[str, Any]]:
    """Check every non-Maven, verification.published:false entry via its
    registry adapter. Mutates `data` in place ONLY for the debounce counter
    (see module docstring) -- never for `verification.published` itself.

    Returns proposals for entries whose debounce threshold was just reached
    this run (should_flip=True). A proposal is a human-review item, not an
    applied change.
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

    return proposals


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
    """Mutate `data` in place to reflect a confirmed proposal. NOT called by
    the automatic scheduled run -- the pure state-transition function for the
    human-reviewed follow-up, mirroring publish_watcher.py's apply_proposal()."""
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
    entry["content_healing_status"] = (
        "pending" if proposal.get("content_healing_needed") else "not_needed"
    )
    entry["content_healing_status_set_at"] = checked_at
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Load DATA_PATH, check every unpublished non-Maven entry (false->true
    direction) AND every published non-Maven entry (true->false drift
    direction, TC-MT018-09), return (proposals, drift_proposals,
    updated_data). The caller is responsible for persisting updated_data's
    debounce counters (see module docstring) -- this function itself does
    not write to disk, matching publish_watcher.py's I/O separation and
    keeping this function trivially testable.

    Both checks mutate the SAME `data` dict (different counter fields, see
    check_unpublished_entries/check_published_entries_for_drift docstrings)
    so a single persisted write covers both directions' bookkeeping.

    `adapters` is dependency injection (defaults to the real _ADAPTERS) --
    lets tests exercise main()'s full wiring with fake, network-free adapters
    instead of monkeypatching run_watch/check_unpublished_entries themselves
    (this mission's established DI-over-monkeypatch convention, AGENTS.md 16)."""
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    proposals = check_unpublished_entries(data, adapters=adapters)
    drift_proposals = check_published_entries_for_drift(data, adapters=adapters)
    return proposals, drift_proposals, data


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
    args = parser.parse_args(argv)

    proposals, drift_proposals, updated_data = run_watch(adapters=adapters)
    excluded_but_still_live = check_exclusion_reconciliation(scan_fn=scan_fn)

    if not args.no_persist_counters:
        DATA_PATH.write_text(json.dumps(updated_data, indent=2) + "\n", encoding="utf-8")

    bodies = []
    if proposals:
        bodies.append(format_issue_body(proposals))
    if drift_proposals or excluded_but_still_live:
        bodies.append(format_drift_and_reconciliation_body(drift_proposals, excluded_but_still_live))

    if not bodies:
        print("package_publish_watch: no unpublished entry resolves live (with debounce satisfied) yet, "
              "no published entry has drifted away, no exclusion/content reconciliation findings. Nothing to report.")
        return 0

    body = "\n\n".join(bodies)
    print(body)
    if args.issue_body_out:
        Path(args.issue_body_out).write_text(body, encoding="utf-8")

    return 1


if __name__ == "__main__":
    sys.exit(main())
