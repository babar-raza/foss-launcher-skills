# snippet_golden_pkg

Small Python fixture used ONLY by
`test_typescript_snippet_ordering.py::TestNonOptedInPlatformByteParity` to
prove TC-MT040-44's tiered snippet budget change is a no-op for platforms
not in `_TIERED_SNIPPET_PLATFORMS`. Not shared with any other test file
(deliberately -- other python fixtures like `python_pkg/` are pinned by
`test_extraction_goldens.py` for `extract_api_surface`, unrelated to this).

```python
from aspose_core.document import Document

doc = Document()
doc.save('out.pdf')
```
