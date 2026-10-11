#!/usr/bin/env python3
"""
Migrate all _index.*.md homepage translation files to use dynamic platform suffixes.

For each file:
1. Add platform_suffix / platform_conjunction / platform_pair after coming_soon_subtitle
2. For each launched-product item (cells, email, 3d, slides, note):
   - Rename 'description:' → 'base_description:'
   - Strip trailing "Available for..." sentence (contains platform names)
"""

import re
import os
import sys

CONTENT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "content", "www.aspose.org")

# Launched products whose descriptions need stripping
LAUNCHED_FAMILIES = {"cells", "email", "3d", "slides", "note"}

# Platform names as they appear in all language strings (they stay as proper nouns)
PLATFORM_NAMES = r"Python|\.NET|Java|C\+\+|TypeScript|JavaScript|Node\.js|Go|PHP|Ruby"

# i18n fields per language code
# Format: (platform_suffix, platform_conjunction, platform_pair)
LANG_I18N = {
    "ar": ('متاح لـ %s.', '، و', ' و'),
    "bg": ('Налично за %s.', ', и ', ' и '),
    "ca": ('Disponible per a %s.', ', i ', ' i '),
    "cs": ('K dispozici pro %s.', ', a ', ' a '),
    "da": ('Tilgængelig for %s.', ', og ', ' og '),
    "de": ('Verfügbar für %s.', ', und ', ' und '),
    "el": ('Διαθέσιμο για %s.', ', και ', ' και '),
    "es": ('Disponible para %s.', ', y ', ' y '),
    "fa": ('موجود برای %s.', '، و ', ' و '),
    "fi": ('Saatavilla kohteelle %s.', ', ja ', ' ja '),
    "fr": ('Disponible pour %s.', ', et ', ' et '),
    "he": ('זמין עבור %s.', ', ו-', ' ו-'),
    "hi": ('%s के लिए उपलब्ध।', ', और ', ' और '),
    "hr": ('Dostupno za %s.', ', i ', ' i '),
    "hu": ('Elérhető a következőhöz: %s.', ', és ', ' és '),
    "id": ('Tersedia untuk %s.', ', dan ', ' dan '),
    "it": ('Disponibile per %s.', ', e ', ' e '),
    "ja": ('%sで利用可能。', '、および', 'および'),
    "ko": ('%s에서 사용 가능합니다.', ', 및 ', ' 및 '),
    "lt": ('Prieinama %s.', ', ir ', ' ir '),
    "lv": ('Pieejams priekš %s.', ', un ', ' un '),
    "ms": ('Tersedia untuk %s.', ', dan ', ' dan '),
    "nl": ('Beschikbaar voor %s.', ', en ', ' en '),
    "no": ('Tilgjengelig for %s.', ', og ', ' og '),
    "pl": ('Dostępne dla %s.', ', i ', ' i '),
    "pt": ('Disponível para %s.', ', e ', ' e '),
    "ro": ('Disponibil pentru %s.', ', și ', ' și '),
    "ru": ('Доступно для %s.', ', и ', ' и '),
    "sk": ('Dostupné pre %s.', ', a ', ' a '),
    "sr": ('Dostupno za %s.', ', и ', ' и '),
    "sv": ('Tillgänglig för %s.', ', och ', ' och '),
    "th": ('พร้อมใช้งานสำหรับ %s.', ', และ ', ' และ '),
    "tr": ('%s için kullanılabilir.', ', ve ', ' ve '),
    "uk": ('Доступно для %s.', ', та ', ' та '),
    "vi": ('Khả dụng cho %s.', ', và ', ' và '),
    "zh": ('适用于%s。', '、', '和'),
}


def strip_platform_sentence(text: str) -> str:
    """
    Strip the final sentence containing platform names from a description.
    Handles various Unicode sentence terminators (. 。 । ۔).
    """
    # Match last sentence fragment that contains a platform name.
    # The sentence may start with any non-sentence-ending chars.
    pattern = rf'\s+[^.。।۔]*(?:{PLATFORM_NAMES})[^.。।۔]*[.。।۔]\s*$'
    stripped = re.sub(pattern, '', text, flags=re.DOTALL)
    return stripped.rstrip()


def add_platform_fields(content: str, lang: str) -> str:
    """
    Insert platform_suffix / platform_conjunction / platform_pair after
    the 'coming_soon_subtitle:' line in the products block.
    """
    suffix, conjunction, pair = LANG_I18N.get(lang, ("Available for %s.", ", and ", " and "))

    # Escape any double-quotes in values
    suffix_escaped = suffix.replace('"', '\\"')
    conjunction_escaped = conjunction.replace('"', '\\"')
    pair_escaped = pair.replace('"', '\\"')

    new_fields = (
        f'  platform_suffix: "{suffix_escaped}"\n'
        f'  platform_conjunction: "{conjunction_escaped}"\n'
        f'  platform_pair: "{pair_escaped}"\n'
    )

    # Insert after the coming_soon_subtitle line (handles both quoted and unquoted values)
    pattern = r'(  coming_soon_subtitle:.*\n)'
    replacement = r'\1' + new_fields
    result = re.sub(pattern, replacement, content, count=1)
    return result


def rename_description_for_launched(content: str) -> str:
    """
    For each launched-family item block, rename 'description:' to 'base_description:'
    and strip the trailing platform sentence.

    We detect launched-family blocks by finding 'family: <name>' within an item,
    then finding the next 'description:' line within the same item block.
    """
    lines = content.split('\n')
    result = []
    i = 0
    current_family = None
    in_items = False

    while i < len(lines):
        line = lines[i]

        # Track when we enter the items block
        if re.match(r'\s+items:', line):
            in_items = True

        # Detect family within item
        if in_items:
            m = re.match(r'\s+family:\s+(\S+)', line)
            if m:
                current_family = m.group(1).strip('"\'')

        # Rename description → base_description for launched families and strip platform sentence
        if in_items and current_family in LAUNCHED_FAMILIES:
            m = re.match(r'(\s+)(description:\s+)(.*)', line, re.DOTALL)
            if m:
                indent = m.group(1)
                value_raw = m.group(3)

                # Handle multi-line quoted values (unlikely but safe)
                # Strip trailing platform sentence from single-line value
                value = value_raw.strip()
                cleaned = strip_platform_sentence(value)

                result.append(f'{indent}base_description: {cleaned}')
                i += 1
                continue

        # Default: keep line as-is
        result.append(line)
        i += 1

    return '\n'.join(result)


def migrate_file(filepath: str, lang: str) -> bool:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # Step 1: add platform i18n fields
    content = add_platform_fields(content, lang)

    # Step 2: rename description → base_description for launched families
    content = rename_description_for_launched(content)

    if content == original:
        print(f"  SKIP (no changes): {os.path.basename(filepath)}")
        return False

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  OK: {os.path.basename(filepath)}")
    return True


def main():
    print("Migrating homepage translation files...")
    count = 0
    for filename in sorted(os.listdir(CONTENT_DIR)):
        if not filename.startswith('_index.') or not filename.endswith('.md'):
            continue
        # Extract language code: _index.de.md → de
        parts = filename.split('.')
        if len(parts) != 3:
            continue
        lang = parts[1]
        if lang == 'md':
            continue  # skip _index.md (already done manually)

        filepath = os.path.join(CONTENT_DIR, filename)
        if migrate_file(filepath, lang):
            count += 1

    print(f"\nDone. {count} files updated.")


if __name__ == '__main__':
    main()
