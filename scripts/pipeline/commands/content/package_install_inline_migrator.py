"""package_install_inline_migrator.py — ST-054 TC-06
(plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md).

Sibling of package_install_migrator.py (Mission MT015 TC-MT015-09): rewrites
an INLINE, single-backtick-wrapped install-command mention -- e.g. "Run
`dotnet add package Aspose.Slides.Foss` to install it" inside prose -- with
the package-install-inline shortcode (ST-054 TC-01:
`{{< package-install-inline "family" "platform" >}}`), for pypi/nuget/npm/
go_modules entries. Maven/Cargo already have maven-gav.html's own inline
form; out of scope here, same as the block-level migrator.

Deliberately narrow scope, mirroring package_install_migrator.py's own
safety posture:
- Only a SINGLE-backtick inline code span (`` `...` ``) whose entire content
  (backticks stripped) IS an install-command line -- pip install X /
  dotnet add package X / Install-Package X (nuget's PowerShell Package
  Manager Console alternate form, ST-054 TC-02) / npm install X / go get X,
  tolerating a trailing `--version X` flag exactly like
  package_install_migrator.py's own _command_pattern(). A span that merely
  *contains* the command alongside other text (not a fullmatch) is left
  alone and counted as unmatched -- ambiguous prose is a human/S-73 call,
  not this migrator's.
- Never touches a `<PackageReference Include="...">` mention -- that shape
  is raw multi-line .csproj XML, structurally a fenced-block artifact
  (package_install_migrator.py's own scope when it's the sole content of a
  block), not a natural inline mid-sentence mention this shortcode fits.
- Never touches text inside a fenced code block (``` or ~~~) -- computed via
  the same _FENCE_RE package_install_migrator.py uses, imported directly so
  the two migrators can never drift on what counts as "inside a fence."
  This means the two migrators can run back-to-back over the same file with
  no double-processing risk: the block migrator only ever touches fenced
  regions, this one only ever touches text outside them.
- English source only (ST-054 TC-07 handles locale propagation separately,
  via S-75) -- discover_files_english_only() below, not
  package_install_migrator.py's all-locales discover_files().
- Never migrates a COLLISION_RISK product -- PKGINSTALL-COLLISION-CLASSIFIER
  (2026-09-10) closed the gap this line used to document: run_migration()
  now calls install_collision_classifier.classify_collision_risk() itself
  and refuses to touch any file unless the result is
  SAFE_FOR_MECHANICAL_MIGRATION/NOT_APPLICABLE or --force is passed. The
  static ST-054 TC-05 Markdown report this classifier codifies is no longer
  the only thing standing between this migrator and a real corruption risk.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.package_install_inline_migrator pdf go --dry-run
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.package_install_inline_migrator pdf go --execute
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.package_install_inline_migrator pdf go --execute --limit 20
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
from commands.content.package_install_migrator import (  # noqa: E402
    _FENCE_RE,
    _command_pattern,
)
from audit.package_install_literal import _is_noise_line  # noqa: E402
from lib.install_collision_classifier import (  # noqa: E402
    classify_collision_risk, CollisionClassification,
)

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTENT_ROOT = _REPO_ROOT / "content"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT, _CONTENT_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTENT_ROOT = _REPO_ROOT / "content"


# registry_type -> the inline command prefix(es) this shortcode covers.
# nuget gets both its normal CLI form and the PowerShell Package Manager
# Console alternate form (ST-054 TC-02) -- both are real, live .NET patterns.
_REGISTRY_COMMAND_PREFIXES = {
    "pypi": ["pip install"],
    "nuget": ["dotnet add package", "Install-Package"],
    "npm": ["npm install"],
    "go_modules": ["go get"],
}

_TRACKED_REGISTRY_TYPES = set(_REGISTRY_COMMAND_PREFIXES)

_IN_SCOPE_SUBSITES = ("docs.aspose.org", "blog.aspose.org", "kb.aspose.org", "products.aspose.org")

# blog.aspose.org has no locale directories -- locale copies are
# filename-suffixed instead (e.g. index.fr.md); same pattern
# install_block_updater.py's own English-only guard uses.
_LOCALE_SUFFIX_RE = re.compile(r"\.[a-z]{2}(?:-[a-z0-9]{2,4})?\.md$", re.IGNORECASE)

_INLINE_SPAN_RE = re.compile(r"`([^`\n]+)`")

R_MIGRATED = "MIGRATED"
R_NOOP = "NOOP_NO_MATCH"
R_DRY_RUN = "DRY_RUN"
R_SKIPPED_PROTECTED = "SKIPPED_PROTECTED"
R_NO_REGISTRY_ENTRY = "NO_REGISTRY_ENTRY"


def _fenced_spans(text: str) -> list[tuple[int, int]]:
    """Character-offset (start, end) spans covered by a fenced code block --
    reused so this migrator never touches the same text
    package_install_migrator.py's block-replacement pass owns."""
    return [(m.start(), m.end()) for m in _FENCE_RE.finditer(text)]


def _inside_any(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def _containing_line(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return text[start:end]


def migrate_file(
    filepath: Path, family: str, platform: str, *, dry_run: bool = True, registry: dict | None = None,
) -> dict[str, Any]:
    """Replace inline single-backtick install-command spans with the
    package-install-inline shortcode.

    Never partially writes -- either the full transform (all qualifying
    spans) is applied, or nothing is written."""
    result: dict[str, Any] = {
        "path": str(filepath), "result": R_NOOP,
        "inline_replacements": 0, "error": "",
    }

    data = registry if registry is not None else load_registry()
    entry = data.get(family, {}).get(platform)
    if not entry or entry.get("registry_type") not in _TRACKED_REGISTRY_TYPES:
        result["result"] = R_NO_REGISTRY_ENTRY
        result["error"] = f"no data/package_registry.json entry for {family}/{platform} with a tracked registry_type"
        return result

    if not filepath.is_file():
        result["error"] = "file not found"
        return result

    prefixes = _REGISTRY_COMMAND_PREFIXES[entry["registry_type"]]
    cmd_patterns = [_command_pattern(p) for p in prefixes]

    original = filepath.read_text(encoding="utf-8", errors="replace")
    text = original
    shortcode = f'{{{{< package-install-inline "{family}" "{platform}" >}}}}'

    fenced = _fenced_spans(text)
    matches = list(_INLINE_SPAN_RE.finditer(text))
    replacements = 0
    for m in reversed(matches):
        if _inside_any(m.start(), fenced):
            continue  # owned by package_install_migrator.py's block pass
        if _is_noise_line(_containing_line(text, m.start())):
            # Same guard package_install_literal.py uses (ST-054 regression
            # pin, content/kb.aspose.org/en/words/net/troubleshooting.md): a
            # heading like "### `dotnet add package X` cannot find the
            # package" explains the command DOESN'T work -- it is not an
            # install instruction, and replacing it with the live shortcode
            # would render a self-contradicting heading once the package is
            # actually published (the correct command would then "find the
            # package" the heading claims it can't).
            continue
        span_content = m.group(1).strip()
        if any(pat.fullmatch(span_content) for pat in cmd_patterns):
            text = text[: m.start()] + shortcode + text[m.end():]
            replacements += 1

    result["inline_replacements"] = replacements

    if replacements == 0:
        result["result"] = R_NOOP
        return result

    if dry_run:
        result["result"] = R_DRY_RUN
        return result

    try:
        safe_content_write(filepath, text, mechanism="package-install-inline-migrator")
    except ProtectedPageError:
        result["result"] = R_SKIPPED_PROTECTED
        return result

    result["result"] = R_MIGRATED
    return result


def discover_files_english_only(family: str, platform: str) -> list[Path]:
    """Find every ENGLISH-source content file for family/platform across
    in-scope subsites. Locale copies (locale directories on docs/kb/products,
    locale-suffixed filenames on blog) are explicitly excluded -- ST-054
    TC-07 propagates to them separately, via S-75, not this migrator."""
    files: list[Path] = []
    for subsite in _IN_SCOPE_SUBSITES:
        base = _CONTENT_ROOT / subsite
        if subsite == "blog.aspose.org":
            search_root = base / family / platform
            if search_root.is_dir():
                files.extend(
                    p for p in search_root.rglob("*.md")
                    if not _LOCALE_SUFFIX_RE.search(p.name)
                )
            continue
        target = base / "en" / family / platform
        if target.is_dir():
            files.extend(p for p in target.rglob("*.md"))
    return sorted(set(files))


def run_migration(
    family: str, platform: str, *, dry_run: bool = True, limit: "int | None" = None,
    registry: dict | None = None, respect_collision_gate: bool = True, force: bool = False,
) -> dict[str, Any]:
    reg = registry if registry is not None else load_registry()

    collision_result = None
    if respect_collision_gate and not force:
        collision_result = classify_collision_risk(family, platform, registry=reg)
        if collision_result.classification not in (
            CollisionClassification.SAFE_FOR_MECHANICAL_MIGRATION,
            CollisionClassification.NOT_APPLICABLE,
        ):
            return {
                "family": family, "platform": platform, "dry_run": dry_run,
                "files_checked": 0, "files_migrated": 0,
                "inline_replacements": 0, "skipped_protected": 0,
                "no_registry_entry": 0, "results": [],
                "collision_gate_blocked": True,
                "collision_classification": collision_result.classification.value,
                "collision_reason": collision_result.reason,
            }

    files = discover_files_english_only(family, platform)
    if limit is not None:
        files = files[:limit]

    summary: dict[str, Any] = {
        "family": family, "platform": platform, "dry_run": dry_run,
        "files_checked": len(files), "files_migrated": 0,
        "inline_replacements": 0, "skipped_protected": 0,
        "no_registry_entry": 0, "results": [],
        "collision_gate_blocked": False,
        "collision_classification": collision_result.classification.value if collision_result else None,
    }

    for fp in files:
        res = migrate_file(fp, family, platform, dry_run=dry_run, registry=reg)
        summary["results"].append(res)
        summary["inline_replacements"] += res["inline_replacements"]
        if res["result"] in (R_MIGRATED, R_DRY_RUN):
            summary["files_migrated"] += 1
        elif res["result"] == R_SKIPPED_PROTECTED:
            summary["skipped_protected"] += 1
        elif res["result"] == R_NO_REGISTRY_ENTRY:
            summary["no_registry_entry"] += 1

    return summary


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="package_install_inline_migrator")
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--force", action="store_true",
        help="Bypass the collision-safety gate (PKGINSTALL-COLLISION-CLASSIFIER) -- "
             "only for a product already manually verified safe despite a "
             "COLLISION_RISK_* classification. Never pass this by default.",
    )
    args = parser.parse_args(argv)

    dry_run = not args.execute
    summary = run_migration(
        args.family, args.platform, dry_run=dry_run, limit=args.limit, force=args.force,
    )

    if summary.get("collision_gate_blocked"):
        print(f"=== package_install_inline_migrator [BLOCKED] {args.family}/{args.platform} ===")
        print(f"collision_classification: {summary['collision_classification']}")
        print(f"reason: {summary['collision_reason']}")
        print("Refusing to migrate -- pass --force only after manual verification.")
        return 1

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"=== package_install_inline_migrator [{mode}] {args.family}/{args.platform} ===")
    print(f"files_checked: {summary['files_checked']}")
    print(f"files_migrated: {summary['files_migrated']}")
    print(f"inline_replacements: {summary['inline_replacements']}")
    print(f"skipped_protected: {summary['skipped_protected']}")
    print(f"no_registry_entry: {summary['no_registry_entry']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
