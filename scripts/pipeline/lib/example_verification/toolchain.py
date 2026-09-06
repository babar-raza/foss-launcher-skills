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

import re
import shutil
import subprocess
from dataclasses import dataclass

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
    Windows-only special case."""
    if name not in _FIND_CACHE:
        _FIND_CACHE[name] = shutil.which(name)
    return _FIND_CACHE[name]


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
