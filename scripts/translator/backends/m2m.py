"""
M2MBackend: optional offline translation using facebook/m2m100_418m.

This backend requires transformers and torch, which are NOT in the base
requirements.txt. They must be installed separately:
  pip install transformers torch

Activated via:
  - --offline flag in CLI
  - TRANSLATE_OFFLINE=1 environment variable

Suitable for: large-batch initial translation of new locale directories
where quality can be slightly lower than LLM translation.
"""
from __future__ import annotations
import logging
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator import BackendUnavailableError, ConfigurationError
from translator.backends.base import TranslationBackend

logger = logging.getLogger(__name__)

_DEFAULT_M2M_MODEL = "facebook/m2m100_418m"

# M2M100 language code mapping (subset — full list has 100 languages)
# Maps ISO 639-1 to M2M100 language code
M2M_LANG_MAP = {
    "ar": "ar",
    "bg": "bg",
    "ca": "ca",
    "cs": "cs",
    "da": "da",
    "de": "de",
    "el": "el",
    "es": "es",
    "fa": "fa",
    "fi": "fi",
    "fr": "fr",
    "he": "he",
    "hi": "hi",
    "hr": "hr",
    "hu": "hu",
    "id": "id",
    "it": "it",
    "ja": "ja",
    "ko": "ko",
    "lt": "lt",
    "lv": "lv",
    "ms": "ms",
    "nl": "nl",
    "no": "no",
    "pl": "pl",
    "pt": "pt",
    "ro": "ro",
    "ru": "ru",
    "sk": "sk",
    "sr": "sr",
    "sv": "sv",
    "th": "th",
    "tr": "tr",
    "uk": "uk",
    "vi": "vi",
    "zh": "zh",
    "en": "en",
}


class M2MBackend(TranslationBackend):
    """
    Offline translation backend using M2M100.
    Requires: pip install transformers torch

    Model and tokenizer are loaded lazily on first use to avoid startup cost
    and to allow the class to be imported even when transformers is not installed.
    """

    def __init__(self, model_name: str = _DEFAULT_M2M_MODEL):
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
        self._loaded = False

    def _load(self) -> None:
        """
        Lazy-load the M2M100 model. Raises ImportError with a helpful message
        if transformers/torch are not installed.
        """
        if self._loaded:
            return
        try:
            from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
        except ImportError:
            raise ImportError(
                "M2M100 backend requires 'transformers' and 'torch'. "
                "Install with: pip install transformers torch\n"
                "Or remove --offline flag to use the LLM backend."
            )
        logger.info(f"Loading M2M100 model {self.model_name}...")
        self._tokenizer = M2M100Tokenizer.from_pretrained(self.model_name)  # nosec B615 - loading HuggingFace model is expected behavior
        self._model = M2M100ForConditionalGeneration.from_pretrained(self.model_name)  # nosec B615 - loading HuggingFace model is expected behavior
        self._loaded = True
        logger.info("M2M100 model loaded.")

    def is_available(self) -> bool:
        """
        Return True if transformers and torch are installed.
        NOTE: does NOT check whether the model weights are downloaded.
        Call check_download_state() for that.
        """
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
            return True
        except ImportError:
            return False

    def check_download_state(self) -> dict:
        """
        Inspect the Hugging Face cache to determine if model weights are present.

        Returns a dict with:
          downloaded  (bool)  — True if model directory with snapshots exists
          cache_dir   (str)   — Path checked
          size_bytes  (int)   — Approximate total size of cached files (0 if not downloaded)
          reason      (str)   — Human-readable status message

        Respects HF_HOME / HUGGINGFACE_HUB_CACHE environment overrides.
        """
        # Determine HF cache root (same resolution order as huggingface_hub)
        hf_home = os.environ.get("HF_HOME") or os.environ.get("HUGGINGFACE_HUB_CACHE")
        if hf_home:
            cache_root = Path(hf_home)
        else:
            cache_root = Path.home() / ".cache" / "huggingface" / "hub"

        # Convert model name to HF cache directory format
        # "facebook/m2m100_418m" → "models--facebook--m2m100_418m"
        model_dir_name = "models--" + self.model_name.replace("/", "--")
        model_cache_dir = cache_root / model_dir_name
        snapshots_dir = model_cache_dir / "snapshots"

        if not model_cache_dir.exists():
            return {
                "downloaded": False,
                "cache_dir": str(model_cache_dir),
                "size_bytes": 0,
                "reason": (
                    f"Model directory not found: {model_cache_dir}. "
                    f"Run with --offline once to trigger download (~2 GB), "
                    f"or set HF_HOME to a directory with a pre-downloaded copy."
                ),
            }

        if not snapshots_dir.exists() or not any(snapshots_dir.iterdir()):
            return {
                "downloaded": False,
                "cache_dir": str(model_cache_dir),
                "size_bytes": 0,
                "reason": (
                    f"Model directory exists but snapshots/ is empty: {model_cache_dir}. "
                    "Download may have been interrupted."
                ),
            }

        # Estimate total size
        try:
            size_bytes = sum(
                f.stat().st_size for f in model_cache_dir.rglob("*") if f.is_file()
            )
        except OSError:
            size_bytes = 0

        return {
            "downloaded": True,
            "cache_dir": str(model_cache_dir),
            "size_bytes": size_bytes,
            "reason": f"Model cached at {model_cache_dir} ({size_bytes // (1024 * 1024)} MB)",
        }

    def list_models(self) -> list[dict]:
        """Return the single M2M100 model as a list for consistent interface."""
        return [{"id": self.model_name}]

    def translate(self, text: str, src_lang: str, tgt_lang: str) -> str:
        """Translate a single text segment using M2M100."""
        self._load()
        src_m2m = M2M_LANG_MAP.get(src_lang, src_lang)
        tgt_m2m = M2M_LANG_MAP.get(tgt_lang, tgt_lang)

        self._tokenizer.src_lang = src_m2m
        encoded = self._tokenizer(
            text, return_tensors="pt", truncation=True, max_length=512
        )
        tgt_lang_id = self._tokenizer.get_lang_id(tgt_m2m)
        generated = self._model.generate(
            **encoded,
            forced_bos_token_id=tgt_lang_id,
            max_new_tokens=512,
        )
        return self._tokenizer.batch_decode(generated, skip_special_tokens=True)[0]

    def translate_batch(
        self, texts: list[str], src_lang: str, tgt_lang: str
    ) -> list[str]:
        """
        Batch translation using M2M100.
        More efficient than sequential calls because the model generates
        all sequences in parallel on GPU/CPU.
        """
        self._load()
        src_m2m = M2M_LANG_MAP.get(src_lang, src_lang)
        tgt_m2m = M2M_LANG_MAP.get(tgt_lang, tgt_lang)

        self._tokenizer.src_lang = src_m2m
        encoded = self._tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        tgt_lang_id = self._tokenizer.get_lang_id(tgt_m2m)
        generated = self._model.generate(
            **encoded,
            forced_bos_token_id=tgt_lang_id,
            max_new_tokens=512,
        )
        return self._tokenizer.batch_decode(generated, skip_special_tokens=True)

    def get_model_info(self) -> dict:
        return {"backend": "m2m100", "model": self.model_name}
