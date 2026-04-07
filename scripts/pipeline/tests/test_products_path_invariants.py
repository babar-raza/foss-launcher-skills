"""Regression gate: products.aspose.org path/role invariants.

These tests ensure skill files cannot silently re-introduce the wrong products
path assumption that was corrected in 2026-04. The canonical rule:

  Family landing page  → content/products.aspose.org/en/{family}/_index.md      (layout: family, /family-sync)
  Platform product page → content/products.aspose.org/en/{family}/{platform}/_index.md (layout: plugin, /new-products-page)

Tests fail immediately if any skill file:
- Claims "products pages are per-family"
- Has new-products-page writing to {family}/_index.md instead of {family}/{platform}/_index.md
- Loses the explicit guard note in new-products-page
- Has page-plan routing note referencing the wrong path
"""
from __future__ import annotations

import glob
from pathlib import Path

import pytest

from _repo_root import repo_root

_REPO_ROOT = repo_root()


def _all_skill_files() -> list[Path]:
    """Return paths of all skill/command markdown files in all 4 provider locations."""
    patterns = [
        "skills/*.md",
        ".claude/commands/*.md",
        ".agents/skills/*/SKILL.md",
        ".kilocode/skills/*/SKILL.md",
    ]
    files: list[Path] = []
    for pat in patterns:
        files.extend(Path(_REPO_ROOT).glob(pat))
    return files


def _skill_files_named(name: str) -> list[Path]:
    """Return all provider copies of a skill by base name (e.g. 'new-products-page')."""
    return [f for f in _all_skill_files() if name in f.parts[-1] or name in str(f.parent)]


# ===========================================================================
# new-products-page invariants
# ===========================================================================

class TestNewProductsPagePath:
    """new-products-page (S-61) must write to {family}/{platform}/_index.md, not {family}/_index.md."""

    @pytest.fixture(scope="class")
    def skill_files(self):
        files = _skill_files_named("new-products-page")
        assert files, "No new-products-page skill files found — provider mirrors may be missing"
        return files

    def test_new_products_page_targets_platform_path(self, skill_files):
        """Write step must reference {family}/{platform}/_index.md (not {family}/_index.md)."""
        for path in skill_files:
            content = path.read_text(encoding="utf-8")
            assert "{family}/{platform}/_index.md" in content, (
                f"{path}: missing '{{family}}/{{platform}}/_index.md' — "
                "write target may be wrong (family-only path)"
            )

    def test_new_products_page_has_family_guard(self, skill_files):
        """An explicit guard note must be present: do NOT write to the family page."""
        for path in skill_files:
            content = path.read_text(encoding="utf-8")
            has_guard = (
                "Do NOT write to" in content or
                "NOT modified" in content or
                "do not read or write the family page" in content
            )
            assert has_guard, (
                f"{path}: missing explicit guard note preventing writes to {{family}}/_index.md"
            )

    def test_new_products_page_write_step_is_platform_path(self, skill_files):
        """The Write step line must reference the platform path, not the family path."""
        for path in skill_files:
            content = path.read_text(encoding="utf-8")
            # The write destination line should say {family}/{platform}/_index.md
            # The family-only path should not appear as a write target
            # We look for the pattern that was wrong: "Write to ... {family}/_index.md"
            # but allow mentions of the family path in the guard note itself
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if "Write" in line and "products.aspose.org" in line and "{family}/_index.md" in line:
                    if "{platform}" not in line:
                        pytest.fail(
                            f"{path}:{i+1}: Write step targets family path '{{family}}/_index.md' "
                            "instead of '{{family}}/{{platform}}/_index.md'"
                        )


# ===========================================================================
# Global skill file invariants
# ===========================================================================

class TestGlobalSkillInvariants:
    """No skill file should assert that products pages are per-family."""

    def test_no_skill_claims_products_is_per_family(self):
        """The phrase 'products pages are per-family' must not appear in any skill file."""
        offenders: list[str] = []
        for path in _all_skill_files():
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            if "products pages are per-family" in content:
                offenders.append(str(path))
        assert not offenders, (
            "The following skill files contain the wrong claim 'products pages are per-family':\n"
            + "\n".join(f"  {p}" for p in offenders)
        )

    def test_no_per_family_combined_with_products_path(self):
        """No skill file should use 'per-family' in a products path context."""
        offenders: list[str] = []
        for path in _all_skill_files():
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            # Check for the specific wrong combination
            if "per-family" in content and "products.aspose.org" in content:
                # Allow it only if it's clearly in a correct context (e.g., describing family-sync)
                # Disallow if it implies the products page itself is per-family
                lines = [l for l in content.splitlines() if "per-family" in l and "products" in l]
                for line in lines:
                    # Legitimate: describing that family-sync manages the per-family page
                    if "family-sync" in line or "layout: family" in line:
                        continue
                    offenders.append(f"{path}: {line.strip()}")
        assert not offenders, (
            "Potential wrong 'per-family products' claims in skill files:\n"
            + "\n".join(f"  {p}" for p in offenders)
        )


# ===========================================================================
# page-plan routing invariants
# ===========================================================================

class TestPagePlanRouting:
    """page-plan (S-18) must describe the two-level products path correctly."""

    @pytest.fixture(scope="class")
    def skill_files(self):
        files = _skill_files_named("page-plan")
        assert files, "No page-plan skill files found"
        return files

    def test_page_plan_products_routing_mentions_platform_path(self, skill_files):
        """page-plan must describe the platform product page path (layout: plugin)."""
        for path in skill_files:
            content = path.read_text(encoding="utf-8")
            assert "{family}/{platform}" in content, (
                f"{path}: page-plan does not mention '{{family}}/{{platform}}' products path — "
                "routing description may be incomplete"
            )

    def test_page_plan_products_routing_mentions_plugin_layout(self, skill_files):
        """page-plan must reference layout: plugin for platform product pages."""
        for path in skill_files:
            content = path.read_text(encoding="utf-8")
            assert "layout: plugin" in content or "plugin" in content, (
                f"{path}: page-plan does not mention 'plugin' layout for products pages"
            )
