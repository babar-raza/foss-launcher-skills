# Upstream issues — pdf/typescript

Verified: 2026-09-03T14:16:00Z against the clone cache pinned to `197de270`
(https://github.com/aspose-pdf-foss/Aspose.PDF-FOSS-for-TypeScript), via a real
`verify-examples --typescript-runner` end-to-end run (npm install + build + execution).

## `htmlFileToPdf` is documented as importable from `@asposefoss/pdf` but is never re-exported
- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: the upstream README's own `### Use file-based helper methods` section shows
  `import { ..., htmlFileToPdf } from '@asposefoss/pdf';` and calls
  `await htmlFileToPdf('page.html', 'out.pdf', { format: PageFormat.A4 })` (`README.md:2025`,
  `README.md:2042`). `htmlFileToPdf` is a real, fully implemented, exported function in
  `src/node.ts:194`. But the package's only real entry point, `src/node.ts:194` is re-exported
  through `src/index.ts` (`"main": "dist/index.js"`, no `exports` subpath map in
  `package.json`), and `src/index.ts`'s own re-export block
  (`splitPdfFile, readMetadataFile, updateMetadataFile, clearMetadataFile, savePageImageFile,
  exportFdfFile, exportXfdfFile, importFdfFile, importXfdfFile`) omits `htmlFileToPdf` — a
  direct read of both files confirms the omission. Reproduced live: a real `npm run build` +
  `import { htmlFileToPdf } from '@asposefoss/pdf'` under Node's real ESM loader raises
  `SyntaxError: The requested module '@asposefoss/pdf' does not provide an export named
  'htmlFileToPdf'`.
- **Impact**: a visitor copy-pasting this exact, correctly-transcribed upstream example cannot
  run it at all — the import itself fails before any of the function's own logic executes.
- **Not fixable here because**: the missing re-export line is upstream source
  (`src/index.ts`), not something a README edit can change; this candidate preserves the
  upstream example verbatim (byte-exact transcription is the mission's own retention
  requirement) and this finding is disclosed here rather than silently dropping or rewriting
  a real, documented capability.

## Six worked examples span multiple `###` headings with no re-stated setup, by upstream design
- **Severity**: INFORMATIONAL
- **Evidence**: `### Encrypted output`, `### Certificate-based (public-key) encryption`,
  `### Split and merge`, `### Content streams`, and similar clusters (`README.md:158-249`) read
  as one continuous narrative under an ambient `doc`/`bytes` established several `###` headings
  earlier, not as independently-runnable snippets per heading — confirmed present in this exact
  shape in the live upstream source, not introduced by this candidate's own extraction. A
  verification runner that treats every `###` heading as an independent example (this session's
  new `readme_refresh_run.py` TypeScript runner v2 chaining heuristic included) cannot always
  bridge a later section that reimports one symbol while still depending on an unrelated
  earlier section's local variable; 5 of 91 real code blocks fail this way
  (`verify-examples --typescript-runner`, blocks under `Certificate-based encryption`,
  `Content streams`, `Build and Style Tables`, `Build Multi-Column Flow Layouts`, `Markdown`).
- **Impact**: none for a human reader following the narrative top-to-bottom (the upstream
  authoring style is a legitimate, common README convention); only affects fully-automated,
  standalone-per-heading execution.
- **Not fixable here because**: this is the upstream README's own authoring style, faithfully
  preserved; see backlog **ST-179** for the runner-side follow-up (a small number of examples
  the chain heuristic cannot bridge without a deeper, out-of-scope static-scope analysis).
