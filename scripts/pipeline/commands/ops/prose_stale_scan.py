"""
G-15 Removed-API Prose-Scan Hardening.

Scans content files for prose references to removed APIs that are no longer
part of the product. S-20 (page_update) only checks evidence.apis[] citations;
this scanner detects stale mentions in the body text itself.

Design gap addressed: when APIs are removed from a product, prose body text
mentioning the removed class/method names is never detected by citation scanning
alone. This scanner closes that gap.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/ops/prose_stale_scan.py {family} {platform}

Reads:
    knowledge/{family}/{platform}/merged/knowledge_delta.json

Scans:
    content/**/{family}/{platform}/ (all 5 subdomains)

Writes:
    reports/gap-analysis/{family}-{platform}-prose-stale.json

Exit codes:
    0  — scan complete (hits may or may not have been found)
    1  — configuration error (missing delta file, bad args, etc.)
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

_REPO_ROOT = _PIPELINE_ROOT.parents[1]

# ------------------------------------------------------------------
# Confidence scoring constants
# ------------------------------------------------------------------
CONFIDENCE_HIGH = 0.95   # bare word in prose sentence
CONFIDENCE_MED  = 0.80   # word inside backtick code span
CONFIDENCE_LOW  = 0.60   # word inside a code block (```) or table


# ------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------

def _strip_frontmatter(lines: list[str]) -> tuple[list[str], int]:
    """Return (body_lines, body_start_lineno_1indexed).

    The first --- block (frontmatter) is removed entirely.
    Line numbers in the returned list start at the line *after* the closing ---.
    """
    if not lines or lines[0].rstrip() != "---":
        return lines, 1

    close = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            close = i
            break

    if close is None:
        # Malformed — treat everything as body
        return lines, 1

    body = lines[close + 1:]
    return body, close + 2   # 1-indexed line number of first body line


def _is_see_also_header(line: str) -> bool:
    stripped = line.strip()
    return bool(re.match(r"^#{1,6}\s+See\s+Also", stripped, re.IGNORECASE))


def _is_evidence_block_start(line: str) -> bool:
    """True if the line starts a YAML evidence: block (at key indent level)."""
    return bool(re.match(r"^evidence\s*:", line))


def _is_pure_link_line(line: str) -> bool:
    """True if the line is *only* a markdown link (possibly in a list).

    Matches patterns like:
      - [Some Text](https://example.com)
      * [text](url)
      [text](url)
    Does NOT match prose sentences that happen to contain a link.
    """
    return bool(re.match(r"^\s*[-*]?\s*\[.*\]\([^)]+\)\s*$", line))


def _line_confidence(line: str) -> float:
    """Assign confidence based on the syntactic context of the line."""
    stripped = line.strip()
    # Inside a fenced code block or table — lower confidence
    if stripped.startswith("```") or stripped.startswith("|"):
        return CONFIDENCE_LOW
    # Inside a backtick code span
    if "`" in stripped:
        return CONFIDENCE_MED
    return CONFIDENCE_HIGH


# ------------------------------------------------------------------
# Core scanner
# ------------------------------------------------------------------

def scan_file(
    file_path: Path,
    patterns: dict[str, re.Pattern],  # api_name -> compiled regex
) -> list[dict[str, Any]]:
    """Scan one markdown file; return list of hit dicts."""
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = raw.splitlines()
    body_lines, body_start = _strip_frontmatter(lines)

    hits: list[dict[str, Any]] = []
    in_see_also = False
    in_evidence_block = False
    in_fenced_code = False
    fenced_fence = None

    for rel_idx, line in enumerate(body_lines):
        abs_lineno = body_start + rel_idx  # 1-indexed

        # --- Track fenced code blocks ---
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence_char = stripped[:3]
            if not in_fenced_code:
                in_fenced_code = True
                fenced_fence = fence_char
            elif fence_char == fenced_fence:
                in_fenced_code = False
                fenced_fence = None
            # Still scan code block lines (with lower confidence) — don't skip

        # --- Track ## See Also ---
        if _is_see_also_header(line):
            in_see_also = True
        if in_see_also:
            continue

        # --- Track evidence: block (YAML front block in body — rare, but some files) ---
        if _is_evidence_block_start(line):
            in_evidence_block = True
        if in_evidence_block:
            # Evidence block ends when a non-indented non-blank line is seen
            # (after the opening line itself)
            if rel_idx > 0 and line and not line[0].isspace() and not _is_evidence_block_start(line):
                in_evidence_block = False
            else:
                continue

        # --- Skip pure link lines ---
        if _is_pure_link_line(line):
            continue

        # --- Match removed API names ---
        confidence = _line_confidence(line)
        for api_name, pattern in patterns.items():
            if pattern.search(line):
                hits.append({
                    "file": str(file_path),
                    "line_number": abs_lineno,
                    "api_name": api_name,
                    "context_snippet": line.rstrip(),
                    "confidence": confidence,
                    "finding": "PROSE_STALE_API_REF",
                })

    return hits


def build_patterns(removed_apis: list[str]) -> dict[str, re.Pattern]:
    """Compile word-boundary patterns for each removed API name."""
    return {
        name: re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        for name in removed_apis
    }


def find_content_files(repo_root: Path, family: str, platform: str) -> list[Path]:
    """Find all markdown files under content/**/{family}/{platform}/."""
    content_root = repo_root / "content"
    results: list[Path] = []

    for subdir in content_root.iterdir():
        if not subdir.is_dir():
            continue
        # Matches all subdomains: docs.aspose.org/en/, blog.aspose.org/, etc.
        for candidate in subdir.rglob(f"{family}/{platform}/**/*.md"):
            results.append(candidate)
        # Also check direct subdir/en/{family}/{platform}/
        for candidate in subdir.rglob(f"en/{family}/{platform}/**/*.md"):
            if candidate not in results:
                results.append(candidate)

    # Deduplicate (rglob can hit the same file via different patterns)
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in results:
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(p)

    return sorted(unique)


def run_scan(
    repo_root: Path,
    family: str,
    platform: str,
    removed_apis: list[str],
) -> dict[str, Any]:
    """Run the full scan and return a result dict."""
    patterns = build_patterns(removed_apis)
    content_files = find_content_files(repo_root, family, platform)

    all_hits: list[dict[str, Any]] = []
    files_with_hits: set[str] = set()

    for fpath in content_files:
        file_hits = scan_file(fpath, patterns)
        if file_hits:
            all_hits.extend(file_hits)
            files_with_hits.add(str(fpath))

    return {
        "scan_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "family": family,
            "platform": platform,
            "removed_apis_count": len(removed_apis),
            "files_scanned": len(content_files),
            "files_with_hits": len(files_with_hits),
            "total_hits": len(all_hits),
        },
        "removed_apis": removed_apis,
        "hits": all_hits,
        "files_with_hits": sorted(files_with_hits),
    }


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: prose_stale_scan.py <family> <platform>", file=sys.stderr)
        print("Example: prose_stale_scan.py cells net", file=sys.stderr)
        return 1

    family = sys.argv[1].lower()
    platform = sys.argv[2].lower()

    delta_path = _REPO_ROOT / "knowledge" / family / platform / "merged" / "knowledge_delta.json"
    if not delta_path.exists():
        print(f"ERROR: knowledge_delta.json not found at {delta_path}", file=sys.stderr)
        return 1

    delta = json.loads(delta_path.read_text(encoding="utf-8"))
    removed_apis: list[str] = delta.get("removed_apis", [])

    if not removed_apis:
        print(f"INFO: No removed_apis found in {delta_path}", file=sys.stderr)
        print("Scan complete — nothing to check.")
        return 0

    print(f"Scanning for {len(removed_apis)} removed APIs in {family}/{platform} content ...",
          file=sys.stderr)

    result = run_scan(_REPO_ROOT, family, platform, removed_apis)

    out_dir = _REPO_ROOT / "reports" / "gap-analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{family}-{platform}-prose-stale.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    meta = result["scan_meta"]
    print(
        f"Done: scanned {meta['files_scanned']} files, "
        f"found {meta['total_hits']} hits in {meta['files_with_hits']} files.",
        file=sys.stderr,
    )
    print(f"Output: {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
