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

Detection heuristic: does the module's own name (as a Python import target,
e.g. `taskcard_store` for taskcard_store.py) appear anywhere in the repo's
scripts/ tree OUTSIDE the module's own file and any file whose name starts
with `test_` or lives under a `tests/`/`test/` directory? A textual
substring/import-statement search, not an AST/call-graph analysis -- same
coarseness this repo's other check_*_parity.py scripts already accept, and
sufficient to catch the actual failure mode this check exists for (a module
that literally nothing outside its own tests ever imports).

Usage:
    python check_module_consumption.py --module scripts/pipeline/lib/taskcard_store.py

Exit codes:
  0 -- at least one real (non-test) consumer found
  1 -- no real consumer found (advisory -- caller decides whether this
       blocks anything; this script itself never blocks a commit)
  2 -- module path not found / not a Python file
"""
from __future__ import annotations

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


# Matches `import <name>`, `from <name> import`, `from lib.<name> import`,
# `from commands.X.<name> import`, or a bare `<name>.py` filename mention
# (e.g. in a docstring/registry entry referencing the file by path).
def _reference_pattern(module_name: str) -> "re.Pattern[str]":
    escaped = re.escape(module_name)
    return re.compile(
        rf"(^|[^\w]){escaped}(\.py\b|\b)(?!\s*=)",
    )


def find_module_name(module_path: Path) -> str:
    """The Python import name for a module path, e.g.
    scripts/pipeline/lib/taskcard_store.py -> taskcard_store."""
    return module_path.stem


def find_real_consumers(
    module_path: str, *, scan_root: Path = _SCAN_ROOT, repo_root: Path = _REPO_ROOT,
) -> list[Path]:
    """Return every non-test file (outside module_path itself) whose text
    references the module's own import name. Empty list means no detected
    real consumer."""
    full_module_path = (repo_root / module_path).resolve()
    module_name = find_module_name(Path(module_path))
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
        if pattern.search(text):
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

    consumers = find_real_consumers(args.module)
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
