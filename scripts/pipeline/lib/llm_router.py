"""llm_router.py — LLM routing stub for scripts/pipeline/lib/.

In aspose.org this re-exports from commands/ops/llm_router.py which provides
LLM provider selection and call routing. That module is not yet ported to
foss-launcher (no canonical location exists under commands/ops/).

This stub provides a minimal no-op implementation so imports do not fail.
When the full llm_router is ported, replace this stub with a re-export shim.

TODO (SC-*): Port commands/ops/llm_router.py from aspose.org and replace this
stub with: from scripts.pipeline.commands.ops.llm_router import *
"""
from __future__ import annotations

from typing import Any


class LLMRouterNotImplementedError(NotImplementedError):
    """Raised when llm_router functionality is invoked before porting is complete."""


def route(
    provider: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Route an LLM call — STUB: always raises until ported.

    Args:
        provider: LLM provider name (e.g. "openai", "anthropic").
        model: Model identifier string.
        **kwargs: Additional call parameters.

    Raises:
        LLMRouterNotImplementedError: Always. Port commands/ops/llm_router.py first.
    """
    raise LLMRouterNotImplementedError(
        "llm_router is not yet ported to foss-launcher. "
        "Port scripts/pipeline/commands/ops/llm_router.py from aspose.org "
        "and update this stub to re-export from that module."
    )


def get_provider(name: str | None = None) -> str:
    """Return the configured LLM provider — STUB: always raises until ported."""
    raise LLMRouterNotImplementedError(
        "llm_router is not yet ported. See route() docstring."
    )
