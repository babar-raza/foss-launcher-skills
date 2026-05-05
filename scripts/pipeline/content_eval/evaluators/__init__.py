"""Evaluator base class and registry.

Each evaluator is a class that:
1. Takes a Page + Knowledge
2. Returns a list of Findings
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import Finding, Page

# Registry of evaluator classes by name
_REGISTRY: dict[str, type["BaseEvaluator"]] = {}


class BaseEvaluator(ABC):
    """Base class for all content evaluators."""

    name: str = ""  # Override in subclass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name:
            _REGISTRY[cls.name] = cls

    @abstractmethod
    def evaluate(self, page: "Page", knowledge: Any) -> list["Finding"]:
        """Evaluate a page and return findings."""
        ...


def get_evaluator(name: str) -> type[BaseEvaluator]:
    """Get evaluator class by name."""
    if name not in _REGISTRY:
        raise KeyError(f"Unknown evaluator: {name}. Available: {list(_REGISTRY)}")
    return _REGISTRY[name]


def list_evaluators() -> list[str]:
    """List all registered evaluator names."""
    return sorted(_REGISTRY.keys())


# Import all evaluator modules to trigger registration
def _ensure_loaded():
    """Import all evaluator modules so they self-register."""
    from . import (  # noqa: F401
        api_accuracy,
        api_backtick,
        api_completeness,
        capability_claim_check,
        claim_coverage,
        code_block_api,
        code_plausibility,
        code_syntax_check,
        consumer_usefulness,
        content_substance,
        coverage,
        dead_internal_link,
        description_completeness,
        encoding_check,
        evidence_completeness,
        evidence_depth,
        forbidden_claims,
        format_completeness,
        format_truth,
        install_recipe,
        limitations_check,
        member_validity,
        namespace_correctness,
        page_role,
        platform_purity,
        prose_claim_binding,
        prose_grounding,
        prose_truth,
        risk_language,
        structure,
        type_accuracy,
        version_claim_check,
    )
