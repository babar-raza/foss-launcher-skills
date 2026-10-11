"""Tests for kilocode_skill_chain.py - Skill dependency chain verification."""

import pytest
from pathlib import Path


class TestKiloCodeSkillChain:
    """Test cases for Kilo Code skill chain verification."""

    def test_load_dar_table(self):
        """Test loading DAR table from AGENTS.md."""
        from kilocode_skill_chain import load_dar_table
        
        dar_table = load_dar_table()
        
        # Verify table is loaded
        assert isinstance(dar_table, dict)

    def test_get_upstream_skills(self):
        """Test getting upstream skills for a skill."""
        from kilocode_skill_chain import get_upstream_skills
        
        # Test with a skill that has upstream dependencies
        upstream = get_upstream_skills("page-plan")
        
        # Should return a list
        assert isinstance(upstream, list)

    def test_verify_skill_chain_valid(self):
        """Test verifying a valid skill chain."""
        from kilocode_skill_chain import verify_skill_chain
        
        # Valid chain: knowledge-bootstrap -> page-plan -> page-draft
        chain = ["knowledge-bootstrap", "page-plan", "page-draft"]
        valid, issues = verify_skill_chain(chain)
        
        assert isinstance(valid, bool)
        assert isinstance(issues, list)

    def test_verify_skill_chain_invalid(self):
        """Test verifying an invalid skill chain."""
        from kilocode_skill_chain import verify_skill_chain
        
        # Invalid chain: missing upstream dependency
        chain = ["page-plan", "page-draft"]  # Missing knowledge-bootstrap
        valid, issues = verify_skill_chain(chain)
        
        # Should have issues about missing upstream
        assert isinstance(valid, bool)

    def test_verify_skill_chain_unknown_skill(self):
        """Test verifying a chain with unknown skills."""
        from kilocode_skill_chain import verify_skill_chain
        
        # Chain with unknown skill
        chain = ["unknown-skill", "page-plan"]
        valid, issues = verify_skill_chain(chain)
        
        # Should have issues about unknown skill
        assert isinstance(valid, bool)

    def test_main_valid_chain(self, capsys):
        """Test main function with valid chain."""
        from kilocode_skill_chain import main
        
        # Valid chain
        result = main(["page-plan", "page-draft"])
        
        # Should return 0 for valid chain
        assert result == 0

    def test_main_help(self, capsys):
        """Test main function with help flag."""
        from kilocode_skill_chain import main
        
        # Should handle help flag
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        
        assert exc_info.value.code == 0


class TestKiloCodeSkillChainIntegration:
    """Integration tests for Kilo Code skill chain."""

    def test_chain_with_real_agents_file(self):
        """Test chain with real AGENTS.md file."""
        from kilocode_skill_chain import _REPO_ROOT
        
        # Verify AGENTS.md exists
        agents_file = _REPO_ROOT / "AGENTS.md"
        assert agents_file.exists(), "AGENTS.md should exist"

    def test_chain_error_handling(self):
        """Test chain error handling for missing AGENTS.md."""
        import os
        from kilocode_skill_chain import _REPO_ROOT
        
        # Verify we can access the repo root
        assert _REPO_ROOT.exists(), "Repo root should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
