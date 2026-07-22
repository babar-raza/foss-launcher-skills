# core/ — Shared Infrastructure

Utility modules shared across all pipeline scripts. No circular dependencies — these modules import only from the standard library.

## Modules

### fs.py — Atomic Filesystem Operations

Crash-safe file writes via a write-to-tmp + `os.replace()` pattern.

| Function | Signature | Description |
|----------|-----------|-------------|
| `atomic_write` | `(path: Path, content: str, encoding: str = "utf-8") -> None` | Write content atomically; temp file cleaned up on failure |
| `file_hash` | `(path: Path) -> str` | 16-hex-char fingerprint based on size + mtime_ns; for change detection only |

```python
from core.fs import atomic_write, file_hash

atomic_write(Path("knowledge/3d/python/merged/model.yaml"), yaml_text)
stamp = file_hash(Path("knowledge/3d/python/merged/claims.json"))
```

### manifest.py — Pipeline Step Completion Tracking

Manages `.pipeline_state.json` per product to record which pipeline steps have completed. Lets downstream steps detect partial runs and skip already-processed products.

| Function | Signature | Description |
|----------|-----------|-------------|
| `write_step_manifest` | `(state_path, step, metadata, *, success=True) -> None` | Record step completion atomically |
| `check_step_complete` | `(state_path, step) -> bool` | Return True if step has a successful record |
| `get_step_metadata` | `(state_path, step) -> dict` | Return metadata dict for the step, or `{}` |

State file location: `knowledge/{family}/{platform}/.pipeline_state.json`

```python
from core.manifest import write_step_manifest, check_step_complete

state_path = Path("knowledge/3d/python/.pipeline_state.json")

# After scout.py completes:
write_step_manifest(state_path, "scout", {"repo_sha": sha, "class_count": 42})

# Before merge.py runs:
if check_step_complete(state_path, "scout"):
    print("scout already done, proceeding to merge")
```

### clone_cache.py — FOSS Repo Clone Lifecycle

Manages shallow git clones of FOSS source repos stored at `runs/.clone_cache/`. Reads `clone_url` from `data/products.json` for auto-cloning.

| Function | Signature | Description |
|----------|-----------|-------------|
| `cache_root` | `() -> Path` | Resolved cache directory; respects `ASPOSE_CLONE_CACHE` env var |
| `clone_path` | `(family, platform) -> Path` | Expected clone directory (`cache_root/aspose_{family}_{platform}`) |
| `clone_exists` | `(family, platform) -> bool` | True if a valid `.git` directory is present |
| `clone_head_sha` | `(family, platform) -> str \| None` | HEAD commit SHA, or None if clone is missing |
| `ensure_clone` | `(family, platform) -> Path` | Ensure clone exists; auto-clones from GitHub if missing; raises `RuntimeError` on failure |

```python
from core.clone_cache import cache_root, clone_path, ensure_clone

# Auto-clone if needed
repo = ensure_clone("3d", "python")  # raises RuntimeError if no clone_url

# Check manually
if clone_exists("3d", "python"):
    sha = clone_head_sha("3d", "python")
```

Environment override: set `ASPOSE_CLONE_CACHE=/path/to/cache` to use an alternate pre-populated cache (CI, shared NFS, etc.).

### constants.py — Shared Constants

All shared values used across pipeline modules. Import from here rather than redefining.

| Constant | Type | Value / Description |
|----------|------|---------------------|
| `KNOWLEDGE_ROOT` | `Path` | `Path("knowledge")` — relative to CWD / repo root |
| `CONTENT_ROOT` | `Path` | `Path("content")` |
| `AUDIT_REPORTS_DIR` | `Path` | `Path("reports/audit")` |
| `CONTENT_EVAL_REPORTS_DIR` | `Path` | `Path("reports/content_eval")` |
| `REMEDIATION_REPORTS_DIR` | `Path` | `Path("reports/remediation")` |
| `SITE_PATHS` | `list[tuple]` | Per-site content path templates |
| `LOCALE_RE` | `re.Pattern` | Regex matching translated file suffixes (`.ar.md`, `.de.md`, etc.) |
| `_TEST_PATH_PATTERNS` | `tuple` | File path fragments identifying test code |
| `_INTERNAL_PATH_PATTERNS` | `tuple` | File path fragments identifying private/internal code |
| `DUAL_OVERLAP_THRESHOLD` | `float` | `0.8` — Jaccard threshold for scout+FL dual-source match |
| `QUALITY_TREND_MAX_ENTRIES` | `int` | `180` — Entries retained in quality_trend.jsonl |

`MAX_FILES`/`MAX_SNIPPETS` do **not** live here — a duplicate, unused pair was
removed from this module (2026-07-22, HARDEN-words-net) after it drifted out
of sync with the real, active values in `extraction/tree_helpers.py::MAX_FILES`
and `extraction/scout.py::MAX_SNIPPETS`. See those modules for the current
scout-extraction limits.

```python
from core.constants import KNOWLEDGE_ROOT, DUAL_OVERLAP_THRESHOLD
```

## Notes

- `KNOWLEDGE_ROOT` is relative to CWD. All pipeline scripts must be run from the repo root.
- `clone_cache.py` does not depend on foss-launcher; clones are self-contained inside this repo.
- `manifest.py` uses `atomic_write` from `fs.py` internally; do not import `fs.py` directly from `manifest.py` callers.
