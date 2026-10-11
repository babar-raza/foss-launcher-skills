# Finding: orphaned closing code fence (missing opening fence) — 320 files

Discovered as a byproduct of taskcard C1's portfolio-wide fence-parity pilot
(diffing `lib/example_verification/code_fences.py` against
`content_eval/models.py`'s existing regex parser over all 158,863
`content/**/*.md` files). **Not filed to `backlog/inbox.md` from this
taskcard run** — `backlog/inbox.md` is outside C1's `allowed_paths`
(`scripts/pipeline/lib/example_verification/**`, `content_eval/models.py`,
`core/markdown.py`, `tests/test_example_verification_code_fences.py`,
`.github/workflows/example-verification-tests.yml`), and the loop
protocol's hard safety rule is "never touch a file outside this card's
allowed_paths." A drafted ST-192 entry was written and then reverted
(`git checkout -- backlog/inbox.md`) once this was noticed — recorded here
instead so a session with `backlog/` in scope can file it properly.

## Summary

158,543 of 158,863 files (99.8%) parse identically between the old and new
tokenizers. 320 files diverge for the same root cause: a code example is
embedded in the page with **no opening fence**, leaving an orphaned closing
` ``` ` that desyncs whichever fence-toggle parser reads it. Both the old
regex parser and the new tokenizer resync differently after the orphaned
closer — neither "recovers correctly," because the input markdown is
genuinely malformed. This is a **content defect**, not a tokenizer defect,
and is why C1 did **not** switch `content_eval/models.py` onto the new
tokenizer this iteration (see the Decision section of this same evidence
run's summary).

## Confirmed examples (read directly, not inferred)

- `content/reference.aspose.org/zh/3d/java/mesh.md:65-88` — a "构建四边形网格"
  Java example missing its `` ```java `` opener; orphaned closer at line 88.
- `content/blog.aspose.org/email/python/python-outlook-msg-create-read/index.fa.md:187-196`
  — a `with msg.MsgReader.from_file(...)` Python example missing its
  `` ```python `` opener; orphaned closer at line 196. This is a
  **translated-locale-only** instance: the English `index.md` in the same
  directory is clean. The same shape independently recurs in
  `index.{fa,ru,th,tr,uk,vi}.md` in that directory — introduced per-locale,
  not inherited from the English source.

## Scope (from `c1_orphan_fence_family_breakdown.json`)

320 files total, concentrated in:
- `reference.aspose.org/*/3d/{typescript,java}` — dozens of locales across a
  small number of underlying EN reference pages (`mesh`, `node`, `scene`,
  `quaternion`, `vector3`, `load-save-options/_index`), multiplied by locale
  mirroring.
- 3 `blog.aspose.org` posts, each affecting only a subset of their own
  locale set: `email/python/python-outlook-msg-create-read`,
  `email/python/email-key-features-python`,
  `tex/python/introducing-tex-foss-python`.

Full per-file breakdown: `c1_fence_parity_report.json` (category counts +
5 examples per category) and `c1_orphan_fence_family_breakdown.json` (by
site/locale/family/platform) in this same evidence directory.

## Suggested follow-ups (for whoever files this)

1. Find the true number of underlying EN source pages (likely ~6-9, not
   320) so the fix is made once per source and re-propagated, not repeated
   320 times.
2. Investigate whether `body_refresh._example_regeneration` — already
   flagged upstream as RC21 in the governing plan
   (`<local-plan-cache>/do-another-round-of-indexed-graham.md`)
   for writing a replacement code block with no compile/parse verification
   — or the translation pipeline is the actual defect-introduction
   mechanism. Both a template-generation pathway (reference pages) and a
   translation pathway (blog locale variants) independently produced the
   identical "missing opening fence" shape, so there may be two distinct
   root causes rather than one.

## Suggested backlog entry (drafted, not filed)

```
| ST-19x | C | GI | MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION taskcard C1 ... [see this file's Summary/Confirmed examples/Scope sections above for the full narrative] ... | queued | P2 | M | 0 | related-to:MT065 | none | 2026-09-06 |
```
