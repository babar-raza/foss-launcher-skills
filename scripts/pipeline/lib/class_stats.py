"""Single source of truth for "how many classes does this product have."

Extracted (MT067-2026-09-10, TC-01) after a portfolio scan found four independently-computed,
non-namespaced "class_count" formulas scattered across ``extraction/outputs.py``,
``commands/knowledge/scout.py``, ``commands/knowledge/promote.py``, ``commands/knowledge/index.py``,
and ``commands/launch/site_planner.py`` -- all writing a field literally named ``class_count`` (or
labeled "Classes") under genuinely different definitions, with zero reconciliation between them.
On barcode/python this produced three simultaneously-true, differently-scoped numbers (26 / 79 /
146) depending which artifact was read; a portfolio-wide rescan found the same mechanism live on
15 of 32 launched products. See ``knowledge-stats.md`` (docs/reference/) for the full taxonomy.

Three distinct concepts previously shared one overloaded field name; each now has its own name:

- ``total_declared`` -- every class-kind entry extracted from source (``kind != "function"``).
  Matches the pre-existing "TC-SYS-015" formula in ``outputs.py``/``promote.py``. An extraction
  completeness/QA metric -- includes private, internal, test-file, and duplicate-namespace entries.
- ``public_documented`` -- the name-deduplicated subset that is public, non-test, non-internal
  (or explicitly re-exported via package ``__init__``). Matches the pre-existing filter in
  ``index.py``'s ``_is_public_api_entry`` + ``set()``-based name dedup. The number relevant to
  content-generation sizing and documentation scope.
- ``raw_entries_including_non_class`` -- ``len(api_surface)``, i.e. every entry regardless of
  kind, functions included. Previously silently reused as "Classes" in ``merge_report.md`` (a
  labeling bug, not a legitimate third definition) and as the real (correct, but mislabeled)
  sizing input in ``site_planner.py``.

A single bug in this module now propagates uniformly to every artifact and every product instead
of being scattered -- that trade is deliberate (see docs/reference/knowledge-stats.md's "Risks"
section), which is why ``test_class_stats.py`` asserts structural invariants, not just examples.
"""

from __future__ import annotations

from core.constants import _INTERNAL_PATH_PATTERNS, _TEST_PATH_PATTERNS


def is_public_api_entry(entry: dict) -> bool:
    """Return True if *entry* represents a developer-visible public API class.

    Excludes free functions, private (``_``-prefixed) names, test-file entries, and internal
    implementation-directory entries. An entry whose scout data marked it
    ``exported_via_package_init`` is public regardless of its physical file path -- this handles
    packages (e.g. barcode-foss) that implement classes under ``_internal/`` and re-export them
    via ``__init__.py.__all__``.

    Moved here from ``commands/knowledge/index.py``'s former ``_is_public_api_entry`` (identical
    behavior) so every caller shares one implementation instead of a second, divergent copy.
    """
    if not isinstance(entry, dict):
        return False
    if entry.get("kind") == "function":
        return False
    name = entry.get("name", "")
    if not name or name.startswith("_"):
        return False
    file = entry.get("file", "")
    if any(pat in file for pat in _TEST_PATH_PATTERNS):
        return False
    if entry.get("exported_via_package_init"):
        return True
    if any(pat in file for pat in _INTERNAL_PATH_PATTERNS):
        return False
    return True


def compute_class_stats(api_surface: list[dict]) -> dict:
    """Compute the three namespaced class-count statistics for one product's ``api_surface.json``.

    *api_surface* is the parsed JSON list as loaded from ``scout/api_surface.json`` or
    ``merged/api_surface.json`` (both have identical schema and entry count -- ``promote.py``
    copies the list verbatim). Pure function: no I/O, no randomness, deterministic given the
    same input list -- the entire class of "why did this change on rerun" bugs this module
    replaces was never actually a rerun-nondeterminism problem, only a cross-artifact
    definitional one (see docs/reference/knowledge-stats.md).
    """
    if not isinstance(api_surface, list):
        return {"total_declared": 0, "public_documented": 0, "raw_entries_including_non_class": 0}

    total_declared = sum(1 for c in api_surface if isinstance(c, dict) and c.get("kind") != "function")
    public_entries = [c for c in api_surface if is_public_api_entry(c)]
    public_documented = len({c["name"] for c in public_entries if "name" in c})
    raw_entries_including_non_class = len(api_surface)

    return {
        "total_declared": total_declared,
        "public_documented": public_documented,
        "raw_entries_including_non_class": raw_entries_including_non_class,
    }
