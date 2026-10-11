import re, pathlib

base = pathlib.Path('d:/onedrive/Documents/GitHub/aspose.org')

locales_prod = sorted([
    p for p in base.glob('content/products.aspose.org/*/slides/python/_index.md')
    if '/en/' not in str(p).replace('\\', '/')
])

prod_results = []

for path in locales_prod:
    locale = path.parts[path.parts.index('products.aspose.org') + 1]
    text = path.read_text(encoding='utf-8')
    orig = text
    patches_applied = []
    patches_not_found = []

    # ------------------------------------------------------------------
    # Patch 2a: slides.export.SaveFormat.PPTX -> SaveFormat.PPTX
    # ------------------------------------------------------------------
    if 'slides.export.SaveFormat.PPTX' in text:
        text = text.replace('slides.export.SaveFormat.PPTX', 'SaveFormat.PPTX')
        patches_applied.append('SaveFormat_fix')
    else:
        patches_not_found.append('slides.export.SaveFormat.PPTX_not_found')

    # ------------------------------------------------------------------
    # Patch 2b: Add SaveFormat import to python code blocks that use SaveFormat
    # ------------------------------------------------------------------
    IMPORT_LINE = 'from aspose.slides_foss.export import SaveFormat'

    def fix_saveformat_import(m):
        block = m.group(0)
        if 'SaveFormat.PPTX' in block and IMPORT_LINE not in block:
            if 'import aspose.slides_foss as slides\n' in block:
                block = block.replace(
                    'import aspose.slides_foss as slides\n',
                    'import aspose.slides_foss as slides\n' + IMPORT_LINE + '\n',
                    1
                )
            elif 'from aspose.slides_foss import' in block:
                lines = block.split('\n')
                insert_at = None
                for i, l in enumerate(lines):
                    if l.strip().startswith('from aspose.slides_foss import') or l.strip().startswith('import aspose.slides_foss'):
                        insert_at = i + 1
                if insert_at is not None:
                    lines.insert(insert_at, IMPORT_LINE)
                    block = '\n'.join(lines)
        return block

    new_text, n_subs = re.subn(
        r'```python\n.*?```',
        fix_saveformat_import,
        text,
        flags=re.DOTALL
    )
    if new_text != text:
        text = new_text
        patches_applied.append('SaveFormat_import_added_codeblock')
    elif 'SaveFormat.PPTX' in text and IMPORT_LINE not in text:
        # Try inline YAML: escaped \n sequences
        if 'import aspose.slides_foss as slides\\n' in text and IMPORT_LINE not in text:
            text = text.replace(
                'import aspose.slides_foss as slides\\n',
                'import aspose.slides_foss as slides\\n' + IMPORT_LINE + '\\n',
                1
            )
            patches_applied.append('SaveFormat_import_added_inline')
        else:
            patches_not_found.append('SaveFormat_import_location_unknown')
    else:
        if IMPORT_LINE in text:
            patches_not_found.append('SaveFormat_import_already_present')
        else:
            patches_not_found.append('SaveFormat_import_no_SaveFormat_in_file')

    # ------------------------------------------------------------------
    # Patch 2c: Add fill_type = FillType.SOLID before portion color line
    # ------------------------------------------------------------------
    TARGET_COLOR = 'portion.portion_format.fill_format.solid_fill_color.color'
    TARGET_FILL = 'portion.portion_format.fill_format.fill_type = FillType.SOLID'

    if TARGET_COLOR in text:
        if TARGET_FILL not in text:
            lines = text.split('\n')
            new_lines = []
            inserted = False
            for l in lines:
                if TARGET_COLOR in l and not inserted:
                    indent = len(l) - len(l.lstrip())
                    new_lines.append(' ' * indent + TARGET_FILL)
                    inserted = True
                new_lines.append(l)
            if inserted:
                text = '\n'.join(new_lines)
                patches_applied.append('fill_type_SOLID_added')
        else:
            patches_not_found.append('fill_type_SOLID_already_present')
    else:
        # Inline YAML handling
        INLINE_COLOR = 'portion.portion_format.fill_format.solid_fill_color.color'
        INLINE_FILL = 'portion.portion_format.fill_format.fill_type = FillType.SOLID'
        if INLINE_COLOR in text and INLINE_FILL not in text:
            # Try to match inline pattern with escaped newlines
            OLD_PAT = '\\n            ' + INLINE_COLOR
            NEW_PAT = '\\n            ' + INLINE_FILL + '\\n            ' + INLINE_COLOR
            if OLD_PAT in text:
                text = text.replace(OLD_PAT, NEW_PAT, 1)
                patches_applied.append('fill_type_SOLID_added_inline')
            else:
                patches_not_found.append('fill_type_SOLID_inline_pattern_not_found')
        elif INLINE_FILL in text:
            patches_not_found.append('fill_type_SOLID_already_present')
        else:
            patches_not_found.append('fill_type_SOLID_no_target_color_line')

    if text != orig:
        path.write_text(text, encoding='utf-8')
        status = 'WRITTEN'
    else:
        status = 'NO_CHANGE'

    prod_results.append((locale, patches_applied, patches_not_found, status))

for r in prod_results:
    print(f'PROD {r[0]}: applied={r[1]} not_found={r[2]} status={r[3]}')
print(f'Total PROD files processed: {len(prod_results)}')
