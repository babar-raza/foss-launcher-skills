# TC-19: ST-211 locale SYNTAX-ERROR categorization

**Date**: 2026-09-24
**Method**: live re-scan of all 151,459 non-English content files using the same
`code_fences.py`/`syntax.py` tooling TC-09's English sweep uses (reused directly, not
reimplemented). **Reconciled exactly against ST-211's original figures**: 2,290 files
with at least one real SYNTAX-ERROR block, 7,322 error blocks total — unchanged by
this session's TC-16/TC-20 fixes (neither touches python/java/csharp/cpp/typescript
classification).

## Headline finding: one dominant, well-understood, mechanical root cause

**A fence's language tag gets silently replaced during locale translation.** English
correctly tags non-code content (a bare API-signature stub, license text, an email
preview, a comment-only fragment) as `text` (or another `NON_EXECUTABLE_LANGS` member)
— the locale version of the SAME block, at the SAME position, gets tagged with the
page's dominant PROGRAMMING language instead (`typescript`, `java`, `csharp`, `cpp`).
`syntax.py`'s tree-sitter grammar then correctly tries to parse content that was never
meant to be code, and correctly reports SYNTAX-ERROR — the "defect" is the WRONG TAG,
not broken code.

**Directly confirmed on 6 real files across 4 different languages/families** (not an
inference — read and compared byte-for-byte against the English counterpart):

| Locale file | Block | English tag | Locale tag | Content |
|---|---|---|---|---|
| `reference.aspose.org/ar/3d/typescript/VertexElement.md` (+ 6 more blocks, same file) | idx 2,3,4,6,8,9,11 | `text` | `typescript` | bare method/constructor signatures |
| `docs.aspose.org/ar/slides/net/getting-started/license.md` | 1 | `text` | `csharp` | MIT license text |
| `docs.aspose.org/ar/email/cpp/getting-started/quickstart.md` | 1 | (same pattern) | `cpp` | "Subject: ... From: ... Body: ..." email preview |
| `docs.aspose.org/ar/pdf/java/getting-started/installation.md` | 2 | `text` | `java` | `// Core API: Document, Page...` comment-only fragment |
| `docs.aspose.org/ar/pdf/java/developer-guide/security.md` | 1 | `text` | `java` | `byte[] key = ...; // 128, 192, or 256-bit key` (placeholder ellipsis, not real code) |
| `docs.aspose.org/ar/tex/python/developer-guide/engine.md` | 1 | `text` | `python` | bare type signature |

Every one of these is clearly non-code (license prose, an email mock-up, a bare
signature, a placeholder ellipsis) — legitimately untagged/text-tagged on English,
and legitimately would NOT be a defect if the locale had kept the same tag.

## Site-level correlation

`reference.aspose.org` alone accounts for **6,444 of 7,322 blocks (88%) and 1,486 of
2,290 files (65%)** of ST-211's entire figure. That site's own structure (per-member
API pages, heavy use of `text`-tagged bare-signature stubs alongside real
`typescript`/`java`/`csharp` example blocks on the SAME page — confirmed directly on
`VertexElement.md`) makes it exactly the shape most exposed to this tag-replacement
mechanism: a translator/generator that defaults every fence on a page to that page's
"main" language, rather than preserving each block's own original tag, would produce
precisely this signature at exactly this scale.

## Other confirmed classes (smaller, already-known)

| Class | Blocks | Files | Note |
|---|---|---|---|
| `PLACEHOLDER_WRONG_COMMENT_SYNTAX` | 172 | 172 | `// Basic usage of X` / `// See reference documentation for full API details` inside `python`-tagged blocks — the exact `batch_gen_missing.py` placeholder-fallback shape TC-10 already fixed 44 instances of on English pages, here on locale copies of the same pages |
| `3D_CONVERTER_MISTRANSLATION` | 84 | 14 | ST-211's own originally-cited `using Aspose.3D.Converter;` (should be `using Aspose.ThreeD;`) — confirmed still present, unchanged |

## Honest limitation of this categorization

An automated position-based check (comparing English block *N* against locale block
*N* directly) only mechanically confirmed 271 of the 7,322 blocks as tag-mismatches,
far fewer than the ~6,700+ the site-level correlation and direct sampling suggest are
the real number. The gap is explained by widespread **English/locale block-COUNT
misalignment** (documented separately, at portfolio scale, in TC-21's own ST-215
categorization) — once a page's block count differs between English and locale at
all, naive positional index comparison stops being reliable partway through the file,
so many real tag-mismatches are invisible to that specific check even though they are
real. This report does **not** claim a single precise block-level count for the
tag-mistranslation class; it claims the mechanism is confirmed real, is the dominant
explanation for the bulk of the 7,322 (particularly reference.aspose.org's 88%), and
names its exact honest boundary rather than rounding an estimate up to a precise-
sounding number.

## Recommendation

**Do not attempt a blanket fix in this taskcard.** The fix itself is mechanical and
low-risk in principle (restore each locale block's fence tag to match English's tag
at the same content position) — but building a SAFE, position-robust matcher (one that
doesn't misfire on the same block-count-drift that defeated the naive check above),
testing it, and then touching up to ~1,486 locale files is real, substantial,
separately-scoped engineering and content work — not a natural extension of a
categorization taskcard, and disproportionate to attempt inside this same session pass.

**Concrete, ready-to-execute follow-on scope** (for a future mission):
1. Build a block-count-robust matcher (e.g. anchor on surrounding heading text or
   content-similarity, not raw positional index) to reliably pair English/locale
   blocks even when counts drift.
2. For every confirmed pair where English is a `NON_EXECUTABLE_LANGS` tag and locale
   is a real language tag on genuinely non-code content: restore the locale tag to
   match English. This is a tag-only fix — no code content changes, the lowest-risk
   class of fix this mission has dealt with.
3. Re-run this same categorization script to confirm the class collapses to ~0 and
   reconcile the residual against `PLACEHOLDER_WRONG_COMMENT_SYNTAX`/
   `3D_CONVERTER_MISTRANSLATION` (which DO need real content fixes, not tag fixes).

This mirrors TC-21/ST-215's own disposition: categorization is this taskcard's real,
complete deliverable; the fix itself needs its own scoped mission.

## CORRECTION (2026-09-24, MT073/TC-01+TC-02): the 88% site-level correlation was an overclaim

MT073's own TC-01 built the block-count-robust matcher this report specified as the
concrete follow-on (anchor on content similarity via `difflib.SequenceMatcher`, not
raw index — `lib/example_verification/block_matcher.py`). Running it against the full
portfolio with this report's own narrow, verified candidate criteria (English tag is
`NON_EXECUTABLE_LANGS`, locale tag is a real language, locale content is a genuine
`SYNTAX-ERROR` under that tag) found **exactly 271 candidates — zero more than the
naive positional check already found**, and every one of the 271 matched via
`position` (equal block counts), none via the new `content-similarity` fallback.

The matcher itself is verified working (direct tests below confirm it correctly
re-orders a real 3-vs-4 block-count mismatch case) — it simply found nothing new for
*this specific defect signature*, because block-count-mismatched reference.aspose.org
files turn out NOT to be simple tag swaps at all. Direct investigation of the
"unaccounted" reference.aspose.org errors found a **different, larger mechanism**:
some locale reference pages (e.g. `3d/typescript/vector2-vector4/_index.md`,
`3d/java/base-classes/_index.md`) have an English counterpart with as few as **1**
code block, while the locale copy still has **12** — the English side was
consolidated/restructured (likely by a later reference-index-structure regeneration
pass — see `sprint_archive_2026h1.md`'s own "reference grouped-index" work) into a
different content shape entirely, while the locale side is frozen on the old,
pre-restructuring layout of many small bare-signature blocks. This is NOT a tag
mistranslation and a tag-only fix must not be applied to it — it needs the actual
reference-page-generation pipeline to regenerate the locale side, or a decision that
these locale pages are simply stale and need re-translation from the current English
structure. **Retracting this report's own "88% / 6,444 blocks" figure** — that number
was a plausibility correlation ("reference.aspose.org's shape makes it exposed to this
mechanism"), not a verified count, and it does not hold up: the real tag-mismatch
class is 271 blocks/187 files, full stop, portfolio-wide. The remaining reference.aspose.org
SYNTAX-ERROR blocks (roughly 3,600+, still not fully characterized) are a distinct,
unresolved structural-divergence class, registered as follow-on investigation (see
MT073's own taskcard register) rather than left silently folded into a wrong number.

**Real fix applied on the strength of the CORRECT 271-candidate figure**: see MT073
TC-03's own evidence for the real commit(s).
