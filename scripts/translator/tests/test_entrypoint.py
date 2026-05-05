from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class TranslatorEntrypointTests(unittest.TestCase):
    def test_top_level_translator_module_runs_cache_stats(self):
        result = subprocess.run(
            [sys.executable, "-m", "translator", "cache-stats"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Cache:", result.stdout)

    def test_scripts_translator_module_runs_cache_stats(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.translator", "cache-stats"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Cache:", result.stdout)


if __name__ == "__main__":
    unittest.main()
