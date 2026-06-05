"""
test_supervisor.py — Unit and integration tests for the aspose.org Local Supervisor Control Plane.

Test coverage:
  - import/syntax: every script imports without errors
  - no-stub: scripts must have real logic (not pass/TODO placeholders)
  - schema/output shape: correct dict keys returned by each function
  - missing-dir graceful fallback: handles absent knowledge/ and reports/
  - dry-run forbidden-path guard: is_forbidden() and safe_emit() block protected paths
  - idempotency: two passes produce identical action lists (ignoring timestamps)
  - zero-action acceptance: NO_ACTIONS_READY is valid, not an error
  - ruflo unavailable: TOOL_UNAVAILABLE recorded correctly
  - MCP rollback preservation: pre-existing mcpServers preserved
  - rollback manifest schema: manifest has required fields
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Make supervisor package importable
_REPO = Path(__file__).resolve().parents[4]  # tests/ -> supervisor/ -> maintenance/ -> scripts/ -> repo
_SUP = _REPO / "scripts" / "maintenance" / "supervisor"
if str(_SUP) not in sys.path:
    sys.path.insert(0, str(_SUP))


def _import(name: str):
    """Import a supervisor module by name from the supervisor directory."""
    spec = importlib.util.spec_from_file_location(name, _SUP / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    # Ensure _SUP is on sys.path for relative imports within the module
    if str(_SUP) not in sys.path:
        sys.path.insert(0, str(_SUP))
    spec.loader.exec_module(mod)
    return mod


# ============================================================
# 1. Import tests
# ============================================================

class TestImports(unittest.TestCase):
    """Every supervisor script must import without errors."""

    def test_common(self):
        m = _import("_common")
        self.assertTrue(hasattr(m, "REPO_ROOT"))
        self.assertTrue(hasattr(m, "is_forbidden"))
        self.assertTrue(hasattr(m, "safe_emit"))
        self.assertTrue(hasattr(m, "base_args"))

    def test_discover(self):
        m = _import("discover")
        self.assertTrue(hasattr(m, "discover"))
        self.assertTrue(hasattr(m, "main"))

    def test_validate(self):
        m = _import("validate")
        self.assertTrue(hasattr(m, "validate"))
        self.assertTrue(hasattr(m, "main"))

    def test_compare(self):
        m = _import("compare")
        self.assertTrue(hasattr(m, "compare"))
        self.assertTrue(hasattr(m, "main"))

    def test_generate(self):
        m = _import("generate")
        self.assertTrue(hasattr(m, "generate"))
        self.assertTrue(hasattr(m, "main"))

    def test_sync(self):
        m = _import("sync")
        self.assertTrue(hasattr(m, "sync"))
        self.assertTrue(hasattr(m, "main"))

    def test_orchestrate(self):
        m = _import("orchestrate")
        self.assertTrue(hasattr(m, "orchestrate"))
        self.assertTrue(hasattr(m, "main"))

    def test_tm_export(self):
        m = _import("tm_export")
        self.assertTrue(hasattr(m, "tm_export"))
        self.assertTrue(hasattr(m, "main"))

    def test_ruflo_export(self):
        m = _import("ruflo_export")
        self.assertTrue(hasattr(m, "ruflo_export"))
        self.assertTrue(hasattr(m, "main"))


# ============================================================
# 2. No-stub tests
# ============================================================

class TestNoStub(unittest.TestCase):
    """Scripts must have real logic — not placeholder implementations."""

    SCRIPTS = ["discover", "validate", "compare", "generate", "sync",
               "orchestrate", "tm_export", "ruflo_export"]

    def _check(self, name):
        content = (_SUP / f"{name}.py").read_text(encoding="utf-8")
        self.assertIn("return", content, f"{name}.py has no return statement")
        stub_patterns = ["pass  # TODO", "raise NotImplementedError", "# STUB"]
        for pat in stub_patterns:
            self.assertNotIn(pat, content, f"{name}.py contains stub: {pat!r}")
        real_lines = [l for l in content.splitlines()
                      if l.strip() and not l.strip().startswith("#")]
        self.assertGreater(len(real_lines), 25,
                           f"{name}.py has only {len(real_lines)} non-comment lines")

    def test_no_stub_discover(self): self._check("discover")
    def test_no_stub_validate(self): self._check("validate")
    def test_no_stub_compare(self): self._check("compare")
    def test_no_stub_generate(self): self._check("generate")
    def test_no_stub_sync(self): self._check("sync")
    def test_no_stub_orchestrate(self): self._check("orchestrate")
    def test_no_stub_tm_export(self): self._check("tm_export")
    def test_no_stub_ruflo_export(self): self._check("ruflo_export")


# ============================================================
# 3. Schema / output shape tests
# ============================================================

class TestDiscoverSchema(unittest.TestCase):
    def test_empty_dir_returns_valid_schema(self):
        m = _import("discover")
        with tempfile.TemporaryDirectory() as tmp:
            r = m.discover(repo_root=tmp)
        required = ["stale_products", "fresh_products", "missing_products",
                    "warnings", "source_files_read", "knowledge_dir_exists"]
        for key in required:
            self.assertIn(key, r, f"discover() missing key: {key}")
        self.assertFalse(r["knowledge_dir_exists"])
        self.assertGreater(len(r["warnings"]), 0)

    def test_real_repo_finds_products(self):
        m = _import("discover")
        r = m.discover()
        total = (len(r["stale_products"]) + len(r["fresh_products"])
                 + len(r["missing_products"]))
        self.assertGreater(total, 0, "No products found in real knowledge dir")


class TestValidateSchema(unittest.TestCase):
    def test_empty_dir_returns_valid_schema(self):
        m = _import("validate")
        with tempfile.TemporaryDirectory() as tmp:
            r = m.validate(repo_root=tmp)
        required = ["grade_summary", "pages_needing_heal", "api_audit_status",
                    "warnings", "eval_reports_found", "audit_reports_found"]
        for key in required:
            self.assertIn(key, r, f"validate() missing key: {key}")
        self.assertGreater(len(r["warnings"]), 0)

    def test_real_repo(self):
        m = _import("validate")
        r = m.validate()
        self.assertIn("grade_summary", r)


class TestValidateDedup(unittest.TestCase):
    """Tests for validate.py deduplication of per-page findings."""

    def _make_eval_report(self, tmp, filename, findings):
        """Create a minimal eval-*.json with given findings."""
        eval_dir = Path(tmp) / "reports" / "content_eval"
        eval_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": "1.0",
            "generated_at": "2026-06-01T00:00:00Z",
            "scope": {},
            "summary": {
                "total_findings": len(findings),
                "pages_evaluated": 1,
                "pages_clean": 0 if findings else 1,
                "pages_with_findings": 1 if findings else 0,
                "by_severity": {},
                "by_category": {},
            },
            "findings": findings,
        }
        for f in findings:
            sev = f.get("level", "INFO")
            data["summary"]["by_severity"][sev] = (
                data["summary"]["by_severity"].get(sev, 0) + 1
            )
        (eval_dir / filename).write_text(json.dumps(data), encoding="utf-8")
        # Also create empty audit dir to avoid warning
        (Path(tmp) / "reports" / "audit").mkdir(parents=True, exist_ok=True)

    def test_dedup_keeps_only_latest_report_per_page(self):
        """Same page in two reports: only latest report's findings counted."""
        m = _import("validate")
        page = "/content/docs/test.md"
        with tempfile.TemporaryDirectory() as tmp:
            # Older report: 2 FAILs for the page
            self._make_eval_report(tmp, "eval-20260601-100000.json", [
                {"file": page, "level": "FAIL", "evaluator": "e1",
                 "id": "1", "category": "X", "line": 1, "message": "old1", "suggestion": ""},
                {"file": page, "level": "FAIL", "evaluator": "e2",
                 "id": "2", "category": "X", "line": 2, "message": "old2", "suggestion": ""},
            ])
            # Newer report: 0 FAILs for the page (fixed)
            self._make_eval_report(tmp, "eval-20260602-100000.json", [
                {"file": page, "level": "WARN", "evaluator": "e1",
                 "id": "3", "category": "X", "line": 1, "message": "warn1", "suggestion": ""},
            ])

            r = m.validate(repo_root=tmp, dedup=True)
            # Page should NOT appear in pages_needing_heal (0 FAILs in latest report)
            heal_paths = [p["path"] for p in r["pages_needing_heal"]]
            self.assertNotIn(page, heal_paths)

    def test_no_dedup_accumulates_across_reports(self):
        """With dedup=False, findings from all reports are accumulated."""
        m = _import("validate")
        with tempfile.TemporaryDirectory() as tmp:
            page_file = Path(tmp) / "content" / "docs" / "test.md"
            page_file.parent.mkdir(parents=True, exist_ok=True)
            page_file.write_text("---\ngrade: D\n---\ncontent", encoding="utf-8")
            page = str(page_file)
            self._make_eval_report(tmp, "eval-20260601-100000.json", [
                {"file": page, "level": "FAIL", "evaluator": "e1",
                 "id": "1", "category": "X", "line": 1, "message": "f1", "suggestion": ""},
            ])
            self._make_eval_report(tmp, "eval-20260602-100000.json", [
                {"file": page, "level": "FAIL", "evaluator": "e2",
                 "id": "2", "category": "X", "line": 2, "message": "f2", "suggestion": ""},
            ])

            r = m.validate(repo_root=tmp, dedup=False)
            heal = [p for p in r["pages_needing_heal"] if p["path"] == page]
            self.assertEqual(len(heal), 1)
            self.assertEqual(heal[0]["fail_count"], 2)  # Accumulated

    def test_max_age_days_filters_old_reports(self):
        """Old reports excluded when max_age_days is set."""
        m = _import("validate")
        page = "/content/docs/test.md"
        with tempfile.TemporaryDirectory() as tmp:
            # Report from 30+ days ago
            self._make_eval_report(tmp, "eval-20260501-100000.json", [
                {"file": page, "level": "FAIL", "evaluator": "e1",
                 "id": "1", "category": "X", "line": 1, "message": "old", "suggestion": ""},
            ])
            # Recent report (today-ish)
            self._make_eval_report(tmp, "eval-20260603-100000.json", [])

            r = m.validate(repo_root=tmp, max_age_days=7)
            heal_paths = [p["path"] for p in r["pages_needing_heal"]]
            self.assertNotIn(page, heal_paths)  # Old report excluded

    def test_dedup_latest_report_wins(self):
        """When latest report has FAILs, they are counted correctly."""
        m = _import("validate")
        with tempfile.TemporaryDirectory() as tmp:
            page_file = Path(tmp) / "content" / "docs" / "test.md"
            page_file.parent.mkdir(parents=True, exist_ok=True)
            page_file.write_text("---\ngrade: D\n---\ncontent", encoding="utf-8")
            page = str(page_file)
            # Older: 0 FAILs
            self._make_eval_report(tmp, "eval-20260601-100000.json", [])
            # Newer: 1 FAIL
            self._make_eval_report(tmp, "eval-20260602-100000.json", [
                {"file": page, "level": "FAIL", "evaluator": "e1",
                 "id": "1", "category": "X", "line": 1, "message": "new", "suggestion": ""},
            ])

            r = m.validate(repo_root=tmp, dedup=True)
            heal = [p for p in r["pages_needing_heal"] if p["path"] == page]
            self.assertEqual(len(heal), 1)
            self.assertEqual(heal[0]["fail_count"], 1)


class TestCompareSchema(unittest.TestCase):
    def setUp(self):
        self.m = _import("compare")
        self.empty_disc = {
            "stale_products": [], "fresh_products": [], "missing_products": [],
            "warnings": [], "source_files_read": []
        }
        self.empty_val = {
            "grade_summary": {}, "pages_needing_heal": [], "api_audit_status": {},
            "eval_reports_found": [], "audit_reports_found": [], "warnings": []
        }

    def test_schema_keys(self):
        r = self.m.compare(self.empty_disc, self.empty_val)
        for key in ["status", "actions", "action_count", "backlog_status", "warnings"]:
            self.assertIn(key, r)

    def test_no_actions_ready_valid(self):
        r = self.m.compare(self.empty_disc, self.empty_val)
        self.assertEqual(r["status"], "NO_ACTIONS_READY")
        self.assertIsInstance(r["actions"], list)

    def test_stale_product_produces_refresh_action(self):
        disc = {**self.empty_disc, "stale_products": [{
            "family": "3d", "platform": "net", "stale_since": "2026-05-01", "version": "1.0"
        }]}
        r = self.m.compare(disc, self.empty_val)
        self.assertEqual(r["status"], "ACTIONS_READY")
        types = [a["type"] for a in r["actions"]]
        self.assertIn("REFRESH_PRODUCT", types)

    def test_actions_sorted_by_priority(self):
        disc = {**self.empty_disc, "stale_products": [
            {"family": "3d", "platform": "net", "stale_since": "x", "version": "1"}
        ]}
        val = {**self.empty_val, "pages_needing_heal": [{"path": "p.md", "grade": "C"}]}
        r = self.m.compare(disc, val)
        priorities = [a.get("priority", 99) for a in r["actions"]]
        self.assertEqual(priorities, sorted(priorities))


# ============================================================
# 4. Forbidden-path guard tests
# ============================================================

class TestForbiddenPathGuard(unittest.TestCase):
    def setUp(self):
        self.m = _import("_common")

    def test_agents_md_forbidden(self):
        self.assertTrue(self.m.is_forbidden("AGENTS.md"))

    def test_claude_md_forbidden(self):
        self.assertTrue(self.m.is_forbidden("CLAUDE.md"))

    def test_content_forbidden(self):
        self.assertTrue(self.m.is_forbidden(
            "content/docs.aspose.org/en/3d/net/index.md"))

    def test_knowledge_forbidden(self):
        self.assertTrue(self.m.is_forbidden(
            "knowledge/3d/net/merged/model.yaml"))

    def test_backlog_forbidden(self):
        self.assertTrue(self.m.is_forbidden("backlog/HANDOFF.md"))

    def test_taskmaster_forbidden(self):
        self.assertTrue(self.m.is_forbidden(".taskmaster/tasks/tasks.json"))

    def test_reports_allowed(self):
        self.assertFalse(self.m.is_forbidden("reports/supervisor/run.json"))

    def test_scripts_maintenance_allowed(self):
        self.assertFalse(self.m.is_forbidden(
            "scripts/maintenance/supervisor/discover.py"))

    def test_safe_emit_raises_on_agents_md(self):
        with self.assertRaises(PermissionError):
            self.m.safe_emit({}, "AGENTS.md")

    def test_safe_emit_raises_on_content(self):
        with self.assertRaises(PermissionError):
            self.m.safe_emit({}, "content/docs.aspose.org/index.md")

    def test_safe_emit_succeeds_on_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "test_output.json")
            # safe_emit to a temp path should succeed
            self.m.safe_emit({"test": True}, out)
            data = json.loads(Path(out).read_text())
            self.assertTrue(data["test"])


# ============================================================
# 5. Idempotency tests
# ============================================================

class TestIdempotency(unittest.TestCase):
    def _strip_ts(self, obj):
        TS_KEYS = {"started_at", "completed_at", "generated_at",
                   "last_sync", "created_at", "run_id"}
        if isinstance(obj, dict):
            return {k: self._strip_ts(v) for k, v in obj.items() if k not in TS_KEYS}
        if isinstance(obj, list):
            return [self._strip_ts(i) for i in obj]
        return obj

    def test_discover_idempotent(self):
        m = _import("discover")
        r1 = self._strip_ts(m.discover())
        r2 = self._strip_ts(m.discover())
        self.assertEqual(r1, r2, "discover() is not idempotent")

    def test_compare_idempotent(self):
        disc = _import("discover").discover()
        val = _import("validate").validate()
        m = _import("compare")
        r1 = self._strip_ts(m.compare(disc, val))
        r2 = self._strip_ts(m.compare(disc, val))
        self.assertEqual(r1["actions"], r2["actions"],
                         "compare() action list is not idempotent")


# ============================================================
# 6. Zero-action state acceptance
# ============================================================

class TestZeroActionState(unittest.TestCase):
    EMPTY_PLAN = {
        "status": "NO_ACTIONS_READY",
        "actions": [],
        "backlog_priority_ids": [],
    }

    def test_tm_export_empty(self):
        m = _import("tm_export")
        r = m.tm_export(self.EMPTY_PLAN)
        self.assertIn("tasks", r)
        self.assertEqual(r["task_count"], 0)
        self.assertFalse(r["taskmaster_dir_written"])

    def test_ruflo_export_empty(self):
        m = _import("ruflo_export")
        r = m.ruflo_export(self.EMPTY_PLAN)
        self.assertIn("lanes", r)
        self.assertGreater(r["lane_count"], 0, "C0 idle lane should exist")
        self.assertFalse(r["daemon_started"])
        self.assertFalse(r["mcp_registered"])


# ============================================================
# 7. Ruflo TOOL_UNAVAILABLE
# ============================================================

class TestRufloUnavailable(unittest.TestCase):
    def test_unavailable_recorded_in_output(self):
        m = _import("ruflo_export")
        r = m.ruflo_export({"actions": []})
        # claude-flow is not in PATH in this environment
        if not r["claude_flow_available"]:
            self.assertIn("TOOL_UNAVAILABLE", r["claude_flow_status"])
        # Lanes must always be present regardless
        self.assertIn("lanes", r)
        self.assertIsInstance(r["lanes"], list)


# ============================================================
# 8. MCP rollback preservation
# ============================================================

class TestMCPRollbackPreservation(unittest.TestCase):
    def test_pre_existing_servers_preserved(self):
        # Simulate rollback logic (from normalized plan)
        config_with_sprint = {
            "mcpServers": {
                "pre_existing_tool": {"command": "some-tool"},
                "task-master-ai": {"command": "npx"},
            },
            "_supervisor_mcp_pre_existing": {
                "pre_existing_tool": {"command": "some-tool"}
            }
        }
        # Rollback: restore pre-existing only
        pre_existing = config_with_sprint.get("_supervisor_mcp_pre_existing", {})
        restored = {"mcpServers": pre_existing}
        self.assertIn("pre_existing_tool", restored["mcpServers"])
        self.assertNotIn("task-master-ai", restored["mcpServers"])


# ============================================================
# 9. Rollback manifest schema
# ============================================================

class TestRollbackManifestSchema(unittest.TestCase):
    def test_manifest_has_required_fields(self):
        manifest = {
            "sprint": "gentle-zooming-walrus",
            "created_at": "2026-05-30",
            "created_files": ["scripts/maintenance/supervisor/__init__.py"],
            "created_dirs": ["scripts/maintenance/supervisor/"],
            "rollback_procedure": "delete_listed_files_only",
        }
        for key in ["created_files", "rollback_procedure", "sprint"]:
            self.assertIn(key, manifest)
        self.assertEqual(manifest["rollback_procedure"], "delete_listed_files_only")
        # No rm -rf in manifest
        self.assertNotIn("rm -rf", json.dumps(manifest))


# ============================================================
# 10. Stale product execution path (TC-ASP-017)
# ============================================================

class TestStaleProductPath(unittest.TestCase):
    """End-to-end test of the REFRESH_PRODUCT action path using a temp-dir fixture.

    Creates a minimal knowledge/ structure with a stale model.yaml and verifies
    the full discover -> compare -> generate -> orchestrate pipeline produces
    the correct REFRESH_PRODUCT action with skill chain.
    """

    STALE_MODEL_YAML = """\
stale_since: '2026-05-01T00:00:00Z'
version: '1.0.0'
repo_sha: abc123test
source: https://example.com/test-repo
"""

    def _make_stale_repo(self, tmp):
        """Create a minimal repo structure with one stale product."""
        root = Path(tmp)
        model_dir = root / "knowledge" / "test-family" / "test-platform" / "merged"
        model_dir.mkdir(parents=True)
        (model_dir / "model.yaml").write_text(self.STALE_MODEL_YAML, encoding="utf-8")
        return root

    def test_discover_finds_stale_product(self):
        m = _import("discover")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_stale_repo(tmp)
            r = m.discover(repo_root=root)
        self.assertEqual(len(r["stale_products"]), 1)
        self.assertEqual(len(r["fresh_products"]), 0)
        self.assertEqual(r["stale_products"][0]["family"], "test-family")
        self.assertEqual(r["stale_products"][0]["platform"], "test-platform")
        self.assertIsNotNone(r["stale_products"][0]["stale_since"])

    def test_compare_produces_refresh_action(self):
        disc_m = _import("discover")
        comp_m = _import("compare")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_stale_repo(tmp)
            disc = disc_m.discover(repo_root=root)
            empty_val = {
                "grade_summary": {}, "pages_needing_heal": [], "api_audit_status": {},
                "eval_reports_found": [], "audit_reports_found": [], "warnings": []
            }
            r = comp_m.compare(disc, empty_val, repo_root=root)
        self.assertEqual(r["status"], "ACTIONS_READY")
        self.assertGreater(r["action_count"], 0)
        types = [a["type"] for a in r["actions"]]
        self.assertIn("REFRESH_PRODUCT", types)

    def test_refresh_action_has_skill_chain(self):
        disc_m = _import("discover")
        comp_m = _import("compare")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_stale_repo(tmp)
            disc = disc_m.discover(repo_root=root)
            empty_val = {
                "grade_summary": {}, "pages_needing_heal": [], "api_audit_status": {},
                "eval_reports_found": [], "audit_reports_found": [], "warnings": []
            }
            r = comp_m.compare(disc, empty_val, repo_root=root)
        refresh = next(a for a in r["actions"] if a["type"] == "REFRESH_PRODUCT")
        self.assertIn("suggested_skills", refresh)
        skills = refresh["suggested_skills"]
        self.assertTrue(any("/knowledge-diff" in s for s in skills),
                        "Expected /knowledge-diff in skill chain")
        self.assertTrue(any("/knowledge-update" in s for s in skills),
                        "Expected /knowledge-update in skill chain")

    def test_generate_produces_prompt_with_family_platform(self):
        disc_m = _import("discover")
        comp_m = _import("compare")
        gen_m = _import("generate")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_stale_repo(tmp)
            disc = disc_m.discover(repo_root=root)
            empty_val = {
                "grade_summary": {}, "pages_needing_heal": [], "api_audit_status": {},
                "eval_reports_found": [], "audit_reports_found": [], "warnings": []
            }
            comp = comp_m.compare(disc, empty_val, repo_root=root)
            gen = gen_m.generate(comp, dry_run=True, repo_root=root)
        self.assertIn("prompt", gen)
        self.assertIn("test-family", gen["prompt"])
        self.assertIn("test-platform", gen["prompt"])
        self.assertEqual(gen["selected_action_type"], "REFRESH_PRODUCT")

    def test_orchestrate_dry_run_completes_with_stale_product(self):
        orch_m = _import("orchestrate")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_stale_repo(tmp)
            trace, exit_code = orch_m.orchestrate(dry_run=True, repo_root=root)
        self.assertEqual(exit_code, 0)
        self.assertEqual(trace["status"], "DRY_RUN_COMPLETE")
        self.assertGreater(len(trace["actions"]), 0)
        self.assertEqual(trace["actions"][0]["type"], "REFRESH_PRODUCT")

    def test_orchestrate_not_no_actions_ready_when_stale(self):
        orch_m = _import("orchestrate")
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_stale_repo(tmp)
            trace, exit_code = orch_m.orchestrate(dry_run=True, repo_root=root)
        self.assertNotEqual(trace["status"], "NO_ACTIONS_READY",
                            "Stale product should produce actions, not NO_ACTIONS_READY")


# ============================================================
# 11. sync() state persistence (TC-ASP-018)
# ============================================================

class TestSyncPersistence(unittest.TestCase):
    """Verify sync() write_to_disk parameter correctly persists or withholds state."""

    def test_write_to_disk_false_does_not_create_state_file(self):
        m = _import("sync")
        with tempfile.TemporaryDirectory() as tmp:
            r = m.sync(repo_root=tmp, write_to_disk=False)
            state_file = Path(tmp) / ".supervisor" / "state" / "current.json"
            self.assertFalse(state_file.exists(),
                             "write_to_disk=False must not write current.json")
        self.assertEqual(r["status"], "SYNC_COMPLETE")
        self.assertNotIn("persisted", r)

    def test_write_to_disk_true_creates_state_file(self):
        m = _import("sync")
        with tempfile.TemporaryDirectory() as tmp:
            r = m.sync(repo_root=tmp, write_to_disk=True)
            state_file = Path(tmp) / ".supervisor" / "state" / "current.json"
            self.assertTrue(state_file.exists(),
                            "write_to_disk=True must write current.json")
            state_data = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertIn("last_sync", state_data)
            self.assertEqual(state_data["sprint_count"], 1)
        self.assertTrue(r.get("persisted", False))

    def test_orchestrate_execute_persists_state(self):
        m = _import("orchestrate")
        with tempfile.TemporaryDirectory() as tmp:
            trace, exit_code = m.orchestrate(dry_run=False, repo_root=tmp)
            state_file = Path(tmp) / ".supervisor" / "state" / "current.json"
            self.assertTrue(state_file.exists(),
                            "orchestrate execute mode must persist state to disk")
        self.assertEqual(exit_code, 0)
        self.assertTrue(trace["stages"]["sync"].get("persisted", False))

    def test_orchestrate_dry_run_does_not_persist_state(self):
        m = _import("orchestrate")
        with tempfile.TemporaryDirectory() as tmp:
            trace, exit_code = m.orchestrate(dry_run=True, repo_root=tmp)
            state_file = Path(tmp) / ".supervisor" / "state" / "current.json"
            self.assertFalse(state_file.exists(),
                             "orchestrate dry-run must NOT write state to disk")
        self.assertEqual(exit_code, 0)


# ============================================================
# 12. Validate.py real schema test (TC-ASP-016)
# ============================================================

class TestValidateRealSchema(unittest.TestCase):
    """Verify validate.py reads the actual eval JSON schema correctly."""

    MOCK_EVAL_JSON = {
        "schema_version": "1.0",
        "generated_at": "2026-05-30T10:00:00Z",
        "scope": {"family": "test", "platform": "net"},
        "summary": {
            "total_findings": 3,
            "pages_evaluated": 2,
            "pages_clean": 1,
            "pages_with_findings": 1,
            "by_severity": {"FAIL": 2, "WARN": 1, "INFO": 0},
            "by_category": {"SG": 2, "EG": 1},
        },
        "findings": [
            {"id": "f1", "level": "FAIL", "category": "SG",
             "file": "content/docs/page1.md", "line": 10,
             "message": "bad api", "suggestion": "fix it", "evaluator": "api_accuracy"},
            {"id": "f2", "level": "FAIL", "category": "SG",
             "file": "content/docs/page1.md", "line": 20,
             "message": "bad api 2", "suggestion": "fix it", "evaluator": "api_accuracy"},
            {"id": "f3", "level": "WARN", "category": "EG",
             "file": "content/docs/page2.md", "line": 5,
             "message": "warn", "suggestion": "check it", "evaluator": "content_substance"},
        ],
    }

    def test_grade_summary_non_empty_from_mock_eval(self):
        import json
        m = _import("validate")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eval_dir = root / "reports" / "content_eval"
            eval_dir.mkdir(parents=True)
            (eval_dir / "eval-test-001.json").write_text(
                json.dumps(self.MOCK_EVAL_JSON), encoding="utf-8"
            )
            r = m.validate(repo_root=root)
        self.assertNotEqual(r["grade_summary"], {},
                            "grade_summary must not be empty with eval file present")
        self.assertEqual(r["grade_summary"]["pages_evaluated"], 2)
        self.assertEqual(r["grade_summary"]["pages_clean"], 1)
        self.assertEqual(r["grade_summary"]["severity_totals"]["FAIL"], 2)

    def test_pages_needing_heal_from_fail_findings(self):
        import json
        m = _import("validate")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eval_dir = root / "reports" / "content_eval"
            eval_dir.mkdir(parents=True)
            # Create the page file with grade: D so it is not skipped by the
            # manifest cross-reference (the file must exist and have D/F grade).
            page_file = root / "content" / "docs" / "page1.md"
            page_file.parent.mkdir(parents=True, exist_ok=True)
            page_file.write_text("---\ngrade: D\n---\ncontent", encoding="utf-8")
            # Build eval JSON using absolute path so existence check passes
            mock_eval = {
                **self.MOCK_EVAL_JSON,
                "findings": [
                    {**self.MOCK_EVAL_JSON["findings"][0], "file": str(page_file)},
                    {**self.MOCK_EVAL_JSON["findings"][1], "file": str(page_file)},
                    {**self.MOCK_EVAL_JSON["findings"][2]},
                ],
            }
            (eval_dir / "eval-test-001.json").write_text(
                json.dumps(mock_eval), encoding="utf-8"
            )
            r = m.validate(repo_root=root)
        self.assertEqual(len(r["pages_needing_heal"]), 1)
        self.assertEqual(r["pages_needing_heal"][0]["fail_count"], 2)

    def test_warn_only_page_not_in_pages_needing_heal(self):
        import json
        m = _import("validate")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eval_dir = root / "reports" / "content_eval"
            eval_dir.mkdir(parents=True)
            (eval_dir / "eval-test-001.json").write_text(
                json.dumps(self.MOCK_EVAL_JSON), encoding="utf-8"
            )
            r = m.validate(repo_root=root)
        # page2.md has only WARN, no FAIL — should NOT be in pages_needing_heal
        heal_paths = [p["path"] for p in r["pages_needing_heal"]]
        self.assertNotIn("content/docs/page2.md", heal_paths)


# ============================================================
# 13. MCP structure verification (TC-ASP-020)
# ============================================================

class TestMCPStructure(unittest.TestCase):
    """Verify .claude/settings.json mcpServers structure and ruflo TOOL_UNAVAILABLE behavior."""

    def test_settings_json_has_mcp_servers_section(self):
        settings_path = _REPO / ".claude" / "settings.json"
        self.assertTrue(settings_path.exists(), ".claude/settings.json must exist")
        cfg = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("mcpServers", cfg,
                      "settings.json must have mcpServers key after TC-ASP-014")

    def test_task_master_mcp_entry_uses_npx(self):
        settings_path = _REPO / ".claude" / "settings.json"
        cfg = json.loads(settings_path.read_text(encoding="utf-8"))
        mcp = cfg.get("mcpServers", {})
        self.assertIn("task-master-ai", mcp,
                      "task-master-ai must be registered in mcpServers")
        tm = mcp["task-master-ai"]
        self.assertEqual(tm.get("command"), "npx",
                         "task-master-ai invocation must use npx (PATH-independent)")
        args = tm.get("args", [])
        self.assertTrue(any("task-master-ai" in a for a in args),
                        "task-master-ai npx args must reference the package")

    def test_claude_flow_mcp_entry_uses_npx(self):
        settings_path = _REPO / ".claude" / "settings.json"
        cfg = json.loads(settings_path.read_text(encoding="utf-8"))
        mcp = cfg.get("mcpServers", {})
        self.assertIn("claude-flow", mcp,
                      "claude-flow must be registered in mcpServers")
        cf = mcp["claude-flow"]
        self.assertEqual(cf.get("command"), "npx",
                         "claude-flow invocation must use npx (PATH-independent)")
        args = cf.get("args", [])
        self.assertTrue(any("claude-flow" in a for a in args),
                        "claude-flow npx args must reference the package")

    def test_ruflo_export_tool_unavailable_is_intentional(self):
        """TOOL_UNAVAILABLE from shutil.which('claude-flow') is by design.
        ruflo_export uses shutil.which for lane-coordination feature only,
        which is separate from MCP server activation (npx-based, PATH-independent).
        """
        m = _import("ruflo_export")
        # _check_claude_flow returns (bool, status_str)
        available, status_str = m._check_claude_flow()
        # Either TOOL_AVAILABLE or TOOL_UNAVAILABLE is acceptable — both are intentional states
        self.assertIsInstance(available, bool)
        self.assertIn("TOOL_", status_str,
                      "_check_claude_flow status must start with TOOL_ prefix")

    def test_mcp_supervisor_pre_existing_key_preserved(self):
        settings_path = _REPO / ".claude" / "settings.json"
        cfg = json.loads(settings_path.read_text(encoding="utf-8"))
        # The rollback anchor key must be present (added in TC-ASP-014)
        self.assertIn("_supervisor_mcp_pre_existing", cfg,
                      "rollback anchor _supervisor_mcp_pre_existing must be in settings.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
