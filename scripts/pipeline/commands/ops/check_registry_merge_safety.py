"""check_registry_merge_safety.py — MT075-T5 (plan Revision 2 SR2.5).

The deterministic decision engine behind the unified registry watcher
(registry_watch.py, MT075-T6): given the CURRENT (base) state of one
data/package_registry.json entry and a CANDIDATE (proposed) state a watcher
observed, decide whether the candidate may be applied with NO human step at
all, must be held pending stronger evidence, or is rejected outright. This
replaces the old design (a PR that sits until a human notices and merges it)
for every registry, not just Maven -- see the module's own two-tier model
below for why "no human required" does not mean "trust anything."

Modeled on scripts/seo/pipeline/check_merge_safety.py's gate SHAPE (diff-scope
allowlist, changed-key allowlist, a change-budget-style entry cap) -- but NOT
on its identity/corroboration model. An adversarial review of the first draft
of this design (2026-09-27) found that model unsafe for this domain
specifically: SEO keywords have no outside adversary who can plant the exact
resource the system is about to trust; package registries do (PyPI/npm/crates
have no reserved-name protection, per finding F10). The concrete attack the
review demonstrated: a squatter pre-registers the exact name this repo's own
naming-convention guesser would produce, the watcher's "independent re-fetch"
just re-confirms the squatter's own package exists, and a free-text
evidence_note clears every check that only re-reads the registry's own page.

Two-tier model (this is the fix for that attack, not a re-labeling of it):

  Tier 1 (AUTO_APPLY, no corroboration needed beyond what's below): a VERSION
  BUMP of an entry that is ALREADY verification.published=true in the base
  state, same identity, same registry_type, monotonically newer per
  lib.version_compare (never a downgrade, never a prerelease unless the base
  is already on a prerelease line), diff scope restricted to
  data/package_registry.json with changed JSON paths restricted to an
  allowlist of version/verification fields, batch size <=5 entries. This is
  the overwhelming majority of real events (every steady-state release) and
  the risk here is bounded: the identity itself was already accepted before
  this decision runs -- a version bump doesn't re-litigate identity.

  Tier 2 (HOLD unless out-of-band corroborated): a FIRST PUBLISH (base
  unpublished or absent -> candidate published), an IDENTITY_CHANGE (name/
  registry_type differs from base), or any PUBLISHED_TRUE_TO_FALSE flip.
  These get a real out-of-band check: does the candidate's name+version
  match a tag or release in the product's OWN GitHub repository (from
  data/products.json's recorded repo_url -- a value the candidate package
  itself cannot control or redirect)? If yes, AUTO_APPLY (still no human
  step). If no -- no matching release exists yet, the repo can't be reached,
  or there's no products.json entry to check against -- the candidate is
  HELD, never touches the live registry, and is retried on a later cycle as
  more evidence may appear. This is not "wait for a human"; it is "don't
  fabricate confidence the evidence doesn't support yet."

  A PUBLISHED_TRUE_TO_FALSE flip is additionally NEVER auto-applied even
  with corroboration (REJECT) -- unpublishing is exactly the kind of
  transient-looking signal (registry hiccup, mirror lag) that must never
  silently take a live install command away from public pages; it always
  needs the reconcile/live-probe loop to see it repeatedly before anything
  acts, which is out of this gate's scope by design (this gate is a
  per-observation decision, not the multi-cycle debounce policy).

  A downgrade (candidate older than base under the registry's own ordering)
  or a schema-invalid candidate is always REJECT, in either tier -- there is
  no amount of corroboration that makes a downgrade or an invalid record
  correct to apply.

Honesty note: corroboration bounds the specific pre-squat attack the review
demonstrated; it does not eliminate all supply-chain risk (a compromised or
spoofed upstream repo could still poison both sides). See the plan's own
Revision 2 SR2.9 for this tradeoff stated plainly.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_SCRIPTS_DIR = str(_PIPELINE_ROOT.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import requests  # noqa: E402

from version_compare import (  # noqa: E402
    VersionParseError, compare as version_compare_fn, is_prerelease,
)
from package_registry_data import validate_package_entry  # noqa: E402
from product_registry import get_product  # noqa: E402

DECISION_AUTO_APPLY = "AUTO_APPLY"
DECISION_HOLD = "HOLD"
DECISION_REJECT = "REJECT"
DECISION_NO_CHANGE = "NO_CHANGE"

TIER_1_VERSION_BUMP = "TIER_1_VERSION_BUMP"
TIER_2_FIRST_PUBLISH = "TIER_2_FIRST_PUBLISH"
TIER_2_IDENTITY_CHANGE = "TIER_2_IDENTITY_CHANGE"
TIER_2_UNPUBLISH = "TIER_2_UNPUBLISH"
TIER_NONE = "NONE"

MAX_ENTRIES_PER_BATCH = 5

# Tier 1's allowlist: a version-bump candidate may only change these JSON
# paths relative to the base entry. Anything else changing (candidate name,
# candidate_owner, registry_type, ...) forces Tier 2 classification even if
# the version also happens to look like a bump.
_TIER1_ALLOWED_CHANGED_PATHS = {
    "candidate.version",
    "verification.verified_at",
    "verification.evidence_url",
    "verification.evidence_note",
    "verification.method",
    "verification.consecutive_checks_agreeing",
    "verification.consecutive_version_checks_agreeing",
}


@dataclass
class Verdict:
    decision: str
    tier: str
    reason: str
    checks: dict = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.decision == DECISION_AUTO_APPLY


def _candidate_identity_key(entry: dict) -> "tuple | None":
    """Extract the identity-defining fields from an entry's candidate block,
    independent of registry_type's differing shape (name-based for pypi/
    nuget/npm/go_modules/cargo, group_id+artifact_id for maven)."""
    candidate = entry.get("candidate") or {}
    if "group_id" in candidate or "artifact_id" in candidate:
        return ("maven", candidate.get("group_id"), candidate.get("artifact_id"))
    return ("name", candidate.get("name"))


def _semantically_unchanged(base_entry: dict, candidate_entry: dict) -> bool:
    """True when base and candidate agree on every field that could
    possibly justify an apply -- registry_type, identity, version, and
    published -- even if cosmetic fields (verified_at, evidence_note,
    evidence_url, method) differ. See evaluate_entry_change's own comment
    for why exact dict equality doesn't work here."""
    if base_entry.get("registry_type") != candidate_entry.get("registry_type"):
        return False
    if _candidate_identity_key(base_entry) != _candidate_identity_key(candidate_entry):
        return False
    base_version = (base_entry.get("candidate") or {}).get("version")
    cand_version = (candidate_entry.get("candidate") or {}).get("version")
    if base_version != cand_version:
        return False
    base_published = bool((base_entry.get("verification") or {}).get("published"))
    cand_published = bool((candidate_entry.get("verification") or {}).get("published"))
    return base_published == cand_published


def _diff_changed_paths(base: dict, candidate: dict, *, prefix: str = "") -> set[str]:
    """Dotted-path diff between two JSON-like dicts -- returns every leaf
    path whose value differs (added, removed, or changed). Used both to
    classify an identity change and to enforce Tier 1's field allowlist."""
    changed: set[str] = set()
    keys = set(base.keys()) | set(candidate.keys())
    for key in keys:
        path = f"{prefix}.{key}" if prefix else key
        b_val = base.get(key)
        c_val = candidate.get(key)
        if isinstance(b_val, dict) and isinstance(c_val, dict):
            changed |= _diff_changed_paths(b_val, c_val, prefix=path)
        elif b_val != c_val:
            changed.add(path)
    return changed


def classify_event(base_entry: "dict | None", candidate_entry: dict) -> str:
    """Return the tier/event-shape classification for one entry transition.
    Pure classification -- does not decide AUTO_APPLY/HOLD/REJECT, only what
    KIND of transition this is (evaluate_entry_change applies the policy)."""
    if base_entry is None:
        return TIER_2_FIRST_PUBLISH

    base_published = bool((base_entry.get("verification") or {}).get("published"))
    cand_published = bool((candidate_entry.get("verification") or {}).get("published"))

    # Checked BEFORE identity, deliberately: independent review (2026-09-28)
    # found that checking identity first let a candidate that changes BOTH
    # identity AND published:true->false get classified as
    # TIER_2_IDENTITY_CHANGE (corroboration-eligible) instead of
    # TIER_2_UNPUBLISH (always-reject) -- a real bypass of the "never
    # auto-unpublish" invariant. An unpublish is an unpublish regardless of
    # what else also changed in the same candidate.
    if base_published and not cand_published:
        return TIER_2_UNPUBLISH

    base_type = base_entry.get("registry_type")
    cand_type = candidate_entry.get("registry_type")
    if base_type != cand_type:
        return TIER_2_IDENTITY_CHANGE

    base_identity = _candidate_identity_key(base_entry)
    cand_identity = _candidate_identity_key(candidate_entry)
    if base_identity != cand_identity:
        return TIER_2_IDENTITY_CHANGE

    if not base_published and cand_published:
        return TIER_2_FIRST_PUBLISH
    if base_published and cand_published:
        return TIER_1_VERSION_BUMP
    # Neither base nor candidate is published -- e.g. a scouted-but-never-
    # confirmed candidate whose identity fields got touched up. Nothing this
    # gate needs to auto-apply (there's no live claim on public pages yet);
    # treat it the same as first-publish-shaped so any future flip to
    # published still goes through corroboration, not a bare unattended pass.
    return TIER_2_FIRST_PUBLISH


def fetch_repo_tags_and_releases(repo_url: str, *, fetch: "Callable[[str], Any] | None" = None) -> list[str]:
    """Return every tag and release name from the product's own GitHub repo
    -- the out-of-band evidence source Tier 2 corroboration checks against.
    Deliberately NOT the package registry itself (that's what the watcher
    already checked; re-checking it again proves nothing new, per this
    module's own docstring on the pre-squat attack). Returns [] on any
    network/parsing failure -- corroboration is meant to fail toward HOLD,
    never to crash the gate."""
    owner_repo = _owner_repo_from_url(repo_url)
    if owner_repo is None:
        return []
    owner, repo = owner_repo
    fetcher = fetch or _default_github_fetch
    names: list[str] = []
    for kind in ("tags", "releases"):
        try:
            data = fetcher(f"https://api.github.com/repos/{owner}/{repo}/{kind}")
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("tag_name")
            if name:
                names.append(str(name))
    return names


def _owner_repo_from_url(repo_url: "str | None") -> "tuple[str, str] | None":
    if not repo_url:
        return None
    parts = repo_url.rstrip("/").split("/")
    if len(parts) < 2:
        return None
    return parts[-2], parts[-1]


def _default_github_fetch(url: str) -> Any:
    resp = requests.get(url, timeout=15, headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    return resp.json()


def version_corroborated_by_repo(version: str, tag_names: list[str]) -> bool:
    """The candidate's bare version must appear in a tag/release name as a
    boundary-delimited token -- not preceded or followed by another digit or
    '.', so it can't be a fragment of a longer version. Covers the common
    real tagging conventions (v26.7.0, release-26.7.0, Aspose.Cells.FOSS-
    26.7.0) while rejecting the false positives independent review
    (2026-09-28) found in the original naive substring version: "7.0"
    matching "v26.7.0", "1.0.0" matching a bare tag "v1", "0.1.0" matching
    "v10.1.0", and (the most dangerous one -- it ran in the WRONG direction)
    any version matching a tag of just "v", since `tag_bare in version` is
    true for almost anything once the tag is short enough. That reverse
    check is removed entirely; only "does the candidate version appear
    in the tag" is a valid corroboration direction."""
    bare = version.lstrip("vV")
    if not bare:
        return False
    pattern = re.compile(r"(?<![0-9.])" + re.escape(bare) + r"(?![0-9.])")
    for tag in tag_names:
        if pattern.search(tag):
            return True
    return False


def check_repo_release_corroboration(
    family: str, platform: str, candidate_version: str,
    *, fetch: "Callable[[str], Any] | None" = None,
    product_lookup: "Callable[[str, str], dict | None] | None" = None,
) -> bool:
    """The Tier 2 gate: does data/products.json even have a repo recorded
    for this family/platform, and does that repo's own tag/release history
    corroborate the candidate version? False (never an exception) whenever
    the answer can't be established -- absence of proof is HOLD, not
    auto-reject and not auto-apply."""
    lookup = product_lookup or get_product
    product = lookup(family, platform)
    if not product or not product.get("repo_url"):
        return False
    tags = fetch_repo_tags_and_releases(product["repo_url"], fetch=fetch)
    if not tags:
        return False
    return version_corroborated_by_repo(candidate_version, tags)


def _load_change_budget():
    """Lazy, defensive import of scripts/seo/pipeline/change_budget.py --
    mirrors the existing precedent in commands/ops/page_impact_assess.py
    (core pipeline infrastructure must degrade cleanly if the seo subpackage
    is ever unavailable, moved, or its optional data is missing), but UNLIKE
    that precedent this is a safety control, not a display hint: see
    check_registry_velocity()'s own docstring for why unavailability fails
    closed (HOLD) here rather than silently skipping the check."""
    try:
        from seo.pipeline import change_budget
        return change_budget
    except ImportError:
        return None


_UNSET = object()  # sentinel: distinguishes "not provided" from an explicit None (module unavailable)


def check_registry_velocity(
    family: str, *, budgets: "dict | None" = None, history: "dict | None" = None,
    _change_budget_module: Any = _UNSET,
) -> "tuple[bool, str]":
    """MT075-T9 (plan Revision 2 SR2.13): the cross-run velocity/anomaly
    check that was missing before this -- reuses scripts/seo/pipeline/
    change_budget.py's proven rolling-baseline design (mechanism=
    "registry_watch", keyed by family) rather than building a new one.

    Why this exists: the deterministic Tier 1/2 checks and the 5-entry
    MAX_ENTRIES_PER_BATCH cap are both single-run, single-decision controls
    -- neither has any memory across runs. A sustained pattern of changes to
    one family, each run individually within budget, would pass every
    single run forever. That gap mattered less while a bootstrap PR still
    required a human to merge the first few changes (R2.12); it became
    load-bearing the instant R2.13 removed that step -- this is the real
    control replacing the human step, not a weaker substitute for it.

    `_change_budget_module` is a configure()-seam-style injection point for
    tests to exercise the "module unavailable"/"module raises" paths without
    monkeypatching the private `_load_change_budget` (AGENTS.md 16, T2 --
    banned internal-patch pattern) -- leave it unset in real use.

    Returns (blocked, reason). Never raises: an unavailable/erroring
    change_budget module is treated as BLOCKED (fail toward HOLD), not
    silently skipped -- this is a safety control, not a display hint, so
    "can't tell" must resolve the same way "looks bad" does.
    """
    cb = _load_change_budget() if _change_budget_module is _UNSET else _change_budget_module
    if cb is None:
        return True, "change_budget module unavailable -- failing closed (HOLD), not skipping the velocity check"
    try:
        loaded_budgets = budgets if budgets is not None else cb.load_budgets()
        volume = cb.ProposedChangeVolume(total_items=1)
        verdict = cb.check_budget(family, "registry_watch", volume, budgets=loaded_budgets, history=history)
        return (not verdict.allowed), f"{verdict.reason} ({verdict.anomaly_status})"
    except Exception as exc:  # pragma: no cover - defensive, see docstring
        return True, f"change_budget check raised {exc!r} -- failing closed (HOLD)"


def record_registry_watch_apply(family: str, actual_count: int) -> None:
    """Record this run's REAL applied count for `family` into change_budget's
    rolling history -- must be called only after a write actually succeeds,
    with the real count, never the proposed one (change_budget.record_run()'s
    own documented contract). Called by registry_watch.py's run_auto_apply()
    once per family after a successful atomic write. A no-op (never raises)
    if the change_budget module is unavailable -- losing one run's history
    point degrades the anomaly baseline, it does not compromise a decision
    already made and already written."""
    cb = _load_change_budget()
    if cb is None:
        return
    try:
        cb.record_run(family, "registry_watch", actual_count)
    except Exception:  # pragma: no cover - defensive, see docstring
        pass


def evaluate_entry_change(
    family: str, platform: str, base_entry: "dict | None", candidate_entry: dict,
    *, corroboration_check: "Callable[[str, str, str], bool] | None" = None,
    velocity_check: "Callable[[str], tuple[bool, str]] | None" = None,
) -> Verdict:
    """Evaluate ONE entry's proposed change. Does not check batch-level
    concerns (entry count, file scope) -- see evaluate_batch() for those."""
    check_velocity = velocity_check or check_registry_velocity
    errors = validate_package_entry(candidate_entry, context=f"{family}.{platform}")
    if errors:
        return Verdict(DECISION_REJECT, TIER_NONE, f"schema-invalid candidate: {errors}")

    # Defense in depth (live-data proof run, 2026-09-28): if the candidate
    # carries no semantically new information over the base entry, there is
    # nothing to apply, regardless of what tier classification would
    # otherwise say. Compares registry_type/identity/version/published only
    # -- NOT full dict equality: independent review (2026-09-28) found that
    # build_candidate_entry always rewrites verified_at and evidence_note to
    # the current observation timestamp, so an exact-equality guard could
    # never actually fire against a real candidate (every unchanged
    # observation would still differ cosmetically) -- it only ever passed in
    # tests that reused the identical dict. This is the guard that actually
    # catches a future candidate-construction bug leaking a stale but
    # semantically-meaningful field through unchanged.
    if base_entry is not None and _semantically_unchanged(base_entry, candidate_entry):
        return Verdict(DECISION_NO_CHANGE, TIER_NONE, "candidate has no semantic change over the base entry")

    tier = classify_event(base_entry, candidate_entry)

    if tier == TIER_2_UNPUBLISH:
        # Hard invariant, not evidence-gated: never auto-flip a confirmed
        # publish back to unpublished from a single observation.
        return Verdict(
            DECISION_REJECT, tier,
            "published:true -> false is never auto-applied regardless of corroboration "
            "-- requires the multi-cycle reconcile/live-probe loop, out of this gate's scope",
        )

    cand_version = (candidate_entry.get("candidate") or {}).get("version")
    registry_type = candidate_entry.get("registry_type")
    base_version = (base_entry or {}).get("candidate", {}).get("version")

    # Applied to BOTH tiers, not just Tier 1: independent review (2026-09-28)
    # found the original code only ever compared versions inside the Tier-1
    # branch, so a Tier-2 candidate (first publish / identity change) could
    # be corroborated and AUTO_APPLY a downgrade or a prerelease with no
    # version check at all -- reproduced live with pdf/go's base v0.9.0
    # against a candidate v0.1.0. A downgrade or an unjustified prerelease
    # is never correct to apply, in either tier, whenever there's a base
    # version to compare against.
    if base_version and cand_version and registry_type:
        try:
            cmp = version_compare_fn(registry_type, cand_version, base_version)
        except VersionParseError as exc:
            return Verdict(DECISION_REJECT, tier, f"version parse failure: {exc}")
        if cmp < 0:
            return Verdict(DECISION_REJECT, tier, f"downgrade: {cand_version} < {base_version}, never applied")
        if cmp == 0 and tier == TIER_1_VERSION_BUMP:
            return Verdict(DECISION_NO_CHANGE, tier, "candidate version equals base -- nothing to apply")
    if cand_version and registry_type:
        # Prerelease check does NOT require a base_version -- independent
        # review found the original guard was skipped entirely whenever
        # base_version was falsy (e.g. a published entry with no recorded
        # version yet), silently admitting a prerelease candidate. With no
        # base version to prove "already on a prerelease line", the safe
        # default is to treat the base as NOT prerelease.
        try:
            base_prerelease = is_prerelease(registry_type, base_version) if base_version else False
            cand_prerelease = is_prerelease(registry_type, cand_version)
        except VersionParseError:
            base_prerelease = cand_prerelease = False
        if cand_prerelease and not base_prerelease:
            return Verdict(
                DECISION_HOLD, tier,
                "candidate is a prerelease and the base entry is not on a prerelease line",
            )

    if tier == TIER_1_VERSION_BUMP:
        changed_paths = _diff_changed_paths(base_entry or {}, candidate_entry)
        disallowed = changed_paths - _TIER1_ALLOWED_CHANGED_PATHS
        if disallowed:
            return Verdict(
                DECISION_HOLD, tier,
                f"version-bump-shaped but touches non-allowlisted fields {sorted(disallowed)} "
                "-- demoted to HOLD rather than trusted as a plain bump",
            )
        # MT075-T9 (R2.13): the cross-run velocity check that replaces the
        # human-merge step's nominal safety net -- checked last, only once
        # every other gate has already cleared the entry for AUTO_APPLY, so
        # a velocity block never masks a more specific rejection reason.
        blocked, velocity_reason = check_velocity(family)
        if blocked:
            return Verdict(DECISION_HOLD, tier, f"velocity/anomaly check blocked this apply: {velocity_reason}")
        return Verdict(DECISION_AUTO_APPLY, tier, "version bump of an already-published, same-identity entry")

    # Tier 2 (first publish / identity change): needs out-of-band corroboration.
    corroborate = corroboration_check or (
        lambda f, p, v: check_repo_release_corroboration(f, p, v)
    )
    if not cand_version:
        return Verdict(DECISION_HOLD, tier, "no candidate version to corroborate against")
    corroborated = corroborate(family, platform, cand_version)
    if not corroborated:
        return Verdict(
            DECISION_HOLD, tier,
            "no matching release/tag found in the product's own repo (or no repo recorded) -- "
            "held, not applied; will be retried as more evidence may appear",
        )
    blocked, velocity_reason = check_velocity(family)
    if blocked:
        return Verdict(DECISION_HOLD, tier, f"velocity/anomaly check blocked this apply: {velocity_reason}")
    return Verdict(DECISION_AUTO_APPLY, tier, "corroborated against the product's own GitHub repo releases/tags")


@dataclass
class BatchVerdict:
    decision: str
    reason: str
    per_entry: "dict[tuple[str, str], Verdict]" = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.decision == DECISION_AUTO_APPLY


def evaluate_batch(
    base_registry: dict, candidate_registry: dict,
    *, corroboration_check: "Callable[[str, str, str], bool] | None" = None,
    velocity_check: "Callable[[str], tuple[bool, str]] | None" = None,
) -> BatchVerdict:
    """Evaluate every changed (family, platform) entry between two full
    registry snapshots. The batch as a whole is only AUTO_APPLY if every
    changed entry is individually AUTO_APPLY or NO_CHANGE, and the changed-
    entry count is within budget -- one bad entry in a batch holds the whole
    batch rather than silently applying the rest and skipping the risky one
    (a partial apply would itself be an unreviewed, undocumented state)."""
    # Deletions checked first and separately: independent review (2026-09-28)
    # found the original loop only ever iterated candidate_registry, so a
    # family/platform present in base but ABSENT from candidate was silently
    # invisible -- a real entry could be deleted entirely and evaluate_batch
    # would report NO_CHANGE, sidestepping the "never auto-unpublish"
    # invariant by a different route. A deletion is never auto-applied.
    deleted: "list[tuple[str, str]]" = []
    for family, platforms in base_registry.items():
        if not isinstance(platforms, dict):
            continue
        cand_platforms = candidate_registry.get(family, {}) if isinstance(candidate_registry.get(family), dict) else {}
        for platform, base_entry in platforms.items():
            if isinstance(base_entry, dict) and platform not in cand_platforms:
                deleted.append((family, platform))
    if deleted:
        return BatchVerdict(
            DECISION_HOLD,
            f"{len(deleted)} entrie(s) present in base but missing from candidate {sorted(deleted)} "
            "-- a deletion is never auto-applied",
        )

    changed: "dict[tuple[str, str], tuple[dict | None, dict]]" = {}
    for family, platforms in candidate_registry.items():
        if not isinstance(platforms, dict):
            continue
        base_platforms = base_registry.get(family, {}) if isinstance(base_registry.get(family), dict) else {}
        for platform, cand_entry in platforms.items():
            if not isinstance(cand_entry, dict):
                continue
            base_entry = base_platforms.get(platform)
            if base_entry != cand_entry:
                changed[(family, platform)] = (base_entry, cand_entry)

    if not changed:
        return BatchVerdict(DECISION_NO_CHANGE, "no entries differ between base and candidate")

    if len(changed) > MAX_ENTRIES_PER_BATCH:
        return BatchVerdict(
            DECISION_HOLD,
            f"{len(changed)} entries changed, exceeds the {MAX_ENTRIES_PER_BATCH}-entry batch cap",
        )

    per_entry: "dict[tuple[str, str], Verdict]" = {}
    for (family, platform), (base_entry, cand_entry) in changed.items():
        per_entry[(family, platform)] = evaluate_entry_change(
            family, platform, base_entry, cand_entry,
            corroboration_check=corroboration_check, velocity_check=velocity_check,
        )

    bad = {k: v for k, v in per_entry.items() if v.decision not in (DECISION_AUTO_APPLY, DECISION_NO_CHANGE)}
    if bad:
        reasons = "; ".join(f"{k[0]}/{k[1]}: {v.decision} ({v.reason})" for k, v in bad.items())
        return BatchVerdict(DECISION_HOLD, f"{len(bad)} of {len(changed)} entries not clear to apply: {reasons}", per_entry)

    return BatchVerdict(DECISION_AUTO_APPLY, f"all {len(changed)} changed entries clear to apply", per_entry)
