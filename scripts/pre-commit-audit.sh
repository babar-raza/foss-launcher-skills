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
# Step 4b: Provenance protection — warn when auto_updatable: false pages are modified
# ---------------------------------------------------------------------------
# Detects staged modifications to pages that have auto_updatable: false in their
# committed (HEAD) provenance block.  These pages contain manually curated content
# that should not be overwritten by automated processes.
# Currently warning-only; will be promoted to blocking after validation period.
python scripts/ci/check_protected_overwrites.py --check-staged
_prot_status=$?
if [ $_prot_status -eq 2 ]; then
    echo ""
    echo "WARNING: Protected page(s) modified (auto_updatable: false). See above."
    echo "  This is currently a warning. It will become blocking in a future release."
    # Not blocking yet: exit would be here when promoted
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
    # Compare HEAD's content_hash against current computed hash to detect body
    # changes.  We read HEAD (not the working copy) because Step 5 already
    # normalized the working copy's stored hash — comparing stored vs computed
    # on the working copy would always match after Step 5.
    # Pass file path via sys.argv to avoid shell quoting issues.
    head_info=$(git show HEAD:"$staged_file" 2>/dev/null | python -c "
import sys, yaml, re
text = sys.stdin.read()
m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
if m:
    try:
        fm = yaml.safe_load(m.group(1))
        prov = (fm or {}).get('provenance') or {}
        h = prov.get('content_hash', '')
        mech = prov.get('last_mechanism', '')
        print(f'{h}|{mech}')
    except: pass
" 2>/dev/null)
    [ -z "$head_info" ] && continue
    head_hash="${head_info%%|*}"
    head_mech="${head_info##*|}"
    # Compute current body hash and read current mechanism
    current_info=$(python -c "
import sys; sys.path.insert(0, 'scripts/pipeline')
from provenance import read_provenance, compute_content_hash
from pathlib import Path
p = Path(sys.argv[1])
computed = compute_content_hash(p)
prov = read_provenance(p)
mech = prov.get('last_mechanism', '') if prov else ''
print(f'{computed}|{mech}')
" "$staged_file" 2>/dev/null)
    [ -z "$current_info" ] && continue
    current_hash="${current_info%%|*}"
    current_mech="${current_info##*|}"
    # If body hash changed (HEAD hash != current computed hash) but mechanism
    # was not updated, warn about undeclared content edit.
    if [ -n "$head_hash" ] && [ "$head_hash" != "$current_hash" ] && [ "$current_mech" = "$head_mech" ]; then
        echo "WARNING: content changed but last_mechanism not updated in $staged_file"
        echo "  Consider calling update_mechanism() after content-modifying writes."
    fi
done

# ---------------------------------------------------------------------------
# Step 7: Python file placement check (staged .py files only)
# ---------------------------------------------------------------------------
# Blocks commits of .py files in forbidden locations (repo root, scripts/ root,
# scripts/one-shot/). Uses --check-staged so only staged files are examined —
# existing legacy files in the working tree don't trigger false positives.
# See AGENTS.md §4b for placement rules.
if git diff --cached --name-only --diff-filter=ACM | grep -q '\.py$'; then
    python scripts/ci/check_python_placement.py --check-staged
    if [ $? -ne 0 ]; then
        echo ""
        echo "BLOCKED: Staged Python file(s) are in forbidden locations (see above)."
        echo "  Correct locations:"
        echo "    scripts/maintenance/  (operator one-off; add to scripts/maintenance/registry.yaml)"
        echo "    scripts/pipeline/     (operational; follow PIPELINE.md New File Protocol)"
        echo "    scripts/ci/           (CI-only validator)"
        echo "  See AGENTS.md §4b for the full decision tree."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 7b: Venv enforcement on staged skill files
# ---------------------------------------------------------------------------
# Blocks commits where skill bash blocks contain bare `python`, `pip install --user`,
# or PYTHONPATH=$USER_SITE.  Only checks staged skill files to avoid false positives
# on unmodified legacy files.  See AGENTS.md §virtual-environment.
if git diff --cached --name-only --diff-filter=ACM | grep -qE '^(skills/|\.agents/skills/|\.kilocode/skills/|\.claude/commands/|\.claude/settings\.(json|local\.json))'; then
    # Cross-platform .venv detection (same pattern as Step 9)
    if [ -f ".venv/Scripts/python" ]; then
        _venv_py=".venv/Scripts/python"
    elif [ -f ".venv/bin/python" ]; then
        _venv_py=".venv/bin/python"
    else
        echo "[Step 7b] WARN: .venv not found — skipping venv enforcement check."
        _venv_py=""
    fi
    if [ -n "$_venv_py" ]; then
        "$_venv_py" scripts/ci/enforce_venv_python.py --check
        if [ $? -ne 0 ]; then
            echo ""
            echo "BLOCKED: Staged file(s) contain bare python/pip or --user violations."
            echo "  Auto-fix: .venv/Scripts/python scripts/ci/enforce_venv_python.py --fix"
            echo "  DENY violations (--user, USER_SITE) require manual skill redesign."
            exit 1
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Step 8: Session-ledger enforcement (content files only)
# ---------------------------------------------------------------------------
# When an ACTIVE session pointer exists, verify that every staged content .md
# file appears in the session ledger's touched_files.  This converts the
# session ledger from an advisory system to a blocking enforcement layer.
# Bypass: SKIP_SESSION_CHECK=1 git commit ...
# Non-content files (scripts, configs, skills, etc.) are exempt — the session
# ledger tracks content authorship, not infrastructure changes.
if [ -f "reports/session-state/ACTIVE" ]; then
    # Bypass via environment variable (reliable across all git commit modes).
    if [ "${SKIP_SESSION_CHECK:-0}" != "1" ]; then
        _staged_content=$(git diff --cached --name-only --diff-filter=ACM | grep '^content/.*\.md$')
        if [ -n "$_staged_content" ]; then
            _session_check_result=$(echo "$_staged_content" | \
                python scripts/pipeline/session_ledger.py check-staged 2>&1)
            _session_check_status=$?
            if [ $_session_check_status -ne 0 ]; then
                echo ""
                echo "$_session_check_result"
                echo ""
                echo "BLOCKED: Staged content files not found in session ledger."
                echo "  Options:"
                echo "    1. Record files: session_ledger.py record --file <path> --action modified"
                echo "    2. Adopt files:  session_ledger.py adopt --files <path> [<path> ...]"
                echo "    3. If operator-authorized, see docs/OPERATOR_BYPASSES.md"
                echo ""
                # Include full diagnostics (non-fatal if diagnose itself fails).
                python scripts/pipeline/session_ledger.py diagnose 2>&1 || true
                exit 1
            fi
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Step 9: Onboarding integrity — runs ONLY when an operator doc is staged.
# Skipped entirely for all other commits (< 1ms gate check, ~2s when triggered).
# Enforces: AGENTS.md link, CLAUDE.md ref, relative links, venv prefix, structure.
# Primary gate: CI job 'onboarding-integrity' in ci-eval-consistency.yml (TC-08).
# This is a local redundancy layer — catches issues before push.
# Cross-platform: auto-detects .venv/Scripts/python (Windows) vs .venv/bin/python (Unix).
# Graceful: warns (does not block) if .venv is absent (pre-bootstrap state).
# ---------------------------------------------------------------------------
STAGED_FILES="$(git diff --cached --name-only)"
ONBOARDING_PATTERN='^(AGENTS\.md|CLAUDE\.md|RUNBOOK\.md|OPERATOR_GUIDE\.md|docs/QUICKSTART\.md|skills/getting-started\.md|skills/session-start\.md)$'

if echo "$STAGED_FILES" | grep -qE "$ONBOARDING_PATTERN"; then
  echo "[Step 9] Operator doc staged — running onboarding integrity check..."

  # Cross-platform .venv detection
  if [ -f ".venv/Scripts/python" ]; then
    venv_python=".venv/Scripts/python"       # Windows Git Bash / MINGW
  elif [ -f ".venv/bin/python" ]; then
    venv_python=".venv/bin/python"            # macOS / Linux
  else
    echo "[Step 9] WARN: .venv not found — skipping onboarding integrity check."
    echo "         Run the bootstrap step in docs/QUICKSTART.md §2 to enable this gate."
    venv_python=""
  fi

  if [ -n "$venv_python" ]; then
    if ! "$venv_python" scripts/ci/check_onboarding_integrity.py; then
      echo "[Step 9] FAIL: onboarding integrity check failed. Fix issues above before committing."
      exit 1
    fi
    echo "[Step 9] PASS"
  fi
fi


# ---------------------------------------------------------------------------
# Step 10: graded_at-only reversion
# Auto-revert staged .md files where the only diff from HEAD is graded_at:.
# Calls check_graded_at_only.py (which uses the venv python -- not bare python).
# Blocking (exit 1): PARSE_FAILURE signals an unreadable diff (Case D).
# Non-blocking: Case A files are reverted and commit continues without them.
# ---------------------------------------------------------------------------
if [ ${#changed[@]} -gt 0 ]; then
    # Cross-platform .venv detection
    if [ -f ".venv/Scripts/python" ]; then
        _ga_python=".venv/Scripts/python"
    elif [ -f ".venv/bin/python" ]; then
        _ga_python=".venv/bin/python"
    else
        _ga_python=""
    fi

    if [ -n "$_ga_python" ]; then
        _tmpfile10=$(mktemp /tmp/graded-at-only-XXXXXX.txt 2>/dev/null || mktemp)
        printf '%s\n' "${changed[@]}" > "$_tmpfile10"
        _ga_stderr=$(mktemp /tmp/graded-at-err-XXXXXX.txt 2>/dev/null || mktemp)
        revert_candidates=()
        while IFS= read -r _line; do revert_candidates+=("$_line"); done < <(
            "$_ga_python" scripts/pipeline/check_graded_at_only.py \
                --files-from "$_tmpfile10" 2>"$_ga_stderr"
        )
        rm -f "$_tmpfile10"
        if grep -q '^PARSE_FAILURE:' "$_ga_stderr" 2>/dev/null; then
            echo "[Step 10] ERROR: graded_at-only check had parse failures:"
            grep '^PARSE_FAILURE:' "$_ga_stderr" | sed 's/^PARSE_FAILURE:/  /'
            rm -f "$_ga_stderr"
            exit 1
        fi
        rm -f "$_ga_stderr"
        if [ ${#revert_candidates[@]} -gt 0 ]; then
            echo "[Step 10] Auto-reverting graded_at-only staged files:"
            for _f in "${revert_candidates[@]}"; do
                echo "  REVERT $_f"
                git restore --staged "$_f" 2>/dev/null || git reset HEAD -- "$_f" 2>/dev/null
                git restore "$_f" 2>/dev/null || git checkout HEAD -- "$_f" 2>/dev/null
            done
            echo "[Step 10] Reverted ${#revert_candidates[@]} graded_at-only file(s)."
        fi
    fi
fi

exit 0
