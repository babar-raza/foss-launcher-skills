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
from lib.install_collision_classifier import (  # noqa: E402
    classify_collision_risk, CollisionClassification,
)
from lib.install_change_budget import (  # noqa: E402
    ProposedInstallChangeVolume, check_budget, record_run,
)

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

# TC-PKG-02-08-FIX (mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION):
# additional literal command-line forms that install the SAME package as the
# primary CLI prefix above, for registries that have more than one common,
# live install idiom. package_install_literal.py (ST-054 TC-02) already
# flags nuget's PowerShell/NuGet Package Manager Console form
# (`Install-Package X`) as a finding distinct from `dotnet add package X` --
# this migrator had no matching remediation pattern for it until this fix.
# Confirmed live against email/net: 111 real findings across 37 locales, all
# in this form or the <PackageReference> XML form below; 0 files ever
# migrated. Folded into _command_pattern()'s alternation so
# _block_is_sole_command and the inline-mention counter cover it for free.
_REGISTRY_ALT_COMMAND_PREFIXES: dict[str, tuple[str, ...]] = {
    "nuget": ("Install-Package",),
}

# Same 4 registries package_install_literal.py (TC-MT015-05) audits -- Maven
# and Cargo keep their own dedicated migrator/shortcode, not this one.
_TRACKED_REGISTRY_TYPES = set(_REGISTRY_COMMAND_PREFIX)

# TC-PKG-02-08-FIX: nuget's raw csproj XML form -- `<PackageReference
# Include="X" ... />` (self-closing) or `<PackageReference Include="X" ...>
# ...</PackageReference>` (with a body) -- is a real, live alternate to the
# CLI install commands above; package_install_literal.py already flags it
# (ST-054 TC-02), remediation did not until this fix. Structurally distinct
# from a verb+token command line, so it gets its own element-level regex
# rather than joining _command_pattern()'s alternation. Doesn't anchor on
# the specific package identifier -- mirrors _command_pattern()'s own
# "structural match, not value match" philosophy: package-install.html
# renders the correct identity for the family/platform regardless of what
# literal text it's replacing.
_PACKAGE_REFERENCE_ELEMENT_RE = re.compile(
    r'<PackageReference\s+Include="[^"]+"(?:\s+Version="[^"]+")?\s*(?:/>|>.*?</PackageReference\s*>)',
    re.IGNORECASE | re.DOTALL,
)

# Loose "is there a PackageReference mention at all" match, for counting
# remaining/inline occurrences post block-pass -- mirrors
# package_install_literal.py's own second regex alternative.
_PACKAGE_REFERENCE_ANY_RE = re.compile(r'<PackageReference\s+Include="[^"]+"', re.IGNORECASE)

_IN_SCOPE_SUBSITES = ("docs.aspose.org", "blog.aspose.org", "kb.aspose.org", "products.aspose.org")

_FENCE_RE = re.compile(r"^([ \t]*)(```|~~~)([^\n]*)\n(.*?)\n[ \t]*(```|~~~)[ \t]*$", re.DOTALL | re.MULTILINE)

R_MIGRATED = "MIGRATED"
R_NOOP = "NOOP_NO_MATCH"
R_DRY_RUN = "DRY_RUN"
R_SKIPPED_PROTECTED = "SKIPPED_PROTECTED"
R_NO_REGISTRY_ENTRY = "NO_REGISTRY_ENTRY"


def _command_pattern(prefixes: "str | tuple[str, ...]") -> re.Pattern:
    """Match an install command, tolerating a trailing `--version X` flag
    (dotnet's CLI syntax, space-separated -- unlike npm's `@X`/pip's `==X`,
    which are already covered since they glue onto the package-name token
    with no space). Found live (2026-08-02, MT018 verification pass): a block
    containing exactly `dotnet add package X --version Y` was being skipped
    by _block_is_sole_command's fullmatch check and misclassified as an
    unfixable "inline mention" -- it's a perfectly safe, isolated code block,
    just with a version pin. ~1,950 occurrences repo-wide matched this exact
    recoverable pattern.

    `prefixes` may be a single string (the common case) or a tuple of
    alternate command-line forms that all install the same package (e.g.
    nuget's `dotnet add package` and `Install-Package` -- TC-PKG-02-08-FIX,
    _REGISTRY_ALT_COMMAND_PREFIXES above)."""
    if isinstance(prefixes, str):
        prefixes = (prefixes,)
    # One alternative per prefix, each with its OWN version-flag tail (see
    # _version_flag_tail): every prefix keeps the `--version X` tail
    # unchanged; only Install-Package additionally accepts PowerShell's
    # native single-dash `-Version X` (TC-PKG-02-01, 3d/net).
    alternatives = "|".join(
        re.escape(p) + r"\s+\S+" + _version_flag_tail(p) for p in prefixes
    )
    return re.compile(r"\b(?:" + alternatives + r")", re.IGNORECASE)


# TC-PKG-02-01 (mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION):
# casefolded prefixes whose real tool takes PowerShell-style SINGLE-dash
# parameters. `Install-Package X -Version Y` is the native form of that
# cmdlet (parameters are single-dash and case-insensitive); the dotnet CLI,
# pip, npm and go do not accept a single-dash `-Version`, so they must NOT
# gain it -- confirmed live against 3d/net: 35 locale copies of
# getting-started/installation.md carry a fenced block whose entire body is
# `Install-Package Aspose.3D -Version 26.1.0`, flagged by
# package_install_literal.py but never migrated.
_SINGLE_DASH_VERSION_PREFIXES = frozenset({"install-package"})


def _version_flag_tail(prefix: str) -> str:
    """Regex tail tolerating ONE trailing version flag for `prefix`:
    `--version X` for every prefix, plus `-Version X` for the PowerShell
    Install-Package cmdlet only. Optional and single -- never a blanket
    'anything after the package name' loosening."""
    if prefix.casefold() in _SINGLE_DASH_VERSION_PREFIXES:
        return r"(?:\s+--?version\s+\S+)?"
    return r"(?:\s+--version\s+\S+)?"


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


def _block_is_sole_package_reference(block_text: str) -> bool:
    """True if the fenced block's body (excluding fence lines) is ONLY a
    single `<PackageReference Include="..." .../>` XML element -- self-
    closing or with a body -- not a larger project-file listing (an
    ItemGroup wrapper, multiple references, or any other surrounding
    content). TC-PKG-02-08-FIX: same "structural safety over aggressive
    matching" bar as _block_is_sole_command, applied to the XML shape --
    unlike that function, the element can legitimately span multiple lines
    (a body-form PackageReference), so this matches the whole stripped body
    as one string rather than requiring every line to fullmatch on its own."""
    lines = block_text.splitlines()
    if len(lines) < 3:
        return False
    body = "\n".join(lines[1:-1]).strip()
    if not body:
        return False
    return _PACKAGE_REFERENCE_ELEMENT_RE.fullmatch(body) is not None


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

    registry_type = entry["registry_type"]
    prefixes = (_REGISTRY_COMMAND_PREFIX[registry_type],) + _REGISTRY_ALT_COMMAND_PREFIXES.get(registry_type, ())
    cmd_re = _command_pattern(prefixes)
    # TC-PKG-02-08-FIX: the raw csproj XML form only exists for nuget --
    # gated here rather than added to _TRACKED_REGISTRY_TYPES/prefix map
    # since it isn't a verb+token command line at all.
    check_package_reference = registry_type == "nuget"

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
        if _block_is_sole_command(block_text, cmd_re) or (
            check_package_reference and _block_is_sole_package_reference(block_text)
        ):
            text = text[: m.start()] + f"{indent}{shortcode}" + text[m.end():]
            block_count += 1

    # Count remaining inline mentions (post block-pass) for reporting --
    # never rewritten, per the module docstring.
    inline_count = len(cmd_re.findall(text))
    if check_package_reference:
        inline_count += len(_PACKAGE_REFERENCE_ANY_RE.findall(text))

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


def _locale_from_path(filepath: Path, family: str) -> str:
    """Best-effort locale extraction for install_change_budget's per-locale
    cap -- a coarse blast-radius signal, not a precision analytics tool.
    Two real conventions in this repo: docs/kb/products.aspose.org carry the
    locale as a DIRECTORY segment (content/{site}/{locale}/{family}/{platform}/...,
    "en" included); blog.aspose.org carries it as a FILENAME suffix
    (content/blog.aspose.org/{family}/{platform}/{slug}/index.md for English,
    index.{locale}.md for a translation -- confirmed by discover_files()'s
    own blog branch, which globs directly under {family}/{platform} with no
    locale-prefixed directory tier at all)."""
    parts = filepath.parts
    try:
        content_idx = parts.index("content")
    except ValueError:
        return "en"
    if len(parts) <= content_idx + 2:
        return "en"
    site = parts[content_idx + 1]
    if site == "blog.aspose.org":
        name_parts = filepath.name.split(".")
        if len(name_parts) >= 3:  # e.g. "index.fr.md" -> ["index", "fr", "md"]
            return name_parts[-2]
        return "en"
    segment = parts[content_idx + 2]
    return "en" if segment == family else segment


def _run_pass(files: list[Path], family: str, platform: str, *, dry_run: bool, registry: dict) -> dict[str, Any]:
    summary: dict[str, Any] = {
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


def run_migration(
    family: str, platform: str, *, dry_run: bool = True, limit: "int | None" = None,
    registry: dict | None = None, respect_collision_gate: bool = True, force: bool = False,
    respect_change_budget: bool = True,
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
                "block_replacements": 0, "inline_mentions_found": 0,
                "skipped_protected": 0, "no_registry_entry": 0, "results": [],
                "collision_gate_blocked": True,
                "collision_classification": collision_result.classification.value,
                "collision_reason": collision_result.reason,
                "budget_blocked": False,
            }

    files = discover_files(family, platform)
    if limit is not None:
        files = files[:limit]

    # Probe pass (always dry-run, regardless of the caller's real dry_run
    # intent) so the change-budget check sees the REAL proposed volume --
    # files that would actually be migrated, not the raw candidate count
    # discover_files() returns (most of which are typically R_NOOP/
    # R_NO_REGISTRY_ENTRY and never touched at all).
    probe = _run_pass(files, family, platform, dry_run=True, registry=reg)

    budget_verdict = None
    if respect_change_budget and not force:
        migrated_files = [
            fp for fp, res in zip(files, probe["results"])
            if res["result"] in (R_MIGRATED, R_DRY_RUN)
        ]
        files_by_locale: dict[str, int] = {}
        for fp in migrated_files:
            loc = _locale_from_path(fp, family)
            files_by_locale[loc] = files_by_locale.get(loc, 0) + 1
        volume = ProposedInstallChangeVolume(
            total_files=len(migrated_files), files_by_locale=files_by_locale,
        )
        budget_verdict = check_budget(family, "mechanical_migration", volume)
        if not budget_verdict.allowed:
            return {
                "family": family, "platform": platform, "dry_run": dry_run,
                "files_checked": len(files), "files_migrated": 0,
                "block_replacements": 0, "inline_mentions_found": 0,
                "skipped_protected": 0, "no_registry_entry": 0, "results": [],
                "collision_gate_blocked": False,
                "collision_classification": collision_result.classification.value if collision_result else None,
                "budget_blocked": True,
                "budget_reason": budget_verdict.reason,
                "budget_static_cap_violations": budget_verdict.static_cap_violations,
                "budget_anomaly_status": budget_verdict.anomaly_status,
            }

    if dry_run:
        summary = probe
    else:
        summary = _run_pass(files, family, platform, dry_run=False, registry=reg)
        if respect_change_budget and not force:
            record_run(family, "mechanical_migration", summary["files_migrated"])

    summary.update({
        "family": family, "platform": platform, "dry_run": dry_run,
        "collision_gate_blocked": False,
        "collision_classification": collision_result.classification.value if collision_result else None,
        "budget_blocked": False,
        "budget_anomaly_status": budget_verdict.anomaly_status if budget_verdict else None,
    })
    return summary


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="package_install_migrator")
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
        print(f"=== package_install_migrator [BLOCKED] {args.family}/{args.platform} ===")
        print(f"collision_classification: {summary['collision_classification']}")
        print(f"reason: {summary['collision_reason']}")
        print("Refusing to migrate -- pass --force only after manual verification.")
        return 1

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
