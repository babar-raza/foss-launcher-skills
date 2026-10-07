"""MT074 B6 (R8): Java Example Verifier product-artifact acquisition.

Covers
  - toolchain.py bounded discovery (PATH -> JAVA_HOME/MAVEN_HOME -> ordered
    roots incl. ASPOSE_TOOLCHAIN_ROOTS): synthetic fake JDK/Maven homes, so
    these run on any machine
  - JavaRunner(product_jar=...) / JavaRunner(product_build=...): tier-2
    compile and tier-3 run against a tiny SYNTHETIC product ("gadget"),
    compiled and jar'd with the discovered javac/jar inside a tmp dir
  - fixture prelude, missing-fixture disclosure (FIXTURE-UNAVAILABLE, tier 2)
  - explicit BLOCKED_TOOLCHAIN outcome (never PASS) with an injected empty
    toolchain
  - clone-cache untouched / temp build never under the clone path
  - base.py additions (registered acquire-failure reason pass-through,
    result_meta -> BlockResult, proof_tier override), proven with a
    NON-Java toy runner

Real-JDK tests are SKIPPED with a loud reason when no JDK/jar tool is
discoverable -- they never pass silently.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from lib.example_verification import toolchain as tc_mod
from lib.example_verification.policy import Policy, ProductContext
from lib.example_verification.runners.base import BaseRunner
from lib.example_verification.runners.java import (
    EMPTY_TOOLCHAIN,
    FixtureSpec,
    JavaRunner,
    ProductBuild,
    _missing_input,
    _safe_fixture_path,
)

_REAL = tc_mod.discover_java_toolchain()
_HAVE_JDK = _REAL.jdk is not None and _REAL.jdk.jar is not None
needs_jdk = pytest.mark.skipif(
    not _HAVE_JDK,
    reason=("NO JDK (>= 11) WITH A `jar` TOOL DISCOVERABLE via PATH / JAVA_HOME / roots "
            f"{list(_REAL.searched_roots)} -- real-JDK product-jar tests are SKIPPED, not "
            "passed; install a JDK or set ASPOSE_TOOLCHAIN_ROOTS"),
)

GREETER = (
    "package gadget;\n"
    "public class Greeter {\n"
    "    public static String hello(String n) { return \"hi \" + n; }\n"
    "    public static String readAll(String f) throws java.io.IOException {\n"
    "        return new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(f)));\n"
    "    }\n"
    "}\n"
)
GREETER_V2 = GREETER.replace('"hi "', '"bye "')

POLICY = Policy(max_tier=3, allow_acquire=True)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_jar(src_dir: Path, out_jar: Path, tc: "tc_mod.JavaToolchain | None" = None) -> Path:
    """Compile every .java under src_dir and jar the classes with the
    discovered JDK's own tools (no Maven, no network)."""
    jdk = (tc or _REAL).jdk
    classes = src_dir.parent / (src_dir.name + "-classes")
    classes.mkdir(parents=True, exist_ok=True)
    sources = [str(p) for p in sorted(src_dir.rglob("*.java"))]
    subprocess.run([jdk.javac, "-d", str(classes), *sources], check=True,
                   capture_output=True, text=True, encoding="utf-8")
    subprocess.run([jdk.jar, "cf", str(out_jar), "-C", str(classes), "."], check=True,
                   capture_output=True, text=True, encoding="utf-8")
    return out_jar


@pytest.fixture
def gadget_jar(tmp_path) -> Path:
    src = tmp_path / "gadget-src" / "gadget"
    src.mkdir(parents=True)
    (src / "Greeter.java").write_text(GREETER, encoding="utf-8")
    return _build_jar(tmp_path / "gadget-src", tmp_path / "gadget.jar")


def _run(runner: JavaRunner, *codes: str):
    blocks = [(f"sha-{i}", (i + 1, i + 1), c) for i, c in enumerate(codes)]
    return BaseRunner(runner).run(blocks, POLICY, ProductContext())


def _tree_hash(root: Path) -> str:
    """Hash of EVERYTHING under root (relative path, size, mtime, content),
    .git included -- any write under the clone changes it."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file():
            st = p.stat()
            h.update(f"{rel}|{st.st_size}|{st.st_mtime_ns}|".encode())
            h.update(p.read_bytes())
        else:
            h.update(f"{rel}/".encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Discovery (synthetic homes -- machine independent)
# ---------------------------------------------------------------------------

def _fake_jdk(root: Path, dirname: str, java_version: str) -> Path:
    home = root / dirname
    (home / "bin").mkdir(parents=True)
    for tool in ("java", "javac", "jar"):
        (home / "bin" / tc_mod._exe(tool)).write_bytes(b"")
    (home / "release").write_text(f'JAVA_VERSION="{java_version}"\n', encoding="utf-8")
    return home


def _fake_maven(root: Path, dirname: str) -> Path:
    home = root / dirname
    (home / "bin").mkdir(parents=True)
    (home / "bin" / tc_mod._mvn_name()).write_bytes(b"")
    return home


def _none(_name: str):
    return None


class TestJdkDiscovery:
    def test_newest_lts_is_chosen_over_newer_non_lts_and_old_jdks(self, tmp_path):
        root = tmp_path / "jdks"
        _fake_jdk(root, "jdk-8.0.292", "1.8.0_292")
        _fake_jdk(root, "jdk-11.0.2", "11.0.2")
        _fake_jdk(root, "jdk-17.0.19", "17.0.19")
        _fake_jdk(root, "jdk-21.0.11", "21.0.11")
        _fake_jdk(root, "jdk-22.0.1", "22.0.1")  # newer but NOT an LTS
        jdk = tc_mod.discover_jdk(env={}, roots=[root], which=_none)
        assert jdk is not None
        assert jdk.version == "21.0.11" and jdk.major == 21
        assert jdk.source == f"root:{root}"
        assert jdk.jar is not None

    def test_jdk_below_11_is_never_accepted(self, tmp_path):
        root = tmp_path / "jdks"
        _fake_jdk(root, "jdk-8", "1.8.0_292")
        assert tc_mod.discover_jdk(env={}, roots=[root], which=_none) is None

    def test_non_lts_is_used_only_when_the_root_has_no_lts(self, tmp_path):
        root = tmp_path / "jdks"
        _fake_jdk(root, "jdk-22.0.1", "22.0.1")
        jdk = tc_mod.discover_jdk(env={}, roots=[root], which=_none)
        assert jdk is not None and jdk.major == 22

    def test_version_falls_back_to_the_directory_name_without_a_release_file(self, tmp_path):
        root = tmp_path / "jdks"
        home = _fake_jdk(root, "jdk-17.0.5-hotspot", "ignored")
        (home / "release").unlink()
        jdk = tc_mod.discover_jdk(env={}, roots=[root], which=_none)
        assert jdk is not None and jdk.version == "17.0.5"

    def test_earlier_root_takes_precedence_over_a_newer_jdk_in_a_later_root(self, tmp_path):
        first, second = tmp_path / "a", tmp_path / "b"
        _fake_jdk(first, "jdk-17.0.1", "17.0.1")
        _fake_jdk(second, "jdk-21.0.1", "21.0.1")
        jdk = tc_mod.discover_jdk(env={}, roots=[first, second], which=_none)
        assert jdk.major == 17 and jdk.source == f"root:{first}"

    def test_env_var_roots_come_before_the_defaults(self, tmp_path):
        env = {tc_mod.ENV_ROOTS_VAR: os.pathsep.join([str(tmp_path / "x"), str(tmp_path / "y")])}
        roots = tc_mod.search_roots(env)
        assert roots[:2] == [tmp_path / "x", tmp_path / "y"]
        assert roots[2:] == [r for r in tc_mod.default_search_roots()
                             if r not in (tmp_path / "x", tmp_path / "y")]

    def test_search_roots_deduplicates(self, tmp_path):
        d = tc_mod.default_search_roots()[0]
        env = {tc_mod.ENV_ROOTS_VAR: str(d)}
        assert tc_mod.search_roots(env).count(d) == 1

    def test_java_home_beats_roots_and_records_its_source(self, tmp_path):
        home = _fake_jdk(tmp_path / "elsewhere", "jdk-17.0.1", "17.0.1")
        root = tmp_path / "jdks"
        _fake_jdk(root, "jdk-21.0.1", "21.0.1")
        jdk = tc_mod.discover_jdk(env={"JAVA_HOME": str(home)}, roots=[root], which=_none)
        assert jdk.source == "env:JAVA_HOME" and jdk.major == 17

    def test_path_javac_beats_everything_unchanged_legacy_semantics(self, tmp_path):
        on_path = _fake_jdk(tmp_path / "pathjdk", "jdk-17.0.1", "17.0.1")
        root = tmp_path / "jdks"
        _fake_jdk(root, "jdk-21.0.1", "21.0.1")
        jdk = tc_mod.discover_jdk(
            env={}, roots=[root],
            which=lambda n: str(on_path / "bin" / tc_mod._exe("javac")) if n == "javac" else None)
        assert jdk.source == "path" and jdk.major == 17

    def test_a_root_is_bounded_to_its_first_200_sorted_children(self, tmp_path):
        root = tmp_path / "jdks"
        root.mkdir()
        for i in range(tc_mod._MAX_ROOT_CHILDREN):
            (root / f"a{i:04d}").mkdir()
        _fake_jdk(root, "zzz-jdk-17.0.1", "17.0.1")  # sorts after the 200th child
        assert tc_mod.discover_jdk(env={}, roots=[root], which=_none) is None

    def test_nothing_discoverable_returns_none_never_raises(self, tmp_path):
        assert tc_mod.discover_jdk(env={}, roots=[tmp_path / "missing"], which=_none) is None
        tc = tc_mod.discover_java_toolchain(env={}, roots=[tmp_path / "missing"], which=_none)
        assert tc.jdk is None and tc.maven is None
        assert tc.describe()["jdk_source"] == "none"


class TestMavenDiscovery:
    def test_newest_maven_in_a_root_with_version_and_source(self, tmp_path):
        root = tmp_path / "tools"
        _fake_maven(root, "apache-maven-3.8.8")
        _fake_maven(root, "apache-maven-3.9.16")
        (root / "unrelated").mkdir(parents=True)
        mvn = tc_mod.discover_maven(env={}, roots=[root], which=_none)
        assert mvn.version == "3.9.16" and mvn.source == f"root:{root}"

    def test_maven_home_then_m2_home_before_roots(self, tmp_path):
        a = _fake_maven(tmp_path / "x", "apache-maven-3.6.3")
        b = _fake_maven(tmp_path / "y", "apache-maven-3.8.8")
        root = tmp_path / "tools"
        _fake_maven(root, "apache-maven-3.9.16")
        both = tc_mod.discover_maven(env={"MAVEN_HOME": str(a), "M2_HOME": str(b)},
                                     roots=[root], which=_none)
        assert both.source == "env:MAVEN_HOME" and both.version == "3.6.3"
        only_m2 = tc_mod.discover_maven(env={"M2_HOME": str(b)}, roots=[root], which=_none)
        assert only_m2.source == "env:M2_HOME"

    def test_path_mvn_wins(self, tmp_path):
        home = _fake_maven(tmp_path / "p", "apache-maven-3.5.0")
        mvn = tc_mod.discover_maven(
            env={}, roots=[], which=lambda n: str(home / "bin" / tc_mod._mvn_name()) if n == "mvn" else None)
        assert mvn.source == "path" and mvn.version == "3.5.0"


class TestFindStaysPathFirstAndNonJvmUntouched:
    """Non-Java fixtures: `find()` keeps its PATH-only behaviour for every
    tool that is not part of the JVM toolchain."""

    def test_unknown_tool_is_none_and_source_none(self):
        assert tc_mod.find_with_source("definitely-not-a-real-tool-xyz123") == (None, "none")

    @pytest.mark.parametrize("tool", ["definitely-not-go-xyz", "definitely-not-dotnet-xyz"])
    def test_non_jvm_tools_never_consult_the_jvm_roots(self, tool):
        assert tc_mod.find(tool) is None
        assert tool not in tc_mod._JVM_TOOLS

    def test_path_resident_python_is_found_with_source_path(self):
        import shutil
        if shutil.which("git") is None:
            pytest.skip("git not on PATH (loud skip: cannot exercise a PATH-resident tool)")
        path, source = tc_mod.find_with_source("git")
        assert path is not None and source == "path"


# ---------------------------------------------------------------------------
# Explicit BLOCKED_TOOLCHAIN outcome (machine independent)
# ---------------------------------------------------------------------------

class TestBlockedToolchain:
    def test_no_jdk_is_blocked_never_a_pass_end_to_end(self):
        runner = JavaRunner("synthetic", toolchain=EMPTY_TOOLCHAIN)
        (result,) = _run(runner, 'System.out.println("never runs");')
        assert result.status == "BLOCKED-WITH-REASON"
        assert result.reason == "TOOLCHAIN-UNAVAILABLE"
        assert result.detail.startswith("BLOCKED_TOOLCHAIN:")
        assert result.proof_tier == 0
        assert result.artifact["toolchain"]["jdk_source"] == "none"

    def test_toolchain_may_be_a_callable_provider(self):
        calls = []

        def provider():
            calls.append(1)
            return EMPTY_TOOLCHAIN
        (result,) = _run(JavaRunner("synthetic", toolchain=provider), "int x = 1;")
        assert result.reason == "TOOLCHAIN-UNAVAILABLE" and calls

    def test_both_artifact_options_at_once_is_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            JavaRunner("synthetic", product_jar=tmp_path / "a.jar",
                       product_build=ProductBuild(tmp_path, "0" * 40))


# ---------------------------------------------------------------------------
# base.py additions, proven with a NON-Java toy runner
# ---------------------------------------------------------------------------

class _ToyRunner:
    """A python-flavoured toy LanguageRunner: no JVM anywhere."""

    canonical_lang = "python"
    ceiling_tier = 3

    def __init__(self, acquire_result: dict, execute_result: "dict | None" = None):
        self._acquire = acquire_result
        self._execute = execute_result or {"status": "PASS"}

    def starts_chain(self, code):
        return True

    def acquire(self, work_dir, policy, product):
        return dict(self._acquire)

    def compile(self, acquired, code, index):
        return None

    def execute(self, acquired, code, index):
        return dict(self._execute)

    def classify(self, output, context=None):
        return "RUNTIME-ERROR", output


def _toy_run(toy: _ToyRunner):
    return BaseRunner(toy).run([("s", (1, 1), "x = 1\n")], POLICY, ProductContext())[0]


class TestBaseAdditionsWithNonJavaRunner:
    META = {"toolchain_name": "toy", "toolchain_version": "9.9", "toolchain_path": "/opt/toy",
            "artifact": {"jar_sha256": "abc", "note": "n"}}

    def test_registered_acquire_reason_is_passed_through(self):
        r = _toy_run(_ToyRunner({"ok": False, "reason": "TOOLCHAIN-UNAVAILABLE",
                                 "detail": "none here", "result_meta": self.META}))
        assert (r.status, r.reason, r.proof_tier) == ("BLOCKED-WITH-REASON", "TOOLCHAIN-UNAVAILABLE", 0)
        assert r.toolchain_name == "toy" and r.artifact == self.META["artifact"]

    def test_unregistered_acquire_reason_is_not_trusted(self):
        r = _toy_run(_ToyRunner({"ok": False, "reason": "MADE-UP-REASON", "detail": "d"}))
        assert r.reason == "ACQUIRE-FAILED"

    def test_no_reason_keeps_the_generic_acquire_failed(self):
        r = _toy_run(_ToyRunner({"ok": False, "detail": "d"}))
        assert r.reason == "ACQUIRE-FAILED" and r.artifact is None

    def test_meta_lands_on_a_passing_result(self):
        r = _toy_run(_ToyRunner({"ok": True, "result_meta": self.META}))
        assert r.status == "PASS" and r.proof_tier == 3
        assert (r.toolchain_version, r.toolchain_path) == ("9.9", "/opt/toy")

    def test_executed_failure_may_report_a_lower_proof_tier(self):
        r = _toy_run(_ToyRunner({"ok": True}, {"status": "BLOCKED-WITH-REASON",
                                               "reason": "FIXTURE-UNAVAILABLE",
                                               "detail": "d", "proof_tier": 2}))
        assert (r.reason, r.proof_tier) == ("FIXTURE-UNAVAILABLE", 2)

    def test_default_executed_failure_tier_is_still_3(self):
        r = _toy_run(_ToyRunner({"ok": True}, {"status": "BLOCKED-WITH-REASON",
                                               "reason": "RUNTIME-ERROR", "detail": "d"}))
        assert r.proof_tier == 3

    def test_a_runner_recording_nothing_is_unchanged(self):
        r = _toy_run(_ToyRunner({"ok": True}))
        assert r.artifact is None and r.toolchain_name is None


# ---------------------------------------------------------------------------
# Fixture helpers (machine independent)
# ---------------------------------------------------------------------------

class TestFixtureHelpers:
    @pytest.mark.parametrize("bad", ["../escape.txt", "/abs/path.txt", "a/../../b.txt", " "])
    def test_unsafe_fixture_names_are_rejected(self, tmp_path, bad):
        with pytest.raises(ValueError):
            _safe_fixture_path(tmp_path, bad)

    def test_safe_nested_name_resolves_inside_work_dir(self, tmp_path):
        target = _safe_fixture_path(tmp_path, "data/in.bin")
        assert tmp_path.resolve() in target.parents

    @pytest.mark.parametrize("output,expected", [
        ("java.io.FileNotFoundException: report.pdf (The system cannot find the file specified)", "report.pdf"),
        ("java.io.FileNotFoundException: in/book.xlsx (No such file or directory)", "in/book.xlsx"),
        ("Exception in thread main java.nio.file.NoSuchFileException: README.md\n\tat x", "README.md"),
        ("java.lang.ArithmeticException: / by zero", None),
        ("", None),
    ])
    def test_missing_input_extraction(self, output, expected):
        assert _missing_input(output) == expected


# ---------------------------------------------------------------------------
# Real JDK: product jar on the classpath
# ---------------------------------------------------------------------------

IMPORT_BLOCK = 'import gadget.Greeter;\nSystem.out.println(Greeter.hello("world"));'


@needs_jdk
class TestProductJarCompileAndRun:
    def test_compile_ok_and_run_ok_against_the_product_jar(self, gadget_jar):
        runner = JavaRunner("synthetic", product_jar=gadget_jar)
        (r,) = _run(runner, IMPORT_BLOCK)
        assert r.status == "PASS" and r.proof_tier == 3
        assert r.artifact["jar_sha256"] == _sha(gadget_jar)
        assert r.artifact["origin"] == "prebuilt"
        assert r.artifact["toolchain"]["jdk_version"] == r.toolchain_version
        assert r.toolchain_name == "java" and r.toolchain_path

    def test_without_the_jar_the_same_block_cannot_compile(self):
        (r,) = _run(JavaRunner("synthetic"), IMPORT_BLOCK)
        assert r.status == "BLOCKED-WITH-REASON" and r.reason == "COMPILE-ERROR"
        assert r.proof_tier == 2 and "gadget" in r.detail

    def test_compile_failure_against_the_jar_is_blocked_compile_error(self, gadget_jar):
        runner = JavaRunner("synthetic", product_jar=gadget_jar)
        (r,) = _run(runner, 'import gadget.Greeter;\nGreeter.doesNotExist();')
        assert r.status == "BLOCKED-WITH-REASON" and r.reason == "COMPILE-ERROR"
        assert r.proof_tier == 2
        assert r.artifact["jar_sha256"] == _sha(gadget_jar)

    def test_runtime_error_inside_the_product_is_classified_against_the_jar(self, gadget_jar):
        runner = JavaRunner("synthetic", product_jar=gadget_jar)
        (r,) = _run(runner, 'import gadget.Greeter;\nGreeter.readAll(null);')
        assert r.status == "BLOCKED-WITH-REASON" and r.proof_tier == 3
        assert r.reason in ("RUNTIME-ERROR", "UPSTREAM-BROKEN")

    def test_missing_product_jar_is_acquire_failed_not_a_pass(self, tmp_path):
        runner = JavaRunner("synthetic", product_jar=tmp_path / "absent.jar")
        (r,) = _run(runner, IMPORT_BLOCK)
        assert r.status == "BLOCKED-WITH-REASON" and r.reason == "ACQUIRE-FAILED"
        assert "absent.jar" in r.detail

    def test_extra_classpath_entries_are_honoured(self, tmp_path):
        dep_src = tmp_path / "dep-src" / "dep"
        dep_src.mkdir(parents=True)
        (dep_src / "Extra.java").write_text(
            "package dep;\npublic class Extra { public static int one() { return 1; } }\n",
            encoding="utf-8")
        dep_jar = _build_jar(tmp_path / "dep-src", tmp_path / "dep.jar")
        (r,) = _run(JavaRunner("synthetic", extra_classpath=[dep_jar]),
                    'import dep.Extra;\nSystem.out.println(Extra.one());')
        # javac needs the dep too: compile is only given the extra entry
        assert r.status == "PASS" and r.proof_tier == 3

    def test_fingerprint_tracks_the_jar_content(self, gadget_jar, tmp_path):
        assert JavaRunner("synthetic").fingerprint() == ""
        fp1 = JavaRunner("synthetic", product_jar=gadget_jar).fingerprint()
        other = tmp_path / "other.jar"
        other.write_bytes(gadget_jar.read_bytes() + b"x")
        fp2 = JavaRunner("synthetic", product_jar=other).fingerprint()
        assert fp1.startswith("jar:") and fp1 != fp2


@needs_jdk
class TestFixturePrelude:
    READ_BLOCK = 'import gadget.Greeter;\nSystem.out.println(Greeter.readAll("report.txt"));'

    def test_missing_input_without_a_prelude_is_disclosed_compile_only(self, gadget_jar):
        runner = JavaRunner("synthetic", product_jar=gadget_jar)
        (r,) = _run(runner, self.READ_BLOCK)
        assert r.status == "BLOCKED-WITH-REASON"          # never a silent PASS
        assert r.reason == "FIXTURE-UNAVAILABLE"
        assert r.proof_tier == 2                           # compiled, not run to completion
        assert "report.txt" in r.detail
        assert not r.is_cacheable()

    def test_spec_prelude_stages_the_input_and_the_run_passes(self, gadget_jar):
        runner = JavaRunner("synthetic", product_jar=gadget_jar,
                            prelude=[FixtureSpec("report.txt", b"%DATA%")])
        (r,) = _run(runner, self.READ_BLOCK)
        assert r.status == "PASS" and r.proof_tier == 3
        assert r.artifact["fixtures_staged"] == ["report.txt"]

    def test_callable_prelude_is_supported(self, gadget_jar):
        def prelude(work_dir: Path) -> None:
            (work_dir / "report.txt").write_text("hello", encoding="utf-8")
        runner = JavaRunner("synthetic", product_jar=gadget_jar, prelude=prelude)
        (r,) = _run(runner, self.READ_BLOCK)
        assert r.status == "PASS" and r.artifact["fixtures_staged"] == ["report.txt"]

    def test_prelude_covering_a_different_file_still_discloses_the_gap(self, gadget_jar):
        runner = JavaRunner("synthetic", product_jar=gadget_jar,
                            prelude=[FixtureSpec("other.txt", "x")])
        (r,) = _run(runner, self.READ_BLOCK)
        assert r.reason == "FIXTURE-UNAVAILABLE" and "other.txt" in r.detail

    def test_lazy_callable_content_is_resolved_deterministically(self, gadget_jar):
        runner = JavaRunner("synthetic", product_jar=gadget_jar,
                            prelude=[FixtureSpec("report.txt", lambda: "lazy")])
        (r,) = _run(runner, self.READ_BLOCK)
        assert r.status == "PASS"


# ---------------------------------------------------------------------------
# Real JDK: build the pinned SHA in a temp copy; clone cache untouched
# ---------------------------------------------------------------------------

def _git(cwd: Path, *argv: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    r = subprocess.run(["git", *argv], cwd=str(cwd), check=True, capture_output=True,
                       text=True, encoding="utf-8", env=env)
    return r.stdout.strip()


@pytest.fixture
def fake_clone_cache(tmp_path):
    """A tiny real git repo standing in for runs/.clone_cache/<product>:
    two commits (v1 'hi', v2 'bye') so SHA pinning is observable."""
    import shutil
    if shutil.which("git") is None:
        pytest.skip("git not on PATH (loud skip: cannot build the temp-copy fixture)")
    repo = tmp_path / "clone_cache" / "synthetic_product"
    src = repo / "src" / "gadget"
    src.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    (src / "Greeter.java").write_text(GREETER, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "v1")
    sha1 = _git(repo, "rev-parse", "HEAD")
    (src / "Greeter.java").write_text(GREETER_V2, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "v2")
    sha2 = _git(repo, "rev-parse", "HEAD")
    return repo, sha1, sha2


class _Builder:
    """Injected build command: compiles src/ in the TEMP COPY with the
    discovered JDK (no Maven/network) and records what it was given."""

    def __init__(self):
        self.calls: list[Path] = []

    def __call__(self, source_dir: Path, tc: "tc_mod.JavaToolchain") -> Path:
        self.calls.append(source_dir)
        return _build_jar(source_dir / "src", source_dir / "out.jar", tc)


VERSION_PROBE = ('import gadget.Greeter;\n'
                 'if (!Greeter.hello("x").equals("hi x")) throw new RuntimeException("not v1: " + Greeter.hello("x"));')


@needs_jdk
class TestPinnedShaBuildInTempCopy:
    def test_builds_the_pinned_sha_not_the_clone_head_and_records_provenance(self, fake_clone_cache):
        repo, sha1, sha2 = fake_clone_cache
        builder = _Builder()
        with JavaRunner("synthetic", product_build=ProductBuild(repo, sha1, builder)) as runner:
            (r,) = _run(runner, VERSION_PROBE)
        assert r.status == "PASS" and r.proof_tier == 3     # v1 jar: hello() == "hi x"
        assert r.artifact["source_sha"] == sha1
        assert r.artifact["origin"] == "built-from-pinned-sha"
        assert len(r.artifact["jar_sha256"]) == 64
        # ... while the clone's own HEAD (v2) would have failed the probe:
        with JavaRunner("synthetic", product_build=ProductBuild(repo, sha2, _Builder())) as runner2:
            (r2,) = _run(runner2, VERSION_PROBE)
        assert r2.status == "BLOCKED-WITH-REASON" and r2.artifact["source_sha"] == sha2

    def test_clone_cache_is_untouched_and_build_never_writes_under_it(self, fake_clone_cache):
        repo, sha1, _sha2 = fake_clone_cache
        before = _tree_hash(repo)
        listing_before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*"))
        builder = _Builder()
        with JavaRunner("synthetic", product_build=ProductBuild(repo, sha1, builder)) as runner:
            results = _run(runner, VERSION_PROBE, 'System.out.println("second block");')
        assert [r.status for r in results] == ["PASS", "PASS"]
        assert _tree_hash(repo) == before
        assert sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*")) == listing_before
        resolved = repo.resolve()
        for src in builder.calls:
            assert resolved not in src.resolve().parents and src.resolve() != resolved
        assert (repo / "src" / "gadget" / "Greeter.java").read_text(encoding="utf-8") == GREETER_V2

    def test_build_runs_once_per_runner_instance_not_once_per_block(self, fake_clone_cache):
        repo, sha1, _ = fake_clone_cache
        builder = _Builder()
        with JavaRunner("synthetic", product_build=ProductBuild(repo, sha1, builder)) as runner:
            _run(runner, VERSION_PROBE, 'System.out.println("b");', 'System.out.println("c");')
        assert len(builder.calls) == 1

    def test_close_removes_the_temp_build_dir(self, fake_clone_cache):
        repo, sha1, _ = fake_clone_cache
        builder = _Builder()
        runner = JavaRunner("synthetic", product_build=ProductBuild(repo, sha1, builder))
        _run(runner, 'System.out.println("x");')
        build_root = builder.calls[0].parent
        assert build_root.is_dir()
        runner.close()
        assert not build_root.exists()
        runner.close()  # idempotent

    def test_unreachable_sha_is_acquire_failed_not_a_pass(self, fake_clone_cache):
        repo, _s1, _s2 = fake_clone_cache
        with JavaRunner("synthetic", product_build=ProductBuild(repo, "f" * 40, _Builder())) as runner:
            (r,) = _run(runner, 'System.out.println("x");')
        assert r.status == "BLOCKED-WITH-REASON" and r.reason == "ACQUIRE-FAILED"
        assert "checkout" in r.detail

    def test_a_failing_build_command_is_acquire_failed(self, fake_clone_cache):
        repo, sha1, _ = fake_clone_cache

        def boom(source_dir, tc):
            raise RuntimeError("compiler exploded")
        with JavaRunner("synthetic", product_build=ProductBuild(repo, sha1, boom)) as runner:
            (r,) = _run(runner, 'System.out.println("x");')
        assert r.reason == "ACQUIRE-FAILED" and "compiler exploded" in r.detail

    def test_missing_clone_path_is_acquire_failed(self, tmp_path):
        spec = ProductBuild(tmp_path / "no-such-clone", "a" * 40, _Builder())
        with JavaRunner("synthetic", product_build=spec) as runner:
            (r,) = _run(runner, 'System.out.println("x");')
        assert r.reason == "ACQUIRE-FAILED" and "clone_path" in r.detail

    def test_default_build_without_maven_is_acquire_failed_with_a_clear_reason(self, fake_clone_cache):
        repo, sha1, _ = fake_clone_cache
        no_mvn = tc_mod.JavaToolchain(jdk=_REAL.jdk, maven=None)
        with JavaRunner("synthetic", toolchain=no_mvn,
                        product_build=ProductBuild(repo, sha1)) as runner:
            (r,) = _run(runner, 'System.out.println("x");')
        assert r.reason == "ACQUIRE-FAILED" and "Maven" in r.detail


@needs_jdk
class TestApiPlumbing:
    def test_verify_markdown_forwards_runner_kwargs_and_fingerprint(self, gadget_jar):
        from lib.example_verification import api
        text = "```java\n" + IMPORT_BLOCK + "\n```\n"
        report = api.verify_markdown(
            text, family="synthetic", platform="java", policy=POLICY,
            runner_kwargs={"product_jar": gadget_jar})
        (block,) = report.blocks
        assert block.status == "PASS" and block.proof_tier == 3
        assert block.artifact["jar_sha256"] == _sha(gadget_jar)


# ===========================================================================
# MT074 B6b: default fixture prelude (fixtures.py) -- format-generic
# ===========================================================================

import io  # noqa: E402
import json as _json  # noqa: E402
import re  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402
import zipfile  # noqa: E402
from html.parser import HTMLParser  # noqa: E402

from lib.example_verification import fixtures as fx  # noqa: E402
from lib.example_verification.result import BlockIdentity, BlockResult  # noqa: E402


def _parse_pdf(data: bytes) -> dict:
    """Small PDF checker: header, %%EOF, startxref -> 'xref', every xref
    offset lands on 'N 0 obj', stream /Length matches, trailer /Size."""
    assert data.startswith(b"%PDF-1.4\n")
    assert data.rstrip().endswith(b"%%EOF")
    m = re.search(rb"startxref\n(\d+)\n%%EOF", data)
    assert m, "no startxref"
    xref_at = int(m.group(1))
    assert data[xref_at:xref_at + 4] == b"xref"
    head = re.match(rb"xref\n0 (\d+)\n", data[xref_at:])
    count = int(head.group(1))
    table = data[xref_at + head.end():].split(b"trailer")[0]
    entries = [table[i:i + 20] for i in range(0, len(table), 20)]
    assert len(entries) == count and all(len(e) == 20 and e.endswith(b" \n") for e in entries)
    assert entries[0] == b"0000000000 65535 f \n"
    for number, entry in enumerate(entries[1:], start=1):
        off = int(entry[:10])
        assert data[off:].startswith(f"{number} 0 obj\n".encode()), number
    assert re.search(rb"/Size %d" % count, data)
    stream = re.search(rb"/Length (\d+) >>\nstream\n(.*?)\nendstream", data, re.DOTALL)
    assert int(stream.group(1)) == len(stream.group(2))
    return {"objects": count - 1, "stream": stream.group(2)}


def _check_ooxml(data: bytes, required: "list[str]") -> zipfile.ZipFile:
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert zf.testzip() is None
    names = zf.namelist()
    assert names[0] == "[Content_Types].xml"
    for r in required:
        assert r in names, r
    for n in names:
        ET.fromstring(zf.read(n))  # every part is well-formed XML
        assert zf.getinfo(n).date_time == (1980, 1, 1, 0, 0, 0)
    return zf


class _TagBalance(HTMLParser):
    VOID = {"meta", "br", "hr", "img", "link", "input"}

    def __init__(self):
        super().__init__()
        self.stack, self.seen = [], set()

    def handle_starttag(self, tag, attrs):
        self.seen.add(tag)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, tag


class TestGenerators:
    def test_pdf_is_valid_with_text_and_table(self):
        info = _parse_pdf(fx.make_pdf())
        assert info["objects"] == 5
        assert b"Sample Document" in info["stream"] and b"Widget" in info["stream"]
        assert b"Widget" not in _parse_pdf(fx.make_pdf(table=False))["stream"]

    def test_pdf_escapes_parentheses_in_custom_lines(self):
        stream = _parse_pdf(fx.make_pdf(["a (b) c"], table=False))["stream"]
        assert b"(a \\(b\\) c) Tj" in stream

    def test_xlsx_is_valid_ooxml_with_the_required_cell_kinds(self):
        zf = _check_ooxml(fx.make_xlsx(), [
            "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels",
            "xl/worksheets/sheet1.xml", "xl/styles.xml", "xl/sharedStrings.xml"])
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        cells = {c.get("r"): c for c in sheet.iter("{%s}c" % ns["m"])}
        assert cells["A1"].get("t") == "s"                       # string
        assert cells["B2"].find("m:v", ns).text == "2"          # number
        assert cells["E2"].get("s") == "1"                       # date-formatted number
        assert cells["F2"].get("t") == "b"                       # boolean
        assert cells["D2"].find("m:f", ns).text == "B2*C2"       # formula ...
        assert cells["D2"].find("m:v", ns).text == "7"           # ... with cached value
        assert [m.get("ref") for m in sheet.iter("{%s}mergeCell" % ns["m"])] == ["A5:D5"]
        styles = ET.fromstring(zf.read("xl/styles.xml"))
        xfs = list(styles.find("m:cellXfs", ns))
        assert xfs[1].get("numFmtId") == "14"

    def test_docx_has_heading_paragraph_and_2x2_table(self):
        zf = _check_ooxml(fx.make_docx(), [
            "_rels/.rels", "word/document.xml", "word/_rels/document.xml.rels", "word/styles.xml"])
        w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        doc = ET.fromstring(zf.read("word/document.xml"))
        assert doc.find(f".//{w}pStyle").get(f"{w}val") == "Heading1"
        rows = doc.findall(f".//{w}tr")
        assert len(rows) == 2 and all(len(r.findall(f"{w}tc")) == 2 for r in rows)

    def test_html_parses_with_balanced_tags_and_structure(self):
        p = _TagBalance()
        p.feed(fx.make_html().decode("utf-8"))
        assert p.stack == [] and {"h1", "ul", "li", "table", "tr", "td"} <= p.seen

    def test_markdown_has_each_construct(self):
        md = fx.make_md().decode("utf-8")
        assert md.startswith("# ")
        assert re.search(r"^- ", md, re.M) and re.search(r"\[[^\]]+\]\(https?://[^)]+\)", md)
        assert re.search(r"^\| .+ \|\n\| --- \|", md, re.M)
        assert md.count("```") == 2

    def test_txt_json_csv_parse(self):
        import csv
        assert fx.make_txt().decode("utf-8").splitlines()
        assert _json.loads(fx.make_json())["items"][0]["name"]
        rows = list(csv.reader(io.StringIO(fx.make_csv().decode("utf-8"))))
        assert rows[0] == ["Item", "Qty", "Price"] and all(len(r) == 3 for r in rows)

    @pytest.mark.parametrize("ext", sorted(fx.GENERATORS))
    def test_every_generator_is_byte_identical_across_runs(self, ext):
        a, b = fx.GENERATORS[ext](), fx.GENERATORS[ext]()
        assert a == b and a
        assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()

    def test_generate_by_name_and_unknown_extension(self):
        assert fx.generate("Report.PDF") == fx.make_pdf()
        assert fx.generate("dir/book.xlsx") == fx.make_xlsx()
        assert fx.generate("blob.xyz") is None and fx.generate("noext") is None


class TestInputClassification:
    """Language-flavoured snippets (java / c# / python) -- format-generic."""

    @pytest.mark.parametrize("code,expected", [
        ('Document d = new Document("report.pdf");\nd.save("out.pdf");', ["report.pdf"]),
        ('var wb = new Workbook("book.xlsx");\nwb.Save("copy.xlsx");', ["book.xlsx"]),
        ('text = File.ReadAllText("in.json");\nFile.WriteAllText("out.json", text);', ["in.json"]),
        ('with open("data.csv") as f:\n    rows = f.read()\ndf.to_csv("result.csv")', ["data.csv"]),
        ('Files.write(Paths.get("out.txt"), data);', []),
        ('new FileOutputStream("o.bin");', []),
        ('doc.save("a.pdf"); Document d = new Document("a.pdf");', []),   # also an output -> excluded
        ('mystery("who-knows.pdf");', []),                                # unclassifiable -> excluded
        ('Files.readAllBytes(Paths.get("data/in.md"));', ["data/in.md"]),
        ('new Document("/abs/x.pdf"); new Document("../up.pdf");', []),   # unsafe paths dropped
        ('open("a.txt")\nopen("a.txt")\nopen("b.txt")', ["a.txt", "b.txt"]),
    ])
    def test_only_names_the_example_reads_are_kept(self, code, expected):
        assert fx.input_fixture_names(code) == expected


class TestDefaultPrelude:
    def test_maps_by_extension_in_order_and_skips_unknown(self):
        specs = fx.default_prelude(["a.pdf", "b.xyz", "c.md", "a.pdf", "d.docx"])
        assert [s.name for s in specs] == ["a.pdf", "c.md", "d.docx"]
        assert specs[0].content() == fx.make_pdf()

    def test_extensions_filter_accepts_dotted_and_bare(self):
        assert [s.name for s in fx.default_prelude(["a.pdf", "b.md"], extensions={"pdf"})] == ["a.pdf"]
        assert [s.name for s in fx.default_prelude(["a.pdf", "b.md"], extensions=[".MD"])] == ["b.md"]

    def test_empty_and_all_unknown_give_empty_list(self):
        assert fx.default_prelude([]) == []
        assert fx.default_prelude(["x.unknownext"]) == []

    def test_prelude_is_deterministic_across_calls(self):
        a = [(s.name, s.content()) for s in fx.default_prelude(["a.xlsx", "b.docx", "c.pdf"])]
        b = [(s.name, s.content()) for s in fx.default_prelude(["a.xlsx", "b.docx", "c.pdf"])]
        assert a == b


class TestBlockResultArtifactSerialisation:
    """to_legacy_s120() (also what `cli --json` prints) now carries the
    artifact record -- additive, only when present."""

    def _result(self, **kw):
        return BlockResult(identity=BlockIdentity("s", "java", 0, 1, 1), **kw)

    def test_artifact_is_serialised_for_a_tier3_pass_and_a_blocked_block(self):
        from lib.example_verification.result import VerificationReport
        art = {"jar_sha256": "ab" * 32, "source_sha": "c" * 40,
               "toolchain": {"jdk_source": "root:X"}, "fixtures_staged": ["a.pdf"]}
        report = VerificationReport(runner="java", blocks=[
            self._result(status="PASS", proof_tier=3, artifact=art),
            self._result(status="BLOCKED-WITH-REASON", reason="FIXTURE-UNAVAILABLE",
                         detail="d", proof_tier=2, artifact=art)])
        out = report.to_legacy_s120()
        assert out["blocks"][0]["artifact"] == art and out["blocks"][1]["artifact"] == art
        assert _json.loads(_json.dumps(out)) == out      # JSON round-trips (evidence bundle)

    def test_shapes_without_an_artifact_are_unchanged(self):
        from lib.example_verification.result import VerificationReport
        out = VerificationReport(runner="x", blocks=[
            self._result(status="PASS", proof_tier=3),
            self._result(status="BLOCKED-WITH-REASON", reason="TIMEOUT", detail="d")]).to_legacy_s120()
        assert out["blocks"][0] == {"index": 0, "status": "COMPILED+RAN CLEAN"}
        assert out["blocks"][1] == {"index": 0, "status": "BLOCKED-WITH-REASON",
                                    "reason": "TIMEOUT", "detail": "d"}


@needs_jdk
class TestJavaRunnerDefaultPrelude:
    READ = 'import gadget.Greeter;\nSystem.out.println(Greeter.readAll("{name}"));'

    @pytest.mark.parametrize("prelude", ["default", fx.default_prelude])
    def test_opt_in_stages_a_generated_input_and_the_run_passes(self, gadget_jar, prelude):
        runner = JavaRunner("synthetic", product_jar=gadget_jar, prelude=prelude)
        (r,) = _run(runner, self.READ.format(name="notes.md"))
        assert r.status == "PASS" and r.proof_tier == 3
        assert r.artifact["fixtures_staged"] == ["notes.md"]

    def test_unknown_extension_is_left_unresolved_and_still_fixture_unavailable(self, gadget_jar):
        runner = JavaRunner("synthetic", product_jar=gadget_jar, prelude="default")
        (r,) = _run(runner, self.READ.format(name="blob.xyz"))
        assert r.reason == "FIXTURE-UNAVAILABLE" and r.proof_tier == 2 and "blob.xyz" in r.detail

    def test_output_names_are_never_staged(self, gadget_jar):
        code = ('import gadget.Greeter;\n'
                'java.nio.file.Files.write(java.nio.file.Paths.get("made.txt"), new byte[0]);\n'
                'System.out.println(Greeter.hello("x"));')
        (r,) = _run(JavaRunner("synthetic", product_jar=gadget_jar, prelude="default"), code)
        assert r.status == "PASS"
        assert "fixtures_staged" not in r.artifact       # nothing was an input

    def test_no_prelude_keeps_pre_b6b_behaviour(self, gadget_jar):
        (r,) = _run(JavaRunner("synthetic", product_jar=gadget_jar), self.READ.format(name="notes.md"))
        assert r.reason == "FIXTURE-UNAVAILABLE"


_ENV_JAR = os.environ.get("MT074_PRODUCT_JAR", "")
_ENV_BLOCK = os.environ.get("MT074_OPEN_BLOCK", "")


@pytest.mark.skipif(
    not (_HAVE_JDK and _ENV_JAR and Path(_ENV_JAR).is_file() and _ENV_BLOCK),
    reason=("SKIPPED (opt-in): needs a discoverable JDK AND env MT074_PRODUCT_JAR=<built product jar> "
            "AND MT074_OPEN_BLOCK=<Java block opening sample.pdf with that product>; "
            "not required in normal runs"))
def test_generated_pdf_opens_with_the_real_product():
    runner = JavaRunner("product", product_jar=_ENV_JAR, prelude="default")
    (r,) = _run(runner, _ENV_BLOCK)
    assert r.status == "PASS" and r.proof_tier == 3, (r.reason, r.detail)
    assert "sample.pdf" in r.artifact["fixtures_staged"]


# ===========================================================================
# R3 fixes (MT074 independent review round 3)
# ===========================================================================

import sys  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402

from lib.example_verification import RUNNERS_MODULE_VERSION  # noqa: E402
from lib.example_verification.cache import CacheEntry, ResultCache, cache_key  # noqa: E402
from lib.example_verification.result import VerificationReport  # noqa: E402
from lib.example_verification.runners import java as java_mod  # noqa: E402

BS = chr(92)


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True, encoding="utf-8").stdout
        return f" {pid} " in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class TestCacheSchemaVersion:
    """MT074 coordinator decision: RUNNERS_MODULE_VERSION stays "1" (it is
    stamped into sweeps/proofs); stale cached entries are orphaned by the
    separate CACHE_SCHEMA_VERSION instead."""

    def test_runners_module_version_is_unchanged_and_schema_is_separate(self):
        from lib.example_verification.cache import CACHE_SCHEMA_VERSION
        assert RUNNERS_MODULE_VERSION == "1"
        assert VerificationReport(runner="x").runners_module_version == "1"
        assert CACHE_SCHEMA_VERSION == "2"

    def test_the_schema_version_is_part_of_the_cache_key(self):
        import hashlib as _h
        from lib.example_verification.cache import CACHE_SCHEMA_VERSION
        old = _h.sha256(b"1|s|java|h|fp|1").hexdigest()           # the pre-schema-2 key format
        new = _h.sha256(f"{CACHE_SCHEMA_VERSION}|s|java|h|fp|1".encode()).hexdigest()
        assert cache_key("s", "java", "h", "fp", "1") == new != old

    def test_a_v1_schema_entry_under_the_current_key_is_a_miss(self, tmp_path):
        """A stale cached RUNTIME-ERROR from the old semantics, even if it
        somehow sits under today's key, must never be served."""
        import json as _j
        cache = ResultCache("fam", "java", root=tmp_path)
        cache.path.parent.mkdir(parents=True)
        key = cache_key("s", "java", "h", "fp", "1")
        cache.path.write_text(_j.dumps({key: {
            "status": "BLOCKED-WITH-REASON", "proof_tier": 3, "reason": "RUNTIME-ERROR",
            "detail": "FileNotFoundException: in.pdf", "clone_head": "", "toolchain_version": "",
            "runners_module_version": "1", "code_sha256": ""}}), encoding="utf-8")  # no schema_version
        assert cache.get(key, 3) is None
        assert cache.get(key, 1) is None            # not even as a deterministic failure

    def test_put_stamps_the_current_schema_and_roundtrips(self, tmp_path):
        from lib.example_verification.cache import CACHE_SCHEMA_VERSION
        cache = ResultCache("fam", "java", root=tmp_path)
        key = cache_key("s", "java", "h", "fp", "1")
        assert cache.put(key, CacheEntry(status="PASS", proof_tier=3)) is True
        entry = ResultCache("fam", "java", root=tmp_path).get(key, 3)
        assert entry is not None and entry.schema_version == CACHE_SCHEMA_VERSION

    def test_a_schema_2_entry_without_meta_still_loads_with_meta_none(self, tmp_path):
        cache = ResultCache("fam", "java", root=tmp_path)
        cache.path.parent.mkdir(parents=True)
        cache.path.write_text(
            '{"k": {"status": "PASS", "proof_tier": 3, "reason": null, "detail": "",'
            ' "clone_head": "", "toolchain_version": "", "runners_module_version": "1",'
            ' "code_sha256": "", "schema_version": "2"}}', encoding="utf-8")
        entry = cache.get("k", 3)
        assert isinstance(entry, CacheEntry) and entry.meta is None


# --- R3-7a/c + M14: cache provenance, prelude fingerprint, jar fingerprint in the key ---

@needs_jdk
class TestCacheProvenanceAndKeyEndToEnd:
    TEXT = "```java\nimport gadget.Greeter;\nSystem.out.println(Greeter.hello(\"w\"));\n```\n"
    READ = "```java\nimport gadget.Greeter;\nSystem.out.println(Greeter.readAll(\"notes.md\"));\n```\n"

    def _verify(self, text, cache, **runner_kwargs):
        from lib.example_verification import api
        report = api.verify_markdown(text, family="synthetic", platform="java", policy=POLICY,
                                     runner_kwargs=runner_kwargs, cache=cache)
        (block,) = report.blocks
        return block

    @pytest.fixture
    def other_jar(self, tmp_path) -> Path:
        src = tmp_path / "other-src" / "other"
        src.mkdir(parents=True)
        (src / "Thing.java").write_text("package other;\npublic class Thing {}\n", encoding="utf-8")
        return _build_jar(tmp_path / "other-src", tmp_path / "other.jar")

    def test_cache_hit_restores_the_artifact_and_toolchain_provenance(self, tmp_path, gadget_jar):
        cache = ResultCache("synthetic", "java", root=tmp_path / "cache")
        first = self._verify(self.TEXT, cache, product_jar=gadget_jar)
        assert first.status == "PASS" and first.provenance == "executed"
        second = self._verify(self.TEXT, cache, product_jar=gadget_jar)
        assert second.provenance == "cache" and second.status == "PASS"
        assert second.artifact["jar_sha256"] == _sha(gadget_jar)
        assert second.artifact["toolchain"]["jdk_version"] == first.toolchain_version
        assert (second.toolchain_name, second.toolchain_path) == (first.toolchain_name, first.toolchain_path)

    def test_a_different_jar_is_never_served_the_cached_pass(self, tmp_path, gadget_jar, other_jar):
        """M14: dropping toolchain_fp (the jar fingerprint) from the cache key in
        api.py would serve jar A's PASS to a runner holding jar B."""
        cache = ResultCache("synthetic", "java", root=tmp_path / "cache")
        assert self._verify(self.TEXT, cache, product_jar=gadget_jar).status == "PASS"
        other = self._verify(self.TEXT, cache, product_jar=other_jar)
        assert other.provenance == "executed"
        assert other.status == "BLOCKED-WITH-REASON" and other.reason == "COMPILE-ERROR"

    def test_a_runner_without_fixtures_is_never_served_the_default_prelude_pass(self, tmp_path, gadget_jar):
        cache = ResultCache("synthetic", "java", root=tmp_path / "cache")
        with_prelude = self._verify(self.READ, cache, product_jar=gadget_jar, prelude="default")
        assert with_prelude.status == "PASS" and with_prelude.proof_tier == 3
        without = self._verify(self.READ, cache, product_jar=gadget_jar)
        assert without.provenance == "executed"
        assert without.reason == "FIXTURE-UNAVAILABLE"
        # ... and the original configuration still hits its own entry
        again = self._verify(self.READ, cache, product_jar=gadget_jar, prelude="default")
        assert again.provenance == "cache" and again.status == "PASS"


class TestPreludeFingerprint:
    def test_fingerprint_distinguishes_prelude_configurations(self, gadget_jar_path=None):
        none = JavaRunner("s").fingerprint()
        default = JavaRunner("s", prelude="default").fingerprint()
        same = JavaRunner("s", prelude=fx.default_prelude).fingerprint()
        specs_a = JavaRunner("s", prelude=[FixtureSpec("a.txt", b"1")]).fingerprint()
        specs_b = JavaRunner("s", prelude=[FixtureSpec("a.txt", b"2")]).fingerprint()
        assert none == "" and default.startswith("prelude:default:") and default == same
        assert specs_a != specs_b and len({none, default, specs_a, specs_b}) == 4

    def test_jar_and_prelude_parts_are_both_in_the_key(self, tmp_path):
        jar = tmp_path / "p.jar"
        jar.write_bytes(b"jar-bytes")
        fp = JavaRunner("s", product_jar=jar, prelude="default").fingerprint()
        assert fp.startswith("jar:") and "|prelude:default:" in fp
        assert JavaRunner("s", product_jar=jar).fingerprint() == fp.split("|")[0]


# --- R3-8a: only expected INPUT names become FIXTURE-UNAVAILABLE ---

class TestExpectedInputGate:
    def test_is_expected_input_matches_exact_nested_and_dot_slash_paths(self):
        exp = {"report.pdf", "data/in.md"}
        assert java_mod._is_expected_input("report.pdf", exp)
        assert java_mod._is_expected_input("./report.pdf", exp)
        assert java_mod._is_expected_input("data" + BS + "in.md", exp)
        assert java_mod._is_expected_input("C:/work/data/in.md", exp)
        assert not java_mod._is_expected_input("other.pdf", exp)
        assert not java_mod._is_expected_input("xreport.pdf", exp)       # suffix must be a path segment

    @needs_jdk
    def test_a_missing_directory_on_a_write_stays_a_runtime_error(self, gadget_jar):
        code = ('import gadget.Greeter;\n'
                'java.nio.file.Files.write(java.nio.file.Paths.get("nodir/made.txt"), new byte[0]);')
        (r,) = _run(JavaRunner("synthetic", product_jar=gadget_jar, prelude="default"), code)
        assert r.status == "BLOCKED-WITH-REASON"
        assert r.reason != "FIXTURE-UNAVAILABLE" and r.proof_tier == 3

    @needs_jdk
    def test_an_unclassified_literal_is_not_relabelled_fixture_unavailable(self, gadget_jar):
        code = 'import gadget.Greeter;\nString t = "x.txt";\nGreeter.readAll(t);'
        (r,) = _run(JavaRunner("synthetic", product_jar=gadget_jar), code)
        assert r.status == "BLOCKED-WITH-REASON"
        assert r.reason != "FIXTURE-UNAVAILABLE" and r.proof_tier == 3

    @needs_jdk
    def test_a_classified_input_is_still_fixture_unavailable(self, gadget_jar):
        code = 'import gadget.Greeter;\nGreeter.readAll("report.txt");'
        (r,) = _run(JavaRunner("synthetic", product_jar=gadget_jar), code)
        assert r.reason == "FIXTURE-UNAVAILABLE" and r.proof_tier == 2


# --- R3-8b: whole-word classification ---

class TestWholeWordClassification:
    @pytest.mark.parametrize("code", [
        'String target = "result.pdf";',
        'String address = "mail.json";',
        'var profile = "p.json";',
        'String prefix = "out.csv";',
        'string addressBook = "book.xlsx";',
        'target = "result.pdf"',
    ])
    def test_substring_lookalikes_are_not_staged(self, code):
        assert fx.input_fixture_names(code) == []

    @pytest.mark.parametrize("code,expected", [
        ('doc = Document.getFrom("a.pdf")', ["a.pdf"]),
        ('Workbook wb = Workbook.Load("b.xlsx");', ["b.xlsx"]),
        ('p = XMLParser.parse("c.html")', ["c.html"]),
        ('read_all_text("d.txt")', ["d.txt"]),
        ('new FileInputStream("e.bin")', ["e.bin"]),      # words: file, input, stream
        ('new FileOutputStream("f.bin")', []),            # output wins over file
        ('wb.saveAs("g.xlsx")', []),
    ])
    def test_real_words_still_classify(self, code, expected):
        assert fx.input_fixture_names(code) == expected

    def test_word_splitting_handles_camel_pascal_snake_and_acronyms(self):
        assert fx._words("readAllBytes") == {"read", "all", "bytes"}
        assert fx._words("ReadAllText") == {"read", "all", "text"}
        assert fx._words("XMLParser") == {"xml", "parser"}
        assert fx._words("save_as") == {"save", "as"}
        assert fx._words("target") == {"target"}


# --- R3-8c: sha validation ---

class TestPinnedShaValidation:
    @pytest.mark.parametrize("sha", [
        "--upload-pack=touch /tmp/pwned", "-" + "a" * 7, "abc", "", "g" * 40, "a" * 65, "main", "HEAD~1",
    ])
    def test_non_hex_or_wrong_length_sha_is_rejected_before_any_git_call(self, tmp_path, sha):
        import shutil
        if shutil.which("git") is None:
            pytest.skip("git not on PATH (loud skip)")
        fake_jdk = tc_mod._jdk_from_home(_fake_jdk(tmp_path / "jdks", "jdk-17.0.1", "17.0.1"), "test")
        tc = tc_mod.JavaToolchain(jdk=fake_jdk, maven=None)
        runner = JavaRunner("s", toolchain=tc, product_build=ProductBuild(tmp_path, sha, _Builder()))
        try:
            out = runner.acquire(tmp_path / "w", POLICY, ProductContext())
        finally:
            runner.close()
        assert out["ok"] is False and "hex" in out["detail"]

    def test_git_commands_use_the_double_dash_separators(self):
        src = Path(java_mod.__file__).read_text(encoding="utf-8")
        assert '"-q", "--",' in src and '"--detach", spec.sha, "--"' in src


# --- R3-8d: process-tree kill and non-silent cleanup ---

class TestProcessTreeAndCleanup:
    def test_timeout_kills_grandchildren_not_just_the_launcher(self, tmp_path):
        script = tmp_path / "spawn.py"
        script.write_text(
            "import subprocess, sys, time\n"
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            "print(p.pid, flush=True)\n"
            "time.sleep(120)\n", encoding="utf-8")
        code, out, _err, timed_out = java_mod._run_tree([sys.executable, str(script)], timeout=6)
        assert timed_out is True
        pid = int(out.split()[0])
        deadline = time.time() + 10
        while time.time() < deadline and _pid_alive(pid):
            time.sleep(0.2)
        assert not _pid_alive(pid), "grandchild survived the timeout kill"

    def test_run_tree_returns_output_and_exit_code_when_it_finishes(self):
        code, out, err, timed_out = java_mod._run_tree(
            [sys.executable, "-c", "import sys; print('hi'); sys.exit(3)"], timeout=30)
        assert (code, out.strip(), timed_out) == (3, "hi", False)

    def test_cleanup_retries_then_warns_and_records_instead_of_leaking_silently(self, tmp_path):
        stuck = tmp_path / "stuck"
        stuck.mkdir()
        calls = []

        def never_removes(path):
            calls.append(path)
            raise PermissionError("locked by a child JVM")

        before = list(java_mod.LEAKED_BUILD_DIRS)
        with pytest.warns(RuntimeWarning, match="could not remove temp build dir"):
            gone = java_mod._rmtree_force(stuck, attempts=3, delay=0, remover=never_removes)
        assert gone is False and len(calls) == 3
        assert java_mod.LEAKED_BUILD_DIRS[len(before):] == [str(stuck)]
        del java_mod.LEAKED_BUILD_DIRS[len(before):]

    def test_cleanup_removes_a_tree_with_read_only_files(self, tmp_path):
        d = tmp_path / "tree" / "objects"
        d.mkdir(parents=True)
        f = d / "pack"
        f.write_bytes(b"x")
        os.chmod(f, 0o444)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert java_mod._rmtree_force(tmp_path / "tree", delay=0) is True
        assert not (tmp_path / "tree").exists()


# --- R3-8e: preferred JDK majors ---

class TestPreferredJdkMajors:
    def _roots(self, tmp_path, *versions):
        root = tmp_path / "jdks"
        for v in versions:
            _fake_jdk(root, f"jdk-{v}", v)
        return root

    def test_default_prefers_21_over_a_newer_lts_25(self, tmp_path):
        root = self._roots(tmp_path, "11.0.2", "17.0.1", "21.0.1", "25.0.1")
        assert tc_mod.discover_jdk(env={}, roots=[root], which=_none).major == 21

    def test_default_order_is_21_then_17_then_11_all_before_25(self, tmp_path):
        assert tc_mod.DEFAULT_PREFERRED_MAJORS == (21, 17, 11)
        r17 = self._roots(tmp_path / "a", "11.0.2", "17.0.1", "25.0.1")
        assert tc_mod.discover_jdk(env={}, roots=[r17], which=_none).major == 17
        r11 = self._roots(tmp_path / "b", "11.0.2", "25.0.1")
        assert tc_mod.discover_jdk(env={}, roots=[r11], which=_none).major == 11

    def test_falls_back_to_the_newest_lts_when_no_preferred_major_exists(self, tmp_path):
        root = self._roots(tmp_path, "25.0.1", "22.0.1")
        assert tc_mod.discover_jdk(env={}, roots=[root], which=_none).major == 25

    def test_env_var_overrides_the_order(self, tmp_path):
        root = self._roots(tmp_path, "17.0.1", "21.0.1")
        env = {tc_mod.ENV_PREFERRED_MAJORS_VAR: "17, 21"}
        assert tc_mod.discover_jdk(env=env, roots=[root], which=_none).major == 17

    def test_explicit_preferred_argument_beats_env_and_default(self, tmp_path):
        root = self._roots(tmp_path, "21.0.1", "25.0.1")
        assert tc_mod.discover_jdk(env={}, roots=[root], which=_none, preferred=(25,)).major == 25

    def test_garbage_env_value_falls_back_to_the_default(self):
        assert tc_mod.preferred_majors({tc_mod.ENV_PREFERRED_MAJORS_VAR: "latest"}) == (21, 17, 11)
        assert tc_mod.preferred_majors({}) == (21, 17, 11)

    def test_path_and_java_home_ignore_the_preference(self, tmp_path):
        home = _fake_jdk(tmp_path / "x", "jdk-25.0.1", "25.0.1")
        jdk = tc_mod.discover_jdk(env={"JAVA_HOME": str(home)}, roots=[self._roots(tmp_path, "21.0.1")], which=_none)
        assert jdk.major == 25 and jdk.source == "env:JAVA_HOME"


# --- M11: _safe_fixture_path guards, each independently exercised ---

class TestSafeFixturePathGuards:
    @pytest.mark.parametrize("bad", [
        "../x.pdf", "..", "a/../b.txt",                    # lexical: `..` even when it stays inside
        "/abs/x.pdf", BS + "rooted.pdf",                   # absolute / rooted
        "C:" + BS + "x.pdf", "C:/x.pdf", "C:x.pdf",        # drive-letter and drive-relative (every OS)
        BS * 2 + "server" + BS + "share" + BS + "x.pdf",   # UNC
        "", "   ",
    ])
    def test_lexical_guard_rejects_on_every_os(self, tmp_path, bad):
        with pytest.raises(ValueError):
            _safe_fixture_path(tmp_path, bad)

    def test_resolved_guard_rejects_a_symlink_or_junction_escape(self, tmp_path):
        work = tmp_path / "work"
        outside = tmp_path / "outside"
        work.mkdir()
        outside.mkdir()
        link = work / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            made = os.name == "nt" and subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                capture_output=True).returncode == 0
            if not made:
                pytest.skip("cannot create a symlink/junction here (loud skip: resolved-path guard untested)")
        with pytest.raises(ValueError, match="escapes"):
            _safe_fixture_path(work, "link/x.pdf")

    def test_a_normal_nested_name_is_accepted(self, tmp_path):
        assert _safe_fixture_path(tmp_path, "data/sub/in.pdf").name == "in.pdf"
