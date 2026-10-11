# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/pre-refactor/governance/launch-gates.md

---

---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §7a, §6f
# Plan: delightful-wondering-hartmanis (TC-03)
# Extracted: 2026-04-28
---

## 7a. Launch-Readiness Gates

Before any product launch (new family/platform going live), run the automated gate checker:

```bash
python scripts/pipeline/commands/launch/launch_gate.py {family} {platform}
```

All 15 automated gates must report PASS (or SKIP/WARN) before a product is considered launch-eligible.

| Gate | ID | What it checks | Fail behavior |
|------|----|----------------|---------------|
| Knowledge freshness | L-01 | `model.yaml stale_since` is null | FAIL — run S-12 → S-14 |
| Evidence coverage | L-02 | All content files have non-empty `evidence:` block | FAIL — run attach_evidence.py |
| Forbidden claims | L-03 | `change_guard.py` reports 0 DENY on active claims | FAIL — remove or correct claim |
| API accuracy | L-04 | `audit.py` exits 0 FAIL on all content files | FAIL — fix API references |
| Format truth | L-05 | `content_eval --evaluators format_truth` exits 0 FAIL | FAIL — correct format table |
| Knowledge reconciliation | L-06 | `promote.py` reconciliation passes (no format/claim contradiction) | FAIL — fix formats.json or claims |
| Pipeline tests | L-07 | `pytest` on `scripts/pipeline/tests/` exits 0 | FAIL — fix broken test |
| Provenance coverage | L-08 | All English content files with a provenance block have `content_origin` set | FAIL — fix skill template or run provenance_backfill.py |
| Hugo build | L-09 | `hugo --config configs/products.aspose.org.toml` exits 0 | FAIL — fix YAML/template errors (does not verify rendering completeness) |
| No coming-soon | L-10 | Family `_index.md` must not contain stale "coming soon" placeholder | FAIL — run `/family-sync` |
| Family display name | L-11 | Family root `_index.md` uses canonical "Aspose.{Product} FOSS" title, no `linkTitle` | FAIL — fix family page frontmatter |
| Denominator reconciliation | L-12 | Generation manifest `denominator_gap == 0` (scope-eligible == pages on disk) | FAIL (gap > 5) — run `/batch-reference`; WARN (gap ≤ 5) |
| Cross-subdomain Hugo build | L-13 | Hugo build for all local-theme sites exits 0 | FAIL — fix template/frontmatter errors |
| Grade non-regression | L-14 | No page grade decreased vs baseline in `grade_manifest.json` | FAIL — investigate grade regression |
| Snippet syntax | L-15 | All snippets in `merged/snippets/` are non-empty with balanced brackets | WARN — fix or remove broken snippets |

**Fail-closed policy**: Any FAIL blocks launch. WARN does not block launch but must be logged.

The following 5 gates are executed by S-90 (`/publish-readiness-review`) — see §7c:

| Gate | ID | What it checks | S-90 execution |
|------|----|----------------|----------------|
| Prose review | H-01 | Random sample of 5 non-reference pages reviewed for content quality | S-90 inspection pass: reads each page, checks against `claims.json` and `api_surface.json`, classifies findings |
| Reference accuracy | H-02 | Stratified sample of 10 reference pages spot-checked against source | S-38 (truth-audit) invoked by S-90 Step 7g; checks `evidence.apis` entries against `api_surface.json` |
| Format table spot-check | H-03 | Format support tables verified against `formats.json` | `content_eval --evaluators format_truth` invoked by S-90 Step 7f |
| Link validation | H-04 | All cross-subdomain links resolve in local build | S-65 (link-validate) invoked by S-90 Step 7e |
| License accuracy | H-05 | Open source license claim matches repo LICENSE file | S-90 Step 7h reads LICENSE from clone cache, checks against products page claim |

**Output**: `launch_gate.py` writes a per-gate result report to `reports/launch-gate/{family}-{platform}-{date}.md` (local only — never commit). S-90 writes `reports/publish-review/{family}-{platform}-{date}/final-verdict.md` which covers all H-gate equivalents.

### Launch Planning Governance Rules (added 2026-04-07)

**Translation staging rule**: In S-49 (launch-product), translation is a **terminal stage**.
Stage 6.5 is the **only** translation stage in the launch flow. No translation command may
run before Stage 6 (truth audit) completes with 0 FAIL. All 5 subdomains (products, docs,
kb, reference, blog) must be translated in Stage 6.5 — in a single consolidated batch,
after all English pages across all subdomains have been generated and validated. Any plan
or skill variant that schedules translation for individual subdomains before Stage 6 is in
violation of this rule. The only exception is S-84 (refresh-product), where translation
at Step 11 is content-hash-filtered and runs after content-check and link-validate.

**Translation completeness rule**: For any 5-subdomain launch, all 5 subdomains must be
translated in Stage 6.5 after Stage 6 (truth audit) passes. The Stage 8 readiness scorecard
must report per-subdomain locale coverage. `READY TO SHIP` requires products >= 80% locale
coverage (>= 29 of 36 locales) and all other subdomains >= 70% (>= 26 of 36 locales).
Untranslated subdomains are a launch blocker at the same severity as a failing quality gate.

**Proof-of-mechanism rule**: Any planning statement of the form "derived from X", "generated
from Y", or "one page per Z" MUST identify the exact skill, script, output file, and threshold
involved. Vague derivations — e.g. "one page per distinct capability cluster in claims" without
naming `site_planner.py` / `/site-plan` — are treated as NONE capability (§6b) and must be
escalated. Agents must trace the mechanism to code before writing it into a plan.

**Computed slug policy**: Blog and KB how-to slugs in 5-subdomain launch plans MUST be read
from `/site-plan` output (`reports/plans/{family}/{platform}/site_plan.yaml`). Hardcoding slug
patterns in plan documents is prohibited unless the system explicitly requires manual operator
input and that requirement is documented in the skill contract. This includes the 3rd optional
blog deep-dive post: it is in the site plan or it does not exist — do not add or omit it
based on agent judgment alone.

**Minimum page-count check**: A launch plan that lists exactly 1 KB how-to article, exactly
2 blog posts, or zero cluster-derived developer-guide pages without reading the site plan
output is likely incomplete. Before finalising a launch plan, verify the site plan section
counts match expectations (docs: >= 2 developer-guide pages for non-trivial products;
KB: >= 1 how-to per eligible cluster up to 7; blog: 2 mandatory + optional 3rd).

### §6f Blog Slug Governance (added 2026-04-08)

**Features post slug (Post 2, weight 2, mandatory) MUST be cluster-derived.**
`plan_blog()` in `site_planner.py` derives the Post 2 slug from the highest-claim-count
non-limitations knowledge cluster. The pattern `{family}-key-features-{platform}` is
**banned for `source: derived`**; the validator raises `ValueError` at plan generation time
if it appears on a derived record.

**Existing posts are protected by default.** Any existing post with a `*-key-features-*`
slug is preserved as `source: discovered` on every normal re-plan. These slugs are NEVER
overridden automatically — doing so would break deployed URLs without a redirect strategy.

**Migration path (opt-in only).** To replace a legacy features slug with a cluster-derived
one, a human must explicitly run:
```bash
python scripts/pipeline/commands/launch/site_planner.py {family} {platform} --replan-blog
```
This flag may only be invoked by a human operator with deliberate intent. It MUST NOT be
called automatically from `/launch-product`, `/refresh-product`, or any orchestration skill.
After `--replan-blog` is used, the plan's `sections.blog.pages_to_retire` list will contain
the old post path — run `/page-retire {family} {platform} {old_slug}` immediately for the
replaced post before committing.

**`auto_updatable: false` is an unconditional block.** A blog post with `auto_updatable: false`
in its frontmatter provenance block was authored or edited by a human. Even with `--replan-blog`,
its slug is never overridden. Do not set `auto_updatable: false` on skill-generated content.

**Traceability fields.** All mandatory blog post records in `site_plan.yaml` include:
- `blog_role: announcement | features | deep-dive` — identifies the post's function
- `cluster: {category}` — present on `features` and `deep-dive` records; identifies the
  knowledge cluster that determined the slug

These fields are consumed by `/new-blog-post` to scope content correctly. Do not strip them.

---

## Knowledge Confidence Tier Review Requirements (TC-GP-3, added 2026-05-05)

Products are assigned a knowledge confidence tier based on method coverage percentage from `reports/coverage-tier-table.json`. This tier determines additional review requirements beyond the automated L-gates.

| Knowledge Tier | Method % | Required review |
|----------------|----------|----------------|
| Tier 1 HIGH | ≥ 79% | Automated gates (L-01 through L-09) sufficient |
| Tier 2 MODERATE | 42–78% | S-90 spot-check required (at minimum H-01 sampling) |
| Tier 3 LOW | < 42% | S-90 full review required; PUBLICATION READY blocked until complete |

**Products currently at Tier 3 LOW:** slides/net (39.8%), words/python (32.4%)

**Enforcement:** A PUBLICATION READY verdict for a Tier 3 LOW product that lacks an S-90 evidence bundle is a governance violation. The evidence bundle must be present at `reports/publish-review/{family}/{platform}/` with a `final-verdict.md` showing PUBLICATION_READY.

---

## mandatory_manual_compensation Launch Gate (TC-GP-1, added 2026-05-05)

Some products have `mandatory_manual_compensation: true` in `reports/coverage-tier-table.json`. This flag indicates that the knowledge model's method coverage is too low to rely on automated gates alone — a human reviewer must conduct S-90 before any PUBLICATION READY verdict.

**Products currently flagged:** slides/net (method_pct=39.8%), words/python (method_pct=32.4%)

### Rule TC-GP-1: S-90 Required Before PUBLICATION READY

For any product with `mandatory_manual_compensation: true`:

1. S-90 (`/publish-readiness-review`) MUST be completed with an evidence bundle before a PUBLICATION READY verdict is accepted.
2. S-90 must run **all five H-gates** (H-01 through H-05) — spot-checks are insufficient.
3. For mandatory_manual_compensation products, H-01 must review ALL docs pages, not just the 5-page sample.
4. For mandatory_manual_compensation products, H-04 must review ALL reference class pages, not just the index.
5. S-90 must be run by or under the supervision of a human reviewer — it cannot be delegated to automated execution alone.
6. The S-90 evidence bundle must be committed to `reports/publish-review/{family}/{platform}/` before the PUBLICATION READY verdict is recorded.

**Gate 3 EXPANDED review substitute (sprint forensic-audit-healing-20260505-1238 only):** The Gate 3 EXPANDED manual review conducted for slides/net and words/python in this sprint fulfills the equivalent of S-90 H-01 and H-04 for the purposes of this sprint's verdicts. Future sprints must run S-90 per this rule.

**Violation:** A PUBLICATION READY verdict for slides/net or words/python without an S-90 evidence bundle is a governance violation. The previous PUBLICATION READY verdicts for these products from the 2026-04-30 sprint were declared without this review — those verdicts are reclassified as CONDITIONAL pending S-90 evidence.

---

## PUBLICATION READY Grade Floor (TC-GP-2, added 2026-05-05)

gap-eval PUBLICATION READY verdict (no M-findings) is a necessary but not sufficient condition for publication. The following grade floor policy applies to content-eval grades.

### Rule TC-GP-2: Minimum Grade Floor by Page Type

| Page type | Minimum grade for publication | Evaluator scope |
|-----------|------------------------------|----------------|
| Docs developer-guide pages | B or better | All canonical evaluators |
| Blog posts (English, published) | B or better | All canonical evaluators |
| KB how-to articles (English, published) | B or better | All canonical evaluators |
| Reference class pages | Exempt from grade floor* | See note |
| Locale-variant pages | Same as English source | Must not be lower than English source |

*Reference pages are exempt from the grade floor until the canonical evaluator false-positive rate for reference content is characterized. Known false-positive sources: `description_completeness` for reference tables (systematic), `api_accuracy` for interface-inherited members (slides/java ISS-SLIDESJAVA-001). These must be resolved before the exemption is lifted.

**Enforcement:** A product with docs or blog pages at grade D or F (canonical grade, not experimental) may not be declared PUBLICATION READY even if gap-eval shows no M-findings.

**Known violations at time of writing (2026-05-05):**
- email/cpp: 23 locale blog variant pages at grade D — must be remediated before next PUBLICATION READY declaration
- No docs or blog pages at grade D/F for other products (reference pages excluded per exemption)

---

## Evaluator Design Stability Rule (TC-FN-001B framework, added 2026-05-05)

New evaluators must not be added to the CANONICAL_EVALUATORS set without a 14-day experimental period as specified in GRADE_CONTRACT.md §6. This applies to all new evaluators regardless of their expected impact on grades.

**Process for adding a new canonical evaluator:**
1. Add to EXPERIMENTAL_EVALUATORS in config.py only (not CANONICAL)
2. Run for 14 days across all 16 products
3. Document false-positive rate and impact on grade distribution
4. Human review of false-positive rate before promoting to canonical
5. Only after step 4 approval: move from EXPERIMENTAL_EVALUATORS to CANONICAL_EVALUATORS

**Pending evaluators in experimental stage:** None at time of writing (TC-FN-001B design only — no implementation yet).

---

## Metrics Gate

Before promoting a metrics sprint to production posting (Slice 15+), the following gates apply:
1. All dry-run payloads validate (`check_metrics_sheet_payload_schema.py` passes)
2. Secret scan passes (`check_metrics_no_secrets.py`)
3. At least 1 test row confirmed in the Google Sheet (`job_type="test"`, `[TEST]` prefix)
4. `AGENT_METRICS_ENDPOINT` and `AGENT_METRICS_TOKEN` verified in environment
5. Owner explicitly approves (`owner_approved=True` in `MetricsSubmitter`)

See `AGENTS.md §15` for the full metrics obligation.
