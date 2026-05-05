"""
Tests for translation backends: LLMBackend, OllamaBackend, M2MBackend, BackendRouter.

Zero real network calls — all HTTP is mocked with unittest.mock.patch.

Run: python -m pytest scripts/translator/tests/test_backends.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

# Ensure scripts/ is on sys.path so 'translator' is importable
_SCRIPTS = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_SCRIPTS))

from translator import BackendUnavailableError, ConfigurationError
from translator.backends.base import BackendRouter
from translator.backends.llm import LLMBackend
from translator.backends.ollama import OllamaBackend
from translator.backends.m2m import M2MBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code: int, json_data=None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


def _llm_backend(**kwargs) -> LLMBackend:
    """Construct an LLMBackend with a dummy API key."""
    return LLMBackend(api_key="test-key-abc", **kwargs)


# ---------------------------------------------------------------------------
# LLMBackend
# ---------------------------------------------------------------------------

class TestLLMBackendIsAvailable:

    def test_available_on_200(self):
        backend = _llm_backend()
        with patch.object(backend._session, "get", return_value=_make_response(200)) as mock_get:
            assert backend.is_available() is True
            mock_get.assert_called_once()

    def test_available_on_401(self):
        """401 means endpoint reachable but bad key — still counts as available."""
        backend = _llm_backend()
        with patch.object(backend._session, "get", return_value=_make_response(401)):
            assert backend.is_available() is True

    def test_unavailable_on_connection_error(self):
        backend = _llm_backend()
        with patch.object(backend._session, "get", side_effect=Exception("no route to host")):
            assert backend.is_available() is False

    def test_unavailable_on_500(self):
        backend = _llm_backend()
        with patch.object(backend._session, "get", return_value=_make_response(500)):
            assert backend.is_available() is False


class TestLLMBackendTranslate:

    def _success_response(self, translated: str) -> MagicMock:
        data = {"choices": [{"message": {"content": translated}}]}
        return _make_response(200, data)

    def test_translate_success(self):
        backend = _llm_backend(max_retries=1)
        with patch.object(backend._session, "post", return_value=self._success_response("Bonjour")):
            result = backend.translate("Hello", "en", "fr")
        assert result == "Bonjour"

    def test_translate_strips_whitespace(self):
        backend = _llm_backend(max_retries=1)
        with patch.object(backend._session, "post", return_value=self._success_response("  Hola  \n")):
            result = backend.translate("Hello", "en", "es")
        assert result == "Hola"

    def test_translate_http_500_retries_and_raises(self):
        """HTTP 500 should cause retries equal to max_retries, then raise."""
        max_retries = 3
        backend = _llm_backend(max_retries=max_retries)
        error_resp = _make_response(500, text="Internal Server Error")
        with patch.object(backend._session, "post", return_value=error_resp) as mock_post:
            with patch("translator.backends.base.time.sleep"):  # suppress delays
                with pytest.raises(BackendUnavailableError):
                    backend.translate("Hello", "en", "de")
        assert mock_post.call_count == max_retries

    def test_translate_connection_error_retries(self):
        """ConnectionError should be wrapped and retried."""
        import requests
        max_retries = 2
        backend = _llm_backend(max_retries=max_retries)
        with patch.object(
            backend._session, "post",
            side_effect=requests.exceptions.ConnectionError("refused")
        ) as mock_post:
            with patch("translator.backends.base.time.sleep"):
                with pytest.raises(BackendUnavailableError):
                    backend.translate("Hello", "en", "ja")
        assert mock_post.call_count == max_retries

    def test_missing_api_key_raises_configuration_error(self):
        with patch.dict("os.environ", {}, clear=False):
            # Ensure LLM_API_KEY is not set in the environment
            import os
            os.environ.pop("LLM_API_KEY", None)
            with pytest.raises(ConfigurationError):
                LLMBackend(api_key="")

    def test_get_model_info(self):
        backend = _llm_backend(model="test-model")
        info = backend.get_model_info()
        assert info["backend"] == "llm.professionalize.com"
        assert info["model"] == "test-model"


# ---------------------------------------------------------------------------
# OllamaBackend
# ---------------------------------------------------------------------------

class TestOllamaBackendIsAvailable:

    def test_available_when_tags_returns_200(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        tags_data = {"models": [{"name": "llama3.2:latest"}]}
        # T3-MOCK: target=requests.get reason="HTTP boundary call to Ollama API" removal=PERMANENT
        with patch("requests.get", return_value=_make_response(200, tags_data)):
            assert backend.is_available() is True

    def test_unavailable_when_tags_returns_non_200(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        # T3-MOCK: target=requests.get reason="HTTP boundary call to Ollama API" removal=PERMANENT
        with patch("requests.get", return_value=_make_response(404)):
            assert backend.is_available() is False

    def test_unavailable_on_connection_error(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        # T3-MOCK: target=requests.get reason="HTTP boundary call to Ollama API" removal=PERMANENT
        with patch("requests.get", side_effect=Exception("connection refused")):
            assert backend.is_available() is False

    def test_is_available_cached(self):
        """Second call should not re-fetch tags."""
        backend = OllamaBackend(base_url="http://localhost:11434")
        tags_data = {"models": []}
        # T3-MOCK: target=requests.get reason="HTTP boundary call to Ollama API" removal=PERMANENT
        with patch("requests.get", return_value=_make_response(200, tags_data)) as mock_get:
            backend.is_available()
            backend.is_available()
        assert mock_get.call_count == 1


class TestOllamaBackendTranslate:

    def _make_available_backend(self) -> OllamaBackend:
        backend = OllamaBackend(base_url="http://localhost:11434", max_retries=1)
        # Pre-set availability so translate() doesn't try to re-fetch
        backend._available = True
        backend._tags_cache = {}
        return backend

    def _chat_response(self, content: str) -> MagicMock:
        data = {"message": {"content": content}}
        return _make_response(200, data)

    def test_translate_success(self):
        backend = self._make_available_backend()
        with patch.object(backend._session, "post", return_value=self._chat_response("Bonjour le monde")):
            result = backend.translate("Hello world", "en", "fr")
        assert result == "Bonjour le monde"

    def test_translate_raises_when_unavailable(self):
        backend = OllamaBackend(base_url="http://localhost:11434")
        backend._available = False
        backend._tags_cache = {}
        with pytest.raises(BackendUnavailableError):
            backend.translate("Hello", "en", "fr")

    def test_get_model_info(self):
        backend = OllamaBackend(base_url="http://myhost:11434", model="mistral")
        info = backend.get_model_info()
        assert info["backend"] == "ollama"
        assert info["model"] == "mistral"
        assert "myhost" in info["url"]


# ---------------------------------------------------------------------------
# M2MBackend
# ---------------------------------------------------------------------------

class TestM2MBackendIsAvailable:

    def test_available_when_transformers_present(self):
        backend = M2MBackend()
        # Patch builtins.__import__ via sys.modules trick
        fake_transformers = MagicMock()
        fake_torch = MagicMock()
        with patch.dict("sys.modules", {"transformers": fake_transformers, "torch": fake_torch}):
            assert backend.is_available() is True

    def test_unavailable_when_transformers_missing(self):
        backend = M2MBackend()
        with patch.dict("sys.modules", {"transformers": None, "torch": None}):
            # is_available does 'import transformers' which will raise ImportError for None
            result = backend.is_available()
        assert result is False

    def test_get_model_info(self):
        backend = M2MBackend()
        info = backend.get_model_info()
        assert info["backend"] == "m2m100"
        assert "m2m100" in info["model"]

    def test_list_models_returns_model_name(self):
        backend = M2MBackend(model_name="facebook/m2m100_418m")
        models = backend.list_models()
        assert len(models) == 1
        assert models[0]["id"] == "facebook/m2m100_418m"


# ---------------------------------------------------------------------------
# BackendRouter
# ---------------------------------------------------------------------------

class TestBackendRouter:

    def _make_backend(self, name: str, translate_result=None, raises=None) -> MagicMock:
        b = MagicMock()
        b.get_model_info.return_value = {"backend": name, "model": name}
        if raises:
            b.translate.side_effect = raises
            b.translate_batch.side_effect = raises
        else:
            b.translate.return_value = translate_result
            b.translate_batch.return_value = [translate_result]
        return b

    def test_uses_primary_when_available(self):
        primary = self._make_backend("primary", translate_result="translated")
        secondary = self._make_backend("secondary", translate_result="fallback")
        router = BackendRouter([primary, secondary])
        result = router.translate("Hello", "en", "fr")
        assert result == "translated"
        primary.translate.assert_called_once()
        secondary.translate.assert_not_called()

    def test_falls_back_to_secondary_when_primary_fails(self):
        primary = self._make_backend("primary", raises=BackendUnavailableError("down"))
        secondary = self._make_backend("secondary", translate_result="fallback-result")
        router = BackendRouter([primary, secondary])
        result = router.translate("Hello", "en", "fr")
        assert result == "fallback-result"
        primary.translate.assert_called_once()
        secondary.translate.assert_called_once()

    def test_raises_when_all_backends_fail(self):
        primary = self._make_backend("primary", raises=BackendUnavailableError("down"))
        secondary = self._make_backend("secondary", raises=BackendUnavailableError("also down"))
        router = BackendRouter([primary, secondary])
        with pytest.raises(BackendUnavailableError):
            router.translate("Hello", "en", "fr")

    def test_empty_backend_list_raises_configuration_error(self):
        with pytest.raises(ConfigurationError):
            BackendRouter([])

    def test_active_backend_info_updated_after_success(self):
        backend = self._make_backend("primary", translate_result="ok")
        router = BackendRouter([backend])
        router.translate("Hello", "en", "fr")
        info = router.active_backend_info()
        assert info is not None
        assert info["backend"] == "primary"

    def test_active_backend_info_none_before_any_translation(self):
        backend = self._make_backend("primary", translate_result="ok")
        router = BackendRouter([backend])
        assert router.active_backend_info() is None

    def test_translate_batch_falls_back(self):
        primary = self._make_backend("primary", raises=BackendUnavailableError("down"))
        secondary = self._make_backend("secondary", translate_result="batch-result")
        router = BackendRouter([primary, secondary])
        result = router.translate_batch(["Hello"], "en", "fr")
        assert result == ["batch-result"]
        secondary.translate_batch.assert_called_once()
