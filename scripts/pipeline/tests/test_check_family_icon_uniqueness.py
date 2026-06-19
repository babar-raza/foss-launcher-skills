"""Unit tests for check_family_icon_uniqueness.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_CI_CHECKS = Path(__file__).resolve().parent.parent.parent / "ci" / "checks"
if str(_CI_CHECKS) not in sys.path:
    sys.path.insert(0, str(_CI_CHECKS))

from check_family_icon_uniqueness import _parse_frontmatter, _print_unused_suggestions  # noqa: E402


def _tmp_md(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".md", mode="w", encoding="utf-8", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# Minimal icon name set for testing (avoids loading the real icons.yaml)
_ICONS = {"cube", "table", "mail", "document-report", "beaker", "newspaper",
          "document-text", "pencil-alt", "presentation-chart-bar", "font",
          "star", "fire", "globe"}

# Minimal family_icons map for testing
_FAMILY_ICONS = {
    "3d": "cube",
    "cells": "table",
    "email": "mail",
    "pdf": "document-report",
    "tex": "beaker",
    "page": "newspaper",
}


class TestParseFrontmatter:
    def test_valid(self):
        p = _tmp_md("---\ntitle: Hello\nicon: cube\n---\nBody\n")
        fm, err = _parse_frontmatter(p)
        assert fm == {"title": "Hello", "icon": "cube"}
        assert err is None

    def test_missing_delimiters(self):
        p = _tmp_md("No frontmatter here\n")
        fm, err = _parse_frontmatter(p)
        assert fm is None
        assert "missing frontmatter" in err

    def test_unclosed_frontmatter(self):
        p = _tmp_md("---\ntitle: Hello\n")
        fm, err = _parse_frontmatter(p)
        assert fm is None
        assert "unclosed" in err


class TestUnusedSuggestions:
    def test_prints_unused_icons(self, capsys):
        _print_unused_suggestions(_FAMILY_ICONS, _ICONS)
        captured = capsys.readouterr()
        # Used icons: cube, table, mail, document-report, beaker, newspaper
        # Unused from _ICONS: document-text, pencil-alt, presentation-chart-bar, font, star, fire, globe
        assert "Available unused icons" in captured.out
        assert "star" in captured.out or "fire" in captured.out  # at least some unused shown

    def test_all_icons_used_shows_zero(self, capsys):
        all_used = {"a": "cube", "b": "table"}
        _print_unused_suggestions(all_used, {"cube", "table"})
        captured = capsys.readouterr()
        assert "Available unused icons (0" in captured.out


class TestValidatorIntegration:
    """Integration tests that run the validator against a controlled repo-like structure."""

    def _run_validator(self, family_icons_yaml: str, index_mds: dict[str, str]) -> tuple[int, str]:
        """Run the validator with temporary files, return (exit_code, stdout)."""
        import subprocess
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Write family_icons.yaml
            (tmpdir / "data").mkdir()
            (tmpdir / "data" / "family_icons.yaml").write_text(family_icons_yaml)

            # Write minimal icons.yaml (subset)
            (tmpdir / "themes" / "docs" / "data").mkdir(parents=True)
            icons_content = "\n".join(f"{k}: <svg/>" for k in _ICONS)
            (tmpdir / "themes" / "docs" / "data" / "icons.yaml").write_text(icons_content)

            # Write minimal metrics_taxonomy.yaml (only the test families)
            (tmpdir / "scripts" / "pipeline" / "config").mkdir(parents=True)
            tax = "products:\n" + "\n".join(f"  {k}: Aspose.{k.title()}" for k in _FAMILY_ICONS)
            (tmpdir / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml").write_text(tax)

            # Write family _index.md files
            for rel_path, content in index_mds.items():
                p = tmpdir / rel_path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)

            # Run the validator script with REPO_ROOT pointing to tmpdir
            # We need to patch _REPO_ROOT — easiest is to run as a subprocess
            # with a wrapper that monkey-patches it.
            wrapper = tmpdir / "_run_check.py"
            wrapper.write_text(
                f"import sys; sys.path.insert(0, r'{_CI_CHECKS}')\n"
                f"import check_family_icon_uniqueness as m\n"
                f"from pathlib import Path\n"
                f"m._REPO_ROOT = Path(r'{tmpdir}')\n"
                f"m._FAMILY_ICONS_PATH = Path(r'{tmpdir / 'data' / 'family_icons.yaml'}')\n"
                f"m._ICONS_YAML_PATH = Path(r'{tmpdir / 'themes' / 'docs' / 'data' / 'icons.yaml'}')\n"
                f"m._TAXONOMY_PATH = Path(r'{tmpdir / 'scripts' / 'pipeline' / 'config' / 'metrics_taxonomy.yaml'}')\n"
                f"sys.exit(m.main())\n"
            )
            result = subprocess.run(
                [sys.executable, str(wrapper)],
                capture_output=True, text=True
            )
            return result.returncode, result.stdout + result.stderr

    def _make_index_md(self, icon: str) -> str:
        return f"---\ntitle: Test\nicon: {icon}\n---\nBody\n"

    def _all_sites_index(self, icon: str) -> dict[str, str]:
        """Return index_mds dict with all 3 sites for the given family."""
        result = {}
        for site in ("docs.aspose.org", "reference.aspose.org", "kb.aspose.org"):
            for family, expected_icon in _FAMILY_ICONS.items():
                result[f"content/{site}/en/{family}/_index.md"] = self._make_index_md(
                    icon if family == "pdf" else expected_icon
                )
        return result

    def test_happy_path_all_valid(self):
        """All families registered, valid icons, unique, frontmatter matches — exit 0."""
        fiy = "\n".join(f"{k}: {v}" for k, v in _FAMILY_ICONS.items())
        index_mds = {}
        for site in ("docs.aspose.org", "reference.aspose.org", "kb.aspose.org"):
            for family, icon in _FAMILY_ICONS.items():
                index_mds[f"content/{site}/en/{family}/_index.md"] = self._make_index_md(icon)
        code, out = self._run_validator(fiy, index_mds)
        assert code == 0, f"Expected exit 0, got {code}. Output:\n{out}"
        assert "OK" in out

    def test_v_i_01_family_missing_from_registry(self):
        """Content family missing from family_icons.yaml → V-I-01 FAIL."""
        # Only register 5 of 6 families (omit 'page')
        partial_icons = {k: v for k, v in _FAMILY_ICONS.items() if k != "page"}
        fiy = "\n".join(f"{k}: {v}" for k, v in partial_icons.items())
        index_mds = {}
        for site in ("docs.aspose.org",):
            for family, icon in _FAMILY_ICONS.items():
                index_mds[f"content/{site}/en/{family}/_index.md"] = self._make_index_md(icon)
        code, out = self._run_validator(fiy, index_mds)
        assert code == 1, f"Expected exit 1, got {code}"
        assert "V-I-01" in out
        assert "page" in out

    def test_v_i_02_invalid_icon_name(self):
        """Icon value not in icons.yaml → V-I-02 FAIL."""
        bad_icons = dict(_FAMILY_ICONS)
        bad_icons["pdf"] = "nonexistent-icon-xyz"
        fiy = "\n".join(f"{k}: {v}" for k, v in bad_icons.items())
        index_mds = {}
        for site in ("docs.aspose.org",):
            for family, icon in bad_icons.items():
                index_mds[f"content/{site}/en/{family}/_index.md"] = self._make_index_md(icon)
        code, out = self._run_validator(fiy, index_mds)
        assert code == 1
        assert "V-I-02" in out
        assert "nonexistent-icon-xyz" in out

    def test_v_i_03_duplicate_icon(self):
        """Two families share same icon → V-I-03 FAIL."""
        dup_icons = dict(_FAMILY_ICONS)
        dup_icons["tex"] = "cube"  # same as 3d
        fiy = "\n".join(f"{k}: {v}" for k, v in dup_icons.items())
        index_mds = {}
        for site in ("docs.aspose.org",):
            for family, icon in dup_icons.items():
                index_mds[f"content/{site}/en/{family}/_index.md"] = self._make_index_md(icon)
        code, out = self._run_validator(fiy, index_mds)
        assert code == 1
        assert "V-I-03" in out
        assert "cube" in out

    def test_v_i_04_frontmatter_mismatch(self):
        """Frontmatter icon differs from family_icons.yaml → V-I-04 FAIL."""
        fiy = "\n".join(f"{k}: {v}" for k, v in _FAMILY_ICONS.items())
        index_mds = {}
        for site in ("docs.aspose.org", "reference.aspose.org", "kb.aspose.org"):
            for family, icon in _FAMILY_ICONS.items():
                wrong = "globe" if family == "pdf" else icon
                index_mds[f"content/{site}/en/{family}/_index.md"] = self._make_index_md(wrong)
        code, out = self._run_validator(fiy, index_mds)
        assert code == 1
        assert "V-I-04" in out
        assert "globe" in out

    def test_v_i_04_missing_icon_frontmatter(self):
        """Frontmatter has no icon: field for a registered family → V-I-04 FAIL."""
        fiy = "\n".join(f"{k}: {v}" for k, v in _FAMILY_ICONS.items())
        index_mds = {}
        for site in ("docs.aspose.org",):
            for family in _FAMILY_ICONS:
                if family == "pdf":
                    index_mds[f"content/{site}/en/{family}/_index.md"] = "---\ntitle: No Icon\n---\nBody\n"
                else:
                    index_mds[f"content/{site}/en/{family}/_index.md"] = self._make_index_md(_FAMILY_ICONS[family])
        code, out = self._run_validator(fiy, index_mds)
        assert code == 1
        assert "V-I-04" in out
        assert "missing" in out

    def test_fail_output_includes_unused_suggestions(self):
        """Any FAIL prints unused icon suggestions."""
        bad_icons = dict(_FAMILY_ICONS)
        bad_icons["pdf"] = "nonexistent-icon-xyz"
        fiy = "\n".join(f"{k}: {v}" for k, v in bad_icons.items())
        index_mds = {}
        for site in ("docs.aspose.org",):
            for family, icon in bad_icons.items():
                index_mds[f"content/{site}/en/{family}/_index.md"] = self._make_index_md(icon)
        code, out = self._run_validator(fiy, index_mds)
        assert code == 1
        assert "Available unused icons" in out
