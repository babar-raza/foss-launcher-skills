import argparse
import json
import logging
import os
import sys
import time
import yaml
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
        f"Generate a concise list of SEO keywords for the product page titled '{page_title}'. "
        f"Focus on long tail keywords related to the {platform_label} platform having medium to high search volume, and low to medium competition."
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


# Process Markdown files grouped by families
def process_markdown_files_by_families(families, root_dir, output_dir, platform="net"):
    family_data = {}
    call_success_count = 0
    call_failure_count = 0

    for family in families:
        family_dir = os.path.join(root_dir, family)
        if not os.path.exists(family_dir):
            logging.warning(f"Directory for family '{family}' does not exist: {family_dir}")
            continue

        logging.info(f"Processing family: {family}")
        family_data[family] = []

        for subdir, _, files in os.walk(family_dir):
            for file in files:
                if file.endswith('.md'):
                    file_path = os.path.join(subdir, file)
                    source_path = Path(file_path).resolve().relative_to(_REPO_ROOT).as_posix()
                    page_title = extract_head_title(file_path)
                    if page_title:
                        existing = find_existing_entry(family, source_path, page_title, output_dir)
                        if existing is not None:
                            logging.info(f"Appending keywords: {page_title} (Family: {family})")
                            new_keywords = get_keywords_from_gemini(page_title, platform)
                            if new_keywords is None:
                                call_failure_count += 1
                            else:
                                call_success_count += 1
                                if new_keywords:
                                    append_keywords_to_existing(family, source_path, page_title, new_keywords, output_dir)
                            continue

                        logging.info(f"Processing new title: {page_title} (Family: {family})")
                        keywords = get_keywords_from_gemini(page_title, platform)
                        if keywords is None:
                            call_failure_count += 1
                        else:
                            call_success_count += 1
                            if keywords:
                                family_data[family].append({
                                    "pageTitle": page_title,
                                    "sourcePath": source_path,
                                    "keywords": keywords
                                })

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
        default="net",
        help=(
            "Platform label used in the Gemini prompt (e.g. net, java, python, cpp, nodejs, php). "
            "Previously hardcoded to '.NET platform' regardless of the actual content being "
            "scanned (Finding #33) -- default remains net for backward compatibility."
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

    process_markdown_files_by_families(args.families, args.content_dir, args.output_dir, args.platform)
    logging.info("Processing complete.")
