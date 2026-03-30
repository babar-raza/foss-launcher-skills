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
    import knowledge_core

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        merged = root / "knowledge" / "fake" / "python" / "merged"
        merged.mkdir(parents=True)

        for fname in (
            "fake_api_surface.json",
            "fake_model.yaml",
            "fake_claims.json",
            "fake_formats.json",
        ):
            dest = fname.replace("fake_", "")
            shutil.copy(_FIXTURES_DIR / fname, merged / dest)
        (merged / "install.md").write_text("pip install aspose-fake-foss\n", encoding="utf-8")

        original_root = knowledge_core.KNOWLEDGE_ROOT
        knowledge_core.KNOWLEDGE_ROOT = root / "knowledge"

        content_root = root / "content" / "docs.aspose.org" / "en" / "fake" / "python"
        content_root.mkdir(parents=True)
        target = content_root / "sample.md"
        try:
            yield target
        finally:
            knowledge_core.KNOWLEDGE_ROOT = original_root


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
