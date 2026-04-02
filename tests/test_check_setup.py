"""Tests for scripts/check_setup.py — environment validation before content skills run."""
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_setup import OK, WARN, ERROR, check_setup, _print_issues  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _levels(issues):
    """Return just the level strings from a list of (level, msg) tuples."""
    return [lvl for lvl, _ in issues]


def _msgs(issues):
    """Return just the message strings."""
    return [msg for _, msg in issues]


def _has_level(issues, level):
    return any(lvl == level for lvl, _ in issues)


def _worst(issues):
    rank = {OK: 0, WARN: 1, ERROR: 2}
    return max((rank.get(lvl, 0) for lvl, _ in issues), default=0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_config(tmp_path):
    """Write a valid config.yaml to tmp_path and return it as a dict."""
    config = {
        "content_repo": str(tmp_path),
        "sites": {
            "docs": {"content_path": "content/docs.aspose.org/en/{family}/{platform}/", "type": "docs"},
        },
        "knowledge_path": "knowledge/{family}/{platform}/",
        "evidence_path": "evidence/{family}/{platform}/",
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config), encoding="utf-8")
    return {"path": config_path, "data": config, "root": tmp_path}


@pytest.fixture
def knowledge_merged(tmp_path):
    """Create knowledge/{family}/{platform}/merged/ with index.json and model.yaml.

    Includes stats block with sufficient claims/classes to pass the readiness gate.
    """
    merged = tmp_path / "knowledge" / "words" / "python" / "merged"
    merged.mkdir(parents=True)
    (merged / "index.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
    (merged / "model.yaml").write_text(
        yaml.dump({
            "family": "words",
            "platform": "python",
            "stale_since": None,
            "stats": {"merged_claims": 100, "class_count": 20},
        }),
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# 1. CONTENT_REPO_PATH resolution checks
# ---------------------------------------------------------------------------

class TestContentRepoCheck:
    def test_valid_dir_gives_ok(self, tmp_path):
        """A valid, non-CWD directory should produce an OK line."""
        config = {"content_repo": str(tmp_path)}
        issues = check_setup(config=config, content_root=tmp_path.resolve())
        assert any(OK == lvl and "CONTENT_REPO_PATH" in msg for lvl, msg in issues)

    def test_none_content_root_gives_error(self):
        """When content_root is None the check must emit an ERROR."""
        issues = check_setup(config={}, content_root=None)
        assert _has_level(issues, ERROR)
        assert any("CONTENT_REPO_PATH" in msg for _, msg in issues)

    def test_cwd_fallback_without_content_dir_gives_error(self, tmp_path, monkeypatch):
        """CWD fallback without content/ present should be ERROR."""
        monkeypatch.chdir(tmp_path)
        issues = check_setup(config={}, content_root=tmp_path.resolve())
        # Without content/ dir, this should be an ERROR
        content_repo_issues = [(lvl, msg) for lvl, msg in issues if "CONTENT_REPO_PATH" in msg]
        assert any(lvl == ERROR for lvl, _ in content_repo_issues)

    def test_cwd_fallback_with_content_dir_gives_warn(self, tmp_path, monkeypatch):
        """CWD fallback WITH content/ dir present should be WARN (not ERROR)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "content").mkdir()
        issues = check_setup(config={}, content_root=tmp_path.resolve())
        content_repo_issues = [(lvl, msg) for lvl, msg in issues if "CONTENT_REPO_PATH" in msg]
        assert any(lvl == WARN for lvl, _ in content_repo_issues)
        assert not any(lvl == ERROR for lvl, _ in content_repo_issues)

    def test_explicit_path_not_equal_to_cwd_is_ok(self, tmp_path, monkeypatch):
        """An explicit path that differs from CWD should give OK."""
        # Use a sibling directory to ensure it differs from CWD
        other = tmp_path / "repo"
        other.mkdir()
        monkeypatch.chdir(tmp_path)
        issues = check_setup(config={"content_repo": str(other)}, content_root=other.resolve())
        content_repo_issues = [(lvl, msg) for lvl, msg in issues if "CONTENT_REPO_PATH" in msg]
        assert any(lvl == OK for lvl, _ in content_repo_issues)

    def test_resolved_path_appears_in_ok_message(self, tmp_path):
        """The resolved path string should appear in the OK message."""
        issues = check_setup(config={"content_repo": str(tmp_path)}, content_root=tmp_path.resolve())
        ok_msgs = [msg for lvl, msg in issues if lvl == OK and "CONTENT_REPO_PATH" in msg]
        assert ok_msgs, "Expected an OK message mentioning CONTENT_REPO_PATH"
        assert str(tmp_path.resolve()) in ok_msgs[0]


# ---------------------------------------------------------------------------
# 2. Package checks
# ---------------------------------------------------------------------------

class TestPackageChecks:
    def test_yaml_always_importable(self, tmp_path):
        """yaml is always installed; should produce OK."""
        issues = check_setup(config={}, content_root=tmp_path.resolve())
        pkg_issues = [(lvl, msg) for lvl, msg in issues if "package 'yaml'" in msg]
        assert pkg_issues, "Expected a check for yaml package"
        assert pkg_issues[0][0] == OK

    def test_json_always_importable(self, tmp_path):
        """json is a stdlib module; should always be OK."""
        issues = check_setup(config={}, content_root=tmp_path.resolve())
        pkg_issues = [(lvl, msg) for lvl, msg in issues if "package 'json'" in msg]
        assert pkg_issues, "Expected a check for json package"
        assert pkg_issues[0][0] == OK

    def test_pathlib_always_importable(self, tmp_path):
        """pathlib is a stdlib module; should always be OK."""
        issues = check_setup(config={}, content_root=tmp_path.resolve())
        pkg_issues = [(lvl, msg) for lvl, msg in issues if "package 'pathlib'" in msg]
        assert pkg_issues, "Expected a check for pathlib package"
        assert pkg_issues[0][0] == OK

    def test_tree_sitter_missing_gives_warn(self, tmp_path):
        """Simulate tree_sitter missing via injectable optional packages — WARN, not ERROR."""
        # Inject a fake optional package that does not exist
        issues = check_setup(
            config={},
            content_root=tmp_path.resolve(),
            _optional_packages={"tree_sitter_nonexistent_xyz": "tree-sitter language packs required for repo-scout"},
        )
        ts_issues = [(lvl, msg) for lvl, msg in issues if "tree_sitter_nonexistent_xyz" in msg]
        assert ts_issues, "Expected a check result for the fake tree_sitter package"
        assert ts_issues[0][0] == WARN, f"Expected WARN, got {ts_issues[0][0]}"

    def test_missing_required_package_gives_error(self, tmp_path):
        """Simulate a required package missing via injectable packages — should produce ERROR."""
        issues = check_setup(
            config={},
            content_root=tmp_path.resolve(),
            _required_packages=["nonexistent_package_xyz_required"],
        )
        pkg_issues = [(lvl, msg) for lvl, msg in issues if "nonexistent_package_xyz_required" in msg]
        assert pkg_issues, "Expected a check result for the fake required package"
        assert pkg_issues[0][0] == ERROR, f"Expected ERROR, got {pkg_issues[0][0]}"


# ---------------------------------------------------------------------------
# 3. config.yaml checks
# ---------------------------------------------------------------------------

class TestConfigCheck:
    def test_empty_config_gives_warn(self, tmp_path):
        """Empty config dict should produce a WARN about config.yaml."""
        issues = check_setup(config={}, content_root=tmp_path.resolve())
        config_issues = [(lvl, msg) for lvl, msg in issues if "config.yaml" in msg]
        assert config_issues, "Expected a check result mentioning config.yaml"
        assert config_issues[0][0] == WARN

    def test_non_empty_config_gives_ok(self, tmp_path):
        """Non-empty config dict should produce an OK for config.yaml."""
        issues = check_setup(config={"sites": {}}, content_root=tmp_path.resolve())
        config_issues = [(lvl, msg) for lvl, msg in issues if "config.yaml" in msg]
        assert config_issues, "Expected a check result mentioning config.yaml"
        assert config_issues[0][0] == OK


# ---------------------------------------------------------------------------
# 4. Knowledge model checks
# ---------------------------------------------------------------------------

class TestKnowledgeModelChecks:
    def test_index_present_gives_ok(self, knowledge_merged):
        """All merged artifacts present with sufficient stats → no ERROR for knowledge."""
        issues = check_setup(
            config={"knowledge_root": str(knowledge_merged / "knowledge")},
            content_root=knowledge_merged.resolve(),
            family="words", platform="python"
        )
        # No ERROR among knowledge-related messages
        knowledge_issues = [(lvl, msg) for lvl, msg in issues
                            if "knowledge/words/python" in msg]
        assert knowledge_issues, "Expected at least one knowledge check message"
        assert not any(lvl == ERROR for lvl, msg in knowledge_issues)

    def test_model_yaml_present_gives_ok(self, knowledge_merged):
        """All merged artifacts present → 'artifacts found' OK message."""
        issues = check_setup(
            config={"knowledge_root": str(knowledge_merged / "knowledge")},
            content_root=knowledge_merged.resolve(),
            family="words", platform="python"
        )
        artifact_issues = [(lvl, msg) for lvl, msg in issues if "artifacts found" in msg]
        assert artifact_issues, "Expected an 'artifacts found' OK message"
        assert artifact_issues[0][0] == OK

    def test_index_missing_gives_error(self, tmp_path):
        """model.yaml present but index.json absent → ERROR mentioning index.json."""
        merged = tmp_path / "knowledge" / "words" / "python" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text(
            yaml.dump({"family": "words", "platform": "python"}), encoding="utf-8"
        )
        # index.json intentionally absent

        issues = check_setup(
            config={"knowledge_root": str(tmp_path / "knowledge")},
            content_root=tmp_path.resolve(),
            family="words", platform="python"
        )
        index_issues = [(lvl, msg) for lvl, msg in issues if "index.json" in msg]
        assert index_issues, "Expected a check for index.json"
        assert index_issues[0][0] == ERROR

    def test_model_yaml_missing_gives_error(self, tmp_path):
        """model.yaml absent → ERROR (missing knowledge model is always a hard failure)."""
        merged = tmp_path / "knowledge" / "cells" / "net" / "merged"
        merged.mkdir(parents=True)
        (merged / "index.json").write_text(json.dumps({}), encoding="utf-8")
        # model.yaml intentionally absent

        issues = check_setup(
            config={"knowledge_root": str(tmp_path / "knowledge")},
            content_root=tmp_path.resolve(),
            family="cells", platform="net"
        )
        model_issues = [(lvl, msg) for lvl, msg in issues if "model.yaml" in msg]
        assert model_issues, "Expected a check for model.yaml"
        assert model_issues[0][0] == ERROR

    def test_no_family_platform_skips_knowledge_check(self, tmp_path):
        """Without family+platform, no knowledge checks should appear."""
        issues = check_setup(config={}, content_root=tmp_path.resolve())
        knowledge_issues = [(lvl, msg) for lvl, msg in issues
                            if "index.json" in msg or "model.yaml" in msg]
        assert not knowledge_issues, "Should not check knowledge when family/platform absent"

    def test_only_family_no_platform_skips_knowledge_check(self, tmp_path):
        """With only family (no platform), knowledge check should be skipped."""
        issues = check_setup(config={}, content_root=tmp_path.resolve(), family="words")
        knowledge_issues = [(lvl, msg) for lvl, msg in issues
                            if "index.json" in msg or "model.yaml" in msg]
        assert not knowledge_issues

    def test_error_message_contains_family_and_platform(self, tmp_path):
        """ERROR messages for missing knowledge should mention family/platform."""
        issues = check_setup(
            config={"knowledge_root": str(tmp_path / "knowledge")},
            content_root=tmp_path.resolve(),
            family="pdf", platform="java"
        )
        # model.yaml is the first thing checked when both are absent
        errors = [msg for lvl, msg in issues if lvl == ERROR and ("pdf" in msg or "java" in msg)]
        assert errors, "Expected an ERROR mentioning the family/platform"
        assert "pdf" in errors[0]
        assert "java" in errors[0]


# ---------------------------------------------------------------------------
# 5. Overall exit-code / worst-level logic
# ---------------------------------------------------------------------------

class TestExitCodeLogic:
    def test_all_ok_returns_zero(self, knowledge_merged):
        """All OK issues (with sufficient knowledge) should give no ERROR."""
        issues = check_setup(
            config={
                "sites": {},
                "knowledge_root": str(knowledge_merged / "knowledge"),
            },
            content_root=knowledge_merged.resolve(),
            family="words", platform="python",
        )
        assert not _has_level(issues, ERROR)

    def test_missing_index_pushes_rank_to_error(self, tmp_path):
        """Missing index.json should push worst rank to 2 (ERROR)."""
        issues = check_setup(
            config={}, content_root=tmp_path.resolve(),
            family="words", platform="python",
        )
        assert _worst(issues) == 2

    def test_print_issues_returns_correct_exit_code(self, tmp_path, capsys):
        """_print_issues should return 2 when an ERROR is present."""
        issues = [(ERROR, "something broken")]
        code = _print_issues(issues)
        assert code == 2

    def test_print_issues_warn_only_returns_one(self, capsys):
        """_print_issues with only WARNs should return 1."""
        issues = [(WARN, "something optional missing")]
        code = _print_issues(issues)
        assert code == 1

    def test_print_issues_ok_only_returns_zero(self, capsys):
        """_print_issues with only OKs should return 0."""
        issues = [(OK, "all good")]
        code = _print_issues(issues)
        assert code == 0

    def test_print_issues_outputs_level_prefix(self, capsys):
        """Output lines should contain the level prefix."""
        issues = [(OK, "everything fine"), (WARN, "optional missing")]
        _print_issues(issues)
        captured = capsys.readouterr()
        assert "OK" in captured.out
        assert "WARN" in captured.out


# ---------------------------------------------------------------------------
# 6. CLI integration tests
# ---------------------------------------------------------------------------

class TestCLI:
    def _run(self, *args, env=None):
        """Run check_setup.py as a subprocess and return (returncode, stdout)."""
        script = str(REPO_ROOT / "scripts" / "check_setup.py")
        cmd = [sys.executable, script] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
        return result.returncode, result.stdout, result.stderr

    def test_cli_exit_zero_valid_setup(self, tmp_path):
        """CLI should exit 0 when CONTENT_REPO_PATH is an explicit non-CWD dir."""
        # Use a fresh tmp_path so it differs from CWD (REPO_ROOT)
        env = os.environ.copy()
        env["CONTENT_REPO_PATH"] = str(tmp_path)
        code, stdout, stderr = self._run(env=env)
        assert code == 0, f"Expected exit 0, got {code}.\nstdout={stdout}\nstderr={stderr}"

    def test_cli_exit_nonzero_bad_content_repo(self, tmp_path):
        """CLI should exit non-zero when content_root falls back to CWD without content/."""
        env = os.environ.copy()
        # Remove CONTENT_REPO_PATH so it falls back to CWD
        env.pop("CONTENT_REPO_PATH", None)
        # Also temporarily use a tmp_path as CWD (no content/ inside, no valid config)
        script = str(REPO_ROOT / "scripts" / "check_setup.py")
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            env=env,
        )
        # Should be WARN or ERROR (non-zero)
        # When run from tmp_path with no config.yaml & no content/, expect exit code 2
        assert result.returncode >= 1, (
            f"Expected non-zero exit code, got {result.returncode}.\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )

    def test_cli_output_contains_ok_lines(self, tmp_path):
        """CLI stdout should contain 'OK' lines."""
        env = os.environ.copy()
        env["CONTENT_REPO_PATH"] = str(tmp_path)
        code, stdout, _ = self._run(env=env)
        assert "OK" in stdout

    def test_cli_with_family_platform_and_missing_knowledge(self, tmp_path):
        """CLI with --family/--platform pointing to non-existent knowledge should exit 2."""
        env = os.environ.copy()
        env["CONTENT_REPO_PATH"] = str(tmp_path)
        # Use a family/platform that cannot exist in the real knowledge/ dir
        code, stdout, _ = self._run("--family", "doesnotexist", "--platform", "xyz", env=env)
        assert code == 2, f"Expected exit 2 for missing knowledge, got {code}\n{stdout}"
        assert "model.yaml" in stdout or "knowledge" in stdout

    def test_cli_with_family_platform_and_valid_knowledge(self, tmp_path):
        """CLI with existing valid knowledge (email/python: 488 claims, 36 classes) should exit 0."""
        env = os.environ.copy()
        env["CONTENT_REPO_PATH"] = str(tmp_path)
        code, stdout, _ = self._run("--family", "email", "--platform", "python", env=env)
        assert code == 0, f"Expected exit 0 with valid knowledge, got {code}\n{stdout}"
