"""SEO-STATE-MANIFEST (Finding #60): a purely additive index of every SEO
pipeline stage's state-file output.

Every existing ``reports/seo/*.json``, ``patches/seo/patch_manifest.json``,
and ``data/seo_schema_a_migration_state.json`` file keeps its exact current
shape, location, and consumer -- this module never reads or reshapes any of
them. It only records WHEN a stage last wrote its output (timestamp, sha256,
size), so a future health/staleness view (``SEO-HEALTH-SUMMARY``) or a
content-stable cache (``SEO-RECOMMENDATION-MEMORY``) has one place to check
"is this state fresh?" without re-deriving each stage's own notion of
freshness.

``STAGE_REGISTRY`` maps every real, currently-existing SEO pipeline
state-file output to a relative path, verified live against each producing
script's own source (2026-09-06). ``frontmatter_grounding.py`` is
deliberately absent: it is a read-only library with no ``main()`` and no
file write anywhere in it (confirmed by inspection) -- it produces nothing
for this manifest to index.

No backfill: ``load_pipeline_state()`` bootstraps an empty
``{"schema_version": 1, "stages": {}}`` shape when the manifest file does
not exist yet, and each stage entry is filled in only by a real future call
to ``record_stage_write()`` -- never synthesized retroactively from a file's
current on-disk mtime, which would misrepresent a pre-existing file as
"written by this mechanism." Per the mission's own integration order, each
dependent card (``SEO-RECOMMENDATION-MEMORY``, ``SEO-HEALTH-SUMMARY``,
``SEO-METADATA-OBSERVATION-LOOP``) wires its own ``record_stage_write()``
call from within its own ``allowed_paths`` as it is built; this card's own
``allowed_paths`` covers only this module, its own output file, and its
tests -- not the 12 producer scripts a full future wiring pass would touch.

``record_stage_write()`` never raises: a metrics/index-recording failure
must never block the real pipeline work it is observing, mirroring the
same non-fatal discipline this mission already established for
``scripts/seo/llm_metrics_adapter.py`` (SEO-LLM-METRICS-UNIFY).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_THIS_FILE = Path(__file__).resolve()
_DEFAULT_REPO_ROOT = _THIS_FILE.parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT

SCHEMA_VERSION = 1

# stage_key -> path relative to the repo root, one entry per real,
# currently-existing SEO pipeline state-file producer.
STAGE_REGISTRY: dict[str, str] = {
    "page_index": "reports/seo/page_index.json",                       # inventory.py
    "opportunities": "reports/seo/opportunities.json",                 # analyze.py / recommend.py
    "gap_summary": "reports/seo/seo_gap_summary.json",                 # analyze.py
    "validation_report": "reports/seo/validation_report.json",         # validate.py
    "recommendations": "reports/seo/recommendations.json",             # recommend.py
    "safe_recommendations": "reports/seo/safe_recommendations.json",   # safety.py
    "rejected": "reports/seo/rejected.json",                           # safety.py
    "safety_summary": "reports/seo/safety_summary.json",               # safety.py
    "report_summary": "reports/seo/summary.md",                        # report.py
    "report_low_priority_summary": "reports/seo/low_priority_summary.md",  # report.py
    "patch_manifest": "patches/seo/patch_manifest.json",               # apply.py
    "keyword_gap_report": "reports/seo/keyword_gap_report.json",       # keyword_gap_report.py
    "title_consistency_report": "reports/seo/title_consistency_report.json",  # title_consistency_evaluator.py
    "schema_a_stale_audit": "reports/seo/schema_a_stale_audit.json",   # audit_schema_a.py
    "weekly_analysis_summary": "reports/seo/weekly_analysis_summary.json",  # weekly_analysis.py
    "schema_a_migration_state": "data/seo_schema_a_migration_state.json",  # migrate_platform_labels.py
}

_MANIFEST_RELPATH = "reports/seo/pipeline_state.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override the module-level repo root for testing."""
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def _manifest_path() -> Path:
    return REPO_ROOT / _MANIFEST_RELPATH


def load_pipeline_state() -> dict[str, Any]:
    """The current manifest, or a bootstrap-empty shape if none exists yet."""
    path = _manifest_path()
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "stages": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, json.JSONDecodeError):
        log.warning("pipeline_state.py: failed to read %s; treating as empty", path, exc_info=True)
        return {"schema_version": SCHEMA_VERSION, "stages": {}}


def _sha256_and_size(path: Path) -> "tuple[str, int] | tuple[None, None]":
    try:
        data = path.read_bytes()
    except OSError:
        return None, None
    return hashlib.sha256(data).hexdigest(), len(data)


def _save_atomic(path: Path, state: dict[str, Any]) -> None:
    """Write via a temp file + os.replace so a crash mid-write can never
    leave a partially-written, corrupt manifest -- mirrors the exact
    pattern already established by migrate_platform_labels.py's
    save_migration_state_atomic()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".seo_pipeline_state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def record_stage_write(stage_key: str, *, path: "Path | str | None" = None, extra: "dict[str, Any] | None" = None) -> bool:
    """Record that `stage_key` just wrote its output. Purely additive: only
    the named stage's entry changes, every other stage's entry is preserved
    byte-for-byte. Never raises -- a failure here must never block the real
    pipeline stage that called it; returns False on any failure instead.
    """
    try:
        relpath = str(path) if path is not None else STAGE_REGISTRY.get(stage_key)
        if relpath is None:
            log.warning("pipeline_state.py: unknown stage_key %r with no path given; not recorded", stage_key)
            return False
        target = REPO_ROOT / relpath if not Path(relpath).is_absolute() else Path(relpath)
        sha256, size_bytes = _sha256_and_size(target)
        entry = {
            "path": relpath,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "sha256": sha256,
            "size_bytes": size_bytes,
        }
        if extra:
            entry["extra"] = extra
        state = load_pipeline_state()
        state.setdefault("schema_version", SCHEMA_VERSION)
        state.setdefault("stages", {})[stage_key] = entry
        _save_atomic(_manifest_path(), state)
        return True
    except Exception:
        log.warning("pipeline_state.py: record_stage_write(%r) failed", stage_key, exc_info=True)
        return False
