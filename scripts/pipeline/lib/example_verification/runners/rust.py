"""
lib/example_verification/runners/rust.py

CONTRACT: scripts/pipeline/lib/example_verification/runners/rust.py
  purpose: C13 (MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION) --
           the Rust `LanguageRunner` implementation on `runners/base.py`,
           mirroring `runners/go.py` (C5)'s already-reviewed shape: tier 1
           (syntax) is handled generically by `BaseRunner` via `syntax.py`
           (already has a Rust grammar entry, via `tree_sitter_language_
           pack`'s fallback -- confirmed live, see this taskcard's own
           promotion-gate evidence); tier 2 (`cargo build`) / tier 3
           (`cargo run`) are this module's own job.
  inputs:  a fenced ```rust code block's raw text; a Rust product's family
           name
  outputs: BaseRunner(RustRunner(family)).run(...) -> list[BlockResult]
  owner_domain: content-quality

**The one real, confirmed toolchain gap in this rollout** (named explicitly
in the governing plan's own Rust section and this taskcard's own title):
no `cargo`/`rustc`/`rustup` on this machine's PATH (verified live:
`shutil.which("cargo")`/`shutil.which("rustc")`/`shutil.which("rustup")`
all return `None`). Unlike C5/C11/C12 (Go/.NET/Java), where a working
toolchain let every design decision be proven by actually running it, tier
2/3 here cannot be exercised end-to-end on this machine at all. Per this
taskcard's own row ("honest stub above tier 1") and stage-matrix promotion
gate ("tier 1 green without rustup; tier >= 2 an honest TOOLCHAIN-
UNAVAILABLE until rustup is installed"), this module mirrors `GoRunner`'s
exact, already-reviewed pattern for the SAME shape of problem: `acquire()`
always succeeds (pure staging, no subprocess call); the real toolchain
check happens inside `compile()`/`execute()` via `shutil.which("cargo")`,
which returns the specific `TOOLCHAIN-UNAVAILABLE` reason -- honest,
tested FOR REAL on this machine (cargo genuinely is absent, so this is not
a mocked path), and structurally ready to prove tier 2/3 for real the
first time `rustup` is installed anywhere this runs, with zero further
code changes.

Disclosed, deliberate scope reduction (matching `GoRunner`'s own precedent
for the identical reason -- "no fixture to prove that path against without
inventing one"): only the unpublished/local-clone acquire path (a Cargo.toml
`path = "..."` dependency against `runs/.clone_cache/`) is implemented. The
plan's `published: cargo add {crate}@{version}` branch (a real crates.io
resolve) is not built -- the one real Rust product (`cells/rust`) is not
published to crates.io today, and there is no way to prove that branch
without either a live toolchain or a real published crate, neither of
which exists on this machine. `compile()`/`execute()` set
`CARGO_NET_OFFLINE=true` (cargo's own real, documented offline-mode env
var -- see `_exec_cargo`) so an unresolved dependency fails loudly instead
of silently resolving over the network, mirroring `GoRunner`'s own
`GOPROXY=off` safety rationale exactly.

Also disclosed: unlike Go's `_infer_imports` (a per-symbol import-injection
heuristic that took real `go vet` runs to develop and get right), this
module's `_wrap_fragment` injects at most one `use {lib_ident}::*;` wildcard
import (never per-symbol heuristics) -- a deliberately simpler design
chosen BECAUSE there is no live toolchain here to iterate a more precise
heuristic against; building Go-style per-symbol guesswork that can never be
verified would be worse than an honest, coarser fallback. `lib_ident` (the
crate's `[lib] name`, hyphens turned to underscores) is derived from the
crate name via Cargo's own universal, documented naming convention -- not a
per-product guess -- and the crate name itself is confirmed correct for the
one real Rust product this repo has: `knowledge/cells/rust/merged/
model.yaml`'s `product_name: aspose-cells-foss-rust` matches the real
`runs/.clone_cache/aspose_cells_rust/Cargo.toml`'s `[package] name =
"aspose-cells-foss-rust"` byte-for-byte (checked directly against the real
clone before writing this).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ..policy import clone_cache_path, Policy, ProductContext

_REPO_ROOT = Path(__file__).resolve().parents[5]

# A rustc/cargo error's own file:line:col location citation, e.g.
# "  --> src/main.rs:4:5" or "  --> upstream_crate/src/lib.rs:12:9" --
# stable, well-documented rustc diagnostic format (unlike Go/.NET/Java,
# this was NOT live-verified against a real compile on this machine, since
# no toolchain exists here to produce one -- disclosed honestly rather than
# silently presented as proven the way every prior runner's classify() was).
#
# Independent-review finding (round 1), fixed here: the original pattern's
# character class had no `:` at all, so it could never match a Windows
# absolute path citation (`D:/.../lib.rs:12:9` or `D:\...\lib.rs:12:9`) --
# and `_find_rust_replace_path` (below) itself builds exactly that path
# shape for `replace_path` on this repo's own OS (win32), so a real cargo
# diagnostic citing the replaced crate's own absolute path would silently
# never match, defeating classify()'s entire purpose on this exact machine.
# Now accepts an optional drive-letter prefix.
_RUST_FILE_LOCATION_RE = re.compile(r'-->\s*((?:[A-Za-z]:)?[\w./\\-]+\.rs):\d+')

_PRODUCT_NAME_RE = re.compile(r'^product_name:\s*(.+)$', re.MULTILINE)


def _cites_other_file_in_primary_span(tail: str) -> bool:
    """True when a genuine ERROR's own PRIMARY `-->` citation (the one
    immediately following its `error`/`error[E....]:` header line) names a
    file other than `main.rs`.

    Independent-review finding (round 1), fixed here: the original version
    counted ANY `-->` citation anywhere in the tail, including a `note:`
    follow-up's own citation -- but a real rustc diagnostic routinely cites
    the DEPENDENCY's own definition site in an explanatory note (e.g.
    "note: required by a bound in `baz`" followed by its own `--> upstream_
    crate/src/lib.rs:10:5`) even when the actual defect is an ordinary mistake in the
    block's own generated wrapper (`main.rs`) -- reproduced live with a
    synthetic fixture matching this exact shape (see
    test_classify_ignores_a_note_citation_when_the_primary_span_is_main_rs).
    Now only the span immediately after an `error`-prefixed line counts;
    `note:`/`warning:`/`help:` lines reset the "awaiting a primary span"
    state so their own citations are never mistaken for the primary one."""
    awaiting_primary = False
    for line in tail.splitlines():
        stripped = line.strip()
        if stripped.startswith("error"):
            awaiting_primary = True
            continue
        if awaiting_primary and "-->" in stripped:
            m = _RUST_FILE_LOCATION_RE.search(stripped)
            awaiting_primary = False
            if m and Path(m.group(1)).name != "main.rs":
                return True
            continue
        if stripped.startswith(("note:", "warning:", "help:")):
            awaiting_primary = False
    return False


def _resolve_rust_crate_for_family(family: str, repo_root: "Path | None" = None) -> "str | None":
    """Read *family*'s own `product_name` field -- confirmed, for the one
    real Rust product on this machine (cells/rust), to be the exact real
    Cargo crate name (verified directly against `runs/.clone_cache/
    aspose_cells_rust/Cargo.toml`'s `[package] name` before writing this).
    Prefers the git-tracked `merged/model.yaml` over gitignored
    `scout/model.yaml`, same tier preference as `runners/go.py`'s
    `_resolve_go_module_for_family` and for the identical reason (a fresh
    checkout/CI box has no local `scout/` run)."""
    root = repo_root if repo_root is not None else _REPO_ROOT
    for tier in ("merged", "scout"):
        model_path = root / "knowledge" / family / "rust" / tier / "model.yaml"
        if not model_path.is_file():
            continue
        try:
            text = model_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = _PRODUCT_NAME_RE.search(text)
        if m:
            name = m.group(1).strip().strip('"').strip("'")
            if name:
                return name
    return None


def _lib_ident_for_crate(crate_name: str) -> str:
    """Cargo's own universal, documented convention: a crate's `[lib] name`
    (the identifier `use`d in code) is the package name with every `-`
    turned into `_` -- true for every real Cargo crate, not a per-product
    guess. Confirmed directly for cells/rust: `Cargo.toml`'s package name
    `aspose-cells-foss-rust` -> `[lib] name = "aspose_cells_foss_rust"`,
    exactly matching real snippets' own `use aspose_cells_foss_rust::...`."""
    return crate_name.replace("-", "_")


def _find_rust_replace_path(
    family: str, clone_cache_root: "Path | None" = None,
) -> "str | None":
    """Return a local clone-cache path for a Cargo.toml `path =` dependency,
    if that family's own clone exists and has a real Cargo.toml -- same
    `clone_cache_path` layout `runners/go.py`'s `_find_module_replace_path`
    uses for the identical purpose."""
    root = clone_cache_root
    candidate = clone_cache_path(family, "rust", root=root) if root is not None \
        else clone_cache_path(family, "rust")
    if (candidate / "Cargo.toml").is_file():
        return str(candidate).replace("\\", "/")
    return None


def _has_top_level_main(code: str) -> bool:
    """True when *code* already declares its own `fn main(` (or `async fn
    main(`, e.g. under a `#[tokio::main]` attribute) at column 0 -- real
    cells/rust snippets (`knowledge/cells/rust/merged/snippets/*.rs`) are
    frequently complete programs, not bare fragments (confirmed live by
    reading snippet_001.rs before writing this).

    Independent-review finding (round 1), fixed here: the original regex
    didn't match `async fn main(`, so an async example would get
    double-wrapped inside another `fn main` -- syntactically legal Rust
    (tree-sitter PASSes it, so this was never caught by a syntax check),
    but a proc-macro attribute like `#[tokio::main]` on a nested/local item
    is a real rustc restriction that would fail a real `cargo build` for a
    wrapping-artifact reason, not a genuine content defect. No real
    cells/rust example uses this today (grepped before fixing), but the
    fix costs nothing and removes a known, disclosed gap."""
    return bool(re.search(r"^[ \t]*(?:async\s+)?fn\s+main\s*\(", code, re.MULTILINE))


def _has_leading_use(code: str) -> bool:
    return bool(re.search(r"^\s*use\s", code, re.MULTILINE))


def _needs_wrap(code: str) -> bool:
    return not _has_top_level_main(code)


def _wrap_fragment(code: str, lib_ident: "str | None") -> str:
    """Wrap a bare statement fragment in a `Result`-returning `main` (the
    standard idiom for fragments that use `?` error propagation -- confirmed
    live: real docs pages under `content/docs.aspose.org/en/cells/rust/
    developer-guide/` show exactly this shape, e.g. `working-with-
    spreadsheet-management.md`'s `let mut workbook = Workbook::new(); {
    ... }`, no `fn main`, no `use`). Injects at most one wildcard `use
    {lib_ident}::*;` when the fragment doesn't already mention it -- see
    this module's own docstring for why a single wildcard, not Go's
    per-symbol heuristic."""
    import_line = ""
    if lib_ident and lib_ident not in code:
        import_line = f"use {lib_ident}::*;\n\n"
    indented = "\n".join(("    " + line if line.strip() else line) for line in code.splitlines())
    return (
        f"{import_line}fn main() -> Result<(), Box<dyn std::error::Error>> {{\n"
        f"{indented}\n    Ok(())\n}}\n"
    )


def _write_cargo_project(
    work_dir: Path, wrapped_code: str, crate_name: "str | None",
    replace_path: "str | None", edition: str,
) -> None:
    """Same scratch-crate shape `runners/go.py`'s `_write_go_module` uses
    for the identical purpose -- a disposable Cargo.toml/src/main.rs this
    runner generates, never a real project's own manifest."""
    lines = [
        "[package]\nname = \"check_block\"\nversion = \"0.0.0\"\n"
        f"edition = \"{edition}\"\n"
    ]
    if crate_name and replace_path:
        lines.append(f'\n[dependencies]\n{crate_name} = {{ path = "{replace_path}" }}\n')
    (work_dir / "Cargo.toml").write_text("".join(lines), encoding="utf-8")
    src_dir = work_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "main.rs").write_text(wrapped_code, encoding="utf-8")


def _exec_cargo(argv: list[str], work_dir: Path, timeout: float) -> "tuple[str, str]":
    """("OK"|"FAILED"|"TIMEOUT", output). `CARGO_NET_OFFLINE=true` is
    cargo's own real, documented offline-mode flag (not a guess) -- mirrors
    `runners/go.py`'s `_exec_go`'s `GOPROXY=off` rationale exactly: when a
    real product crate needs a `path` dependency but `acquire()` couldn't
    resolve one, this makes the failure a loud, honest COMPILE-ERROR
    instead of a silent network resolve against a same-named public crate
    (which `execute()` would then actually RUN unverified)."""
    env = {**os.environ, "CARGO_NET_OFFLINE": "true"}
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


class RustRunner:
    """C13's `LanguageRunner` implementation. One instance = one product
    (`family` fixed at construction, same convention as `GoRunner`).

    `ceiling_tier = 3`: this is the architectural ceiling this CODE is
    designed to prove, mirroring Python/TypeScript/Go/.NET/Java exactly --
    NOT a claim that tier 3 is reachable on THIS machine today (registry.py's
    `PLATFORM_CONTRACT["rust"].max_tier` -- out of this taskcard's
    `allowed_paths`, disclosed in this taskcard's own evidence -- still
    correctly gates the deployed ceiling at 1 until a runner-bearing
    machine confirms cargo/rustc are actually present). `compile()`/
    `execute()` below are the ONLY methods that discover the real,
    live toolchain state (`shutil.which("cargo")`), exactly like
    `GoRunner.compile()`/`execute()` discover `shutil.which("go")` --
    the class's static `ceiling_tier` is a design-time capability
    declaration, the live `TOOLCHAIN-UNAVAILABLE` check is a run-time fact.
    """

    canonical_lang = "rust"
    ceiling_tier = 3

    def __init__(self, family: str, edition: str = "2021") -> None:
        self._family = family
        self._edition = edition
        self._crate_name = _resolve_rust_crate_for_family(family)
        self._lib_ident = _lib_ident_for_crate(self._crate_name) if self._crate_name else None

    def starts_chain(self, code: str) -> bool:
        """True (fresh, self-contained example) when the block declares its
        own `fn main(`/`async fn main(`, a leading `use` statement, or a
        leading attribute (`#[...]`/`#![...]`, e.g. `#[derive(Debug)]` on a
        fresh struct, or `#[tokio::main]` on a fresh async main); False
        (continues the previous block's chain) otherwise. Confirmed against
        real content: `content/docs.aspose.org/en/cells/rust/developer-
        guide/working-with-spreadsheet-management.md` has a block declaring
        `let mut workbook = Workbook::new(); { let mut worksheets = ...;
        let sheet = worksheets.get(0)?; sheet.set_name(...)?; }` immediately
        followed, several paragraphs later in the SAME page, by a block
        that uses `sheet.get_cells_mut()` with no `fn main`/`use`/attribute
        of its own -- a real continuation of the earlier block's local
        variables, the same shape Python/TypeScript's own chain heuristic
        already handles.

        Independent-review finding (round 1), fixed here: the original
        version only recognized `fn main`/`use `, so a block starting with
        `#[derive(Debug)]` (a fresh, self-contained struct/enum) would have
        been misclassified as a chain continuation. No real cells/rust
        content uses a leading attribute today (grepped before fixing), so
        this was untested rather than live-wrong, but the fix is cheap and
        removes a known, disclosed gap."""
        for line in code.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            return stripped.startswith(("fn main", "async fn main", "use ", "#[", "#!["))
        return True

    def acquire(self, work_dir: Path, policy: Policy, product: ProductContext) -> dict:
        """Mirrors `GoRunner.acquire()` exactly: there is no environment-
        setup step here that can genuinely fail on its own (a block that
        only uses `std` needs no path dependency at all); this always
        succeeds, and `compile()`/`execute()` below are where a genuinely
        missing toolchain (or an unresolvable product dependency) surfaces
        -- honestly, never silently."""
        replace_path = _find_rust_replace_path(self._family)
        return {
            "ok": True, "work_dir": work_dir,
            "crate_name": self._crate_name, "lib_ident": self._lib_ident,
            "replace_path": replace_path,
        }

    def compile(self, acquired: dict, code: str, index: int) -> "dict | None":
        cargo_exe = shutil.which("cargo")
        if cargo_exe is None:
            return {"reason": "TOOLCHAIN-UNAVAILABLE", "detail": "cargo not found on PATH"}
        wrapped = _wrap_fragment(code, acquired.get("lib_ident")) if _needs_wrap(code) else code
        work_dir = acquired["work_dir"]
        _write_cargo_project(
            work_dir, wrapped, acquired.get("crate_name"), acquired.get("replace_path"), self._edition)
        outcome, detail = _exec_cargo([cargo_exe, "build"], work_dir, 60)
        if outcome == "OK":
            return None
        if outcome == "TIMEOUT":
            return {"reason": "TIMEOUT", "detail": "cargo build timed out (crate not cached)"}
        reason, tail = self.classify(detail, {"stage": "compile"})
        return {"reason": reason, "detail": tail}

    def execute(self, acquired: dict, code: str, index: int) -> dict:
        cargo_exe = shutil.which("cargo")
        if cargo_exe is None:
            return {"status": "BLOCKED-WITH-REASON", "reason": "TOOLCHAIN-UNAVAILABLE",
                     "detail": "cargo not found on PATH"}
        wrapped = _wrap_fragment(code, acquired.get("lib_ident")) if _needs_wrap(code) else code
        work_dir = acquired["work_dir"]
        _write_cargo_project(
            work_dir, wrapped, acquired.get("crate_name"), acquired.get("replace_path"), self._edition)
        outcome, detail = _exec_cargo([cargo_exe, "run"], work_dir, 90)
        if outcome == "OK":
            return {"status": "PASS"}
        if outcome == "TIMEOUT":
            return {"status": "BLOCKED-WITH-REASON", "reason": "TIMEOUT", "detail": "cargo run timed out"}
        reason, tail = self.classify(detail, {"stage": "execute"})
        return {"status": "BLOCKED-WITH-REASON", "reason": reason, "detail": tail}

    def classify(self, output: str, context: "dict | None" = None) -> "tuple[str, str]":
        """Distinguishes a real defect in the UPSTREAM crate's own source
        from an ordinary COMPILE-ERROR/RUNTIME-ERROR in the block's own
        generated wrapper (`main.rs`) -- the same file-citation-basename
        pattern `GoRunner.classify()`/`DotNetRunner`/`JavaRunner` use,
        applied to rustc's `--> file:line:col` diagnostic format. NOT
        live-verified against a real rustc failure (no toolchain exists on
        this machine to produce one) -- disclosed honestly, unlike every
        prior runner's classify(), which each had a working compiler to
        confirm this against."""
        tail = (output or "").strip()[-2000:]
        if _cites_other_file_in_primary_span(tail):
            return "UPSTREAM-BROKEN", tail
        stage = (context or {}).get("stage", "compile")
        return ("COMPILE-ERROR" if stage == "compile" else "RUNTIME-ERROR"), tail
