#!/bin/bash
# decommission-self-hosted-runner.sh -- Remove a GitHub Actions self-hosted runner: stop it,
# delete its GitHub registration, remove its install directory. See
# docs/operations/self-hosted-runner-setup.md "Decommissioning a runner" (was: "Not yet
# automated" -- MT069 HC-18, 2026-09-23, built and proven against a real temporary runner).
#
# What this script does NOT do, and why:
#   - Does not stop/uninstall a systemd SERVICE. That needs `sudo`, which cannot be supplied
#     non-interactively by an agent session (confirmed live, twice, in this repo's history --
#     see docs/operations/self-hosted-runner-setup.md). If a service is detected for this
#     runner, this script prints the exact sudo commands and stops -- it never guesses at
#     removing a service it cannot itself stop cleanly.
#   - Never targets alienware-m18-wsl2-private or alienware-m18-wsl2-test by name unless you
#     pass --i-mean-it (see below) -- those are this org's two real, load-bearing runners, and
#     accidentally decommissioning one is exactly the mistake this safety check exists to catch.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: decommission-self-hosted-runner.sh --repo <owner/repo> --name <runner-name> [--dir <path>] [--token <PAT>] [--i-mean-it]

Required:
  --repo   The repo this runner is registered against (e.g. Aspose/aspose.org-workflows).
  --name   The runner's exact name as it appears in `gh api repos/<repo>/actions/runners`.

Optional:
  --dir         Install directory to remove after registration is deleted.
                Default: $HOME/actions-runner-<name>
  --token       A registration/admin token if `gh` is unavailable in this shell (same as
                setup-self-hosted-runner.sh's --token). Otherwise `gh api` is used directly.
  --i-mean-it   Required to target alienware-m18-wsl2-private or alienware-m18-wsl2-test by
                name -- this org's two real runners. Without it, targeting either by name is
                refused before anything is touched.

What it does, in order:
  1. Looks up the runner's id and status via the GitHub API.
  2. If a systemd service unit matching this runner is active, prints the sudo stop/uninstall
     commands and STOPS -- rerun this script after you've run them.
  3. Otherwise, if a foreground (non-service) listener process is running for this runner's
     directory, kills it (the same `Runner.Listener run$` pattern the setup guide documents --
     note the trailing `$`, which excludes a service-managed listener).
  4. Deletes the runner's GitHub registration (`DELETE .../actions/runners/<id>`).
  5. Removes the install directory.
  6. Verifies: the runner no longer appears in the API's runner list, and the directory is gone.
EOF
}

REPO=""; NAME=""; DIR=""; TOKEN=""; I_MEAN_IT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --dir) DIR="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --i-mean-it) I_MEAN_IT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$REPO" ] || [ -z "$NAME" ]; then
  echo "ERROR: --repo and --name are required." >&2; usage >&2; exit 2
fi

case "$NAME" in
  alienware-m18-wsl2-private|alienware-m18-wsl2-test)
    if [ "$I_MEAN_IT" -ne 1 ]; then
      echo "REFUSING: '$NAME' is one of this org's two real, load-bearing runners." >&2
      echo "If you genuinely mean to decommission it, rerun with --i-mean-it." >&2
      exit 3
    fi
    ;;
esac

DIR="${DIR:-$HOME/actions-runner-$NAME}"

# Portable JSON filtering: this host has no system `jq` (a confirmed, real gap -- see
# docs/operations/self-hosted-runner-setup.md). Every JSON response is filtered through python
# instead, never through a --jq flag passed to gh/curl (found live: curl silently rejected
# --jq and, wrapped in `|| true`, that failure read as "runner not found" instead of an error --
# the script reported a successful decommission while the runner was still fully registered).
_PY=""
for cand in python3 python .venv/Scripts/python; do
  if command -v "$cand" >/dev/null 2>&1; then _PY="$cand"; break; fi
done
if [ -z "$_PY" ]; then echo "ERROR: no python interpreter found (tried python3, python, .venv/Scripts/python)." >&2; exit 5; fi

# Raw JSON GET, always -- no --jq passed to either transport.
_gh_get() {
  if [ -n "$TOKEN" ]; then
    curl -fsS -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "https://api.github.com/$1"
  else
    gh api "$1"
  fi
}

_gh_delete() {
  if [ -n "$TOKEN" ]; then
    curl -fsS -X DELETE -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "https://api.github.com/$1"
  else
    gh api -X DELETE "$1"
  fi
}

echo "== Looking up '$NAME' in $REPO =="
RUNNERS_JSON=$(_gh_get "repos/$REPO/actions/runners" 2>&1) || { echo "ERROR: could not list runners: $RUNNERS_JSON" >&2; exit 5; }
RUNNER_ID=$(echo "$RUNNERS_JSON" | "$_PY" -c "
import json, sys
d = json.load(sys.stdin.buffer)  # bytes -> json.load's own UTF-8 decoding, never locale-dependent text-mode stdin (ST-096 class)
matches = [r['id'] for r in d.get('runners', []) if r['name'] == '$NAME']
print(matches[0] if matches else '')
")
if [ -z "$RUNNER_ID" ]; then
  echo "No runner named '$NAME' found in $REPO -- nothing to remove from GitHub (may already be decommissioned)."
else
  echo "  id=$RUNNER_ID"
fi

echo "== Checking for a systemd service for this runner (read-only, no sudo) =="
SERVICE=$(systemctl list-units --type=service --all --no-legend 2>/dev/null | grep -i "$NAME" | awk '{print $1}' | head -1 || true)
if [ -n "$SERVICE" ] && systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
  echo "ACTIVE SERVICE FOUND: $SERVICE"
  echo "This script cannot stop a service without sudo. Run these yourself, then rerun this script:"
  echo "  sudo systemctl stop $SERVICE"
  echo "  cd $DIR && sudo ./svc.sh uninstall"
  exit 4
fi

echo "== No active service -- checking for a foreground (non-service) listener =="
if pgrep -f "$DIR/bin/Runner.Listener run\$" >/dev/null 2>&1; then
  echo "Killing foreground listener for $DIR"
  pkill -f "$DIR/bin/Runner.Listener run\$" || true
  sleep 1
else
  echo "No foreground listener process found for $DIR."
fi

if [ -n "$RUNNER_ID" ]; then
  echo "== Deleting the GitHub registration (id=$RUNNER_ID) =="
  _gh_delete "repos/$REPO/actions/runners/$RUNNER_ID" || echo "  (delete call returned non-zero -- verified below regardless)"
fi

if [ -d "$DIR" ]; then
  echo "== Removing install directory: $DIR =="
  rm -rf "$DIR"
fi

echo "== Verifying =="
VERIFY_JSON=$(_gh_get "repos/$REPO/actions/runners" 2>&1) || { echo "ERROR: could not verify: $VERIFY_JSON" >&2; exit 1; }
STILL_THERE=$(echo "$VERIFY_JSON" | "$_PY" -c "
import json, sys
d = json.load(sys.stdin.buffer)  # bytes -> json.load's own UTF-8 decoding, never locale-dependent text-mode stdin
print('yes' if any(r['name'] == '$NAME' for r in d.get('runners', [])) else '')
")
if [ -n "$STILL_THERE" ]; then
  echo "WARNING: '$NAME' still appears in $REPO's runner list." >&2
  exit 1
fi
if [ -d "$DIR" ]; then
  echo "WARNING: $DIR still exists on disk." >&2
  exit 1
fi
echo "OK: '$NAME' is absent from the API and $DIR is gone."
