"""HARDEN-A11: structural guard against the ST-013 bug CLASS, generalized.

ST-013 was fixed narrowly in `_flatten_inheritance()` (see
test_flatten_inheritance.py). A follow-up audit found a SECOND, structurally
identical site in the same file — `_merge_members()` (called from
`consolidate_classes()`, which runs immediately BEFORE `_flatten_inheritance`
in the real pipeline) — appending method/property dicts straight from a
discarded duplicate-class fragment into the surviving class, with no copy.
It wasn't exploitable as a live bug only because the discarded fragment is
never referenced again — an invariant enforced by caller discipline, not by
any test or type system, which is exactly the shape of assumption that broke
once already.

This file tests the INVARIANT ("no two classes' member dicts are the same
object after consolidation+flattening"), covering BOTH functions together, the
way the real pipeline actually calls them
(`extract_api_surface()`: consolidate_classes() -> _flatten_inheritance()).
Generated fixtures (loop over small multi-level/duplicate-class combinations)
rather than a hypothesis-style property test, matching this codebase's
existing convention (no `hypothesis` dependency anywhere in the pipeline).
"""
from __future__ import annotations

import itertools

from extraction.api_surface import _flatten_inheritance, _merge_members, consolidate_classes


def _cls(name, *, methods=None, properties=None, bases=None, file="a.cs",
        namespace="", is_partial=False):
    return {
        "name": name,
        "kind": "class_declaration",
        "visibility": "public",
        "file": file,
        "methods": methods or [],
        "properties": properties or [],
        "bases": bases or [],
        "canonical_namespace": namespace,
        "is_partial": is_partial,
    }


def _method(name, doc="", line=1):
    return {"name": name, "params": [], "return_type": "void", "doc": doc,
            "line": line, "is_constructor": False}


def _prop(name, doc="", line=1):
    return {"name": name, "type": "String", "doc": doc, "line": line}


def _all_dict_ids(classes: list[dict]) -> list[int]:
    """id() of every method/property dict across every class — used to detect
    ANY aliasing anywhere in the flattened+consolidated output, not just the
    specific pair a narrower test happens to check."""
    ids = []
    for c in classes:
        for m in c.get("methods", []):
            ids.append(id(m))
        for p in c.get("properties", []):
            ids.append(id(p))
    return ids


# ---------------------------------------------------------------------------
# _merge_members() — the second ST-013-shaped site (consolidate_classes path)
# ---------------------------------------------------------------------------

def test_merge_members_deepcopies_methods_and_properties():
    target = _cls("Foo", methods=[_method("A")], properties=[_prop("X")])
    source = _cls("Foo", methods=[_method("B", doc="from source")],
                  properties=[_prop("Y", doc="from source")])
    _merge_members(target, source)

    merged_method = next(m for m in target["methods"] if m["name"] == "B")
    merged_prop = next(p for p in target["properties"] if p["name"] == "Y")
    assert merged_method is not source["methods"][0]
    assert merged_prop is not source["properties"][0]

    # Mutating the merged copy must not corrupt the (nominally discarded) source
    merged_method["doc"] = "corrupted"
    assert source["methods"][0]["doc"] == "from source"


def test_consolidate_classes_partial_merge_no_aliasing():
    """Category 1 (is_partial merge) via the real consolidate_classes() entry
    point, not just the internal _merge_members() helper."""
    part1 = _cls("Document", namespace="Aspose.Words", is_partial=True,
                 methods=[_method("Save")], properties=[_prop("PageCount")])
    part2 = _cls("Document", namespace="Aspose.Words", is_partial=True,
                 methods=[_method("Load")], properties=[_prop("PageCount")])
    # Snapshot BEFORE the call — consolidate_classes/_merge_members mutate the
    # surviving fragment (part1) in place, so capturing ids afterward from
    # part1 would already include the (correctly) deep-copied entries.
    original_load_id = id(part2["methods"][0])
    original_prop_id = id(part2["properties"][0])

    result = consolidate_classes([part1, part2], "csharp")

    assert len(result) == 1
    merged = result[0]
    method_names = {m["name"] for m in merged["methods"]}
    assert {"Save", "Load"} <= method_names

    merged_load = next(m for m in merged["methods"] if m["name"] == "Load")
    assert id(merged_load) != original_load_id, (
        "merged method from the discarded fragment must be a deep copy, "
        "not the same object as the (now-orphaned) source dict"
    )
    # part2's original dict is untouched by the merge — proves no live alias
    assert part2["methods"][0]["name"] == "Load"
    assert id(part2["methods"][0]) == original_load_id


def test_full_pipeline_no_shared_dict_ids_across_generated_fixtures():
    """Generated-fixture sweep (not hypothesis — matches this codebase's
    convention): several small multi-level-inheritance + duplicate-class
    combinations, run through consolidate_classes() -> _flatten_inheritance()
    exactly as extract_api_surface() does, asserting NO two dicts anywhere in
    the output share identity.

    Coverage note (honest, not oversold): of the 9 depth x dup_count
    combinations, the 3 with dup_count=0 have no duplicate-named classes, so
    consolidate_classes() takes its `if not dup_names: return list(classes)`
    fast path and those 3 iterations exercise only _flatten_inheritance()'s
    existing isolation guarantee (already covered by test_flatten_inheritance.py).
    The other 6 (dup_count=1 or 2) DO force consolidate_classes()'s
    partial-merge branch, exercising the _merge_members() deepcopy fix this
    test exists to generalize — that's the genuinely new coverage here, not
    all 9 combinations equally."""
    depths = [1, 2, 3]
    dup_partial_counts = [0, 1, 2]  # extra duplicate/partial fragments injected

    for depth, dup_count in itertools.product(depths, dup_partial_counts):
        classes = []
        # Build a chain: Base <- Mid1 <- Mid2 <- ... <- Leaf
        base = _cls("Base0", namespace="NS", methods=[_method("shared_method")],
                    properties=[_prop("shared_prop")])
        classes.append(base)
        prev_name = "Base0"
        for level in range(1, depth + 1):
            name = f"Level{level}"
            cls = _cls(name, namespace="NS", bases=[prev_name],
                      methods=[_method(f"own_method_{level}")])
            classes.append(cls)
            prev_name = name

        # Inject `dup_count` extra partial fragments of the leaf class, each
        # contributing a distinctly-named member, forcing consolidate_classes'
        # merge path before flattening runs.
        leaf_name = prev_name
        for d in range(dup_count):
            classes.append(_cls(leaf_name, namespace="NS", is_partial=True,
                                methods=[_method(f"partial_method_{d}")]))
        # Mark the original leaf as partial too so consolidate_classes' merge
        # branch (not the stub/shim/dedup branches) actually engages.
        for c in classes:
            if c["name"] == leaf_name:
                c["is_partial"] = dup_count > 0

        consolidated = consolidate_classes(classes, "csharp")
        _flatten_inheritance(consolidated)

        all_ids = _all_dict_ids(consolidated)
        assert len(all_ids) == len(set(all_ids)), (
            f"depth={depth} dup_count={dup_count}: shared dict identity found "
            f"in flattened+consolidated output — the ST-013 bug class recurred"
        )

        # Mutate every single dict and confirm no other class's same-named
        # member changed as a side effect (the actual failure mode ST-013
        # produced in production: a doc-backfill pass on one page silently
        # rewriting unrelated pages' rendered content).
        for c in consolidated:
            for m in c.get("methods", []):
                original_doc = m.get("doc", "")
                m["doc"] = f"MUTATED-{c['name']}-{m['name']}"
                for other in consolidated:
                    if other is c:
                        continue
                    for om in other.get("methods", []):
                        if om is not m:
                            assert om.get("doc", "") != f"MUTATED-{c['name']}-{m['name']}", (
                                f"mutating {c['name']}.{m['name']} corrupted "
                                f"{other['name']}'s member — shared reference"
                            )
                m["doc"] = original_doc  # restore for subsequent iterations
