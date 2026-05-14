#!/usr/bin/env python3
"""Compatibility entrypoint for standalone skill mirror sync checks."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--sync", action="store_true")
    mode.add_argument("--report", action="store_true")
    mode.add_argument("--list-ids", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    if args.list_ids:
        registry = args.repo_root / "skills" / "registry.yaml"
        print(registry.read_text(encoding="utf-8") if registry.exists() else "skills: []")
        return 0
    if args.report:
        check = subprocess.run([sys.executable, str(args.repo_root / "scripts" / "sync_agents.py"), "--check", "--repo-root", str(args.repo_root)])
        commands = subprocess.run([sys.executable, str(args.repo_root / "scripts" / "sync_commands.py"), "--check", "--repo-root", str(args.repo_root)])
        return 0 if check.returncode == 0 and commands.returncode == 0 else 1
    flag = "--check" if args.check else "--sync"
    check = subprocess.run([sys.executable, str(args.repo_root / "scripts" / "sync_agents.py"), flag, "--repo-root", str(args.repo_root)])
    commands = subprocess.run([sys.executable, str(args.repo_root / "scripts" / "sync_commands.py"), flag, "--repo-root", str(args.repo_root)])
    return 0 if check.returncode == 0 and commands.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
