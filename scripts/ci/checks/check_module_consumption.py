"""check_module_consumption.py — advisory check: does a module have a real
(non-test) consumer? (production concurrency redesign follow-up, MT019's
own .supervisor convergence audit, 2026-08-02, backlog G-48.)

Found live: 2 of 3 new library modules the concurrency redesign built
(taskcard_store.py, master_plan_index.py) reached "fully tested, correctly
implemented" status without anything outside their own test suite actually
calling them -- this repo's governance (registry.yaml's requires_test)
verifies a module HAS tests, not that it HAS a caller. Both gaps were caught
by manual self-audit within the same session they were introduced, but
nothing structurally guarantees a future mission does the same -- "hope the
next agent is equally diligent" is not a durable, consistent-across-reruns
design.

This is deliberately a coarse, on-demand ADVISORY check (matching
check_taskcard_plan_parity.py's own documented status: an agent-invoked
tool, NOT a CI/pre-commit gate) -- not wired into pre-commit by default.
Retrofitting all ~277 existing registry.yaml library entries would produce
mostly noise (many have real consumers this check's simple text-matching
heuristic won't recognize: dynamic imports, subprocess-only CLI invocation,
etc.). The intended use is proportionate and narrow: run it against a
JUST-BUILT module, once, before considering that module's own task
"done" -- the same moment this exact gap was found twice in one mission.

Detection: does the module's own name (as a Python import target, e.g.
`taskcard_store` for taskcard_store.py) appear anywhere in the repo's
scripts/ tree OUTSIDE the module's own file and any file whose name starts
with `test_` or lives under a `tests/`/`test/` directory?

MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION/TC-01: primary
detection is now a real AST import-graph walk (_ast_references_module),
not a substring search. The original substring heuristic (still present
as `_reference_pattern`) is demoted to a fallback used ONLY when a
candidate file fails to parse (e.g. a .py used as a text fixture) --
confirmed live bug in the original design: for a module named after a
common English word (`go.py`, `python.py`, `result.py`, `base.py`,
`cache.py` -- all real example_verification/ module names), the substring
search matched every DOCSTRING/COMMENT mention of that word, reporting
hundreds of false "real consumers" for modules that in fact had zero real
callers outside their own tests (found live during the
EXAMPLE-VERIFICATION-PRODUCTIONIZATION audit: `runners/python.py` scored
433 "consumers" this way). The AST walk only counts real `import`/
`from ... import` bindings (plus a dynamic-import-by-string check for the
`_pipeline_module("lib.example_verification.registry")` pattern this
codebase's own check_platform_capabilities.py already uses) -- a bare
word in a comment or docstring is not in the AST at all, so it can no
longer produce a false positive.

Usage:
    python check_module_consumption.py --module scripts/pipeline/lib/taskcard_store.py

Exit codes:
  0 -- at least one real (non-test) consumer found
  1 -- no real consumer found (advisory -- caller decides whether this
       blocks anything; this script itself never blocks a commit)
  2 -- module path not found / not a Python file
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCAN_ROOT = _REPO_ROOT / "scripts"

_EXCLUDED_DIR_PARTS = {"__pycache__", ".venv", "node_modules"}


def _is_test_path(path: Path) -> bool:
    if path.name.startswith("test_"):
        return True
    return any(part in ("tests", "test") for part in path.parts)


def _is_excluded_dir(path: Path) -> bool:
    return any(part in _EXCLUDED_DIR_PARTS for part in path.parts)


# Fallback only (see module docstring): matches `import <name>`,
# `from <name> import`, or a bare `<name>.py` mention -- used ONLY when a
# candidate file fails to parse as Python (e.g. used as a text fixture).
def _reference_pattern(module_name: str) -> "re.Pattern[str]":
    escaped = re.escape(module_name)
    return re.compile(
        rf"(^|[^\w]){escaped}(\.py\b|\b)(?!\s*=)",
    )


def find_module_name(module_path: Path) -> str:
    """The Python import name for a module path, e.g.
    scripts/pipeline/lib/taskcard_store.py -> taskcard_store."""
    return module_path.stem


def _module_dotted_names(module_path: Path, repo_root: Path) -> "set[str]":
    """Qualified dotted import-paths that could resolve to this module,
    given this repo's real import conventions: PYTHONPATH=scripts/pipeline
    means `lib.x.y` and `x.y` (once lib/ itself is also inserted, as
    _bootstrap.py and most commands/ headers do) both resolve to the same
    file, depending on which sys.path entry a given caller used.

    Deliberately does NOT include the bare last-path-component alone for
    a module nested under a subpackage (e.g. `go` for
    example_verification/runners/go.py, `cli` for
    example_verification/cli.py) -- confirmed live false positives while
    building this check (MT072-2026-09-23-EXAMPLE-VERIFICATION-
    PRODUCTIONIZATION/TC-01): this ~1500-script repo has multiple,
    unrelated modules sharing the same generic stem
    (content_eval/cli.py vs example_verification/cli.py;
    extraction/lang/go.py vs example_verification/runners/go.py), and a
    bare-stem match matched the WRONG file's real import statement. The
    bare stem IS kept for a module living directly under lib/ or
    commands/{domain}/ with no further subpackage nesting (e.g.
    lib/taskcard_store.py) -- that is this repo's real, only qualified
    form for such a module (`from taskcard_store import ...`, confirmed
    by this module's own real sanity tests), and single-word collisions
    were not observed at that shallower depth."""
    try:
        rel_parts = module_path.resolve().relative_to(repo_root.resolve()).with_suffix("").parts
    except ValueError:
        rel_parts = module_path.with_suffix("").parts
    dotted: set[str] = set()
    tail: tuple[str, ...] = ()
    if "pipeline" in rel_parts:
        i = rel_parts.index("pipeline")
        tail = rel_parts[i + 1:]
        if tail:
            dotted.add(".".join(tail))
            if tail[0] in ("lib", "commands") and len(tail) > 1:
                dotted.add(".".join(tail[1:]))
    if len(rel_parts) >= 2:
        dotted.add(".".join(rel_parts[-2:]))
    if len(tail) == 2 and tail[0] in ("lib", "commands"):
        dotted.add(tail[-1])
    elif not tail and rel_parts:
        dotted.add(rel_parts[-1])
    return {d for d in dotted if d}


# Call targets that mean "the first string argument is a dotted module
# path to dynamically import" -- scoped narrowly on purpose. Treating
# EVERY string constant in a file as a candidate dotted name was tried
# first and produced real false positives: short, common module names
# (`go`, `python`, `api`) are also ordinary string literals used for
# unrelated things (a platform-name comparison, a dict key, a URL
# segment) throughout this codebase, and each one would then be
# misread as "this file dynamically imports that module."
_DYNAMIC_IMPORT_CALLEES = frozenset({"import_module", "_pipeline_module"})


def _fstring_literal_prefix(node: ast.JoinedStr) -> "str | None":
    """The constant text before the FIRST interpolated `{...}` in an
    f-string, or None if the f-string starts with an interpolation (no
    usable literal prefix at all). Only the leading literal run matters:
    `f"example_verification.runners.{mod_name}"` -> the prefix
    "example_verification.runners." (a real, live pattern this codebase
    uses -- confirmed in lib/example_verification/api.py's own
    `_load_language_runner`, the exact case that motivated this fix: a
    dynamic import via f-string, invisible to a Constant-only check)."""
    prefix_parts: list[str] = []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            prefix_parts.append(part.value)
            continue
        break  # first FormattedValue -- stop; anything after is unreachable as a fixed prefix
    prefix = "".join(prefix_parts)
    return prefix or None


def _dynamic_import_targets(tree: ast.AST) -> "tuple[set[str], set[str]]":
    """Returns (exact_names, prefixes). `exact_names` are plain string-
    constant dynamic-import targets (matched by equality/suffix, same as
    a static import). `prefixes` are f-string dynamic-import LITERAL
    PREFIXES (matched by `dotted_name.startswith(prefix)` in
    _ast_references_module -- the interpolated tail is an unresolvable
    wildcard, so a prefix match is the most this coarse, advisory check
    can honestly claim)."""
    exact_names: set[str] = set()
    prefixes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        callee = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else None
        )
        if callee not in _DYNAMIC_IMPORT_CALLEES:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            exact_names.add(first.value)
        elif isinstance(first, ast.JoinedStr):
            prefix = _fstring_literal_prefix(first)
            if prefix:
                prefixes.add(prefix)
    return exact_names, prefixes


def _imported_dotted_names(tree: ast.AST) -> "tuple[set[str], set[str]]":
    """Returns (exact_names, dynamic_prefixes) -- every dotted name a
    file's AST actually imports statically, plus dynamic-import targets
    from _dynamic_import_targets (the `_pipeline_module("lib.x.y")` /
    `importlib.import_module("x.y")` pattern this codebase already uses,
    e.g. check_platform_capabilities.py's own `_pipeline_module` calls,
    PLUS the f-string variant, e.g.
    `importlib.import_module(f"example_verification.runners.{mod_name}")`,
    lib/example_verification/api.py's own real pattern)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
                for alias in node.names:
                    names.add(f"{node.module}.{alias.name}")
    exact_dynamic, prefixes = _dynamic_import_targets(tree)
    names |= exact_dynamic
    return names, prefixes


def _ast_references_module(text: str, module_name: str, dotted_names: "set[str]") -> "bool | None":
    """True/False if the file parses; None if it doesn't (caller falls
    back to the substring heuristic for that one file only).

    Matches ONLY against `dotted_names` (module_name is accepted as a
    parameter for API stability but is not compared in isolation) --
    an earlier version of this function also matched on bare
    `module_name` equality/suffix directly, which reintroduced the exact
    common-word collision `_module_dotted_names` was written to avoid
    (`content_eval.cli` was matched as a "cli.py" import even though
    `_module_dotted_names` deliberately excludes the bare "cli" for a
    nested module -- the bare check here bypassed that safeguard).
    The endswith check requires a 2+-component dotted suffix (`d` always
    has a `.` in it once `_module_dotted_names` excludes bare single
    words for nested modules), so it can never degrade back into a
    single-generic-word match either.

    A dynamic-import f-string's literal PREFIX is matched by
    `dotted_name.startswith(prefix)` (after stripping one leading `.` from
    the prefix, so a relative dynamic import like
    `importlib.import_module(f".runners.{mod_name}", package=__package__)`
    -- registry.py's own real pattern -- matches the same way an absolute
    one does): confirmed real gap found by independent review (TC-01
    fast-follow) -- the original Constant-only dynamic-import check could
    not see either of this codebase's two live f-string dynamic-import
    call sites at all (api.py, registry.py), so it never actually proved
    what its own registry.yaml notes claimed."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    exact_and_static, prefixes = _imported_dotted_names(tree)
    for name in exact_and_static:
        if name in dotted_names:
            return True
        if any(name.endswith(f".{d}") for d in dotted_names if "." in d):
            return True
    for prefix in prefixes:
        stripped = prefix.lstrip(".")
        if any(d == stripped.rstrip(".") or d.startswith(stripped) for d in dotted_names):
            return True
    return False


def find_real_consumers(
    module_path: str, *, scan_root: Path = _SCAN_ROOT, repo_root: Path = _REPO_ROOT,
) -> list[Path]:
    """Return every non-test file (outside module_path itself) that
    really imports this module -- an AST import-graph walk, with the
    original substring heuristic used only as a fallback for files that
    fail to parse. Empty list means no detected real consumer."""
    full_module_path = (repo_root / module_path).resolve()
    module_name = find_module_name(Path(module_path))
    dotted_names = _module_dotted_names(Path(module_path), repo_root)
    pattern = _reference_pattern(module_name)

    consumers = []
    if not scan_root.exists():
        return consumers
    for candidate in scan_root.rglob("*.py"):
        if _is_excluded_dir(candidate):
            continue
        if candidate.resolve() == full_module_path:
            continue
        if _is_test_path(candidate):
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        ast_result = _ast_references_module(text, module_name, dotted_names)
        if ast_result is True:
            consumers.append(candidate)
        elif ast_result is None and pattern.search(text):
            consumers.append(candidate)
    return sorted(set(consumers))


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True,
                        help="Repo-relative path to the module, e.g. scripts/pipeline/lib/foo.py")
    args = parser.parse_args(argv)

    module_path = _REPO_ROOT / args.module
    if not module_path.is_file() or module_path.suffix != ".py":
        print(f"ERROR: not a Python file: {args.module}", file=sys.stderr)
        return 2

    # Pass the current module globals explicitly rather than relying on
    # find_real_consumers()'s keyword defaults: those defaults are bound
    # once at function-definition time, so a caller that monkeypatches
    # _SCAN_ROOT/_REPO_ROOT after import (every test in this suite that
    # exercises main() against a synthetic tmp_path tree) would otherwise
    # silently keep scanning the real repo -- confirmed live while fixing
    # TC-01's false-positive bug: test_main_exits_0_when_consumer_found
    # was passing only by coincidence (some real file in this actual repo
    # happens to reference the word "helper"), not because its tmp_path
    # fixture was ever actually scanned.
    consumers = find_real_consumers(args.module, scan_root=_SCAN_ROOT, repo_root=_REPO_ROOT)
    if consumers:
        print(f"OK: {len(consumers)} real (non-test) consumer(s) found for {args.module}:")
        for c in consumers:
            try:
                rel = c.relative_to(_REPO_ROOT)
            except ValueError:
                rel = c
            print(f"  {rel}")
        return 0

    print(f"NO REAL CONSUMER FOUND for {args.module} -- nothing outside its own "
          f"test suite appears to import it. This is advisory, not a block: if "
          f"this module is genuinely infrastructure awaiting its first caller, "
          f"that caller is real work this task isn't done without yet.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
