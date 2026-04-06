"""Tests for kilocode_learning.py - Violation-driven learning examples."""

import pytest
import json
from pathlib import Path


class TestKiloCodeLearning:
    """Test cases for Kilo Code learning examples."""

    def test_generate_learning_examples(self):
        """Test generating learning examples from violations."""
        from kilocode_learning import generate_learning_examples
        
        # Test violations
        violations = [
            {
                "type": "skill_bypass",
                "violation": "Agent bypassed skill-first mandate",
                "request": "Create a page",
                "action": "Inline reasoning",
                "correct_action": "Invoke page-plan skill"
            }
        ]
        
        examples = generate_learning_examples(violations)
        
        assert isinstance(examples, list)
        assert len(examples) > 0
        assert "instruction" in examples[0]
        assert "context" in examples[0]
        assert "response" in examples[0]

    def test_load_violations(self):
        """Test loading violations from file."""
        from kilocode_learning import load_violations
        
        # Test with non-existent file
        violations = load_violations()
        assert isinstance(violations, list)

    def test_generate_examples_from_file(self):
        """Test generating examples from violations file."""
        from kilocode_learning import generate_examples_from_file
        
        # Test with non-existent file
        examples = generate_examples_from_file()
        assert isinstance(examples, list)

    def test_save_examples(self):
        """Test saving learning examples to file."""
        from kilocode_learning import save_examples
        
        # Create temp file for testing
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            # Save examples
            examples = [
                {
                    "instruction": "Test instruction",
                    "context": {"test": "context"},
                    "response": {"reasoning": "Test reasoning"}
                }
            ]
            save_examples(examples, Path(temp_file))
            
            # Verify file was created
            assert Path(temp_file).exists()
            
            # Verify content
            with open(temp_file, encoding="utf-8") as f:
                loaded = json.load(f)
            
            assert len(loaded) == 1
            assert loaded[0]["instruction"] == "Test instruction"
        finally:
            import os
            os.unlink(temp_file)

    def test_main_help(self, capsys):
        """Test main function with help flag."""
        from kilocode_learning import main
        
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        
        assert exc_info.value.code == 0


class TestKiloCodeLearningIntegration:
    """Integration tests for Kilo Code learning examples."""

    def test_learning_with_real_violations(self):
        """Test learning with real violations data."""
        from kilocode_learning import load_violations
        
        # Load violations
        violations = load_violations()
        
        # Should return a list
        assert isinstance(violations, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
