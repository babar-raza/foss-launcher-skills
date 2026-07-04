---
name: scaffold-capability
id: S-115
description: >
  Create a new governed capability with canonical contract, registry entry, Claude command
  adapter, and agent skill adapter. All adapters are generated from the canonical source.
args: "{name} {id} {description} [--category {category}] [--internal]"
---

# S-115: Scaffold Capability — Create New Governed Capability

**Arguments**: $ARGUMENTS
```
{name}          Required. Kebab-case capability name (e.g. my-new-capability)
{id}            Required. Unique skill ID (e.g. S-116). Check skills/registry.yaml for next available.
{description}   Required. One-sentence description of the capability purpose.
--category      Optional. One of: governance, knowledge, content, quality, translation, orchestration, utility
--internal      Optional flag. If set, skill is internal (no Claude command adapter generated).
```

**Examples:**
```
/scaffold-capability my-new-capability S-116 "Run X analysis and emit Y report" --category quality
/scaffold-capability my-internal-gate S-117 "Internal quality gate" --internal
```

---

## Purpose

Create a complete new governed capability following the canonical lifecycle:
1. Canonical contract (`skills/{name}.md`)
2. Registry entry (`skills/registry.yaml`)
3. Claude command adapter (`.claude/commands/{name}.md`) — unless `--internal`
4. Agent skill adapter (`.agents/skills/{name}/SKILL.md`)
5. KiloCode skill adapter (`.kilocode/skills/{name}/SKILL.md`)
6. Governance metadata (`.governance/capabilities/registry.yaml` entry)

**A new capability is incomplete until all required agent surfaces are synchronized.**

## Pre-conditions

- The chosen `{id}` must not already exist in `skills/registry.yaml`
- The chosen `{name}` must not already exist in `skills/`
- You must be operating under an active skill context (this skill or a parent)
- `pyyaml` must be installed

## Steps

1. **Validate uniqueness** — Check that `{id}` and `{name}` are not already registered.

2. **Create canonical skill contract** — Write `skills/{name}.md` with:
   ```yaml
   ---
   name: {name}
   id: {id}
   description: >
     {description}
   args: "[args...]"
   ---

   # {id}: {Title}

   ## Purpose
   ## Pre-conditions
   ## Steps
   ## Output
   ## Post-conditions
   ```

3. **Add registry entry** — Append to `skills/registry.yaml`:
   ```yaml
   - id: {id}
     name: {name}
     description: {description}
     internal: {true|false}
     script: null
   ```

4. **Run `/sync-capabilities`** — Automatically generate all adapter surfaces from the new canonical skill.

5. **Add governance metadata** — Add entry to `.governance/capabilities/registry.yaml` with
   category, operation_type, mutating, and idempotency fields.

6. **Verify** — Run `/capability-status` to confirm FULL_PARITY for the new capability.

7. **Write receipt** — Emit execution receipt to `reports/receipts/scaffold-{name}-{date}.json`.

## Output

- `skills/{name}.md` — canonical contract
- Updated `skills/registry.yaml` — registry entry added
- `.claude/commands/{name}.md` — Claude adapter (if not internal)
- `.agents/skills/{name}/SKILL.md` — Codex adapter
- `.kilocode/skills/{name}/SKILL.md` — KiloCode adapter
- Updated `.governance/capabilities/registry.yaml` — metadata entry

## Post-conditions

- `/capability-status` shows the new capability at FULL_PARITY
- The new capability is immediately discoverable by all supported agents
- CI validation passes for the new capability

## Idempotency

If called with a name that already has a canonical skill file, the skill stops and reports
"capability already exists". It does not overwrite existing artifacts.

## New Capability Resolution Order

Before creating a new capability:
1. Query `skills/registry.yaml` for exact match
2. Query for parameterized match (existing capability handles this with different args)
3. Consider composing existing capabilities
4. Consider extending an existing capability
5. Only if none apply: scaffold this new micro-capability
