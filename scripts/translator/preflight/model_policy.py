"""
Model classification policy for translation backend selection.

Determines whether a model is:
  - a thinking/reasoning model (expensive, slow, not suitable by default)
  - suitable for routine translation

Classification uses naming-pattern heuristics. This is intentionally
permissive: unknown models are assumed suitable unless they match a
thinking pattern, and produce a warning rather than an error.

Environment variables:
  TRANSLATE_ALLOW_THINKING_MODELS=1   Allow thinking models as a last resort.
                                      Default: 0 (block thinking models).
  TRANSLATE_MODEL_BLOCKLIST           Comma-separated additional blocklist patterns.
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Thinking-model patterns (case-insensitive)
# Models matching any of these are treated as reasoning/thinking models.
# ---------------------------------------------------------------------------
_THINKING_PATTERNS: list[str] = [
    r"o1[-/:]",              # OpenAI o1 family (o1-mini, o1-preview, o1:latest)
    r"\bo1\b",               # bare "o1"
    r"o3[-/:]",              # OpenAI o3 family
    r"\bo3\b",               # bare "o3"
    r"deepseek-r\d",         # DeepSeek R1, R2, ...
    r"\bthinking\b",         # any model with "thinking" in the name
    r"with[-_]thinking",     # explicit thinking variant
    r"extended[-_]thinking",
    r"\bqwq\b",              # QwQ reasoning model
    r"qvq",                  # QVQ (vision reasoning)
    r"r1[-_/]",              # generic R1 prefix
    r"[-/]r1\b",             # generic R1 suffix
]

# Compile once at module load
_THINKING_RE = re.compile(
    "|".join(_THINKING_PATTERNS),
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Known-good translation model patterns (case-insensitive)
# Models matching these are explicitly flagged as translation-suitable.
# Models that don't match either list are treated as "unknown" — still
# allowed, but with a warning.
# ---------------------------------------------------------------------------
_SUITABLE_PATTERNS: list[str] = [
    r"gpt-oss",
    r"gpt-4",
    r"gpt-3\.5",
    r"llama[23]",
    r"llama-[23]",
    r"mistral",
    r"mixtral",
    r"qwen[12]",              # Qwen 1.x / 2.x (non-thinking)
    r"qwen-[12]",
    r"m2m100",                # M2M100 offline model (always suitable)
    r"gemma",
    r"phi[-_]\d",
    r"nemo",
    r"command[-_]r",
    r"orca",
    r"vicuna",
    r"solar",
    r"openchat",
    r"hermes",
    r"nous[-_]",
    r"zephyr",
    r"falcon",
    r"yi[-_]\d",              # Yi 1.5, Yi-34B, etc.
    r"internlm",
    r"deepseek[-_]v",         # DeepSeek-V series (non-thinking)
    r"deepseek[-_]coder",
]

_SUITABLE_RE = re.compile(
    "|".join(_SUITABLE_PATTERNS),
    re.IGNORECASE,
)


@dataclass
class ModelInfo:
    """Classification result for a single model."""
    model_id: str
    is_thinking: bool
    is_translation_suitable: bool
    reason: str


def classify_model(model_id: str) -> ModelInfo:
    """
    Classify a model by ID into thinking/non-thinking and suitability categories.

    Returns ModelInfo with:
      is_thinking              — True if the model appears to be a reasoning model
      is_translation_suitable  — True if the model is appropriate for routine translation
      reason                   — Human-readable explanation
    """
    name = model_id.strip().lower()

    # Check additional user-supplied blocklist patterns
    extra_blocklist = os.environ.get("TRANSLATE_MODEL_BLOCKLIST", "")
    if extra_blocklist:
        for pattern in extra_blocklist.split(","):
            pattern = pattern.strip()
            if pattern and re.search(pattern, name, re.IGNORECASE):
                return ModelInfo(
                    model_id=model_id,
                    is_thinking=True,
                    is_translation_suitable=False,
                    reason=f"Blocked by TRANSLATE_MODEL_BLOCKLIST pattern: {pattern!r}",
                )

    is_thinking = bool(_THINKING_RE.search(name))
    if is_thinking:
        allow_thinking = os.environ.get("TRANSLATE_ALLOW_THINKING_MODELS", "0").strip() == "1"
        return ModelInfo(
            model_id=model_id,
            is_thinking=True,
            is_translation_suitable=allow_thinking,
            reason=(
                "Thinking/reasoning model — suitable only when TRANSLATE_ALLOW_THINKING_MODELS=1"
                if not allow_thinking
                else "Thinking/reasoning model — allowed via TRANSLATE_ALLOW_THINKING_MODELS=1"
            ),
        )

    is_known_suitable = bool(_SUITABLE_RE.search(name))
    if is_known_suitable:
        return ModelInfo(
            model_id=model_id,
            is_thinking=False,
            is_translation_suitable=True,
            reason="Known translation-suitable model",
        )

    # Unknown model: treat as suitable but warn
    return ModelInfo(
        model_id=model_id,
        is_thinking=False,
        is_translation_suitable=True,
        reason="Unknown model — assumed suitable for translation (unrecognised name pattern)",
    )


def select_best_model(models: list[dict], preferred_id: str | None = None) -> ModelInfo | None:
    """
    From a list of raw model dicts (each with {"id": str}), return the best
    ModelInfo for translation.

    Selection priority:
      1. preferred_id if specified and translation-suitable
      2. first non-thinking, known-suitable model
      3. first non-thinking unknown model (with warning)
      4. None if no suitable model found

    If TRANSLATE_ALLOW_THINKING_MODELS=1, thinking models are also considered
    as a last resort.
    """
    if not models:
        return None

    classified = [classify_model(m["id"]) for m in models]

    # Priority 1: explicit preferred model
    if preferred_id:
        for m in classified:
            if m.model_id == preferred_id or m.model_id.split(":")[0] == preferred_id.split(":")[0]:
                if m.is_translation_suitable:
                    return m
                # Preferred model exists but is not suitable — still return it with a note
                # (caller decides whether to accept)
                return m

    # Priority 2: non-thinking, known-suitable
    for m in classified:
        if not m.is_thinking and m.is_translation_suitable and "Unknown" not in m.reason:
            return m

    # Priority 3: non-thinking unknown
    for m in classified:
        if not m.is_thinking and m.is_translation_suitable:
            return m

    # Priority 4: thinking model if explicitly allowed
    allow_thinking = os.environ.get("TRANSLATE_ALLOW_THINKING_MODELS", "0").strip() == "1"
    if allow_thinking:
        for m in classified:
            if m.is_thinking:
                return m

    return None
