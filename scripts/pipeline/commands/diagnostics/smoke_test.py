"""smoke_test.py — Code block syntax and type checking for content pages.

Extracts fenced code blocks from Markdown content files and validates their
syntax. Python blocks are checked with py_compile (syntax) and optionally mypy
(type hints). Non-Python blocks (Java, C#, TypeScript, C++) are checked with
tree-sitter for syntax errors.

Never EXECUTES code — compile/type-check only.

Exit codes:
  0 — all blocks PASS
  1 — at least one block WARN (Python type errors only, no syntax errors)
  2 — at least one block FAIL (syntax error)

Usage:
  python scripts/pipeline/commands/diagnostics/smoke_test.py {family} {platform}
  python scripts/pipeline/commands/diagnostics/smoke_test.py --files path/to/file.md [path2.md ...]
  python scripts/pipeline/commands/diagnostics/smoke_test.py --files path/to/file.md --lang java

Supported languages:
  python     — py_compile syntax + optional mypy type check
  java       — tree-sitter syntax check
  csharp/cs  — tree-sitter syntax check
  typescript — tree-sitter syntax check
  cpp        — tree-sitter syntax check

Limitation: multi-block code examples (variables defined in block 1 used in
block 2) are checked independently. This may produce false-positive
NameError/type complaints. Each block is annotated with its source file + line
number for traceability.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, NamedTuple

_LIB_DIR = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from example_verification import registry as _ev_registry  # noqa: E402
from example_verification import syntax as _ev_syntax  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
KNOWLEDGE_BASE = REPO_ROOT / "knowledge"
CONTENT_BASE = REPO_ROOT / "content"

# Matches any fenced code block: captures (lang_tag, code)
_CODE_FENCE_ANY_RE = re.compile(
    r"```([\w+\-#]*)\n(.*?)```",
    re.DOTALL,
)

# C4 (RC20 fix): both dicts below used to be independent, hand-maintained
# copies that silently lacked "go" -- a Go product's blocks fell through
# `_PLATFORM_LANGS.get(platform, frozenset({"python"}))`'s default and were
# checked as if they were Python. Both are now derived from the shared
# `lib/example_verification/registry.py` (the same source
# platform_capabilities.yaml's `example_verification` site mirrors), so a
# new platform/tag only needs to be declared once. Confirmed byte-identical
# to the old hardcoded dicts for every pre-existing key (see
# test_smoke_test.py's existing per-platform assertions), plus "go" is
# picked up automatically since registry.py already declares it.

# Non-Python language tags handled by tree-sitter.
# Maps content-file tag → canonical tree-sitter parser key.
_TS_LANG_MAP: dict[str, str] = {
    tag: canon
    for _contract in _ev_registry.PLATFORM_CONTRACT.values()
    for tag in _contract.fence_tags
    if (canon := _ev_syntax.canonical_for(tag)) is not None
}

# Platform name → frozenset of language tags to extract. A platform's fence
# tags that have no real tree-sitter grammar (e.g. python's own "bash"/"sh"/
# "shell", which are runnable via S-120 but never syntax-checkable here) are
# excluded -- this is a "can smoke_test check it" set, not "can this
# platform's example-verification runner execute it" (registry.py's own
# concept, a superset).
_PLATFORM_LANGS: dict[str, frozenset[str]] = {
    platform: checkable
    for platform, _contract in _ev_registry.PLATFORM_CONTRACT.items()
    if (checkable := frozenset(
        tag for tag in _contract.fence_tags if _ev_syntax.canonical_for(tag) is not None
    ))
}

# ---------------------------------------------------------------------------
# Tree-sitter parser cache
# ---------------------------------------------------------------------------
#
# RC17/Phase-0-item-9: this used to be an independent copy of the same
# loader content_eval/evaluators/code_syntax_check.py also carried, and the
# two disagreed on which languages got a tree_sitter_language_pack fallback
# when the standalone wheel was absent (confirmed live: code_syntax_check's
# copy resolved only rust that way, this one resolved java/csharp/
# typescript/cpp/rust) -- a Java page could get a real parse in one
# subsystem and a silent skip in the other. Both now delegate to the same
# lib/example_verification/syntax.py loader.


def _ts_parser_for(lang_tag: str) -> Any | None:
    """Return a cached tree-sitter Parser for lang_tag, or None if unavailable."""
    return _ev_syntax.parser_for(lang_tag)


def _first_error_node(node: Any) -> Any | None:
    """Return the first ERROR node in the tree (BFS), or None.

    MISSING nodes represent parser-inserted tokens that occur normally in
    partial code snippets — they are NOT treated as errors.
    """
    queue = [node]
    while queue:
        n = queue.pop(0)
        if n.type == "ERROR":
            return n
        queue.extend(n.children)
    return None


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class BlockResult(NamedTuple):
    file: str
    block_index: int
    start_line: int
    status: str        # PASS | WARN | FAIL
    message: str


class SmokeResult(NamedTuple):
    file: str
    blocks_checked: int
    pass_count: int
    warn_count: int
    fail_count: int
    results: list[BlockResult]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_canonical_import(family: str, platform: str) -> str:
    """Read canonical_import from knowledge/{family}/{platform}/scout/model.yaml."""
    model_path = (KNOWLEDGE_BASE / family / platform / "scout" / "model.yaml")
    if not model_path.exists():
        return ""
    try:
        import yaml  # type: ignore[import]
        with open(model_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("canonical_import", "") or ""
    except Exception:
        return ""


def _extract_blocks(
    md_path: Path,
    langs: frozenset[str],
) -> list[tuple[int, str, str]]:
    """Return list of (start_line, lang, code) tuples for code blocks in langs."""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    blocks = []
    for m in _CODE_FENCE_ANY_RE.finditer(text):
        lang = m.group(1).lower()
        if lang not in langs:
            continue
        code = textwrap.dedent(m.group(2))
        # Compute 1-based line number of the opening ``` fence
        start_line = text[:m.start()].count("\n") + 1
        blocks.append((start_line, lang, code))
    return blocks


def _run_py_compile(code: str) -> tuple[bool, str]:
    """Compile-check the code. Returns (ok, message)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", tmp_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            msg = (result.stderr or result.stdout).strip()
            # Replace temp path with <code_block> for clean output
            msg = msg.replace(tmp_path, "<code_block>")
            return False, msg
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "py_compile timed out"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _run_mypy(code: str) -> tuple[bool, str]:
    """Type-check the code with mypy. Returns (clean, message)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [
                sys.executable, "-m", "mypy",
                tmp_path,
                "--ignore-missing-imports",
                "--no-error-summary",
                "--no-pretty",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        output = output.replace(tmp_path, "<code_block>")
        # If mypy is not installed, python -m mypy exits non-zero with "No module named mypy"
        if "No module named mypy" in output or "No module named 'mypy'" in output:
            return True, ""
        # mypy returns 0 when no errors
        if result.returncode == 0:
            return True, ""
        return False, output
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # mypy not installed or timed out — skip type check
        return True, ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _run_ts_parse(code: str, parser: Any) -> tuple[bool, str]:
    """Syntax-check code via tree-sitter. Returns (ok, message).

    FAIL only on genuine ERROR nodes. MISSING nodes (parser-inserted tokens
    to complete a partial parse) are normal in code snippets and are NOT
    treated as errors.
    """
    try:
        tree = parser.parse(code.encode("utf-8", errors="replace"))
    except Exception:
        return True, ""  # never let a parser crash block the evaluator

    if not tree.root_node.has_error:
        return True, ""

    error_node = _first_error_node(tree.root_node)
    if error_node is None:
        return True, ""  # only MISSING nodes — not a real error in a snippet

    line_no = error_node.start_point[0] + 1
    return False, f"syntax error at line {line_no} (tree-sitter)"


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------


_LANG_DISPLAY: dict[str, str] = {
    "csharp": "C#", "cs": "C#", "c#": "C#",
    "typescript": "TypeScript", "ts": "TypeScript",
    "cpp": "C++", "c++": "C++",
    "java": "Java",
    "rust": "Rust", "rs": "Rust",
}


def check_file(
    md_path: Path,
    canonical_import: str = "",
    langs: frozenset[str] | None = None,
    *,
    max_tier: int = 2,
) -> SmokeResult:
    """Check code blocks in a Markdown file.

    langs: set of language tags to extract (default: frozenset({"python"})).
    Python blocks: py_compile syntax + (max_tier>=2 only) optional mypy type
    check. Non-Python blocks (java/csharp/typescript/cpp/go/rust): tree-sitter
    syntax only, at every tier (there is no separate compile step for these
    today; max_tier only changes Python's own behavior).

    max_tier: 1 = syntax-only (skip mypy even for Python); 2 (default,
    unchanged from this module's original behavior) = syntax + Python mypy
    type-check. C4's own promotion gate requires max_tier=2 (the default)
    to remain byte-identical to this module's pre-C4 behavior -- confirmed
    by every existing test in test_smoke_test.py passing unchanged.
    """
    if langs is None:
        langs = frozenset({"python"})

    blocks = _extract_blocks(md_path, langs)
    results: list[BlockResult] = []
    pass_count = warn_count = fail_count = 0

    for idx, (start_line, lang, raw_code) in enumerate(blocks, start=1):
        if lang == "python":
            # Prepend canonical import if provided and not already present
            if canonical_import and canonical_import not in raw_code:
                code = f"# auto-prepended by smoke_test\n{canonical_import}\n\n{raw_code}"
            else:
                code = raw_code

            # Step 1: syntax check
            syntax_ok, syntax_msg = _run_py_compile(code)
            if not syntax_ok:
                results.append(BlockResult(
                    file=str(md_path),
                    block_index=idx,
                    start_line=start_line,
                    status="FAIL",
                    message=f"SyntaxError: {syntax_msg}",
                ))
                fail_count += 1
                continue

            if max_tier < 2:
                results.append(BlockResult(
                    file=str(md_path),
                    block_index=idx,
                    start_line=start_line,
                    status="PASS",
                    message="",
                ))
                pass_count += 1
                continue

            # Step 2: type check (WARN only — never FAIL)
            type_ok, type_msg = _run_mypy(code)
            if not type_ok:
                results.append(BlockResult(
                    file=str(md_path),
                    block_index=idx,
                    start_line=start_line,
                    status="WARN",
                    message=f"TypeWarning: {type_msg}",
                ))
                warn_count += 1
            else:
                results.append(BlockResult(
                    file=str(md_path),
                    block_index=idx,
                    start_line=start_line,
                    status="PASS",
                    message="",
                ))
                pass_count += 1

        else:
            # Non-Python: tree-sitter syntax check (PASS/FAIL, or a loud WARN
            # when no grammar is available -- Round 3 A / Phase 0 item 9: a
            # missing grammar and a genuinely clean parse must never look
            # the same to a caller deciding whether a block has real proof
            # behind it. This used to silently report PASS here.
            parser = _ts_parser_for(lang)
            if parser is None:
                lang_display = _LANG_DISPLAY.get(lang, lang.title())
                results.append(BlockResult(
                    file=str(md_path),
                    block_index=idx,
                    start_line=start_line,
                    status="WARN",
                    message=f"GRAMMAR-UNAVAILABLE: no tree-sitter grammar available for {lang_display}",
                ))
                warn_count += 1
                continue

            syntax_ok, syntax_msg = _run_ts_parse(raw_code, parser)
            if not syntax_ok:
                lang_display = _LANG_DISPLAY.get(lang, lang.title())
                results.append(BlockResult(
                    file=str(md_path),
                    block_index=idx,
                    start_line=start_line,
                    status="FAIL",
                    message=f"{lang_display} {syntax_msg}",
                ))
                fail_count += 1
            else:
                results.append(BlockResult(
                    file=str(md_path),
                    block_index=idx,
                    start_line=start_line,
                    status="PASS",
                    message="",
                ))
                pass_count += 1

    return SmokeResult(
        file=str(md_path),
        blocks_checked=len(blocks),
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        results=results,
    )


# ---------------------------------------------------------------------------
# Product-wide scan
# ---------------------------------------------------------------------------


def check_product(family: str, platform: str, *, max_tier: int = 2) -> list[SmokeResult]:
    """Check code blocks across all content files for a product.

    Language tags are auto-detected from platform using _PLATFORM_LANGS.
    """
    langs = _PLATFORM_LANGS.get(platform, frozenset({"python"}))
    canonical_import = ""
    if "python" in langs:
        canonical_import = _get_canonical_import(family, platform)
        if not canonical_import:
            print(
                f"WARNING: canonical_import not found for {family}/{platform}. "
                "Blocks will be checked without import prefix.",
                file=sys.stderr,
            )

    # Collect all content files for this product
    paths: list[Path] = []
    for site in ["docs.aspose.org", "blog.aspose.org", "kb.aspose.org",
                 "reference.aspose.org"]:
        base = CONTENT_BASE / site
        # docs/kb/reference use /en/ prefix
        if site in ("docs.aspose.org", "kb.aspose.org", "reference.aspose.org"):
            product_dir = base / "en" / family / platform
        else:
            product_dir = base / family / platform

        if product_dir.exists():
            paths.extend(product_dir.rglob("*.md"))

    results = []
    for path in sorted(paths):
        result = check_file(path, canonical_import, langs, max_tier=max_tier)
        if result.blocks_checked > 0:
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _exit_code_for(total_fail: int, total_warn: int) -> int:
    """The one, shared 0/1/2 exit-code rule -- both print_report() and
    print_json_report() must return the exact same code for the same
    results (C4's promotion gate: exit codes 0/1/2 preserved)."""
    if total_fail > 0:
        return 2
    if total_warn > 0:
        return 1
    return 0


def print_report(all_results: list[SmokeResult]) -> int:
    """Print smoke test report. Returns exit code (0/1/2)."""
    total_blocks = sum(r.blocks_checked for r in all_results)
    total_pass = sum(r.pass_count for r in all_results)
    total_warn = sum(r.warn_count for r in all_results)
    total_fail = sum(r.fail_count for r in all_results)

    print("=" * 60)
    print(f"SMOKE TEST REPORT")
    print(f"Files checked:  {len(all_results)}")
    print(f"Blocks checked: {total_blocks}")
    print(f"  PASS: {total_pass}")
    print(f"  WARN: {total_warn}")
    print(f"  FAIL: {total_fail}")
    print("=" * 60)

    for smoke in all_results:
        if smoke.warn_count == 0 and smoke.fail_count == 0:
            continue  # Only print files with issues
        print(f"\n{smoke.file}")
        for br in smoke.results:
            if br.status == "PASS":
                continue
            print(f"  [{br.status}] block {br.block_index} (line {br.start_line}): {br.message}")

    exit_code = _exit_code_for(total_fail, total_warn)
    if exit_code == 2:
        print(f"\nRESULT: FAIL — {total_fail} block(s) have syntax errors")
    elif exit_code == 1:
        print(f"\nRESULT: WARN — {total_warn} block(s) have type warnings")
    else:
        print(f"\nRESULT: PASS — all {total_blocks} block(s) are clean")
    return exit_code


def print_json_report(all_results: list[SmokeResult]) -> int:
    """Same data as print_report(), as machine-readable JSON on stdout.
    Returns the identical exit code print_report() would for the same
    results (see _exit_code_for)."""
    import json as _json

    total_blocks = sum(r.blocks_checked for r in all_results)
    total_pass = sum(r.pass_count for r in all_results)
    total_warn = sum(r.warn_count for r in all_results)
    total_fail = sum(r.fail_count for r in all_results)

    report = {
        "files_checked": len(all_results),
        "blocks_checked": total_blocks,
        "pass_count": total_pass,
        "warn_count": total_warn,
        "fail_count": total_fail,
        "files": [
            {
                "file": smoke.file,
                "blocks_checked": smoke.blocks_checked,
                "pass_count": smoke.pass_count,
                "warn_count": smoke.warn_count,
                "fail_count": smoke.fail_count,
                "results": [
                    {
                        "block_index": br.block_index,
                        "start_line": br.start_line,
                        "status": br.status,
                        "message": br.message,
                    }
                    for br in smoke.results
                ],
            }
            for smoke in all_results
        ],
    }
    print(_json.dumps(report, indent=2, sort_keys=True))
    return _exit_code_for(total_fail, total_warn)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# C4: every language this module knows how to syntax-check at all --
# derived the same way _PLATFORM_LANGS/_TS_LANG_MAP are (registry.py +
# syntax.py), used only to scope auto-detection for a bare `--files`
# invocation (never changes _PLATFORM_LANGS/_TS_LANG_MAP themselves).
_ALL_KNOWN_LANGS: frozenset[str] = frozenset({"python"}) | frozenset(_TS_LANG_MAP.keys())


def _detect_langs_in_files(paths: "list[Path]") -> frozenset[str]:
    """RC22 fix: eval-page.md's step 2b documents this CLI as checking
    "all platforms — Python, Java, C#, TypeScript, C++, Rust", but its own
    invocation is a bare `--files {path}` with no `--lang`/platform --
    which this module's own prior default silently resolved to
    `frozenset({"python"})` only, regardless of the file's real content
    (confirmed live: the doc's claim and the code's actual default
    disagreed). Scans each file's own fence tags and returns the subset
    this module can syntax-check; falls back to `{"python"}` only when a
    file has no fenced code at all (or none in a known language), so a
    plain python-only page's smoke-test still behaves exactly as before."""
    present: set[str] = set()
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        present.update(m.group(1).lower() for m in _CODE_FENCE_ANY_RE.finditer(text))
    detected = frozenset(present) & _ALL_KNOWN_LANGS
    return detected or frozenset({"python"})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test code blocks in Markdown content files."
    )
    parser.add_argument(
        "family_or_files", nargs="?",
        help="Family name (e.g. 3d) or omit if using --files",
    )
    parser.add_argument(
        "platform", nargs="?",
        help="Platform name (e.g. python, java, net, typescript, cpp)",
    )
    parser.add_argument(
        "--files", nargs="+", metavar="FILE",
        help="Specific Markdown files to check",
    )
    parser.add_argument(
        "--lang", metavar="LANG",
        help=(
            "Language tag(s) to check, comma-separated "
            "(e.g. java,csharp,typescript,cpp,python). "
            "Default: auto-detected from platform, or from each file's own "
            "fence tags for --files without a platform."
        ),
    )
    parser.add_argument(
        "--max-tier", choices=("1", "2"), default="2",
        help=(
            "1 = syntax-only (no Python mypy type-check); "
            "2 (default) = current behavior (syntax + Python mypy type-check). "
            "Tier 3 (real execution) is not wired into this CLI yet -- "
            "see lib/example_verification/runners/ for the real per-language "
            "runners, not yet dispatched from here (a later taskcard's scope)."
        ),
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit a machine-readable JSON report instead of the human-readable one.",
    )
    args = parser.parse_args()
    max_tier = int(args.max_tier)

    # Resolve language set
    if args.lang:
        langs: frozenset[str] = frozenset(t.strip().lower() for t in args.lang.split(","))
    elif args.files and not (args.family_or_files and args.platform):
        langs = _detect_langs_in_files([Path(f) for f in args.files])
    elif args.family_or_files and args.platform:
        langs = _PLATFORM_LANGS.get(args.platform, frozenset({"python"}))
    else:
        langs = frozenset({"python"})

    if args.files:
        canonical_import = ""
        if "python" in langs and args.family_or_files and args.platform:
            canonical_import = _get_canonical_import(args.family_or_files, args.platform)
        results = [check_file(Path(f), canonical_import, langs, max_tier=max_tier) for f in args.files]
    elif args.family_or_files and args.platform:
        results = check_product(args.family_or_files, args.platform, max_tier=max_tier)
    else:
        parser.print_help()
        return 1

    if args.json:
        return print_json_report(results)
    return print_report(results)


if __name__ == "__main__":
    sys.exit(main())
