"""SEO-METADATA-OBSERVATION-LOOP (Contract H): post-publication observation
for every applied metadata change, generalizing SEO-TITLE-PILOT-OBSERVATION-
MEASURE's own proven, real, live-tested shape (2-4 week window, <=10%
position degradation, <=20% CTR drop, real weekly GSC snapshots read from
`keywords/{site}.aspose.org.json`'s own git history via `gsc_history.py`)
from a one-off pilot mechanism into a reusable, permanent framework covering
every applied title/description change, any (family, mechanism).

**Never auto-reverts.** On detecting real degradation, this module creates a
FAIL decision and autonomously flags the responsible (family, mechanism) as
SUSPENDED in the Autonomy State Machine (`autonomy_state.suspend()`, an
existing public function this module calls, never modifies) -- *stopping*
further similar changes is always safe, only *reverting* a published one
needs a human/independent-reviewer decision (Contract H, `SEO-METADATA-
ROLLBACK`'s own separate, dependent card). This module produces the
decision and the stop; it never writes content or reverts anything itself.

**Hardened per v14 design doc Sec.q/r (Contract H)**:
- Impression floor: `_IMPRESSION_FLOOR = 10`, matching `analyze.py`'s own
  `_IMPRESSION_THRESHOLD` (independently defined here, not cross-imported --
  `analyze.py` is outside this card's `allowed_paths` and importing a
  leading-underscore private name across modules is fragile; the VALUE is
  reused, per the design doc's own instruction, not the name binding).
- Data lag: GSC data lags real search activity by ~2-3 days
  (`_DATA_LAG_DAYS = 3`, the conservative end) -- the "after" measurement
  window is never checked until `deploy_confirmed_at + _DATA_LAG_DAYS` has
  elapsed, so a too-early check never compares against incomplete data.
- Control-group comparison: `select_control_set()` pulls same-site pages
  with real GSC data in both the pre and post snapshot windows (excluding
  the treated page); `compute_verdict()` judges the treated page's
  degradation *in excess of* the control group's own median delta over the
  same period, so a site-wide traffic swing or seasonal shift is never
  misattributed to the change itself.
- Genuine INCONCLUSIVE: insufficient impressions in either window, or no
  matched GSC data at all, is neither PASS nor FAIL, never triggers
  SUSPENDED, and extends the observation window exactly once
  (`_MAX_EXTENSIONS = 1`) before finalizing as INCONCLUSIVE.
- Deploy confirmation: an experiment's observation window does NOT begin at
  commit time -- `check_deploy_confirmed()` reads the real, live
  `scripts/deploy/deploy_manifest.json` from `Aspose/aspose.org-workflows`
  (the repo's own real, confirmed-existing "Deploy Status Checker" workflow
  output) and confirms `publish_revision` is an ancestor of (or equal to)
  the manifest's own `content_sha` with `state == "completed"`.

**Disclosed structural gap, real production topology**: `apply.py` itself
never commits (a separate governed step, `git_plumb_commit.py`, does, after
`apply.py` returns) -- so `apply.py` genuinely does not know the eventual
commit SHA at write time. `record_experiment_start()` therefore accepts
`publish_revision=None` (status `awaiting_commit`); a later step -- whatever
wraps `apply.py` + the commit step together in the real production
topology, outside this card's own `allowed_paths` -- must call
`attach_publish_revision()` once the real SHA is known.
`run_observation_pass()` silently skips any experiment still
`awaiting_commit`, never treating the absence of a revision as any kind of
verdict.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

_THIS_FILE = Path(__file__).resolve()
_SEO_SCRIPTS = _THIS_FILE.parents[1]
if str(_SEO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SEO_SCRIPTS))
# map_url.py (imported below) has no sys.path bootstrap of its own and its
# own internal fallback import (`from schema import ...`) requires this
# exact directory -- scripts/seo/pipeline itself -- to already be on
# sys.path; every other real caller of map_url.py in this codebase
# (keyword_gap_report.py, frontmatter_grounding_audit.py) has the same
# requirement but relies on ambient caller context to provide it. Added
# explicitly here so this module never depends on being lucky about which
# process imported it first.
_PIPELINE_DIR = _THIS_FILE.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
try:
    from seo.pipeline import gsc_history
    from seo.pipeline import autonomy_state
    from seo.pipeline import pipeline_state
    from seo.pipeline import map_url
except ImportError:
    from pipeline import gsc_history
    from pipeline import autonomy_state
    from pipeline import pipeline_state
    from pipeline import map_url

log = logging.getLogger("observe_experiments")

_DEFAULT_REPO_ROOT = _THIS_FILE.parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT

_STORE_RELPATH = "reports/seo/metadata_experiments.json"
SCHEMA_VERSION = 1

CommandRunner = Callable[..., "subprocess.CompletedProcess"]

_WORKFLOWS_REPO = "Aspose/aspose.org-workflows"
_DEPLOY_MANIFEST_PATH = "scripts/deploy/deploy_manifest.json"

# Reused thresholds -- SEO-TITLE-PILOT-OBSERVATION-MEASURE's own proven
# shape (v14 design doc, Contract H): 2-4 week window, <=10% position
# degradation, <=20% CTR drop.
_WINDOW_WEEKS = 3
_MAX_EXTENSIONS = 1
_POSITION_DEGRADATION_THRESHOLD = 0.10
_CTR_DROP_THRESHOLD = 0.20
_IMPRESSION_FLOOR = 10
_DATA_LAG_DAYS = 3

_OPEN_STATUSES = frozenset({"awaiting_commit", "awaiting_deploy_confirmation", "in_window"})
_FINAL_STATUSES = frozenset({
    "finalized_pass", "finalized_fail", "finalized_inconclusive", "superseded_before_window_end",
})


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override the module-level repo root for testing -- also syncs
    gsc_history.py's own repo root, since every real GSC read in this
    module goes through that module."""
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    gsc_history.configure(repo_root=REPO_ROOT)


def _store_path() -> Path:
    return REPO_ROOT / _STORE_RELPATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_experiments() -> dict:
    """The current experiment store, or a bootstrap-empty shape if none
    exists yet or the file is unreadable/corrupt -- fail open, never raise."""
    path = _store_path()
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "experiments": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("experiments"), dict):
            raise ValueError("unexpected metadata_experiments.json shape")
        return data
    except Exception:
        log.warning("observe_experiments.py: failed to read %s; treating as empty", path, exc_info=True)
        return {"schema_version": SCHEMA_VERSION, "experiments": {}}


def _save_atomic(state: dict) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".seo_metadata_experiments_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False, sort_keys=True)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ---------------------------------------------------------------------------
# Experiment lifecycle: start, supersession, publish-revision attachment
# ---------------------------------------------------------------------------


def record_experiment_start(
    page_path: str,
    field: str,
    old_value: "str | None",
    new_value: "str | None",
    *,
    family: "str | None" = None,
    mechanism: str = "title_description_writes",
    keyword_signal: "str | None" = None,
    source: "str | None" = None,
    intent: "str | None" = None,
    composition_method: "str | None" = None,
    confidence: "float | None" = None,
    review_result: "str | None" = None,
    publish_revision: "str | None" = None,
) -> str:
    """Open a new experiment record for a just-applied change. Returns the
    new `change_id`. Never raises -- a failure here must never roll back a
    write `apply.py` already made; the caller logs and moves on.

    `publish_revision=None` (the default, and apply.py's own real call
    shape -- see module docstring) leaves the record `awaiting_commit`, not
    actionable by `run_observation_pass()` until `attach_publish_revision()`
    is called by whatever later step learns the real commit SHA.
    """
    change_id = uuid.uuid4().hex
    try:
        state = load_experiments()
        state.setdefault("experiments", {})[change_id] = {
            "change_id": change_id,
            "page_path": page_path,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "family": family,
            "mechanism": mechanism,
            "keyword_signal": keyword_signal,
            "source": source,
            "intent": intent,
            "composition_method": composition_method,
            "confidence": confidence,
            "review_result": review_result,
            "publish_revision": publish_revision,
            "publish_timestamp": None,
            "deploy_confirmed_at": None,
            "observation_window_end": None,
            "extension_count": 0,
            "before_metrics": None,
            "after_metrics": None,
            "control_url_count": None,
            "decision": None,
            "decision_reasons": [],
            "status": "awaiting_commit" if publish_revision is None else "awaiting_deploy_confirmation",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        _save_atomic(state)
    except Exception:
        log.warning(
            "observe_experiments.py: record_experiment_start(%r, %r) failed",
            page_path, field, exc_info=True,
        )
    return change_id


def attach_publish_revision(change_id: str, commit_sha: str, *, runner: CommandRunner = subprocess.run) -> bool:
    """Record the real commit SHA once known (see module docstring's
    disclosed topology gap). Resolves the commit's own author date via
    `git show` to anchor the "before" measurement cutoff at the real change
    time, not an approximation. Returns False (never raises) if the
    experiment doesn't exist or the git lookup fails."""
    try:
        state = load_experiments()
        entry = state.get("experiments", {}).get(change_id)
        if entry is None:
            return False
        result = runner(
            ["git", "show", "-s", "--format=%aI", commit_sha],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False
        entry["publish_revision"] = commit_sha
        entry["publish_timestamp"] = result.stdout.strip()
        entry["status"] = "awaiting_deploy_confirmation"
        entry["updated_at"] = _now_iso()
        _save_atomic(state)
        return True
    except Exception:
        log.warning("observe_experiments.py: attach_publish_revision(%r) failed", change_id, exc_info=True)
        return False


def check_experiment_supersession(page_path: str, field: str) -> "list[str]":
    """Contract H hardening (v14 Sec.m): before publishing a NEW change to
    (page_path, field), mark any still-open experiment on that exact pair
    `superseded_before_window_end` and exclude it from future aggregation --
    a later change's effect is never misattributed to an earlier,
    already-superseded one. Returns the list of change_ids superseded
    (usually 0 or 1). Never raises."""
    superseded: "list[str]" = []
    try:
        state = load_experiments()
        experiments = state.get("experiments", {})
        changed = False
        for change_id, entry in experiments.items():
            if entry.get("page_path") != page_path or entry.get("field") != field:
                continue
            if entry.get("status") not in _OPEN_STATUSES:
                continue
            entry["status"] = "superseded_before_window_end"
            entry["decision"] = "superseded"
            entry["updated_at"] = _now_iso()
            superseded.append(change_id)
            changed = True
        if changed:
            _save_atomic(state)
    except Exception:
        log.warning(
            "observe_experiments.py: check_experiment_supersession(%r, %r) failed",
            page_path, field, exc_info=True,
        )
    return superseded


# ---------------------------------------------------------------------------
# Deploy confirmation (real, live Aspose/aspose.org-workflows dependency)
# ---------------------------------------------------------------------------


def fetch_deploy_manifest(*, runner: CommandRunner = subprocess.run) -> "dict | None":
    """Fetch and parse the real, live `deploy_manifest.json` from
    `Aspose/aspose.org-workflows` via `gh api`. Returns None on any
    network/auth/parse failure -- unresolved, never treated as "not
    confirmed" by a caller, which should instead retry on the next pass."""
    try:
        result = runner(
            ["gh", "api", f"repos/{_WORKFLOWS_REPO}/contents/{_DEPLOY_MANIFEST_PATH}", "--jq", ".content"],
            capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        raw_b64 = "".join(result.stdout.split())
        return json.loads(base64.b64decode(raw_b64).decode("utf-8"))
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, json.JSONDecodeError):
        return None


def check_deploy_confirmed(
    revision: str, *, runner: CommandRunner = subprocess.run, manifest: "dict | None" = None,
) -> "dict | None":
    """True if `revision` is confirmed live: the real deploy manifest's own
    `state == "completed"` AND `revision` is an ancestor of (or equal to)
    its `content_sha`, checked via real local git ancestry (this repo
    already holds the full history). `manifest` may be injected directly
    (tests); otherwise fetched live. Returns None (unresolved) on any
    fetch/parse/git failure -- a caller must retry later, never treat this
    as "not confirmed"."""
    if manifest is None:
        manifest = fetch_deploy_manifest(runner=runner)
        if manifest is None:
            return None

    if manifest.get("state") != "completed":
        return {"confirmed": False, "content_sha": manifest.get("content_sha"), "completed_at": manifest.get("completed_at")}

    content_sha = manifest.get("content_sha")
    if not content_sha:
        return {"confirmed": False, "content_sha": None, "completed_at": None}

    try:
        anc = runner(
            ["git", "merge-base", "--is-ancestor", revision, content_sha],
            cwd=REPO_ROOT, capture_output=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    return {
        "confirmed": anc.returncode == 0,
        "content_sha": content_sha,
        "completed_at": manifest.get("completed_at"),
    }


# ---------------------------------------------------------------------------
# GSC data access (reuses gsc_history.py + map_url.py, never reinvents)
# ---------------------------------------------------------------------------

_URL_SITE_RE = re.compile(r"^https://([a-z0-9]+)\.aspose\.org/")


def _site_from_gsc_url(url: str) -> "str | None":
    m = _URL_SITE_RE.match(url)
    if not m:
        return None
    site = m.group(1)
    return site if site in gsc_history.SCHEMA_B_SITES else None


def resolve_gsc_url(page_path: str) -> "str | None":
    """Reverse-lookup a page's real GSC URL via map_url.py's own proven,
    already-hardened url_map (forward GSC-url -> content-path resolver,
    reused rather than reimplemented). None if the page has no matched GSC
    entry (e.g. never appeared in any Schema B snapshot)."""
    try:
        result = map_url.build_url_map()
    except Exception:
        log.warning("observe_experiments.py: resolve_gsc_url(%r) — build_url_map failed", page_path, exc_info=True)
        return None
    norm_target = page_path.replace("\\", "/")
    for entry in result.get("url_map", []):
        if entry.get("matched") and entry.get("content_path") == norm_target:
            return entry.get("gsc_url")
    return None


def select_control_set(
    site: str, treated_url: str, pre_snapshot_sha: str, post_snapshot_sha: str, *, max_control_urls: int = 10,
) -> "list[dict]":
    """Real, same-site pages with real GSC data in BOTH the pre and post
    snapshots -- excludes the treated URL itself. Generalizes the exact
    control-set shape already proven live in SEO-TITLE-PILOT-OBSERVATION-
    MEASURE's own evidence bundle into a reusable function."""
    pre_records = gsc_history.load_snapshot(site, pre_snapshot_sha)
    post_by_url = {r.get("url"): r for r in gsc_history.load_snapshot(site, post_snapshot_sha)}
    control: "list[dict]" = []
    for rec in pre_records:
        url = rec.get("url")
        if not url or url == treated_url:
            continue
        post_rec = post_by_url.get(url)
        if post_rec is None:
            continue
        pre_m = gsc_history.aggregate_metrics(rec)
        post_m = gsc_history.aggregate_metrics(post_rec)
        if pre_m is None or post_m is None:
            continue
        control.append({"url": url, "pre_metrics": pre_m, "post_metrics": post_m})
        if len(control) >= max_control_urls:
            break
    return control


# ---------------------------------------------------------------------------
# Verdict computation (pure function)
# ---------------------------------------------------------------------------


def _position_delta(before_position: float, after_position: float) -> float:
    """Positive = WORSE (a higher/larger SERP position number ranks lower)."""
    return after_position - before_position


def _relative_ctr_delta(before_ctr: float, after_ctr: float) -> "float | None":
    """Negative = WORSE (a CTR drop). None if the before CTR is zero -- a
    relative drop from a zero baseline is not a meaningful ratio."""
    if before_ctr <= 0:
        return None
    return (after_ctr - before_ctr) / before_ctr


def _median(values: "list[float]") -> "float | None":
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


# Hardened after independent review (round 1 REJECT): a treated page with
# ZERO real change (stable position/CTR, well over the floor) was
# live-reproduced to FAIL when its control set consisted of same-site pages
# at 1 impression each showing an unrelated synthetic swing --
# select_control_set()'s own "has real GSC data in both windows" filter
# only requires impressions > 0 (aggregate_metrics's own floor), never the
# SAME _IMPRESSION_FLOOR the treated page itself must clear. A "control"
# baseline built from noisy, near-zero-signal pages is not a reliable
# comparator and must never be allowed to swing a FAIL verdict -- which
# directly triggers autonomy_state.suspend(), the single most consequential
# action this module can take.
_MIN_RELIABLE_CONTROL_URLS = 2


def _reliable_control_entries(control_set: "list[dict]") -> "list[dict]":
    """Control-set members meeting the SAME impression floor the treated
    page itself must clear, in BOTH windows."""
    return [
        c for c in control_set
        if c["pre_metrics"]["impressions"] >= _IMPRESSION_FLOOR
        and c["post_metrics"]["impressions"] >= _IMPRESSION_FLOOR
    ]


def compute_verdict(
    before_metrics: "dict | None", after_metrics: "dict | None", control_set: "list[dict]",
) -> dict:
    """Pure function (no I/O): returns {"decision": PASS|FAIL|INCONCLUSIVE,
    "reasons": [...], ...delta detail...}. See module docstring for the
    full threshold/control-group design."""
    if before_metrics is None or after_metrics is None:
        return {"decision": "INCONCLUSIVE", "reasons": ["no matched GSC snapshot data in one or both windows"]}

    if before_metrics["impressions"] < _IMPRESSION_FLOOR or after_metrics["impressions"] < _IMPRESSION_FLOOR:
        return {
            "decision": "INCONCLUSIVE",
            "reasons": [f"impressions below the {_IMPRESSION_FLOOR}-impression floor in at least one window"],
        }

    position_delta = _position_delta(before_metrics["position"], after_metrics["position"])
    ctr_delta = _relative_ctr_delta(before_metrics["ctr"], after_metrics["ctr"])

    # Only reliable (>= floor, both windows) control entries may inform the
    # adjustment baseline. Fewer than _MIN_RELIABLE_CONTROL_URLS of them ->
    # no adjustment at all (baseline 0.0) rather than letting a thin or
    # noisy comparator set silently determine the verdict -- the treated
    # page's own (already floor-checked, above) signal is judged on its own
    # merits against the absolute thresholds in that case, exactly as it
    # would be if this hardening had never been added.
    reliable_control = _reliable_control_entries(control_set)
    if len(reliable_control) >= _MIN_RELIABLE_CONTROL_URLS:
        control_position_deltas = [
            _position_delta(c["pre_metrics"]["position"], c["post_metrics"]["position"]) for c in reliable_control
        ]
        control_ctr_deltas = [
            d for d in (
                _relative_ctr_delta(c["pre_metrics"]["ctr"], c["post_metrics"]["ctr"]) for c in reliable_control
            )
            if d is not None
        ]
        control_position_baseline = _median(control_position_deltas) or 0.0
        control_ctr_baseline = _median(control_ctr_deltas) or 0.0
    else:
        control_position_baseline = 0.0
        control_ctr_baseline = 0.0

    # "Excess" degradation: the treated page's own delta beyond what the
    # control group itself experienced over the same period -- isolates a
    # page-specific effect from a site-wide swing/seasonal shift.
    excess_position_degradation = position_delta - control_position_baseline
    excess_ctr_delta = (ctr_delta - control_ctr_baseline) if ctr_delta is not None else None

    reasons: "list[str]" = []
    fail = False
    if excess_position_degradation > _POSITION_DEGRADATION_THRESHOLD * before_metrics["position"]:
        fail = True
        reasons.append(
            f"position degraded {excess_position_degradation:.2f} beyond the control-group baseline "
            f"(> {_POSITION_DEGRADATION_THRESHOLD:.0%} of the pre-change position)"
        )
    if excess_ctr_delta is not None and excess_ctr_delta < -_CTR_DROP_THRESHOLD:
        fail = True
        reasons.append(
            f"CTR dropped {excess_ctr_delta:.1%} beyond the control-group baseline "
            f"(> {_CTR_DROP_THRESHOLD:.0%} relative drop)"
        )

    return {
        "decision": "FAIL" if fail else "PASS",
        "reasons": reasons or ["within thresholds after control-group adjustment"],
        "position_delta": position_delta,
        "ctr_delta": ctr_delta,
        "control_position_baseline": control_position_baseline,
        "control_ctr_baseline": control_ctr_baseline,
        # The RELIABLE count actually used to inform the verdict (0 when
        # fewer than _MIN_RELIABLE_CONTROL_URLS cleared the floor, even if
        # control_set itself was non-empty) -- not the raw input size, so a
        # caller/evidence-reader can tell an unadjusted verdict from an
        # adjusted one at a glance.
        "control_url_count": len(reliable_control),
    }


# ---------------------------------------------------------------------------
# Weekly entry point
# ---------------------------------------------------------------------------


def _parse_iso(value: "str | None") -> "datetime | None":
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _process_one_experiment(change_id: str, entry: dict, *, runner: CommandRunner, now: datetime) -> bool:
    """Advance one experiment's lifecycle by at most one step. Returns True
    if the entry was modified (caller persists). Every internal failure is
    caught and logged -- one broken experiment must never abort the whole
    weekly pass over every other experiment."""
    try:
        status = entry.get("status")

        if status == "awaiting_deploy_confirmation":
            result = check_deploy_confirmed(entry["publish_revision"], runner=runner)
            if result is None or not result.get("confirmed"):
                return False
            confirmed_at = _parse_iso(result.get("completed_at")) or now
            entry["deploy_confirmed_at"] = confirmed_at.isoformat()
            entry["observation_window_end"] = (confirmed_at + timedelta(weeks=_WINDOW_WEEKS)).isoformat()
            entry["status"] = "in_window"
            entry["updated_at"] = _now_iso()
            return True

        if status == "in_window":
            window_end = _parse_iso(entry.get("observation_window_end"))
            if window_end is None or now < window_end + timedelta(days=_DATA_LAG_DAYS):
                return False

            gsc_url = resolve_gsc_url(entry["page_path"])
            if gsc_url is None:
                verdict = {"decision": "INCONCLUSIVE", "reasons": ["page has no matched GSC URL"]}
            else:
                site = _site_from_gsc_url(gsc_url)
                change_time = _parse_iso(entry.get("publish_timestamp")) or now
                after_target = _parse_iso(entry["deploy_confirmed_at"]) + timedelta(days=_DATA_LAG_DAYS)
                before_record = gsc_history.get_url_record_asof(site, gsc_url, change_time, direction="before")
                after_record = gsc_history.get_url_record_asof(site, gsc_url, after_target, direction="after")
                before_metrics = gsc_history.aggregate_metrics(before_record)
                after_metrics = gsc_history.aggregate_metrics(after_record)
                control_set: "list[dict]" = []
                if before_record and after_record:
                    control_set = select_control_set(
                        site, gsc_url, before_record["_snapshot_sha"], after_record["_snapshot_sha"],
                    )
                verdict = compute_verdict(before_metrics, after_metrics, control_set)
                entry["before_metrics"] = before_metrics
                entry["after_metrics"] = after_metrics
                entry["control_url_count"] = verdict.get("control_url_count")

            entry["decision_reasons"] = verdict["reasons"]
            entry["updated_at"] = _now_iso()

            if verdict["decision"] == "INCONCLUSIVE":
                if entry.get("extension_count", 0) < _MAX_EXTENSIONS:
                    entry["extension_count"] = entry.get("extension_count", 0) + 1
                    entry["observation_window_end"] = (window_end + timedelta(weeks=_WINDOW_WEEKS)).isoformat()
                    entry["status"] = "in_window"
                else:
                    entry["decision"] = "INCONCLUSIVE"
                    entry["status"] = "finalized_inconclusive"
                return True

            entry["decision"] = verdict["decision"]
            entry["status"] = "finalized_pass" if verdict["decision"] == "PASS" else "finalized_fail"

            if verdict["decision"] == "FAIL":
                family = entry.get("family")
                mechanism = entry.get("mechanism") or "title_description_writes"
                if family:
                    try:
                        autonomy_state.suspend(
                            family, mechanism,
                            reason=(
                                f"metadata observation FAIL for change {change_id} "
                                f"({entry.get('page_path')}#{entry.get('field')}): "
                                f"{'; '.join(verdict['reasons'])}"
                            ),
                            source_sha=entry.get("publish_revision"),
                        )
                    except Exception:
                        log.warning(
                            "observe_experiments.py: autonomy_state.suspend(%r, %r) failed for change %r",
                            family, mechanism, change_id, exc_info=True,
                        )
            return True

        return False
    except Exception:
        log.warning("observe_experiments.py: _process_one_experiment(%r) failed", change_id, exc_info=True)
        return False


def run_observation_pass(*, runner: CommandRunner = subprocess.run) -> dict:
    """The weekly entry point (Contract H). Advances every open experiment
    by at most one lifecycle step. Always registers a pipeline_state
    heartbeat on completion -- even when there are zero open experiments --
    since `SEO-OBSERVATION-LIVENESS-CHECK` (a separate, dependent card)
    needs a real "last successful run" timestamp to detect this job going
    silently dark. Never raises past this boundary."""
    now = datetime.now(timezone.utc)
    state = load_experiments()
    experiments = state.get("experiments", {})

    processed = 0
    modified = False
    for change_id, entry in experiments.items():
        if entry.get("status") not in _OPEN_STATUSES:
            continue
        if _process_one_experiment(change_id, entry, runner=runner, now=now):
            modified = True
        processed += 1

    if modified:
        _save_atomic(state)

    try:
        pipeline_state.configure(repo_root=REPO_ROOT)
        pipeline_state.record_stage_write("metadata_experiments", path=_STORE_RELPATH)
    except Exception:
        log.warning("observe_experiments.py: pipeline_state registration failed", exc_info=True)

    return {
        "run_at": now.isoformat(),
        "open_experiments_examined": processed,
        "total_experiments": len(experiments),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    summary = run_observation_pass()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
