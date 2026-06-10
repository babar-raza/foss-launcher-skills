# S-97: Triage Confirm — Layer 2 Body-Prose Staleness Scanner

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--files {glob}] [--output {path}]`

## Purpose

Scan content page body prose for references to API classes or knowledge claims that have
changed or been removed since the last knowledge update. Provides Layer 2 staleness detection
to complement the Layer 1 SHA-based check in `refresh_knowledge.py` / `knowledge_delta.json`.

Use S-97 when:
- Layer 1 reports SHA unchanged but you suspect content drift
- A knowledge update changed API signatures without changing the repo SHA
- Running a deep-triage pass on a product after a knowledge refresh

**Do not use to modify content** — this skill is read-only. Route stale pages to S-20
(page-update), S-26 (heal-page), or S-21 (page-enhance) based on severity.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/` exists and is current (`stale_since: null`)
2. Content pages exist under `$CONTENT_REPO_PATH/content/` for the target product
3. `knowledge/{family}/{platform}/merged/api_surface.json` and `claims.json` exist

## Steps

1. **Parse arguments**: Extract `family`, `platform`, optional `--files` glob, and `--output` path.

2. **Load knowledge artifacts**:
   - Read `knowledge/{family}/{platform}/merged/api_surface.json` — current API surface
   - Read `knowledge/{family}/{platform}/merged/claims.json` — current claims
   - Read `knowledge/{family}/{platform}/merged/knowledge_delta.json` if it exists — changed APIs from last refresh

3. **Determine target files**:
   - If `--files` provided: use that glob pattern
   - Otherwise: scan all `$CONTENT_REPO_PATH/content/**/{family}/{platform}/**/*.md`

4. **For each target file, run Layer 2 staleness scan**:

   a. **API class name scan**: Extract all API identifiers from body prose and code blocks.
      Compare against `api_surface.json`:
      - **STALE**: identifier present in body but absent from current `api_surface.json`
      - **CHANGED**: identifier present but method signatures have changed (from `knowledge_delta.json`)
      - **CURRENT**: identifier matches current API surface

   b. **Claim reference scan**: Extract `CLM-` IDs from `evidence.claims` frontmatter.
      Compare against `claims.json`:
      - **ORPHANED**: claim ID cited in evidence but absent from current `claims.json`
      - **CURRENT**: claim ID exists in `claims.json`

   c. **Prose accuracy scan**: For each high-confidence sentence containing an API class name,
      verify the sentence does not contradict `api_surface.json` (e.g. claims a method exists
      that has been removed).

5. **Classify each file**:
   | Classification | Criteria | Recommended skill |
   |---|---|---|
   | `CURRENT` | No stale identifiers, no orphaned claims | None needed |
   | `WARN:stale-refs` | 1-3 stale identifiers or orphaned claims | S-20 (page-update) |
   | `FAIL:stale-refs` | 4+ stale identifiers or orphaned claims | S-26 (heal-page) |
   | `FAIL:contradicts-api` | Prose contradicts current `api_surface.json` | S-26 (heal-page) |

6. **Write output report** (to `--output` path or `reports/triage-confirm/{family}-{platform}-{date}.json`):
   ```json
   {
     "family": "{family}",
     "platform": "{platform}",
     "scanned_at": "{ISO datetime}",
     "files_scanned": N,
     "summary": {
       "current": N,
       "warn_stale_refs": N,
       "fail_stale_refs": N,
       "fail_contradicts_api": N
     },
     "findings": [
       {
         "file": "{path}",
         "classification": "WARN:stale-refs",
         "stale_identifiers": ["ClassName.MethodName"],
         "orphaned_claims": ["CLM-xxx"],
         "recommended_skill": "S-20"
       }
     ]
   }
   ```

7. **Print summary**:
   ```
   TRIAGE CONFIRM — {family}/{platform}
   Files scanned: N
   Current:              N (no action needed)
   WARN (stale refs):    N (route to S-20)
   FAIL (stale refs):    N (route to S-26)
   FAIL (contradicts):   N (route to S-26)

   Report written to: {output-path}
   ```

## Post-conditions

- Staleness report written to output path
- No content files modified (read-only)
- Each non-CURRENT file has a `recommended_skill` entry

## Error handling

| Error | Action |
|-------|--------|
| Knowledge model stale | REFUSE: run S-12 + S-14 first |
| No content files found for product | WARN: "No content files found for {family}/{platform}" |
| `api_surface.json` missing | FAIL: run `/knowledge-bootstrap {family} {platform}` first |
