# Real defect found live by TC-03's tier-3 dispatch (ahead of the TC-09 sweep)

**Date:** 2026-09-23
**How found:** manual spot-check of TC-03's new `smoke_test.py --max-tier 3` real-execution
path against a real product, before the full portfolio sweep (TC-09) runs.
**Command:** `smoke_test.py cells go --files content/docs.aspose.org/en/cells/go/developer-guide/features.md --max-tier 3 --json`
**Confirmed NOT a runner bug:** the same command against
`content/docs.aspose.org/en/pdf/go/getting-started/installation.md` (a different product,
same runner, same code path) returned a clean real PASS. The go runner and its acquire/build/
execute path are working correctly; this is a real defect in either the cells/go example or
the underlying `aspose-cells-foss` Go library.

## Finding

`content/docs.aspose.org/en/cells/go/developer-guide/features.md` (starting at line 157):
block 1 panics at real execution:

```
panic: runtime error: invalid memory address or nil pointer dereference
[signal 0xc0000005 code=0x0 addr=0x58 pc=0x7ff678ee8412]

goroutine 1 [running]:
github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Go/v26/aspose/cells_foss.(*Cell).SetStyle(...)
	.../runs/.clone_cache/aspose_cells_go/aspose/cells_foss/cell.go:30 +0x12
main.main()
	.../main.go:24 +0x4b6
exit status 2
```

Blocks 2-5 (lines 185/209/226/242, same page) all report `DEPENDS-ON-FAILED-BLOCK` because
they chain-continue from block 1's failure -- so this single root cause accounts for all 5
FAILs on this page, not 5 independent defects.

## Not fixed here

Out of TC-03's scope (`content/` is not in its allowed_paths; content edits require `/manual-edit`
S-73). Queued for TC-10 (fix real defects found by the sweep) or an earlier ad hoc S-73 fix if
the user wants it addressed sooner. Root cause needs a real diagnosis pass first: read
`cell.go:30`'s `SetStyle` implementation and the example's own call sequence to determine
whether the example is missing a required initialization step (most likely, given every other
Go example on this page's own family works) or whether the library itself has a real nil-deref
bug that needs an upstream-issue filing (per the `production-localization-incident`/upstream-issue
workflow this repo already has for genuine library defects).
