import argparse
import os

DEFAULT_LOCALES = [
    'de', 'es', 'fr', 'ja', 'ko', 'ru', 'zh', 'ar', 'it', 'pt',
    'pl', 'fa', 'id', 'cs', 'vi', 'tr', 'th', 'sv', 'el', 'uk',
]


def clean_locale_folders(base_path, locales):
    """Traverse and delete files in other locales not present in English."""
    en_path = os.path.join(base_path, 'en')

    if not os.path.exists(en_path):
        print(f"English folder not found: {en_path}")
        return

    # Collect all English files with relative paths
    en_files = set()
    for root, _, files in os.walk(en_path):
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), en_path)
            en_files.add(rel_path)

    # Check each locale and delete files not present in English
    for locale in locales:
        locale_path = os.path.join(base_path, locale)
        if not os.path.exists(locale_path):
            print(f"Locale folder not found, skipping: {locale_path}")
            continue

        for root, _, files in os.walk(locale_path):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), locale_path)
                if rel_path not in en_files:
                    file_to_delete = os.path.join(root, file)
                    os.remove(file_to_delete)
                    print(f"Deleted: {file_to_delete}")

    print("Cleanup complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete locale files that have no corresponding English source."
    )
    parser.add_argument(
        "base_path",
        help="Directory containing 'en/' and locale subdirs (e.g. content/reference.aspose.org/tex)",
    )
    parser.add_argument(
        "--locales",
        nargs="+",
        default=DEFAULT_LOCALES,
        help="Locale codes to check (default: 20 standard locales)",
    )
    args = parser.parse_args()
    clean_locale_folders(args.base_path, args.locales)
