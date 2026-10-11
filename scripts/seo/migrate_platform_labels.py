"""SEO-SCHEMA-A-WORKFLOW-UPDATE Migration Plan v2: automatic, budget-bounded,
resumable correction of the 896 Schema A entries SEO-SCHEMA-A-BOOTSTRAP-
REGENERATION generated before per-file platform detection existed (Finding
#50 -- most non-.NET entries were labeled ".NET platform" in their Gemini
prompt regardless of the page's real platform).

Runs as its own step inside the weekly seo-keyword-refresh.yml, BEFORE the
routine get_keywords.py refresh, so migration reliably gets its budget
allocation every week rather than being crowded out by routine work. Tracks
progress in a small committed JSON file (data/seo_schema_a_migration_state.json)
so it can safely resume across separate weekly runs without redoing already-
corrected files or losing track of what's left -- this is what lets the
correction run unattended "along with the cron's usual tasks" instead of
needing a human to remember to trigger a one-off --force dispatch.

Reuses get_keywords.py's platform extraction, Gemini call (pacing/retry/
circuit-breaker), and title extraction rather than duplicating them. Uses
replace_keywords_for_entry() (Finding #52), never append_keywords_to_existing()
-- a migration run's whole point is to remove known-wrong keywords, not
union fresh correct ones on top of them.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
from core.env_loader import load_env  # noqa: E402
load_env()

_SEO_SCRIPTS = Path(__file__).resolve().parent
if str(_SEO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SEO_SCRIPTS))
import get_keywords  # noqa: E402

_DEFAULT_STATE_PATH = _REPO_ROOT / "data" / "seo_schema_a_migration_state.json"

# The 12 families SEO-SCHEMA-A-BOOTSTRAP-REGENERATION actually generated
# entries for (Finding #42's 7 quarantine-recovered + Finding #35's 5
# originally-gapped families) -- deliberately NOT all of DEFAULT_FAMILIES.
# Stub-tier / not-yet-launched families have no bootstrap entries to correct.
TARGET_FAMILIES = [
    "tex", "barcode", "page", "font", "note", "html",
    "email", "words", "3d", "cells", "slides", "pdf",
]

_CIRCUIT_BREAKER_CONSECUTIVE_FAILURES = get_keywords._CIRCUIT_BREAKER_CONSECUTIVE_FAILURES


def load_migration_state(state_path):
    state_path = Path(state_path)
    if not state_path.exists():
        return {"target_families": list(TARGET_FAMILIES), "families": {}, "migration_complete": False}
    with open(state_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_migration_state_atomic(state_path, state):
    """Write via a temp file + os.replace so a crash mid-write can never
    leave a partially-written, corrupt state file -- the previous, valid
    state (or no file at all) is always what survives an interruption."""
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(state_path.parent), prefix=".seo_migration_state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, state_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _family_entry(state, family):
    return state.setdefault("families", {}).setdefault(
        family, {"status": "in_progress", "migrated_source_paths": []}
    )


def _iter_family_files(content_sites, family):
    """Yield (file_path, source_path, family_dir) for every real .md file
    under {site}/{family}/ across all given content roots, in sorted
    (deterministic) order."""
    for site in content_sites:
        family_dir = os.path.join(site, family)
        if not os.path.exists(family_dir):
            continue
        for subdir, dirnames, files in os.walk(family_dir):
            dirnames.sort()
            for file in sorted(files):
                if not file.endswith(".md"):
                    continue
                file_path = os.path.join(subdir, file)
                source_path = Path(file_path).resolve().relative_to(_REPO_ROOT).as_posix()
                yield file_path, source_path, family_dir


def migrate_families(target_families, content_sites, output_dir, state_path=None, max_calls=None):
    # SEO-LLM-METRICS-UNIFY (Finding #59): distinguishes migration calls from
    # get_keywords.py's own routine refresh in the shared Gemini metrics
    # ledger -- this module rides along on get_keywords_from_gemini()'s own
    # instrumentation, so only the consumer_id tag needs setting here.
    get_keywords.set_metrics_consumer_id("migrate_platform_labels")
    state_path = state_path or _DEFAULT_STATE_PATH
    state = load_migration_state(state_path)
    state.setdefault("target_families", list(target_families))
    state.setdefault("families", {})

    calls_made = 0
    call_success_count = 0
    call_failure_count = 0
    consecutive_failures = 0
    circuit_tripped = False
    budget_reached = False

    for family in target_families:
        if circuit_tripped or budget_reached:
            break
        fam_state = _family_entry(state, family)
        if fam_state.get("status") == "done":
            continue

        migrated = set(fam_state.get("migrated_source_paths", []))
        all_source_paths_seen = set()

        for file_path, source_path, family_dir in _iter_family_files(content_sites, family):
            all_source_paths_seen.add(source_path)
            if circuit_tripped or budget_reached or source_path in migrated:
                continue

            page_title = get_keywords.extract_head_title(file_path)
            if not page_title:
                continue

            if max_calls is not None and calls_made >= max_calls:
                logging.info(
                    f"Migration call budget ({max_calls}) reached -- stopping cleanly, "
                    f"saving progress made so far."
                )
                budget_reached = True
                continue

            platform = get_keywords._extract_platform_from_path(file_path, family_dir)
            calls_made += 1
            new_keywords = get_keywords.get_keywords_from_gemini(page_title, platform)
            if new_keywords is None:
                call_failure_count += 1
                consecutive_failures += 1
            else:
                call_success_count += 1
                consecutive_failures = 0
                if new_keywords:
                    get_keywords.replace_keywords_for_entry(
                        family, source_path, page_title, new_keywords, output_dir
                    )
                    migrated.add(source_path)

            if consecutive_failures >= _CIRCUIT_BREAKER_CONSECUTIVE_FAILURES:
                logging.error(
                    f"Migration circuit breaker tripped: {consecutive_failures} consecutive "
                    f"page failures -- quota has evidently not recovered. Saving progress "
                    f"made so far and stopping now."
                )
                circuit_tripped = True

        fam_state["migrated_source_paths"] = sorted(migrated)
        if all_source_paths_seen and all_source_paths_seen <= migrated:
            fam_state["status"] = "done"
            fam_state.pop("migrated_source_paths", None)
        else:
            fam_state["status"] = "in_progress"

    state["migration_complete"] = bool(target_families) and all(
        state["families"].get(f, {}).get("status") == "done" for f in target_families
    )
    save_migration_state_atomic(state_path, state)

    total_calls = call_success_count + call_failure_count
    if total_calls:
        summary = (
            f"Migration Gemini calls: {call_success_count} succeeded, "
            f"{call_failure_count} failed ({total_calls} total)."
        )
        logging.info(summary)
        print(summary)
        if circuit_tripped:
            raise SystemExit(
                f"ERROR: migration circuit breaker tripped after "
                f"{_CIRCUIT_BREAKER_CONSECUTIVE_FAILURES} consecutive failures -- quota is "
                f"evidently exhausted for this window. Progress made so far has been saved "
                f"to {state_path}. Resume next run once quota recovers."
            )
        if call_success_count == 0:
            raise SystemExit(
                f"ERROR: all {total_calls} migration Gemini call(s) failed this run -- "
                f"check for a retired model, revoked/exhausted API key, or changed error "
                f"format. Not writing this off as 'no changes'."
            )
        if budget_reached:
            print(
                f"Migration call budget ({max_calls}) reached after {calls_made} call(s) "
                f"this run -- stopping cleanly, not a failure. Progress saved to {state_path}."
            )

    if state.get("migration_complete"):
        print("Schema A platform-label migration complete -- all target families corrected.")

    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "output_dir",
        help="Directory containing per-family keyword JSON files (e.g. keywords/)",
    )
    parser.add_argument(
        "--content-sites",
        required=True,
        help=(
            "Comma-separated content root directories to scan, e.g. "
            "content/kb.aspose.org/en,content/docs.aspose.org/en,content/products.aspose.org/en"
        ),
    )
    parser.add_argument(
        "--families",
        nargs="+",
        default=TARGET_FAMILIES,
        help=f"Target families to migrate (default: the {len(TARGET_FAMILIES)} already-bootstrapped families)",
    )
    parser.add_argument(
        "--state-file",
        default=str(_DEFAULT_STATE_PATH),
        help="Path to the persisted migration progress state file",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help="Migration call budget for this run (unbounded if omitted)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Error: GOOGLE_API_KEY environment variable is not set.")
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    logging.basicConfig(
        filename="migrate_platform_labels.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    content_sites = [s.strip() for s in args.content_sites.split(",") if s.strip()]
    migrate_families(args.families, content_sites, args.output_dir, state_path=args.state_file, max_calls=args.max_calls)
    logging.info("Migration run complete.")
