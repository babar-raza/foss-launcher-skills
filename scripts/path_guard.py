"""Path guard — enforce allowed write paths for content operations.

Usage:
    python scripts/path_guard.py <path>
    python scripts/path_guard.py --content-root /path/to/repo <path>

Exit codes:
    0  ALLOW — path is safe to write
    1  DENY  — path matches a forbidden prefix
    2  ERROR — configuration or argument error

Output (stdout):
    ALLOW: <path>
    DENY: <path> — matches forbidden prefix '<prefix>'
"""
import os
import sys
from pathlib import Path

# Allow `import config_loader` when invoked directly from repo root or tests
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config, resolve_content_repo


# Safety net: always forbidden regardless of config.yaml contents
_HARDCODED_FORBIDDEN = [
    "themes/",
    "layouts/",
    "configs/",
    ".git/",
    "AGENTS.md",
    "CLAUDE.md",
    "CODEX.md",
    ".claude/",
    ".agents/",
    ".kilocode/",
    "skills/",
    "scripts/",
]


def _normalise(path_str: str) -> str:
    """Return a forward-slash, trailing-separator-free, lower-agnostic relative form."""
    return path_str.replace("\\", "/").rstrip("/")


def _to_relative(path: Path, content_root: Path | None) -> str:
    """Return the path string relative to content_root (if resolvable), else as-is."""
    if content_root is not None:
        try:
            rel = path.resolve().relative_to(content_root.resolve())
            return _normalise(str(rel))
        except ValueError:
            pass
    return _normalise(str(path))


def check_path(
    target: str | Path,
    *,
    content_root: Path | None = None,
    config: dict | None = None,
) -> tuple[str, str | None]:
    """Check whether *target* is safe to write.

    Args:
        target: The file path to evaluate (absolute or relative).
        content_root: Root of the content repo; used to relativise absolute paths.
        config: Pre-loaded config dict (loaded from config.yaml if None).

    Returns:
        ("ALLOW", None) if the path is permitted.
        ("DENY", reason) if the path is forbidden; *reason* explains which prefix matched.
    """
    if config is None:
        config = load_config()

    # Build forbidden list preserving original strings (for readable DENY messages)
    # De-duplicate by normalised form.
    seen_norms: set[str] = set()
    forbidden: list[str] = []
    for entry in list(_HARDCODED_FORBIDDEN) + list(config.get("forbidden_paths", [])):
        norm = _normalise(str(entry))
        if norm not in seen_norms:
            seen_norms.add(norm)
            forbidden.append(str(entry))

    rel = _to_relative(Path(target), content_root)

    for prefix in forbidden:
        norm_prefix = _normalise(prefix)
        # Exact match (e.g. "AGENTS.md") or directory-prefix match (e.g. "themes/foo.css")
        if rel == norm_prefix or rel.startswith(norm_prefix + "/"):
            return ("DENY", f"matches forbidden prefix '{prefix}'")

    return ("ALLOW", None)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Returns exit code."""
    args = argv if argv is not None else sys.argv[1:]

    content_root: Path | None = None
    positional: list[str] = []

    i = 0
    while i < len(args):
        if args[i] in ("--content-root", "-r") and i + 1 < len(args):
            content_root = Path(args[i + 1])
            i += 2
        elif args[i].startswith("--content-root="):
            content_root = Path(args[i].split("=", 1)[1])
            i += 1
        else:
            positional.append(args[i])
            i += 1

    if not positional:
        print("ERROR: no path argument supplied", file=sys.stderr)
        print("Usage: path_guard.py [--content-root <root>] <path>", file=sys.stderr)
        return 2

    if content_root is None:
        try:
            content_root = resolve_content_repo()
        except Exception:
            content_root = None

    target = positional[0]
    verdict, reason = check_path(target, content_root=content_root)

    if verdict == "ALLOW":
        print(f"ALLOW: {target}")
        return 0
    else:
        print(f"DENY: {target} — {reason}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
