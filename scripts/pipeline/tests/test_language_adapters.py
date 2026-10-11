"""B11 (MT074): lib/language_adapters.py -- GT-1 / GT-2 adapters, registry, path classifier.

All process execution goes through a fake runner (no JDK/Maven/network needed). One real
javac/javap test runs ONLY when a JDK and git are discoverable and otherwise skips LOUDLY.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# sys.path is set by tests/conftest.py
import language_adapters as la

NUL = "\0"


class R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def diff_output(*pairs: "tuple[str, str]") -> str:
    return "".join(f"{s}{NUL}{p}{NUL}" for s, p in pairs)


# ── glob + classifier ────────────────────────────────────────────────────────

class TestGlob:
    @pytest.mark.parametrize("pattern,path,expected", [
        ("src/main/**", "src/main/a/B.java", True),
        ("**/src/main/**", "mod/src/main/a/B.java", True),
        ("**/tests/**", "tests/x.py", True),          # **/ matches zero directories
        ("*.go", "a.go", True),
        ("*.go", "pkg/a.go", False),                   # * does not cross "/"
        ("**/*.go", "pkg/deep/a.go", True),
        ("**/_[!_]*.py", "pkg/_private.py", True),
        ("**/_[!_]*.py", "pkg/__init__.py", False),
        ("*/__init__.py", "pkg/__init__.py", True),
        ("SRC/**", "src/a.rs", False),                 # case-SENSITIVE by default
        ("a?c", "abc", True),
        ("a?c", "a/c", False),
    ])
    def test_glob(self, pattern, path, expected):
        assert la.glob_match(pattern, path) is expected

    def test_ignore_case_is_opt_in(self):
        assert la.glob_match("SRC/**", "src/a.rs", ignore_case=True) is True
        assert la.glob_match("src/**", "SRC/a.rs") is False


NAMES_INSIDE_SOURCE_TREES = [
    # (platform, path inside a SOURCE tree whose directory is called build/docs/test/bin ...)
    ("java", "src/main/java/org/acme/build/BuildInfo.java"),
    ("java", "src/main/java/org/acme/test/Probe.java"),
    ("net", "src/Acme.Core/Docs/DocsApi.cs"),
    ("net", "src/Acme.Core/bin/Binary.cs"),
    ("python", "pkg/sub/mod.py"),
    ("python", "pkg/build/mod.py"),
    ("typescript", "src/docs/index.ts"),
    ("typescript", "src/build/compile.ts"),
    ("go", "pkg/build/builder.go"),
    ("go", "docs.go"),
    ("rust", "src/build/mod.rs"),
    ("cpp", "include/acme/test/probe.h"),
]


class TestAnchoredNonSourcePatterns:
    @pytest.mark.parametrize("platform,path", NAMES_INSIDE_SOURCE_TREES)
    def test_directory_names_inside_source_trees_do_not_demote_source(self, platform, path):
        r = la.classify_paths(platform, [path])
        assert r["source_files"] == [path], (platform, path)
        assert r["api_files"] == [path], (platform, path)

    @pytest.mark.parametrize("platform,path", [
        ("java", "build/generated/Gen.java"),
        ("java", "docs/Example.java"),
        ("java", "examples/Demo.java"),
        ("java", "module-b/src/test/java/p/ThingTest.java"),
        ("net", "tests/Acme.Core.Tests/CoreTests.cs"),
        ("net", "src/Acme.Core.Tests/CoreTests.cs"),
        ("python", "tests/test_a.py"),
        ("python", "docs/conf.py"),
        ("python", "scripts/release.py"),
        ("typescript", "test/a.ts"),
        ("typescript", "examples/demo.ts"),
        ("go", "a_test.go"),
        ("go", "pkg/testdata/fixture.go"),
        ("rust", "samples/s.rs"),
        ("cpp", "tests/t.cpp"),
    ])
    def test_real_top_level_non_source_still_non_source(self, platform, path):
        r = la.classify_paths(platform, [path])
        assert r["source_files"] == [] and r["api_files"] == [], (platform, path)

    def test_flat_python_layout_counts_as_api_but_private_modules_do_not(self):
        r = la.classify_paths("python", ["pkg/sub/mod.py", "pkg/__init__.py", "pkg/_private.py", "pkg/_pkg/x.py", "setup.py"])
        assert r["api_files"] == ["pkg/__init__.py", "pkg/sub/mod.py"]

    def test_case_sensitivity_is_configurable(self):
        cfg = la.load_language_config()
        loose = {**cfg, "common": {**cfg["common"], "case_sensitive": False}}
        assert la.classify_paths("net", ["Docs/Api.cs"], config=cfg)["source_files"] == ["Docs/Api.cs"]
        assert la.classify_paths("net", ["Docs/Api.cs"], config=loose)["source_files"] == []


class TestClassifyPaths:
    def test_java(self):
        r = la.classify_paths("java", [
            "src/main/java/p/Api.java", "src/main/java/p/internal/Hidden.java",
            "src/test/java/p/ApiTest.java", "README.md", "pom.xml",
        ])
        assert r["known_platform"] is True
        assert r["api_files"] == ["src/main/java/p/Api.java"]
        assert "src/main/java/p/internal/Hidden.java" in r["source_files"]
        assert "src/test/java/p/ApiTest.java" not in r["source_files"]

    def test_python(self):
        r = la.classify_paths("python", [
            "src/pkg/__init__.py", "src/pkg/_impl.py", "src/pkg/public.py", "tests/test_a.py", "setup.py",
        ])
        assert r["api_files"] == ["src/pkg/__init__.py", "src/pkg/public.py"]
        assert r["source_files"] == ["src/pkg/__init__.py", "src/pkg/_impl.py", "src/pkg/public.py"]

    def test_typescript(self):
        r = la.classify_paths("typescript", ["src/index.ts", "src/a.test.ts", "test/b.ts", "vitest.config.ts"])
        assert r["api_files"] == ["src/index.ts"]
        assert r["source_files"] == ["src/index.ts"]

    def test_go_root_and_tests(self):
        r = la.classify_paths("go", ["doc.go", "a_test.go", "internal/x.go", "_examples/e.go", "pkg/b.go"])
        assert r["api_files"] == ["doc.go", "pkg/b.go"]

    def test_cpp_and_rust(self):
        c = la.classify_paths("cpp", ["include/x/y.h", "include/internal/z.h", "src/internal/q.cpp", "tests/t.cpp"])
        assert c["api_files"] == ["include/x/y.h"]
        r = la.classify_paths("rust", ["src/lib.rs", "src/bin/main.rs", "samples/s.rs"])
        assert r["api_files"] == ["src/lib.rs"]

    def test_unknown_platform_is_unknown_safe(self):
        r = la.classify_paths("zig", ["src/a.go", "docs/x.md"])
        assert r["known_platform"] is False
        assert r["unknown_reason"] == "platform_not_in_language_api_paths"
        assert r["api_files"] == []          # never guesses an API verdict
        assert r["source_files"] == ["src/a.go"]

    def test_config_has_no_product_or_family_names(self):
        text = la.DEFAULT_CONFIG_PATH.read_text(encoding="utf-8").lower()
        for banned in ("aspose", "pdf", "cells", "words", "slides", "barcode", "imaging", "email"):
            assert banned not in text


# ── registry / honesty of the tier ───────────────────────────────────────────

class TestRegistry:
    def test_java_is_gt1_everything_else_gt2(self):
        assert la.adapter_for("java").ground_truth_tier == "GT-1"
        for platform in ("python", "typescript", "go", "cpp", "rust", "net", "zig"):
            a = la.adapter_for(platform)
            assert a.ground_truth_tier == "GT-2", platform
            assert a.platform == platform
            assert isinstance(a, la.GenericFileAdapter)

    def test_tier_is_explicit_on_every_adapter(self):
        for cls in (la.LanguageAdapter, la.GenericFileAdapter, la.JavaGT1Adapter):
            assert cls.ground_truth_tier in ("GT-1", "GT-2")
        assert la.ground_truth_tier_for("java") == "GT-1" and la.ground_truth_tier_for("python") == "GT-2"

    def test_base_contract_not_implemented(self):
        with pytest.raises(NotImplementedError):
            la.LanguageAdapter().api_delta("a", "b", repo_path=".", runner=None)
        with pytest.raises(NotImplementedError):
            la.LanguageAdapter().build_artifact("a", repo_path=".", runner=None)


# ── generic GT-2 ─────────────────────────────────────────────────────────────

OLD, NEW = "a" * 40, "b" * 40


class TestRefValidation:
    @pytest.mark.parametrize("ref", ["--output=/tmp/x", "-p", "a b", "main; rm -rf /", "", "abc", "refs/../x", "refs/heads/-x",
                                     "x" * 40, "--upload-pack=evil"])
    def test_hostile_or_ambiguous_refs_rejected_before_git_runs(self, ref):
        calls = []
        with pytest.raises(la.AdapterError, match="ref"):
            la.adapter_for("python").api_delta(ref, NEW, repo_path="/r", runner=lambda c, **k: calls.append(c) or R())
        with pytest.raises(la.AdapterError, match="ref"):
            la.adapter_for("python").api_delta(OLD, ref, repo_path="/r", runner=lambda c, **k: calls.append(c) or R())
        assert calls == []

    @pytest.mark.parametrize("ref", [OLD, "abcdef1", "A" * 40, "refs/heads/main", "refs/tags/v1.2.3", "refs/remotes/origin/feature-x"])
    def test_hex_and_refs_names_accepted(self, ref):
        assert la.adapter_for("python").api_delta(ref, NEW, repo_path="/r", runner=lambda c, **k: R())["changed_files"] == []

    def test_paths_are_separated_from_revisions(self):
        calls = []
        la.adapter_for("go").api_delta(OLD, NEW, repo_path="/r", runner=lambda c, **k: calls.append(c) or R())
        assert calls[0][-3:] == [OLD, NEW, "--"] or calls[0][-1] == "--"
        assert calls[0].index("--") > calls[0].index(NEW)

    def test_java_checkout_validates_refs_too(self, tmp_path):
        jdk, mvn = _make_tools(tmp_path)
        adapter = la.JavaGT1Adapter(env={"JAVA_HOME": str(jdk), "MAVEN_HOME": str(mvn)}, which=lambda *a, **k: None,
                                    jdk_search_roots=[], maven_search_roots=[])
        calls = []
        with pytest.raises(la.AdapterError, match="ref"):
            adapter.api_delta("--evil", NEW, repo_path="r", runner=lambda c, **k: calls.append(c) or R())
        assert calls == []


class TestGenericAdapter:
    def _run(self, platform, pairs):
        calls = []

        def runner(cmd, **kw):
            calls.append(cmd)
            return R(out=diff_output(*pairs))

        res = la.adapter_for(platform).api_delta(OLD, NEW, repo_path="/repo", runner=runner)
        return res, calls

    def test_python_file_level(self):
        res, calls = self._run("python", [
            ("M", "src/pkg/api.py"), ("A", "src/pkg/new_mod.py"), ("D", "src/pkg/old.py"),
            ("M", "CHANGELOG.md"), ("M", "README.md"), ("M", "docs/guide.md"), ("M", "tests/test_x.py"),
        ])
        assert calls[0][:4] == ["git", "-C", "/repo", "diff"]
        assert res["ground_truth_tier"] == "GT-2" and res["compiled_api_truth"] is False
        assert "added_types" not in res and "removed_types" not in res  # never claims compiled-API truth
        assert res["added_source_files"] == ["src/pkg/new_mod.py"]
        assert res["removed_source_files"] == ["src/pkg/old.py"]
        assert res["modified_source_files"] == ["src/pkg/api.py"]
        assert res["api_surface_touched"] is True
        assert res["changelog_files"] == ["CHANGELOG.md"]
        assert res["readme_files"] == ["README.md"]
        assert "docs/guide.md" in res["docs_files"]
        assert res["test_files"] == ["tests/test_x.py"]

    def test_typescript_non_api_change(self):
        res, _ = self._run("typescript", [("M", "src/a.test.ts"), ("M", "package.json")])
        assert res["api_surface_touched"] is False and res["source_files"] == []

    def test_go_and_unknown(self):
        res, _ = self._run("go", [("M", "client.go"), ("M", "client_test.go")])
        assert res["api_path_files"] == ["client.go"]
        res, _ = self._run("zig", [("M", "src/x.zig")])
        assert res["known_platform"] is False and res["api_surface_touched"] is None
        assert any("not in language_api_paths" in n for n in res["notes"])

    def test_git_failure_raises(self):
        with pytest.raises(la.AdapterError):
            la.adapter_for("python").api_delta(OLD, NEW, repo_path="/r", runner=lambda c, **k: R(128, "", "bad object"))

    def test_deterministic(self):
        pairs = [("M", "src/b.py"), ("M", "src/a.py")]
        assert self._run("python", pairs)[0] == self._run("python", list(reversed(pairs)))[0]

    def test_build_artifact_declines_honestly(self):
        res = la.adapter_for("python").build_artifact("sha", repo_path="/r", runner=None)
        assert res["built"] is False and res["ground_truth_tier"] == "GT-2"


# ── tool discovery ───────────────────────────────────────────────────────────

def _make_tools(tmp_path: Path):
    jdk = tmp_path / "jdk" / "bin"
    mvn = tmp_path / "mvnhome" / "bin"
    jdk.mkdir(parents=True, exist_ok=True)
    mvn.mkdir(parents=True, exist_ok=True)
    for n in ("javap", "jar"):
        (jdk / n).write_text("", encoding="utf-8")
    (mvn / "mvn").write_text("", encoding="utf-8")
    return tmp_path / "jdk", tmp_path / "mvnhome"


class TestToolDiscovery:
    def test_home_vars_then_path_then_roots(self, tmp_path):
        jdk, mvn = _make_tools(tmp_path)
        none = lambda *a, **k: None  # noqa: E731
        env = {"JAVA_HOME": str(jdk), "MAVEN_HOME": str(mvn)}
        a = la.JavaGT1Adapter(env=env, which=none, jdk_search_roots=[], maven_search_roots=[])
        tools = a.discover_tools()
        assert Path(tools["javap"]).parent == jdk / "bin" and Path(tools["mvn"]).parent == mvn / "bin"
        # no env, but a configured search root (newest child first)
        root = tmp_path / "roots"
        (root / "jdk-11" / "bin").mkdir(parents=True)
        (root / "jdk-17" / "bin").mkdir(parents=True)
        for v in ("jdk-11", "jdk-17"):
            for n in ("javap", "jar"):
                (root / v / "bin" / n).write_text("", encoding="utf-8")
        b = la.JavaGT1Adapter(env={}, which=none, jdk_search_roots=[str(root)], maven_search_roots=[str(mvn)])
        assert "jdk-17" in b.discover_tools(need_maven=False)["javap"]

    def test_path_lookup_uses_injected_which(self, tmp_path):
        seen = []

        def which(name, *a, **k):
            seen.append(name)
            return f"/fake/{name}"

        a = la.JavaGT1Adapter(env={}, which=which, jdk_search_roots=[], maven_search_roots=[])
        tools = a.discover_tools()
        assert tools["javap"] == "/fake/javap" and tools["mvn"] == "/fake/mvn"

    def test_missing_tools_raise_unavailable(self):
        a = la.JavaGT1Adapter(env={}, which=lambda *a, **k: None, jdk_search_roots=[], maven_search_roots=[])
        with pytest.raises(la.AdapterUnavailable) as ei:
            a.discover_tools()
        assert "javap" in str(ei.value) and "mvn" in str(ei.value)


# ── javap parsing + Java GT-1 with a fake runner ─────────────────────────────

OLD_API = {
    "pkg.Doc": ["public pkg.Doc();", "public void save(java.lang.String);"],
    "pkg.Gone": ["public void x();"],
    "pkg.Color": ["public static final pkg.Color RED;", "public static pkg.Color[] values();"],
}
NEW_API = {
    "pkg.Doc": ["public pkg.Doc();", "public void save(java.lang.String);", "public void save(java.io.File);"],
    "pkg.Color": ["public static final pkg.Color RED;", "public static final pkg.Color BLUE;",
                  "public static pkg.Color[] values();"],
    "pkg.Fresh": ["public pkg.Fresh();", "public int size();"],
}


def javap_text(api: dict) -> str:
    out = []
    for t, members in sorted(api.items()):
        if t.endswith("Color"):
            out.append(f'Compiled from "X.java"\npublic final class {t} extends java.lang.Enum<{t}> {{')
        else:
            out.append(f'Compiled from "X.java"\npublic class {t} {{')
        out += [f"  {m}" for m in members]
        out.append("}")
    out.append('Compiled from "Hidden.java"\nclass pkg.Hidden {\n  void pkgPrivate();\n}')
    return "\n".join(out) + "\n"


class FakeJavaRunner:
    """Pretends to be git + mvn + jar + javap. Creates real marker files so the adapter's own
    filesystem logic (jar picking) runs for real."""

    def __init__(self, apis: "dict[str, dict]", *, fail_build_for: "str | None" = None):
        self.apis, self.calls, self.fail_build_for = apis, [], fail_build_for
        self.checkouts: "list[Path]" = []

    def __call__(self, cmd, *, cwd=None, timeout=None, env=None):
        self.calls.append(list(cmd))
        exe = Path(cmd[0]).name
        if cmd[0] == "git" and cmd[1] == "clone":
            dest = Path(cmd[-1])
            dest.mkdir(parents=True)
            self.checkouts.append(dest)
            return R()
        if cmd[0] == "git" and "checkout" in cmd:
            (Path(cmd[2]) / "REF").write_text(cmd[-1], encoding="utf-8")
            return R()
        if exe == "mvn":
            ref = (Path(cwd) / "REF").read_text(encoding="utf-8")
            if ref == self.fail_build_for:
                return R(1, "", "[ERROR] COMPILATION ERROR")
            (Path(cwd) / "target").mkdir()
            (Path(cwd) / "target" / "lib-1.0.jar").write_text(ref, encoding="utf-8")
            (Path(cwd) / "target" / "lib-1.0-sources.jar").write_text(ref + "-sources-is-bigger-than-main", encoding="utf-8")
            return R()
        if exe == "jar":
            ref = Path(cmd[-1]).parent.parent.joinpath("REF").read_text(encoding="utf-8")
            names = [t.replace(".", "/") + ".class" for t in self.apis[ref]]
            return R(out="\n".join(["META-INF/MANIFEST.MF", "module-info.class", "pkg/package-info.class",
                                    "pkg/Hidden.class", *names]) + "\n")
        if exe == "javap":
            jar = Path(cmd[cmd.index("-cp") + 1])
            ref = jar.parent.parent.joinpath("REF").read_text(encoding="utf-8")
            wanted = set(cmd[cmd.index("-cp") + 2:])
            api = {t: m for t, m in self.apis[ref].items() if t in wanted}
            return R(out=javap_text(api))
        raise AssertionError(f"unexpected command {cmd}")


def _java_adapter(tmp_path, **kw):
    jdk, mvn = _make_tools(tmp_path)
    return la.JavaGT1Adapter(env={"JAVA_HOME": str(jdk), "MAVEN_HOME": str(mvn)},
                             which=lambda *a, **k: None, jdk_search_roots=[], maven_search_roots=[], **kw)


class TestParseJavap:
    def test_ignores_package_private_and_collects_enum_constants(self):
        parsed = la.parse_javap(javap_text(NEW_API))
        assert "pkg.Hidden" not in parsed
        assert parsed["pkg.Color"]["is_enum"] is True
        assert parsed["pkg.Color"]["constants"] == {"RED", "BLUE"}
        assert parsed["pkg.Doc"]["is_enum"] is False

    def test_generic_and_interface_headers(self):
        text = "public interface pkg.Visitor<T> {\n  public abstract T visit(pkg.Node);\n}\n"
        assert list(la.parse_javap(text)) == ["pkg.Visitor"]


class TestJavaAdapter:
    def test_api_delta(self, tmp_path):
        runner = FakeJavaRunner({OLD: OLD_API, NEW: NEW_API})
        res = _java_adapter(tmp_path).api_delta(OLD, NEW, repo_path=tmp_path / "repo", runner=runner)
        assert res["ground_truth_tier"] == "GT-1" and res["compiled_api_truth"] is True
        assert [t["type"] for t in res["added_types"]] == ["pkg.Fresh"]
        assert res["removed_types"] == ["pkg.Gone"]
        assert res["changed_types"]["pkg.Doc"]["added"] == ["public void save(java.io.File);"]
        assert res["changed_types"]["pkg.Color"]["enum_constants_added"] == ["BLUE"]
        assert res["summary"] == {"added_types": 1, "removed_types": 1, "changed_types": 2, "enum_constants_added": 1}
        # clones were made from the repo, never touching it; temp copies cleaned up
        assert all(not c.exists() for c in runner.checkouts)
        # the sources jar (bigger, but excluded) was not the one inspected
        javap_jars = [Path(c[c.index("-cp") + 1]).name for c in runner.calls if Path(c[0]).name == "javap"]
        assert set(javap_jars) == {"lib-1.0.jar"}
        # machine-specific values live only under `volatile`
        assert "tools" in res["volatile"]
        assert str(tmp_path) not in repr({k: v for k, v in res.items() if k != "volatile"})

    def test_identical_refs_yield_empty_delta_and_result_is_deterministic(self, tmp_path):
        a = _java_adapter(tmp_path).api_delta(OLD, OLD, repo_path="r", runner=FakeJavaRunner({OLD: OLD_API}))
        assert a["added_types"] == [] and a["removed_types"] == [] and a["changed_types"] == {}
        one = _java_adapter(tmp_path).api_delta(OLD, NEW, repo_path="r", runner=FakeJavaRunner({OLD: OLD_API, NEW: NEW_API}))
        two = _java_adapter(tmp_path).api_delta(OLD, NEW, repo_path="r", runner=FakeJavaRunner({OLD: OLD_API, NEW: NEW_API}))
        one.pop("volatile"); two.pop("volatile")
        assert one == two

    def test_javap_chunking(self, tmp_path):
        runner = FakeJavaRunner({OLD: OLD_API, NEW: NEW_API})
        _java_adapter(tmp_path, javap_chunk=1).api_delta(OLD, NEW, repo_path="r", runner=runner)
        javap_calls = [c for c in runner.calls if Path(c[0]).name == "javap"]
        assert all(len(c[c.index("-cp") + 2:]) == 1 for c in javap_calls) and len(javap_calls) >= 6

    def test_build_failure_raises_and_cleans_up(self, tmp_path):
        runner = FakeJavaRunner({OLD: OLD_API, NEW: NEW_API}, fail_build_for=NEW)
        with pytest.raises(la.AdapterError, match=f"maven build failed at {NEW}"):
            _java_adapter(tmp_path).api_delta(OLD, NEW, repo_path="r", runner=runner)
        assert all(not c.exists() for c in runner.checkouts)

    def test_fallback_to_gt2_is_explicit(self, tmp_path):
        calls = []

        def runner(cmd, **kw):
            calls.append(cmd)
            return R(out=diff_output(("M", "src/main/java/p/Api.java")))

        res = la.api_delta_with_fallback(
            "java", OLD, NEW, repo_path="r", runner=runner,
            env={}, which=lambda *x, **k: None, jdk_search_roots=[], maven_search_roots=[])
        assert res["ground_truth_tier"] == "GT-2"          # the tier actually achieved
        assert res["fallback_from"] == "GT-1" and "missing tool" in res["fallback_reason"]
        assert res["compiled_api_truth"] is False
        assert res["api_surface_touched"] is True

    def test_fallback_wrapper_gt2_platform_errors_propagate(self):
        with pytest.raises(la.AdapterError):
            la.api_delta_with_fallback("python", OLD, NEW, repo_path="r", runner=lambda c, **k: R(1, "", "boom"))

    def test_default_runner_never_raises_for_missing_tool(self):
        r = la.default_runner(["definitely-not-a-real-binary-xyz", "--v"])
        assert r.returncode == 127 and "cannot run" in r.stderr


# ── real javac/javap (skips loudly when the environment cannot run it) ───────

def _real_toolchain():
    env = dict(os.environ)
    ad = la.JavaGT1Adapter(env=env)
    try:
        tools = ad.discover_tools(need_maven=False)
    except la.AdapterUnavailable as exc:
        pytest.skip(f"REAL-JDK TEST NOT RUN: {exc}")
    javac = la.find_tool("javac", env=env, home_vars=("JAVA_HOME",), search_roots=ad._jdk_roots)
    if not javac:
        pytest.skip("REAL-JDK TEST NOT RUN: javac not discoverable")
    if not shutil.which("git"):
        pytest.skip("REAL-JDK TEST NOT RUN: git not on PATH")
    return ad, tools, javac


def _git(repo: Path, *args: str):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.test", "-c", "user.name=t", *args],
                   check=True, capture_output=True, text=True, encoding="utf-8")


def test_real_javac_javap_roundtrip(tmp_path):
    _ad, _tools, javac = _real_toolchain()
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "src" / "Tiny.java").write_text(
        "package demo;\npublic class Tiny { public int one() { return 1; } }\n"
        "enum Hidden { A }\n", encoding="utf-8")
    (repo / "src" / "Mode.java").write_text("package demo;\npublic enum Mode { FAST }\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "one")
    old = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
    (repo / "src" / "Tiny.java").write_text(
        "package demo;\npublic class Tiny { public int one() { return 1; } public int two() { return 2; } }\n",
        encoding="utf-8")
    (repo / "src" / "Mode.java").write_text("package demo;\npublic enum Mode { FAST, SLOW }\n", encoding="utf-8")
    (repo / "src" / "Extra.java").write_text("package demo;\npublic class Extra { }\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "two")
    new = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()

    def builder(checkout: Path, runner, tools):
        out = checkout / "target" / "classes"
        out.mkdir(parents=True)
        sources = sorted(str(p) for p in (checkout / "src").glob("*.java"))
        r = runner([javac, "-d", str(out), *sources])
        assert r.returncode == 0, r.stderr
        jar = checkout / "target" / "tiny.jar"
        r = runner([tools["jar"], "cf", str(jar), "-C", str(out), "."])
        assert r.returncode == 0, r.stderr
        return jar

    adapter = la.JavaGT1Adapter(env=dict(os.environ), builder=builder)
    res = adapter.api_delta(old, new, repo_path=repo, runner=la.default_runner)
    assert res["ground_truth_tier"] == "GT-1"
    assert [t["type"] for t in res["added_types"]] == ["demo.Extra"]
    assert res["removed_types"] == []
    assert any("two()" in m for m in res["changed_types"]["demo.Tiny"]["added"])
    assert res["changed_types"]["demo.Mode"]["enum_constants_added"] == ["SLOW"]
