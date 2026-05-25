"""Unit tests for lane_manifest.py — Lane manifest validator."""
import json
import tempfile
import unittest
from pathlib import Path

from lane_manifest import validate_manifest, validate_file, validate_directory, VALID_STATUSES


def _make_valid_manifest(**overrides):
    """Build a valid lane manifest dict with optional overrides."""
    base = {
        "lane_id": "LANE-A",
        "sprint_id": "test-sprint-20260526",
        "owned_path_prefixes": ["content/docs.aspose.org/en/cells/java/"],
        "shared_path_prefixes": [],
        "skills_expected": ["S-20", "S-21"],
        "depends_on_lanes": [],
        "status": "PROPOSED",
        "created_at": "2026-05-26T03:00:00Z",
        "committed_at": None,
        "commit_sha": None,
        "revert_sha": None,
    }
    base.update(overrides)
    return base


class TestValidateManifest(unittest.TestCase):
    def test_valid_manifest(self):
        errors = validate_manifest(_make_valid_manifest())
        self.assertEqual(errors, [])

    def test_missing_required_field(self):
        m = _make_valid_manifest()
        del m["lane_id"]
        errors = validate_manifest(m)
        self.assertTrue(any("Missing required field: lane_id" in e for e in errors))

    def test_invalid_status(self):
        errors = validate_manifest(_make_valid_manifest(status="INVALID"))
        self.assertTrue(any("Invalid status" in e for e in errors))

    def test_all_valid_statuses(self):
        for status in VALID_STATUSES:
            errors = validate_manifest(_make_valid_manifest(status=status))
            status_errors = [e for e in errors if "status" in e.lower()]
            self.assertEqual(status_errors, [], f"Status {status} should be valid")

    def test_empty_owned_path_prefixes(self):
        errors = validate_manifest(_make_valid_manifest(owned_path_prefixes=[]))
        self.assertTrue(any("must not be empty" in e for e in errors))

    def test_absolute_path_prefix(self):
        errors = validate_manifest(
            _make_valid_manifest(owned_path_prefixes=["/absolute/path/"])
        )
        self.assertTrue(any("must be relative" in e for e in errors))

    def test_windows_absolute_path(self):
        errors = validate_manifest(
            _make_valid_manifest(owned_path_prefixes=["D:/some/path/"])
        )
        self.assertTrue(any("must be relative" in e for e in errors))

    def test_parent_directory_escape(self):
        errors = validate_manifest(
            _make_valid_manifest(owned_path_prefixes=["../escape/"])
        )
        self.assertTrue(any("must not contain '..'" in e for e in errors))

    def test_duplicate_path_prefixes(self):
        errors = validate_manifest(
            _make_valid_manifest(
                owned_path_prefixes=["content/a/", "content/a/"]
            )
        )
        self.assertTrue(any("duplicated" in e for e in errors))

    def test_lane_id_format(self):
        errors = validate_manifest(_make_valid_manifest(lane_id="BAD"))
        self.assertTrue(any("must start with" in e for e in errors))

    def test_empty_lane_id(self):
        errors = validate_manifest(_make_valid_manifest(lane_id=""))
        self.assertTrue(any("non-empty string" in e for e in errors))

    def test_empty_sprint_id(self):
        errors = validate_manifest(_make_valid_manifest(sprint_id=""))
        self.assertTrue(any("sprint_id" in e for e in errors))

    def test_empty_created_at(self):
        errors = validate_manifest(_make_valid_manifest(created_at=""))
        self.assertTrue(any("created_at" in e for e in errors))

    def test_shared_path_with_parent_escape(self):
        errors = validate_manifest(
            _make_valid_manifest(shared_path_prefixes=["../hack/"])
        )
        self.assertTrue(any("must not contain '..'" in e for e in errors))

    def test_depends_on_lanes_must_be_list(self):
        errors = validate_manifest(_make_valid_manifest(depends_on_lanes="LANE-B"))
        self.assertTrue(any("depends_on_lanes must be a list" in e for e in errors))


class TestValidateFile(unittest.TestCase):
    def test_valid_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(_make_valid_manifest(), f)
            f.flush()
            errors = validate_file(Path(f.name))
        self.assertEqual(errors, [])

    def test_nonexistent_file(self):
        errors = validate_file(Path("/nonexistent/file.json"))
        self.assertTrue(any("File not found" in e for e in errors))

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{bad json}")
            f.flush()
            errors = validate_file(Path(f.name))
        self.assertTrue(any("Invalid JSON" in e for e in errors))

    def test_filename_lane_id_mismatch(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="LANE-B",
            delete=False, encoding="utf-8"
        ) as f:
            json.dump(_make_valid_manifest(lane_id="LANE-A"), f)
            f.flush()
            errors = validate_file(Path(f.name))
        # Should detect mismatch
        self.assertTrue(any("does not match filename" in e for e in errors))


class TestValidateDirectory(unittest.TestCase):
    def test_valid_directory(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "LANE-A.json"
            p.write_text(json.dumps(_make_valid_manifest()), encoding="utf-8")
            errors = validate_directory(Path(d))
        self.assertEqual(errors, [])

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            errors = validate_directory(Path(d))
        self.assertTrue(any("No .json files" in e for e in errors))

    def test_nonexistent_directory(self):
        errors = validate_directory(Path("/nonexistent/dir"))
        self.assertTrue(any("Directory not found" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
