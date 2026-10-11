"""MT074 B4 wiring: refresh_run.prepare_run builds the plan-time capability ledger and
post_refresh_verify Check 13 (capability_ledger_plan) gates it.

Two differently shaped products: a Java-style one (dotted packages, typed signatures) and a
Python-style one (file-path qualifiers). The ledger builder is a pure file-to-file CLI, so the
command runner executes the real capability_ledger.py; everything else is the suite's usual stub.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

import post_refresh_verify as prv
import refresh_run
from test_refresh_run import HEAD_SHA, MODEL_SHA, _write_empty_backlink_manifest

REAL_SCRIPT = Path(refresh_run.__file__).resolve().parent / "capability_ledger.py"


def _entry(name, ns=None, file=None, kind="class_declaration", methods=()):
    out = {"name": name, "kind": kind, "file": file or f"src/{name}.x", "visibility": "public",
           "methods": [{"name": m, "params": [], "return_type": ""} for m in methods],
           "properties": [], "enum_members": []}
    if ns:
        out["canonical_namespace"] = ns
    return out


SHAPES = {
    "java": {
        "family": "acme", "platform": "java",
        "old": [_entry("Doc", "org.acme.core", methods=["open"])],
        "new": [_entry("Doc", "org.acme.core", methods=["open", "save"]),
                _entry("RenderJob", "org.acme.render", methods=["run"])],
        "delta": {"new_apis_qualified": ["org.acme.render::RenderJob"],
                  "new_apis": ["RenderJob"],
                  "modified_apis_qualified": ["org.acme.core::Doc"]},
        "new_symbol": "org.acme.render::RenderJob",
    },
    "python": {
        "family": "zeta", "platform": "python",
        "old": [_entry("Sheet", file="zeta/sheet.py", kind="class_definition")],
        "new": [_entry("Sheet", file="zeta/sheet.py", kind="class_definition"),
                _entry("CsvReader", file="zeta/io/csv_reader.py", kind="class_definition",
                       methods=["read"])],
        "delta": {"new_apis_qualified": ["zeta/io/csv_reader.py::CsvReader"],
                  "new_apis": ["CsvReader"]},
        "new_symbol": "zeta/io/csv_reader.py::CsvReader",
    },
}


class Env:
    """A product's knowledge tree, one content page, and a pre-refresh api_surface at base."""

    def __init__(self, root: Path, shape: dict, *, delta=None):
        self.root = root
        self.family, self.platform = shape["family"], shape["platform"]
        self.shape = shape
        self.merged = root / "knowledge" / self.family / self.platform / "merged"
        self.merged.mkdir(parents=True, exist_ok=True)
        (self.merged / "model.yaml").write_text(
            yaml.safe_dump({"family": self.family, "platform": self.platform,
                            "repo_sha": MODEL_SHA, "stale_since": None}), encoding="utf-8")
        self.old_text = json.dumps(shape["old"])
        (self.merged / "api_surface.json").write_text(self.old_text, encoding="utf-8")
        self.delta = shape["delta"] if delta is None else delta
        (self.merged / "knowledge_delta.json").write_text(json.dumps(self.delta), encoding="utf-8")
        self.page = root / f"content/docs.aspose.org/en/{self.family}/{self.platform}/page.md"
        self.page.parent.mkdir(parents=True, exist_ok=True)
        self.page.write_text("page\n", encoding="utf-8")

    def runner(self):
        env = self

        def run(args, **_):
            strs = [str(a) for a in args]
            if args[:3] == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(args, 0, HEAD_SHA + "\n", "")
            if args[:2] == ["git", "show"]:
                return subprocess.CompletedProcess(args, 0, env.old_text, "")
            if any("refresh_knowledge.py" in a for a in strs):
                # the real knowledge refresh overwrites the working-tree bundle
                (env.merged / "api_surface.json").write_text(
                    json.dumps(env.shape["new"]), encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, "", "")
            if any("capability_ledger.py" in a for a in strs):
                return subprocess.run(
                    [str(REAL_SCRIPT) if "capability_ledger.py" in a else a for a in strs],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            _write_empty_backlink_manifest(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        return run

    def configure(self):
        refresh_run.configure(
            repo_root=self.root, command_runner=self.runner(),
            source_sha_resolver=lambda _f, _p: MODEL_SHA,
            now=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc))

    def start(self, run_id, *, mode="upstream", released=None, scope_manifest=None):
        self.configure()
        manifest = refresh_run.create_run(
            self.family, self.platform, mode=mode, run_id=run_id, session_id="s1",
            scope_manifest=scope_manifest, released_api_surface=released)
        planning = (self.root / "reports/refresh_runs" / self.family / self.platform
                    / run_id / "planning" / self.family / self.platform)
        planning.mkdir(parents=True)
        (planning / "page_impact.json").write_text(json.dumps({"pages": [
            {"path": self.page.relative_to(self.root).as_posix(), "pia_score": "HIGH_IMPACT"}]}),
            encoding="utf-8")
        return manifest

    def run_root(self, run_id):
        return self.root / "reports/refresh_runs" / self.family / self.platform / run_id


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    for var in ("AGENT_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "_no_clone_cache"))
    prv.configure(repo_root=tmp_path, reports_root=tmp_path / "refresh_state")
    yield
    refresh_run.configure()
    prv.configure()


def _ledger(env: Env, run_id: str) -> dict:
    return json.loads((env.run_root(run_id) / "capability_ledger.json").read_text(encoding="utf-8"))


def _units_by_symbol(ledger: dict) -> dict:
    return {s: u for u in ledger["units"] for s in u["symbols"]}


# ---------------------------------------------------------------------------
# prepare_run wiring
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_upstream_run_builds_ledger_with_proxy_released_surface(tmp_path, shape):
    env = Env(tmp_path, SHAPES[shape])
    prepared = refresh_run.prepare_run(env.start("RUN-LEDGER"))
    record = prepared["capability_ledger"]
    ledger_path = env.run_root("RUN-LEDGER") / "capability_ledger.json"
    assert record["release_surface"] == "proxy_pre_refresh_bundle"
    assert record["path"].endswith("RUN-LEDGER/capability_ledger.json")
    assert record["initial_sha256"] == (
        "sha256:" + hashlib.sha256(ledger_path.read_bytes()).hexdigest())
    assert record["plan_fingerprint"] == refresh_run.capability_plan_fingerprint(
        json.loads(ledger_path.read_text(encoding="utf-8")))
    assert "sha256" not in record
    # The proxy is the PRE-refresh bundle even though the (stubbed) refresh overwrote it.
    proxy = env.run_root("RUN-LEDGER") / "released_surface_proxy.json"
    assert json.loads(proxy.read_text(encoding="utf-8")) == SHAPES[shape]["old"]
    assert json.loads((env.merged / "api_surface.json").read_text(encoding="utf-8")) == SHAPES[shape]["new"]
    ledger = _ledger(env, "RUN-LEDGER")
    unit = _units_by_symbol(ledger)[SHAPES[shape]["new_symbol"]]
    assert unit["availability"] == "unreleased"  # absent from the released (proxy) surface
    errors, _warnings = _validate(ledger)
    assert errors == []
    assert prepared["state"] == "PLANNED"


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_explicit_released_surface_is_pinned_and_used(tmp_path, shape):
    env = Env(tmp_path, SHAPES[shape])
    explicit = tmp_path / "published_surface.json"
    # The published release ALREADY contains the new symbol.
    explicit.write_text(json.dumps(SHAPES[shape]["new"]), encoding="utf-8")
    manifest = env.start("RUN-EXPLICIT", released=str(explicit))
    assert manifest["released_api_surface"]["path"] == "published_surface.json"
    assert manifest["released_api_surface"]["sha256"] == (
        "sha256:" + hashlib.sha256(explicit.read_bytes()).hexdigest())
    prepared = refresh_run.prepare_run(manifest)
    assert prepared["capability_ledger"]["release_surface"] == "explicit"
    assert not (env.run_root("RUN-EXPLICIT") / "released_surface_proxy.json").exists()
    unit = _units_by_symbol(_ledger(env, "RUN-EXPLICIT"))[SHAPES[shape]["new_symbol"]]
    assert unit["availability"] == "released"


def test_explicit_released_surface_changed_after_start_blocks_prepare(tmp_path):
    env = Env(tmp_path, SHAPES["java"])
    explicit = tmp_path / "published_surface.json"
    explicit.write_text("[]", encoding="utf-8")
    manifest = env.start("RUN-EXPLICIT-DRIFT", released=str(explicit))
    explicit.write_text('[{"name": "Tampered"}]', encoding="utf-8")
    with pytest.raises(refresh_run.RefreshRunError, match="changed since it was pinned"):
        refresh_run.prepare_run(manifest)


def test_missing_explicit_released_surface_is_rejected_at_start(tmp_path):
    env = Env(tmp_path, SHAPES["python"])
    env.configure()
    with pytest.raises(refresh_run.RefreshRunError, match="Released api surface not found"):
        refresh_run.create_run("zeta", "python", mode="upstream", run_id="RUN-NOFILE",
                               session_id="s1", released_api_surface="nope.json")


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_ledger_for_noop_delta(tmp_path, shape):
    env = Env(tmp_path, SHAPES[shape], delta={})
    prepared = refresh_run.prepare_run(env.start("RUN-NOOP"))
    assert "capability_ledger" not in prepared
    assert not (env.run_root("RUN-NOOP") / "capability_ledger.json").exists()


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_ledger_for_remediation(tmp_path, shape):
    env = Env(tmp_path, SHAPES[shape])
    scope = tmp_path / "scope.json"
    rel = env.page.relative_to(tmp_path).as_posix()
    scope.write_text(json.dumps({"paths": [rel]}), encoding="utf-8")
    manifest = env.start("RUN-REMED", mode="remediation", scope_manifest="scope.json")
    prepared = refresh_run.prepare_run(manifest)
    assert "capability_ledger" not in prepared
    assert not (env.run_root("RUN-REMED") / "capability_ledger.json").exists()
    assert not (env.run_root("RUN-REMED") / "released_surface_proxy.json").exists()


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_rebuild_on_resume_is_byte_identical_and_proxy_survives(tmp_path, shape):
    env = Env(tmp_path, SHAPES[shape])
    manifest = refresh_run.prepare_run(env.start("RUN-RESUME"))
    root = env.run_root("RUN-RESUME")
    ledger = root / "capability_ledger.json"
    proxy = root / "released_surface_proxy.json"
    before = (ledger.read_bytes(), proxy.read_bytes(), ledger.stat().st_mtime_ns,
              dict(manifest["capability_ledger"]))
    # A resumed prepare_run repeats exactly these two steps, now against a
    # working tree whose bundle was already overwritten by the first attempt.
    refresh_run._capture_released_surface_proxy(manifest, root)
    refresh_run._build_capability_ledger(
        manifest, root, env.merged / "knowledge_delta.json", MODEL_SHA)
    assert (ledger.read_bytes(), proxy.read_bytes(), ledger.stat().st_mtime_ns,
            manifest["capability_ledger"]) == before
    assert not (root / "capability_ledger.json.tmp").exists()


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_disposition_edit_survives_a_rebuild_with_unchanged_plan(tmp_path, shape):
    env, manifest, ledger_path = _prepared(tmp_path, shape, "RUN-EDITED")
    recorded = dict(manifest["capability_ledger"])
    downgrade = _is_downgrade(ledger_path)
    assert _set_docs_disposition(ledger_path, env) == 0
    edited = ledger_path.read_bytes()
    refresh_run._build_capability_ledger(
        manifest, env.run_root("RUN-EDITED"), env.merged / "knowledge_delta.json", MODEL_SHA)
    assert ledger_path.read_bytes() == edited
    assert manifest["capability_ledger"] == recorded
    cell = _docs_cell(ledger_path)
    assert cell["action"] == "update"
    if downgrade:  # the override object persists across the rebuild
        assert cell["override"]["token_id"] == OVERRIDE_TOKEN
    else:
        assert "override" not in cell


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_downgrade_without_override_is_refused_and_leaves_ledger_unchanged(tmp_path, shape, capsys):
    import capability_ledger as cli
    env, manifest, ledger_path = _prepared(tmp_path, shape, "RUN-NOOVR")
    before = ledger_path.read_bytes()
    data = json.loads(before.decode("utf-8"))
    # docs -> none is below the computed action for any shape
    code = cli.main(["set-disposition", "--ledger", str(ledger_path),
                     "--unit", data["units"][0]["id"], "--surface", "docs",
                     "--action", "none", "--rationale", "skip it"])
    assert code != 0
    assert "requires --override-token and --override-reason" in capsys.readouterr().out
    assert ledger_path.read_bytes() == before
    failures, _w, note = prv.check_capability_ledger_plan(manifest)
    assert failures == [] and note.startswith("PASS")


def test_plan_tampered_ledger_is_never_clobbered_by_a_rebuild(tmp_path):
    env, manifest, ledger_path = _prepared(tmp_path, "java", "RUN-TAMPERED")
    recorded = dict(manifest["capability_ledger"])
    _mutate(ledger_path, lambda d: d["units"].pop(0))
    tampered = ledger_path.read_bytes()
    refresh_run._build_capability_ledger(
        manifest, env.run_root("RUN-TAMPERED"), env.merged / "knowledge_delta.json", MODEL_SHA)
    assert ledger_path.read_bytes() == tampered
    assert manifest["capability_ledger"] == recorded


def test_cli_start_accepts_released_api_surface(tmp_path, capsys):
    env = Env(tmp_path, SHAPES["python"])
    env.configure()
    explicit = tmp_path / "pub.json"
    explicit.write_text("[]", encoding="utf-8")
    code = refresh_run.main(["start", "zeta", "python", "--mode", "upstream", "--run-id", "RUN-CLI",
                             "--session-id", "s1", "--released-api-surface", str(explicit)])
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["released_api_surface"]["path"] == "pub.json"


# ---------------------------------------------------------------------------
# post_refresh_verify Check 13
# ---------------------------------------------------------------------------

def _validate(ledger):
    import capability_delta as cd
    return cd.validate_ledger_ex(ledger, stage="plan")


def _prepared(tmp_path, shape, run_id="RUN-V"):
    env = Env(tmp_path, SHAPES[shape])
    manifest = refresh_run.prepare_run(env.start(run_id))
    return env, manifest, env.run_root(run_id) / "capability_ledger.json"


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_check13_passes_and_lists_plan_warnings(tmp_path, shape):
    env, manifest, ledger_path = _prepared(tmp_path, shape)
    failures, warnings, note = prv.check_capability_ledger_plan(manifest)
    assert failures == []
    assert note.startswith("PASS") and "proxy_pre_refresh_bundle" in note
    # plan stage: unresolved targets are warnings, not errors
    assert warnings == _validate(json.loads(ledger_path.read_text(encoding="utf-8")))[1]


def _mutate(ledger_path: Path, fn) -> None:
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    fn(data)
    ledger_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


OVERRIDE_TOKEN = "OVR-test-0001"


def _docs_cell(ledger_path: Path) -> dict:
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    return data["units"][0]["dispositions"]["docs"]


def _set_docs_disposition(ledger_path: Path, env: Env, *, override: bool = True) -> int:
    """docs -> update. Going below the cell computed_action (create) needs an
    override token + reason; they are only recorded when the edit is a downgrade."""
    import capability_ledger as cli
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    argv = ["set-disposition", "--ledger", str(ledger_path),
            "--unit", data["units"][0]["id"], "--surface", "docs",
            "--action", "update", "--rationale", "edited by the content step",
            "--target", env.page.relative_to(env.root).as_posix()]
    if override:
        argv += ["--override-token", OVERRIDE_TOKEN,
                 "--override-reason", "update an existing page instead of a new one"]
    return cli.main(argv)


def _is_downgrade(ledger_path: Path) -> bool:
    import capability_delta as cd
    cell = _docs_cell(ledger_path)
    return cd.ACTION_RANK["update"] < cd.ACTION_RANK.get(cell.get("computed_action", cell["action"]), 0)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_check13_passes_after_set_disposition_edit(tmp_path, shape):
    """Disposition edits change the file's bytes but not its plan identity."""
    env, manifest, ledger_path = _prepared(tmp_path, shape)
    before = ledger_path.read_bytes()
    downgrade = _is_downgrade(ledger_path)
    assert _set_docs_disposition(ledger_path, env) == 0
    assert ledger_path.read_bytes() != before
    if downgrade:
        assert _docs_cell(ledger_path)["override"]["token_id"] == OVERRIDE_TOKEN
    failures, _w, note = prv.check_capability_ledger_plan(manifest)
    assert failures == [] and note.startswith("PASS")


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_check13_fails_when_a_unit_is_removed(tmp_path, shape):
    env, manifest, ledger_path = _prepared(tmp_path, shape)
    _mutate(ledger_path, lambda d: d["units"].pop(0))
    failures, _w, _n = prv.check_capability_ledger_plan(manifest)
    assert len(failures) == 1 and "plan identity changed" in failures[0]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_check13_fails_when_a_unit_is_added(tmp_path, shape):
    import capability_delta as cd
    env, manifest, ledger_path = _prepared(tmp_path, shape)

    def add(d):
        extra = json.loads(json.dumps(d["units"][0]))
        extra["symbols"] = ["x::Added"]
        extra["formats"] = []
        extra["id"] = cd.unit_id(["x::Added"], [])
        d["units"].append(extra)
    _mutate(ledger_path, add)
    failures, _w, _n = prv.check_capability_ledger_plan(manifest)
    assert len(failures) == 1 and "plan identity changed" in failures[0]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_check13_fails_when_a_unit_is_regrouped(tmp_path, shape):
    """A regrouped unit with a self-consistent id is a VALID ledger, yet a
    different plan: only the fingerprint catches it."""
    import capability_delta as cd
    env, manifest, ledger_path = _prepared(tmp_path, shape)

    def regroup(d):
        unit = d["units"][0]
        unit["symbols"] = sorted(unit["symbols"] + ["x::Merged"])
        unit["id"] = cd.unit_id(unit["symbols"], unit.get("formats") or [])
    _mutate(ledger_path, regroup)
    assert _validate(json.loads(ledger_path.read_text(encoding="utf-8")))[0] == []
    failures, _w, _n = prv.check_capability_ledger_plan(manifest)
    assert len(failures) == 1 and "plan identity changed" in failures[0]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_check13_fails_on_invalid_ledger_even_with_matching_fingerprint(tmp_path, shape):
    env, manifest, ledger_path = _prepared(tmp_path, shape)
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    data["schema_version"] = 999
    data["units"][0]["id"] = "u-tampered"
    ledger_path.write_text(json.dumps(data), encoding="utf-8")
    manifest["capability_ledger"]["plan_fingerprint"] = (
        refresh_run.capability_plan_fingerprint(data))
    failures, _w, _n = prv.check_capability_ledger_plan(manifest)
    assert len(failures) == 1
    assert "invalid at plan stage" in failures[0] and "schema_version" in failures[0]


def test_check13_fails_when_ledger_file_missing(tmp_path):
    env, manifest, ledger_path = _prepared(tmp_path, "java")
    ledger_path.unlink()
    failures, _w, _n = prv.check_capability_ledger_plan(manifest)
    assert len(failures) == 1 and "ledger file missing" in failures[0]


def test_check13_fails_for_marked_real_delta_without_recorded_ledger(tmp_path):
    env, manifest, _ = _prepared(tmp_path, "python")
    assert manifest["capability_ledger_required"] is True  # written by create_run
    manifest.pop("capability_ledger")
    failures, _w, _n = prv.check_capability_ledger_plan(manifest)
    assert len(failures) == 1 and "no capability_ledger is recorded" in failures[0]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_marker_written_for_new_upstream_and_combined_runs_only(tmp_path, shape):
    env = Env(tmp_path, SHAPES[shape])
    env.configure()
    for mode in ("upstream", "combined"):
        m = refresh_run.create_run(env.family, env.platform, mode=mode,
                                   run_id=f"RUN-MARK-{mode}", session_id="s1")
        assert m["capability_ledger_required"] is True
        refresh_run.abandon_run(env.family, env.platform, m["run_id"],
                                reason="test", session_id="s1")
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps({"paths": [env.page.relative_to(tmp_path).as_posix()]}),
                     encoding="utf-8")
    m = refresh_run.create_run(env.family, env.platform, mode="remediation",
                               run_id="RUN-MARK-REM", session_id="s1",
                               scope_manifest="scope.json")
    assert "capability_ledger_required" not in m


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_check13_is_na_for_legacy_manifest_without_marker(tmp_path, shape):
    """R3-2: a manifest created before the ledger existed has no marker and no
    record; it must verify (NA), not fail with no way to remediate."""
    env, manifest, _ = _prepared(tmp_path, shape)
    manifest.pop("capability_ledger")
    manifest.pop("capability_ledger_required")
    manifest["blog_announcement_required"] = True
    failures, warnings, note = prv.check_capability_ledger_plan(manifest)
    assert (failures, warnings) == ([], [])
    assert note.startswith("NA") and "predates capability ledger" in note


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_legacy_manifest_still_prepares_resumes_and_verifies(tmp_path, shape):
    """R3-2: a run created BEFORE the marker existed (no capability_ledger_required)
    resumes through prepare_run and verifies: Check 13 never blocks it."""
    env = Env(tmp_path, SHAPES[shape])
    manifest = env.start("RUN-LEGACY")
    manifest.pop("capability_ledger_required")
    refresh_run._save_manifest(manifest)
    legacy = refresh_run._load_manifest(env.family, env.platform, "RUN-LEGACY")
    assert "capability_ledger_required" not in legacy
    prepared = refresh_run.prepare_run(legacy)
    assert prepared["state"] == "PLANNED"
    assert "capability_ledger_required" not in prepared
    failures, _w, note = prv.check_capability_ledger_plan(prepared)
    assert failures == [] and note.startswith("PASS")  # a ledger was built anyway
    prepared.pop("capability_ledger")
    assert prv.check_capability_ledger_plan(prepared)[2].startswith("NA")


def test_check13_not_applicable_cases(tmp_path):
    assert prv.check_capability_ledger_plan(None)[2].startswith("NA")
    f, w, note = prv.check_capability_ledger_plan({"mode": "remediation"})
    assert (f, w) == ([], []) and note.startswith("NA") and "remediation" in note
    f, w, note = prv.check_capability_ledger_plan(
        {"mode": "upstream", "capability_ledger_required": True,
         "blog_announcement_required": False})
    assert (f, w) == ([], []) and note.startswith("NA") and "no-op" in note


def test_verify_unbound_reports_check13_not_applicable(tmp_path, capsys):
    merged = tmp_path / "knowledge" / "acme" / "java" / "merged"
    merged.mkdir(parents=True)
    (merged / "model.yaml").write_text("stale_since: null\n", encoding="utf-8")
    (merged / "claims.json").write_text("[]", encoding="utf-8")
    (merged / "api_surface.json").write_text("[]", encoding="utf-8")
    prv.verify("acme", "java", base_ref="HEAD", unknowns_out=[])
    assert "Check 13: NA" in capsys.readouterr().out
