"""check_governance_doc_links.py — regression guard for governance-hook
remediation-doc links (H6, 2026-09-11).

Every governance PreToolUse hook under scripts/ci/hooks/ that blocks an
agent points at a remediation doc via `_gov_block`'s DOC argument
(scripts/ci/hooks/_gov_block.sh, printed as "DOC:     <path>" in the block
message). Confirmed live 2026-09-11, while diagnosing this repo's own
governance-enforcement reality (reports/skill-gaps/2026-09-11-imaging-net-
pipeline-hardening-prerequisites.md): nearly every hook cited
docs/GOVERNANCE_QUICKSTART.md and/or docs/BYPASS_REGISTRY.md, and NEITHER
file existed anywhere in the repo -- every blocked agent was pointed at a
dead link with no way to self-remediate. This check asserts every doc path
any hook script cites resolves to a real file, so this can't rot again
silently.

Usage:
    python scripts/ci/checks/check_governance_doc_links.py
    python scripts/ci/checks/check_governance_doc_links.py --json

Exit codes:
    0  every governance-doc reference resolves to a real file
    1  at least one hook points at a doc that does not exist
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_cfg_repo_root = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _cfg_repo_root
    _cfg_repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


# Matches a quoted argument that is one or more comma-separated docs/*.md
# paths, e.g. "docs/GOVERNANCE_QUICKSTART.md" or the one real multi-doc call
# site "docs/BYPASS_REGISTRY.md, docs/GOVERNANCE_QUICKSTART.md". Deliberately
# NOT a positional parse of _gov_block's argument list (that list's shape
# varies call to call, and arguments span shell line-continuations) -- any
# quoted docs/*.md-shaped string in a hook script is treated as a citation.
_DOC_REF_RE = re.compile(r'"((?:docs/[\w./-]+\.md,?\s*)+)"')


def find_doc_references(hooks_dir: "Path | None" = None) -> "dict[str, list[str]]":
    """hook filename -> sorted list of unique docs/*.md paths it cites."""
    hooks_dir = hooks_dir or (_cfg_repo_root / "scripts" / "ci" / "hooks")
    refs: "dict[str, list[str]]" = {}
    if not hooks_dir.is_dir():
        return refs
    for sh_file in sorted(hooks_dir.glob("*.sh")):
        if sh_file.name == "_gov_block.sh":
            continue  # the helper's own definition, not a caller
        text = sh_file.read_text(encoding="utf-8")
        found: "set[str]" = set()
        for match in _DOC_REF_RE.finditer(text):
            for piece in match.group(1).split(","):
                piece = piece.strip()
                if piece:
                    found.add(piece)
        if found:
            refs[sh_file.name] = sorted(found)
    return refs


def find_broken_links(hooks_dir: "Path | None" = None) -> "dict[str, list[str]]":
    """hook filename -> sorted list of doc paths it cites that don't exist."""
    broken: "dict[str, list[str]]" = {}
    for hook_name, docs in find_doc_references(hooks_dir).items():
        missing = sorted(d for d in docs if not (_cfg_repo_root / d).is_file())
        if missing:
            broken[hook_name] = missing
    return broken


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    refs = find_doc_references()
    broken = find_broken_links()

    if args.json:
        print(json.dumps({"references": refs, "broken": broken}, indent=2))
        return 1 if broken else 0

    if not broken:
        total = sum(len(v) for v in refs.values())
        print(f"OK: {total} governance-doc reference(s) across {len(refs)} hook(s), all resolve.")
        return 0

    print("BROKEN governance-doc links (hook failure messages point at files that don't exist):")
    for hook_name, missing in sorted(broken.items()):
        for doc in missing:
            print(f"  {hook_name}: {doc}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
