"""Fixer base class and registry — mirrors evaluators/__init__.py pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...models import Finding

# Registry of fixer classes by name
_FIXER_REGISTRY: dict[str, type["BaseFixer"]] = {}


class BaseFixer(ABC):
    """Base class for all deterministic content fixers.

    Each fixer handles a specific category of eval findings and applies
    safe, idempotent text transformations to resolve them.
    """

    name: str = ""                  # Override in subclass
    categories: set[str] = set()    # Which finding categories this handles

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name:
            _FIXER_REGISTRY[cls.name] = cls

    @abstractmethod
    def can_fix(self, finding: "Finding", page_text: str, meta: dict[str, Any]) -> bool:
        """Return True if this fixer can handle this specific finding.

        Args:
            finding: The eval finding to consider.
            page_text: Full raw text of the page.
            meta: Dict with keys: filepath, family, platform, subdomain, page_role.
        """
        ...

    @abstractmethod
    def apply(self, finding: "Finding", page_text: str, meta: dict[str, Any]) -> str:
        """Apply the fix and return the modified page text.

        Must be idempotent — applying twice yields same result.

        Args:
            finding: The eval finding to fix.
            page_text: Full raw text of the page.
            meta: Dict with keys: filepath, family, platform, subdomain, page_role.

        Returns:
            Modified page text (or original if no change needed).
        """
        ...


def get_fixer(name: str) -> type[BaseFixer]:
    """Get fixer class by name."""
    _ensure_loaded()
    if name not in _FIXER_REGISTRY:
        raise KeyError(f"Unknown fixer: {name}. Available: {list(_FIXER_REGISTRY)}")
    return _FIXER_REGISTRY[name]


def list_fixers() -> list[str]:
    """List all registered fixer names."""
    _ensure_loaded()
    return sorted(_FIXER_REGISTRY.keys())


def get_fixer_for_category(category: str) -> list[type[BaseFixer]]:
    """Get all fixers that handle a given category."""
    _ensure_loaded()
    return [cls for cls in _FIXER_REGISTRY.values() if category in cls.categories]


def _ensure_loaded():
    """Import all fixer modules so they self-register."""
    from . import (  # noqa: F401
        code_fence_lang,
        evidence_attach,
        frontmatter_author,
        frontmatter_categories,
        frontmatter_layout,
        frontmatter_type,
        placeholder_remove,
        steps_shortcode,
    )
