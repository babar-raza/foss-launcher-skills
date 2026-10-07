"""MT074 B4: commands/ops/capability_ledger.py -- build / validate / set-disposition / satisfaction.

Two differently shaped products: a Java-style one (dotted packages, typed signatures) and a
Python-style one (file-path qualifiers, no signature types). Files live in tmp dirs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import capability_delta as cd
import capability_ledger as cli

HEAD = "f" * 40


def e(name, ns=None, file=None, methods=(), enums=(), kind="class_declaration"):
    out = {"name": name, "kind": kind, "file": file or f"src/{name}.x", "visibility": "public",
           "methods": [dict(m) if isinstance(m, dict) else {"name": m, "params": [], "return_type": ""} for m in methods],
           "properties": [], "enum_members": [{"name": c} for c in enums]}
    if ns:
        out["canonical_namespace"] = ns
    return out


# ---- Java-style: baseline (= released) < release < HEAD; EarlyType is new vs the delta baseline but already released
J_RELEASED = [e("Doc", "org.acme.core", methods=["open", "save"]), e("EarlyType", "org.acme.core")]
J_NEW = [e("Doc", "org.acme.core", methods=["open", "save",
                                           {"name": "renderTo", "params": [{"name": "j", "type": "RenderJob"}],
                                            "return_type": ""}]),
         e("EarlyType", "org.acme.core"),
         e("RenderJob", "org.acme.render", methods=["run"]),
         e("RenderOptions", "org.acme.render", methods=["a", "b"])]
J_KD = {"new_apis_qualified": ["org.acme.core::EarlyType", "org.acme.render::RenderJob", "org.acme.render::RenderOptions"],
        "modified_apis_qualified": ["org.acme.core::Doc"],
        "api_signature_changes": {"Doc": {"added_methods": ["renderTo"], "removed_methods": [], "added_properties": [],
                                          "removed_properties": []}}}
# ---- Python-style
P_NEW = [e("Sheet", file="acme/sheet.py", kind="class_definition"),
         e("CsvReader", file="acme/io/csv_reader.py", kind="class_definition", methods=["read"]),
         e("CsvParser", file="acme/io/csv_parser.py", kind="class_definition", methods=["parse"])]
P_KD = {"new_apis_qualified": ["acme/io/csv_parser.py::CsvParser", "acme/io/csv_reader.py::CsvReader"]}
P_RELEASED = [e("Sheet", file="acme/sheet.py", kind="class_definition")]


def jwrite(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def run(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    out = capsys.readouterr().out
    return code, (json.loads(out) if out.strip() else None)


@pytest.fixture
def java(tmp_path):
    return {"kd": jwrite(tmp_path / "kd.json", J_KD), "surface": jwrite(tmp_path / "surf.json", J_NEW),
            "released": jwrite(tmp_path / "rel.json", J_RELEASED), "out": tmp_path / "ledger.json"}


@pytest.fixture
def py(tmp_path):
    return {"kd": jwrite(tmp_path / "kd.json", P_KD), "surface": jwrite(tmp_path / "surf.json", P_NEW),
            "released": jwrite(tmp_path / "rel.json", P_RELEASED), "out": tmp_path / "ledger.json"}


def build(capsys, fx, *extra, family="fam", platform="plat"):
    return run(capsys, "build", "--family", family, "--platform", platform, "--knowledge-delta", fx["kd"],
               "--api-surface", fx["surface"], "--out", fx["out"], "--upstream-head", HEAD, *extra)


def ledger(fx):
    return json.loads(Path(fx["out"]).read_text(encoding="utf-8"))


def unit_with(led, simple):
    return next(u for u in led["units"] if any(s.endswith("::" + simple) for s in u["symbols"]))


@pytest.mark.parametrize("shape", ["java", "py"])
class TestBuild:
    def test_build_writes_deterministic_ledger(self, shape, request, capsys):
        fx = request.getfixturevalue(shape)
        code, out = build(capsys, fx)
        assert code == 0 and out["ok"] is True and out["units"] >= 1
        first = Path(fx["out"]).read_bytes()
        assert first.endswith(b"\n") and b"\r\n" not in first
        assert build(capsys, fx)[0] == 0
        assert Path(fx["out"]).read_bytes() == first          # byte-identical re-run
        led = json.loads(first)
        assert led["schema_version"] == 1 and led["upstream_head"] == HEAD and led["symbol_level"] is True
        assert cd.validate_ledger(led, stage="plan") == []

    def test_availability_unknown_without_a_released_source(self, shape, request, capsys):
        fx = request.getfixturevalue(shape)
        build(capsys, fx)
        assert {u["availability"] for u in ledger(fx)["units"]} == {"unknown"}

    def test_surface_targets_and_blocks_flow_through(self, shape, request, capsys, tmp_path):
        fx = request.getfixturevalue(shape)
        targets = jwrite(tmp_path / "t.json", {"reference": "ref/", "docs": "docs/x.md", "kb": "kb/", "blog": "blog/",
                                               "products": "products/new.md"})
        blocks = jwrite(tmp_path / "b.json", [{"id": "b", "path": "products/p.md",
                                               "terms": ["Render", "Csv", "Job", "Reader", "Options", "Early", "Sheet"]}])
        build(capsys, fx, "--surface-targets", targets, "--blocks", blocks)
        led = ledger(fx)
        assert cd.validate_ledger(led, stage="close") == []
        assert any(u["dispositions"]["products"]["target"] == "products/p.md#b" for u in led["units"])
        assert all(u["dispositions"]["reference"]["target"] == "ref/" for u in led["units"])


class TestAvailabilityFromReleasedSurface:
    def test_released_unreleased_unknown(self, java, capsys):
        code, out = build(capsys, java, "--released-api-surface", java["released"])
        assert code == 0
        led = ledger(java)
        early = unit_with(led, "EarlyType")
        render = unit_with(led, "RenderJob")
        assert early["availability"] == "released" and "RenderJob" not in " ".join(early["symbols"])
        assert render["availability"] == "unreleased"
        assert "org.acme.core::Doc.renderTo" in render["symbols"]      # attached through its signature
        assert led["availability_context"]["release_source"] == "released_api_surface"
        assert len(led["availability_context"]["release_surface_sha256"]) == 64
        assert out["availability"] == {"released": 1, "unreleased": 1, "unknown": 0}

    def test_ambiguous_qualifier_is_unknown(self, java, capsys, tmp_path):
        # at the release the type was extracted with a file qualifier (older extractor)
        rel = jwrite(tmp_path / "old.json", [e("Doc", "org.acme.core", methods=["open", "save", "renderTo"]),
                                             e("RenderJob", file="src/RenderJob.x"),
                                             e("RenderOptions", file="src/RenderOptions.x")])
        build(capsys, java, "--released-api-surface", rel)
        assert unit_with(ledger(java), "RenderJob")["availability"] == "unknown"

    def test_python_style(self, py, capsys):
        build(capsys, py, "--released-api-surface", py["released"])
        assert {u["availability"] for u in ledger(py)["units"]} == {"unreleased"}

    def test_released_surface_rerun_is_byte_identical(self, java, capsys):
        build(capsys, java, "--released-api-surface", java["released"])
        a = Path(java["out"]).read_bytes()
        build(capsys, java, "--released-api-surface", java["released"])
        assert Path(java["out"]).read_bytes() == a

    def test_registry_json_adds_context_but_not_symbol_availability(self, java, capsys, tmp_path):
        reg = jwrite(tmp_path / "reg.json", {"_comment": "x", "fam": {"plat": {
            "registry_type": "maven", "candidate": {"version": "26.7.0", "repo_sha": "a" * 40},
            "verification": {"published": True}}}})
        build(capsys, java, "--registry-json", reg)
        led = ledger(java)
        assert led["availability_context"]["released_versions"] == ["26.7.0"]
        assert led["availability_context"]["release_ref"] == "a" * 40
        assert {u["availability"] for u in led["units"]} == {"unknown"}

    def test_registry_without_entry_gives_empty_context(self, java, capsys, tmp_path):
        reg = jwrite(tmp_path / "reg.json", {"other": {}})
        build(capsys, java, "--registry-json", reg)
        ctx = ledger(java)["availability_context"]
        assert ctx["release_ref"] is None and ctx["released_versions"] == []


class TestOverridesAndErrors:
    def test_grouping_overrides_file(self, java, capsys, tmp_path):
        ov = jwrite(tmp_path / "ov.json", [{"id": "split", "symbols": ["org.acme.render::RenderOptions"]}])
        build(capsys, java, "--grouping-overrides", ov)
        led = ledger(java)
        opt = unit_with(led, "RenderOptions")
        assert opt["grouping"] == "reviewed" and opt["title"] == "split"
        assert unit_with(led, "RenderJob") is not opt

    def test_bad_override_exits_2(self, java, capsys, tmp_path):
        ov = jwrite(tmp_path / "ov.json", [{"symbols": ["Nope::Missing"]}])
        code, out = build(capsys, java, "--grouping-overrides", ov)
        assert code == 2 and "unknown symbol" in out["error"] and not Path(java["out"]).exists()

    def test_missing_input_exits_2(self, tmp_path, capsys):
        code, out = run(capsys, "build", "--family", "f", "--platform", "p", "--knowledge-delta",
                        tmp_path / "nope.json", "--out", tmp_path / "o.json")
        assert code == 2 and out["ok"] is False
        code, out = run(capsys, "validate", "--ledger", tmp_path / "nope.json")
        assert code == 2

    def test_absent_optional_inputs_are_fine(self, tmp_path, capsys):
        kd = jwrite(tmp_path / "kd.json", {})
        code, out = run(capsys, "build", "--family", "f", "--platform", "p", "--knowledge-delta", kd,
                        "--out", tmp_path / "o.json")
        assert code == 0 and out["units"] == 0


class TestValidateStages:
    def test_plan_vs_close(self, java, capsys):
        build(capsys, java)    # no surface targets, no blocks
        code, rep = run(capsys, "validate", "--ledger", java["out"], "--stage", "plan")
        assert code == 0 and rep["valid"] is True and rep["errors"] == []
        assert rep["warnings"] and any("unplaced" in w for w in rep["warnings"])
        code, rep = run(capsys, "validate", "--ledger", java["out"], "--stage", "close")
        assert code == 1 and rep["valid"] is False and any("target" in e or "unplaced" in e for e in rep["errors"])
        assert run(capsys, "validate", "--ledger", java["out"])[0] == 1      # close is the default

    def test_plan_still_requires_structure(self, java, capsys):
        build(capsys, java)
        led = ledger(java)
        led["units"][0]["dispositions"]["blog"].update(action="none", rationale="", status="none_justified")
        del led["units"][0]["dispositions"]["kb"]
        led["units"][0]["id"] = "CU-00000000"
        jwrite(Path(java["out"]), led)
        code, rep = run(capsys, "validate", "--ledger", java["out"], "--stage", "plan")
        assert code == 1
        text = " ".join(rep["errors"])
        assert "rationale" in text and "missing" in text and "does not match" in text


class TestSetDisposition:
    def ids(self, java, capsys):
        build(capsys, java)
        led = ledger(java)
        return led, unit_with(led, "RenderJob")["id"]

    def test_update_is_validated_deterministic_and_never_touches_symbols(self, java, capsys):
        led, uid = self.ids(java, capsys)
        args = ["set-disposition", "--ledger", java["out"], "--unit", uid, "--surface", "products", "--action", "mention",
                "--target", "products/p.md#b", "--rationale", "placed by reviewer"]
        code, out = run(capsys, *args)
        assert code == 0 and out["disposition"]["target"] == "products/p.md#b"
        first = Path(java["out"]).read_bytes()
        assert run(capsys, *args)[0] == 0 and Path(java["out"]).read_bytes() == first
        new = ledger(java)
        u = unit_with(new, "RenderJob")
        assert u["dispositions"]["products"]["placement"] == "mention"           # unplaced -> placed
        assert u["symbols"] == unit_with(led, "RenderJob")["symbols"] and u["id"] == uid
        assert {x["id"] for x in new["units"]} == {x["id"] for x in led["units"]}

    def test_none_gets_none_justified_and_clears_placement(self, java, capsys):
        _, uid = self.ids(java, capsys)
        code, out = run(capsys, "set-disposition", "--ledger", java["out"], "--unit", uid, "--surface", "blog",
                        "--action", "none", "--rationale", "internal housekeeping")
        d = out["disposition"]
        assert code == 0 and d["status"] == "none_justified" and d["target"] is None and d["placement"] is None

    def test_refuses_unknown_unit_and_surface_without_writing(self, java, capsys):
        led, uid = self.ids(java, capsys)
        before = Path(java["out"]).read_bytes()
        code, out = run(capsys, "set-disposition", "--ledger", java["out"], "--unit", "CU-deadbeef", "--surface", "kb",
                        "--action", "none", "--rationale", "r")
        assert code == 1 and "unknown unit" in out["error"]
        code, out = run(capsys, "set-disposition", "--ledger", java["out"], "--unit", uid, "--surface", "newsletter",
                        "--action", "none", "--rationale", "r")
        assert code == 1 and "unknown surface" in out["error"]
        assert Path(java["out"]).read_bytes() == before

    def test_refuses_edit_that_introduces_an_error(self, java, capsys):
        _, uid = self.ids(java, capsys)
        before = Path(java["out"]).read_bytes()
        code, out = run(capsys, "set-disposition", "--ledger", java["out"], "--unit", uid, "--surface", "blog",
                        "--action", "none", "--rationale", "   ")
        assert code == 1 and any("rationale" in x for x in out["errors"])
        code, out = run(capsys, "set-disposition", "--ledger", java["out"], "--unit", uid, "--surface", "docs",
                        "--action", "create", "--target", "d.md", "--rationale", "r", "--status", "satisfied")
        assert code == 1 and any("evidence" in x for x in out["errors"])      # satisfied needs evidence
        assert Path(java["out"]).read_bytes() == before

    def test_satisfied_with_evidence_and_close_stage_becomes_valid(self, java, capsys):
        led, _ = self.ids(java, capsys)
        assert run(capsys, "validate", "--ledger", java["out"], "--stage", "close")[0] == 1
        for u in led["units"]:
            for surface, d in u["dispositions"].items():
                if d["action"] == "none":
                    continue
                extra = ["--evidence", "x/y.md", "--status", "satisfied"] if surface == "docs" else []
                code, _ = run(capsys, "set-disposition", "--ledger", java["out"], "--unit", u["id"], "--surface",
                              surface, "--action", d["action"], "--target", f"{surface}/page.md", "--rationale", "set",
                              *extra)
                assert code == 0
        code, rep = run(capsys, "validate", "--ledger", java["out"], "--stage", "close")
        assert code == 0 and rep["errors"] == []


class TestSatisfactionCli:
    def test_read_only_report(self, java, capsys, tmp_path):
        targets = jwrite(tmp_path / "t.json", {"reference": "ref/", "docs": "docs/x.md", "kb": "kb/", "blog": "blog/",
                                               "products": "products/new.md"})
        blocks = jwrite(tmp_path / "b.json", [{"id": "b", "path": "products/p.md", "terms": ["Render", "Early"]}])
        build(capsys, java, "--surface-targets", targets, "--blocks", blocks)
        led_bytes = Path(java["out"]).read_bytes()
        root = tmp_path / "content"
        code, rep = run(capsys, "satisfaction", "--ledger", java["out"], "--content-root", root)
        assert code == 1 and rep["all_satisfied"] is False and rep["problems"]
        led = ledger(java)
        for u in led["units"]:
            terms = " ".join(cd.unit_terms_from_symbols(u))
            for surface, d in u["dispositions"].items():
                if d["action"] == "none":
                    continue
                t = d["target"].split("#")[0]
                p = root / t / "page.md" if t.endswith("/") else root / t
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a", encoding="utf-8") as fh:
                    fh.write(terms + " ")
        code, rep = run(capsys, "satisfaction", "--ledger", java["out"], "--content-root", root)
        assert code == 0 and rep["all_satisfied"] is True
        assert Path(java["out"]).read_bytes() == led_bytes                     # never writes the ledger


class TestGenerality:
    def test_cli_has_no_product_literals(self):
        import re
        src = Path(cli.__file__).read_text(encoding="utf-8")
        assert not re.search(r"\b(pdf|java|xlsx|docx|markdown|cells|slides|python|csharp|typescript|aspose)\b", src,
                             re.IGNORECASE)


# ---- B5b: "Since <version>" from the current and previous PUBLISHED surfaces ----
class TestAvailableSince:
    def since_build(self, capsys, fx, tmp_path, *, cur, prev=None, version="26.9.0", prev_version="26.8.0", extra=()):
        flags = ["--released-api-surface", jwrite(tmp_path / "cur.json", cur), "--release-version", version]
        if prev is not None:
            flags += ["--previous-released-api-surface", jwrite(tmp_path / "prev.json", prev)]
        if prev_version:
            flags += ["--previous-release-version", prev_version]
        return build(capsys, fx, *flags, *extra)

    def test_three_outcomes_across_units(self, java, capsys, tmp_path):
        # published current = everything except RenderOptions; previous = baseline surface
        cur = [x for x in J_NEW if x["name"] != "RenderOptions"]
        code, out = self.since_build(capsys, java, tmp_path, cur=cur, prev=J_RELEASED)
        assert code == 0
        led = ledger(java)
        early, render = unit_with(led, "EarlyType"), unit_with(led, "RenderJob")
        assert (early["availability"], early["available_since"]) == ("released", "26.8.0")      # earlier
        assert render["availability"] == "unreleased" and render["available_since"] is None   # RenderOptions unshipped
        assert render["symbol_counts"]["unreleased"] == 1 and render["symbol_counts"]["since_current"] >= 1
        ctx = led["availability_context"]
        assert ctx["release_version"] == "26.9.0" and ctx["previous_release_version"] == "26.8.0"
        assert ctx["released_versions"] == ["26.8.0", "26.9.0"]
        assert ctx["symbol_counts"]["unreleased"] == 1 and ctx["symbol_counts"]["earlier"] == 1
        assert len(ctx["previous_release_surface_sha256"]) == 64

    def test_new_in_current_release(self, java, capsys, tmp_path):
        self.since_build(capsys, java, tmp_path, cur=J_NEW, prev=J_RELEASED)
        led = ledger(java)
        render = unit_with(led, "RenderJob")
        assert (render["availability"], render["available_since"], render["partial_earlier"]) == ("released", "26.9.0", False)
        assert render["release_version"] == "26.9.0"
        assert cd.validate_ledger(led, stage="plan") == []

    def test_mixed_unit_needs_current_version_and_flags_partial_earlier(self, java, capsys, tmp_path):
        ov = jwrite(tmp_path / "ov.json", [{"id": "both", "symbols": ["org.acme.core::EarlyType",
                                                                       "org.acme.render::RenderJob"]}])
        self.since_build(capsys, java, tmp_path, cur=J_NEW, prev=J_RELEASED, extra=("--grouping-overrides", ov))
        mixed = unit_with(ledger(java), "EarlyType")
        assert mixed["available_since"] == "26.9.0" and mixed["partial_earlier"] is True
        assert mixed["symbol_counts"]["earlier"] == 1 and mixed["symbol_counts"]["since_current"] >= 1

    def test_unknown_stays_unknown_and_python_shape(self, py, capsys, tmp_path):
        # python-style: previous release already had the reader; the parser is new in 3.2.0
        prev = [P_NEW[0], P_NEW[1]]
        self.since_build(capsys, py, tmp_path, cur=P_NEW, prev=prev, version="3.2.0", prev_version="3.1.0")
        led = ledger(py)
        reader, parser = unit_with(led, "CsvReader"), unit_with(led, "CsvParser")
        if reader is parser:   # token affinity merged them: mixed unit
            assert reader["available_since"] == "3.2.0" and reader["partial_earlier"] is True
        else:
            assert (reader["available_since"], parser["available_since"]) == ("3.1.0", "3.2.0")
        # no surface at all -> unknown, no since
        build(capsys, py)
        assert {(u["availability"], u["available_since"]) for u in ledger(py)["units"]} == {("unknown", None)}

    def test_without_previous_surface_since_is_unknown(self, java, capsys, tmp_path):
        self.since_build(capsys, java, tmp_path, cur=J_NEW, prev=None)
        render = unit_with(ledger(java), "RenderJob")
        assert render["availability"] == "released" and render["available_since"] is None
        assert render["symbol_counts"]["since_unknown"] >= 1

    def test_previous_version_unknown_gives_earlier_than(self, java, capsys, tmp_path):
        self.since_build(capsys, java, tmp_path, cur=J_NEW, prev=J_RELEASED, prev_version=None)
        assert unit_with(ledger(java), "EarlyType")["available_since"] == "earlier-than-26.9.0"

    def test_rerun_is_byte_identical(self, java, capsys, tmp_path):
        self.since_build(capsys, java, tmp_path, cur=J_NEW, prev=J_RELEASED)
        a = Path(java["out"]).read_bytes()
        self.since_build(capsys, java, tmp_path, cur=J_NEW, prev=J_RELEASED)
        assert Path(java["out"]).read_bytes() == a

    def test_flag_errors(self, java, capsys, tmp_path):
        prev = jwrite(tmp_path / "prev.json", J_RELEASED)
        code, out = build(capsys, java, "--previous-released-api-surface", prev, "--release-version", "1.0.0")
        assert code == 2 and "released-api-surface" in out["error"]
        code, out = build(capsys, java, "--released-api-surface", java["released"], "--previous-released-api-surface", prev)
        assert code == 2 and "release-version" in out["error"]

    def test_validate_accepts_new_fields_and_rejects_since_on_unreleased(self, java, capsys, tmp_path):
        self.since_build(capsys, java, tmp_path, cur=[x for x in J_NEW if x["name"] != "RenderOptions"], prev=J_RELEASED)
        led = ledger(java)
        assert cd.validate_ledger(led, stage="plan") == []
        unit_with(led, "RenderJob")["available_since"] = "26.9.0"          # unreleased unit must not claim a since
        assert any("available_since" in e for e in cd.validate_ledger(led, stage="plan"))


# ---- B5c: owner-name collisions resolved against the new surface ----
class TestCollidingOwners:
    def surf(self, with_export=True, forms_shared=True):
        facades = e("Form", "org.acme.facades", methods=(["exportJson"] if with_export else []) + ["other", "shared"])
        forms = e("Form", "org.acme.forms", methods=["fill", "other"] + (["shared"] if forms_shared else []))
        return [facades, forms]

    KD = {"new_apis_qualified": [], "modified_apis_qualified": ["org.acme.facades::Form", "org.acme.forms::Form"],
          "name_collisions": [{"name": "Form", "old": [], "new": [], "added": [], "removed": [],
                               "modified": ["org.acme.facades::Form", "org.acme.forms::Form"]}],
          "api_signature_changes": {"Form": {"added_methods": ["exportJson", "shared"], "removed_methods": [],
                                              "added_properties": [], "removed_properties": []}}}

    def go(self, capsys, tmp_path, *, cur, prev):
        fx = {"kd": jwrite(tmp_path / "kd.json", self.KD), "surface": jwrite(tmp_path / "surf.json", self.surf()),
              "out": tmp_path / "ledger.json"}
        code, out = build(capsys, fx, "--released-api-surface", jwrite(tmp_path / "cur.json", cur),
                          "--previous-released-api-surface", jwrite(tmp_path / "prev.json", prev),
                          "--release-version", "26.9.0", "--previous-release-version", "26.8.0")
        assert code == 0
        return ledger(fx)

    def test_resolved_member_is_qualified_and_released_since(self, capsys, tmp_path):
        led = self.go(capsys, tmp_path, cur=self.surf(), prev=self.surf(with_export=False, forms_shared=False)[:1])
        sym = next(x for x in led["units"] if "org.acme.facades::Form.exportJson" in x["symbols"])
        assert sym["availability"] == "released" and sym["available_since"] == "26.9.0"
        assert led["availability_context"]["symbol_counts"]["ambiguous_resolved"] == 1
        assert cd.validate_ledger(led, stage="plan") == []

    def test_ambiguous_member_released_iff_all_candidates_released(self, capsys, tmp_path):
        prev = [e("Form", "org.acme.facades", methods=["other"]), e("Form", "org.acme.forms", methods=["fill", "other"])]
        led = self.go(capsys, tmp_path, cur=self.surf(), prev=prev)
        amb = next(x for x in led["units"] if x["ambiguous_symbols"])
        assert amb["symbols"] == ["Form.shared"]
        assert amb["ambiguous_symbols"][0]["candidates"] == ["org.acme.facades::Form.shared", "org.acme.forms::Form.shared"]
        assert (amb["availability"], amb["available_since"]) == ("released", "26.9.0")
        # one candidate missing from the published surface -> unknown, never released
        led2 = self.go(capsys, tmp_path, cur=self.surf(forms_shared=False), prev=prev)
        amb2 = next(x for x in led2["units"] if x["ambiguous_symbols"])
        assert amb2["availability"] == "unknown" and amb2["available_since"] is None


# ---- independent-review fixes: base binding, override-gated downgrade, worth ----
class TestBindingFlagsAndWorth:
    def test_build_records_base_unreleased_versions_and_static_limits(self, java, capsys):
        build(capsys, java, "--base-sha", "a" * 40, "--base-knowledge-commit", "b" * 40,
              "--unreleased-version", "26.10.0", "--unreleased-version", "26.11.0")
        led = ledger(java)
        assert (led["base_sha"], led["base_knowledge_commit"]) == ("a" * 40, "b" * 40)
        assert led["availability_context"]["unreleased_versions"] == ["26.10.0", "26.11.0"]
        assert led["delta_kinds_unseen"] == ["behavioural", "changelog", "readme"] and led["delta_sha256"]

    def test_worth_file_at_build_and_errors(self, java, capsys, tmp_path):
        sym = "org.acme.render::RenderOptions"
        w = jwrite(tmp_path / "w.json", [{"symbol": sym, "worth": "internal", "reason": "pipeline helper"}])
        build(capsys, java, "--worth", w)
        render = unit_with(ledger(java), "RenderJob")
        assert render["symbol_worth"][sym]["worth"] == "internal" and sym in render["internal_symbols"]
        bad = jwrite(tmp_path / "bad.json", [{"symbol": "Nope::X", "worth": "internal", "reason": "r"}])
        code, out = build(capsys, java, "--worth", bad)
        assert code == 2 and "unknown symbol" in out["error"]

    def build_plain(self, java, capsys):
        build(capsys, java)
        led = ledger(java)
        return led, unit_with(led, "RenderJob")

    def test_downgrade_below_the_computed_action_needs_an_override(self, java, capsys):
        led, u = self.build_plain(java, capsys)
        before = Path(java["out"]).read_bytes()
        surf = next(s for s, d in u["dispositions"].items() if d["computed_action"] == "create")
        args = ["set-disposition", "--ledger", java["out"], "--unit", u["id"], "--surface", surf, "--action", "none",
                "--rationale", "not worth a page"]
        code, out = run(capsys, *args)
        assert code == 1 and "override" in out["error"] and Path(java["out"]).read_bytes() == before
        code, out = run(capsys, *args, "--override-token", "OV-1")
        assert code == 1 and Path(java["out"]).read_bytes() == before            # reason missing too
        code, out = run(capsys, *args, "--override-token", "OV-1", "--override-reason", "reviewer agreed it is internal")
        assert code == 0
        cell = unit_with(ledger(java), "RenderJob")["dispositions"][surf]
        assert cell["action"] == "none" and cell["computed_action"] == "create"
        assert cell["override"] == {"token_id": "OV-1", "reason": "reviewer agreed it is internal"}
        assert cd.validate_ledger(ledger(java), stage="plan") == []

    def test_upgrade_clears_the_override_and_keeps_computed_fields(self, java, capsys):
        led, u = self.build_plain(java, capsys)
        surf = next(s for s, d in u["dispositions"].items() if d["computed_action"] == "create")
        run(capsys, "set-disposition", "--ledger", java["out"], "--unit", u["id"], "--surface", surf, "--action", "none",
            "--rationale", "r", "--override-token", "OV-1", "--override-reason", "because")
        code, out = run(capsys, "set-disposition", "--ledger", java["out"], "--unit", u["id"], "--surface", surf,
                        "--action", "create", "--target", f"{surf}/x.md", "--rationale", "restored")
        cell = unit_with(ledger(java), "RenderJob")["dispositions"][surf]
        assert code == 0 and "override" not in cell and cell["computed_action"] == "create"

    def test_set_worth_recomputes_the_unit(self, java, capsys):
        led, u = self.build_plain(java, capsys)
        sym = "org.acme.render::RenderOptions"
        before = u["scale"]["new_public_types"]
        code, out = run(capsys, "set-worth", "--ledger", java["out"], "--unit", u["id"], "--symbol", sym,
                        "--worth", "internal", "--reason", "pipeline helper")
        assert code == 0 and out["ok"] is True
        new = unit_with(ledger(java), "RenderJob")
        assert new["scale"]["new_public_types"] == before - 1 and sym in new["internal_symbols"]
        assert new["id"] == u["id"] and new["symbol_worth"][sym]["reason"] == "pipeline helper"
        assert cd.validate_ledger(ledger(java), stage="plan") == []
        first = Path(java["out"]).read_bytes()
        run(capsys, "set-worth", "--ledger", java["out"], "--unit", u["id"], "--symbol", sym, "--worth", "internal",
            "--reason", "pipeline helper")
        assert Path(java["out"]).read_bytes() == first                           # idempotent
        code, _ = run(capsys, "set-worth", "--ledger", java["out"], "--unit", u["id"], "--symbol", sym,
                      "--worth", "public", "--reason", "documented after all")
        assert code == 0 and unit_with(ledger(java), "RenderJob")["scale"]["new_public_types"] == before

    def test_set_worth_refusals_leave_the_file_alone(self, java, capsys):
        led, u = self.build_plain(java, capsys)
        before = Path(java["out"]).read_bytes()
        for extra in (["--unit", "CU-deadbeef", "--symbol", "org.acme.render::RenderJob"],
                      ["--unit", u["id"], "--symbol", "ns::Missing"]):
            code, out = run(capsys, "set-worth", "--ledger", java["out"], *extra, "--worth", "internal", "--reason", "r")
            assert code == 1 and out["ok"] is False
        code, out = run(capsys, "set-worth", "--ledger", java["out"], "--unit", u["id"], "--symbol",
                        "org.acme.render::RenderJob", "--worth", "internal", "--reason", "  ")
        assert code == 1 and "reason" in out["error"]
        assert Path(java["out"]).read_bytes() == before
