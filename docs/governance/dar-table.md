# Dependency Authority Registry (DAR)

Status: Current
Audience: Agent, Operator
Last verified: 2026-07-16 (full skill-ID audit against docs/registries/skills.md — 8 stale mappings corrected; see aspose-org-foss-refresh-tidy-lightning.md RPR-A-04)

## Summary

The DAR maps downstream skills to their upstream knowledge dependencies.
Skills that consume knowledge artifacts must declare their dependency here
so that stale-knowledge risks are visible and CI can enforce bootstrap order.

See AGENTS.md §6a for the full DAR governance rules.

## DAR Table

| Downstream skill | Upstream skill | Trigger |
|---|---|---|
| `/batch-eval-fix` (S-41) | `/knowledge-bootstrap` | Knowledge artifacts must exist before evaluation |
| `/batch-reference` (S-62) | `/knowledge-bootstrap` | Requires api_surface.json for page generation |
| `/batch-remediate` (S-40) | `/knowledge-bootstrap` | Requires knowledge for remediation grounding |
| `/change-guard` | `/knowledge-bootstrap` | Requires knowledge to assess change impact |
| `/content-audit` (S-32) | `/knowledge-bootstrap` | Requires knowledge for semantic verification |
| `/content-check` (S-23) | `/knowledge-bootstrap` | Requires knowledge for accuracy audit |
| `/content-enrich` (S-98) | `/knowledge-bootstrap` | Requires knowledge for cross-subdomain enrichment |
| `/family-sync` (S-48) | `/knowledge-bootstrap` | Requires knowledge to sync family page |
| `/faq-generate` (S-22) | `/knowledge-bootstrap` | Requires knowledge for FAQ grounding |
| `/gap-apply` (S-46) | `/knowledge-bootstrap` | Requires knowledge for fix spec execution |
| `/heal-page` (S-26) | `/knowledge-bootstrap` | Requires knowledge for page healing |
| `/new-blog-post` (S-57) | `/knowledge-bootstrap` | Requires knowledge for blog content grounding |
| `/new-blog-post` (S-57) | `data/package_registry.json` | Same install-instruction data-file dependency as `/new-docs-page` below (Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-02: S-57 was found ungrounded and additionally sourcing package identity from `scout/model.yaml.canonical_import` — a full-repo audit found this exact skill's output responsible for a large share of the ~5,000+ pages carrying fabricated or never-published install commands). |
| `/new-docs-index` (S-70) | `/knowledge-bootstrap` | Requires knowledge for docs index scaffold |
| `/new-docs-page` (S-56) | `/knowledge-bootstrap` | Requires knowledge for docs page grounding |
| `/new-docs-page` (S-56) | `data/package_registry.json` | Install-instruction rendering (maven-coord/maven-gav/cargo-crate/package-install shortcodes) reads this file directly — a data-file dependency, not a skill-form one, since no skill currently maintains it end-to-end (root cause 1, Mission MT015-2026-07-30-PACKAGE-REGISTRY: this exact gap — a mandated grounding source with no producer — is what let 3D-NET-REFRESH-002's wrong NuGet command ship undetected). `/repo-scout` (S-34) + `naming_convention_candidate()` (TC-MT015-07) populate the "candidate" side; the planned `/package-publish-watch` (TC-MT015-09, not yet built) will be the live-verification producer for `verification.published`. |
| `/new-kb-faq` (S-59) | `/knowledge-bootstrap` | Requires knowledge for KB FAQ generation |
| `/new-kb-faq` (S-59) | `data/package_registry.json` | Same install-instruction data-file dependency as `/new-docs-page` below (Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-02: added grounding guidance for the "How do I install?" FAQ answer, which previously had none). |
| `/new-kb-howto` (S-58) | `/knowledge-bootstrap` | Requires knowledge for KB how-to generation |
| `/new-kb-howto` (S-58) | `data/package_registry.json` | Same install-instruction data-file dependency as `/new-docs-page` below (Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-02: S-58 was found ungrounded for python/net/typescript, literally instructing `pip install`/`dotnet add package`/`npm install` — a full-repo audit found this exact skill's output responsible for a large share of the ~5,000+ pages carrying fabricated or never-published install commands). |
| `/new-kb-index` (S-69) | `/knowledge-bootstrap` | Requires knowledge for KB index scaffold |
| `/new-products-page` (S-61) | `/knowledge-bootstrap` | Requires knowledge for products page generation |
| `/new-products-page` (S-61) | `data/package_registry.json` | Same install-instruction data-file dependency as `/new-docs-page` above (root cause 1, Mission MT015-2026-07-30-PACKAGE-REGISTRY) — see that row for detail. |
| `/new-reference-index` (S-71) | `/knowledge-bootstrap` | Requires knowledge for reference index scaffold |
| `/new-reference-page` (S-60) | `/knowledge-bootstrap` | Requires knowledge for reference page generation |
| `/page-draft` (S-19) | `/knowledge-bootstrap` | Requires knowledge for draft grounding |
| `/page-plan` (S-18) | `/knowledge-bootstrap` | Requires knowledge for page planning |
| `/publish-readiness-review` (S-90) | `/knowledge-bootstrap` | Requires knowledge for publish verification |
| `/refresh-product` (S-84) | `/knowledge-bootstrap` | Requires knowledge for product refresh |
| `/register-human-content` (S-66) | `/knowledge-bootstrap` | Requires knowledge for evidence attachment |
| `/seo-review` (S-116) | `/knowledge-bootstrap` | Grounding-check step independently re-verifies each recommendation against claims.json/formats.json before approving |
| `/site-plan` (S-47) | `/knowledge-bootstrap` | Requires knowledge for site planning |
| `/system-heal` (S-87) | `/knowledge-bootstrap` | Requires knowledge for system healing |
| `/truth-audit-content` (S-85) | `/knowledge-bootstrap` | Requires knowledge for truth audit |

## Exceptions

Skills in the `DAR_EXCEPTIONS` set in `scripts/ci/checks/check_dar_coverage.py`
are excluded from this table. See the script for justifications (Category B
orchestrators managing their own chains, Category C false positives).

## Metrics Obligation

Pipeline workflows using `llm.professionalize.com` carry a metrics obligation. Decision records
that approve new professionalize call sites must note the corresponding `metrics_callsite_registry.yaml`
entry and the `AGENT_METRICS` capture method. See `AGENTS.md §15`.

## Related

- [AGENTS.md §6a](../../AGENTS.md) — DAR governance rules
- [check_dar_coverage.py](../../scripts/ci/checks/check_dar_coverage.py) — CI validator
