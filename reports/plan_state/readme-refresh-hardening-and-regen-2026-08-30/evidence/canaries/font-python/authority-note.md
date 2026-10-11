# font/python — publication-authority note (TC-27b, manual substitute for TC-16)

**Status**: NOT PUSHED. Will never be pushed by this mission. This note exists because
`push()`'s code-level `target_authority` classifier (TC-16) was not built this pass
(Hardening Track B, deferred) — the refusal recorded here is enforced by hard rule 1
of this loop's own operating instructions and by AGENTS.md's human-authority-boundary
convention, not by classifier code. This is an explicit, disclosed downgrade from the
original mission acceptance criterion ("push refused as `target_authority: mirror`"),
not an equivalent satisfaction of it.

## Live-verified mirror signals (2026-08-31, re-confirmed at TC-27b execution time)

- `runs/.clone_cache/aspose_font_python` HEAD: `c6d820937a37eae3131ad2f4efdef0a2b15edbc3`
- HEAD has **zero parents** (`git log -1 --format=%P` → empty) — a synthetic root commit,
  not an organic commit reached by normal development history.
- The repository contains **12 distinct zero-parent root commits**
  (`git rev-list --max-parents=0 --all` → 12 lines) — twelve separate points where history
  was replaced wholesale, not once but repeatedly, over the product's lifetime.
- The previously-merged README PR (`#7971880`, merged 2026-08-15) is **absent from the
  current history entirely** — a real, merged change was wiped by a subsequent history
  rewrite, not superseded by a newer edit.
- `resolve_baseline('font','python')` → SHA `136b6e20c3916ac4c8efac0714948a4136b491a3`,
  which is **not an ancestor of HEAD** (`git merge-base --is-ancestor` exit 1) yet its
  tree (`75a0b491ae...`) is **byte-identical** to HEAD's tree — the repo's *content*
  is stable; only its *commit history* is being discarded and rebuilt on a cadence,
  the signature behavior of a canonical-repo → mirror resync (e.g. GitLab canonical,
  GitHub as a periodically-resynced mirror), not organic force-pushes/rebases.

## Conclusion

These signals are consistent with `font/python`'s GitHub repository being a **mirror**,
not the canonical source, of the real upstream project. A canonical-vs-mirror
determination for the *upstream GitLab* side (does it exist, is it reachable, is it the
true source of truth) was never independently verified this session — the evidence
above is inferred from repository-shape signals only (RC's own "Missing evidence /
unknowns" section already flagged this as unresolved). Combined with hard rule 1
(never push font/python, full stop, no exception this loop can grant), this candidate
will remain **local-only**.

## Freshness mechanism — the actual, code-demonstrated half of this criterion

Unlike the push-refusal half above, this half **was** code-demonstrated, not asserted:

```
$ check_freshness('font', 'python', mode='degraded')
state:  HISTORY_REWRITTEN_CONTENT_IDENTICAL
reason: baseline commit 136b6e20c3 is unreachable from the clone-cache HEAD, but its
        live (object still present, not yet garbage-collected) tree SHA (75a0b491ae)
        matches the tree SHA now at HEAD -- a content-identical history rewrite
        (e.g. a GitLab-canonical -> GitHub-mirror resync), not real staleness
```

This required a real, live bug fix (TC-36 — `git_reachable()` tested object existence
via `cat-file -e`, not ancestry via `merge-base --is-ancestor`; the dangling orphan
object was still present in the local clone cache, so the old check silently reported
it "reachable" and the state resolved to `CURRENT`, not `HISTORY_REWRITTEN_CONTENT_
IDENTICAL`) — see `taskcards.jsonl` TC-36 and commit `68200a0662396fb492abf7a97995123b36633db7`
for the full root-cause writeup. Re-verified against `slides/python` in the same pass:
`STALE_ORPHANED` (genuine content drift), proving the falsifiable "one mechanism, two
opposite correct answers" acceptance test genuinely holds against the real repositories.
