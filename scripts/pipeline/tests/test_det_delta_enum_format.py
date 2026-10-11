"""MT074 B2 -- generic delta extraction: real-schema format delta, enum-member diff,
qualified API identity.

Fixtures use the REAL tracked shapes:
  * formats.json  : {format, enum, value, file, line, direction, functional}
  * api_surface   : {name, kind, file, line, methods[], properties[], enum_members[{name,value}],
                     canonical_namespace/class_package/class_import ...}
Two language shapes are exercised on purpose (generality gate G-1): a namespaced
Java-style surface (``class_package``) and a Python-style surface that carries no namespace
fields (only ``file``) next to a C#-style one (``canonical_namespace``).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import refresh_knowledge as _rk


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fmt(name, direction="import", *, enum="LoadFormat", file="Fmt.src", line=1, functional=True):
    entry = {"format": name, "enum": enum, "value": "", "file": file, "line": line, "direction": direction}
    if functional is not None:
        entry["functional"] = functional
    return entry


def _java_type(name, pkg, *, methods=(), props=(), enum=None, file=None):
    e = {
        "name": name, "kind": "enum_declaration" if enum is not None else "class_declaration",
        "doc": "", "file": file or f"src/{pkg.replace('.', '/')}/{name}.java", "line": 1,
        "bases": [], "methods": [{"name": m} for m in methods], "properties": [{"name": p} for p in props],
        "visibility": "public", "class_package": pkg, "canonical_namespace": pkg,
        "class_import": f"{pkg}.{name}",
    }
    if enum is not None:
        e["enum_members"] = [{"name": m, "value": ""} for m in enum]
    return e


def _cs_type(name, ns, *, methods=(), enum=None):
    e = {
        "name": name, "kind": "enum_declaration" if enum is not None else "class_declaration",
        "file": f"src/{name}.cs", "line": 3, "bases": [],
        "methods": [{"name": m} for m in methods], "properties": [],
        "canonical_namespace": ns, "class_import": f"{ns}.{name}",
    }
    if enum is not None:
        e["enum_members"] = [{"name": m, "value": ""} for m in enum]
    return e


def _py_type(name, file, *, methods=(), enum=None):
    """Python-shaped entry: no namespace fields at all (like many real python surfaces)."""
    e = {"name": name, "kind": "class_declaration", "file": file, "line": 10, "bases": [],
         "methods": [{"name": m, "params": []} for m in methods], "properties": []}
    if enum is not None:
        e["kind"] = "enum"
        e["enum_members"] = [{"name": m, "value": str(i)} for i, m in enumerate(enum)]
    return e


def _write_delta(tmp_path: Path, old_apis, new_apis, old_formats=None, new_formats=None,
                 prev_extractor_hash="current"):
    """prev_extractor_hash: "current" (extractor unchanged), None (no model.yaml -> unknown),
    or any other string (a different, older extractor)."""
    bak, merged = tmp_path / "bak", tmp_path / "merged"
    bak.mkdir()
    merged.mkdir()
    if prev_extractor_hash is not None:
        value = _rk._compute_extractor_hash() if prev_extractor_hash == "current" else prev_extractor_hash
        (bak / "model.yaml").write_text("extractor_hash: " + str(value) + "\n", encoding="utf-8")
    for d, apis, fmts in ((bak, old_apis, old_formats), (merged, new_apis, new_formats)):
        (d / "api_surface.json").write_text(json.dumps(apis), encoding="utf-8")
        (d / "claims.json").write_text("[]", encoding="utf-8")
        if fmts is not None:
            (d / "formats.json").write_text(json.dumps(fmts), encoding="utf-8")
    _rk._write_knowledge_delta("fam", "plat", bak, merged, "new_sha", "old_sha")
    _rk._write_format_delta("fam", "plat", bak, merged, "new_sha", "old_sha")
    kd = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
    fd = json.loads((merged / "format_delta.json").read_text(encoding="utf-8"))
    return kd, fd


# ---------------------------------------------------------------------------
# format delta (real schema)
# ---------------------------------------------------------------------------

class TestFormatDeltaRealSchema:
    def test_added_format_detected_with_real_schema(self, tmp_path):
        old = [_fmt("Alpha"), _fmt("Alpha", "export", enum="SaveFormat")]
        new = old + [_fmt("Beta"), _fmt("Beta", "export", enum="SaveFormat")]
        _, fd = _write_delta(tmp_path, [], [], old, new)
        assert [f["name"] for f in fd["formats_added"]] == ["Beta"]
        assert fd["formats_added"][0]["support"] == "both"
        assert fd["formats_removed"] == []
        assert fd["formats_direction_changed"] == []

    def test_removed_format_and_direction_change(self, tmp_path):
        old = [_fmt("Alpha"), _fmt("Alpha", "export", enum="SaveFormat"), _fmt("Gone")]
        new = [_fmt("Alpha")]  # Alpha lost export; Gone vanished
        _, fd = _write_delta(tmp_path, [], [], old, new)
        assert [f["name"] for f in fd["formats_removed"]] == ["Gone"]
        assert fd["formats_direction_changed"] == [
            {"name": "Alpha", "old_support": "both", "new_support": "import-only"}
        ]

    def test_detect_and_enum_only_are_noise_never_support(self, tmp_path):
        old = [_fmt("Alpha")]
        new = [_fmt("Alpha"), _fmt("Sniffed", "detect"), _fmt("Phantom", "enum_only", functional=False)]
        _, fd = _write_delta(tmp_path, [], [], old, new)
        assert fd["formats_added"] == []  # never counted as added support
        reasons = {(n["name"], n["direction"], n["change"]) for n in fd["noise"]}
        assert ("Sniffed", "detect", "added") in reasons
        assert ("Phantom", "enum_only", "added") in reasons  # never silently dropped

    def test_non_functional_import_is_not_support(self, tmp_path):
        old = [_fmt("Alpha")]
        new = [_fmt("Alpha"), _fmt("Stub", "import", functional=False)]
        _, fd = _write_delta(tmp_path, [], [], old, new)
        assert fd["formats_added"] == []
        assert any(n["name"] == "Stub" and n["reason"] == "non_functional" for n in fd["noise"])

    def test_empty_enum_duplicates_collapse_to_one_entry(self):
        entries = [
            _fmt("Alpha", enum="", file="z.src", line=9),
            _fmt("alpha ", enum="LoadFormat", file="a.src", line=1),  # same format, case/space differ
        ]
        supported, _ = _rk._index_formats(entries)
        assert list(supported) == ["alpha"]
        assert supported["alpha"]["name"] == "alpha"  # entry with the real enum is preferred
        delta = _rk._compute_format_delta([], entries)
        assert len(delta["formats_added"]) == 1

    def test_identical_snapshots_produce_empty_delta(self):
        snap = [_fmt("Alpha"), _fmt("Sniffed", "detect"), _fmt("Alpha", enum="")]
        delta = _rk._compute_format_delta(snap, list(snap))
        assert delta == {"formats_added": [], "formats_removed": [],
                         "formats_direction_changed": [], "noise": []}

    def test_python_shaped_formats_without_functional_key(self):
        """Python formats.json entries carry no `functional` key and an empty enum."""
        old = [{"format": "Markdown", "enum": "", "value": "", "file": "r.py", "line": 24, "direction": "import"}]
        new = old + [{"format": "Epub", "enum": "", "value": "", "file": "w.py", "line": 5, "direction": "export"}]
        delta = _rk._compute_format_delta(old, new)
        assert [f["name"] for f in delta["formats_added"]] == ["Epub"]
        assert delta["formats_added"][0]["support"] == "export-only"

    def test_legacy_support_label_entries_still_work(self):
        old = [{"name": "XPS", "support": "import-only"}]
        new = [{"name": "XPS", "support": "both"}]
        delta = _rk._compute_format_delta(old, new)
        assert delta["formats_direction_changed"] == [
            {"name": "XPS", "old_support": "import-only", "new_support": "both"}
        ]

    def test_missing_or_garbage_formats_files_are_tolerated(self, tmp_path):
        _, fd = _write_delta(tmp_path, [], [], None, None)
        assert fd["formats_added"] == [] and fd["noise"] == []


# ---------------------------------------------------------------------------
# enum member diff
# ---------------------------------------------------------------------------

class TestEnumMemberDelta:
    def test_enum_only_change_surfaces_in_modified_apis(self, tmp_path):
        old = [_java_type("Mode", "org.x.core", enum=["A", "B"])]
        new = [_java_type("Mode", "org.x.core", enum=["A", "B", "C"])]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["modified_apis"] == ["Mode"]
        sig = kd["api_signature_changes"]["Mode"]
        assert sig["enum_members_added"] == ["C"] and sig["enum_members_removed"] == []
        assert sig["added_methods"] == [] and sig["removed_methods"] == []
        assert kd["modified_apis_qualified"] == ["org.x.core::Mode"]
        assert kd["breaking_apis"] == []

    def test_removed_constant_is_flagged_breaking(self, tmp_path):
        old = [_cs_type("Kind", "Acme.Lib", enum=["One", "Two"])]
        new = [_cs_type("Kind", "Acme.Lib", enum=["One"])]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["modified_apis"] == ["Kind"]
        assert kd["api_signature_changes"]["Kind"]["enum_members_removed"] == ["Two"]
        assert kd["breaking_apis"] == ["Kind"]
        assert kd["breaking_changes"]["Kind"] == {"enum_members_removed": ["Two"]}

    def test_removed_method_is_also_breaking_added_method_is_not(self, tmp_path):
        old = [_cs_type("Svc", "Acme.Lib", methods=["Run", "Stop"])]
        new = [_cs_type("Svc", "Acme.Lib", methods=["Run", "Pause"])]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["breaking_changes"]["Svc"] == {"removed_methods": ["Stop"]}
        old2 = [_cs_type("Svc", "Acme.Lib", methods=["Run"])]
        new2 = [_cs_type("Svc", "Acme.Lib", methods=["Run", "Pause"])]
        (tmp_path / "second").mkdir()
        kd2, _ = _write_delta(tmp_path / "second", old2, new2)
        assert kd2["breaking_apis"] == []

    def test_unchanged_enum_is_not_modified(self, tmp_path):
        snap = [_java_type("Mode", "org.x.core", enum=["A", "B"])]
        kd, _ = _write_delta(tmp_path, snap, list(snap))
        assert kd["modified_apis"] == [] and kd["api_signature_changes"] == {}

    def test_python_shaped_enum_without_namespace(self, tmp_path):
        old = [_py_type("LoadFormat", "pkg/formats.py", enum=["AUTO", "DOC"])]
        new = [_py_type("LoadFormat", "pkg/formats.py", enum=["AUTO", "DOC", "DOCX"])]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["modified_apis"] == ["LoadFormat"]
        assert kd["api_signature_changes"]["LoadFormat"]["enum_members_added"] == ["DOCX"]
        assert kd["modified_apis_qualified"] == ["pkg/formats.py::LoadFormat"]

    def test_string_enum_members_are_supported(self, tmp_path):
        old = [{"name": "E", "enum_members": ["A"]}]
        new = [{"name": "E", "enum_members": ["A", "B"]}]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["api_signature_changes"]["E"]["enum_members_added"] == ["B"]


# ---------------------------------------------------------------------------
# qualified identity / collisions
# ---------------------------------------------------------------------------

class TestQualifiedIdentity:
    def test_new_same_simple_name_type_is_not_masked(self, tmp_path):
        old = [_java_type("Result", "org.x.a", methods=["ok"])]
        new = [_java_type("Result", "org.x.a", methods=["ok"]),
               _java_type("Result", "org.x.b", methods=["ok"])]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["new_apis"] == ["Result"]  # was masked before (undercount)
        assert kd["new_apis_qualified"] == ["org.x.b::Result"]
        assert kd["modified_apis"] == []  # and no bogus modification of the existing one
        assert kd["removed_apis"] == [] and kd["removed_apis_qualified"] == []
        assert len(kd["name_collisions"]) == 1
        col = kd["name_collisions"][0]
        assert col["name"] == "Result" and col["added"] == ["org.x.b::Result"]
        assert col["old"] == ["org.x.a::Result"] and col["new"] == ["org.x.a::Result", "org.x.b::Result"]

    def test_collision_no_bogus_modified_when_members_differ_across_packages(self, tmp_path):
        """Two same-named types with different members, both unchanged -> no change at all
        (the old simple-name dict made one overwrite the other and reported 'modified')."""
        types = [_java_type("Value", "org.x.a", methods=["get"]),
                 _java_type("Value", "org.x.b", methods=["set", "reset"])]
        kd, _ = _write_delta(tmp_path, list(types), list(reversed(types)))
        assert kd["modified_apis"] == [] and kd["new_apis"] == [] and kd["removed_apis"] == []
        assert kd["name_collisions"] == []

    def test_removed_one_of_two_same_named_types_is_not_reported_removed(self, tmp_path):
        old = [_java_type("Value", "org.x.a"), _java_type("Value", "org.x.b")]
        new = [_java_type("Value", "org.x.a")]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["removed_apis"] == []  # compat list: the simple name still exists
        assert kd["removed_apis_qualified"] == ["org.x.b::Value"]
        assert kd["name_collisions"][0]["removed"] == ["org.x.b::Value"]

    def test_truly_removed_type_still_in_simple_removed_list(self, tmp_path):
        old = [_cs_type("Old", "Acme"), _cs_type("Keep", "Acme")]
        new = [_cs_type("Keep", "Acme")]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["removed_apis"] == ["Old"] and kd["removed_apis_qualified"] == ["Acme::Old"]

    def test_modified_in_the_right_package_only(self, tmp_path):
        old = [_java_type("Value", "org.x.a", methods=["get"]), _java_type("Value", "org.x.b", methods=["set"])]
        new = [_java_type("Value", "org.x.a", methods=["get", "peek"]), _java_type("Value", "org.x.b", methods=["set"])]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["modified_apis"] == ["Value"]
        assert kd["modified_apis_qualified"] == ["org.x.a::Value"]
        assert kd["api_signature_changes"]["Value"]["added_methods"] == ["peek"]

    def test_schema_upgrade_adding_namespaces_is_not_a_mass_change(self, tmp_path):
        """An older snapshot without namespace fields vs a newer one that has them must
        pair by name+file, not report every type as removed AND added."""
        old = [_py_type("Doc", "pkg/doc.py", methods=["save"]), _py_type("Page", "pkg/page.py")]
        new = [dict(_py_type("Doc", "pkg/doc.py", methods=["save"]), canonical_namespace="pkg"),
               dict(_py_type("Page", "pkg/page.py"), canonical_namespace="pkg")]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["new_apis"] == [] and kd["removed_apis"] == [] and kd["modified_apis"] == []

    def test_entries_without_any_qualifier_behave_like_the_old_simple_name_diff(self, tmp_path):
        old = [{"name": "A", "methods": [{"name": "m"}], "properties": []}]
        new = [{"name": "A", "methods": [{"name": "m"}, {"name": "n"}], "properties": []},
               {"name": "B", "methods": [], "properties": []}]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["new_apis"] == ["B"] and kd["new_apis_qualified"] == ["B"]
        assert kd["modified_apis"] == ["A"]

    def test_qualified_name_prefers_namespace_then_file(self):
        assert _rk._api_qualified_name({"name": "T", "canonical_namespace": "N", "file": "f"}) == "N::T"
        assert _rk._api_qualified_name({"name": "T", "class_package": "P", "file": "f"}) == "P::T"
        assert _rk._api_qualified_name({"name": "T", "file": "f.py"}) == "f.py::T"
        assert _rk._api_qualified_name({"name": "T"}) == "T"
        # a language whose names contain '::' keeps a parseable identity
        assert _rk._api_qualified_name({"name": "ns::T", "canonical_namespace": "N"}) == "N::ns::T"

    def test_simple_name_with_scope_separator_is_not_mangled(self, tmp_path):
        old = []
        new = [{"name": "ns::Widget", "canonical_namespace": "N", "methods": [], "properties": []}]
        kd, _ = _write_delta(tmp_path, old, new)
        assert kd["new_apis"] == ["ns::Widget"]
        assert kd["new_apis_qualified"] == ["N::ns::Widget"]

    def test_resurrection_still_uses_simple_names(self, tmp_path):
        (tmp_path / "merged").mkdir()
        (tmp_path / "merged" / "knowledge_delta.prev.json").write_text(
            json.dumps({"removed_apis": ["Back"]}), encoding="utf-8")
        bak = tmp_path / "bak"
        bak.mkdir()
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        merged = tmp_path / "merged"
        (merged / "api_surface.json").write_text(json.dumps([_cs_type("Back", "Acme")]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")
        _rk._write_knowledge_delta("fam", "plat", bak, merged, "n", "o")
        kd = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
        assert kd["resurrected_apis"] == ["Back"]


# ---------------------------------------------------------------------------
# downstream consumers
# ---------------------------------------------------------------------------

class TestConsumers:
    def test_semantic_diff_emits_enum_events_and_format_added(self, tmp_path):
        import commands.knowledge.semantic_diff as sd
        old = [_cs_type("Kind", "Acme", enum=["One", "Two"]), _cs_type("Svc", "Acme", methods=["a"])]
        new = [_cs_type("Kind", "Acme", enum=["One", "Three"]), _cs_type("Svc", "Acme", methods=["a"])]
        old_f = [_fmt("Alpha")]
        new_f = [_fmt("Alpha"), _fmt("Beta", "export", enum="SaveFormat"), _fmt("Sniffed", "detect")]
        root = tmp_path / "knowledge" / "fam" / "plat" / "merged"
        kd, fd = _write_delta(tmp_path, old, new, old_f, new_f)
        root.mkdir(parents=True)
        (root / "knowledge_delta.json").write_text(json.dumps(kd), encoding="utf-8")
        (root / "format_delta.json").write_text(json.dumps(fd), encoding="utf-8")
        sd.configure(knowledge_root=str(tmp_path / "knowledge"), reports_root=str(tmp_path / "reports"))
        try:
            changes = sd.run("fam", "plat")
        finally:
            sd.configure(knowledge_root="knowledge", reports_root="reports/refresh_review")
        by_type = {}
        for c in changes:
            by_type.setdefault(c["change_type"], []).append(c)
        feat = [c for c in by_type["FEATURE_ADDED"] if c["symbol_kind"] == "enum"]
        assert feat and feat[0]["symbol"] == "Kind" and feat[0]["enum_members_added"] == ["Three"]
        sig = [c for c in by_type["API_SIGNATURE_CHANGED"] if c["symbol_kind"] == "enum"]
        assert sig and sig[0]["breaking"] is True and sig[0]["enum_members_removed"] == ["Two"]
        modified = [c for c in by_type["API_MODIFIED"] if c["symbol"] == "Kind"]
        assert modified and modified[0]["breaking"] is True
        fmt = by_type["FORMAT_ADDED"]
        assert [c["symbol"] for c in fmt] == ["Beta"]  # detect noise is not an event
        assert fmt[0]["format_support"] == "export-only"

    def test_body_impact_update_types_for_new_events(self):
        import commands.content.body_impact as bi
        section = {"heading": "H", "section_id": "s", "claims": []}
        pick = lambda ct: bi._select_update_type({"change_type": ct}, section)  # noqa: E731
        assert pick("FORMAT_ADDED") == bi.UT_REWRITE
        assert pick("FORMAT_DIRECTION_CHANGED") == bi.UT_REWRITE
        assert pick("FORMAT_REMOVED") == bi.UT_SURGICAL  # never a section removal
        assert pick("FEATURE_ADDED") == bi.UT_REWRITE
        assert pick("API_SIGNATURE_CHANGED") == bi.UT_REWRITE

    def test_page_impact_changed_ids_include_enum_members(self):
        import page_impact_assess as pia
        delta = {"modified_apis": ["Kind"], "api_signature_changes": {
            "Kind": {"added_methods": [], "removed_methods": [], "added_properties": [],
                     "removed_properties": [], "enum_members_added": ["Three"],
                     "enum_members_removed": ["Two"]}}}
        ids = pia._extract_changed_api_ids(delta)
        assert {"Kind", "Kind.Three", "Kind.Two"} <= ids
        # a page citing the new constant is affected; one citing an unrelated type is not
        assert pia._match_cited_apis(["Kind.Three"], ids) == {"Kind.Three"}
        assert pia._match_cited_apis(["Other.Member"], ids) == set()

    def test_page_impact_tolerates_old_deltas_without_new_fields(self):
        import page_impact_assess as pia
        assert pia._extract_changed_api_ids({"modified_apis": ["A"]}) == {"A"}
        assert pia._extract_changed_api_ids({"api_signature_changes": {"A": "garbage"}}) == set()


# ---------------------------------------------------------------------------
# extractor-version awareness: confirmed vs unconfirmed removals, drift suspects
# ---------------------------------------------------------------------------

def _methods(n, prefix="m"):
    return [f"{prefix}{i}" for i in range(n)]


class TestExtractorAwareBreaking:
    def test_extractor_changed_states_recorded(self, tmp_path):
        snap = [_cs_type("Svc", "Acme", methods=["a"])]
        for i, (prev, expected) in enumerate([("current", "false"), ("old-hash", "true"), (None, "unknown")]):
            d = tmp_path / f"c{i}"
            d.mkdir()
            kd, _ = _write_delta(d, snap, list(snap), prev_extractor_hash=prev)
            assert kd["extractor_changed"] == expected

    @pytest.mark.parametrize("prev", ["old-hash", None])
    def test_member_removals_unconfirmed_when_extractor_changed_or_unknown(self, tmp_path, prev):
        old = [_py_type("Doc", "pkg/doc.py", methods=["a", "b", "c"], enum=None),
               _cs_type("Kind", "Acme", enum=["One", "Two"])]
        new = [_py_type("Doc", "pkg/doc.py", methods=["a"], enum=None),
               _cs_type("Kind", "Acme", enum=["One"])]
        kd, _ = _write_delta(tmp_path, old, new, prev_extractor_hash=prev)
        assert kd["breaking_changes"] == {} and kd["breaking_apis"] == []
        assert sorted(kd["breaking_unconfirmed_apis"]) == ["Doc", "Kind"]
        doc = kd["breaking_unconfirmed"]["Doc"]
        assert doc["removed_methods"] == ["b", "c"]
        assert doc["reason"] == "extractor_changed_or_unknown" and doc["verify_against_source"] is True
        assert kd["breaking_unconfirmed"]["Kind"]["enum_members_removed"] == ["Two"]
        assert kd["modified_apis"] == ["Doc", "Kind"]  # still reported as modified

    def test_confirmed_when_extractor_unchanged_and_file_persisted(self, tmp_path):
        old = [_py_type("Doc", "pkg/doc.py", methods=["a", "b"])]
        new = [_py_type("Doc", "pkg/doc.py", methods=["a"])]
        kd, _ = _write_delta(tmp_path, old, new, prev_extractor_hash="current")
        assert kd["breaking_changes"] == {"Doc": {"removed_methods": ["b"]}}
        assert kd["breaking_unconfirmed"] == {} and kd["breaking_unconfirmed_apis"] == []

    def test_moved_file_is_never_confirmed(self, tmp_path):
        old = [_py_type("Doc", "pkg/doc.py", methods=["a", "b"])]
        new = [_py_type("Doc", "pkg/doc_v2.py", methods=["a"])]
        kd, _ = _write_delta(tmp_path, old, new, prev_extractor_hash="current")
        assert kd["breaking_changes"] == {}
        assert kd["breaking_unconfirmed"]["Doc"]["removed_methods"] == ["b"]

    def test_whole_type_removal_listed_and_flagged_unconfirmed_unless_extractor_stable(self, tmp_path):
        old = [_cs_type("Gone", "Acme"), _cs_type("Keep", "Acme")]
        new = [_cs_type("Keep", "Acme")]
        kd, _ = _write_delta(tmp_path, old, new, prev_extractor_hash=None)
        assert kd["removed_apis"] == ["Gone"] and kd["removed_apis_unconfirmed"] == ["Gone"]
        (tmp_path / "s").mkdir()
        kd2, _ = _write_delta(tmp_path / "s", old, new, prev_extractor_hash="current")
        assert kd2["removed_apis"] == ["Gone"] and kd2["removed_apis_unconfirmed"] == []

    def test_extraction_drift_suspect_flags_big_member_drop_even_when_extractor_stable(self, tmp_path):
        old = [_java_type("Big", "org.x.m", methods=_methods(60)),
               _java_type("Small", "org.x.m", methods=_methods(8))]
        new = [_java_type("Big", "org.x.m", methods=_methods(38)),   # -22 (37%): suspect
               _java_type("Small", "org.x.m", methods=_methods(4))]  # -4: below the 5-member floor
        kd, _ = _write_delta(tmp_path, old, new, prev_extractor_hash="current")
        suspects = kd["extraction_drift_suspect"]
        assert [x["qualified"] for x in suspects] == ["org.x.m::Big"]
        assert suspects[0]["old_member_count"] == 60 and suspects[0]["new_member_count"] == 38

    def test_python_shaped_drift_suspect_and_additions_cancel_suspicion(self, tmp_path):
        old = [_py_type("Doc", "pkg/doc.py", methods=_methods(10))]
        shrunk = [_py_type("Doc", "pkg/doc.py", methods=_methods(5))]
        kd, _ = _write_delta(tmp_path, old, shrunk, prev_extractor_hash="old-hash")
        assert [x["name"] for x in kd["extraction_drift_suspect"]] == ["Doc"]
        (tmp_path / "b").mkdir()
        replaced = [_py_type("Doc", "pkg/doc.py", methods=_methods(4) + ["brand_new"])]
        kd2, _ = _write_delta(tmp_path / "b", old, replaced, prev_extractor_hash="old-hash")
        assert kd2["extraction_drift_suspect"] == []  # a real signature-level addition: not drift

    def test_semantic_diff_marks_unconfirmed_removals_informational(self, tmp_path):
        import commands.knowledge.semantic_diff as sd
        old = [_cs_type("Kind", "Acme", enum=["One", "Two"]), _cs_type("Gone", "Acme")]
        new = [_cs_type("Kind", "Acme", enum=["One"])]
        kd, _ = _write_delta(tmp_path, old, new, prev_extractor_hash=None)
        root = tmp_path / "knowledge" / "fam" / "plat" / "merged"
        root.mkdir(parents=True)
        (root / "knowledge_delta.json").write_text(json.dumps(kd), encoding="utf-8")
        sd.configure(knowledge_root=str(tmp_path / "knowledge"), reports_root=str(tmp_path / "reports"))
        try:
            changes = sd.run("fam", "plat")
        finally:
            sd.configure(knowledge_root="knowledge", reports_root="reports/refresh_review")
        enum_ev = next(c for c in changes if c["symbol_kind"] == "enum")
        assert "breaking" not in enum_ev
        assert enum_ev["breaking_unconfirmed"] is True and enum_ev["verify_against_source"] is True
        assert enum_ev["content_impact"] == "REVIEW_ONLY"
        removed = next(c for c in changes if c["change_type"] == "API_REMOVED")
        assert removed["content_impact"] == "REVIEW_ONLY" and removed["verify_against_source"] is True
        klass = next(c for c in changes if c["symbol"] == "Kind" and c["symbol_kind"] == "class")
        assert klass["breaking_unconfirmed"] is True and "breaking" not in klass

    def test_body_impact_never_acts_on_unverified_removals(self):
        import commands.content.body_impact as bi
        cm = {"page_path": "p.md", "sections": [{
            "section_id": "s1", "heading": "H", "start_line": 1, "end_line": 5,
            "claims": [{"sentence": "Gone is documented here.", "detected_symbols": ["Gone"]}]}]}
        base = {"change_id": "C1", "change_type": "API_REMOVED", "symbol": "Gone",
                "symbol_kind": "class", "public_impact": "USER_VISIBLE", "content_impact": "BODY_UPDATE"}
        assert bi._match_change_to_sections(dict(base), cm)  # confirmed removal still acts
        unverified = dict(base, verify_against_source=True, breaking_unconfirmed=True)
        assert bi._match_change_to_sections(unverified, cm) == []
        for ct in ("API_SIGNATURE_CHANGED", "FEATURE_REMOVED"):
            assert bi._match_change_to_sections(dict(unverified, change_type=ct), cm) == []

    def test_page_impact_ignores_unconfirmed_removed_enum_members(self):
        import page_impact_assess as pia
        delta = {
            "modified_apis": ["Kind"],
            "api_signature_changes": {"Kind": {"enum_members_added": ["Three"], "enum_members_removed": ["Two"]}},
            "breaking_unconfirmed": {"Kind": {"enum_members_removed": ["Two"],
                                              "reason": "extractor_changed_or_unknown",
                                              "verify_against_source": True}},
        }
        ids = pia._extract_changed_api_ids(delta)
        assert "Kind.Three" in ids and "Kind.Two" not in ids
