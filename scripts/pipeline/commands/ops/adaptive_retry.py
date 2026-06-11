"""adaptive_retry.py — Retry wrapper with exponential backoff and strategy fallback.

Wraps skill invocations with configurable retry, exponential backoff, and
fallback skill suggestion when primary execution is exhausted. This moves
failure handling from immediate human escalation toward adaptive recovery.

Usage (programmatic):
    from scripts.pipeline.commands.ops.adaptive_retry import retry_skill

    result = retry_skill(
        skill_id="S-21",
        execute_fn=my_skill_runner,
        max_retries=3,
    )
    if result["status"] == "exhausted":
        print("Fallback suggested:", result["fallback_suggested"])

Concurrency:
    retry_skill is stateless and safe to call from multiple threads or
    processes concurrently. Each call is fully independent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RetryResult:
    """Structured result from a retry_skill invocation."""
    status: str  # "success" | "exhausted"
    attempts: int
    fallback_suggested: str | None
    error_chain: list[str] = field(default_factory=list)
    last_result: Any = None


# Lightweight fallback map — maps skill IDs to their fallback alternative.
# This is intentionally minimal; a production version would query skill_chain.py.
_FALLBACK_MAP: dict[str, str] = {
    "S-21": "S-26",   # page-enhance -> heal-page
    "S-26": "S-78",   # heal-page -> manual-edit
    "S-20": "S-21",   # page-update -> page-enhance
    "S-25": "S-32",   # eval-page -> content-audit
}


def retry_skill(
    skill_id: str,
    execute_fn: Callable[[], Any],
    *,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute a skill with retry, backoff, and fallback suggestion.

    Args:
        skill_id: The skill S-ID being executed. Must be a non-empty string.
        execute_fn: Callable that runs the skill. Must raise on failure.
        max_retries: Maximum number of retry attempts (total attempts = max_retries + 1).
                     Must be >= 0.
        backoff_base: Base for exponential backoff in seconds.
        sleep_fn: Sleep function (injectable for testing).

    Returns:
        Dict with keys: status, attempts, fallback_suggested, error_chain, last_result.

    Raises:
        ValueError: If skill_id is empty or not a string, or if max_retries < 0.
    """
    if not isinstance(skill_id, str) or not skill_id.strip():
        raise ValueError(
            f"skill_id must be a non-empty string, got {skill_id!r}"
        )
    if max_retries < 0:
        raise ValueError(
            f"max_retries must be >= 0, got {max_retries!r}"
        )

    error_chain: list[str] = []
    last_result = None

    for attempt in range(max_retries + 1):
        try:
            last_result = execute_fn()
            return RetryResult(
                status="success",
                attempts=attempt + 1,
                fallback_suggested=None,
                error_chain=error_chain,
                last_result=last_result,
            ).__dict__
        except Exception as exc:
            error_chain.append(f"attempt {attempt + 1}: {exc}")
            if attempt < max_retries:
                delay = backoff_base ** attempt
                sleep_fn(delay)

    fallback = _FALLBACK_MAP.get(skill_id)
    return RetryResult(
        status="exhausted",
        attempts=max_retries + 1,
        fallback_suggested=fallback,
        error_chain=error_chain,
        last_result=last_result,
    ).__dict__
