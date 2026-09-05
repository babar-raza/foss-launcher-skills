"""SEO-AUTONOMY-STATE-MACHINE (Contract I, v14 design authority
``C:\\Users\\prora\\.claude\\plans\\check-keywords-this-data-curious-feather.md``
lines 726-746): per-(family, mechanism) autonomy grants.

Resolves, as an enforced state machine rather than open prose, the tension
named in the predecessor mission: "the already-deployed weekly cron can
touch a not-yet-reviewed product before the operator reviews it." State is
keyed per (family, mechanism) pair -- a family can legitimately be
AUTONOMOUSLY_ELIGIBLE for one mechanism (e.g. the long-proven Schema A
keyword refresh) while still UNREVIEWED for a different, higher-risk one
(e.g. title/description content writes), since these are genuinely
different risk classes with different review history.

State machine::

    UNREVIEWED -> REVIEW_PENDING -> HUMAN_CLEARED -> AUTONOMOUSLY_ELIGIBLE
                                          ^                    |
                                   REVIEW_REQUIRED <-----------+
                                    (new non-self commit touches
                                     an already-cleared product)

    AUTONOMOUSLY_ELIGIBLE -> SUSPENDED (change-budget breach / rollback
                                         candidate / workflow-drift /
                                         token-liveness failure)
    SUSPENDED -> HUMAN_CLEARED (a human/independent-reviewer re-clears the
                                 suspension before autonomy can resume; the
                                 design doc does not name an explicit
                                 un-suspend target, so this module reuses
                                 the same re-review path REVIEW_REQUIRED
                                 already uses, rather than allowing a
                                 silent SUSPENDED -> AUTONOMOUSLY_ELIGIBLE
                                 shortcut)

Only ``HUMAN_CLEARED`` transitions may be driven by a real per-family
review outcome (``SEO-PER-PRODUCT-COMMIT-REVIEW``'s
``product_review_log.jsonl`` CLEARED verdicts, or an operator/independent-
reviewer sign-off) -- granting a real family's real mechanism a real
HUMAN_CLEARED transition is a named human-authority boundary (v14 design
doc, "Architecture contradictions" (b)/(c)) and is never self-granted by
this module or by the code that imports it. Everything this module does by
itself (initial UNREVIEWED default, REVIEW_REQUIRED auto-flip, SUSPENDED
auto-flip, synthetic-test transitions) is ordinary agent-operable
bookkeeping, not an authority grant.

Concurrency: writes go through an atomic tempfile + ``os.replace`` (mirrors
``migrate_platform_labels.py``'s ``save_migration_state_atomic()``), and
every transition that names a ``source_sha`` is idempotent against it -- a
second process re-detecting the identical triggering commit is a no-op,
never a duplicate transition (v14 Contract I hardening, Reviewer F).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT
STATE_PATH = REPO_ROOT / "data" / "seo_autonomy_state.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing (tiered monkeypatch
    policy, AGENTS.md §16 / docs/development/testing-seams.md)."""
    global REPO_ROOT, STATE_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    STATE_PATH = REPO_ROOT / "data" / "seo_autonomy_state.json"


# --- Status vocabulary ------------------------------------------------------

STATUS_UNREVIEWED = "UNREVIEWED"
STATUS_REVIEW_PENDING = "REVIEW_PENDING"
STATUS_HUMAN_CLEARED = "HUMAN_CLEARED"
STATUS_AUTONOMOUSLY_ELIGIBLE = "AUTONOMOUSLY_ELIGIBLE"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATUS_SUSPENDED = "SUSPENDED"

ALL_STATUSES = frozenset({
    STATUS_UNREVIEWED,
    STATUS_REVIEW_PENDING,
    STATUS_HUMAN_CLEARED,
    STATUS_AUTONOMOUSLY_ELIGIBLE,
    STATUS_REVIEW_REQUIRED,
    STATUS_SUSPENDED,
})

# Terminal-per-transition legal target set for each source status. Anything
# not listed here is an illegal transition and raises InvalidTransitionError.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_UNREVIEWED: frozenset({STATUS_REVIEW_PENDING}),
    STATUS_REVIEW_PENDING: frozenset({STATUS_HUMAN_CLEARED}),
    STATUS_HUMAN_CLEARED: frozenset({STATUS_AUTONOMOUSLY_ELIGIBLE, STATUS_REVIEW_REQUIRED}),
    STATUS_AUTONOMOUSLY_ELIGIBLE: frozenset({STATUS_REVIEW_REQUIRED, STATUS_SUSPENDED}),
    STATUS_REVIEW_REQUIRED: frozenset({STATUS_HUMAN_CLEARED}),
    STATUS_SUSPENDED: frozenset({STATUS_HUMAN_CLEARED}),
}

_DEFAULT_RECORD: dict[str, Any] = {
    "status": STATUS_UNREVIEWED,
    "transitioned_at": None,
    "transition_reason": None,
    "actor": None,
    "source_sha": None,
    "last_reviewed_sha": None,
}

# The Schema A cron's own authorized auto-merge commits, per the exact real
# precedent cited in the v14 design doc ("Architecture contradictions" (d)):
# PR #46/#60's real titles all follow this convention. A commit matching
# this pattern never re-triggers REVIEW_REQUIRED on itself -- otherwise the
# cron's own authorized writes would immediately un-clear the very autonomy
# that produced them (an infinite flip-flop).
_SELF_COMMIT_PATTERNS = (
    re.compile(r"^chore\(seo\):\s*Schema A keyword refresh", re.IGNORECASE),
)


class AutonomyStateError(Exception):
    """Base class for autonomy-state errors."""


class InvalidTransitionError(AutonomyStateError):
    """Raised when a requested transition is not a legal edge in the state
    machine from the record's current status."""


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- State I/O ---------------------------------------------------------------

def load_state(state_path: "Path | str | None" = None) -> dict:
    """Load the full ``{family: {mechanism: record}}`` state dict. Missing
    file -> ``{}`` (every family/mechanism defaults to UNREVIEWED), matching
    ``migrate_platform_labels.py``'s missing-state-file convention."""
    path = Path(state_path) if state_path is not None else STATE_PATH
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise AutonomyStateError(f"{path}: expected a JSON object at the top level")
    return data


def save_state_atomic(state: dict, state_path: "Path | str | None" = None) -> None:
    """Write via a temp file + ``os.replace`` so a crash mid-write can never
    leave a partially-written, corrupt state file -- the previous, valid
    state (or no file at all) is always what survives an interruption."""
    path = Path(state_path) if state_path is not None else STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".seo_autonomy_state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# --- Record access -----------------------------------------------------------

def get_record(family: str, mechanism: str, state: "dict | None" = None) -> dict:
    """Return the full record for (family, mechanism), defaulting every
    missing field to the UNREVIEWED default record. Never raises on a
    missing family or mechanism -- an unreviewed pair is exactly what an
    absent entry means."""
    if state is None:
        state = load_state()
    raw = state.get(family, {}).get(mechanism)
    record = dict(_DEFAULT_RECORD)
    if raw:
        record.update(raw)
    return record


def get_status(family: str, mechanism: str, state: "dict | None" = None) -> str:
    return get_record(family, mechanism, state)["status"]


def is_autonomously_eligible(family: str, mechanism: str, state: "dict | None" = None) -> bool:
    """The one check every write-path call site needs: is this
    (family, mechanism) currently AUTONOMOUSLY_ELIGIBLE? Per Contract J
    invariant 11 (``autonomy_state_eligible_or_dry_run``), the *only* other
    condition that permits a write is the action being a dry run --
    call sites gate on that separately, since this module has no notion of
    "dry run"."""
    return get_status(family, mechanism, state) == STATUS_AUTONOMOUSLY_ELIGIBLE


def is_self_commit(commit_message: "str | None") -> bool:
    """True iff a commit message matches an already-established, operator-
    authorized mechanism's own commit-message convention (currently only
    the Schema A cron's). Used to exclude a mechanism's own authorized
    writes from re-triggering REVIEW_REQUIRED on itself."""
    if not commit_message:
        return False
    return any(pattern.search(commit_message) for pattern in _SELF_COMMIT_PATTERNS)


# --- Transitions ---------------------------------------------------------

def transition(
    family: str,
    mechanism: str,
    to_status: str,
    *,
    reason: str,
    actor: str,
    source_sha: "str | None" = None,
    state_path: "Path | str | None" = None,
) -> dict:
    """Apply one legal state-machine transition for (family, mechanism) and
    persist it atomically. Returns the new record.

    Idempotent-by-source_sha (v14 Contract I race-condition hardening,
    Reviewer F): if the record is *already* at ``to_status`` with the exact
    same ``source_sha`` this call would write, this is a no-op that returns
    the existing record unchanged -- two processes independently detecting
    the same triggering commit at close to the same time never double-
    transition or double-notify.

    Raises ``InvalidTransitionError`` if ``to_status`` is not a legal edge
    from the record's current status (an already-idempotent no-op is
    checked first and never raises).
    """
    if to_status not in ALL_STATUSES:
        raise AutonomyStateError(f"unknown status {to_status!r}; must be one of {sorted(ALL_STATUSES)}")

    path = Path(state_path) if state_path is not None else STATE_PATH
    state = load_state(path)
    family_state = state.setdefault(family, {})
    current = family_state.get(mechanism)
    current_status = current["status"] if current else STATUS_UNREVIEWED

    if (
        current is not None
        and current.get("status") == to_status
        and source_sha is not None
        and current.get("source_sha") == source_sha
    ):
        return dict(current)

    allowed = VALID_TRANSITIONS.get(current_status, frozenset())
    if to_status not in allowed:
        raise InvalidTransitionError(
            f"{family}/{mechanism}: {current_status} -> {to_status} is not a legal transition "
            f"(legal targets from {current_status}: {sorted(allowed) or 'none'})"
        )

    record = {
        "status": to_status,
        "transitioned_at": _now_iso(),
        "transition_reason": reason,
        "actor": actor,
        "source_sha": source_sha,
        "last_reviewed_sha": current.get("last_reviewed_sha") if current else None,
    }
    if to_status == STATUS_HUMAN_CLEARED:
        record["last_reviewed_sha"] = source_sha if source_sha is not None else record["last_reviewed_sha"]

    family_state[mechanism] = record
    save_state_atomic(state, path)
    return dict(record)


def check_commit_for_review_required(
    family: str,
    mechanism: str,
    *,
    commit_sha: str,
    commit_message: "str | None",
    state_path: "Path | str | None" = None,
) -> "dict | None":
    """Implements the auto-flip described in the design doc: "a later commit
    touching an already-cleared product's keyword/content files mechanically
    flips its state back to REVIEW_REQUIRED." Call once per (family,
    mechanism, commit) a caller has already determined touched that family's
    files.

    Returns the new record if a transition happened, or ``None`` if no
    transition was needed: the pair is not currently AUTONOMOUSLY_ELIGIBLE,
    the commit matches a known self-commit pattern for an authorized
    mechanism (excluded so the mechanism's own writes never un-clear
    themselves), or this exact commit was already processed
    (``last_reviewed_sha`` already equals ``commit_sha`` -- distinct from
    the ``source_sha`` idempotency ``transition()`` itself provides, since
    here the caller may re-run this check for the same commit against a
    record that has since moved on).
    """
    state = load_state(state_path)
    record = get_record(family, mechanism, state)
    if record["status"] != STATUS_AUTONOMOUSLY_ELIGIBLE:
        return None
    if is_self_commit(commit_message):
        return None
    if record.get("last_reviewed_sha") == commit_sha:
        return None
    return transition(
        family,
        mechanism,
        STATUS_REVIEW_REQUIRED,
        reason=f"commit {commit_sha} touched an already-cleared product's files",
        actor="autonomy-state-machine",
        source_sha=commit_sha,
        state_path=state_path,
    )


def suspend(
    family: str,
    mechanism: str,
    *,
    reason: str,
    source_sha: "str | None" = None,
    state_path: "Path | str | None" = None,
) -> "dict | None":
    """AUTONOMOUSLY_ELIGIBLE -> SUSPENDED, the stop-the-line transition
    (Contract J). No-op (returns None) if the pair is not currently
    AUTONOMOUSLY_ELIGIBLE -- suspending an already-stopped or never-started
    mechanism is meaningless, not an error, since multiple independent
    stop-the-line triggers (change-budget breach, rollback candidate,
    workflow-drift, token-liveness failure) may fire for the same pair.

    Notification (filing/deduping a ``seo-autonomy-suspended`` tracking
    issue, per the v14 hardening note) is deliberately NOT done by this
    function -- issue-filing is an external GitHub write with its own
    injectable-CommandRunner testing seam, and belongs in a thin caller
    (mirroring ``check_upstream_drift.py``'s ``file_or_update_issue``
    pattern) so this module stays a pure, easily-testable state machine.
    """
    state = load_state(state_path)
    record = get_record(family, mechanism, state)
    if record["status"] != STATUS_AUTONOMOUSLY_ELIGIBLE:
        return None
    return transition(
        family,
        mechanism,
        STATUS_SUSPENDED,
        reason=reason,
        actor="autonomy-state-machine",
        source_sha=source_sha,
        state_path=state_path,
    )


# --- Family extraction (self-contained; no dependency on inventory.py) ------

_SITE_LANG_FAMILY_PLATFORM_SITES = ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org")


def family_from_page_path(page_path: "str | Path") -> "str | None":
    """Extract the family segment from a content-relative page path, e.g.
    ``content/kb.aspose.org/en/pdf/python/faq.md`` -> ``"pdf"``.

    Mirrors ``inventory.py``'s ``_get_family_platform_from_path`` site-shape
    table (docs/kb/reference: lang/family/platform; products: lang/family;
    blog: family/platform) without importing that module, so this state-
    machine module carries no dependency on the analysis pipeline. Returns
    ``None`` for a path this module doesn't recognize (e.g. websites/www,
    which have no family concept) rather than guessing.
    """
    # Normalize backslashes explicitly rather than relying on pathlib's
    # OS-dependent separator handling -- this repo's CI runs on Linux while
    # local dev is Windows (F2's own case-sensitivity lesson: never let a
    # path helper's correctness depend on which OS ran it).
    parts = str(page_path).replace("\\", "/").split("/")
    try:
        idx = parts.index("content")
    except ValueError:
        return None
    rest = parts[idx + 1:]
    if not rest:
        return None
    site, rest = rest[0], rest[1:]
    if site in _SITE_LANG_FAMILY_PLATFORM_SITES:
        # rest[0] is the language code (e.g. "en"); family is rest[1]
        return rest[1] if len(rest) > 1 else None
    if site == "products.aspose.org":
        return rest[1] if len(rest) > 1 else None
    if site == "blog.aspose.org":
        return rest[0] if len(rest) > 0 else None
    return None
