"""
lib/example_verification/acquire.py

CONTRACT: scripts/pipeline/lib/example_verification/acquire.py
  purpose: the language-agnostic half of "acquiring" a disposable
           environment to verify code blocks against -- specifically,
           README-named fixture staging, faithfully ported from S-120's
           `_stage_readme_fixtures`/`_readme_fixture_names`
           (readme_refresh_run.py:4874-4923). Both existing real runners
           (python, typescript) already called this unchanged for the same
           reason it lives here rather than in either runner file: it
           operates on `(lang, code)` pairs, not on anything Python- or
           TypeScript-specific.
  inputs:  a work/project directory, the candidate's (lang, code) block
           pairs, and the product's clone-cache path
  outputs: stage_fixtures() -> {"staged": {basename: relative_source_path},
           "unresolved": [basename, ...]}
  owner_domain: content-quality

Rollout step C3 note: this is a faithful, behavior-preserving port (the
stage's own promotion gate is "100% of existing python/ts tests green",
not a redesign) -- the acquire-failure classification/retry machinery the
governing plan's Round 2 design describes (transient-network vs.
resolution-failure vs. unknown, narrowly retried) is real, but unbuilt,
future work for a later phase, not something this port invents ahead of
its own dedicated design pass. Language-specific acquire (a real venv +
pip install; a real npm install + build + self-link) stays in
runners/python.py and runners/typescript.py, ported alongside each
runner's own execution logic in a later step of this same taskcard.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

_FIXTURE_NAME_RE = re.compile(r"""["']([A-Za-z0-9_][A-Za-z0-9_.,+ -]*\.[A-Za-z0-9]{1,6})["']""")
_FIXTURE_SEARCH_SKIP_DIRS = frozenset({".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"})


def readme_fixture_names(blocks: "list[tuple[str, str]]") -> list[str]:
    """Quoted, extension-bearing file names used by any code block (both
    the reader's input fixtures and the example's own output names -- the
    latter are simply never found in the clone cache, so staging them is a
    harmless no-op). Bash lines contribute their bare `path.ext` tokens
    too (a CLI example rarely quotes its input file). `blocks` is a list
    of `(lang, code)` pairs, e.g. from `code_fences.enumerate_code_blocks`."""
    names: list[str] = []
    for lang, code in blocks:
        names.extend(_FIXTURE_NAME_RE.findall(code))
        if lang in ("bash", "sh", "shell"):
            for token in re.findall(r"(?<![\w/\\-])([A-Za-z0-9_][A-Za-z0-9_,+-]*\.[A-Za-z0-9]{1,6})(?![\w/])", code):
                names.append(token)
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        base = n.replace("\\", "/").split("/")[-1]
        if base and base not in seen and "." in base and not base.startswith("."):
            seen.add(base)
            out.append(base)
    return out


def stage_fixtures(work_dir: Path, blocks: "list[tuple[str, str]]", clone_cache: Path) -> dict:
    """Copy every README-named file that exists in the clone cache (exact
    basename match, first match in sorted walk order; symlinks never
    followed) into `work_dir`. Returns `{"staged": {basename: relative
    source path}, "unresolved": [basename, ...]}`."""
    wanted = readme_fixture_names(blocks)
    staged: dict[str, str] = {}
    if not wanted or not clone_cache.is_dir():
        return {"staged": staged, "unresolved": list(wanted)}
    remaining = set(wanted)
    for root, dirs, files in os.walk(clone_cache):
        dirs[:] = sorted(d for d in dirs if d not in _FIXTURE_SEARCH_SKIP_DIRS)
        for name in sorted(files):
            if name in remaining:
                src = Path(root) / name
                if src.is_symlink():
                    continue
                dest = work_dir / name
                if not dest.exists():
                    shutil.copyfile(src, dest)
                staged[name] = src.relative_to(clone_cache).as_posix()
                remaining.discard(name)
        if not remaining:
            break
    return {"staged": staged, "unresolved": sorted(remaining)}
