# Project Assessment: Recruitize.AI Review Agent

**Date:** 2026-06-09
**Scope:** Full reverse-engineering assessment for operational adoption
**Assessor:** Deep static analysis of codebase, entrypoints, tests, CI, and config

---

## Executive Verdict

This is a production-internal, private-operator pipeline tool for a specific organization (Recruitize.AI). It ingests WordPress blog posts about AI product announcements, uses an LLM to classify them, identifies linked GitHub repositories, sends those repositories through a 16-step LLM analysis pipeline via an external coding-orchestration MCP service, scores them against a proprietary 4-axis APRV framework (Agentic, Practices, Readiness, Verification), and publishes structured HTML review artifacts back to WordPress — with optional consolidated and supergroup portfolio reports on top.

The engineering quality is significantly above average. The code is well-structured, consistently styled, defensively programmed, and makes correct non-trivial choices: LLM resilience via retry chains and circuit-breaker model registry; structured outcome taxonomy (ok/degraded/failed); file-based state machine for HITL and agent lifecycle; LangGraph as a thin decision/reflection node over a deterministic pipeline. The test suite is substantial (60+ test files), uses Node.js native test runner, injects dependencies cleanly, and tests real orchestration flows with mock stages.

Hard blocker for any new adopter: the system is inseparable from 3-4 external proprietary services — a BigData MCP service, an upstream coding-orchestration MCP service (the actual repo scanner), an OpenAI-compatible LLM API, and a WordPress target. Without all four, the system does not run end-to-end. The model-registry.json ships empty and the automation schedule is disabled. These are deployment configuration realities, not code defects.

For an operator who owns all four infrastructure pieces: close to production-adoptable with targeted hardening. For anyone without those pieces: architecture reference only.

---

## Project Identity

| Attribute | Value |
|-----------|-------|
| Type | Automation pipeline / scheduled worker / MCP service / CLI tool |
| Language | JavaScript (Node.js ESM, all `.mjs`) |
| Framework | LangGraph for agent loop; native `node:http` for MCP server; no web framework |
| Package manager | npm |
| Runtime | Node.js 20+ |
| Deployment | CLI scripts + Docker container (MCP server mode) + automation loop |
| Version | 0.1.0 (private, not published to npm) |
| Dependencies | `@langchain/langgraph` (runtime); `ajv`, `eslint`, `globals` (dev) |
| Maturity | Active development, post-initial release, 37+ tracked issues in `.agent/issues/` |
| Intended users | Internal operator team (Recruitize.AI editorial/engineering) |

---

## What the Project Actually Does

The system watches a WordPress blog for posts announcing AI projects. It fetches and caches those posts via a BigData MCP service. It asks an LLM to decide which posts are genuinely AI/agentic product announcements (the WHERE/SELECT query engine stages). For each matched post, it extracts linked GitHub repository URLs, normalizes them, and sends each repository to an external coding-orchestration service that reads the repo and runs a 16-step LLM analysis. Those step results are merged into an APRV scorecard. A composition LLM then writes a human-readable HTML review page. Optionally, reviews are aggregated into a portfolio summary and a supergroup comparative review. Results are published to WordPress under HITL operator control.

### Main capabilities

- Content ingestion from a BigData MCP source
- LLM-powered post classification with WHERE/SELECT query engine and checkpoint resume
- Repository URL extraction, normalization, and deduplication
- 16-step repo analysis pipeline via upstream coding MCP: `orient`, `footprint`, `gitMeta`, `tests`, `securityScan`, `aCollect`/`aWar`, `pCollect`/`pWar`, `rCollect`/`rWar`, `vCollect`/`vWar`, `aprvCoherence`, `deepening`, `summary`
- Four-axis APRV scoring (Agentic, Practices, Readiness, Verification maturity)
- Review composition with per-post HTML output and traffic-light badges
- Portfolio and supergroup (SG) comparative report generation
- WordPress publish with create-or-update idempotency
- LangGraph agent loop with decide/reflect nodes and HITL gate
- Scheduled automation with blocking logic (HITL check, active run check)
- MCP server exposing the pipeline as JSON-RPC 2.0 tools on port 3200
- Feedback digest for cross-run LLM prompt injection

### Hard boundaries — what it does NOT do

- Does not scan repositories itself — delegated entirely to the upstream coding-orchestration MCP
- Does not have a UI
- Does not support multiple concurrent operators (single-primary-process file lock)
- Does not use a database — all state is filesystem under `.cache/`
- Does not directly call GitHub API — that is the upstream MCP's job
- Does not have built-in cache eviction or TTL

---

## How It Actually Works

### True entrypoints

| Command | Script | Role |
|---------|--------|------|
| `pipeline:review:run` | `scripts/pipeline/run-review-reporting.mjs` | Full pipeline CLI, primary operator path |
| `mcp:review-agent:serve` | `scripts/mcp/run-review-agent-mcp-server.mjs` | HTTP MCP server on port 3200, Docker default |
| `pipeline:automation:serve` | `scripts/pipeline/run-scheduled-automation.mjs` | Scheduled automation loop |
| `pipeline:review:agent` | `scripts/pipeline/run-review-agent-loop.mjs` | LangGraph agent loop |
| `pipeline:sg-review:run` | `scripts/pipeline/run-sg-review-reporting.mjs` | Supergroup portfolio review |

All five entrypoints go through `runPrimaryProcess()` which acquires a file-based lock at `.cache/locks/primary-process.lock`, enforcing single-process discipline.

### End-to-end main flow

```
run-review-reporting.mjs
  └── runAnnouncementReviewReportingPipeline()
        ├── Stage 1: runContentIngestionPipeline()
        │     ├── BigDataMcpClient.callTool("Search") → fetch post list
        │     ├── BigDataMcpClient.callTool("GetPost") × N → fetch bodies
        │     └── BigDataMcpClient.callTool("GetComment") × N → fetch comments
        │     (results cached to .cache/ingestion/)
        │
        ├── Stage 2: runQueryRepoIntelligencePipeline()
        │     ├── QueryEngine WHERE: LLM classifies each post → matched / not_matched
        │     ├── QueryEngine SELECT: LLM extracts repo URLs from matched posts
        │     └── Normalization: deduplicate, validate, extract GitHub owner/repo
        │     (results checkpointed to .cache/query/)
        │
        ├── Stage 3: runRepoProfileBatch() (if runRepo=true)
        │     ├── For each normalized repo URL (concurrency: REPO_SCAN_CONCURRENCY, default 2):
        │     │     ├── upstream coding MCP: projects/clone or pull
        │     │     └── 16 analysis steps: orient → footprint → ... → summary
        │     │           Each step: runStructuredCall() with up to 5 retries
        │     │           2 full chain retries on failure
        │     └── Results: stepResults merged into APRV scorecard per repo
        │     (results cached to .cache/repo/)
        │
        ├── Stage 4: runReviewComposeStage()
        │     ├── LLM composition call via runStructuredCall()
        │     ├── Deterministic APRV scale scoring, traffic-light badge assignment
        │     ├── Employee directory match for authors and contributors
        │     ├── HITL queue build from failure signals and quality gaps
        │     └── HTML render to .cache/pipelines/review/<runId>/
        │
        └── Stage 5: runReviewPublishStage() (optional, gated by HITL)
              └── WordPressApiPublisher.createOrCommitPost()
```

### External service dependencies

| Service | Role | Auth |
|---------|------|------|
| BigData MCP | Content search and post/comment fetch | `REVIEW_AGENT_BIGDATA_BEARER_TOKEN` |
| Upstream coding-orchestration MCP | Repository analysis (actual code scanning) | `REVIEW_AGENT_UPSTREAM_BEARER_TOKEN` |
| LLM API (OpenAI-compatible) | Classification, composition, agent loop decisions | `REVIEW_AGENT_LLM_API_KEY` |
| WordPress REST API | Publish reviews as posts | `WP_TOKEN` |
| SMTP (optional) | Critical failure email alerts | `REVIEW_AGENT_AUTOMATION_SMTP_*` |

### State and persistence

100% filesystem under `.cache/`. No database. Cache policy is configurable per run: `on` (use cached), `off` (always fresh), `rebuild` (rewrite cache). The process lock at `.cache/locks/primary-process.lock` is a JSON file with PID and timestamp — not an OS-level lock. All agent loop state (status, events, artifacts paths, HITL queue) is written to `state.json` and `events.json` per run.

---

## Architecture Judgment

### Actual architecture style

Staged pipeline with explicit artifact handoffs, layered by an agent loop state machine, wrapped by an MCP service boundary. Deliberately synchronous inside each pipeline run. Not event-driven. Not microservices.

### Strong patterns

- **Dependency injection throughout:** pipeline functions accept `deps` objects (`runAnnouncementReviewReportingPipeline(input, deps)`), making all orchestration testable without mock libraries.
- **`runStructuredCall()`** (`src/core/agents/runner/structured-call.mjs`): sophisticated LLM call wrapper with retry, failure taxonomy (timeout / transport_error / empty_output / json_parse_failed / schema_invalid), requiredness levels (blocking/important/optional), and HITL escalation signals.
- **`ModelRegistry`** (`src/core/agents/runner/model-registry.mjs`): in-memory circuit breaker with exponential backoff banning, alias resolution, fallback chains, depth-limited traversal (MAX_RESOLVE_DEPTH=20).
- **Primary process lock** prevents concurrent corruption without distributed locking.
- **HITL as first-class state machine state**, not a side effect.
- **Feedback digest injection** into LangGraph prompts for bounded cross-run adaptation.

### Weak patterns

- **File-based lock has no heartbeat renewal.** `runPrimaryProcess()` acquires the lock and releases it on exit, but there is no periodic write to prove the process is still alive. A crash leaves a stale lock that blocks all future runs until manual deletion of `.cache/locks/primary-process.lock`.
- **No cache eviction.** `.cache/` grows indefinitely. After sustained operation, disk consumption becomes a real operational concern.
- **LangGraph dependency is heavyweight for the actual usage.** The graph has two nodes (decide + reflect). The adaptive graph pattern is correct but adds a production dependency for what could be two plain async functions.
- **Model registry is empty by default.** `config/model-registry.json` ships with `"models": {}`. The entire fallback/circuit-breaker infrastructure is inert until the operator populates it.
- **`console.error` and the observability service run in parallel.** The runner layer logs via `console.error` directly; the `observability-service.mjs` with its log routing and OpenTelemetry integration is used at the pipeline layer. Log routing (file sink, OTEL) therefore misses all runner-level output.

### Coupling analysis

- `run-announcement-review-reporting-pipeline.mjs` (55KB+) is the single large orchestrator. It imports from nearly every subsystem. Correct for a pipeline pattern but the highest-friction file for future changes.
- The 16-step repo analysis pipeline is tightly coupled to the upstream MCP API contract. A breaking change in the upstream service requires updates in multiple files.
- `WordPressApiPublisher` is cleanly isolated.

### Dead zones

- `scripts/ops/evaluate-repo-analysis.0` — unknown extension, not referenced anywhere. Likely vestigial.
- The `loadOldPhasePrompt` fallback path in `repo-analysis-pipeline.mjs` (line 305-315) — old phase-1 prompt fallback for the `orient` step. Active dead code that runs silently when the new prompt file is missing.

---

## Code and Engineering Assessment

### Well written

- `structured-call.mjs` — sophisticated retry/outcome/HITL design with a meaningful failure taxonomy
- `model-registry.mjs` — correct circuit breaker with exponential backoff, alias resolution with cycle detection
- `wordpress-api-publisher.mjs` — handles WordPress.com and self-hosted URLs, binary-search comment truncation to 50KB byte limit, idempotent create-or-update
- `primary-process-lock.mjs` — uses `fs.open(..., "wx")` (O_EXCL exclusive create), stale takeover support, clean release
- `run-agent-loop.mjs` — clean state machine, events persisted at each transition, progress streaming via `onProgress` callbacks
- Test design — `forceDeterministic(true)` to bypass LLM for agent loop tests; inline dep injection; no third-party mock framework

### Risky or poorly implemented

- **`config/model-registry.json` sentinel value.** `"defaultFallbackModel": "no-default-fallback-model"` — if the fallback chain resolution is ever hit and this value is used, `resolveModel()` will throw a fatal error with an opaque message that operators won't recognize.
- **Recursive retry in agent loop.** `runAgentLoop()` calls itself on reflection-retry (`run-agent-loop.mjs` line 218). Bounded at MAX_REFLECTION_COUNT=2 in practice, but the recursion is implicit rather than explicit.
- **`process.env` and `.env` read at module load time** in `model-policy.mjs` via `fs.readFileSync`. A parse error in `.env` throws at module import, not at call time.
- **"Good work." / "Thank you for correcting" prefixes** injected between analysis steps in `repo-analysis-pipeline.mjs` (lines 322-328). Relies on session context in the upstream MCP. If the session is not preserved, this text appears as a meaningless preamble to a cold LLM context.

### Likely expensive to maintain

- **The 16-step repo analysis pipeline.** Any changes to the APRV framework require coordinating prompt file updates, normalizer updates, validator updates, and test fixture updates across a large number of files.
- **`run-review-composition-publication-stage.mjs`** — the largest single file (34KB+). Every review format change touches it.

---

## Reality vs. Claims

### Verified truths

- Five distinct control surfaces over one core: all five entrypoints converge on `runAnnouncementReviewReportingPipeline()`. Verified by direct tracing.
- HITL is a first-class state machine state. Verified in `run-state.mjs` and lifecycle tests.
- The agent loop uses LangGraph. Verified in `langgraph-agent-loop-brain.mjs`.
- Model registry implements circuit breaking with exponential backoff. Verified in `model-registry.mjs`.
- Artifacts are persisted and not reconstructed from logs. Verified by `.cache/` write paths throughout the pipeline.

### Partially true claims

- "Released and operated under the documented runtime profile" — the code is production-quality, but nothing runs by default. The automation schedule has `"enabled": false`. The model registry is empty. An inheriting operator must populate 15+ env vars before anything executes.
- "Deterministic stage topology" — the stage sequence is fixed, but the composition stage has significant LLM-driven variability in output content.

### Misleading

- The README and docs imply the model registry has meaningful fallback chains configured. It does not. The infrastructure exists but ships unconfigured.

### Critical undocumented behavior

- A crash leaves a stale lock file. The operator must manually delete `.cache/locks/primary-process.lock` to proceed. Not documented in the quickstart.
- The `--fresh-start` flag runs `rm -rf .cache` with no confirmation prompt. All checkpoints, cached repo analyses, and scheduler receipts are permanently deleted.
- APRV scoring calibration zones are baked into prompt files, not config. Changing the scoring methodology requires prompt and normalizer code changes.

---

## Operational Readiness

### Required environment variables (minimum set)

```
REVIEW_AGENT_BIGDATA_MCP_URL
REVIEW_AGENT_BIGDATA_BEARER_TOKEN
REVIEW_AGENT_UPSTREAM_MCP_URL
REVIEW_AGENT_UPSTREAM_BEARER_TOKEN
REVIEW_AGENT_LLM_BASE_URL
REVIEW_AGENT_LLM_API_KEY
REVIEW_AGENT_MODEL_QUERY_ANALYSIS       # or all REVIEW_AGENT_MODEL_* roles
REVIEW_AGENT_MODEL_UPSTREAM_CODING
REVIEW_AGENT_MODEL_REVIEW_COMPOSITION
REVIEW_AGENT_MCP_BEARER_TOKEN           # required for MCP server mode
WP_TOKEN                                # required for WordPress publish
```

### Failure behavior

| Failure mode | Handling |
|-------------|----------|
| LLM call fails | Retry up to 5 times per step; HITL escalation on failure |
| Repo analysis step times out | Logged; chain retry with clean session |
| Upstream MCP unavailable | Transport error; step marked failed; overall run degraded or blocked |
| Process crash mid-run | Stale lock left; manual cleanup required |
| WordPress publish fails | Error thrown; run exits with code 2 |

### Observability

- JSON structured logging to stdout/stderr via `observability-service.mjs`
- Optional OpenTelemetry integration (soft-load, no hard dependency on `@opentelemetry/api`)
- In-memory counters exposed at `/metrics` HTTP endpoint (lost on restart — not durable)
- Optional log file sink via `--log-file` CLI argument
- Run events persisted to `events.json` per run (durable debugging record)

### Security posture

- Bearer token authentication required on MCP server; service refuses to start without it
- No database — no SQL injection surface
- No user-facing HTML rendering in this codebase — no XSS surface
- `gitleaks` secret scanning in CI
- `npm audit` at moderate level in CI
- Secrets are env-var only; `.gitignore` covers `.env`

### Deployment

- Single machine, single operator process at a time
- Docker compose wraps MCP server mode cleanly with volume for `.cache/`
- Healthcheck implemented in Dockerfile and docker-compose.yml
- No horizontal scaling support — process lock is local filesystem only

---

## Adoption Recommendation

**Adopt with limited hardening** — if you own all four upstream services.

The engineering quality justifies adoption. The architecture is well-considered: explicit artifacts, fail-closed HITL, model circuit breaking, dependency injection into testable pipeline functions, and a clean MCP surface for external orchestration. The CI pipeline has real quality gates: coverage minimums (70/60/70/70), secret scanning, artifact schema validation, and MCP smoke testing.

The required hardening items are tactical, not architectural:

1. Add lock stale-takeover by default (e.g., `staleAfterMs: 4 * 60 * 60 * 1000`) so crash recovery is automatic
2. Add cache eviction — a `--max-cache-age-days` option or scheduled cleanup job
3. Populate `config/model-registry.json` with model aliases and fallback chains before first production run
4. Enable `config/automation-schedules.json` and verify with a short dry-run window
5. Add a `--dry-run` flag that runs all stages but skips WordPress publish

If you do not own the upstream BigData and coding-orchestration MCP services, adopt only selected subsystems: `QueryEngine`, `runStructuredCall`, `ModelRegistry`, `WordPressApiPublisher`, and `runPrimaryProcess` are all general-purpose and well-implemented.

---

## Top Gaps and Fixes

### Fix before production use

| Priority | Issue | Location | Severity |
|----------|-------|----------|----------|
| P0 | Stale lock not auto-cleared after crash | `run-primary-process.mjs` | HIGH |
| P0 | Model registry ships empty — fallback infrastructure inert | `config/model-registry.json` | HIGH |
| P1 | No cache eviction — `.cache/` grows forever | All write paths | MEDIUM |
| P1 | Automation schedule disabled by default | `config/automation-schedules.json` | MEDIUM (doc gap) |
| P2 | `console.error` logging bypasses observability service in runner layer | `structured-call.mjs`, `llm-response-api-runner.mjs` | LOW |

### Fastest pilot path

1. Set all required env vars
2. Run `npm test` to verify baseline
3. Run `pipeline:review:run --stop-after intelligence --run-repo false` to test content ingestion and query classification without repo analysis or publish
4. Add `--run-repo true --repos-limit 5` to test repo analysis on a small set
5. Inspect `.cache/` artifacts before enabling WordPress publish

### Highest-risk assumptions to verify first

1. **Upstream coding-orchestration MCP API contract** — all 16 analysis steps depend on it. Its performance, session-continuity behavior, and error responses are opaque from this codebase. The `runMaxWaitMs=30min` default suggests it can be very slow.
2. **BigData MCP content schema** — if post/comment JSON structure differs from what `bigdata-post-search.mjs` expects, content ingestion silently produces empty indexes.
3. **WordPress category resolution** — `resolveCategoryIdByName()` returns `0` if the category doesn't exist. Posts published with `categories: [0]` may silently publish uncategorized.

---

## Grades

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Functional clarity | 8/10 | System does one specific thing well; code matches docs; dock for undocumented stale-lock behavior and empty model registry |
| Architectural quality | 8/10 | Excellent stage/artifact discipline, clean DI, correct HITL state; dock for monolith orchestrator and filesystem-only persistence |
| Code quality | 8/10 | Consistently defensive, clean naming, well-commented decisions; dock for logging inconsistency and "Good work." injection |
| Operational maturity | 7/10 | CI is serious; dock for no cache eviction, no lock heartbeat, disabled automation by default |
| Test confidence | 7/10 | 60+ files, DI injection, `forceDeterministic` pattern; dock for zero real external integration tests |
| Documentation trustworthiness | 7/10 | ADRs are accurate; underdocuments stale lock, empty model registry, disabled automation |
| Security confidence | 7/10 | Bearer auth, no DB injection, secret scan in CI; dock for no lock heartbeat and WordPress category silent-fail |
| Integration fitness | 6/10 | Clean MCP and SDK surfaces; dock heavily for 4 required external proprietary services with no setup guides included |
| Maintainability | 7/10 | Good modularity; dock for 55KB orchestrator monolith and 16-step prompt-coupled analysis pipeline |
| Overall adoption confidence | 7/10 | Production-ready with limited hardening for an operator who owns the full stack; reference-only otherwise |
