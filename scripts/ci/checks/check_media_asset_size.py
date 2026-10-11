"""check_media_asset_size.py -- blocks a commit that would introduce an
over-budget file under static/media/.

Found live 2026-08-06 and again 2026-08-07: an operator manually drops a
freshly-updated icon.png/banner.png straight at its canonical path in
static/media/{family}/{platform}/, over S-119's 1,048,576-byte budget, twice
in two days across 13 files total (static/media/email/*, then
static/media/html/*, static/media/page/*). S-119's own tool
(optimize_media_assets.py) already handles this correctly once someone
remembers to run it -- but nothing stopped an oversized file from being
committed BEFORE that happens. This check closes that gap at the one point
that can't be skipped by forgetting a manual step: the commit itself.

Deliberately narrow: only checks byte size against the SAME budget constant
S-119 itself uses (_cfg_max_bytes, imported directly -- not duplicated, so
the two can never silently drift apart), and only for files already staged
in a commit. It does not run compression, does not judge visual quality, and
does not replace the mandatory human/agent visual review S-119's own skill
doc requires for a lossy result -- it exists solely to fail loud, before the
oversized bytes reach git history, when that review step was skipped
entirely.

Usage:
    git diff --cached --name-only | python check_media_asset_size.py
    python check_media_asset_size.py --files static/media/pdf/python/icon.png

Exit codes:
  0 -- no staged static/media/ file exceeds the budget (including: no
       staged files under static/media/ at all)
  1 -- at least one staged static/media/ file exceeds the budget
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_DIR = _REPO_ROOT / "scripts" / "pipeline"
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops.optimize_media_assets import _cfg_max_bytes  # noqa: E402

_MEDIA_PREFIX = "static/media/"
_IMAGE_SUFFIXES = (".png", ".webp", ".jpg", ".jpeg")


def find_oversized(files: "list[str]", *, repo_root: Path = _REPO_ROOT) -> "list[tuple[str, int]]":
    violations = []
    for f in files:
        normalized = f.replace("\\", "/")
        if not normalized.startswith(_MEDIA_PREFIX):
            continue
        if not normalized.lower().endswith(_IMAGE_SUFFIXES):
            continue
        path = repo_root / normalized
        if not path.is_file():
            continue  # staged deletion or rename target already gone from working tree
        size = path.stat().st_size
        if size > _cfg_max_bytes:
            violations.append((normalized, size))
    return violations


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="*", default=None,
                         help="Explicit file list (default: read newline-separated paths from stdin)")
    args = parser.parse_args(argv)

    if args.files is not None:
        files = args.files
    else:
        files = [line.strip() for line in sys.stdin if line.strip()]

    violations = find_oversized(files, repo_root=_REPO_ROOT)
    if not violations:
        return 0

    for path, size in violations:
        over_by = size - _cfg_max_bytes
        print(f"  {path}  ({size:,} bytes, {over_by:,} over the {_cfg_max_bytes:,}-byte budget)")
    print(
        "FAIL: staged static/media/ file(s) exceed the S-119 byte budget. "
        "Run /media-optimize (S-119) on the affected family/platform, visually "
        "review the result, then --confirm-reviewed before committing."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
