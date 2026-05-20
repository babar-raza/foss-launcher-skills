<!-- Adapted from aspose.org docs/workflows/ for standalone use -->

# Maintenance Workflow

> **Updated:** Use `/refresh-product` as the canonical path.
> The manual 5-step chain below is **deprecated** -- see the skill chains document
> (Maintenance chain) for the operative chain. The skill chains document is authoritative.
> This document is preserved for reference only.

**Trigger**: upstream FOSS repo has changed since last knowledge extraction
(i.e., `knowledge/{family}/{platform}/merged/model.yaml stale_since` is not null,
or `refresh_knowledge.py --check-only` reports STALE).

**Canonical path -- use this**:
```
/refresh-product {family} {platform}
```
The refresh-product skill orchestrates the complete 14-step chain (detect -> knowledge-update ->
delta-site-plan -> page-update -> delta-dispatch -> page-retire -> reference-regen -> family-sync ->
content-check -> link-validate -> translate -> verify -> commit). See the skill chains document
(Maintenance chain) for the full step sequence with progress tracking.

<details>
<summary>Deprecated manual chain (do not follow)</summary>

1. Knowledge-diff -- identify which files changed
2. Stale-detect -- which content pages are affected
3. For each affected page: knowledge-update -> page-update -> eval-page
4. Embed-knowledge -- sync vector store if used
5. Commit: `knowledge/` changes + `content/` changes together

</details>
