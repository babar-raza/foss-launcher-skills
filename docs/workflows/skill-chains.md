# Skill Chains by Task

> Source: AGENTS.md §6
> Status: Current (restored from archive 2026-06-24)
> Override token: 20260624-113217-docs-workflows-mental-model-refresh-md

Skills are the **only sanctioned execution mechanism** for the task types listed below. When
your requirement matches a listed task type, follow the corresponding chain — invoking each skill
in order, passing outputs forward, and not substituting manual reasoning for any step that has a
registered skill. If your requirement does not match any listed task type, follow the protocol in
`docs/workflows/gap-escalation.md` before doing anything else.

## Initial Generation (New Page)

```
S-10 (project-phase-store) → S-18 (page-plan) → S-19 (page-draft) → S-22 (faq-generate)
→ S-23 (content-check / audit.py) → S-38 (truth-audit) → S-01 (path-guard) → write
```

## Knowledge Bootstrap

```
S-34 (repo-scout) → S-37 (knowledge-enrich) → S-35 (truth-merge) → S-31 (truth-index)
```

## Full-Product Launch (5-Subdomain)

```
S-54 (knowledge-bootstrap) → S-47 (site-plan) → S-49 (launch-product stages 1–8)
```

Every launch MUST run `/site-plan` after knowledge bootstrap and BEFORE any content generation.
The site plan output (`reports/plans/{family}/{platform}/site_plan.yaml`) is the authoritative
slug manifest. Stages that skip site-plan are in violation of this chain.

## Maintenance (Repo Changed)

Use S-84 (refresh-product) to run the full maintenance cycle:

```
/refresh-product {family} {platform}
```

S-84 orchestrates internally:
```
S-12 (knowledge-diff) → S-14 (knowledge-update) → S-82 (delta-site-plan)
→ S-20 (page-update) → S-62 (batch-reference) → S-48 (family-sync)
→ S-23 (content-check) → S-65 (link-validate) → S-76 (commit)
```

**Optional — vector regeneration**: after a knowledge update, S-15 (embed-knowledge)'s
`gap-index` mode may be re-run for the affected product to keep S-43 (gap-eval) Tier 2 vectors
current — skip if already current (see `docs/pipeline/vector-regeneration-procedure.md`'s
coverage-report command). This is non-blocking: content generation and the maintenance chain
above do not require it.

## Reusable Propagation Chain (Release or Upstream Drift, Any Family/Platform)

> Added by mission MT074. One parameterised chain; no per-product code. Use it whenever a product
> has a new release or API-touching upstream change whose features are not yet on the five sites.

```
release / drift detected
→ S-94 (change-sweep: fleet_drift.py step, then L2-L4 analysis for candidates)
→ S-95 (discovery-triage: keyed FLEET-PROPAGATE-{family}-{platform}-{sha8} row)
→ S-84 (refresh-product --mode upstream: knowledge, capability ledger, reference rebuild, existing-page refresh)
→ S-126 (example-write: verified examples for units that need code)
→ surface skills by disposition
     docs: S-56 (new-docs-page) / S-20 (page-update)   kb: S-58 (new-kb-howto)
     blog: S-57 (new-blog-post) + S-124 (blog-release-check)   products: S-73 (manual-edit)
→ S-23 (content-check) and S-90 (publish-readiness-review): author-side gates
→ S-127 (independent-content-review: calibrated, author-separated panel; page-by-page clearance)
→ capability_surface_gate.py (the close step of S-84; sole writer of content_propagated_*)
→ S-76 (commit) / git_plumb_commit.py --no-push, one commit per class of change
→ publication-readiness dossier
→ user-gated push
```

How the links work:

- **Detection.** The weekly monitor workflow, the 6-hourly registry watch (its release-trigger step) or an on-demand `fleet_drift.py` run puts a product in `DRIFTED` (or a new release) in `data/content_propagation_state.json`. A product with no record is `UNRECORDED`, which is drift by definition. Detection compares upstream with the last *content-propagated* SHA, never with the knowledge-accepted baseline, so a knowledge-only refresh cannot hide drift.
- **Triage.** S-95 files one keyed, duplicate-safe backlog row. It never starts the refresh.
- **Refresh.** S-84 builds the capability ledger: every new capability unit gets a disposition (`create | update | mention | none`) on each of reference, docs, kb, blog and products. Plan-stage Check 13 proves the ledger complete.
- **Examples.** S-126 selects code mechanically from harvested snippets and docs fences, verifies it against the product artifact, and hands the content skills a table. Unverified code never reaches a page.
- **Surfaces.** One skill per disposition; every content edit runs under an S-73 context. The skills record their decision with `capability_ledger.py set-disposition`.
- **Verification.** S-90 is the author's gate. S-127 is the independent one: fresh read-only reviewers, a calibrated panel, hash-bound verdicts. An edit after review invalidates the verdict.
- **Close.** `capability_surface_gate.py` recomputes satisfaction from the files and, only on PASS, records the propagation (`PROPAGATED_LOCAL` while content is committed but not pushed). A product whose gate has not passed is still drifted.
- **Push.** Content is never pushed by a skill. A state commit containing `PROPAGATED_LOCAL` is never pushed. Capability `availability` flips from `unreleased` to `released` automatically once the published release contains the symbols, which removes the availability qualifier on the next run.

If a step finds a defect in the machinery rather than in one product's content, open a hardening card
(`/pipeline-harden`, S-99; `/workflow-harden`, S-115 for deployed-workflow templates) with a failing test
first, then replay the fix against products already processed.

## Healing / Fix

```
S-73 (manual-edit) → S-23 (content-check) → S-90 (system-heal if multi-page)
```

## Translation (Single Page)

```
/ht-translate {src_path} {site} {locales}
  -> hugo-translator CLI (--site explicit, --validation-mode normal, --force-accept)
  -> dry-run pass
  -> live translation to OUTPUT_TMP
  -> manual review of output
  -> copy step to content/{site}/{lang}/
  -> /commit (S-76)
```

The `{site}` argument is mandatory. No site profile = no translation.
Valid site profiles: `docs.aspose.org`, `kb.aspose.org`, `products.aspose.org`,
`reference.aspose.org`, `blog.aspose.org`, `www.aspose.org`.

## Translation (Batch)

```
/ht-translate-batch {family} {platform} {site} {locales}
  -> scope estimation (warn if >500 jobs)
  -> hugo-translator CLI (--site explicit, --validation-mode normal, --force-accept)
  -> dry-run pass
  -> live batch translation to OUTPUT_TMP
  -> spot-check 3-5 output files
  -> copy step to content/{site}/{lang}/
  -> /commit (S-76)
```

www.aspose.org requires `--force-retranslate --force-restart`.
blog.aspose.org must use m2m100_418m model only (not m2m100_1.2b -- OOM).

## Locale Patch (Targeted Fix)

```
S-75 (locale-patch) -> patch discovery -> apply -> validate_frontmatter.py
```

## Post-Body-Refresh Re-Translation

```
S-105 (body-refresh) -> S-107 (locale-refresh-handoff)
  -> < 3 sentences changed: S-75 (locale-patch)
  -> >= 3 sentences changed: S-56 (new-docs-page) for full re-translation
```

## Production Localization Incident

```
S-109 (production-localization-incident)
  -> containment + forensics
  -> rectification via S-HT-01 / S-HT-02 (hugo-translator, explicit --site)
  -> hardening via S-99 (pipeline-harden)
```

## Retired Translation Paths (DO NOT USE)

The following are permanently retired and must not be recreated:
- `/translate` -> was dispatcher to S-52/S-53; now tombstone
- `S-52 translate-page` -> deleted; internal `python -m translator` package deleted
- `S-53 translate-batch` -> deleted; internal `python -m translator` package deleted
- `scripts/translator/` -> deleted; no fallback

## Archive

Pre-refactor version:
[docs/_archive/pre-refactor/workflows/skill-chains.md](../_archive/pre-refactor/workflows/skill-chains.md)
