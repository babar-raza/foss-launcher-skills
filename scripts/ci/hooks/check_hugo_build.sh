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

    # reference.aspose.org: committed segments are family-agnostic (shared, sitemap);
    # per-family/platform segments are synthesized by the deploy workflow from the
    # content tree (plan zesty-whistling-hopper). Validate the committed segments plus
    # one synthesized shard so the synthesis mechanism itself is exercised.
    # NOTE: search must be disabled here — this repo is a FULL checkout, and the
    # FlexSearch data template overflows on the whole-site page graph (slice bounds
    # error). CI shard jobs use sparse checkouts, where search is safe and stays on.
    if [ "$site" = "reference.aspose.org" ]; then
        ref_fail=0
        for segment in shared sitemap; do
            famtmp=$(mktemp -d)
            echo -n "  Building $site [$segment]... "
            if HUGO_PARAMS_SEARCH_ENABLE=false hugo --config "$config" \
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
        # Synthesized shard: smallest {family}/{platform} by page count (fast, exercises
        # the same append-to-config-copy mechanism the deploy workflow uses).
        shard=$(find "$REPO_ROOT/content/reference.aspose.org/en" -mindepth 2 -maxdepth 2 -type d \
            | while read -r d; do printf '%s %s\n' "$(find "$d" -name '*.md' | wc -l)" "${d#"$REPO_ROOT/content/reference.aspose.org/en/"}"; done \
            | sort -n | head -1 | cut -d' ' -f2)
        fam=${shard%%/*}; plat=${shard##*/}
        famtmp=$(mktemp -d)
        # Hugo infers config format from the file extension — an extensionless
        # mktemp file fails with "not a valid configuration format".
        jobcfg="$famtmp/job.toml"
        cp "$config" "$jobcfg"
        printf '\n[[segments.target.includes]]\n  path = "{/%s,/%s/%s,/%s/%s/**}"\n' \
            "$fam" "$fam" "$plat" "$fam" "$plat" >> "$jobcfg"
        echo -n "  Building $site [synthesized $fam/$plat]... "
        if HUGO_PARAMS_SEARCH_ENABLE=false hugo --config "$jobcfg" \
                --renderSegments "target" \
                -d "$famtmp" \
                --quiet 2>"$famtmp/stderr.txt"; then
            # Guard: the shard must render its own family and nothing else
            rendered=$(find "$famtmp" -name 'index.html' | wc -l)
            leaked=$(find "$famtmp" -name 'index.html' \
                | sed "s#^$famtmp/##" \
                | awk -F/ '{ seg = ($1 ~ /^[a-z]{2}(-[a-z]+)?$/ && NF > 1) ? $2 : $1; print seg }' \
                | sort -u | grep -vx "$fam" || true)
            if [ "$rendered" -eq 0 ] || [ -n "$leaked" ]; then
                echo "FAIL (rendered=$rendered leaked='$leaked')"
                ref_fail=$((ref_fail + 1))
            else
                echo "PASS"
            fi
        else
            echo "FAIL"
            sed 's/^/    /' "$famtmp/stderr.txt" | head -10
            ref_fail=$((ref_fail + 1))
        fi
        rm -rf "$famtmp" "$jobcfg"
        if [ $ref_fail -eq 0 ]; then
            echo "Building $site... PASS (shared + sitemap + synthesized shard)"
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
