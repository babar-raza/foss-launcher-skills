"""Tests for TC-PSD-HRD-07: launch-product.md must have a .NET/NuGet platform-notes section
(it previously had TypeScript notes only) that discloses the known, already-filed
NET-OPERATOR-OVERLOAD-001 gap -- confirmed live to affect psd/net specifically (8 real public
`operator ==`/`operator !=` overloads on Point/Rectangle/RectangleF/Size, 0 of which appear in
`knowledge/psd/net/merged/api_surface.json`).

A content/doc-assertion test, the same style this repo already uses for skill-doc parity
(test_skill_contract_paths.py) -- there is no code-level fix for this card (G-24, the other named
sub-hypothesis, did not reproduce for psd/net's own clean single-PropertyGroup csproj; see
evidence/decisions/hrd-07-01-investigate.md), so the test asserts the real doc content rather
than a function's return value.
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LAUNCH_PRODUCT_MD = _REPO_ROOT / "skills" / "launch-product.md"


def _text() -> str:
    return _LAUNCH_PRODUCT_MD.read_text(encoding="utf-8")


def test_net_nuget_platform_notes_section_exists():
    text = _text()
    assert "### Platform notes — .NET/NuGet" in text, (
        "launch-product.md has no .NET/NuGet platform-notes section (TC-PSD-HRD-07's own "
        "defect: TypeScript notes only)"
    )


def test_net_nuget_section_discloses_operator_overload_gap():
    text = _text()
    idx = text.index("### Platform notes — .NET/NuGet")
    # Section body runs until the next "---" separator or the next "### " heading.
    rest = text[idx:]
    end = min(
        (rest.index(marker) for marker in ("\n---", "\n### ") if marker in rest[3:]),
        default=len(rest),
    )
    section = rest[:end]
    assert "NET-OPERATOR-OVERLOAD-001" in section, (
        "the .NET/NuGet platform-notes section exists but does not disclose the confirmed "
        "NET-OPERATOR-OVERLOAD-001 gap (operator overloads invisible to extraction)"
    )


def test_net_nuget_section_names_the_install_shortcode():
    text = _text()
    idx = text.index("### Platform notes — .NET/NuGet")
    rest = text[idx:]
    end = min(
        (rest.index(marker) for marker in ("\n---", "\n### ") if marker in rest[3:]),
        default=len(rest),
    )
    section = rest[:end]
    assert "package-install" in section, (
        "the .NET/NuGet platform-notes section does not name the package-install shortcode "
        "convention (same rule the TypeScript section already states for npm)"
    )


def test_mirrors_stay_in_parity_after_the_edit():
    """Regression: the canonical skills/launch-product.md and its provider mirrors must carry
    the same new section (sync_providers.py is the fix tool; this just pins the observable
    outcome for the .claude/commands mirror specifically, the one HRD-02-05 already touched)."""
    mirror = _REPO_ROOT / ".claude" / "commands" / "launch-product.md"
    mirror_text = mirror.read_text(encoding="utf-8")
    assert "### Platform notes — .NET/NuGet" in mirror_text
    assert "NET-OPERATOR-OVERLOAD-001" in mirror_text
