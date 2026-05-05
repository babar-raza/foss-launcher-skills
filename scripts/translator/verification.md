# Translator Subsystem — Verification Guide

All commands below are run from the repo root (`d:\onedrive\Documents\GitHub\aspose.org`) unless stated otherwise. `python` refers to the interpreter with `scripts/translator/requirements.txt` installed.

---

## 1. Import Smoke Tests

Verify the package and all submodules import cleanly.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
import translator
from translator.policy.loader import ContentTypePolicy
from translator.parser.document import parse_string
from translator.parser.protector import protect, restore
from translator.cache.sqlite_cache import TranslationCache
from translator.backends.base import BackendRouter, TranslationBackend
from translator.backends.llm import LLMBackend
from translator.backends.ollama import OllamaBackend
from translator.backends.m2m import M2MBackend
from translator.writer.reconstructor import reconstruct_document
print('OK — all imports succeeded, version', translator.__version__)
"
```

Expected output: `OK — all imports succeeded, version 1.0.0`

---

## 2. Policy Detection Test

Verify `ContentTypePolicy.for_path()` returns the correct content type for known paths.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.policy.loader import ContentTypePolicy

cases = [
    ('content/docs.aspose.org/en/slides/net/_index.md', 'docs'),
    ('content/kb.aspose.org/en/slides/java/how-to-open.md', 'kb'),
    ('content/products.aspose.org/en/slides/net/_index.md', 'products'),
    ('content/reference.aspose.org/en/3d/net/_index.md', 'reference'),
    ('content/blog.aspose.org/en/slides/some-post.md', 'blog'),
]
for path, expected in cases:
    policy = ContentTypePolicy.for_path(path)
    status = 'PASS' if policy.content_type == expected else f'FAIL (got {policy.content_type})'
    print(f'{status}: {path}')
"
```

Expected: all five lines print `PASS`.

---

## 3. Protector Roundtrip Test

Verify that `protect()` followed by `restore()` is lossless for a document containing shortcodes, code fences, and inline code.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.policy.loader import ContentTypePolicy
from translator.parser.protector import protect, restore

policy = ContentTypePolicy.for_path('content/docs.aspose.org/en/slides/net/_index.md')
text = '''
See \`SomeClass.Method\` for details.
\`\`\`csharp
var x = new Presentation();
\`\`\`
{{< button text=\"Download\" >}}
Learn [more](https://docs.aspose.com/slides/).
'''
masked, ph_map = protect(text, policy.protected_patterns, policy.placeholder_format)
restored = restore(masked, ph_map)
assert restored == text, f'Mismatch:\n{restored!r}'
print('PASS — roundtrip lossless, placeholders used:', len(ph_map))
"
```

Expected: `PASS — roundtrip lossless, placeholders used: 4` (exact count depends on content; must be > 0).

---

## 4. Cache Store/Retrieve Test

Verify the SQLite cache stores and retrieves a translation using an in-memory database.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.cache.sqlite_cache import TranslationCache

cache = TranslationCache(':memory:')
cache.store('docs', 'en', 'fr', 'Hello world', 'Bonjour le monde', 'test_model')
hit = cache.lookup('docs', 'en', 'fr', 'Hello world')
assert hit == 'Bonjour le monde', f'Expected translation, got: {hit!r}'
miss = cache.lookup('docs', 'en', 'de', 'Hello world')
assert miss is None, f'Expected None for cache miss, got: {miss!r}'
stats = cache.stats()
assert stats['total_entries'] == 1
assert stats['total_hits'] == 1  # lookup() increments hit_count
print('PASS — store/retrieve/miss/stats all correct')
cache.close()
"
```

Expected: `PASS — store/retrieve/miss/stats all correct`

---

## 5. Evidence Preservation Test

Translate a synthetic docs page and confirm the `evidence` block is unchanged.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.parser.document import parse_string

src = '''---
title: Hello
description: World
evidence:
  source_url: https://example.com
  verified_at: 2026-01-01
  model: test
---

Some body text.
'''
doc = parse_string(src)
original_evidence = doc.get_evidence()
# Simulate a translate pass that modifies only title/description
doc.frontmatter['title'] = 'Hola'
doc.frontmatter['description'] = 'Mundo'
assert doc.get_evidence() == original_evidence, 'Evidence was mutated!'
print('PASS — evidence block survived frontmatter modification')
"
```

Expected: `PASS — evidence block survived frontmatter modification`

---

## 6. Selective Field Test

Confirm that for a `docs` page, only `title` and `description` are listed as translatable; structural keys are not.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.policy.loader import ContentTypePolicy
from translator.parser.frontmatter import iter_translatable_fields

policy = ContentTypePolicy.for_path('content/docs.aspose.org/en/slides/net/_index.md')
fm = {
    'title': 'My Title',
    'description': 'My description',
    'type': 'docs',
    'weight': 1,
    'date': '2026-01-01',
    'evidence': {'source_url': 'x'},
}
fields = dict(iter_translatable_fields(
    fm,
    policy.field_policy.translate,
    policy.field_policy.translate_nested,
))
assert set(fields.keys()) == {'title', 'description'}, f'Unexpected fields: {set(fields.keys())}'
print('PASS — only title and description are translatable for docs content type')
"
```

Expected: `PASS — only title and description are translatable for docs content type`

---

## 7. Code Fence Preservation Test

Run protection on a body with a code fence and confirm the fence contents survive unchanged.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.policy.loader import ContentTypePolicy
from translator.parser.protector import protect, restore

policy = ContentTypePolicy.for_path('content/docs.aspose.org/en/slides/net/_index.md')
fence = '\`\`\`csharp\nPresentation pres = new Presentation();\npres.Save(\"out.pptx\", SaveFormat.Pptx);\n\`\`\`'
body = f'Introduction.\n\n{fence}\n\nConclusion.'
masked, ph_map = protect(body, policy.protected_patterns, policy.placeholder_format)
assert fence not in masked, 'Code fence should have been replaced'
# Simulate LLM translating only the prose (tokens stay intact)
fake_translated = masked.replace('Introduction.', 'Einleitung.').replace('Conclusion.', 'Schlussfolgerung.')
restored = restore(fake_translated, ph_map)
assert fence in restored, 'Code fence must be present after restore'
print('PASS — code fence contents preserved through protect/restore cycle')
"
```

Expected: `PASS — code fence contents preserved through protect/restore cycle`

---

## 8. Shortcode Preservation Test

Confirm shortcodes are captured by the protector on a products-type path.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.policy.loader import ContentTypePolicy
from translator.parser.protector import protect, restore

policy = ContentTypePolicy.for_path('content/products.aspose.org/en/slides/net/_index.md')
shortcode = '{{< blocks/products/pf/main-wrap-class >}}'
body = f'Download now.\n{shortcode}\nLearn more.'
masked, ph_map = protect(body, policy.protected_patterns, policy.placeholder_format)
assert shortcode not in masked, 'Shortcode should be replaced with placeholder'
assert len(ph_map) >= 1, 'At least one placeholder expected'
restored = restore(masked, ph_map)
assert shortcode in restored, 'Shortcode must survive restore'
print('PASS — shortcode replaced and restored correctly')
"
```

Expected: `PASS — shortcode replaced and restored correctly`

---

## 9. Idempotence Test

Run the same translation twice on a synthetic document (using the cache) and confirm the output is identical.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.cache.sqlite_cache import TranslationCache
from translator.parser.document import parse_string
from translator.writer.reconstructor import reconstruct_document

cache = TranslationCache(':memory:')
src_fm = {'title': 'Hello', 'description': 'World', 'type': 'docs'}

# First pass — store in cache
cache.store('docs', 'en', 'fr', 'Hello', 'Bonjour', 'test_model')
cache.store('docs', 'en', 'fr', 'World', 'Monde', 'test_model')

def do_translate(cache):
    from translator.parser.frontmatter import iter_translatable_fields, set_field
    import copy
    fm = copy.deepcopy(src_fm)
    for path, value in iter_translatable_fields(fm, ['title', 'description'], []):
        hit = cache.lookup('docs', 'en', 'fr', value)
        if hit:
            set_field(fm, path, hit)
    doc = parse_string('---\ntitle: Hello\ndescription: World\ntype: docs\n---\n\nBody.\n')
    doc.frontmatter = fm
    return reconstruct_document(doc)

out1 = do_translate(cache)
out2 = do_translate(cache)
assert out1 == out2, 'Second pass produced different output!'
print('PASS — two passes produce identical output (idempotent)')
cache.close()
"
```

Expected: `PASS — two passes produce identical output (idempotent)`

---

## 10. Blog Exclusion Test

Confirm that blog paths return a policy with `skip=True` and are never translated.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.policy.loader import ContentTypePolicy

blog_path = 'content/blog.aspose.org/3d/net/some-post/index.md'
policy = ContentTypePolicy.for_path(blog_path)
assert policy.skip is True, f'Expected skip=True, got skip={policy.skip}'
assert policy.content_type == 'blog'
assert policy.field_policy.translate == []
assert policy.field_policy.translate_body is False
print('PASS — blog path correctly marked as skip=True, no translatable fields')
"
```

Expected: `PASS — blog path correctly marked as skip=True, no translatable fields`

---

## 11. Validation Gate Test

Confirm that if an `evidence` block is present in the source but missing from the output, the check can detect it.

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.parser.document import parse_string

src_with_evidence = '''---
title: Hello
evidence:
  source_url: https://example.com
---

Body.
'''
output_without_evidence = '''---
title: Bonjour
---

Corps.
'''

src_doc = parse_string(src_with_evidence)
out_doc = parse_string(output_without_evidence)

# Validation: if source has evidence, output must also have it
if src_doc.has_evidence() and not out_doc.has_evidence():
    print('PASS — missing evidence detected correctly (validator would reject this output)')
else:
    print('FAIL — evidence loss not detected')
"
```

Expected: `PASS — missing evidence detected correctly (validator would reject this output)`

---

## 12. Backend Fallback Test

Confirm `OllamaBackend.is_available()` returns `False` when Ollama is not running (and therefore `BackendRouter` would skip it).

```bash
python -c "
import sys; sys.path.insert(0, 'scripts')
from translator.backends.ollama import OllamaBackend

# Use a port that is guaranteed to be closed
backend = OllamaBackend(base_url='http://localhost:19999')
available = backend.is_available()
assert available is False, f'Expected False, got {available}'
print('PASS — OllamaBackend correctly reports unavailable when server is not running')
print('      In production: BackendRouter would skip this backend and raise BackendUnavailableError')
print('      if LLMBackend also fails (due to invalid LLM_API_KEY).')
"
```

Expected: `PASS — OllamaBackend correctly reports unavailable when server is not running`

To test the full primary-fails-then-Ollama-activates flow in a live environment:

```bash
LLM_API_KEY=bad_key_intentional python -c "
import sys; sys.path.insert(0, 'scripts')
import os
from translator.backends.llm import LLMBackend
from translator.backends.ollama import OllamaBackend
from translator.backends.base import BackendRouter
from translator import BackendUnavailableError, ConfigurationError

try:
    llm = LLMBackend()
    ollama = OllamaBackend()
    router = BackendRouter([llm, ollama])
    result = router.translate('Hello', 'en', 'fr')
    print(f'Translated via {router.active_backend_info()[\"backend\"]}: {result}')
except (BackendUnavailableError, ConfigurationError) as e:
    print(f'Both backends failed as expected: {e}')
"
```

If Ollama is running with a model loaded, the output will show `Translated via ollama: ...`. If neither backend is available, both fail with a `BackendUnavailableError`.
