#!/usr/bin/env python3
# Adapted from aspose.org
"""content_created_at_backfill.py — Backfill content_created_at for existing English files.

Two sources, in priority order:
  Source 1: frontmatter date: field  — covers blog.aspose.org and kb.aspose.org files
            that have a Hugo publication date.  Value is normalized from 'YYYY-MM-DD'
            to YYYY-MM-DDT00:00:00Z.
  Source 2: bulk git log (--diff-filter=A) — one subprocess call builds a full
            {filepath → first_commit_date} map for the remaining files.

Files with neither source are skipped — no fabricated values are ever written.

Only English .md files are processed.  Locale translation files (index.fr.md, etc.)
are excluded; their content_created_at should track the English source.

Usage:
    python content_created_at_backfill.py [--apply] [--path PATH]

    --dry-run  (default) Print what would change without writing
    --apply    Write changes to disk
    --path     Directory to scan (default: content/ relative to repo root)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_PIPELINE = _HERE.parents[1]
_SCRIPTS = _HERE.parents[2]
_COMMANDS = _HERE.parent
for _path in (_SCRIPTS, _PIPELINE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from config_loader import resolve_content_repo  # noqa: E402


def _resolve_repo_root() -> Path:
    """Return the repo root via $CONTENT_REPO_PATH or config_loader."""
    env = os.environ.get("CONTENT_REPO_PATH")
    if env:
        return Path(env).resolve()
    try:
        return resolve_content_repo()
    except Exception:
        return _HERE.parents[3]


try:
    from provenance import read_provenance, write_provenance  # noqa: E402
except ImportError:
    def read_provenance(fp): return None
    def write_provenance(fp, prov): return False

_REPO_ROOT = _resolve_repo_root()
_CONTENT_ROOT = _REPO_ROOT / "content"

# Locale file detection: e.g. index.fr.md, how-to-foo.es.md
_KNOWN_LANGS = frozenset({
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
    "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
    "sv", "th", "tr", "uk", "vi", "zh",
})

try:
    from core.markdown import _FRONTMATTER_WRITER_RE as _FRONTMATTER_RE
except ImportError:
    import re as _re
    _FRONTMATTER_WRITER_RE = _re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", _re.DOTALL)
    _FRONTMATTER_RE = _FRONTMATTER_WRITER_RE
_DATE_RE = re.compile(r"^date:\s*['\"]?(\d{4}-\d{2}-\d{2})['\"]?", re.MULTILINE)


def _is_locale_file(path: Path) -> bool:
    """Return True if the file is a locale translation (e.g. index.fr.md)."""
    parts = path.name.split(".")
    return len(parts) >= 3 and parts[-1] == "md" and parts[-2] in _KNOWN_LANGS


def _read_date_field(filepath: Path) -> str | None:
    """Return the date: field value from frontmatter, or None if absent."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    fm = _FRONTMATTER_RE.match(text)
    if not fm:
        return None
    m = _DATE_RE.search(fm.group(2))
    if not m:
        return None
    return m.group(1)  # 'YYYY-MM-DD'


def _normalize_date(date_str: str) -> str:
    """Normalize 'YYYY-MM-DD' to 'YYYY-MM-DDT00:00:00Z'."""
    return f"{date_str}T00:00:00Z"


def build_git_map(repo_root: Path) -> dict[str, str]:
    """Build a {absolute_filepath → first_commit_date} map via one bulk git log call.

    Uses --diff-filter=A to find "added" commits only.  The format emits
    a COMMIT <ISO-8601> line before each batch of added files.
    """
    result: dict[str, str] = {}
    try:
        proc = subprocess.run(
            [
                "git", "log",
                "--diff-filter=A",
                "--name-only",
                "--format=COMMIT %aI",
                "--",
                "content/",
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=300,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return result

    current_date: str | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("COMMIT "):
            current_date = line[len("COMMIT "):].strip()
        elif line and current_date:
            abs_path = str((repo_root / line.strip()).resolve())
            # Only record first occurrence (git log is newest-first per path,
            # but --diff-filter=A means each path appears only once anyway).
            if abs_path not in result:
                result[abs_path] = current_date
    return result


def process_file(
    filepath: Path,
    git_map: dict[str, str],
    apply: bool,
) -> str:
    """Process one English .md file.

    Returns one of:
      "updated"          — would write (dry-run) or did write (apply)
      "skipped-ok"       — content_created_at already set
      "skipped-no-prov"  — no provenance block; not our responsibility
      "skipped-no-source"— neither date: field nor git map entry
      "error"            — unexpected exception
    """
    try:
        prov = read_provenance(filepath)
        if prov is None:
            return "skipped-no-prov"

        if "content_created_at" in prov:
            return "skipped-ok"

        # Source 1: frontmatter date: field
        date_val = _read_date_field(filepath)
        if date_val:
            created_at = _normalize_date(date_val)
        else:
            # Source 2: git map
            abs_key = str(filepath.resolve())
            created_at = git_map.get(abs_key)

        if not created_at:
            return "skipped-no-source"

        if apply:
            prov["content_created_at"] = created_at
            write_provenance(filepath, prov)

        return "updated"

    except Exception as exc:
        print(f"ERROR: {filepath}: {exc}", file=sys.stderr)
        return "error"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill content_created_at for English .md files."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to disk (default: dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would change without writing (default behaviour)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="Directory to scan (default: content/ relative to repo root)",
    )
    args = parser.parse_args()

    apply = args.apply

    scan_root = Path(args.path).resolve() if args.path else _CONTENT_ROOT
    if not scan_root.exists():
        print(f"ERROR: scan path does not exist: {scan_root}", file=sys.stderr)
        sys.exit(1)

    mode_label = "APPLY" if apply else "DRY-RUN"
    print(f"content_created_at_backfill — mode={mode_label}  root={scan_root}")
    print("Building git map (one subprocess call) …", end=" ", flush=True)
    git_map = build_git_map(_REPO_ROOT)
    print(f"{len(git_map):,} file-to-date entries loaded.")
    print()

    counters: dict[str, int] = {
        "updated": 0, "skipped-ok": 0, "skipped-no-prov": 0,
        "skipped-no-source": 0, "error": 0,
    }

    for md_file in sorted(scan_root.rglob("*.md")):
        if _is_locale_file(md_file):
            continue
        status = process_file(md_file, git_map, apply)
        counters[status] = counters.get(status, 0) + 1
        if status == "updated":
            print(f"  {'WRITE' if apply else 'WOULD'}: {md_file}")

    print()
    print("Summary:")
    for k, v in counters.items():
        if v:
            print(f"  {k:<22} {v:>6}")


if __name__ == "__main__":
    main()