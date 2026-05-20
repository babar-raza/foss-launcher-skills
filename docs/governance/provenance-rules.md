---
# Governance child document — extracted from AGENTS.md
# Source: adapted from AGENTS.md §10b
# Plan: delightful-wondering-hartmanis (TC-03)
# Ported: 2026-05-20 (parity migration sprint)
---

## 10b. Content Provenance Rules

Every `.md` content file carries a `provenance:` block in its YAML frontmatter. This block is **internal metadata** — never rendered in site templates.

### Provenance fields

```yaml
provenance:
  content_origin: skill-generated | agent-drafted | human-authored | unknown
  content_created_at: <ISO-8601 UTC; set once at page creation; never updated>
  content_hash: <first 32 hex chars of SHA-256 of body text after frontmatter>
  translation_origin: translator-batch | translator-sync | translator-page | translator-retranslate | agent-translated | human-translated | unknown
  source_file: <relative path of English source>   # locale files only
  source_sha: <first 24 hex chars of SHA-256 of English source>  # locale files only
  last_mechanism: translator | content-fixer | fixer | skill | agent-edit | human-edit | unknown
  auto_updatable: true | false
  reviewed: true | false  # deprecated — no enforcement gate; use auto_updatable: false to protect files
```

### Lifecycle rules

| Event | Fields updated |
|-------|----------------|
| Translator produces a new or updated locale file | `translation_origin`, `source_file`, `source_sha`, `last_mechanism: translator`, `auto_updatable: true`, `reviewed: false` |
| Evidence writer writes evidence block | `evidence:` block updated. **`last_mechanism` is NOT updated** — evidence attachment is metadata-only. |
| Grade writer writes canonical grade block | `grade`, `graded_content_hash`, and `grade_reasons` written. `graded_at` is NOT written (operational state; lives in grade manifest only). **`last_mechanism` is NOT updated** — grade writes are metadata-only. |
| Grade writer re-runs; all grade fields identical to current frontmatter | No write. `write_grade()` idempotency guard fires (`_should_write_canonical_grade()` returns False). Working tree stays clean — no dirty files created. |
| Remediation fixer modifies content body | `last_mechanism: content-fixer`, `content_hash` updated |
| Remediation fixer modifies frontmatter only (type/author/layout/categories) | No provenance fields updated — these are structural metadata fixes |
| Skill generates a new English page | `content_origin: skill-generated`, `content_created_at: <now>`, `content_hash: <body hash>`, `last_mechanism: skill`, `auto_updatable: true`, `reviewed: false` |
| Human edits content | `last_mechanism: human-edit`, `content_hash` updated, `auto_updatable: false`, `reviewed: true` |
| Agent edits content directly | `last_mechanism: agent-edit`, `content_hash` updated, `reviewed: false` |
| page-update skill modifies content | `last_mechanism: page-update`. `content_hash` auto-normalized by pre-commit hook. |
| page-enhance skill modifies content | `last_mechanism: page-enhance`. `content_hash` auto-normalized by pre-commit hook. |
| heal-page skill modifies content | `last_mechanism: heal-page`. `content_hash` auto-normalized by pre-commit hook. |
| manual-edit skill modifies content | `last_mechanism: manual-edit-skill`, `auto_updatable: false`. `content_hash` auto-normalized by pre-commit hook. |
| family-sync skill updates family page | `last_mechanism: family-sync`, `content_origin: family-sync`. |

**Skill provenance contract :** Every creation-path skill MUST write a `provenance:` block containing `content_origin: skill-generated` and `last_mechanism: skill` in the **same `Write` tool call** that creates the page frontmatter. This is the only mechanism that achieves `verified_at_creation` state (see provenance state taxonomy below). Post-hoc assignment via `content_origin_recover.py` yields only `pipeline_signal_only` — not equivalent. Do NOT remove or omit the `provenance:` block from a skill's frontmatter template. Index-scaffold skills (`new-docs-index`, `new-kb-index`, `new-reference-index`) are exempt from `skill-generated` — they use `content_origin: unknown`, `auto_updatable: false`, `provenance_recovery_note: structural-page` (structural-deferred classification). The `content_created_at` field is intentionally omitted from skill templates; it is populated by `provenance_backfill.py` in the post-creation pipeline step.

**Critical:** Evidence attachment and grade writes are metadata-only operations. They MUST NOT update `last_mechanism`, `auto_updatable`, or `translation_origin`. Only content-changing operations (skill, agent-edit, human-edit, manual-edit-skill, page-update, page-enhance, heal-page, family-sync, translator, content-fixer) update `last_mechanism`. The `graded_at` timestamp is the authoritative record of when grading occurred. This timestamp belongs in the external grade manifest (GRADE_CONTRACT.md §4) — NOT in `.md` frontmatter. A `.md` file whose only diff from HEAD is a changed `graded_at:` line is a non-meaningful change and MUST be reverted, not committed (see graded_at-only diff rule below).

**content_hash normalization:** The pre-commit hook (`scripts/pre-commit-audit.sh` Step 5) automatically computes and writes the correct `content_hash` for all staged English content files. Skills do NOT need to compute or pass `content_hash` — they only need to call `update_mechanism(path, "<mechanism_name>")` after modifying body content. The hook also emits a non-blocking warning (Step 6) when body content changed but `last_mechanism` was not updated.

### Overwrite/skip decision rules

The translator sync command uses `auto_updatable` to decide whether to overwrite an existing locale file:

```
locale file does not exist → translate (new file)
locale file exists AND auto_updatable == true → translate (overwrite)
locale file exists AND auto_updatable == false → skip, log reason
```

**The git commit author email is NOT a reliable provenance indicator and MUST NOT be used for overwrite decisions.** The `_is_bot_authored()` function was removed in the provenance integration commit. Do not recreate it.

### Provenance state taxonomy (authoritative)

The `content_origin` field value alone does not indicate how that value was established. The following taxonomy captures the evidence level behind each classification. **Use this taxonomy when deciding what origin data may be used for.**

| State | How assigned | May be used for | May NOT be used for |
|-------|-------------|-----------------|---------------------|
| `verified_at_creation` | `content_origin` written by the originating skill at page-creation time (concurrent write — strongest signal) | origin-proof reporting; compliance claims | — |
| `pipeline_signal_only` | `model_sha` present; Rule A or Rule B fired; no concurrent creation write | quality triage; risk sampling; overwrite eligibility | origin-proof reporting; compliance claims |
| `heuristic_bulk_assigned` | Bulk CSV decision (`apply_origin_decisions.py`); no per-file human examination | risk pooling; candidate lists for review | verified origin totals; compliance; origin-proof reporting |
| `explicit_non_skill` | `human-authored` or `manual-remediation` set by `register-human-content` or `manual-edit` skill with human operator sign-off | human-authored reporting | — |
| `structural_deferred` | `auto_updatable: false` + `provenance_recovery_note: structural-page`; `content_origin: unknown` preserved | structural page identification | any origin claim |
| `unverifiable_legacy` | No origin evidence; no skill-run log; pre-provenance-system file | deferred bucket | any origin claim |

**`model_sha` is a pipeline-contact signal, not a content-origin proof.** Its presence means evidence-repair skill contacted the knowledge model for the file. It does not prove the content body was generated by a skill or that the file was not subsequently edited.

**`last_mechanism: grade-writer` is unreliable as an origin signal.** Per lifecycle rules above, grade writes must not update `last_mechanism`. Files carrying this value had their `last_mechanism` overwritten by a metadata-only operation; the original mechanism is lost and must not be used for origin inference.

### Interpreting unknown provenance

`translation_origin: unknown` and `content_origin: unknown` are set by the backfill migration on pre-existing files. This means **origin is unverified**, not that the file is safe to overwrite. Use `auto_updatable` to make overwrite decisions — it is set to `true` by the backfill for all existing files, which is the correct conservative default.

### Protecting a file from automated overwrite

Set `auto_updatable: false` in the file's provenance block. The translator sync will log `[SKIP] ... -- auto_updatable=false, requires review` and skip the file.

### `reviewed` field status

`reviewed: true | false` has been **removed**. It is no longer written by any code path. Use `auto_updatable: false` to protect a file from automated overwrite (which is the operative signal). Existing files may still have `reviewed:` in their frontmatter; it is inert and will be stripped by the next provenance rewrite.

### Staleness detection

`source_sha` holds the first 24 hex characters of SHA-256 of the English source content at the time of translation. If `source_sha` does not match the current English source, the locale file is stale and eligible for re-translation (if `auto_updatable: true`).

### Backfill and fresh-clone durability

`scripts/pipeline/commands/migration/provenance_backfill.py` writes provenance to all existing files that lack it. It is idempotent and safe to re-run. Files that already have a provenance block are skipped.

**Which files have committed provenance (durable across clones):** All locale files translated or re-translated since the provenance integration commit (provenance integration). These carry `translation_origin: translator-*` written by the translator and are in git.

**Which files require backfill after a fresh clone:** Locale files that existed before `cdaa1daac` and have not been re-translated since. On a fresh clone these files have no `provenance:` block. Run:

```bash
python scripts/pipeline/commands/migration/provenance_backfill.py
```

The backfill sets `translation_origin: unknown`, `auto_updatable: true`, and derives `source_file` / `source_sha` from the path mapping. This is the correct conservative default. See RUNBOOK §1 for the canonical post-clone setup sequence.

### content_created_at governance (TC-7E, 2026-04-05)

`content_created_at` records when the English page was **first committed to the repository**. It is NOT the date content was authored, drafted, or published.

**Field semantics:**
- Format: ISO-8601 UTC (`YYYY-MM-DDTHHMMSSZ`), e.g. `2025-03-15T00:00:00Z`
- Source priority: (1) frontmatter `date:` field (blog/KB files); (2) `git log --diff-filter=A` first-commit date
- Intentionally absent from skill frontmatter templates — the agent cannot know the commit timestamp at Write time; `provenance_backfill.py` populates this field in the post-creation pipeline

**Write-once rule (enforced by code):**
Once `content_created_at` is set in a file, `write_provenance()` MUST NOT overwrite it. The TC-7B write-once guard in `scripts/pipeline/lib/provenance.py` enforces this: if an existing `content_created_at` value is found in the file, it is merged into the outgoing dict before write, even if the caller omitted the field. Any caller that attempts to change an existing value receives a `WARN: preserving existing content_created_at` log line.

**Authorized write paths:**
- `scripts/pipeline/commands/content/content_created_at_backfill.py` — primary corpus backfill; uses `date:` field (Source 1) or bulk git log (Source 2); dry-run by default; `--apply` required
- `scripts/pipeline/commands/migration/provenance_backfill.py` — writes `content_created_at` only on first provenance block creation (new-file path); never overwrites an existing value
- Post-creation pipeline: for any future creation-path that can supply a verified commit timestamp

**Do NOT:**
- Set `content_created_at` in skill frontmatter templates — use `content_created_at_backfill.py` after creation
- Fabricate a date for any file without a git history source
- Call `write_provenance()` with a dict that overwrites an existing `content_created_at` value

### content_origin recovery (two-step provisioning workflow)

After `provenance_backfill.py` runs, newly provisioned English files carry `content_origin: unknown`. `scripts/pipeline/commands/content/content_origin_recover.py` upgrades eligible files to `content_origin: skill-generated` using two confidence rules:

- **Rule A** (strong): grade ∈ {A, B} AND `evidence.claims` non-empty → `skill-generated`
  Claims are matched against the knowledge model; their presence is a strong signal that the page was skill-generated.
- **Rule B** (weaker): grade ∈ {A, B} AND `evidence.apis` non-empty (claims may be empty) → `skill-generated`
  Covers prose-only pages (no code blocks) where evidence-repair Stage 1 cannot populate claims but API tokens were verified. Applicable to the majority of API reference prose pages.

Rule A is tested first. Rule B fires only when Rule A does not qualify.

**Locale files are automatically skipped.** Files with `translation_origin` in their provenance block are never processed — they lack `content_origin` entirely and must not receive automated origin assignments.

**Two-step provisioning flow:**

```
Step 1 — provenance_backfill.py     (writes provenance block; sets content_origin: unknown)
Step 2 — content_origin_recover.py  (upgrades content_origin for Rule A or Rule B eligible files)
```

**Usage:**

```bash
# Dry-run first — review all proposed changes before writing
python scripts/pipeline/commands/content/content_origin_recover.py --dry-run

# Human sampling gate: inspect 30 files across families; confirm rules are correct
# Save review record to reports/tc4-review-sample.txt (gitignored)

# Apply after sampling passes
python scripts/pipeline/commands/content/content_origin_recover.py --apply
```

**Idempotency:** Both scripts are safe to re-run. `content_origin_recover` skips files that already have a non-`unknown` `content_origin`. Running the two-step sequence multiple times produces no additional changes after the first full run.

**Sampling gate requirement:** Before running `--apply` on a new corpus batch, sample at least 30 files evenly across product families and verify that grade + claims/apis justify `skill-generated`. Document the review in `reports/` (local-only — never commit).

**Files not upgraded by Rule A or Rule B:** Pages graded C/D/F, human-authored docs, and files with neither non-empty claims nor non-empty apis remain at `content_origin: unknown` — this is correct. Do not manually patch these to `skill-generated` without confirming authorship.

**Evidence level of Rule A/B results:** Files upgraded by Rule A or Rule B are classified as `pipeline_signal_only` per the provenance state taxonomy in this section. Rule A and Rule B are inference rules, not origin proofs. A grade A/B + non-empty evidence block is a strong indicator of skill generation but does not verify that the content body was produced by a specific skill at a specific time. Do not present Rule A/B results as `verified_at_creation` provenance.

---
