#!/usr/bin/env python3
"""Compile-check fenced code blocks in Markdown files.

The checker never executes examples. Python blocks are syntax-checked with
``py_compile`` and optionally type-checked with mypy. Other supported language
tags are accepted through tree-sitter when the parser packages are installed;
otherwise they are treated as unchecked PASS for compatibility.
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

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from scripts.content_repo_adapter import resolve_content_root  # noqa: E402

KNOWLEDGE_BASE = REPO_ROOT / "knowledge"
_CODE_FENCE_ANY_RE = re.compile(r"```([\w+\-#]*)\n(.*?)```", re.DOTALL)

_PLATFORM_LANGS: dict[str, frozenset[str]] = {
    "python": frozenset({"python"}),
    "java": frozenset({"java"}),
    "net": frozenset({"csharp", "cs", "c#"}),
    "typescript": frozenset({"typescript", "ts"}),
    "cpp": frozenset({"cpp", "c++"}),
}
_TS_LANG_MAP: dict[str, str] = {
    "java": "java",
    "csharp": "csharp",
    "cs": "csharp",
    "c#": "csharp",
    "typescript": "typescript",
    "ts": "typescript",
    "cpp": "cpp",
    "c++": "cpp",
}
_LANG_DISPLAY: dict[str, str] = {
    "csharp": "C#",
    "cs": "C#",
    "c#": "C#",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "cpp": "C++",
    "c++": "C++",
    "java": "Java",
}
_TS_PARSER_CACHE: dict[str, Any] = {}
_TS_LOADED = False


class BlockResult(NamedTuple):
    file: str
    block_index: int
    start_line: int
    status: str
    message: str


class SmokeResult(NamedTuple):
    file: str
    blocks_checked: int
    pass_count: int
    warn_count: int
    fail_count: int
    results: list[BlockResult]


def _load_ts_parsers() -> None:
    global _TS_LOADED
    if _TS_LOADED:
        return
    _TS_LOADED = True
    try:
        import tree_sitter_language_pack as language_pack  # type: ignore
    except Exception:
        return
    for tag, parser_name in _TS_LANG_MAP.items():
        try:
            parser = language_pack.get_parser(parser_name)
        except Exception:
            parser = None
        if parser is not None:
            _TS_PARSER_CACHE[tag] = parser


def _ts_parser_for(lang_tag: str) -> Any | None:
    _load_ts_parsers()
    return _TS_PARSER_CACHE.get(lang_tag)


def _first_error_node(node: Any) -> Any | None:
    queue = [node]
    while queue:
        current = queue.pop(0)
        if getattr(current, "type", None) == "ERROR":
            return current
        queue.extend(getattr(current, "children", []))
    return None


def _extract_blocks(md_path: Path, langs: frozenset[str]) -> list[tuple[int, str, str]]:
    text = md_path.read_text(encoding="utf-8", errors="replace")
    blocks: list[tuple[int, str, str]] = []
    for match in _CODE_FENCE_ANY_RE.finditer(text):
        lang = match.group(1).lower()
        if lang not in langs:
            continue
        start_line = text[: match.start()].count("\n") + 1
        blocks.append((start_line, lang, textwrap.dedent(match.group(2))))
    return blocks


def _run_py_compile(code: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as handle:
        handle.write(code)
        tmp_path = handle.name
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", tmp_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return False, (result.stderr or result.stdout).strip().replace(tmp_path, "<code_block>")
        return True, ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _run_mypy(code: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as handle:
        handle.write(code)
        tmp_path = handle.name
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "--ignore-missing-imports", "--no-error-summary", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout or result.stderr).strip().replace(tmp_path, "<code_block>")
        if result.returncode != 0 and "No module named mypy" not in output:
            return False, output
        return True, ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _run_ts_parse(code: str, parser: Any) -> tuple[bool, str]:
    try:
        tree = parser.parse(code.encode("utf-8"))
    except Exception as exc:
        return False, str(exc)
    error = _first_error_node(tree.root_node)
    if error is None:
        return True, ""
    return False, f"SyntaxError near byte {error.start_byte}"


def _get_canonical_import(family: str, platform: str) -> str:
    path = KNOWLEDGE_BASE / family / platform / "scout" / "model.yaml"
    if not path.exists():
        return ""
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    return data.get("canonical_import", "") or ""


def check_file(
    md_path: Path,
    canonical_import: str = "",
    langs: frozenset[str] | None = None,
) -> SmokeResult:
    if langs is None:
        langs = frozenset({"python"})

    blocks = _extract_blocks(md_path, langs)
    results: list[BlockResult] = []
    pass_count = warn_count = fail_count = 0

    for index, (start_line, lang, raw_code) in enumerate(blocks, start=1):
        if lang == "python":
            code = raw_code
            if canonical_import and canonical_import not in raw_code:
                code = f"# auto-prepended by smoke_test\n{canonical_import}\n\n{raw_code}"
            syntax_ok, syntax_message = _run_py_compile(code)
            if not syntax_ok:
                results.append(BlockResult(str(md_path), index, start_line, "FAIL", f"SyntaxError: {syntax_message}"))
                fail_count += 1
                continue
            type_ok, type_message = _run_mypy(code)
            if not type_ok:
                results.append(BlockResult(str(md_path), index, start_line, "WARN", f"TypeWarning: {type_message}"))
                warn_count += 1
                continue
            results.append(BlockResult(str(md_path), index, start_line, "PASS", ""))
            pass_count += 1
            continue

        parser = _ts_parser_for(lang)
        if parser is None:
            results.append(BlockResult(str(md_path), index, start_line, "PASS", ""))
            pass_count += 1
            continue
        syntax_ok, syntax_message = _run_ts_parse(raw_code, parser)
        if syntax_ok:
            results.append(BlockResult(str(md_path), index, start_line, "PASS", ""))
            pass_count += 1
        else:
            display = _LANG_DISPLAY.get(lang, lang.title())
            results.append(BlockResult(str(md_path), index, start_line, "FAIL", f"{display} {syntax_message}"))
            fail_count += 1

    return SmokeResult(str(md_path), len(blocks), pass_count, warn_count, fail_count, results)


def check_product(
    family: str,
    platform: str,
    *,
    content_root: Path | None = None,
) -> list[SmokeResult]:
    if content_root is None:
        content_root = resolve_content_root({"content_root": "content"} if (REPO_ROOT / "content").exists() else None)
    langs = _PLATFORM_LANGS.get(platform, frozenset({"python"}))
    canonical_import = _get_canonical_import(family, platform) if "python" in langs else ""

    roots = [
        content_root / "docs.aspose.org" / "en" / family / platform,
        content_root / "blog.aspose.org" / family / platform,
        content_root / "kb.aspose.org" / "en" / family / platform,
        content_root / "reference.aspose.org" / "en" / family / platform,
    ]
    results: list[SmokeResult] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            result = check_file(path, canonical_import, langs)
            if result.blocks_checked:
                results.append(result)
    return results


def print_report(all_results: list[SmokeResult]) -> int:
    total_blocks = sum(result.blocks_checked for result in all_results)
    total_pass = sum(result.pass_count for result in all_results)
    total_warn = sum(result.warn_count for result in all_results)
    total_fail = sum(result.fail_count for result in all_results)

    print("=" * 60)
    print("SMOKE TEST REPORT")
    print(f"Files checked:  {len(all_results)}")
    print(f"Blocks checked: {total_blocks}")
    print(f"  PASS: {total_pass}")
    print(f"  WARN: {total_warn}")
    print(f"  FAIL: {total_fail}")
    print("=" * 60)
    for smoke in all_results:
        if smoke.warn_count == 0 and smoke.fail_count == 0:
            continue
        print(f"\n{smoke.file}")
        for block in smoke.results:
            if block.status != "PASS":
                print(f"  [{block.status}] block {block.block_index} (line {block.start_line}): {block.message}")
    if total_fail:
        print(f"\nRESULT: FAIL - {total_fail} block(s) have syntax errors")
        return 2
    if total_warn:
        print(f"\nRESULT: WARN - {total_warn} block(s) have type warnings")
        return 1
    print(f"\nRESULT: PASS - all {total_blocks} block(s) are clean")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test code blocks in Markdown files.")
    parser.add_argument("family_or_files", nargs="?")
    parser.add_argument("platform", nargs="?")
    parser.add_argument("--files", nargs="+", metavar="FILE")
    parser.add_argument("--lang", metavar="LANG")
    parser.add_argument("--content-root", metavar="PATH")
    args = parser.parse_args(argv)

    if args.lang:
        langs = frozenset(item.strip().lower() for item in args.lang.split(",") if item.strip())
    elif args.files and not (args.family_or_files and args.platform):
        langs = frozenset({"python"})
    elif args.family_or_files and args.platform:
        langs = _PLATFORM_LANGS.get(args.platform, frozenset({"python"}))
    else:
        langs = frozenset({"python"})

    if args.files:
        canonical_import = ""
        if "python" in langs and args.family_or_files and args.platform:
            canonical_import = _get_canonical_import(args.family_or_files, args.platform)
        results = [check_file(Path(file), canonical_import, langs) for file in args.files]
    elif args.family_or_files and args.platform:
        content_root = Path(args.content_root).resolve() if args.content_root else None
        results = check_product(args.family_or_files, args.platform, content_root=content_root)
    else:
        parser.print_help()
        return 1
    return print_report(results)


if __name__ == "__main__":
    raise SystemExit(main())
