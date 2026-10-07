# Production Page Rubric

Status: Current
Audience: Agent (reviewer), Operator
Canonical reference: this page
Consumed by: `/independent-content-review` (S-127); author-side companion gate: `/publish-readiness-review` (S-90)

The standard an Aspose.org page must meet before it goes live. Pages are public the moment they are
published, so every new or changed page is checked against this rubric by a reviewer who did not write
it. The rubric is deliberately command-driven: a reviewer proves each check by running something and
recording where the output is, never by quoting the author's own gates.

Anchors: `docs/reference/hugo-rendering.md` §16/§17/§20, `docs/reference/content-contracts.md`,
`GRADE_CONTRACT.md`, AGENTS.md §5/§7b/§13. Standing rules applied here: relative links are fine within
one subdomain, cross-subdomain links must be absolute `https://` and omit `/en/` for English; a visible
"Example removed: ..." marker is never acceptable (find a real example or remove the whole section);
evidence/provenance data is internal-only and must never render publicly.

## Independence rules (enforced; recorded in every verdict)

- A reviewer is a fresh read-only agent with no write tools and no shared context with any author or any
  other reviewer of the same page.
- **Tier-1** pages (every blog post; any page with code blocks, format tables or capability claims, per
  AGENTS.md §7b) get **two independent reviewers**. Tier-2/3 pages get one.
- Disagreement between reviewers, or any blocker, adds a third reviewer and sets `REWORK_REQUIRED`.
  A blocker always overrides PASS verdicts.
- Authors never clear a finding. Only a re-review of the changed content hash can.
- A verdict is bound to the `content_sha256` of the reviewed page. Any later change invalidates it.

## Checks

Each check is recorded with the command run, a reference to its output, and the result `PASS`, `FAIL`
or `NA` (an `NA` needs a stated reason).

### R1 Truth

- R1.1 Every identifier, signature, option and enum constant named on the page exists (source at the
  pinned SHA, or `javap` / equivalent introspection of the built product artifact).
- R1.2 Every behavioural claim ("supports...", "converts...", "preserves...") is backed by source, a test
  or upstream docs at the pinned SHA.
- R1.3 Limitations are stated and not contradicted elsewhere on the page.
- R1.4 Availability wording is correct. Unreleased capability is never implied released, and no
  unpublished version or coordinate appears. Where a capability is unreleased the page gives the
  source-build path. Released capability states the version it first shipped in.
- R1.5 Numbers and counts match the knowledge model or the source.

### R2 Examples

- R2.1 Each code block is compiled by the reviewer in a clean scratch directory against the product
  artifact.
- R2.2 Each block is run where a run is meaningful, and the output matches the page's stated result.
- R2.3 Imports are complete and no symbol is undefined.
- R2.4 No placeholder or "Example removed" marker.
- R2.5 The example is the verified one: its hash equals the example-write ledger row. The reviewer uses
  the ledger only for provenance, never for the pass/fail decision.

### R3 Rendered output

Build the affected site section to a temp directory with production flags and inspect the HTML.

- R3.1 Exactly one `<h1>`, with sane heading order.
- R3.2 Title, description, canonical and Open Graph tags are present and correct.
- R3.3 Code blocks render as `<pre><code>`, and their count equals the number of Markdown fences.
- R3.4 Tables are intact.
- R3.5 Images have alt text.
- R3.6 Internal links resolve inside the build.
- R3.7 External links respond (HEAD, rate-limited, cached).
- R3.8 No internal metadata is visible: the evidence panel, `evidence:` blocks, `CLM-` / `ERC-` ids.
- R3.9 Navigation, breadcrumb and submenu entries are present.
- R3.10 A sitemap entry is present.
- R3.11 No placeholder markers.

### R4 Purpose, distinctness, linking

- R4.1 Docs, KB, blog and products pages serve distinct purposes, with no duplicated paragraphs.
- R4.2 Cross-links are natural, relevant, valid and bidirectional where useful, never forced.
- R4.3 New reference pages are reachable from their namespace, parent and index (no orphans).
- R4.4 Link format follows the rules above.

### R5 Scope hygiene

- R5.1 `git diff --name-only` is a subset of the declared scope.
- R5.2 No unrelated product or locale files changed.
- R5.3 No diffs that only touch `graded_at` or other automatic fields.
- R5.4 No unexplained body deletions: check the deletions-to-additions ratio and flag any word-count drop
  without a recorded disposition.
- R5.5 Evidence and provenance blocks are present and unchanged in meaning.

### R6 Standard and tone

- R6.1 Clear, correct language at production-website standard.
- R6.2 Proportion: a Products-page edit is not exaggerated or disruptive, and page flow, positioning and
  SEO intent are preserved.
- R6.3 Commercial and FOSS offerings are kept separate.
- R6.4 No marketing fluff or unsupported superlatives.
- R6.5 Accessibility basics: heading semantics, meaningful link text, alt text.

### R7 Feature-coverage sampling

Applies when the run has a feature-coverage matrix or capability ledger. Re-derive at least 25% of its
rows (minimum 10) from source independently. A worth-mentioning feature missing from its page or surface
is a blocker.

## Verdict file schema

```json
{"page": "<repo-relative path>", "content_sha256": "<hash>", "reviewer_id": "<agent id>", "tier": 1,
 "checks": [{"id": "R1.1", "command": "...", "output_ref": "path#line", "result": "PASS|FAIL|NA", "note": ""}],
 "findings": [{"severity": "blocker|major|minor", "check": "R2.1", "evidence": "...", "proposed_fix_owner": "skill|script|content"}],
 "verdict": "PASS|FAIL"}
```

`PASS` requires no blocker or major findings, and every R1-R6 check either `PASS` or a justified `NA`.

## Sampling policy for mechanically generated reference changes

1. Review 100% of every new reference page for a capability unit, and of every page whose body changed
   beyond an evidence-only restamp.
2. Run a deterministic diff-class check on 100% of the remaining changed pages: only `evidence.*` or
   automatic fields changed, no body deletions, and `rendered_page_audit.py` over the whole set.
3. Review a seeded random sample of at least 5% (minimum 25) of the evidence-only or
   regenerated-unchanged pages. Record the seed. A defect doubles the sample; a systemic defect opens a
   hardening card.

Docs, KB, blog and Products pages are always reviewed 100% by hand. No sampling applies to them.

## Calibration

Before the panel judges real pages it must catch every seeded defect in a canary page. Build the canary
from a real, clean page of the same site by seeding one defect per rubric dimension, at least eight in
total. Suggested set:

| Id | Rubric check | Seeded defect |
|---|---|---|
| D1 | R1.1 | prose cites a method that does not exist |
| D2 | R1.4 | claims availability in an unpublished release |
| D3 | R3.6 | internal link to a page that does not exist |
| D4 | R2.1 | code block with an undefined variable and a missing semicolon |
| D5 | R3.1 | second H1 inside the body |
| D6 | R3.8 | internal claim ids or an evidence marker leaked into visible prose |
| D7 | R2.4 | visible "Example removed" placeholder |
| D8 | R1.2 | unsupported superlative capability claim |
| D9 | R4.1 | an existing paragraph duplicated verbatim |
| D10 | R4.4 | cross-subdomain link written relative, with an `/en/` prefix |

The canary lives only under `reports/ivp/.../canaries/`, never under `content/`. The answer key is
written next to it and withheld from reviewers; reviewers get only the page and its sha256. A missed
defect means the rubric or reviewer prompt is fixed and calibration re-run. A systemic miss opens a
hardening card.
