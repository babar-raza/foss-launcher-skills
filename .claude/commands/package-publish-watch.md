---
name: package-publish-watch
id: S-118
description: >
  Maven has its own watcher (`publish_watcher.py`, Mission MT008 D-03) because
---

<!-- CONTRACT: agent-executed
     purpose: check pypi/nuget/npm/go_modules/cargo registries for FOSS packages that
              have gone live since data/package_registry.json last recorded them
              unpublished, and — with operator confirmation — flip the registry entry
              and heal any remaining literal install-command content
     preconditions: active session; data/package_registry.json exists (Mission
                    MT015-2026-07-30-PACKAGE-REGISTRY)
     postcondition: verification.published flipped for any confirmed entry; content
                    healing applied (or explicitly deferred) for families still using
                    literal install text; all changes committed via S-76
     idempotent: yes — re-running with no new publish events makes no changes
     verified: 2026-08-01
-->
# S-118: Package Publish Watch — Multi-Registry Publish Detection and Content Healing

**Arguments**: $ARGUMENTS
Expected format:
```
[{family} {platform}] [--auto]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `{family} {platform}` | No | Check only this one entry instead of the full registry |
| `--auto` | No | Apply confirmed proposals and run content healing without an interactive confirmation prompt (matches S-110 Phase B's `--auto` convention) |

**Examples:**
```
# Check every pypi/nuget/npm/go_modules/cargo entry
/package-publish-watch

# Check only slides/net
/package-publish-watch slides net

# Unattended run (e.g. invoked from a maintenance sweep, not a human session)
/package-publish-watch --auto
```

---

## Purpose

Maven has its own watcher (`publish_watcher.py`, Mission MT008 D-03) because
`maven-metadata.xml` presence is a strong single-check signal. The other 5 registries
(pypi, nuget, npm, go_modules, cargo) don't have that guarantee — a bare HTTP 200 can
be a mid-deployment false positive — so this skill drives the debounce-gated adapters
built in TC-MT015-04/09 (`scripts/pipeline/lib/package_registries/`) instead, requiring
2 consecutive agreeing checks before proposing a flip.

This closes RUST-CRATESIO-001 (crates.io publish watch for `aspose-cells-foss-rust`)
and gives every future non-Java/non-Maven FOSS package the same "someone must remember
to check" problem Mission MT008's `foss-java-publish` (S-110) solved for Java — without
duplicating S-110's Java/Sonatype/GPG-specific machinery, none of which applies here.

**Use S-118 when:**
- Periodically checking whether an unpublished FOSS package (words/net, slides/net,
  cells/rust, or any future one) has gone live
- Following up on a `package-publish-watch` GitHub issue filed by the scheduled workflow
- After a product team reports a manual publish, to record it with real evidence

**Do NOT use S-118 for:**
- Maven/Java packages (use `/foss-java-publish` S-110)
- Actually publishing a package (this skill only detects and records; it never runs `twine upload`, `dotnet nuget push`, `npm publish`, or `cargo publish`)
- Full-corpus content remediation of an already-known defect (that's a dedicated content-healing effort, e.g. SLIDES-NET-NUGET-001 — this skill only heals content for a family/platform that JUST flipped published this run)

---

## Pre-conditions

1. `data/package_registry.json` exists and validates (`validate_package_registry`)
2. Active session ledger, or `--force-all` available for the eventual S-76 commit

---

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-118 --scope "data/package_registry.json,content/*/en/{family}/{platform}/**"
> ```

### Step 1 — Run the watcher

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.package_publish_watch
```

This reads `data/package_registry.json`, checks every `verification.published: false`
entry whose `registry_type` is one of `pypi`/`nuget`/`npm`/`go_modules`/`cargo` via its
adapter, applies the 2-consecutive-check debounce, and **persists the updated counters
to disk** (this is the one piece of state the automatic path writes — see
`package_publish_watch.py`'s module docstring for why that's safe: it's bookkeeping,
not a customer-facing change). Exit code 1 means at least one entry crossed the
debounce threshold this run; exit 0 means nothing to report.

If `{family} {platform}` was given in `$ARGUMENTS`, filter the printed findings to that
one entry (the script itself always checks the whole registry — filter the output, not
the invocation, so the persisted counters stay consistent for every entry).

### Step 2 — Present each proposal for confirmation

For each proposal in the output:
```
=== PROPOSAL: {family}/{platform} ({registry_type}) ===
Evidence: {evidence_url}
Method: {method}
Verified owner: {verified_owner or "not available from this registry's API"}
Content healing needed: {content_healing_needed} ({literal_content_files_flagged} file(s) flagged, if any)

Apply this state flip? [Y/N]
```

If `--auto` was passed, apply without prompting. Otherwise wait for confirmation.
If declined: leave the entry as-is (the debounce counter from Step 1 already persisted;
the next scheduled run will re-check from there, not from zero).

### Step 3 — Apply confirmed proposals

```python
# via a short inline script, or interactively:
from commands.ops.package_publish_watch import apply_proposal
import json
data = json.loads(open("data/package_registry.json", encoding="utf-8").read())
apply_proposal(data, proposal, checked_at="{today's date}")
json.dump(data, open("data/package_registry.json", "w", encoding="utf-8"), indent=2)
```

### Step 4 — Content healing, if flagged

If `content_healing_needed` is true for a just-applied proposal:

1. **Check the shortcode is already wired** — if `{family}/{platform}` already renders
   via `maven-coord`/`cargo-crate`/`package-install`, no content edit is needed at all;
   the registry flip in Step 3 alone fixes every page's rendered output on the next
   Hugo build. Confirm via a real Hugo build (same `HUGO_PARAMS_SEARCH_ENABLE=false`
   convention as TC-MT015-02) that the shortcode now renders the live install command
   for at least one representative page.
2. **If literal (non-shortcode) text remains** — run the shared migrator:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.package_install_migrator {family} {platform} --dry-run
   ```
   Review the dry-run summary (`files_migrated`, `block_replacements`,
   `inline_mentions_found`). Present it for confirmation (same gate as S-110 Phase B's
   content-healing plan) unless `--auto`. Then:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.package_install_migrator {family} {platform} --execute
   ```
   `inline_mentions_found` are NEVER auto-migrated (package-install renders a block-level
   element, unsafe to splice mid-sentence — see the migrator's module docstring). Report
   these as follow-up items; do not hand-edit them under this skill's own scope unless
   the count is small enough for a direct S-73 pass in the same session. If it's large
   (tens to hundreds of files), file a backlog row instead of attempting it inline —
   mirror the rigor of SLIDES-NET-NUGET-001's own filing, don't silently drop the count.
3. **Post-migration sweep**: re-run `verify_package_install_literals` (via
   `/content-check` or a direct audit run) across the family/platform's content — the
   only literal matches remaining should be the `inline_mentions_found` count from step
   2, nothing new.

### Step 5 — Commit

```
/commit --scope pipeline --hint "package-publish-watch: {family}/{platform} confirmed published, {N} files healed"
```

> **Skill context close** — run after Step 5:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-118 --status completed
> ```

---

## Scheduled detection (notification only, no auto-commit)

`.github/workflows/package-publish-watch.yml` runs `package_publish_watch.py
--no-persist-counters` on a schedule and files a GitHub issue when proposals appear —
mirroring `maven-publish-watcher.yml`'s shape exactly. **Deliberate scope limit**: the
scheduled CI run does NOT persist debounce counters back to the repository (that would
require a CI bot-commit path with its own conflict-safety design, a nontrivial and
separate piece of infrastructure not built in this pass — flagged honestly rather than
attempted unsafely). Counter persistence in practice happens when this skill (S-118) is
run interactively by an agent (Step 1 above), which naturally commits through the normal
session/S-76 path. The scheduled workflow's job is narrower and safe: tell a human/agent
there's something to check, the same job `maven-publish-watcher.yml` and
`upstream-monitor.yml` already do.

---

## Post-conditions

- **If proposals confirmed**: `data/package_registry.json` reflects the new
  `verification.published: true` state with real evidence; content healed (shortcode-only
  fix or migrator-applied) or a follow-up backlog row filed for what wasn't
- **If no proposals**: only the debounce counters may have changed (persisted); no
  content or `verification.published` change
- **If proposals declined**: counters persisted from Step 1; nothing else changes

---

## Refusal and halt conditions

| Condition | Response |
|-----------|----------|
| `data/package_registry.json` fails schema validation | HALT — fix the data file first |
| A proposal's evidence_url returns something other than what Step 1 recorded (re-checked at apply time) | HALT that one proposal, do not apply; report as a possible flapping-API false positive |
| Migrator dry-run shows `skipped_protected` > 0 | Report which files were skipped (protected-page provenance) and why; do not force-write them |
| Operator declines a proposal | Leave state as Step 1 left it; do not retry within the same invocation |
| `--auto` requested content healing on a family/platform with >50 `inline_mentions_found` | Do not attempt inline; file a backlog row instead (matches SLIDES-NET-NUGET-001 precedent) |

### What S-118 will never do

- Publish a package to any registry (detection and content-healing only)
- Auto-apply a `verification.published` flip without operator confirmation (unless `--auto`)
- Rewrite an inline backtick-wrapped install-command mention (block-level shortcode only)
- Touch Maven/Cargo's own dedicated shortcode data beyond what `apply_proposal` sets for a cargo entry (Maven stays on `publish_watcher.py` entirely)
- Commit without going through `/commit` (S-76)

---

## Error handling

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: No module named 'commands'` | Missing `PYTHONPATH=scripts/pipeline` | Prefix every invocation with `PYTHONPATH=scripts/pipeline` |
| Adapter returns `ambiguous=True` repeatedly | Transient network/API issue | Counter does not advance; re-run later, no action needed |
| Migrator `no_registry_entry` | Family/platform has no `data/package_registry.json` entry, or its `registry_type` is `maven`/`cargo` | Add the entry first (see TC-MT015-01/07), or use the correct dedicated shortcode/migrator |

---

## LLM Metrics Obligation

This skill makes no `llm.professionalize.com` calls — no metrics obligation applies.
