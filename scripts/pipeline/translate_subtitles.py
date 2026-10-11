"""translate_subtitles.py — Translate untranslated subtitle fields in locale _index.md files.

Finds locale family-level _index.md files where subtitle: matches the English source
and translates ONLY the subtitle field, leaving all other content unchanged.

Usage:
    cd <repo_root>
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/translate_subtitles.py
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/translate_subtitles.py --dry-run
    PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/translate_subtitles.py --locale fr,de

FD-LOCALE-001: Addresses 395 locale _index.md files with untranslated subtitle fields.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

# Force UTF-8 output on Windows to handle non-ASCII translations
if hasattr(sys.stdout, "buffer") and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Sites to check (blog has no family-level _index.md)
_SITES = ["docs.aspose.org", "kb.aspose.org", "reference.aspose.org", "products.aspose.org"]

# Locale codes to full language names (used by the translator)
# Based on LOCALE_NAMES in scripts/translator/__init__.py
_LOCALE_NAMES: dict[str, str] = {
    "ar": "Arabic", "bg": "Bulgarian", "ca": "Catalan", "cs": "Czech",
    "da": "Danish", "de": "German", "el": "Greek", "es": "Spanish",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian", "id": "Indonesian",
    "it": "Italian", "ja": "Japanese", "ko": "Korean", "lt": "Lithuanian",
    "lv": "Latvian", "ms": "Malay", "nl": "Dutch", "no": "Norwegian",
    "pl": "Polish", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "sk": "Slovak", "sl": "Slovenian", "sr": "Serbian", "sv": "Swedish",
    "th": "Thai", "tr": "Turkish", "uk": "Ukrainian", "vi": "Vietnamese",
    "zh": "Chinese",
}


def _get_english_subtitle(filepath: Path) -> str:
    """Extract subtitle: field from a file."""
    for line in filepath.read_text(encoding="utf-8").split("\n"):
        if line.startswith("subtitle:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def _set_subtitle(filepath: Path, new_subtitle: str) -> bool:
    """Replace the subtitle: field in a file. Returns True if modified."""
    text = filepath.read_text(encoding="utf-8")
    new_text = re.sub(
        r'^subtitle:\s*.*$',
        f'subtitle: {new_subtitle}',
        text,
        flags=re.MULTILINE,
        count=1,
    )
    if new_text == text:
        return False
    filepath.write_text(new_text, encoding="utf-8")
    return True


def collect_work(locale_filter: list[str] | None) -> dict[str, list[tuple[Path, str]]]:
    """Collect files that need subtitle translation.

    Returns {locale_code: [(filepath, english_subtitle), ...]}
    """
    # First, collect English subtitles per (site, family)
    en_subtitles: dict[tuple[str, str], str] = {}
    for site in _SITES:
        base = _REPO_ROOT / "content" / site / "en"
        if not base.exists():
            continue
        for en_idx in base.glob("*/_index.md"):
            family = en_idx.parent.name
            subtitle = _get_english_subtitle(en_idx)
            if subtitle:
                en_subtitles[(site, family)] = subtitle

    # Find locale files with matching English subtitle (untranslated)
    work: dict[str, list[tuple[Path, str]]] = {}
    for site in _SITES:
        base = _REPO_ROOT / "content" / site
        if not base.exists():
            continue
        for locale_idx in base.glob("*/*/_index.md"):
            parts = locale_idx.parts
            # Expect: content/{site}/{locale}/{family}/_index.md
            locale = parts[-3]
            family = parts[-2]
            if locale == "en":
                continue
            if locale_filter and locale not in locale_filter:
                continue
            key = (site, family)
            en_sub = en_subtitles.get(key, "")
            if not en_sub:
                continue
            current_sub = _get_english_subtitle(locale_idx)
            if current_sub == en_sub:  # still English — needs translation
                if locale not in work:
                    work[locale] = []
                work[locale].append((locale_idx, en_sub))

    return work


def _build_backend():
    """Build the LLM translation backend."""
    sys.path.insert(0, str(_REPO_ROOT))
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    from translator.backends.llm import LLMBackend
    return LLMBackend(model="gpt-oss")


def translate_subtitles(dry_run: bool = False, locale_filter: list[str] | None = None):
    work = collect_work(locale_filter)

    total_files = sum(len(v) for v in work.values())
    print(f"Found {total_files} files with untranslated subtitles across {len(work)} locales")

    if not work:
        print("Nothing to translate.")
        return

    if dry_run:
        print("DRY-RUN: no files will be modified")
        for locale, files in sorted(work.items()):
            print(f"  [{locale}] {len(files)} files")
            for fp, en_sub in files[:3]:
                print(f"    {fp.relative_to(_REPO_ROOT)}: '{en_sub}'")
        return

    backend = _build_backend()
    updated = 0
    errors = 0

    for locale, files in sorted(work.items()):
        lang_name = _LOCALE_NAMES.get(locale, locale.upper())
        print(f"\n[{locale}] Translating {len(files)} subtitles to {lang_name}...")

        # Deduplicate subtitles — many locales share the same English subtitle per family
        unique_subs = list(dict.fromkeys(en_sub for _, en_sub in files))
        try:
            translated = backend.translate_batch(unique_subs, src_lang="en", tgt_lang=locale)
        except Exception as e:
            print(f"  ERROR translating batch for {locale}: {e}")
            errors += len(files)
            continue

        sub_map = dict(zip(unique_subs, translated))

        for fp, en_sub in files:
            new_sub = sub_map.get(en_sub, "")
            if not new_sub:
                print(f"  SKIP {fp.name}: no translation returned")
                errors += 1
                continue
            if new_sub == en_sub:
                print(f"  SKIP {fp.name}: translation equals source (unchanged)")
                continue
            if _set_subtitle(fp, new_sub):
                print(f"  OK {fp.relative_to(_REPO_ROOT)}: '{en_sub}' -> '{new_sub}'")
                updated += 1
            else:
                print(f"  SKIP {fp.name}: subtitle field not found in file")

    print(f"\n=== Summary ===")
    print(f"  Updated: {updated}")
    print(f"  Errors:  {errors}")
    print(f"  Locales: {len(work)}")


def main():
    parser = argparse.ArgumentParser(description="Translate subtitle fields in locale _index.md files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--locale", help="Comma-separated locale codes to process (default: all)")
    args = parser.parse_args()
    locale_filter = [l.strip() for l in args.locale.split(",")] if args.locale else None
    translate_subtitles(dry_run=args.dry_run, locale_filter=locale_filter)


if __name__ == "__main__":
    main()
