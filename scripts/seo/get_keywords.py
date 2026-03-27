import argparse
import json
import logging
import os
import time
import yaml

import google.generativeai as genai

DEFAULT_FAMILIES = [
    # KB-oriented families (original)
    "barcode", "cells", "html", "imaging", "ocr", "page", "pdf", "psd", "tasks", "tex", "words", "zip",
    # Extended families (docs/products/reference content)
    "3d", "cad", "diagram", "email", "note", "slides",
]


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

# Check if keywords for a title exist in the JSON file
def keywords_exist_in_json(family, title, output_dir):
    file_path = os.path.join(output_dir, f"{family}.json")
    if not os.path.exists(file_path):
        return False
    with open(file_path, 'r', encoding='utf-8') as json_file:
        try:
            data = json.load(json_file)
            for entry in data:
                if "pageTitle" in entry and entry["pageTitle"] == title:
                    return True
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {file_path}")
    return False


# Append new keywords to existing entry in JSON file
def append_keywords_to_existing(family, title, new_keywords, output_dir):
    file_path = os.path.join(output_dir, f"{family}.json")
    if not os.path.exists(file_path):
        return
    with open(file_path, 'r', encoding='utf-8') as json_file:
        try:
            data = json.load(json_file)
            for entry in data:
                if entry["pageTitle"] == title:
                    existing_keywords = set(entry.get("keywords", []))
                    updated_keywords = list(existing_keywords.union(new_keywords))
                    entry["keywords"] = updated_keywords
                    break
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {file_path}")
            return
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

# Get keywords from Google Gemini using google.generativeai
def get_keywords_from_gemini(page_title):
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = (
        f"Generate a concise list of SEO keywords for the product page titled '{page_title}'. "
        f"Focus on long tail keywords related to .NET platform having medium to high search volume, and low to medium competition."
        f"Provide only the keywords, with each keyword on a new line, and no additional explanations."
    )
    while True:
        try:
            response = model.generate_content(prompt)
            keywords_text = response.text
            keywords = [kw.strip() for kw in keywords_text.split('\n') if kw.strip()]
            return keywords
        except Exception as e:
            if "429" in str(e):  # Check specifically for rate limit error
                logging.warning("Rate limit reached, pausing for 1 minute.")
                time.sleep(60)  # Wait for 1 minute
            else:
                logging.error(f"Error with Gemini API for page '{page_title}': {e}")
                return []

# Process Markdown files grouped by families
def process_markdown_files_by_families(families, root_dir, output_dir):
    family_data = {}
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
                    page_title = extract_head_title(file_path)
                    if page_title:
                        if keywords_exist_in_json(family, page_title, output_dir):
                            logging.info(f"Appending keywords: {page_title} (Family: {family})")
                            new_keywords = get_keywords_from_gemini(page_title)
                            if new_keywords:
                                append_keywords_to_existing(family, page_title, new_keywords, output_dir)
                            continue

                        logging.info(f"Processing new title: {page_title} (Family: {family})")
                        keywords = get_keywords_from_gemini(page_title)
                        if keywords:
                            family_data[family].append({
                                "pageTitle": page_title,
                                "keywords": keywords
                            })

        save_family_to_json(family, family_data[family], output_dir)

    return family_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Generate Schema A SEO keywords for content pages using Google Gemini.\n\n"
            "Pass the root of any content subdirectory as content_dir. Common invocations:\n"
            "  KB pages:       python get_keywords.py content/kb.aspose.org keywords/\n"
            "  Docs pages:     python get_keywords.py content/docs.aspose.org/en keywords/\n"
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
            f"Default: {len(DEFAULT_FAMILIES)} families "
            "(barcode, cells, html, imaging, ocr, page, pdf, psd, tasks, tex, words, zip, "
            "3d, cad, diagram, email, note, slides)"
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Error: GOOGLE_API_KEY environment variable is not set.")
    genai.configure(api_key=api_key)

    logging.basicConfig(
        filename="process_log.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    process_markdown_files_by_families(args.families, args.content_dir, args.output_dir)
    logging.info("Processing complete.")
