"""SEO-TITLE-PILOT-OBSERVATION-MEASURE (F5) / Contract H data source.

Real Google Search Console demand data (Schema B, per
``scripts/seo/pipeline/schema.py``) lives in ``keywords/{site}.aspose.org.json``,
refreshed weekly by the ``GSC Query Collector`` workflow. Per the mission plan's
own Context table, every commit to one of these files is a real snapshot, so
``git log -p -- keywords/<site>.json`` is a weekly time series. This module
reads that time series directly from git history -- no live GSC API access is
needed to compute a real before/after comparison around a past date.

Doctrine (already encoded in every other consumer): a query proves demand,
never truth; a URL absent from a snapshot means no data was collected for it
that week, never that it had zero impressions -- callers must preserve that
distinction (``get_url_record_asof`` returns ``None`` for "not observed",
distinct from a record with ``agg.impressions == 0`` which cannot occur in
real GSC exports but is handled the same way defensively).

This module is read-only: it never runs the collector and never writes
``keywords/``. It is the shared data-access layer this card
(``SEO-TITLE-PILOT-OBSERVATION-MEASURE``) uses to build
``reports/seo/pilot_observation_2026-09.json``, and that
``SEO-METADATA-OBSERVATION-LOOP`` (Contract H) is designed to reuse for every
future applied metadata change's observation window.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT

SCHEMA_B_SITES = ("www", "products", "reference", "websites", "docs", "blog", "kb")


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override the module-level repo root for testing."""
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


class GscHistoryError(Exception):
    """Base class for gsc_history errors."""


def _keywords_relpath(site: str) -> str:
    return f"keywords/{site}.aspose.org.json"


def _run_git(args: list[str]) -> bytes:
    """Run git and return raw stdout bytes (never text=True -- decoding
    subprocess output with the platform locale codepage instead of UTF-8
    silently corrupts non-ASCII bytes; a real bug of exactly this shape was
    caught by independent review earlier in this mission)."""
    result = subprocess.run(
        ["git", *args], capture_output=True, check=True, cwd=REPO_ROOT
    )
    return result.stdout


def list_snapshot_commits(site: str) -> list[dict[str, Any]]:
    """Every commit that touched this site's Schema B file, oldest first,
    as ``[{"sha": str, "date": datetime}]``. Uses the commit's own author
    date (the collector's real weekly-Sunday commits), not commit date,
    since a later rebase/cherry-pick could change the latter without
    changing when the data was actually collected.
    """
    relpath = _keywords_relpath(site)
    out = _run_git(
        ["log", "--follow", "--format=%H|%aI", "--reverse", "--", relpath]
    ).decode("utf-8")
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, iso_date = line.split("|", 1)
        commits.append({"sha": sha, "date": datetime.fromisoformat(iso_date)})
    return commits


def load_snapshot(site: str, sha: str) -> list[dict[str, Any]]:
    """Parse the Schema B JSON list for `site` as it existed at commit `sha`."""
    relpath = _keywords_relpath(site)
    out = _run_git(["show", f"{sha}:{relpath}"])
    data = json.loads(out.decode("utf-8"))
    if not isinstance(data, list):
        raise GscHistoryError(f"{site}@{sha}: expected a JSON array, got {type(data)}")
    return data


def find_snapshot_asof(
    site: str, target_date: datetime, direction: str = "before"
) -> "dict[str, Any] | None":
    """The nearest real snapshot commit to `target_date`.

    direction="before": the latest snapshot committed on or before
    target_date (a "pre" baseline). direction="after": the earliest
    snapshot committed on or after target_date (a "post" measurement).
    Returns None if no such snapshot exists in either direction (e.g.
    target_date predates the collector's first run, or is more recent than
    its latest run).
    """
    if direction not in ("before", "after"):
        raise GscHistoryError(f"direction must be 'before' or 'after', got {direction!r}")
    commits = list_snapshot_commits(site)
    if target_date.tzinfo is None:
        target_date = target_date.replace(tzinfo=timezone.utc)
    # Both directions are inclusive of an exact match, matching this
    # docstring's own "on or before" / "on or after" language -- found live
    # (SEO-GSC-HISTORY-ASOF-BOUNDARY-RESOLVER-1) as an asymmetry where
    # direction="after" silently used a strict `>` (via `(date <= target) ==
    # (direction == "before")`, which resolves to `date > target` when
    # direction != "before"), excluding a commit whose timestamp exactly
    # equalled target_date. Written as two explicit branches rather than the
    # earlier boolean-equality one-liner so the intended inclusive boundary
    # on each side is visible at the call site, not just in the docstring.
    if direction == "before":
        candidates = [c for c in commits if c["date"] <= target_date]
    else:
        candidates = [c for c in commits if c["date"] >= target_date]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["date"]) if direction == "before" else min(
        candidates, key=lambda c: c["date"]
    )


def get_url_record_asof(
    site: str, url: str, target_date: datetime, direction: str = "before"
) -> "dict[str, Any] | None":
    """The Schema B record for `url` in the nearest snapshot in that
    direction. Returns None if no snapshot exists in that direction, or the
    snapshot exists but does not contain `url` -- both are "no data
    observed", never conflated with a genuine zero.
    """
    snapshot = find_snapshot_asof(site, target_date, direction)
    if snapshot is None:
        return None
    records = load_snapshot(site, snapshot["sha"])
    for record in records:
        if record.get("url") == url:
            return {**record, "_snapshot_sha": snapshot["sha"], "_snapshot_date": snapshot["date"].isoformat()}
    return None


def aggregate_metrics(record: "dict[str, Any] | None") -> "dict[str, Any] | None":
    """Roll up a Schema B record's per-query rows into one summary:
    total clicks, total impressions, impression-weighted average position,
    and overall CTR. Returns None for a missing record or one with zero
    impressions (nothing to weight an average by) -- never a fabricated 0.
    """
    if record is None:
        return None
    queries = record.get("queries") or []
    total_impressions = sum(q.get("impressions", 0) or 0 for q in queries)
    if total_impressions <= 0:
        return None
    total_clicks = sum(q.get("clicks", 0) or 0 for q in queries)
    weighted_position_sum = sum(
        (q.get("position", 0) or 0) * (q.get("impressions", 0) or 0) for q in queries
    )
    return {
        "clicks": total_clicks,
        "impressions": total_impressions,
        "ctr": total_clicks / total_impressions,
        "position": weighted_position_sum / total_impressions,
        "query_count": len(queries),
        "snapshot_sha": record.get("_snapshot_sha"),
        "snapshot_date": record.get("_snapshot_date"),
    }
