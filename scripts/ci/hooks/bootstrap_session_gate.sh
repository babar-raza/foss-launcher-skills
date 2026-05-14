#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-$(pwd)}"

if [ ! -f "$repo_root/AGENTS.md" ]; then
  echo "BOOTSTRAP_SESSION_GATE: missing AGENTS.md at $repo_root" >&2
  exit 1
fi

if [ ! -d "$repo_root/skills" ]; then
  echo "BOOTSTRAP_SESSION_GATE: missing skills directory at $repo_root" >&2
  exit 1
fi

echo "BOOTSTRAP_SESSION_GATE: OK"
