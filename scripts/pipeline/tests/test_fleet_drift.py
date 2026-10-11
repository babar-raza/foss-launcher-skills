"""B10 + B12 (MT074): commands/diagnostics/fleet_drift.py -- clone-free fleet drift classifier.

Everything is offline: recorded compare-API fixtures through FixtureRunner, a recording fake for
`gh issue ...`, injectable registry fetch. Synthetic families on real language platforms
(java, python, typescript, go, rust, cpp, net) plus one platform unknown to the config.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import content_propagation_state as cps
import fleet_drift as fd
import language_adapters as la

H = {n: (c * 40) for n, c in zip("abcdefghi", "abcdef0123")}  # distinct 40-char shas
K = "9" * 40  # an old knowledge sha

NOW = "2026-10-07T00:00:00Z"


# ── fixture world ────────────────────────────────────────────────────────────

def page(files, *, status="ahead", ahead_by=3):
    return {"status": status, "ahead_by": ahead_by, "files": [{"filename": f} for f in files]}


def write_fixture(fx_dir: Path, owner, repo, *, head, pages=None, error=None, ls_error=None, by_base=None):
    """by_base: {base_sha: {"pages": [...]} | {"error": "..."}} -- answers for a specific compare base."""
    body = {"head": head, "ls_remote_error": ls_error}
    if error is not None:
        body["compare"] = {"error": error}
    elif pages is not None:
        body["compare"] = {"pages": pages}
    if by_base:
        body.setdefault("compare", {})["by_base"] = by_base
    (fx_dir / f"{owner}__{repo}.json").write_text(json.dumps(body), encoding="utf-8")


def product(family, platform, repo, *, active=True):
    return {"family": family, "platform": platform, "repo_name": repo,
            "repo_url": f"https://github.com/org-{family}/{repo}",
            "clone_url": f"https://github.com/org-{family}/{repo}.git", "active": active}


def write_model(root: Path, family, platform, sha):
    d = root / "knowledge" / family / platform / "merged"
    d.mkdir(parents=True, exist_ok=True)
    (d / "model.yaml").write_text(f"name: x\nrepo_sha: '{sha}'\nother: 1\n" if sha else "name: x\n", encoding="utf-8")


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    fx = tmp_path / "fixtures"
    fx.mkdir()
    products = [
        product("famA", "java", "Lib.Alpha-for-Java"),            # dots in the repo name
        product("famB", "python", "Lib.Beta-for-Python"),
        product("famC", "typescript", "Lib.Gamma-for-TypeScript"),
        product("famD", "go", "Lib.Delta-for-Go"),
        product("famE", "net", "Lib.Epsilon-for-.NET"),           # no knowledge
        product("famF", "python", "Lib.Zeta-for-Python"),
        product("famG", "rust", "Lib.Eta-for-Rust"),
        product("famH", "zig", "Lib.Theta-for-Zig"),              # platform not in the config
        product("famI", "cpp", "Lib.Iota-for-Cpp"),
        product("famZ", "java", "Lib.Inactive-for-Java", active=False),
    ]
    (root / "data" / "products.json").write_text(json.dumps(products), encoding="utf-8")
    # knowledge shas
    for fam, plat in (("famA", "java"), ("famB", "python"), ("famC", "typescript"), ("famD", "go"),
                      ("famG", "rust"), ("famH", "zig"), ("famI", "cpp")):
        write_model(root, fam, plat, K)
    write_model(root, "famF", "python", H["f"])
    # famF: knowledge == head -> NO_CHANGE; baselines store DISAGREES for famA only
    baselines = {"famA/java": "8" * 40, "famB/python": K, "famC/typescript": K, "famD/go": K,
                 "famF/python": H["f"], "famG/rust": K, "famH/zig": K, "famI/cpp": K}
    (root / "data" / "upstream_baselines.json").write_text(json.dumps(baselines), encoding="utf-8")
    registry = {
        "famA": {"java": {"registry_type": "maven", "candidate": {"group_id": "g", "artifact_id": "a", "version": "1.0", "repo_sha": H["a"]},
                          "verification": {"published": True}}},
        "famB": {"python": {"registry_type": "pypi", "candidate": {"name": "pkg-b", "version": "2.0", "repo_sha": "7" * 40},
                            "verification": {"published": True}}},
        "famG": {"rust": {"registry_type": "cargo", "candidate": {"name": "crate-g", "version": "0.3", "repo_sha": "6" * 40},
                          "verification": {"published": True}}},
        "famI": {"cpp": {"registry_type": "weird-registry", "candidate": {}, "verification": {"published": True}}},
    }
    (root / "data" / "package_registry.json").write_text(json.dumps(registry), encoding="utf-8")

    write_fixture(fx, "org-famA", "Lib.Alpha-for-Java", head=H["a"],
                  pages=[page(["src/main/java/x/Api.java", "README.md", "src/test/java/x/ApiTest.java"])])
    write_fixture(fx, "org-famB", "Lib.Beta-for-Python", head=H["b"], pages=[page(["README.md", "docs/guide.md", "CHANGELOG.md"])])
    big = [page([f"src/internal/f{i}.ts" for i in range(100 * n, 100 * n + 100)]) for n in range(3)]
    write_fixture(fx, "org-famC", "Lib.Gamma-for-TypeScript", head=H["c"], pages=big)
    write_fixture(fx, "org-famD", "Lib.Delta-for-Go", head=H["d"],
                  error="gh: No common ancestor between 999 and ddd. (HTTP 404)")
    write_fixture(fx, "org-famE", "Lib.Epsilon-for-.NET", head=H["e"], pages=[page(["src/A.cs"])])
    write_fixture(fx, "org-famF", "Lib.Zeta-for-Python", head=H["f"])
    write_fixture(fx, "org-famG", "Lib.Eta-for-Rust", head=H["g"], pages=[page(["src/internal/mod.rs"])])
    write_fixture(fx, "org-famH", "Lib.Theta-for-Zig", head=H["h"], pages=[page(["src/a.zig", "src/b.zig"])])
    write_fixture(fx, "org-famI", "Lib.Iota-for-Cpp", head=H["i"],
                  error="gh: API rate limit exceeded for user ID 1. (HTTP 403)")
    fd.configure(repo_root=root)
    yield {"root": root, "fx": fx, "out": tmp_path / "out", "state": root / "data" / "content_propagation_state.json"}
    fd.configure(repo_root=None)


def run(world, *extra, now=NOW, runner=None, fetch=None, state_file=True):
    """Offline by default. `--update-state` offline needs an explicit --state-file (added here unless
    state_file=False), exactly as a real operator would have to."""
    args = ["--workers", "1", *extra]
    if runner is None and "--offline" not in extra:
        args += ["--offline", str(world["fx"])]
    if state_file and "--update-state" in extra and "--offline" in args and "--state-file" not in args:
        args += ["--state-file", str(world["state"])]
    import io
    buf = io.StringIO()
    rc = fd.main(args, runner=runner, fetch=fetch, now=now, out=buf)
    return rc, buf.getvalue()


def ledger(world, **kw):
    p = world["out"] / "ledger.json"
    rc, _ = run(world, "--json-out", str(p), **kw)
    assert rc == 0
    return json.loads(p.read_text(encoding="utf-8"))


# ── unit pieces ──────────────────────────────────────────────────────────────

class TestParsing:
    @pytest.mark.parametrize("url,expected", [
        ("https://github.com/org/Lib.Alpha-for-Java", ("org", "Lib.Alpha-for-Java")),
        ("https://github.com/org/Lib.Alpha-for-Java.git", ("org", "Lib.Alpha-for-Java")),
        ("https://github.com/org/Lib-for-.NET/", ("org", "Lib-for-.NET")),
        ("https://github.com/org/a.b.c", ("org", "a.b.c")),
        ("https://example.com/nope", (None, None)),
        (None, (None, None)),
    ])
    def test_owner_repo_keeps_dots(self, url, expected):
        assert fd.parse_owner_repo(url) == expected

    @pytest.mark.parametrize("text,rc,kind", [
        ("gh: API rate limit exceeded (HTTP 403)", 1, "rate_limited"),
        ("gh: Bad credentials (HTTP 401)", 1, "auth_error"),
        ("To get started with GitHub CLI, please run:  gh auth login", 4, "auth_error"),
        ("gh: No common ancestor between a and b. (HTTP 404)", 1, "no_common_ancestor"),
        ("gh: Not Found (HTTP 404)", 1, "not_found"),
        ("remote: Repository not found.", 128, "not_found"),
        ("fatal: could not read Username for https://x: terminal prompts disabled", 128, "auth_error"),
        ("timeout after 60s: git", 124, "timeout"),
        ("cannot run gh: [Errno 2]", 127, "tool_missing"),
        ("fatal: unable to access 'https://x': Could not resolve host", 128, "network_error"),
        ("something odd", 1, "gh_error"),
    ])
    def test_classify_error(self, text, rc, kind):
        assert fd.classify_error(text, rc) == kind


class TestFetchCompare:
    def runner_for(self, pages, calls):
        def runner(cmd, **kw):
            calls.append(cmd[2])
            n = int(re.search(r"&page=(\d+)", cmd[2]).group(1))
            body = pages[n - 1] if n <= len(pages) else page([])
            return subprocess.CompletedProcess(cmd, 0, json.dumps(body), "")
        return runner

    def test_single_page_stops_early(self):
        calls = []
        r = fd.fetch_compare("o", "r.x", "b", "h", runner=self.runner_for([page(["a", "b"])], calls))
        assert r["files"] == ["a", "b"] and r["truncated"] is False and len(calls) == 1
        assert calls[0] == "repos/o/r.x/compare/b...h?per_page=100&page=1"

    def test_paginates_and_flags_truncation_at_300(self):
        calls = []
        pages = [page([f"f{i}" for i in range(n * 100, n * 100 + 100)]) for n in range(3)]
        r = fd.fetch_compare("o", "r", "b", "h", runner=self.runner_for(pages, calls))
        assert r["files_seen"] == 300 and r["truncated"] is True and len(calls) == 4  # page 4 comes back empty

    def test_299_files_is_not_truncated(self):
        pages = [page([f"f{i}" for i in range(100)]), page([f"g{i}" for i in range(100)]), page([f"h{i}" for i in range(99)])]
        r = fd.fetch_compare("o", "r", "b", "h", runner=self.runner_for(pages, []))
        assert r["files_seen"] == 299 and r["truncated"] is False

    def test_error_midway_is_reported_not_raised(self):
        def runner(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, "", "gh: API rate limit exceeded")
        r = fd.fetch_compare("o", "r", "b", "h", runner=runner)
        assert r["error"]["kind"] == "rate_limited"


class TestClassifyTier:
    cfg = None

    @pytest.fixture(autouse=True)
    def _cfg(self):
        self.cfg = la.load_language_config()

    def cmp(self, files, status="ahead", truncated=False):
        return {"files": files, "files_seen": len(files), "truncated": truncated, "status": status, "ahead_by": 1}

    def test_matrix_across_languages(self):
        cases = [
            ("java", ["src/main/java/a/B.java"], "API_TOUCHED"),
            ("java", ["src/main/java/a/internal/B.java"], "SOURCE"),
            ("java", ["pom.xml", "README.md"], "NON_SOURCE"),
            ("python", ["src/p/__init__.py"], "API_TOUCHED"),
            ("python", ["src/p/_x.py"], "SOURCE"),
            ("typescript", ["src/index.ts"], "API_TOUCHED"),
            ("go", ["client.go"], "API_TOUCHED"),
            ("go", ["client_test.go"], "NON_SOURCE"),
            ("cpp", ["include/p/a.h"], "API_TOUCHED"),
            ("rust", ["src/lib.rs"], "API_TOUCHED"),
            ("net", ["src/A.cs"], "API_TOUCHED"),
        ]
        for platform, files, tier in cases:
            assert fd.classify_tier(platform, self.cmp(files), config=self.cfg)["tier"] == tier, (platform, files)

    def test_unknown_platform_never_guesses(self):
        v = fd.classify_tier("zig", self.cmp(["src/a.zig"]), config=self.cfg)
        assert v["tier"] == "UNKNOWN" and v["reason"] == "platform_not_in_language_api_paths"
        assert v["api_surface_touched"] is False

    def test_truncated_without_api_is_unknown_with_api_is_api(self):
        v = fd.classify_tier("typescript", self.cmp([f"src/internal/{i}.ts" for i in range(300)], truncated=True), config=self.cfg)
        assert v["tier"] == "UNKNOWN" and v["reason"] == "truncated_compare_incomplete" and v["truncated"] is True
        files = [f"src/internal/{i}.ts" for i in range(299)] + ["src/index.ts"]
        assert fd.classify_tier("typescript", self.cmp(files, truncated=True), config=self.cfg)["tier"] == "API_TOUCHED"

    def test_behind_and_empty(self):
        assert fd.classify_tier("java", self.cmp(["src/main/A.java"], status="behind"), config=self.cfg)["tier"] == "UNKNOWN"
        assert fd.classify_tier("java", self.cmp([]), config=self.cfg)["tier"] == "NO_CHANGE"


class TestReleaseState:
    info = {"registry_type": "pypi", "candidate": {"name": "p", "version": "1.0", "repo_sha": "r" * 40},
            "verification": {"published": True}}

    def test_matrix(self):
        head = "r" * 40
        assert fd.compute_release_state(self.info, head) == ("released", "head_is_release_commit")
        assert fd.compute_release_state(self.info, "z" * 40)[0] == "unreleased_main"
        assert fd.compute_release_state(None, head) == ("unknown", "no_registry_entry")
        assert fd.compute_release_state({**self.info, "registry_type": "weird"}, head)[0] == "unknown"
        assert fd.compute_release_state({**self.info, "verification": {"published": False}}, head) == ("unknown", "not_published")
        no_sha = {**self.info, "candidate": {"name": "p", "version": "1.0"}}
        assert fd.compute_release_state(no_sha, head) == ("unknown", "no_release_sha")
        assert fd.compute_release_state(self.info, None) == ("unknown", "no_upstream_head")

    def test_probe_rules(self):
        head = "r" * 40
        live_ok = {"source": "live_probe", "effective_published": True, "live": {"ambiguous": False, "latest_version": "1.0"}}
        assert fd.compute_release_state(self.info, head, probe=live_ok)[0] == "released"
        stale = {**live_ok, "live": {"ambiguous": False, "latest_version": "9.9"}}
        assert fd.compute_release_state(self.info, head, probe=stale) == ("unknown", "registry_version_stale_vs_live")
        ambiguous = {"source": "package_registry.json (probe ambiguous)", "live": {"ambiguous": True}}
        assert fd.compute_release_state(self.info, head, probe=ambiguous) == ("unknown", "live_probe_ambiguous")
        gone = {**live_ok, "effective_published": False}
        assert fd.compute_release_state(self.info, head, probe=gone) == ("unknown", "not_published")


# ── the fleet run ────────────────────────────────────────────────────────────

class TestFleetRun:
    def test_every_scenario(self, world):
        led = ledger(world)
        p = led["products"]
        assert sorted(p) == ["famA/java", "famB/python", "famC/typescript", "famD/go", "famE/net",
                             "famF/python", "famG/rust", "famH/zig", "famI/cpp"]  # inactive famZ excluded
        assert (p["famA/java"]["tier"], p["famA/java"]["api_surface_touched"]) == ("API_TOUCHED", True)
        assert p["famA/java"]["repo"] == "org-famA/Lib.Alpha-for-Java"
        assert p["famA/java"]["api_files"] == ["src/main/java/x/Api.java"]
        assert p["famB/python"]["tier"] == "NON_SOURCE"
        c = p["famC/typescript"]
        assert (c["tier"], c["truncated"], c["files_seen"]) == ("UNKNOWN", True, 300)
        assert c["tier_reason"] == "truncated_compare_incomplete"
        d = p["famD/go"]
        assert (d["status"], d["tier"]) == ("orphaned_baseline", "UNKNOWN") and "ORPHANED_BASELINE" in d["tier_reason"]
        assert (p["famE/net"]["status"], p["famE/net"]["tier_reason"]) == ("no_knowledge", "no_knowledge")
        assert p["famF/python"]["tier"] == "NO_CHANGE"
        assert p["famG/rust"]["tier"] == "SOURCE"
        assert p["famH/zig"]["tier"] == "UNKNOWN" and p["famH/zig"]["tier_reason"] == "platform_not_in_language_api_paths"
        i = p["famI/cpp"]
        assert (i["status"], i["tier"], i["transient"]) == ("error", "UNKNOWN", True) and "rate_limited" in i["tier_reason"]
        # release states
        assert p["famA/java"]["release_state"] == "released"
        assert p["famB/python"]["release_state"] == "unreleased_main"
        assert p["famG/rust"]["release_state"] == "unreleased_main"
        assert p["famI/cpp"]["release_state"] == "unknown"      # unsupported registry
        assert p["famC/typescript"]["release_state"] == "unknown"  # no registry entry
        # ground truth tier is explicit
        assert p["famA/java"]["ground_truth_tier"] == "GT-1" and p["famB/python"]["ground_truth_tier"] == "GT-2"
        assert led["summary"]["total"] == 9 and led["summary"]["api_touched"] == ["famA/java"]

    def test_rate_limit_does_not_crash_the_run(self, world):
        def hostile(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, "", "gh: API rate limit exceeded (HTTP 403)")
        rc, _ = run(world, "--json-out", str(world["out"] / "l.json"), runner=hostile)
        led = json.loads((world["out"] / "l.json").read_text(encoding="utf-8"))
        assert rc == 0
        assert all(r["tier"] == "UNKNOWN" and r["transient"] for r in led["products"].values())

    def test_missing_tools_are_unknown_not_crash(self, world):
        def missing(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 127, "", f"cannot run {cmd[0]}")
        rc, _ = run(world, "--json-out", str(world["out"] / "l.json"), runner=missing)
        led = json.loads((world["out"] / "l.json").read_text(encoding="utf-8"))
        assert rc == 0 and all("tool_missing" in r["tier_reason"] for r in led["products"].values())

    def test_products_filter_and_unknown_product(self, world):
        rc, _ = run(world, "--products", "famA/java", "--json-out", str(world["out"] / "one.json"))
        one = json.loads((world["out"] / "one.json").read_text(encoding="utf-8"))
        assert rc == 0 and list(one["products"]) == ["famA/java"] and one["scope"] == ["famA/java"]
        assert run(world, "--products", "nope/nothing")[0] == 2
        assert run(world, "--products", "famZ/java")[0] == 2   # inactive

    def test_missing_products_file_is_config_error(self, world):
        (world["root"] / "data" / "products.json").unlink()
        assert run(world)[0] == 2


class TestDeterminism:
    def test_same_inputs_byte_identical(self, world):
        run(world, "--json-out", str(world["out"] / "a.json"), "--md-out", str(world["out"] / "a.md"))
        run(world, "--json-out", str(world["out"] / "b.json"), "--md-out", str(world["out"] / "b.md"))
        assert (world["out"] / "a.json").read_bytes() == (world["out"] / "b.json").read_bytes()
        assert (world["out"] / "a.md").read_bytes() == (world["out"] / "b.md").read_bytes()

    def test_only_volatile_differs_across_times(self, world):
        run(world, "--json-out", str(world["out"] / "a.json"), now="2026-01-01T00:00:00Z")
        run(world, "--json-out", str(world["out"] / "b.json"), now="2027-06-06T06:06:06Z")
        a = json.loads((world["out"] / "a.json").read_text(encoding="utf-8"))
        b = json.loads((world["out"] / "b.json").read_text(encoding="utf-8"))
        assert a != b
        assert cps.canonical_for_compare(a) == cps.canonical_for_compare(b)
        raw = (world["out"] / "a.json").read_text(encoding="utf-8")
        assert raw.count("2026-01-01") == 1  # the timestamp appears exactly once, under volatile
        assert list(json.loads(raw)) == sorted(json.loads(raw))

    def test_markdown_lists_products(self, world):
        run(world, "--md-out", str(world["out"] / "l.md"))
        md = (world["out"] / "l.md").read_text(encoding="utf-8")
        assert "famA/java" in md and "API_TOUCHED" in md and "| Product |" in md


class TestSweepReport:
    def test_repo_patrol_schema(self, world):
        p = world["out"] / "sweep.json"
        run(world, "--sweep-out", str(p))
        rep = json.loads(p.read_text(encoding="utf-8"))
        assert set(rep) == {"generated_at", "total_products", "changed", "unchanged", "fetch_failures", "summary"}
        assert set(rep["summary"]) == {"changed", "unchanged", "fetch_failures", "high_impact", "medium_impact", "low_impact"}
        by = {c["family"] + "/" + c["platform"]: c for c in rep["changed"]}
        assert by["famA/java"]["impact"] == "HIGH" and by["famA/java"]["current_sha"] == H["a"]
        assert by["famB/python"]["impact"] == "LOW"
        assert by["famC/typescript"]["impact"] == "MEDIUM"
        assert by["famE/net"]["impact"] == "HIGH" and by["famE/net"]["stored_sha"] is None
        assert [u["family"] for u in rep["unchanged"]] == ["famF"]
        assert rep["total_products"] == 9
        for c in rep["changed"]:
            assert set(c) >= {"family", "platform", "stored_sha", "current_sha", "impact"}

    def test_upstream_unreachable_goes_to_fetch_failures(self, world):
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"], ls_error="fatal: unable to access")
        p = world["out"] / "sweep.json"
        run(world, "--sweep-out", str(p))
        rep = json.loads(p.read_text(encoding="utf-8"))
        assert [f["family"] for f in rep["fetch_failures"]] == ["famF"]
        assert rep["summary"]["fetch_failures"] == 1

    def test_not_written_unless_requested(self, world):
        run(world)
        assert not (world["root"] / "reports").exists() and not world["out"].exists()


# ── state writes ─────────────────────────────────────────────────────────────

class TestUpdateState:
    def test_writes_drift_never_propagation(self, world):
        # product A already propagated at an OLD sha; the scan must flip it to DRIFTED, not touch it
        cps.record_propagation("famA", "java", content_propagated_sha="0" * 40,
                               content_propagated_knowledge_commit="k" * 40, local_only=False,
                               capability_units=[], gate_verdict="PASS")
        before = cps.read_state("famA", "java")
        rc, _ = run(world, "--update-state")
        assert rc == 0
        a = cps.read_state("famA", "java")
        assert a["upstream_head"] == H["a"] and a["tier"] == "API_TOUCHED" and a["status"] == "DRIFTED"
        assert a["api_surface_touched"] is True and a["ground_truth_tier"] == "GT-1"
        for field in cps.PROPAGATION_FIELDS:
            assert a[field] == before[field]
        # knowledge-only products are never PROPAGATED
        f = cps.read_state("famF", "python")
        assert f["tier"] == "NO_CHANGE" and f["knowledge_sha"] == f["upstream_head"] and f["status"] == "UNRECORDED"
        # famD (orphaned) and famI (rate limited): head known -> recorded as UNKNOWN
        assert cps.read_state("famD", "go")["tier"] == "UNKNOWN"
        assert cps.read_state("famE", "net")["knowledge_sha"] is None

    def test_idempotent_bytes_and_dry_run(self, world):
        state_file = cps.state_path()
        assert run(world, "--update-state", "--dry-run")[0] == 0
        assert not state_file.exists()
        run(world, "--update-state")
        first = state_file.read_bytes()
        run(world, "--update-state")
        assert state_file.read_bytes() == first
        run(world, "--update-state", now="2030-01-01T00:00:00Z")
        assert cps.canonical_for_compare(json.loads(state_file.read_text(encoding="utf-8"))) == \
            cps.canonical_for_compare(json.loads(first.decode("utf-8")))

    def test_head_unreachable_does_not_clobber_good_state(self, world):
        run(world, "--update-state")
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"], ls_error="fatal: unable to access")
        rc, out = run(world, "--update-state")
        assert cps.read_state("famF", "python")["upstream_head"] == H["f"]
        assert "famF/python" in out


# ── issues ───────────────────────────────────────────────────────────────────

class GhRecorder:
    """Fixture git/gh-api answers + a recording, stateful fake of `gh issue ...`."""

    def __init__(self, fx_dir, existing=None, list_fails=False):
        self.inner = fd.FixtureRunner(fx_dir)
        self.clock = 0
        self.issues = {}
        for i in (existing or []):
            self.issues[i["number"]] = {"labels": [], **i}
            self.issues[i["number"]].setdefault("updatedAt", self._tick())
        self.next = 100
        self.ops: list[list[str]] = []
        self.list_fails = list_fails

    def _tick(self):
        self.clock += 1
        return f"2026-01-01T00:{self.clock:05d}Z"

    def __call__(self, cmd, **kw):
        if cmd[:2] == ["gh", "label"]:
            self.ops.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:2] != ["gh", "issue"]:
            return self.inner(cmd, **kw)
        self.ops.append(list(cmd))
        sub = cmd[2]
        arg = lambda flag: cmd[cmd.index(flag) + 1]  # noqa: E731
        multi = lambda flag: [cmd[i + 1] for i, c in enumerate(cmd) if c == flag]  # noqa: E731
        ok = lambda out="": subprocess.CompletedProcess(cmd, 0, out, "")  # noqa: E731
        if sub == "list":
            if self.list_fails:
                return subprocess.CompletedProcess(cmd, 1, "", "gh: HTTP 502")
            limit = int(arg("--limit"))
            items = sorted(self.issues.values(), key=lambda i: i["number"])[:limit]   # like gh: silently capped
            return ok(json.dumps(items))
        if sub == "create":
            n, self.next = self.next, self.next + 1
            self.issues[n] = {"number": n, "title": arg("--title"), "body": arg("--body"),
                              "labels": multi("--label"), "updatedAt": self._tick()}
            return ok(f"https://github.com/{arg('--repo')}/issues/{n}\n")
        if sub == "edit":
            i = self.issues[int(cmd[3])]
            labels = [x for x in i.get("labels", []) if x not in multi("--remove-label")] + multi("--add-label")
            i.update(title=arg("--title"), body=arg("--body"), labels=labels, updatedAt=self._tick())
            return ok()
        if sub == "close":
            self.issues.pop(int(cmd[3]))
            return ok()
        raise AssertionError(cmd)

    def kinds(self, sub, group="issue"):
        return [o for o in self.ops if o[1] == group and o[2] == sub]


def seed_propagated(*products):
    """Record each (family, platform) as fully propagated at its fixture head -- a healthy fleet."""
    for fam, plat in products:
        head = H[fam[-1].lower()]
        cps.record_drift(fam, plat, upstream_head=head, knowledge_sha=head, tier="NO_CHANGE", release_state="unknown",
                         ahead_by=0, files_seen=0, source_files=0, api_surface_touched=False, truncated=False,
                         ground_truth_tier="GT-2")
        cps.record_propagation(fam, plat, content_propagated_sha=head, content_propagated_knowledge_commit="k" * 40,
                               local_only=False, capability_units=[], gate_verdict="PASS")


ISSUE_ARGS = ("--file-issues", "--repo", "owner/tracker")
ELIGIBLE = ["famA/java", "famC/typescript", "famD/go", "famG/rust", "famH/zig"]  # see decide_issue_action


def titles(gh):
    return sorted(i["title"] for i in gh.issues.values())


@pytest.fixture
def steady(world):
    """A healthy fleet: the products with no source drift are already propagated."""
    seed_propagated(("famB", "python"), ("famF", "python"))


@pytest.mark.usefixtures("steady")
class TestIssues:
    def test_creates_one_issue_per_eligible_product(self, world):
        gh = GhRecorder(world["fx"])
        rc, out = run(world, *ISSUE_ARGS, runner=gh)
        assert rc == 0
        assert len(gh.kinds("create")) == 5
        got = sorted(t.split(":")[0] for t in titles(gh))
        assert got == sorted(f"FLEET-PROPAGATE-{p.replace('/', '-')}" for p in ELIGIBLE)
        by_prefix = {i["title"].split(":")[0]: i for i in gh.issues.values()}
        body = by_prefix["FLEET-PROPAGATE-famA-java"]["body"]
        assert H["a"] in body and K in body and "API_TOUCHED" in body and "src/main/java/x/Api.java" in body
        # skipped for the documented reasons: NON_SOURCE, no_knowledge, NO_CHANGE, transient
        assert "FLEET-PROPAGATE-famB-python" not in by_prefix
        # unreleased main still gets its issue, with an explicit availability warning in the body
        rust = by_prefix["FLEET-PROPAGATE-famG-rust"]["body"]
        assert "unreleased_main" in rust and "unreleased main: do not present as released" in rust
        assert "do not present as released" not in body            # released product: no such line
        assert "FLEET-PROPAGATE-famI-cpp" not in by_prefix and "FLEET-PROPAGATE-famE-net" not in by_prefix

    def test_rerun_is_deduplicated_and_quiet(self, world):
        gh = GhRecorder(world["fx"])
        run(world, *ISSUE_ARGS, runner=gh)
        n = len(gh.issues)
        run(world, *ISSUE_ARGS, runner=gh)
        assert len(gh.issues) == n and len(gh.kinds("create")) == 5 and not gh.kinds("edit")

    def test_changed_head_updates_in_place_never_a_second_issue(self, world):
        gh = GhRecorder(world["fx"])
        run(world, *ISSUE_ARGS, runner=gh)
        big = [page([f"src/internal/f{i}.ts" for i in range(100 * n, 100 * n + 100)]) for n in range(3)]
        # HEAD / ahead_by churn alone must NOT rewrite the issue (volatile section is excluded from the comparison)
        write_fixture(world["fx"], "org-famC", "Lib.Gamma-for-TypeScript", head="5" * 40, pages=big)
        run(world, *ISSUE_ARGS, runner=gh)
        assert not gh.kinds("edit") and len(gh.issues) == 5
        # a STABLE change (tier flips to API_TOUCHED) edits in place -- never a second issue
        write_fixture(world["fx"], "org-famC", "Lib.Gamma-for-TypeScript", head="5" * 40,
                      pages=[page(["src/index.ts"])])
        run(world, *ISSUE_ARGS, runner=gh)
        edits = gh.kinds("edit")
        assert len(edits) == 1 and len(gh.issues) == 5 and len(gh.kinds("create")) == 5
        body = next(i["body"] for i in gh.issues.values() if "famC-typescript" in i["title"])
        assert "API_TOUCHED" in body and "5" * 40 in body

    def test_prefix_match_is_exact_per_product(self, world):
        decoy = {"number": 7, "title": "FLEET-PROPAGATE-famA-javascript: other product", "body": "x"}
        gh = GhRecorder(world["fx"], existing=[decoy])
        run(world, "--products", "famA/java", *ISSUE_ARGS, runner=gh)
        assert len(gh.kinds("create")) == 1 and 7 in gh.issues and gh.issues[7]["body"] == "x"

    def test_max_issues_per_run_defers_lowest_priority(self, world):
        gh = GhRecorder(world["fx"])
        rc, out = run(world, *ISSUE_ARGS, "--max-issues-per-run", "2", runner=gh)
        assert len(gh.kinds("create")) == 2
        # API_TOUCHED (java) first, then SOURCE (rust, unreleased main); UNKNOWN products wait
        assert [t.split(":")[0] for t in titles(gh)] == ["FLEET-PROPAGATE-famA-java", "FLEET-PROPAGATE-famG-rust"]
        assert out.count("deferred") == 3
        run(world, *ISSUE_ARGS, "--max-issues-per-run", "10", runner=gh)  # next run catches up
        assert len(gh.issues) == 5

    def test_closes_when_state_says_propagated(self, world):
        gh = GhRecorder(world["fx"])
        run(world, *ISSUE_ARGS, runner=gh)
        cps.record_drift("famA", "java", upstream_head=H["a"], knowledge_sha=H["a"], tier="NO_CHANGE",
                         release_state="released", ahead_by=0, files_seen=0, source_files=0,
                         api_surface_touched=False, truncated=False, ground_truth_tier="GT-1")
        cps.record_propagation("famA", "java", content_propagated_sha=H["a"], content_propagated_knowledge_commit=H["a"],
                               local_only=False, capability_units=[], gate_verdict="PASS")
        run(world, *ISSUE_ARGS, runner=gh)
        assert len(gh.kinds("close")) == 1
        assert not any("famA-java" in i["title"] for i in gh.issues.values())

    def test_lookup_failure_never_creates(self, world):
        gh = GhRecorder(world["fx"], list_fails=True)
        rc, out = run(world, *ISSUE_ARGS, runner=gh)
        assert rc == 1 and not gh.kinds("create") and "failed" in out

    @pytest.mark.parametrize("extra", [("--dry-run",), ("--offline",)])
    def test_dry_run_and_offline_never_touch_issues(self, world, extra):
        gh = GhRecorder(world["fx"])
        if extra == ("--offline",):
            rc, out = run(world, *ISSUE_ARGS, "--offline", str(world["fx"]))
        else:
            rc, out = run(world, *ISSUE_ARGS, *extra, runner=gh)
        assert rc == 0 and not gh.ops
        assert "would_file" in out

    def test_repo_required_to_file(self, world, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        gh = GhRecorder(world["fx"])
        assert run(world, "--file-issues", runner=gh)[0] == 2 and not gh.ops


def mk_row(**kw):
    row = {"family": "f", "platform": "p", "product": "f/p", "upstream_head": H["a"], "status": "ok",
           "transient": False, "tier": "NO_CHANGE", "tier_reason": "x", "release_state": "released",
           "release_state_reason": "x", "knowledge_sha": K, "ahead_by": 0, "files_seen": 0, "source_files": 0,
           "api_surface_touched": False, "truncated": False, "api_files": [], "ground_truth_tier": "GT-2"}
    row.update(kw)
    return row


class TestDecideIssueAction:
    def test_knowledge_only_refresh_is_not_a_blind_spot(self):
        # knowledge == head (NO_CHANGE) but nothing was ever propagated: must NOT be skipped
        for tier in ("NO_CHANGE", "NON_SOURCE"):
            for status in ("UNRECORDED", "DRIFTED"):
                assert fd.decide_issue_action(mk_row(tier=tier), status)[0] == "file", (tier, status)

    def test_propagation_baseline_tier_can_justify_skipping(self):
        for ptier in ("NO_CHANGE", "NON_SOURCE"):
            action, reason = fd.decide_issue_action(mk_row(tier="API_TOUCHED", propagation_tier=ptier), "DRIFTED")
            assert action == "skip" and "since_propagation" in reason
        for ptier in ("SOURCE", "API_TOUCHED", "UNKNOWN", "UNKNOWN-BASELINE"):
            assert fd.decide_issue_action(mk_row(propagation_tier=ptier), "DRIFTED")[0] == "file"

    def test_genuinely_propagated_product_is_not_filed(self):
        assert fd.decide_issue_action(mk_row(tier="NO_CHANGE"), "PROPAGATED")[0] == "close"

    def test_only_propagated_closes(self):
        # mutant guard: closing for DRIFTED / UNRECORDED / PROPAGATED_LOCAL must fail this test
        for status in ("DRIFTED", "UNRECORDED", "PROPAGATED_LOCAL"):
            assert fd.decide_issue_action(mk_row(tier="API_TOUCHED"), status)[0] != "close", status
        assert fd.decide_issue_action(mk_row(tier="API_TOUCHED"), "PROPAGATED_LOCAL") == ("skip", "propagated_local_awaiting_push")

    @pytest.mark.parametrize("kw,reason", [
        ({"upstream_head": None}, "no_upstream_head"),
        ({"status": "no_knowledge"}, "no_knowledge"),
        ({"status": "repo_unreachable"}, "repo_unreachable"),
        ({"transient": True}, "transient_error"),
        ({"propagation_transient": True}, "transient_error"),
    ])
    def test_skips(self, kw, reason):
        assert fd.decide_issue_action(mk_row(tier="API_TOUCHED", **kw), "DRIFTED") == ("skip", reason)


def _drift_famA(**kw):
    args = dict(upstream_head=H["a"], knowledge_sha=H["a"], tier="NO_CHANGE", release_state="released", ahead_by=0,
                files_seen=0, source_files=0, api_surface_touched=False, truncated=False, ground_truth_tier="GT-1")
    args.update(kw)
    cps.record_drift("famA", "java", **args)


def _propagate_famA(sha, *, local_only):
    cps.record_propagation("famA", "java", content_propagated_sha=sha, content_propagated_knowledge_commit="k" * 40,
                           local_only=local_only, capability_units=[], gate_verdict="PASS")


@pytest.mark.usefixtures("steady")
class TestIssueLifecycleSafety:
    def _open_issue_for_famA(self, world):
        gh = GhRecorder(world["fx"])
        run(world, "--products", "famA/java", *ISSUE_ARGS, runner=gh)
        assert len(gh.issues) == 1
        return gh

    def test_propagated_local_does_not_close_the_issue(self, world):
        gh = self._open_issue_for_famA(world)
        _drift_famA()
        _propagate_famA(H["a"], local_only=True)
        assert cps.read_state("famA", "java")["status"] == "PROPAGATED_LOCAL"
        run(world, "--products", "famA/java", *ISSUE_ARGS, runner=gh)
        assert not gh.kinds("close") and len(gh.issues) == 1
        # ... and once it is pushed (local_only False) the issue closes
        _propagate_famA(H["a"], local_only=False)
        run(world, "--products", "famA/java", *ISSUE_ARGS, runner=gh)
        assert len(gh.kinds("close")) == 1 and not gh.issues

    def test_drifted_does_not_close_the_issue(self, world):
        gh = self._open_issue_for_famA(world)
        _drift_famA()
        _propagate_famA("3" * 40, local_only=False)
        assert cps.read_state("famA", "java")["status"] == "DRIFTED"
        run(world, "--products", "famA/java", *ISSUE_ARGS, runner=gh)
        assert not gh.kinds("close") and len(gh.issues) == 1


class TestNeverPropagated:
    def test_knowledge_only_refresh_files_a_never_propagated_issue(self, world):
        gh = GhRecorder(world["fx"])
        rc, out = run(world, "--products", "famF/python", "famB/python", *ISSUE_ARGS, runner=gh)
        assert rc == 0
        # famF: knowledge == head (NO_CHANGE); famB: NON_SOURCE -- yet nothing was ever propagated
        keyed = {i["title"].split(":")[0]: i for i in gh.issues.values()}
        assert sorted(keyed) == ["FLEET-PROPAGATE-famB-python", "FLEET-PROPAGATE-famF-python"]
        for issue in keyed.values():
            assert "UNKNOWN-BASELINE" in issue["body"] and "never propagated" in issue["body"].lower()
            assert issue["labels"] == ["never-propagated"]
        assert [o[3] for o in gh.kinds("create", "label")] == ["never-propagated"]     # label ensured, once
        # re-run: deduplicated, quiet
        run(world, "--products", "famF/python", "famB/python", *ISSUE_ARGS, runner=gh)
        assert len(gh.issues) == 2 and not gh.kinds("edit") and len(gh.kinds("create")) == 2

    def test_ledger_row_carries_the_propagation_baseline(self, world):
        led = ledger(world)
        f = led["products"]["famF/python"]
        assert f["tier"] == "NO_CHANGE" and f["propagation_tier"] == "UNKNOWN-BASELINE"
        assert f["propagation_basis"] == "never_propagated" and f["propagation_status"] == "UNRECORDED"

    def test_never_propagated_ranks_after_real_drift_and_obeys_the_cap(self, world):
        gh = GhRecorder(world["fx"])
        run(world, *ISSUE_ARGS, "--max-issues-per-run", "5", runner=gh)
        got = [t.split(":")[0] for t in titles(gh)]
        assert len(got) == 5
        assert "FLEET-PROPAGATE-famB-python" not in got and "FLEET-PROPAGATE-famF-python" not in got  # last in line

    def _set_propagated_sha(self, world, sha, *, family="famF", platform="python"):
        seed_propagated((family, platform))
        state = json.loads(world["state"].read_text(encoding="utf-8"))
        state["products"][f"{family}/{platform}"]["content_propagated_sha"] = sha
        world["state"].write_text(json.dumps(state), encoding="utf-8")

    def test_propagated_sha_derives_the_tier_from_that_sha(self, world):
        P = "7" * 40
        self._set_propagated_sha(world, P)     # propagated at P, older than the fixture head
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"], pages=[page(["README.md"])],
                      by_base={P: {"pages": [page(["src/pkg/__init__.py"])]}})
        row = ledger(world)["products"]["famF/python"]
        assert row["propagation_basis"] == "propagated_sha" and row["propagation_tier"] == "API_TOUCHED"
        assert row["propagation_api_files"] == ["src/pkg/__init__.py"]

    def test_verified_propagated_sha_with_only_docs_changes_needs_no_issue(self, world):
        P = "7" * 40
        self._set_propagated_sha(world, P)
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"], pages=[page(["src/x.py"])],
                      by_base={P: {"pages": [page(["README.md", "docs/guide.md"])]}})
        gh = GhRecorder(world["fx"])
        run(world, "--products", "famF/python", *ISSUE_ARGS, runner=gh)
        row = ledger(world)["products"]["famF/python"]
        assert row["propagation_basis"] == "propagated_sha" and row["propagation_tier"] == "NON_SOURCE"
        assert not gh.issues

    def test_unverified_propagated_sha_is_not_trusted_as_a_baseline(self, world):
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"], pages=[page(["README.md"])],
                      by_base={"7" * 40: {"pages": [page(["README.md"])]}})
        cps.record_drift("famF", "python", upstream_head=H["f"], knowledge_sha=H["f"], tier="NO_CHANGE",
                         release_state="unknown", ahead_by=0, files_seen=0, source_files=0,
                         api_surface_touched=False, truncated=False, ground_truth_tier="GT-2")
        state = json.loads(world["state"].read_text(encoding="utf-8"))
        state["products"]["famF/python"]["content_propagated_sha"] = "7" * 40      # hand edit, no PASS verdict
        world["state"].write_text(json.dumps(state), encoding="utf-8")
        row = ledger(world)["products"]["famF/python"]
        assert row["propagation_basis"] == "never_propagated" and row["propagation_tier"] == "UNKNOWN-BASELINE"

    def test_orphaned_propagated_sha_is_unknown_and_filed(self, world):
        P = "7" * 40
        self._set_propagated_sha(world, P)
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"], pages=[page([])],
                      by_base={P: {"error": "gh: No common ancestor between 777 and fff. (HTTP 404)"}})
        row = ledger(world)["products"]["famF/python"]
        assert row["propagation_tier"] == "UNKNOWN" and "ORPHANED_PROPAGATED_BASELINE" in row["propagation_tier_reason"]


class TestRepoUnreachable:
    def test_repo_not_found_is_unreachable_not_orphaned(self, world):
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"],
                      ls_error="remote: Repository not found. fatal: repository was not found")
        p = world["out"] / "l.json"
        gh = GhRecorder(world["fx"])
        rc, out = run(world, "--products", "famF/python", "--json-out", str(p), *ISSUE_ARGS, runner=gh)
        row = json.loads(p.read_text(encoding="utf-8"))
        assert row["products"]["famF/python"]["status"] == "repo_unreachable"
        assert row["products"]["famF/python"]["tier"] == "UNKNOWN"
        assert row["summary"]["repo_unreachable"] == ["famF/python"]
        assert row["summary"]["orphaned_baseline"] == []
        assert not gh.issues                                   # no issue for an unreachable repository

    def test_no_access_is_unreachable(self, world):
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"],
                      ls_error="fatal: could not read Username for https://github.com: terminal prompts disabled")
        assert ledger(world)["products"]["famF/python"]["status"] == "repo_unreachable"

    def test_404_on_compare_with_reachable_repo_is_orphaned_baseline(self, world):
        # ls-remote worked (repository reachable) but the knowledge sha is gone from compare -> orphaned
        write_fixture(world["fx"], "org-famD", "Lib.Delta-for-Go", head=H["d"], error="gh: Not Found (HTTP 404)")
        d = ledger(world)["products"]["famD/go"]
        assert d["status"] == "orphaned_baseline" and "ORPHANED_BASELINE" in d["tier_reason"]

    def test_rate_limit_and_network_stay_transient_errors(self, world):
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"],
                      ls_error="fatal: unable to access: Could not resolve host")
        f = ledger(world)["products"]["famF/python"]
        assert f["status"] == "error" and f["transient"] is True

    def test_unreachable_is_listed_in_markdown_and_sweep(self, world):
        write_fixture(world["fx"], "org-famF", "Lib.Zeta-for-Python", head=H["f"], ls_error="remote: Repository not found.")
        run(world, "--md-out", str(world["out"] / "l.md"), "--sweep-out", str(world["out"] / "s.json"))
        assert "repo_unreachable" in (world["out"] / "l.md").read_text(encoding="utf-8")
        sweep = json.loads((world["out"] / "s.json").read_text(encoding="utf-8"))
        assert [f["family"] for f in sweep["fetch_failures"]] == ["famF"]


def issue_rows(n_existing, n_new, tier="SOURCE"):
    rows = [mk_row(family=f"old{i:02d}", platform="p", product=f"old{i:02d}/p", tier=tier, tier_reason="r")
            for i in range(n_existing)]
    rows += [mk_row(family=f"new{i:02d}", platform="p", product=f"new{i:02d}/p", tier=tier, tier_reason="r")
             for i in range(n_new)]
    return rows


def stale_issue(number, family, updated):
    return {"number": number, "title": f"FLEET-PROPAGATE-{family}-p: propagate upstream changes to content",
            "body": "<!-- fleet-propagate:stale -->\nold body", "labels": [], "updatedAt": updated}


class TestIssueBudgets:
    def _run(self, gh, rows, **kw):
        client = fd.IssueClient(repo="o/r", runner=gh)
        return fd.process_issues(rows, client=client, state_lookup=lambda f, p: None, dry_run=False, **kw)

    def test_new_products_are_not_starved_by_stale_issues(self, world):
        existing = [stale_issue(i + 1, f"old{i:02d}", f"2026-01-01T00:{i:05d}Z") for i in range(10)]
        gh = GhRecorder(world["fx"], existing=existing)
        res = self._run(gh, issue_rows(10, 2), max_issues=2, max_edits=2)
        created = sorted(r["product"] for r in res if r["action"] == "created")
        assert created == ["new00/p", "new01/p"]
        assert len([r for r in res if r["action"] == "updated"]) == 2
        assert len([r for r in res if r["action"] == "deferred"]) == 8

    def test_edits_rotate_oldest_updated_first_without_starvation(self, world):
        existing = [stale_issue(i + 1, f"old{i:02d}", f"2026-01-01T00:{i:05d}Z") for i in range(10)]
        gh = GhRecorder(world["fx"], existing=existing)
        edited_order = []
        for _ in range(5):
            res = self._run(gh, issue_rows(10, 0), max_issues=10, max_edits=2)
            edited_order += [r["product"] for r in res if r["action"] == "updated"]
        assert edited_order == [f"old{i:02d}/p" for i in range(10)]     # each exactly once, oldest first
        res = self._run(gh, issue_rows(10, 0), max_issues=10, max_edits=2)
        assert all(r["action"] == "unchanged" for r in res)

    def test_default_edit_budget_equals_issue_budget(self, world):
        existing = [stale_issue(i + 1, f"old{i:02d}", f"2026-01-01T00:{i:05d}Z") for i in range(5)]
        gh = GhRecorder(world["fx"], existing=existing)
        res = self._run(gh, issue_rows(5, 0), max_issues=3)
        assert len([r for r in res if r["action"] == "updated"]) == 3

    def test_creates_are_budgeted_before_edits_in_call_order(self, world):
        existing = [stale_issue(1, "old00", "2026-01-01T00:00001Z")]
        gh = GhRecorder(world["fx"], existing=existing)
        self._run(gh, issue_rows(1, 1), max_issues=5, max_edits=5)
        subs = [o[2] for o in gh.ops if o[1] == "issue" and o[2] in ("create", "edit")]
        assert subs == ["create", "edit"]

    def test_cli_exposes_max_edits_per_run(self):
        assert fd.build_parser().parse_args(["--max-edits-per-run", "3"]).max_edits_per_run == 3
        assert fd.build_parser().parse_args([]).max_edits_per_run is None


class TestIssueBodyStability:
    def _body(self, **kw):
        row = mk_row(tier="API_TOUCHED", tier_reason="api_path_files_changed", api_surface_touched=True,
                     api_files=["src/a.x"], **kw)
        return fd.issue_body(row, "DRIFTED", {"content_propagated_sha": H["c"]})

    def test_volatile_fields_live_behind_a_marker_and_are_excluded(self):
        one = self._body()
        two = self._body(upstream_head="9" * 40, ahead_by=99, files_seen=77, knowledge_sha="8" * 40)
        assert one != two                                           # the sha IS in the body ...
        assert H["a"] in one and "9" * 40 in two
        assert fd.stable_body(one) == fd.stable_body(two)           # ... but never counts as staleness
        assert fd.VOLATILE_MARKER in one
        stable = fd.stable_body(one)
        assert H["a"] not in stable and "ahead" not in stable.lower()

    def test_stable_fields_do_count(self):
        assert fd.stable_body(self._body()) != fd.stable_body(
            fd.issue_body(mk_row(tier="SOURCE", tier_reason="x"), "DRIFTED", None))

    def test_crlf_and_trailing_whitespace_are_normalised(self):
        body = self._body()
        assert fd.stable_body(body.replace("\n", "\r\n") + "\r\n\r\n") == fd.stable_body(body)

    def test_crlf_body_from_github_is_not_stale(self, world):
        row = mk_row(family="famA", platform="java", product="famA/java", tier="API_TOUCHED",
                     tier_reason="api_path_files_changed", api_surface_touched=True)
        body = fd.issue_body(row, "UNRECORDED", None)
        gh = GhRecorder(world["fx"], existing=[{"number": 4, "title": fd.issue_title("famA", "java"),
                                                 "body": body.replace("\n", "\r\n"), "labels": []}])
        client = fd.IssueClient(repo="o/r", runner=gh)
        res = fd.process_issues([row], client=client, max_issues=5, state_lookup=lambda f, p: None, dry_run=False)
        assert res[0]["action"] == "unchanged" and not gh.kinds("edit")

    def test_unreleased_and_never_propagated_markers(self):
        body = fd.issue_body(mk_row(release_state="unreleased_main", propagation_basis="never_propagated",
                                    propagation_tier="UNKNOWN-BASELINE", propagation_tier_reason="never_propagated"),
                             "UNRECORDED", None)
        assert "unreleased main: do not present as released" in body and "UNKNOWN-BASELINE" in body


class TestIssueListLimit:
    def test_reaching_the_limit_is_an_error_not_a_silent_miss(self, world):
        crowd = [{"number": 1000 + i, "title": f"unrelated {i}", "body": "", "labels": [], "updatedAt": "x"}
                 for i in range(fd.ISSUE_LIST_LIMIT)]
        gh = GhRecorder(world["fx"], existing=crowd)
        rc, out = run(world, "--products", "famA/java", *ISSUE_ARGS, runner=gh)
        assert rc == 1 and not gh.kinds("create") and "limit" in out.lower()

    def test_just_under_the_limit_is_fine(self, world):
        crowd = [{"number": 1000 + i, "title": f"unrelated {i}", "body": "", "labels": [], "updatedAt": "x"}
                 for i in range(fd.ISSUE_LIST_LIMIT - 1)]
        gh = GhRecorder(world["fx"], existing=crowd)
        rc, _ = run(world, "--products", "famA/java", *ISSUE_ARGS, runner=gh)
        assert rc == 0 and len(gh.kinds("create")) == 1

    def test_list_command_asks_for_updatedat_and_the_limit(self, world):
        gh = GhRecorder(world["fx"])
        run(world, "--products", "famA/java", *ISSUE_ARGS, runner=gh)
        cmd = gh.kinds("list")[0]
        assert str(fd.ISSUE_LIST_LIMIT) in cmd and "number,title,body,updatedAt" in cmd

    def test_find_picks_the_oldest_duplicate_regardless_of_list_order(self, world):
        dupes = [{"number": n, "title": f"FLEET-PROPAGATE-famA-java: dup {n}", "body": "", "labels": [], "updatedAt": "x"}
                 for n in (12, 5, 9)]
        gh = GhRecorder(world["fx"], existing=dupes)
        gh.issues = {n: i for n, i in reversed(list(gh.issues.items()))}
        client = fd.IssueClient(repo="o/r", runner=gh)
        assert client.find("famA", "java")["number"] == 5
        # and an edit goes to the oldest one only
        row = mk_row(family="famA", platform="java", product="famA/java", tier="API_TOUCHED")
        fd.process_issues([row], client=fd.IssueClient(repo="o/r", runner=gh), max_issues=3,
                          state_lookup=lambda f, p: None, dry_run=False)
        assert [o[3] for o in gh.kinds("edit")] == ["5"]


class TestOfflineNeverTouchesRealState:
    def test_offline_update_state_without_state_file_changes_nothing_on_disk(self, world):
        # repro: the fixture head equals the recorded propagated sha; a write would flip DRIFTED -> PROPAGATED
        _drift_famA(upstream_head="5" * 40, knowledge_sha=K, tier="SOURCE", ahead_by=1, files_seen=1, source_files=1)
        _propagate_famA(H["a"], local_only=False)
        before = world["state"].read_bytes()
        assert cps.read_state("famA", "java")["status"] == "DRIFTED"
        rc, out = run(world, "--update-state", state_file=False)
        assert rc == 0
        assert world["state"].read_bytes() == before
        assert cps.read_state("famA", "java")["status"] == "DRIFTED"
        assert "--state-file" in out

    def test_explicit_state_file_override_is_honoured_and_real_file_untouched(self, world):
        other = world["root"] / "elsewhere" / "state.json"
        assert not world["state"].exists()
        rc, _ = run(world, "--update-state", "--offline", str(world["fx"]), "--state-file", str(other))
        assert rc == 0 and other.exists() and not world["state"].exists()
        assert cps.state_path() == world["state"]               # the module's path is restored afterwards
        cps.configure(other)
        try:
            assert cps.read_state("famA", "java")["upstream_head"] == H["a"]
        finally:
            cps.configure(world["state"])

    def test_dry_run_with_state_file_still_writes_nothing(self, world):
        other = world["root"] / "elsewhere" / "state.json"
        run(world, "--update-state", "--dry-run", "--offline", str(world["fx"]), "--state-file", str(other))
        assert not other.exists() and not world["state"].exists()

    def test_online_update_state_still_writes_the_configured_state(self, world):
        gh = GhRecorder(world["fx"])
        rc, _ = run(world, "--update-state", runner=gh)
        assert rc == 0 and world["state"].exists()


class TestStateFailuresExitCleanly:
    def _fail_replace(self, world):
        def replace(src, dst):
            raise PermissionError(13, "Permission denied")
        cps.configure(world["state"], replace=replace, sleep=lambda s: None, retry_budget=0.05)

    def test_write_failure_exits_4_after_reports_and_issues(self, world, capsys):
        self._fail_replace(world)
        gh = GhRecorder(world["fx"])
        p, m, sw = (world["out"] / n for n in ("l.json", "l.md", "s.json"))
        rc, out = run(world, "--update-state", *ISSUE_ARGS, "--json-out", str(p), "--md-out", str(m),
                      "--sweep-out", str(sw), runner=gh)
        err = capsys.readouterr().err
        assert rc == 4
        assert p.exists() and m.exists() and sw.exists()               # reports written BEFORE the state write
        assert "created" in out                                         # issues already filed are reported
        assert "state" in err.lower() and "Traceback" not in err and "Traceback" not in out
        assert len(gh.kinds("create")) >= 1

    def test_corrupt_state_exits_4(self, world, capsys):
        world["state"].write_text("{broken", encoding="utf-8")
        p = world["out"] / "l.json"
        rc, out = run(world, "--update-state", "--json-out", str(p), runner=GhRecorder(world["fx"]))
        assert rc == 4 and p.exists() and "Traceback" not in capsys.readouterr().err
        assert world["state"].read_text(encoding="utf-8") == "{broken"      # never overwritten

    def test_lock_timeout_exits_4(self, world, capsys):
        def boom(*a, **k):
            raise cps.StateLockTimeout("lock busy")
        fd.configure(repo_root=world["root"], record_drift=boom)      # world teardown resets the seam
        rc, _ = run(world, "--update-state", runner=GhRecorder(world["fx"]))
        assert rc == 4 and "lock busy" in capsys.readouterr().err

    def test_unreadable_state_while_analysing_exits_4(self, world, capsys):
        world["state"].write_text("{}", encoding="utf-8")

        def deny(path):
            raise PermissionError(13, "denied")
        cps.configure(world["state"], read_bytes=deny, sleep=lambda s: None, retry_budget=0.05)
        rc, _ = run(world, runner=GhRecorder(world["fx"]))
        assert rc == 4 and "Traceback" not in capsys.readouterr().err

    def test_exit_code_is_documented(self):
        assert "4" in fd.__doc__.split("Exit codes:")[1]


class TestReleaseTrigger:
    def test_refreshes_one_product_and_files_its_issue(self, world):
        # released later: the registry now names the head as the released commit
        reg_path = world["root"] / "data" / "package_registry.json"
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["famG"]["rust"]["candidate"]["repo_sha"] = H["g"]
        reg_path.write_text(json.dumps(reg), encoding="utf-8")
        gh = GhRecorder(world["fx"])
        rc, _ = run(world, "--release-trigger", "famG/rust", "--repo", "owner/tracker", runner=gh)
        assert rc == 0
        assert len(gh.kinds("create")) == 1 and "FLEET-PROPAGATE-famG-rust" in titles(gh)[0]
        rec = cps.read_state("famG", "rust")
        assert rec["release_state"] == "released" and rec["tier"] == "SOURCE"
        assert cps.read_state("famA", "java") is None   # nothing else analysed or recorded
        touched = {c[2].split("/")[2] for c in gh.inner.calls if c[:2] == ["gh", "api"]}
        assert touched == {"Lib.Eta-for-Rust"}

    def test_unreleased_product_still_files_its_issue_with_qualifier(self, world):
        gh = GhRecorder(world["fx"])
        run(world, "--release-trigger", "famG/rust", "--repo", "owner/tracker", runner=gh)
        assert len(gh.kinds("create")) == 1
        assert "unreleased main: do not present as released" in next(iter(gh.issues.values()))["body"]
        assert cps.read_state("famG", "rust")["release_state"] == "unreleased_main"

    def test_unreleased_api_touched_python_gets_issue(self, world):
        # a non-Java, non-Rust API_TOUCHED product on unreleased main
        write_fixture(world["fx"], "org-famB", "Lib.Beta-for-Python", head=H["b"],
                      pages=[page(["src/pkg/__init__.py", "README.md"])])
        gh = GhRecorder(world["fx"])
        run(world, "--products", "famB/python", *ISSUE_ARGS, runner=gh)
        (issue,) = gh.issues.values()
        assert issue["title"].startswith("FLEET-PROPAGATE-famB-python:")
        assert "API_TOUCHED" in issue["body"]
        assert "unreleased main: do not present as released" in issue["body"] and H["b"] in issue["body"]


class TestRegistryProbe:
    def test_injected_fetch_drives_release_state(self, world):
        from package_registries import FetchResponse
        seen = []

        def fetch(url):
            seen.append(url)
            body = {"info": {"version": "2.0", "author": "a", "project_urls": {"Repository": "x"}},
                    "releases": {"2.0": [{"packagetype": "sdist"}]}}
            return FetchResponse(200, json.dumps(body).encode("utf-8"))

        p = world["out"] / "l.json"
        rc, _ = run(world, "--probe-registry", "--offline", str(world["fx"]), "--json-out", str(p), fetch=fetch)
        # --offline disables probing entirely (no network, ever)
        assert seen == []
        runner = fd.FixtureRunner(world["fx"])
        rc, _ = run(world, "--probe-registry", "--json-out", str(p), runner=runner, fetch=fetch)
        led = json.loads(p.read_text(encoding="utf-8"))
        assert any("pypi.org/pypi/pkg-b/json" in u for u in seen)
        # live version 2.0 == recorded 2.0 -> trusted; head != release sha -> unreleased_main
        assert led["products"]["famB/python"]["release_state"] == "unreleased_main"

    def test_ambiguous_probe_is_unknown(self, world):
        p = world["out"] / "l.json"
        runner = fd.FixtureRunner(world["fx"])
        run(world, "--probe-registry", "--json-out", str(p), runner=runner, fetch=lambda url: None)
        led = json.loads(p.read_text(encoding="utf-8"))
        assert led["products"]["famB/python"]["release_state"] == "unknown"
        assert led["products"]["famB/python"]["release_state_reason"] == "live_probe_ambiguous"


# ── B12 ──────────────────────────────────────────────────────────────────────

class TestBaselineStores:
    def test_per_product_flag_and_fleet_summary(self, world):
        led = ledger(world)
        assert led["products"]["famA/java"]["baseline_stores_disagree"] is True
        assert led["products"]["famB/python"]["baseline_stores_disagree"] is False
        assert led["products"]["famE/net"]["baseline_stores_disagree"] is False  # nothing to compare
        b = led["baseline_stores"]
        assert b["disagree_count"] == 1 and b["disagree_products"] == ["famA/java"]
        assert b["projection_staleness"] is None  # not requested

    def test_projection_check_through_runner(self, world):
        stale = [{"family": "famB", "platform": "python", "projection_sha": "a", "source_sha": "b"},
                 {"family": "famA", "platform": "java", "projection_sha": "c", "source_sha": "d"}]

        class Runner(fd.FixtureRunner):
            def __call__(self, cmd, **kw):
                if "check-staleness" in cmd:
                    assert cmd[-1] == "--json"
                    return subprocess.CompletedProcess(cmd, 1, "WARNING: noise\n" + json.dumps(stale), "")
                return super().__call__(cmd, **kw)

        p = world["out"] / "l.json"
        run(world, "--check-projections", "--json-out", str(p), runner=Runner(world["fx"]))
        ps = json.loads(p.read_text(encoding="utf-8"))["baseline_stores"]["projection_staleness"]
        assert ps["ran"] is True and ps["stale_count"] == 2 and ps["stale"][0]["family"] == "famA"

    def test_projection_check_failure_is_reported_not_fatal(self, world):
        class Runner(fd.FixtureRunner):
            def __call__(self, cmd, **kw):
                if "check-staleness" in cmd:
                    return subprocess.CompletedProcess(cmd, 2, "", "boom")
                return super().__call__(cmd, **kw)

        p = world["out"] / "l.json"
        rc, _ = run(world, "--check-projections", "--json-out", str(p), runner=Runner(world["fx"]))
        ps = json.loads(p.read_text(encoding="utf-8"))["baseline_stores"]["projection_staleness"]
        assert rc == 0 and ps["ran"] is False and "check_staleness_failed" in ps["reason"]

    def test_offline_skips_projection_check(self, world):
        p = world["out"] / "l.json"
        run(world, "--check-projections", "--json-out", str(p))
        assert json.loads(p.read_text(encoding="utf-8"))["baseline_stores"]["projection_staleness"] == \
            {"ran": False, "reason": "skipped_offline"}

    def test_read_only_no_repair(self, world):
        before = (world["root"] / "data" / "upstream_baselines.json").read_bytes()
        run(world, "--check-projections", "--update-state")
        assert (world["root"] / "data" / "upstream_baselines.json").read_bytes() == before


# ── generality + write boundary ──────────────────────────────────────────────

SRC_FILES = [Path(fd.__file__), Path(la.__file__), Path(cps.__file__), la.DEFAULT_CONFIG_PATH]


class TestGenerality:
    def test_no_product_or_family_literals(self):
        banned = re.compile(r"\b(aspose|pdf|cells|slides|barcode|imaging|psd|gis)\b", re.IGNORECASE)
        for path in SRC_FILES:
            hits = [m.group(0) for m in banned.finditer(path.read_text(encoding="utf-8"))]
            assert hits == [], f"{path.name}: product/family literal(s) {hits}"

    def test_language_literals_only_in_config(self):
        # code may mention a language only inside docstrings/comments-free logic: the platform
        # switch lives in the YAML. No `== "java"`-style branching in fleet_drift.
        text = Path(fd.__file__).read_text(encoding="utf-8")
        assert not re.search(r"""[=!]=\s*["'](java|net|python|typescript|go|cpp|rust)["']""", text)

    def test_fleet_drift_never_writes_propagation_fields(self):
        import ast
        tree = ast.parse(Path(fd.__file__).read_text(encoding="utf-8"))
        names = {getattr(n.func, "attr", getattr(n.func, "id", None)) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert "record_propagation" not in names | attrs and "record_drift" in attrs
