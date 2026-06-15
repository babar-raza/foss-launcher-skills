# Post-Sprint Autonomy Loop (PSAL)

Machine-controlled post-sprint review cycle. Replaces the manual
Prompt 1 → Prompt 2 → Prompt 3 → inspect → decide loop.

## Layout

```
scripts/maintenance/supervisor/
├── loop_controller.py          # Core engine: classify, validate, decide
├── skill-sprint-loop.md        # S-103 skill definition (staging; copy to .claude/commands/)
├── README.md                   # This file
├── prompts/
│   ├── prompt1-post-sprint-audit.md
│   ├── prompt2-plan-hardening.md
│   ├── prompt3-controlled-execution.md
│   ├── prompt-loop-controller.md
│   ├── prompt-output-contracts.md
│   ├── project-adapter-template.md
│   ├── project-adapter-aspose.yaml
│   └── prompt-registry.yaml
├── schemas/
│   ├── stage1-issue-model-schema.yaml
│   ├── stage2-taskcard-contract.yaml
│   ├── stage3-quality-scoring-rubric.yaml
│   ├── taskcard-state-machine.yaml
│   ├── summary-parser-contract.yaml
│   ├── loop-decision-state-machine.yaml
│   ├── evidence-bundle-contract.yaml
│   ├── project-adapter-contract.yaml
│   └── governance-contract.yaml
└── tests/
    └── test_loop_controller.py  # 34 tests (24 negative + 2 positive + 5 helper + 3 integration)
```

## Usage

```bash
# Dry run (no files written)
.venv/Scripts/python scripts/maintenance/supervisor/loop_controller.py \
  --evidence-dir path/to/evidence --dry-run

# Execute (writes loop-decision YAML to reports/supervisor/)
.venv/Scripts/python scripts/maintenance/supervisor/loop_controller.py \
  --evidence-dir path/to/evidence --execute
```

## Decision Flow

1. Parse `stage3-final-sprint-summary.yaml` from evidence directory
2. Classify into one of 9 states (STRUCTURED_ALL_GREEN, PROSE_ONLY, MISSING, etc.)
3. Validate evidence bundle completeness
4. Check quality scores (all dimensions must be >= 4/5)
5. Emit decision: ACCEPT / RETRY / BLOCK / ESCALATE

Only `STRUCTURED_ALL_GREEN` with complete evidence and passing scores produces `ACCEPT`.

## Registration

- Pipeline registry: `scripts/pipeline/config/registry.yaml` (entry added)
- Skill registry: pending human copy of `skill-sprint-loop.md` to `.claude/commands/sprint-loop.md`
- Skill ID: S-103 (pending registration in `docs/registries/skills.md`)
