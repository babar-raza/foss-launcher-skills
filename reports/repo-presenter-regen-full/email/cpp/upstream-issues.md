# Upstream Issues — email/cpp

Verified during clean-room composition of `reports/repo-presenter-regen-full/email/cpp/readme.md`
against the real upstream repo (`runs/.clone_cache/aspose_email_cpp/`, pinned SHA
`c7252b3e4f6bbec4bbe5e2f50f51eb2a7384eaf2` per `knowledge/email/cpp/merged/model.yaml`).

## Stale examples directory path in the old README

- **Severity**: INFORMATIONAL
- **Evidence**: the old upstream README's "Examples" section says runnable examples live under a
  `cpp/`-prefixed subdirectory. The real, on-disk repo root has no such prefix directory at all —
  the examples directory sits directly at the repo root, as a sibling of the library's headers and
  sources (confirmed by a direct listing of the clone cache root). The three named example files
  are real and exist exactly where the old README says, just one path segment shallower than
  claimed.
- **Impact**: a reader following the old README's literal path would not find the directory;
  finding the real, correctly-shallower path takes only a moment of looking around the repo root,
  so this never blocks anyone.
- **Not fixable here because**: this is a leftover from what looks like an earlier monorepo layout
  (a language-named package folder inside a multi-language superrepo) that was never updated after
  this became its own standalone repo — a real upstream inconsistency, not something a README edit
  changes at the source. The new candidate uses the real, verified path throughout instead of
  repeating the stale one.

## No other issues found

No blocking build/install command, no broken code example, and no other factual inaccuracy was
found in the old README or the repo's other documentation/build files. The old README's build/test
commands match the repo's own CMake presets exactly and are reused verbatim in the new candidate.
