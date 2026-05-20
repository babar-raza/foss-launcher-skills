---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §9
# Plan: delightful-wondering-hartmanis (TC-04)
# Extracted: 2026-04-28
---

# Maintenance Workflow

> **Updated 2026-04-07 (S-84 added):** Use `/refresh-product` as the canonical path.
> The manual 5-step chain below is **deprecated** — see §6 (Maintenance chain) for the
> operative chain. §6 is authoritative. §9 is preserved for reference only.

**Trigger**: upstream FOSS repo has changed since last knowledge extraction
(i.e., `knowledge/{family}/{platform}/merged/model.yaml stale_since` is not null,
or `refresh_knowledge.py --check-only` reports STALE).

**Canonical path — use this**:
```
/refresh-product {family} {platform}
```
S-84 orchestrates the complete 14-step chain (detect → knowledge-update → delta-site-plan
→ page-update → delta-dispatch → page-retire → reference-regen → family-sync →
content-check → link-validate → translate → verify → commit). See §6 Maintenance chain
for the full step sequence with progress tracking.

<details>
<summary>Deprecated manual chain (pre-S-84; do not follow)</summary>

1. S-12 (diff) — identify which files changed
2. S-13 (stale-detect) — which content pages are affected
3. For each affected page: S-14 → S-20 → S-25
4. S-15 (embed-knowledge) — sync vector store if used
5. Commit: `knowledge/` changes + `content/` changes together

</details>

