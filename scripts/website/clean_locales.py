import argparse
import os
import subprocess
import sys

DEFAULT_LOCALES = [
    'de', 'es', 'fr', 'ja', 'ko', 'ru', 'zh', 'ar', 'it', 'pt',
    'pl', 'fa', 'id', 'cs', 'vi', 'tr', 'th', 'sv', 'el', 'uk',
]


def _assert_not_git_tracked(path: str, repo_root: str) -> None:
    """Raise RuntimeError if path is tracked by git.

    Prevents clean_locales.py from silently deleting git-tracked files.
    Such deletions require a Deletion Governance Record (DGR).
    See docs/DELETION_GOVERNANCE.md.
    """
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        raise RuntimeError(
            f"GOVERNANCE BLOCK: '{path}' is git-tracked. "
            "Cannot delete without a DGR. See docs/DELETION_GOVERNANCE.md"
        )


def clean_locale_folders(base_path, locales, dry_run=False):
    """Traverse and delete files in other locales not present in English."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
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
                    try:
                        _assert_not_git_tracked(file_to_delete, repo_root)
                    except RuntimeError as e:
                        print(f"BLOCKED: {e}", file=sys.stderr)
                        sys.exit(2)
                    if dry_run:
                        print(f"[dry-run] Would delete: {file_to_delete}")
                    else:
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print files that would be deleted without actually deleting them",
    )
    args = parser.parse_args()
    clean_locale_folders(args.base_path, args.locales, dry_run=args.dry_run)
