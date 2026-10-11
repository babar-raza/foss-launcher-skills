#!/usr/bin/env bash
# Bootstrap Tier 2 API surface vectors for all launched products.
#
# Populates knowledge/_vectors/{family}/{platform}/api.vectors.json
# for each product that has merged/api_surface.json.
#
# Usage:
#   bash scripts/pipeline/commands/knowledge/bootstrap_vectors.sh
#
# Prerequisites:
#   - PROFESSIONALIZE_API_KEY env var set (or Ollama running locally)
#   - .venv activated or available at .venv/Scripts/python
#
# TC-GAPEVAL-001: Bootstrap Tier 2 Vector Search for Gap-Eval

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
EMBED_SCRIPT="$REPO_ROOT/scripts/pipeline/commands/knowledge/embed.py"
PYTHON="${PYTHON:-$REPO_ROOT/.venv/Scripts/python}"

if [ ! -f "$EMBED_SCRIPT" ]; then
    echo "ERROR: embed.py not found at $EMBED_SCRIPT" >&2
    exit 1
fi

echo "=== Bootstrap Tier 2 API Surface Vectors ==="
echo "Repo root: $REPO_ROOT"
echo "Python:    $PYTHON"
echo ""

cd "$REPO_ROOT"
export PYTHONPATH="scripts/pipeline"

# Run gap-index for all discovered products
"$PYTHON" "$EMBED_SCRIPT" gap-index all "$@"

echo ""
echo "=== Vector population complete ==="
echo "Listing populated vectors:"
find knowledge/_vectors -name "api.vectors.json" 2>/dev/null | sort || echo "(none found)"
