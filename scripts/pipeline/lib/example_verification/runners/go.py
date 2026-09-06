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

import os
import re
import shutil
import subprocess
from pathlib import Path

from ..policy import clone_cache_path, Policy, ProductContext

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

# A go vet/go run error's own file:line location citation -- e.g.
# "..\upstream_pkg\lib.go:4:2: undefined: x" or
# "C:/tmp/.../main.go:5 +0x9" -- used by GoRunner.classify() below.
_GO_FILE_LOCATION_RE = re.compile(r'([\w./\\-]+\.go):\d+')


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


def _infer_imports(
    code: str, extra_heuristics: "list[tuple[re.Pattern, str]] | None" = None,
) -> list[str]:
    """`extra_heuristics` defaults to the module-level `_EXTRA_IMPORT_HEURISTICS`
    global (the CLI's own single-shot-process convention, mutated by
    `check_go_code_blocks.py`'s `main()`); pass an explicit list instead to avoid
    that shared, process-wide mutable state -- `GoRunner` (below) does this, since
    a single process may construct runners for more than one family/product and
    must not have one instance's alias heuristic leak into another's."""
    heuristics = _IMPORT_HEURISTICS + (
        extra_heuristics if extra_heuristics is not None else _EXTRA_IMPORT_HEURISTICS
    )
    imports: list[str] = []
    for pattern, import_line in heuristics:
        if pattern.search(code):
            imports.append(f'\t{import_line}')
    if re.search(r'\bfmt\.', code):
        imports.append('\t"fmt"')
    if re.search(r'\bos\.', code):
        imports.append('\t"os"')
    return imports


def _wrap_fragment(
    code: str, extra_heuristics: "list[tuple[re.Pattern, str]] | None" = None,
) -> str:
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
        extra = _infer_imports(body, extra_heuristics)
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
        imports = _infer_imports(code, extra_heuristics)
        import_block = ""
        if imports:
            import_block = "import (\n" + "\n".join(imports) + "\n)\n\n"
        return f"package main\n\n{import_block}{code}\n"

    imports = _infer_imports(code, extra_heuristics)
    import_block = ""
    if imports:
        import_block = "import (\n" + "\n".join(imports) + "\n)\n\n"
    indented = "\n".join("\t" + line for line in code.splitlines())
    return f"package main\n\n{import_block}func main() {{\n{indented}\n}}\n"


def _needs_wrap(code: str) -> bool:
    return not re.search(r"^\s*package\s+\w+", code, re.MULTILINE)


def _write_go_module(
    work_dir: Path, wrapped_code: str, module_path: str, replace_path: "str | None", go_version: str,
) -> None:
    """Same scratch go.mod/main.go shape `check_go_code_blocks.py:_vet_block`
    already uses -- a disposable module the checker itself generates, never a
    real project's own go.mod."""
    go_mod_lines = [f"module check_block\n\ngo {go_version}\n"]
    if replace_path:
        # A module path with a major-version suffix (/vN, N>=2 -- Go's semantic
        # import versioning convention) requires the required version's own major
        # component to match that suffix (e.g. `.../v26` must be required at
        # `v26.x.y`, not `v0.0.0`) -- found live on cells/go.
        major_suffix = re.search(r"/v(\d+)$", module_path)
        placeholder_version = f"v{major_suffix.group(1)}.0.0" if major_suffix else "v0.0.0"
        go_mod_lines.append(
            f"\nrequire {module_path} {placeholder_version}\n"
            f"replace {module_path} => {replace_path}\n"
        )
    (work_dir / "go.mod").write_text("".join(go_mod_lines), encoding="utf-8")
    (work_dir / "main.go").write_text(wrapped_code, encoding="utf-8")


def _exec_go(argv: list[str], work_dir: Path, timeout: float) -> "tuple[str, str]":
    """("OK"|"FAILED"|"TIMEOUT", output). GOFLAGS=-mod=mod: a fresh go.mod
    referencing a local `replace` target has no go.sum entry yet; without this,
    the command refuses with "updates to go.mod needed" instead of running.
    GOPROXY=off: independent-reviewer finding -- when a real product module
    needs a replace directive but `acquire()` couldn't resolve one (evicted
    clone cache, fresh checkout), `-mod=mod` alone would let Go silently
    resolve the bare `require` over the real network against whatever public
    package happens to share that module path, and `execute()` would then
    actually RUN that unverified code with no error ever surfacing. Blocking
    the network here makes that failure loud (a real, honest COMPILE-ERROR/
    RUNTIME-ERROR) instead of silent."""
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(work_dir), timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", ""
    if result.returncode != 0:
        return "FAILED", (result.stderr or result.stdout or "").strip()
    return "OK", (result.stdout or "").strip()


class GoRunner:
    """C5 checkpoint 2: the first concrete `runners/base.py` `LanguageRunner`
    implementation -- syntax (tier 1, handled generically by `BaseRunner` via
    `syntax.py`, not here) -> compile (tier 2, `go vet`, the same check
    `check_go_code_blocks.py` already runs) -> execute (tier 3, `go run`, a real
    new capability this taskcard adds). One instance = one product (`family` is
    fixed at construction), so the alias import heuristic resolved from that
    product's own `model.yaml` is kept on the INSTANCE (`_extra_heuristics`),
    never mutating the module-level `_EXTRA_IMPORT_HEURISTICS` global
    `check_go_code_blocks.py`'s single-shot CLI process relies on -- a process
    that constructs runners for more than one family (this class's own test
    suite does) must not have one instance's alias leak into another's.

    Disclosed scope limit: only the unpublished/local-clone acquire path (a
    go.mod `replace` directive against `runs/.clone_cache/`) is implemented --
    matching what `check_go_code_blocks.py` has always done, and what both real
    Go products (cells/go, pdf/go) actually need today. The plan's `published:
    go get {module}@{version}` (a real proxy.golang.org resolve) branch is not
    built: neither real product is published this way, and there is no fixture
    to prove that path against without inventing one. `acquire()` always
    reports `{"ok": True}` (see its own docstring below for why); when a real
    product module needs a replace directive but none resolves, `compile()`/
    `execute()` run with `GOPROXY=off` (see `_exec_go`) so an unresolved
    dependency fails loudly at the vet/run stage instead of silently
    resolving over the network against a possibly-different or stale public
    package of the same name -- independent-reviewer finding, fixed here:
    an earlier draft had no such guard, so a missing replace path combined
    with `GOFLAGS=-mod=mod` could have silently succeeded against whatever a
    real network fetch happened to resolve, then `execute()` would have
    actually RUN that code."""

    canonical_lang = "go"
    ceiling_tier = 3

    def __init__(self, family: str, go_version: str = "1.24") -> None:
        self._family = family
        self._go_version = go_version
        resolved = _resolve_go_module_for_family(family)
        if resolved:
            alias, import_path, self._module_path = resolved
            self._extra_heuristics: "list[tuple[re.Pattern, str]]" = [
                (re.compile(rf"\b{re.escape(alias)}\."), f'{alias} "{import_path}"'),
            ]
        else:
            self._module_path = _PDF_GO_MODULE
            self._extra_heuristics = []

    def starts_chain(self, code: str) -> bool:
        """First non-comment line is `package`/`import` -- per the governing
        plan's own Go chain-start heuristic."""
        for line in code.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            return stripped.startswith(("package ", "import "))
        return True

    def acquire(self, work_dir: Path, policy: Policy, product: ProductContext) -> dict:
        """Unlike Python's real venv creation, there is no environment-setup
        step here that can genuinely fail -- a block that only uses stdlib
        (`fmt`/`os`) needs no replace directive at all, and `_write_go_module`
        already treats a `None` replace_path as "omit the replace block", the
        same way `check_go_code_blocks.py:_vet_block` always has. So this
        always succeeds; `replace_path` is simply `None` when this product has
        no resolvable local clone, and compile()/execute() below will fail
        (correctly, at the vet/run stage, never silently over the network --
        see `_exec_go`'s `GOPROXY=off`) only if the code actually references
        an unresolved product import."""
        replace_path = _find_module_replace_path(self._module_path, family=self._family)
        return {
            "ok": True, "work_dir": work_dir,
            "module_path": self._module_path, "replace_path": replace_path,
        }

    def compile(self, acquired: dict, code: str, index: int) -> "dict | None":
        go_exe = shutil.which("go")
        if go_exe is None:
            return {"reason": "TOOLCHAIN-UNAVAILABLE", "detail": "go not found on PATH"}
        wrapped = _wrap_fragment(code, self._extra_heuristics) if _needs_wrap(code) else code
        work_dir = acquired["work_dir"]
        _write_go_module(work_dir, wrapped, acquired["module_path"], acquired.get("replace_path"), self._go_version)
        outcome, detail = _exec_go([go_exe, "vet", "./..."], work_dir, 30)
        if outcome == "OK":
            return None
        if outcome == "TIMEOUT":
            return {"reason": "TIMEOUT", "detail": "go vet timed out (module not cached)"}
        reason, tail = self.classify(detail, {"stage": "compile", "replace_path": acquired.get("replace_path")})
        return {"reason": reason, "detail": tail}

    def execute(self, acquired: dict, code: str, index: int) -> dict:
        go_exe = shutil.which("go")
        if go_exe is None:
            return {"status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE",
                     "detail": "go not found on PATH"}
        wrapped = _wrap_fragment(code, self._extra_heuristics) if _needs_wrap(code) else code
        work_dir = acquired["work_dir"]
        _write_go_module(work_dir, wrapped, acquired["module_path"], acquired.get("replace_path"), self._go_version)
        outcome, detail = _exec_go([go_exe, "run", "main.go"], work_dir, 60)
        if outcome == "OK":
            return {"status": "PASS"}
        if outcome == "TIMEOUT":
            return {"status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT", "detail": "go run timed out"}
        reason, tail = self.classify(detail, {"stage": "execute", "replace_path": acquired.get("replace_path")})
        return {"status": "BLOCKED-WITH-REASON", "reason": reason, "detail": tail}

    def classify(self, output: str, context: "dict | None" = None) -> "tuple[str, str]":
        """Distinguishes a real defect in the UPSTREAM package's own source
        from an ordinary COMPILE-ERROR/RUNTIME-ERROR in the block's own
        generated wrapper (`main.go`).

        Independent-reviewer finding, fixed here: the original version checked
        whether the raw `replace_path` string appeared verbatim in the output --
        but real `go vet`/`go run` failures inside a replaced package cite a
        location RELATIVE to the invoking directory (e.g.
        `..\\upstream_pkg\\lib.go:4:2: undefined: ...`), never the replace
        target's own absolute path, so that check silently never fired
        (confirmed by reproducing a real replaced-package compile error).
        Now looks for ANY `<file>.go:<line>` location citation whose basename
        isn't `main.go` -- present for a real upstream defect (a citation
        inside the replaced package), absent for an ordinary error in the
        block's own generated wrapper (whose only citation is `main.go`,
        whether relative or the absolute path a runtime panic trace uses)."""
        tail = (output or "").strip()[-2000:]
        cites_other_file = any(
            Path(loc).name != "main.go" for loc in _GO_FILE_LOCATION_RE.findall(tail)
        )
        if cites_other_file:
            return "UPSTREAM-BROKEN", tail
        stage = (context or {}).get("stage", "compile")
        return ("COMPILE-ERROR" if stage == "compile" else "RUNTIME-ERROR"), tail
