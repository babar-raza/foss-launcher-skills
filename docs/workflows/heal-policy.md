---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §6d, §6e
# Ported: 2026-05-20 (parity migration)
# ID mapping: aspose.org skill IDs remapped to foss-launcher IDs per docs/id-mapping.md
---

# Heal-Enabled Policy Table and Terminal-Success State

### 6d. Heal-Enabled Policy Table

The healing automation system (`scripts/pipeline/lib/heal_controller.py`) uses a
policy table (`scripts/pipeline/lib/heal_policy.py`) to route triaged findings to
the correct healing strategy. This section documents the binding between
evaluation findings and healing actions.

#### Heal modes

| Mode | Meaning | Automated? |
|------|---------|------------|
| `auto` | Deterministic fixer available (frontmatter, placeholder, code fence) | Yes |
| `llm` | Requires LLM-assisted rewrite grounded in knowledge artifacts | Yes |
| `regen` | Requires upstream causal backtracking before local fix | Yes |
| `human` | No automated path — escalate to operator | No |
| `skip` | INFO-level or not worth fixing | No |

#### Policy resolution order

1. **Exact match** on `(fix_type, category)` — e.g., `(llm, FC)` routes
   forbidden-claim findings to S-21 with FC-specific prompt constraints.
2. **Wildcard match** on `(fix_type, *)` — default for that fix type.
3. **Fallback** to `human` mode if neither matches.

#### Category-specific LLM policies

| Category | Description | Skill | Effort |
|----------|-------------|-------|--------|
| AA | API accuracy — verify against api_surface.json | S-21 | medium |
| FC | Forbidden claims — remove and rewrite | S-21 | medium |
| PC | Platform contamination — replace with correct platform code | S-21 | medium |
| PT | Prose truth — correct against enriched_claims.json | S-21 | medium |
| CP | Code plausibility — replace snippet from clone cache | S-21 | medium |
| RL | Risk language — context-aware rewrite | S-21 | medium |
| ST | Structure — regenerate missing sections | S-21 | medium |
| RV | Role violations (LLM bucket) — restructure page | S-21 | medium |

#### Non-LLM policies

| Fix type | Mode | Skill | Regen after? | Effort |
|----------|------|-------|--------------|--------|
| `auto` | auto | — | No | low |
| `upstream` | regen | S-79 (causal-backtrack) | Yes | high |
| `human` | human | — | No | high |
| `skip` | skip | — | No | low |

#### Governance rules

- **Only `auto`, `llm`, and `regen` modes are heal-enabled.** `human` and
  `skip` are excluded from automated healing pipelines.
- **The policy table is the single source of truth** for heal-mode routing.
  Do not hard-code heal-mode decisions outside `heal_policy.py`.
- **Regression detection is mandatory.** After any healing pass, run
  `verify.py` to compare before/after findings. If regression severity is
  `critical` (grade decreased), revert the healing and escalate.
- **Regen-after findings** (upstream mode) must complete causal backtracking
  via S-79 before local fixes run. The heal controller enforces this ordering.

### 6e. Terminal-Success State (ceiling-reached)

A page is **ceiling-reached** when ALL of the following are true:

1. `audit.py --files {path}` exits 0 (no FAIL findings)
2. `validate_frontmatter.py --files {path}` exits 0
3. Grade is A or B (0 FAIL, ≤5 WARN)
4. All remaining WARN findings have been explicitly classified as one of:
   - Evaluator/linter conflict artifacts (prose softening triggers linter revert;
     WARN is restored; no stable prose edit resolves it)
   - Known false positives (token collision, etc.) with a classification record
     in `reports/skill-gaps/`
5. A skill run has been attempted to address each WARN and confirmed that no further
   content change improves the stable outcome

**When a page is ceiling-reached, agents MUST**:
- Classify it as ceiling-reached in session notes or plan artifacts
- NOT re-apply prose softening that a prior session confirmed the linter reverts
- NOT invoke S-21 (page-enhance) again without a changed pre-condition (e.g., new
  knowledge model, updated evaluator, linter rule change)
- NOT invoke S-83 (evidence-enhance) again if a prior S-78 run returned ESCAPED and
  the manual evidence panel is richer than auto-detection output

**Ceiling-reached is not a failure state.** Grade B with 0 FAIL and known
evaluator-conflict WARNs is publish-ready per the quality rubric. The WARNs are
system artifacts, not content defects.

**Reopening conditions** (any one of these allows retry):
- `prose_truth` evaluator updated to consult evidence panel (Option P1 from
  `reports/skill-gaps/2026-04-06-prose-truth-evaluator-claim-check.md`)
- Linter rule is identified and found to be configurable or removable
- `attach_evidence.py` gains merge-safe mode that preserves manual `apis`
- Knowledge model is updated (re-run S-12 → S-14 first; re-evaluate; if grade
  drops, use appropriate skill chain)
- Human explicitly authorizes a retry with specific rationale

#### Quality gate dispatch — development vs launch

| Use case | Correct skill | When to use |
|----------|---------------|-------------|
| Iterative development (page-by-page improvement) | S-25 (eval-page) or S-48 (content-eval) | During generation/enhancement loops; many times per session |
| Pre-launch publishability gate | S-62 (gap-eval) | Once per launch cycle; verifies against clone cache truth |
| Cross-product quality summary | S-64 (gap-report) | Post-launch or periodic; cluster analysis across families |

**Rule:** Use S-62 at most once per launch cycle (expensive; requires clone cache). Use S-25/S-51 during development. Do not use S-62 as a development-loop quality check — it is a launch-readiness gate, not a rapid-iteration tool.

