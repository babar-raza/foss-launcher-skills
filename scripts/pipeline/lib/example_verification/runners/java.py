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

Disclosed scope limit (matching `GoRunner`'s and `DotNetRunner`'s own
precedent): only a BCL/stdlib-only `javac`/`java` compile+run path is
implemented here -- no real product JAR is acquired via `mvn package`
(`acquire()` never puts anything but the block's own generated `Main.java`
on the classpath). The plan's own "Known extra wrinkle" -- Maven's first
build resolving its own build plugins over the network even for a trivial
project, requiring real fixture engineering (an offline-installable local
Maven mirror) to test safely -- is real, substantial, separable work,
parallel to how C5/C11 each deferred their own "acquire a real product's
build artifact" branch (Go's `go get`, .NET's `dotnet add package`). No
`java_offline_mirror` fixture is created this iteration for the same
reason: there is nothing yet that needs one. `mvn` is used ONLY for
toolchain discovery here (a single, fast, offline `-version` call), never
to build or resolve a dependency.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ..policy import Policy, ProductContext

_MVN_VERSION_RE = re.compile(r'Java version:\s*([\d.]+).*?runtime:\s*(.+)', re.IGNORECASE)

# A real javac compile error's own file:line citation, e.g.
# "Main.java:3: error: cannot find symbol". Confirmed via a real javac call.
_JAVAC_LOCATION_RE = re.compile(r'([\w./\\-]+\.java):\d+:')
# A real uncaught-exception stack frame's own citation, e.g.
# "at Main.main(Main.java:3)". Confirmed via a real java call.
_JAVA_STACK_LOCATION_RE = re.compile(r'\(([\w./\\-]+\.java):\d+\)')

_CLASS_DECL_RE = re.compile(r'^\s*(?:public\s+)?(?:final\s+)?class\s+(\w+)', re.MULTILINE)


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


def _needs_wrap(code: str) -> bool:
    return _CLASS_DECL_RE.search(code) is None


def _class_name_for(code: str) -> str:
    m = _CLASS_DECL_RE.search(code)
    return m.group(1) if m else "Main"


def _wrap_fragment(code: str) -> str:
    indented = "\n".join("        " + line for line in code.splitlines())
    return (
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
    scope limit: no real product JAR is acquired yet)."""

    canonical_lang = "java"
    ceiling_tier = 3

    def __init__(self, family: str) -> None:
        self._family = family

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
        """Real toolchain discovery (see `_discover_java_toolchain`) is the
        only genuinely fallible step here -- no real product JAR is put on
        the classpath (disclosed scope limit, module docstring), so there is
        no dependency-resolution step that could fail the way Go's/`.NET`'s
        real acquire steps can."""
        toolchain = _discover_java_toolchain()
        if toolchain is None:
            return {"ok": False, "detail": "could not discover a Java toolchain via `mvn -version`"}
        java_exe, javac_exe, version = toolchain
        return {
            "ok": True, "work_dir": work_dir,
            "java_exe": java_exe, "javac_exe": javac_exe, "toolchain_version": version,
        }

    def compile(self, acquired: dict, code: str, index: int) -> "dict | None":
        wrapped = _wrap_fragment(code) if _needs_wrap(code) else code
        class_name = _class_name_for(wrapped)
        source_path = acquired["work_dir"] / f"{class_name}.java"
        source_path.write_text(wrapped, encoding="utf-8")
        outcome, detail = _exec_java(
            [acquired["javac_exe"], "-d", str(acquired["work_dir"]), str(source_path)],
            acquired["work_dir"], 30,
        )
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
        outcome, detail = _exec_java(
            [acquired["java_exe"], "-cp", str(acquired["work_dir"]), class_name],
            acquired["work_dir"], 30,
        )
        if outcome == "OK":
            return {"status": "PASS"}
        if outcome == "TIMEOUT":
            return {"status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT", "detail": "java timed out"}
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
