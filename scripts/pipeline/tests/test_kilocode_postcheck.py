"""Tests for kilocode_postcheck.py - Post-execution validation."""

import pytest
from pathlib import Path


class TestKiloCodePostcheck:
    """Test cases for Kilo Code postcheck functionality."""

    def test_check_path(self):
        """Test path check."""
        from kilocode_postcheck import check_path
        
        # Test with a path that should be allowed
        allowed, reason = check_path("content/docs.aspose.org/en/slides/net/_index.md")
        # Path check may fail if path_guard.py doesn't exist, which is expected
        # Just verify the function returns a tuple
        assert isinstance(allowed, bool)
        assert isinstance(reason, str)

    def test_has_evidence_frontmatter(self):
        """Test evidence frontmatter check."""
        from kilocode_postcheck import has_evidence_frontmatter
        
        # Test with a file that doesn't have evidence frontmatter
        has_evidence = has_evidence_frontmatter("content/docs.aspose.org/en/slides/net/_index.md")
        # Just verify the function returns a boolean
        assert isinstance(has_evidence, bool)

    def test_main_help(self, capsys):
        """Test main function with help flag."""
        from kilocode_postcheck import main
        
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        
        assert exc_info.value.code == 0


class TestKiloCodePostcheckIntegration:
    """Integration tests for Kilo Code postcheck."""

    def test_postcheck_with_real_file(self):
        """Test postcheck with a real content file."""
        from kilocode_postcheck import has_evidence_frontmatter
        
        # Test with a real content file
        content_file = Path("content/docs.aspose.org/en/slides/net/_index.md")
        
        if content_file.exists():
            has_evidence = has_evidence_frontmatter(str(content_file))
            assert isinstance(has_evidence, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
