# Upstream Issues — cells/python

Genuine defects found in the real upstream repository (`runs/.clone_cache/aspose_cells_python/`)
during clean-room composition/verification.

## 1. The old README's own repo/issue links point to a stale repository name

`README.md`'s Documentation and Support sections link to a GitHub repository path using an
all-lowercase, undecorated project-name style with no FOSS-suffix segment. The knowledge
pipeline's own pinned, verified source of truth for this product (`knowledge/cells/python/
merged/model.yaml`'s `repo_url` field) uses the same title-cased, FOSS-suffixed naming
convention as every other real cells-family sibling repo (confirmed via each sibling's own
`model.yaml`). The old README's links use a different, likely superseded repository name. The
new candidate uses the real, current, pipeline-verified repository path for every GitHub link
and badge.

## 2. The old README's own License link has a case mismatch

`README.md`'s License section links to `License/license.txt` (lowercase filename). The real file
on disk is `License/LICENSE.txt` (uppercase) — confirmed via direct directory listing of
`runs/.clone_cache/aspose_cells_python/License/`. Not BLOCKING (case-insensitive filesystems —
Windows, macOS default — resolve it anyway), but would 404 on a case-sensitive Linux checkout or
a raw GitHub content link. The new candidate's License section links to the real, correctly-cased
`License/LICENSE.txt`.

## 3. Knowledge-pipeline version baseline is behind the checked-out clone cache

`knowledge/cells/python/merged/model.yaml` pins this product's extraction at `version: 26.3.1`
(`repo_sha: 5b5b28eb372c28f4529928ea81696a0031b68d60`), but the clone cache's own current
`pyproject.toml` declares `version = "26.7.0"`. This is a knowledge-staleness signal (the
checked-out clone cache has moved past the last `repo-scout` baseline), not a README wording
defect in either candidate — flagged for a `knowledge-diff`/`knowledge-update` follow-up rather
than "fixed" by hand-picking a version number in the new candidate's Installation section (which
deliberately cites no specific version, matching the plain `pip install aspose-cells-foss` form
that doesn't need one).
