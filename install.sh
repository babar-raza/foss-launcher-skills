#!/usr/bin/env bash
# install.sh — Install foss-launcher-skills into a target content repo.
#
# Usage:
#   ./install.sh /path/to/target-repo                  # Embedded mode (default)
#   ./install.sh --standalone /path/to/target-repo      # Standalone mode
#
# Embedded mode: copies scripts and skills into the target repo.
# Standalone mode: keeps skills here, configures content_repo to point at target.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STANDALONE=false

# Parse flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --standalone)
            STANDALONE=true
            shift
            ;;
        *)
            break
            ;;
    esac
done

if [ $# -lt 1 ]; then
    echo "Usage: $0 [--standalone] /path/to/target-repo"
    exit 1
fi

TARGET="$(cd "$1" && pwd)"

if [ ! -d "$TARGET" ]; then
    echo "Error: target directory does not exist: $TARGET"
    exit 1
fi

echo "=== foss-launcher-skills installer ==="
echo "Source: $SCRIPT_DIR"
echo "Target: $TARGET"
echo "Mode:   $([ "$STANDALONE" = true ] && echo 'standalone' || echo 'embedded')"
echo ""

if [ "$STANDALONE" = true ]; then
    # --- Standalone mode ---
    # Skills stay in this project, set content_repo to point at target.
    echo "--- Configuring standalone mode ---"

    # Update content_repo in config.yaml
    if [ -f "$SCRIPT_DIR/config.yaml" ]; then
        sed -i.bak "s|^content_repo:.*|content_repo: \"$TARGET\"|" "$SCRIPT_DIR/config.yaml"
        rm -f "$SCRIPT_DIR/config.yaml.bak"
        echo "Set content_repo to: $TARGET"
    fi

    # Write a link file in target so it knows where skills live
    echo "$SCRIPT_DIR" > "$TARGET/.skills-link"
    date -u +"%Y-%m-%dT%H:%M:%SZ" >> "$TARGET/.skills-link"
    echo "Created .skills-link in target."

    # Distribute skills locally (for this project's agent directories)
    echo ""
    echo "--- Distributing skills ---"
    python3 "$SCRIPT_DIR/tools/distribute.py" "$SCRIPT_DIR"

else
    # --- Embedded mode (original behavior) ---
    # 1. Copy scripts package tree
    echo "--- Copying scripts/ ---"
    mkdir -p "$TARGET/scripts"
    cp -R "$SCRIPT_DIR/scripts/." "$TARGET/scripts/"
    find "$TARGET/scripts" -type d -name "__pycache__" -prune -exec rm -rf {} +
    find "$TARGET/scripts" -type f -name "*.pyc" -delete
    echo "Done."

    # 2. Copy configs/
    echo ""
    echo "--- Copying configs/ ---"
    mkdir -p "$TARGET/configs"
    cp "$SCRIPT_DIR/configs/"*.yaml "$TARGET/configs/" 2>/dev/null || true
    echo "Done."

    # 3. Copy config.yaml with content_repo set to current dir
    echo ""
    echo "--- Copying config.yaml ---"
    cp "$SCRIPT_DIR/config.yaml" "$TARGET/config.yaml"
    sed -i.bak 's|^content_repo:.*|content_repo: "."|' "$TARGET/config.yaml"
    rm -f "$TARGET/config.yaml.bak"
    echo "Done."

    # 4. Distribute skills to agent directories
    echo ""
    echo "--- Distributing skills ---"
    python3 "$SCRIPT_DIR/tools/distribute.py" "$TARGET"

    # 5. Copy AGENTS.template.md if AGENTS.md doesn't exist
    if [ ! -f "$TARGET/AGENTS.md" ]; then
        echo ""
        echo "--- Creating AGENTS.md from template ---"
        cp "$SCRIPT_DIR/AGENTS.template.md" "$TARGET/AGENTS.md"
        echo "Created AGENTS.md (review and customize for your project)."
    else
        echo ""
        echo "AGENTS.md already exists in target — skipping (see AGENTS.template.md for reference)."
    fi

    # 6. Write version marker
    echo "$SCRIPT_DIR" > "$TARGET/.skills-source"
    date -u +"%Y-%m-%dT%H:%M:%SZ" >> "$TARGET/.skills-source"
fi

echo ""
echo "=== Installation complete ==="
echo "Installed to: $TARGET"
echo ""
echo "Next steps:"
echo "  1. pip install -r scripts/requirements.txt"
echo "  2. Review AGENTS.md and customize for your project"
echo "  3. Run your first skill: /repo-scout {family} {platform} {repo-path}"
echo "  4. Then: /truth-merge {family} {platform}"
echo "  5. Scan existing content: /corpus-scan {family} {platform} docs"
