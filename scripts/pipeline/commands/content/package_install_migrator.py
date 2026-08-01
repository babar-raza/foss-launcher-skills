"""package_install_migrator.py — Mission MT015-2026-07-30-PACKAGE-REGISTRY, TC-MT015-09.

Generic sibling of maven_shortcode_migrator.py (Mission MT008), for the 4
registries package-install.html covers (pypi, nuget, npm, go_modules).
Deferred at TC-MT015-05 time ("not proportionate to build a full generalized
codemod for one file") -- the SLIDES-NET-NUGET-001 discovery (1296 files, all
locales) is exactly the "more literal-text instances" scale that scope note
named as the trigger for building this for real.

Scope, deliberately narrower than the Maven migrator: only replaces a FENCED
CODE BLOCK whose entire content is a single literal install-command line
(the common, structurally-clean case -- e.g. a ```shell / ```powershell /
```bash block containing exactly `dotnet add package X` or `pip install X`).
package-install.html renders a BLOCK-level element (<pre><code>...</code></pre>
when published, an <em>...</em> notice when not) -- it is not designed to sit
inline mid-sentence the way maven-gav.html is. An INLINE backtick-wrapped
mention (e.g. "Run `dotnet add package Aspose.Slides.Foss`" inside an FAQ
answer) is therefore NOT auto-migrated: silently text-substituting it would
either mangle the HTML (nesting a <pre> mid-paragraph) or require guessing at
replacement prose per file, both worse than flagging it for a human S-73 pass.
Every inline mention found is reported, never silently dropped.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.package_install_migrator slides net --dry-run
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.package_install_migrator slides net --execute
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.package_install_migrator slides net --execute --limit 20
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from lib.provenance import safe_content_write, ProtectedPageError  # noqa: E402
from lib.package_registry_data import load_registry  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTENT_ROOT = _REPO_ROOT / "content"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT, _CONTENT_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTENT_ROOT = _REPO_ROOT / "content"


# registry_type -> the CLI command prefix package-install.html renders for it
# (must match layouts/shortcodes/package-install.html exactly).
_REGISTRY_COMMAND_PREFIX = {
    "pypi": "pip install",
    "nuget": "dotnet add package",
    "npm": "npm install",
    "go_modules": "go get",
}

# Same 4 registries package_install_literal.py (TC-MT015-05) audits -- Maven
# and Cargo keep their own dedicated migrator/shortcode, not this one.
_TRACKED_REGISTRY_TYPES = set(_REGISTRY_COMMAND_PREFIX)

_IN_SCOPE_SUBSITES = ("docs.aspose.org", "blog.aspose.org", "kb.aspose.org", "products.aspose.org")

_FENCE_RE = re.compile(r"^([ \t]*)(```|~~~)([^\n]*)\n(.*?)\n[ \t]*(```|~~~)[ \t]*$", re.DOTALL | re.MULTILINE)

R_MIGRATED = "MIGRATED"
R_NOOP = "NOOP_NO_MATCH"
R_DRY_RUN = "DRY_RUN"
R_SKIPPED_PROTECTED = "SKIPPED_PROTECTED"
R_NO_REGISTRY_ENTRY = "NO_REGISTRY_ENTRY"


def _command_pattern(prefix: str) -> re.Pattern:
    """Match an install command, tolerating a trailing `--version X` flag
    (dotnet's CLI syntax, space-separated -- unlike npm's `@X`/pip's `==X`,
    which are already covered since they glue onto the package-name token
    with no space). Found live (2026-08-02, MT018 verification pass): a block
    containing exactly `dotnet add package X --version Y` was being skipped
    by _block_is_sole_command's fullmatch check and misclassified as an
    unfixable "inline mention" -- it's a perfectly safe, isolated code block,
    just with a version pin. ~1,950 occurrences repo-wide matched this exact
    recoverable pattern."""
    return re.compile(
        r"\b" + re.escape(prefix) + r"\s+\S+(?:\s+--version\s+\S+)?", re.IGNORECASE,
    )


def _block_is_sole_command(block_text: str, cmd_re: re.Pattern) -> bool:
    """True if the fenced block's body (excluding fence lines) is ONLY the
    install command (plus optional blank lines) -- not a multi-step snippet
    that happens to mention the command among other content."""
    lines = block_text.splitlines()
    if len(lines) < 3:
        return False
    body = lines[1:-1]
    non_blank = [ln for ln in body if ln.strip()]
    if not non_blank:
        return False
    return all(cmd_re.fullmatch(ln.strip()) for ln in non_blank)


def migrate_file(filepath: Path, family: str, platform: str, *, dry_run: bool = True, registry: dict | None = None) -> dict[str, Any]:
    """Replace sole-command fenced blocks with the package-install shortcode.

    Never partially writes -- either the full transform (all qualifying
    blocks) is applied, or nothing is written. Inline backtick mentions are
    counted and reported but never rewritten (see module docstring)."""
    result: dict[str, Any] = {
        "path": str(filepath), "result": R_NOOP,
        "block_replacements": 0, "inline_mentions_found": 0, "error": "",
    }

    data = registry if registry is not None else load_registry()
    entry = data.get(family, {}).get(platform)
    if not entry or entry.get("registry_type") not in _TRACKED_REGISTRY_TYPES:
        result["result"] = R_NO_REGISTRY_ENTRY
        result["error"] = f"no data/package_registry.json entry for {family}/{platform} with a tracked registry_type"
        return result

    prefix = _REGISTRY_COMMAND_PREFIX[entry["registry_type"]]
    cmd_re = _command_pattern(prefix)

    if not filepath.is_file():
        result["error"] = "file not found"
        return result

    original = filepath.read_text(encoding="utf-8", errors="replace")
    text = original
    shortcode = f'{{{{< package-install "{family}" "{platform}" >}}}}'

    blocks = list(_FENCE_RE.finditer(text))
    block_count = 0
    for m in reversed(blocks):
        block_text = m.group(0)
        indent = m.group(1)
        if _block_is_sole_command(block_text, cmd_re):
            text = text[: m.start()] + f"{indent}{shortcode}" + text[m.end():]
            block_count += 1

    # Count remaining inline mentions (post block-pass) for reporting --
    # never rewritten, per the module docstring.
    inline_count = len(cmd_re.findall(text))

    result["block_replacements"] = block_count
    result["inline_mentions_found"] = inline_count

    if block_count == 0:
        result["result"] = R_NOOP
        return result

    if dry_run:
        result["result"] = R_DRY_RUN
        return result

    try:
        safe_content_write(filepath, text, mechanism="package-install-migrator")
    except ProtectedPageError:
        result["result"] = R_SKIPPED_PROTECTED
        return result

    result["result"] = R_MIGRATED
    return result


def discover_files(family: str, platform: str) -> list[Path]:
    """Find every content file for family/platform across in-scope subsites,
    all locales. reference.aspose.org is excluded -- same rationale as
    maven_shortcode_migrator.py (auto-generated per-class API pages carry no
    install snippets)."""
    files: list[Path] = []
    for subsite in _IN_SCOPE_SUBSITES:
        base = _CONTENT_ROOT / subsite
        if subsite == "blog.aspose.org":
            search_root = base / family / platform
            if search_root.is_dir():
                files.extend(p for p in search_root.rglob("*.md"))
            continue
        if not base.is_dir():
            continue
        for locale_dir in base.iterdir():
            if not locale_dir.is_dir():
                continue
            target = locale_dir / family / platform
            if target.is_dir():
                files.extend(p for p in target.rglob("*.md"))
    return sorted(set(files))


def run_migration(family: str, platform: str, *, dry_run: bool = True, limit: "int | None" = None, registry: dict | None = None) -> dict[str, Any]:
    files = discover_files(family, platform)
    if limit is not None:
        files = files[:limit]

    summary: dict[str, Any] = {
        "family": family, "platform": platform, "dry_run": dry_run,
        "files_checked": len(files), "files_migrated": 0,
        "block_replacements": 0, "inline_mentions_found": 0,
        "skipped_protected": 0, "no_registry_entry": 0, "results": [],
    }

    for fp in files:
        res = migrate_file(fp, family, platform, dry_run=dry_run, registry=registry)
        summary["results"].append(res)
        summary["block_replacements"] += res["block_replacements"]
        summary["inline_mentions_found"] += res["inline_mentions_found"]
        if res["result"] in (R_MIGRATED, R_DRY_RUN):
            summary["files_migrated"] += 1
        elif res["result"] == R_SKIPPED_PROTECTED:
            summary["skipped_protected"] += 1
        elif res["result"] == R_NO_REGISTRY_ENTRY:
            summary["no_registry_entry"] += 1

    return summary


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="package_install_migrator")
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    dry_run = not args.execute
    summary = run_migration(args.family, args.platform, dry_run=dry_run, limit=args.limit)

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"=== package_install_migrator [{mode}] {args.family}/{args.platform} ===")
    print(f"files_checked: {summary['files_checked']}")
    print(f"files_migrated: {summary['files_migrated']}")
    print(f"block_replacements: {summary['block_replacements']}")
    print(f"inline_mentions_found (NOT auto-migrated, needs manual S-73 review): {summary['inline_mentions_found']}")
    print(f"skipped_protected: {summary['skipped_protected']}")
    print(f"no_registry_entry: {summary['no_registry_entry']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
