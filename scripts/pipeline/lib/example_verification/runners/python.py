"""
lib/example_verification/runners/python.py

CONTRACT: scripts/pipeline/lib/example_verification/runners/python.py
  purpose: rollout step C3 -- a faithful, behavior-preserving port of
           S-120's real Python verification runner
           (readme_refresh_run.py:4725-5115: `_acquire_python_environment`,
           `_classify_python_failure`, `_run_single_python_block`,
           `_python_block_starts_chain`, `_product_console_scripts`,
           `_venv_script_path`, `_classify_bash_failure`,
           `_run_bash_block`, `python_verification_runner`). Fixture
           staging is shared via `lib.example_verification.acquire`
           (already identical between the real python/typescript runners
           before this port). `readme_refresh_run.py` itself is untouched
           by this port -- it stays the live, active code path until C7
           wires the dispatch; this module exists to be proven at parity
           first (see test_example_verification_runners_python.py), not to
           replace anything yet.
  inputs:  candidate_path (a README candidate file), factpack (dict:
           family/platform/install info)
  outputs: python_verification_runner(candidate_path, factpack) -> dict,
           in the exact legacy S-120 shape (this module does not yet
           produce a result.py VerificationReport -- that adapter lands
           when C7 wires the real dispatch, per the Central module design)
  owner_domain: content-quality

Deliberately still uses the same `_ANY_LANG_CODE_BLOCK_RE` regex S-120
uses today (`\\w*` -- cannot match `c#`/`c++`, RC6/RC19), not
`code_fences.enumerate_code_blocks` -- switching the tokenizer here is a
separate, evidence-gated decision (see C1's own promotion-gate writeup for
why a tokenizer swap needs a measured parity diff first); this port's job
is byte-identical behavior against the function it replaces, not a second
change bundled into the same commit.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .. import acquire

_ANY_LANG_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

_PY_TRACEBACK_FILE_RE = re.compile(r'^\s*File "([^"]+)", line \d+', re.MULTILINE)
_PY_SYNTAX_ERROR_CLASSES = ("SyntaxError", "IndentationError", "TabError")

_NON_PRODUCT_COMMAND_REASON = "NOT-A-PRODUCT-COMMAND"

RUNNABLE_LANGS = ("python", "bash", "sh", "shell")


def pip_installed_version(venv_python: str, package_name: str) -> "str | None":
    try:
        shown = subprocess.run(
            [venv_python, "-m", "pip", "show", package_name], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (shown.stdout or "").splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip() or None
    return None


def acquire_python_environment(work_dir: Path, install_info: dict, clone_cache: Path) -> dict:
    """Real acquire step: published -> disposable venv + `pip install
    {package}` from real PyPI; unpublished -> a real editable install of
    the read-only clone cache (`pip install -e`) -- never `git clone
    --local` into a fresh dir first, since the clone cache is already a
    real local checkout and `pip install -e` itself is read-only against
    it. Returns {"ok", "venv_python", "detail"}."""
    venv_dir = work_dir / "venv"
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    if created.returncode != 0:
        return {"ok": False, "venv_python": None, "detail": f"venv creation failed: {created.stderr.strip()}"}
    venv_python = str(venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python"))

    candidate = (install_info or {}).get("candidate") or {}
    package_name = candidate.get("name") if isinstance(candidate, dict) else None
    published = bool((install_info or {}).get("published", False))
    probed_version = (((install_info or {}).get("publication") or {}).get("live") or {}).get("latest_version")

    if published and package_name:
        spec = f"{package_name}=={probed_version}" if probed_version else package_name
        installed = subprocess.run(
            [venv_python, "-m", "pip", "install", "--quiet", spec],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        )
        if installed.returncode != 0:
            return {
                "ok": False, "venv_python": None,
                "detail": f"pip install {spec} (PyPI) failed: {installed.stderr.strip()[-2000:]}",
            }
        return {
            "ok": True, "venv_python": venv_python, "detail": f"installed {spec} from PyPI",
            "environment": {"install_source": "pypi", "package": package_name,
                            "version": probed_version or pip_installed_version(venv_python, package_name)},
        }

    if not clone_cache.is_dir():
        return {"ok": False, "venv_python": None, "detail": "unpublished and no clone cache directory available"}
    installed = subprocess.run(
        [venv_python, "-m", "pip", "install", "--quiet", "-e", str(clone_cache)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    if installed.returncode != 0:
        return {
            "ok": False, "venv_python": None,
            "detail": f"editable install from clone cache failed: {installed.stderr.strip()[-2000:]}",
        }
    return {
        "ok": True, "venv_python": venv_python, "detail": f"editable-installed from clone cache ({clone_cache})",
        "environment": {"install_source": "clone_cache_editable", "package": package_name,
                        "version": pip_installed_version(venv_python, package_name) if package_name else None},
    }


def classify_python_failure(traceback_text: str, script_path: Path) -> "tuple[str, str]":
    """Distinguishes a real defect in the UPSTREAM package's own source
    from a real defect in the example itself. Signal: the traceback's own
    error class is a syntax-family one (SyntaxError/IndentationError/
    TabError) AND its last cited file is NOT this block's own script."""
    file_frames = _PY_TRACEBACK_FILE_RE.findall(traceback_text)
    has_syntax_error = any(cls in traceback_text for cls in _PY_SYNTAX_ERROR_CLASSES)
    if has_syntax_error and file_frames and file_frames[-1] != str(script_path):
        return "UPSTREAM-BROKEN", traceback_text[-2000:]
    return "RUNTIME-ERROR", traceback_text[-2000:]


def run_single_python_block(venv_python: str, code: str, work_dir: Path, index: int) -> dict:
    """Real execution IS the check. Deliberately does not attempt to
    synthesize a missing preamble for a Fragment-style block -- a block
    that references a prior block's identifier fails honestly as
    BLOCKED-WITH-REASON: RUNTIME-ERROR."""
    script_path = work_dir / f"block_{index}.py"
    script_path.write_text(code, encoding="utf-8")
    try:
        result = subprocess.run(
            [venv_python, str(script_path)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60, cwd=str(work_dir),
        )
    except subprocess.TimeoutExpired:
        return {"index": index, "status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT"}
    if result.returncode == 0:
        return {"index": index, "status": "COMPILED+RAN CLEAN"}
    reason, detail = classify_python_failure((result.stderr or result.stdout).strip(), script_path)
    return {"index": index, "status": "BLOCKED-WITH-REASON", "reason": reason, "detail": detail}


def python_block_starts_chain(code: str) -> bool:
    """A block whose first real statement is an import is a self-contained
    example; anything else continues the previous Python block's example."""
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped.startswith(("import ", "from "))
    return True


def product_console_scripts(clone_cache: Path) -> dict[str, str]:
    """`{script name: "module:function"}` from pyproject.toml
    `[project.scripts]` (and, as a fallback, setup.py's `console_scripts`
    entry points). Regex parse, never an import of the product's build
    config; empty when neither declares any."""
    scripts: dict[str, str] = {}
    pyproject = clone_cache / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8", errors="replace")
        section = re.search(r"^\[project\.scripts\]\s*$(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL)
        if section:
            for m in re.finditer(r'^\s*"?([A-Za-z0-9_.-]+)"?\s*=\s*"([^"]+)"', section.group(1), re.MULTILINE):
                scripts[m.group(1)] = m.group(2)
    setup_py = clone_cache / "setup.py"
    if not scripts and setup_py.is_file():
        text = setup_py.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'["\']([A-Za-z0-9_.-]+)\s*=\s*([A-Za-z0-9_.]+:[A-Za-z0-9_]+)["\']', text):
            scripts[m.group(1)] = m.group(2)
    return scripts


def venv_script_path(venv_python: str, script_name: str) -> "Path | None":
    bin_dir = Path(venv_python).parent
    for candidate in (bin_dir / f"{script_name}.exe", bin_dir / script_name, bin_dir / f"{script_name}.cmd"):
        if candidate.is_file():
            return candidate
    return None


def classify_bash_failure(output: str, unresolved_fixtures: "list[str]") -> "tuple[str, str]":
    tail = output.strip()[-2000:]
    for name in unresolved_fixtures:
        if name in tail and ("No such file" in tail or "FileNotFoundError" in tail or "not found" in tail.lower()):
            return "FIXTURE-UNAVAILABLE", tail
    return "RUNTIME-ERROR", tail


def run_bash_block(
    venv_python: str, code: str, work_dir: Path, index: int, console_scripts: dict[str, str],
    unresolved_fixtures: "list[str]",
) -> dict:
    """Run every product-console-script line of one ```bash block through
    the script installed in the disposable venv, in document order, in the
    shared work dir. A block with no product line at all is
    NOT-A-PRODUCT-COMMAND (install/build/tooling lines are never executed
    here)."""
    product_lines: list[str] = []
    for raw in code.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        first = line.split()[0]
        if first in console_scripts:
            product_lines.append(line)
    if not product_lines:
        return {"index": index, "status": "BLOCKED-WITH-REASON", "reason": _NON_PRODUCT_COMMAND_REASON,
                "detail": "no line in this block invokes one of the product's own console scripts"}
    ran: list[str] = []
    failures: list[dict] = []
    for line in product_lines:
        try:
            argv = shlex.split(line)
        except ValueError as exc:
            failures.append({"line": line, "reason": "RUNTIME-ERROR", "detail": f"could not parse command line: {exc}"})
            continue
        script = venv_script_path(venv_python, argv[0])
        if script is None:
            failures.append({"line": line, "reason": "ACQUIRE-FAILED",
                             "detail": f"console script {argv[0]!r} is declared by the product but was not installed into the venv"})
            continue
        try:
            result = subprocess.run(
                [str(script), *argv[1:]], capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=300, cwd=str(work_dir),
            )
        except subprocess.TimeoutExpired:
            failures.append({"line": line, "reason": "TIMEOUT", "detail": "timed out after 300s"})
            continue
        if result.returncode != 0:
            reason, detail = classify_bash_failure(result.stderr or result.stdout, unresolved_fixtures)
            failures.append({"line": line, "reason": reason, "detail": detail[-600:]})
            continue
        ran.append(line)
    if failures:
        first = failures[0]
        return {
            "index": index, "status": "BLOCKED-WITH-REASON", "reason": first["reason"],
            "detail": f"{first['line']}\n{first['detail']}",
            "commands_run": len(ran), "commands_failed": len(failures),
            "failed_lines": [f["line"] for f in failures],
            "failure_reasons": sorted({f["reason"] for f in failures}),
        }
    return {"index": index, "status": "COMPILED+RAN CLEAN", "commands_run": len(ran)}


def python_verification_runner(
    candidate_path: Path, factpack: dict, *, clone_cache_root: "Path | None" = None,
) -> dict:
    """Real for `python`-tagged fenced code blocks and for the
    product-console-script lines of ```bash blocks; every other language
    still honestly reports BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE --
    a strict, real superset of the stub's honesty, not a different
    philosophy.

    `clone_cache_root` is additive (not present in the S-120 original,
    which reads a module-level `configure()`-seam global instead) --
    this package has no such global, so the caller passes the root
    explicitly; C7's adapter passes S-120's own configured root, keeping
    behavior identical end-to-end."""
    import tempfile

    from ..policy import clone_cache_path

    text = candidate_path.read_text(encoding="utf-8") if candidate_path.is_file() else ""
    blocks = [(m.group(1).strip().lower(), m.group(2)) for m in _ANY_LANG_CODE_BLOCK_RE.finditer(text)]
    family = factpack.get("family")
    platform = factpack.get("platform")
    install_info = factpack.get("install") or {}

    block_statuses = [
        {"index": i, "status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE"}
        for i, (lang, _code) in enumerate(blocks) if lang not in RUNNABLE_LANGS
    ]
    runnable = [(i, lang, code) for i, (lang, code) in enumerate(blocks) if lang in RUNNABLE_LANGS]
    staging: dict = {"staged": {}, "unresolved": []}
    environment: dict = {"install_source": None, "package": None, "version": None}

    if runnable and family and platform:
        with tempfile.TemporaryDirectory(prefix=f"readme-refresh-verify-{family}-{platform}-") as tmp:
            work_dir = Path(tmp)
            clone_cache = clone_cache_path(family, platform, root=clone_cache_root)
            acquired = acquire_python_environment(work_dir, install_info, clone_cache)
            environment = acquired.get("environment") or {**environment, "detail": acquired.get("detail")}
            if not acquired["ok"]:
                for i, _lang, _code in runnable:
                    block_statuses.append({
                        "index": i, "status": "BLOCKED-WITH-REASON", "reason": "ACQUIRE-FAILED",
                        "detail": acquired["detail"],
                    })
            else:
                staging = acquire.stage_fixtures(work_dir, blocks, clone_cache)
                console_scripts = product_console_scripts(clone_cache)
                chain_prefix: list[str] = []
                chain_failed_at: "int | None" = None
                for i, lang, code in runnable:
                    if lang != "python":
                        block_statuses.append(run_bash_block(
                            acquired["venv_python"], code, work_dir, i, console_scripts, staging["unresolved"],
                        ))
                        continue
                    if python_block_starts_chain(code):
                        chain_prefix, chain_failed_at = [], None
                    if chain_failed_at is not None:
                        block_statuses.append({
                            "index": i, "status": "BLOCKED-WITH-REASON", "reason": "DEPENDS-ON-FAILED-BLOCK",
                            "detail": f"continues the example started in block {chain_failed_at}, which already failed",
                            "depends_on": chain_failed_at,
                        })
                        continue
                    script = "\n".join(chain_prefix + [code]) if chain_prefix else code
                    status = run_single_python_block(acquired["venv_python"], script, work_dir, i)
                    if status["status"] == "BLOCKED-WITH-REASON":
                        if status.get("reason") == "RUNTIME-ERROR":
                            for name in staging["unresolved"]:
                                if name in (status.get("detail") or "") and "FileNotFoundError" in (status.get("detail") or ""):
                                    status["reason"] = "FIXTURE-UNAVAILABLE"
                                    status["missing_fixture"] = name
                                    break
                        chain_failed_at = i
                    if chain_prefix or not python_block_starts_chain(code):
                        status["continues_example"] = True
                    chain_prefix.append(code)
                    block_statuses.append(status)
    else:
        for i, _lang, _code in runnable:
            block_statuses.append({"index": i, "status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE"})

    block_statuses.sort(key=lambda b: b["index"])
    return {
        "runner": "python_verification_runner_v2",
        "blocks_found": len(blocks),
        "block_statuses": block_statuses,
        "fixtures": staging,
        "environment": environment,
        "all_named": True,
    }
