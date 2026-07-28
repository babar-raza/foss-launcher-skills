"""Tests for project_phase_store.py and no_downgrade_guard.py."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import no_downgrade_guard  # noqa: E402
import project_phase_store  # noqa: E402


_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@contextmanager
def fake_content_target():
    from commands.knowledge import knowledge_core

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        merged = root / "knowledge" / "fake" / "python" / "merged"
        merged.mkdir(parents=True)

        for fname in (
            "fake_api_surface.json",
            "fake_model.yaml",
            "fake_claims.json",
            "fake_formats.json",
            "fake_index.json",
        ):
            dest = fname.replace("fake_", "")
            shutil.copy(_FIXTURES_DIR / fname, merged / dest)
        (merged / "install.md").write_text("pip install aspose-fake-foss\n", encoding="utf-8")

        original_root = knowledge_core._KNOWLEDGE_ROOT
        knowledge_core._KNOWLEDGE_ROOT = root / "knowledge"

        content_root = root / "content" / "docs.aspose.org" / "en" / "fake" / "python"
        content_root.mkdir(parents=True)
        target = content_root / "sample.md"
        try:
            yield target
        finally:
            knowledge_core._KNOWLEDGE_ROOT = original_root


def _page_body(body: str, *, code_lang: str | None = None, apis: list[str] | None = None) -> str:
    if code_lang:
        body = f"```{code_lang}\n{body}\n```"
    if apis:
        api_block = "  apis:\n" + "\n".join(f"    - {api}" for api in apis) + "\n"
    else:
        api_block = "  apis: []\n"
    return (
        "---\n"
        "title: Sample\n"
        "description: Sample page\n"
        "draft: false\n"
        "type: docs\n"
        "evidence:\n"
        "  model_sha: \"abc\"\n"
        "  claims: []\n"
        f"{api_block}"
        "---\n\n"
        f"{body}\n"
    )


class ProjectPhaseStoreTests(unittest.TestCase):
    def test_set_get_clear_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"

            self.assertEqual(project_phase_store.main([
                "set",
                "slides",
                "python",
                "knowledge_ready",
                "true",
                "--state-file",
                str(state_file),
            ]), 0)

            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertIs(state["slides/python"]["values"]["knowledge_ready"], True)

            self.assertEqual(project_phase_store.main([
                "set",
                "slides",
                "python",
                "complete",
                "--state-file",
                str(state_file),
            ]), 0)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["slides/python"]["values"]["phase"], "complete")

            self.assertEqual(project_phase_store.main([
                "clear",
                "slides",
                "python",
                "knowledge_ready",
                "--state-file",
                str(state_file),
            ]), 0)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertNotIn("knowledge_ready", state["slides/python"]["values"])

    def test_corrupt_state_is_backed_up(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            state_file.write_text("{bad json", encoding="utf-8")

            state, backup = project_phase_store.load_state(state_file)
            self.assertEqual(state, {})
            self.assertIsNotNone(backup)
            self.assertTrue(backup.exists())
            self.assertIn("corrupt", backup.name)

    def test_concurrent_sets_no_lost_updates(self):
        """HARDEN-A2: two threads setting different keys must both land — the
        unlocked read-mutate-save used to silently drop one write."""
        import threading
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            errors: list[Exception] = []

            def worker(key_prefix: str):
                try:
                    for i in range(10):
                        rc = project_phase_store.main([
                            "set", "fam", "plat", f"{key_prefix}_{i}", "true",
                            "--state-file", str(state_file),
                        ])
                        assert rc == 0
                except Exception as exc:  # pragma: no cover - diagnostics
                    errors.append(exc)

            threads = [__import__("threading").Thread(target=worker, args=(p,))
                       for p in ("alpha", "beta")]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=120)

            self.assertEqual(errors, [])
            state = json.loads(state_file.read_text(encoding="utf-8"))
            values = state["fam/plat"]["values"]
            self.assertEqual(
                sum(1 for k in values if k.startswith(("alpha_", "beta_"))), 20,
                f"lost update: only {sorted(values)} present",
            )


class BlogDoneEvidenceGuardTests(unittest.TestCase):
    """HARDEN-A6 (MT012): blog_done=true must carry real evidence.

    Found live: cells/cpp's phase_state.json entry had blog_done: true with
    zero blog content anywhere on disk. This guard refuses that write going
    forward -- either a real --artifact fingerprint, or an explicit
    blog_skipped reason instead.
    """

    def test_bare_blog_done_true_without_artifact_is_refused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            with self.assertRaises(SystemExit) as ctx:
                project_phase_store.main([
                    "set", "cells", "cpp", "blog_done", "true",
                    "--state-file", str(state_file),
                ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertFalse(state_file.exists())

    def test_blog_done_true_with_artifact_succeeds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            artifact = Path(temp_dir) / "index.md"
            artifact.write_text("# Blog index\n", encoding="utf-8")

            rc = project_phase_store.main([
                "set", "pdf", "cpp", "blog_done", "true",
                "--state-file", str(state_file),
                "--artifact", str(artifact),
            ])
            self.assertEqual(rc, 0)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertIs(state["pdf/cpp"]["values"]["blog_done"], True)
            self.assertIn("blog_done__fingerprint", state["pdf/cpp"]["values"])

    def test_blog_done_false_does_not_require_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            rc = project_phase_store.main([
                "set", "cells", "cpp", "blog_done", "false",
                "--state-file", str(state_file),
            ])
            self.assertEqual(rc, 0)

    def test_blog_skipped_reason_does_not_require_artifact(self):
        """The honest alternative to a bare blog_done:true lie."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            rc = project_phase_store.main([
                "set", "cells", "cpp", "blog_skipped",
                "below blog-eligibility claim threshold",
                "--state-file", str(state_file),
            ])
            self.assertEqual(rc, 0)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(
                state["cells/cpp"]["values"]["blog_skipped"],
                "below blog-eligibility claim threshold",
            )

    def test_other_done_keys_unaffected(self):
        """Guard is scoped to blog_done only, not every _done key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            rc = project_phase_store.main([
                "set", "cells", "cpp", "docs_done", "true",
                "--state-file", str(state_file),
            ])
            self.assertEqual(rc, 0)


class VerifyCheckpointTests(unittest.TestCase):
    """HARDEN-A5: artifact-fingerprinted checkpoints."""

    def test_set_with_artifact_then_verify_ok(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            artifact = Path(temp_dir) / "site_plan.yaml"
            artifact.write_text("pages: [a, b]\n", encoding="utf-8")

            rc = project_phase_store.main([
                "set", "words", "net", "site_plan_done", "true",
                "--state-file", str(state_file),
                "--artifact", str(artifact),
            ])
            self.assertEqual(rc, 0)
            rc = project_phase_store.main([
                "verify", "words", "net", "site_plan_done",
                "--state-file", str(state_file),
            ])
            self.assertEqual(rc, 0)

    def test_verify_detects_artifact_drift(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            artifact = Path(temp_dir) / "site_plan.yaml"
            artifact.write_text("pages: [a, b]\n", encoding="utf-8")

            project_phase_store.main([
                "set", "words", "net", "site_plan_done", "true",
                "--state-file", str(state_file),
                "--artifact", str(artifact),
            ])
            artifact.write_text("pages: [CORRUPTED]\n", encoding="utf-8")

            state, _ = project_phase_store.load_state(state_file)
            ok, notes = project_phase_store.verify_checkpoint(state, "words", "net", "site_plan_done")
            self.assertFalse(ok)
            self.assertTrue(any("content changed" in n for n in notes))

    def test_verify_detects_missing_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "phase_state.json"
            artifact = Path(temp_dir) / "site_plan.yaml"
            artifact.write_text("pages: [a]\n", encoding="utf-8")

            project_phase_store.main([
                "set", "words", "net", "site_plan_done", "true",
                "--state-file", str(state_file),
                "--artifact", str(artifact),
            ])
            artifact.unlink()

            state, _ = project_phase_store.load_state(state_file)
            ok, notes = project_phase_store.verify_checkpoint(state, "words", "net", "site_plan_done")
            self.assertFalse(ok)
            self.assertTrue(any("missing" in n for n in notes))

    def test_legacy_bool_only_checkpoint_is_unverifiable_not_blocking(self):
        """2026-06-era entries have no fingerprint — they warn, never block."""
        state = {
            "3d/java": {
                "values": {"docs_done": True},
                "updated_at": "2026-06-14T06:19:26+00:00",
                "updated_by": "agent",
            }
        }
        ok, notes = project_phase_store.verify_checkpoint(state, "3d", "java", "docs_done")
        self.assertTrue(ok)
        self.assertTrue(any("unverifiable" in n for n in notes))

    def test_unset_checkpoint_fails_verify(self):
        ok, notes = project_phase_store.verify_checkpoint({}, "words", "net", "docs_done")
        self.assertFalse(ok)
        self.assertTrue(any("not set" in n for n in notes))


class ValidateCompletionTests(unittest.TestCase):
    def test_readiness_done_with_all_hgates_no_warnings(self):
        """readiness_done=true with all H-gate files present → no warnings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            hgate_dir = root / "reports" / "human-review"
            hgate_dir.mkdir(parents=True)
            for gate in ("h01", "h02", "h03", "h04", "h05"):
                (hgate_dir / f"pdf-net-{gate}-sample.md").write_text(
                    f"# H-{gate}\nresult: PASS\n", encoding="utf-8"
                )
            state = {
                "pdf/net": {
                    "values": {"readiness_done": True},
                    "updated_by": "test",
                    "updated_at": "2026-06-15",
                }
            }
            import os
            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                warnings = project_phase_store.validate_completion(state, "pdf", "net")
            finally:
                os.chdir(old_cwd)
            self.assertEqual(warnings, [])

    def test_readiness_done_with_missing_hgates_warns(self):
        """readiness_done=true with missing H-gate files → warnings returned."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            hgate_dir = root / "reports" / "human-review"
            hgate_dir.mkdir(parents=True)
            # Only create h01 and h02
            for gate in ("h01", "h02"):
                (hgate_dir / f"pdf-net-{gate}-sample.md").write_text(
                    f"# H-{gate}\nresult: PASS\n", encoding="utf-8"
                )
            state = {
                "pdf/net": {
                    "values": {"readiness_done": True},
                    "updated_by": "test",
                    "updated_at": "2026-06-15",
                }
            }
            import os
            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                warnings = project_phase_store.validate_completion(state, "pdf", "net")
            finally:
                os.chdir(old_cwd)
            self.assertEqual(len(warnings), 3)  # h03, h04, h05 missing
            self.assertTrue(all("missing" in w.lower() for w in warnings))

    def test_readiness_not_done_with_missing_hgates_no_warnings(self):
        """readiness_done=false with missing H-gate files → no warnings."""
        state = {
            "pdf/net": {
                "values": {"readiness_done": False},
                "updated_by": "test",
                "updated_at": "2026-06-15",
            }
        }
        warnings = project_phase_store.validate_completion(state, "pdf", "net")
        self.assertEqual(warnings, [])


class NoDowngradeGuardTests(unittest.TestCase):
    def test_new_file_is_allow(self):
        with fake_content_target() as target:
            result = no_downgrade_guard.compare_content(
                target,
                _page_body(
                    'scene = Scene.from_file("in.3ds")\nscene.save("out.obj")',
                    code_lang="python",
                    apis=["Scene.from_file", "Scene.save"],
                ),
                family="fake",
                platform="python",
            )
        self.assertEqual(result["decision"], no_downgrade_guard.DECISION_ALLOW)
        self.assertFalse(result["target_exists"])

    def test_regressive_content_is_block(self):
        with fake_content_target() as target:
            target.write_text(
                _page_body(
                    'scene = Scene.from_file("in.3ds")\nscene.save("out.obj")',
                    code_lang="python",
                    apis=["Scene.from_file", "Scene.save"],
                ),
                encoding="utf-8",
            )

            proposed = _page_body(
                'scene = Scene.from_file("in.3ds")\nscene.fake_one()\nscene.fake_two()\nscene.fake_three()',
                code_lang="python",
                apis=["Scene.fake_one", "Scene.fake_two", "Scene.fake_three"],
            )
            result = no_downgrade_guard.compare_content(
                target,
                proposed,
                family="fake",
                platform="python",
            )

        # Canonical compute_grade: 0 FAIL + 0 WARN = A (was B under old proxy)
        self.assertIn(result["existing"]["grade"], {"A", "B"})
        self.assertIn(result["proposed"]["grade"], {"D", "F"})
        self.assertEqual(result["decision"], no_downgrade_guard.DECISION_BLOCK)


if __name__ == "__main__":
    unittest.main()
