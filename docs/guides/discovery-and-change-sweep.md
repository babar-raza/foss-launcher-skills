<!--
OWNERSHIP: docs/discovery-workflow.md
AUTHORITY: Discovery and change-detection workflow for operators (S-93, S-94, S-95)
MUST NOT RESTATE: Governance rules — AGENTS.md is the only authority for rules
REVIEW TRIGGERS:
  - repo_patrol.py CLI changes → update §3 command reference
  - S-93/S-94/S-95 skill step changes → update §2 workflows
  - products.json status enum changes → update §4 candidate states
MAINTAINED BY: Agent (docs/ is ALLOWED per AGENTS.md §4b)
ADDED: 2026-04-24 (TC-DOC-01/03/04, discovery-plan dapper-splashing-bengio Phase 5)
-->

# Discovery & Change Detection Workflow

Covers the three discovery skills (S-93 `/repo-patrol`, S-94 `/change-sweep`, S-95 `/discovery-triage`)
and their backing script `scripts/pipeline/commands/diagnostics/repo_patrol.py`. For governance rules, see `AGENTS.md`.

---

## §1 — Overview

The discovery system has three responsibilities:

| Responsibility | Skill | What it does |
|---------------|-------|-------------|
| Find new FOSS repos | S-93 `/repo-patrol` | Scans 26 GitHub orgs; confidence-scores new repos; writes `patrol_report.json` |
| Detect upstream changes | S-94 `/change-sweep` | Batch SHA comparison across all 15 active products; writes `sweep_report.json` |
| Route findings to action | S-95 `/discovery-triage` | Reads patrol+sweep reports; creates backlog items; **never auto-invokes S-84 in MVP** |

**Triage-first mandate (MVP)**: S-95 routes all findings to backlog items only. It never directly
invokes S-12 or S-84. Operator reviews backlog items and manually runs `/refresh-product` per product.

---

## §2 — When to Run Each Skill

### Session-start advisory
At every session start, S-77 step 5.5 checks discovery report ages:
- `patrol_report.json` older than 7 days → suggests `/repo-patrol`
- `sweep_report.json` has `high_count > 0` or `medium_count > 0` → suggests `/discovery-triage`
- Neither report exists → suggests running both for initial baseline

The advisory is **informational only** — it never triggers scans automatically.

### Manual invocation cadence (MVP operating model)
A weekly reminder (R-12) surfaces in session-start. Recommended workflow:

```
/repo-patrol           # Scan 26 orgs for new repos
/change-sweep          # Sweep 15 products for SHA changes
/discovery-triage      # Route findings to backlog
```

---

## §3 — Command Reference

### S-93: `/repo-patrol` — Org Scan

```bash
# Skill invocation (recommended)
/repo-patrol

# Backing script — dry-run (read-only, no registry update)
.venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py scan

# With registry update (adds candidates to data/products.json)
.venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py scan --apply

# Custom inactivity threshold (default: 180 days)
.venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py scan --inactive-days 90

# Force-include a previously rejected repo
.venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py scan --force {repo_name}
```

**Outputs**: `reports/discovery/patrol_report.json`

| Field | Meaning |
|-------|---------|
| `new_candidates` | Repos not yet in `data/products.json` with action and confidence |
| `status_changes` | Repos already in registry that changed state (e.g., newly archived) |
| `unclassifiable` | Repos whose name doesn't match any known FOSS pattern |
| `skipped_count` | Already-launched repos with no change |

### S-94: `/change-sweep` — Batch SHA Comparison

```bash
# Skill invocation (recommended)
/change-sweep

# Backing script
.venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py sweep
```

**Outputs**: `reports/discovery/sweep_report.json`

| Field | Meaning |
|-------|---------|
| `changed` | Products whose upstream repo SHA differs from stored SHA |
| `unchanged` | Products with matching SHAs (no action needed) |
| `fetch_failures` | Products where `update_clone()` failed (network/auth issue) |
| `summary.high_impact` / `medium_impact` | Impact classification counts |

**Note**: `/change-sweep` calls `update_clone()` per product (network fetch). It does NOT set
`stale_since` — that is S-12's responsibility. Route HIGH/MEDIUM findings to S-12 via S-95.

### S-95: `/discovery-triage` — Route Findings to Backlog

```bash
# Skill invocation (agent-executed, no backing script)
/discovery-triage
```

Reads `patrol_report.json` and `sweep_report.json` and creates backlog items:

| Finding type | Backlog item | Priority |
|-------------|-------------|----------|
| New candidate (confidence ≥ 0.70) | ST-item, Cat=K, Effect=KF | P1 |
| New candidate (confidence 0.40–0.69) | INV-item | P2 |
| Unclassifiable repo | INV-item | P3 |
| Changed product (HIGH impact) | ST-item, Cat=K, Effect=TF | P1 |
| Changed product (MEDIUM impact) | ST-item, Cat=K, Effect=TF | P2 |

**S-95 NEVER directly invokes S-12 or S-84 in MVP.** All findings → backlog items only.

### Combined report

```bash
.venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py report
```

Generates `reports/discovery/combined_report.md` — human-readable summary of latest patrol
and sweep data. Suitable for operator review or inclusion in session notes.

---

## §4 — Discovery Reports

Reports are **local-only** (gitignored at `reports/`). They are not committed.

| File | Purpose |
|------|---------|
| `reports/discovery/patrol_report.json` | Latest org scan: candidates, status changes, unclassifiable |
| `reports/discovery/sweep_report.json` | Latest batch sweep: changed/unchanged products, fetch failures |
| `reports/discovery/combined_report.md` | Human-readable summary of both reports |
| `reports/discovery/history/YYYY-MM-DD-patrol_report.json` | Dated scan snapshots |
| `reports/discovery/history/YYYY-MM-DD-sweep_report.json` | Dated sweep snapshots |

**Cleanup**: History files are local-only and accumulate over time. Manual cleanup:
```bash
# Remove history files older than 90 days (adjust date as needed)
ls reports/discovery/history/
```
No automated cleanup is planned (OOS-15).

---

## §5 — Candidate State Machine

`data/products.json` uses a `status` field for discovered repos:

| Status | Meaning | Next action |
|--------|---------|-------------|
| `launched` | Full content published | Routine refresh via S-84 when sweep detects change |
| `candidate` | Confidence ≥ 0.70; awaiting human triage | Operator reviews; runs `/launch-product` if approved |
| `investigating` | Confidence 0.40–0.69; needs validation | Operator investigates; promotes to `candidate` or `rejected` |
| `rejected` | Explicitly excluded | No action; `rejection_reason` recorded in registry |
| `archived` | Was active; now archived on GitHub | Checked at each scan; promoted to `candidate` if un-archived |

**Rejected repos persist**: A `rejected` entry is not re-promoted automatically. To reconsider:
```bash
.venv/Scripts/python scripts/pipeline/commands/diagnostics/repo_patrol.py scan --force {repo_name} --apply
```

Adding a `candidate` to the registry requires `--apply` on the scan. **Human approval is required
before running `/launch-product`** regardless of confidence score — `/discovery-triage` creates a
backlog item for human triage; it does not initiate launch.

---

## §6 — Session-Start Advisory Output

When discovery reports are present, session-start step 5.5 outputs an advisory block:

```
=== DISCOVERY ADVISORY ===
patrol_report.json: 3 days old — current
sweep_report.json: unprocessed HIGH findings (slides/python)
→ Suggest: /discovery-triage to route unprocessed findings
```

This block is **read-only** and does not trigger any scan or triage automatically.

---

## §7 — Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `patrol_report.json` shows 0 repos | GitHub API rate limit or missing `GITHUB_TOKEN` | Set `GITHUB_TOKEN` in `.env`; retry |
| Fetch failure in sweep report | Clone URL invalid or network down | Check `reports/discovery/sweep_report.json` `fetch_failures` list; verify clone URL in `data/products.json` |
| New candidate not in products.json | Scan ran without `--apply` | Re-run scan with `--apply` to persist the entry |
| Session advisory shows stale patrol | `patrol_report.json` older than 7 days | Run `/repo-patrol` |
| Rejected repo reappears | Scan ran without `--force` and registry was reset | Check `data/products.json` for `status: "rejected"` — should persist across rescans |

---

## §8 — Post-Pilot Auto-Refresh Gate (TC-GATE-01)

**Currently: CLOSED.** Direct S-84 auto-dispatch from S-95 is gated behind TC-GATE-01.

Activation requires:
1. 3 successful triage cycles with correct backlog routing (TC-MONITOR-01)
2. Human operator reviews and approves enabling `--auto-refresh` flag in S-95 skill definition

Until TC-GATE-01 is opened, S-95 routes all findings to backlog items only and the operator
manually invokes `/refresh-product {family} {platform}` per product.
