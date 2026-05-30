# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/pre-refactor/governance/positioning-policy.md

---

# Aspose.org Advisory Positioning Policy

**Status**: Advisory — guides generation, review, and repair. Does not block commits.
**Created**: 2026-05-19
**Updated**: 2026-05-22 (enterprise-positioning-system-healing sprint — v2 anchor policy)

## Core Rule

Aspose.org = open-source / FOSS / entry-level / developer-friendly file format libraries.
Aspose.com = enterprise-grade / commercial / full-featured product line.

Content on Aspose.org must not position the FOSS libraries as enterprise-grade or equivalent to Aspose.com.

## Preferred Language for Aspose.org

- open source, FOSS, entry-level, developer-friendly
- starter libraries, native SDKs, community-accessible, file format libraries
- Use "MIT-licensed" only where verified true for the specific product/platform
- Use "zero-dependency" or "dependency-light" only where verified true

## Avoided Language for Aspose.org Self-Description

The following terms are FORBIDDEN when describing Aspose.org FOSS libraries themselves:
- enterprise-grade, enterprise-ready, enterprise-level, enterprise-class
- mission-critical enterprise, commercial-grade, premium

## Enterprise Language — ALLOWED and REQUIRED in Aspose.com CTAs

The word "Enterprise" is REQUIRED (not forbidden) when the sentence points the reader to Aspose.com:
- Anchor text MUST use "Aspose.{Family} Enterprise Product Family" (family URL targets)
- Anchor text MUST use "Aspose.{Family} for {Platform} Enterprise Product" (platform URL targets)
- Reference pages MUST use "Aspose.{Family} [for {Platform}] — Enterprise API Reference"
- "Commercial Edition", "Commercial Reference", "commercial product family" are DEPRECATED

Deprecated anchor patterns (must not appear in new or healed content):
- `— Commercial Edition` (any form)
- `— Commercial Reference`
- `commercial product family with dedicated support` (CTA sentence)
- `commercial counterpart` (CTA sentence)
- Platform-level anchor with family-level URL (PLATFORM_IMPLIED_BUT_TARGET_FAMILY_ONLY)

## Do NOT Overcorrect

Content should sound valuable, useful, credible, and practical. Avoid weak or apologetic language.

## Upgrade CTA Language (Required v2 — Enterprise Anchors)

Compliant CTA examples (v2 — Enterprise positioning):
- Family target: "For the enterprise product family, see [Aspose.{Family} Enterprise Product Family](https://products.aspose.com/{family}/)."
- Platform target: "For enterprise features and support, see [Aspose.{Family} for {Platform} Enterprise Product](https://products.aspose.com/{family}/{platform}/)."
- Reference: "- [Aspose.{Family} for {Platform} — Enterprise API Reference](https://products.aspose.com/{family}/{platform}/)"
- Natural sentence (docs/kb/blog): "Developers requiring enterprise features can use Aspose.{Family} for {Platform} Enterprise Product alongside these open-source libraries."

These CTAs position Aspose.com as the enterprise destination, not Aspose.org.

## Per-Subdomain Tone

| Subdomain | Tone | Enterprise Self-Claims |
|-----------|------|----------------------|
| products.aspose.org | Marketing-credible, FOSS-positioned | Forbidden |
| docs.aspose.org | Developer-guide, neutral technical | Forbidden (comparison context OK) |
| kb.aspose.org | Practical how-to | Forbidden |
| blog.aspose.org | Announcement/explanatory | Forbidden (upgrade CTA OK) |
| reference.aspose.org | Pure API reference | Forbidden |
| www.aspose.org | Homepage marketing, FOSS-first | Forbidden |

## Finding Classification Taxonomy

| Code | Definition | Action |
|------|-----------|--------|
| SELF_POSITIONING_VIOLATION | FOSS product described as enterprise-grade/class/level | MUST FIX |
| ASPOSE_COM_ENTERPRISE_CTA_REQUIRED | CTA to aspose.com using deprecated "commercial edition" wording | MUST FIX — use Enterprise anchor |
| WRONG_ENTERPRISE_ANCHOR | Enterprise anchor has wrong form (e.g., platform anchor with family URL) | MUST FIX |
| PLATFORM_IMPLIED_BUT_TARGET_FAMILY_ONLY | Platform name in anchor but target URL is family-level | MUST FIX |
| ASPOSE_COM_UPGRADE_CTA_COMPLIANT | CTA using correct v2 Enterprise anchor wording | KEEP |
| LEGITIMATE_TECHNICAL_USE | "Enterprise" describes use case or licensing comparison | NO ACTION |
| HISTORICAL_OR_QUOTED_CONTEXT | Quoted text or historical reference | NO ACTION |
| NEEDS_REVIEW | Ambiguous | TRIAGE |
| FALSE_POSITIVE | Regex matched but not a positioning issue | NO ACTION |

## Evaluator Integration

The risk_language evaluator (experimental, INFO severity) detects:
- enterprise-grade (including Unicode U+2011 non-breaking hyphen)
- enterprise-ready, enterprise-level, enterprise-class
- commercial-grade

INFO severity means: detected and reported, but does not affect page grade or block commits.

## Future Governance Escalation Path

Phase 2 (not yet active):
1. Escalate severity from INFO to WARN
2. Add context-aware detection to distinguish self-positioning from CTAs
3. Add positioning_exception: true frontmatter field for excepted pages
4. After full content migration, consider FAIL for self-positioning violations

---

## Metrics Obligation

This policy governs content positioning language only. It does not involve LLM API calls or metrics capture. No AGENT_METRICS integration required.
