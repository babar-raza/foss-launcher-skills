#!/usr/bin/env bash
# find_hugo.sh -- print the absolute path of the pinned local Hugo binary.
#
# Usage:
#     find_hugo.sh [--version V]
#
# Version precedence: --version, then env HUGO_VERSION, then 0.154.5.
# Resolves <repo>/hugo/runtime/V-* (exactly one match required) and prints
# the path of hugo.exe (or hugo on non-Windows). No fallback to PATH, ever.
#
# Exit codes: 0 found; 1 not found / ambiguous / bad usage.
set -euo pipefail

DEFAULT_VERSION="0.154.5"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
RUNTIME_DIR="$REPO_ROOT/hugo/runtime"

die() { echo "find_hugo.sh: ERROR: $*" >&2; exit 1; }

version=""
while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            [ $# -ge 2 ] || die "--version requires a value"
            version="$2"; shift 2 ;;
        --version=*) version="${1#--version=}"; shift ;;
        -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) die "unknown argument: $1 (usage: find_hugo.sh [--version V])" ;;
    esac
done
version="${version:-${HUGO_VERSION:-$DEFAULT_VERSION}}"

# Version is used inside a glob: allow only plain version characters.
case "$version" in
    ""|*[!0-9A-Za-z.]*) die "invalid version '$version' (allowed: digits, letters, dots)" ;;
esac

[ -d "$RUNTIME_DIR" ] || die "runtime dir missing: $RUNTIME_DIR (see docs/operations/hugo-runtime.md to provision)"

matches=()
for d in "$RUNTIME_DIR/$version"-*/; do
    [ -d "$d" ] && matches+=("${d%/}")
done

if [ "${#matches[@]}" -eq 0 ]; then
    die "no runtime directory matching $RUNTIME_DIR/$version-* (see docs/operations/hugo-runtime.md to provision)"
fi
if [ "${#matches[@]}" -gt 1 ]; then
    die "ambiguous: ${#matches[@]} runtime directories match version $version: ${matches[*]}"
fi

dir="${matches[0]}"
bin=""
for name in hugo.exe hugo; do
    if [ -f "$dir/$name" ]; then bin="$dir/$name"; break; fi
done
[ -n "$bin" ] || die "no hugo.exe or hugo binary in $dir"

printf '%s\n' "$bin"
