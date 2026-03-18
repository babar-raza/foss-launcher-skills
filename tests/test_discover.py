"""Tests for scripts/discover.py — name parsing and extraction logic.

No network calls. All tests are pure-function or use monkey-patched scan_org.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# Allow importing from scripts/ without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.discover import (
    _extract_family_from_org,
    _parse_repo_name,
    _parse_link_header,
    discover,
)

# ---------------------------------------------------------------------------
# Minimal families fixture matching real families.yaml structure
# ---------------------------------------------------------------------------

FAMILIES = {
    "families": {
        "cells": {"display": "Aspose.Cells", "category": "spreadsheet processing"},
        "note": {"display": "Aspose.Note", "category": "digital notebook processing"},
        "3d": {"display": "Aspose.3D", "category": "3D modeling and rendering"},
        "words": {"display": "Aspose.Words", "category": "document processing"},
        "pdf": {"display": "Aspose.PDF", "category": "PDF manipulation"},
        "slides": {"display": "Aspose.Slides", "category": "presentation processing"},
        "barcode": {"display": "Aspose.BarCode", "category": "barcode"},
    }
}


# ---------------------------------------------------------------------------
# _extract_family_from_org
# ---------------------------------------------------------------------------

class TestExtractFamilyFromOrg:
    def test_standard_aspose_foss_org(self):
        fams = set(FAMILIES["families"].keys())
        assert _extract_family_from_org("aspose-cells-foss", fams) == "cells"

    def test_3d_family(self):
        fams = set(FAMILIES["families"].keys())
        assert _extract_family_from_org("aspose-3d-foss", fams) == "3d"

    def test_words_family(self):
        fams = set(FAMILIES["families"].keys())
        assert _extract_family_from_org("aspose-words-foss", fams) == "words"

    def test_unknown_org_returns_stripped_name(self):
        fams = set(FAMILIES["families"].keys())
        result = _extract_family_from_org("aspose-imaging-foss", fams)
        # "imaging" not in small fixture — returns normalized name without raising
        assert result == "imaging"

    def test_empty_family_set(self):
        result = _extract_family_from_org("aspose-cells-foss", set())
        assert result == "cells"


# ---------------------------------------------------------------------------
# _parse_repo_name
# ---------------------------------------------------------------------------

class TestParseRepoName:
    def test_python_suffix(self):
        family, platform = _parse_repo_name(
            "Aspose.Cells-FOSS-for-Python",
            "aspose-cells-foss",
            FAMILIES,
        )
        assert family == "cells"
        assert platform == "python"

    def test_dotnet_suffix(self):
        family, platform = _parse_repo_name(
            "Aspose.Words-FOSS-for-.NET",
            "aspose-words-foss",
            FAMILIES,
        )
        assert family == "words"
        assert platform == "dotnet"

    def test_java_suffix(self):
        family, platform = _parse_repo_name(
            "Aspose.Slides-FOSS-for-Java",
            "aspose-slides-foss",
            FAMILIES,
        )
        assert family == "slides"
        assert platform == "java"

    def test_3d_python(self):
        family, platform = _parse_repo_name(
            "Aspose.3D-FOSS-for-Python",
            "aspose-3d-foss",
            FAMILIES,
        )
        assert family == "3d"
        assert platform == "python"

    def test_unknown_platform_returns_none(self):
        family, platform = _parse_repo_name(
            "Aspose.Cells-FOSS-for-COBOL",
            "aspose-cells-foss",
            FAMILIES,
        )
        assert family == "cells"
        assert platform is None

    def test_no_for_suffix_returns_family_only(self):
        family, platform = _parse_repo_name(
            "Aspose.Cells-FOSS",
            "aspose-cells-foss",
            FAMILIES,
        )
        assert family == "cells"
        # platform may be None when no "-for-" pattern present
        assert platform is None

    def test_empty_families_still_extracts_platform(self):
        family, platform = _parse_repo_name(
            "Aspose.Cells-FOSS-for-Python",
            "aspose-cells-foss",
            {},
        )
        # family extracted from org name even without families dict
        assert family == "cells"
        assert platform == "python"


# ---------------------------------------------------------------------------
# _parse_link_header
# ---------------------------------------------------------------------------

class TestParseLinkHeader:
    def test_next_and_last(self):
        header = '<https://api.github.com/orgs/foo/repos?page=2>; rel="next", <https://api.github.com/orgs/foo/repos?page=5>; rel="last"'
        links = _parse_link_header(header)
        assert links["next"] == "https://api.github.com/orgs/foo/repos?page=2"
        assert links["last"] == "https://api.github.com/orgs/foo/repos?page=5"

    def test_empty_header(self):
        assert _parse_link_header("") == {}


# ---------------------------------------------------------------------------
# discover() with mocked scan_org
# ---------------------------------------------------------------------------

def _make_fake_repo(full_name: str, html_url: str, language: str = "Python") -> Dict[str, Any]:
    org, name = full_name.split("/", 1)
    return {
        "full_name": full_name,
        "name": name,
        "html_url": html_url,
        "language": language,
        "stargazers_count": 5,
        "archived": False,
        "fork": False,
        "size": 100,
        "pushed_at": "2025-01-01T00:00:00Z",
        "owner": {"login": org, "type": "Organization"},
    }


class TestDiscover:
    def test_manifest_entries_have_family_and_platform(self):
        fake_repos = [
            _make_fake_repo(
                "aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
                "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
            ),
        ]
        with patch("scripts.discover.scan_org", return_value=fake_repos):
            manifest = discover(
                ["aspose-cells-foss"],
                families=FAMILIES,
                clone_dir=None,
            )
        assert len(manifest) == 1
        assert manifest[0]["family"] == "cells"
        assert manifest[0]["platform"] == "python"
        assert "repo_url" in manifest[0]

    def test_language_fallback_for_platform(self):
        """When repo name has no -for- suffix, platform falls back to GitHub language."""
        fake_repos = [
            _make_fake_repo(
                "aspose-cells-foss/Aspose.Cells-FOSS",
                "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS",
                language="C#",
            ),
        ]
        with patch("scripts.discover.scan_org", return_value=fake_repos):
            manifest = discover(["aspose-cells-foss"], families=FAMILIES)
        assert manifest[0]["platform"] == "dotnet"

    def test_deduplication_across_orgs(self):
        """Same repo appearing in two org scans should be deduplicated."""
        repo = _make_fake_repo(
            "aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
            "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
        )
        with patch("scripts.discover.scan_org", return_value=[repo]):
            manifest = discover(
                ["aspose-cells-foss", "aspose-cells-foss"],
                families=FAMILIES,
            )
        assert len(manifest) == 1

    def test_empty_org_returns_empty_manifest(self):
        with patch("scripts.discover.scan_org", return_value=[]):
            manifest = discover(["aspose-cells-foss"], families=FAMILIES)
        assert manifest == []


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

class TestStatePersistence:
    def test_state_saved_and_loaded(self, tmp_path):
        """Second run with same state_dir skips repos already seen."""
        repo = _make_fake_repo(
            "aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
            "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
        )
        with patch("scripts.discover.scan_org", return_value=[repo]):
            # First run — repo is new
            m1 = discover(["aspose-cells-foss"], families=FAMILIES, state_dir=tmp_path)
        assert len(m1) == 1

        # State file should now exist
        state_file = tmp_path / "scan_state.json"
        assert state_file.is_file()
        state = json.loads(state_file.read_text())
        assert "aspose-cells-foss/Aspose.Cells-FOSS-for-Python" in state["seen_repos"]

        with patch("scripts.discover.scan_org", return_value=[repo]):
            # Second run — repo is in seen set, scan_org receives seen_repos with it
            # discover() itself also guards; manifest should be empty
            m2 = discover(["aspose-cells-foss"], families=FAMILIES, state_dir=tmp_path)
        assert len(m2) == 0

    def test_force_rescan_ignores_state(self, tmp_path):
        """force_rescan=True should return repos even if they are in saved state."""
        repo = _make_fake_repo(
            "aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
            "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
        )
        # Seed the state file with the repo already seen
        state_file = tmp_path / "scan_state.json"
        state_file.write_text(
            json.dumps({"seen_repos": ["aspose-cells-foss/Aspose.Cells-FOSS-for-Python"]}),
            encoding="utf-8",
        )
        with patch("scripts.discover.scan_org", return_value=[repo]):
            m = discover(
                ["aspose-cells-foss"],
                families=FAMILIES,
                state_dir=tmp_path,
                force_rescan=True,
            )
        assert len(m) == 1

    def test_missing_state_dir_is_graceful(self):
        """No state_dir means no persistence — should not raise."""
        repo = _make_fake_repo(
            "aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
            "https://github.com/aspose-cells-foss/Aspose.Cells-FOSS-for-Python",
        )
        with patch("scripts.discover.scan_org", return_value=[repo]):
            manifest = discover(["aspose-cells-foss"], families=FAMILIES, state_dir=None)
        assert len(manifest) == 1
