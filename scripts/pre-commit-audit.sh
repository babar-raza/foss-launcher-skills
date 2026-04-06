#!/bin/bash
# Pre-commit hook: enforce path guard and verify API accuracy in staged content files.
# Install: cp scripts/pre-commit-audit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

# ---------------------------------------------------------------------------
# Step 0: reports/ boundary — local-only artifacts must never be committed
# ---------------------------------------------------------------------------
# reports/ is gitignored and is a strict local-only boundary. Any staged
# addition or modification under reports/ is an error (usually caused by
# git add -f bypassing .gitignore). Deletions (git rm --cached) are allowed
# so that the cleanup commit can untrack already-committed files.
staged_reports=$(git diff --cached --name-only --diff-filter=ACM | grep '^reports/')
if [ -n "$staged_reports" ]; then
    echo "ERROR: Staged files under reports/ violate the local-only artifact boundary:"
    echo "$staged_reports"
    echo ""
    echo "reports/ is gitignored. Do not use 'git add -f' to stage files under reports/."
    echo "Override tokens are validated from disk (reports/overrides/pending/) — do not stage them."
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: Forbidden-path enforcement
# ---------------------------------------------------------------------------
# Check all staged paths in a single Python invocation using --stdin batch mode.
# This avoids one Python startup per file (~120ms/file) which was ~56 min for
# large commits.  The --stdin flag reads one path per line and prints only DENY
# paths to stdout, exit 0 if all ALLOW, exit 2 if any DENY.
forbidden_staged=()
while IFS= read -r _line; do forbidden_staged+=("$_line"); done < <(
    git diff --cached --name-only --diff-filter=ACM | \
        python scripts/pipeline/path_guard.py --stdin | tr -d '\r'
)

if [ ${#forbidden_staged[@]} -gt 0 ]; then
    forbidden_violation=0
    for staged_file in "${forbidden_staged[@]}"; do
        echo "Forbidden path staged: $staged_file"
        python scripts/pipeline/override_manager.py validate-for-path "$staged_file" 2>&1
        if [ $? -ne 0 ]; then
            forbidden_violation=1
        fi
    done
    if [ $forbidden_violation -ne 0 ]; then
        echo ""
        echo "BLOCKED: One or more staged files are in forbidden paths and have no override token."
        echo "  Create an override token before committing:"
        echo "    python scripts/pipeline/override_manager.py create \\"
        echo "      --paths <path> --reason '...' --plan '...'"
        echo "  The token is auto-validated from reports/overrides/pending/ — do NOT stage it."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 2: API accuracy audit on staged English content files
# ---------------------------------------------------------------------------
# Locale files (/ar/, /fr/, /de/, etc.) are translator output and are not
# subject to API accuracy audit — only English source pages are checked.
changed=()
while IFS= read -r _line; do changed+=("$_line"); done < <(
    git diff --cached --name-only --diff-filter=ACM \
        | grep '^content/.*\.md$' \
        | grep '/en/'
)
[ ${#changed[@]} -eq 0 ] && exit 0

echo "Running content API audit on staged files (${#changed[@]} English pages)..."
# Use --files-from to avoid OS argument-list-too-long errors on large commits.
_tmpfile=$(mktemp /tmp/audit-files-XXXXXX.txt 2>/dev/null || mktemp)
printf '%s\n' "${changed[@]}" > "$_tmpfile"
python scripts/pipeline/audit.py --files-from "$_tmpfile" --fail-fast
status=$?
rm -f "$_tmpfile"

if [ $status -ne 0 ]; then
    echo ""
    echo "BLOCKED: Content has API accuracy failures."
    echo "Fix the issues above, then re-stage and commit."
    exit 1
fi

echo "Content API audit passed."

# ---------------------------------------------------------------------------
# Step 3: Check plugin_platform canonical values for products pages
# ---------------------------------------------------------------------------
if git diff --cached --name-only --diff-filter=ACM | grep -q '^content/products\.aspose\.org/'; then
    echo "Running plugin_platform canonical-value check..."
    python scripts/ci/check_plugin_platform.py
    if [ $? -ne 0 ]; then
        echo ""
        echo "BLOCKED: plugin_platform has non-canonical values (see AGENTS.md Section 3b)."
        echo "Fix the values above, then re-stage and commit."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 4: Provenance frontmatter validation on staged English pages
# ---------------------------------------------------------------------------
# Check 2b (validate_frontmatter.py): warn when a non-empty provenance block is
# present but content_origin is absent. This prevents new pages from entering the
# corpus without a content_origin field. Warnings are non-blocking (the validator
# exits 0 on warnings) but are visible in hook output to the committer.
# Hard errors (e.g. malformed frontmatter) are blocking (exit 1).
if [ ${#changed[@]} -gt 0 ]; then
    _tmpfile3=$(mktemp /tmp/prov-files-XXXXXX.txt 2>/dev/null || mktemp)
    printf '%s\n' "${changed[@]}" > "$_tmpfile3"
    python scripts/pipeline/validate_frontmatter.py --files-from "$_tmpfile3"
    prov_status=$?
    rm -f "$_tmpfile3"
    if [ $prov_status -ne 0 ]; then
        echo ""
        echo "BLOCKED: Frontmatter has hard errors (see above). Fix before committing."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 5: content_hash normalization for staged English content files
# ---------------------------------------------------------------------------
# Computes the current body hash for each staged English .md file and updates
# the stored content_hash in the provenance block if it differs.  Re-stages
# modified files so the commit includes the corrected hash.
# Non-blocking: hash normalization is mechanical (analogous to auto-formatting).
# Note: this may add provenance-only frontmatter changes to the staged diff.
# Scope: all content/*/en/ sites.  websites.aspose.org hub pages (_index.md)
# lack provenance by design — they are navigation pages outside the content
# quality pipeline (no grade, evidence, or staleness tracking expected).
if [ ${#changed[@]} -gt 0 ]; then
    _tmpfile5=$(mktemp /tmp/hash-norm-XXXXXX.txt 2>/dev/null || mktemp)
    printf '%s\n' "${changed[@]}" > "$_tmpfile5"
    python scripts/pipeline/provenance_normalize_hash.py \
        --apply --files-from "$_tmpfile5" --auto-stage 2>&1
    rm -f "$_tmpfile5"
    # Non-blocking: normalization errors are logged but do not block the commit.
fi

# ---------------------------------------------------------------------------
# Step 6: last_mechanism staleness warning
# ---------------------------------------------------------------------------
# For each staged file where the body changed (hash was stale), check whether
# last_mechanism was also updated.  Warns if the mechanism appears unchanged
# despite body changes — indicates an undeclared content edit.
# Non-blocking: warning only.  Will be upgraded to hard error after skill
# contracts (S-20, S-21, S-26) include provenance update steps.
for staged_file in "${changed[@]}"; do
    if [ ! -f "$staged_file" ]; then continue; fi
    # Read current last_mechanism from the working copy
    # Pass file path via sys.argv to avoid shell quoting issues with
    # single quotes or special characters in file paths.
    current_mech=$(python -c "
import sys; sys.path.insert(0, 'scripts/pipeline')
from provenance import read_provenance, compute_content_hash
from pathlib import Path
p = Path(sys.argv[1])
prov = read_provenance(p)
if prov:
    stored = prov.get('content_hash', '')
    computed = compute_content_hash(p)
    if stored and stored == computed:
        sys.exit(0)  # hash matches — no body change
    mech = prov.get('last_mechanism', '')
    print(mech)
" "$staged_file" 2>/dev/null)
    if [ -z "$current_mech" ]; then continue; fi
    # Compare with HEAD version
    head_mech=$(git show HEAD:"$staged_file" 2>/dev/null | python -c "
import sys, yaml, re
text = sys.stdin.read()
m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
if m:
    try:
        fm = yaml.safe_load(m.group(1))
        prov = (fm or {}).get('provenance') or {}
        print(prov.get('last_mechanism', ''))
    except: pass
" 2>/dev/null)
    if [ -n "$head_mech" ] && [ "$current_mech" = "$head_mech" ]; then
        echo "WARNING: content changed but last_mechanism not updated in $staged_file"
        echo "  Consider calling update_mechanism() after content-modifying writes."
    fi
done

exit 0
