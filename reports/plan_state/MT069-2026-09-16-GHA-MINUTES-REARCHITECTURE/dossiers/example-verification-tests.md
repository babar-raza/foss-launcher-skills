# Dossier: example-verification-tests.yml

**CORRECTION (TC-12, MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION,
2026-09-24)**: this dossier's original text (below the line) described a workflow
that ran exactly ONE of the package's ~19 real test files
(`test_example_verification_code_fences.py`) on both jobs, and its own #12/#13
open question ("not yet confirmed whether the Windows leg tests anything
genuinely OS-sensitive... if not, demote it") is now answered: TC-12 pointed
this workflow at all ~19 files (RC7, MT072's own root-cause list) plus
`test_code_syntax_check.py` (TC-11 collapsed that evaluator's own loader onto
the shared one this package owns, so its regression coverage now belongs
here too), and added explicit toolchain setup (`actions/setup-java`,
`dtolnay/rust-toolchain`, `actions/setup-dotnet`, plus a `pip install cmake
ninja` step mirroring TC-13's own local-machine install) so those tests
actually exercise real per-language runners instead of degrading to
GRAMMAR-UNAVAILABLE/TOOLCHAIN-UNAVAILABLE on a bare runner image.
`test_example_verification_cpp.py` (real MSVC-backed C++ builds) now runs on
the Windows job ONLY -- MSVC cannot exist on Linux, so this is a genuine,
confirmed OS-sensitivity reason the dual-OS split must stay, reversing the
consolidation lean below. Real per-run duration will also be materially
higher than the #4 baseline (more test files, more setup steps, more real
compiles) -- the Sept usage figures below predate this change entirely and
should not be used to estimate the new workflow's cost; re-measure after
this change has run at least once.

**Original text below (2026-09-16/23), left for the historical record but
superseded by the correction above wherever it conflicts:**

**1. Identity/purpose**: Verifies published code examples compile/run correctly across
languages — protects content quality directly.
**2. Trigger**: `push(main)`/`pull_request`, identical 6-entry path filter (HP-08,
possibly dead PR trigger, unconfirmed). 2 independent jobs, ubuntu + windows, same test
target on both (deliberate cross-platform duplication per the file's own comments).
**3. Importance**: `P1_HIGH`.
**4. Usage**: windows 61 min/4.1% + linux 30 min/2.0% = 91 min/6.1% (Sept). Windows costs
more than Linux here too, consistent with `skill-governance.yml`'s pattern.
**5. Failure analysis**: 0% failure, both jobs, Sept and full history — fully healthy.
**6. Secrets/permissions**: `permissions:` absent/default. No `secrets.*`.
**7. Data classification**: push/PR-gated, needs native integration — private only.
**8. Runner**: ubuntu-latest + windows-latest, GitHub-hosted, no matrix (2 explicit
jobs).
**9-11. Options**: must stay private (native integration); self-hosting not warranted
(healthy, moderate cost, no reliability driver).
**12. Optimization/retirement — real lever here (SUPERSEDED, see correction above)**:
the dual-OS duplication (91 min combined) is a genuine, unresolved consolidation
target. Not yet confirmed whether the Windows leg tests anything genuinely
OS-sensitive (e.g., CRLF/path handling) — if not, demote it to schedule/dispatch like
`skill-governance.yml`'s own soft-launch pattern.
**13. Recommendation (SUPERSEDED, see correction above)**: `CONSOLIDATE_WITH_ANOTHER_WORKFLOW`
(confidence MEDIUM — the OS-sensitivity question is unverified, not the destination).
Now answered YES (real MSVC-only cpp builds) -- do not consolidate the Windows leg away.
**14. Rejected alternatives**: public/self-hosted migration (both structurally
unavailable/unwarranted).
**15. Expected savings (SUPERSEDED)**: up to ~61 min/month if the Windows leg is
demoted and proven unnecessary on every push — not confirmed, and now moot (see
correction above).
**16. Migration complexity**: LOW (a trigger change), contingent on the OS-sensitivity
verification.
**17. Risks**: demoting the Windows leg without confirming it's safe could silently drop
real OS-specific test coverage. (Confirmed real by TC-12 -- this risk would have
materialized.)
**18. Tests**: none run (design-only; the OS-sensitivity check itself wasn't performed
this taskcard).
**19. Rollback**: trivial — restore the original trigger if a regression is found.
**20. Evidence/confidence**: HIGH on cost; MEDIUM on the consolidation recommendation
pending the OS-sensitivity verification. (Verification now complete -- see correction.)
