#\!/bin/bash
# reference-transaction-unshallow.sh
# Installed as .git/hooks/reference-transaction by scripts/install-hooks.sh
#
# Purpose: auto-remove false .git/shallow entries after GitHub Desktop fetches.
#
# Root cause addressed:
#   GitHub Desktop 3.5.8 ships git 2.53.0.windows.3, which writes server-sent
#   shallow packets into .git/shallow during every normal fetch, even without
#   --depth. GitHub's protocol v2 server sends these packets for repos that
#   were previously served shallow. The shallow file is false: all history
#   objects are locally present. Deleting it restores correct git behaviour.
#
# Trigger:
#   git fires "reference-transaction committed" after every committed reference
#   update (fetch, commit, merge, checkout) -- standard hook, git 2.28+.
#
# Lock handling:
#   Waits for any concurrent .git/shallow.lock to clear before deleting, so
#   the hook does not race with an in-progress fetch that is still writing.
#
# Loop guard:
#   Guard file .git/.unshallow-in-progress contains the PID of the running
#   instance. Stale guards (PID no longer alive) are removed automatically.
#   A trap ensures the guard is always cleaned up on exit.

[ "$1" = "committed" ] || exit 0

GIT_DIR=$(git rev-parse --git-dir 2>/dev/null) || exit 0
SHALLOW="$GIT_DIR/shallow"
GUARD="$GIT_DIR/.unshallow-in-progress"

[ -f "$SHALLOW" ] || exit 0   # nothing to do

# PID-based guard: if another instance is still alive, skip; else clean stale guard
if [ -f "$GUARD" ]; then
    guard_pid=$(cat "$GUARD" 2>/dev/null)
    if [ -n "$guard_pid" ] && kill -0 "$guard_pid" 2>/dev/null; then
        exit 0   # another live instance is handling it
    fi
    rm -f "$GUARD"   # stale guard (prior crash) -- clean up and proceed
fi

echo $$ > "$GUARD"
trap 'rm -f "$GUARD"' EXIT

# Wait for any concurrent fetch to finish writing the shallow file
i=0
while [ -f "${SHALLOW}.lock" ] && [ $i -lt 30 ]; do
    sleep 1
    i=$((i + 1))
done

# Remove the false shallow file (full history objects are locally intact)
rm -f "$SHALLOW"
