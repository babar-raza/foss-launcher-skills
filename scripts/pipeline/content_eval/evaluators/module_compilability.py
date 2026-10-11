"""Module compilability evaluator -- verifies that the source file backing a
page's cited public API classes actually compiles against the pinned clone
cache.

RC-tex-python-05 (MT037-2026-08-24-FOSS-PORTFOLIO-FORENSIC-HEAL): no existing
evaluator checks whether a documented public API module can be imported at
all. Reachability-style checks (private_api_usage, api_completeness) verify a
name is exported, but assume the containing module parses successfully.
tex/python's presentation/__init__.py (defining TeXJob, TeXOptions, and all 3
output devices) fails py_compile with IndentationError -- 35 of 45 files in
the whole package fail identically -- yet every other evaluator returned
clean or near-clean results for pages built entirely around this
non-importable module, because none of them attempt to import it.

Python-only for now (py_compile is fast, stdlib, always available in this
environment). Other platforms would need their own real toolchain (javac,
csc, g++, go build, rustc), which is heavier and not guaranteed available
here -- deliberately out of scope for this first version, not silently
pretended to be covered.

Category: MC (Module Compilability)
"""

from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# --- Test seam (configure() pattern, see AGENTS.md SS16 tiered monkeypatch policy) ---
_CLONE_CACHE_ROOT_OVERRIDE: "Path | None" = None
_COMPILE_CACHE: "dict[tuple[str, str, str], str | None]" = {}


def configure(*, clone_cache_root: "Path | str | None" = None) -> None:
    """Test seam: override the clone-cache root. Pass None to restore the
    real resolver. Also resets the compile-result cache, since tests use
    fresh temp directories per case."""
    global _CLONE_CACHE_ROOT_OVERRIDE, _COMPILE_CACHE
    _CLONE_CACHE_ROOT_OVERRIDE = Path(clone_cache_root) if clone_cache_root is not None else None
    _COMPILE_CACHE = {}


def _clone_dir(family: str, platform: str) -> "Path | None":
    if _CLONE_CACHE_ROOT_OVERRIDE is not None:
        return _CLONE_CACHE_ROOT_OVERRIDE if _CLONE_CACHE_ROOT_OVERRIDE.is_dir() else None
    try:
        from core.clone_cache import clone_path
    except ImportError:
        return None
    path = clone_path(family, platform)
    return path if path.is_dir() else None


def _check_compiles_cached(family: str, platform: str, rel_file: str) -> "str | None":
    """Return None if rel_file compiles cleanly (or can't be checked -- a
    missing clone cache is not evidence of a defect), else the first line of
    the compile error."""
    key = (family, platform, rel_file)
    if key in _COMPILE_CACHE:
        return _COMPILE_CACHE[key]

    clone_dir = _clone_dir(family, platform)
    target = (clone_dir / rel_file) if clone_dir is not None else None
    if target is None or not target.is_file():
        _COMPILE_CACHE[key] = None
        return None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            py_compile.compile(str(target), cfile=str(Path(tmp) / "out.pyc"), doraise=True)
        result = None
    except py_compile.PyCompileError as exc:
        result = str(exc).splitlines()[0][:200]
    except (SyntaxError, ValueError) as exc:
        result = f"{type(exc).__name__}: {exc}".splitlines()[0][:200]

    _COMPILE_CACHE[key] = result
    return result


class ModuleCompilabilityEvaluator(BaseEvaluator):
    """FAILs a page when a cited public API class's source file does not
    compile against the pinned clone cache -- i.e. the class the page
    describes as usable cannot actually be imported.

    Deliberately conservative: only reports a FAIL when it can positively
    reproduce a compile error against a real, present clone-cache file. It
    never treats a missing clone cache, missing knowledge, or an unresolved
    class name as evidence of a defect -- absence of proof is not proof of
    absence.
    """

    name = "module_compilability"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if page.platform != "python":
            return []
        if knowledge is None:
            return []

        evidence = page.frontmatter.get("evidence") or {}
        apis = evidence.get("apis") or []
        if not apis:
            return []

        classes = getattr(knowledge, "classes", None)
        if not isinstance(classes, dict):
            return []

        seen_files: set[str] = set()
        findings: list[Finding] = []
        for api_token in apis:
            class_name = api_token.split(".", 1)[0]
            entry = classes.get(class_name)
            if not entry:
                continue
            rel_file = entry.get("file")
            if not rel_file or rel_file in seen_files:
                continue
            seen_files.add(rel_file)

            error = _check_compiles_cached(page.family, page.platform, rel_file)
            if error is None:
                continue

            findings.append(Finding(
                level="FAIL",
                category="MC",
                filepath=str(page.filepath),
                line_no=0,
                message=(
                    f"Page cites `{class_name}`, defined in `{rel_file}`, but that file "
                    f"does not compile against the pinned clone cache ({error}). The "
                    f"documented API cannot actually be imported as described."
                ),
                suggestion=(
                    f"Verify `{rel_file}` compiles in the upstream repo at the pinned "
                    f"commit (e.g. `git show HEAD:{rel_file}` inside the clone, reproduced "
                    f"against the exact pinned repo_sha). If this is a genuine upstream "
                    f"defect rather than a clone-cache artifact, disclose the current "
                    f"non-functional status rather than presenting working code examples."
                ),
                evaluator=self.name,
            ))
        return findings
