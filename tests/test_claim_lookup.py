"""Tests for scripts/claim_lookup.py"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

# Minimal PEF fixture for testing
FAKE_PEF = {
    "family": "email",
    "platform": "python",
    "claims": [
        {"claim_id": "CLM-email-9db99c", "text": 'MapiMessage.from_file(path, strict) -> "MapiMessage"'},
        {"claim_id": "CLM-email-c308b2", "text": 'MapiMessage.create(subject, body, unicode_strings) -> "MapiMessage"'},
        {"claim_id": "CLM-email-c8b202", "text": 'MapiMessage.save(path) -> None'},
        {"claim_id": "CLM-email-404eaa", "text": 'MapiMessage.to_email_message() -> EmailMessage'},
        {"claim_id": "CLM-email-c65341", "text": 'MapiAttachment.is_embedded_message() -> bool'},
        {"claim_id": "CLM-email-1fb91a", "text": 'CFBReader.from_file(path) -> "CFBReader"'},
    ],
    "api_surface": [],
}


@pytest.fixture
def fake_pef(tmp_path, monkeypatch):
    """Write fake PEF to tmp_path and monkeypatch Path so lookup finds it."""
    pef_dir = tmp_path / "evidence" / "email" / "python"
    pef_dir.mkdir(parents=True)
    (pef_dir / "pef.json").write_text(json.dumps(FAKE_PEF))
    # Monkeypatch working directory so relative path resolves
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _lookup(family, platform, api_ref, pef_dir):
    """Helper that imports lookup with correct cwd."""
    from scripts.claim_lookup import lookup
    return lookup(family, platform, api_ref)


class TestLookupHappyPath:
    def test_exact_class_method(self, fake_pef):
        from scripts.claim_lookup import lookup
        assert lookup("email", "python", "MapiMessage.from_file") == "CLM-email-9db99c"

    def test_exact_create(self, fake_pef):
        from scripts.claim_lookup import lookup
        assert lookup("email", "python", "MapiMessage.create") == "CLM-email-c308b2"

    def test_exact_save(self, fake_pef):
        from scripts.claim_lookup import lookup
        assert lookup("email", "python", "MapiMessage.save") == "CLM-email-c8b202"

    def test_to_email_message(self, fake_pef):
        from scripts.claim_lookup import lookup
        assert lookup("email", "python", "MapiMessage.to_email_message") == "CLM-email-404eaa"

    def test_attachment_method(self, fake_pef):
        from scripts.claim_lookup import lookup
        assert lookup("email", "python", "MapiAttachment.is_embedded_message") == "CLM-email-c65341"

    def test_cfbreader_from_file(self, fake_pef):
        from scripts.claim_lookup import lookup
        assert lookup("email", "python", "CFBReader.from_file") == "CLM-email-1fb91a"


class TestLookupNotFound:
    def test_nonexistent_method(self, fake_pef):
        from scripts.claim_lookup import lookup
        assert lookup("email", "python", "MapiMessage.nonexistent_method") is None

    def test_nonexistent_class(self, fake_pef):
        from scripts.claim_lookup import lookup
        assert lookup("email", "python", "FakeClass.method") is None


class TestLookupEdgeCases:
    def test_class_only_ref(self, fake_pef):
        from scripts.claim_lookup import lookup
        # Class-only ref: should match first claim containing "MapiMessage"
        result = lookup("email", "python", "MapiMessage")
        assert result is not None
        assert result.startswith("CLM-email-")

    def test_missing_pef_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from scripts.claim_lookup import lookup
        with pytest.raises(FileNotFoundError, match="PEF not found"):
            lookup("email", "python", "MapiMessage.from_file")
