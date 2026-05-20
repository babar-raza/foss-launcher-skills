#!/usr/bin/env python3
# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""classify_bash_readonly.py - Ultra-strict fail-closed Bash read-only classifier.

Used by check_session_gate.sh to determine if a Bash command is safe to run
without an active session gate (TC-DS-01).

Exit codes:
  0 = command is read-only (safe to allow)
  1 = command is NOT read-only or cannot be determined (block)

Design principle: FAIL-CLOSED. Any unknown command, pattern, or structure
is classified as NOT read-only. Only an exhaustive allowlist passes.
"""
import re
import sys

# ---------------------------------------------------------------------------
# Exhaustive allowlist of read-only commands
# ---------------------------------------------------------------------------

ALLOWED_SIMPLE = frozenset({
    'ls', 'dir', 'cat', 'head', 'tail', 'wc', 'grep', 'rg', 'awk', 'sort',
    'uniq', 'cut', 'tr', 'column', 'echo', 'printf', 'pwd', 'which', 'type',
    'file', 'stat', 'date', 'uname', 'env', 'printenv', 'hostname',
    'basename', 'dirname', 'realpath', 'readlink', 'test', '[', 'true',
    'false', 'diff', 'comm', 'md5sum', 'sha256sum', 'sha1sum', 'b2sum',
    'xxd', 'od', 'hexdump', 'strings', 'less', 'more', 'tac', 'rev',
    'nl', 'expand', 'unexpand', 'fold', 'fmt', 'paste', 'join',
    'seq', 'yes', 'expr', 'bc', 'id', 'whoami', 'groups', 'locale',
    'tree', 'du', 'df',
})

ALLOWED_GIT_SUBCOMMANDS = frozenset({
    'log', 'status', 'diff', 'show', 'branch', 'rev-parse', 'describe',
    'remote', 'tag', 'config', 'name-rev', 'symbolic-ref', 'rev-list',
    'shortlog', 'cat-file', 'ls-tree', 'ls-files', 'ls-remote',
    'count-objects', 'fsck', 'verify-pack', 'for-each-ref',
    'merge-base', 'blame', 'annotate', 'reflog',
})

BLOCKED_GIT_SUBCOMMANDS = frozenset({
    'reset', 'clean', 'checkout', 'restore', 'stash', 'rebase',
    'push', 'pull', 'merge', 'cherry-pick', 'revert', 'am', 'apply',
    'rm', 'mv', 'add', 'commit', 'fetch', 'clone', 'init', 'submodule',
    'bisect', 'gc', 'prune', 'filter-branch', 'replace', 'notes',
    'worktree',
})

BLOCKED_COMMANDS = frozenset({
    'rm', 'rmdir', 'mv', 'cp', 'chmod', 'chown', 'ln', 'mkfifo',
    'touch', 'mkdir', 'tee', 'install', 'dd',
    'python', 'python3', 'node', 'ruby', 'perl', 'php',
    'pip', 'pip3', 'npm', 'npx', 'yarn', 'pnpm', 'cargo', 'gem',
    'make', 'cmake', 'hugo', 'pytest', 'tox', 'nox',
    'curl', 'wget', 'ssh', 'scp', 'rsync', 'nc', 'netcat',
    'kill', 'pkill', 'killall', 'nohup', 'disown',
    'sudo', 'su', 'doas',
    'bash', 'sh', 'zsh', 'dash', 'ksh', 'csh', 'fish',
    'eval', 'exec', 'source', '.',
    'xargs',
})

# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------


def _strip_quotes(cmd: str) -> str:
    """Remove quoted strings to avoid false matches inside them."""
    # Remove double-quoted strings
    result = re.sub(r'"[^"]*"', 'QUOTED', cmd)
    # Remove single-quoted strings
    result = re.sub(r"'[^']*'", 'QUOTED', result)
    return result


def _has_redirect(cmd: str) -> bool:
    """Check for output redirects. Conservative: may have false positives."""
    cleaned = _strip_quotes(cmd)
    if re.search(r'(^|[^<])>{1,2}|&>|2>|\|&', cleaned):
        return True
    return False


def _has_dangerous_patterns(cmd: str) -> bool:
    """Check for command substitution, process substitution, heredocs, subshells."""
    cleaned = _strip_quotes(cmd)
    # Command substitution
    if '$(' in cleaned or '`' in cleaned:
        return True
    # Process substitution
    if '<(' in cleaned or '>(' in cleaned:
        return True
    # Subshells
    if '(' in cleaned:
        return True
    # Heredocs
    if '<<' in cleaned:
        return True
    return False


def _split_compound(cmd: str) -> list:
    """Split command on ;, &&, || — naive but sufficient for classification."""
    cleaned = _strip_quotes(cmd)
    # Find split positions in cleaned version
    parts = []
    current_start = 0
    i = 0
    while i < len(cleaned):
        if cleaned[i] == ';':
            parts.append(cmd[current_start:i].strip())
            current_start = i + 1
        elif cleaned[i:i+2] == '&&':
            parts.append(cmd[current_start:i].strip())
            current_start = i + 2
            i += 1
        elif cleaned[i:i+2] == '||':
            parts.append(cmd[current_start:i].strip())
            current_start = i + 2
            i += 1
        i += 1
    parts.append(cmd[current_start:].strip())
    return [p for p in parts if p]


def _split_pipe(cmd: str) -> list:
    """Split on pipe | (not || or |&)."""
    cleaned = _strip_quotes(cmd)
    parts = []
    current_start = 0
    i = 0
    while i < len(cleaned):
        if cleaned[i] == '|' and (i + 1 >= len(cleaned) or cleaned[i + 1] not in ('|', '&')):
            if i == 0 or cleaned[i - 1] != '|':
                parts.append(cmd[current_start:i].strip())
                current_start = i + 1
        i += 1
    parts.append(cmd[current_start:].strip())
    return [p for p in parts if p]


def _classify_single(cmd: str) -> bool:
    """Classify a single command (no pipes, no compounds). Returns True if read-only."""
    cmd = cmd.strip()
    if not cmd:
        return True

    # Check for redirects
    if _has_redirect(cmd):
        return False

    # Check for dangerous patterns
    if _has_dangerous_patterns(cmd):
        return False

    # Tokenize
    tokens = cmd.split()

    # Strip leading variable assignments (FOO=bar cmd ...)
    # Design decision (GAP-01/H-01): env prefixes are stripped before classification.
    # This allows 'FOO=bar git status' (benign read-only). Dangerous commands like
    # 'python' are still blocked regardless of prefix. True safety risk is near-zero
    # because the blocked-commands list catches all dangerous executables independently.
    while tokens and '=' in tokens[0] and not tokens[0].startswith('='):
        tokens = tokens[1:]

    if not tokens:
        # Only variable assignments — block (side effect)
        return False

    first = tokens[0]

    # Strip path prefix if present (e.g., /usr/bin/ls -> ls)
    base = first.rsplit('/', 1)[-1] if '/' in first else first

    # Check blocked first (takes priority)
    if base in BLOCKED_COMMANDS:
        return False

    # Git special handling
    if base == 'git':
        if len(tokens) < 2:
            return True  # bare 'git' shows help
        # Find the subcommand (skip flags)
        subcommand = None
        for t in tokens[1:]:
            if not t.startswith('-'):
                subcommand = t
                break
        if subcommand is None:
            return True  # git with only flags

        if subcommand in BLOCKED_GIT_SUBCOMMANDS:
            return False
        if subcommand in ALLOWED_GIT_SUBCOMMANDS:
            # git config --get/--list is OK, but git config key value is not
            if subcommand == 'config':
                rest = ' '.join(tokens[2:])
                if '--get' in rest or '--list' in rest or '--show' in rest or not rest:
                    return True
                return False
            return True
        # Unknown git subcommand — block
        return False

    # find special handling
    if base == 'find':
        rest = ' '.join(tokens[1:])
        if re.search(r'-delete|-exec|-execdir|-ok', rest):
            return False
        return True

    # sed special handling (block -i)
    if base == 'sed':
        for t in tokens[1:]:
            if t == '-i' or (t.startswith('-') and 'i' in t and t != '-'):
                return False
        return True

    # awk variants
    if base in ('awk', 'gawk', 'mawk'):
        return True

    # Check simple allowlist
    if base in ALLOWED_SIMPLE:
        return True

    # Unknown command — BLOCK (fail-closed)
    return False


def classify(command: str) -> bool:
    """Classify a full command string. Returns True if entirely read-only."""
    command = command.strip()

    # Empty command is safe
    if not command:
        return True

    # Multi-line commands — block
    if '\n' in command:
        return False

    # Split on compound operators
    segments = _split_compound(command)

    for segment in segments:
        # Split on pipes
        pipe_parts = _split_pipe(segment)
        for part in pipe_parts:
            if not _classify_single(part):
                return False

    return True


def main():
    """Read command from stdin or first argument, exit 0 if read-only, 1 if not."""
    if len(sys.argv) > 1:
        command = ' '.join(sys.argv[1:])
    else:
        command = sys.stdin.read().strip()

    if classify(command):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
