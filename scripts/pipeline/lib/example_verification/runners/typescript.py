"""
lib/example_verification/runners/typescript.py

CONTRACT: scripts/pipeline/lib/example_verification/runners/typescript.py
  purpose: rollout step C3 -- a faithful, behavior-preserving port of
           S-120's real TypeScript verification runner
           (readme_refresh_run.py:5144-5426:
           `_acquire_typescript_environment`,
           `_self_link_typescript_package`, `_typescript_block_starts_chain`,
           `_classify_typescript_failure`, `_run_single_typescript_block`,
           `typescript_verification_runner`). Fixture staging is shared via
           `lib.example_verification.acquire` (already identical between
           the real python/typescript runners before this port). Node/npm/
           npx resolution now goes through the shared `toolchain.find()`
           (the same `shutil.which` fix `_resolve_node_bin` already proved
           necessary on Windows) instead of a second private copy.
           `readme_refresh_run.py` itself is untouched by this port -- see
           runners/python.py's module docstring for the full rationale
           (same taskcard, same posture).
  inputs:  candidate_path (a README candidate file), factpack (dict:
           family/platform)
  outputs: typescript_verification_runner(candidate_path, factpack) -> dict,
           in the exact legacy S-120 shape
  owner_domain: content-quality
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .. import acquire
from .. import toolchain

_ANY_LANG_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


class NodeToolNotFoundError(RuntimeError):
    """Raised when a required Node tool (npm/npx) is not found on PATH."""


def _resolve_node_bin(name: str) -> str:
    """`npm`/`npx` are `.cmd` shims on Windows -- a bare `subprocess.run`
    without a resolved path fails with `WinError 2` -- delegates to the
    shared `toolchain.find()` (same `shutil.which` mechanism)."""
    resolved = toolchain.find(name)
    if not resolved:
        raise NodeToolNotFoundError(f"{name!r} not found on PATH")
    return resolved


def self_link_typescript_package(project_dir: Path, package_name: "str | None") -> bool:
    """Creates `node_modules/{scope}/{name}` inside `project_dir` as a
    directory symlink back to `project_dir` itself, so an example that
    imports the product BY ITS OWN DECLARED PACKAGE NAME resolves from
    inside the product's own source tree -- the real, standard mechanism
    `npm link`/a monorepo workspace uses under the hood. Returns whether
    the link was created; `False` (no `package_name`, or a real `OSError`
    creating it) is a soft failure, never raised."""
    if not package_name:
        return False
    self_link = project_dir / "node_modules" / Path(*package_name.split("/"))
    self_link.parent.mkdir(parents=True, exist_ok=True)
    try:
        self_link.symlink_to(project_dir, target_is_directory=True)
        return True
    except OSError:
        return False


def acquire_typescript_environment(work_dir: Path, clone_cache: Path) -> dict:
    """Copies the clone cache into a disposable project dir (never mutates
    the shared, read-only clone cache with a node_modules/ install), then
    `npm install` for real. Returns `{"ok", "project_dir", "detail"}`.

    Two additional, disposable-copy-only steps close a real self-import
    gap (a product's own examples importing it BY ITS OWN DECLARED
    PACKAGE NAME): `npm run build` when the manifest declares that
    script, and a real package self-link (see self_link_typescript_package)."""
    if not clone_cache.is_dir():
        return {"ok": False, "project_dir": None, "detail": "no clone cache directory available"}
    package_json_path = clone_cache / "package.json"
    if not package_json_path.is_file():
        return {"ok": False, "project_dir": None, "detail": "clone cache has no package.json"}

    project_dir = work_dir / "project"
    shutil.copytree(clone_cache, project_dir, ignore=shutil.ignore_patterns(".git", "node_modules"))
    installed = subprocess.run(
        [_resolve_node_bin("npm"), "install", "--no-audit", "--no-fund"],
        cwd=str(project_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )
    if installed.returncode != 0:
        return {
            "ok": False, "project_dir": None,
            "detail": f"npm install failed: {(installed.stderr or installed.stdout).strip()[-2000:]}",
        }

    try:
        manifest = json.loads(package_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    if (manifest.get("scripts") or {}).get("build"):
        built = subprocess.run(
            [_resolve_node_bin("npm"), "run", "build"],
            cwd=str(project_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        )
        if built.returncode != 0:
            return {
                "ok": False, "project_dir": None,
                "detail": f"npm run build failed: {(built.stderr or built.stdout).strip()[-2000:]}",
            }

    self_link_typescript_package(project_dir, manifest.get("name"))
    return {"ok": True, "project_dir": project_dir, "detail": "npm install (+ build, + self-link) completed in a disposable project copy"}


def typescript_block_starts_chain(code: str) -> bool:
    """Same convention as `python_block_starts_chain` -- a block whose
    first real statement is an import is a self-contained example;
    anything else continues the previous block's example. TS/JS line
    comments are `//`, not `#`."""
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        return stripped.startswith(("import ", "import{"))
    return True


_TS_MISSING_EXPORT_RE = re.compile(r"does not provide an export named ['\"]?([\w$]+)['\"]?")


def classify_typescript_failure(output: str) -> "tuple[str, str]":
    """Analogous to `classify_python_failure`'s distinction: Node's ESM
    loader raises exactly `SyntaxError: The requested module '<pkg>' does
    not provide an export named '<name>'` when a README-documented import
    can never resolve against the package's real built entry point -- a
    real reader copy-pasting this exact, correctly-transcribed example
    hits this exact error; it is not a mistake in the candidate."""
    if _TS_MISSING_EXPORT_RE.search(output):
        return "UPSTREAM-BROKEN", output[-2000:]
    return "RUNTIME-ERROR", output[-2000:]


def run_single_typescript_block(project_dir: Path, code: str, index: int) -> dict:
    """Writes the block at the PROJECT ROOT (not a subdirectory) -- every
    real product's own Quick Start examples import via a root-relative
    path, so the block must sit alongside the real source. `tsc --noEmit`
    runs PROJECT-WIDE (no explicit file argument) -- an explicit file
    argument silently drops real tsconfig.json settings. Written as
    `.mts`, never bare `.ts` -- real Quick Start examples use top-level
    `await`, and a bare `.ts` file is treated as CommonJS by default
    (esbuild/tsx hard-rejects top-level await under cjs); `.mts` is
    unambiguously ESM regardless of package.json."""
    npx = _resolve_node_bin("npx")
    script_name = f"verify_block_{index}.mts"
    script_path = project_dir / script_name
    script_path.write_text(code, encoding="utf-8")
    try:
        typecheck = subprocess.run(
            [npx, "--no-install", "tsc", "--noEmit"],
            cwd=str(project_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
    except subprocess.TimeoutExpired:
        script_path.unlink(missing_ok=True)
        return {"index": index, "status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT"}
    if typecheck.returncode != 0:
        own_errors = "\n".join(
            line for line in (typecheck.stdout or "").splitlines() if line.startswith(script_name)
        )
        if own_errors:
            script_path.unlink(missing_ok=True)
            return {
                "index": index, "status": "BLOCKED-WITH-REASON", "reason": "TYPE-CHECK-FAILED",
                "detail": own_errors[-2000:],
            }
        # Every reported error is in some OTHER file (a real, pre-existing
        # project defect this block never touches) -- not this block's fault.

    try:
        run = subprocess.run(
            [npx, "--no-install", "tsx", script_name],
            cwd=str(project_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
    except subprocess.TimeoutExpired:
        script_path.unlink(missing_ok=True)
        return {"index": index, "status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT"}
    script_path.unlink(missing_ok=True)
    if run.returncode == 0:
        return {"index": index, "status": "COMPILED+RAN CLEAN"}
    reason, detail = classify_typescript_failure((run.stderr or run.stdout).strip())
    return {"index": index, "status": "BLOCKED-WITH-REASON", "reason": reason, "detail": detail}


def typescript_verification_runner(
    candidate_path: Path, factpack: dict, *, clone_cache_root: "Path | None" = None,
) -> dict:
    """Real for `typescript`/`ts`-tagged fenced code blocks; every other
    language still honestly reports BLOCKED-WITH-REASON:
    TOOLCHAIN-UNAVAILABLE. Deliberately a strict superset of the stub's
    honesty, same posture as python_verification_runner.

    `clone_cache_root` is additive -- see python_verification_runner's own
    docstring for why (no `configure()`-seam global in this package)."""
    import tempfile

    from ..policy import clone_cache_path

    text = candidate_path.read_text(encoding="utf-8") if candidate_path.is_file() else ""
    blocks = [(m.group(1).strip().lower(), m.group(2)) for m in _ANY_LANG_CODE_BLOCK_RE.finditer(text)]
    family = factpack.get("family")
    platform = factpack.get("platform")
    staging: dict = {"staged": {}, "unresolved": []}

    block_statuses = [
        {"index": i, "status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE"}
        for i, (lang, _code) in enumerate(blocks) if lang not in ("typescript", "ts")
    ]
    ts_blocks = [(i, code) for i, (lang, code) in enumerate(blocks) if lang in ("typescript", "ts")]

    if ts_blocks and family and platform:
        with tempfile.TemporaryDirectory(prefix=f"readme-refresh-verify-ts-{family}-{platform}-") as tmp:
            work_dir = Path(tmp)
            clone_cache = clone_cache_path(family, platform, root=clone_cache_root)
            acquired = acquire_typescript_environment(work_dir, clone_cache)
            if not acquired["ok"]:
                for i, _code in ts_blocks:
                    block_statuses.append({
                        "index": i, "status": "BLOCKED-WITH-REASON", "reason": "ACQUIRE-FAILED",
                        "detail": acquired["detail"],
                    })
            else:
                project_dir = acquired["project_dir"]
                staging = acquire.stage_fixtures(project_dir, blocks, clone_cache)
                chain_prefix: list[str] = []
                chain_failed_at: "int | None" = None
                for i, code in ts_blocks:
                    if typescript_block_starts_chain(code):
                        chain_prefix, chain_failed_at = [], None
                    if chain_failed_at is not None:
                        block_statuses.append({
                            "index": i, "status": "BLOCKED-WITH-REASON", "reason": "DEPENDS-ON-FAILED-BLOCK",
                            "detail": f"continues the example started in block {chain_failed_at}, which already failed",
                            "depends_on": chain_failed_at,
                        })
                        continue
                    script = "\n".join(chain_prefix + [code]) if chain_prefix else code
                    status = run_single_typescript_block(project_dir, script, i)
                    if status["status"] == "BLOCKED-WITH-REASON" and status.get("reason") == "RUNTIME-ERROR":
                        detail = status.get("detail") or ""
                        for name in staging["unresolved"]:
                            if name in detail and ("ENOENT" in detail or "no such file" in detail.lower()):
                                status["reason"] = "FIXTURE-UNAVAILABLE"
                                status["missing_fixture"] = name
                                break
                    if status["status"] == "BLOCKED-WITH-REASON":
                        chain_failed_at = i
                    if chain_prefix or not typescript_block_starts_chain(code):
                        status["continues_example"] = True
                    chain_prefix.append(code)
                    block_statuses.append(status)
    else:
        for i, _code in ts_blocks:
            block_statuses.append({"index": i, "status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE"})

    block_statuses.sort(key=lambda b: b["index"])
    return {
        "runner": "typescript_verification_runner_v2",
        "blocks_found": len(blocks),
        "block_statuses": block_statuses,
        "fixtures": staging,
        "all_named": True,
    }
