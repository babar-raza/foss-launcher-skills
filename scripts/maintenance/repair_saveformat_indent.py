"""
Fix indentation of `from aspose.slides_foss.export import SaveFormat` lines
that were inserted without proper indentation in products locale _index.md files.

The problem: the line was inserted without matching the YAML block indentation.
The fix: if the import line exists but is not properly indented (has no leading spaces
but the surrounding code lines have indentation), fix the indentation.
"""
import re, pathlib

base = pathlib.Path('d:/onedrive/Documents/GitHub/aspose.org')
IMPORT_LINE = 'from aspose.slides_foss.export import SaveFormat'

locales_prod = sorted([
    p for p in base.glob('content/products.aspose.org/*/slides/python/_index.md')
    if '/en/' not in str(p).replace('\\', '/')
])

results = []

for path in locales_prod:
    locale = path.parts[path.parts.index('products.aspose.org') + 1]
    text = path.read_text(encoding='utf-8')
    orig = text
    fixes = []

    lines = text.split('\n')
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if this is the bare (unindented) import line we added
        if line == IMPORT_LINE:
            # Look at neighbouring lines to determine expected indentation
            # Check the line before and after for indentation context
            indent = ''
            for j in [i-1, i+1]:
                if 0 <= j < len(lines):
                    neighbour = lines[j]
                    stripped = neighbour.lstrip()
                    if stripped and stripped.startswith(('import ', 'from ', 'with ', '#', 'prs.', 'shape', 'slide', 'portion')):
                        indent_len = len(neighbour) - len(stripped)
                        if indent_len > 0:
                            indent = ' ' * indent_len
                            break
            if indent:
                new_lines.append(indent + IMPORT_LINE)
                fixes.append(f'fixed_indent_to_{len(indent)}spaces_at_line_{i+1}')
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
        i += 1

    new_text = '\n'.join(new_lines)
    if new_text != orig:
        path.write_text(new_text, encoding='utf-8')
        results.append((locale, 'FIXED', fixes))
    else:
        results.append((locale, 'NO_CHANGE', []))

for r in results:
    if r[1] != 'NO_CHANGE' or r[2]:
        print(f'{r[0]}: {r[1]} {r[2]}')

changed = [r for r in results if r[1] == 'FIXED']
print(f'Total fixed: {len(changed)}')
