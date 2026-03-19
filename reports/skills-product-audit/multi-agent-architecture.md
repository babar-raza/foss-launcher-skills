# Multi-Agent Architecture — foss-launcher-skills

> Date: 2026-03-19
> Agents: Claude Code, Codex CLI, Kilo Code

---

## Current State

`tools/distribute.py` reads `skills/*.md`, splits YAML frontmatter from markdown body via regex, and writes:

| Agent | Output Path | Format |
|-------|-------------|--------|
| Claude Code | `.claude/commands/{name}.md` | Body only (frontmatter stripped) |
| Codex CLI | `.agents/skills/{name}/SKILL.md` | Full file with frontmatter |
| Kilo Code | `.kilocode/skills/{name}/SKILL.md` | Full file with frontmatter |

### Current Limitations

1. **No capability awareness**: All skills distributed to all agents regardless of whether the agent can execute them
2. **No dependency validation**: Skill chains (S-34 → S-35 → S-31 → ...) are documented in prose but not machine-validated
3. **No install manifest**: Agents have no structured index of available skills, their capabilities, or safety rules
4. **No argument schemas**: Skill arguments are freeform strings, not typed or validated
5. **No behavioral contracts**: Same markdown body goes to all agents; no agent-specific execution hints
6. **No output contracts**: No machine-readable declaration of what files a skill produces
7. **Identical treatment of Codex and Kilo Code**: Both get full frontmatter, no differentiation

---

## Target: Canonical Skill Manifest Schema

### Extended Frontmatter

Each skill's YAML frontmatter expands from:

```yaml
# CURRENT (minimal)
---
name: evidence-materialize
id: S-40
description: >
  Materialize knowledge into canonical PEF.
args: "{family} {platform}"
---
```

To:

```yaml
# TARGET (full manifest)
---
name: evidence-materialize
id: S-40
version: "1.0"
description: >
  Materialize knowledge into canonical PEF.
args: "{family} {platform}"

execution:
  mode: script                    # script | instruction | hybrid
  entry: scripts/materialize.py   # executable path (when mode=script)
  timeout_seconds: 300
  idempotent: true                # safe to re-run

requires:                         # agent capabilities needed
  - file_read
  - file_write
  - python_exec

safety:
  autonomy_tier: AUTO             # AUTO | WARN | BLOCK | HUMAN-ONLY
  write_paths:
    - "evidence/{family}/{platform}/"
  forbidden_paths: inherit        # inherit from config.yaml
  max_output_files: 5
  requires_human_review: false

depends_on: [S-35, S-31]         # skills that must run before this one
required_by: [S-41, S-42, S-43]  # skills that depend on this one

produces:                         # output contract
  - path: "evidence/{family}/{platform}/pef.json"
    schema: pef                   # references configs/schemas/pef.schema.json
  - path: "evidence/{family}/{platform}/changelog.json"
    schema: null

consumes:                         # input contract
  - path: "knowledge/{family}/{platform}/merged/claims.json"
    required: true
  - path: "knowledge/{family}/{platform}/merged/api_surface.json"
    required: true
  - path: "knowledge/{family}/{platform}/merged/model.yaml"
    required: true

agent_hints:
  claude:
    strip_frontmatter: true
    system_context: "You are a scout agent with write access to evidence/."
  codex:
    keep_frontmatter: true
  kilocode:
    keep_frontmatter: true
    category: evidence
---
```

### Schema Validation

A new `configs/schemas/skill_manifest.schema.json` validates all frontmatter fields. Required fields: `name`, `id`, `description`, `args`. All other fields are optional with sensible defaults.

---

## Canonical Skill Source Format

The source of truth is `skills/{name}.md`. Every agent-specific output is derived from this single file. The canonical format is:

```
---
{YAML frontmatter — full manifest}
---

# S-{id}: {Title}

{Markdown body — agent-readable instructions}
```

The body IS the skill instruction. Frontmatter IS the metadata. They are never separated in the canonical source.

---

## Distribution / Transpilation Model

### Phase 1: Enhanced distribute.py

```
skills/*.md → distribute.py → agent-specific outputs
```

For each skill, distribute.py:

1. **Parses** full YAML frontmatter + markdown body
2. **Validates** frontmatter against skill_manifest.schema.json
3. **Checks** capability requirements against agent capability matrix
4. **Renders** agent-specific output:

| Agent | Skill File | Manifest Entry | Capability Filter |
|-------|-----------|----------------|-------------------|
| Claude Code | `.claude/commands/{name}.md` — body only | Entry in `.claude/skills.json` | Warn if requires unsupported capability |
| Codex CLI | `.agents/skills/{name}/SKILL.md` — full | Entry in `.agents/manifest.json` | Warn if requires unsupported capability |
| Kilo Code | `.kilocode/skills/{name}/SKILL.md` — full | Entry in `.kilocode/manifest.json` | Skip or degrade if requires unsupported capability |

5. **Validates** skill chain DAG (depends_on/required_by form valid DAG, no orphans)
6. **Generates** per-agent install manifest

### Per-Agent Install Manifests

Each agent gets a structured JSON index:

```json
// .claude/skills.json
{
  "schema_version": 1,
  "generated_at": "2026-03-19T...",
  "skill_count": 36,
  "skills": {
    "S-40": {
      "name": "evidence-materialize",
      "command": "evidence-materialize",
      "description": "Materialize knowledge into canonical PEF.",
      "args": "{family} {platform}",
      "autonomy_tier": "AUTO",
      "depends_on": ["S-35", "S-31"],
      "required_by": ["S-41", "S-42", "S-43"],
      "produces": ["evidence/{family}/{platform}/pef.json"],
      "requires": ["file_read", "file_write", "python_exec"]
    }
  },
  "chains": {
    "new_page": ["S-10", "S-18", "S-19", "S-22", "S-23", "S-24", "S-01"],
    "maintenance": ["S-12", "S-13", "S-14", "S-20", "S-23", "S-24", "S-01"],
    "enhancement": ["S-17", "S-21", "S-23", "S-01"],
    "healing": ["S-25", "S-26", "S-23", "S-25", "S-01"],
    "launch": ["S-34", "S-35", "S-31", "S-15", "S-37", "S-40", "S-41", "S-43"]
  }
}
```

---

## Agent Capability Matrix

| Capability | Claude Code | Codex CLI | Kilo Code | Used By |
|-----------|-------------|-----------|-----------|---------|
| `file_read` | yes | yes | yes | All skills |
| `file_write` | yes | yes | yes | All skills that produce output |
| `python_exec` | yes | yes | limited | S-34, S-35, S-31, S-15, S-37, S-39, S-40, S-41, S-42, S-43 |
| `git_operations` | yes | yes | no | Commit workflows |
| `json_validation` | yes | yes | yes | Schema validation steps |
| `subprocess` | yes | yes | limited | Pipeline script execution |
| `network_access` | restricted | restricted | no | S-39 (discover), S-15 (embed API tier) |

### Capability-Based Distribution Rules

1. If a skill `requires: [python_exec]` and the agent has `python_exec: limited`:
   - Emit skill with a warning comment at the top: `<!-- WARNING: This skill requires Python execution. Limited support on this agent. -->`
   - In the manifest, mark as `"capability_warning": "python_exec limited"`

2. If a skill `requires: [network_access]` and the agent has `network_access: no`:
   - Skip distribution entirely for that agent
   - In the manifest, mark as `"skipped": true, "reason": "requires network_access"`

3. If a skill has `safety.autonomy_tier: BLOCK`:
   - Emit skill with human approval instruction injected
   - In the manifest, mark as `"requires_approval": true`

---

## Argument Schema

For agents that support typed arguments (future enhancement):

```yaml
# In skill frontmatter
args_schema:
  type: object
  required: [family, platform]
  properties:
    family:
      type: string
      description: "Product family (e.g., words, cells, email)"
      enum_ref: "configs/families.yaml#families"
    platform:
      type: string
      description: "Target platform (e.g., python, java, dotnet)"
      enum_ref: "configs/families.yaml#platforms"
    repo_path:
      type: string
      description: "Path to cloned FOSS repository"
      required: false
```

Initially, `args_schema` is optional. distribute.py ignores it if absent but validates it if present. Future agent integrations can use it for auto-completion, validation, and structured invocation.

---

## Validation Rules (Enforced by distribute.py)

### Per-Skill Validation
1. Every skill MUST have: `name`, `id`, `description`, `args`
2. `id` must be unique across all skills
3. `id` must match `S-{number}` pattern or be a lowercase slug
4. If `execution.mode: script`, then `execution.entry` must point to an existing file
5. `depends_on` references must resolve to existing skill IDs
6. `required_by` references must be bidirectional (if A depends_on B, B must have required_by A)
7. `safety.write_paths` must not overlap with `forbidden_paths` from config.yaml
8. `produces[].schema` must reference a valid schema in `configs/schemas/`

### Skill Chain Validation
1. The full dependency graph must be a DAG (no cycles)
2. Every skill referenced in AGENTS.md skill chains must exist
3. Skills in the `launch` chain must cover all required pipeline steps
4. No orphan skills (skills with no chain membership and no depends_on/required_by)

### Distribution Validation
1. Every canonical skill in `skills/` must produce exactly one output per agent
2. Output files must not conflict (no two skills writing to the same path)
3. Manifest JSON must validate against its own schema

---

## Packaging / Install Implications

### For Claude Code
- Skills distributed as `.claude/commands/*.md` (body only)
- Index at `.claude/skills.json` (NEW)
- Permissions in `.claude/settings.local.json` (existing)
- User installs by cloning repo or running install script

### For Codex CLI
- Skills distributed as `.agents/skills/{name}/SKILL.md`
- Index at `.agents/manifest.json` (NEW)
- User installs by cloning repo and pointing Codex at `.agents/`

### For Kilo Code
- Skills distributed as `.kilocode/skills/{name}/SKILL.md`
- Index at `.kilocode/manifest.json` (NEW)
- User installs by cloning repo and configuring Kilo Code skill path

### Cross-Agent Install Script
`install.sh` / `install.ps1` should:
1. Run `pip install -e .` (or `pip install foss-launcher-skills`)
2. Run `python tools/distribute.py` to generate agent-specific outputs
3. Create data directories at `$data_root`
4. Print instructions for configuring each agent
