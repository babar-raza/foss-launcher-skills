"""Unit tests for lane_evidence_schema.py."""
import tempfile, unittest
from pathlib import Path
from lane_evidence_schema import get_schema, check_evidence

class TestGetSchema(unittest.TestCase):
    def test_pilot_1_ids(self):
        ids=[r["id"] for r in get_schema(1)]
        self.assertIn("lane-manifest",ids); self.assertIn("overlap-check",ids); self.assertIn("dirty-classifier",ids)
    def test_pilot_2_ids(self):
        ids=[r["id"] for r in get_schema(2)]
        self.assertIn("s23-audit",ids); self.assertIn("rollback-drill",ids); self.assertIn("commit-sha",ids)
    def test_pilot_3_ids(self):
        ids=[r["id"] for r in get_schema(3)]
        self.assertIn("generation-manifest",ids); self.assertIn("repeatability-proof",ids)
    def test_invalid_pilot(self):
        with self.assertRaises(ValueError): get_schema(99)
    def test_all_have_required_fields(self):
        for pilot in [1,2,3]:
            for req in get_schema(pilot):
                self.assertIn("id",req); self.assertIn("description",req); self.assertIn("required",req)
    def test_pilot2_superset_pilot1(self):
        p1={r["id"] for r in get_schema(1) if r["required"]}
        p2={r["id"] for r in get_schema(2)}
        missing=p1-p2; missing.discard("state-transition-log")
        self.assertEqual(missing,set())

class TestCheckEvidence(unittest.TestCase):
    def test_empty_dir_has_fails(self):
        with tempfile.TemporaryDirectory() as d:
            results=check_evidence(1,Path(d))
        self.assertTrue(len([r for r in results if r["status"]=="FAIL"])>0)
    def test_files_found(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/"lane_manifest.json").write_text("{}",encoding="utf-8")
            (p/"overlap_check.txt").write_text("PASS",encoding="utf-8")
            (p/"dirty_classifier.json").write_text("{}",encoding="utf-8")
            (p/"state_transition_log.txt").write_text("",encoding="utf-8")
            results=check_evidence(1,p)
        self.assertEqual(len([r for r in results if r["status"]=="PASS"]),4)
    def test_optional_warn(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/"lane_manifest.json").write_text("{}",encoding="utf-8")
            (p/"overlap_check.txt").write_text("PASS",encoding="utf-8")
            (p/"dirty_classifier.json").write_text("{}",encoding="utf-8")
            (p/"state_transition_log.txt").write_text("",encoding="utf-8")
            results=check_evidence(1,p)
        self.assertTrue(len([r for r in results if r["status"]=="WARN"])>=1)

    # Regression: LANE-*.json must be recognised as lane-manifest evidence (Defect 1)
    def test_lane_id_json_recognised_as_manifest(self):
        """LANE-A.json must satisfy the lane-manifest requirement."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "LANE-A.json").write_text("{}", encoding="utf-8")
            (p / "overlap_check.txt").write_text("PASS", encoding="utf-8")
            (p / "dirty_classifier.json").write_text("{}", encoding="utf-8")
            (p / "state_transition_log.txt").write_text("", encoding="utf-8")
            results = check_evidence(1, p)
        lm = next(r for r in results if r["id"] == "lane-manifest")
        self.assertEqual(lm["status"], "PASS",
                         "LANE-A.json must satisfy lane-manifest evidence requirement")

    def test_lane_numbered_json_recognised(self):
        """LANE-1.json must also satisfy the lane-manifest requirement."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "LANE-1.json").write_text("{}", encoding="utf-8")
            (p / "overlap_check.txt").write_text("PASS", encoding="utf-8")
            (p / "dirty_classifier.json").write_text("{}", encoding="utf-8")
            (p / "state_transition_log.txt").write_text("", encoding="utf-8")
            results = check_evidence(1, p)
        lm = next(r for r in results if r["id"] == "lane-manifest")
        self.assertEqual(lm["status"], "PASS",
                         "LANE-1.json must satisfy lane-manifest evidence requirement")

    def test_irrelevant_json_does_not_satisfy_manifest(self):
        """A random JSON file must NOT satisfy lane-manifest requirement."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "results.json").write_text("{}", encoding="utf-8")
            results = check_evidence(1, p)
        lm = next(r for r in results if r["id"] == "lane-manifest")
        self.assertEqual(lm["status"], "FAIL")

    def test_pilot1_full_pass_with_lane_id_files(self):
        """Full Pilot 1 evidence dir using LANE-*.json must have 0 required failures."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "LANE-A.json").write_text("{}", encoding="utf-8")
            (p / "overlap_check_PASS.txt").write_text("PASS", encoding="utf-8")
            (p / "dirty_classifier_output.json").write_text("{}", encoding="utf-8")
            (p / "state_transition_log.txt").write_text("transitions", encoding="utf-8")
            results = check_evidence(1, p)
        required_fails = [r for r in results if r["required"] and r["status"] == "FAIL"]
        self.assertEqual(required_fails, [],
                         f"Required evidence items failed: {required_fails}")

if __name__=="__main__": unittest.main()
