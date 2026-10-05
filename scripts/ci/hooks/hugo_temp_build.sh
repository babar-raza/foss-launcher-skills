#!/usr/bin/env bash
# hugo_temp_build.sh -- build a Hugo site into a self-cleaning temp dir.
#
# Usage:
#     hugo_temp_build.sh --config <path> [--version V] [--source-dir DIR] [--exec "<shell cmd>"]
#
# Creates ${TMPDIR:-/tmp}/aspose-hugo.XXXXXX, builds into <tmp>/out with the
# pinned Hugo from find_hugo.sh, optionally runs --exec with HUGO_OUT=<tmp>/out
# so the caller can inspect the output, then removes the temp dir (also on
# failure, EXIT, INT and TERM). Sibling aspose-hugo.* dirs older than 24h are
# swept first. Output is NEVER written into the repo, public/, or elsewhere.
#
# --source-dir defaults to the repo root (the layout all configs/*.toml expect).
# Hugo itself may still touch <source>/.hugo_build.lock and <source>/resources/
# (both gitignored); the build OUTPUT is only ever <tmp>/out.
#
# Exit code: hugo's exit code if the build fails, else the --exec command's
# exit code (0 when no --exec). 130 / 143 when interrupted by INT / TERM.
# Note: a shell that starts this script as a background job without job
# control (plain "cmd &" in a non-interactive shell) makes it ignore SIGINT
# by POSIX rule; SIGTERM and interactive Ctrl-C are unaffected.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"

die() { echo "hugo_temp_build.sh: ERROR: $*" >&2; exit 2; }

config="" version="" source_dir="$REPO_ROOT" exec_cmd=""
while [ $# -gt 0 ]; do
    case "$1" in
        --config)     [ $# -ge 2 ] || die "--config requires a value"; config="$2"; shift 2 ;;
        --version)    [ $# -ge 2 ] || die "--version requires a value"; version="$2"; shift 2 ;;
        --source-dir) [ $# -ge 2 ] || die "--source-dir requires a value"; source_dir="$2"; shift 2 ;;
        --exec)       [ $# -ge 2 ] || die "--exec requires a value"; exec_cmd="$2"; shift 2 ;;
        -h|--help)    sed -n '2,22p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done
[ -n "$config" ] || die "--config is required"
[ -f "$config" ] || echo "hugo_temp_build.sh: WARNING: config file not found: $config" >&2

if [ -n "$version" ]; then
    hugo_bin="$("$HERE/find_hugo.sh" --version "$version")"
else
    hugo_bin="$("$HERE/find_hugo.sh")"
fi

tmp_root="${TMPDIR:-/tmp}"
[ -d "$tmp_root" ] || die "temp root does not exist: $tmp_root"

# Sweep stale sibling temp dirs (older than 24h) before creating ours.
find "$tmp_root" -maxdepth 1 -type d -name 'aspose-hugo.*' -mmin +1440 \
    -exec rm -rf {} + 2>/dev/null || true

tmp="$(mktemp -d "$tmp_root/aspose-hugo.XXXXXX")"
child_pid=""
set -m   # job control: each background job gets its own process group

cleanup() {
    local i
    if [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null; then
        # Job control (set -m above) gives the child its own process group, so
        # this also takes down grandchildren (e.g. the sleep under bash -c).
        kill -TERM -- "-$child_pid" 2>/dev/null || kill "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true   # let it release files before rm
    fi
    case "$tmp" in
        */aspose-hugo.*)   # safety: only ever remove our own pattern
            for i in 1 2 3 4 5; do
                rm -rf "$tmp" 2>/dev/null && [ ! -e "$tmp" ] && break
                sleep 0.5
            done
            [ ! -e "$tmp" ] || echo "hugo_temp_build.sh: WARNING: could not remove $tmp" >&2 ;;
    esac
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Run commands in the background + wait, so INT/TERM traps fire immediately
# instead of after the foreground child finishes.
run_bg() {
    "$@" &
    child_pid=$!
    local rc=0
    wait "$child_pid" || rc=$?
    child_pid=""
    return "$rc"
}

out="$tmp/out"
rc=0
run_bg "$hugo_bin" --config "$config" --source "$source_dir" -d "$out" --quiet || rc=$?
if [ "$rc" -ne 0 ]; then
    echo "hugo_temp_build.sh: hugo build failed (exit $rc)" >&2
    exit "$rc"
fi

if [ -n "$exec_cmd" ]; then
    export HUGO_OUT="$out"
    run_bg bash -c "$exec_cmd" || rc=$?
fi
exit "$rc"
