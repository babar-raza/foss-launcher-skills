"""check_go_code_blocks.py — Advisory validator for Go code blocks in content files.

Extracts fenced ```go code blocks from Markdown content files, wraps standalone
snippets in a compilable package main / func main() scaffolding, and runs
``go vet`` to detect type errors and undefined API usage.

Requires the ``go`` toolchain to be installed and on PATH.

Exit codes:
  0 — all blocks vetted successfully (or --advisory mode: warnings printed only)
  1 — one or more blocks failed go vet
  2 — setup error (go not found, content_dir not found, etc.)

Usage:
    .venv/Scripts/python scripts/ci/checks/check_go_code_blocks.py \\
        content/docs.aspose.org/en/pdf/go/
    .venv/Scripts/python scripts/ci/checks/check_go_code_blocks.py \\
        content/docs.aspose.org/en/pdf/go/ --advisory
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION/C5: the wrapping/module-
# resolution helpers below moved to lib/example_verification/runners/go.py --
# re-exported here (not just imported privately) so every existing caller of
# `from check_go_code_blocks import (...)` -- including
# scripts/pipeline/tests/test_ci_go_code_blocks.py -- keeps working unchanged.
# `_EXTRA_IMPORT_HEURISTICS` is the SAME list object as go.py's module-level
# global (mutating it here, e.g. in main() below, mutates the one go.py's own
# `_infer_imports` reads -- not a copy).
_LIB_DIR = REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from example_verification.runners.go import (  # noqa: E402
    _EXTRA_IMPORT_HEURISTICS,
    _PDF_GO_MODULE,
    _find_module_replace_path,
    _has_top_level_main,
    _infer_imports,
    _resolve_go_module,
    _wrap_fragment,
)

# Pattern to extract fenced go code blocks
_GO_BLOCK_RE = re.compile(r"```go\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _find_go() -> str | None:
    return shutil.which("go")


def _needs_package_wrapper(code: str) -> bool:
    return not re.search(r"^\s*package\s+\w+", code, re.MULTILINE)


def _vet_block(
    go_exe: str,
    code: str,
    source_file: str,
    block_index: int,
    module_path: str,
    go_version: str,
    family: str | None = None,
) -> str | None:
    """Vet a single Go code block. Returns None on success, error string on failure."""
    wrapped = _wrap_fragment(code) if _needs_package_wrapper(code) else code

    with tempfile.TemporaryDirectory(prefix="go_vet_") as tmpdir:
        tmp = Path(tmpdir)
        go_mod_lines = [f"module check_block\n\ngo {go_version}\n"]
        replace_path = _find_module_replace_path(module_path, family=family)
        if replace_path:
            # A module path with a major-version suffix (/vN, N>=2 -- Go's
            # semantic import versioning convention) requires the required
            # version's own major component to match that suffix (e.g.
            # `.../v26` must be required at `v26.x.y`, not `v0.0.0`). Found
            # live on cells/go (module path ends `/v26`): the hardcoded
            # `v0.0.0` placeholder made `go.mod` itself invalid before `go
            # vet` ever ran.
            major_suffix = re.search(r"/v(\d+)$", module_path)
            placeholder_version = f"v{major_suffix.group(1)}.0.0" if major_suffix else "v0.0.0"
            go_mod_lines.append(
                f"\nrequire {module_path} {placeholder_version}\n"
                f"replace {module_path} => {replace_path}\n"
            )
        (tmp / "go.mod").write_text("".join(go_mod_lines), encoding="utf-8")
        (tmp / "main.go").write_text(wrapped, encoding="utf-8")

        # GOFLAGS=-mod=mod: a fresh go.mod referencing a local `replace`
        # target has no go.sum entry yet; without this, `go vet` refuses
        # with "updates to go.mod needed; to update it: go mod tidy"
        # instead of vetting. Safe here since this go.mod is a disposable
        # scratch file the checker itself generated, not a real project
        # module -- there is nothing to "silently modify" that matters.
        vet_env = {**os.environ, "GOFLAGS": "-mod=mod"}
        try:
            result = subprocess.run(
                [go_exe, "vet", "./..."],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(tmp),
                timeout=30,
                env=vet_env,
            )
        except subprocess.TimeoutExpired:
            return f"TIMEOUT:{source_file} block #{block_index + 1}: go vet timed out (module not cached)"

        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            return f"{source_file} block #{block_index + 1}:\n{stderr}\n"
    return None


def check_content_dir(
    content_dir: Path,
    go_exe: str,
    module_path: str = _PDF_GO_MODULE,
    go_version: str = "1.24",
) -> list[str]:
    """Check all Go code blocks in *content_dir*. Returns list of error strings."""
    content_dir = content_dir.resolve()
    # Same convention _resolve_go_module uses: the family is content_dir's own
    # parent directory name, regardless of subdomain layout. Threaded into
    # _vet_block so _find_module_replace_path can resolve this product's own
    # clone directly instead of scanning every directory under the clone cache.
    family = content_dir.parent.name
    errors: list[str] = []
    for md_file in sorted(content_dir.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blocks = _GO_BLOCK_RE.findall(text)
        if not blocks:
            continue
        rel = str(md_file.relative_to(REPO_ROOT)).replace("\\", "/")
        for i, block in enumerate(blocks):
            if not block.strip():
                continue
            # Skip import-only blocks (no executable code to vet). The
            # aliased-import branch (`alias "path"`) must allow underscores
            # -- real Go aliases commonly contain them (e.g. `cells_foss`,
            # this repo's own alias for cells/go), and the unfixed
            # `[a-zA-Z]+` char class silently failed to recognize them,
            # letting an import-only block fall through to _vet_block and
            # fail with "imported and not used" instead of being skipped.
            stripped_lines = [
                ln for ln in block.strip().splitlines()
                if ln.strip() and not re.match(
                    r'^\s*(import\s|import\s*\(|\)|"[^"]*"$|[a-zA-Z_]\w*\s+"[^"]*"$)',
                    ln,
                )
            ]
            if not stripped_lines:
                continue
            err = _vet_block(go_exe, block, rel, i, module_path, go_version, family=family)
            if err:
                errors.append(err)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Go code blocks in content files via go vet."
    )
    parser.add_argument(
        "content_dir",
        nargs="?",
        default=str(REPO_ROOT / "content" / "docs.aspose.org" / "en" / "pdf" / "go"),
        help="Directory to scan for .md files",
    )
    parser.add_argument(
        "--advisory",
        action="store_true",
        help="Print warnings but always exit 0",
    )
    parser.add_argument(
        "--module",
        default=None,
        help="Go module path (default: auto-resolved from "
             "knowledge/{family}/go/scout/model.yaml's canonical_import; "
             f"falls back to {_PDF_GO_MODULE} if that can't be resolved)",
    )
    parser.add_argument(
        "--go-version",
        default="1.24",
        dest="go_version",
        help="Go version for generated go.mod (default: 1.24)",
    )
    args = parser.parse_args(argv)

    content_dir = Path(args.content_dir)
    if not content_dir.exists():
        print(f"ERROR: content_dir not found: {content_dir}", file=sys.stderr)
        return 2

    go_exe = _find_go()
    if go_exe is None:
        print(
            "WARNING: go not found on PATH — skipping Go code block check",
            file=sys.stderr,
        )
        return 0 if args.advisory else 2

    module_path = args.module
    if module_path is None:
        resolved = _resolve_go_module(content_dir)
        if resolved:
            alias, import_path, module_path = resolved
            _EXTRA_IMPORT_HEURISTICS.append(
                (re.compile(rf"\b{re.escape(alias)}\."), f'{alias} "{import_path}"')
            )
        else:
            module_path = _PDF_GO_MODULE

    errors = check_content_dir(
        content_dir,
        go_exe,
        module_path=module_path,
        go_version=args.go_version,
    )

    timeouts = [e[len("TIMEOUT:"):] for e in errors if e.startswith("TIMEOUT:")]
    failures = [e for e in errors if not e.startswith("TIMEOUT:")]

    if timeouts:
        print(f"WARNING: {len(timeouts)} block(s) timed out (advisory — not counted as failures):")
        for t in timeouts:
            print(f"  {t}")

    if not failures:
        md_count = len(list(content_dir.rglob("*.md")))
        print(f"PASS: Go code blocks OK ({md_count} .md files checked)")
        return 0

    label = "WARN" if args.advisory else "FAIL"
    print(f"{label}: {len(failures)} Go code block(s) failed go vet:\n")
    for err in failures:
        print(err)
    if args.advisory:
        print("(advisory mode — exit 0)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
