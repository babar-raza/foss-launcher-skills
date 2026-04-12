"""Tests for gap-eval precondition gate (S1-1 fix).

Ensures that _load_api_surface raises FileNotFoundError when the file is
absent, and that an empty api_names set raises ValueError downstream.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Allow imports from scripts/gap-eval/
_GAP_EVAL_DIR = Path(__file__).resolve().parents[2] / "gap-eval"
if str(_GAP_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_GAP_EVAL_DIR))

import run as gap_eval_run  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# _load_api_surface precondition: missing file
# ---------------------------------------------------------------------------

class TestLoadApiSurfaceMissingFile:
    def test_raises_file_not_found(self, tmp_path):
        """api_surface.json absent -> FileNotFoundError, not empty list."""
        with patch.object(gap_eval_run, '_api_surface_path', return_value=tmp_path / "nonexistent.json"):
            with pytest.raises(FileNotFoundError, match="PRECONDITION FAILED"):
                gap_eval_run._load_api_surface("test", "python")


# ---------------------------------------------------------------------------
# _load_api_surface: file exists but empty list
# ---------------------------------------------------------------------------

class TestLoadApiSurfaceEmptyClasses:
    def test_returns_empty_list(self, tmp_path):
        """api_surface.json exists but has empty list -> returns [] (caught downstream)."""
        p = tmp_path / "api_surface.json"
        p.write_text("[]")
        with patch.object(gap_eval_run, '_api_surface_path', return_value=p):
            result = gap_eval_run._load_api_surface("test", "python")
            assert result == []


# ---------------------------------------------------------------------------
# _load_api_surface: dict-style data with "classes" key
# ---------------------------------------------------------------------------

class TestLoadApiSurfaceDictFormat:
    def test_extracts_classes_key(self, tmp_path):
        """api_surface.json with dict format -> extracts 'classes' key."""
        p = tmp_path / "api_surface.json"
        data = {"classes": [{"name": "Foo"}]}
        p.write_text(json.dumps(data))
        with patch.object(gap_eval_run, '_api_surface_path', return_value=p):
            result = gap_eval_run._load_api_surface("test", "python")
            assert result == [{"name": "Foo"}]

    def test_extracts_entries_key(self, tmp_path):
        """api_surface.json with 'entries' key -> extracts it."""
        p = tmp_path / "api_surface.json"
        data = {"entries": [{"name": "Bar"}]}
        p.write_text(json.dumps(data))
        with patch.object(gap_eval_run, '_api_surface_path', return_value=p):
            result = gap_eval_run._load_api_surface("test", "python")
            assert result == [{"name": "Bar"}]
