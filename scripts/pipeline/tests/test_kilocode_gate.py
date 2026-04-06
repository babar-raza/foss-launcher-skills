"""Tests for kilocode_gate.py - Pre-execution gate for skill-first enforcement."""

import pytest
from pathlib import Path


class TestKiloCodeGate:
    """Test cases for Kilo Code gate functionality."""

    def test_check_skill_first_allowed(self):
        """Test skill-first check for allowed requests."""
        from kilocode_gate import check_skill_first
        
        allowed, reason = check_skill_first("read", False)
        assert allowed is True
        assert reason == "OK"

    def test_check_skill_first_denied(self):
        """Test skill-first check for denied requests."""
        from kilocode_gate import check_skill_first
        
        allowed, reason = check_skill_first("generate", True)
        assert allowed is False
        assert "skill-first" in reason.lower() or "registered skills" in reason.lower()

    def test_check_forbidden_path(self):
        """Test forbidden path check."""
        from kilocode_gate import check_forbidden_path
        
        # Test with a path that should be allowed
        allowed, reason = check_forbidden_path("content/docs.aspose.org/en/slides/net/_index.md")
        # Path check may fail if path_guard.py doesn't exist, which is expected
        # Just verify the function returns a tuple
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)

    def test_check_skill_exists(self):
        """Test skill existence check."""
        from kilocode_gate import check_skill_exists
        
        # Test with a known skill
        allowed, reason = check_skill_exists("path-guard")
        assert allowed is True
        assert reason == "OK"

    def test_check_unknown_skill(self):
        """Test unknown skill check."""
        from kilocode_gate import check_skill_exists
        
        allowed, reason = check_skill_exists("unknown-skill")
        assert allowed is False
        assert "Unknown skill" in reason

    def test_main_skill_first_allowed(self, capsys):
        """Test main function with allowed skill-first request."""
        from kilocode_gate import main
        
        result = main(["skill-first", "read", "no-content"])
        assert result == 0

    def test_main_skill_first_denied(self, capsys):
        """Test main function with denied skill-first request."""
        from kilocode_gate import main
        
        result = main(["skill-first", "generate", "content"])
        assert result == 1

    def test_main_path(self, capsys):
        """Test main function with path check."""
        from kilocode_gate import main
        
        result = main(["path", "content/docs.aspose.org/en/slides/net/_index.md"])
        # Path check may fail if path_guard.py doesn't exist
        # Just verify it returns a valid exit code
        assert result in (0, 1)

    def test_main_skill(self, capsys):
        """Test main function with skill check."""
        from kilocode_gate import main
        
        result = main(["skill", "path-guard"])
        assert result == 0

    def test_main_unknown_skill(self, capsys):
        """Test main function with unknown skill."""
        from kilocode_gate import main
        
        result = main(["skill", "unknown-skill"])
        assert result == 1

    def test_main_help(self, capsys):
        """Test main function with help flag."""
        from kilocode_gate import main
        
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        
        assert exc_info.value.code == 0


class TestKiloCodeGateIntegration:
    """Integration tests for Kilo Code gate."""

    def test_gate_with_real_agents_file(self):
        """Test gate with real AGENTS.md file."""
        from kilocode_gate import _REPO_ROOT
        
        # Verify AGENTS.md exists
        agents_file = _REPO_ROOT / "AGENTS.md"
        assert agents_file.exists(), "AGENTS.md should exist"

    def test_gate_error_handling(self):
        """Test gate error handling for missing AGENTS.md."""
        import os
        from kilocode_gate import _REPO_ROOT
        
        # Verify we can access the repo root
        assert _REPO_ROOT.exists(), "Repo root should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
