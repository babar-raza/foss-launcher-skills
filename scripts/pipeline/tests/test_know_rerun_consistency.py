"""MT074 B13 -- knowledge-lane rerun consistency.

Proves, with a FAKE LLM only (no network, no router, no cache I/O), that a rerun over
unchanged or slightly changed inputs does not lose, churn or needlessly regenerate
enriched claims:

  (a) tracked-state seed + promote fail-closed
  (b) re-identified claim restamp (+ incident replay through the real delta writer)
  (c) incremental per-unit enrichment with a stable hash partition
  (d) LF-normalised extractor hash, preserved/stamped by promote

Every test runs against at least two differently shaped products (a Java-like one with
qualified imports and a Python-like one with only file paths).
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import enrich as E  # noqa: E402
import promote as P  # noqa: E402
import refresh_knowledge as RK  # noqa: E402


def _load_attach_evidence():
    path = Path(__file__).resolve().parents[1] / "commands" / "healing" / "attach_evidence.py"
    spec = importlib.util.spec_from_file_location("attach_evidence_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AE = _load_attach_evidence()
_NOGATE = lambda fam, plat: None  # noqa: E731  (no audit gate: gates have their own tests)


# ---------------------------------------------------------------------------
# Product shapes + fixtures
# ---------------------------------------------------------------------------

SHAPES = {
    "java_like": {"family": "ptxj", "platform": "java", "qualified": True, "ext": ".java"},
    "py_like": {"family": "ptxp", "platform": "python", "qualified": False, "ext": ".py"},
}
SHAPE_IDS = list(SHAPES)


def _names(prefix: str, n: int) -> list[str]:
    return [f"{prefix}Widget{i:03d}" for i in range(n)]


def _entry(shape: dict, name: str, *, doc: str | None = None, extra_method: str | None = None,
           line: int = 10) -> dict:
    low = name.lower()
    methods = [{"name": f"{low}Run", "params": [{"name": "arg", "type": "int"}],
                "return_type": "void", "doc": ""}]
    if extra_method:
        methods.append({"name": extra_method, "params": [], "return_type": "int", "doc": ""})
    entry = {
        "name": name, "kind": "class_declaration", "doc": doc if doc is not None else f"{name} docs.",
        "file": f"src/main/{shape['platform']}/{name}{shape['ext']}", "line": str(line),
        "methods": methods,
        "properties": [{"name": f"{low}Prop", "type": "int", "doc": ""}],
        "enum_members": [], "visibility": "public",
    }
    if shape["qualified"]:
        entry["class_import"] = f"org.demo.{shape['family']}.{name}"
        entry["canonical_namespace"] = f"org.demo.{shape['family']}"
    return entry


def _surface(shape: dict, names: list[str]) -> list[dict]:
    return [_entry(shape, n) for n in names]


@pytest.fixture(autouse=True)
def _reset_enrich_hooks():
    yield
    E.configure()


class Product:
    """A tmp knowledge tree for one product shape."""

    def __init__(self, tmp_path: Path, shape_id: str):
        self.shape = SHAPES[shape_id]
        self.family, self.platform = self.shape["family"], self.shape["platform"]
        self.kroot = tmp_path / "knowledge"
        self.base = self.kroot / self.family / self.platform
        self.scout = self.base / "scout"
        self.merged = self.base / "merged"
        self.reports = tmp_path / "reports"
        self.scout.mkdir(parents=True)

    def write_surface(self, entries: list[dict]) -> None:
        (self.scout / "api_surface.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def write_scout(self) -> None:
        (self.scout / "claims.json").write_text(json.dumps([
            {"claim_id": f"CLM-{self.family}-000001", "text": "Scout level fact one.", "kind": "format"},
        ], indent=2), encoding="utf-8")
        (self.scout / "model.yaml").write_text(yaml.dump({
            "family": self.family, "platform": self.platform, "repo_sha": "sha-one", "version": "1.0",
        }), encoding="utf-8")

    def enrich(self, fake, *, mode="capability", **kw) -> bool:
        E.configure(llm_call_fn=fake, preflight_fn=lambda: {"fake": "ok"},
                    clone_exists_fn=lambda _f, _p: False,
                    metrics_fn=lambda *a, **k: None)
        return E.enrich(self.family, self.platform, knowledge_root=str(self.kroot),
                        mode=mode, reports_root=str(self.reports), **kw)

    def promote(self, **kw) -> bool:
        return P.promote(self.family, self.platform, knowledge_root=str(self.kroot), **kw)

    def enriched(self) -> dict:
        return json.loads((self.scout / "enriched_claims.json").read_text(encoding="utf-8"))

    def merged_bytes(self) -> bytes:
        return (self.merged / "claims.json").read_bytes()


class FakeLLM:
    """Deterministic stand-in for enrich._llm_call; records every call."""

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []
        self.fail_classes: set[str] = set()

    def __call__(self, prompt_system, prompt_user, cache=None, cache_extra=None):
        classes = re.findall(r"^Class: (\w+)$", prompt_user, flags=re.M)
        if "llm_member_doc" in prompt_user:
            self.calls.append(("member", classes))
            if set(classes) & self.fail_classes:
                return None, ""
            cls = classes[0]
            claims = []
            for m in re.findall(r"^  method (\w+)\(", prompt_user, flags=re.M) + \
                    re.findall(r"^  property (\w+)", prompt_user, flags=re.M):
                claims.append({
                    "text": f"{cls}.{m} uses {m}k1 {m}k2 {m}k3 in its {m}k4 workflow",
                    "kind": "api", "confidence": 0.9, "claim_source": "llm_member_doc",
                })
            return claims, "fake/model"
        self.calls.append(("capability", classes))
        if set(classes) & self.fail_classes:
            return None, ""
        claims = [{
            "text": f"{c} provides capability {c}capx for {c}", "kind": "api",
            "page_role": "docs", "confidence": 0.9, "claim_source": "llm_enriched",
        } for c in classes]
        return claims, "fake/model"


def _full_build(prod: Product, names: list[str], fake: FakeLLM, *, mode="capability") -> None:
    prod.write_surface(_surface(prod.shape, names))
    prod.write_scout()
    assert prod.enrich(fake, mode=mode) is True
    assert prod.promote() is True


def _erc(path: Path) -> list[dict]:
    return [c for c in json.loads(path.read_text(encoding="utf-8"))
            if str(c.get("claim_id", "")).startswith("ERC-")]


# ---------------------------------------------------------------------------
# (a) tracked-state seed + fail-closed promote
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("shape_id", SHAPE_IDS)
class TestTrackedSeedAndFailClosed:
    def test_scout_enrichment_deleted_erc_claims_survive_via_tracked_seed(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        fake = FakeLLM()
        _full_build(prod, _names("Seed", 6), fake)
        before = prod.merged_bytes()
        assert _erc(prod.merged / "claims.json")
        (prod.scout / "enriched_claims.json").unlink()          # untracked state gone

        fake2 = FakeLLM()
        assert prod.enrich(fake2) is True
        assert fake2.calls == [], "seeded + stamped units must need ZERO LLM calls"
        assert prod.promote() is True
        assert prod.merged_bytes() == before, "ERC claims must survive byte-identically"

    def test_seed_strips_promote_provenance_key(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        _full_build(prod, _names("Seed", 4), FakeLLM())
        (prod.scout / "enriched_claims.json").unlink()
        assert prod.enrich(FakeLLM(), no_llm=True) is True
        seeded = prod.enriched()["claims"]
        assert seeded and all("provenance" not in c for c in seeded)

    def test_promote_aborts_when_seed_and_enrichment_both_absent(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        _full_build(prod, _names("Gate", 5), FakeLLM())
        before = prod.merged_bytes()
        (prod.scout / "enriched_claims.json").unlink()
        assert prod.promote() is False, "promote must FAIL CLOSED"
        assert prod.merged_bytes() == before, "nothing may be written on abort"

    def test_promote_aborts_on_empty_enrichment_file(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        _full_build(prod, _names("Gate", 5), FakeLLM())
        before = prod.merged_bytes()
        (prod.scout / "enriched_claims.json").write_text(json.dumps({"claims": []}), encoding="utf-8")
        assert prod.promote() is False
        assert prod.merged_bytes() == before

    def test_promote_aborts_on_stale_enrichment(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        _full_build(prod, _names("Gate", 5), FakeLLM())
        before = prod.merged_bytes()
        data = prod.enriched()
        data["api_surface_sha"] = "0" * 16
        (prod.scout / "enriched_claims.json").write_text(json.dumps(data), encoding="utf-8")
        assert prod.promote() is False
        assert prod.merged_bytes() == before

    def _truncate_enrichment(self, prod, keep: int) -> None:
        data = prod.enriched()
        data["claims"] = data["claims"][:keep]
        data["claim_count"] = keep
        (prod.scout / "enriched_claims.json").write_text(json.dumps(data), encoding="utf-8")

    def test_partial_loss_below_ratio_aborts(self, tmp_path, shape_id):
        """R1-6: a stale/truncated enrichment retaining only 25% of the tracked ERC claims."""
        prod = Product(tmp_path, shape_id)
        _full_build(prod, _names("Drop", 20), FakeLLM())
        before = prod.merged_bytes()
        self._truncate_enrichment(prod, 5)
        assert prod.promote() is False
        assert prod.merged_bytes() == before
        assert prod.promote(allow_drop_enrichment=True) is True
        assert len(_erc(prod.merged / "claims.json")) == 5

    def test_loss_at_or_above_ratio_is_not_blocked(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        _full_build(prod, _names("Drop", 20), FakeLLM())
        self._truncate_enrichment(prod, 10)          # exactly 50%: allowed
        assert P.ENRICHMENT_MIN_RETAINED_RATIO == 0.5
        assert prod.promote() is True
        assert len(_erc(prod.merged / "claims.json")) == 10

    def test_allow_drop_enrichment_bypass_works_and_is_loud(self, tmp_path, shape_id, capsys):
        prod = Product(tmp_path, shape_id)
        _full_build(prod, _names("Gate", 5), FakeLLM())
        (prod.scout / "enriched_claims.json").unlink()
        assert prod.promote(allow_drop_enrichment=True) is True
        assert not _erc(prod.merged / "claims.json")
        assert "allow-drop-enrichment" in capsys.readouterr().out

    def test_first_ever_promote_without_enrichment_is_unaffected(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        prod.write_surface(_surface(prod.shape, _names("Fresh", 3)))
        prod.write_scout()
        assert prod.promote() is True, "no tracked ERC claims => nothing to protect => no abort"

    def test_promote_atomic_forwards_flag_and_fails_closed(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        _full_build(prod, _names("Gate", 5), FakeLLM())
        before = prod.merged_bytes()
        (prod.scout / "enriched_claims.json").unlink()
        assert P.promote_atomic(prod.family, prod.platform, knowledge_root=str(prod.kroot)) is False
        assert prod.merged_bytes() == before
        assert P.promote_atomic(prod.family, prod.platform, knowledge_root=str(prod.kroot),
                                allow_drop_enrichment=True) is True


# ---------------------------------------------------------------------------
# (c) incremental per-unit enrichment + stable partition
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("shape_id", SHAPE_IDS)
class TestIncrementalEnrichment:
    def test_one_new_class_reenriches_exactly_one_capability_batch(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        names = _names("Inc", 45)
        _full_build(prod, names, FakeLLM())
        first = {c["claim_id"]: c for c in prod.enriched()["claims"]}

        fake = FakeLLM()
        prod.write_surface(_surface(prod.shape, names + ["AaaIncWidgetNEW"]))
        assert prod.enrich(fake) is True
        assert len(fake.calls) == 1, f"expected ONE batch re-enriched, got {fake.calls}"
        assert "AaaIncWidgetNEW" in fake.calls[0][1]
        after = {c["claim_id"]: c for c in prod.enriched()["claims"]}
        new_claim = next(c for c in after.values() if "AaaIncWidgetNEW" in c["text"])
        regenerated_unit = new_claim["enrich_unit"]
        untouched = [cid for cid, c in first.items() if c["enrich_unit"] != regenerated_unit]
        assert len(untouched) == len(first) - len(fake.calls[0][1]) + 1
        for cid in untouched:
            assert after[cid] == first[cid], "unchanged units must be carried forward byte-identical"
        # the regenerated unit lost nothing: every previous claim of it is still present
        assert {cid for cid, c in first.items() if c["enrich_unit"] == regenerated_unit} <= set(after)

    def test_changed_class_signature_reenriches_only_its_batch(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        names = _names("Chg", 45)
        _full_build(prod, names, FakeLLM())
        entries = _surface(prod.shape, names)
        entries[7] = _entry(prod.shape, names[7], extra_method="chg007Extra")
        fake = FakeLLM()
        prod.write_surface(entries)
        assert prod.enrich(fake) is True
        assert len(fake.calls) == 1 and names[7] in fake.calls[0][1]

    def test_unchanged_rerun_makes_zero_calls_and_does_not_touch_the_file(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        names = _names("Same", 45)
        _full_build(prod, names, FakeLLM())
        raw = (prod.scout / "enriched_claims.json").read_bytes()
        fake = FakeLLM()
        assert prod.enrich(fake) is True
        assert fake.calls == []
        assert (prod.scout / "enriched_claims.json").read_bytes() == raw

    def test_line_number_only_change_makes_no_calls_but_refreshes_api_sha(self, tmp_path, shape_id):
        """api_surface moved (e.g. a line number) but no enrichment unit changed: no LLM, claims
        identical, and api_surface_sha refreshed -- otherwise promote would treat ALL ERC claims
        as stale."""
        prod = Product(tmp_path, shape_id)
        names = _names("Line", 30)
        _full_build(prod, names, FakeLLM())
        old = prod.enriched()
        entries = _surface(prod.shape, names)
        for e in entries:
            e["line"] = "999"
        prod.write_surface(entries)
        fake = FakeLLM()
        assert prod.enrich(fake) is True
        assert fake.calls == []
        new = prod.enriched()
        assert new["claims"] == old["claims"]
        assert new["api_surface_sha"] != old["api_surface_sha"]
        assert prod.promote() is True, "refreshed sha => promote must not see the claims as stale"

    def test_llm_outage_on_a_changed_unit_does_not_bless_stale_claims(self, tmp_path, shape_id):
        """The api_surface changed AND the LLM is down for the changed unit: the file must be
        left untouched (old sha), so promote sees it as stale and fails closed -- never a
        refreshed sha that would present old claims as valid for the new surface."""
        prod = Product(tmp_path, shape_id)
        names = _names("Out", 30)
        _full_build(prod, names, FakeLLM())
        raw = (prod.scout / "enriched_claims.json").read_bytes()
        prod.write_surface(_surface(prod.shape, names + ["AaaOutWidgetNEW"]))
        fake = FakeLLM()
        fake.fail_classes = {"AaaOutWidgetNEW"}
        prod.enrich(fake)
        assert (prod.scout / "enriched_claims.json").read_bytes() == raw
        assert prod.promote() is False

    def _two_changed_in_different_buckets(self, prod, names):
        units = E._plan_capability_units(_surface(prod.shape, names), 20)
        first = next(u for u in units if u["classes"])
        second = next(u for u in units if u["unit"] != first["unit"] and u["classes"])
        a, b = first["classes"][0]["name"], second["classes"][0]["name"]
        entries = _surface(prod.shape, names)
        for i, n in enumerate(names):
            if n in (a, b):
                entries[i] = _entry(prod.shape, n, extra_method=f"{n.lower()}Extra")
        return entries, a, b

    def test_partial_failure_among_changed_units_is_not_blessed(self, tmp_path, shape_id):
        """R1-5: two changed units in different buckets, the LLM fails for one.  The sha must
        NOT be refreshed, the output must be marked partial, promote must refuse it (unless
        explicitly allowed), and the next healthy run retries only the failed unit."""
        prod = Product(tmp_path, shape_id)
        names = _names("Par", 60)
        _full_build(prod, names, FakeLLM())
        old_sha = prod.enriched()["api_surface_sha"]
        entries, a, b = self._two_changed_in_different_buckets(prod, names)
        prod.write_surface(entries)
        fake = FakeLLM()
        fake.fail_classes = {b}
        assert prod.enrich(fake) is True
        data = prod.enriched()
        assert data["api_surface_sha"] == old_sha, "sha of a partially enriched surface must not be refreshed"
        assert data.get("enrichment_status") == "partial"
        assert data["incomplete_units"]
        assert prod.promote() is False
        assert prod.promote(allow_partial_enrichment=True) is True
        fake2 = FakeLLM()
        assert prod.enrich(fake2) is True
        assert [c[1] for c in fake2.calls if b in c[1]], "the failed unit must be retried"
        assert not [c for c in fake2.calls if a in c[1]], "the already-regenerated unit must not be"
        done = prod.enriched()
        assert "enrichment_status" not in done and "incomplete_units" not in done
        assert done["api_surface_sha"] != old_sha
        assert prod.promote() is True

    def test_changed_unit_yielding_nothing_acceptable_marks_partial(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        names = _names("Nil", 60)
        _full_build(prod, names, FakeLLM())
        old_sha = prod.enriched()["api_surface_sha"]
        entries, a, b = self._two_changed_in_different_buckets(prod, names)
        prod.write_surface(entries)

        class EmptyForB(FakeLLM):
            def __call__(self, sp, up, cache=None, cache_extra=None):
                out, model = super().__call__(sp, up, cache, cache_extra)
                if b in re.findall(r"^Class: (\w+)$", up, flags=re.M):
                    return [], model
                return out, model
        assert prod.enrich(EmptyForB()) is True
        data = prod.enriched()
        assert data.get("enrichment_status") == "partial"
        assert data["api_surface_sha"] == old_sha

    def test_force_full_reenriches_every_unit_without_duplicating_claims(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        names = _names("Full", 45)
        _full_build(prod, names, FakeLLM())
        before = prod.enriched()["claims"]
        fake = FakeLLM()
        assert prod.enrich(fake, force_full=True) is True
        assert sum(len(c[1]) for c in fake.calls) == len(names)
        after = prod.enriched()["claims"]
        assert sorted(c["claim_id"] for c in after) == sorted(c["claim_id"] for c in before)

    def test_member_doc_mode_only_new_class_is_enriched(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        names = _names("Mem", 12)
        _full_build(prod, names, FakeLLM(), mode="member-doc")
        first = prod.enriched()["claims"]
        assert first and all(c["enrich_unit"].startswith("class:") for c in first)
        fake = FakeLLM()
        prod.write_surface(_surface(prod.shape, names + ["AaaMemWidgetNEW"]))
        assert prod.enrich(fake, mode="member-doc") is True
        assert [c[1] for c in fake.calls] == [["AaaMemWidgetNEW"]]
        after = {c["claim_id"]: c for c in prod.enriched()["claims"]}
        for c in first:
            assert after[c["claim_id"]] == c

    def test_failed_regeneration_never_drops_the_units_existing_claims(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        names = _names("Fail", 12)
        _full_build(prod, names, FakeLLM(), mode="member-doc")
        before = prod.enriched()["claims"]
        entries = _surface(prod.shape, names)
        entries[3] = _entry(prod.shape, names[3], extra_method="fail003Extra")
        prod.write_surface(entries)
        fake = FakeLLM()
        fake.fail_classes = {names[3]}
        assert prod.enrich(fake, mode="member-doc") is True
        after = prod.enriched()["claims"]
        assert {c["claim_id"] for c in before} <= {c["claim_id"] for c in after}

    def test_legacy_unstamped_claims_are_adopted_then_converge(self, tmp_path, shape_id):
        """Pre-B13 enriched claims carry no unit stamp.  A first run keeps them all (never
        dropped), adopts those the regeneration re-derives, and the SECOND run is a no-op."""
        prod = Product(tmp_path, shape_id)
        names = _names("Leg", 25)
        _full_build(prod, names, FakeLLM())
        legacy = [{k: v for k, v in c.items() if k not in ("enrich_unit", "class_hash")}
                  for c in prod.enriched()["claims"]]
        data = prod.enriched()
        data["claims"] = legacy
        data.pop("enrich_units", None)
        (prod.scout / "enriched_claims.json").write_text(json.dumps(data), encoding="utf-8")
        assert prod.enrich(FakeLLM()) is True
        got = prod.enriched()["claims"]
        assert {c["claim_id"] for c in legacy} <= {c["claim_id"] for c in got}
        assert len(got) == len(legacy), "adoption must not duplicate re-derived claims"
        assert all("enrich_unit" in c for c in got)
        fake = FakeLLM()
        assert prod.enrich(fake) is True
        assert fake.calls == []


@pytest.mark.parametrize("shape_id", SHAPE_IDS)
class TestStablePartition:
    def test_adding_a_class_changes_membership_of_exactly_one_unit(self, shape_id):
        shape = SHAPES[shape_id]
        names = _names("Part", 90)
        before = E._plan_capability_units(_surface(shape, names), 20)
        after = E._plan_capability_units(_surface(shape, names + ["AaaPartWidgetNEW"]), 20,
                                         prior_count=E._bucket_count_for(90, 20))
        b = {u["unit"]: [E._class_qualified_key(c) for c in u["classes"]] for u in before}
        a = {u["unit"]: [E._class_qualified_key(c) for c in u["classes"]] for u in after}
        assert set(a) == set(b)
        differing = [u for u in a if a[u] != b[u]]
        assert len(differing) == 1
        only = differing[0]
        assert set(a[only]) - set(b[only]) == {E._class_qualified_key(_entry(shape, "AaaPartWidgetNEW"))}

    def test_partition_is_independent_of_input_order(self, shape_id):
        shape = SHAPES[shape_id]
        entries = _surface(shape, _names("Ord", 50))
        fwd = E._plan_capability_units(entries, 20)
        rev = E._plan_capability_units(list(reversed(entries)), 20)
        assert [(u["unit"], u["hash"]) for u in fwd] == [(u["unit"], u["hash"]) for u in rev]

    def test_every_class_is_in_exactly_one_unit(self, shape_id):
        shape = SHAPES[shape_id]
        entries = _surface(shape, _names("All", 77))
        units = E._plan_capability_units(entries, 20)
        keys = [E._class_qualified_key(c) for u in units for c in u["classes"]]
        assert sorted(keys) == sorted(E._class_qualified_key(c) for c in entries)

    def test_bucket_count_is_kept_until_the_mean_outgrows_the_batch(self, shape_id):
        assert E._bucket_count_for(46, 20, prior_count=4) == 4
        assert E._bucket_count_for(400, 20, prior_count=4) == 32

    def test_duplicate_simple_names_stay_distinct_via_qualified_key(self, shape_id):
        shape = SHAPES[shape_id]
        a = _entry(shape, "Value")
        b = dict(_entry(shape, "Value"), file=f"other/dir/Value{shape['ext']}")
        if shape["qualified"]:
            b["class_import"] = f"org.demo.other.Value"
        assert E._class_qualified_key(a) != E._class_qualified_key(b)


# ---------------------------------------------------------------------------
# no-change rerun => byte-identical outputs (minus timestamps)
# ---------------------------------------------------------------------------

_VOLATILE_MODEL_KEYS = ("promoted_at", "bundle_id", "bundle_generated_at")


@pytest.mark.parametrize("shape_id", SHAPE_IDS)
def test_no_change_second_run_is_byte_identical(tmp_path, shape_id):
    prod = Product(tmp_path, shape_id)
    names = _names("Idem", 30)
    _full_build(prod, names, FakeLLM(), mode="both")
    claims_1 = prod.merged_bytes()
    enriched_1 = prod.enriched()
    model_1 = yaml.safe_load((prod.merged / "model.yaml").read_text(encoding="utf-8"))

    fake = FakeLLM()
    assert prod.enrich(fake, mode="both") is True
    assert prod.promote() is True
    assert fake.calls == []
    assert prod.merged_bytes() == claims_1
    enriched_2 = prod.enriched()
    for volatile in ("generated_at", "run_stats"):
        enriched_1.pop(volatile, None)
        enriched_2.pop(volatile, None)
    assert enriched_2 == enriched_1
    model_2 = yaml.safe_load((prod.merged / "model.yaml").read_text(encoding="utf-8"))
    for k in _VOLATILE_MODEL_KEYS:
        model_1.pop(k, None)
        model_2.pop(k, None)
    assert model_2 == model_1


# ---------------------------------------------------------------------------
# (b) re-identified claim restamp + incident replay
# ---------------------------------------------------------------------------

def _page(evidence_claims, section_claims, body="## Body\n\nUntouched prose.\n"):
    return (
        "---\ntitle: T\nevidence:\n  model_sha: abc\n  model_version: '1.0'\n  claims:\n"
        + "".join(f"  - {c}\n" for c in evidence_claims)
        + "  apis: []\n  sections:\n  - heading: Body\n    line: 6\n    claims:\n"
        + "".join(f"    - {c}\n" for c in section_claims)
        + "    apis: []\n---\n" + body
    )


@pytest.mark.parametrize("fam,plat,old,new,keep", [
    ("ptxj", "java", "ERC-ptxj-java-11111111", "ERC-ptxj-java-22222222", "CLM-ptxj-aaaaaa"),
    ("ptxp", "python", "CLM-ptxp-bbbbbb", "ERC-ptxp-python-33333333", "ERC-ptxp-python-44444444"),
])
class TestReidentifiedRestamp:
    def _knowledge(self, tmp_path, fam, plat, old, new, keep, *, new_present=True):
        merged = tmp_path / "knowledge" / fam / plat / "merged"
        merged.mkdir(parents=True)
        claims = [{"claim_id": keep, "text": "k", "kind": "api"}]
        if new_present:
            claims.append({"claim_id": new, "text": "same text", "kind": "api"})
        (merged / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
        (merged / "knowledge_delta.json").write_text(
            json.dumps({"removed_claims": [], "reidentified_claims": {old: new}}), encoding="utf-8")
        return tmp_path / "knowledge"

    def test_citations_are_restamped_old_to_new_body_untouched(self, tmp_path, fam, plat, old, new, keep):
        kroot = self._knowledge(tmp_path, fam, plat, old, new, keep)
        page = tmp_path / "content" / "docs.aspose.org" / "en" / fam / plat / "p.md"
        page.parent.mkdir(parents=True)
        original = _page([old, keep], [old])
        page.write_text(original, encoding="utf-8")
        body_before = original.split("---\n", 2)[2]

        result = AE._pre_restamp(["--files", str(page), "--force"], knowledge_root=kroot, audit_gate_factory=_NOGATE)
        assert result["ids_restamped"] >= 2 and result["files_changed"] == 1
        text = page.read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---\n", 2)[1])
        assert fm["evidence"]["claims"] == sorted([new, keep])
        assert fm["evidence"]["sections"][0]["claims"] == [new]
        assert old not in text
        assert text.split("---\n", 2)[2] == body_before

    def test_second_pass_is_a_noop(self, tmp_path, fam, plat, old, new, keep):
        kroot = self._knowledge(tmp_path, fam, plat, old, new, keep)
        page = tmp_path / "content" / "docs.aspose.org" / "en" / fam / plat / "p.md"
        page.parent.mkdir(parents=True)
        page.write_text(_page([old, keep], [old]), encoding="utf-8")
        AE._pre_restamp(["--files", str(page)], knowledge_root=kroot, audit_gate_factory=_NOGATE)
        once = page.read_bytes()
        again = AE._pre_restamp(["--files", str(page)], knowledge_root=kroot, audit_gate_factory=_NOGATE)
        assert again["files_changed"] == 0 and page.read_bytes() == once

    def test_dry_run_writes_nothing(self, tmp_path, fam, plat, old, new, keep):
        kroot = self._knowledge(tmp_path, fam, plat, old, new, keep)
        page = tmp_path / "content" / "docs.aspose.org" / "en" / fam / plat / "p.md"
        page.parent.mkdir(parents=True)
        page.write_text(_page([old, keep], [old]), encoding="utf-8")
        before = page.read_bytes()
        AE._pre_restamp(["--files", str(page), "--force", "--dry-run"], knowledge_root=kroot, audit_gate_factory=_NOGATE)
        assert page.read_bytes() == before

    def test_mapping_to_a_nonexistent_new_id_is_ignored(self, tmp_path, fam, plat, old, new, keep):
        """A restamp must never create a fresh orphan."""
        kroot = self._knowledge(tmp_path, fam, plat, old, new, keep, new_present=False)
        assert AE.load_reidentified_claims(kroot, fam, plat) == {}

    def test_duplicate_after_mapping_is_collapsed(self, tmp_path, fam, plat, old, new, keep):
        kroot = self._knowledge(tmp_path, fam, plat, old, new, keep)
        page = tmp_path / "content" / "docs.aspose.org" / "en" / fam / plat / "p.md"
        page.parent.mkdir(parents=True)
        page.write_text(_page([old, new, keep], [old, new]), encoding="utf-8")
        AE._pre_restamp(["--files", str(page)], knowledge_root=kroot, audit_gate_factory=_NOGATE)
        fm = yaml.safe_load(page.read_text(encoding="utf-8").split("---\n", 2)[1])
        assert fm["evidence"]["claims"] == sorted([new, keep])
        assert fm["evidence"]["sections"][0]["claims"] == [new]


@pytest.mark.parametrize("fam,plat,old,new,keep", [
    ("ptxj", "java", "ERC-ptxj-java-11111111", "ERC-ptxj-java-22222222", "CLM-ptxj-aaaaaa"),
    ("ptxp", "python", "CLM-ptxp-bbbbbb", "ERC-ptxp-python-33333333", "ERC-ptxp-python-44444444"),
])
class TestRestampGates:
    """R1-7: the pre-pass honours the runner's gates and write-mode-only shape."""

    def _setup(self, tmp_path, fam, plat, old, new, keep, pages=("p.md",), site="docs.aspose.org"):
        merged = tmp_path / "knowledge" / fam / plat / "merged"
        merged.mkdir(parents=True)
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": keep, "text": "k", "kind": "api"}, {"claim_id": new, "text": "t", "kind": "api"}]),
            encoding="utf-8")
        (merged / "knowledge_delta.json").write_text(
            json.dumps({"reidentified_claims": {old: new}}), encoding="utf-8")
        out = []
        for name in pages:
            f = tmp_path / "content" / site / "en" / fam / plat / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(_page([old, keep], [old]), encoding="utf-8")
            out.append(f)
        return tmp_path / "knowledge", out

    def _cited_old(self, f, old):
        return old in f.read_text(encoding="utf-8")

    def test_draft_page_is_never_restamped(self, tmp_path, fam, plat, old, new, keep):
        kroot, (page,) = self._setup(tmp_path, fam, plat, old, new, keep)
        page.write_text(page.read_text(encoding="utf-8").replace("title: T", "title: T\ndraft: true", 1),
                        encoding="utf-8")
        r = AE._pre_restamp(["--files", str(page)], knowledge_root=kroot, audit_gate_factory=_NOGATE)
        assert r["ids_restamped"] == 0 and r["skipped_draft"] == 1 and self._cited_old(page, old)

    def test_audit_fail_page_is_skipped_passing_page_is_restamped(self, tmp_path, fam, plat, old, new, keep):
        kroot, (bad, good) = self._setup(tmp_path, fam, plat, old, new, keep, pages=("bad.md", "good.md"))
        gate = lambda f, p: (lambda fp: fp.name != "bad.md")  # noqa: E731
        r = AE._pre_restamp(["--files", str(bad), str(good)], knowledge_root=kroot, audit_gate_factory=gate)
        assert r["skipped_gate"] == 1 and r["files_changed"] == 1
        assert self._cited_old(bad, old) and not self._cited_old(good, old)

    @pytest.mark.parametrize("argv", [
        ["{fam}", "{plat}", "--detect-stale-claims", "--report-json", "out.json"],
        ["--report-json", "out.json"],
        ["{fam}", "--force"],
        ["--help"],
        [],
        ["--files"],
    ])
    def test_non_write_or_malformed_shapes_do_nothing(self, tmp_path, fam, plat, old, new, keep, argv):
        kroot, (page,) = self._setup(tmp_path, fam, plat, old, new, keep)
        before = page.read_bytes()
        calls = []
        argv = [a.format(fam=fam, plat=plat) for a in argv]
        AE._pre_restamp(argv, knowledge_root=kroot, discover_fn=lambda f, p: calls.append(1) or [page],
                        audit_gate_factory=_NOGATE)
        assert page.read_bytes() == before and calls == []

    def test_subdomain_filter_is_honoured(self, tmp_path, fam, plat, old, new, keep):
        kroot, (doc,) = self._setup(tmp_path, fam, plat, old, new, keep, site="docs.aspose.org")
        kroot, (ref,) = self._setup_extra(tmp_path, fam, plat, old, keep, "reference.aspose.org")
        r = AE._pre_restamp([fam, plat, "--subdomain", "docs.aspose.org"], knowledge_root=kroot,
                            audit_gate_factory=_NOGATE, discover_fn=lambda f, p: [doc, ref])
        assert r["files_changed"] == 1
        assert not self._cited_old(doc, old) and self._cited_old(ref, old)

    def _setup_extra(self, tmp_path, fam, plat, old, keep, site):
        f = tmp_path / "content" / site / "en" / fam / plat / "r.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(_page([old, keep], [old]), encoding="utf-8")
        return tmp_path / "knowledge", [f]

    def test_bulk_force_over_version_jump_is_refused_unless_confirmed(self, tmp_path, fam, plat, old, new, keep):
        kroot, (page,) = self._setup(tmp_path, fam, plat, old, new, keep)
        kw = dict(knowledge_root=kroot, audit_gate_factory=_NOGATE, discover_fn=lambda f, p: [page],
                  version_jump_refused=lambda f, p: True)
        assert AE._pre_restamp([fam, plat, "--force"], **kw)["files_changed"] == 0
        assert self._cited_old(page, old)
        # confirmed -> proceeds
        assert AE._pre_restamp([fam, plat, "--force", "--confirm-model-version-jump"], **kw)["files_changed"] == 1

    def test_non_force_run_is_not_subject_to_the_version_jump_gate(self, tmp_path, fam, plat, old, new, keep):
        kroot, (page,) = self._setup(tmp_path, fam, plat, old, new, keep)
        r = AE._pre_restamp([fam, plat], knowledge_root=kroot, audit_gate_factory=_NOGATE,
                            discover_fn=lambda f, p: [page], version_jump_refused=lambda f, p: True)
        assert r["files_changed"] == 1


@pytest.mark.parametrize("fam,plat", [("ptxj", "java"), ("ptxp", "python")])
def test_incident_replay_ids_changed_text_identical(tmp_path, fam, plat):
    """The 41-page / 2,390-deletion incident shape, end to end through the REAL delta writer:
    every claim id changes, every claim text is identical.  The delta must report zero
    removals, the semantic diff must therefore contain no FEATURE_REMOVED change (so
    body_refresh has nothing to delete), and the evidence citations must be restamped."""
    from commands.knowledge import semantic_diff as SD

    old_claims = [{"claim_id": f"ERC-{fam}-{plat}-{i:08x}", "text": f"Feature number {i} behaves so.",
                   "kind": "feature", "confidence": 0.9} for i in range(40)]
    new_claims = [dict(c, claim_id=f"ERC-{fam}-{plat}-{i + 0x1000:08x}") for i, c in enumerate(old_claims)]
    root = tmp_path / "knowledge" / fam / plat
    bak, merged = root / "merged.bak", root / "merged"
    for d, claims in ((bak, old_claims), (merged, new_claims)):
        d.mkdir(parents=True)
        (d / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
        (d / "api_surface.json").write_text("[]", encoding="utf-8")
    RK.configure(repo_root=tmp_path)
    try:
        RK._write_knowledge_delta(fam, plat, bak, merged, "new", "old")
    finally:
        RK.configure()
    delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
    assert delta["removed_claims"] == [] and delta["new_claims"] == []
    assert len(delta["reidentified_claims"]) == 40

    changes = SD._build_changes(fam, plat, delta)
    assert not [c for c in changes if c.get("change_type") == "FEATURE_REMOVED"]

    page = tmp_path / "content" / "docs.aspose.org" / "en" / fam / plat / "guide.md"
    page.parent.mkdir(parents=True)
    cited = [old_claims[0]["claim_id"], old_claims[5]["claim_id"]]
    page.write_text(_page(cited, cited[:1]), encoding="utf-8")
    AE._pre_restamp(["--files", str(page)], knowledge_root=tmp_path / "knowledge", audit_gate_factory=_NOGATE)
    fm = yaml.safe_load(page.read_text(encoding="utf-8").split("---\n", 2)[1])
    assert fm["evidence"]["claims"] == sorted([new_claims[0]["claim_id"], new_claims[5]["claim_id"]])


# ---------------------------------------------------------------------------
# (d) extractor hash
# ---------------------------------------------------------------------------

def _fake_repo(tmp_path: Path, newline: str, extra: str = "") -> Path:
    root = tmp_path
    ext = root / "scripts" / "pipeline" / "extraction"
    ext.mkdir(parents=True, exist_ok=True)
    (ext / "alpha.py").write_bytes(f"def a():{newline}    return 1{newline}{extra}".encode())
    (ext / "beta.py").write_bytes(f"X = 1{newline}Y = 2{newline}".encode())
    pr = root / "scripts" / "pipeline" / "commands" / "knowledge"
    pr.mkdir(parents=True, exist_ok=True)
    (pr / "promote.py").write_bytes(f"# promote{newline}pass{newline}".encode())
    return root


class TestExtractorHash:
    def test_crlf_and_lf_checkouts_hash_identically(self, tmp_path):
        lf = _fake_repo(tmp_path / "lf", "\n")
        crlf = _fake_repo(tmp_path / "crlf", "\r\n")
        try:
            RK.configure(repo_root=lf)
            h_lf = RK._compute_extractor_hash()
            RK.configure(repo_root=crlf)
            h_crlf = RK._compute_extractor_hash()
        finally:
            RK.configure()
        assert h_lf == h_crlf and len(h_lf) == 16

    def test_hash_still_reacts_to_real_content_change(self, tmp_path):
        a = _fake_repo(tmp_path / "a", "\n")
        b = _fake_repo(tmp_path / "b", "\n", extra="Z = 3\n")
        try:
            RK.configure(repo_root=a)
            ha = RK._compute_extractor_hash()
            RK.configure(repo_root=b)
            hb = RK._compute_extractor_hash()
        finally:
            RK.configure()
        assert ha != hb

    def test_scope_unchanged_unrelated_file_does_not_affect_hash(self, tmp_path):
        a = _fake_repo(tmp_path / "a", "\n")
        try:
            RK.configure(repo_root=a)
            h1 = RK._compute_extractor_hash()
            (a / "scripts" / "pipeline" / "lib").mkdir(parents=True)
            (a / "scripts" / "pipeline" / "lib" / "other.py").write_text("x=1", encoding="utf-8")
            h2 = RK._compute_extractor_hash()
        finally:
            RK.configure()
        assert h1 == h2

    @pytest.mark.parametrize("shape_id", SHAPE_IDS)
    def test_promote_preserves_an_existing_extractor_hash(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        prod.write_surface(_surface(prod.shape, _names("Hash", 3)))
        prod.write_scout()
        assert prod.promote() is True
        model = prod.merged / "model.yaml"
        assert "extractor_hash" not in yaml.safe_load(model.read_text(encoding="utf-8"))
        data = yaml.safe_load(model.read_text(encoding="utf-8"))
        data["extractor_hash"] = "deadbeefdeadbeef"
        model.write_text(yaml.safe_dump(data), encoding="utf-8")
        assert prod.promote() is True
        assert yaml.safe_load(model.read_text(encoding="utf-8"))["extractor_hash"] == "deadbeefdeadbeef"

    @pytest.mark.parametrize("shape_id", SHAPE_IDS)
    def test_promote_stamps_the_current_hash_inside_a_refresh(self, tmp_path, shape_id):
        prod = Product(tmp_path, shape_id)
        prod.write_surface(_surface(prod.shape, _names("Hash", 3)))
        prod.write_scout()
        assert prod.promote(extractor_hash="0123456789abcdef") is True
        model = yaml.safe_load((prod.merged / "model.yaml").read_text(encoding="utf-8"))
        assert model["extractor_hash"] == "0123456789abcdef"
        # and a later standalone promote keeps it
        assert prod.promote() is True
        model = yaml.safe_load((prod.merged / "model.yaml").read_text(encoding="utf-8"))
        assert model["extractor_hash"] == "0123456789abcdef"


@pytest.mark.parametrize("fam,plat", [("ptxj", "java"), ("ptxp", "python")])
def test_default_audit_gate_follows_the_runners_verify_tokens(tmp_path, fam, plat):
    """The pre-pass's default gate IS the runner's audit gate (extract + verify tokens, FAIL
    => skipped), resolved through the runner's own configure() seams."""
    import evidence.runner as R

    class _Finding:
        def __init__(self, level):
            self.level = level

    class _K:
        available = True
        version = "1.0"

    verdict = {"level": "FAIL"}
    R.configure(knowledge_fn=lambda f, p: _K(), extract_tokens_fn=lambda fp, platform: [],
                verify_tokens_fn=lambda tokens, k, fp: [_Finding(verdict["level"])])
    try:
        gate = AE._default_audit_gate(fam, plat)
        assert gate(tmp_path / "x.md") is False
        verdict["level"] = "WARN"
        assert gate(tmp_path / "x.md") is True
        R.configure(knowledge_fn=lambda f, p: type("U", (), {"available": False})())
        assert AE._default_audit_gate(fam, plat)(tmp_path / "x.md") is False
    finally:
        R.configure()
