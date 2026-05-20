"""knowledge_core.py — Re-export shim for scripts/pipeline/lib/.

Re-exports from the canonical location commands/knowledge/knowledge_core.py.
Import from here for path-independent access to knowledge core functions.
"""
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("scripts.pipeline.commands.knowledge.knowledge_core")
_sys.modules[__name__] = _real
