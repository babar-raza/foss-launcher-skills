#!/usr/bin/env python3
"""upstream_readiness_check.py -- Stage -1 readiness of an UPSTREAM FOSS repo, before any registry,
knowledge or content work.

CONTRACT: scripts/pipeline/commands/launch/upstream_readiness_check.py
  purpose: Make the family-first launch preconditions machine-checkable instead of living in backlog
           prose (INV-014/INV-015 forbade launching psd/net and psd/python until a LICENSE exists, but
           nothing enforced it, and the rule went stale). Runs BEFORE /update-registry,
           /knowledge-bootstrap and /launch-product and answers one question per check:
             U-01 license_file            a LICENSE/COPYING/UNLICENSE file exists at the repo root      (WARN)
             U-02 source_merged            the clone holds real product source, not an empty stub        (FAIL)
             U-03 clone_current            the clone cache HEAD equals the remote default-branch SHA     (WARN)
             U-04 install_fallback_viable  the source-install command the unpublished-package shortcode
                                           will render can work for this repo (F-PSD-07)                 (FAIL)
             U-05 git_hooks_installed      this checkout enforces commit-time gates                      (WARN)
             U-06 family_placeholder       the family page no longer says "coming soon"                  (WARN)
           Compile/import smoke (U-07) is reserved for the per-platform smoke capability and reports
           NOT_RUN until that exists; NOT_RUN is never a PASS and fails under --strict.

  U-01 design (R1/R2, MT076, F-PSD-15): file-first, API second. A GitHub-API-only check
           false-fails 5 already-launched `cells/*` products that carry a LICENSE file GitHub's
           license API does not recognize. The absence of a LICENSE file is an UPSTREAM
           MISCONFIGURATION, never a launch blocker (owner decision, 2026-10-07): it WARNs
           (`MISCONFIGURED_NO_LICENSE_FILE`), never FAILs, and `verdict()` never counts it against
           exit code 0 even without --strict. Two additional fields ride on the Result:
           `license_link_allowed` (True only when a file exists -- nothing may link to a license
           file or page while this is False) and `license_statement` (the product's
           `data/products.json` `overrides.license`, when set -- the owner-attested wording a page
           may use; `None` when neither a file nor an attestation exists, meaning no license
           statement is sourced yet).

  inputs:  family platform [--json] [--strict] [--clone-path PATH]
  outputs: a per-check table (or JSON); exit 0 when no check FAILs (and, with --strict, none WARN/NOT_RUN),
           1 when any check FAILs, 2 on a usage/registry error.
  owner_domain: content-governance
  requires_test: true

Every external process goes through the injected `runner` (configure(runner=...)) so the tests are offline.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve()
_PIPELINE_ROOT = _HERE.parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from extraction.tree_helpers import _is_non_public_path  # noqa: E402  (single definition of "product source")

PASS, FAIL, WARN, NOT_RUN = "PASS", "FAIL", "WARN", "NOT_RUN"

_REPO_ROOT = _HERE.parents[4]
_CLONE_ROOT_REL = Path("runs") / ".clone_cache"

# configure() seam (module _cfg_* globals + configure() + autouse fixture in the tests)
_cfg_runner: "Callable[..., Any] | None" = None
_cfg_repo_root: "Path | None" = None


def configure(*, runner: "Callable[..., Any] | None" = None, repo_root: "Path | str | None" = None) -> None:
    """Test/operator hook. Called with no arguments it restores the defaults."""
    global _cfg_runner, _cfg_repo_root
    _cfg_runner = runner
    _cfg_repo_root = Path(repo_root) if repo_root is not None else None


def _root() -> Path:
    return _cfg_repo_root or _REPO_ROOT


def _run(cmd: "list[str]", *, cwd: "Path | None" = None, timeout: int = 60) -> Any:
    if _cfg_runner is not None:
        return _cfg_runner(cmd, cwd=cwd, timeout=timeout)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)


@dataclass
class Result:
    check_id: str
    name: str
    status: str
    detail: str
    license_link_allowed: "bool | None" = field(default=None)
    license_statement: "str | None" = field(default=None)


_SOURCE_EXT = {"net": (".cs",), "python": (".py",), "java": (".java",), "typescript": (".ts",), "javascript": (".js",),
               "go": (".go",), "cpp": (".cpp", ".cc", ".h", ".hpp"), "rust": (".rs",)}
_MIN_SOURCE_FILES = 3

# File-first license detection (R1/R2, F-PSD-15): dedicated license files at the repo root only.
# Broader than a fixed name list -- matches any LICENSE*/COPYING*/UNLICENSE* file, case-insensitively,
# so LICENSE, LICENSE.txt, LICENSE.md, COPYING, UNLICENSE.md, etc. all count. The GitHub license API
# is consulted ONLY to attach a human-readable SPDX id to an already-PASSing result -- it never
# downgrades a file-backed PASS (the exact false-fail the plan's F-PSD-15 finding identified: 5
# launched `cells/*` repos have a LICENSE file the API reports as null).
_LICENSE_FILE_PREFIXES = ("license", "copying", "unlicense")


def _find_license_file(clone: Path) -> "Path | None":
    """Root-level file first; then one level into a root-level directory whose name also
    matches (found live, MT076 R1: all 5 `cells/*` repos keep their license text under a
    `License/LICENSE.txt` directory, not a root-level file -- GitHub's license API does not
    detect it there either, matching the measured API-null result for these 5 repos, but it is
    a real, on-disk license file and must PASS, not WARN)."""
    if not clone.is_dir():
        return None
    for child in sorted(clone.iterdir()):
        if child.is_file() and child.name.lower().startswith(_LICENSE_FILE_PREFIXES):
            return child
    for child in sorted(clone.iterdir()):
        if child.is_dir() and child.name.lower().startswith(_LICENSE_FILE_PREFIXES):
            for grandchild in sorted(child.iterdir()):
                if grandchild.is_file() and grandchild.name.lower().startswith(_LICENSE_FILE_PREFIXES):
                    return grandchild
    return None


def _load_json(rel: str, default: Any) -> Any:
    try:
        return json.loads((_root() / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def find_product(family: str, platform: str) -> "dict | None":
    for row in _load_json("data/products.json", []):
        if row.get("family") == family and row.get("platform") == platform:
            return row
    return None


def _owner_repo(product: dict) -> "tuple[str, str] | None":
    url = (product.get("repo_url") or "").rstrip("/")
    parts = url.split("github.com/")[-1].split("/") if "github.com/" in url else []
    return (parts[0], parts[1]) if len(parts) >= 2 else None


def _is_published(family: str, platform: str) -> bool:
    entry = ((_load_json("data/package_registry.json", {}) or {}).get(family) or {}).get(platform) or {}
    return bool((entry.get("verification") or {}).get("published"))


def check_license(product: dict, clone: Path) -> Result:
    license_statement = (product.get("overrides") or {}).get("license")
    license_file = _find_license_file(clone)

    if license_file is None:
        return Result(
            "U-01", "license_file", WARN,
            "MISCONFIGURED_NO_LICENSE_FILE: no LICENSE/COPYING/UNLICENSE file at the repo root "
            "(upstream misconfiguration, not a launch blocker)"
            + (f"; owner-attested license: {license_statement}" if license_statement else ""),
            license_link_allowed=False,
            license_statement=license_statement,
        )

    spdx = None
    ident = _owner_repo(product)
    if ident is not None:
        try:
            proc = _run(["gh", "api", f"repos/{ident[0]}/{ident[1]}", "--jq", ".license.spdx_id"])
            out = (getattr(proc, "stdout", "") or "").strip()
            if getattr(proc, "returncode", 1) == 0 and out and out.lower() != "null":
                spdx = out
        except (OSError, subprocess.SubprocessError):
            pass  # best-effort only -- a file-backed PASS never depends on the API call succeeding

    detail = f"license file {license_file.name}" + (f" (SPDX: {spdx})" if spdx else " (not recognized by GitHub's license API)")
    return Result(
        "U-01", "license_file", PASS, detail,
        license_link_allowed=True,
        license_statement=license_statement or spdx,
    )


def _clone_path(family: str, platform: str, override: "Path | None") -> Path:
    return override or (_root() / _CLONE_ROOT_REL / f"aspose_{family}_{platform}")


def check_source_merged(platform: str, clone: Path) -> Result:
    exts = _SOURCE_EXT.get(platform)
    if exts is None:
        return Result("U-02", "source_merged", WARN, f"no source-extension rule for platform {platform!r}")
    if not clone.is_dir():
        return Result("U-02", "source_merged", FAIL, f"clone not found at {clone.name}")
    n = 0
    for path in clone.rglob("*"):
        if path.is_file() and path.suffix.lower() in exts and ".git" not in path.parts \
                and not _is_non_public_path(path, clone):
            n += 1
    if n < _MIN_SOURCE_FILES:
        return Result("U-02", "source_merged", FAIL, f"only {n} product source file(s) (need >= {_MIN_SOURCE_FILES}); empty stub")
    return Result("U-02", "source_merged", PASS, f"{n} product source files")


def check_clone_current(product: dict, clone: Path) -> Result:
    ident = _owner_repo(product)
    if ident is None or not clone.is_dir():
        return Result("U-03", "clone_current", WARN, "cannot compare (no repo_url or no clone)")
    try:
        local = (_run(["git", "-C", str(clone), "rev-parse", "HEAD"]).stdout or "").strip()
        remote = (_run(["gh", "api", f"repos/{ident[0]}/{ident[1]}/commits/HEAD", "--jq", ".sha"]).stdout or "").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return Result("U-03", "clone_current", WARN, f"UNVERIFIED: {exc}")
    if not local or not remote:
        return Result("U-03", "clone_current", WARN, "UNVERIFIED: could not read one of the two SHAs")
    if local != remote:
        return Result("U-03", "clone_current", WARN, f"clone {local[:8]} != remote {remote[:8]}")
    return Result("U-03", "clone_current", PASS, f"clone at {local[:8]}")


def _install_viable(platform: str, clone: Path) -> "tuple[bool | None, str]":
    names = {p.name for p in clone.iterdir()} if clone.is_dir() else set()
    if platform == "python":
        return bool(names & {"pyproject.toml", "setup.py", "setup.cfg"}), "pyproject.toml / setup.py / setup.cfg at the repo root"
    if platform in ("typescript", "javascript"):
        return "package.json" in names, "package.json at the repo root"
    if platform == "net":
        sln = [n for n in names if n.endswith((".sln", ".slnx"))]
        proj = [n for n in names if n.endswith((".csproj", ".fsproj", ".vbproj"))]
        return len(sln) == 1 or (not sln and len(proj) == 1), "exactly one .sln/.slnx (or one project file) at the repo root"
    if platform == "java":
        return "pom.xml" in names, "pom.xml at the repo root"
    if platform == "go":
        return "go.mod" in names, "go.mod at the repo root"
    if platform == "cpp":
        return "CMakeLists.txt" in names, "CMakeLists.txt at the repo root"
    if platform == "rust":
        return "Cargo.toml" in names, "Cargo.toml at the repo root"
    return None, f"no rule for platform {platform!r}"


def check_install_fallback(family: str, platform: str, clone: Path) -> Result:
    """The unpublished-package shortcode renders `git clone && <platform install>`; it never verifies the repo
    can satisfy that command (F-PSD-07). Only relevant while the registry says the package is unpublished."""
    if _is_published(family, platform):
        return Result("U-04", "install_fallback_viable", PASS, "package is published: the source fallback is not rendered")
    ok, need = _install_viable(platform, clone)
    if ok is None:
        return Result("U-04", "install_fallback_viable", WARN, need)
    if not ok:
        return Result("U-04", "install_fallback_viable", FAIL,
                      f"unpublished package would render a source-install command that cannot work: needs {need}")
    return Result("U-04", "install_fallback_viable", PASS, f"found {need}")


def check_hooks_installed() -> Result:
    hooks = _root() / ".git" / "hooks"
    if (hooks / "pre-commit").is_file():
        return Result("U-05", "git_hooks_installed", PASS, "pre-commit hook present")
    return Result("U-05", "git_hooks_installed", WARN, "no pre-commit hook installed: commit-time gates do not run in this checkout")


def check_family_placeholder(family: str) -> Result:
    page = _root() / "content" / "products.aspose.org" / "en" / family / "_index.md"
    if not page.is_file():
        return Result("U-06", "family_placeholder", PASS, "no family page yet")
    if "coming soon" in page.read_text(encoding="utf-8", errors="replace").lower():
        return Result("U-06", "family_placeholder", WARN, "family page still says 'coming soon' (Stage 1.5 /family-sync must replace it; gate L-10)")
    return Result("U-06", "family_placeholder", PASS, "no placeholder text")


def run_checks(family: str, platform: str, *, clone_path: "Path | None" = None) -> "list[Result]":
    product = find_product(family, platform)
    if product is None:
        return [Result("U-00", "registered", FAIL, f"{family}/{platform} is not in data/products.json")]
    clone = _clone_path(family, platform, clone_path)
    return [
        check_license(product, clone),
        check_source_merged(platform, clone),
        check_clone_current(product, clone),
        check_install_fallback(family, platform, clone),
        check_hooks_installed(),
        check_family_placeholder(family),
        Result("U-07", "compile_smoke", NOT_RUN, "reserved for the per-platform smoke capability (HRD-02)"),
    ]


def verdict(results: "list[Result]", *, strict: bool = False) -> int:
    if any(r.status == FAIL for r in results):
        return 1
    if strict and any(r.status in (WARN, NOT_RUN) for r in results):
        return 1
    return 0


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="Stage -1 upstream readiness check")
    ap.add_argument("family")
    ap.add_argument("platform")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="WARN and NOT_RUN also exit non-zero")
    ap.add_argument("--clone-path", default=None)
    args = ap.parse_args(argv)
    results = run_checks(args.family, args.platform, clone_path=Path(args.clone_path) if args.clone_path else None)
    if results and results[0].check_id == "U-00":
        print(f"ERROR: {results[0].detail}", file=sys.stderr)
        return 2
    code = verdict(results, strict=args.strict)
    if args.json:
        print(json.dumps({"family": args.family, "platform": args.platform, "exit": code,
                          "results": [asdict(r) for r in results]}, indent=2))
    else:
        print(f"UPSTREAM READINESS: {args.family}/{args.platform}")
        for r in results:
            print(f"  {r.check_id}  {r.name:<26} {r.status:<8} {r.detail}")
        print("RESULT:", "READY" if code == 0 else "NOT READY")
    return code


if __name__ == "__main__":
    sys.exit(main())
