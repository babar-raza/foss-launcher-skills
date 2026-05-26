# Tests for validate_clean_working_tree_bundle.py
import tempfile, unittest, zipfile
from pathlib import Path
from validate_clean_working_tree_bundle import (
    validate, check1_required_deliverables, check4_verdict_consistency,
    check5_p0_tooling, check6_contradiction_repair, check7_dirty_tree_classified,
    REQUIRED_DELIVERABLES, P0_TOOL_NAMES,
)

def _make_bundle(files):
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(tmp.name, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return Path(tmp.name)

MINIMAL_STATE = "final_verdict: PLAN_HARDENED_IMPLEMENTATION_READY_FOR_P0\nblocked_items: []\n"
PILOT_READY_STATE = "final_verdict: PLAN_HARDENED_READY_FOR_DOCS_ONLY_PILOT\nblocked_items: []\n"
PILOT_BLOCKED_STATE = "final_verdict: PLAN_HARDENED_READY_FOR_DOCS_ONLY_PILOT\nblocked_items: [TC-LCM-01]\n"
PREFLIGHT = "=== git status --short ===\n M .claude/settings.json\n"

class TestCheck1(unittest.TestCase):
    def test_all_present(self):
        names = [r.replace("-","_") + ".md" for r in REQUIRED_DELIVERABLES]
        self.assertEqual(check1_required_deliverables(names)["status"], "PASS")
    def test_missing_one(self):
        names = [r.replace("-","_") + ".md" for r in REQUIRED_DELIVERABLES if "taskcards" not in r]
        r = check1_required_deliverables(names)
        self.assertEqual(r["status"], "FAIL")
        self.assertIn("taskcards", r["detail"])

class TestCheck4(unittest.TestCase):
    def test_non_pilot(self):
        bp = _make_bundle({"plan-state.yaml": MINIMAL_STATE})
        try: self.assertEqual(check4_verdict_consistency(bp, ["plan-state.yaml"])["status"], "PASS")
        finally: bp.unlink(missing_ok=True)
    def test_pilot_blocked(self):
        bp = _make_bundle({"plan-state.yaml": PILOT_BLOCKED_STATE})
        try: self.assertEqual(check4_verdict_consistency(bp, ["plan-state.yaml"])["status"], "FAIL")
        finally: bp.unlink(missing_ok=True)
    def test_pilot_ready_ok(self):
        bp = _make_bundle({"plan-state.yaml": PILOT_READY_STATE})
        try: self.assertEqual(check4_verdict_consistency(bp, ["plan-state.yaml"])["status"], "PASS")
        finally: bp.unlink(missing_ok=True)

class TestCheck5(unittest.TestCase):
    def test_non_pilot_skips(self):
        bp = _make_bundle({"plan-state.yaml": MINIMAL_STATE})
        try:
            r = check5_p0_tooling(bp, ["plan-state.yaml"])
            self.assertEqual(r["status"], "PASS")
            self.assertIn("skipped", r["detail"].lower())
        finally: bp.unlink(missing_ok=True)
    def test_pilot_missing_p0(self):
        bp = _make_bundle({"plan-state.yaml": PILOT_READY_STATE})
        try: self.assertEqual(check5_p0_tooling(bp, ["plan-state.yaml"])["status"], "FAIL")
        finally: bp.unlink(missing_ok=True)
    def test_pilot_p0_present(self):
        files = {"plan-state.yaml": PILOT_READY_STATE}
        files.update({f"{t}.py": "# x" for t in P0_TOOL_NAMES})
        bp = _make_bundle(files)
        try: self.assertEqual(check5_p0_tooling(bp, list(files.keys()))["status"], "PASS")
        finally: bp.unlink(missing_ok=True)

class TestCheck6(unittest.TestCase):
    def test_no_contradictions(self):
        bp = _make_bundle({"contradiction-log.md": "All clear"})
        try: self.assertEqual(check6_contradiction_repair(bp, ["contradiction-log.md"])["status"], "PASS")
        finally: bp.unlink(missing_ok=True)
    def test_accepted_no_repair(self):
        bp = _make_bundle({"contradiction-log.md": "C-01: accepted as-is"})
        try: self.assertEqual(check6_contradiction_repair(bp, ["contradiction-log.md"])["status"], "FAIL")
        finally: bp.unlink(missing_ok=True)
    def test_accepted_with_repair(self):
        bp = _make_bundle({"contradiction-log.md": "C-01: accepted as-is", "repair-loop-1.md": "C-01 resolved by correcting line ref"})
        try: self.assertEqual(check6_contradiction_repair(bp, ["contradiction-log.md", "repair-loop-1.md"])["status"], "PASS")
        finally: bp.unlink(missing_ok=True)

class TestCheck7(unittest.TestCase):
    def test_with_git_status(self):
        bp = _make_bundle({"command-logs/preflight.txt": PREFLIGHT})
        try: self.assertEqual(check7_dirty_tree_classified(bp, ["command-logs/preflight.txt"])["status"], "PASS")
        finally: bp.unlink(missing_ok=True)
    def test_no_preflight(self):
        bp = _make_bundle({"readme.md": "nothing"})
        try: self.assertEqual(check7_dirty_tree_classified(bp, ["readme.md"])["status"], "FAIL")
        finally: bp.unlink(missing_ok=True)

class TestValidateDir(unittest.TestCase):
    def test_has_10_checks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for r in REQUIRED_DELIVERABLES:
                (p / f"{r}.md").write_text(f"# {r}", encoding="utf-8")
            (p / "sha256-manifest.txt").write_text("a"*64 + "  file.md", encoding="utf-8")
            (p / "plan-state.yaml").write_text(MINIMAL_STATE, encoding="utf-8")
            logs = p / "command-logs"
            logs.mkdir()
            (logs / "preflight.txt").write_text(PREFLIGHT, encoding="utf-8")
            report = validate(p)
        self.assertEqual(report["total_checks"], 10)
    def test_nonexistent(self):
        self.assertEqual(validate(Path("/nonexistent/x.zip"))["overall"], "FAIL")

if __name__ == "__main__": unittest.main()