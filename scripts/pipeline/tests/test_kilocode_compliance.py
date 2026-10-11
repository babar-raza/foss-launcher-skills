"""Tests for kilocode_compliance.py - Compliance tracking framework."""

import pytest
import json
from pathlib import Path

# Import ComplianceTracker for global tracker tests
from kilocode_compliance import ComplianceTracker


class TestKiloCodeCompliance:
    """Test cases for Kilo Code compliance tracking."""

    def test_compliance_tracker_init(self):
        """Test initializing compliance tracker."""
        from kilocode_compliance import ComplianceTracker
        
        tracker = ComplianceTracker()
        
        assert isinstance(tracker.violations, list)
        assert isinstance(tracker.score_history, list)

    def test_record_violation(self):
        """Test recording a violation."""
        from kilocode_compliance import ComplianceTracker
        
        # Create temp file for testing
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([], f)
            temp_file = f.name
        
        try:
            tracker = ComplianceTracker(Path(temp_file))
            tracker.record_violation("page-plan", "Skill bypass detected", "HIGH")
            
            # Verify violation was recorded
            assert len(tracker.violations) > 0
        finally:
            import os
            os.unlink(temp_file)

    def test_calculate_compliance_score(self):
        """Test calculating compliance score."""
        from kilocode_compliance import ComplianceTracker
        
        tracker = ComplianceTracker()
        
        # Should have 100 score with no violations
        score = tracker.calculate_compliance_score()
        assert score == 100.0

    def test_get_violation_summary(self):
        """Test getting violation summary."""
        from kilocode_compliance import ComplianceTracker
        
        tracker = ComplianceTracker()
        
        summary = tracker.get_violation_summary()
        assert isinstance(summary, dict)

    def test_generate_feedback(self):
        """Test generating feedback."""
        from kilocode_compliance import ComplianceTracker
        
        tracker = ComplianceTracker()
        
        feedback = tracker.generate_feedback()
        assert isinstance(feedback, str)

    def test_clear_violations(self):
        """Test clearing violations."""
        from kilocode_compliance import ComplianceTracker
        
        # Create temp file for testing
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([], f)
            temp_file = f.name
        
        try:
            tracker = ComplianceTracker(Path(temp_file))
            tracker.record_violation("page-plan", "Skill bypass detected", "HIGH")
            tracker.clear_violations()
            
            # Verify violations were cleared
            assert len(tracker.violations) == 0
        finally:
            import os
            os.unlink(temp_file)

    def test_get_compliance_tracker(self):
        """Test getting global compliance tracker."""
        from kilocode_compliance import get_compliance_tracker
        
        tracker = get_compliance_tracker()
        
        assert isinstance(tracker, ComplianceTracker)

    def test_tracker_function(self):
        """Test tracker function."""
        from kilocode_compliance import tracker
        
        tracker_instance = tracker()
        
        assert isinstance(tracker_instance, ComplianceTracker)


class TestKiloCodeComplianceIntegration:
    """Integration tests for Kilo Code compliance tracking."""

    def test_compliance_with_real_data(self):
        """Test compliance tracking with real data."""
        from kilocode_compliance import ComplianceTracker
        
        # Create tracker with default file
        tracker = ComplianceTracker()
        
        # Verify structure
        assert isinstance(tracker.violations, list)
        assert isinstance(tracker.score_history, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
