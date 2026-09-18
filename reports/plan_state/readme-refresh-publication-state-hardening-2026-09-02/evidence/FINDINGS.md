
## Published 2026-09-03T07:12:50Z (user instruction: "create and merge pr for 3d/python on destination repo without touching anything else")

- approve (note records the instruction + COMPARISON.html numbers; publication re-probed with
  no drift) -> push --dry-run (declared_files = ["README.md"], target_authority "canonical") ->
  live push -> PR #3 https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-Python/pull/3
  (branch readme-refresh/2026-09-03, head 158f2eea, 1 commit, 1 file, +601/-243).
- Independent pre-merge proof: PR README bytes == candidate bytes modulo CRLF;
  compare master...branch files == ["README.md"].
- gh pr merge --squash --delete-branch -> merge commit 65b1f577c0f16d0d9112bb6c1153d3024543ac02,
  branch 404 afterwards; live master README == candidate modulo CRLF; merge commit touches
  README.md only.
- verify -> pr_state MERGED (run stays PUSHED, terminal). reconcile-publications --apply ->
  IN_SYNC row (published_commit 65b1f577c0). clone cache d9f3bfe -> 65b1f577c0 via
  core.clone_cache.update_clone.
- Ledger commit 03854f7616 (data/readme_published_state.json only).
- Mission CLOSED: publication is a live-probed fact end to end, 3d/python regenerated and
  published through it, 3 real defects surfaced upstream (never README content).
