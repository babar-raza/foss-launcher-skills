"""
lib/example_verification/toolchain.py

CONTRACT: scripts/pipeline/lib/example_verification/toolchain.py
  purpose: shared toolchain discovery for every runner (rollout step C3
           onward), including the two real runners (python/typescript)
           once C3 retrofits them -- instead of each runner growing its
           own PATH-probing logic. Covers the one gotcha already proven
           live in this repo (`_resolve_node_bin` in readme_refresh_run.py:
           `subprocess.run(["npm", ...])` raises WinError 2 on Windows
           without `shutil.which` resolving the real `.cmd` shim path --
           confirmed live, not a hypothetical) and the one genuinely new
           discovery step no runner has needed yet: MSVC's `cl.exe`,
           which is deliberately not on PATH outside a Developer Command
           Prompt.
  inputs:  a tool name (e.g. "dotnet", "java", "mvn", "cl")
  outputs: find() / version_of() / msvc_env() / maven_java_version() /
           exec_env() / fingerprint()
  owner_domain: content-quality

Every discovery result is cached in-process (confirmed live once per
process, not once per call) and is meant to be recorded into a block's
result (`toolchain_path`, `toolchain_version`) so a `TOOLCHAIN-UNAVAILABLE`
on a machine that genuinely lacks a toolchain is visibly different from
one caused by a discovery bug -- this module changes how reliably a
present toolchain is found, not the honesty contract for a genuinely
absent one (see result.py's REASONS vocabulary, which this module never
touches).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

_FIND_CACHE: dict[str, "str | None"] = {}
_VERSION_CACHE: dict[str, "str | None"] = {}
_MSVC_ENV_CACHE: "dict[str, str] | None | bool" = False  # False = not yet attempted


def find(name: str) -> "str | None":
    """Resolve `name` on PATH via `shutil.which`, unconditionally -- the
    same fix `_resolve_node_bin` already proved necessary for npm/npx on
    Windows (a bare `subprocess.run(["npm", ...])` raises WinError 2
    without it, since CreateProcess does not resolve PATHEXT the way a
    shell does). A no-op path-through on POSIX, where these are already
    real executables/symlinks -- correct to call unconditionally, not a
    Windows-only special case.

    MT074 B6: when `name` is one of the JVM-toolchain executables
    (`java`, `javac`, `jar`, `mvn`) and is NOT on PATH, fall back to the
    bounded discovery in `discover_java_toolchain()` (JAVA_HOME /
    MAVEN_HOME / configured search roots). PATH still wins whenever the
    tool is on it -- semantics for a PATH-resident tool are unchanged. Use
    `find_with_source()` to learn WHERE a tool was found."""
    return find_with_source(name)[0]


def find_with_source(name: str) -> "tuple[str | None, str]":
    """(path-or-None, source) where source is "path", "env:JAVA_HOME",
    "env:MAVEN_HOME", "env:M2_HOME", "root:<dir>" or "none". Cached
    in-process like `find()`."""
    if name not in _FIND_CACHE:
        _FIND_CACHE[name] = shutil.which(name)
        _FIND_SOURCE_CACHE[name] = "path" if _FIND_CACHE[name] else "none"
        if _FIND_CACHE[name] is None and name in _JVM_TOOLS:
            discovered = _discovered_tool_path(name)
            if discovered is not None:
                _FIND_CACHE[name], _FIND_SOURCE_CACHE[name] = discovered
    return _FIND_CACHE[name], _FIND_SOURCE_CACHE.get(name, "none")


_FIND_SOURCE_CACHE: dict[str, str] = {}
_JVM_TOOLS = frozenset({"java", "javac", "jar", "mvn"})


def _discovered_tool_path(name: str) -> "tuple[str, str] | None":
    tc = discover_java_toolchain()
    if name == "mvn":
        return (tc.maven.mvn, tc.maven.source) if tc.maven else None
    if tc.jdk is None:
        return None
    path = {"java": tc.jdk.java, "javac": tc.jdk.javac, "jar": tc.jdk.jar}[name]
    return (path, tc.jdk.source) if path else None


# (tool name, version-flag, regex to pull the version string out of the
# combined stdout+stderr). Kept as one table instead of one function per
# tool -- every one of these follows the same "<tool> --version"-ish shape.
_VERSION_PROBES: dict[str, tuple[str, "re.Pattern[str]"]] = {
    "dotnet": ("--version", re.compile(r"^\s*([\d.]+)", re.MULTILINE)),
    "java": ("-version", re.compile(r'version "([\d._]+)"')),
    "mvn": ("-version", re.compile(r"Apache Maven ([\d.]+)")),
    "go": ("version", re.compile(r"go version go([\d.]+)")),
    "cargo": ("--version", re.compile(r"cargo ([\d.]+)")),
    "rustc": ("--version", re.compile(r"rustc ([\d.]+)")),
    "cmake": ("--version", re.compile(r"cmake version ([\d.]+)")),
    "ninja": ("--version", re.compile(r"^([\d.]+)")),
    "node": ("--version", re.compile(r"v([\d.]+)")),
    "npm": ("--version", re.compile(r"([\d.]+)")),
}


def version_of(name: str) -> "str | None":
    """Best-effort version string for a tool already found on PATH. Never
    raises -- an unparseable or crashing probe just means an unknown
    version, not a discovery failure (the tool itself may still work)."""
    if name in _VERSION_CACHE:
        return _VERSION_CACHE[name]
    path = find(name)
    probe = _VERSION_PROBES.get(name)
    if path is None or probe is None:
        _VERSION_CACHE[name] = None
        return None
    flag, pattern = probe
    try:
        result = subprocess.run(
            [path, flag], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        _VERSION_CACHE[name] = None
        return None
    combined = (result.stdout or "") + (result.stderr or "")
    m = pattern.search(combined)
    version = m.group(1) if m else None
    _VERSION_CACHE[name] = version
    return version


def maven_java_version() -> "str | None":
    """The JDK Maven itself resolves and builds against -- confirmed on
    this machine to differ from whichever `java` happens to be on PATH
    (Maven 3.9.16 here resolves its own JDK 17.0.19, a different JDK than
    the `java` found on PATH). A Java runner must record THIS version as
    what it actually built against, not the separate `java` on PATH."""
    mvn = find("mvn")
    if mvn is None:
        return None
    try:
        result = subprocess.run(
            [mvn, "-version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
            # MT074 B6: a discovered (not-on-PATH) Maven needs JAVA_HOME.
            env=java_exec_env(discover_java_toolchain()),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    combined = (result.stdout or "") + (result.stderr or "")
    m = re.search(r"Java version:\s*([\d._]+)", combined)
    return m.group(1) if m else None


@dataclass(frozen=True, slots=True)
class MsvcEnv:
    installation_path: str
    env: dict[str, str]


def _find_vswhere() -> "str | None":
    # The standard, fixed install location vswhere.exe always uses --
    # confirmed present at this exact path on this machine.
    standard = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    from pathlib import Path
    if Path(standard).is_file():
        return standard
    return find("vswhere")


def msvc_env() -> "MsvcEnv | None":
    """Locate the MSVC install via `vswhere.exe -latest -property
    installationPath`, then capture the real build environment by running
    `vcvarsall.bat x64` and parsing the resulting `set` output -- exactly
    what Visual Studio's own Developer Command Prompt does at launch, not
    a new invention. `cl.exe` is deliberately not on PATH outside that
    prompt, so this is the one genuinely new discovery step no existing
    runner in this repo has needed. Cached process-wide (a real subprocess
    call plus environment capture is not something to repeat per block).
    Returns None if vswhere, the installation, or vcvarsall itself can't
    be found or fails -- never raises."""
    global _MSVC_ENV_CACHE
    if _MSVC_ENV_CACHE is not False:
        return _MSVC_ENV_CACHE  # type: ignore[return-value]

    _MSVC_ENV_CACHE = None
    vswhere = _find_vswhere()
    if vswhere is None:
        return None
    try:
        result = subprocess.run(
            [vswhere, "-latest", "-property", "installationPath"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    installation_path = (result.stdout or "").strip()
    if not installation_path:
        return None

    from pathlib import Path
    vcvarsall = Path(installation_path) / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if not vcvarsall.is_file():
        return None
    try:
        captured = subprocess.run(
            ["cmd", "/c", f'call "{vcvarsall}" x64 && set'],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if captured.returncode != 0:
        return None

    env: dict[str, str] = {}
    for line in (captured.stdout or "").splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key:
            env[key] = value

    _MSVC_ENV_CACHE = MsvcEnv(installation_path=installation_path, env=env)
    return _MSVC_ENV_CACHE


# ---------------------------------------------------------------------------
# MT074 B6 -- bounded JDK / Maven discovery (R8: the Java runner reported
# TOOLCHAIN-UNAVAILABLE on a machine whose JDK 17/21 and Maven live under
# D:\Program Files\Eclipse Adoptium and D:\tools but are not on PATH).
#
# Precedence, per tool: PATH (unchanged legacy semantics) -> the tool's own
# env var (JAVA_HOME | MAVEN_HOME, M2_HOME) -> an ORDERED list of search
# roots (ASPOSE_TOOLCHAIN_ROOTS entries first so an operator override wins,
# then sane per-OS defaults). Roots are scanned in order and the FIRST root
# holding any acceptable install wins; inside that root the newest LTS JDK
# (11/17/21/25, >= 11) is chosen (newest non-LTS >= 11 only if the root has
# no LTS) -- but the ordered PREFERRED majors (default 21, 17, 11, override
# ASPOSE_JDK_PREFERRED_MAJORS) are tried first, so a very new LTS (25) never
# beats an older one that Maven plugins are known to work with. Only a root's DIRECT children are inspected (bounded: at most
# _MAX_ROOT_CHILDREN per root, no recursion). Every result records its
# discovery SOURCE so a toolchain miss is distinguishable from a discovery
# bug.
# ---------------------------------------------------------------------------

ENV_ROOTS_VAR = "ASPOSE_TOOLCHAIN_ROOTS"
# Ordered JDK majors preferred BEFORE any newer one (a brand-new LTS such as
# 25 can be too new for older Maven plugins). Override with a comma-separated
# list in ASPOSE_JDK_PREFERRED_MAJORS, e.g. "17,21". A root that holds none
# of them falls back to its newest LTS, then its newest JDK >= 11.
ENV_PREFERRED_MAJORS_VAR = "ASPOSE_JDK_PREFERRED_MAJORS"
DEFAULT_PREFERRED_MAJORS = (21, 17, 11)
_LTS_MAJORS = frozenset({11, 17, 21, 25})
_MIN_JDK_MAJOR = 11
_MAX_ROOT_CHILDREN = 200


@dataclass(frozen=True, slots=True)
class JdkInfo:
    home: str
    java: str
    javac: str
    jar: "str | None"
    version: str
    major: int
    source: str


@dataclass(frozen=True, slots=True)
class MavenInfo:
    home: str
    mvn: str
    version: "str | None"
    source: str


@dataclass(frozen=True, slots=True)
class JavaToolchain:
    jdk: "JdkInfo | None"
    maven: "MavenInfo | None"
    searched_roots: tuple = ()

    def describe(self) -> dict:
        """Flat, JSON-safe record of what was discovered and from where --
        what a runner stores into each BlockResult."""
        return {
            "jdk_path": self.jdk.javac if self.jdk else None,
            "jdk_home": self.jdk.home if self.jdk else None,
            "jdk_version": self.jdk.version if self.jdk else None,
            "jdk_source": self.jdk.source if self.jdk else "none",
            "maven_path": self.maven.mvn if self.maven else None,
            "maven_version": self.maven.version if self.maven else None,
            "maven_source": self.maven.source if self.maven else "none",
        }


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def _mvn_name() -> str:
    return "mvn.cmd" if os.name == "nt" else "mvn"


def default_search_roots() -> "list[Path]":
    if os.name == "nt":
        return [
            Path(r"C:\Program Files\Eclipse Adoptium"),
            Path(r"D:\Program Files\Eclipse Adoptium"),
            Path(r"C:\Program Files\Java"),
            Path(r"D:\Program Files\Java"),
            Path(r"C:\Program Files\Microsoft"),
            Path(r"C:\tools"),
            Path(r"D:\tools"),
        ]
    return [Path("/usr/lib/jvm"), Path("/usr/local/lib/jvm"), Path("/opt")]


def search_roots(env: "Mapping[str, str] | None" = None) -> "list[Path]":
    """Ordered, de-duplicated search roots: `ASPOSE_TOOLCHAIN_ROOTS`
    (os.pathsep-separated) first, then the per-OS defaults."""
    env = os.environ if env is None else env
    roots: list[Path] = []
    for entry in (env.get(ENV_ROOTS_VAR) or "").split(os.pathsep):
        entry = entry.strip()
        if entry:
            roots.append(Path(entry))
    roots.extend(default_search_roots())
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = os.path.normcase(str(r))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _version_tuple(version: "str | None") -> tuple:
    if not version:
        return ()
    return tuple(int(p) for p in re.findall(r"\d+", version.split("+")[0]))


def _major_of(version: "str | None") -> int:
    parts = _version_tuple(version)
    if not parts:
        return 0
    # Legacy "1.8.0_292" style: the major is the second component.
    return parts[1] if parts[0] == 1 and len(parts) > 1 else parts[0]


def _release_version(home: Path) -> "str | None":
    try:
        text = (home / "release").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r'^JAVA_VERSION="?([^"\r\n]+)"?', text, re.MULTILINE)
    return m.group(1) if m else None


def _jdk_from_home(home: Path, source: str) -> "JdkInfo | None":
    java = home / "bin" / _exe("java")
    javac = home / "bin" / _exe("javac")
    if not (java.is_file() and javac.is_file()):
        return None
    version = _release_version(home)
    if version is None:
        m = re.search(r"(\d+(?:\.\d+)*)", home.name)
        version = m.group(1) if m else None
    if version is None:
        return None
    jar = home / "bin" / _exe("jar")
    return JdkInfo(
        home=str(home), java=str(java), javac=str(javac),
        jar=str(jar) if jar.is_file() else None,
        version=version, major=_major_of(version), source=source,
    )


def preferred_majors(env: "Mapping[str, str] | None" = None) -> "tuple[int, ...]":
    """The ordered preferred-JDK-major list: ASPOSE_JDK_PREFERRED_MAJORS
    (comma-separated; non-numeric entries ignored) or the default 21, 17, 11."""
    env = os.environ if env is None else env
    raw = (env.get(ENV_PREFERRED_MAJORS_VAR) or "").strip()
    parsed = tuple(int(p) for p in re.findall(r"\d+", raw))
    return parsed or DEFAULT_PREFERRED_MAJORS


def _best_jdk(candidates: "list[JdkInfo]", preferred: "Sequence[int]" = DEFAULT_PREFERRED_MAJORS) -> "JdkInfo | None":
    """Selection inside one root: the newest JDK of the first preferred major
    that is present; else the newest LTS >= 11; else the newest JDK >= 11."""
    usable = [c for c in candidates if c.major >= _MIN_JDK_MAJOR]
    if not usable:
        return None

    def newest(pool: "list[JdkInfo]") -> JdkInfo:
        return max(pool, key=lambda c: (_version_tuple(c.version), c.home))

    for major in preferred:
        of_major = [c for c in usable if c.major == major]
        if of_major:
            return newest(of_major)
    lts = [c for c in usable if c.major in _LTS_MAJORS]
    return newest(lts or usable)


def _children(root: Path) -> "list[Path]":
    try:
        kids = [c for c in root.iterdir() if c.is_dir()]
    except OSError:
        return []
    return sorted(kids, key=lambda p: p.name)[:_MAX_ROOT_CHILDREN]


def discover_jdk(
    *, env: "Mapping[str, str] | None" = None, roots: "list[Path] | None" = None,
    which: "Callable[[str], str | None] | None" = None,
    preferred: "Sequence[int] | None" = None,
) -> "JdkInfo | None":
    """PATH `javac` (>= 11) -> JAVA_HOME -> ordered roots. See the section
    comment above for the full precedence/selection rule. `preferred`
    (default: preferred_majors(env)) orders the majors tried first inside a
    root; PATH and JAVA_HOME are explicit choices and ignore it."""
    env = os.environ if env is None else env
    preferred = preferred_majors(env) if preferred is None else tuple(preferred)
    which = shutil.which if which is None else which
    on_path = which("javac")
    if on_path:
        try:
            home = Path(on_path).resolve().parent.parent
        except OSError:
            home = Path(on_path).parent.parent
        jdk = _jdk_from_home(home, "path")
        if jdk is not None and jdk.major >= _MIN_JDK_MAJOR:
            return jdk
    java_home = (env.get("JAVA_HOME") or "").strip()
    if java_home:
        jdk = _jdk_from_home(Path(java_home), "env:JAVA_HOME")
        if jdk is not None and jdk.major >= _MIN_JDK_MAJOR:
            return jdk
    for root in (search_roots(env) if roots is None else roots):
        found: list[JdkInfo] = []
        own = _jdk_from_home(root, f"root:{root}")
        if own is not None:
            found.append(own)
        for child in _children(root):
            jdk = _jdk_from_home(child, f"root:{root}")
            if jdk is not None:
                found.append(jdk)
        best = _best_jdk(found, preferred)
        if best is not None:
            return best
    return None


def _maven_from_home(home: Path, source: str) -> "MavenInfo | None":
    mvn = home / "bin" / _mvn_name()
    if not mvn.is_file():
        return None
    m = re.search(r"maven-(\d+(?:\.\d+)*)", home.name)
    version = m.group(1) if m else None
    if version is None:
        try:
            for jar in sorted((home / "lib").glob("maven-core-*.jar")):
                mm = re.search(r"maven-core-(\d+(?:\.\d+)*)", jar.name)
                if mm:
                    version = mm.group(1)
                    break
        except OSError:
            version = None
    return MavenInfo(home=str(home), mvn=str(mvn), version=version, source=source)


def discover_maven(
    *, env: "Mapping[str, str] | None" = None, roots: "list[Path] | None" = None,
    which: "Callable[[str], str | None] | None" = None,
) -> "MavenInfo | None":
    """PATH `mvn` -> MAVEN_HOME -> M2_HOME -> ordered roots (a root's direct
    children named `*maven*`)."""
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    on_path = which("mvn")
    if on_path:
        try:
            home = Path(on_path).resolve().parent.parent
        except OSError:
            home = Path(on_path).parent.parent
        info = _maven_from_home(home, "path")
        return info if info is not None else MavenInfo(
            home=str(Path(on_path).parent.parent), mvn=on_path, version=None, source="path")
    for var in ("MAVEN_HOME", "M2_HOME"):
        value = (env.get(var) or "").strip()
        if value:
            info = _maven_from_home(Path(value), f"env:{var}")
            if info is not None:
                return info
    for root in (search_roots(env) if roots is None else roots):
        found: list[MavenInfo] = []
        for child in _children(root):
            if "maven" in child.name.lower():
                info = _maven_from_home(child, f"root:{root}")
                if info is not None:
                    found.append(info)
        if found:
            return max(found, key=lambda i: (_version_tuple(i.version), i.home))
    return None


_JAVA_TC_CACHE: "JavaToolchain | None" = None


def discover_java_toolchain(
    *, env: "Mapping[str, str] | None" = None, roots: "list[Path] | None" = None,
    which: "Callable[[str], str | None] | None" = None,
) -> JavaToolchain:
    """JDK + Maven discovery. Called with no arguments the result is cached
    in-process (a real filesystem scan is not something to repeat per
    block); any explicit argument bypasses the cache (test seam)."""
    global _JAVA_TC_CACHE
    explicit = env is not None or roots is not None or which is not None
    if not explicit and _JAVA_TC_CACHE is not None:
        return _JAVA_TC_CACHE
    resolved_roots = search_roots(env) if roots is None else list(roots)
    tc = JavaToolchain(
        jdk=discover_jdk(env=env, roots=resolved_roots, which=which),
        maven=discover_maven(env=env, roots=resolved_roots, which=which),
        searched_roots=tuple(str(r) for r in resolved_roots),
    )
    if not explicit:
        _JAVA_TC_CACHE = tc
    return tc


def java_exec_env(tc: JavaToolchain, extra: "dict[str, str] | None" = None) -> "dict[str, str]":
    """`exec_env()` plus what a Maven/JDK invocation needs when the tools are
    discovered rather than on PATH: JAVA_HOME and the JDK/Maven bin dirs
    prepended to PATH."""
    env = exec_env()
    prepend: list[str] = []
    if tc.jdk is not None:
        env["JAVA_HOME"] = tc.jdk.home
        prepend.append(str(Path(tc.jdk.javac).parent))
    if tc.maven is not None:
        prepend.append(str(Path(tc.maven.mvn).parent))
    if prepend:
        env["PATH"] = os.pathsep.join([*prepend, env.get("PATH", "")])
    if extra:
        env.update(extra)
    return env


def exec_env(allowlist: "frozenset[str] | None" = None, extra: "dict[str, str] | None" = None) -> dict[str, str]:
    """Build the environment dict for an executed code block: only
    allow-listed variables from the real process environment (Round 3 H --
    never this repo's own PYTHONPATH), plus any tool-specific vars a
    caller supplies (e.g. an MsvcEnv's captured INCLUDE/LIB/PATH). `extra`
    always wins over the base environment on key collision."""
    import os
    from .policy import DEFAULT_ENV_ALLOWLIST
    keys = allowlist if allowlist is not None else DEFAULT_ENV_ALLOWLIST
    env = {k: v for k, v in os.environ.items() if k in keys}
    if extra:
        env.update(extra)
    return env


def fingerprint(name: str) -> str:
    """A short, stable string identifying the discovered toolchain for
    `name`, for cache.py's cache_key() `toolchain_fp` component: `"{name}@
    {version}"`, or `"{name}@unavailable"` if not found -- deliberately
    still a distinct, stable string in the unavailable case, so a cache
    entry computed while a toolchain was missing never collides with one
    computed after it becomes available."""
    version = version_of(name)
    return f"{name}@{version}" if version else f"{name}@unavailable"
