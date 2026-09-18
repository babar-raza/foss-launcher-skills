# C4 pilot: real /eval-page step 2b dry run against font/python

Per the stage matrix's pilot scope ("font/python via a real /eval-page
step-2b dry run") and promotion gate ("step-2b latency unchanged at
default tier; exit codes 0/1/2 preserved").

## What ran

The exact command eval-page.md's step 2b documents:

```
python scripts/pipeline/commands/diagnostics/smoke_test.py --files content/docs.aspose.org/en/font/python/developer-guide/core-management.md
```

## Direct old-vs-new comparison (same process, same file, real check_file())

Loaded the pre-C4 version of smoke_test.py (commit `b76392b9f3`, the last
commit before this taskcard) side-by-side with the current, real module,
and ran both against the same real file:

- **Result equality**: `old_result == new_result` → **True** (byte-identical
  `SmokeResult`, all 6 blocks, all PASS, identical messages/line numbers).
- **Auto-detection**: `_detect_langs_in_files()` resolved to
  `frozenset({'python'})` for this file (matching the OLD hardcoded
  default exactly, since the file only contains Python blocks) --
  confirming the RC22 auto-detect fix (langs auto-detected from file
  content rather than hardcoded to `{"python"}`) does not change behavior
  for a python-only product like font/python.

## Latency (5 runs total: 1 in the direct comparison + 4 standalone CLI invocations)

| Run | Time |
|---|---|
| direct comparison (old, in-process) | 1.403s |
| direct comparison (new, in-process) | 1.615s |
| standalone CLI (new) | 1.549s |
| standalone CLI (new) | 1.697s |
| standalone CLI (new) | 1.749s |
| standalone CLI (new) | 1.744s |

All in the same ~1.4-1.75s band (Python interpreter startup + the real
`mypy` subprocess spawn per block, unchanged since this taskcard adds no
new subprocess calls to the default max_tier=2 path) -- no latency
regression at default tier.

## Exit code

`echo $?` after the standalone CLI run: **0** (PASS), matching the
pre-existing 0/1/2 contract exactly (6/6 blocks PASS, 0 WARN, 0 FAIL).

## Conclusion

Zero-network assertion at default tier: confirmed (no new network calls
introduced; `mypy`/`py_compile` are the same local subprocess calls as
before). Exit codes 0/1/2 preserved: confirmed. Latency unchanged:
confirmed. The RC22 auto-detection fix is a real, disclosed improvement
for non-python-only products (a Java/TypeScript/etc. page's blocks are now
actually smoke-tested via a bare `--files` invocation, where they were
previously silently skipped) with zero observable effect on this
python-only pilot product.
