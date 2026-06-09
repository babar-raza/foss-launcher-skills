"""extraction/snippets.py — Code snippet extraction from test/example dirs.

Extracted from scout.py (step 4.6). Standalone functions usable without the
Scout class.

Public API::

    extract_snippets(parser, language, pkg_root, repo, classes, formats)
        -> list[dict]   # snippet dicts ready for scout output
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from extraction.tree_helpers import (
    MAX_FILES,
    _CLASS_TYPES,
    _FILE_EXTENSIONS,
    _FUNC_TYPES,
    _node_name,
    child_by_field,
    collect_nodes,
    node_text,
)

MAX_SNIPPETS = 100


def _collect_snippet_functions(
    root,
    language: str,
    func_types: set,
    class_types: set,
    source_text: str,
    is_example_dir: bool = False,
) -> list[tuple[str, Any, int]]:
    """Collect candidate test/example functions from a parsed tree.

    Returns list of (function_name, node, line_number) tuples.
    Language-specific heuristics determine which functions qualify.
    When *is_example_dir* is True, C++ ``main()`` functions are also
    captured — example files use ``main`` rather than test_ naming.
    """
    results: list[tuple[str, Any, int]] = []

    if language == "python":
        for fn in collect_nodes(root, func_types):
            fname = _node_name(fn, language)
            if fname and (fname.startswith("test_")
                          or fname.startswith("example_")
                          or fname.startswith("demo_")):
                results.append((fname, fn, fn.start_point[0] + 1))

    elif language in ("java", "csharp"):
        for cn in collect_nodes(root, class_types):
            cname = _node_name(cn, language)
            if not cname:
                continue
            is_test_class = ("Test" in cname or "Example" in cname
                             or "Demo" in cname or "Sample" in cname)
            if not is_test_class:
                continue
            for fn in collect_nodes(cn, func_types):
                fname = _node_name(fn, language)
                if fname and not fname.startswith("_"):
                    results.append((fname, fn, fn.start_point[0] + 1))
        # C# top-level statement files (no class wrapper) in sample dirs:
        # treat root-level expression/statement nodes as a single file snippet.
        if language == "csharp" and is_example_dir and not results:
            non_class_nodes = [
                ch for ch in root.children
                if ch.type not in class_types and ch.type != "using_directive"
                and ch.type not in ("namespace_declaration", "comment",
                                    "extern_alias_directive")
                and not ch.type.endswith("_statement")  # skip isolated stmts
            ]
            # If there is any meaningful code at top level (not just using/ns)
            has_top_level = any(
                ch for ch in root.children
                if ch.type not in ("using_directive", "extern_alias_directive",
                                   "namespace_declaration")
                and ch.type != "comment"
            )
            if has_top_level:
                # Emit the entire root as one "file-level" snippet
                results.append(("(top_level_program)", root, 1))

    elif language == "cpp":
        _gtest_macros = {"TEST", "TEST_F", "TEST_P", "TYPED_TEST"}
        for fn in collect_nodes(root, func_types):
            fname = _node_name(fn, language)
            if not fname:
                # C++ function_definition: name lives in function_declarator child
                for ch in fn.children:
                    if ch.type == "function_declarator":
                        for gch in ch.children:
                            if gch.type == "identifier":
                                fname = node_text(gch)
                                break
                        break
            if fname and (fname.startswith("test_")
                          or fname.startswith("Test")
                          or fname in _gtest_macros
                          or (is_example_dir and fname == "main")):
                results.append((fname, fn, fn.start_point[0] + 1))

    elif language in ("typescript", "javascript"):
        for fn in collect_nodes(root, func_types):
            fname = _node_name(fn, language)
            if not fname:
                continue
            parent = fn.parent
            is_exported = (parent and parent.type == "export_statement")
            is_test_fn = (fname.startswith("test")
                          or fname.startswith("example")
                          or fname.startswith("demo"))
            if is_exported or is_test_fn:
                results.append((fname, fn, fn.start_point[0] + 1))

        _test_block_names = {"test", "it", "describe"}
        for call_node in collect_nodes(root, {"call_expression"}):
            fn_part = child_by_field(call_node, "function")
            if fn_part and node_text(fn_part) in _test_block_names:
                args = child_by_field(call_node, "arguments")
                if args and args.children:
                    desc = ""
                    for ch in args.children:
                        if ch.type in ("string", "template_string"):
                            desc = node_text(ch).strip("'\"` ")
                            break
                    block_name = desc[:60] or node_text(fn_part)
                    results.append(
                        (block_name, call_node,
                         call_node.start_point[0] + 1))

    elif language == "go":
        # Go testable examples: ExampleXxx functions in *_test.go files.
        # main() functions in _examples/ dirs (is_example_dir=True).
        for fn in collect_nodes(root, func_types):
            fname = _node_name(fn, language)
            if not fname:
                continue
            if fname.startswith("Example"):
                results.append((fname, fn, fn.start_point[0] + 1))
            elif is_example_dir and fname == "main":
                results.append((fname, fn, fn.start_point[0] + 1))

    return results


def extract_snippets(
    parser,
    language: str,
    pkg_root: Path,
    repo: Path,
    classes: list[dict],
    formats: list[dict],
) -> list[dict]:
    """Extract function-level snippets from test/example directories.

    For each test/example function found, records which API classes and
    methods it references (cross-referenced against *classes*) and which
    file format names appear in *formats*.  Also extracts README code
    blocks as whole-file snippets.  Capped at MAX_SNIPPETS per product.

    Returns a list of snippet dicts.
    """
    # Build lookup sets from already-extracted api_surface
    api_class_names: set[str] = set()
    api_method_index: dict[str, set[str]] = {}
    for cls in classes:
        cname = cls.get("name", "")
        if not cname or cls.get("kind") == "function":
            continue
        api_class_names.add(cname)
        meths: set[str] = set()
        for m in cls.get("methods", []):
            if isinstance(m, dict) and m.get("name"):
                meths.add(m["name"])
        api_method_index[cname] = meths

    format_names: set[str] = set()
    for fmt in formats:
        fname = fmt.get("format", "")
        if fname:
            format_names.add(fname.lower())

    snippet_dirs = ["tests", "test", "examples", "example", "samples", "demo",
                     "ApiExamples", "api_examples", "_examples"]
    _example_dirs = {"examples", "example", "samples", "demo",
                     "ApiExamples", "api_examples", "_examples"}
    ext = _FILE_EXTENSIONS.get(language, ".py")
    func_types = _FUNC_TYPES.get(language, set())
    class_types = _CLASS_TYPES.get(language, set())

    # Build search base list: walk from pkg_root up to repo root
    _search_bases: list[Path] = []
    _p = pkg_root
    while True:
        try:
            _p.relative_to(repo)
            _search_bases.append(_p)
        except ValueError:
            pass
        if _p == repo or _p.parent == _p:
            break
        _p = _p.parent
    if repo not in _search_bases:
        _search_bases.append(repo)

    snippets: list[dict] = []
    snippet_counter = 0

    for sdir in snippet_dirs:
        _visited: set[Path] = set()
        for _base in _search_bases:
            d = _base / sdir
            if d in _visited:
                continue
            _visited.add(d)
            if not d.is_dir():
                continue
            files = sorted(d.rglob(f"*{ext}"))[:MAX_FILES]
            for fpath in files:
                if snippet_counter >= MAX_SNIPPETS:
                    break
                rel = str(fpath.relative_to(repo)).replace("\\", "/")
                try:
                    src = fpath.read_bytes()
                except OSError:
                    continue
                tree = parser.parse(src)
                text = src.decode("utf-8", errors="replace")
                root = tree.root_node

                func_nodes = _collect_snippet_functions(
                    root, language, func_types, class_types, text,
                    is_example_dir=(sdir in _example_dirs))

                for fn_name, fn_node, fn_line in func_nodes:
                    if snippet_counter >= MAX_SNIPPETS:
                        break
                    code = node_text(fn_node)
                    if not code.strip():
                        continue

                    classes_used: list[str] = []
                    methods_used: list[str] = []
                    formats_ref: list[str] = []

                    code_lower = code.lower()
                    for cname in api_class_names:
                        if cname in code:
                            classes_used.append(cname)
                            for mname in api_method_index.get(cname, set()):
                                if (f"{cname}.{mname}" in code
                                        or f".{mname}(" in code):
                                    methods_used.append(f"{cname}.{mname}")

                    for fmt_name in format_names:
                        if fmt_name in code_lower:
                            formats_ref.append(fmt_name)

                    snippet_id = f"snippet_{snippet_counter + 1:03d}"
                    snippets.append({
                        "id": snippet_id,
                        "file": f"{snippet_id}{ext}",
                        "source_file": rel,
                        "source_function": fn_name,
                        "source_line": fn_line,
                        "language": language,
                        "code": code[:5000],
                        "valid": not fn_node.has_error,
                        "classes_used": sorted(set(classes_used)),
                        "methods_used": sorted(set(methods_used)),
                        "formats_referenced": sorted(set(formats_ref)),
                    })
                    snippet_counter += 1

        if snippet_counter >= MAX_SNIPPETS:
            break

    # Go-specific: scan *_test.go at package/repo root for ExampleXxx funcs.
    # Go testable examples live in *_test.go files alongside the package source,
    # not inside a tests/ subdirectory — so the snippet_dirs loop misses them.
    if language == "go" and snippet_counter < MAX_SNIPPETS:
        _visited_test: set[Path] = set()
        for _base in _search_bases:
            for test_file in sorted(_base.glob("*_test.go"))[:MAX_FILES]:
                if test_file in _visited_test:
                    continue
                _visited_test.add(test_file)
                if snippet_counter >= MAX_SNIPPETS:
                    break
                rel = str(test_file.relative_to(repo)).replace("\\", "/")
                try:
                    src = test_file.read_bytes()
                except OSError:
                    continue
                tree = parser.parse(src)
                text = src.decode("utf-8", errors="replace")
                root = tree.root_node
                func_nodes = _collect_snippet_functions(
                    root, language, func_types, class_types, text,
                    is_example_dir=False)
                for fn_name, fn_node, fn_line in func_nodes:
                    if snippet_counter >= MAX_SNIPPETS:
                        break
                    if any(s.get("source_function") == fn_name for s in snippets):
                        continue
                    code = node_text(fn_node)
                    if not code.strip():
                        continue

                    classes_used: list[str] = []
                    methods_used: list[str] = []
                    formats_ref: list[str] = []
                    code_lower = code.lower()
                    for cname in api_class_names:
                        if cname in code:
                            classes_used.append(cname)
                            for mname in api_method_index.get(cname, set()):
                                if (f"{cname}.{mname}" in code
                                        or f".{mname}(" in code):
                                    methods_used.append(f"{cname}.{mname}")
                    for fmt_name in format_names:
                        if fmt_name in code_lower:
                            formats_ref.append(fmt_name)

                    snippet_id = f"snippet_{snippet_counter + 1:03d}"
                    snippets.append({
                        "id": snippet_id,
                        "file": f"{snippet_id}{ext}",
                        "source_file": rel,
                        "source_function": fn_name,
                        "source_line": fn_line,
                        "language": language,
                        "code": code[:5000],
                        "valid": not fn_node.has_error,
                        "classes_used": sorted(set(classes_used)),
                        "methods_used": sorted(set(methods_used)),
                        "formats_referenced": sorted(set(formats_ref)),
                    })
                    snippet_counter += 1

    # README fenced code blocks (as whole-file snippets)
    for readme_name in ("README.md", "readme.md", "README.rst"):
        if snippet_counter >= MAX_SNIPPETS:
            break
        readme = repo / readme_name
        if readme.exists():
            try:
                text = readme.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lang_names = {language}
            if language == "csharp":
                lang_names.update({"csharp", "cs", "c#"})
            if language == "javascript":
                lang_names.update({"javascript", "js"})
            if language == "typescript":
                lang_names.update({"typescript", "ts"})
            if language == "python":
                lang_names.update({"python", "py"})
            if language == "java":
                lang_names.add("java")
            if language == "cpp":
                lang_names.update({"cpp", "c++"})

            fence_pattern = re.compile(
                r"```(" + "|".join(re.escape(n) for n in lang_names)
                + r")\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
            for m in fence_pattern.finditer(text):
                if snippet_counter >= MAX_SNIPPETS:
                    break
                code = m.group(2)
                t = parser.parse(code.encode("utf-8"))
                valid = not t.root_node.has_error

                classes_used = [c for c in api_class_names if c in code]
                methods_used = []
                for cname in classes_used:
                    for mname in api_method_index.get(cname, set()):
                        if f"{cname}.{mname}" in code or f".{mname}(" in code:
                            methods_used.append(f"{cname}.{mname}")
                formats_ref = [f for f in format_names if f in code.lower()]

                snippet_id = f"snippet_{snippet_counter + 1:03d}"
                snippets.append({
                    "id": snippet_id,
                    "file": f"{snippet_id}{ext}",
                    "source_file": readme_name,
                    "source_function": "(readme_block)",
                    "source_line": text[:m.start()].count("\n") + 1,
                    "language": language,
                    "code": code[:5000],
                    "valid": valid,
                    "classes_used": sorted(set(classes_used)),
                    "methods_used": sorted(set(methods_used)),
                    "formats_referenced": sorted(set(formats_ref)),
                })
                snippet_counter += 1
            break

    return snippets
