#!/usr/bin/env python3
"""compile_smoke.py -- U-07: real per-platform compile/import smoke against a product's actual
clone, the gap tree-sitter's lenient parser can't see (HRD-02: gis/net held at 320 real compile
errors invisible to extraction). A sibling of upstream_readiness_check.py, same `Result`/
`configure()` seam convention.

Only `net` and `python` get a real implementation (the card's own repro set, §H.7 HRD-02 row);
every other platform declared in platform_capabilities.yaml returns an honest NOT_RUN rather than
inventing an untested rule. Wiring this into upstream_readiness_check.py's own U-07 placeholder
is a later card's job -- this card only builds the capability.

CONTRACT: scripts/pipeline/commands/launch/compile_smoke.py
  inputs:  platform, clone (Path to a product's source tree)
  outputs: compile_smoke(platform, clone) -> Result (PASS/FAIL/WARN/NOT_RUN)
  owner_domain: content-governance
  requires_test: true

Third-party code only ever runs against a scratch build-output directory (never writes `bin/`/
`obj/` back into the shared read-only clone cache) and with token-like env vars stripped from the
subprocess environment first.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import yaml

_HERE = Path(__file__).resolve()
_PIPELINE_ROOT = _HERE.parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from extraction.package_root import detect_package_root  # noqa: E402
from commands.launch.upstream_readiness_check import PASS, FAIL, WARN, NOT_RUN, Result  # noqa: E402

_CONFIG_PATH = _PIPELINE_ROOT / "config" / "platform_capabilities.yaml"

# configure() seam (module _cfg_* globals + configure() + autouse fixture in the tests)
_cfg_runner: "Callable[..., Any] | None" = None


def configure(*, runner: "Callable[..., Any] | None" = None) -> None:
    """Test/operator hook. Called with no arguments it restores the defaults."""
    global _cfg_runner
    _cfg_runner = runner


_TOKEN_LIKE_RE = re.compile(r"(TOKEN|_PAT|SECRET|PASSWORD)$", re.IGNORECASE)


def _scrubbed_env() -> dict:
    """Hard rule: third-party code (the clone's own source) never sees a token-like env var."""
    return {k: v for k, v in os.environ.items() if not _TOKEN_LIKE_RE.search(k)}


def _run(cmd: "list[str]", *, cwd: "Path | None" = None, timeout: int = 180) -> Any:
    if _cfg_runner is not None:
        return _cfg_runner(cmd, cwd=cwd, timeout=timeout)
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=_scrubbed_env(),
    )


def _declared_platforms() -> set:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return set(yaml.safe_load(f)["platforms"].keys())


def compile_smoke(platform: str, clone: Path) -> Result:
    if platform not in _declared_platforms():
        return Result("U-07", "compile_smoke", NOT_RUN,
                       f"platform {platform!r} not declared in platform_capabilities.yaml")
    if platform == "net":
        return _smoke_dotnet(clone)
    if platform == "python":
        return _smoke_python(clone)
    return Result("U-07", "compile_smoke", NOT_RUN,
                   f"no compile-smoke rule for platform {platform!r} yet (HRD-02 scoped net+python only)")


def _smoke_dotnet(clone: Path) -> Result:
    """Builds a disposable COPY of the whole clone, never the clone itself. A `-p:BaseOutputPath`/
    `-p:BaseIntermediateOutputPath` override is not sufficient on its own: found live building
    this card, psd/net's own csproj hard-codes `<DocumentationFile>bin\\$(Configuration)\\...`
    as a literal relative path (not `$(OutputPath)`-derived), so it still writes into the real
    clone's `bin/` regardless of any output-path property override. A full disposable copy is
    the only approach immune to an arbitrary per-project hard-coded relative path -- matching
    the hard rule that third-party code only ever runs against a scratch copy."""
    dotnet_exe = shutil.which("dotnet")
    if dotnet_exe is None:
        return Result("U-07", "compile_smoke", WARN, "dotnet not found on PATH")
    root = detect_package_root(clone, "net")
    csproj = sorted(root.glob("*.csproj"))
    if not csproj:
        return Result("U-07", "compile_smoke", FAIL, f"no .csproj found under {root}")
    rel_csproj = csproj[0].relative_to(clone)
    with tempfile.TemporaryDirectory(prefix="compile-smoke-net-") as scratch:
        work_clone = Path(scratch) / "clone"
        shutil.copytree(clone, work_clone, ignore=shutil.ignore_patterns(".git"))
        proc = _run(
            [dotnet_exe, "build", str(work_clone / rel_csproj), "--nologo", "-clp:ErrorsOnly"],
            cwd=work_clone, timeout=180,
        )
    out = (getattr(proc, "stdout", "") or "") + (getattr(proc, "stderr", "") or "")
    if getattr(proc, "returncode", 1) != 0:
        return Result("U-07", "compile_smoke", FAIL, f"dotnet build failed:\n{out.strip()[-2000:]}")
    return Result("U-07", "compile_smoke", PASS, f"dotnet build succeeded ({csproj[0].name})")


def _smoke_python(clone: Path) -> Result:
    root = detect_package_root(clone, "python")
    if root == clone:
        return Result("U-07", "compile_smoke", WARN,
                       "no importable package root detected (no manifest + __init__.py package)")
    pkg_name = root.name
    script = f"import sys; sys.path.insert(0, {str(root.parent)!r}); import {pkg_name}"
    proc = _run([sys.executable, "-I", "-c", script], cwd=str(root.parent), timeout=60)
    out = (getattr(proc, "stdout", "") or "") + (getattr(proc, "stderr", "") or "")
    if getattr(proc, "returncode", 1) != 0:
        return Result("U-07", "compile_smoke", FAIL, f"import {pkg_name} failed:\n{out.strip()[-2000:]}")
    return Result("U-07", "compile_smoke", PASS, f"import {pkg_name} succeeded")


def main(argv: "list[str] | None" = None) -> int:
    import argparse
    import json
    from dataclasses import asdict

    ap = argparse.ArgumentParser(description="U-07 per-platform compile/import smoke")
    ap.add_argument("platform")
    ap.add_argument("clone", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = compile_smoke(args.platform, args.clone)
    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(f"{result.check_id}  {result.name:<14} {result.status:<8} {result.detail}")
    return 0 if result.status in (PASS, NOT_RUN, WARN) else 1


if __name__ == "__main__":
    sys.exit(main())
