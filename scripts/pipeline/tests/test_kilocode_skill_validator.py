"""Tests for kilocode_skill_validator.py - Skill contract validation."""

import pytest
from pathlib import Path


class TestKiloCodeSkillValidator:
    """Test cases for Kilo Code skill validator functionality."""

    def test_load_registered_skills(self):
        """Test loading registered skills."""
        from kilocode_skill_validator import load_registered_skills
        
        skills = load_registered_skills()
        
        # Verify skills is a dict
        assert isinstance(skills, dict)

    def test_validate_skill_invocation(self):
        """Test validating skill invocation."""
        from kilocode_skill_validator import validate_skill_invocation
        
        # Test with a known skill - path-guard expects 1 argument
        valid, reason = validate_skill_invocation("path-guard", ["content/test.md"])
        
        # Should be valid (path-guard exists and has correct args)
        assert valid is True
        assert reason == "OK"

    def test_validate_unknown_skill(self):
        """Test validating unknown skill."""
        from kilocode_skill_validator import validate_skill_invocation
        
        # Test with unknown skill
        valid, reason = validate_skill_invocation("unknown-skill", [])
        
        # Should be invalid
        assert valid is False
        assert "Unknown skill" in reason

    def test_main_help(self, capsys):
        """Test main function with help flag."""
        from kilocode_skill_validator import main
        
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        
        assert exc_info.value.code == 0


class TestKiloCodeSkillValidatorIntegration:
    """Integration tests for Kilo Code skill validator."""

    def test_validator_with_real_skills(self):
        """Test validator with real skill files."""
        from kilocode_skill_validator import load_registered_skills, _REPO_ROOT
        
        # Load skills
        skills = load_registered_skills()
        
        # Verify at least some skills exist
        assert len(skills) > 0, "Should have at least some registered skills"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
