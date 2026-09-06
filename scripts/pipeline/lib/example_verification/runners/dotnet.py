"""
lib/example_verification/runners/dotnet.py

CONTRACT: scripts/pipeline/lib/example_verification/runners/dotnet.py
  purpose: C11 (MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION) -- the
           .NET `LanguageRunner` (runners/base.py protocol): real `dotnet
           build` (tier 2) -> real `dotnet run` (tier 3). The second concrete
           `LanguageRunner` implementation after C5's `GoRunner`, following
           the same design conventions (instance-scoped state, no shared
           mutable globals; a file-citation-basename check in `classify()`
           rather than a raw-path substring match -- see GoRunner's own
           independent-review history for why the substring approach is
           unreliable against real compiler output).
  inputs:  a fenced ```csharp code block's raw text (top-level statements,
           matching this repo's real Quick Start snippet convention -- see
           the governing plan's ".NET" language-runner notes); a .NET
           product's family name
  outputs: DotNetRunner, a `runners/base.py.LanguageRunner`
  owner_domain: content-quality

Disclosed scope limit (matching GoRunner's own precedent): only the
unpublished/local-reference acquire path (`dotnet add reference` against a
`_select_main_csproj`-selected project from `runs/.clone_cache/`) is
implemented. The plan's `published: dotnet add package {name} --version {v}`
(a real NuGet resolve) branch is not built -- there is no fixture to prove
that path against without inventing one, and no real product in this
portfolio needs it for offline-installable stdlib-only test coverage. A
block with no product dependency at all (pure BCL, e.g. `Console.WriteLine`)
needs no reference and works regardless.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ..policy import clone_cache_path, Policy, ProductContext

# ---------------------------------------------------------------------------
# _select_main_csproj -- ported from dependency_extract.py, not imported
# ---------------------------------------------------------------------------
# scripts/pipeline/commands/foss/dependency_extract.py:_select_main_csproj's own
# docstring says this exact heuristic is "reimplemented locally (not imported)"
# there too -- following that repo-established convention rather than importing
# a content-extraction-scoped module from this shared verification package.
# "Shortest-path csproj wins," excluding test-named projects, preferring
# non-Exe output -- the real fix for words/net's 4 same-depth top-level
# .csproj files (Aspose.Words, .Tests, .TestFx, .JavaMs.Tests) picking a test
# project purely by sort order.

_TEST_CSPROJ_STEM_RE = re.compile(r"test", re.IGNORECASE)
_CSPROJ_EXE_OUTPUT_RE = re.compile(r"<OutputType>\s*Exe\s*</OutputType>", re.IGNORECASE)


def _select_main_csproj(repo_root: Path) -> "Path | None":
    all_csproj = sorted(
        repo_root.rglob("*.csproj"), key=lambda p: len(p.relative_to(repo_root).parts)
    )
    if not all_csproj:
        return None
    non_test = [p for p in all_csproj if not _TEST_CSPROJ_STEM_RE.search(p.stem)]
    candidates = non_test if non_test else all_csproj
    non_exe = [
        p for p in candidates
        if not _CSPROJ_EXE_OUTPUT_RE.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    return non_exe[0] if non_exe else candidates[0]


# ---------------------------------------------------------------------------
# Real dotnet execution plumbing
# ---------------------------------------------------------------------------

# A real MSBuild diagnostic's own file:line,col citation, e.g.
# "C:\...\Program.cs(1,19): error CS0103: ...". Never `:line` like Go --
# confirmed via a real build, not guessed.
_DOTNET_BUILD_LOCATION_RE = re.compile(r'([^\s()]+\.cs)\(\d+,\d+\)')
# A real unhandled-exception stack frame's own citation, e.g.
# "... in C:\...\Program.cs:line 2". Confirmed via a real `dotnet run` crash.
_DOTNET_RUNTIME_LOCATION_RE = re.compile(r'in ([^\s()]+\.cs):line \d+')


def _exec_dotnet(argv: list[str], work_dir: Path, timeout: float) -> "tuple[str, str]":
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


class DotNetRunner:
    """C11: the second concrete `runners/base.py` `LanguageRunner`
    implementation. One instance = one product (`family` fixed at
    construction, matching `GoRunner`'s own convention)."""

    canonical_lang = "csharp"
    ceiling_tier = 3

    def __init__(self, family: str) -> None:
        self._family = family

    def starts_chain(self, code: str) -> bool:
        """First non-comment line is `using` -- this repo's real Quick Start
        snippets are top-level-statement C# programs, each self-contained
        example beginning with its own `using` directives (per the governing
        plan's own ".NET" language-runner notes)."""
        for line in code.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            return stripped.startswith("using ")
        return True

    def acquire(self, work_dir: Path, policy: Policy, product: ProductContext) -> dict:
        """Real acquire, unlike Go's: `dotnet new console` genuinely
        scaffolds a project and can genuinely fail (a real environment-setup
        step, the same risk class as Python's real venv creation), so this
        reports `{"ok": False}` when the toolchain is missing or scaffolding
        fails -- there is no cheaper, string-only equivalent to Go's always-
        succeeds design. `dotnet add reference` against this product's own
        main csproj (resolved from its real clone cache) is attempted but
        NOT required to succeed: a pure-BCL block needs no reference at all,
        matching `GoRunner.acquire()`'s "a missing dependency isn't an
        acquire failure" posture."""
        dotnet_exe = shutil.which("dotnet")
        if dotnet_exe is None:
            return {"ok": False, "detail": "dotnet not found on PATH"}

        outcome, detail = _exec_dotnet(
            [dotnet_exe, "new", "console", "--no-restore", "-o", str(work_dir)], work_dir, 30,
        )
        if outcome != "OK":
            return {"ok": False, "detail": f"dotnet new console failed: {detail[-500:]}"}

        csproj_files = list(work_dir.glob("*.csproj"))
        if not csproj_files:
            return {"ok": False, "detail": "dotnet new console produced no .csproj"}
        project_csproj = csproj_files[0]

        reference_path = None
        clone_dir = clone_cache_path(self._family, "net")
        if clone_dir.is_dir():
            main_csproj = _select_main_csproj(clone_dir)
            if main_csproj is not None:
                ref_outcome, _ref_detail = _exec_dotnet(
                    [dotnet_exe, "add", str(project_csproj), "reference", str(main_csproj)],
                    work_dir, 30,
                )
                if ref_outcome == "OK":
                    reference_path = str(main_csproj)

        return {
            "ok": True, "work_dir": work_dir, "dotnet_exe": dotnet_exe,
            "program_cs": work_dir / "Program.cs", "reference_path": reference_path,
        }

    def compile(self, acquired: dict, code: str, index: int) -> "dict | None":
        acquired["program_cs"].write_text(code, encoding="utf-8")
        outcome, detail = _exec_dotnet(
            [acquired["dotnet_exe"], "build", "--nologo"], acquired["work_dir"], 60,
        )
        if outcome == "OK":
            return None
        if outcome == "TIMEOUT":
            return {"reason": "TIMEOUT", "detail": "dotnet build timed out"}
        reason, tail = self.classify(detail, {"stage": "compile"})
        return {"reason": reason, "detail": tail}

    def execute(self, acquired: dict, code: str, index: int) -> dict:
        # Independently rewrites+rebuilds rather than assuming compile() already ran
        # in this exact call sequence -- the same "each method independently correct"
        # posture GoRunner's execute() uses, even though BaseRunner._climb always
        # calls compile() first in practice.
        acquired["program_cs"].write_text(code, encoding="utf-8")
        build_outcome, build_detail = _exec_dotnet(
            [acquired["dotnet_exe"], "build", "--nologo"], acquired["work_dir"], 60,
        )
        if build_outcome == "TIMEOUT":
            return {"status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT", "detail": "dotnet build timed out"}
        if build_outcome != "OK":
            reason, tail = self.classify(build_detail, {"stage": "compile"})
            return {"status": "BLOCKED-WITH-REASON", "reason": reason, "detail": tail}

        outcome, detail = _exec_dotnet(
            [acquired["dotnet_exe"], "run", "--no-build"], acquired["work_dir"], 60,
        )
        if outcome == "OK":
            return {"status": "PASS"}
        if outcome == "TIMEOUT":
            return {"status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT", "detail": "dotnet run timed out"}
        reason, tail = self.classify(detail, {"stage": "execute"})
        return {"status": "BLOCKED-WITH-REASON", "reason": reason, "detail": tail}

    def classify(self, output: str, context: "dict | None" = None) -> "tuple[str, str]":
        """Distinguishes a real defect in the referenced product's own source
        (the error/exception cites a `.cs` file whose basename isn't
        `Program.cs`) from an ordinary COMPILE-ERROR/RUNTIME-ERROR in the
        block's own generated wrapper -- the same file-citation-basename
        design `GoRunner.classify()` uses, for the same reason: a raw
        replace/reference-path substring match does not appear verbatim in
        real compiler/runtime output."""
        tail = (output or "").strip()[-2000:]
        locations = (
            _DOTNET_BUILD_LOCATION_RE.findall(tail) + _DOTNET_RUNTIME_LOCATION_RE.findall(tail)
        )
        cites_other_file = any(Path(loc).name.lower() != "program.cs" for loc in locations)
        if cites_other_file:
            return "UPSTREAM-BROKEN", tail
        stage = (context or {}).get("stage", "compile")
        return ("COMPILE-ERROR" if stage == "compile" else "RUNTIME-ERROR"), tail
