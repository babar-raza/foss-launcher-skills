"""Tests for L-16 platform linkTitle launch gate."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from scripts.pipeline.commands.launch.launch_gate import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    configure,
    gate_l16_platform_linktitle,
)


@pytest.fixture()
def gate_repo(tmp_path: Path):
    """Create a minimal repo structure for L-16 testing."""
    # data/platforms.json
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "platforms.json").write_text(
        json.dumps({"java": "Java", "net": ".NET", "go": "Go"}),
        encoding="utf-8",
    )

    configure(repo_root=tmp_path)
    return tmp_path


def _write_index(repo: Path, site: str, family: str, platform: str, fm: str) -> None:
    if site == "blog":
        d = repo / "content" / f"{site}.aspose.org" / family / platform
    else:
        d = repo / "content" / f"{site}.aspose.org" / "en" / family / platform
    d.mkdir(parents=True, exist_ok=True)
    (d / "_index.md").write_text(
        textwrap.dedent(fm),
        encoding="utf-8",
    )


class TestL16PlatformLinkTitle:
    def test_pass_correct_linktitle(self, gate_repo: Path) -> None:
        _write_index(gate_repo, "docs", "pdf", "java", """\
            ---
            title: Aspose.PDF FOSS for Java
            linktitle: Java
            ---
            Body
        """)
        result = gate_l16_platform_linktitle("pdf", "java")
        assert result.status == STATUS_PASS

    def test_pass_camelcase_linktitle(self, gate_repo: Path) -> None:
        _write_index(gate_repo, "kb", "pdf", "java", """\
            ---
            title: Aspose.PDF FOSS for Java
            linkTitle: Java
            ---
            Body
        """)
        result = gate_l16_platform_linktitle("pdf", "java")
        assert result.status == STATUS_PASS

    def test_fail_missing_linktitle(self, gate_repo: Path) -> None:
        _write_index(gate_repo, "docs", "pdf", "java", """\
            ---
            title: Aspose.PDF FOSS for Java
            ---
            Body
        """)
        result = gate_l16_platform_linktitle("pdf", "java")
        assert result.status == STATUS_FAIL
        assert "linkTitle missing" in result.detail or any(
            "linkTitle missing" in l for l in result.extra_lines
        )

    def test_fail_wrong_linktitle(self, gate_repo: Path) -> None:
        _write_index(gate_repo, "docs", "pdf", "java", """\
            ---
            title: Aspose.PDF FOSS for Java
            linktitle: Aspose.PDF FOSS for Java
            ---
            Body
        """)
        result = gate_l16_platform_linktitle("pdf", "java")
        assert result.status == STATUS_FAIL

    def test_fail_unknown_platform_slug(self, gate_repo: Path) -> None:
        result = gate_l16_platform_linktitle("pdf", "rust")
        assert result.status == STATUS_FAIL
        assert "not in data/platforms.json" in result.detail

    def test_fail_forbidden_pattern(self, gate_repo: Path) -> None:
        _write_index(gate_repo, "kb", "pdf", "java", """\
            ---
            title: Aspose.PDF FOSS for Java
            linkTitle: Java Knowledge Base
            ---
            Body
        """)
        result = gate_l16_platform_linktitle("pdf", "java")
        assert result.status == STATUS_FAIL

    def test_skip_no_platform_pages(self, gate_repo: Path) -> None:
        result = gate_l16_platform_linktitle("nonexistent", "java")
        assert result.status == STATUS_SKIP

    def test_pass_multi_site(self, gate_repo: Path) -> None:
        for site in ("docs", "kb", "reference"):
            lt_key = "linktitle" if site == "docs" else "linkTitle"
            _write_index(gate_repo, site, "pdf", "go", f"""\
                ---
                title: Aspose.PDF FOSS for Go
                {lt_key}: Go
                ---
                Body
            """)
        result = gate_l16_platform_linktitle("pdf", "go")
        assert result.status == STATUS_PASS
        assert "3 site(s)" in result.detail
