"""Unit tests for lane_overlap_check.py."""
import json, tempfile, unittest
from pathlib import Path
from lane_overlap_check import check_overlaps, load_manifests

def _m(lane_id, prefixes, status="PROPOSED"):
    return {"lane_id": lane_id, "sprint_id": "s", "owned_path_prefixes": prefixes,
            "shared_path_prefixes": [], "skills_expected": [], "depends_on_lanes": [],
            "status": status, "created_at": "2026-05-26T03:00:00Z",
            "committed_at": None, "commit_sha": None, "revert_sha": None}

class TestCheckOverlaps(unittest.TestCase):
    def test_disjoint(self):
        self.assertEqual(check_overlaps([_m("LANE-A",["content/docs/"]),_m("LANE-B",["content/kb/"])]), [])
    def test_identical(self):
        c = check_overlaps([_m("LANE-A",["content/docs/"]),_m("LANE-B",["content/docs/"])])
        self.assertTrue(len(c)>0); self.assertEqual(c[0]["type"],"identical")
    def test_nested(self):
        c = check_overlaps([_m("LANE-A",["content/docs/"]),_m("LANE-B",["content/docs/cells/"])])
        self.assertTrue(len(c)>0); self.assertEqual(c[0]["type"],"nested")
    def test_reverse_nested(self):
        c = check_overlaps([_m("LANE-A",["content/docs/cells/"]),_m("LANE-B",["content/docs/"])])
        self.assertTrue(len(c)>0)
    def test_duplicate_id(self):
        c = check_overlaps([_m("LANE-A",["a/"]),_m("LANE-A",["b/"])])
        self.assertTrue(any(x["type"]=="duplicate_lane_id" for x in c))
    def test_trailing_slash_norm(self):
        c = check_overlaps([_m("LANE-A",["content/docs/cells"]),_m("LANE-B",["content/docs/cells/"])])
        self.assertTrue(len(c)>0)
    def test_single(self):
        self.assertEqual(check_overlaps([_m("LANE-A",["content/docs/"])]), [])
    def test_three_disjoint(self):
        self.assertEqual(check_overlaps([_m("LANE-A",["a/"]),_m("LANE-B",["b/"]),_m("LANE-C",["c/"])]), [])

class TestLoadManifests(unittest.TestCase):
    def test_filters_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p1=Path(d)/"LANE-A.json"; p1.write_text(json.dumps(_m("LANE-A",["a/"],"PROPOSED")),encoding="utf-8")
            p2=Path(d)/"LANE-B.json"; p2.write_text(json.dumps(_m("LANE-B",["b/"],"REJECTED")),encoding="utf-8")
            r=load_manifests([p1,p2])
        self.assertEqual(len(r),1); self.assertEqual(r[0]["lane_id"],"LANE-A")
    def test_filters_reverted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"LANE-A.json"; p.write_text(json.dumps(_m("LANE-A",["a/"],"REVERTED")),encoding="utf-8")
            self.assertEqual(load_manifests([p]),[])

if __name__=="__main__": unittest.main()
