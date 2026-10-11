"""One-off pilot script for taskcard C1 (read-only, not part of the package).

Walks every content/**/*.md file, parses fenced code blocks with (a) the old
content_eval/models.py toggle-based regex parser and (b) the new
lib.example_verification.code_fences.enumerate_code_blocks tokenizer, and
diffs the resulting block sets. Categorizes every difference so the C1
promotion gate ("diff = 0, or every difference is an explained CommonMark
case, recorded as evidence") can be judged from real portfolio data instead
of guesswork. Writes a JSON summary to stdout; the caller redirects it into
evidence/$RUN/.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))

from lib.example_verification.code_fences import enumerate_code_blocks  # noqa: E402

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
_CODE_FENCE_RE = re.compile(r"^```(\w*)")


def old_parse(body: str) -> list[tuple[str, str]]:
    """Reproduce content_eval/models.py's Page._parse() fence toggle exactly
    (backtick-only, any length treated as 3, no dedent, never emits an
    unterminated trailing block)."""
    lines = body.splitlines()
    in_code = False
    code_lang = ""
    code_lines: list[str] = []
    blocks: list[tuple[str, str]] = []
    for line in lines:
        if line.strip().startswith("```"):
            if not in_code:
                m = _CODE_FENCE_RE.match(line.strip())
                code_lang = m.group(1) if m else ""
                code_lines = []
                in_code = True
            else:
                blocks.append((code_lang, "\n".join(code_lines)))
                in_code = False
            continue
        if in_code:
            code_lines.append(line)
    return blocks


def strip_frontmatter(text: str) -> str:
    m = _FRONTMATTER_RE.match(text)
    return text[m.end():] if m else text


def classify_diff(old_blocks, new_blocks) -> str:
    if len(old_blocks) != len(new_blocks):
        if len(new_blocks) > len(old_blocks):
            return "new_finds_more_blocks"  # tilde fences, unterminated fences, etc.
        return "old_finds_more_blocks"  # unexpected -- worth inspecting
    for (old_lang, old_content), nb in zip(old_blocks, new_blocks):
        if old_lang != nb.lang:
            return "lang_token_differs"  # c#/c++/objective-c truncation
        if old_content != nb.content:
            return "content_differs"  # indentation dedent, etc.
    return "identical"


def main() -> int:
    content_dir = REPO_ROOT / "content"
    total_files = 0
    files_with_blocks = 0
    category_counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    csharp_cpp_tag_files = 0
    csharp_cpp_tag_count = 0
    tilde_fence_files = 0

    for md_path in content_dir.rglob("*.md"):
        total_files += 1
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = strip_frontmatter(text)
        old_blocks = old_parse(body)
        new_blocks = enumerate_code_blocks(body)
        if old_blocks or new_blocks:
            files_with_blocks += 1
        rel = str(md_path.relative_to(REPO_ROOT))

        for lang, _content in old_blocks:
            if lang.lower() in ("c#", "c++"):
                csharp_cpp_tag_count += 1
        if any(lang.lower() in ("c#", "c++") for lang, _ in old_blocks):
            csharp_cpp_tag_files += 1
        if "~~~" in body:
            tilde_fence_files += 1

        category = classify_diff(old_blocks, new_blocks)
        category_counts[category] = category_counts.get(category, 0) + 1
        if category != "identical" and len(examples.get(category, [])) < 5:
            examples.setdefault(category, []).append(rel)

    result = {
        "total_files_scanned": total_files,
        "files_with_any_code_block": files_with_blocks,
        "category_counts": category_counts,
        "examples_per_category": examples,
        "csharp_or_cpp_tagged_files": csharp_cpp_tag_files,
        "csharp_or_cpp_tagged_block_occurrences": csharp_cpp_tag_count,
        "files_containing_tilde_sequence": tilde_fence_files,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
