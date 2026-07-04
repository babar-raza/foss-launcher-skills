# S-113: Validate Capability Parity — Semantic Parity Validation

**Arguments**: $ARGUMENTS
```
[--check]   Exit 1 if any parity gaps found (default behavior is to emit report and exit 0)
```

**Examples:**
```
/validate-capability-parity
/validate-capability-parity --check
```

---

## Purpose

Validate that every capability in `skills/registry.yaml` has semantically consistent adapters
across all agent surfaces. Unlike file-level sync checking, this validation compares the
actual body content (after frontmatter stripping) to detect content drift.

Emits `.governance/generated/parity-report.yaml` with per-capability parity status.

## Pre-conditions

- `skills/registry.yaml` must exist
- All canonical skill files must exist at `skills/{name}.md`
- `pyyaml` must be installed

## Steps

1. **Load registry** — Read all skills from `skills/registry.yaml`.

2. **For each capability**:
   - Read canonical body from `skills/{name}.md` (frontmatter stripped)
   - If not internal: compare to `.claude/commands/{name}.md`
   - Compare to `.agents/skills/{name}/SKILL.md` (frontmatter stripped)
   - Compare to `.kilocode/skills/{name}/SKILL.md` (frontmatter stripped)
   - Hash each body and record: `FULL_PARITY`, `SEMANTIC_DRIFT`, or adapter missing

3. **Emit parity report** — Write `.governance/generated/parity-report.yaml` with:
   - Per-capability status
   - Summary counts
   - `final_verdict: FULL_PARITY` or `GAPS_DETECTED`

4. **Print summary** — Show counts by status category.

5. **Exit code** — Exit 0 if `FULL_PARITY`; exit 1 if `--check` and gaps found.

## Implementation

```bash
python tools/capability_sync/validate_semantic_parity.py --sync
python tools/capability_sync/validate_semantic_parity.py --check
```

## Output

- `.governance/generated/parity-report.yaml`
- Console summary

## Post-conditions

- Parity report reflects current state of all adapters
- No files are modified beyond the report

## Recovery

If SEMANTIC_DRIFT is detected, repair by running `/sync-capabilities` which regenerates
all adapters from the canonical source.
