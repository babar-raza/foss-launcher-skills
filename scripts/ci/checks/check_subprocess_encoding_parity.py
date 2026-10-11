"""check_subprocess_encoding_parity.py — ratchet gate for locale-dependent
subprocess text decoding (2026-08-30 stale-guard plan, T7 / TC-SG-06).

The defect class (ST-096, reproduced): `subprocess.run(..., text=True)` with
no `encoding=` decodes with the LOCALE codec — cp1252 on this repo's Windows
production platform — so a single unmappable byte kills the reader thread
(stdout=None, silently readable as any verdict) and mappable non-ASCII bytes
decode differently from UTF-8 file reads, silently defusing byte-exact
comparisons. ~144 call sites existed at plan time, ~35 of them hidden behind
runner ALIASES (`_COMMAND_RUNNER(...)`, `runner(...)`), which is why this
check lints the CALL SHAPE (a `text=True`/`universal_newlines=True` keyword
with no `encoding=`), not the callee name.

Also scanned: inline `$PYTHON -c` heredocs in hook .sh files that read
`sys.stdin` without going through `sys.stdin.buffer` (the same locale decode,
inside fail-closed 2>/dev/null blocks).

Ratchet semantics (model: scripts/ci/monkeypatch_baseline.json): existing
sites are grandfathered in scripts/ci/subprocess_encoding_baseline.json;
a file may only ever DECREASE its count. Regenerate deliberately with
`--baseline > scripts/ci/subprocess_encoding_baseline.json` and commit the
diff with a note — never regenerate to make a new violation fit.

Exit codes: 0 ok; 1 regression vs baseline (or any violation with
--no-baseline); 2 usage.
"""
from __future__ import annotations

import argparse
import ast
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning)
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_BASELINE = Path(__file__).resolve().parent.parent / "subprocess_encoding_baseline.json"
_SCAN_ROOT = _REPO_ROOT / "scripts"

_EXCLUDED_PARTS = {"__pycache__", ".venv", "node_modules"}
_STDIN_RE = re.compile(r"(json\.load\(sys\.stdin\)|sys\.stdin\.read\(\))")


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Test seam."""
    global _REPO_ROOT, _SCAN_ROOT
    if repo_root is None:
        _REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
    else:
        _REPO_ROOT = Path(repo_root)
    _SCAN_ROOT = _REPO_ROOT / "scripts"


def _py_violations(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return 0
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {kw.arg for kw in node.keywords if kw.arg}
        text_mode = False
        for kw in node.keywords:
            if kw.arg in ("text", "universal_newlines") \
                    and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                text_mode = True
        if text_mode and "encoding" not in keywords:
            count += 1
    return count


def _sh_violations(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    count = 0
    for line in text.splitlines():
        if _STDIN_RE.search(line) and "sys.stdin.buffer" not in line:
            count += 1
    return count


def _scan_file(path: Path) -> int:
    if path.suffix == ".py":
        return _py_violations(path)
    if path.suffix == ".sh":
        return _sh_violations(path)
    return 0


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def scan(paths: "list[Path] | None" = None) -> "dict[str, int]":
    """path(repo-relative, posix) -> violation count (only non-zero entries)."""
    if paths is None:
        candidates = [p for pattern in ("*.py", "*.sh")
                      for p in _SCAN_ROOT.rglob(pattern)
                      if not any(part in _EXCLUDED_PARTS for part in p.parts)]
    else:
        candidates = [Path(p) if Path(p).is_absolute() else _REPO_ROOT / p for p in paths]
    out: "dict[str, int]" = {}
    for path in sorted(set(candidates)):
        if not path.is_file():
            continue
        count = _scan_file(path)
        if count:
            out[_rel(path)] = count
    return out


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true",
                        help="Print the current scan as baseline JSON and exit 0")
    parser.add_argument("--compare-baseline", default=None, metavar="JSON",
                        help="Fail (exit 1) if any scanned file EXCEEDS its baselined count")
    parser.add_argument("--all-files", action="store_true",
                        help="Scan every scripts/**/*.py|sh (default when no --files/stdin)")
    parser.add_argument("--files", nargs="*", default=None,
                        help="Scope to these files (e.g. the staged set); "
                             "default reads newline-delimited paths from stdin when piped")
    args = parser.parse_args(argv)

    files: "list[str] | None" = args.files
    if files is None and not args.all_files and not args.baseline and not sys.stdin.isatty():
        files = [line.strip() for line in sys.stdin if line.strip()]
    scoped = None if (args.all_files or args.baseline or files is None) else [Path(f) for f in files]
    if scoped is not None and not scoped:
        print("subprocess-encoding-parity: no files in scope.")
        return 0

    current = scan(scoped)

    if args.baseline:
        print(json.dumps({
            "generator": "check_subprocess_encoding_parity.py --baseline",
            "policy": "counts may only decrease; regenerate deliberately, never to fit a new violation",
            "files": current,
        }, indent=2, sort_keys=True))
        return 0

    if args.compare_baseline:
        try:
            baseline = json.loads(Path(args.compare_baseline).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"subprocess-encoding-parity: cannot read baseline: {exc}", file=sys.stderr)
            return 2
        base_files = baseline.get("files", {})
        regressions = {
            path: (count, base_files.get(path, 0))
            for path, count in current.items()
            if count > base_files.get(path, 0)
        }
        if regressions:
            print(f"SUBPROCESS ENCODING PARITY: {len(regressions)} file(s) add "
                  f"text-mode subprocess calls without encoding= (the ST-096 class):")
            for path, (count, base) in sorted(regressions.items()):
                print(f"  {path}: {count} (baseline {base})")
            print("Fix: pass encoding='utf-8', errors='replace' (this repo's house style),")
            print("or read bytes and decode explicitly. Comparisons of git-object content")
            print("belong in lib/stale_file_regression.py's OID engine, not in decoded text.")
            return 1
        print(f"subprocess-encoding-parity: OK ({len(current)} baselined file(s) in scope, "
              f"no increases).")
        return 0

    if current:
        print(f"subprocess-encoding-parity: {sum(current.values())} violation(s) "
              f"in {len(current)} file(s):")
        for path, count in sorted(current.items()):
            print(f"  {path}: {count}")
        return 1
    print("subprocess-encoding-parity: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
