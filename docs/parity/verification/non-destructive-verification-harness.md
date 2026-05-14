# Non-Destructive Verification Harness Design

Status: Phase 7 foundation artifact

## Purpose

Phase 8 must prove parity without writing to `aspose.org/content`. This harness defines the required verification layers and safety evidence.

## Verification Layers

1. Inventory completeness checks:
   - regenerate both inventories;
   - compare record counts and provider paths;
   - fail on missing registered standalone records.
2. Registry and discoverability checks:
   - run `python scripts/validate_skills.py`;
   - run `python scripts/sync_agents.py --check`;
   - run `python scripts/sync_commands.py --check`.
3. Contract consistency checks:
   - compare declared args, outputs, dry-run support, and write paths for representative skills.
4. Config coverage checks:
   - exercise content root resolution with env var, config fallback, missing root, and temp output root.
5. Docs-to-code consistency checks:
   - verify documented script paths exist or have approved compatibility mappings.
6. Helper dependency checks:
   - verify registry script bindings and required helper modules exist.
7. Dry-run execution tests:
   - run representative skills with `--dry-run` or no-op modes.
8. Redirected output tests:
   - run representative write-capable commands against a temporary output root.
9. Governance tests:
   - prove forbidden aspose.org content writes fail.
10. Safety check:
   - capture a before/after snapshot of `D:/onedrive/Documents/GitHub/aspose.org/content` metadata or use a file-list checksum where feasible.

## Fixture Strategy

Use these sources in order:

- `tests/fixtures/**` for unit-level skill and script tests.
- temporary directories under the OS temp root for output-root tests.
- temporary copies of sampled content files when content shape is required.
- no-op manifests for orchestrator skills.

## Representative Skill Set

Phase 8 should include at least:

- registry-only/internal: `path-guard`, `knowledge-bootstrap`;
- validation: `content-check`, `content-audit`, `content-eval`;
- generation/orchestration: `new-docs-page`, `batch-reference`, `launch-product` in dry-run/no-op mode;
- maintenance: `knowledge-update`, `refresh-product`;
- translation: `translate`, `translate-page`, `translate-batch`;
- standalone-only preservation: `ground-check`, `evidence-materialize`, `corpus-scan`.

## Required Evidence

Each verification run must record:

- command;
- working directory;
- input fixture or temp root;
- resolved content root;
- resolved output root;
- exit code;
- summary output;
- write-target list if available;
- safety proof for `aspose.org/content`.

## Done Criteria

- Every parity-proven capability has objective evidence.
- Every content-writing path is exercised only through dry-run, fixture, no-op, or redirected output.
- The verification evidence proves no command required writes to `aspose.org/content`.
