#!/usr/bin/env bash
# check_hugo_build.sh — Verify Hugo builds succeed for all buildable sites.
#
# Usage:
#     bash scripts/ci/hooks/check_hugo_build.sh              # build all sites
#     bash scripts/ci/hooks/check_hugo_build.sh products.aspose.org  # build one site
#
# Exit codes:
#     0 — All attempted builds succeeded
#     1 — One or more builds failed
#
# Known limitations:
#     - docs/kb/reference: require hextra theme module — SKIP if not cached
#     - A passing build does NOT prove rendering completeness. Hugo silently
#       skips missing frontmatter sections via {{ with }} template guards.
#       Use validate_plugin_structure.py for structural completeness checks.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ALL_SITES="products.aspose.org docs.aspose.org kb.aspose.org reference.aspose.org blog.aspose.org"
REQUESTED_SITES="${1:-$ALL_SITES}"

EXIT=0
PASS=0
FAIL=0
SKIP=0

for site in $REQUESTED_SITES; do
    # Find config by any supported extension (.toml, .yml, .yaml)
    config=""
    for ext in toml yml yaml; do
        if [ -f "$REPO_ROOT/configs/$site.$ext" ]; then
            config="$REPO_ROOT/configs/$site.$ext"
            break
        fi
    done

    # Check config exists
    if [ -z "$config" ]; then
        echo "SKIP: $site (no config at configs/$site.{toml,yml,yaml})"
        SKIP=$((SKIP + 1))
        continue
    fi

    # reference.aspose.org: build per-family segment to isolate failures
    if [ "$site" = "reference.aspose.org" ]; then
        ref_fail=0
        for segment in shared 3d cells email font note page pdf slides tex words; do
            famtmp=$(mktemp -d)
            echo -n "  Building $site [$segment]... "
            if hugo --config "$config" \
                    --renderSegments "$segment" \
                    -d "$famtmp" \
                    --quiet 2>"$famtmp/stderr.txt"; then
                echo "PASS"
            else
                echo "FAIL"
                sed 's/^/    /' "$famtmp/stderr.txt" | head -10
                ref_fail=$((ref_fail + 1))
            fi
            rm -rf "$famtmp"
        done
        if [ $ref_fail -eq 0 ]; then
            echo "Building $site... PASS (11/11 segments)"
            PASS=$((PASS + 1))
        else
            echo "Building $site... FAIL ($ref_fail segment(s) failed)"
            FAIL=$((FAIL + 1))
            EXIT=1
        fi
        continue
    fi

    tmpdir=$(mktemp -d)
    trap "rm -rf '$tmpdir'" EXIT

    echo -n "Building $site... "
    if hugo --config "$config" -d "$tmpdir" --quiet 2>"$tmpdir/stderr.txt"; then
        echo "PASS"
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        echo "  stderr:"
        sed 's/^/    /' "$tmpdir/stderr.txt" | head -20
        FAIL=$((FAIL + 1))
        EXIT=1
    fi

    rm -rf "$tmpdir"
done

echo ""
echo "Hugo Build Summary: $PASS PASS, $FAIL FAIL, $SKIP SKIP"

exit $EXIT
