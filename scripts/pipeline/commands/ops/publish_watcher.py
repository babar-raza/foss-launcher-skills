"""publish_watcher.py — Mission MT008 (plans/master-plan.md) D-03.

For every Maven-registry family/platform in data/package_registry.json with
verification.published:false, independently verifies whether the candidate
coordinate is now live on Maven Central -- never inferred from a green
release-workflow exit code (this repo's own history documents a workflow that
can report success while the artifact silently sits in "Pending Validation":
the waitUtil/waitUntil typo, see .claude/commands/foss-java-publish.md).

MT036 update (2026-08-21, PDF/Java Maven publish hardening, gap G3): also
checks the steady-state case -- every already-published Maven entry, for a
LIVE version newer than what's recorded. The original design above only ever
fired once per family, on the unpublished-to-published transition; it silently
stopped watching a family the moment it flipped to published:true, so no
subsequent release of an already-published product (the normal, recurring
case going forward) was ever detected. See
check_published_families_for_new_version() below.

This closes Finding F-05: S-110 (foss-java-publish)'s content-healing phase is
manually triggered and was never run for 2 of 4 families. This script replaces
"someone must remember" with a scheduled check (see .github/workflows/maven-publish-watcher.yml).

Design note: does NOT auto-commit a state flip to data/package_registry.json, and
does NOT open a pull request. It detects and reports only -- a human reviews the
finding (via a GitHub issue, following this repo's existing scripts/ci/checks/check_upstream_drift.py
+ .github/workflows/upstream-monitor.yml precedent) before the data file is ever
touched. This is a deliberate adaptation of the mission plan's original "opens a PR"
design: an issue requires zero git/branch/commit operations (strictly lower blast
radius than a PR) while preserving the same human-review-before-landing guarantee,
and matches this repo's own proven, already-working pattern instead of introducing a
new one.

MT015 update (2026-08-01): repointed from the retired data/foss_packages.json
(Maven-only) to the unified data/package_registry.json (Mission
MT015-2026-07-30-PACKAGE-REGISTRY) -- filters on registry_type=="maven" so this
module's Maven-Central-specific live-check logic (maven-metadata.xml, not a
generic JSON API) only ever runs against Maven entries in the now-shared file.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.publish_watcher
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.publish_watcher --issue-body-out path.md

Exit codes:
    0  no unpublished family resolved live (nothing to report)
    1  at least one unpublished family now resolves live (report to stdout / issue body)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from package_registry_data import validate_package_registry  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_DATA_PATH = _DEFAULT_REPO_ROOT / "data" / "package_registry.json"
DATA_PATH = _DEFAULT_DATA_PATH
_LIVE_CHECKER: "Callable[[str, str], str | None] | None" = None

DEFAULT_MAX_AUTO_APPLY = 5


def _write_github_output(key: str, value: str) -> None:
    """Best-effort write to $GITHUB_OUTPUT if running inside a GitHub Actions
    step; a no-op (never raises) outside that environment, e.g. under pytest
    or a local manual run."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def configure(
    *,
    data_path: "Path | str | None" = None,
    live_checker: "Callable[[str, str], str | None] | None" = None,
) -> None:
    """Override module-level constants for testing (configure() seam, AGENTS.md 16 --
    used instead of monkeypatch.setattr on module functions directly)."""
    global DATA_PATH, _LIVE_CHECKER
    DATA_PATH = Path(data_path) if data_path is not None else _DEFAULT_DATA_PATH
    _LIVE_CHECKER = live_checker


def default_live_checker(group_id: str, artifact_id: str) -> "str | None":
    """Query Maven Central's maven-metadata.xml directly for group_id/artifact_id.

    Returns the live release version string if the artifact resolves, or None on
    any failure (network error, 404, malformed XML). Never raises -- a checker
    failure must never be mistaken for "confirmed unpublished"; callers treat
    None as "could not confirm this run", not as a negative result to act on.
    """
    group_path = group_id.replace(".", "/")
    url = f"https://repo1.maven.org/maven2/{group_path}/{artifact_id}/maven-metadata.xml"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; aspose-org-publish-watcher/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError):
        return None
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return None
    return root.findtext("versioning/release") or root.findtext("versioning/latest")


def check_unpublished_families(
    data: dict[str, Any],
    live_checker: Callable[[str, str], "str | None"] = default_live_checker,
) -> list[dict[str, Any]]:
    """Return proposed state flips for every Maven-registry, verification.published:false
    entry whose candidate coordinate now resolves live on Maven Central.

    Pure detection -- never mutates `data`. INV-02 (plans/master-plan.md): the only
    signal that can produce a proposal is `live_checker`'s own return value, never a
    workflow exit code or any other indirect signal.
    """
    proposals: list[dict[str, Any]] = []
    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            if entry.get("registry_type") != "maven":
                continue
            if entry.get("verification", {}).get("published"):
                continue
            candidate = entry.get("candidate") or {}
            group_id, artifact_id = candidate.get("group_id"), candidate.get("artifact_id")
            if not group_id or not artifact_id:
                continue
            live_version = live_checker(group_id, artifact_id)
            if live_version:
                proposals.append({
                    "family": family,
                    "platform": platform,
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": live_version,
                    "central_url": f"https://repo1.maven.org/maven2/{group_id.replace('.', '/')}/{artifact_id}/",
                })
    return proposals


def check_published_families_for_new_version(
    data: dict[str, Any],
    live_checker: Callable[[str, str], "str | None"] = default_live_checker,
) -> list[dict[str, Any]]:
    """Return proposed version updates for every Maven-registry, verification.published:true
    entry whose live Maven Central version differs from the recorded candidate.version.

    Added MT036-2026-08-21 (PDF/Java Maven publish hardening, gap G3): closes a real,
    confirmed gap -- check_unpublished_families() above only ever fires once, on the
    unpublished-to-published transition (it explicitly `continue`s past any entry
    already marked verification.published:true). Once a family flips to published, it
    was never re-checked again by anything in this pipeline -- no detection of a
    SUBSEQUENT version landing on Central (a real, recurring case: every future
    release of an already-published product, e.g. pdf/java going from 26.6.0 to
    26.8.0), and no re-confirmation that the recorded version is still accurate.

    This function is the steady-state counterpart: for every already-published Maven
    entry, re-query Central and flag a proposal only when the live version differs
    from what's recorded. Pure detection, same INV-02 discipline as
    check_unpublished_families -- never mutates `data`, never trusts a workflow exit
    code, only ever acts on live_checker's own return value.
    """
    proposals: list[dict[str, Any]] = []
    for family, platforms in data.items():
        if family.startswith("_"):
            continue
        for platform, entry in platforms.items():
            if entry.get("registry_type") != "maven":
                continue
            if not entry.get("verification", {}).get("published"):
                continue  # unpublished entries are check_unpublished_families()'s job
            candidate = entry.get("candidate") or {}
            group_id, artifact_id = candidate.get("group_id"), candidate.get("artifact_id")
            recorded_version = candidate.get("version")
            if not group_id or not artifact_id:
                continue
            live_version = live_checker(group_id, artifact_id)
            if live_version and live_version != recorded_version:
                proposals.append({
                    "family": family,
                    "platform": platform,
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "recorded_version": recorded_version,
                    "live_version": live_version,
                    "central_url": f"https://repo1.maven.org/maven2/{group_id.replace('.', '/')}/{artifact_id}/",
                })
    return proposals


def apply_version_update_proposal(
    data: dict[str, Any], proposal: dict[str, Any], *, checked_at: "str | None" = None
) -> dict[str, Any]:
    """Mutate `data` in place to reflect a confirmed version-update proposal.

    Distinct from apply_proposal() (which flips published:false -> true) --
    this updates candidate.version on an ALREADY-published entry. Called
    automatically by run_auto_apply() (Phase 3) when --auto-apply is set;
    otherwise a human-reviewed follow-up action, same as apply_proposal().
    """
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    entry = data[proposal["family"]][proposal["platform"]]
    entry["candidate"] = {**entry.get("candidate", {}), "version": proposal["live_version"]}
    entry["verification"] = {
        **entry.get("verification", {}),
        "published": True,
        "verified_at": checked_at,
        "evidence_url": proposal["central_url"],
        "evidence_note": f"publish-watcher steady-state version-update check, {checked_at}: "
                          f"{proposal['recorded_version']} -> {proposal['live_version']}",
        "method": "maven-central-poll-version-update",
    }
    return entry


def format_version_update_issue_body(proposals: list[dict[str, Any]]) -> str:
    """Build the GitHub issue body for a batch of steady-state version-update
    proposals (an already-published family's live version moved past what's
    recorded), mirroring format_issue_body()'s structure for the sibling
    unpublished-to-published case."""
    lines = [
        "## Java-FOSS Package(s) With a Newer Version on Maven Central",
        "",
        "The scheduled publish-watcher found that one or more already-published "
        "Java-FOSS packages now resolve a NEWER version on Maven Central than what's "
        "recorded in `data/package_registry.json`. This means a release happened "
        "that this pipeline's own records haven't caught up to.",
        "",
        "### Action Required",
        "1. Verify each finding below independently before applying it (this issue "
        "is a proposal, not an auto-applied change).",
        "2. If this release went through `/foss-java-publish --mode=republish` for "
        "real, the recorded version should already match — a mismatch here likely "
        "means a publish happened outside the governed pipeline; investigate before "
        "updating the record.",
        "3. Update `data/package_registry.json` for each confirmed family (see "
        "`publish_watcher.apply_version_update_proposal` for the exact shape).",
        "4. Re-run `/knowledge-diff {family} java` to reconcile `knowledge/` with the "
        "newly-confirmed version.",
        "",
        "### Findings",
        "",
    ]
    for p in proposals:
        lines.append(
            f"- **{p['family']}/{p['platform']}**: `{p['group_id']}:{p['artifact_id']}` "
            f"recorded `{p['recorded_version']}`, live is `{p['live_version']}` — {p['central_url']}"
        )
    return "\n".join(lines)


def apply_proposal(data: dict[str, Any], proposal: dict[str, Any], *, checked_at: "str | None" = None) -> dict[str, Any]:
    """Mutate `data` in place to reflect a confirmed proposal.

    Called automatically by run_auto_apply() (Mission
    MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 3) when
    --auto-apply is set; otherwise the pure state-transition function used by
    tests and by a human-reviewed follow-up action after reading the issue
    this module's CLI helps generate.
    """
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    entry = data[proposal["family"]][proposal["platform"]]
    entry["candidate"] = {
        "group_id": proposal["group_id"],
        "artifact_id": proposal["artifact_id"],
        "version": proposal["version"],
    }
    entry["verification"] = {
        **entry.get("verification", {}),
        "published": True,
        "verified_at": checked_at,
        "evidence_url": proposal["central_url"],
        "evidence_note": f"publish-watcher live check, {checked_at}",
        "method": "maven-central-poll",
    }
    return entry


def format_issue_body(proposals: list[dict[str, Any]]) -> str:
    """Build the GitHub issue body for a batch of proposals, following the
    check_upstream_drift.py / upstream-monitor.yml precedent (actionable next
    steps, not just a raw dump)."""
    lines = [
        "## Java-FOSS Package(s) Now Live on Maven Central",
        "",
        "The scheduled publish-watcher found that one or more Java-FOSS packages "
        "previously marked `verification.published: false` in `data/package_registry.json` "
        "now resolve live on Maven Central.",
        "",
        "### Action Required",
        "1. Verify each finding below independently before applying it (this issue "
        "is a proposal, not an auto-applied change).",
        "2. Update `data/package_registry.json` for each confirmed family (see "
        "`publish_watcher.apply_proposal` for the exact shape).",
        "3. Re-run `/repo-scout {family} java` and `/truth-merge {family} java` to "
        "reconcile `knowledge/` with the newly-confirmed coordinate.",
        "4. Run the full test suite (`scripts/pipeline/tests/test_package_registry_data.py` "
        "at minimum) before committing.",
        "",
        "### Findings",
        "",
    ]
    for p in proposals:
        lines.append(
            f"- **{p['family']}/{p['platform']}**: `{p['group_id']}:{p['artifact_id']}:{p['version']}` "
            f"— {p['central_url']}"
        )
    return "\n".join(lines)


def run_watch(*, live_checker: "Callable[[str, str], str | None] | None" = None) -> list[dict[str, Any]]:
    """Load DATA_PATH, check every unpublished entry, return proposals (if any).

    Does not write anything -- see module docstring for why the automatic path
    never mutates data/package_registry.json directly.

    `live_checker` defaults to None and is resolved INSIDE the function body
    (not as a bound default parameter value), falling back to a `configure()`-
    injected checker and then to the module-level `default_live_checker` --
    a bound default would silently keep referencing the original function
    object regardless of `configure()`, confirmed as a real gotcha while
    testing this module.
    """
    checker = live_checker if live_checker is not None else (_LIVE_CHECKER or default_live_checker)
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return check_unpublished_families(data, checker)


def run_version_watch(*, live_checker: "Callable[[str, str], str | None] | None" = None) -> list[dict[str, Any]]:
    """Load DATA_PATH, check every already-published entry for a newer live
    version, return proposals (if any). Sibling of run_watch() for the
    steady-state case (added MT036 -- see check_published_families_for_new_version)."""
    checker = live_checker if live_checker is not None else (_LIVE_CHECKER or default_live_checker)
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return check_published_families_for_new_version(data, checker)


def run_auto_apply(
    *, live_checker: "Callable[[str, str], str | None] | None" = None,
    max_apply: int = DEFAULT_MAX_AUTO_APPLY,
) -> dict[str, Any]:
    """Detect and apply eligible Maven proposals (Mission
    MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 3) against a SINGLE
    in-memory copy of the registry, then atomically write it -- never partially.

    Both check_unpublished_families() and check_published_families_for_new_version()
    are run against the same `data` object (both are pure/non-mutating, so this
    is safe) so their proposals can be applied together and validated as one
    whole-file change, rather than two separate reads/writes racing each other.

    Registry-level circuit breaker: at most `max_apply` proposals (across BOTH
    kinds combined) are applied in one run -- a guard against a systemic
    adapter bug flipping many entries at once. Proposals beyond the cap are
    returned in `skipped_capped`, unapplied, for the caller to report via the
    existing issue-filing path (unchanged behavior for the overflow).

    Returns a result dict (never raises for an ordinary detection/validation
    outcome):
        applied            -- proposals actually applied this run
        skipped_capped     -- proposals found but not applied (circuit breaker)
        unpublished_proposals / version_proposals -- full raw detection output
        wrote_changes      -- True only if data/package_registry.json was
                               actually rewritten on disk
        validation_errors  -- non-empty only if validation aborted the ENTIRE
                               write (nothing was persisted in that case)
    """
    checker = live_checker if live_checker is not None else (_LIVE_CHECKER or default_live_checker)
    original_bytes = DATA_PATH.read_text(encoding="utf-8")
    original_data = json.loads(original_bytes)
    data = json.loads(original_bytes)

    unpublished_proposals = check_unpublished_families(data, checker)
    version_proposals = check_published_families_for_new_version(data, checker)

    tagged = [("unpublished", p) for p in unpublished_proposals] + [("version", p) for p in version_proposals]
    applied: list[dict[str, Any]] = []
    skipped_capped: list[dict[str, Any]] = []
    for kind, proposal in tagged:
        if len(applied) >= max_apply:
            skipped_capped.append(proposal)
            continue
        if kind == "unpublished":
            apply_proposal(data, proposal)
        else:
            apply_version_update_proposal(data, proposal)
        applied.append(proposal)

    result: dict[str, Any] = {
        "applied": applied,
        "skipped_capped": skipped_capped,
        "unpublished_proposals": unpublished_proposals,
        "version_proposals": version_proposals,
        "wrote_changes": False,
        "validation_errors": [],
    }

    if not applied:
        return result

    # Validate the WHOLE mutated dict before persisting anything -- a validator
    # failure aborts the entire write, never a partial one.
    errors = validate_package_registry(data)
    if errors:
        result["applied"] = []  # nothing was actually persisted; report as not-applied
        result["validation_errors"] = errors
        return result

    if data == original_data:
        # Idempotent no-op: the applied proposal(s) set fields identical to what
        # was already recorded (e.g. re-running after a crash between write and
        # commit) -- never write or signal a commit when nothing actually
        # changed. Deliberately a structural (parsed) comparison, not a raw-bytes
        # one: the on-disk file's formatting is not guaranteed to match
        # json.dumps(..., indent=2)'s exact output, and a byte compare would
        # report "changed" for a purely cosmetic reformatting with zero semantic
        # difference, causing a spurious commit.
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
    # Re-read + re-validate the real path once more before ever reporting success.
    final_errors = validate_package_registry(json.loads(DATA_PATH.read_text(encoding="utf-8")))
    if final_errors:
        # Should be unreachable (we just validated identical bytes) -- but if the
        # filesystem lied to us somehow, never claim success on unverified data.
        result["applied"] = []
        result["validation_errors"] = final_errors
        return result

    result["wrote_changes"] = True
    return result


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="publish_watcher")
    parser.add_argument("--issue-body-out", metavar="PATH", help="Write the GitHub issue body to this path if any proposals are found")
    parser.add_argument("--version-issue-body-out", metavar="PATH", help="Write the steady-state version-update issue body to this path if any proposals are found")
    parser.add_argument("--auto-apply", action="store_true",
                         help="Apply eligible proposals and atomically write data/package_registry.json "
                              "instead of only reporting them (Mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION, Phase 3)")
    parser.add_argument("--max-auto-apply", type=int, default=DEFAULT_MAX_AUTO_APPLY, metavar="N",
                         help=f"Registry-level circuit breaker: at most N proposals applied per run (default {DEFAULT_MAX_AUTO_APPLY})")
    args = parser.parse_args(argv)

    if args.auto_apply:
        result = run_auto_apply(max_apply=args.max_auto_apply)
        _write_github_output("wrote_changes", "true" if result["wrote_changes"] else "false")

        if result["validation_errors"]:
            print("publish_watcher --auto-apply: validation FAILED after applying proposals -- "
                  "the entire write was aborted, data/package_registry.json is untouched.")
            for err in result["validation_errors"]:
                print(f"  - {err}")
            return 1

        applied_keys = {(p["family"], p["platform"]) for p in result["applied"]}
        remaining_unpublished = [p for p in result["unpublished_proposals"]
                                  if (p["family"], p["platform"]) not in applied_keys]
        remaining_version = [p for p in result["version_proposals"]
                              if (p["family"], p["platform"]) not in applied_keys]

        if result["applied"]:
            print(f"publish_watcher --auto-apply: applied {len(result['applied'])} proposal(s); "
                  f"wrote_changes={result['wrote_changes']}")
        if result["skipped_capped"]:
            print(f"publish_watcher --auto-apply: circuit breaker reached -- "
                  f"{len(result['skipped_capped'])} proposal(s) deferred to issue-filing below")

        # Overflow beyond the circuit breaker still gets reported the normal way.
        if remaining_unpublished:
            print(format_issue_body(remaining_unpublished))
            if args.issue_body_out:
                Path(args.issue_body_out).write_text(format_issue_body(remaining_unpublished), encoding="utf-8")
        if remaining_version:
            print(format_version_update_issue_body(remaining_version))
            if args.version_issue_body_out:
                Path(args.version_issue_body_out).write_text(
                    format_version_update_issue_body(remaining_version), encoding="utf-8")

        if not result["applied"] and not remaining_unpublished and not remaining_version:
            print("publish_watcher: no unpublished family resolves live yet, and no already-published "
                  "family has a newer live version. Nothing to report.")
            return 0
        return 1

    proposals = run_watch()
    version_proposals = run_version_watch()

    if not proposals and not version_proposals:
        print("publish_watcher: no unpublished family resolves live yet, and no already-published family has a newer live version. Nothing to report.")
        return 0

    if proposals:
        body = format_issue_body(proposals)
        print(body)
        if args.issue_body_out:
            Path(args.issue_body_out).write_text(body, encoding="utf-8")

    if version_proposals:
        version_body = format_version_update_issue_body(version_proposals)
        print(version_body)
        if args.version_issue_body_out:
            Path(args.version_issue_body_out).write_text(version_body, encoding="utf-8")

    return 1


if __name__ == "__main__":
    sys.exit(main())
