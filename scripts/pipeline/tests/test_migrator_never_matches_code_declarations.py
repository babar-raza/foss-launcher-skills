"""ST-054 TC-18 (plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md).

Promotes reports/audit/st-054-collision-classification-2026-08-16.md's own
prose caveat into an enforced invariant instead of a one-time hand
classification: that report flags 9 products COLLISION_RISK (a registry
candidate identifier that normalizes to the same thing as a real in-code
declaration, e.g. cells/net's NuGet ID `Aspose.Cells.FOSS` vs. the real C#
namespace `Aspose.Cells_FOSS`), then in its own text argues 8 of the 9
(every pypi hit) are actually safe for the mechanical migrators, because
those migrators only ever match text anchored to a literal install-command
prefix (`pip install `, `dotnet add package `, `Install-Package `,
`npm install `, `go get `) -- which never appears before a bare `import`/
`using`/`namespace` declaration in real code.

That argument was correct reasoning but never verified against real source,
and never became anything a future classification pass is forced to trust
instead of re-deriving by hand. This module verifies it directly: for every
COLLISION_RISK product, extract real declaration lines from the actual
`runs/.clone_cache/` source (not synthetic reproductions) and assert neither
migrator's matching logic -- `_command_pattern()` (package_install_migrator.py,
reused unchanged by package_install_inline_migrator.py) nor
`_INSTALL_CMD_RE` (audit/package_install_literal.py) -- ever matches one,
wrapped in a single-backtick span or bare. If this test ever needs to be
loosened, that is itself the signal a future registry_type genuinely needs
`cells/net`-style manual review, not a hand re-classification.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from audit.package_install_literal import _INSTALL_CMD_RE  # noqa: E402
from commands.content.package_install_migrator import _command_pattern  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLONE_CACHE = _REPO_ROOT / "runs" / ".clone_cache"

# The 9 products reports/audit/st-054-collision-classification-2026-08-16.md
# flags COLLISION_RISK, their clone-cache directory name, source language,
# and the install-command prefix(es) their registry_type maps to
# (package_install_inline_migrator.py's _REGISTRY_COMMAND_PREFIXES).
_COLLISION_RISK_PRODUCTS = [
    # (family, platform, clone_cache_dir, language, prefixes)
    ("barcode", "python", "aspose_barcode_python", "python", ["pip install"]),
    ("cells", "net", "aspose_cells_net", "csharp", ["dotnet add package", "Install-Package"]),
    ("cells", "python", "aspose_cells_python", "python", ["pip install"]),
    ("email", "python", "aspose_email_python", "python", ["pip install"]),
    ("font", "python", "aspose_font_python", "python", ["pip install"]),
    ("note", "python", "aspose_note_python", "python", ["pip install"]),
    ("slides", "python", "aspose_slides_python", "python", ["pip install"]),
    ("tex", "python", "aspose_tex_python", "python", ["pip install"]),
    ("words", "python", "aspose_words_python", "python", ["pip install"]),
]

_CSHARP_DECL_RE = re.compile(r"^\s*(using|namespace)\s+[\w.]+\s*[;{]?\s*$")
_PYTHON_DECL_RE = re.compile(r"^\s*(import|from)\s+[\w.]+")

_EXCLUDE_DIRS = {".git", "bin", "obj", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}


def _iter_source_files(clone_dir: Path, extension: str):
    for path in clone_dir.rglob(f"*{extension}"):
        if any(part in _EXCLUDE_DIRS for part in path.parts):
            continue
        yield path


def _collect_declaration_lines(clone_dir: Path, language: str, *, max_files: int = 4000) -> list[str]:
    """Real using/namespace (C#) or import/from (Python) declaration lines,
    deduplicated, from the actual clone-cache checkout -- not a synthetic
    reproduction. Bounded by max_files as a safety valve against a
    pathologically large checkout, not because this repo's FOSS product repos
    are expected to hit it (largest seen in TC-05's own scan: ~3,100
    identifiers for pdf/go)."""
    extension = ".cs" if language == "csharp" else ".py"
    decl_re = _CSHARP_DECL_RE if language == "csharp" else _PYTHON_DECL_RE
    lines: set[str] = set()
    for n, path in enumerate(_iter_source_files(clone_dir, extension)):
        if n >= max_files:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if decl_re.match(line):
                lines.add(line.strip())
    return sorted(lines)


def _cmd_res_for(prefixes: list[str]) -> list[re.Pattern]:
    return [_command_pattern(p) for p in prefixes]


@pytest.mark.parametrize(
    "family,platform,clone_dir_name,language,prefixes", _COLLISION_RISK_PRODUCTS,
    ids=[f"{f}-{p}" for f, p, *_ in _COLLISION_RISK_PRODUCTS],
)
def test_no_real_declaration_fullmatches_the_inline_migrator_command_pattern(
    family, platform, clone_dir_name, language, prefixes,
):
    """The inline migrator (package_install_inline_migrator.py) only ever
    replaces a single-backtick span whose ENTIRE stripped content fullmatches
    one of these compiled patterns -- if a real declaration line can never
    fullmatch, the migrator structurally cannot corrupt it, regardless of how
    visually similar the registry candidate and the real identifier are."""
    clone_dir = _CLONE_CACHE / clone_dir_name
    if not clone_dir.is_dir():
        pytest.skip(f"clone cache not present: {clone_dir}")

    declarations = _collect_declaration_lines(clone_dir, language)
    if not declarations:
        pytest.skip(f"no {language} declaration lines found under {clone_dir} (unexpected but not this test's failure mode)")

    cmd_res = _cmd_res_for(prefixes)
    offenders = [
        decl for decl in declarations
        if any(pat.fullmatch(decl) for pat in cmd_res)
    ]
    assert offenders == [], (
        f"{family}/{platform}: {len(offenders)} real declaration line(s) from "
        f"{clone_dir_name} fullmatch an install-command pattern -- the inline "
        f"migrator could touch these. Sample: {offenders[:5]}"
    )


@pytest.mark.parametrize(
    "family,platform,clone_dir_name,language,prefixes", _COLLISION_RISK_PRODUCTS,
    ids=[f"{f}-{p}" for f, p, *_ in _COLLISION_RISK_PRODUCTS],
)
def test_no_real_declaration_matches_the_audit_detector(
    family, platform, clone_dir_name, language, prefixes,
):
    """audit/package_install_literal.py's _INSTALL_CMD_RE is the detector
    that DRIVES every sweep count and taskcard evidence in this campaign -- if
    it ever matched a bare code declaration (not just an install command), a
    documentation page showing real `using`/`import` sample code would be a
    false positive, and worse, a future 'fix' based on that false finding
    could touch real code text. Confirms the detector, not just the migrator,
    is anchored to command syntax."""
    clone_dir = _CLONE_CACHE / clone_dir_name
    if not clone_dir.is_dir():
        pytest.skip(f"clone cache not present: {clone_dir}")

    declarations = _collect_declaration_lines(clone_dir, language)
    if not declarations:
        pytest.skip(f"no {language} declaration lines found under {clone_dir}")

    offenders = [decl for decl in declarations if _INSTALL_CMD_RE.search(decl)]
    assert offenders == [], (
        f"{family}/{platform}: {len(offenders)} real declaration line(s) from "
        f"{clone_dir_name} match _INSTALL_CMD_RE. Sample: {offenders[:5]}"
    )


def test_cells_net_specifically_the_named_precedent_is_covered():
    """The one product reports/audit/st-054-collision-classification-2026-08-16.md
    calls a GENUINE structural collision, not a benign packaging-convention
    hit -- ground-truth-verified in that report against
    runs/.clone_cache/aspose_cells_net/samples/*/Program.cs. This test exists
    so a future edit to _COLLISION_RISK_PRODUCTS above cannot silently drop
    cells/net's coverage without a visible, named failure."""
    names = {(f, p) for f, p, *_ in _COLLISION_RISK_PRODUCTS}
    assert ("cells", "net") in names


def test_synthetic_cells_net_using_declaration_does_not_fullmatch_dotnet_add_package():
    """Fast, no-clone-cache-required pin of the exact confirmed real pair
    (candidate `Aspose.Cells.FOSS` vs. real namespace `Aspose.Cells_FOSS`) --
    survives even in an environment with no clone cache checked out, unlike
    the parametrized tests above which skip in that case."""
    cmd_res = _cmd_res_for(["dotnet add package", "Install-Package"])
    for decl in ("using Aspose.Cells_FOSS;", "namespace Aspose.Cells_FOSS"):
        assert not any(pat.fullmatch(decl) for pat in cmd_res), decl
        assert not _INSTALL_CMD_RE.search(decl), decl


def test_synthetic_pypi_import_declarations_do_not_fullmatch_pip_install():
    """Same fast pin for the 8 pypi cases' shared shape (distribution name
    vs. import name divergence) -- a bare `import X` line must never
    fullmatch `pip install X`."""
    cmd_res = _cmd_res_for(["pip install"])
    for decl in ("import aspose_note", "from aspose.cells_foss import Workbook", "import aspose_barcode_foss"):
        assert not any(pat.fullmatch(decl) for pat in cmd_res), decl
        assert not _INSTALL_CMD_RE.search(decl), decl
