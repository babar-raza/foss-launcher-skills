#!/bin/bash
# setup-self-hosted-runner.sh -- Register a GitHub Actions self-hosted runner
# against a specific repo, on a fresh clone or a fresh machine. See
# docs/operations/self-hosted-runner-setup.md for the full guide (why two
# separate runner identities exist in this org, label conventions, and the
# troubleshooting section covering a real double-listener incident this
# script's design avoids).
#
# MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE (2026-09-18): written after
# registering two runners by hand via ad hoc shell commands with no reusable
# script or committed guide -- the entire procedure previously existed only
# as gitignored planning notes (reports/plan_state/**) and cross-session
# agent memory, invisible to a fresh clone. This is the durable fix.
#
# What this script does NOT do, and why:
#   - Does not install it as a systemd service. That needs `sudo`, which
#     cannot be supplied non-interactively by an agent session -- confirmed
#     live twice in this repo's history. This script prints the exact
#     follow-up commands instead of attempting them.
#   - Does not choose a target repo or label for you. A runner registered
#     against the wrong repo is a real, previously-shipped incident in this
#     org (a runner meant for the private Aspose/aspose.org repo was
#     registered against the public Aspose/aspose.org-workflows instead,
#     silently, and could never have served its intended jobs) -- both
#     --repo and --labels are required, not defaulted.

set -euo pipefail

RUNNER_VERSION="2.337.0"
WORK_FOLDER="_work"

usage() {
  cat <<'EOF'
Usage: setup-self-hosted-runner.sh --repo <owner/repo> --name <runner-name> --labels <label1,label2,...> [--dir <path>] [--version <x.y.z>]

Required:
  --repo     Target repo, e.g. Aspose/aspose.org or Aspose/aspose.org-workflows.
             This is the ONLY repo the runner will ever serve jobs for -- a
             runner registered against one repo cannot service another's
             queued jobs, no matter what a workflow's runs-on: says.
  --name     Runner display name, shown in the repo's Settings -> Actions ->
             Runners page and in `gh api repos/<repo>/actions/runners`.
  --labels   Comma-separated custom labels (no spaces), e.g. gha-private-native.
             GitHub always adds self-hosted,<OS>,<ARCH> automatically -- do not
             repeat those here.

Optional:
  --dir      Install directory (default: ~/actions-runner-<repo-name-with-dashes>).
  --version  Runner package version to install (default: 2.337.0, the version
             already proven working in this org as of 2026-09-18).

Requires: `gh` CLI authenticated with permission to create a runner
registration token for --repo (repo admin, or an org-level PAT with the
`admin:org`/repo-admin equivalent scope). Fails loudly, not silently, if
that permission is missing.
EOF
}

REPO=""
RUNNER_NAME=""
LABELS=""
INSTALL_DIR=""
TOKEN=""

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --name) RUNNER_NAME="$2"; shift 2 ;;
    --labels) LABELS="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --version) RUNNER_VERSION="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [ -z "$REPO" ] || [ -z "$RUNNER_NAME" ] || [ -z "$LABELS" ]; then
  echo "ERROR: --repo, --name, and --labels are all required." >&2
  usage >&2
  exit 1
fi

if [ -z "$INSTALL_DIR" ]; then
  REPO_SLUG=$(echo "$REPO" | tr '/' '-')
  INSTALL_DIR="$HOME/actions-runner-$REPO_SLUG"
fi

if [ -f "$INSTALL_DIR/.runner" ]; then
  echo "ERROR: $INSTALL_DIR already has a registered runner (.runner exists)." >&2
  echo "  Registered against: $(grep -o '\"gitHubUrl\": *\"[^\"]*\"' "$INSTALL_DIR/.runner" 2>/dev/null || echo unknown)" >&2
  echo "  If you want a second, separate runner, pass a different --dir." >&2
  exit 1
fi

if [ -n "$TOKEN" ]; then
  echo "== Using --token supplied on the command line (skipping gh) =="
  # WSL2 note (confirmed on this dev machine 2026-09-18): `gh` is commonly
  # installed only on the Windows host, not inside the WSL2 distro where the
  # runner itself lives and where sudo/svc.sh must run. Fetch the token from
  # wherever gh IS available and pass it here, e.g. from a Windows shell:
  #   gh api -X POST repos/<owner>/<repo>/actions/runners/registration-token --jq .token
  # then pass the printed value as --token in the WSL2 shell running this script.
elif command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "== Requesting a registration token for $REPO (via gh, found locally) =="
  TOKEN=$(gh api -X POST "repos/$REPO/actions/runners/registration-token" --jq '.token')
  if [ -z "$TOKEN" ]; then
    echo "ERROR: could not obtain a registration token for $REPO." >&2
    echo "  Most likely cause: the authenticated gh identity lacks admin access" >&2
    echo "  to $REPO's Actions runner settings." >&2
    exit 1
  fi
  echo "  OK (token expires in ~1 hour -- config.sh runs immediately below)"
else
  echo "ERROR: gh CLI is not available/authenticated in this shell, and no --token was given." >&2
  echo "  Either install+auth gh here ('gh auth login'), or fetch a token from a" >&2
  echo "  shell where gh IS available and pass it with --token:" >&2
  echo "    gh api -X POST repos/$REPO/actions/runners/registration-token --jq .token" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

TARBALL="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
if [ -f "$TARBALL" ]; then
  echo "== Reusing already-downloaded $TARBALL =="
else
  # Reuse a sibling runner's already-downloaded tarball if one exists on this
  # machine, before hitting the network -- this org has needed >1 runner more
  # than once, and the package is the same ~220MB regardless of target repo.
  REUSE_CANDIDATE=$(find "$HOME" -maxdepth 2 -name "$TARBALL" 2>/dev/null | grep -v "^$INSTALL_DIR/" | head -1 || true)
  if [ -n "$REUSE_CANDIDATE" ]; then
    echo "== Reusing $REUSE_CANDIDATE (found on this machine) =="
    cp "$REUSE_CANDIDATE" "$TARBALL"
  else
    echo "== Downloading actions-runner v${RUNNER_VERSION} =="
    curl -fsSLo "$TARBALL" \
      "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${TARBALL}"
  fi
fi

echo "== Extracting =="
tar xzf "$TARBALL"

echo "== Registering against $REPO as '$RUNNER_NAME' (labels: $LABELS) =="
./config.sh --unattended \
  --url "https://github.com/$REPO" \
  --token "$TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$LABELS" \
  --work "$WORK_FOLDER" \
  --replace

echo ""
echo "== Registered. Verify: =="
echo "  gh api repos/$REPO/actions/runners --jq '.runners[] | select(.name==\"$RUNNER_NAME\")'"
echo "  (expect status: offline until you start the listener below)"
echo ""
echo "== NOT DONE YET: make it persistent =="
echo "This script cannot supply an interactive sudo password. Run these"
echo "yourself in a shell that can prompt for one:"
echo ""
echo "  cd $INSTALL_DIR"
echo "  sudo ./svc.sh install"
echo "  sudo ./svc.sh start"
echo "  sudo ./svc.sh status   # expect: active (running)"
echo ""
echo "Do NOT also run './run.sh' or 'nohup ./run.sh &' once the service is"
echo "installed -- two listeners against the same runner identity collide"
echo "(a real incident this exact script's guide documents: see"
echo "docs/operations/self-hosted-runner-setup.md, 'Troubleshooting')."
echo ""
echo "For a quick, non-persistent smoke test before installing the service,"
echo "you may run 'nohup ./run.sh &' temporarily -- but kill it"
echo "(pkill -f 'Runner.Listener run \$') before the svc.sh install step above."
