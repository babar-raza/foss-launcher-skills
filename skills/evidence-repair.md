# S-72: Evidence Repair — Repair Evidence Frontmatter for Validator-Blocked Pages

<!-- CONTRACT: evidence/runner.py (Stage 1 auto-attach via attach_evidence.py)
postcondition: Stage 1 runs attach_evidence.py --force and re-verifies
postcondition: Stage 2 (LLM reasoning) executes only when Stage 1 leaves claims or apis empty
postcondition: Safe-escape sets provenance.content_origin=manual-remediation and halts
postcondition: skill is evidence-frontmatter-only — page body content is NEVER modified
postcondition: validate_frontmatter.py + audit.py both exit 0 before reporting REPAIRED
verified: 2026-04-03
-->

**Arguments**: $ARGUMENTS
Expected format: `{relative-file-path} [additional-paths...]` — e.g.
`content/blog.aspose.org/3d/typescript/key-features/index.md`

Optional flags: `--dry-run` (no file writes), `--scope claims|apis|both` (default: `both`)

## Purpose

Repair the `evidence:` frontmatter block on a content page that is blocked by the
pre-commit validator (`validate_frontmatter.py` P-03 or `audit.py` evidence FAIL).

This skill is triggered when `git commit` is blocked with an error like:
```
blog post evidence.claims is empty — run: /evidence-repair {path}
blog post evidence.apis is empty — run: /evidence-repair {path}
```

**Critical scope boundary**: This skill ONLY modifies the `evidence:` and `provenance:`
blocks in the YAML frontmatter. It NEVER modifies page title, description, body content,
headings, code blocks, or any prose text.

## Pre-conditions (Preflight — halt immediately on any failure)

1. Parse file path(s) from `$ARGUMENTS`. If `--dry-run` is present, record it and make no file writes.
2. For each file:
   a. File must exist under an allowed `content/` path (S-01 path-guard ALLOW)
   b. File must be an English source file — refuse locale variants (index.ar.md, index.fr.md, etc.)
   c. Detect `{family}` and `{platform}` from the file path
   d. `knowledge/{family}/{platform}/merged/model.yaml` must exist and be readable
   e. `model.yaml` field `stale_since` must be null — if not null, HALT:
      ```
      REFUSED: Knowledge is stale for {family}/{platform}.
      Run S-12 (knowledge-diff) then S-14 (knowledge-update) before proceeding.
      ```
   f. `knowledge/{family}/{platform}/merged/claims.json` and `api_surface.json` must exist
   g. File must not have double-frontmatter (check with validate_frontmatter.py first; if double-frontmatter found, HALT with guidance to fix structural issue before evidence repair)

## Section-Specific Evidence Requirements

| Section | claims required? | apis required? | draft required? | Validator |
|---------|-----------------|----------------|-----------------|-----------|
| `blog.aspose.org` | YES (P-03) | YES (P-03) | YES (P-03) | validate_frontmatter.py |
| `docs.aspose.org` | YES | YES | NO | audit.py |
| `kb.aspose.org` | YES | YES | NO | audit.py |
| `products.aspose.org` | NO | NO | NO | — (evidence optional) |
| `reference.aspose.org` | YES | YES | NO | audit.py |

## Steps

### Stage 1 — Auto-Attach (script-driven)

3. **Run attach_evidence.py with --force** to rebuild the evidence block from code blocks and tables:
   ```bash
   python scripts/pipeline/attach_evidence.py --files {path} --force
   ```
   (Skip if `--dry-run`; report what would happen instead.)

4. **Verify Stage 1 result**:
   ```bash
   python scripts/pipeline/validate_frontmatter.py {path}
   python scripts/pipeline/audit.py --files {path}
   ```
   - If both exit 0 → report **REPAIRED (auto)** and stop for this file.
   - If either still fails → proceed to Stage 2.

### Stage 2 — Reasoning-Based Population (LLM-executed, knowledge-grounded)

5. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/claims.json` — full claim registry
   - Read `knowledge/{family}/{platform}/merged/api_surface.json` — full API surface
   - Read `knowledge/{family}/{platform}/merged/api_surface.md` — human-readable reference

6. **Read current page content** — full text including all sections and code blocks.

7. **Identify remaining gaps** — run validate_frontmatter.py --json to get exact findings.
   For each finding, determine whether it needs: claims repair, apis repair, or both.

8. **Populate evidence.claims** (if claims is empty or gap was claims-related):

   Scan the page content for factual claims it makes about the product. For each claim, find
   the matching `claim_id` in `claims.json`. Rules:
   - Only add claim IDs that exist in `claims.json` — NEVER invent IDs
   - Match by reading the claim's `description` or `text` field and comparing to page prose
   - Include 2–8 most relevant claim IDs; prefer specificity over breadth
   - If no claims can be confidently matched → skip claims (proceed to safe-escape after Stage 2)
   - NEVER add a claim ID you cannot trace to a specific passage in the page content

9. **Populate evidence.apis** (if apis is empty or gap was apis-related):

   Scan the page content for API class names, method names, enum values, or property names
   that the page discusses — in code blocks AND in prose. For each API mention, find the
   matching entry in `api_surface.json`. Rules:
   - Only add API refs that exist in `api_surface.json` — NEVER invent refs
   - Match class names, qualified names (ClassName.method), or enum values exactly
   - Include API refs found in code blocks FIRST; then prose mentions if clearly identifiable
   - If no API refs can be confidently matched → skip apis (proceed to safe-escape after Stage 2)
   - NEVER add an API ref you cannot trace to a specific passage in the page content

10. **Write evidence block** with the populated values:
    - MAY modify: `evidence.claims`, `evidence.apis`, `evidence.model_sha`, `evidence.model_version`
    - Update `evidence.model_sha` from `knowledge/{family}/{platform}/merged/model.yaml.repo_sha`
    - Update `evidence.model_version` from `model.yaml.version`
    - Set `provenance.last_mechanism: evidence-attach`
    - MUST NOT touch: `provenance.auto_updatable`, `provenance.translation_origin`
    - MUST NOT touch: page title, description, body content, headings, code blocks, any prose

    (Skip writes if `--dry-run`; report what would be written.)

11. **Verify Stage 2 result**:
    ```bash
    python scripts/pipeline/validate_frontmatter.py {path}
    python scripts/pipeline/audit.py --files {path}
    ```
    - If both exit 0 → report **REPAIRED (reasoning)** and stop for this file.
    - If either still fails → proceed to Safe-Escape.

### Safe-Escape — When Confidence Is Insufficient

Activate safe-escape when Stage 2 cannot confidently populate claims or apis (e.g., the
page is introductory prose with no traceable API surface or no claim language matching
any entry in `claims.json`).

12. **Set manual-remediation escape**:
    - Set `provenance.content_origin: manual-remediation` in frontmatter
    - Do NOT modify `evidence.claims` or `evidence.apis` (leave them empty — do not guess)
    - Set `provenance.last_mechanism: evidence-attach`

    (Skip write if `--dry-run`.)

13. **Verify escape works**:
    ```bash
    python scripts/pipeline/validate_frontmatter.py {path}
    ```
    P-03 claims/apis check is bypassed for `manual-remediation` files. Verify exit 0.

14. **Write escalation entry**:
    Append to `reports/evidence-repair/needs-human-{YYYYMMDD}.md`:
    ```markdown
    ## {path}
    Date: {date}
    Reason: Evidence could not be auto-populated — page has no confident claim or API matches.
    Required action: Human must read knowledge/{family}/{platform}/merged/claims.json and
    api_surface.json and manually populate evidence.claims and evidence.apis, then set
    provenance.content_origin back to skill-generated or human-authored.
    ```

15. Report **ESCAPED** for this file.

## Report (one entry per file)

```
EVIDENCE REPAIR — {file-path}
  Section: {blog|docs|kb|products|reference}
  Product: {family}/{platform}
  Knowledge SHA: {model_sha}

  Stage 1 (auto-attach): {RESOLVED | PARTIAL | FAILED}
  Stage 2 (reasoning):   {RESOLVED | PARTIAL | SKIPPED | N/A}
  Safe-escape:           {APPLIED | NOT NEEDED}

  Result: REPAIRED (auto) | REPAIRED (reasoning) | ESCAPED | REFUSED

  Changes:
    evidence.claims: {[] → [CLM-xxx, ...] | unchanged}
    evidence.apis:   {[] → [ClassName.method, ...] | unchanged}
    provenance.content_origin: {unchanged | manual-remediation}
    provenance.last_mechanism: {unchanged | evidence-attach}

  Validation:
    validate_frontmatter.py: PASS | FAIL
    audit.py:                PASS | FAIL | SKIPPED
```

Audit report written to `reports/evidence-repair/{family}-{platform}-{YYYYMMDD-HHMMSS}.json`.

## Post-conditions

- Files with result REPAIRED (auto|reasoning): both validators pass; evidence is populated with verified values only
- Files with result ESCAPED: validate_frontmatter.py passes (P-03 bypassed); marked for human follow-up
- Files with result REFUSED: no changes made; error report explains why
- Page body content is identical to input (no prose changes)
- `evidence.model_sha` matches current `knowledge/{family}/{platform}/merged/model.yaml.repo_sha`
- `provenance.last_mechanism` is `evidence-attach` for all modified files
- Escalation entries written for all ESCAPED files

## Error Handling / Refusal Conditions

The skill MUST refuse and immediately halt (without modifying any file) when:

| Condition | Refusal message |
|-----------|----------------|
| Knowledge model missing | `REFUSED: No knowledge model found at knowledge/{family}/{platform}/merged/model.yaml` |
| Knowledge model stale | `REFUSED: Knowledge stale for {family}/{platform} — run S-12 + S-14 first` |
| File not under content/ | `REFUSED: {path} is not under an allowed content/ path (path-guard DENY)` |
| Locale variant file | `REFUSED: {path} is a locale translation file — run on the English source only` |
| Double frontmatter | `REFUSED: {path} has double frontmatter — fix structural issue first before evidence repair` |
| --scope requires content edit | `REFUSED: requested edit scope would require body content modification — use heal-page (S-26) instead` |
| Post-edit audit still fails after retry | File reverted; reported as ESCAPED; escalation entry written |

## Never Do

- Never modify page title, description, summary, body text, headings, or code blocks
- Never invent or guess claim IDs — all claim IDs must exist in `claims.json`
- Never invent or guess API refs — all API refs must exist in `api_surface.json`
- Never apply this skill to locale translation files — English source only
- Never skip the post-edit validation step (Steps 11 / 13)
- Never apply more than one Stage 2 reasoning pass per file
- Never call itself recursively or enter an infinite retry loop
