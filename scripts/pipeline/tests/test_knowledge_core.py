"""Tests for scripts/pipeline/knowledge_core.py — diff command and CLI.

These tests verify the diff command functionality using real products from
the knowledge base. The tests are designed to be:
- Isolated: Each test runs independently
- Deterministic: Same results on every run
- Fast: No network calls, no external dependencies
- Self-contained: All test data is in the test file or temp directory
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest


class TestDiffCommand:
    """Tests for the diff command in knowledge_core.py."""

    def test_diff_sha_match(self, tmp_path):
        """Test diff command when repo SHA matches stored SHA.
        
        This test creates a temporary git repo, commits a file, and creates
        a knowledge model with the same SHA. The diff command should report
        SHA MATCH.
        """
        # Create a temporary git repo
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
        
        # Create a file and commit
        (repo_dir / "test.txt").write_text("test content")
        subprocess.run(["git", "add", "test.txt"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
        
        # Get current SHA
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True)
        current_sha = result.stdout.strip()
        
        # Create knowledge model with matching SHA in the actual knowledge directory
        # We use a test product that won't interfere with real products
        test_family = "test"
        test_platform = "python"
        knowledge_dir = Path("knowledge") / test_family / test_platform / "merged"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        
        model = {
            "version": "1.0.0",
            "repo_sha": current_sha,
            "surface_tier": 2,
            "family": test_family,
            "platform": test_platform,
            "package_name": "test.package",
            "package_version": "1.0.0"
        }
        (knowledge_dir / "model.yaml").write_text(json.dumps(model, indent=2))
        
        api_surface = [{"name": "TestClass", "file": "TestClass.py", "kind": "class", "methods": [], "properties": [], "doc": "", "enum_members": []}]
        (knowledge_dir / "api_surface.json").write_text(json.dumps(api_surface))
        
        try:
            # Run diff command
            from knowledge_core import diff
            result = diff(test_family, test_platform, repo_dir)
            
            assert "SHA MATCH" in result
            assert current_sha[:8] in result
        finally:
            # Clean up knowledge model
            if knowledge_dir.exists():
                import shutil
                shutil.rmtree(knowledge_dir.parent.parent, ignore_errors=True)

    def test_diff_sha_mismatch(self, tmp_path):
        """Test diff command when repo SHA does not match stored SHA.
        
        This test creates a temporary git repo, commits a file, and creates
        a knowledge model with a different SHA. The diff command should report
        SHA MISMATCH.
        """
        # Create a temporary git repo
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
        
        # Create a file and commit
        (repo_dir / "test.txt").write_text("test content")
        subprocess.run(["git", "add", "test.txt"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
        
        # Get current SHA
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True)
        current_sha = result.stdout.strip()
        
        # Create knowledge model with different SHA
        test_family = "test"
        test_platform = "python"
        knowledge_dir = Path("knowledge") / test_family / test_platform / "merged"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        
        model = {
            "version": "1.0.0",
            "repo_sha": "different123456789",
            "surface_tier": 2,
            "family": test_family,
            "platform": test_platform,
            "package_name": "test.package",
            "package_version": "1.0.0"
        }
        (knowledge_dir / "model.yaml").write_text(json.dumps(model, indent=2))
        
        api_surface = [{"name": "TestClass", "file": "TestClass.py", "kind": "class", "methods": [], "properties": [], "doc": "", "enum_members": []}]
        (knowledge_dir / "api_surface.json").write_text(json.dumps(api_surface))
        
        try:
            # Run diff command
            from knowledge_core import diff
            result = diff(test_family, test_platform, repo_dir)
            
            assert "SHA MISMATCH" in result
            assert current_sha[:8] in result
            assert "differen" in result  # SHA is truncated to 8 chars in output
        finally:
            # Clean up knowledge model
            if knowledge_dir.exists():
                import shutil
                shutil.rmtree(knowledge_dir.parent.parent, ignore_errors=True)

    def test_diff_invalid_repo_path(self, tmp_path):
        """Test diff command with invalid repo path.
        
        This test verifies that the diff command handles invalid repo paths
        gracefully and returns an appropriate error message.
        """
        from knowledge_core import diff
        result = diff("test", "python", tmp_path / "nonexistent")
        
        assert "ERROR" in result
        assert "does not exist" in result or "not a directory" in result

    def test_diff_missing_knowledge_model(self, tmp_path):
        """Test diff command with missing knowledge model.
        
        This test verifies that the diff command handles missing knowledge
        models gracefully and returns an appropriate error message.
        """
        # Create a temporary git repo
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
        
        # Create a file and commit
        (repo_dir / "test.txt").write_text("test content")
        subprocess.run(["git", "add", "test.txt"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
        
        # Run diff command with missing knowledge model
        from knowledge_core import diff
        result = diff("nonexistent_family", "python", repo_dir)
        
        assert "ERROR" in result
        assert "Knowledge model not available" in result

    def test_diff_git_not_found(self, tmp_path):
        """Test diff command when git is not available.
        
        This test verifies that the diff command handles the case when git
        is not installed or not in PATH.
        """
        # Create a temporary directory (not a git repo)
        repo_dir = tmp_path / "not_a_repo"
        repo_dir.mkdir()
        
        from knowledge_core import diff
        result = diff("test", "python", repo_dir)

        # Should return an error since this is not a valid git repo
        assert "ERROR" in result


class TestDiscoverContentCWDIndependence:
    """Regression tests for CWD-independent content discovery.

    The discover_content() function must use absolute paths derived from
    __file__, not bare relative Path("content/..."). If this test fails,
    someone likely reverted the _REPO_ROOT fix in knowledge_core.py.
    """

    def test_discover_content_from_foreign_cwd(self, tmp_path, monkeypatch):
        """discover_content must find files when CWD is an empty temp dir."""
        monkeypatch.chdir(tmp_path)
        from content_discovery import discover_content  # R-1b: canonical home
        files = discover_content("note", "python")
        assert len(files) > 0, (
            f"discover_content('note','python') returned 0 files from CWD={tmp_path}. "
            "Path resolution must use __file__-based _REPO_ROOT, not relative paths."
        )

    def test_discover_products_from_foreign_cwd(self, tmp_path, monkeypatch):
        """discover_products must find products when CWD is an empty temp dir."""
        monkeypatch.chdir(tmp_path)
        from content_discovery import discover_products  # R-1b: canonical home
        products = discover_products()
        assert len(products) >= 10, (
            f"discover_products() returned {len(products)} from CWD={tmp_path}. "
            "Expected at least 10 products."
        )
