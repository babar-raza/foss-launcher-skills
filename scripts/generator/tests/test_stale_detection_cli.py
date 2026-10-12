"""
MT069 HC-12: CLI-level tests proving detect_stale_llms.py's --manifest-path fix.

The underlying detect_issues()/build_manifest() functions (test_stale_detection.py) always
correctly found drift when GIVEN a manifest from before the drift. The real defect was in how
scripts/ci/deployed-workflows/llms-generation.yml (and the private original) used the CLI: it ran
--update-manifest (rebuilds a FRESH manifest by hashing the CURRENT source files) immediately
before --check-only (loads that same just-written manifest and re-hashes the SAME unchanged
files) -- by construction that comparison can never disagree, so the "stale check gate" always
passed regardless of whether anything was actually stale.

--manifest-path lets a caller point --check-only at a manifest PERSISTED FROM A PRIOR RUN (via a
CI artifact -- see the workflow) instead of the one this run just rebuilt, which is what makes the
comparison meaningful. These tests exercise main() itself (not just the pure functions), reproducing
the exact two-step CLI sequence the workflow runs.
"""
import importlib.util
import os

import pytest

_GEN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_STALE_FILE = os.path.join(_GEN_DIR, "detect_stale_llms.py")
_spec = importlib.util.spec_from_file_location("detect_stale_llms_cli", _STALE_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

main = _mod.main


@pytest.fixture
def tmp_env(tmp_path):
    """content/kb.aspose.org/en/pdf/net/how-to-test.md + its llms-output/.../*.txt sibling."""
    src_dir = tmp_path / "content" / "kb.aspose.org" / "en" / "pdf" / "net"
    src_dir.mkdir(parents=True)
    src_md = src_dir / "how-to-test.md"
    src_md.write_text("---\ntitle: Test Article\n---\n\n# Test Article\n\nContent here.\n", encoding="utf-8")

    out_dir = tmp_path / "llms-output" / "kb.aspose.org" / "pdf" / "net"
    out_dir.mkdir(parents=True)
    (out_dir / "how-to-test.txt").write_text(
        "---\nProduct: Aspose.PDF\nPlatform: net\nPage Type: kb\n---\n\n# Test Article\n", encoding="utf-8")

    return {
        "src_md": src_md,
        "llms_output": str(tmp_path / "llms-output"),
        "content": str(tmp_path / "content"),
        "manifest": str(tmp_path / "manifest.json"),
        "report": str(tmp_path / "stale-report.json"),
    }


def _run(tmp_env, *extra):
    return main([
        "--llms-output", tmp_env["llms_output"], "--content", tmp_env["content"],
        "--manifest-path", tmp_env["manifest"], "--stale-report-path", tmp_env["report"],
        *extra,
    ])


class TestTheOldWorkflowPatternWasVacuousByConstruction:
    """Reproduces the exact bug: rebuild-then-check-the-same-run's-own-manifest can never fail,
    even after content that predates the manifest has drifted, because the rebuild step re-reads
    the ALREADY-drifted content and records it as the new truth before the check ever runs."""

    def test_update_then_check_in_one_run_always_passes_regardless_of_prior_drift(self, tmp_env):
        # Content already differs from what generated the .txt output (drift exists RIGHT NOW)...
        tmp_env["src_md"].write_text("---\ntitle: Test Article\n---\n\n# Test Article\n\nDRIFTED CONTENT.\n",
                                      encoding="utf-8")
        # ...but a single run's own --update-manifest + --check-only (the old workflow's own two
        # steps, run back to back against the SAME --manifest-path) cannot see it: it rebuilds the
        # manifest from the (already-drifted) current content, then checks against that.
        assert _run(tmp_env, "--update-manifest", "--check-only") == 0, (
            "This documents the defect, not a requirement: the old two-step CLI pattern is "
            "definitionally blind to any drift that already existed before it ran."
        )


class TestManifestPathMakesCheckOnlyAGenuineCrossRunGate:
    def test_a_prior_run_manifest_catches_drift_the_current_run_introduces(self, tmp_env):
        # Simulates a PRIOR successful run: build + persist the manifest while content is clean.
        assert _run(tmp_env, "--update-manifest") == 0

        # Time passes; content changes WITHOUT anyone re-running the generator.
        tmp_env["src_md"].write_text("---\ntitle: Test Article\n---\n\n# Test Article\n\nModified later.\n",
                                      encoding="utf-8")

        # THIS run checks against the manifest PERSISTED from the prior run (restored from a CI
        # artifact in production) -- not one it just rebuilt -- so it must fail.
        assert _run(tmp_env, "--check-only") == 1

    def test_regenerating_then_updating_the_persisted_manifest_clears_the_finding(self, tmp_env):
        assert _run(tmp_env, "--update-manifest") == 0
        tmp_env["src_md"].write_text("---\ntitle: Test Article\n---\n\n# Test Article\n\nModified later.\n",
                                      encoding="utf-8")
        assert _run(tmp_env, "--check-only") == 1          # caught (previous test's assertion, restated)

        # The generator would normally rewrite the .txt to match here; the manifest update alone is
        # what this CLI controls, and once it reflects the new content the finding clears.
        assert _run(tmp_env, "--update-manifest", "--check-only") == 0

    def test_missing_manifest_at_the_given_path_is_a_clear_error_not_a_silent_pass(self, tmp_env):
        assert _run(tmp_env, "--check-only") == 1

    def test_manifest_path_defaults_to_the_original_constant_for_existing_callers(self, monkeypatch, tmp_path):
        """Existing callers that never pass --manifest-path must be unaffected."""
        monkeypatch.chdir(tmp_path)
        called = {}

        def _fake_save(manifest, manifest_path=_mod.MANIFEST_PATH):
            called["path"] = manifest_path

        monkeypatch.setattr(_mod, "save_manifest", _fake_save)
        monkeypatch.setattr(_mod, "build_manifest", lambda *a, **k: {"page_count": 0, "pages": {}})
        assert main(["--update-manifest"]) == 0
        assert called["path"] == _mod.MANIFEST_PATH
