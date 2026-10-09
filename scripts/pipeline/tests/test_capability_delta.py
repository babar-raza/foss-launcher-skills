"""B4 (MT074): lib/capability_delta.py -- capability units + five-surface disposition ledger.

Fixtures deliberately use three differently shaped products (hard gate G-1):
  JAVA-style   dotted package qualifiers, options/saver route types, an internal `engine` package
  C#-style     PascalCase namespaces, members that reference new types in their signatures
  Python-style file-path qualifiers (no namespace), snake_case modules, no signature type info
Every threshold is exercised on BOTH sides, with config passed in (never monkeypatching internals).
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import re
from pathlib import Path, PurePosixPath

import pytest

# sys.path is set by tests/conftest.py
import capability_delta as cd

SURFACES = ("reference", "docs", "kb", "blog", "products")
CFG = cd.load_config()
TARGETS = {"reference": "ref/", "docs": "docs/page.md", "kb": "kb/", "blog": "blog/", "products": "products/new.md"}


def T(q, members=0, refs=(), kind="class"):
    return {"qualified": q, "member_count": members, "signature_refs": list(refs), "kind": kind}


def delta(**kw):
    base = {"schema_version": 1, "added_types": [], "added_members": [], "enum_constants_added": [],
            "formats_added": [], "name_collisions": [], "existing_symbols": [], "public_surface_size": None,
            "ground_truth": {"tier": None, "symbol_level": True}}
    base.update(kw)
    return base


def java_style(existing=None):
    return delta(
        added_types=[T("org.acme.render::RenderOptions", 4), T("org.acme.render::RenderSaver", 5),
                     T("org.acme.render::RenderJob", 6), T("org.acme.render::RenderResult", 3),
                     T("org.acme.render::RenderStage", 2), T("org.acme.render.engine::Scheduler", 3)],
        added_members=[{"owner": "org.acme.core::Document", "name": "renderTo",
                        "signature_refs": ["RenderJob", "String"]}],
        enum_constants_added=[{"owner": "org.acme.core::OutputMode", "name": "TILED"}],
        existing_symbols=existing if existing is not None else ["Document", "OutputMode", "Page", "Font", "Image"],
        public_surface_size=400)


def net_style(existing=None):
    return delta(
        added_types=[T("Acme.Sheets.Charts::ChartPalette", 3), T("Acme.Sheets.Charts::ChartTheme", 2),
                     T("Acme.Sheets.Fonts::FontFallback", 4)],
        added_members=[{"owner": "Acme.Sheets::Workbook", "name": "ApplyTheme", "signature_refs": ["ChartTheme"]}],
        existing_symbols=existing if existing is not None else ["Workbook", "Chart", "Cell"])


def py_style(existing=None):
    return delta(
        added_types=[T("acme/imports/csv_reader.py::CsvReader", 3),
                     T("acme/imports/legacy/csv_legacy.py::CsvLegacyParser", 2),
                     T("acme/util/color.py::Color", 1)],
        existing_symbols=existing if existing is not None else ["Sheet", "Book", "Cell"])


def types_of(unit):
    return sorted(s for s in unit["symbols"] if not cd.is_member_symbol(s))


def by_type(units, simple):
    for u in units:
        if any(t.endswith("::" + simple) or t == simple for t in types_of(u)):
            return u
    raise AssertionError(f"no unit holds {simple}")


def cfg_with(path, value):
    c = copy.deepcopy(CFG)
    node = c
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return c


# ── grouping ────────────────────────────────────────────────────────────────────────────────────

class TestStructuralGrouping:
    def test_java_style_namespace_groups_and_member_attach(self):
        units = cd.group_units(java_style())
        render = by_type(units, "RenderJob")
        assert types_of(render) == sorted(f"org.acme.render::{n}" for n in
                                          ["RenderJob", "RenderOptions", "RenderResult", "RenderSaver", "RenderStage"])
        assert "org.acme.core::Document.renderTo" in render["symbols"]  # signature references RenderJob
        engine = by_type(units, "Scheduler")
        assert engine is not render and types_of(engine) == ["org.acme.render.engine::Scheduler"]

    def test_net_style_two_namespaces_two_groups(self):
        units = cd.group_units(net_style())
        theme = by_type(units, "ChartTheme")
        assert types_of(theme) == ["Acme.Sheets.Charts::ChartPalette", "Acme.Sheets.Charts::ChartTheme"]
        assert "Acme.Sheets::Workbook.ApplyTheme" in theme["symbols"]
        assert types_of(by_type(units, "FontFallback")) == ["Acme.Sheets.Fonts::FontFallback"]

    def test_python_style_file_qualifier_uses_directory(self):
        d = delta(added_types=[T("acme/tables/pivot.py::PivotTable", 2), T("acme/tables/pivot_cache.py::PivotCache", 2),
                               T("acme/util/color.py::Color", 1)], existing_symbols=["Sheet"])
        units = cd.group_units(d, config=cfg_with(["grouping", "token_affinity", "enabled"], False))
        assert types_of(by_type(units, "PivotTable")) == ["acme/tables/pivot.py::PivotTable",
                                                          "acme/tables/pivot_cache.py::PivotCache"]
        assert len(units) == 2

    def test_bare_names_without_qualifier_share_one_group(self):
        d = delta(added_types=[T("Alpha", 1), T("Beta", 1)], existing_symbols=["X"])
        units = cd.group_units(d, config=cfg_with(["grouping", "token_affinity", "enabled"], False))
        assert len(units) == 1

    def test_added_members_without_new_type_refs_form_api_extension_per_owner(self):
        d = delta(added_members=[{"owner": "ns::Doc", "name": "a"}, {"owner": "ns::Doc", "name": "b"},
                                 {"owner": "ns::Page", "name": "c"}], existing_symbols=["Doc", "Page"])
        units = cd.group_units(d, config=cfg_with(["grouping", "token_affinity", "enabled"], False))
        assert sorted(sorted(u["symbols"]) for u in units) == [["ns::Doc.a", "ns::Doc.b"], ["ns::Page.c"]]

    def test_every_member_lands_in_exactly_one_unit(self):
        units = cd.group_units(java_style())
        flat = list(itertools.chain.from_iterable(u["symbols"] for u in units))
        assert len(flat) == len(set(flat))
        assert "org.acme.core::Document.renderTo" in flat


class TestTokenAffinity:
    def _units(self, n_existing_csv, *, config=None, new=None):
        existing = [f"Csv{i}Thing" for i in range(n_existing_csv)] + ["Sheet"]
        d = py_style(existing)
        if new is not None:
            d["added_types"] = new
        return cd.group_units(d, config=config)

    def test_links_at_max_existing_boundary_and_not_above(self):
        linked = self._units(3)   # <= max_existing_symbols_sharing (3) -> link
        assert len(by_type(linked, "CsvReader")["symbols"]) == 2
        assert by_type(linked, "CsvReader") is by_type(linked, "CsvLegacyParser")
        apart = self._units(4)    # above the threshold -> the token carries no information
        assert by_type(apart, "CsvReader") is not by_type(apart, "CsvLegacyParser")

    def test_needs_two_new_symbols_sharing_the_token(self):
        one = self._units(0, new=[T("acme/imports/csv_reader.py::CsvReader", 3), T("acme/imports/legacy/x.py::XmlLegacyParser", 2)])
        assert by_type(one, "CsvReader") is not by_type(one, "XmlLegacyParser")
        two = self._units(0)
        assert by_type(two, "CsvReader") is by_type(two, "CsvLegacyParser")

    def test_thresholds_come_from_config(self):
        c = cfg_with(["grouping", "token_affinity", "max_existing_symbols_sharing"], 0)
        u = self._units(1, config=c)
        assert by_type(u, "CsvReader") is not by_type(u, "CsvLegacyParser")

    def test_disabled_by_config(self):
        c = cfg_with(["grouping", "token_affinity", "enabled"], False)
        u = self._units(0, config=c)
        assert by_type(u, "CsvReader") is not by_type(u, "CsvLegacyParser")

    def test_unknown_existing_symbols_disables_affinity_honestly(self):
        d = py_style(None)
        d["existing_symbols"] = None
        units = cd.group_units(d)
        assert by_type(units, "CsvReader") is not by_type(units, "CsvLegacyParser")

    def test_generic_and_short_tokens_never_link(self):
        d = delta(added_types=[T("a::ItemOne", 1), T("b::ItemTwo", 1), T("c::AbX", 1), T("d::AbY", 1)],
                  existing_symbols=["Z"])
        units = cd.group_units(d)
        assert len(units) == 4

    def test_member_attaches_to_type_by_token_when_signature_has_no_types(self):
        d = delta(added_types=[T("acme/pivots::PivotTable", 2)],
                  added_members=[{"owner": "acme/sheet::Sheet", "name": "add_pivot_table", "signature_refs": []}],
                  existing_symbols=["Sheet", "Book"])
        units = cd.group_units(d)
        assert len(units) == 1 and "acme/sheet::Sheet.add_pivot_table" in units[0]["symbols"]

    def test_every_auto_unit_is_draft(self):
        assert {u["grouping"] for u in cd.group_units(java_style())} == {"draft"}


class TestReviewerOverrides:
    def test_override_wins_and_marks_reviewed(self):
        d = net_style()
        ov = [{"id": "charts-and-fonts", "symbols": ["Acme.Sheets.Charts::ChartTheme", "Acme.Sheets.Fonts::FontFallback"]}]
        units = cd.group_units(d, grouping_overrides=ov)
        rev = [u for u in units if u["grouping"] == "reviewed"]
        assert len(rev) == 1 and types_of(rev[0]) == ["Acme.Sheets.Charts::ChartTheme", "Acme.Sheets.Fonts::FontFallback"]
        # the leftover palette is auto-grouped alone, and the member that referenced ChartTheme moved with it
        assert "Acme.Sheets::Workbook.ApplyTheme" not in by_type(units, "ChartPalette")["symbols"]
        assert by_type(units, "ChartPalette")["grouping"] == "draft"

    def test_member_symbol_can_be_overridden_into_another_unit(self):
        d = net_style()
        ov = [{"symbols": ["Acme.Sheets.Charts::ChartPalette", "Acme.Sheets::Workbook.ApplyTheme"]}]
        units = cd.group_units(d, grouping_overrides=ov)
        assert "Acme.Sheets::Workbook.ApplyTheme" in by_type(units, "ChartPalette")["symbols"]

    def test_unknown_symbol_is_an_error(self):
        with pytest.raises(cd.GroupingOverrideError, match="unknown symbol"):
            cd.group_units(net_style(), grouping_overrides=[{"symbols": ["Nope::Missing"]}])

    def test_symbol_claimed_twice_is_an_error(self):
        ov = [{"symbols": ["Acme.Sheets.Fonts::FontFallback"]}, {"symbols": ["Acme.Sheets.Fonts::FontFallback"]}]
        with pytest.raises(cd.GroupingOverrideError, match="claimed twice"):
            cd.group_units(net_style(), grouping_overrides=ov)

    def test_override_can_carry_a_format(self):
        d = delta(added_types=[T("ns::Reader", 1)], formats_added=[{"name": "TAB", "ext": ".tab"}],
                  existing_symbols=["X"])
        units = cd.group_units(d, grouping_overrides=[{"symbols": ["ns::Reader", "format:TAB"]}])
        assert len(units) == 1 and units[0]["formats"] == ["TAB"]


class TestEnumConstantsAndFormats:
    def test_standalone_constants_become_format_route_unit_per_owner_enum(self):
        d = delta(enum_constants_added=[{"owner": "ns::Mode", "name": "ALPHA"}, {"owner": "ns::Mode", "name": "BETA"},
                                        {"owner": "ns::Other", "name": "GAMMA"}], existing_symbols=["Mode", "Other"])
        ledger = cd.build_ledger(d, family="f", platform="p", surface_targets=TARGETS)
        kinds = sorted((u["kind"], tuple(u["enum_constants"])) for u in ledger["units"])
        assert kinds == [("format-route", ("ns::Mode.ALPHA", "ns::Mode.BETA")), ("format-route", ("ns::Other.GAMMA",))]

    def test_constant_and_format_with_same_key_share_a_unit(self):
        d = delta(enum_constants_added=[{"owner": "ns::Mode", "name": "TabSep"}],
                  formats_added=[{"name": "TABSEP", "ext": ".tsv"}], existing_symbols=["Mode"])
        units = cd.group_units(d)
        assert len(units) == 1 and units[0]["formats"] == ["TABSEP"]

    def test_constant_links_to_group_by_normalised_key_substring(self):
        d = delta(added_types=[T("ns::TabSepLoadOptions", 3)],
                  enum_constants_added=[{"owner": "ns::LoadMode", "name": "TabSep"}],
                  existing_symbols=["LoadMode", "Doc"])
        units = cd.group_units(d)
        assert len(units) == 1 and units[0]["enum_constants"] == ["ns::LoadMode.TabSep"]

    def test_constant_key_common_in_existing_api_does_not_link(self):
        d = delta(added_types=[T("ns::TabSepLoadOptions", 3)],
                  enum_constants_added=[{"owner": "ns::LoadMode", "name": "TabSep"}],
                  existing_symbols=["TabSepA", "TabSepB", "TabSepC", "TabSepD"])
        assert len(cd.group_units(d)) == 2

    def test_formats_only_form_one_unit_without_constants(self):
        d = delta(formats_added=[{"name": "ONE", "ext": ".one"}, {"name": "TWO", "ext": None}], existing_symbols=[])
        units = cd.group_units(d)
        assert len(units) == 1 and units[0]["formats"] == ["ONE", "TWO"]

    def test_constants_on_a_new_type_travel_with_it_and_are_not_new_enum_constants(self):
        d = delta(added_types=[T("ns::Level", 3, kind="enum")],
                  enum_constants_added=[{"owner": "ns::Level", "name": "HIGH"}], existing_symbols=["X"])
        ledger = cd.build_ledger(d, family="f", platform="p", surface_targets=TARGETS)
        (u,) = ledger["units"]
        assert u["enum_constants"] == ["ns::Level.HIGH"] and u["scale"]["new_enum_constants"] == 0


class TestIds:
    def test_format_and_stability_under_input_order(self):
        base = java_style()
        a = cd.group_units(base)
        rev = copy.deepcopy(base)
        rev["added_types"].reverse()
        b = cd.group_units(rev)
        assert [u["id"] for u in a] == [u["id"] for u in b]
        for u in a:
            assert re.fullmatch(r"CU-[0-9a-f]{8}", u["id"])

    def test_id_is_hash_of_sorted_symbols(self):
        syms = ["b::B", "a::A"]
        expect = "CU-" + hashlib.sha256("\n".join(sorted(syms)).encode("utf-8")).hexdigest()[:8]
        assert cd.unit_id(syms) == expect == cd.unit_id(list(reversed(syms)))
        assert cd.unit_id(syms, formats=["X"]) != cd.unit_id(syms)

    def test_units_sorted_by_id(self):
        ids = [u["id"] for u in cd.group_units(java_style())]
        assert ids == sorted(ids)


# ── scale ───────────────────────────────────────────────────────────────────────────────────────

def ledger_of(d, **kw):
    kw.setdefault("surface_targets", TARGETS)
    return cd.build_ledger(d, family="fam", platform="plat", upstream_head="e" * 40, **kw)


class TestScale:
    def test_java_style_scale(self):
        led = ledger_of(java_style(), verified_example_symbols={"RenderJob"})
        render = by_type(led["units"], "RenderJob")
        s = render["scale"]
        assert (s["new_public_types"], s["new_public_members"]) == (5, 4 + 5 + 6 + 3 + 2 + 1)
        assert s["introduces_new_io_route"] is True and s["verified_example_present"] is True
        assert s["share_of_public_surface"] == round((5 + 21) / 400, 6)
        assert render["kind"] == "route"
        engine = by_type(led["units"], "Scheduler")
        assert engine["scale"]["new_public_types"] == 0 and engine["scale"]["new_internal_types"] == 1

    def test_verified_example_none_when_not_supplied_false_when_supplied_without_match(self):
        none = by_type(ledger_of(net_style())["units"], "ChartTheme")
        assert none["scale"]["verified_example_present"] is None
        no_match = by_type(ledger_of(net_style(), verified_example_symbols={"Other"})["units"], "ChartTheme")
        assert no_match["scale"]["verified_example_present"] is False

    def test_snippet_candidates_from_index(self):
        led = ledger_of(py_style(), snippet_index={"CsvReader": ["snip-b", "snip-a"], "Unrelated": ["z"]})
        assert by_type(led["units"], "CsvReader")["scale"]["snippet_candidates"] == ["snip-a", "snip-b"]

    @pytest.mark.parametrize("build,expected", [
        # R1: new constant on an existing enum + a new public type
        (lambda: delta(added_types=[T("n::Thing", 1)], enum_constants_added=[{"owner": "n::M", "name": "Thing"}],
                       existing_symbols=["M"]), True),
        # R2: a new format + a new public type
        (lambda: delta(added_types=[T("n::Thing", 1)], formats_added=[{"name": "Thing", "ext": None}],
                       existing_symbols=["M"]), True),
        # R3: a new options type
        (lambda: delta(added_types=[T("n::SomeOptions", 1)], existing_symbols=["M"]), True),
        # R3: a load/save-style type
        (lambda: delta(added_types=[T("n::SheetSaver_x", 1)], existing_symbols=["M"]), False),
        (lambda: delta(added_types=[T("n::sheet_save_task", 1)], existing_symbols=["M"]), True),
        # R4: a loader-verb member whose signature references the new type
        (lambda: delta(added_types=[T("n::Thing", 1)], existing_symbols=["M"],
                       added_members=[{"owner": "n::M", "name": "loadFrom", "signature_refs": ["Thing"]}]), True),
        (lambda: delta(added_types=[T("n::Thing", 1)], existing_symbols=["M"],
                       added_members=[{"owner": "n::M", "name": "rename", "signature_refs": ["Thing"]}]), False),
        # R5: format-route with a format
        (lambda: delta(formats_added=[{"name": "ONE", "ext": None}], existing_symbols=[]), True),
        # constants alone, no new type
        (lambda: delta(enum_constants_added=[{"owner": "n::M", "name": "Z"}], existing_symbols=["M"]), False),
        # plain new types
        (lambda: delta(added_types=[T("n::Alpha", 2), T("n::Beta", 2)], existing_symbols=["M"]), False),
    ])
    def test_io_route_rule(self, build, expected):
        led = ledger_of(build())
        assert any(u["scale"]["introduces_new_io_route"] for u in led["units"]) is expected

    def test_internal_types_excluded_from_public_counts_and_all_internal_unit_is_reference_only(self):
        led = ledger_of(delta(added_types=[T("n.engine::Sched", 5), T("n.internal.x::Clock", 2)], existing_symbols=[]),
                        config=None)
        for u in led["units"]:
            assert u["scale"]["new_public_types"] == 0 and u["scale"]["new_public_members"] == 0
            assert u["internal_symbols"] == types_of(u)
            assert u["dispositions"]["reference"]["action"] == "create"
            for s in ("docs", "kb", "blog", "products"):
                d = u["dispositions"][s]
                assert d["action"] == "none" and d["status"] == "none_justified"
                assert d["rationale"].startswith("none_justified:internal")

    def test_internal_segments_come_from_config(self):
        c = cfg_with(["internal_namespace_segments"], ["secret"])
        led = ledger_of(delta(added_types=[T("n.engine::Sched", 5), T("n.secret::Hid", 1)], existing_symbols=[]), config=c)
        sched = by_type(led["units"], "Sched")
        assert sched["scale"]["new_public_types"] == 1 and sched["internal_symbols"] == []
        assert by_type(led["units"], "Hid")["scale"]["new_public_types"] == 0


# ── placement: boundary tests (frozen initial values) ─────────────────────────────────────────

def scale(types=0, members=0, route=False, example=True, consts=0, formats=0, internal=0, options=False):
    return {"new_public_types": types, "new_internal_types": internal, "new_public_members": members,
            "new_enum_constants": consts, "new_formats": formats, "introduces_new_io_route": route,
            "introduces_options_type": options, "verified_example_present": example,
            "share_of_public_surface": None, "snippet_candidates": []}


BLOCKS = [{"id": "blk-a", "path": "products/page.md", "terms": ["render", "Output"]},
          {"id": "blk-b", "path": "products/other.md", "terms": ["Chart"]}]


def products(sc, blocks=BLOCKS, terms=("RenderJob",)):
    return cd.decide_products(sc, unit_terms=list(terms), candidate_blocks=blocks, config=CFG)


class TestProductsPlacementFrozenValues:
    def test_frozen_values_in_yaml(self):
        p = CFG["placement"]["products"]
        assert p["dedicated_section"] == {"min_public_types": 5, "min_public_members_without_route": 15,
                                          "require_verified_example": True}
        assert (p["mention"]["min_public_types"], p["mention"]["min_public_members"],
                p["mention"]["min_new_enum_constants"]) == (1, 3, 1)

    @pytest.mark.parametrize("types,members,route,example,expected", [
        (5, 0, True, True, "dedicated_section"),    # route path
        (4, 0, True, True, "mention"),              # types one below
        (5, 0, False, True, "mention"),             # no route, members 0 < 15
        (5, 14, False, True, "mention"),            # members one below
        (5, 15, False, True, "dedicated_section"),  # members exactly 15
        (5, 15, True, False, "mention"),            # no verified example
        (5, 15, True, None, "mention"),             # None counts as absent
        (9, 40, True, True, "dedicated_section"),
    ])
    def test_dedicated_section_boundaries(self, types, members, route, example, expected):
        d = products(scale(types, members, route, example))
        assert d["placement"] == expected
        assert d["action"] == ("create" if expected == "dedicated_section" else "mention")

    @pytest.mark.parametrize("sc,expected", [
        (scale(types=1), "mention"), (scale(types=0, members=3), "mention"), (scale(members=2), "none"),
        (scale(consts=1), "mention"), (scale(formats=1), "mention"), (scale(), "none"),
    ])
    def test_mention_boundaries(self, sc, expected):
        d = products(sc)
        assert (d["placement"] if d["action"] != "none" else "none") == expected

    def test_none_requires_rationale(self):
        d = products(scale(members=2))
        assert d["action"] == "none" and d["status"] == "none_justified" and d["rationale"].strip()

    def test_dedicated_section_target_is_the_products_target(self):
        d = cd.decide_products(scale(5, 0, True, True), unit_terms=["x"], candidate_blocks=[], config=CFG,
                               new_section_target="products/new.md")
        assert d["target"] == "products/new.md" and d["placement"] == "dedicated_section"


class TestMentionBlockMatching:
    def test_highest_overlap_wins(self):
        d = products(scale(types=1), terms=["RenderJob", "OutputMode"])
        assert d["action"] == "mention" and d["target"] == "products/page.md#blk-a"
        assert d["placement"] == "mention"

    def test_no_match_is_unplaced_never_promoted(self):
        d = products(scale(types=9, members=99, route=False, example=False), terms=["Zzz"])
        assert d["placement"] == "unplaced" and d["target"] is None and d["action"] == "mention"
        assert d["status"] == "pending"

    def test_no_candidate_blocks_is_unplaced(self):
        assert products(scale(types=1), blocks=[])["placement"] == "unplaced"

    def test_tie_broken_by_path_then_id(self):
        blocks = [{"id": "b", "path": "z.md", "terms": ["render"]}, {"id": "a", "path": "a.md", "terms": ["render"]}]
        assert products(scale(types=1), blocks=blocks)["target"] == "a.md#a"

    def test_min_overlap_from_config(self):
        c = cfg_with(["placement", "products", "block_match", "min_overlap"], 2)
        d = cd.decide_products(scale(types=1), unit_terms=["RenderJob"], candidate_blocks=BLOCKS, config=c)
        assert d["placement"] == "unplaced"
        d2 = cd.decide_products(scale(types=1), unit_terms=["RenderJob", "OutputMode"], candidate_blocks=BLOCKS, config=c)
        assert d2["target"] == "products/page.md#blk-a"

    def test_generic_tokens_do_not_count_as_overlap(self):
        blocks = [{"id": "g", "path": "g.md", "terms": ["Manager Helper Utils"]}]
        assert products(scale(types=1), blocks=blocks, terms=["FooManagerHelper"])["placement"] == "unplaced"


class TestOtherSurfaceRules:
    def decide(self, sc, kind="type-group", **kw):
        return cd.decide_dispositions(sc, kind=kind, unit_terms=["RenderJob"], surface_targets=TARGETS,
                                      candidate_blocks=BLOCKS, config=CFG, **kw)

    def test_reference_creates_for_every_new_public_type(self):
        assert self.decide(scale(types=1))["reference"]["action"] == "create"
        assert self.decide(scale(types=0, members=1))["reference"]["action"] == "update"
        assert self.decide(scale(types=0, consts=1))["reference"]["action"] == "update"
        r = self.decide(scale(types=0, formats=2), kind="format-route")["reference"]
        assert r["action"] == "none" and r["rationale"].strip()

    @pytest.mark.parametrize("types,route,expected", [
        (3, False, "create"), (2, False, "update"), (1, False, "update"), (0, False, "none"), (1, True, "create")])
    def test_docs_boundaries(self, types, route, expected):
        assert self.decide(scale(types=types, route=route))["docs"]["action"] == expected

    def test_docs_update_by_members(self):
        assert self.decide(scale(members=3))["docs"]["action"] == "update"
        assert self.decide(scale(members=2))["docs"]["action"] == "none"

    @pytest.mark.parametrize("sc,expected", [
        (scale(types=1, options=True), "create"), (scale(types=1, route=True), "create"),
        (scale(types=1), "update"), (scale(types=0, members=9), "none")])
    def test_kb_boundaries(self, sc, expected):
        assert self.decide(sc)["kb"]["action"] == expected

    @pytest.mark.parametrize("types,kind,expected", [
        (5, "route", "create"), (4, "route", "none"), (5, "type-group", "none"), (5, "api-extension", "none")])
    def test_blog_boundaries(self, types, kind, expected):
        assert self.decide(scale(types=types), kind=kind)["blog"]["action"] == expected

    def test_blog_format_route_by_formats(self):
        assert self.decide(scale(formats=3), kind="format-route")["blog"]["action"] == "create"
        assert self.decide(scale(formats=2), kind="format-route")["blog"]["action"] == "none"

    def test_every_none_has_rationale_and_status(self):
        for sc in (scale(), scale(types=1), scale(members=1), scale(formats=1)):
            for surface, d in self.decide(sc, kind="type-group").items():
                if d["action"] == "none":
                    assert d["status"] == "none_justified" and d["rationale"].strip(), surface
                else:
                    assert d["status"] == "pending" and d["rationale"].strip()

    def test_thresholds_live_in_config_not_code(self):
        c = cfg_with(["placement", "docs", "create_min_public_types"], 2)
        d = cd.decide_dispositions(scale(types=2), kind="type-group", unit_terms=["x"], surface_targets=TARGETS,
                                   candidate_blocks=BLOCKS, config=c)
        assert d["docs"]["action"] == "create"


# ── ledger: build / validate / satisfaction ─────────────────────────────────────────────────────

class TestBuildAndValidate:
    def test_ledger_shape_and_determinism(self):
        a = ledger_of(java_style(), candidate_blocks=BLOCKS, verified_example_symbols={"RenderJob"})
        b = ledger_of(java_style(), candidate_blocks=BLOCKS, verified_example_symbols={"RenderJob"})
        assert cd.dump_ledger(a) == cd.dump_ledger(b)
        assert a["schema_version"] == 1 and a["family"] == "fam" and a["platform"] == "plat"
        assert a["upstream_head"] == "e" * 40 and a["symbol_level"] is True
        assert json.loads(cd.dump_ledger(a)) == a
        for u in a["units"]:
            assert set(u["dispositions"]) == set(SURFACES)
            for d in u["dispositions"].values():
                assert set(d) >= {"action", "target", "rationale", "status", "evidence_paths"}
                assert d["action"] in ("create", "update", "mention", "none")
                assert d["status"] in ("pending", "satisfied", "none_justified")

    def test_validate_clean_when_all_placed(self):
        led = ledger_of(java_style(), candidate_blocks=BLOCKS, verified_example_symbols={"RenderJob"},
                        availability={})
        assert cd.validate_ledger(led) == []

    def test_validate_flags_unplaced_mention(self):
        led = ledger_of(py_style(), candidate_blocks=[])
        errs = cd.validate_ledger(led)
        assert any("unplaced" in e and "products" in e for e in errs)

    def test_validate_missing_surface_and_bad_schema(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS)
        bad = copy.deepcopy(led)
        del bad["units"][0]["dispositions"]["kb"]
        bad["schema_version"] = 2
        errs = cd.validate_ledger(bad)
        assert any("schema_version" in e for e in errs) and any("kb" in e and "missing" in e for e in errs)

    def test_validate_none_needs_rationale_and_status(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS)
        u = led["units"][0]
        u["dispositions"]["blog"].update(action="none", status="none_justified", rationale="  ")
        u["dispositions"]["kb"].update(action="none", status="pending", rationale="because")
        errs = cd.validate_ledger(led)
        assert any("blog" in e and "rationale" in e for e in errs)
        assert any("kb" in e and "none_justified" in e for e in errs)

    def test_validate_target_required_for_create_update_mention(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS, surface_targets={})
        errs = cd.validate_ledger(led)
        assert any("target" in e for e in errs)

    def test_validate_id_must_match_symbols(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS)
        led["units"][0]["id"] = "CU-00000000"
        assert any("id" in e and "does not match" in e for e in cd.validate_ledger(led))

    def test_validate_duplicate_symbols_unless_declared(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS)
        sym = led["units"][0]["symbols"][0]
        led["units"][1]["symbols"] = sorted(led["units"][1]["symbols"] + [sym])
        led["units"][1]["id"] = cd.unit_id(led["units"][1]["symbols"], led["units"][1]["formats"])
        assert any("duplicate" in e and sym in e for e in cd.validate_ledger(led))
        led["declared_shared_symbols"] = [sym]
        assert not any("duplicate" in e for e in cd.validate_ledger(led))

    def test_validate_flags_statuses_that_claim_satisfied_at_plan_time_without_evidence(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS)
        led["units"][0]["dispositions"]["docs"]["status"] = "satisfied"
        assert any("docs" in e and "evidence" in e for e in cd.validate_ledger(led))

    def test_availability_per_unit_and_unconfirmed_flags(self):
        avail = {"org.acme.render::RenderJob": "released", "org.acme.render::RenderOptions": "unreleased"}
        led = ledger_of(java_style(), availability=avail, candidate_blocks=BLOCKS)
        assert by_type(led["units"], "RenderJob")["availability"] == "unreleased"
        assert by_type(led["units"], "Scheduler")["availability"] == "unknown"   # nothing known => unknown

    def test_unconfirmed_flags_from_delta(self):
        d = net_style()
        d["name_collisions"] = [{"name": "ChartTheme"}]
        d["unconfirmed"] = {"extraction_drift_suspect": ["Acme.Sheets::Workbook"], "breaking_unconfirmed": ["Cell"]}
        d["ground_truth"] = {"tier": "GT-2", "symbol_level": True}
        led = ledger_of(d, candidate_blocks=BLOCKS)
        flags = by_type(led["units"], "ChartTheme")["unconfirmed_flags"]
        assert "name_collision:ChartTheme" in flags
        assert "extraction_drift_suspect:Acme.Sheets::Workbook" in flags
        assert "ground_truth:GT-2" in flags
        assert not any(f.startswith("breaking_unconfirmed") for f in flags)  # Cell is not in this unit

    def test_gt2_only_delta_is_not_symbol_level(self):
        d = cd.from_adapter_delta({"ground_truth_tier": "GT-2", "api_path_files": ["x"], "method": "file-level"})
        led = ledger_of(d)
        assert led["symbol_level"] is False and led["units"] == [] and led["ground_truth_tier"] == "GT-2"

    def test_gt1_adapter_delta_maps_types_members_constants(self):
        adapter = {"ground_truth_tier": "GT-1", "added_types": [
            {"type": "org.acme.fresh.Loader", "decl": "public class org.acme.fresh.Loader", "members": 2,
             "member_list": ["public org.acme.fresh.Loader(org.acme.fresh.Source);", "public void run();"],
             "is_enum": False}],
            "removed_types": [], "changed_types": {
                "org.acme.core.Mode": {"added": ["public static final org.acme.core.Mode X;"], "removed": [],
                                       "enum_constants_added": ["X"], "enum_constants_removed": []}}}
        d = cd.from_adapter_delta(adapter)
        assert d["ground_truth"] == {"tier": "GT-1", "symbol_level": True}
        assert [t["qualified"] for t in d["added_types"]] == ["org.acme.fresh::Loader"]
        assert d["added_types"][0]["member_count"] == 2
        assert d["enum_constants_added"] == [{"owner": "org.acme.core::Mode", "name": "X"}]
        # enum constants are not double counted as plain added members
        assert d["added_members"] == []


class TestValidateStages:
    def test_close_is_the_default_and_unchanged(self):
        led = ledger_of(py_style(), candidate_blocks=[])
        assert cd.validate_ledger(led) == cd.validate_ledger(led, stage="close") == cd.validate_ledger_ex(led)[0]
        assert any("unplaced" in e for e in cd.validate_ledger(led))

    def test_plan_demotes_unplaced_and_missing_targets_to_warnings(self):
        led = ledger_of(py_style(), candidate_blocks=[], surface_targets={})
        errs, warns = cd.validate_ledger_ex(led, stage="plan")
        assert errs == []
        assert any("unplaced" in w for w in warns) and any("requires a target" in w for w in warns)
        assert cd.validate_ledger(led, stage="plan") == []

    def test_plan_still_errors_on_structure(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS)
        u = led["units"][0]
        u["id"] = "CU-00000000"
        del u["dispositions"]["kb"]
        u["dispositions"]["blog"].update(action="none", status="none_justified", rationale="")
        u["dispositions"]["docs"]["status"] = "satisfied"
        led["schema_version"] = 9
        text = " ".join(cd.validate_ledger(led, stage="plan"))
        for needle in ("schema_version", "does not match", "missing", "rationale", "evidence"):
            assert needle in text

    def test_unknown_stage_rejected(self):
        with pytest.raises(ValueError):
            cd.validate_ledger({}, stage="later")


class TestSatisfaction:
    ROOT = PurePosixPath("c")

    def fs(self, files):
        files = {str(self.ROOT / k): v for k, v in files.items()}

        def reader(p):
            return files.get(PurePosixPath(p).as_posix())

        def lister(p):
            pre = PurePosixPath(p).as_posix().rstrip("/") + "/"
            return sorted(PurePosixPath(k) for k in files if k.startswith(pre))

        return reader, lister

    def led(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS,
                        surface_targets={"reference": "ref/", "docs": "docs/p.md", "kb": "kb/", "blog": "blog/",
                                         "products": "prod/new.md"})
        return led

    def test_status_computed_never_trusted(self):
        led = self.led()
        theme = by_type(led["units"], "ChartTheme")
        for d in theme["dispositions"].values():
            d["status"] = "satisfied" if d["action"] != "none" else "none_justified"
        reader, lister = self.fs({})
        rep = cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister)
        row = next(u for u in rep["units"] if u["id"] == theme["id"])
        assert all(s["status"] != "satisfied" for s in row["surfaces"].values() if s["action"] != "none")
        assert rep["all_satisfied"] is False

    def test_file_mentioning_symbols_satisfies_and_evidence_is_recorded(self):
        led = self.led()
        theme = by_type(led["units"], "ChartTheme")
        files = {"docs/p.md": "ChartPalette and ChartTheme explained", "ref/ChartPalette.md": "ChartPalette ref",
                 "ref/ChartTheme.md": "ChartTheme ref ChartPalette", "kb/a.md": "ChartTheme how-to ChartPalette",
                 "prod/new.md": "ChartTheme ChartPalette", "blog/x.md": "ChartTheme"}
        reader, lister = self.fs(files)
        rep = cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister)
        row = next(u for u in rep["units"] if u["id"] == theme["id"])
        ref = row["surfaces"]["reference"]
        assert ref["status"] == "satisfied" and ref["evidence_paths"] == ["ref/ChartPalette.md", "ref/ChartTheme.md"]
        assert row["surfaces"]["docs"]["evidence_paths"] == ["docs/p.md"]

    def test_term_ratio_threshold_both_sides(self):
        led = self.led()
        theme = by_type(led["units"], "ChartTheme")
        # reference requires ratio 1.0: one of two types mentioned -> not satisfied
        reader, lister = self.fs({"ref/a.md": "only ChartTheme here"})
        row = next(u for u in cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister)["units"]
                   if u["id"] == theme["id"])
        assert row["surfaces"]["reference"]["status"] == "pending"
        assert "ChartPalette" in " ".join(row["surfaces"]["reference"]["problems"])
        # docs requires 0.5: one of two is enough
        reader, lister = self.fs({"docs/p.md": "only ChartTheme here"})
        row = next(u for u in cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister)["units"]
                   if u["id"] == theme["id"])
        assert row["surfaces"]["docs"]["status"] == "satisfied"

    def test_missing_target_file_and_zero_term_hits_are_pending(self):
        led = self.led()
        theme = by_type(led["units"], "ChartTheme")
        reader, lister = self.fs({"docs/p.md": "nothing relevant"})
        row = next(u for u in cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister)["units"]
                   if u["id"] == theme["id"])
        assert row["surfaces"]["docs"]["status"] == "pending"
        assert row["surfaces"]["kb"]["status"] == "pending"

    def test_none_justified_requires_rationale_at_close_time(self):
        led = self.led()
        theme = by_type(led["units"], "ChartTheme")
        theme["dispositions"]["blog"].update(action="none", rationale="")
        reader, lister = self.fs({})
        row = next(u for u in cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister)["units"]
                   if u["id"] == theme["id"])
        assert row["surfaces"]["blog"]["status"] == "pending"

    def test_mention_target_fragment_is_stripped_and_unplaced_never_satisfied(self):
        led = ledger_of(py_style(), candidate_blocks=[{"id": "csv", "path": "prod/p.md", "terms": ["Csv", "Reader"]}],
                        surface_targets=TARGETS)
        unit = by_type(led["units"], "CsvReader")
        assert unit["dispositions"]["products"]["target"] == "prod/p.md#csv"
        reader, lister = self.fs({"prod/p.md": "We now read CsvReader and CsvLegacyParser."})
        row = next(u for u in cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister)["units"]
                   if u["id"] == unit["id"])
        assert row["surfaces"]["products"]["status"] == "satisfied"
        led2 = ledger_of(py_style(), candidate_blocks=[], surface_targets=TARGETS)
        unit2 = by_type(led2["units"], "CsvReader")
        row2 = next(u for u in cd.satisfaction_report(led2, [self.ROOT], reader=reader, lister=lister)["units"]
                    if u["id"] == unit2["id"])
        assert row2["surfaces"]["products"]["status"] == "pending"
        assert row2["surfaces"]["products"]["placement"] == "unplaced"

    def test_multiple_content_roots(self):
        led = self.led()
        theme = by_type(led["units"], "ChartTheme")
        r1 = PurePosixPath("c1")
        files = {"c2/docs/p.md": "ChartTheme ChartPalette"}
        reader = lambda p: files.get(PurePosixPath(p).as_posix())  # noqa: E731
        lister = lambda p: []  # noqa: E731
        rep = cd.satisfaction_report(led, [r1, PurePosixPath("c2")], reader=reader, lister=lister)
        row = next(u for u in rep["units"] if u["id"] == theme["id"])
        assert row["surfaces"]["docs"]["status"] == "satisfied" and row["surfaces"]["docs"]["evidence_paths"] == ["docs/p.md"]

    def test_report_is_deterministic(self):
        led = self.led()
        reader, lister = self.fs({"docs/p.md": "ChartTheme"})
        a = json.dumps(cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister), sort_keys=True)
        b = json.dumps(cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister), sort_keys=True)
        assert a == b


# ── from_knowledge_delta ────────────────────────────────────────────────────────────────────────

class TestFromKnowledgeDelta:
    def entries(self):
        return [
            {"name": "Doc", "canonical_namespace": "org.acme.core", "visibility": "public",
             "methods": [{"name": "open", "params": [], "return_type": ""}], "properties": []},
            {"name": "Mode", "canonical_namespace": "org.acme.core", "visibility": "public",
             "enum_members": [{"name": "A"}, {"name": "B"}, {"name": "C"}]},
            {"name": "LoadOptions", "canonical_namespace": "org.acme.core", "visibility": "public",
             "methods": [{"name": "LoadOptions", "params": [{"name": "m", "type": "Mode"}], "return_type": ""}]},
            {"name": "Hidden", "canonical_namespace": "org.acme.core", "visibility": "private", "methods": []},
        ]

    def kd(self):
        return {"new_apis_qualified": ["org.acme.core::LoadOptions", "org.acme.core::Hidden"],
                "removed_apis_qualified": [], "modified_apis_qualified": ["org.acme.core::Doc", "org.acme.core::Mode"],
                "name_collisions": [],
                "api_signature_changes": {
                    "Doc": {"added_methods": ["openWith"], "removed_methods": [], "added_properties": [],
                            "removed_properties": []},
                    "Mode": {"added_methods": [], "removed_methods": [], "added_properties": [],
                             "removed_properties": [], "enum_members_added": ["C"], "enum_members_removed": []}}}

    def test_adapter_builds_delta_from_knowledge_delta_and_api_surface(self):
        entries = self.entries()
        entries[0]["methods"].append({"name": "openWith", "params": [{"name": "o", "type": "LoadOptions"}],
                                      "return_type": "void"})
        d = cd.from_knowledge_delta(self.kd(), {"formats_added": [{"name": "TAB", "ext": ".tab"}]}, api_surface=entries)
        assert [t["qualified"] for t in d["added_types"]] == ["org.acme.core::LoadOptions"]  # private dropped
        assert d["added_types"][0]["member_count"] == 1
        assert d["added_members"] == [{"owner": "org.acme.core::Doc", "name": "openWith",
                                       "signature_refs": ["LoadOptions", "void"]}]
        assert d["enum_constants_added"] == [{"owner": "org.acme.core::Mode", "name": "C"}]
        assert d["formats_added"] == [{"name": "TAB", "ext": ".tab"}]
        assert d["ground_truth"]["symbol_level"] is True
        assert "org.acme.core::Doc" in d["existing_symbols"] and "org.acme.core::LoadOptions" not in d["existing_symbols"]
        assert d["public_surface_size"] > 0
        led = ledger_of(d, candidate_blocks=BLOCKS)
        unit = by_type(led["units"], "LoadOptions")
        assert "org.acme.core::Doc.openWith" in unit["symbols"]   # attached through the signature
        assert any("org.acme.core::Mode.C" in u["enum_constants"] for u in led["units"])

    def test_absent_keys_are_empty(self):
        d = cd.from_knowledge_delta({}, None)
        assert d["added_types"] == [] and d["added_members"] == [] and d["formats_added"] == []
        assert d["existing_symbols"] is None and d["public_surface_size"] is None
        assert d["unconfirmed"] == {"breaking_unconfirmed": [], "extraction_drift_suspect": []}

    def test_unconfirmed_and_collisions_carried(self):
        kd = self.kd()
        kd["breaking_unconfirmed"] = {"Doc": {"removed_methods": ["x"]}}
        kd["extraction_drift_suspect"] = [{"name": "Doc", "qualified": "org.acme.core::Doc"}]
        kd["name_collisions"] = [{"name": "Doc", "old": [], "new": [], "added": [], "removed": [], "modified": []}]
        d = cd.from_knowledge_delta(kd, None)
        assert d["unconfirmed"] == {"breaking_unconfirmed": ["Doc"], "extraction_drift_suspect": ["org.acme.core::Doc"]}
        assert d["name_collisions"][0]["name"] == "Doc"

    def test_ambiguous_modified_owner_keeps_simple_name_and_flags_collision(self):
        kd = {"new_apis_qualified": [], "modified_apis_qualified": ["a::Doc", "b::Doc"],
              "name_collisions": [{"name": "Doc", "old": ["a::Doc", "b::Doc"], "new": ["a::Doc", "b::Doc"],
                                   "added": [], "removed": [], "modified": ["a::Doc", "b::Doc"]}],
              "api_signature_changes": {"Doc": {"added_methods": ["m"], "removed_methods": [],
                                                 "added_properties": [], "removed_properties": []}}}
        d = cd.from_knowledge_delta(kd, None)
        assert d["added_members"][0]["owner"] == "Doc"
        led = ledger_of(d)
        assert any(f == "name_collision:Doc" for u in led["units"] for f in u["unconfirmed_flags"])

    def test_python_style_empty_param_types_give_no_refs(self):
        entries = [{"name": "Table", "file": "acme/t.py", "methods": [{"name": "add", "params": [{"name": "x", "type": ""}],
                                                                       "return_type": ""}]},
                   {"name": "Row", "file": "acme/r.py", "methods": []}]
        kd = {"new_apis_qualified": ["acme/r.py::Row"], "modified_apis_qualified": ["acme/t.py::Table"],
              "api_signature_changes": {"Table": {"added_methods": ["add"], "removed_methods": [],
                                                  "added_properties": [], "removed_properties": []}}}
        d = cd.from_knowledge_delta(kd, None, api_surface=entries)
        assert d["added_members"] == [{"owner": "acme/t.py::Table", "name": "add", "signature_refs": []}]


# ── generality gate G-1 ─────────────────────────────────────────────────────────────────────────

class TestOwnerNameCollisions:
    """B5c: members whose owner simple name collides are resolved against the NEW api_surface."""

    def surface(self, shared_in_both=True):
        facades = {"name": "Form", "canonical_namespace": "org.acme.facades", "visibility": "public",
                   "methods": [{"name": "exportJson"}, {"name": "other"}] + ([{"name": "shared"}] if shared_in_both else [])}
        forms = {"name": "Form", "canonical_namespace": "org.acme.forms", "visibility": "public",
                 "methods": [{"name": "fill"}, {"name": "other"}] + ([{"name": "shared"}] if shared_in_both else [])}
        forms["enum_members"] = [{"name": "MODE_X"}]
        return [facades, forms]

    def kd(self, added=("exportJson", "fill", "shared"), consts=()):
        sig = {"added_methods": list(added), "removed_methods": [], "added_properties": [], "removed_properties": []}
        if consts:
            sig.update(enum_members_added=list(consts), enum_members_removed=[])
        return {"new_apis_qualified": [], "modified_apis_qualified": ["org.acme.facades::Form", "org.acme.forms::Form"],
                "name_collisions": [{"name": "Form", "old": [], "new": [], "added": [], "removed": [],
                                     "modified": ["org.acme.facades::Form", "org.acme.forms::Form"]}],
                "api_signature_changes": {"Form": sig}}

    def test_member_in_exactly_one_candidate_is_qualified(self):
        d = cd.from_knowledge_delta(self.kd(), None, api_surface=self.surface())
        owners = {m["name"]: m for m in d["added_members"]}
        assert owners["exportJson"]["owner"] == "org.acme.facades::Form" and "owner_candidates" not in owners["exportJson"]
        assert owners["fill"]["owner"] == "org.acme.forms::Form"
        assert d["ambiguous_resolved"] == 2

    def test_member_in_several_candidates_stays_ambiguous_with_candidates(self):
        d = cd.from_knowledge_delta(self.kd(), None, api_surface=self.surface())
        shared = next(m for m in d["added_members"] if m["name"] == "shared")
        assert shared["owner"] == "Form"
        assert shared["owner_candidates"] == ["org.acme.facades::Form", "org.acme.forms::Form"]

    def test_member_in_no_candidate_is_ambiguous_over_all_candidates(self):
        d = cd.from_knowledge_delta(self.kd(added=("ghost",)), None, api_surface=self.surface())
        assert d["added_members"][0]["owner_candidates"] == ["org.acme.facades::Form", "org.acme.forms::Form"]
        assert d["ambiguous_resolved"] == 0

    def test_enum_constants_resolve_the_same_way(self):
        d = cd.from_knowledge_delta(self.kd(added=(), consts=("MODE_X",)), None, api_surface=self.surface())
        assert d["enum_constants_added"] == [{"owner": "org.acme.forms::Form", "name": "MODE_X"}]
        assert d["ambiguous_resolved"] == 1

    def test_without_api_surface_stays_unresolved_simple_owner(self):
        d = cd.from_knowledge_delta(self.kd(), None)
        assert {m["owner"] for m in d["added_members"]} == {"Form"} and d["ambiguous_resolved"] == 0
        assert all("owner_candidates" not in m for m in d["added_members"])

    def test_ledger_symbols_are_qualified_and_ambiguous_symbols_listed(self):
        d = cd.from_knowledge_delta(self.kd(), None, api_surface=self.surface())
        led = ledger_of(d, candidate_blocks=BLOCKS)
        flat = {s for u in led["units"] for s in u["symbols"]}
        assert {"org.acme.facades::Form.exportJson", "org.acme.forms::Form.fill", "Form.shared"} <= flat
        amb = [a for u in led["units"] for a in u["ambiguous_symbols"]]
        assert amb == [{"symbol": "Form.shared", "candidates": ["org.acme.facades::Form.shared", "org.acme.forms::Form.shared"]}]
        assert all(u["ambiguous_symbols"] == [] for u in led["units"] if "Form.shared" not in u["symbols"])
        assert cd.validate_ledger(led, stage="plan") == []
        assert any("name_collision:Form" in u["unconfirmed_flags"] for u in led["units"])

    def test_ambiguous_symbol_released_only_if_all_candidates_released(self):
        d = cd.from_knowledge_delta(self.kd(added=("shared",)), None, api_surface=self.surface())
        a, b = "org.acme.facades::Form.shared", "org.acme.forms::Form.shared"
        rel = {"state": "released", "available_since": "26.9.0", "since_basis": "current_only"}
        both = ledger_of(d, availability={a: dict(rel), b: dict(rel)}, availability_context={"release_version": "26.9.0"})
        (u,) = both["units"]
        assert (u["availability"], u["available_since"]) == ("released", "26.9.0")
        one = ledger_of(d, availability={a: dict(rel), b: {"state": "unreleased", "available_since": None}})
        assert one["units"][0]["availability"] == "unknown"
        none = ledger_of(d, availability={a: dict(rel)})
        assert none["units"][0]["availability"] == "unknown" and none["units"][0]["available_since"] is None

    def test_resolved_counter_lands_in_availability_context(self):
        d = cd.from_knowledge_delta(self.kd(), None, api_surface=self.surface())
        led = ledger_of(d, availability={}, candidate_blocks=BLOCKS)
        assert led["availability_context"]["symbol_counts"]["ambiguous_resolved"] == 2

    def test_validate_rejects_malformed_ambiguous_symbols_and_accepts_absent_field(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS)
        for u in led["units"]:
            u.pop("ambiguous_symbols", None)               # older ledgers have no such field
        assert cd.validate_ledger(led, stage="plan") == []
        led["units"][0]["ambiguous_symbols"] = [{"symbol": "Nope.x", "candidates": []}]
        errs = " ".join(cd.validate_ledger(led, stage="plan"))
        assert "ambiguous_symbols" in errs


class TestEvidenceHygiene:
    """B1: frontmatter is internal metadata, draft and non-English pages are never evidence."""
    ROOT = PurePosixPath("c")

    def fs(self, files):
        files = {str(self.ROOT / k): v for k, v in files.items()}
        reader = lambda p: files.get(PurePosixPath(p).as_posix())  # noqa: E731

        def lister(p):
            pre = PurePosixPath(p).as_posix().rstrip("/") + "/"
            return sorted(PurePosixPath(k) for k in files if k.startswith(pre))

        return reader, lister

    def led(self):
        return ledger_of(net_style(), candidate_blocks=BLOCKS,
                         surface_targets={"reference": "ref/", "docs": "docs/p.md", "kb": "kb/", "blog": "blog/",
                                          "products": "prod/new.md"})

    def row(self, files, surface="docs"):
        led = self.led()
        theme = by_type(led["units"], "ChartTheme")
        reader, lister = self.fs(files)
        rep = cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister)
        return next(u for u in rep["units"] if u["id"] == theme["id"])["surfaces"][surface], rep

    FM = "---\ntitle: T\n{extra}evidence:\n  apis: [ChartTheme, ChartPalette]\n---\n"

    def test_frontmatter_only_mention_is_not_evidence(self):
        page = self.FM.format(extra="") + "Nothing relevant in the body."
        r, _ = self.row({"docs/p.md": page})
        assert r["status"] == "pending" and r["evidence_paths"] == []

    def test_body_mention_with_frontmatter_is_evidence(self):
        page = self.FM.format(extra="") + "The ChartTheme and ChartPalette classes."
        r, _ = self.row({"docs/p.md": page})
        assert r["status"] == "satisfied" and r["evidence_paths"] == ["docs/p.md"]

    @pytest.mark.parametrize("marker", ["draft: true", "draft: True", "draft:   true"])
    def test_draft_pages_are_refused_with_a_reason(self, marker):
        page = self.FM.format(extra=marker + "\n") + "The ChartTheme and ChartPalette classes."
        r, rep = self.row({"docs/p.md": page})
        assert r["status"] == "pending" and r["refused"] == [{"path": "docs/p.md", "reason": "draft"}]
        assert any(x["path"] == "docs/p.md" and x["reason"] == "draft" and x["surface"] == "docs" for x in rep["refused"])

    def test_toml_draft_is_refused(self):
        page = "+++\ndraft = true\n+++\nThe ChartTheme and ChartPalette classes."
        r, _ = self.row({"docs/p.md": page})
        assert r["refused"][0]["reason"] == "draft"

    def test_draft_false_is_fine(self):
        page = self.FM.format(extra="draft: false\n") + "The ChartTheme and ChartPalette classes."
        assert self.row({"docs/p.md": page})[0]["status"] == "satisfied"

    def test_locale_suffixed_and_locale_directory_files_are_refused(self):
        body = "The ChartTheme and ChartPalette classes."
        r, _ = self.row({"kb/page.fr.md": body, "kb/fr/other.md": body, "kb/page.md": "unrelated"}, "kb")
        assert r["status"] == "pending"
        assert sorted((x["path"], x["reason"]) for x in r["refused"]) == [
            ("kb/fr/other.md", "locale-directory"), ("kb/page.fr.md", "locale-suffixed")]

    def test_english_page_next_to_refused_ones_still_satisfies(self):
        body = "The ChartTheme and ChartPalette classes."
        r, _ = self.row({"kb/page.fr.md": body, "kb/page.md": body}, "kb")
        assert r["status"] == "satisfied" and r["evidence_paths"] == ["kb/page.md"]
        assert [x["path"] for x in r["refused"]] == ["kb/page.fr.md"]

    def test_five_draft_pages_with_frontmatter_evidence_fail_every_surface(self):
        files = {}
        for surface, path in (("reference", "ref/a.md"), ("docs", "docs/p.md"), ("kb", "kb/a.md"), ("blog", "blog/a.md"),
                              ("products", "prod/new.md")):
            files[path] = self.FM.format(extra="draft: true\n") + "empty body"
        led = self.led()
        reader, lister = self.fs(files)
        rep = cd.satisfaction_report(led, [self.ROOT], reader=reader, lister=lister)
        assert rep["all_satisfied"] is False


class TestMentionMatching:
    """m3: case-sensitive identifier matching; common-word symbols only in code or qualified."""

    def test_matching_is_case_sensitive_for_strong_terms(self):
        assert cd.find_mentions("The ChartTheme class", "ChartTheme")
        assert cd.find_mentions("the charttheme class", "ChartTheme") == []       # N10 mutant: case-insensitive
        assert cd.find_mentions("CHARTTHEME", "ChartTheme") == []
        assert cd.find_mentions("My ChartThemeExtra", "ChartTheme") == []         # word-bounded
        assert cd.find_mentions("`ChartTheme`", "ChartTheme")

    def test_a_case_insensitive_page_does_not_satisfy_a_unit(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS)
        theme = by_type(led["units"], "ChartTheme")
        files = {"c/docs/feature.md": "we describe charttheme and chartpalette here"}
        rep = cd.satisfaction_report(led, [PurePosixPath("c")], reader=lambda p: files.get(PurePosixPath(p).as_posix()),
                                     lister=lambda p: [])
        row = next(u for u in rep["units"] if u["id"] == theme["id"])
        assert row["surfaces"]["docs"]["status"] == "pending"

    @pytest.mark.parametrize("term", ["Result", "Typed", "Value", "Form"])
    def test_common_word_symbol_in_prose_does_not_count(self, term):
        assert cd.find_mentions(f"The {term} of the operation is fine. {term} again.", term) == []

    def test_common_word_symbol_counts_in_code_span_fence_or_qualified(self):
        assert cd.find_mentions("Call `Result` here", "Result")
        assert cd.find_mentions("```java\nResult r = f();\n```", "Result")
        assert cd.find_mentions("see org.acme.Result for details", "Result")
        assert cd.find_mentions("see org.acme::Result for details", "Result")
        assert cd.find_mentions("The Result is shown", "Result") == []

    def test_multiword_identifiers_are_strong(self):
        assert cd.find_mentions("The SaveOptions type", "SaveOptions") and cd.find_mentions("use csv_reader", "csv_reader")


class TestConfigIsRequired:
    """M5: every required key is enumerated; a damaged config fails closed naming the key."""

    def test_current_config_is_complete(self):
        assert cd.missing_config_keys(CFG) == []

    def test_required_keys_is_one_structure_of_dotted_paths(self):
        assert all(isinstance(k, tuple) and k for k in cd.REQUIRED_KEYS)
        assert ("satisfaction", "min_term_ratio", "reference") in cd.REQUIRED_KEYS
        assert ("availability", "coordinate_scan", "ignore_patterns") in cd.REQUIRED_KEYS

    @pytest.mark.parametrize("path", cd.REQUIRED_KEYS, ids=[".".join(k) for k in cd.REQUIRED_KEYS])
    def test_each_missing_key_is_named(self, path):
        import copy
        c = copy.deepcopy(CFG)
        node = c
        for k in path[:-1]:
            node = node[k]
        del node[path[-1]]
        assert cd.missing_config_keys(c) == [".".join(path)]
        with pytest.raises(cd.ConfigError, match=re.escape(".".join(path))):
            cd.build_ledger(net_style(), family="f", platform="p", config=c)
        errs = cd.validate_ledger(ledger_of(net_style(), candidate_blocks=BLOCKS), config=c)
        assert any(".".join(path) in e for e in errs)

    def test_reference_ratio_is_not_defaulted_in_code(self):
        led = ledger_of(net_style(), candidate_blocks=BLOCKS)
        c = cfg_with(["satisfaction", "min_term_ratio"], {"docs": 0.5})
        with pytest.raises(cd.ConfigError, match="satisfaction.min_term_ratio.reference"):
            cd.satisfaction_report(led, [PurePosixPath("c")], reader=lambda p: None, lister=lambda p: [], config=c)


class TestComputedActions:
    """B2a: the build persists computed_action/computed_placement per cell; weaker needs an override."""

    def led(self):
        return ledger_of(net_style(), candidate_blocks=BLOCKS + [{"id": "f", "path": "products/f.md",
                                                                  "terms": ["Font", "Fallback"]}])

    def test_every_cell_carries_computed_fields_equal_to_the_decision(self):
        for u in self.led()["units"]:
            for d in u["dispositions"].values():
                assert d["computed_action"] == d["action"] and d["computed_placement"] == d["placement"]
                assert "override" not in d

    def test_weaker_action_without_override_is_an_error_at_both_stages(self):
        led = self.led()
        cell = next(d for d in led["units"][0]["dispositions"].values() if d["action"] == "create")
        cell.update(action="none", status="none_justified", rationale="trust me", target=None, placement=None)
        for stage in ("plan", "close"):
            errs = cd.validate_ledger(led, stage=stage)
            assert any("weaker" in e and "computed_action" in e for e in errs), errs

    def test_valid_override_allows_the_downgrade(self):
        led = self.led()
        cell = next(d for d in led["units"][0]["dispositions"].values() if d["action"] == "create")
        cell.update(action="none", status="none_justified", rationale="reviewed", target=None, placement=None,
                    override={"token_id": "OV-1", "reason": "internal helper, reviewer agreed"})
        assert cd.validate_ledger(led) == []

    @pytest.mark.parametrize("override", [{}, {"token_id": "x"}, {"reason": "y"}, {"token_id": "", "reason": "y"},
                                          {"token_id": "x", "reason": "  "}, "OV-1"])
    def test_malformed_override_does_not_count(self, override):
        led = self.led()
        cell = next(d for d in led["units"][0]["dispositions"].values() if d["action"] == "create")
        cell.update(action="none", status="none_justified", rationale="r", target=None, placement=None, override=override)
        assert any("override" in e or "weaker" in e for e in cd.validate_ledger(led))

    def test_upgrades_and_unplaced_resolution_are_allowed(self):
        led = ledger_of(py_style(), candidate_blocks=[])
        prod = by_type(led["units"], "CsvReader")["dispositions"]["products"]
        assert prod["placement"] == "unplaced"
        prod.update(target="products/p.md#b", placement="mention")
        assert not any("weaker" in e for e in cd.validate_ledger(led))
        kb = led["units"][0]["dispositions"]["kb"]
        if kb["action"] == "none":
            kb.update(action="create", target="kb/", status="pending", rationale="more")
            assert not any("weaker" in e for e in cd.validate_ledger(led))

    def test_recompute_detects_a_rewritten_computed_action(self):
        led = self.led()
        assert cd.check_computed_actions(led, CFG) == []
        cell = next(d for d in led["units"][0]["dispositions"].values() if d["action"] == "create")
        cell.update(action="none", computed_action="none", status="none_justified", rationale="r", target=None,
                    placement=None, computed_placement=None)
        probs = cd.check_computed_actions(led, CFG)
        assert probs and "recomputed" in probs[0]


class TestLedgerBinding:
    """B2b/d: the ledger carries the delta fingerprint, symbol count, base and static limits."""

    def test_empty_delta_fingerprint_and_nonempty_differs(self):
        empty = ledger_of(delta())
        assert empty["delta_sha256"] == cd.empty_delta_sha256() and empty["units"] == []
        assert ledger_of(net_style())["delta_sha256"] != cd.empty_delta_sha256()

    def test_fingerprint_is_order_independent_and_symbol_count_matches_units(self):
        a = ledger_of(java_style())
        rev = java_style()
        rev["added_types"].reverse()
        assert ledger_of(rev)["delta_sha256"] == a["delta_sha256"]
        assert a["delta_symbol_count"] == sum(len(u["symbols"]) + len(u["formats"]) for u in a["units"])

    def test_base_and_static_limits_recorded(self):
        led = ledger_of(net_style(), base_sha="a" * 40, base_knowledge_commit="b" * 40)
        assert (led["base_sha"], led["base_knowledge_commit"]) == ("a" * 40, "b" * 40)
        assert led["delta_kinds_unseen"] == ["behavioural", "changelog", "readme"]
        assert any("overload" in x for x in led["known_limits"])
        assert led["public_surface_size"] is None


class TestWorth:
    """Design item 1: per-symbol worth, internal helpers leave scale and non-reference dispositions."""

    def delta(self):
        return delta(added_types=[T("ns::SaveOptions", 4), T("ns::SaveResult", 3), T("ns::InternalHelper", 6)],
                     existing_symbols=["Doc"])

    def test_worth_override_at_build_excludes_the_symbol_from_scale(self):
        base = ledger_of(self.delta(), candidate_blocks=BLOCKS)["units"][0]["scale"]
        led = ledger_of(self.delta(), candidate_blocks=BLOCKS,
                        worth_overrides=[{"symbol": "ns::InternalHelper", "worth": "internal", "reason": "pipeline type"}])
        u = led["units"][0]
        assert u["scale"]["new_public_types"] == base["new_public_types"] - 1
        assert u["scale"]["new_internal_types"] == base["new_internal_types"] + 1
        assert u["scale"]["new_public_members"] == base["new_public_members"] - 6
        assert u["internal_symbols"] == ["ns::InternalHelper"]
        assert u["symbol_worth"] == {"ns::InternalHelper": {"worth": "internal", "reason": "pipeline type"}}

    def test_unknown_symbol_or_bad_worth_is_an_error(self):
        with pytest.raises(ValueError, match="unknown symbol"):
            ledger_of(self.delta(), worth_overrides=[{"symbol": "ns::Nope", "worth": "internal", "reason": "r"}])
        with pytest.raises(ValueError, match="worth"):
            ledger_of(self.delta(), worth_overrides=[{"symbol": "ns::SaveOptions", "worth": "meh", "reason": "r"}])
        with pytest.raises(ValueError, match="reason"):
            ledger_of(self.delta(), worth_overrides=[{"symbol": "ns::SaveOptions", "worth": "internal", "reason": ""}])

    def test_all_internal_unit_is_reference_only_with_recorded_rationale(self):
        d = delta(added_types=[T("ns::HelperA", 2), T("ns::HelperB", 2)], existing_symbols=[])
        led = ledger_of(d, worth_overrides=[{"symbol": "ns::HelperA", "worth": "internal", "reason": "helper"},
                                            {"symbol": "ns::HelperB", "worth": "internal", "reason": "helper"}])
        (u,) = led["units"]
        assert u["dispositions"]["reference"]["action"] == "create"
        for s in ("docs", "kb", "blog", "products"):
            assert u["dispositions"][s]["action"] == "none" and "internal" in u["dispositions"][s]["rationale"]

    def test_public_worth_overrides_an_internal_namespace(self):
        d = delta(added_types=[T("ns.engine::Exposed", 2)], existing_symbols=[])
        led = ledger_of(d, worth_overrides=[{"symbol": "ns.engine::Exposed", "worth": "public", "reason": "documented"}])
        assert led["units"][0]["scale"]["new_public_types"] == 1

    def test_apply_worth_recomputes_a_built_ledger(self):
        led = ledger_of(self.delta(), candidate_blocks=BLOCKS)
        uid = led["units"][0]["id"]
        before = led["units"][0]["scale"]["new_public_types"]
        out = cd.apply_worth(led, uid, "ns::InternalHelper", "internal", "pipeline type", config=CFG)
        u = out["units"][0]
        assert u["scale"]["new_public_types"] == before - 1 and u["id"] == uid
        assert u["symbol_worth"]["ns::InternalHelper"]["reason"] == "pipeline type"
        assert all(d["computed_action"] for d in u["dispositions"].values())
        assert cd.validate_ledger(out, stage="plan") == []
        assert cd.apply_worth(out, uid, "ns::InternalHelper", "public", "oops", config=CFG)["units"][0]["scale"][
            "new_public_types"] == before
        with pytest.raises(ValueError, match="unknown"):
            cd.apply_worth(led, "CU-0", "ns::InternalHelper", "internal", "r", config=CFG)
        with pytest.raises(ValueError, match="unknown symbol"):
            cd.apply_worth(led, uid, "ns::Missing", "internal", "r", config=CFG)

    def test_unit_terms_from_symbols_excludes_internal_worth(self):
        """MT074 (found live, 2026-10-09): a mixed unit (some symbols public, some marked
        internal via apply_worth) must not require reader-facing content to mention the
        internal ones -- unit_terms_from_symbols() is what the close-time satisfaction
        check reads to decide what a page must say, and it used to read raw `symbols`,
        ignoring `internal_symbols` entirely."""
        led = ledger_of(self.delta(), candidate_blocks=BLOCKS)
        uid = led["units"][0]["id"]
        out = cd.apply_worth(led, uid, "ns::InternalHelper", "internal", "pipeline type", config=CFG)
        u = out["units"][0]
        terms = cd.unit_terms_from_symbols(u)
        assert "InternalHelper" not in terms
        assert {"SaveOptions", "SaveResult"} <= set(terms)


class TestGenerality:
    FORBIDDEN = re.compile(r"\b(pdf|java|xlsx|docx|markdown|cells|slides|words|words|python|csharp|typescript|"
                           r"golang|rust|aspose)\b", re.IGNORECASE)

    def _files(self):
        pipeline = Path(cd.__file__).resolve().parents[1]
        return [pipeline / "lib" / "capability_delta.py", pipeline / "lib" / "availability.py",
                pipeline / "config" / "capability_placement.yaml",
                pipeline / "commands" / "ops" / "capability_surface_gate.py",
                pipeline / "commands" / "ops" / "capability_ledger.py"]

    def test_no_product_family_language_or_format_literals(self):
        offenders = []
        for p in self._files():
            if not p.exists():
                continue
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                m = self.FORBIDDEN.search(line)
                if m:
                    offenders.append(f"{p.name}:{n}: {m.group(0)}")
        assert offenders == []
