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

# Module path for the pdf/go library (injected into go.mod via replace directive)
_PDF_GO_MODULE = "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"

# Heuristics: if code uses these prefixes, inject the corresponding import
_IMPORT_HEURISTICS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bpdf\."), f'pdf "{_PDF_GO_MODULE}"'),
    (re.compile(r"\basposepdf\."), f'asposepdf "{_PDF_GO_MODULE}"'),
]

# Populated per-run by _resolve_go_module() for whichever family/platform is
# being checked -- this script originally only ever ran against pdf/go, so
# the import heuristic above was hardcoded rather than derived. Kept as a
# module-level list (not a parameter threaded through _vet_block/
# _wrap_fragment/_infer_imports) since this script is a single-shot CLI
# process with no concurrency to race against.
_EXTRA_IMPORT_HEURISTICS: list[tuple[re.Pattern, str]] = []

_CANONICAL_IMPORT_RE = re.compile(r'import\s+(\w+)\s+"([^"]+)"')


def _resolve_go_module(content_dir: Path, repo_root: Path | None = None) -> tuple[str, str, str] | None:
    """Derive (alias, import_path, bare_module_path) for the Go product
    under *content_dir*.

    *repo_root* defaults to the real `REPO_ROOT`; tests pass an explicit
    value instead of monkeypatching the module global (dependency
    injection seam, preferred per docs/development/testing-seams.md over
    broad monkeypatching -- AGENTS.md §16 T1/T2 policy blocks
    `monkeypatch.setattr` on module-level names like `REPO_ROOT` in
    staged test files).

    *content_dir* is a platform root such as
    `content/docs.aspose.org/en/{family}/go` -- the family is always its
    parent directory, regardless of subdomain layout (with or without an
    `/en/` segment). Reads the real, scouted
    `knowledge/{family}/go/scout/model.yaml`'s `canonical_import` field
    (e.g. `import cells_foss "github.com/aspose-cells-foss/.../v26/aspose/
    cells_foss"`) for the alias + the exact import path to inject into
    vetted code, rather than hardcoding a per-family constant, so this
    generalizes to every future Go product automatically.

    `import_path` and `bare_module_path` are deliberately kept distinct:
    when the real package lives in a subdirectory (package_manifest.py's
    `_detect_go_package_subpath`), `canonical_import` includes that
    subdirectory, but a go.mod `replace` directive operates at the MODULE
    level -- it must target the bare module path (`model.yaml`'s
    `package_name` field), never the subpackaged import path, or
    `_find_module_replace_path`'s substring match against the real repo's
    `go.mod` (which only ever contains the bare module line) silently
    fails to match and the block gets vetted with no local replace at all.
    """
    family = content_dir.parent.name
    root = repo_root if repo_root is not None else REPO_ROOT
    model_path = root / "knowledge" / family / "go" / "scout" / "model.yaml"
    if not model_path.is_file():
        return None
    try:
        text = model_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    alias = import_path = bare_module_path = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("canonical_import:"):
            m = _CANONICAL_IMPORT_RE.search(line)
            if m:
                alias, import_path = m.group(1), m.group(2)
        elif stripped.startswith("package_name:"):
            bare_module_path = stripped[len("package_name:"):].strip().strip('"').strip("'")
    if alias and import_path and bare_module_path:
        return alias, import_path, bare_module_path
    return None

# Pattern to extract fenced go code blocks
_GO_BLOCK_RE = re.compile(r"```go\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _find_go() -> str | None:
    return shutil.which("go")


def _needs_package_wrapper(code: str) -> bool:
    return not re.search(r"^\s*package\s+\w+", code, re.MULTILINE)


def _has_leading_import(code: str) -> bool:
    """True when the block starts with an import declaration (no package line)."""
    return bool(re.search(r"^\s*import\s", code, re.MULTILINE))


def _has_top_level_main(code: str) -> bool:
    """True when *code* already declares its own `func main(` at column 0.

    Real upstream examples (and this repo's own verified snippets/) are
    frequently complete `func main() { ... }` programs, not bare statement
    fragments. Found live (cells/go launch, 2026-07-28): `_wrap_fragment`
    unconditionally wrapped ANY non-`package`-prefixed block in a second
    `func main() { ... }`, producing an illegal nested `func main` (Go only
    allows anonymous `func() {}` literals inside a function body) --
    `go vet` fails with "expected '(', found main" on the nested named
    function. This is a pre-existing bug, not specific to any one product:
    the same double-wrap would hit pdf/go's own quickstart.md `func main`
    block (which has a leading `import (...)`) if it were ever re-staged,
    it just was never re-vetted since this checker's introduction.
    """
    return bool(re.search(r"^[ \t]*func\s+main\s*\(", code, re.MULTILINE))


def _infer_imports(code: str) -> list[str]:
    imports: list[str] = []
    for pattern, import_line in _IMPORT_HEURISTICS + _EXTRA_IMPORT_HEURISTICS:
        if pattern.search(code):
            imports.append(f'\t{import_line}')
    if re.search(r'\bfmt\.', code):
        imports.append('\t"fmt"')
    if re.search(r'\bos\.', code):
        imports.append('\t"os"')
    return imports


def _wrap_fragment(code: str) -> str:
    if _has_leading_import(code):
        # Block already has import declarations — extract them and wrap
        # only the non-import body in func main().
        import_lines: list[str] = []
        body_lines: list[str] = []
        in_import_block = False
        past_imports = False
        for line in code.splitlines():
            stripped = line.strip()
            if not past_imports:
                if stripped.startswith("import ") and "(" not in stripped:
                    # Single-line import: import pdf "..."
                    import_lines.append(line)
                    continue
                if stripped == "import (" or stripped.startswith("import ("):
                    in_import_block = True
                    import_lines.append(line)
                    continue
                if in_import_block:
                    import_lines.append(line)
                    if stripped == ")":
                        in_import_block = False
                    continue
                if stripped == "" and not body_lines:
                    continue  # skip blank lines between imports and body
                past_imports = True
            body_lines.append(line)
        body = "\n".join(body_lines)
        extra = _infer_imports(body)
        # Merge user imports with inferred ones (avoid duplicates)
        existing = "\n".join(import_lines)
        merged: list[str] = []
        for imp in extra:
            if imp.strip().strip('"') not in existing:
                merged.append(imp)
        if import_lines:
            # Rebuild as import block
            all_imports = "import (\n"
            # Extract import paths from existing lines
            for il in import_lines:
                s = il.strip()
                if s in ("import (", ")") or s.startswith("import ("):
                    continue
                if s.startswith("import "):
                    all_imports += "\t" + s[7:].strip() + "\n"
                else:
                    all_imports += "\t" + s + "\n"
            for m in merged:
                all_imports += m + "\n"
            all_imports += ")\n"
        else:
            all_imports = ""
        if _has_top_level_main(body):
            # Body is already a complete program (e.g. `func main() { ... }`
            # copied verbatim from a real snippet/example) -- emit it as-is,
            # not nested inside a second func main (illegal Go).
            return f"package main\n\n{all_imports}\n{body}\n"
        indented = "\n".join("\t" + line for line in body_lines)
        return f"package main\n\n{all_imports}\nfunc main() {{\n{indented}\n}}\n"

    if _has_top_level_main(code):
        imports = _infer_imports(code)
        import_block = ""
        if imports:
            import_block = "import (\n" + "\n".join(imports) + "\n)\n\n"
        return f"package main\n\n{import_block}{code}\n"

    imports = _infer_imports(code)
    import_block = ""
    if imports:
        import_block = "import (\n" + "\n".join(imports) + "\n)\n\n"
    indented = "\n".join("\t" + line for line in code.splitlines())
    return f"package main\n\n{import_block}func main() {{\n{indented}\n}}\n"


def _find_module_replace_path(module_path: str) -> str | None:
    """Return a local path for a replace directive, if available in clone cache."""
    clone_cache = REPO_ROOT / "runs" / ".clone_cache"
    if not clone_cache.is_dir():
        return None
    for d in clone_cache.iterdir():
        if not d.is_dir():
            continue
        go_mod = d / "go.mod"
        if not go_mod.exists():
            continue
        try:
            text = go_mod.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if module_path in text:
            return str(d).replace("\\", "/")
    return None


def _vet_block(
    go_exe: str,
    code: str,
    source_file: str,
    block_index: int,
    module_path: str,
    go_version: str,
) -> str | None:
    """Vet a single Go code block. Returns None on success, error string on failure."""
    wrapped = _wrap_fragment(code) if _needs_package_wrapper(code) else code

    with tempfile.TemporaryDirectory(prefix="go_vet_") as tmpdir:
        tmp = Path(tmpdir)
        go_mod_lines = [f"module check_block\n\ngo {go_version}\n"]
        replace_path = _find_module_replace_path(module_path)
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
            err = _vet_block(go_exe, block, rel, i, module_path, go_version)
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
