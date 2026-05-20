# Adapted from aspose.org
#!/usr/bin/env python3
"""scout.py — Tree-sitter extraction engine for FOSS repositories.

Extracts API surface, format support, limitations, code examples, and
structured claims from source repositories across Python, .NET, Java,
C++, TypeScript, and JavaScript platforms.

Usage:
    python scripts/scout.py {family} {platform} {repo-path} {output-dir}

Dependencies:
    tree-sitter>=0.25, tree-sitter-language-pack>=0.13,
    tree-sitter-c-sharp>=0.23, pyyaml

Architecture note:
    Scout class lives in extraction/scout.py.
    Extraction sub-modules live in extraction/*.py.
    This file is a ≤200-line shim: re-exports + CLI.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path guard — ensure extraction/ package is importable regardless of cwd
# ---------------------------------------------------------------------------

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/knowledge/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from core.env_loader import load_env  # noqa: E402
load_env()

# ---------------------------------------------------------------------------
# Re-exports from extraction/ sub-modules
# Tests and external callers use `import scout; scout.<name>` — keep these.
# ---------------------------------------------------------------------------

from extraction.tree_helpers import (       # noqa: E402, F401
    PLATFORM_TO_LANG,
    _CLASS_TYPES,
    _FUNC_TYPES,
    _PY_ENUM_BASES,
    _IMPORT_TYPES,
    _MODULE_TYPES,
    _NOT_IMPL_PATTERNS,
    _FILE_EXTENSIONS,
    _HEADER_EXTENSIONS,
    _DOC_COMMENT_STYLES,
    _LANG_ALIASES,
    MAX_FILES,
    get_parser,
    collect_nodes,
    node_text,
    child_by_field,
    find_child_by_type,
    find_children_by_type,
    _node_name,
    is_public,
    _collect_source_files,
    _extract_bases,
    _extract_enum_members,
    _extract_python_enum_members,
)

# Optional extraction sub-modules -- gracefully degrade if not yet ported
try:
    from extraction.package_root import detect_package_root      # noqa: E402, F401
except ImportError:
    detect_package_root = None  # type: ignore[assignment,misc]

try:
    from extraction.package_manifest import parse_manifest       # noqa: E402, F401
except ImportError:
    parse_manifest = None  # type: ignore[assignment,misc]

try:
    from extraction.formats import detect_formats                # noqa: E402, F401
except ImportError:
    detect_formats = None  # type: ignore[assignment,misc]

try:
    from extraction.claims import build_identity_claims          # noqa: E402, F401
except ImportError:
    build_identity_claims = None  # type: ignore[assignment,misc]

try:
    from extraction.snippets import extract_snippets             # noqa: E402, F401
except ImportError:
    extract_snippets = None  # type: ignore[assignment,misc]

try:
    from extraction.api_surface import (                         # noqa: E402, F401
        extract_api_surface,
        _extract_method_params,
        _extract_return_type,
        _extract_doc_comment,
        _first_sentence,
        _JAVA_OBJECT_METHODS,
    )
except ImportError:
    extract_api_surface = None  # type: ignore[assignment,misc]

try:
    from extraction.outputs import write_outputs                 # noqa: E402, F401
except ImportError:
    write_outputs = None  # type: ignore[assignment,misc]

try:
    from extraction.scout import Scout                           # noqa: E402, F401
except ImportError:
    Scout = None  # type: ignore[assignment,misc]

MAX_SNIPPETS = 100
LOG = logging.getLogger("scout")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_preflight(args) -> int:
    """Check basic scout prerequisites without running extraction."""
    checks: list[tuple[str, str, str]] = []

    repo_ok = args.repo_path.is_dir()
    checks.append((
        "repo_path",
        "PASS" if repo_ok else "FAIL",
        str(args.repo_path) if repo_ok else f"Missing repository path: {args.repo_path}",
    ))

    try:
        lang = PLATFORM_TO_LANG[args.platform]
        get_parser(lang)
        checks.append(("parser", "PASS", f"Parser available for {args.platform} ({lang})"))
    except Exception as exc:  # pragma: no cover - exercised by live env
        checks.append(("parser", "FAIL", f"{type(exc).__name__}: {exc}"))

    output_parent = args.output_dir.parent
    if output_parent.exists():
        checks.append(("output_parent", "PASS", str(output_parent)))
    else:
        checks.append(("output_parent", "WARN", f"Parent directory does not exist yet: {output_parent}"))

    print("SCOUT PREFLIGHT")
    for name, status, detail in checks:
        print(f"[{status}] {name}: {detail}")

    return 0 if not any(status == "FAIL" for _, status, _ in checks) else 1


def main():
    parser = argparse.ArgumentParser(
        description="Tree-sitter extraction engine for FOSS repositories")
    parser.add_argument("family", help="Product family (e.g. 3d, cells)")
    parser.add_argument("platform",
                        choices=list(PLATFORM_TO_LANG.keys()),
                        help="Target platform")
    parser.add_argument("repo_path", type=Path,
                        help="Path to the FOSS repository")
    parser.add_argument("output_dir", type=Path,
                        help="Directory to write extraction artifacts")
    parser.add_argument("--preflight", action="store_true",
                        help="Check prerequisites and exit without extraction")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.preflight:
        sys.exit(_run_preflight(args))

    if not args.repo_path.is_dir():
        LOG.error("Repository path does not exist: %s", args.repo_path)
        sys.exit(1)

    s = Scout(args.family, args.platform, args.repo_path, args.output_dir)
    s.run()
    LOG.info("Done. Output written to %s", args.output_dir)

    # Write pipeline state manifest so promote.py / index.py can detect scout completion.
    # Deferred import avoids circular-import at module load time.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # -> pipeline/
    from core.manifest import write_step_manifest
    state_path = args.output_dir.parent / ".pipeline_state.json"
    write_step_manifest(state_path, "scout", {
        "repo_path": str(args.repo_path),
        "output_dir": str(args.output_dir),
        "class_count": len(s.classes) if hasattr(s, "classes") else 0,
        "claim_count": len(s.claims) if hasattr(s, "claims") else 0,
    })


if __name__ == "__main__":
    main()
