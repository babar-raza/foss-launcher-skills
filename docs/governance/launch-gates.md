# Launch Gates — foss-launcher Governance

**Source**: Adapted from aspose.org `docs/governance/launch-gates.md`
**Adapted**: 2026-05-15 (PAR-013 GV-003)

---

## Launch-Readiness Gates

Before any product launch (new family/platform going live), all automated gates must pass.

| Gate | ID | What it checks | Fail behavior |
|------|----|----------------|---------------|
| Knowledge freshness | L-01 | `model.yaml stale_since` is null | FAIL — run S-12 → S-14 |
| Evidence coverage | L-02 | All content files have non-empty `evidence:` block | FAIL — run `attach_evidence.py` |
| Forbidden claims | L-03 | `change_guard.py` reports 0 DENY on active claims | FAIL — remove or correct claim |
| API accuracy | L-04 | `audit.py` exits 0 FAIL on all content files | FAIL — fix API references |
| Format truth | L-05 | `content_eval --evaluators format_truth` exits 0 FAIL | FAIL — correct format table |
| Knowledge reconciliation | L-06 | `promote.py` reconciliation passes | FAIL — fix formats.json or claims |
| Pipeline tests | L-07 | `pytest tests/` exits 0 | FAIL — fix broken test |
| Provenance coverage | L-08 | All English content files with provenance block have `content_origin` set | FAIL — run provenance_backfill.py |
| Grade non-regression | L-14 | No page grade decreased vs baseline | FAIL — investigate grade regression |
| Snippet syntax | L-15 | All snippets in `merged/snippets/` are non-empty with balanced brackets | WARN — fix or remove broken snippets |

**Fail-closed policy**: Any FAIL blocks launch. WARN does not block launch but must be logged.

## Manual Review Gates (executed by S-95 publish-readiness-review)

| Gate | ID | What it checks |
|------|----|----------------|
| Prose review | H-01 | Random sample of 5 non-reference pages reviewed for content quality |
| Reference accuracy | H-02 | Stratified sample of 10 reference pages spot-checked against source |
| Format table spot-check | H-03 | Format support tables verified against `formats.json` |
| Link validation | H-04 | All cross-subdomain links resolve |
| License accuracy | H-05 | Open source license claim matches repo LICENSE file |

## Launch Planning Governance Rules

**Translation staging rule**: In S-38 (launch-product), translation is a **terminal stage**.
All 5 subdomains must be translated after all English pages have been generated and validated.
No translation command may run before truth audit (S-47 truth-audit) completes with 0 FAIL.

**Translation completeness rule**: For a 5-subdomain launch, all 5 subdomains must be
translated. `READY TO SHIP` requires products ≥ 80% locale coverage and all other
subdomains ≥ 70%.

**Proof-of-mechanism rule**: Any planning statement of the form "derived from X", "generated
from Y", or "one page per Z" MUST identify the exact skill, script, output file, and threshold.
Vague derivations are treated as NONE capability and must be escalated.

**Computed slug policy**: Blog and KB how-to slugs MUST be read from S-57 (`/site-plan`) output.
Hardcoding slug patterns in plan documents is prohibited.

## Knowledge Confidence Tier Review Requirements

Products are assigned a knowledge confidence tier based on method coverage percentage.

| Knowledge Tier | Method % | Required review |
|----------------|----------|----------------|
| Tier 1 HIGH | ≥ 79% | Automated L-gates sufficient |
| Tier 2 MODERATE | 42–78% | S-95 spot-check required (at minimum H-01 sampling) |
| Tier 3 LOW | < 42% | S-95 full review required; PUBLICATION READY blocked until complete |

## Grade Floor Policy

| Page type | Minimum grade for publication |
|-----------|------------------------------|
| Docs developer-guide pages | B or better |
| Blog posts (English, published) | B or better |
| KB how-to articles (English, published) | B or better |
| Reference class pages | Exempt until false-positive rate characterized |
| Locale-variant pages | Same as English source |

A product with docs or blog pages at grade D or F may not be declared PUBLICATION READY
even if automated gates show no M-findings.
