import argparse
import datetime
import json
import logging
import os
import sys
import time
import yaml
from collections import deque
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
from core.env_loader import load_env  # noqa: E402
load_env()

_SEO_SCRIPTS = Path(__file__).resolve().parent
if str(_SEO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SEO_SCRIPTS))
try:
    from seo.pipeline.schema import canonical_families
except ImportError:
    from pipeline.schema import canonical_families

try:
    from seo.pipeline import autonomy_state
except ImportError:
    from pipeline import autonomy_state

# google.generativeai is imported lazily, inside get_keywords_from_gemini(),
# not at module load time. This is an optional, heavy dependency ("Install
# only when SEO features are needed" per scripts/seo/requirements.txt) --
# importing it eagerly meant this module (and its DEFAULT_FAMILIES / dedup
# logic) could never be unit-tested or even imported without it installed.

# Single source of truth for "which families exist": data/family_descriptions.json,
# the same registry 4 Hugo home templates already treat as authoritative. This
# used to be a hardcoded 18-name list that had drifted from review_keywords.py's
# 13 and validate.py's 14 (Finding #32) -- all three now derive from one place.
# Falls back to the pre-fix 18-name list only if the registry can't be read at
# all (e.g. a corrupted checkout), so a missing/broken registry degrades to the
# old behavior instead of silently processing zero families.
_FALLBACK_FAMILIES = [
    "barcode", "cells", "html", "imaging", "ocr", "page", "pdf", "psd", "tasks", "tex", "words", "zip",
    "3d", "cad", "diagram", "email", "note", "slides",
]
DEFAULT_FAMILIES = canonical_families() or _FALLBACK_FAMILIES


# Extract head_title from Markdown file
def extract_head_title(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
        if content.startswith('---'):
            end = content.find('---', 3)
            if end != -1:
                front_matter = content[3:end]
                data = yaml.safe_load(front_matter)
                return data.get('title')
    return None


def _extract_platform_from_path(file_path, family_dir):
    """Derive the real platform from a file's path within its family
    directory, instead of trusting a single CLI-wide --platform flag for
    every file regardless of its actual platform (Finding #50). Content is
    laid out as {family_dir}/{platform}/... consistently across all 3 sites
    (docs/kb/products.aspose.org), confirmed directly against real content
    (cpp, go, java, net, python, rust, typescript). A file directly at
    {family_dir}/_index.md, or any file with no platform subdirectory, is
    inherently cross-platform: returns None so the caller uses
    platform-neutral prompt framing instead of defaulting to one platform.
    """
    rel_parts = Path(file_path).resolve().relative_to(Path(family_dir).resolve()).parts
    if len(rel_parts) <= 1:
        return None
    return rel_parts[0]


def rotate_families_by_iso_week(families, today=None):
    """Rotate family processing order by ISO week number so a fixed
    per-run call budget (--max-calls) doesn't always prioritize the same
    early families, starving later ones over many weekly runs (see
    SEO-SCHEMA-A-WORKFLOW-UPDATE). Deterministic given the same date --
    every run in the same ISO week produces the same order.
    """
    families = list(families)
    if not families:
        return families
    today = today or datetime.date.today()
    iso_week = today.isocalendar()[1]
    rotated = deque(families)
    rotated.rotate(-(iso_week % len(families)))
    return list(rotated)


def _find_entry(data, source_path, title):
    """Find an existing entry for this page by stable identity.

    Matches on `sourcePath` first (the file's repo-relative path -- stable
    across title renames), falling back to exact `pageTitle` match only for
    legacy entries that predate the sourcePath field. Matching on title alone
    was the root cause of Finding #32's orphaned-entry class of bug: when a
    page's head_title changed, the old title stayed in the JSON forever (no
    sourcePath to recognize it as the same page) while a new entry was
    created for the new title -- entries only ever accumulated, never healed.
    """
    for entry in data:
        if source_path and entry.get("sourcePath") == source_path:
            return entry
    for entry in data:
        if "sourcePath" not in entry and entry.get("pageTitle") == title:
            return entry
    return None


# Check if keywords for a page already exist in the JSON file; returns the
# matching entry (or None). Matches by sourcePath first, pageTitle as a
# legacy fallback -- see _find_entry().
def find_existing_entry(family, source_path, title, output_dir):
    file_path = os.path.join(output_dir, f"{family}.json")
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r', encoding='utf-8') as json_file:
        try:
            data = json.load(json_file)
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {file_path}")
            return None
    return _find_entry(data, source_path, title)


# Append new keywords to an existing entry, identified by sourcePath (falling
# back to pageTitle for legacy entries). If the page's title has changed
# since the entry was created, the stored pageTitle is updated in place --
# this is what actually stops a rename from producing an orphaned duplicate.
def append_keywords_to_existing(family, source_path, title, new_keywords, output_dir):
    file_path = os.path.join(output_dir, f"{family}.json")
    if not os.path.exists(file_path):
        return
    with open(file_path, 'r', encoding='utf-8') as json_file:
        try:
            data = json.load(json_file)
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {file_path}")
            return
    entry = _find_entry(data, source_path, title)
    if entry is not None:
        existing_keywords = set(entry.get("keywords", []))
        entry["keywords"] = list(existing_keywords.union(new_keywords))
        if source_path:
            entry["sourcePath"] = source_path
        if entry.get("pageTitle") != title:
            logging.info(f"Title changed for {source_path}: '{entry.get('pageTitle')}' -> '{title}'")
            entry["pageTitle"] = title
    with open(file_path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4, ensure_ascii=False)
    logging.info(f"Appended keywords for {title} in {family}.json")


# Replace (not union) an existing entry's keywords, identified by sourcePath
# (falling back to pageTitle for legacy entries). Finding #52: --force was
# meant to correct entries whose platform label was wrong, but reusing
# append_keywords_to_existing() for that case unioned the freshly-generated
# (correct) keywords with the existing (contaminated, wrong-platform) ones
# instead of removing them -- producing a permanently mixed-platform list,
# not a correction. Use this instead of append_keywords_to_existing() when
# the goal is to REPLACE a known-wrong keyword set, not to accumulate
# variety across genuine re-runs (title-changed) or repeated LLM calls.
def replace_keywords_for_entry(family, source_path, title, new_keywords, output_dir):
    file_path = os.path.join(output_dir, f"{family}.json")
    if not os.path.exists(file_path):
        return
    with open(file_path, 'r', encoding='utf-8') as json_file:
        try:
            data = json.load(json_file)
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {file_path}")
            return
    entry = _find_entry(data, source_path, title)
    if entry is not None:
        entry["keywords"] = list(new_keywords)
        if source_path:
            entry["sourcePath"] = source_path
        entry["pageTitle"] = title
    with open(file_path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=4, ensure_ascii=False)
    logging.info(f"Replaced keywords for {title} in {family}.json")


# Save data grouped by family to JSON file
def save_family_to_json(family, data, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{family}.json")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as json_file:
            try:
                existing_data = json.load(json_file)
                data.extend(existing_data)
                data = {json.dumps(entry, sort_keys=True): entry for entry in data}.values()
            except json.JSONDecodeError:
                logging.error(f"Invalid JSON in file: {file_path}")
    with open(file_path, 'w', encoding='utf-8') as json_file:
        json.dump(list(data), json_file, indent=4, ensure_ascii=False)
    logging.info(f"Saved {family} data to {file_path}")


# Free-tier Gemini rate limits are as low as 15 RPM (Google AI Studio free
# tier). Proactively pacing every call keeps us under that ceiling instead of
# relying solely on reactive 429-retry -- fewer 429s, fewer wasted retries,
# and actual behavior now matches the workflow's own documented assumption
# (90-min timeout / ~1,350 calls => ~4s/call).
_RPM_PACING_SECONDS = 4.5
# Retry-on-429 is now bounded with exponential backoff instead of an
# unbounded `while True` -- an exhausted/revoked trial key should fail this
# one call after a few minutes, not spin sleeping for the entire 90-minute
# workflow timeout.
_MAX_429_RETRIES = 5
_BACKOFF_BASE_SECONDS = 60


# Get keywords from Google Gemini using google.generativeai
def get_keywords_from_gemini(page_title, platform="net"):
    import google.generativeai as genai  # lazy: optional heavy dependency

    if platform is None:
        # Family-root pages (Finding #50) have no single real platform --
        # framing the prompt around one anyway is what produced the
        # ".NET platform" mislabeling on non-.NET pages in the first place.
        platform_phrase = "this product"
    else:
        platform_label = {
            "net": ".NET",
            "java": "Java",
            "python": "Python",
            "cpp": "C++",
            "go": "Go",
            "rust": "Rust",
            "typescript": "TypeScript",
            "nodejs": "Node.js",
            "php": "PHP",
        }.get(platform, platform)
        platform_phrase = f"the {platform_label} platform"
    # gemini-1.5-flash was retired (404 as of 2026-07-30, verified against the
    # live API); "-latest" alias tracks Google's current supported flash-lite
    # model without needing another pinned-version update when this one sunsets.
    model = genai.GenerativeModel("gemini-flash-lite-latest")
    prompt = (
        f"Generate a concise list of SEO keywords for the product page titled '{page_title}'. "
        f"Focus on long tail keywords related to {platform_phrase} having medium to high search volume, and low to medium competition."
        f"Provide only the keywords, with each keyword on a new line, and no additional explanations."
    )
    for attempt in range(1, _MAX_429_RETRIES + 1):
        try:
            response = model.generate_content(prompt)
            keywords_text = response.text
            keywords = [kw.strip() for kw in keywords_text.split('\n') if kw.strip()]
            time.sleep(_RPM_PACING_SECONDS)
            return keywords
        except Exception as e:
            if "429" in str(e):  # Check specifically for rate limit error
                if attempt == _MAX_429_RETRIES:
                    logging.error(
                        f"Rate limit still active for page '{page_title}' after "
                        f"{_MAX_429_RETRIES} retries -- giving up on this page "
                        f"(quota may be exhausted, not just rate-limited)."
                    )
                    return None
                backoff = _BACKOFF_BASE_SECONDS * attempt
                logging.warning(
                    f"Rate limit reached (attempt {attempt}/{_MAX_429_RETRIES}), "
                    f"pausing for {backoff}s."
                )
                time.sleep(backoff)
            else:
                # Not a rate-limit error -- e.g. a retired/renamed model (404),
                # auth failure, or malformed response. Return None (distinct
                # from [] meaning "Gemini genuinely suggested no keywords") so
                # the caller can tell a hard failure apart from a soft empty
                # result and surface a systemic problem loudly instead of
                # silently producing sparse/empty output for an entire run.
                logging.error(f"Error with Gemini API for page '{page_title}': {e}")
                return None
    return None  # unreachable, but explicit


# Consecutive-failure circuit breaker: found live, 2026-07-31/08-01 --
# without this, a sustained quota exhaustion (not a transient blip) meant
# ~8.5 hours and 48 consecutive pages each burning their full 5-attempt,
# ~10-minute backoff before giving up, one page at a time, with zero
# successes the entire time. Per-page bounded retry (Finding #47) was never
# meant to substitute for a whole-run abort signal -- it bounds the cost of
# ONE page, not the cost of grinding through an entire remaining file list
# under a quota that has evidently not recovered.
_CIRCUIT_BREAKER_CONSECUTIVE_FAILURES = 3


# Process Markdown files grouped by families
def process_markdown_files_by_families(
    families, root_dir, output_dir, platform_override=None, force=False, max_calls=None,
):
    """
    platform_override: forces every file to this platform, bypassing
        per-file path detection (Finding #50's fix). None (default) means
        "detect from each file's real path" -- the normal, correct behavior.
        Kept only for the rare case a caller needs to force one platform.
    force: bypass skip-if-unchanged (Finding #51's fix) -- always call
        Gemini even when an existing entry's title hasn't changed. When this
        is what causes an existing entry to be re-processed (title genuinely
        unchanged), the result REPLACES the entry's keywords (Finding #52 --
        a real rename still unions, exactly as before). Useful for ad hoc
        whole-family re-generation; the persistent migration mechanism (see
        migrate_platform_labels.py / SEO-SCHEMA-A-WORKFLOW-UPDATE's Migration
        Plan v2) is the primary way the 896 already-mislabeled entries get
        corrected in production.
    max_calls: stop cleanly (not a failure) once this many real Gemini
        calls have been made this run, saving progress made so far. A
        proactive budget, independent of the reactive circuit breaker.
    """
    family_data = {}
    call_success_count = 0
    call_failure_count = 0
    consecutive_failures = 0
    calls_made = 0
    circuit_tripped = False
    budget_reached = False

    for family in families:
        if circuit_tripped or budget_reached:
            break
        family_dir = os.path.join(root_dir, family)
        if not os.path.exists(family_dir):
            logging.warning(f"Directory for family '{family}' does not exist: {family_dir}")
            continue

        # SEO-AUTONOMY-STATE-MACHINE (Contract I) read-gate: a family not yet
        # AUTONOMOUSLY_ELIGIBLE for schema_a_refresh is skipped, not silently
        # processed. data/seo_autonomy_state.json seeds every canonical
        # family AUTONOMOUSLY_ELIGIBLE for this specific mechanism at build
        # time, reconciling state with the Mission Contract's own
        # pre-existing, already-operator-authorized blanket authorization
        # for this cron (human_authority_boundaries) -- this gate is not a
        # new restriction on production behavior, it is that authorization
        # made mechanically enforceable instead of merely documented.
        if not autonomy_state.is_autonomously_eligible(family, "schema_a_refresh"):
            status = autonomy_state.get_status(family, "schema_a_refresh")
            logging.warning(
                f"Skipping family '{family}': schema_a_refresh autonomy state is "
                f"{status}, not AUTONOMOUSLY_ELIGIBLE"
            )
            continue

        logging.info(f"Processing family: {family}")
        family_data[family] = []

        for subdir, _, files in os.walk(family_dir):
            if circuit_tripped or budget_reached:
                break
            for file in files:
                if not file.endswith('.md'):
                    continue
                file_path = os.path.join(subdir, file)
                source_path = Path(file_path).resolve().relative_to(_REPO_ROOT).as_posix()
                page_title = extract_head_title(file_path)
                if not page_title:
                    continue

                existing = find_existing_entry(family, source_path, page_title, output_dir)
                title_unchanged = existing is not None and existing.get("pageTitle") == page_title
                if title_unchanged and not force:
                    logging.info(f"Skipping (title unchanged): {page_title} (Family: {family})")
                    continue

                if max_calls is not None and calls_made >= max_calls:
                    logging.info(
                        f"Call budget ({max_calls}) reached -- stopping cleanly, "
                        f"saving progress made so far."
                    )
                    budget_reached = True
                    break

                platform = (
                    platform_override
                    if platform_override is not None
                    else _extract_platform_from_path(file_path, family_dir)
                )
                calls_made += 1

                if existing is not None:
                    new_keywords = get_keywords_from_gemini(page_title, platform)
                    if new_keywords is None:
                        call_failure_count += 1
                        consecutive_failures += 1
                    else:
                        call_success_count += 1
                        consecutive_failures = 0
                        if new_keywords:
                            if title_unchanged:
                                # force=True got us here with an unchanged title -- a
                                # genuine forced correction (e.g. Finding #50's platform
                                # migration), not a rename. Replace, don't union: the
                                # existing keywords are the known-wrong ones this call
                                # exists to remove (Finding #52).
                                logging.info(f"Replacing keywords (forced): {page_title} (Family: {family})")
                                replace_keywords_for_entry(family, source_path, page_title, new_keywords, output_dir)
                            else:
                                logging.info(f"Appending keywords: {page_title} (Family: {family})")
                                append_keywords_to_existing(family, source_path, page_title, new_keywords, output_dir)
                else:
                    logging.info(f"Processing new title: {page_title} (Family: {family})")
                    keywords = get_keywords_from_gemini(page_title, platform)
                    if keywords is None:
                        call_failure_count += 1
                        consecutive_failures += 1
                    else:
                        call_success_count += 1
                        consecutive_failures = 0
                        if keywords:
                            family_data[family].append({
                                "pageTitle": page_title,
                                "sourcePath": source_path,
                                "keywords": keywords
                            })

                if consecutive_failures >= _CIRCUIT_BREAKER_CONSECUTIVE_FAILURES:
                    logging.error(
                        f"Circuit breaker tripped: {consecutive_failures} consecutive "
                        f"page failures -- quota has evidently not recovered. Saving "
                        f"progress made so far and stopping the whole run now, rather "
                        f"than grinding through the remaining files one at a time."
                    )
                    circuit_tripped = True
                    break

        save_family_to_json(family, family_data[family], output_dir)

    total_calls = call_success_count + call_failure_count
    if total_calls:
        logging.info(
            f"Gemini calls this run: {call_success_count} succeeded, "
            f"{call_failure_count} failed ({total_calls} total)."
        )
        print(
            f"Gemini calls: {call_success_count} succeeded, "
            f"{call_failure_count} failed ({total_calls} total)."
        )
        if circuit_tripped:
            raise SystemExit(
                f"ERROR: circuit breaker tripped after "
                f"{_CIRCUIT_BREAKER_CONSECUTIVE_FAILURES} consecutive failures "
                f"({call_success_count} succeeded, {call_failure_count} failed before "
                f"stopping) -- quota is evidently exhausted for this window. Progress "
                f"made so far has been saved. Resume later once quota recovers."
            )
        if call_success_count == 0:
            # Every single call failed -- this is a systemic problem (retired
            # model, revoked key, exhausted quota), not per-page noise. Exit
            # non-zero so the workflow's existing
            # `|| echo "WARNING: $site exited non-zero"` step actually fires
            # instead of this run silently reporting "0 keyword changes" and
            # looking identical to a genuinely idempotent, healthy run.
            raise SystemExit(
                f"ERROR: all {total_calls} Gemini call(s) failed for this run -- "
                f"check for a retired model, revoked/exhausted API key, or "
                f"changed error format. Not writing this off as 'no changes'."
            )
        if budget_reached:
            msg = (
                f"Call budget ({max_calls}) reached after {calls_made} call(s) this run -- "
                f"stopping cleanly, not a failure. Progress made so far has been saved. "
                f"Resume next run to continue with the remaining files."
            )
            logging.info(msg)
            print(msg)

    return family_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Generate Schema A SEO keywords for content pages using Google Gemini.\n\n"
            "Pass the root of any content subdirectory as content_dir. Common invocations:\n"
            "  KB pages:       python get_keywords.py content/kb.aspose.org keywords/\n"
            "  Docs pages:     python get_keywords.py content/docs.aspose.org/en keywords/ --platform java\n"
            "  Products pages: python get_keywords.py content/products.aspose.org/en keywords/\n\n"
            "The script walks {content_dir}/{family}/ for each family in --families and\n"
            "appends discovered page titles + LLM-generated keywords to keywords/{family}.json."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "content_dir",
        help=(
            "Root content directory to scan. The script looks for "
            "{content_dir}/{family}/ subdirectories. "
            "E.g. content/kb.aspose.org, content/docs.aspose.org/en, "
            "content/products.aspose.org/en"
        ),
    )
    parser.add_argument(
        "output_dir",
        help="Directory to write per-family keyword JSON files (e.g. keywords/)",
    )
    parser.add_argument(
        "--families",
        nargs="+",
        default=DEFAULT_FAMILIES,
        help=(
            "Product families to process. "
            f"Default: {len(DEFAULT_FAMILIES)} families, from data/family_descriptions.json"
        ),
    )
    parser.add_argument(
        "--platform",
        default=None,
        help=(
            "Force this platform for every file, bypassing automatic per-file path "
            "detection (e.g. net, java, python, cpp, go, rust, typescript). Normally "
            "unnecessary -- the platform is now detected per file from its real path "
            "({family}/{platform}/...), since a single CLI-wide flag applied to every "
            "file regardless of its actual platform was itself a defect (Finding #50). "
            "Only pass this to force one platform for content that doesn't follow the "
            "usual layout."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Bypass skip-if-unchanged (Finding #51) and call Gemini for every page, "
            "even when an existing entry's title hasn't changed. Needed once for the "
            "migration pass that corrects already-mislabeled entries after the platform "
            "detection fix lands; not needed for routine weekly runs."
        ),
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help=(
            "Stop cleanly (not a failure) once this many real Gemini calls have been "
            "made this run, saving progress made so far. A proactive budget, independent "
            "of the reactive circuit breaker -- keeps a single run well inside the real, "
            "empirically-tight quota ceiling discovered in the bootstrap regeneration."
        ),
    )
    parser.add_argument(
        "--rotate-weekly",
        action="store_true",
        help=(
            "Rotate --families processing order by the current ISO week number, so a "
            "fixed per-run call budget doesn't always prioritize the same early families "
            "over many weekly runs. Intended for the scheduled weekly workflow, not "
            "one-off manual/migration invocations where explicit family order matters."
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Error: GOOGLE_API_KEY environment variable is not set.")
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    logging.basicConfig(
        filename="process_log.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    families = rotate_families_by_iso_week(args.families) if args.rotate_weekly else args.families

    process_markdown_files_by_families(
        families, args.content_dir, args.output_dir,
        platform_override=args.platform, force=args.force, max_calls=args.max_calls,
    )
    logging.info("Processing complete.")
