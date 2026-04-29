"""check_forbidden_overrides.py — CI gate: verify forbidden-path changes have override tokens.

For every file in the given list that path_guard.py would DENY, check that a committed
override token exists in reports/overrides/ (pending or archived). If any forbidden-path
file lacks a token, exit 1.

Usage:
    python scripts/ci/checks/check_forbidden_overrides.py file1 file2 ...
    python scripts/ci/checks/check_forbidden_overrides.py --stdin   # read file list from stdin

Exit codes:
    0  all forbidden-path changes have override tokens (or no forbidden-path changes)
    1  one or more forbidden-path changes lack override tokens
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Import path_guard from pipeline
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
from commands.governance.path_guard import check_path, FORBIDDEN_EXACT, FORBIDDEN_PREFIXES  # noqa: E402


def _is_explicitly_forbidden(file_path: str) -> bool:
    """Return True only if the path is in FORBIDDEN_EXACT or FORBIDDEN_PREFIXES.

    This excludes paths that are merely "not in allowlist" — those are uncategorized
    paths that do not require override tokens. Override tokens are only required for
    paths that the governance model explicitly forbids (governance files, agent dirs, etc.).
    """
    norm = file_path.replace("\\", "/").lstrip("./")
    # Check exact match (strip leading ./ for comparison)
    norm_exact = file_path.replace("\\", "/")
    while norm_exact.startswith("./"):
        norm_exact = norm_exact[2:]
    if norm_exact in FORBIDDEN_EXACT:
        return True
    # Check forbidden prefixes
    for prefix in FORBIDDEN_PREFIXES:
        if norm.startswith(prefix.lstrip("./")):
            return True
        # Also check with leading dots preserved
        norm2 = file_path.replace("\\", "/")
        if norm2.startswith(prefix):
            return True
    return False


def _normalize(p: str) -> str:
    """Normalize for token comparison: backslashes to forward slashes, strip leading dots/slashes.
    Matches the normalization used in override_manager.py so token paths and file paths compare equal.
    """
    return p.replace("\\", "/").lstrip("./")


def _load_token(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _find_token_for_path(normalized_path: str) -> dict | None:
    """Search pending/ and archived/ for a token that covers the given normalized path."""
    for subdir in ("pending", "archived"):
        token_dir = _REPO_ROOT / "reports" / "overrides" / subdir
        if not token_dir.exists():
            continue
        for token_file in sorted(token_dir.glob("*.json")):
            try:
                token = _load_token(token_file)
            except (json.JSONDecodeError, OSError):
                continue
            token_paths = token.get("paths", [])
            for tp in token_paths:
                tp_norm = _normalize(tp)
                # Match exact or prefix
                if normalized_path == tp_norm or normalized_path.startswith(tp_norm.rstrip("/") + "/"):
                    return token
    return None


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    if "--stdin" in args:
        file_list = [line.strip() for line in sys.stdin if line.strip()]
    else:
        file_list = args

    if not file_list:
        print("No files to check.")
        return 0

    violations: list[str] = []
    covered: list[tuple[str, str]] = []

    for file_path in file_list:
        # Only require override tokens for EXPLICITLY forbidden paths.
        # Paths that are merely "not in allowlist" are uncategorized — no token required.
        if not _is_explicitly_forbidden(file_path):
            continue

        decision, reason = check_path(file_path)
        # Double-check: should be DENY, but guard against edge cases
        if decision != "DENY":
            continue

        normalized = _normalize(file_path)
        token = _find_token_for_path(normalized)
        if token is None:
            violations.append(f"  MISSING TOKEN: {file_path} — {reason}")
        else:
            token_id = token.get("override_id", "unknown")
            retro = " [retroactive]" if token.get("retroactive") else ""
            covered.append((file_path, f"{token_id}{retro}"))

    if covered:
        print(f"Forbidden-path changes with override tokens ({len(covered)}):")
        for path, token_id in covered:
            print(f"  COVERED: {path} -- token {token_id}")

    if violations:
        print(f"\nForbidden-path changes WITHOUT override tokens ({len(violations)}):")
        for v in violations:
            print(v)
        print()
        print("To create an override token:")
        print("  python scripts/pipeline/commands/governance/override_manager.py create \\")
        print("    --paths <path> --reason '...' --plan '...'")
        print("Then commit the token file before or with the forbidden-path edit.")
        return 1

    if covered:
        print(f"\nAll {len(covered)} forbidden-path change(s) have override tokens. OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
