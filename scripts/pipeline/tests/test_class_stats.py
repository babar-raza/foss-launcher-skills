"""Tests for lib/class_stats.py (MT067-2026-09-10, TC-01).

Covers both example-based behavior and structural invariants across generated fixtures — no
`hypothesis` dependency (this codebase deliberately has none anywhere, see
`tests/extraction/test_shared_reference_guard.py`'s own docstring). Invariants matter more than
usual here: consolidating four previously-independent, previously-disagreeing class-count formulas
into this one module means a bug here now propagates uniformly (and invisibly) to every artifact
for every product, instead of being scattered and eventually noticed by disagreement — see the
module docstring in `lib/class_stats.py` and `docs/reference/knowledge-stats.md`.
"""
from __future__ import annotations

import itertools

from lib.class_stats import compute_class_stats, is_public_api_entry


def _entry(name, kind="class_definition", file="pkg/mod.py", exported=False):
    return {"name": name, "kind": kind, "file": file, "exported_via_package_init": exported}


# ---------------------------------------------------------------------------
# is_public_api_entry — example-based, one case per exclusion rule
# ---------------------------------------------------------------------------

def test_public_entry_included():
    assert is_public_api_entry(_entry("Barcode")) is True


def test_function_kind_excluded():
    assert is_public_api_entry(_entry("build_registry", kind="function")) is False


def test_private_name_excluded():
    assert is_public_api_entry(_entry("_InternalHelper")) is False


def test_missing_name_excluded():
    assert is_public_api_entry({"kind": "class_definition", "file": "pkg/mod.py"}) is False


def test_test_path_excluded():
    assert is_public_api_entry(_entry("FixtureClass", file="tests/fixtures/mod.py")) is False
    assert is_public_api_entry(_entry("FixtureClass", file="pkg/test_mod.py")) is False


def test_internal_path_excluded_by_default():
    assert is_public_api_entry(_entry("SymbologyEncoder", file="pkg/_internal/encoders/base.py")) is False


def test_internal_path_included_when_exported_via_package_init():
    # PY-INIT-001 behavior, preserved from the original index.py filter: barcode-foss keeps
    # most implementation under _internal/ and re-exports a subset via __init__.py.__all__.
    assert is_public_api_entry(
        _entry("SymbologyEncoder", file="pkg/_internal/encoders/base.py", exported=True)
    ) is True


def test_non_dict_entry_excluded():
    assert is_public_api_entry("not-a-dict") is False
    assert is_public_api_entry(None) is False


# ---------------------------------------------------------------------------
# compute_class_stats — example-based, reproducing the barcode/python shape
# ---------------------------------------------------------------------------

def test_compute_class_stats_barcode_python_shape():
    # 2 free functions, 1 public class, 1 internal-not-exported (excluded from public_documented
    # but still counted in total_declared), 1 internal-and-exported (included via PY-INIT-001).
    api_surface = [
        _entry("build_default_registry", kind="function"),
        _entry("parse_options", kind="function"),
        _entry("Barcode"),
        _entry("_RawDecoder", file="pkg/_internal/decoders/raw.py"),
        _entry("SymbologyEncoder", file="pkg/_internal/encoders/base.py", exported=True),
    ]
    stats = compute_class_stats(api_surface)
    assert stats == {
        "total_declared": 3,             # Barcode, _RawDecoder, SymbologyEncoder (not the 2 functions)
        "public_documented": 2,          # Barcode, SymbologyEncoder (_RawDecoder excluded: private name)
        "raw_entries_including_non_class": 5,
    }


def test_compute_class_stats_empty_surface():
    assert compute_class_stats([]) == {
        "total_declared": 0, "public_documented": 0, "raw_entries_including_non_class": 0,
    }


def test_compute_class_stats_malformed_input_never_raises():
    assert compute_class_stats(None) == {
        "total_declared": 0, "public_documented": 0, "raw_entries_including_non_class": 0,
    }
    assert compute_class_stats("not-a-list") == {
        "total_declared": 0, "public_documented": 0, "raw_entries_including_non_class": 0,
    }


def test_same_name_different_namespace_counted_both_ways():
    # consolidate_classes() (extraction/api_surface.py) deliberately keeps two same-named
    # classes in different namespaces as distinct entries ("Category 4: KEEP BOTH") -- that
    # behavior is preserved unchanged here. total_declared counts both; public_documented
    # dedups by name (matching the pre-existing index.py behavior this module replaces), so
    # a namespace collision is exactly the mechanism that makes public_documented < total_declared
    # even with zero private/internal/test entries in play.
    api_surface = [
        {"name": "Document", "kind": "class_definition", "file": "pkg/a/document.py",
         "canonical_namespace": "pkg.a", "exported_via_package_init": False},
        {"name": "Document", "kind": "class_definition", "file": "pkg/b/document.py",
         "canonical_namespace": "pkg.b", "exported_via_package_init": False},
    ]
    stats = compute_class_stats(api_surface)
    assert stats["total_declared"] == 2
    assert stats["public_documented"] == 1
    assert stats["raw_entries_including_non_class"] == 2


# ---------------------------------------------------------------------------
# Structural invariants across generated fixtures
# ---------------------------------------------------------------------------

def _generate_fixtures():
    """Every combination of {function, public class, private class, test-path class,
    internal-not-exported class, internal-exported class} appearing 0-2 times, up to a
    small cap -- small enough to stay fast, varied enough to exercise every code path
    compute_class_stats can take together, not just each in isolation."""
    kinds = [
        ("fn", lambda i: _entry(f"do_thing_{i}", kind="function")),
        ("public", lambda i: _entry(f"PublicClass{i}")),
        ("private", lambda i: _entry(f"_PrivateClass{i}")),
        ("test_path", lambda i: _entry(f"FixtureClass{i}", file=f"tests/fixtures/mod{i}.py")),
        ("internal", lambda i: _entry(f"InternalClass{i}", file=f"pkg/_internal/mod{i}.py")),
        ("internal_exported", lambda i: _entry(
            f"ExportedInternal{i}", file=f"pkg/_internal/mod{i}.py", exported=True)),
    ]
    for counts in itertools.product(range(3), repeat=len(kinds)):
        surface = []
        for (label, builder), n in zip(kinds, counts):
            surface.extend(builder(i) for i in range(n))
        yield surface


def test_invariant_ordering_holds_across_generated_fixtures():
    for surface in _generate_fixtures():
        stats = compute_class_stats(surface)
        assert stats["raw_entries_including_non_class"] >= stats["total_declared"] >= 0
        assert stats["total_declared"] >= stats["public_documented"] >= 0
        assert stats["raw_entries_including_non_class"] == len(surface)


def test_invariant_public_documented_backed_by_total_declared_names():
    """Every name counted in public_documented must also appear among the total_declared
    (non-function) entries' names -- public_documented can never count a class that
    total_declared didn't already see."""
    for surface in _generate_fixtures():
        total_names = {c["name"] for c in surface if c.get("kind") != "function"}
        public_names = {c["name"] for c in surface if is_public_api_entry(c)}
        assert public_names <= total_names


def test_invariant_exported_via_package_init_never_excluded_by_path():
    """An entry flagged exported_via_package_init is public regardless of its file path,
    for any combination of other flags -- the PY-INIT-001 override must never be
    silently defeated by a path-pattern check running before it."""
    for file in ("pkg/_internal/mod.py", "pkg/_private/mod.py", "pkg/_impl/mod.py", "pkg/plain.py"):
        entry = _entry("Exported", file=file, exported=True)
        assert is_public_api_entry(entry) is True


def test_determinism_repeated_calls_identical():
    surface = list(_generate_fixtures())[37]
    first = compute_class_stats(surface)
    second = compute_class_stats(surface)
    assert first == second
