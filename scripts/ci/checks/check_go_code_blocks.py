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

# Pattern to extract fenced go code blocks
_GO_BLOCK_RE = re.compile(r"```go\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _find_go() -> str | None:
    return shutil.which("go")


def _needs_package_wrapper(code: str) -> bool:
    return not re.search(r"^\s*package\s+\w+", code, re.MULTILINE)


def _has_leading_import(code: str) -> bool:
    """True when the block starts with an import declaration (no package line)."""
    return bool(re.search(r"^\s*import\s", code, re.MULTILINE))


def _infer_imports(code: str) -> list[str]:
    imports: list[str] = []
    for pattern, import_line in _IMPORT_HEURISTICS:
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
        indented = "\n".join("\t" + line for line in body_lines)
        extra = _infer_imports("\n".join(body_lines))
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
        return f"package main\n\n{all_imports}\nfunc main() {{\n{indented}\n}}\n"

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
            go_mod_lines.append(
                f"\nrequire {module_path} v0.0.0\n"
                f"replace {module_path} => {replace_path}\n"
            )
        (tmp / "go.mod").write_text("".join(go_mod_lines), encoding="utf-8")
        (tmp / "main.go").write_text(wrapped, encoding="utf-8")

        try:
            result = subprocess.run(
                [go_exe, "vet", "./..."],
                capture_output=True,
                text=True,
                cwd=str(tmp),
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return f"{source_file} block #{block_index + 1}: go vet timed out"

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
            # Skip import-only blocks (no executable code to vet)
            stripped_lines = [
                ln for ln in block.strip().splitlines()
                if ln.strip() and not re.match(
                    r'^\s*(import\s|import\s*\(|\)|"[^"]*"$|[a-zA-Z]+\s+"[^"]*"$)',
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
        default=_PDF_GO_MODULE,
        help=f"Go module path (default: {_PDF_GO_MODULE})",
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

    errors = check_content_dir(
        content_dir,
        go_exe,
        module_path=args.module,
        go_version=args.go_version,
    )

    if not errors:
        md_count = len(list(content_dir.rglob("*.md")))
        print(f"PASS: Go code blocks OK ({md_count} .md files checked)")
        return 0

    label = "WARN" if args.advisory else "FAIL"
    print(f"{label}: {len(errors)} Go code block(s) failed go vet:\n")
    for err in errors:
        print(err)
    if args.advisory:
        print("(advisory mode — exit 0)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
