# font/python candidate -- live execution proof (2026-09-02)

Scratch dir with the repository's own fixture fonts (`testdata/Roboto-VariableFont_wdth,wght.ttf`,
`testdata/Fonts/Roboto-Regular.ttf` also copied as `Roboto.ttf`), `PYTHONPATH` = clone-cache `src/`
(tree `75a0b491`, Release 26.8.4).

- Python: every ```python block of the candidate executed in order (fresh namespace per
  import-led block, continuation fragments inherit the previous namespace): **20 ok, 0 failed**.
  Before the c0005 correction the old README's own "release-safe static instance" example failed
  with `ValueError: could not convert string to float: 'Bold'` (see upstream-issues.md).
- CLI: every `aspose-font ...` line inside ```bash blocks run through the real
  `aspose_font.cli:main` entry point: **42 ok, 0 failed** (all 39 real subcommands' flags were
  also checked statically against the argparse definitions: 0 unknown flags).
- `verify-examples --python-runner` (run rr-20260902T104838Z-d00e617b6702) reports 20
  RUNTIME-ERROR / 17 TOOLCHAIN-UNAVAILABLE because the v1 runner stages no fixture fonts and
  runs continuation fragments in isolation -- a disclosed runner limit, not a candidate defect
  (no UPSTREAM-BROKEN: the package imports cleanly, unlike tex/python).

## Update 2026-09-02 (ST-171 / ST-172 fixed, not filed)

The runner limit above is no longer a limit. `verify-examples --python-runner` on the SAME run
(`rr-20260902T104838Z-d00e617b6702`, re-verified in place from AWAITING_REVIEW -- a third gap of
the same family closed the same day: the verb used to be reachable only from VERIFYING_EXAMPLES)
now records `runner: python_verification_runner_v2`:

- first v2 pass (candidate unchanged): 23 COMPILED+RAN CLEAN / 8 NOT-A-PRODUCT-COMMAND /
  5 TOOLCHAIN-UNAVAILABLE / 1 FIXTURE-UNAVAILABLE (`aspose-font info Roboto.ttf` -- `Roboto.ttf`
  exists nowhere in the tree; the file the scratch run above had staged under that name was a
  hand-made copy). 0 RUNTIME-ERROR. `verify-examples.runner-v2.result.json`.
- candidate edit: the three general-inspection CLI lines now name the real fixture
  `Roboto-Regular.ttf` (every Python example already did). The change was CAUGHT by
  `structural_unit_disposition_text_diff` (s0002) and `code_example_disposition_text_diff`
  (c0018a) -- both relabelled `corrected` in `facts/build_ledgers.py` with the reason recorded.
- gate bug found by that relabel and fixed in `readme_refresh_checks.py`: the content and
  structural coverage gates treated `corrected` as `excluded` (demanded a fake
  `excluded_reason`, never validated `target_section`) since MT041 added the enum value;
  u0036 here and 9 entries across 3d/java, 3d/net, pdf/java, words/python carried the
  workaround -- all migrated to `correction_reason`. Portfolio audit after the fix:
  23 clean / 8 dirty, identical set to before (`audit-portfolio.after-st171-st172.json`).
- final v2 pass: **24 COMPILED+RAN CLEAN / 8 NOT-A-PRODUCT-COMMAND / 5 TOOLCHAIN-UNAVAILABLE**,
  0 RUNTIME-ERROR, 0 FIXTURE-UNAVAILABLE; 42 product CLI lines executed, 0 failed
  (`verify-examples.runner-v2.final.result.json`). `recheck` -> 0 hard-gate findings
  (`regen.recheck-3.post-roboto-fix.result.json`); `cli_subcommand_coverage` (ST-172, new
  advisory) = [] on this candidate and reproduces exactly the 17 dropped subcommands when run
  against the pre-regeneration candidate.

State: AWAITING_REVIEW (unchanged; publication still undecided -- mirror target).

## Published 2026-09-02T13:28:18Z (user instruction: "create and merge a pr ... without touching anything else")

- approve (note records the instruction + COMPARISON.html numbers) -> push --dry-run (declared_files
  = ["README.md"]) -> live push with --acknowledge-mirror-target -> PR #2
  https://github.com/aspose-font-foss/Aspose.Font-FOSS-for-Python/pull/2
  (branch readme-refresh/2026-09-02, head 8f268f87, 1 commit, 1 file, +726/-182).
- Independent pre-merge proof: PR README bytes == candidate bytes (54,227 B, sha256 7e0a6b78...),
  compare main...branch files == ["README.md"].
- gh pr merge --squash --delete-branch -> merge commit dcf9549a935158405e96b6c99c39730ffdf4ff50,
  branch 404 afterwards; main README == candidate byte-for-byte; merge commit touches README.md only.
- verify -> pr_state MERGED (run stays PUSHED, terminal). reconcile-publications --apply ->
  IN_SYNC row (published_commit dcf9549a). clone cache c6d8209 -> dcf9549 via core.clone_cache.update_clone.
- Ledger commit a8619a63ec (data/readme_published_state.json only).
- Standing caveat: mirror target; the next weekly re-snapshot may replace main wholesale.
