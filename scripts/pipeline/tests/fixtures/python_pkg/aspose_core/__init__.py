"""Fixture package for extraction golden tests (TC-MT040-42).

Mirrors the real words/python namespace-parent layout: the outer
tests/fixtures/python_pkg/__init__.py is empty; this one level down
declares the actual __all__.
"""
from .document import Document
from .writer import Writer

__all__ = ["Document", "Writer", "SaveFormat"]
