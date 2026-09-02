---
name: ht-translate-batch
id: S-HT-02
description: >
  Skill description pending
---

# S-HT-02: HT-Translate-Batch — Batch Translation via Hugo-Translator

Translate all English content pages for a product family/platform to one or more of the
**25 approved target locales** using the external `hugo-translator` tool's **governed
zero-defect campaign path**.

**Arguments:** `$ARGUMENTS`
**Expected format:** `{family} {platform} {site} {locales}` — e.g.:
`slides net docs.aspose.org fr,de,ar`
`cells java kb.aspose.org all`

- `{family}` — product family (e.g. `slides`, `cells`, `pdf`, `3d`)
- `{platform}` — platform (e.g. `net`, `java`, `python`, `cpp`, `typescript`)
- `{site}` — explicit site profile ID (required — no guessing, no default, no `all`)
- `{locales}` — comma-separated subset of the approved set, or `all` for **all 25 approved locales**
  (`ar cs de el es fa fr he hi hu id it ja ko nl pl pt ro ru sv th tr uk vi zh`).
  The 11 codes `bg ca da fi hr lt lv ms no sk sr` are disabled in every site's Hugo config and
  rejected by every profile's `strict_locale_allowlist` — they are never generated.

> **Governed path only (2026-09-02, TC-APT-025 of mission aspose-org-full-portfolio-translation-20260901).**
> The former plain-CLI invocation (`src.cli … --validation-mode normal --force-accept`) is
> retired: it bypassed the zero-defect write-gate promotion and the receipt ledger. The only
> sanctioned translation execution path is `src/workers/campaign_runner.py` under
> `validation_policy: zero-defect`, driven through a campaign manifest as below. Do not fall back
> to the plain CLI, to `.local/*.py` scripts, or to any `--force-accept` / validator-skip flag.

## Mandatory Pre-Conditions

1. `{site}` argument is one of the valid profile IDs — stop if missing or not recognized
2. Profile exists at `C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/config/site_profiles/{site}.yaml`
3. Content exists at `content/{site}/en/{family}/{platform}/` (blog: `content/blog.aspose.org/{family}/{platform}/`)
4. hugo-translator venv exists at `C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/.venv/`
   (always invoke it as `.venv/Scripts/python` — never bare `python`)
5. The content-repo session ledger is active (`/session-start`): the runner writes receipt-backed
   files directly into `content/{site}/{lang}/…`, and only receipt-listed paths are adopted and committed

## Valid Site Profile IDs

- `docs.aspose.org` — Documentation site
- `kb.aspose.org` — Knowledge base
- `products.aspose.org` — Product landing pages (`max_parallel_files=1` in profile — do not override)
- `reference.aspose.org` — API reference
- `blog.aspose.org` — Blog (file-suffix layout; profile pins `m2m100_418m` — the 1.2B model crashes this host)
- `websites.aspose.org` — Corporate site pages (`content/websites.aspose.org/` is NOT in `path_guard.py`'s
  allowlist: every commit touching it needs an `override_manager.py create` token first — see Step 8)
- ~~`www.aspose.org`~~ — **out of scope** of the governed portfolio mission (operator decision 2026-09-01);
  not a valid target for this skill

## Hard Stops

**STOP** and fail with an error if:
- `{site}` is missing, empty, `all`, or not in the valid profile list above
- `{site}` is `all` — this is NOT allowed. One site per invocation.
- Profile file does not exist in the hugo-translator repo
- Content directory for `{family}/{platform}` does not exist
- Any requested locale is outside the 25 approved codes
- The manifest verify step (Step 4) reports drift, an unreceipted existing output, or a dirty source

Do NOT fall back to any other translation mechanism. Do NOT loop over sites automatically.
Do NOT pass `--force-accept`, `--validation-mode`, or any bypass environment variable.

## Scope Estimation

Before running: estimate scope from the manifest the builder prints
(`sources=N outputs=M locales=L`). If `outputs > 500`, warn the operator and request explicit
confirmation before proceeding.

## Execution Steps

### Step 1 — Validate arguments
Parse `$ARGUMENTS`: extract `{family}`, `{platform}`, `{site}`, `{locales}`.
- If `{site}` is missing, `all`, or invalid: output error and stop.
- If content path does not exist: output error and stop.
- Expand `all` to the 25 approved codes; reject anything outside them.

### Step 2 — Build a scoped campaign manifest
```bash
cd "C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator"
.venv/Scripts/python scripts/campaign/build_campaign_manifest.py \
  --content-repo "D:/onedrive/Documents/GitHub/aspose.org" \
  --site {site} --family {family} --platform {platform} \
  --locale {locale_1} --locale {locale_2} ... \
  --campaign-id "ht-batch-{site}-{family}-{platform}-{YYYYMMDD-HHMMSS}" \
  --manifest-output "data/campaigns/manifests/ht-batch-{site}-{family}-{platform}-{stamp}.yaml"
```
The builder uses the profile's own discovery filter (fed the full language registry, so legacy
`index.bg.md`-style files are never mistaken for sources) and the engine's own output-path
logic; the manifest is `validation_policy: zero-defect` by construction.

### Step 3 — Pre-existing targets
The runner refuses to overwrite an existing target that is not declared in the manifest. Cells
whose target already exists must be declared for governed replacement (`replace_existing` with
the current file's SHA256 — TC-APT-031) or excluded from the batch. Never delete existing files
to get around this.

### Step 4 — Verify (read-only) before translating
```bash
.venv/Scripts/python -m src.workers.autonomous_content_translation_worker \
  --mode oneshot \
  --campaign-manifest "data/campaigns/manifests/ht-batch-{site}-{family}-{platform}-{stamp}.yaml" \
  --validation-policy zero-defect \
  --verify-only
```
Any drift, unreceipted existing output, or dirty-source finding is a hard stop.

### Step 5 — Run the governed batch
```bash
.venv/Scripts/python -m src.workers.autonomous_content_translation_worker \
  --mode oneshot \
  --campaign-manifest "data/campaigns/manifests/ht-batch-{site}-{family}-{platform}-{stamp}.yaml" \
  --validation-policy zero-defect
```
Work is processed in deterministic shards of at most 250 outputs. Every output passes all 44
write gates (the 13 warn-tier gates are promoted to block under zero-defect) or is not written.
Accepted files land **directly** in `content/{site}/{lang}/…` and are receipted in
`data/campaigns/{campaign-id}/acceptance_receipts.jsonl`; rejected candidates are recorded
content-free in `failures.jsonl`. No temp directory, no copy step. After a crash or a qualified
pipeline fix, add `--resume`.

### Step 6 — Concurrency
Concurrency is governed by the manifest's `execution_policy.max_parallel_jobs` (default 1; raised
only after hugo-translator's TC-APT-028 calibration). Do not run two campaigns against the same
site concurrently; the campaign lock will refuse the second runner.

### Step 7 — Review
- Receipts: all 44 gates `passed`, none with action `warn`.
- Spot-check 3–5 representative files: evidence block unchanged, shortcodes preserved, no
  placeholder leakage, product names not transliterated.
- Blocked outputs are reviewed one at a time (Block-Queue) — never force-accepted.

### Step 8 — Adopt and record
```bash
cd "D:/onedrive/Documents/GitHub/aspose.org"
.venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py adopt --files <exactly the receipt-listed paths>
.venv/Scripts/python scripts/pipeline/commands/ops/session_ledger.py candidates --format json   # must equal the receipt set
```
For `websites.aspose.org` paths, create the override token before staging:
```bash
.venv/Scripts/python scripts/pipeline/commands/governance/override_manager.py create \
  --paths <the content/websites.aspose.org/... paths> \
  --reason "S-HT-02 governed locale batch" --plan "<plan or taskcard reference>"
```
Record in the skill run evidence: `site_profile`, `family`, `platform`, `target_locales`,
`campaign_manifest`, `file_count`, receipt count, `hugo_translator_revision` (`git describe`).

### Step 9 — Commit via /commit
Do not commit directly. Use `/commit` (S-76) with a skill run record declaring `S-HT-02`;
the commit body must carry `Skills invoked: [S-HT-02]` and exactly one `Co-Authored-By` trailer.
Sub-scope the title by family/platform (e.g. `content(locale): words/net docs ar–zh batch 3`),
one commit per logical batch. Never push.

## Push Coordination

If multiple batches run concurrently (e.g., different families):
- Each batch agent MUST NOT commit or push independently.
- A single coordinator or the human operator performs the final commit+push after all batches complete.

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` through the hugo-translator LLM backend,
the run carries a metrics obligation per AGENTS.md §15.

## Retirement Note

This skill replaces the retired S-53 (`translate-batch`). The internal `scripts/translator/`
package has been deleted. Do not recreate it. The plain-CLI `--force-accept` invocation this
skill used until 2026-09-02 is likewise retired (hugo-translator plan G-16/G-18).
