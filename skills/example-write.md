# S-126: Example Write — Verified Examples for a Capability Ledger

<!-- CONTRACT: agent-executed
     purpose: produce VERIFIED code examples for the units of a capability ledger. Candidates are
              chosen mechanically from harvested snippets and upstream docs fences and verified by
              the Example Verifier against the product artifact. Nothing is authored by an LLM.
     preconditions: a capability ledger exists (capability_ledger.py build, normally built by
                    refresh_run prepare_run); knowledge for the product is current
                    (merged/snippets present); the product artifact is resolvable: the PUBLISHED
                    artifact via registry coordinates, else a pinned-SHA build in a temp copy
     postcondition: reports/example_verification/{family}/{platform}/{run}/ holds one result JSON
                    per candidate (artifact sha, source sha, toolchain) plus handoff.md; the ledger
                    carries evidence for each unit that has a PASS example; BLOCKED candidates are
                    listed with reasons; no unverified code is handed to a content skill
     forbidden: authoring or editing example code; writing under content/ or knowledge/; building
                inside the clone cache; editing the Example Verifier itself
     idempotent: yes — same ledger + same artifact sha + same toolchain give the same result files
                 and hand-off table (results are keyed by code hash, so a rerun reuses them)
     verified: 2026-10-07
     id: S-126
     depends_on: [S-84]
-->

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--unit CU-ID | --all] [--ledger PATH]`

| Parameter | Required | Meaning |
|-----------|----------|---------|
| `{family} {platform}` | Yes | The product whose ledger units need examples. |
| `--unit CU-ID` / `--all` | No | One capability unit, or every unit that has a `create` or `update` disposition on docs, kb or blog (default `--all`). |
| `--ledger PATH` | No | The capability ledger to work from. Default: the `capability_ledger.path` recorded in the newest run manifest under `reports/refresh_runs/{family}/{platform}/`. |

## Purpose

Produce verified code examples for the units of a capability ledger, taken from code people already wrote and tested, and hand content skills a table of examples they may cite.

A capability unit that needs a code example on docs, KB or the blog must get one that has actually
been compiled and, where meaningful, run against the real product artifact. This skill finds that code
in places a person already wrote and tested it (the product's own tests, README and docs), and proves it
with the Example Verifier.

**The hard rule: unverified code never reaches content.** A unit with no verified example gets a
prose-only description, or a `none` disposition with a rationale. It never gets invented or
"probably works" code (AGENTS.md §5, §11).

## Pre-conditions

1. The ledger parses and validates:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/capability_ledger.py \
     validate --ledger "$LEDGER" --stage plan
   ```
2. Knowledge is bootstrapped (`/knowledge-bootstrap` gate): `knowledge/{family}/{platform}/merged/snippets/snippets_index.json` exists. Each row records `classes_used`, `methods_used`, `source_file` and `code_sha256`. If it is missing, run `/knowledge-update` first.
3. The product artifact is resolvable (Step 2). If it is not, stop with `BLOCKED_ARTIFACT` (see Error handling).
4. Run the skill context gate:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-126 --scope "reports/example_verification/*,reports/refresh_runs/*"
   ```

## Steps

### 1. Select the units

Read the ledger and list units to serve: those with a `create` or `update` disposition on `docs`, `kb` or `blog` (or the single `--unit`). Skip units whose dispositions are all `none` or `mention`-only on those surfaces.

### 2. Resolve the product artifact (never the clone cache)

In this order:

1. **Published artifact.** Take the coordinates from `data/package_registry.json` (`candidate` and `verification` for `{family}/{platform}`), fetch the released artifact into a temp directory, and record its sha256. Use it only if the unit's availability is `released`.
2. **Pinned-SHA build.** For an unreleased unit, build the pinned upstream SHA in a temp copy through the runner's `product_build` option (`git clone --no-checkout --no-hardlinks`, detached checkout, project build). The build never runs in, or writes under, `runs/.clone_cache`.
3. Record the artifact (path, sha256, origin, source SHA) and the toolchain discovery result (JDK and build-tool path, version and source) in `reports/example_verification/{family}/{platform}/{run}/artifact.json`.

Examples verified against a pinned-SHA build of an unreleased unit are valid for the availability-qualified wording only. The hand-off table marks them `availability: unreleased`.

### 3. Choose candidates mechanically

For each unit, build the list of candidates in this fixed priority order, matching on the unit's symbols (type simple names and members):

1. Fences from the product README and `docs/**` at the pinned SHA (harvested into the snippets index as `provenance` README or docs).
2. Harvested test snippets (`snippet_NNN.{ext}`), matched through `classes_used` / `methods_used`.
3. Upstream docs fences not yet harvested, read from the pinned clone read-only.

A candidate qualifies only if it references at least one symbol of the unit. Rank by number of unit symbols covered, then source priority above, then snippet id (lexicographic) so the result is deterministic. Keep at most three candidates per unit. Copy each candidate's text byte-for-byte into a scratch Markdown file with one fenced block; the only allowed edit is wrapping it in the fence. Do not rename, trim, merge or "fix" anything. If a candidate fails because of a defect in the code, that is a BLOCKED result, not an editing task.

### 4. Verify each candidate

Run each candidate through the Example Verifier with the product artifact, the default fixture prelude, and the toolchain discovery enabled:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python - <<'PY'
from pathlib import Path
from lib.example_verification.api import verify_markdown
from lib.example_verification.policy import Policy
text = Path("<scratch candidate .md>").read_text(encoding="utf-8")
report = verify_markdown(
    text, family="<family>", platform="<platform>",
    policy=Policy.for_platform("<platform>", max_tier=3, allow_acquire=True),
    runner_kwargs={"product_jar": "<artifact path>", "prelude": "default"},   # or product_build=ProductBuild(clone_path, sha)
)
Path("<run dir>/<candidate id>.result.json").write_text(
    __import__("json").dumps(report.to_legacy_s120(), indent=2, sort_keys=True), encoding="utf-8")
PY
```

`example_verification/cli.py verify` is the same engine and is fine for a platform that needs no artifact options. Record the proof tier of every block (`tier_histogram`), the artifact record, and the toolchain record from the result JSON. Also append each cacheable result to the durable ledger through `lib.example_verification_ledger.ExecutionProofLedger(family, platform).record_result(report, block, run_id=...)` (the ledger itself skips non-durable outcomes; add `reports/example_verification_ledger` to the skill-context scope if you use it).

### 5. Accept or reject

| Verifier outcome | Disposition of the candidate |
|---|---|
| `COMPILED+RAN CLEAN` (PASS at tier 3) | **ACCEPTED** |
| PASS at tier 2 with a runner-disclosed reason (compile-only) | **ACCEPTED_COMPILE_ONLY**: usable, but content must not state an output, and the hand-off row says so |
| `BLOCKED-WITH-REASON` (any reason, including `COMPILE-ERROR`, `FIXTURE-UNAVAILABLE`, `TOOLCHAIN-UNAVAILABLE`) | **BLOCKED**: listed with the reason, never handed over |
| `NOT-EXECUTABLE-LANG`, `NOT-VERIFIED`, anything else | **BLOCKED** |

At most one ACCEPTED example per unit is handed over by default (highest rank). Keep the others as alternates in the report.

### 6. Record in the ledger

Write the qualified symbols exercised by ACCEPTED examples to `verified_examples.json` as `{"symbols": [...]}` in the run directory. Then:

- Evidence: for each surface of the unit that already has a `create`/`update` disposition, re-run `set-disposition` with the **same** action, target and rationale it already has and add the example file as evidence:
  ```bash
  PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/capability_ledger.py set-disposition \
    --ledger "$LEDGER" --unit CU-xxxxxxxx --surface docs --action update --target "<existing target>" \
    --rationale "<existing rationale>" --evidence reports/example_verification/{family}/{platform}/{run}/<candidate id>.result.json
  ```
- Placement what-if: rebuild into a **sibling** file with `build ... --verified-examples <run dir>/verified_examples.json --out <ledger dir>/capability_ledger.verified.json` and compare each unit's placement with the current ledger. `verified_example_present` can promote a unit to a dedicated section. Never overwrite a ledger whose dispositions have already been edited (a rebuild resets them). If any placement changed, report it and let `/refresh-product` re-plan.

### 7. Write the hand-off table

Write `reports/example_verification/{family}/{platform}/{run}/handoff.md`. Content skills (`/new-docs-page`, `/page-update`, `/new-kb-howto`, `/new-blog-post`) cite examples from this table and nowhere else.

```
| Unit | Example id | Tier | Outcome | File | Artifact sha256 | Availability | Notes |
|------|------------|------|---------|------|-----------------|--------------|-------|
| CU-ab12cd34 | snippet_042 | 3 | ACCEPTED | <run dir>/snippet_042.md | f5d508... | released | |
| CU-9f00aa11 | readme_003  | 2 | ACCEPTED_COMPILE_ONLY | ... | ... | unreleased | no output claim |

BLOCKED (not handed over)
| Unit | Candidate | Reason | Detail |
```

A unit with no ACCEPTED row appears in a `NO EXAMPLE` list with the reason, so the content skill writes prose only or sets the disposition to `none` with a rationale.

### 8. Close

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-126 --status completed
```

## Post-conditions

- Every ACCEPTED example has a result JSON naming artifact sha256, source SHA (or released version), tier and toolchain.
- `handoff.md` exists and lists every selected unit as ACCEPTED, ACCEPTED_COMPILE_ONLY, BLOCKED or NO EXAMPLE.
- No file under `content/`, `knowledge/` or the clone cache was written.

## Error handling

| Condition | Result | Action |
|---|---|---|
| No JDK or build tool discoverable (`TOOLCHAIN-UNAVAILABLE`, detail `BLOCKED_TOOLCHAIN:`) | `BLOCKED_TOOLCHAIN` for every candidate | Report the discovery attempts. Do not fall back to syntax-only PASS. Content gets prose only. |
| Candidate reads an input no prelude provides (`FIXTURE-UNAVAILABLE`) | BLOCKED at proof tier 2 | List it. If the missing input is a plain file type, the default prelude may already cover it; otherwise leave it blocked. |
| Artifact cannot be resolved (published fetch fails, build fails, no registry coordinates) | `BLOCKED_ARTIFACT` | Report; units fall to prose only. Do not substitute a different version. |
| Non-Java platform with no artifact acquisition in its runner | Candidates run at the runner's offline ceiling | Record the tier honestly. Anything below a PASS is BLOCKED; content carries no code block for that unit. |
| Ledger fails validation | Stop | Fix the ledger through `/refresh-product`, never by hand-editing JSON. |
| Candidate needs editing to pass | BLOCKED | Do not edit. A real defect in upstream code is a finding to report. |

## Composition

Runs after `/refresh-product` has built the ledger (S-84) and before the surface skills. Its hand-off
table is read by S-56, S-20, S-58 and S-57, and re-checked independently by `/independent-content-review`
(S-127), which re-compiles every example itself and treats this skill's ledger as provenance only.
