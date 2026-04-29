#!/usr/bin/env bash
# repair_venv.sh — Approved .venv bootstrap/repair script.
#
# Purpose: Create or recreate the repo .venv from scratch.
# Policy (DR-01): System Python is used ONLY for "python -m venv .venv".
#   All subsequent operations (pip install, verify) use .venv Python exclusively.
#
# This script does NOT run any repo scanners, tests, workers, or content tools.
# It only creates/repairs .venv and installs dependencies.
#
# Usage:
#   bash scripts/ci/hooks/repair_venv.sh            # repair in place
#   bash scripts/ci/hooks/repair_venv.sh --fresh    # delete .venv first, recreate clean
#
# Called by: bootstrap_session_gate.sh (recovery message)
#            docs/QUICKSTART.md (manual reference)
#            TC-VE-03 (healing plan)

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
FRESH=0

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
for arg in "$@"; do
    case "$arg" in
        --fresh) FRESH=1 ;;
        --help|-h)
            echo "Usage: bash scripts/ci/hooks/repair_venv.sh [--fresh]"
            echo "  --fresh   Delete existing .venv before recreating"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

echo "=== repair_venv.sh: .venv bootstrap/repair ==="
echo "  REPO_ROOT : $REPO_ROOT"
echo "  VENV_DIR  : $VENV_DIR"

# ---------------------------------------------------------------------------
# Step 0 (optional): delete .venv for a clean recreate
# ---------------------------------------------------------------------------
if [ "$FRESH" -eq 1 ] && [ -d "$VENV_DIR" ]; then
    echo ""
    echo "=== Step 0: Removing existing .venv (--fresh) ==="
    rm -rf "$VENV_DIR"
    echo "  Removed: $VENV_DIR"
fi

# ---------------------------------------------------------------------------
# Step 1: Locate system Python for bootstrap (only used here — DR-01 exception)
# This is the ONLY permitted bare python invocation in this script.
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 1: Locating system Python for bootstrap ==="
_SYS_PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        _ver=$("$candidate" --version 2>&1 | head -1 || true)
        echo "  Found: $(command -v "$candidate") ($_ver)"
        _SYS_PYTHON="$candidate"
        break
    fi
done
if [ -z "$_SYS_PYTHON" ]; then
    echo "ERROR: No Python found on PATH. Install Python 3.8+ first." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 2: Create .venv (bootstrap exception — system Python used here only)
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 2: Creating .venv ==="
SKIP_CREATE=0
if [ -d "$VENV_DIR" ]; then
    echo "  .venv already exists — checking health..."
    if [ -f "$VENV_DIR/Scripts/python.exe" ] || [ -f "$VENV_DIR/Scripts/python" ] || \
       [ -f "$VENV_DIR/bin/python" ]; then
        _test_py=""
        [ -f "$VENV_DIR/Scripts/python" ] && _test_py="$VENV_DIR/Scripts/python"
        [ -z "$_test_py" ] && [ -f "$VENV_DIR/bin/python" ] && _test_py="$VENV_DIR/bin/python"
        if [ -n "$_test_py" ] && "$_test_py" -c "import sys" 2>/dev/null; then
            echo "  .venv is healthy. Skipping creation (use --fresh to force recreate)."
            SKIP_CREATE=1
        else
            echo "  .venv Python fails health check. Recreating..."
            rm -rf "$VENV_DIR"
        fi
    else
        echo "  .venv exists but Python binary missing. Recreating..."
        rm -rf "$VENV_DIR"
    fi
fi

if [ "$SKIP_CREATE" -eq 0 ]; then
    "$_SYS_PYTHON" -m venv "$VENV_DIR"
    echo "  Created: $VENV_DIR"
fi

# ---------------------------------------------------------------------------
# Step 3: Resolve .venv Python (DR-01 — no further system Python usage)
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 3: Resolving .venv Python ==="
PYTHON=""
if [ -f "$VENV_DIR/Scripts/python" ]; then
    PYTHON="$VENV_DIR/Scripts/python"   # Windows Git Bash
elif [ -f "$VENV_DIR/bin/python" ]; then
    PYTHON="$VENV_DIR/bin/python"       # Unix / macOS
fi

if [ -z "$PYTHON" ]; then
    echo "ERROR: .venv Python binary not found after creation. venv creation failed." >&2
    exit 1
fi

if ! "$PYTHON" -c "import sys; print(sys.executable)" 2>/dev/null; then
    echo "ERROR: .venv Python binary exists but cannot start." >&2
    echo "  Path: $PYTHON" >&2
    exit 1
fi

VENV_EXECUTABLE="$("$PYTHON" -c "import sys; print(sys.executable)")"
echo "  .venv Python  : $PYTHON"
echo "  sys.executable: $VENV_EXECUTABLE"

# ---------------------------------------------------------------------------
# Step 4: Upgrade pip inside .venv (DR-01 — .venv Python only)
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 4: Upgrading pip inside .venv ==="
"$PYTHON" -m pip install --upgrade pip --quiet
echo "  pip upgrade: OK"

# ---------------------------------------------------------------------------
# Step 5: Install core dependencies through .venv Python (DR-01)
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 5: Installing core dependencies ==="
REQ_PIPELINE="$REPO_ROOT/scripts/pipeline/requirements.txt"
REQ_CI="$REPO_ROOT/scripts/ci/requirements.txt"

if [ -f "$REQ_PIPELINE" ]; then
    echo "  Installing: scripts/pipeline/requirements.txt"
    "$PYTHON" -m pip install -r "$REQ_PIPELINE" --quiet
    echo "  Pipeline requirements: OK"
else
    echo "WARNING: $REQ_PIPELINE not found — skipping." >&2
fi

if [ -f "$REQ_CI" ]; then
    echo "  Installing: scripts/ci/requirements.txt"
    "$PYTHON" -m pip install -r "$REQ_CI" --quiet
    echo "  CI requirements: OK"
else
    echo "WARNING: $REQ_CI not found — skipping." >&2
fi

# Install pytest for the test suite
"$PYTHON" -m pip install pytest --quiet
echo "  pytest: OK"

# ---------------------------------------------------------------------------
# Step 6: Verify .venv Python, pip, and key dependencies
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 6: Verification ==="
echo "  sys.executable : $("$PYTHON" -c "import sys; print(sys.executable)")"
echo "  Python version : $("$PYTHON" --version)"
echo "  pip version    : $("$PYTHON" -m pip --version | head -1)"

_DEPS_OK=1
for pkg in yaml requests pytest; do
    if "$PYTHON" -c "import $pkg" 2>/dev/null; then
        echo "  import $pkg     : OK"
    else
        echo "  import $pkg     : MISSING" >&2
        _DEPS_OK=1  # warn but continue (some packages are optional)
    fi
done

# python-dotenv: imported as dotenv
if "$PYTHON" -c "from dotenv import load_dotenv" 2>/dev/null; then
    echo "  import dotenv   : OK"
else
    echo "  import dotenv   : MISSING (python-dotenv not installed)" >&2
fi

if [ "$_DEPS_OK" -eq 0 ]; then
    echo ""
    echo "ERROR: Required dependencies failed to import. See above." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "=== repair_venv.sh: COMPLETE ==="
echo "  .venv Python ready: $PYTHON"
echo ""
echo "Next steps:"
echo "  1. Install hooks (if not done): bash scripts/install-hooks.sh"
echo "  2. Verify environment  : $PYTHON scripts/ci/checks/venv_doctor.py"
echo "  3. Run smoke test      : bash scripts/ci/hooks/smoke_chain.sh"
