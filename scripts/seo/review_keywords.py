import argparse
import json
import logging
import os
import sys
import time
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

# google.generativeai is imported lazily, inside reevaluate_keywords(), not at
# module load time -- see get_keywords.py for the same fix and its rationale.

# Single source of truth for "which families exist" -- see get_keywords.py
# and Finding #32. Falls back to the pre-fix 13-name list if the registry is
# unreadable.
_FALLBACK_FAMILIES = ["barcode", "cad", "cells", "html", "imaging", "ocr", "page", "pdf", "psd", "tasks", "tex", "words", "zip"]
DEFAULT_FAMILIES = canonical_families() or _FALLBACK_FAMILIES


# Merge keywords for duplicate titles
def merge_keywords_by_title(data):
    merged_data = {}
    source_paths = {}
    for entry in data:
        title = entry.get("pageTitle")
        keywords = set(entry.get("keywords", []))
        if not title:
            logging.warning("Skipping entry with missing title.")
            continue
        if title in merged_data:
            merged_data[title].update(keywords)
        else:
            merged_data[title] = keywords
        if entry.get("sourcePath") and title not in source_paths:
            source_paths[title] = entry["sourcePath"]

    result = []
    for title, keywords in merged_data.items():
        record = {"pageTitle": title, "keywords": list(keywords)}
        if title in source_paths:
            record["sourcePath"] = source_paths[title]
        result.append(record)
    return result

# Free-tier Gemini rate limits are as low as 15 RPM (Google AI Studio free
# tier) -- see get_keywords.py's identical constants for the full rationale.
_RPM_PACING_SECONDS = 4.5
_MAX_429_RETRIES = 5
_BACKOFF_BASE_SECONDS = 60


# Get improved keywords from Google Gemini
def reevaluate_keywords(title, keywords, platform="net"):
    import google.generativeai as genai  # lazy: optional heavy dependency

    platform_label = {
        "net": ".NET",
        "java": "Java",
        "python": "Python",
        "cpp": "C++",
        "nodejs": "Node.js",
        "php": "PHP",
    }.get(platform, platform)
    # gemini-1.5-flash was retired (404 as of 2026-07-30, verified against the
    # live API); "-latest" alias tracks Google's current supported flash-lite
    # model without needing another pinned-version update when this one sunsets.
    model = genai.GenerativeModel("gemini-flash-lite-latest")
    prompt = (
        f"The title of the content is: '{title}'.\n\n"
        f"Here is the current list of keywords:\n"
        f"{', '.join(keywords)}\n\n"
        f"Your task is to refine and optimize the list of keywords based on the following instructions:\n"
        f"1. Focus on long-tail keywords specifically related to the {platform_label} platform.\n"
        f"2. Prioritize keywords that are likely to have medium to high relevance and engagement for users.\n"
        f"3. Avoid using keywords that seem overly broad or generic.\n"
        f"4. Remove any keywords that mention brand names other than 'Aspose'.\n"
        f"5. Restrict the final list to 30-50 entries.\n"
        f"6. Return the revised list in plain text format, with one keyword per line.\n\n"
        f"Important: Do not justify your actions or mention limitations. Assume the best possible context and provide your most informed response."
    )
    for attempt in range(1, _MAX_429_RETRIES + 1):
        try:
            response = model.generate_content(prompt)
            keywords_text = response.text
            new_keywords = [kw.strip() for kw in keywords_text.split('\n') if kw.strip()]
            time.sleep(_RPM_PACING_SECONDS)
            return new_keywords
        except Exception as e:
            if "429" in str(e):
                if attempt == _MAX_429_RETRIES:
                    logging.error(
                        f"Rate limit still active for title '{title}' after "
                        f"{_MAX_429_RETRIES} retries -- giving up on this title."
                    )
                    return None
                backoff = _BACKOFF_BASE_SECONDS * attempt
                logging.warning(
                    f"Rate limit reached (attempt {attempt}/{_MAX_429_RETRIES}), "
                    f"pausing for {backoff}s."
                )
                time.sleep(backoff)
            else:
                # None (not the original `keywords`) so the caller can tell a
                # hard failure apart from a genuine "no change needed" result
                # instead of silently rewriting the same keywords back with a
                # misleading "Updated keywords..." log line.
                logging.error(f"Error during reevaluation for title '{title}': {e}")
                return None
    return None  # unreachable, but explicit

# Read and process JSON files
def process_json_files_by_family(families, root_dir, platform="net"):
    call_success_count = 0
    call_failure_count = 0

    for family in families:
        family_file = os.path.join(root_dir, f"{family}.json")
        if not os.path.exists(family_file):
            logging.warning(f"JSON file for family '{family}' does not exist: {family_file}")
            continue

        logging.info(f"Processing family: {family}")
        with open(family_file, 'r', encoding='utf-8') as file:
            try:
                data = json.load(file)
            except json.JSONDecodeError:
                logging.error(f"Invalid JSON in file: {family_file}")
                continue

        # Merge keywords for duplicate titles
        merged_data = merge_keywords_by_title(data)

        # Save the merged data to a new file
        merged_file = os.path.join(root_dir, f"{family}_merged.json")
        with open(merged_file, 'w', encoding='utf-8') as file:
            json.dump(merged_data, file, indent=4, ensure_ascii=False)
        logging.info(f"Saved merged data for family '{family}' to {merged_file}")

        # Process the merged data with AI
        for entry in merged_data:
            title = entry.get("pageTitle")
            keywords = entry.get("keywords", [])
            if not title or not keywords:
                logging.warning(f"Skipping entry due to missing title or keywords: {entry}")
                continue

            logging.info(f"Reevaluating keywords for title: {title}")
            improved_keywords = reevaluate_keywords(title, keywords, platform)
            if improved_keywords is None:
                call_failure_count += 1
                continue
            call_success_count += 1
            entry["keywords"] = improved_keywords

            # Save updated JSON immediately after a valid response
            updated_file = os.path.join(root_dir, f"{family}_updated.json")
            with open(updated_file, 'w', encoding='utf-8') as file:
                json.dump(merged_data, file, indent=4, ensure_ascii=False)
            logging.info(f"Updated keywords for title '{title}' saved to {updated_file}")

    total_calls = call_success_count + call_failure_count
    if total_calls:
        print(
            f"Gemini calls: {call_success_count} succeeded, "
            f"{call_failure_count} failed ({total_calls} total)."
        )
        if call_success_count == 0:
            # Same rationale as get_keywords.py: a 100% failure rate is a
            # systemic problem, not per-title noise -- fail loudly rather
            # than silently produce a run that looks like "nothing to update".
            raise SystemExit(
                f"ERROR: all {total_calls} Gemini call(s) failed for this run -- "
                f"check for a retired model, revoked/exhausted API key, or "
                f"changed error format. Not writing this off as 'no changes'."
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Refine and optimize SEO keyword JSON files using Google Gemini."
    )
    parser.add_argument(
        "keywords_dir",
        help="Directory containing per-family keyword JSON files (e.g. keywords/)",
    )
    parser.add_argument(
        "--families",
        nargs="+",
        default=DEFAULT_FAMILIES,
        help=f"Product families to process (default: {len(DEFAULT_FAMILIES)} families, from data/family_descriptions.json)",
    )
    parser.add_argument(
        "--platform",
        default="net",
        help=(
            "Platform label used in the Gemini reevaluation prompt (e.g. net, java, python, "
            "cpp, nodejs, php). Previously hardcoded to '.NET platform' regardless of the "
            "actual family/platform being reviewed (Finding #33) -- default remains net for "
            "backward compatibility."
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Error: GOOGLE_API_KEY environment variable is not set.")
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    logging.basicConfig(
        filename="keyword_reevaluation.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    process_json_files_by_family(args.families, args.keywords_dir, args.platform)
    logging.info("Keyword reevaluation complete.")
