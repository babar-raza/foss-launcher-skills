# Stale-guard soak graduation criteria (TC-SG-07 / R-04)

Status: Current
Audience: Operator
Canonical prior location (not durable — kept for provenance only): `C:\Users\prora\.claude\plans\plan-based-on-above-foamy-hartmanis.md`
(outside the repo) and gitignored `backlog/REMINDERS.md` (reminder R-04). Copied into the repo per MT069 card
HC-10, 2026-09-23, because a decision this consequential should not live only in an external file and a
gitignored reminder.

## What this is

The 2026-08-30 stale-guard redesign (mission `MT058-2026-08-31-STALE-GUARD-WINDOW-IDENTITY-ENCODING`) landed
its window/identity/encoding fixes with two things deliberately soft-launched rather than immediately
blocking, so a real incident during the soak could be triaged instead of breaking every commit on day one.
This file is the durable record of what must be true before each is flipped from advisory to blocking.

## Flip surfaces and current status (re-verified live, 2026-09-23)

| # | Surface | Current state | Flip target |
|---|---|---|---|
| (a) | `--wide-findings` default in `check_stale_file_regression.py` and `git_plumb_commit.py` | `warn` (confirmed: `default="warn"` in both, 2026-09-23) | `block` |
| (b) | `skill-governance.yml`'s Windows leg `continue-on-error` | **Moot.** The leg no longer exists in the private workflow — it moved permanently to the public repo (`Aspose/aspose.org-workflows`, MT069 HC-21, 2026-09-19). A public workflow cannot block a private push. See "What graduation means now" below. | — (superseded) |
| (c) | `content/` keeps the session-base window (D-A(ii) suppression) in `stale_file_regression.py`, pending a measured `content/` replay | Still in effect (`plan D-A(ii)` referenced at `stale_file_regression.py:404,459`) | Wide window extended to `content/` once replayed |
| (d) | `PYTHONUTF8=1` in `scripts/pre-commit-audit.sh` and `scripts/ci/hooks/find_python.sh` | Not set (confirmed: no `PYTHONUTF8` in either file, 2026-09-23) | Set in both |
| (e) | T10 docs (`skills/commit.md` + mirrors, `CLAUDE.md` plumbing section) | Not updated for the new window/identity semantics | Updated |
| — | TC-SG-21 closeout exercise | Not run | Run once (a)–(e) land |

**Stop rule (unconditional):** if any unresolved lookback-class false positive has been seen in Step 34 /
plumb `WARN` output since the soak began (2026-08-30), **do not flip** — fix the false positive first,
re-baseline the soak clock.

## Preconditions, and where they actually stand

The original two preconditions (R-04):

1. **No unresolved lookback-class false positive seen in Step 34/plumb `WARN` output since 2026-08-30.**
   Status: **not independently re-verified** — no dated log of Step 34/plumb WARN output was found when this
   was last checked (2026-09-18). This still needs an operator or agent to actually search for one before
   the flip, not be assumed clean by silence.
2. **`skill-governance.yml` green at the workflow level, on a run that post-dates the `TC-14` fix
   (`d795f669e6`, 2026-09-18).** Status: **met.** Run `35444938440` (2026-09-19, MT069 HC-02 stage 2b) was a
   full workflow-level `success` — 1,700 passed / 45 skipped / 0 failed, post-`TC-14` — the first passing
   run of this workflow since 2026-09-06. `skill-governance.yml` (now a single self-hosted Linux job, no
   Windows leg) has additionally been **enabled persistently** since 2026-09-23 (MT069 H22), so it is now
   getting real, ongoing production runs rather than one proof run.

## What graduation means now (superseding the original "flip governance-tests-windows" framing)

Since (b) is moot, "graduated" for the Windows-defect-class coverage now means: **the public
`governance-tests-windows.yml` leg is green across a real soak, and its alert issue (`windows-governance-red`
on `Aspose/aspose.org-workflows`) stays closed** — not a `continue-on-error` flip on a job that no longer
exists privately. For the private-repo surfaces (a), (c), (d), the soak clock is best measured from
**2026-09-23**, the day `skill-governance.yml` started taking real, continuous production traffic again
(precondition 2 was satisfied that same window) — not from 2026-08-30, which predates the multi-day gap
where the workflow was disabled and produced zero real signal. Two weeks from 2026-09-23 is **2026-10-07**.

## Before flipping (a), (c), (d)

1. Search for any lookback-class `WARN` in Step 34/plumb output since 2026-08-30 (precondition 1) — do not
   assume clean.
2. Confirm ≥2 weeks of real, triaged `skill-governance.yml` production runs from 2026-09-23 with no
   unresolved false positive (target: 2026-10-07).
3. Confirm the public `governance-tests-windows.yml` leg has stayed green (or every red was triaged and
   closed) across the same window.
4. Land (a), (c), (d), (e) and the TC-SG-21 closeout exercise **in one commit** (per the original design —
   flipping surfaces independently reintroduces exactly the "two numbering schemes for the same thing"
   class of bug this redesign exists to prevent).
5. Update this file and close R-04 with the flip commit SHA.
