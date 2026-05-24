"""api_symbol_validator.py — Validate Go API symbols in content code blocks.

Scans fenced Go code blocks in content pages for a given family/platform and
checks each called method/function against knowledge/{family}/{platform}/merged/api_surface.json.
Reports symbols that are not found in the API surface as UNKNOWN.

Exit codes:
    0 — all symbols verified or no Go code blocks found
    1 — one or more BLOCKER-level unknown symbols detected
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

_REPO_ROOT = Path(__file__).resolve().parents[4]

_PKG_FUNC_RE = re.compile(r'pdf\.([A-Z][A-Za-z0-9_]*)\s*[({]')

_SKIP_IDENTIFIERS = {
    "fmt", "os", "log", "err", "io", "bytes", "strings", "strconv",
    "sort", "sync", "context", "time", "math", "rand", "bufio",
    "filepath", "http", "url", "json", "xml",
}


def load_api_surface(family: str, platform: str) -> tuple[set, set]:
    api_path = _REPO_ROOT / "knowledge" / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        print(f"ERROR: api_surface.json not found at {api_path}", file=sys.stderr)
        sys.exit(2)
    with api_path.open(encoding="utf-8") as f:
        entries = json.load(f)
    type_names: set[str] = set()
    func_names: set[str] = set()
    for entry in entries:
        name = entry.get("name", "")
        kind = entry.get("kind", "")
        if kind == "function":
            func_names.add(name)
        elif kind == "type_spec":
            type_names.add(name)
    return type_names, func_names


def extract_go_blocks(filepath: Path) -> list[str]:
    text = filepath.read_text(encoding="utf-8")
    blocks: list[str] = []
    in_block = False
    current: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```go") and not in_block:
            in_block = True
            current = []
        elif s == "```" and in_block:
            in_block = False
            blocks.append(chr(10).join(current))
        elif in_block:
            current.append(line)
    return blocks


def validate_file(filepath: Path, type_names: set, func_names: set) -> list[dict]:
    findings: list[dict] = []
    all_known = type_names | func_names
    for idx, block in enumerate(extract_go_blocks(filepath)):
        seen: set[str] = set()
        for m in _PKG_FUNC_RE.finditer(block):
            sym = m.group(1)
            if sym in _SKIP_IDENTIFIERS or sym in seen:
                continue
            seen.add(sym)
            if sym not in all_known:
                findings.append({
                    "file": str(filepath), "block": idx + 1,
                    "symbol": f"pdf.{sym}",
                    "reason": "not in api_surface.json exported types or functions",
                    "severity": "BLOCKER",
                })
    return findings


def find_content_files(family: str, platform: str, content_dir: Path) -> list[Path]:
    sections = [
        content_dir / "blog.aspose.org" / family / platform,
        content_dir / "docs.aspose.org" / "en" / family / platform,
        content_dir / "kb.aspose.org" / "en" / family / platform,
        content_dir / "products.aspose.org" / "en" / family / platform,
        content_dir / "reference.aspose.org" / "en" / family / platform,
    ]
    files: list[Path] = []
    for sec in sections:
        if sec.exists():
            files.extend(sorted(sec.rglob("*.md")))
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate Go API symbols in content code blocks")
    ap.add_argument("family")
    ap.add_argument("platform")
    ap.add_argument("--content-dir", default=str(_REPO_ROOT / "content"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    content_dir = Path(args.content_dir)
    type_names, func_names = load_api_surface(args.family, args.platform)
    files = find_content_files(args.family, args.platform, content_dir)
    if not files:
        print(f"No content files found for {args.family}/{args.platform}")
        return 0

    all_findings: list[dict] = []
    for filepath in files:
        all_findings.extend(validate_file(filepath, type_names, func_names))

    blockers = [f for f in all_findings if f["severity"] == "BLOCKER"]
    if not args.quiet:
        print(f"api_symbol_validator — {args.family}/{args.platform}")
        print(f"Files checked: {len(files)}")
        print(f"Findings: {len(all_findings)} ({len(blockers)} BLOCKER)")
        print()
    for finding in all_findings:
        print(f"  [{finding['severity']}] {finding['symbol']}: {finding['reason']}")
        print(f"         in {finding['file']} (block {finding['block']})")
    if blockers:
        print()
        print(f"RESULT: FAIL — {len(blockers)} BLOCKER symbol(s) not in API surface")
        return 1
    if not args.quiet:
        print("RESULT: PASS — all Go symbols verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
