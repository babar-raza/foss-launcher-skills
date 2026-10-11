"""
lib/example_verification/runners/java.py

CONTRACT: scripts/pipeline/lib/example_verification/runners/java.py
  purpose: C12 (MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION) -- the
           Java `LanguageRunner` (runners/base.py protocol): real `javac`
           (tier 2) -> real `java` (tier 3). The third concrete
           `LanguageRunner` implementation after C5's `GoRunner` and C11's
           `DotNetRunner`, applying the same design conventions (instance-
           scoped state; a file-citation-basename check in `classify()`
           rather than a raw-path substring match).
  inputs:  a fenced ```java code block's raw text (a bare statement fragment
           or an already-complete `class X { ... }` declaration); a Java
           product's family name
  outputs: JavaRunner, a `runners/base.py.LanguageRunner`
  owner_domain: content-quality

Real, machine-confirmed wrinkle this module designs around (per the
governing plan's own "Java" language-runner notes): `mvn` on this machine
resolves its own build against JDK 17.0.19, while the bare `java` found
directly on PATH is a DIFFERENT JDK, 21.0.11. `_discover_java_toolchain()`
parses `mvn -version`'s own reported "Java version"/"runtime" line -- the
plan's explicit toolchain-discovery source of truth -- rather than
assuming whichever `java` happens to be first on PATH, and uses `shutil.
which("mvn")` (never a bare `"mvn"` argv, which raises WinError 2 on
Windows since `mvn` resolves to `mvn.CMD`, not a directly-executable file
-- the same class of bug already hit and fixed once for Go/TypeScript).

MT074 B6 (R8) -- product-artifact acquisition. The original scope limit
("no real product JAR is ever on the classpath") is closed, additively:

  * Toolchain discovery is no longer PATH-only: `toolchain.discover_java_
    toolchain()` walks PATH -> JAVA_HOME/MAVEN_HOME/M2_HOME -> an ordered,
    configurable root list (`ASPOSE_TOOLCHAIN_ROOTS` + per-OS defaults) and
    picks the newest LTS JDK >= 11. A PATH `mvn` still wins first and its
    own reported JDK is still the one used (legacy semantics unchanged);
    every result records the discovery SOURCE/path/version.
  * `JavaRunner(family, product_jar=...)` puts a pre-built jar on the
    javac (tier 2) and java (tier 3) classpaths. `JavaRunner(family,
    product_build=ProductBuild(clone_path, sha))` builds the PINNED SHA in a
    TEMP COPY (`git clone --no-checkout --no-hardlinks` of the cache path
    into a runner-owned temp dir, `git checkout --detach <sha>`, then `mvn
    -q -B -DskipTests -Dgpg.skip package` -- the build command is
    injectable) once per runner instance; nothing is ever built in, or
    written under, the clone path. The jar's sha256, the source SHA and the
    toolchain record ride on every BlockResult (`BlockResult.artifact`).
  * `prelude=` is a declared, deterministic hook (a list of `FixtureSpec`
    or a callable taking the run's work dir) that stages input files before
    tier-3 execution. An example that still needs an input no prelude
    provides ends as BLOCKED `FIXTURE-UNAVAILABLE` at proof tier 2
    (compiled, not run to completion) -- never a silent PASS.
  * No discoverable JDK is an explicit BLOCKED result whose reason is the
    registered `TOOLCHAIN-UNAVAILABLE` and whose detail is prefixed
    `BLOCKED_TOOLCHAIN:` -- never a PASS (base.py passes a runner's
    registered acquire-failure reason through).

Still out of scope (disclosed): dependency JARs of the product are not
resolved -- pass `extra_classpath=` for a product that needs them; Maven's
first-build plugin resolution needs network access, so an offline-mirror
fixture is not provided.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import warnings
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .. import toolchain as tc_mod
from ..fixtures import FixtureSpec, default_prelude, generators_fingerprint, input_fixture_names
from ..policy import Policy, ProductContext

_MVN_VERSION_RE = re.compile(r'Java version:\s*([\d.]+).*?runtime:\s*(.+)', re.IGNORECASE)

# A real javac compile error's own file:line citation, e.g.
# "Main.java:3: error: cannot find symbol". Confirmed via a real javac call.
_JAVAC_LOCATION_RE = re.compile(r'([\w./\\-]+\.java):\d+:')
# A real uncaught-exception stack frame's own citation, e.g.
# "at Main.main(Main.java:3)". Confirmed via a real java call.
_JAVA_STACK_LOCATION_RE = re.compile(r'\(([\w./\\-]+\.java):\d+\)')

_CLASS_DECL_RE = re.compile(r'^\s*(public\s+)?(?:final\s+)?class\s+(\w+)', re.MULTILINE)

# Text blocks (Java 15+, `"""..."""`) tried BEFORE a plain string literal (leftmost
# alternative that can match at a given position wins in Python's re) -- otherwise the
# plain-string alternative would consume only the first two quotes of the opening
# `"""` as an empty string, leaving the third stray. String/char literals (and text
# blocks) are matched before the comment alternatives for the same reason: so a
# `/*`/`//` sequence INSIDE one (e.g. `"/* not a comment */"`) is consumed as part of
# the literal, never mistaken for the start of a real comment -- independent-reviewer
# finding (round 2): the original `_strip_comments` matched `/\*.*?\*/` completely
# literal-unaware, so a string literal containing an unterminated-looking `/*` let the
# non-greedy regex span all the way to an unrelated, LATER real `*/`, deleting real
# code (including a real `public class` declaration) along with it.
_JAVA_STRING_OR_COMMENT_RE = re.compile(
    r'"""(?:\\.|(?!""").)*?"""'
    r'|"(?:\\.|[^"\\])*"'
    r"|'(?:\\.|[^'\\])*'"
    r'|/\*.*?\*/'
    r'|//[^\n]*',
    re.DOTALL,
)


def _strip_comments(code: str) -> str:
    """A `class X` mention inside a comment (a line comment, or explanatory
    prose in a block comment) must never be mistaken for a real declaration
    -- independent-reviewer finding, fixed here.

    Independent-reviewer finding (round 3), fixed here: string/char
    literals (and text blocks) were preserved VERBATIM -- which correctly
    stopped the comment-stripping regex from being fooled by comment-like
    characters inside one (round 2's fix), but left the literal's own
    CONTENT fully visible to the later `_CLASS_DECL_RE` scan. A `class X`
    mention embedded inside a string/text-block value (e.g. example Java
    source stored as documentation text) was therefore still mistaken for
    a real declaration -- the exact defect this function exists to
    prevent, via a different trigger. Every string/char/text-block match
    is now replaced with a neutral, non-matching placeholder instead of
    being preserved -- their CONTENT is never needed by either caller
    (`_needs_wrap`/`_class_name_for` only care whether/where a REAL `class`
    keyword exists), only their span, so the safe fix is to erase it, not
    keep it."""
    def _replace(m: "re.Match[str]") -> str:
        text = m.group(0)
        return '""' if text[0] in ('"', "'") else ''
    return _JAVA_STRING_OR_COMMENT_RE.sub(_replace, code)


def _discover_java_toolchain() -> "tuple[str, str, str] | None":
    """(java_exe, javac_exe, version) from `mvn -version`'s own reported Java
    runtime -- not whichever `java` happens to be first on PATH, which this
    machine confirms can be a genuinely different JDK than the one `mvn`
    itself resolves against. Returns `None` if `mvn` isn't on PATH, its
    output doesn't parse, or the reported runtime's `java`/`javac` aren't
    actually present on disk."""
    mvn_exe = shutil.which("mvn")
    if mvn_exe is None:
        return None
    try:
        result = subprocess.run(
            [mvn_exe, "-version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    m = _MVN_VERSION_RE.search(result.stdout or "")
    if not m:
        return None
    version, runtime_dir = m.group(1).strip(), m.group(2).strip()
    java_exe = str(Path(runtime_dir) / "bin" / ("java.exe" if os.name == "nt" else "java"))
    javac_exe = str(Path(runtime_dir) / "bin" / ("javac.exe" if os.name == "nt" else "javac"))
    if not Path(java_exe).is_file() or not Path(javac_exe).is_file():
        return None
    return java_exe, javac_exe, version


def _default_java_toolchain() -> tc_mod.JavaToolchain:
    """Default toolchain provider. Legacy semantics first: a `mvn` on PATH
    names the JDK it builds against (`_discover_java_toolchain`), which keeps
    winning exactly as before; otherwise the bounded discovery in
    `toolchain.discover_java_toolchain()` (JAVA_HOME / configured roots)."""
    discovered = tc_mod.discover_java_toolchain()
    legacy = _discover_java_toolchain()
    if legacy is None:
        return discovered
    java_exe, javac_exe, version = legacy
    jdk = tc_mod.JdkInfo(
        home=str(Path(javac_exe).parent.parent), java=java_exe, javac=javac_exe,
        jar=None, version=version, major=tc_mod._major_of(version), source="path:mvn-runtime",
    )
    return tc_mod.JavaToolchain(
        jdk=jdk, maven=discovered.maven, searched_roots=discovered.searched_roots)


# A toolchain with nothing discoverable -- inject it to prove the explicit
# BLOCKED toolchain outcome without touching the real machine.
EMPTY_TOOLCHAIN = tc_mod.JavaToolchain(jdk=None, maven=None)


@dataclass(frozen=True)
class ProductBuild:
    """Build spec for a product jar: `sha` of the repo at `clone_path`
    (read-only -- only ever `git clone`d FROM). `build_command(source_dir,
    toolchain)` returns the built jar's Path; None selects the default
    `mvn -q -B -DskipTests -Dgpg.skip package` + jar pick from `target/`."""

    clone_path: Path
    sha: str
    build_command: "Callable[[Path, tc_mod.JavaToolchain], Path] | None" = None
    mvn_args: tuple = ("-q", "-B", "-DskipTests", "-Dgpg.skip", "package")
    timeout: float = 1200.0


_FILE_NOT_FOUND_RE = re.compile(
    r"(?:java\.io\.FileNotFoundException|java\.nio\.file\.NoSuchFileException):\s*"
    r"([^\r\n(]+?)\s*(?:\(|$)", re.MULTILINE)


def _missing_input(output: str) -> "str | None":
    """The path a failed run could not open, if its output says so."""
    m = _FILE_NOT_FOUND_RE.search(output or "")
    return m.group(1).strip() if m else None


_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _is_expected_input(path: str, expected: "set[str]") -> bool:
    """True only when the missing `path` is one of the INPUT names the
    example reads (statement classifier) or a staged fixture -- a
    FileNotFoundException for a write into a missing directory, a
    permission error, an unclassified literal or an internal resource lookup
    stays a RUNTIME-ERROR instead of being relabelled FIXTURE-UNAVAILABLE."""
    norm = path.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return any(norm == n or norm.endswith("/" + n) for n in expected)


def _safe_fixture_path(work_dir: Path, name: str) -> Path:
    """Resolve a fixture name inside `work_dir` or raise ValueError. Two
    INDEPENDENT guards (each has its own test): (1) a lexical one --
    empty names, absolute / rooted / UNC / drive-letter / drive-relative
    names and any `..` segment (even one that would stay inside, e.g.
    `a/../b`) are rejected on every OS; (2) a resolved one -- the final path,
    after following symlinks/junctions already present in the work dir, must
    still sit under it."""
    norm = name.replace("\\", "/")
    rel = Path(name)
    if (not name.strip() or rel.is_absolute() or norm.startswith("/") or _DRIVE_RE.match(norm)
            or ".." in norm.split("/") or ".." in rel.parts):
        raise ValueError(f"fixture name must be a relative path inside the work dir: {name!r}")
    target = (work_dir / rel).resolve()
    if work_dir.resolve() not in target.parents:
        raise ValueError(f"fixture escapes the work dir: {name!r}")
    return target


# Build dirs that could not be removed (a child process still holding the dir
# locked, antivirus, ...) are RECORDED here and warned about, never silently
# leaked.
LEAKED_BUILD_DIRS: "list[str]" = []


def _rmtree_force(
    path: Path, *, attempts: int = 5, delay: float = 0.5,
    remover: "Callable[[Path], None] | None" = None,
) -> bool:
    """Remove `path`, retrying (Windows holds a dir locked while any child
    process lingers). Returns True when gone; otherwise records it in
    LEAKED_BUILD_DIRS and emits a RuntimeWarning -- never a silent leak."""
    def _fix_readonly(func, p) -> None:  # git object files are read-only on Windows
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    def _default_remove(target: Path) -> None:
        if sys.version_info >= (3, 12):
            shutil.rmtree(target, onexc=lambda func, p, _exc: _fix_readonly(func, p))
        else:  # `onerror` is deprecated from 3.12 and removed later
            shutil.rmtree(target, onerror=lambda func, p, _exc: _fix_readonly(func, p))

    remove = remover or _default_remove
    last: "Exception | None" = None
    for attempt in range(max(1, attempts)):
        try:
            remove(path)
        except OSError as exc:
            last = exc
        if not Path(path).exists():
            return True
        if attempt + 1 < attempts:
            time.sleep(delay)
    LEAKED_BUILD_DIRS.append(str(path))
    warnings.warn(f"example_verification: could not remove temp build dir {path} "
                  f"after {attempts} attempt(s) ({last}); it is recorded in "
                  f"runners.java.LEAKED_BUILD_DIRS", RuntimeWarning, stacklevel=2)
    return False


def _kill_tree(proc: "subprocess.Popen") -> None:
    """Kill `proc` AND its descendants (a bare kill only stops mvn.cmd/the
    launcher; the child JVMs would keep the temp dir locked)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=30)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _run_tree(
    argv: "list[str]", *, cwd: "Path | None" = None, env: "dict | None" = None, timeout: float,
) -> "tuple[int, str, str, bool]":
    """(returncode, stdout, stderr, timed_out). On timeout the WHOLE process
    tree is killed (Windows: taskkill /T /F; POSIX: the process group)."""
    kwargs: dict = {} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace", cwd=str(cwd) if cwd else None, env=env, **kwargs)
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", err or "", False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        return -1, out or "", err or "", True


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_git(argv: "list[str]", cwd: "Path | None" = None, timeout: float = 600.0) -> "tuple[bool, str]":
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        r = subprocess.run(
            ["git", *argv], capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=str(cwd) if cwd else None, timeout=timeout, env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"git {' '.join(argv[:2])} failed to run: {exc}"
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, out


_HEX_SHA_RE = re.compile(r"[0-9a-fA-F]{7,64}")
_EXCLUDED_JAR_MARKERS = ("-sources", "-javadoc", "-tests", "-test-", "original-")


def _default_mvn_build(spec: ProductBuild) -> "Callable[[Path, tc_mod.JavaToolchain], Path]":
    def _build(source_dir: Path, tc: tc_mod.JavaToolchain) -> Path:
        if tc.maven is None:
            raise RuntimeError("no Maven discoverable to build the product jar")
        argv = [tc.maven.mvn, *spec.mvn_args]
        code, out, err, timed_out = _run_tree(
            argv, cwd=source_dir, env=tc_mod.java_exec_env(tc), timeout=spec.timeout)
        if timed_out:
            raise RuntimeError(f"mvn build timed out after {spec.timeout:.0f}s "
                               "(whole process tree killed)")
        if code != 0:
            raise RuntimeError(f"mvn build failed (exit {code}): " + (out + err).strip()[-1500:])
        jars = [j for j in sorted((source_dir / "target").glob("*.jar"))
                if not any(m in j.name for m in _EXCLUDED_JAR_MARKERS)]
        if not jars:
            raise RuntimeError("mvn build produced no jar under target/")
        return max(jars, key=lambda j: (j.stat().st_size, j.name))
    return _build


def _needs_wrap(code: str) -> bool:
    return _CLASS_DECL_RE.search(_strip_comments(code)) is None


def _class_name_for(code: str) -> str:
    """Java requires a file to be named after its PUBLIC class, if one
    exists -- independent-reviewer finding, fixed here: the original version
    returned the FIRST `class` match regardless of modifier, which silently
    picked a helper class's name (and thus the wrong file/invoked-class
    name) for a block declaring a helper class before its real, public one.
    Comment-stripped first, so a `class X` mention in a comment is never
    mistaken for a declaration."""
    matches = _CLASS_DECL_RE.findall(_strip_comments(code))
    if not matches:
        return "Main"
    for is_public, name in matches:
        if is_public:
            return name
    return matches[0][1]


def _wrap_fragment(code: str) -> str:
    """Independent-reviewer finding, fixed here: the original version
    indented the ENTIRE fragment -- including any leading `import`
    statement -- straight into the generated `main()` method body, which is
    illegal Java (imports must precede the class declaration). Now hoists
    leading `import`/comment lines above the class the same way `GoRunner.
    _wrap_fragment` hoists Go's own leading `import` block, matching the
    real shape of this repo's Quick Start snippets (an import of the
    product's own class, then a few statements using it) -- confirmed live:
    this exact shape (an import line followed by code) is what
    `starts_chain()` itself is designed to recognize as a valid chain
    start.

    Independent-reviewer finding (round 2), fixed here: the first version of
    this hoisting only recognized `//` line comments as skippable preamble
    -- a leading `/* ... */` block comment (which can itself span multiple
    lines) stopped hoisting early, landing the import back inside `main()`.
    `in_block_comment` tracks an open, not-yet-closed `/*` across lines the
    same way a real Java tokenizer would.

    Independent-reviewer finding (round 3), fixed here: the round-2 fix
    unconditionally hoisted an ENTIRE line starting with `/*`, even when
    real code follows the comment's own closing `*/` later on that same
    line (`/* note */ System.out.println("hi");` is ordinary, legal Java
    inside a method body) -- silently dropping that trailing code from the
    generated program instead of treating it as body content. Now checks
    whether anything real follows the closing `*/` on the same line before
    deciding to hoist it."""
    import_lines: list[str] = []
    body_lines: list[str] = []
    past_imports = False
    in_block_comment = False
    for line in code.splitlines():
        stripped = line.strip()
        if not past_imports:
            if in_block_comment:
                import_lines.append(line)
                if "*/" in stripped:
                    in_block_comment = False
                continue
            if stripped.startswith("/*"):
                close_idx = stripped.find("*/", 2)
                if close_idx == -1:
                    import_lines.append(line)
                    in_block_comment = True
                    continue
                if stripped[close_idx + 2:].strip() == "":
                    # The whole line is just a (self-closing) comment.
                    import_lines.append(line)
                    continue
                # Real code follows the comment's own close on this same
                # line -- body content, not hoistable preamble.
                past_imports = True
                body_lines.append(line)
                continue
            if stripped.startswith("//"):
                import_lines.append(line)
                continue
            if stripped.startswith("import ") and stripped.endswith(";"):
                import_lines.append(line)
                continue
            if stripped.startswith("package ") and stripped.endswith(";"):
                continue  # a package decl doesn't apply to the synthetic Main class
            if stripped == "" and not body_lines and not import_lines:
                continue  # skip blank lines before the body starts
            past_imports = True
        body_lines.append(line)

    import_block = ("\n".join(import_lines) + "\n\n") if import_lines else ""
    indented = "\n".join("        " + line for line in body_lines)
    return (
        f"{import_block}"
        "public class Main {\n"
        "    public static void main(String[] args) throws Exception {\n"
        f"{indented}\n"
        "    }\n"
        "}\n"
    )


def _exec_java(argv: list[str], work_dir: Path, timeout: float) -> "tuple[str, str]":
    """("OK"|"FAILED"|"TIMEOUT", combined stdout+stderr)."""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(work_dir), timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", ""
    combined = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return "FAILED", combined.strip()
    return "OK", combined.strip()


class JavaRunner:
    """C12: the third concrete `runners/base.py` `LanguageRunner`
    implementation. One instance = one product (`family` fixed at
    construction, matching `GoRunner`/`DotNetRunner`'s own convention,
    though `family` is unused today -- see the module docstring's disclosed
    scope limit: no real product JAR is acquired yet).

    Disclosed, accepted scope limit on `_wrap_fragment`/`_class_name_for`/
    `_strip_comments` (three independent-review rounds fixed real bugs in
    this area: illegal-import-in-body, wrong-class-name-from-a-helper-
    class, comment-hidden class mentions, block-comment-led imports,
    string-literal-fooled comment stripping, same-line comment-then-code,
    and a text-block-embedded fake class mention): these are line/regex
    -based heuristics, not a real Java grammar parser. They are proven,
    by real content-driven fixes across those three rounds, against every
    *realistic* Quick Start snippet shape encountered so far. They are NOT
    proven against every conceivable Java syntax -- e.g. an annotation on
    the same line as a class declaration (`@Deprecated public class X`),
    records, sealed classes, or a class nested inside another class as the
    FIRST declaration. A genuinely complete fix needs a real tokenizer/
    parser, which is out of scope for this taskcard; further exotic
    failures in this specific area, if a real one is ever found against
    real content, should be fixed the same way these were -- reproduced
    for real, fixed, regression-tested -- not preemptively guessed at."""

    canonical_lang = "java"
    ceiling_tier = 3

    def __init__(
        self, family: str, *,
        toolchain: "tc_mod.JavaToolchain | Callable[[], tc_mod.JavaToolchain] | None" = None,
        product_jar: "str | Path | None" = None,
        product_build: "ProductBuild | None" = None,
        extra_classpath: "Sequence[str | Path]" = (),
        prelude: "Sequence[FixtureSpec] | Callable[[Path], object] | str | None" = None,
    ) -> None:
        if product_jar is not None and product_build is not None:
            raise ValueError("pass product_jar OR product_build, not both")
        self._family = family
        self._toolchain_arg = toolchain
        self._product_jar = Path(product_jar) if product_jar is not None else None
        self._product_build = product_build
        self._extra_classpath = tuple(str(p) for p in extra_classpath)
        self._prelude = prelude
        # Instance-scoped artifact state: the pinned-SHA build runs ONCE per
        # runner instance (BaseRunner calls acquire() per block).
        self._artifact: "dict | None" = None
        self._artifact_error: "str | None" = None
        self._build_root: "Path | None" = None
        self._finalizer: "weakref.finalize | None" = None

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Remove the runner-owned temp build dir (idempotent)."""
        root = self._build_root
        if self._finalizer is not None:
            self._finalizer()           # runs _rmtree_force once (retry + report)
            self._finalizer = None
        self._build_root = None
        if root is not None and root.exists():  # finalizer reported it; do not hide it
            warnings.warn(f"JavaRunner.close(): temp build dir still present: {root}",
                          RuntimeWarning, stacklevel=2)

    def __enter__(self) -> "JavaRunner":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _ensure_build_root(self) -> Path:
        if self._build_root is None:
            self._build_root = Path(tempfile.mkdtemp(prefix="ev-java-build-"))
            self._finalizer = weakref.finalize(self, _rmtree_force, self._build_root)
        return self._build_root

    # -- toolchain / artifact ---------------------------------------------

    def _toolchain(self) -> tc_mod.JavaToolchain:
        arg = self._toolchain_arg
        if arg is None:
            return _default_java_toolchain()
        return arg() if callable(arg) else arg

    def fingerprint(self) -> str:
        """Cache-key component describing the product artifact this runner
        verifies against ("" when it has none, so artifact-less runs keep
        their pre-B6 cache identity)."""
        parts: list[str] = []
        if self._product_jar is not None:
            parts.append(f"jar:{_sha256_file(self._product_jar)}" if self._product_jar.is_file()
                         else "jar:missing")
        elif self._product_build is not None:
            parts.append(f"build:{self._product_build.sha}")
        prelude_fp = self._prelude_fingerprint()
        if prelude_fp:
            parts.append(prelude_fp)
        return "|".join(parts)

    def _prelude_fingerprint(self) -> str:
        """Part of the cache key: a PASS proven with staged fixtures must
        never be served to a runner configured without them (or with
        different ones). Content-based for the default generators and for
        spec lists; for an arbitrary callable, its qualified name plus a hash
        of its bytecode and constants."""
        prelude = self._prelude
        if prelude is None:
            return ""
        h = hashlib.sha256()
        if prelude == "default" or prelude is default_prelude:
            return "prelude:default:" + generators_fingerprint()
        if callable(prelude):
            code = getattr(prelude, "__code__", None)
            h.update(getattr(prelude, "__qualname__", repr(prelude)).encode("utf-8"))
            if code is not None:
                h.update(code.co_code + repr(code.co_consts).encode("utf-8"))
            return "prelude:callable:" + h.hexdigest()[:16]
        for spec in prelude:
            data = spec.content() if callable(spec.content) else spec.content
            h.update(spec.name.encode("utf-8") + b"\0"
                     + (data.encode("utf-8") if isinstance(data, str) else bytes(data)) + b"\0")
        return "prelude:specs:" + h.hexdigest()[:16]

    def _acquire_artifact(self, tc: tc_mod.JavaToolchain) -> "tuple[dict | None, str | None]":
        """(artifact-record-or-None, error-or-None). Built/validated once."""
        if self._artifact is not None or self._artifact_error is not None:
            return self._artifact, self._artifact_error
        if self._product_jar is not None:
            if not self._product_jar.is_file():
                self._artifact_error = f"product_jar not found: {self._product_jar}"
            else:
                self._artifact = {
                    "jar_path": str(self._product_jar),
                    "jar_sha256": _sha256_file(self._product_jar),
                    "source_sha": None, "origin": "prebuilt",
                }
        elif self._product_build is not None:
            self._artifact, self._artifact_error = self._build_pinned(self._product_build, tc)
        return self._artifact, self._artifact_error

    def _build_pinned(self, spec: ProductBuild, tc: tc_mod.JavaToolchain) -> "tuple[dict | None, str | None]":
        clone = Path(spec.clone_path)
        if not clone.is_dir():
            return None, f"product_build clone_path is not a directory: {clone}"
        if shutil.which("git") is None:
            return None, "git is not on PATH; cannot make a temp copy of the pinned SHA"
        build_root = self._ensure_build_root()
        resolved_clone = clone.resolve()
        if resolved_clone == build_root.resolve() or resolved_clone in build_root.resolve().parents:
            return None, "refusing to build: temp build dir would sit inside the clone path"
        if not _HEX_SHA_RE.fullmatch(spec.sha or ""):
            return None, f"product_build sha must be 7-64 hex characters, got {spec.sha!r}"
        src = build_root / f"src-{spec.sha[:12]}"
        ok, out = _run_git(["clone", "--no-checkout", "--no-hardlinks", "-q", "--",
                            str(resolved_clone), str(src)])
        if not ok:
            return None, f"git clone of the pinned clone failed: {out[-800:]}"
        # Hex-validated above (so it cannot look like an option); the trailing
        # `--` makes git treat it as a revision, never a path.
        ok, out = _run_git(["checkout", "-q", "--detach", spec.sha, "--"], cwd=src)
        if not ok:
            return None, f"git checkout {spec.sha} failed (SHA unreachable in the clone?): {out[-800:]}"
        ok, head = _run_git(["rev-parse", "HEAD"], cwd=src)
        if not ok or not head.startswith(spec.sha[:7]) or (len(spec.sha) >= 40 and head != spec.sha):
            return None, f"checked-out HEAD {head!r} does not match pinned SHA {spec.sha!r}"
        build = spec.build_command or _default_mvn_build(spec)
        try:
            jar = Path(build(src, tc))
        except Exception as exc:  # noqa: BLE001 -- surface any build failure as a disclosed acquire failure
            return None, f"product build failed: {exc}"
        if not jar.is_file():
            return None, f"product build reported a jar that does not exist: {jar}"
        return {
            "jar_path": str(jar), "jar_sha256": _sha256_file(jar),
            "source_sha": head, "origin": "built-from-pinned-sha",
            "build": "custom" if spec.build_command else "mvn " + " ".join(spec.mvn_args),
        }, None

    def starts_chain(self, code: str) -> bool:
        """First non-comment line is `import`/`package`/`class` -- the same
        shape Go's chain-start heuristic uses, adapted to Java's own
        compilation-unit structure."""
        for line in code.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            return stripped.startswith(("import ", "package ", "class ", "public class "))
        return True

    def acquire(self, work_dir: Path, policy: Policy, product: ProductContext) -> dict:
        """Discover the toolchain (explicit BLOCKED toolchain outcome if no
        JDK is discoverable) and, when configured, acquire the product jar
        (pre-built, or built from the pinned SHA in a temp copy)."""
        tc = self._toolchain()
        meta: dict = {"toolchain_name": "java", "artifact": {"toolchain": tc.describe()}}
        if tc.jdk is None:
            return {
                "ok": False, "reason": "TOOLCHAIN-UNAVAILABLE", "result_meta": meta,
                "detail": (
                    "BLOCKED_TOOLCHAIN: no JDK >= 11 discoverable (searched PATH, "
                    "JAVA_HOME, roots: " + ", ".join(tc.searched_roots or ("<none configured>",)) + ")"
                ),
            }
        meta["toolchain_version"] = tc.jdk.version
        meta["toolchain_path"] = tc.jdk.javac
        record, error = self._acquire_artifact(tc)
        if error is not None:
            return {"ok": False, "detail": error, "result_meta": meta}
        if record is not None:
            meta["artifact"].update(record)
        return {
            "ok": True, "work_dir": work_dir,
            "java_exe": tc.jdk.java, "javac_exe": tc.jdk.javac, "toolchain_version": tc.jdk.version,
            "product_jar": record["jar_path"] if record else None,
            "result_meta": meta,
        }

    # -- classpath / fixtures ---------------------------------------------

    @staticmethod
    def _classpath(acquired: dict) -> str:
        parts = [str(acquired["work_dir"])]
        if acquired.get("product_jar"):
            parts.append(acquired["product_jar"])
        return os.pathsep.join(parts)

    def _full_classpath(self, acquired: dict) -> str:
        return os.pathsep.join([self._classpath(acquired), *self._extra_classpath])

    def _stage_prelude(self, acquired: dict, code: str = "") -> "list[str]":
        """Materialize the declared prelude into the run's work dir; returns
        the staged relative names (deterministic: declaration order).
        `prelude="default"` (or the `default_prelude` function itself) stages
        generated sample files for exactly the INPUT file names `code` reads
        (fixtures.input_fixture_names); names with no generator stay
        unresolved so the run still ends FIXTURE-UNAVAILABLE."""
        work_dir = Path(acquired["work_dir"])
        staged: list[str] = []
        prelude = self._prelude
        if prelude is None:
            return staged
        if prelude == "default" or prelude is default_prelude:
            prelude = default_prelude(input_fixture_names(code))
        if callable(prelude):
            before = {p.relative_to(work_dir).as_posix() for p in work_dir.rglob("*") if p.is_file()}
            prelude(work_dir)
            after = {p.relative_to(work_dir).as_posix() for p in work_dir.rglob("*") if p.is_file()}
            return sorted(after - before)
        for spec in prelude:
            target = _safe_fixture_path(work_dir, spec.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            data = spec.content() if callable(spec.content) else spec.content
            target.write_bytes(data.encode("utf-8") if isinstance(data, str) else bytes(data))
            staged.append(spec.name)
        return staged

    # -- compile / execute -------------------------------------------------

    def compile(self, acquired: dict, code: str, index: int) -> "dict | None":
        wrapped = _wrap_fragment(code) if _needs_wrap(code) else code
        class_name = _class_name_for(wrapped)
        source_path = acquired["work_dir"] / f"{class_name}.java"
        source_path.write_text(wrapped, encoding="utf-8")
        argv = [acquired["javac_exe"]]
        if acquired.get("product_jar") or self._extra_classpath:
            # An explicit -cp replaces javac's implicit "." default, so the
            # work dir is listed first explicitly.
            argv += ["-cp", self._full_classpath(acquired)]
        argv += ["-d", str(acquired["work_dir"]), str(source_path)]
        outcome, detail = _exec_java(argv, acquired["work_dir"], 30)
        if outcome == "OK":
            return None
        if outcome == "TIMEOUT":
            return {"reason": "TIMEOUT", "detail": "javac timed out"}
        reason, tail = self.classify(detail, {"stage": "compile", "own_file": f"{class_name}.java"})
        return {"reason": reason, "detail": tail}

    def execute(self, acquired: dict, code: str, index: int) -> dict:
        # Independently rewrites+recompiles rather than assuming compile() already ran
        # in this exact call sequence -- the same "each method independently correct"
        # posture GoRunner/DotNetRunner use.
        compile_failure = self.compile(acquired, code, index)
        if compile_failure is not None:
            return {
                "status": "BLOCKED-WITH-REASON",
                "reason": compile_failure["reason"], "detail": compile_failure["detail"],
            }
        wrapped = _wrap_fragment(code) if _needs_wrap(code) else code
        class_name = _class_name_for(wrapped)
        staged = self._stage_prelude(acquired, code)
        meta = acquired.get("result_meta")
        if meta is not None and staged:
            meta["artifact"]["fixtures_staged"] = staged
        outcome, detail = _exec_java(
            [acquired["java_exe"], "-cp", self._full_classpath(acquired), class_name],
            acquired["work_dir"], 30,
        )
        if outcome == "OK":
            return {"status": "PASS"}
        if outcome == "TIMEOUT":
            return {"status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT", "detail": "java timed out"}
        missing = _missing_input(detail)
        if missing is not None and _is_expected_input(missing, set(input_fixture_names(code)) | set(staged)):
            # Compiled fine, but an input file the example opens was not
            # provided by any prelude: disclosed compile-only, never a pass.
            return {
                "status": "BLOCKED-WITH-REASON", "reason": "FIXTURE-UNAVAILABLE",
                "proof_tier": 2,
                "detail": (f"compiled OK but not run to completion: input file {missing!r} "
                           f"is not provided by any prelude (staged: {staged or 'none'})"),
            }
        reason, tail = self.classify(detail, {"stage": "execute", "own_file": f"{class_name}.java"})
        return {"status": "BLOCKED-WITH-REASON", "reason": reason, "detail": tail}

    def classify(self, output: str, context: "dict | None" = None) -> "tuple[str, str]":
        """Distinguishes a real defect in a referenced class's own source
        (the compile error or stack frame cites a `.java` file whose
        basename isn't the block's own generated class file) from an
        ordinary COMPILE-ERROR/RUNTIME-ERROR in that generated wrapper --
        the same file-citation-basename design `GoRunner`/`DotNetRunner`
        use, for the same reason confirmed by their own independent
        reviews: a raw dependency-path substring match does not appear
        verbatim in real `javac`/`java` output. Two distinct real formats
        (confirmed via a manual probe before writing this): `javac`'s own
        `<file>.java:<line>:` and a stack frame's `(<file>.java:<line>)`.

        `context["own_file"]` is the exact `{class_name}.java` `compile()`/
        `execute()` just wrote and invoked -- NOT a fixed constant like Go's
        `main.go`/`.NET`'s `Program.cs`, since a block that's already a
        complete `class X` declaration keeps its own name (see
        `_class_name_for`)."""
        tail = (output or "").strip()[-2000:]
        own_file = (context or {}).get("own_file", "Main.java")
        locations = (
            _JAVAC_LOCATION_RE.findall(tail) + _JAVA_STACK_LOCATION_RE.findall(tail)
        )
        cites_other_file = any(Path(loc).name != own_file for loc in locations)
        if cites_other_file:
            return "UPSTREAM-BROKEN", tail
        stage = (context or {}).get("stage", "compile")
        return ("COMPILE-ERROR" if stage == "compile" else "RUNTIME-ERROR"), tail
