"""locale_tag_mistranslation_fixer.py — TC-02/TC-03 (MT073-2026-09-24-
LOCALE-CODE-BLOCK-DEFECT-REMEDIATION): dry-run and apply the tag-only fix
for the dominant ST-211 defect class TC-19 diagnosed.

CONTRACT: scripts/pipeline/commands/governance/locale_tag_mistranslation_fixer.py
  purpose: for every locale page, use block_matcher.py's count-robust
           pairing (TC-01) to find each English/locale block correspondence,
           then flag (and, with --apply, fix) exactly the pattern TC-19's
           report confirmed byte-for-byte on 6 real files: English tags a
           block as a NON_EXECUTABLE_LANGS member (usually `text` -- a bare
           API signature, license text, an email preview, a comment
           fragment), the locale copy of the SAME block gets a real
           programming-language tag instead, and tree-sitter correctly
           flags the now-mis-tagged non-code content as broken. The fix is
           tag-only: restore the locale fence's language token to match
           English's tag at the matched block. No code content is ever
           touched.
  inputs:  none (walks content/ directly via `git ls-files`, same idiom
           example_verification_sweep.py already established)
  outputs: a dated JSON report (--report) of every candidate found; with
           --apply, rewrites the flagged fence lines in place
  owner_domain: content-quality
  requires_test: true

Candidate criteria (all three must hold -- narrow by design, not "any tag
difference"):
  1. English's tag at the matched block is a `NON_EXECUTABLE_LANGS` member.
  2. Locale's tag at the matched block is a real, checkable language
     (resolves via `syntax.canonical_for`), and differs from English's tag.
  3. The locale block's CURRENT content, checked under its CURRENT (wrong)
     tag, is a real `SYNTAX-ERROR` -- the exact, reproducible bug signature
     TC-19 diagnosed. A tag difference alone, with no resulting syntax
     error, is not this defect and is left untouched (it may be a
     legitimate difference, e.g. a locale page that genuinely shows a
     different, valid example).

The match itself must also be high-confidence: block_matcher.py's
"unmatched" or a same-position "position" match are both used as-is
(position implies the pages have equal block counts, the common,
already-reliable case); a "content-similarity" match below
`--min-similarity` (default matches block_matcher.py's own default, 0.5)
is skipped, not guessed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = _PIPELINE_ROOT / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from content_discovery import LOCALE_CODES  # noqa: E402
from example_verification.block_matcher import match_blocks  # noqa: E402
from example_verification.code_fences import CodeBlock, enumerate_code_blocks  # noqa: E402
from example_verification.registry import NON_EXECUTABLE_LANGS  # noqa: E402
from example_verification.syntax import canonical_for, check_syntax  # noqa: E402

_REPO_ROOT = _PIPELINE_ROOT.parents[1]

_SITES: "tuple[str, ...]" = ("docs.aspose.org", "blog.aspose.org", "kb.aspose.org", "reference.aspose.org")


@dataclass(slots=True)
class TagFixCandidate:
    locale_path: str
    en_path: str
    locale_block_index: int
    en_block_index: int
    match_method: str
    match_similarity: float
    old_tag: str
    new_tag: str
    start_line: int  # 1-based, RAW file (frontmatter-inclusive)
    end_line: int


def _is_locale_page(rel_path: str) -> bool:
    parts = rel_path.split("/")
    if len(parts) < 2 or not rel_path.endswith(".md"):
        return False
    site = parts[1]
    if site not in _SITES:
        return False
    if site == "blog.aspose.org":
        stem = parts[-1][:-3]
        segs = stem.split(".")
        return len(segs) >= 2 and segs[-1] in LOCALE_CODES
    return len(parts) > 2 and parts[2] in LOCALE_CODES


def _en_counterpart(rel_path: str) -> str:
    parts = rel_path.split("/")
    site = parts[1]
    if site == "blog.aspose.org":
        stem = parts[-1][:-3]
        segs = stem.split(".")
        base = ".".join(segs[:-1])
        return "/".join(parts[:-1] + [base + ".md"])
    newparts = list(parts)
    newparts[2] = "en"
    return "/".join(newparts)


def _blocks_with_offset(abs_path: Path) -> "tuple[list[CodeBlock], str] | tuple[None, None]":
    """Returns (blocks, raw_text) with block line numbers relative to the
    RAW file (frontmatter included) -- needed so --apply can locate the
    exact fence line on disk, unlike locale_code_block_equivalence.py's
    own body-relative-only numbering."""
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    body = text
    offset = 0
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            body = text[end + 4:]
            offset = text[: end + 4].count("\n")
    return enumerate_code_blocks(body, line_offset=offset), text


def find_candidates(*, repo_root: "Path | None" = None, min_similarity: float = 0.5) -> "list[TagFixCandidate]":
    repo_root = repo_root or _REPO_ROOT
    files = subprocess.run(
        ["git", "ls-files", "content"], cwd=str(repo_root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout.splitlines()

    candidates: "list[TagFixCandidate]" = []
    en_cache: "dict[str, list[CodeBlock] | None]" = {}

    for rel_path in files:
        if not _is_locale_page(rel_path):
            continue
        loc_blocks, _ = _blocks_with_offset(repo_root / rel_path)
        if not loc_blocks:
            continue

        en_path = _en_counterpart(rel_path)
        if en_path not in en_cache:
            en_blocks, _ = _blocks_with_offset(repo_root / en_path)
            en_cache[en_path] = en_blocks
        en_blocks = en_cache[en_path]
        if not en_blocks:
            continue

        matches = match_blocks(en_blocks, loc_blocks, min_similarity=min_similarity)
        for m in matches:
            if m.locale_index is None:
                continue
            en_block = en_blocks[m.en_index]
            loc_block = loc_blocks[m.locale_index]
            en_tag = en_block.canonical_lang or en_block.lang or ""
            loc_tag = loc_block.canonical_lang or loc_block.lang or ""
            if en_tag not in NON_EXECUTABLE_LANGS:
                continue
            if loc_tag == en_tag or canonical_for(loc_tag) is None:
                continue
            result = check_syntax(loc_tag, loc_block.content)
            if result.status != "SYNTAX-ERROR":
                continue
            candidates.append(TagFixCandidate(
                locale_path=rel_path, en_path=en_path,
                locale_block_index=m.locale_index, en_block_index=m.en_index,
                match_method=m.method, match_similarity=m.similarity,
                old_tag=loc_block.lang, new_tag=en_block.lang,
                start_line=loc_block.start_line, end_line=loc_block.end_line,
            ))
    return candidates


def apply_fix(candidate: TagFixCandidate, *, repo_root: "Path | None" = None) -> bool:
    """Rewrite exactly the fence-open line's language token in place.
    Returns True if applied, False if the on-disk line no longer matches
    what was expected (caller should re-scan, not force it)."""
    repo_root = repo_root or _REPO_ROOT
    abs_path = repo_root / candidate.locale_path
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    line_idx = candidate.start_line - 1
    if line_idx < 0 or line_idx >= len(lines):
        return False
    line = lines[line_idx]
    stripped = line.lstrip(" ")
    indent = line[: len(line) - len(stripped)]
    fence_chars = 0
    for ch in stripped:
        if ch in "`~":
            fence_chars += 1
        else:
            break
    if fence_chars < 3:
        return False
    fence = stripped[:fence_chars]
    info = stripped[fence_chars:]
    if not info.startswith(candidate.old_tag):
        return False
    new_info = candidate.new_tag + info[len(candidate.old_tag):]
    lines[line_idx] = f"{indent}{fence}{new_info}"
    # newline="" is mandatory here: read_text() above already normalized
    # CRLF -> LF universally (Path.read_text's own default), so "\n" is
    # the file's real, current line separator -- without newline="",
    # write_text's platform-default translation would convert the WHOLE
    # file to CRLF on Windows (silently, git's own text=auto normalization
    # papers over this at commit time, but the working-tree copy would be
    # left wrong until a future checkout touches it -- confirmed live
    # while building this).
    abs_path.write_text("\n".join(lines), encoding="utf-8", newline="")
    return True


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="write the full candidate list to this path")
    parser.add_argument("--min-similarity", type=float, default=0.5)
    parser.add_argument("--apply", action="store_true", help="write the fixes to disk (default: dry-run)")
    parser.add_argument("--site", help="restrict to one site, e.g. reference.aspose.org")
    parser.add_argument("--limit", type=int, help="apply/report at most N candidates (for reviewable batches)")
    parser.add_argument("--repo-root", type=Path, default=None, help="override repo root (testing)")
    args = parser.parse_args(argv)

    candidates = find_candidates(repo_root=args.repo_root, min_similarity=args.min_similarity)
    if args.site:
        candidates = [c for c in candidates if f"/{args.site}/" in c.locale_path]
    if args.limit:
        candidates = candidates[: args.limit]

    applied = 0
    failed_apply: "list[str]" = []
    if args.apply:
        for c in candidates:
            if apply_fix(c, repo_root=args.repo_root):
                applied += 1
            else:
                failed_apply.append(c.locale_path)

    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "apply" if args.apply else "dry-run",
        "candidate_count": len(candidates),
        "applied_count": applied,
        "failed_apply": failed_apply,
        "by_site": {},
        "candidates": [asdict(c) for c in candidates],
    }
    by_site: "dict[str, int]" = {}
    for c in candidates:
        site = c.locale_path.split("/")[1]
        by_site[site] = by_site.get(site, 0) + 1
    report["by_site"] = by_site

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"mode={report['mode']} candidates={report['candidate_count']} applied={report['applied_count']} by_site={by_site}")
    if failed_apply:
        print(f"FAILED to apply {len(failed_apply)} (on-disk line no longer matched expected -- re-scan): {failed_apply[:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
