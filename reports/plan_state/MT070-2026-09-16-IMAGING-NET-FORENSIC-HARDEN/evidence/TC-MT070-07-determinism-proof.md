# TC-MT070-07: Determinism / no-op regeneration proof

**Method**: ran `scripts/pipeline/commands/knowledge/scout.py imaging net
runs/.clone_cache/aspose_imaging_net {scratch}` (the real S-34 repo-scout backing
script, invoked exactly as its own `SKILL.md` documents) twice, into two separate
isolated scratch directories (`mktemp -d`, never touching the live `knowledge/`
tree), against the same pinned clone (`f2cf68fd64545bfb704c45ee756af3125103fd74`,
unchanged, clean working tree, confirmed before and after).

**Result — byte-identical across all three copies** (two fresh runs + the tracked,
committed `knowledge/imaging/net/scout/` snapshot from the original 2026-09-11
launch), for every artifact:

| Artifact | Run 1 vs Run 2 | Run 1 vs tracked | Notes |
|---|---|---|---|
| `api_surface.json` | identical | identical | 3 entries, all runs |
| `formats.json` | identical | identical | 12 entries (11 formats + Unknown) |
| `class_graph.json` | identical | identical | 0 edges, all runs |
| `coverage_matrix.json` | identical | identical | |
| `limitations.md` | identical | identical | 0 entries, all runs |
| `install.md` | identical | identical | |
| `claims.json` | **content identical** | **content identical** | only `extracted_at` (wall-clock generation timestamp) differs — expected, not content drift |
| `model.yaml` | **content identical** | **content identical** | only `extracted_at` differs, same as above |

Both fresh runs logged identical extraction stats: `Scanning 17 source files`,
`Extracted 50 function-level snippets`, `api_surface.json (3 entries)`,
`claims.json (60 claims, source_sha=f2cf68fd)`, `formats.json (12 formats)`,
`scout_report.json (attempted=17, parsed=17, skipped=0, parse_errors=0)`.

**Conclusion**: extraction for imaging/net is fully deterministic against a pinned
source revision — no nondeterministic filesystem traversal, no cache-key drift, no
ordering instability, no partial-write artifact. Combined with the batch_reference.py
run-log evidence already on record for both the original launch and the H7 relaunch
(`Candidates: 3, Generated: 3, Errors: 0` in both cases — see MT068's own evidence and
TC-MT070-01), this closes the mission brief's "regeneration caused the page count to
change slightly" concern for imaging/net specifically: neither the extraction stage
nor the reference-generation stage exhibits any instability for this product. Whatever
prompted the original "count changed slightly" observation did not reproduce here
under a controlled, isolated, twice-repeated extraction.

**Artifacts**: this file. Scratch directories discarded after comparison (never
written into any tracked path).
