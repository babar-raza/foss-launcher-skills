"""One-off pilot script for taskcard C2 (read-only, not part of the package).

Measures the WARN/FAIL delta code_syntax_check.py's canonical evaluator
would see if its loader were wired to the new shared
lib/example_verification/syntax.py loader (RC17 fix), WITHOUT actually
switching its live logic in this commit (content_eval/__init__.py's
EVALUATOR_LOGIC_VERSION/EVALUATOR_FREEZE_VERSION bump that switch requires
is outside this taskcard's allowed_paths). Runs the evaluator's own real
classification logic (declaration-only skip, noqa, short-block skip)
against every real page under java/typescript/cpp platform directories,
comparing:
  OLD: code_syntax_check.py's own _ts_parser_for (today's live loader --
       only rust gets a tree_sitter_language_pack fallback)
  NEW: lib.example_verification.syntax.parser_for (java/csharp/typescript/
       javascript/cpp/rust/go/python all get the fallback)
Writes a JSON summary to stdout.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))

from content_eval.models import Page  # noqa: E402
from content_eval.evaluators import code_syntax_check as csc  # noqa: E402
from example_verification import syntax as ev_syntax  # noqa: E402


def classify(lang: str, content: str, parser_lookup) -> str:
    """Return 'PASS' | 'FAIL' | 'WARN-BRACKET' using the same control flow
    code_syntax_check.evaluate() uses, but with a swappable parser lookup."""
    if lang in csc._PYTHON_LANGS:
        return "N/A-PYTHON"
    if lang not in csc._TS_LANGS:
        return "N/A-OTHER"
    parser = parser_lookup(lang)
    if parser is None:
        return "WARN-BRACKET"
    try:
        tree = parser.parse(content.encode("utf-8", errors="replace"))
    except Exception:
        return "WARN-BRACKET"
    if not tree.root_node.has_error:
        return "PASS"
    error_node = csc._first_error_node(tree.root_node) if hasattr(csc, "_first_error_node") else None
    if error_node is None:
        return "PASS"
    return "FAIL"


def main() -> int:
    platform_dirs = set()
    for name in ("java", "typescript", "cpp"):
        platform_dirs.update(REPO_ROOT.joinpath("content").rglob(name))

    total_files = 0
    total_blocks_considered = 0
    delta_files: list[str] = []
    old_counts = {"PASS": 0, "FAIL": 0, "WARN-BRACKET": 0}
    new_counts = {"PASS": 0, "FAIL": 0, "WARN-BRACKET": 0}
    new_fails_old_missed: list[dict] = []

    seen_files: set[Path] = set()
    for d in platform_dirs:
        if not d.is_dir():
            continue
        for md in d.rglob("*.md"):
            if md in seen_files:
                continue
            seen_files.add(md)
            total_files += 1
            try:
                page = Page.load(md)
            except Exception:
                continue
            file_changed = False
            for block in page.code_blocks:
                lang = (block.lang or "").lower()
                if lang in csc._SKIP_LANGS:
                    continue
                content = textwrap.dedent(block.content).strip()
                lines = content.splitlines()
                if len(lines) < 3:
                    continue
                if lines and csc._NOQA_SYNTAX_RE.search(lines[0]):
                    continue
                if csc._is_declaration_only_snippet(content, lang):
                    continue
                total_blocks_considered += 1

                old = classify(lang, content, csc._ts_parser_for)
                new = classify(lang, content, ev_syntax.parser_for)
                if old in old_counts:
                    old_counts[old] += 1
                if new in new_counts:
                    new_counts[new] += 1
                if old != new:
                    file_changed = True
                    if new == "FAIL" and old == "WARN-BRACKET":
                        if len(new_fails_old_missed) < 20:
                            new_fails_old_missed.append({
                                "file": str(md.relative_to(REPO_ROOT)),
                                "lang": lang, "start_line": block.start_line,
                            })
            if file_changed:
                delta_files.append(str(md.relative_to(REPO_ROOT)))

    result = {
        "total_files_scanned": total_files,
        "total_blocks_considered": total_blocks_considered,
        "old_counts": old_counts,
        "new_counts": new_counts,
        "files_with_any_delta": len(delta_files),
        "sample_delta_files": delta_files[:20],
        "sample_new_fails_previously_warn_only": new_fails_old_missed,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
