"""Tests for semantic_body_update_dispatch.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from commands.ops.semantic_body_update_dispatch import generate_pending_updates


@pytest.fixture
def sample_page_impact(tmp_path: Path) -> Path:
    data = {
        "family": "cells",
        "platform": "cpp",
        "pages": [
            {
                "path": "content/docs.aspose.org/en/cells/cpp/developer-guide/features.md",
                "subdomain": "docs",
                "pia_score": "HIGH_IMPACT",
                "signals_found": ["api:Workbook", "kw:cells"],
            },
            {
                "path": "content/kb.aspose.org/en/cells/cpp/troubleshooting.md",
                "subdomain": "kb",
                "pia_score": "MEDIUM_IMPACT",
                "signals_found": ["kw:worksheet"],
            },
            {
                "path": "content/reference.aspose.org/en/cells/cpp/Workbook.md",
                "subdomain": "reference",
                "pia_score": "HIGH_IMPACT",
                "signals_found": ["api:Workbook"],
            },
            {
                "path": "content/docs.aspose.org/en/cells/cpp/getting-started.md",
                "subdomain": "docs",
                "pia_score": "LOW_IMPACT",
                "signals_found": [],
            },
            {
                "path": "content/blog.aspose.org/cells/cpp/intro/index.md",
                "subdomain": "blog",
                "pia_score": "NOT_AFFECTED",
                "signals_found": [],
            },
        ],
    }
    p = tmp_path / "page_impact.json"
    p.write_text(json.dumps(data))
    return p


class TestGeneratePendingUpdates:
    def test_filters_high_and_medium_excludes_reference(
        self, sample_page_impact: Path
    ):
        result = generate_pending_updates(
            sample_page_impact, family="cells", platform="cpp"
        )
        paths = [r["path"] for r in result]
        assert len(result) == 2
        assert "content/docs.aspose.org/en/cells/cpp/developer-guide/features.md" in paths
        assert "content/kb.aspose.org/en/cells/cpp/troubleshooting.md" in paths
        # Reference page excluded
        assert not any("reference.aspose.org" in p for p in paths)

    def test_excludes_low_and_not_affected(self, sample_page_impact: Path):
        result = generate_pending_updates(
            sample_page_impact, family="cells", platform="cpp"
        )
        scores = {r["pia_score"] for r in result}
        assert "LOW_IMPACT" not in scores
        assert "NOT_AFFECTED" not in scores

    def test_preserves_signals(self, sample_page_impact: Path):
        result = generate_pending_updates(
            sample_page_impact, family="cells", platform="cpp"
        )
        high = [r for r in result if r["pia_score"] == "HIGH_IMPACT"][0]
        assert "api:Workbook" in high["signals"]

    def test_empty_pages_returns_empty_list(self, tmp_path: Path):
        p = tmp_path / "empty.json"
        p.write_text(json.dumps({"pages": []}))
        result = generate_pending_updates(p, family="x", platform="y")
        assert result == []
