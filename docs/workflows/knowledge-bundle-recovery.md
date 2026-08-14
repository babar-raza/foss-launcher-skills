# Knowledge Bundle Recovery (FRESH-001)

> Added: 2026-08-14 (FRESH-001 — source-freshness / fact-freshness system)
> Companion docs: [freshness-and-bounded-regen.md](freshness-and-bounded-regen.md), [knowledge-git-tracking-migration.md](knowledge-git-tracking-migration.md)

## What this covers

`promote.py`'s `promote_atomic()` (the default path since FRESH-001; opt out with
`--no-atomic` or `PROMOTE_ATOMIC_BUNDLE=0`) writes a complete knowledge bundle into an
isolated `knowledge/{family}/{platform}/merged.staging.{bundle_id}/` directory, then
swaps it into place:

```
merged/  --rename-->  merged.atomic-bak/
merged.staging.{bundle_id}/  --rename-->  merged/
(verify merged/bundle_manifest.json is COMPLETE)
merged.atomic-bak/  --delete-->  (gone)
```

A crash between any two of those steps leaves the product directory in one of three
well-defined, automatically-recoverable states. `promote_recover.py` (module:
`scripts/pipeline/commands/ops/promote_recover.py`) detects and corrects them.

**This runs automatically.** `promote_atomic()` calls `promote_recover.recover()` as
its own first step before starting a new swap — recovery is invisible in the common
case. The CLI below is for manual inspection or when `promote_atomic()` itself
refuses to proceed (AMBIGUOUS state).

## States

| State | Condition | Meaning | Recovery |
|---|---|---|---|
| HEALTHY | `merged/` exists, no `.atomic-bak`, no `.staging.*` | Nothing to do | none |
| COLD_START | `merged/` absent, no `.atomic-bak`, no `.staging.*` | Never promoted yet | none |
| STATE_A | `merged/` exists **and** `.staging.*` exists **and** no `.atomic-bak` | Swap never started, or crashed before step 1. Old bundle untouched. | Delete the stale staging dir(s); next `promote_atomic()` run starts fresh. |
| STATE_B | `merged/` absent **and** `.atomic-bak` exists | Crashed between steps 1 and 2. | Rename `.atomic-bak/` → `merged/` (restores last known good), delete any stale staging dir(s). |
| STATE_C | `merged/` exists **and** `.atomic-bak` exists | Both renames completed; only cleanup (step 4) is pending. | Verify `merged/bundle_manifest.json` is `COMPLETE`, then delete `.atomic-bak/`. |
| AMBIGUOUS | `merged/`, `.atomic-bak`, **and** `.staging.*` all present | Should be unreachable (`promote_atomic()` refuses to start a new swap while `.atomic-bak` exists) | **Refuses to guess.** Inspect manually. |

STATE_C additionally **refuses** to delete `.atomic-bak/` if `merged/bundle_manifest.json`
is missing, unreadable, or not `status: COMPLETE` — evidence is never destroyed when it
can't be verified as safe to discard.

## Manual CLI

```bash
# Inspect only, never mutates:
python scripts/pipeline/commands/ops/promote_recover.py {family} {platform} --dry-run

# Detect and correct:
python scripts/pipeline/commands/ops/promote_recover.py {family} {platform}
```

Exit code `0` = healthy or successfully recovered; `1` = refused (AMBIGUOUS, or a
STATE_C verification failure) — read the printed `ACTION:` line and inspect the
product's `knowledge/{family}/{platform}/` directory by hand.

## Why `merged.atomic-bak`, not `merged.bak`

`refresh_knowledge.py` already uses `merged.bak/` for its own, unrelated purpose (a
copy-based backup it takes before the scout→enrich→promote→index chain runs, used
purely to compute a semantic delta after promote succeeds — see `_backup_merged`/
`_cleanup_bak`). Both directories can legitimately coexist during a single refresh
run. Reusing the same name caused a real collision found live during the T12 pilot
(promote_atomic() saw refresh_knowledge.py's own `merged.bak/` and refused, treating
it as STATE_C from an unrelated legacy directory with no `bundle_manifest.json`) —
`merged.atomic-bak` is a distinct name specifically to avoid this.

## Portability

`os.rename()` is atomic for same-volume renames of both files and directories on
POSIX **and** on Windows (NTFS) — there is no real platform difference to branch on.
The actual risk on any OS is **transient handle contention** (AV scanners, search
indexers, backup agents holding a brief open handle — more common on Windows but not
exclusive to it), which is why both renames go through the same retry-with-backoff
loop `core/fs.py`'s `atomic_write()` already uses in production (5 attempts, 0.2s ×
attempt backoff), rather than an OS-conditional branch. This was verified against a
real Windows filesystem during development (not just mocked) — see
`test_promote_atomic.py`.

## Known residual gap (documented, not silently ignored)

`refresh_knowledge.py`'s own direct field writes to `merged/model.yaml`
(`previous_repo_sha` before the chain runs, `enrichment_status` after) happen
**outside** the atomic swap boundary — they mutate the real `merged/model.yaml`
directly, not through `promote_atomic()`'s staging. This is pre-existing behavior
(not introduced by FRESH-001) and is low-risk (informational/metadata fields, not the
authoritative `repo_sha` that gates freshness), but it means the atomicity guarantee
does not cover 100% of every write path into `merged/model.yaml` — only the fields
`promote.py` itself writes. Flagged here rather than silently claimed as fully closed.
