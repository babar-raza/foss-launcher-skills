#!/bin/bash
# Pre-commit hook: enforce path guard and verify API accuracy in staged content files.
# Install: cp scripts/pre-commit-audit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

# ---------------------------------------------------------------------------
# Shell preflight: validate execution environment (Windows-only, warn mode)
# Phase 4: prepend _SHELL_CHECK_MODE=block before this source line to harden
# ---------------------------------------------------------------------------
# shellcheck source=scripts/ci/hooks/check_shell_bash.sh
_REPO_ROOT_SHELL="$(git rev-parse --show-toplevel)"
source "${_REPO_ROOT_SHELL}/scripts/ci/hooks/check_shell_bash.sh" || exit 1
unset _REPO_ROOT_SHELL

# ---------------------------------------------------------------------------
# DR-01: Central .venv Python resolver — no system Python fallback.
# All Python-based governance checks (steps 1-8, step 10) use $_HOOK_PYTHON.
# When .venv is absent, Python-based steps skip with a diagnostic message
# (consistent with the skip-with-warning policy in steps 7b, 9, 11).
# ---------------------------------------------------------------------------
if [ -f ".venv/Scripts/python" ]; then
    _HOOK_PYTHON=".venv/Scripts/python"
elif [ -f ".venv/bin/python" ]; then
    _HOOK_PYTHON=".venv/bin/python"
else
    echo "[pre-commit] WARN: .venv not found — Python-based governance checks will be skipped." >&2
    echo "  Recovery: bash scripts/ci/hooks/repair_venv.sh" >&2
    _HOOK_PYTHON=""
fi

# ---------------------------------------------------------------------------
# Pre-commit summary mode (TC-DS-02): step tracking and timing
# ---------------------------------------------------------------------------
declare -a _PC_NAMES=()
declare -a _PC_RESULTS=()
declare -a _PC_TIMES=()
_PC_START_EPOCH=""

_pc_now() {
    # Portable epoch seconds (bash 4+ EPOCHSECONDS or date fallback)
    if [ -n "${EPOCHSECONDS:-}" ]; then
        echo "$EPOCHSECONDS"
    else
        date +%s 2>/dev/null || echo 0
    fi
}

_pc_step_start() {
    _PC_NAMES+=("$1")
    _PC_START_EPOCH=$(_pc_now)
}

_pc_step_end() {
    local _result="${1:-PASS}"
    local _end=$(_pc_now)
    local _elapsed=$(( _end - ${_PC_START_EPOCH:-$_end} ))
    _PC_RESULTS+=("$_result")
    _PC_TIMES+=("${_elapsed}.0s")
}

_pc_print_summary() {
    echo ""
    echo "=== Pre-commit Summary ==="
    local _pass=0 _skip=0 _warn=0 _fail=0
    for i in "${!_PC_NAMES[@]}"; do
        local _name="${_PC_NAMES[$i]}"
        local _res="${_PC_RESULTS[$i]:-SKIP}"
        local _time="${_PC_TIMES[$i]:-0.0s}"
        printf "  %-6s %-30s %-6s %s\n" "Step $i" "$_name" "$_res" "$_time"
        case "$_res" in
            PASS) _pass=$((_pass+1)) ;;
            SKIP) _skip=$((_skip+1)) ;;
            WARN) _warn=$((_warn+1)) ;;
            FAIL) _fail=$((_fail+1)) ;;
        esac
    done
    echo "  Total: $_pass passed, $_skip skipped, $_warn warning, $_fail failed"
    echo "=============================="
}

_pc_exit() {
    local _code="${1:-0}"
    _pc_print_summary
    exit "$_code"
}

# ---------------------------------------------------------------------------
_pc_step_start "reports/ boundary"
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
    _pc_step_end "FAIL"
    _pc_exit 1
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "deletion gate"
# Step 0b: Staged deletion gate — blocks Tier 0 and Tier 1 without DGR
# DELETION_GATE_PHASE=2 = blocking (exit 2); unset or 1 = warn-only (exit 0)
if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_staged_deletions.py" ]; then
    DELETION_GATE_PHASE=2 "$_HOOK_PYTHON" scripts/ci/checks/check_staged_deletions.py --check-staged
    _del_status=$?
    if [ $_del_status -eq 2 ]; then
        echo ""
        echo "BLOCKED: Staged deletion requires a Deletion Governance Record (DGR)."
        echo "  Create: \"$_HOOK_PYTHON\" scripts/pipeline/commands/governance/deletion_governance_manager.py create \\"
        echo "    --files <path> --reason '...' --plan '<plan>' --class T-01"
        echo "  Commit DGR to deletion-approvals/ BEFORE staging the deletion."
        echo "  See docs/DELETION_GOVERNANCE.md"
        _pc_step_end "FAIL"
        _pc_exit 2
    fi
    _pc_step_end "PASS"
else
    _pc_step_end "SKIP"
fi

# ---------------------------------------------------------------------------
_pc_step_start "forbidden paths"
# Step 1: Forbidden-path enforcement
# ---------------------------------------------------------------------------
# Check all staged paths in a single Python invocation using --stdin batch mode.
# This avoids one Python startup per file (~120ms/file) which was ~56 min for
# large commits.  The --stdin flag reads one path per line and prints only DENY
# paths to stdout, exit 0 if all ALLOW, exit 2 if any DENY.
forbidden_staged=()
if [ -n "$_HOOK_PYTHON" ]; then
    while IFS= read -r _line; do forbidden_staged+=("$_line"); done < <(
        git diff --cached --name-only --diff-filter=ACM | \
            "$_HOOK_PYTHON" scripts/pipeline/commands/governance/path_guard.py --stdin | tr -d '\r'
    )
else
    echo "[Step 1] SKIP: .venv not found — forbidden-path check skipped." >&2
fi

if [ ${#forbidden_staged[@]} -gt 0 ]; then
    forbidden_violation=0
    for staged_file in "${forbidden_staged[@]}"; do
        echo "Forbidden path staged: $staged_file"
        "$_HOOK_PYTHON" scripts/pipeline/commands/governance/override_manager.py validate-for-path "$staged_file" 2>&1
        if [ $? -ne 0 ]; then
            forbidden_violation=1
        fi
    done
    if [ $forbidden_violation -ne 0 ]; then
        echo ""
        echo "BLOCKED: One or more staged files are in forbidden paths and have no override token."
        echo "  Create an override token before committing:"
        echo "    .venv/Scripts/python scripts/pipeline/commands/governance/override_manager.py create \\"
        echo "      --paths <path> --reason '...' --plan '...'"
        echo "  The token is auto-validated from reports/overrides/pending/ — do NOT stage it."
        _pc_step_end "FAIL"
        _pc_exit 1
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "filename conventions"
# Step 1b: Content filename convention check (TC-NEW-01)
# ---------------------------------------------------------------------------
# Blocks commits where any staged content file has an invalid filename:
#   leading/trailing hyphen, uppercase extension, spaces, double dots, etc.
# Non-English locale files are also validated (same filename rules apply).
if [ -n "$_HOOK_PYTHON" ]; then
    "$_HOOK_PYTHON" scripts/ci/checks/check_content_filenames.py --strict
    if [ $? -ne 0 ]; then
        echo ""
        echo "BLOCKED: One or more content files have invalid filenames (see above)."
        echo "  Rename the file(s) to a valid lowercase slug before committing."
        echo "  Convention: [a-z0-9]+(-[a-z0-9]+)*.md  (no leading/trailing hyphen)"
        _pc_step_end "FAIL"
        _pc_exit 1
    fi
else
    echo "[Step 1b] SKIP: .venv not found — filename check skipped." >&2
fi
_pc_step_end "PASS"


# ---------------------------------------------------------------------------
_pc_step_start "API accuracy audit"
# Step 2: API accuracy audit on staged English content files
# ---------------------------------------------------------------------------
# Locale files (/ar/, /fr/, /de/, etc.) are translator output and are not
# subject to API accuracy audit — only English source pages are checked.
changed=()
while IFS= read -r _line; do changed+=("$_line"); done < <(
    git diff --cached --name-only --diff-filter=ACM \
        | grep '^content/.*\.md$' \
        | grep -E '(/en/|^content/blog\.aspose\.org/)'
)
if [ ${#changed[@]} -eq 0 ]; then
    # No English pages staged — skip the API audit ONLY. Do NOT exit the hook:
    # the early `_pc_exit 0` that used to live here skipped Steps 3-18 for
    # locale-only commits, which is how the 2026-07-12 wave-3 locale commits
    # bypassed every later gate (encoding, blog standards, frontmatter YAML).
    _pc_step_end "SKIP"
else
    echo "Running content API audit on staged files (${#changed[@]} English pages)..."
    # Use --files-from to avoid OS argument-list-too-long errors on large commits.
    _tmpfile=$(mktemp /tmp/audit-files-XXXXXX.txt 2>/dev/null || mktemp)
    printf '%s\n' "${changed[@]}" > "$_tmpfile"
    if [ -n "$_HOOK_PYTHON" ]; then
        "$_HOOK_PYTHON" scripts/pipeline/commands/content/audit.py --files-from "$_tmpfile" --fail-fast
        status=$?
        rm -f "$_tmpfile"
        if [ $status -ne 0 ]; then
            echo ""
            echo "BLOCKED: Content has API accuracy failures."
            echo "Fix the issues above, then re-stage and commit."
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    else
        rm -f "$_tmpfile"
        echo "[Step 2] SKIP: .venv not found — audit skipped." >&2
        status=0
    fi
    _pc_step_end "PASS"

    echo "Content API audit passed."
fi

# ---------------------------------------------------------------------------
_pc_step_start "plugin_platform"
# Step 3: Check plugin_platform canonical values for products pages
# ---------------------------------------------------------------------------
if git diff --cached --name-only --diff-filter=ACM | grep -q '^content/products\.aspose\.org/'; then
    echo "Running plugin_platform canonical-value check..."
    if [ -n "$_HOOK_PYTHON" ]; then
        "$_HOOK_PYTHON" scripts/ci/checks/check_plugin_platform.py
        if [ $? -ne 0 ]; then
            echo ""
            echo "BLOCKED: plugin_platform has non-canonical values (see AGENTS.md Section 3b)."
            echo "Fix the values above, then re-stage and commit."
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    else
        echo "[Step 3] SKIP: .venv not found — plugin_platform check skipped." >&2
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "frontmatter validation"
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
    if [ -n "$_HOOK_PYTHON" ]; then
        "$_HOOK_PYTHON" scripts/pipeline/commands/content/validate_frontmatter.py --files-from "$_tmpfile3"
        prov_status=$?
    else
        prov_status=0
        echo "[Step 4] SKIP: .venv not found — frontmatter check skipped." >&2
    fi
    rm -f "$_tmpfile3"
    if [ $prov_status -ne 0 ]; then
        echo ""
        echo "BLOCKED: Frontmatter has hard errors (see above). Fix before committing."
        _pc_step_end "FAIL"
        _pc_exit 1
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "provenance protection"
# Step 4b: Provenance protection — warn when auto_updatable: false pages are modified
# ---------------------------------------------------------------------------
# Detects staged modifications to pages that have auto_updatable: false in their
# committed (HEAD) provenance block.  These pages contain manually curated content
# that should not be overwritten by automated processes.
# Currently warning-only; will be promoted to blocking after validation period.
# Performance: uses git grep batch scan for large commits (O(1) subprocess).
_prot_status=0
if [ -n "$_HOOK_PYTHON" ]; then
    echo "[Step 4b] Scanning HEAD for provenance-protected pages..."
    "$_HOOK_PYTHON" scripts/ci/checks/check_protected_overwrites.py --check-staged
    _prot_status=$?
fi
if [ $_prot_status -eq 2 ]; then
    echo ""
    echo "WARNING: Protected page(s) modified (auto_updatable: false). See above."
    echo "  This is currently a warning. It will become blocking in a future release."
    # Not blocking yet: exit would be here when promoted
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "content_hash normalization"
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
    [ -n "$_HOOK_PYTHON" ] && PYTHONPATH=scripts/pipeline "$_HOOK_PYTHON" scripts/pipeline/commands/diagnostics/provenance_normalize_hash.py \
        --apply --files-from "$_tmpfile5" --auto-stage 2>&1
    rm -f "$_tmpfile5"
    # Non-blocking: normalization errors are logged but do not block the commit.
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "last_mechanism staleness"
# Step 6: last_mechanism staleness warning
# ---------------------------------------------------------------------------
# For each staged file where the body changed (hash was stale), check whether
# last_mechanism was also updated.  Warns if the mechanism appears unchanged
# despite body changes — indicates an undeclared content edit.
# Non-blocking: warning only.  Will be upgraded to hard error after skill
# contracts (S-20, S-21, S-26) include provenance update steps.
if [ -n "$_HOOK_PYTHON" ]; then
for staged_file in "${changed[@]}"; do
    if [ ! -f "$staged_file" ]; then continue; fi
    # Compare HEAD's content_hash against current computed hash to detect body
    # changes.  We read HEAD (not the working copy) because Step 5 already
    # normalized the working copy's stored hash — comparing stored vs computed
    # on the working copy would always match after Step 5.
    # Pass file path via sys.argv to avoid shell quoting issues.
    head_info=$(git show HEAD:"$staged_file" 2>/dev/null | "$_HOOK_PYTHON" -c "
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
    current_info=$("$_HOOK_PYTHON" -c "
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
fi  # _HOOK_PYTHON guard (Step 6)
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "Python placement"
# Step 7: Python file placement check (staged .py files only)
# ---------------------------------------------------------------------------
# Blocks commits of .py files in forbidden locations (repo root, scripts/ root,
# scripts/one-shot/). Uses --check-staged so only staged files are examined —
# existing legacy files in the working tree don't trigger false positives.
# See AGENTS.md §4b for placement rules.
if git diff --cached --name-only --diff-filter=ACM | grep -q '\.py$'; then
    if [ -n "$_HOOK_PYTHON" ]; then
        "$_HOOK_PYTHON" scripts/ci/checks/check_python_placement.py --check-staged
        if [ $? -ne 0 ]; then
            echo ""
            echo "BLOCKED: Staged Python file(s) are in forbidden locations (see above)."
            echo "  Correct locations:"
            echo "    scripts/maintenance/  (operator one-off; add to scripts/maintenance/registry.yaml)"
            echo "    scripts/pipeline/     (operational; follow PIPELINE.md New File Protocol)"
            echo "    scripts/ci/           (CI-only validator)"
            echo "  See AGENTS.md §4b for the full decision tree."
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    else
        echo "[Step 7] SKIP: .venv not found — Python placement check skipped." >&2
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "venv enforcement"
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
        "$_venv_py" scripts/ci/checks/enforce_venv_python.py --check
        if [ $? -ne 0 ]; then
            echo ""
            echo "BLOCKED: Staged file(s) contain bare python/pip or --user violations."
            echo "  Auto-fix: .venv/Scripts/python scripts/ci/checks/enforce_venv_python.py --fix"
            echo "  DENY violations (--user, USER_SITE) require manual skill redesign."
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "session ledger"
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
        if [ -n "$_staged_content" ] && [ -n "$_HOOK_PYTHON" ]; then
            _session_check_result=$(echo "$_staged_content" | \
                "$_HOOK_PYTHON" scripts/pipeline/commands/ops/session_ledger.py check-staged 2>&1)
            _session_check_status=$?
            if [ $_session_check_status -ne 0 ]; then
                echo ""
                echo "$_session_check_result"
                echo ""
                echo "WARN: Staged content files not found in session ledger (non-blocking)."
                echo "  Options:"
                echo "    1. Record files: session_ledger.py record --file <path> --action modified"
                echo "    2. Adopt files:  session_ledger.py adopt --files <path> [<path> ...]"
                echo "  DOC: docs/BYPASS_REGISTRY.md"
                echo ""
                # Include full diagnostics (non-fatal if diagnose itself fails).
                "$_HOOK_PYTHON" scripts/pipeline/commands/ops/session_ledger.py diagnose 2>&1 || true
                # TC-GOV-02: Downgraded from exit 1 to warning (defense-in-depth, not blocking)
            fi
        fi
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "onboarding integrity"
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
    if ! "$venv_python" scripts/ci/checks/check_onboarding_integrity.py; then
      echo "[Step 9] FAIL: onboarding integrity check failed. Fix issues above before committing."
      _pc_step_end "FAIL"
      _pc_exit 1
    fi
    echo "[Step 9] PASS"
  fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "graded_at reversion"
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
            "$_ga_python" scripts/pipeline/commands/governance/check_graded_at_only.py \
                --files-from "$_tmpfile10" 2>"$_ga_stderr"
        )
        rm -f "$_tmpfile10"
        if grep -q '^PARSE_FAILURE:' "$_ga_stderr" 2>/dev/null; then
            echo "[Step 10] ERROR: graded_at-only check had parse failures:"
            grep '^PARSE_FAILURE:' "$_ga_stderr" | sed 's/^PARSE_FAILURE:/  /'
            rm -f "$_ga_stderr"
            _pc_step_end "FAIL"
            _pc_exit 1
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
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "monkeypatch lint"
# Step 11: Monkeypatch lint — block T1/T2 violations in staged test files
# ---------------------------------------------------------------------------
# Checks for T1/T2 monkeypatch violations (AGENTS.md §16 tiered policy).
# Blocking mode: T1/T2 violations fail the commit. T3/T4 are informational.
staged_test_files=()
while IFS= read -r _tline; do staged_test_files+=("$_tline"); done < <(
    git diff --cached --name-only --diff-filter=ACM | grep -E '^.*(test_[^/]*\.py|[^/]*_test\.py)$' || true
)
if [ ${#staged_test_files[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_monkeypatch_lint.py" ]; then
        _lint_out=$("$_HOOK_PYTHON" scripts/ci/checks/check_monkeypatch_lint.py --strict --tier 1,2 --compare-baseline scripts/ci/monkeypatch_baseline.json -- "${staged_test_files[@]}" 2>&1)
        _lint_exit=$?
        if [ -n "$_lint_out" ]; then
            echo "$_lint_out" | sed 's/^/[Step 11] /' >&2
        fi
        if [ $_lint_exit -ne 0 ]; then
            echo "[Step 11] BLOCKED: T1/T2 monkeypatch violations in staged test files." >&2
            echo "[Step 11] Remediate with configure() seams. See AGENTS.md §16." >&2
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "Go code block vet"
# Step 12: Go code blocks — strict vet of ```go fences in staged Go content
# ---------------------------------------------------------------------------
# Enforcing mode: blocks commit on go vet failure. If Go is not on PATH the
# checker returns exit 2 and the commit is blocked — install Go to proceed.
staged_go_content=()
while IFS= read -r _gline; do staged_go_content+=("$_gline"); done < <(
    git diff --cached --name-only --diff-filter=ACM | grep -E '^content/.*/go/' || true
)
if [ ${#staged_go_content[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_go_code_blocks.py" ]; then
        # Determine content dir from first staged file
        _go_content_dir=$(dirname "${staged_go_content[0]}")
        # Walk up to the platform root (content/.../go/)
        while [[ "$_go_content_dir" != */go && "$_go_content_dir" != "." ]]; do
            _go_content_dir=$(dirname "$_go_content_dir")
        done
        if [ "$_go_content_dir" != "." ]; then
            _go_out=$("$_HOOK_PYTHON" scripts/ci/checks/check_go_code_blocks.py "$_go_content_dir" 2>&1)
            _go_exit=$?
            if [ -n "$_go_out" ]; then
                echo "$_go_out" | sed 's/^/[Step 12] /' >&2
            fi
            if [ "$_go_exit" -ne 0 ]; then
                _pc_step_end "FAIL"
                _pc_exit 1
            fi
        fi
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "encoding guard"
# Step 13: Content encoding — reject U+FFFD replacement characters in staged content
# Guard prevents encoding corruption (e.g., charset misdetection in LLM responses)
# from reaching the live site. Scans staged content/*.md files for EF BF BD bytes.
# ---------------------------------------------------------------------------
staged_content_md=()
while IFS= read -r _eline; do staged_content_md+=("$_eline"); done < <(
    git diff --cached --name-only --diff-filter=ACM | grep -E '^content/.*\.md$' || true
)
if [ ${#staged_content_md[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/check_content_encoding.py" ]; then
        # Batch to avoid OS argument list limit (hits at ~800+ files)
        _enc_exit=0
        _enc_out=""
        _batch_size=200
        for (( _ei=0; _ei<${#staged_content_md[@]}; _ei+=_batch_size )); do
            _batch=("${staged_content_md[@]:$_ei:$_batch_size}")
            _batch_out=$("$_HOOK_PYTHON" scripts/ci/check_content_encoding.py "${_batch[@]}" 2>&1)
            _batch_code=$?
            _enc_out+="$_batch_out"
            if [ $_batch_code -ne 0 ]; then _enc_exit=1; fi
        done
        if [ -n "$_enc_out" ]; then
            echo "$_enc_out" | sed 's/^/[Step 13] /' >&2
        fi
        if [ $_enc_exit -ne 0 ]; then
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "KB slug quality"
# Step 14: KB how-to slug quality gate (TC-KBS-007)
# Checks staged content/kb.aspose.org/**/how-to-*.md filenames for defects:
#   C1 — single-token noun > 12 chars (CamelCase namespace leak)
#   C2 — verb-noun duplication (e.g. how-to-extract-text-extraction-*)
#   C3 — primary noun word in generic-noun banlist (e.g. "core", "content")
# Only staged KB how-to files are checked — pre-existing slugs are not blocked.
# ---------------------------------------------------------------------------
staged_kb_howto=()
while IFS= read -r _kline; do staged_kb_howto+=("$_kline"); done < <(
    git diff --cached --name-only --diff-filter=ACR \
        | grep -E '^content/kb\.aspose\.org/.*how-to-.*\.md$' || true
)
if [ ${#staged_kb_howto[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_kb_slug_quality.py" ]; then
        _kb_out=$("$_HOOK_PYTHON" scripts/ci/checks/check_kb_slug_quality.py \
            "${staged_kb_howto[@]}" 2>&1)
        _kb_exit=$?
        if [ -n "$_kb_out" ]; then
            echo "$_kb_out" | sed 's/^/[Step 14] /'
        fi
        if [ $_kb_exit -ne 0 ]; then
            echo ""
            echo "BLOCKED: Staged KB how-to slug(s) have quality defects (see above)."
            echo "  Fix the slug in site_planner.py and regenerate, or choose a better filename."
            echo "  See docs/governance/ for KB slug naming rules."
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    else
        echo "[Step 14] SKIP: .venv not found or check_kb_slug_quality.py missing." >&2
    fi
fi
_pc_step_start "Blog post standards"
# Step 15: Blog post standards gate (check_blog_post_standards.py)
# Checks staged blog.aspose.org post frontmatter for tag leakage, category
# format, Related Resources section, and platform target registration.
staged_blog_posts=()
while IFS= read -r _bline; do staged_blog_posts+=("$_bline"); done < <(
    git diff --cached --name-only --diff-filter=ACR         | grep -E '^content/blog\.aspose\.org/[^/]+/[^/]+/[^/]+/index\.md$' || true
)
if [ ${#staged_blog_posts[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_blog_post_standards.py" ]; then
        _blog_out=$("$_HOOK_PYTHON" scripts/ci/checks/check_blog_post_standards.py             "${staged_blog_posts[@]}" 2>&1)
        _blog_exit=$?
        if [ -n "$_blog_out" ]; then
            echo "$_blog_out" | sed 's/^/[Step 15] /'
        fi
        if [ $_blog_exit -ne 0 ]; then
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    fi
fi
_pc_step_end "PASS"

# Step 16: Docs developer-guide slug quality gate (SQ-08 / D1 check)
# Checks staged docs developer-guide pages for concatenated CamelCase slugs
# (e.g., "javascriptextensions" instead of "javascript-extensions").
staged_docs_guide=()
while IFS= read -r _dgline; do staged_docs_guide+=("$_dgline"); done < <(
    git diff --cached --name-only --diff-filter=ACR \
        | grep -E '^content/docs\.aspose\.org/en/[^/]+/[^/]+/developer-guide/[^/]+\.md$' || true
)
if [ ${#staged_docs_guide[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_docs_slug_quality.py" ]; then
        _docs_slug_out=$("$_HOOK_PYTHON" scripts/ci/checks/check_docs_slug_quality.py \
            "${staged_docs_guide[@]}" 2>&1)
        _docs_slug_exit=$?
        if [ -n "$_docs_slug_out" ]; then
            echo "$_docs_slug_out" | sed 's/^/[Step 16] /'
        fi
        if [ $_docs_slug_exit -ne 0 ]; then
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    else
        echo "[Step 16] SKIP: .venv not found or check_docs_slug_quality.py missing." >&2
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "code fence blank lines"
# Step 16.5: CODE_BLOCK_BLANK_LINES check on staged products pages (GAP-CSSP-R04/R05)
# Blocks commits that stage products.aspose.org _index.md files with blank lines
# inside code fences (layout: plugin pages). EN pages: ERROR (blocking).
# Locale pages with short snippets: ERROR (blocking). Long snippets: WARN (non-blocking).
# ---------------------------------------------------------------------------
staged_products_pages=()
while IFS= read -r _pline; do staged_products_pages+=("$_pline"); done < <(
    git diff --cached --name-only --diff-filter=ACM \
        | grep -E '^content/products\.aspose\.org/.*/_index\.md$' || true
)
if [ ${#staged_products_pages[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/pipeline/commands/content/validate_plugin_structure.py" ]; then
        echo "[Step 16.5] Checking CODE_BLOCK_BLANK_LINES on ${#staged_products_pages[@]} staged products page(s)..."
        PYTHONPATH=scripts/pipeline "$_HOOK_PYTHON" \
            scripts/pipeline/commands/content/validate_plugin_structure.py \
            --files "${staged_products_pages[@]}"
        _cssp_exit=$?
        if [ $_cssp_exit -ne 0 ]; then
            echo ""
            echo "BLOCKED: Blank lines in code fences detected in staged products page(s) (see above)."
            echo "  Fix: PYTHONPATH=scripts/pipeline .venv/Scripts/python \\"
            echo "         scripts/pipeline/commands/content/normalize_code_block_blanks.py"
            echo "  For multi-line double-quoted YAML scalars (line folding), edit manually:"
            echo "    remove offending \\\\n\\\\n escape sequences inside code fence regions."
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    else
        echo "[Step 16.5] SKIP: .venv not found or validate_plugin_structure.py missing." >&2
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "enterprise link syntax"
# Step 17: Enterprise markdown link syntax gate (TC-BL-011).
# Validates that all staged content files have syntactically correct markdown
# link syntax for *.aspose.com enterprise URLs — specifically that every
# link opener ](https:// has a matching closing ).
# Catches the bug class from bb68a63a22 (unclosed parenthesis).
# ---------------------------------------------------------------------------
staged_content_files=()
while IFS= read -r _clf; do staged_content_files+=("$_clf"); done < <(
    git diff --cached --name-only --diff-filter=ACM \
        | grep -E '^content/.*/(index|_index)\.md$' || true
)
if [ ${#staged_content_files[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_enterprise_link_syntax.py" ]; then
        echo "[Step 17] Checking enterprise link syntax in ${#staged_content_files[@]} staged content file(s)..."
        _ent_out=$("$_HOOK_PYTHON" scripts/ci/checks/check_enterprise_link_syntax.py \
            "${staged_content_files[@]}" 2>&1)
        _ent_exit=$?
        if [ $_ent_exit -ne 0 ]; then
            echo "$_ent_out" | sed 's/^/[Step 17] /'
            echo ""
            echo "BLOCKED: Broken enterprise markdown link syntax detected (see above)."
            echo "  Fix: ensure every [text](https://...) link has a closing ) after the URL."
            echo "  Common mistake: [text](https://url/path/. is missing the closing )"
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    else
        echo "[Step 17] SKIP: .venv not found or check_enterprise_link_syntax.py missing." >&2
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "frontmatter YAML parse"
# Step 18: Frontmatter YAML parse gate — ALL locales (check_frontmatter_yaml.py)
# Steps 2/4/5 validate staged ENGLISH files only; locale files previously had
# no frontmatter gate, which let the 2026-07-12 wave-3 locale commits land
# unparseable YAML on main and break the Hugo site builds (docs run
# 29230300508). This step parses the frontmatter of every staged content/*.md
# file regardless of locale.
# ---------------------------------------------------------------------------
staged_all_content_md=()
while IFS= read -r _fmline; do staged_all_content_md+=("$_fmline"); done < <(
    git diff --cached --name-only --diff-filter=ACMR | grep -E '^content/.*\.md$' || true
)
if [ ${#staged_all_content_md[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_frontmatter_yaml.py" ]; then
        # Batch to avoid OS argument list limit (same pattern as Step 13)
        _fm_exit=0
        _fm_out=""
        _fm_batch_size=200
        for (( _fmi=0; _fmi<${#staged_all_content_md[@]}; _fmi+=_fm_batch_size )); do
            _fm_batch=("${staged_all_content_md[@]:$_fmi:$_fm_batch_size}")
            _fm_batch_out=$("$_HOOK_PYTHON" scripts/ci/checks/check_frontmatter_yaml.py \
                --staged "${_fm_batch[@]}" 2>&1)
            _fm_batch_code=$?
            if [ $_fm_batch_code -ne 0 ]; then
                _fm_exit=1
                _fm_out+="$_fm_batch_out"$'\n'
            fi
        done
        if [ $_fm_exit -ne 0 ]; then
            echo "$_fm_out" | sed 's/^/[Step 18] /'
            echo ""
            echo "BLOCKED: Staged content file(s) have unparseable YAML frontmatter (see above)."
            echo "  These files would abort the Hugo site build. Fix the frontmatter YAML"
            echo "  (most common: a truncated multi-line description with an unterminated quote)."
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    else
        echo "[Step 18] SKIP: .venv not found or check_frontmatter_yaml.py missing." >&2
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "translation regression"
# Step 19: Translation-regression gate — check_translation_regression.py
# Blocks commits that regress a translated locale description back to English
# or stage translation-prompt leak text (the silently-parseable wave-3
# corruption classes; Step 18 only catches UNPARSEABLE frontmatter).
# Compares staged blobs against HEAD, so pre-existing English descriptions
# (backlog ST-012) do not block unrelated commits.
# ---------------------------------------------------------------------------
staged_locale_md=()
while IFS= read -r _trline; do staged_locale_md+=("$_trline"); done < <(
    git diff --cached --name-only --diff-filter=ACMR \
        | grep -E '^content/[^/]+/[a-z]{2}(-[a-z]{2})?/.*\.md$' \
        | grep -vE '^content/[^/]+/en/' || true
)
if [ ${#staged_locale_md[@]} -gt 0 ]; then
    if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_translation_regression.py" ]; then
        _tr_exit=0
        _tr_out=""
        _tr_batch_size=200
        for (( _tri=0; _tri<${#staged_locale_md[@]}; _tri+=_tr_batch_size )); do
            _tr_batch=("${staged_locale_md[@]:$_tri:$_tr_batch_size}")
            _tr_batch_out=$("$_HOOK_PYTHON" scripts/ci/checks/check_translation_regression.py \
                --staged "${_tr_batch[@]}" 2>&1)
            _tr_batch_code=$?
            if [ $_tr_batch_code -ne 0 ]; then
                _tr_exit=1
                _tr_out+="$_tr_batch_out"$'\n'
            fi
        done
        if [ $_tr_exit -ne 0 ]; then
            echo "$_tr_out" | sed 's/^/[Step 19] /'
            echo ""
            echo "BLOCKED: Staged locale file(s) regress translated content (see above)."
            echo "  R1: a previously-translated description became English — restore the"
            echo "      translation or fix the producing tool."
            echo "  R2: translation-prompt leak text staged — remove the leaked prompt."
            _pc_step_end "FAIL"
            _pc_exit 1
        fi
    else
        echo "[Step 19] SKIP: .venv not found or check_translation_regression.py missing." >&2
    fi
fi
_pc_step_end "PASS"

# ---------------------------------------------------------------------------
_pc_step_start "evidence churn"
# Step 20: Evidence-only mass-churn gate — check_evidence_churn.py
# Blocks bulk commits where many staged content .md files change only the
# `evidence:` frontmatter block (model_sha/model_version/claims/apis/
# sections re-stamp) with no body content change and no other frontmatter
# field changed. Local pre-commit counterpart to check_grade_churn.py
# (GUARD-02, wired CI-only) for the `evidence:` block specifically. Root
# incident: commit 643c02f7b8 (TC-SFH-007) re-stamped 845 pdf/net pages after
# a knowledge model jump with zero body reconciliation via S-20 (page-update).
# Override: commit message annotation `EVIDENCE-RESTAMP: approved by ...`.
# ---------------------------------------------------------------------------
if [ -n "$_HOOK_PYTHON" ] && [ -f "scripts/ci/checks/check_evidence_churn.py" ]; then
    _ec_commit_msg="${EVIDENCE_RESTAMP_MSG:-$(cat .git/COMMIT_EDITMSG 2>/dev/null || true)}"
    _ec_out=$("$_HOOK_PYTHON" scripts/ci/checks/check_evidence_churn.py --mode staged --commit-msg "$_ec_commit_msg" 2>&1)
    _ec_exit=$?
    if [ -n "$_ec_out" ]; then
        echo "$_ec_out" | sed 's/^/[Step 20] /'
    fi
    if [ $_ec_exit -ne 0 ]; then
        _pc_step_end "FAIL"
        _pc_exit 1
    fi
else
    echo "[Step 20] SKIP: .venv not found or check_evidence_churn.py missing." >&2
fi
_pc_step_end "PASS"

_pc_exit 0
