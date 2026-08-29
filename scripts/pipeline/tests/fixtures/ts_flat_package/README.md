# fake

A fixture package standing in for a flat-layout TypeScript product (mirrors
`tests/fixtures/rust_crate/`'s role for Rust). Used by
`test_typescript_snippet_ordering.py` (TC-MT040-44 / TC-MT040-16).

## Usage

```ts
import { Document } from '@asposefoss/fake';

const doc = Document.open('sample.pdf');
doc.save('out.pdf');
```
