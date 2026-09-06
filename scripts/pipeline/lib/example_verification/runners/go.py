"""
lib/example_verification/runners/go.py

CONTRACT: scripts/pipeline/lib/example_verification/runners/go.py
  purpose: C5 (MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION) --
           the Go-wrapping/module-resolution helpers extracted from
           scripts/ci/checks/check_go_code_blocks.py, which becomes a thin
           wrapper importing these functions back (re-exported so
           scripts/pipeline/tests/test_ci_go_code_blocks.py's existing
           `from check_go_code_blocks import (...)` imports keep working
           unchanged, and so the CLI's own `go vet` behavior stays
           byte-identical -- proven via an old-vs-new error-set diff over
           both real Go products' content, see this taskcard's own
           promotion-gate evidence).
  inputs:  a fenced ```go code block's raw text; a Go product's family name
  outputs: _wrap_fragment/_infer_imports/_has_top_level_main (pure text
           transforms); _resolve_go_module/_find_module_replace_path (real
           filesystem reads of knowledge/ and runs/.clone_cache/)
  owner_domain: content-quality

Two real bugs fixed while moving (both explicitly named in the governing
plan's C5 consumer-wiring row):

1. `_resolve_go_module` used to read ONLY `knowledge/{family}/go/scout/
   model.yaml` -- but `scout/` is gitignored (`/knowledge/*/*/scout/` in
   .gitignore), so on a fresh checkout/CI box with no local scout run, this
   silently returned None for every real product and the caller fell back
   to a hardcoded pdf/go-specific default, which is simply WRONG for any
   other Go product (e.g. cells/go). Now checks `merged/model.yaml` first
   (git-tracked), falling back to `scout/model.yaml` only if merged lacks
   these fields. Honest limit, disclosed in this taskcard's own promotion-
   gate writeup: `merged/model.yaml` does not actually carry
   `canonical_import`/`package_name` today (nothing currently writes them
   there -- that's a `promote.py` change, outside this taskcard's
   allowed_paths) -- so in TODAY'S real portfolio this is a forward-
   compatible no-op that changes nothing yet, but it is the first half of
   closing the gap, and behavior for every existing caller (dev machines
   with a real scout/ present) is unchanged.
2. `_find_module_replace_path` used to scan EVERY directory under
   `runs/.clone_cache/`, opening each one's `go.mod` and substring-matching
   `module_path` against its text -- slow, and could in principle match the
   wrong clone if two unrelated Go products' go.mod files both happened to
   reference the same dependency path. Now resolves the caller's own
   product's clone directly via `lib.example_verification.policy.
   clone_cache_path(family, "go")` (the same `{root}/aspose_{family}_
   {platform}` layout `runners/python.py`'s `acquire_python_environment`
   already relies on) when `family` is known, still verifying that clone's
   own go.mod actually contains `module_path` before trusting it. Falls
   back to the old full-scan behavior when `family` isn't provided, so any
   caller that doesn't know it (there are none today, but this keeps the
   function's public contract additive, not breaking).
"""
from __future__ import annotations

import re
from pathlib import Path

from ..policy import clone_cache_path

_REPO_ROOT = Path(__file__).resolve().parents[5]

# Module path for the pdf/go library (injected into go.mod via replace directive) --
# the pre-existing hardcoded default, kept for callers that can't resolve a real
# product's module (e.g. no model.yaml anywhere yet).
_PDF_GO_MODULE = "github.com/aspose-pdf-foss/aspose-pdf-foss-for-go"

# Heuristics: if code uses these prefixes, inject the corresponding import
_IMPORT_HEURISTICS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bpdf\."), f'pdf "{_PDF_GO_MODULE}"'),
    (re.compile(r"\basposepdf\."), f'asposepdf "{_PDF_GO_MODULE}"'),
]

# Populated per-run (by check_go_code_blocks.py's main(), which imports this same
# list object and appends to it) for whichever family/platform is being checked --
# this script originally only ever ran against pdf/go, so the import heuristic above
# was hardcoded rather than derived. Kept as a module-level list (not a parameter
# threaded through _vet_block/_wrap_fragment/_infer_imports) since this is a
# single-shot CLI process with no concurrency to race against.
_EXTRA_IMPORT_HEURISTICS: list[tuple[re.Pattern, str]] = []

_CANONICAL_IMPORT_RE = re.compile(r'import\s+(\w+)\s+"([^"]+)"')


def _resolve_go_module_for_family(
    family: str, repo_root: "Path | None" = None,
) -> "tuple[str, str, str] | None":
    """Derive (alias, import_path, bare_module_path) for the Go product
    *family*, preferring the git-tracked `merged/model.yaml` over the
    gitignored `scout/model.yaml` -- see this module's own docstring for
    why both are checked. `import_path` and `bare_module_path` are
    deliberately kept distinct: when the real package lives in a
    subdirectory, `canonical_import` includes that subdirectory, but a
    go.mod `replace` directive operates at the MODULE level -- it must
    target the bare module path (`model.yaml`'s `package_name` field),
    never the subpackaged import path, or `_find_module_replace_path`'s
    match against the real repo's `go.mod` silently fails and the block
    gets vetted with no local replace at all."""
    root = repo_root if repo_root is not None else _REPO_ROOT
    for tier in ("merged", "scout"):
        model_path = root / "knowledge" / family / "go" / tier / "model.yaml"
        if not model_path.is_file():
            continue
        try:
            text = model_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
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


def _resolve_go_module(
    content_dir: Path, repo_root: "Path | None" = None,
) -> "tuple[str, str, str] | None":
    """Same as `_resolve_go_module_for_family`, for callers that only have a
    platform root such as `content/docs.aspose.org/en/{family}/go` -- the
    family is always its parent directory, regardless of subdomain layout
    (with or without an `/en/` segment)."""
    return _resolve_go_module_for_family(content_dir.parent.name, repo_root)


def _find_module_replace_path(
    module_path: str, family: "str | None" = None, clone_cache_root: "Path | None" = None,
) -> "str | None":
    """Return a local path for a replace directive, if available in clone cache.

    Prefers a direct, deterministic lookup of *family*'s own clone
    (`clone_cache_path(family, "go", root=clone_cache_root)`) when `family`
    is known -- still verifying that clone's go.mod actually contains
    `module_path` before trusting it, rather than assuming any clone at
    that path is correct. Falls back to scanning every directory under the
    clone cache root (the pre-fix behavior) when `family` is absent, or
    when that family's own clone doesn't have this module. `clone_cache_root`
    defaults to this repo's real `runs/.clone_cache`; tests pass an explicit
    value instead of touching the real cache."""
    root = clone_cache_root if clone_cache_root is not None else (_REPO_ROOT / "runs" / ".clone_cache")

    if family:
        candidate = clone_cache_path(family, "go", root=root)
        go_mod = candidate / "go.mod"
        if go_mod.is_file():
            try:
                text = go_mod.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            if module_path in text:
                return str(candidate).replace("\\", "/")

    if not root.is_dir():
        return None
    for d in root.iterdir():
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
