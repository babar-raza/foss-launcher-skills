"""launcher_adapter.py — Boundary layer between foss-launcher-skills and upstream launcher.

This module documents which scripts in scripts/ were ported from the upstream
aspose.org launcher, provides a stable invocation interface, and tracks SHA-256
hashes for drift detection.  Any caller needing to invoke the launcher pipeline
should go through this adapter rather than hard-coding paths.

Managed scripts (ported from aspose.org):
    scout.py              — Tree-sitter extraction engine
    merge.py              — Dual-source knowledge merge
    index.py              — Knowledge index generation
    embed.py              — Vector embedding (3-tier)
    corpus_scan.py        — Golden corpus profiling
    golden_index.py       — Golden corpus indexer
    golden_conformance.py — Conformance checking vs golden
    refresh_golden.py     — Golden corpus refresh

Usage (library):
    from scripts.launcher_adapter import LAUNCHER_SCRIPTS, run_scout, run_index

Usage (CLI):
    python scripts/launcher_adapter.py --list          # enumerate managed scripts
    python scripts/launcher_adapter.py --check-drift   # SHA-256 hashes per script
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parent


class LauncherScript(NamedTuple):
    name: str           # stem (e.g. "scout")
    origin: str         # upstream repo name
    purpose: str        # one-line description
    entry_point: str    # repo-relative path


LAUNCHER_SCRIPTS: list[LauncherScript] = [
    LauncherScript(
        "scout", "aspose.org",
        "Tree-sitter extraction engine for FOSS repositories",
        "scripts/scout.py",
    ),
    LauncherScript(
        "merge", "aspose.org",
        "Dual-source knowledge merge (scout + FL)",
        "scripts/merge.py",
    ),
    LauncherScript(
        "index", "aspose.org",
        "Knowledge index generation",
        "scripts/index.py",
    ),
    LauncherScript(
        "embed", "aspose.org",
        "Vector embedding (3-tier)",
        "scripts/embed.py",
    ),
    LauncherScript(
        "corpus_scan", "aspose.org",
        "Golden corpus profiling",
        "scripts/corpus_scan.py",
    ),
    LauncherScript(
        "golden_index", "aspose.org",
        "Golden corpus indexer",
        "scripts/golden_index.py",
    ),
    LauncherScript(
        "golden_conformance", "aspose.org",
        "Conformance checking against golden corpus",
        "scripts/golden_conformance.py",
    ),
    LauncherScript(
        "refresh_golden", "aspose.org",
        "Golden corpus refresh",
        "scripts/refresh_golden.py",
    ),
]

#: Frozen set of filenames (e.g. "scout.py") for membership checks.
LAUNCHER_SCRIPT_NAMES: frozenset[str] = frozenset(
    ls.name + ".py" for ls in LAUNCHER_SCRIPTS
)


def get_script_path(name: str) -> Path:
    """Return the absolute path of a managed launcher script by stem name.

    Raises KeyError if the name is not a managed launcher script.
    """
    for ls in LAUNCHER_SCRIPTS:
        if ls.name == name:
            return REPO_ROOT / ls.entry_point
    raise KeyError(f"Unknown launcher script: {name!r}. "
                   f"Known: {sorted(ls.name for ls in LAUNCHER_SCRIPTS)}")


def script_sha256(name: str) -> str:
    """Return the SHA-256 hex digest of a managed launcher script."""
    path = get_script_path(name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_launcher_script(name: str, args: list[str], **kwargs) -> int:
    """Invoke a managed launcher script as a subprocess.

    Returns the process exit code.  Extra keyword args are forwarded to
    subprocess.run (e.g. cwd=, env=).
    """
    path = get_script_path(name)
    result = subprocess.run([sys.executable, str(path)] + list(args), **kwargs)
    return result.returncode


# ---------------------------------------------------------------------------
# Convenience wrappers for the three core pipeline stages
# ---------------------------------------------------------------------------

def run_scout(family: str, platform: str, repo_path: str, output_dir: str) -> int:
    """Run scout.py: extract knowledge from a FOSS repository."""
    return run_launcher_script("scout", [family, platform, repo_path, output_dir])


def run_merge(family: str, platform: str) -> int:
    """Run merge.py: merge scout and FL claims into merged/."""
    return run_launcher_script("merge", [family, platform])


def run_index(family: str, platform: str) -> int:
    """Run index.py: build the knowledge index from merged/."""
    return run_launcher_script("index", [family, platform])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Inspect the foss-launcher ↔ upstream launcher boundary",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all managed launcher scripts with presence check",
    )
    parser.add_argument(
        "--check-drift", action="store_true",
        help="Print SHA-256 prefix hashes for drift detection",
    )
    args = parser.parse_args(argv)

    if args.list or not (args.list or args.check_drift):
        print("Launcher-origin scripts managed by this adapter:")
        for ls in LAUNCHER_SCRIPTS:
            path = REPO_ROOT / ls.entry_point
            status = "ok" if path.exists() else "MISSING"
            print(f"  [{status}] {ls.entry_point:<40s} {ls.purpose}")

    if args.check_drift:
        print("\nIntegrity hashes (first 16 hex chars of SHA-256) for drift detection:")
        for ls in LAUNCHER_SCRIPTS:
            path = REPO_ROOT / ls.entry_point
            if path.exists():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
                print(f"  {ls.name:<30s}  {digest}…")
            else:
                print(f"  {ls.name:<30s}  MISSING")

    return 0


if __name__ == "__main__":
    sys.exit(_cli())
