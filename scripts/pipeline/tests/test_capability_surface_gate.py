"""B4/B5/B9 (MT074): commands/ops/capability_surface_gate.py -- the close-time gate and the only
caller of the propagation writer. Tmp content trees + a tmp state file; three differently shaped
products (Java-style packages, C#-style namespaces, Python-style file-qualified modules).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import availability as av
import capability_delta as cd
import capability_surface_gate as gate
import content_propagation_state as cps

HEAD = "d" * 40
KNOWLEDGE = "k" * 40
TARGETS = {"reference": "reference/", "docs": "docs/feature.md", "kb": "kb/", "blog": "blog/",
           "products": "products/new.md"}


def T(q, members=0, refs=(), kind="class"):
    return {"qualified": q, "member_count": members, "signature_refs": list(refs), "kind": kind}


def D(**kw):
    base = {"schema_version": 1, "added_types": [], "added_members": [], "enum_constants_added": [],
            "formats_added": [], "name_collisions": [], "existing_symbols": [], "public_surface_size": None,
            "ground_truth": {"tier": "KNOWLEDGE", "symbol_level": True}}
    base.update(kw)
    return base


SHAPES = {
    "java": D(added_types=[T("org.acme.render::RenderOptions", 4), T("org.acme.render::RenderJob", 6),
                           T("org.acme.render::RenderResult", 3)],
              added_members=[{"owner": "org.acme.core::Document", "name": "renderTo", "signature_refs": ["RenderJob"]}],
              existing_symbols=["Document", "Page"]),
    "net": D(added_types=[T("Acme.Sheets.Charts::ChartPalette", 3), T("Acme.Sheets.Charts::ChartTheme", 2)],
             added_members=[{"owner": "Acme.Sheets::Workbook", "name": "ApplyTheme", "signature_refs": ["ChartTheme"]}],
             existing_symbols=["Workbook", "Cell"]),
    "py": D(added_types=[T("acme/imports/csv_reader.py::CsvReader", 3), T("acme/imports/csv_parser.py::CsvParser", 2)],
            existing_symbols=["Sheet", "Book"]),
}


@pytest.fixture(autouse=True)
def _state(tmp_path):
    cps.configure(tmp_path / "state.json")
    yield tmp_path / "state.json"
    cps.configure(None)


def block_for(delta):
    return [{"id": "b1", "path": "products/index.md", "terms": [cd.simple_name(t["qualified"]) for t in delta["added_types"]]}]


def make_ledger(delta, *, availability="released", blocks="auto", head=HEAD, family="fam", platform="plat", **kw):
    units = cd.group_units(delta)
    avail = {s: availability for u in units for s in u["symbols"]} if availability else None
    return cd.build_ledger(delta, family=family, platform=platform, upstream_head=head, surface_targets=TARGETS,
                           candidate_blocks=block_for(delta) if blocks == "auto" else blocks, availability=avail, **kw)


def populate(root: Path, ledger, *, qualifier=False, extra="", skip=()):
    """Write a page for every non-none disposition that mentions every term of its unit."""
    for u in ledger["units"]:
        terms = " ".join(cd.unit_terms_from_symbols(u))
        for surface, d in u["dispositions"].items():
            if d["action"] == "none" or surface in skip or not d["target"]:
                continue
            target = d["target"].split("#", 1)[0]
            path = root / target / "page.md" if target.endswith("/") else root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            body = f"{terms}\n" + ("This capability is not yet released.\n" if qualifier else "") + extra + "\n"
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(body)


def write_ledger(tmp_path, ledger):
    p = tmp_path / "capability_ledger.json"
    cd.write_ledger(p, ledger)
    return p


def run(tmp_path, ledger, root, **kw):
    kw.setdefault("knowledge_commit_resolver", lambda f, p: KNOWLEDGE)
    kw.setdefault("model_head_resolver", lambda f, p: ledger.get("upstream_head"))
    kw.setdefault("knowledge_clean_checker", lambda f, p: (True, ""))
    return gate.run_gate("fam", "plat", write_ledger(tmp_path, ledger), [root], **kw)


def codes(report):
    return sorted({r["code"] for r in report["reasons"]})


@pytest.mark.parametrize("shape", sorted(SHAPES))
class TestPassAcrossShapes:
    def test_pass_records_propagation_with_computed_statuses(self, tmp_path, shape, _state):
        delta = SHAPES[shape]
        ledger = make_ledger(delta)
        root = tmp_path / "content"
        populate(root, ledger)
        cps.record_drift("fam", "plat", upstream_head=HEAD, knowledge_sha="1" * 40, tier="SOURCE",
                         release_state="released", ahead_by=1, files_seen=1, source_files=1,
                         api_surface_touched=True, truncated=False, ground_truth_tier="GT-2")
        code, report = run(tmp_path, ledger, root, local_only=False)
        assert code == 0 and report["verdict"] == "PASS" and report["reasons"] == [] and report["recorded"] is True
        rec = cps.read_state("fam", "plat")
        assert rec["status"] == "PROPAGATED" and rec["content_propagated_sha"] == HEAD
        assert rec["content_propagated_knowledge_commit"] == KNOWLEDGE and rec["gate_verdict"] == "PASS"
        assert rec["local_only"] is False
        assert [u["id"] for u in rec["capability_units"]] == sorted(u["id"] for u in ledger["units"])
        for unit in rec["capability_units"]:
            for surface, d in unit["dispositions"].items():
                assert d["status"] in ("satisfied", "none_justified")
                if d["status"] == "satisfied":
                    assert d["evidence_paths"]

    def test_missing_pages_fail_and_write_nothing(self, tmp_path, shape, _state):
        ledger = make_ledger(SHAPES[shape])
        root = tmp_path / "content"
        root.mkdir()
        code, report = run(tmp_path, ledger, root)
        assert code == 1 and report["verdict"] == "FAIL" and report["recorded"] is False
        assert "unsatisfied" in codes(report)
        assert not _state.exists()


class TestFailureModes:
    def setup_method(self):
        self.delta = SHAPES["net"]

    def test_unplaced_mention_hard_fails(self, tmp_path):
        ledger = make_ledger(self.delta, blocks=[])
        root = tmp_path / "content"
        populate(root, ledger)
        code, report = run(tmp_path, ledger, root)
        assert code == 1 and "ledger_invalid" in codes(report)
        assert any("unplaced" in r["detail"] for r in report["reasons"])
        assert "unsatisfied" in codes(report)

    def test_gt2_ledger_fails_closed(self, tmp_path):
        ledger = cd.build_ledger(cd.from_adapter_delta({"ground_truth_tier": "GT-2"}), family="fam", platform="plat",
                                 upstream_head=HEAD, surface_targets=TARGETS)
        code, report = run(tmp_path, ledger, tmp_path)
        assert code == 1 and codes(report) == ["no_symbol_level_ground_truth"]

    def test_symbol_level_with_no_units_passes(self, tmp_path, _state):
        ledger = cd.build_ledger(D(), family="fam", platform="plat", upstream_head=HEAD, surface_targets=TARGETS)
        code, report = run(tmp_path, ledger, tmp_path)
        assert code == 0 and cps.read_state("fam", "plat")["capability_units"] == []

    def test_missing_upstream_head(self, tmp_path):
        ledger = make_ledger(self.delta, head=None)
        root = tmp_path / "content"
        populate(root, ledger)
        code, report = run(tmp_path, ledger, root)
        assert code == 1 and codes(report) == ["missing_upstream_head"]

    def test_family_platform_mismatch(self, tmp_path):
        ledger = make_ledger(self.delta, family="other")
        root = tmp_path / "content"
        populate(root, ledger)
        code, report = run(tmp_path, ledger, root)
        assert code == 1 and "ledger_mismatch" in codes(report)

    def test_none_without_rationale_fails(self, tmp_path):
        ledger = make_ledger(self.delta)
        root = tmp_path / "content"
        populate(root, ledger)
        blog = ledger["units"][0]["dispositions"]["blog"]
        assert blog["action"] == "none"
        blog["rationale"] = ""
        code, report = run(tmp_path, ledger, root)
        assert code == 1 and any(r["surface"] == "blog" for r in report["reasons"])

    def test_term_coverage_below_threshold_fails(self, tmp_path):
        ledger = make_ledger(self.delta)
        root = tmp_path / "content"
        populate(root, ledger)
        # reference needs every type name: strip one
        for f in (root / "reference").rglob("*.md"):
            f.write_text(f.read_text(encoding="utf-8").replace("ChartPalette", "x"), encoding="utf-8")
        code, report = run(tmp_path, ledger, root)
        assert code == 1 and any(r["surface"] == "reference" and "ChartPalette" in r["detail"] for r in report["reasons"])

    def test_fail_after_pass_leaves_previous_propagation_untouched(self, tmp_path, _state):
        ledger = make_ledger(self.delta)
        root = tmp_path / "content"
        populate(root, ledger)
        assert run(tmp_path, ledger, root)[0] == 0
        before = _state.read_bytes()
        for f in root.rglob("*.md"):
            f.unlink()
        code, _ = run(tmp_path, make_ledger(self.delta, head="e" * 40), root)
        assert code == 1 and _state.read_bytes() == before


class TestAvailabilityQualifiersAndCoordinates:
    def setup_method(self):
        self.delta = SHAPES["java"]

    @pytest.mark.parametrize("state", ["unreleased", "unknown"])
    def test_non_released_units_need_a_qualifier_on_every_evidencing_page(self, tmp_path, state):
        ledger = make_ledger(self.delta, availability=state)
        root = tmp_path / "content"
        populate(root, ledger)
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and codes(report) == ["availability_qualifier_missing"]
        paths = {r["path"] for r in report["reasons"]}
        assert "docs/feature.md" in paths
        shutil_root = tmp_path / "content2"
        populate(shutil_root, ledger, qualifier=True)
        code2, report2 = run(tmp_path, ledger, shutil_root, dry_run=True)
        assert code2 == 0 and report2["reasons"] == []

    def test_released_units_need_no_qualifier(self, tmp_path):
        ledger = make_ledger(self.delta, availability="released")
        root = tmp_path / "content"
        populate(root, ledger)
        assert run(tmp_path, ledger, root, dry_run=True)[0] == 0

    def test_unknown_when_no_availability_supplied_is_treated_as_not_released(self, tmp_path):
        ledger = make_ledger(self.delta, availability=None)
        assert {u["availability"] for u in ledger["units"]} == {"unknown"}
        root = tmp_path / "content"
        populate(root, ledger)
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and codes(report) == ["availability_qualifier_missing"]

    def test_forbidden_coordinate_on_unreleased_page(self, tmp_path):
        ledger = make_ledger(self.delta, availability="unreleased",
                             availability_context={"released_versions": ["26.7.0"]})
        root = tmp_path / "content"
        populate(root, ledger, qualifier=True, extra="Add org.acme:acme-lib:26.8.0 to your build.")
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and codes(report) == ["forbidden_coordinate"]
        assert all("26.8.0" in r["detail"] for r in report["reasons"])
        ok_root = tmp_path / "ok"
        populate(ok_root, ledger, qualifier=True, extra="Current release org.acme:acme-lib:26.7.0.")
        assert run(tmp_path, ledger, ok_root, dry_run=True)[0] == 0

    def test_released_versions_cli_override_and_unknown_set_flags_everything(self, tmp_path):
        ledger = make_ledger(self.delta, availability="unreleased")   # no released set in the ledger
        root = tmp_path / "content"
        populate(root, ledger, qualifier=True, extra="Use org.acme:acme-lib:26.7.0.")
        assert run(tmp_path, ledger, root, dry_run=True)[0] == 1
        assert run(tmp_path, ledger, root, dry_run=True, released_versions=["26.7.0"])[0] == 0

    def test_unreleased_unit_is_not_written_to_state_when_gate_fails(self, tmp_path, _state):
        ledger = make_ledger(self.delta, availability="unreleased")
        root = tmp_path / "content"
        populate(root, ledger)
        run(tmp_path, ledger, root)
        assert not _state.exists()

    def test_unreleased_pass_records_the_availability(self, tmp_path):
        ledger = make_ledger(self.delta, availability="unreleased",
                             availability_context={"released_versions": ["26.7.0"]})
        root = tmp_path / "content"
        populate(root, ledger, qualifier=True)
        assert run(tmp_path, ledger, root)[0] == 0
        assert {u["availability"] for u in cps.read_state("fam", "plat")["capability_units"]} == {"unreleased"}


class TestFlags:
    def test_dry_run_never_writes(self, tmp_path, _state):
        ledger = make_ledger(SHAPES["py"])
        root = tmp_path / "content"
        populate(root, ledger)
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 0 and report["verdict"] == "PASS" and report["recorded"] is False
        assert not _state.exists()

    def test_local_only_is_recorded(self, tmp_path):
        ledger = make_ledger(SHAPES["py"])
        root = tmp_path / "content"
        populate(root, ledger)
        assert run(tmp_path, ledger, root, local_only=True)[0] == 0
        rec = cps.read_state("fam", "plat")
        assert rec["local_only"] is True

    def test_state_path_flag_redirects_the_write(self, tmp_path, _state):
        ledger = make_ledger(SHAPES["py"])
        root = tmp_path / "content"
        populate(root, ledger)
        other = tmp_path / "elsewhere" / "state.json"
        assert run(tmp_path, ledger, root, state_path=other)[0] == 0
        assert other.exists() and not _state.exists()

    def test_report_is_deterministic(self, tmp_path):
        ledger = make_ledger(SHAPES["net"])
        root = tmp_path / "content"
        populate(root, ledger)
        a = gate._dump(run(tmp_path, ledger, root, dry_run=True)[1])
        b = gate._dump(run(tmp_path, ledger, root, dry_run=True)[1])
        assert a == b


class TestCliDefaultContentRoot:
    """MT074 (found live, 2026-10-09): running the real pdf/java capability_ledger_real.json
    (built by capability_ledger.py set-disposition --target content/docs.aspose.org/...,
    this repo's only sanctioned writer) through the gate with no --content-root flag
    reported "target not found" for every single disposition, even ones with a real,
    committed file on disk -- because every real target is already a full repo-relative
    path INCLUDING "content/", and the old default root was `_REPO_ROOT / "content"`,
    doubling the prefix to ".../content/content/...". The gate could never pass against
    a real ledger. Default root must be `_REPO_ROOT` itself."""

    def test_default_root_matches_real_content_prefixed_targets(self, tmp_path, capsys, _state):
        gate.configure(repo_root=tmp_path)
        try:
            targets = {"reference": "content/reference.aspose.org/en/fam/plat/Feature.md",
                       "docs": "content/docs.aspose.org/en/fam/plat/developer-guide/feature.md",
                       "kb": "content/kb.aspose.org/en/fam/plat/how-to-feature.md",
                       "blog": "content/blog.aspose.org/fam/plat/feature/index.md",
                       "products": "content/products.aspose.org/en/fam/_index.md"}
            delta = SHAPES["py"]
            units = cd.group_units(delta)
            avail = {s: "released" for u in units for s in u["symbols"]}
            ledger = cd.build_ledger(delta, family="fam", platform="plat", upstream_head=HEAD,
                                     surface_targets=targets, candidate_blocks=block_for(delta), availability=avail)
            lp = write_ledger(tmp_path, ledger)
            # Populate real files directly under tmp_path (standing in for the repo root),
            # at exactly the content/-prefixed paths the targets already carry -- no extra
            # "content" subdirectory layer, matching how set-disposition actually stores them.
            populate(tmp_path, ledger)
            argv = ["--family", "fam", "--platform", "plat", "--ledger", str(lp), "--state-path", str(_state)]
            seams = dict(model_head_resolver=lambda f, p: ledger["upstream_head"],
                         knowledge_clean_checker=lambda f, p: (True, ""), knowledge_commit_resolver=lambda f, p: KNOWLEDGE)
            code = gate.main(argv + ["--dry-run"], **seams)
            shown = json.loads(capsys.readouterr().out)
            assert code == 0, shown["reasons"]
            assert not any(r["code"] == "unsatisfied" for r in shown["reasons"]), shown["reasons"]
        finally:
            gate.configure()


class TestCli:
    def test_cli_pass_fail_and_json_out(self, tmp_path, capsys, _state):
        ledger = make_ledger(SHAPES["py"])
        root = tmp_path / "content"
        lp = write_ledger(tmp_path, ledger)
        out = tmp_path / "rep" / "gate.json"
        argv = ["--family", "fam", "--platform", "plat", "--ledger", str(lp), "--content-root", str(root),
                "--state-path", str(_state), "--json-out", str(out)]
        seams = dict(model_head_resolver=lambda f, p: ledger["upstream_head"],
                     knowledge_clean_checker=lambda f, p: (True, ""), knowledge_commit_resolver=lambda f, p: KNOWLEDGE)
        assert gate.main(argv, **seams) == 1                      # nothing written yet
        shown = json.loads(capsys.readouterr().out)
        assert shown["verdict"] == "FAIL" and shown["reasons"] and not _state.exists()
        assert json.loads(out.read_text(encoding="utf-8")) == shown
        populate(root, ledger)
        assert gate.main(argv + ["--dry-run"], **seams) == 0
        assert not _state.exists()
        assert gate.main(argv + ["--local-only"], **seams) == 0
        rec = cps.read_state("fam", "plat")
        assert rec["local_only"] is True and rec["gate_verdict"] == "PASS"

    def test_cli_unreadable_ledger_exits_2(self, tmp_path, capsys):
        code = gate.main(["--family", "f", "--platform", "p", "--ledger", str(tmp_path / "nope.json"),
                          "--content-root", str(tmp_path)])
        assert code == 2
        assert json.loads(capsys.readouterr().out)["reasons"][0]["code"] == "gate_error"

    def test_cli_corrupt_state_file_exits_2_and_is_not_overwritten(self, tmp_path, capsys, _state):
        ledger = make_ledger(SHAPES["py"])
        root = tmp_path / "content"
        populate(root, ledger)
        _state.write_text("{not json", encoding="utf-8")
        code = gate.main(["--family", "fam", "--platform", "plat", "--ledger", str(write_ledger(tmp_path, ledger)),
                          "--content-root", str(root), "--state-path", str(_state)],
                         model_head_resolver=lambda f, p: ledger["upstream_head"],
                         knowledge_clean_checker=lambda f, p: (True, ""))
        assert code == 2 and _state.read_text(encoding="utf-8") == "{not json"


class TestWriteBoundary:
    def test_this_module_is_the_sole_caller_and_calls_it_only_after_a_pass(self):
        src = Path(gate.__file__).read_text(encoding="utf-8")
        assert src.count("cps.record_propagation(") == 1
        pre = src.split("cps.record_propagation(")[0]
        assert 'report["verdict"] != PASS' in pre and "if dry_run" in pre


class TestReleasedVersionCoordinates:
    """B5b: a unit released in V may cite V; an unpublished coordinate is still flagged."""

    def released_ledger(self, delta, since="26.9.0", ctx_extra=None, state="released"):
        units = cd.group_units(delta)
        info = {"state": state, "available_since": since if state == "released" else None,
                "since_basis": "current_only"}
        avail = {s: dict(info) for u in units for s in u["symbols"]}
        ctx = {"release_version": "26.9.0", "previous_release_version": "26.8.0", "released_versions": ["26.8.0"]}
        ctx.update(ctx_extra or {})
        return cd.build_ledger(delta, family="fam", platform="plat", upstream_head=HEAD, surface_targets=TARGETS,
                               candidate_blocks=block_for(delta), availability=avail, availability_context=ctx)

    @pytest.mark.parametrize("shape", sorted(SHAPES))
    def test_released_version_allowed_unpublished_flagged(self, tmp_path, shape):
        ledger = self.released_ledger(SHAPES[shape])
        assert {u["available_since"] for u in ledger["units"]} == {"26.9.0"}
        ok = tmp_path / "ok"
        populate(ok, ledger, extra="Requires org.acme:acme-lib:26.9.0 or later (Since 26.9.0).")
        code, report = run(tmp_path, ledger, ok, dry_run=True)
        assert code == 0 and report["reasons"] == []
        bad = tmp_path / "bad"
        populate(bad, ledger, extra="Preview org.acme:acme-lib:26.10.0 is coming.")
        code, report = run(tmp_path, ledger, bad, dry_run=True)
        assert code == 1 and codes(report) == ["forbidden_coordinate"]
        assert all("26.10.0" in r["detail"] for r in report["reasons"])

    def test_release_version_is_allowed_for_released_units_even_without_available_since(self, tmp_path):
        ledger = self.released_ledger(SHAPES["net"], since=None)
        root = tmp_path / "content"
        populate(root, ledger, extra="Use acme-tables==26.9.0 now.")
        assert run(tmp_path, ledger, root, dry_run=True)[0] == 0

    def test_unreleased_unit_may_not_cite_the_release_version(self, tmp_path):
        ledger = self.released_ledger(SHAPES["net"], state="unreleased")
        root = tmp_path / "content"
        populate(root, ledger, qualifier=True, extra="Use org.acme:acme-lib:26.9.0 now.")
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and codes(report) == ["forbidden_coordinate"]

    def test_released_unit_pass_records_state(self, tmp_path):
        ledger = self.released_ledger(SHAPES["py"])
        root = tmp_path / "content"
        populate(root, ledger, extra="Since 26.9.0.")
        assert run(tmp_path, ledger, root)[0] == 0
        assert {u["availability"] for u in cps.read_state("fam", "plat")["capability_units"]} == {"released"}


# ───────────────────────── independent-review fixes (B1, B2, M5, m1, m2) ─────────────────────────

TWO_UNITS = D(added_types=[T("a.x::Alpha", 2), T("b.y::Beta", 2)], existing_symbols=[])
PRIOR_SHA, PRIOR_K = "a" * 40, "c" * 40


def write_pages(root, ledger, *, frontmatter="", body_terms=True, suffix=""):
    """One page per non-none disposition; optionally with frontmatter and without the terms in the body."""
    for u in ledger["units"]:
        terms = " ".join(cd.unit_terms_from_symbols(u))
        for surface, d in u["dispositions"].items():
            if d["action"] == "none" or not d["target"]:
                continue
            target = d["target"].split("#", 1)[0]
            path = root / target / f"page{suffix}.md" if target.endswith("/") else root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(frontmatter + (terms if body_terms else "an empty body") + "\n")


def good(tmp_path, delta=None, **kw):
    ledger = make_ledger(delta or SHAPES["net"], **kw)
    root = tmp_path / "content"
    populate(root, ledger)
    return ledger, root


class TestEvidenceHygieneGate:
    FM_DRAFT = "---\ntitle: T\ndraft: true\nevidence:\n  apis: [ChartTheme, ChartPalette, CsvReader, CsvParser]\n---\n"
    FM = "---\ntitle: T\nevidence:\n  apis: [ChartTheme, ChartPalette, CsvReader, CsvParser]\n---\n"

    def test_five_draft_pages_with_frontmatter_evidence_fail(self, tmp_path, _state):
        ledger = make_ledger(SHAPES["net"])
        root = tmp_path / "content"
        write_pages(root, ledger, frontmatter=self.FM_DRAFT, body_terms=False)
        code, report = run(tmp_path, ledger, root)
        assert code == 1 and "unsatisfied" in codes(report) and not _state.exists()
        assert report["refused_evidence"] and {r["reason"] for r in report["refused_evidence"]} == {"draft"}

    def test_frontmatter_only_mentions_fail_even_when_not_draft(self, tmp_path):
        ledger = make_ledger(SHAPES["net"])
        root = tmp_path / "content"
        write_pages(root, ledger, frontmatter=self.FM, body_terms=False)
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and "unsatisfied" in codes(report) and report["refused_evidence"] == []

    def test_locale_suffixed_pages_are_refused_with_reason(self, tmp_path):
        ledger = make_ledger(SHAPES["net"])
        root = tmp_path / "content"
        write_pages(root, ledger, suffix=".fr")
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1
        assert {r["reason"] for r in report["refused_evidence"]} == {"locale-suffixed"}

    def test_real_body_with_frontmatter_passes(self, tmp_path):
        ledger = make_ledger(SHAPES["net"])
        root = tmp_path / "content"
        write_pages(root, ledger, frontmatter=self.FM)
        assert run(tmp_path, ledger, root, dry_run=True)[0] == 0


class TestLedgerBindingGate:
    def test_empty_units_with_a_nonempty_delta_fail(self, tmp_path):
        ledger, root = good(tmp_path)
        ledger["units"] = []
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and "delta_not_proven_empty" in codes(report)

    def test_a_deleted_unit_fails(self, tmp_path):
        ledger, root = good(tmp_path, TWO_UNITS)
        assert len(ledger["units"]) == 2
        del ledger["units"][0]
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and "delta_incomplete" in codes(report)

    def test_all_none_rewrite_fails(self, tmp_path):
        ledger, root = good(tmp_path)
        for u in ledger["units"]:
            for d in u["dispositions"].values():
                d.update(action="none", target=None, status="none_justified", rationale="nothing to do", placement=None)
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and "ledger_invalid" in codes(report)
        assert any("weaker" in r["detail"] for r in report["reasons"])

    def test_all_none_rewrite_with_computed_action_also_rewritten_is_caught_by_recompute(self, tmp_path):
        ledger, root = good(tmp_path)
        for u in ledger["units"]:
            for d in u["dispositions"].values():
                d.update(action="none", computed_action="none", target=None, status="none_justified",
                         rationale="nothing to do", placement=None, computed_placement=None)
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and "computed_action_tampered" in codes(report)

    def test_downgrade_without_override_fails_and_with_override_passes(self, tmp_path):
        ledger, root = good(tmp_path)
        cell = next(d for d in ledger["units"][0]["dispositions"].values() if d["action"] == "create")
        cell.update(action="none", target=None, status="none_justified", rationale="reviewed", placement=None)
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and any("weaker" in r["detail"] for r in report["reasons"])
        cell["override"] = {"token_id": "OV-7", "reason": "reviewer agreed it is internal"}
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 0 and report["reasons"] == []

    @pytest.mark.parametrize("head", ["not a sha at all", "abc123", "D" * 40, "d" * 39, "d" * 41, "g" * 40])
    def test_upstream_head_must_be_40_lowercase_hex(self, tmp_path, head):
        ledger, root = good(tmp_path, head=head)
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and "upstream_head_invalid" in codes(report)

    def test_stale_config_hash_fails_with_a_clear_message(self, tmp_path):
        ledger, root = good(tmp_path)
        ledger["config_sha256"] = "0" * 64
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and codes(report) == ["config_changed"]
        assert "rebuild" in report["reasons"][0]["detail"]

    def test_ledger_head_must_equal_the_model_head(self, tmp_path):
        ledger, root = good(tmp_path)
        code, report = run(tmp_path, ledger, root, dry_run=True, model_head_resolver=lambda f, p: "e" * 40)
        assert code == 1 and codes(report) == ["upstream_head_mismatch"]
        code, report = run(tmp_path, ledger, root, dry_run=True, model_head_resolver=lambda f, p: None)
        assert code == 1 and codes(report) == ["model_head_unavailable"]

    def test_dirty_knowledge_tree_fails_and_writes_nothing(self, tmp_path, _state):
        ledger, root = good(tmp_path)
        code, report = run(tmp_path, ledger, root, knowledge_clean_checker=lambda f, p: (False, " M knowledge/fam/plat/x"))
        assert code == 1 and codes(report) == ["knowledge_tree_dirty"] and not _state.exists()
        assert "knowledge/fam/plat/x" in report["reasons"][0]["detail"]

    def test_default_checks_fail_closed_without_a_model_or_git(self, tmp_path):
        ledger, root = good(tmp_path)
        code, report = gate.run_gate("fam", "plat", write_ledger(tmp_path, ledger), [root], dry_run=True,
                                     model_head_resolver=lambda f, p: ledger["upstream_head"],
                                     knowledge_clean_checker=lambda f, p: (False, "git status failed"))
        assert code == 1 and "knowledge_tree_dirty" in codes(report)

    def test_cumulative_coverage_requires_the_ledger_base_to_be_the_propagated_sha(self, tmp_path, _state):
        cps.record_propagation("fam", "plat", content_propagated_sha=PRIOR_SHA, content_propagated_knowledge_commit=PRIOR_K,
                               local_only=False, capability_units=[], gate_verdict="PASS")
        ledger, root = good(tmp_path)
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and codes(report) == ["ledger_does_not_cover"]
        assert "ledger does not cover propagated..head" in report["reasons"][0]["detail"]
        wrong = make_ledger(SHAPES["net"], base_sha="b" * 40, base_knowledge_commit=PRIOR_K)
        assert run(tmp_path, wrong, root, dry_run=True)[0] == 1
        wrong_k = make_ledger(SHAPES["net"], base_sha=PRIOR_SHA, base_knowledge_commit="d" * 40)
        code, report = run(tmp_path, wrong_k, root, dry_run=True)
        assert code == 1 and codes(report) == ["ledger_does_not_cover"]
        right = make_ledger(SHAPES["net"], base_sha=PRIOR_SHA, base_knowledge_commit=PRIOR_K)
        code, report = run(tmp_path, right, root, is_descendant=lambda old, new: True)
        assert code == 0 and cps.read_state("fam", "plat")["content_propagated_sha"] == HEAD

    def test_first_propagation_needs_no_base(self, tmp_path):
        ledger, root = good(tmp_path)
        assert run(tmp_path, ledger, root, dry_run=True)[0] == 0

    def test_report_states_what_is_not_verified(self, tmp_path):
        ledger, root = good(tmp_path)
        report = run(tmp_path, ledger, root, dry_run=True)[1]
        assert report["not_verified"] == ["behavioural", "changelog", "readme",
                                          "overloads of existing method names"]


class TestConfigDamageGate:
    @pytest.mark.parametrize("path", cd.REQUIRED_KEYS, ids=[".".join(k) for k in cd.REQUIRED_KEYS])
    def test_every_missing_key_fails_the_gate_naming_it(self, tmp_path, _state, path):
        ledger, root = good(tmp_path)
        c = copy.deepcopy(cd.load_config())
        node = c
        for k in path[:-1]:
            node = node[k]
        del node[path[-1]]
        code, report = run(tmp_path, ledger, root, config=c)
        assert code == 1 and "config_missing_key" in codes(report) and not _state.exists()
        assert any(".".join(path) in r["detail"] for r in report["reasons"])

    def test_cli_config_flag_with_damaged_file_exits_nonzero(self, tmp_path, capsys, _state):
        import yaml
        ledger, root = good(tmp_path)
        c = copy.deepcopy(cd.load_config())
        del c["satisfaction"]["min_term_ratio"]["reference"]
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(yaml.safe_dump(c), encoding="utf-8")
        code = gate.main(["--family", "fam", "--platform", "plat", "--ledger", str(write_ledger(tmp_path, ledger)),
                          "--content-root", str(root), "--state-path", str(_state), "--config", str(cfg), "--dry-run"])
        out = json.loads(capsys.readouterr().out)
        assert code == 1 and any("satisfaction.min_term_ratio.reference" in r["detail"] for r in out["reasons"])


class TestQualifierPerMentionGate:
    def test_a_qualifier_far_from_a_mention_does_not_cover_it(self, tmp_path):
        ledger = make_ledger(SHAPES["java"], availability="unreleased")
        root = tmp_path / "content"
        populate(root, ledger, qualifier=True)
        page = root / "docs" / "feature.md"
        page.write_text(page.read_text(encoding="utf-8") + "x" * 900 + "\nElsewhere RenderJob is used again.\n",
                        encoding="utf-8")
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and codes(report) == ["availability_qualifier_missing"]
        assert {r["path"] for r in report["reasons"]} == {"docs/feature.md"}

    @pytest.mark.parametrize("phrase", ["Everything here is already released, not unreleased.",
                                        "Unreleased changes are listed in the changelog.",
                                        "This part is in development by another team."])
    def test_review_false_qualifiers_do_not_satisfy(self, tmp_path, phrase):
        ledger = make_ledger(SHAPES["java"], availability="unreleased")
        root = tmp_path / "content"
        populate(root, ledger)
        for f in root.rglob("*.md"):
            f.write_text(f.read_text(encoding="utf-8") + phrase + "\n", encoding="utf-8")
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and "availability_qualifier_missing" in codes(report)


class TestCoordinateRulesGate:
    def released(self, extra, **ctx):
        ledger = TestReleasedVersionCoordinates().released_ledger(SHAPES["java"], ctx_extra=ctx)
        return ledger

    def test_tool_versions_dates_and_addresses_are_not_flagged(self, tmp_path):
        ledger = self.released("")
        root = tmp_path / "content"
        populate(root, ledger, extra="Needs JDK 17.0.2 and Hugo 0.121.0 on 192.168.0.1 built 2026.10.07. Prior versions: 26.8.0.")
        assert run(tmp_path, ledger, root, dry_run=True)[0] == 0

    def test_two_component_since_version_is_flagged(self, tmp_path):
        ledger = self.released("")
        root = tmp_path / "content"
        populate(root, ledger, extra="Since 26.11 the API exists.")
        code, report = run(tmp_path, ledger, root, dry_run=True)
        assert code == 1 and codes(report) == ["forbidden_coordinate"]

    def test_unreleased_set_from_the_ledger_and_the_cli_flag(self, tmp_path):
        ledger = self.released("", unreleased_versions=["26.10.0"])
        root = tmp_path / "content"
        populate(root, ledger, extra="Coming in 26.10.0.")
        assert run(tmp_path, ledger, root, dry_run=True)[0] == 1
        ledger2 = self.released("")
        root2 = tmp_path / "c2"
        populate(root2, ledger2, extra="Coming in 26.12.0.")
        assert run(tmp_path, ledger2, root2, dry_run=True)[0] == 0
        assert run(tmp_path, ledger2, root2, dry_run=True, unreleased_versions=["26.12.0"])[0] == 1
