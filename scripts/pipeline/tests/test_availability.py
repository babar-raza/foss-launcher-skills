"""B5 (MT074): lib/availability.py -- symbol-level release availability.

Fixtures span three differently shaped products (Java-style namespaces, C#-style namespaces,
Python-style file-qualified modules) and three registry shapes (Maven GAV, PyPI name, npm name).
"""
from __future__ import annotations

import json
import re

import pytest

# sys.path is set by tests/conftest.py
import availability as av
from package_registries import FetchResponse

REL_SHA, HEAD_SHA = "a" * 40, "b" * 40


def _entry(name, kind="class_declaration", ns=None, file=None, methods=(), props=(), enums=()):
    e = {"name": name, "kind": kind, "file": file or f"src/{name}.x",
         "methods": [{"name": m} for m in methods], "properties": [{"name": p} for p in props],
         "enum_members": [{"name": c} for c in enums]}
    if ns:
        e["canonical_namespace"] = ns
    return e


# three shapes: java-style package, c#-style namespace, python-style (no namespace -> file path)
JAVA_RELEASED = [_entry("Doc", ns="org.acme.core", methods=["open", "save"]),
                 _entry("Mode", kind="enum_declaration", ns="org.acme.core", enums=["A", "B"])]
NET_RELEASED = [_entry("Sheet", ns="Acme.Cells", props=["Name"])]
PY_RELEASED = [_entry("Table", kind="class_definition", file="acme/tables/table.py", methods=["add_row"])]

JAVA_HEAD = [_entry("Doc", ns="org.acme.core", methods=["open", "save", "export"]),
             _entry("Mode", kind="enum_declaration", ns="org.acme.core", enums=["A", "B", "C"]),
             _entry("SaveOptions", ns="org.acme.core")]


class TestSymbolForm:
    def test_type_and_member_symbols_across_shapes(self):
        assert av.symbols_from_api_surface(JAVA_RELEASED) == {
            "org.acme.core::Doc", "org.acme.core::Doc.open", "org.acme.core::Doc.save",
            "org.acme.core::Mode", "org.acme.core::Mode.A", "org.acme.core::Mode.B"}
        assert av.symbols_from_api_surface(NET_RELEASED) == {"Acme.Cells::Sheet", "Acme.Cells::Sheet.Name"}
        assert av.symbols_from_api_surface(PY_RELEASED) == {
            "acme/tables/table.py::Table", "acme/tables/table.py::Table.add_row"}

    def test_helpers(self):
        assert av.is_member_symbol("ns::T.m") and not av.is_member_symbol("ns::T")
        assert av.is_member_symbol("T.m") and not av.is_member_symbol("T")
        assert av.type_of_symbol("ns::T.m") == "ns::T" and av.type_of_symbol("T.m") == "T"
        assert av.simple_name("a.b::T") == "T" and av.simple_name("a.b::T.m") == "m"

    def test_matches_refresh_knowledge_identity(self):
        rk = pytest.importorskip("refresh_knowledge")
        for e in JAVA_RELEASED + NET_RELEASED + PY_RELEASED:
            assert av.qualified_name(e) == rk._api_qualified_name(e)


class TestManifestUnchangedChangelogAhead:
    """The verified failure: manifest version identical at old and new commits, features ahead."""

    ENTRY = {"registry_type": "maven",
             "candidate": {"group_id": "org.acme", "artifact_id": "acme-lib", "version": "26.7.0",
                           "repo_sha": REL_SHA},
             "verification": {"published": True, "verified_at": "2026-09-24"}}
    MANIFEST_AT = {REL_SHA: "26.7.0", HEAD_SHA: "26.7.0"}   # identical -- the trap
    SURFACE_AT = {REL_SHA: JAVA_RELEASED, HEAD_SHA: JAVA_HEAD}

    def _states(self):
        ref = av.release_ref_from_registry(self.ENTRY)
        syms = av.symbols_from_api_surface(JAVA_HEAD)
        return ref, av.symbol_availability(
            syms, ref["ref"], lambda r: av.symbols_from_api_surface(self.SURFACE_AT[r]))

    def test_version_comparison_would_have_lied(self):
        assert self.MANIFEST_AT[REL_SHA] == self.MANIFEST_AT[HEAD_SHA]

    def test_release_ref_is_the_registry_sha_not_the_manifest(self):
        ref, _ = self._states()
        assert ref["ref"] == REL_SHA and ref["source"] == "candidate.repo_sha"

    def test_new_symbols_unreleased_old_released(self):
        _, st = self._states()
        assert st["org.acme.core::Doc"]["state"] == av.RELEASED
        assert st["org.acme.core::Doc.open"]["state"] == av.RELEASED
        assert st["org.acme.core::Doc.export"]["state"] == av.UNRELEASED
        assert st["org.acme.core::Mode.C"]["state"] == av.UNRELEASED

    def test_unit_availability_aggregation(self):
        _, st = self._states()
        pick = lambda *k: [st[x]["state"] for x in k]  # noqa: E731
        assert av.unit_availability(pick("org.acme.core::Doc", "org.acme.core::Mode")) == av.RELEASED
        assert av.unit_availability(pick("org.acme.core::Doc", "org.acme.core::Doc.export")) == av.UNRELEASED
        assert av.unit_availability([av.RELEASED, av.UNKNOWN]) == av.UNKNOWN
        assert av.unit_availability([av.UNRELEASED, av.UNKNOWN]) == av.UNRELEASED
        assert av.unit_availability([]) == av.UNKNOWN

    def test_explicit_verification_ref_wins_over_scout_sha(self):
        entry = json.loads(json.dumps(self.ENTRY))
        entry["verification"]["released_sha"] = "c" * 40
        ref = av.release_ref_from_registry(entry)
        assert ref["ref"] == "c" * 40 and ref["source"] == "verification.released_sha"

    def test_deterministic_sorted_output(self):
        _, st = self._states()
        assert list(st) == sorted(st)


class TestNonMavenRegistryShapes:
    def test_pypi_tag_resolved_from_live_probe(self):
        entry = {"registry_type": "pypi", "candidate": {"name": "acme-tables"},
                 "verification": {"published": True}}
        probe = {"source": "live_probe", "live": {"published": True, "ambiguous": False,
                                                   "latest_version": "3.2.1"}}
        seen = []

        def resolver(tag):
            seen.append(tag)
            return REL_SHA if tag == "3.2.1" else None

        ref = av.release_ref_from_registry(entry, probe, tag_resolver=resolver)
        assert ref["ref"] == REL_SHA and ref["source"] == "tag:3.2.1" and seen == ["v3.2.1", "3.2.1"]

    def test_tag_not_resolvable_and_no_scout_sha_is_unknown(self):
        entry = {"candidate": {"name": "x"}, "verification": {"published": True}}
        probe = {"source": "live_probe", "live": {"published": True, "ambiguous": False, "latest_version": "9.9.9"}}
        ref = av.release_ref_from_registry(entry, probe, tag_resolver=lambda t: None)
        assert ref["ref"] is None and ref["reason"] == "release_tag_not_resolvable"

    def test_npm_style_record_uses_scout_sha(self):
        entry = {"registry_type": "npm", "candidate": {"name": "@acme/sheets", "version": "1.4.0",
                                                       "repo_sha": REL_SHA},
                 "verification": {"published": True}}
        surface = av.symbols_from_api_surface(NET_RELEASED)
        ref = av.release_ref_from_registry(entry)
        st = av.symbol_availability(["Acme.Cells::Sheet", "Acme.Cells::Sheet.Format"], ref["ref"],
                                    lambda r: surface)
        assert st["Acme.Cells::Sheet"]["state"] == av.RELEASED
        assert st["Acme.Cells::Sheet.Format"]["state"] == av.UNRELEASED

    def test_python_file_qualified_symbols(self):
        surface = av.symbols_from_api_surface(PY_RELEASED)
        st = av.symbol_availability(["acme/tables/table.py::Table", "acme/tables/chart.py::Chart"], REL_SHA,
                                    lambda r: surface)
        assert st["acme/tables/table.py::Table"]["state"] == av.RELEASED
        assert st["acme/tables/chart.py::Chart"]["state"] == av.UNRELEASED


class TestUnknownPaths:
    def test_no_entry_no_probe(self):
        ref = av.release_ref_from_registry(None)
        assert ref["ref"] is None and ref["reason"] == "no_registry_entry"
        st = av.symbol_availability(["a::B"], ref["ref"], lambda r: [])
        assert st["a::B"] == {"state": av.UNKNOWN, "reason": "no_release_ref"}

    def test_record_says_unpublished_without_live_proof_is_unknown(self):
        entry = {"candidate": {"repo_sha": REL_SHA}, "verification": {"published": False}}
        ref = av.release_ref_from_registry(entry)
        assert ref["ref"] is None and ref["state_hint"] is None and ref["reason"] == "registry_record_not_published"

    def test_live_404_proves_nothing_released(self):
        probe = {"source": "live_probe", "live": {"published": False, "ambiguous": False}}
        ref = av.release_ref_from_registry({"candidate": {"repo_sha": REL_SHA}}, probe)
        assert ref["ref"] is None and ref["state_hint"] == av.UNRELEASED
        st = av.symbol_availability(["a::B"], None, lambda r: [], state_hint=ref["state_hint"])
        assert st["a::B"]["state"] == av.UNRELEASED

    def test_ambiguous_probe_is_unknown(self):
        probe = {"source": "package_registry.json (probe ambiguous: x)", "live": {"published": None, "ambiguous": True}}
        ref = av.release_ref_from_registry({"candidate": {}, "verification": {"published": True}}, probe)
        assert ref["ref"] is None and ref["reason"] == "probe_unsupported_or_ambiguous"
        assert not av.is_released(av.UNKNOWN)

    def test_symbols_at_failure_and_empty_are_unknown(self):
        def boom(_r):
            raise RuntimeError("clone missing")

        assert av.symbol_availability(["a::B"], REL_SHA, boom)["a::B"]["reason"] == "symbols_at_failed:RuntimeError"
        assert av.symbol_availability(["a::B"], REL_SHA, lambda r: [])["a::B"]["reason"] == "empty_symbol_set_at_release"

    def test_ambiguous_qualifier_is_never_called_unreleased(self):
        # at the release the type was extracted with a file qualifier (older extractor); now it has a namespace
        released = av.symbols_from_api_surface([_entry("Doc", file="src/Doc.x")])
        st = av.symbol_availability(["org.acme::Doc", "org.acme::Doc.open"], REL_SHA, lambda r: released)
        assert st["org.acme::Doc"] == {"state": av.UNKNOWN, "reason": "ambiguous_qualifier"}
        assert st["org.acme::Doc.open"]["state"] == av.UNKNOWN

    def test_unsupported_registry_probe_through_adapter_wrapper(self):
        info = {"registry_type": "carrier-pigeon", "candidate": {"name": "x"}, "verification": {"published": True}}
        out = av.probe_release(info, fetch=lambda url: None)
        assert out["ref"] is None  # no ref and no scout sha -> unknown, never a guess

    def test_probe_wrapper_with_injected_fetch(self):
        body = json.dumps({"info": {"version": "3.2.1"}, "releases": {"3.2.1": []}, "urls": []}).encode()
        info = {"registry_type": "pypi", "candidate": {"name": "acme-tables"}, "published": True,
                "verification": {"published": True}}
        out = av.probe_release(info, fetch=lambda url: FetchResponse(200, body),
                               tag_resolver=lambda t: REL_SHA if t == "v3.2.1" else None)
        assert out["ref"] == REL_SHA and out["source"] == "tag:v3.2.1"
        gone = av.probe_release(info, fetch=lambda url: FetchResponse(404, b""))
        assert gone["state_hint"] == av.UNRELEASED
        net_down = av.probe_release(info, fetch=lambda url: None)
        assert net_down["ref"] is None and net_down["state_hint"] is None


class TestReleasedVersions:
    def test_only_published_record_and_unambiguous_probe(self):
        entry = {"candidate": {"version": "26.7.0"}, "verification": {"published": True}}
        assert av.released_versions(entry) == ["26.7.0"]
        assert av.released_versions({"candidate": {"version": "1.0.0"}, "verification": {"published": False}}) == []
        probe = {"live": {"ambiguous": False, "published": True, "latest_version": "v26.8.0"}}
        assert av.released_versions(entry, probe) == ["26.7.0", "26.8.0"]
        assert av.released_versions(entry, {"live": {"ambiguous": True, "latest_version": "9.9.9"}}) == ["26.7.0"]


def cfg_without(*path):
    import copy
    c = copy.deepcopy(av.load_config())
    node = c
    for k in path[:-1]:
        node = node[k]
    del node[path[-1]]
    return c


class TestForbiddenCoordinateScan:
    """m2: a version token is flagged only in a coordinate context, a keyword context of the
    product's own version scheme, or when it is in the configured unreleased set."""
    RELEASED = ["26.8.0", "26.9.0"]
    UNRELEASED = ["26.10.0"]

    def scan(self, text, released=None, unreleased=None, config=None):
        return av.forbidden_coordinate_scan(text, released_versions=self.RELEASED if released is None else released,
                                            unreleased_versions=self.UNRELEASED if unreleased is None else unreleased,
                                            config=config)

    def versions(self, text, **kw):
        return sorted(x["version"] for x in self.scan(text, **kw))

    def test_gav_coordinate_of_unreleased_version_flagged(self):
        f = self.scan("Add org.acme:acme-lib:26.11.0 to your build.")
        assert [x["version"] for x in f] == ["26.11.0"] and f[0]["kind"] == "coordinate" and f[0]["line"] == 1

    def test_released_version_not_flagged_and_v_prefix_normalised(self):
        text = "Use org.acme:acme-lib:26.9.0 or pip install acme-tables==v26.9.0 or tag v26.9.0."
        assert self.scan(text) == []

    def test_pip_npm_nuget_style_pins(self):
        text = "pip install acme-tables==3.3.0\nnpm i @acme/sheets@2.0.1\n<PackageReference Version=\"4.5.6\" />\n"
        assert self.versions(text) == ["2.0.1", "3.3.0", "4.5.6"]

    def test_xml_version_element_and_artifact_file_names(self):
        assert self.versions("<version>9.9.9</version>") == ["9.9.9"]
        assert self.versions("download acme-lib-26.11.0.jar now") == ["26.11.0"]

    def test_sentence_punctuation_is_not_part_of_the_version(self):
        text = "Use org.acme:acme-lib:26.9.0. Or acme-tables==26.9.0, or version: 26.9.0; see v26.9.0)."
        assert self.scan(text) == []
        assert self.versions("Try org.acme:lib:26.11.0-rc2.") == ["26.11.0-rc2"]

    @pytest.mark.parametrize("text", [
        "Requires JDK 17.0.2 or newer.", "Built on 2026.10.07 by CI.", "Reach the host at 192.168.0.1 first.",
        "Generated with Hugo 0.121.0.", "OID 1.3.6.1.4.1.311.20.2.3 identifies it.",
        "Prior versions: 26.8.0 and 26.9.0 are listed in the changelog.", "Needs Hugo version 0.121.0 or later.",
        "jdk-17.0.2 is required.", "Install with the JDK version 17.0.2 toolchain.", "Released 07.10.2026 and 2026-10-07.",
        "pi is 3.14159 and the ratio is 2.5",
    ])
    def test_review_false_positives_are_not_flagged(self, text):
        assert self.scan(text) == [], text

    @pytest.mark.parametrize("text,expected", [
        ("Since 26.11 the API changed.", ["26.11"]), ("See version 26.11 for details.", ["26.11"]),
        ("requires v26.12 or later", ["26.12"]), ("Coming in 26.10.0.", ["26.10.0"]),
        ("The 26.10.0 release adds it.", ["26.10.0"]),
    ])
    def test_review_false_negatives_are_flagged(self, text, expected):
        assert self.versions(text) == expected

    def test_unreleased_set_wins_over_exclusions_but_released_versions_never_flag(self):
        assert self.versions("host 10.20.30.40 and 26.10.0.1", unreleased=["26.10.0.1"]) == ["26.10.0.1"]
        assert self.scan("Since 26.9.0 and in 26.8.0", unreleased=[]) == []

    def test_unknown_released_set_flags_keyword_contexts(self):
        f = self.scan("version 1.2.3", released=[], unreleased=[])
        assert [x["version"] for x in f] == ["1.2.3"] and f[0]["released_set_known"] is False

    def test_sorted_by_line_and_deduplicated(self):
        text = "org.a:b:9.9.9\norg.a:b:1.1.1\norg.a:b:9.9.9"
        f = self.scan(text, released=["26.9.0"])
        assert [(x["line"], x["version"]) for x in f] == [(1, "9.9.9"), (2, "1.1.1"), (3, "9.9.9")]

    def test_patterns_and_tool_names_come_from_config(self):
        import copy
        c = copy.deepcopy(av.load_config())
        c["availability"]["coordinate_scan"]["coordinate_patterns"] = [r'crate\s+\w+\s+=\s+"(?P<version>{V})"']
        assert self.versions('crate foo = "0.9"', config=c) == ["0.9"]
        assert self.versions("org.a:b:9.9.9", config=c) == []
        c2 = copy.deepcopy(av.load_config())
        c2["availability"]["coordinate_scan"]["ignore_tool_names"] = []
        assert self.versions("jdk-17.0.2 is required.", config=c2) == ["17.0.2"]

    @pytest.mark.parametrize("key", ["coordinate_patterns", "keyword_contexts", "version_pattern", "ignore_patterns",
                                     "ignore_tool_names", "min_components_in_coordinate"])
    def test_missing_config_key_fails_closed_naming_the_key(self, key):
        with pytest.raises(av.ConfigError, match=f"availability.coordinate_scan.{key}"):
            self.scan("org.a:b:9.9.9", config=cfg_without("availability", "coordinate_scan", key))

    def test_missing_coordinate_scan_section_fails_closed(self):
        with pytest.raises(av.ConfigError, match="availability.coordinate_scan"):
            self.scan("org.a:b:9.9.9", config=cfg_without("availability", "coordinate_scan"))


class TestQualifierPresent:
    """m1: word-boundary phrases with negation guards; coverage is per mention within a window."""

    def test_phrases_case_and_whitespace_insensitive(self):
        assert av.qualifier_present("This API is NOT   yet\nreleased.")
        assert av.qualifier_present("Available from source until the next release")
        assert not av.qualifier_present("This API is great.")
        assert not av.qualifier_present("")

    @pytest.mark.parametrize("text", [
        "Everything here is already released, not unreleased.", "Unreleased changes are listed in the changelog.",
        "The tool is in development by another team.", "It is no longer unreleased.", "reunreleased unreleasedness",
    ])
    def test_review_false_cases_do_not_count(self, text):
        assert not av.qualifier_present(text), text

    def test_negation_guard_on_a_configured_bare_phrase(self):
        import copy
        c = copy.deepcopy(av.load_config())
        c["availability"]["qualifier_phrases"] = ["unreleased"]
        assert av.qualifier_present("The feature is unreleased.", config=c)
        assert not av.qualifier_present("The feature is not unreleased.", config=c)
        assert not av.qualifier_present("The feature is no longer unreleased.", config=c)
        assert not av.qualifier_present("Already unreleased? never.", config=c)

    def test_configurable_list(self):
        import copy
        c = copy.deepcopy(av.load_config())
        c["availability"]["qualifier_phrases"] = ["preview build"]
        assert av.qualifier_present("A Preview Build feature", config=c)
        assert not av.qualifier_present("not yet released", config=c)

    @pytest.mark.parametrize("key", ["qualifier_phrases", "qualifier_negation_prefixes", "qualifier_window_chars"])
    def test_missing_config_key_fails_closed(self, key):
        c = cfg_without("availability", key)
        with pytest.raises(av.ConfigError, match=f"availability.{key}"):
            av.qualifier_uncovered("ThingA not yet released", [(0, 6)], config=c)

    def test_each_mention_needs_a_qualifier_inside_the_window(self):
        near = "ThingA is not yet released.\n"
        far = "x" * 900 + "\nElsewhere ThingA appears again with nothing nearby.\n"
        spans = [m.span() for m in re.finditer("ThingA", near + far)]
        assert len(spans) == 2
        assert av.qualifier_uncovered(near + far, spans) == [spans[1]]
        assert av.qualifier_uncovered(near, spans[:1]) == []

    def test_window_comes_from_config(self):
        import copy
        text = "ThingA " + "y" * 300 + " is not yet released."
        span = [re.search("ThingA", text).span()]
        assert av.qualifier_uncovered(text, span) == []
        c = copy.deepcopy(av.load_config())
        c["availability"]["qualifier_window_chars"] = 100
        assert av.qualifier_uncovered(text, span, config=c) == span

    def test_qualifier_before_the_mention_also_covers(self):
        text = "Note: this is not yet released. See ThingB below."
        span = [re.search("ThingB", text).span()]
        assert av.qualifier_uncovered(text, span) == []


class TestReleaseSince:
    """B5b: available_since derived from the current and previous PUBLISHED surfaces."""
    CUR = av.symbols_from_api_surface([_entry("Doc", ns="org.acme.core", methods=["open", "save", "export"]),
                                       _entry("Mode", kind="enum_declaration", ns="org.acme.core", enums=["A", "B", "C"]),
                                       _entry("RenderJob", ns="org.acme.render")])
    PREV = av.symbols_from_api_surface([_entry("Doc", ns="org.acme.core", methods=["open", "save"]),
                                        _entry("Mode", kind="enum_declaration", ns="org.acme.core", enums=["A", "B"])])
    SYMS = ["org.acme.core::Doc.open", "org.acme.core::Doc.export", "org.acme.core::Mode.C",
            "org.acme.render::RenderJob", "org.acme.render::Unshipped"]

    def since(self, syms=None, prev="PREV", **kw):
        kw.setdefault("version", "26.9.0")
        kw.setdefault("previous_version", "26.8.0")
        return av.release_since(syms or self.SYMS, current_symbols=self.CUR,
                                previous_symbols=getattr(self, prev) if prev else None, **kw)

    def test_three_outcomes(self):
        r = self.since()
        assert (r["org.acme.core::Doc.export"]["state"], r["org.acme.core::Doc.export"]["available_since"]) == ("released", "26.9.0")
        assert (r["org.acme.render::RenderJob"]["state"], r["org.acme.render::RenderJob"]["available_since"]) == ("released", "26.9.0")
        assert r["org.acme.core::Mode.C"]["available_since"] == "26.9.0"
        assert (r["org.acme.core::Doc.open"]["state"], r["org.acme.core::Doc.open"]["available_since"]) == ("released", "26.8.0")
        assert r["org.acme.core::Doc.open"]["since_basis"] == "previous"
        assert (r["org.acme.render::Unshipped"]["state"], r["org.acme.render::Unshipped"]["available_since"]) == ("unreleased", None)
        assert list(r) == sorted(r)

    def test_earlier_without_known_previous_version(self):
        r = self.since(previous_version=None)
        assert r["org.acme.core::Doc.open"]["available_since"] == "earlier-than-26.9.0"
        assert self.since(previous_version=None, version=None)["org.acme.core::Doc.open"]["available_since"] == "earlier"

    def test_no_previous_surface_means_since_unknown_never_a_guess(self):
        r = self.since(prev=None)
        assert r["org.acme.core::Doc.export"]["state"] == "released"
        assert r["org.acme.core::Doc.export"]["available_since"] is None
        assert r["org.acme.core::Doc.export"]["since_basis"] == "previous_surface_missing"

    def test_ambiguous_previous_qualifier_is_since_unknown(self):
        self.PREV_AMB = av.symbols_from_api_surface([_entry("RenderJob", file="src/RenderJob.x"),
                                                     _entry("Doc", ns="org.acme.core", methods=["open"])])
        r = av.release_since(["org.acme.render::RenderJob"], current_symbols=self.CUR, previous_symbols=self.PREV_AMB,
                             version="26.9.0", previous_version="26.8.0")
        assert r["org.acme.render::RenderJob"] == {"state": "released", "available_since": None,
                                                    "since_basis": "ambiguous_previous", "reason": "ambiguous_qualifier"}

    def test_ambiguous_or_empty_current_is_unknown(self):
        amb = av.symbols_from_api_surface([_entry("RenderJob", file="src/RenderJob.x")])
        r = av.release_since(["org.acme.render::RenderJob"], current_symbols=amb, previous_symbols=self.PREV, version="26.9.0")
        assert r["org.acme.render::RenderJob"]["state"] == "unknown" and r["org.acme.render::RenderJob"]["available_since"] is None
        assert av.release_since(["x::Y"], current_symbols=set(), previous_symbols=self.PREV)["x::Y"]["state"] == "unknown"

    def test_python_style_file_qualified(self):
        cur = av.symbols_from_api_surface(PY_RELEASED + [_entry("Chart", kind="class_definition", file="acme/tables/chart.py")])
        prev = av.symbols_from_api_surface(PY_RELEASED)
        r = av.release_since(["acme/tables/table.py::Table", "acme/tables/chart.py::Chart"], current_symbols=cur,
                             previous_symbols=prev, version="3.2.0", previous_version="3.1.0")
        assert r["acme/tables/table.py::Table"]["available_since"] == "3.1.0"
        assert r["acme/tables/chart.py::Chart"]["available_since"] == "3.2.0"


class TestUnitSince:
    def info(self, state, since, basis="current_only"):
        return {"state": state, "available_since": since, "since_basis": basis}

    def test_all_new_in_current(self):
        u = av.unit_since([self.info("released", "26.9.0")] * 2, version="26.9.0", previous_version="26.8.0")
        assert u["available_since"] == "26.9.0" and u["partial_earlier"] is False
        assert u["counts"] == {"since_current": 2, "earlier": 0, "since_unknown": 0, "unreleased": 0, "unknown": 0}

    def test_mixed_earlier_and_current_needs_the_current_version(self):
        u = av.unit_since([self.info("released", "26.9.0"), self.info("released", "26.8.0", "previous")],
                          version="26.9.0", previous_version="26.8.0")
        assert u["available_since"] == "26.9.0" and u["partial_earlier"] is True
        assert (u["counts"]["since_current"], u["counts"]["earlier"]) == (1, 1)

    def test_all_earlier(self):
        u = av.unit_since([self.info("released", "26.8.0", "previous")], version="26.9.0", previous_version="26.8.0")
        assert u["available_since"] == "26.8.0" and u["partial_earlier"] is False

    def test_unreleased_or_unknown_symbol_gives_no_since(self):
        u = av.unit_since([self.info("released", "26.9.0"), self.info("unreleased", None)], version="26.9.0")
        assert u["available_since"] is None and u["counts"]["unreleased"] == 1
        u = av.unit_since([self.info("released", "26.9.0"), self.info("unknown", None)], version="26.9.0")
        assert u["available_since"] is None and u["counts"]["unknown"] == 1

    def test_released_symbol_with_unknown_since_blocks_a_since_claim(self):
        u = av.unit_since([self.info("released", None, "previous_surface_missing")], version="26.9.0")
        assert u["available_since"] is None and u["counts"]["since_unknown"] == 1

    def test_plain_string_states_are_accepted(self):
        u = av.unit_since(["released", "released"], version="26.9.0")
        assert u["available_since"] is None and u["counts"]["since_unknown"] == 2


class TestUnitSinceUndeterminedSymbols:
    """B5c: a symbol PRESENT in the current release can never be later than it, so since_unknown
    symbols do not block the unit's required version -- unless nothing in the unit is since_current."""

    def info(self, state, since, basis="current_only"):
        return {"state": state, "available_since": since, "since_basis": basis}

    def test_real_shape_25_current_1_unknown(self):
        infos = [self.info("released", "26.9.0")] * 25 + [self.info("released", None, "ambiguous_previous")]
        u = av.unit_since(infos, version="26.9.0", previous_version="26.8.0")
        assert u["available_since"] == "26.9.0" and u["partial_earlier"] is False
        assert u["counts"] == {"since_current": 25, "earlier": 0, "since_unknown": 1, "unreleased": 0, "unknown": 0}

    def test_real_shape_2_current_1_unknown(self):
        infos = [self.info("released", "26.9.0")] * 2 + [self.info("released", None, "ambiguous_previous")]
        assert av.unit_since(infos, version="26.9.0")["available_since"] == "26.9.0"

    def test_partial_earlier_only_when_determinately_earlier(self):
        infos = [self.info("released", "26.9.0"), self.info("released", None, "ambiguous_previous"),
                 self.info("released", "26.8.0", "previous")]
        u = av.unit_since(infos, version="26.9.0", previous_version="26.8.0")
        assert u["available_since"] == "26.9.0" and u["partial_earlier"] is True

    def test_all_unknown_since_stays_none(self):
        infos = [self.info("released", None, "ambiguous_previous")] * 3
        assert av.unit_since(infos, version="26.9.0")["available_since"] is None

    def test_earlier_plus_unknown_without_current_stays_none(self):
        infos = [self.info("released", "26.8.0", "previous"), self.info("released", None, "ambiguous_previous")]
        assert av.unit_since(infos, version="26.9.0", previous_version="26.8.0")["available_since"] is None

    def test_unreleased_or_unknown_state_still_blocks(self):
        for bad in ("unreleased", "unknown"):
            infos = [self.info("released", "26.9.0"), self.info("released", None, "ambiguous_previous"),
                     self.info(bad, None)]
            assert av.unit_since(infos, version="26.9.0")["available_since"] is None

    def test_no_release_version_known_gives_none(self):
        assert av.unit_since([self.info("released", None, "previous_surface_missing")])["available_since"] is None
