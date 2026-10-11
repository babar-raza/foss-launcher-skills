# pdf/typescript — TC-27c cold-start canary: scope finding (2026-08-31)

**Status: correctly-diagnosed, disclosed BLOCKED.** Not pushed (never attempted).
Not composed. The "no push" boundary was never at risk here — the honest finding
is that full composition genuinely needs its own dedicated unit of work, not that
anything was withheld improperly.

## What was proven, code-demonstrated

- `start pdf typescript` → `INPUTS_PINNED` (run `rr-20260831T180238Z-35973dad60f8`,
  `clone_cache_head=04e7b50a3dc37427e5e7d72147dd0baf62ccbb9f`). The original symptom
  ("`/readme-refresh pdf typescript` aborts at `_resolve_product` — not registered")
  is gone: `data/products.json` carries the row, and cold-start proceeds cleanly.
- `plan` → `PLANNED`. AGENTS.md §7d's knowledge-quality gate passed (`class_count:
  1055`, `total_claims: 8341`, `snippet_count: 100`, `enrichment_status: full` —
  clearing the thresholds by 50-200x, per the plan's own Finding F-2).
- `facts/factpack.json` fully populated: `archetype: "transform"`, real npm
  dependency data, `license_file: LICENSE`, `enterprise_link` correctly resolving
  to the family-level `products.aspose.com/pdf/` target (TC-P6-08's fix, live-
  confirmed working end to end), `homepage`/`documentation_links` verified,
  `available_badges` computed (license + language-version + contributors real;
  package-version and CI-status correctly absent with real reasons), and a real,
  substantial `old_readme_inventory` — the upstream repository has genuine,
  extensive content, not a stub.

## The scope finding

`extract_old_readme_content_units` / `_code_units` / `_structural_units` run
against the real upstream `README.md` (2,568 lines) return:

| Extractor | Units |
|---|---|
| Content units | 315 |
| Code units | 110 |
| Structural units | 3 |
| **Total** | **428** |

Every one of these needs an individually-justified, evidenced disposition entry
(`merged_verbatim` / `merged_reframed` / `corrected` / `excluded`, each with real
verification evidence) before `ingest-candidate` can pass — the same hard-gate
discipline this mission's own hardening work (TC-19/21/23, closed earlier this
session) now correctly enforces, and which this session directly proved working
end-to-end on `tex/python`'s 12-unit case.

The real upstream project (glimpsed via its own `CLAUDE.md`, ~150 source modules)
is a full-featured, from-scratch PDF engine: object model parse/serialize with
brute-force recovery, AcroForms, annotations (all subtypes), redaction, digital
signing (CMS/PAdES, LTV, timestamps), standard-handler encryption, SVG import AND
export, DOCX/EPUB/HTML/Markdown export and import, table extraction AND authoring,
barcode generation, font embedding/subsetting across TrueType/CFF/Type1/WOFF/WOFF2/
dfont/TTC, complex-text shaping (BiDi/UAX#14/OpenType layout), CJK CID/CMap
handling, and codecs for JPEG (baseline+progressive+arithmetic+lossless+
hierarchical), JPEG2000, JBIG2, TIFF, GIF, BMP, plus PDF/A, PDF/X and PDF/UA
validation and remediation. This is not a small or thin library — its own README
inventory (315 content units) reflects that real depth.

## Why this was not attempted in this pass

Composing a properly-grounded README — citing real snippets, real API members
from `reference_api_index`, and a real, individually-reasoned disposition for
each of 428 units distinguishing "belongs in a curated top-level README" from
"belongs in docs.aspose.org's developer guide" — is a task of the same order as
Batch D (`pdf/net`, 173 findings against an *existing* candidate) or larger,
since this is a *fresh* composition with no existing candidate to iterate from.
Rushing it within this canary step risks exactly the unconstrained-generation /
fabrication-under-time-pressure failure mode (RC-5) this whole mission exists to
narrow, not widen. The honest, disciplined choice — matching the standard this
mission has held for `pdf/net` throughout — is to treat this as its own real,
future unit of work.

## What remains true and unblocked

- Registration, cloning, knowledge bootstrap, EE-link resolution, and the
  banner-readiness question (Phase 6) are all genuinely done — verified, not
  asserted — and do not need to be redone.
- `verify-examples` requires no TC-25 (TypeScript runner): the honest,
  disclosed `BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE` stub already applies
  uniformly, matching 6 other launched non-Python languages.
- Compose-step archetype/capability-dependency authoring (Finding F-1) was
  never reached, since composition itself was not attempted — deferred with
  the rest of this canary, not separately.

## Run state

Run `rr-20260831T180238Z-35973dad60f8` left at `PLANNED` (a legitimate resume
point — `ingest-candidate` was never invoked, since there is no candidate to
ingest yet). Not abandoned; a future session composing the candidate should
resume from here rather than re-pinning inputs.
