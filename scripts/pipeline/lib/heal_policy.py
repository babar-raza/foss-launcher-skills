"""heal_policy.py — Re-export shim for scripts/pipeline/lib/.

Re-exports from the canonical location commands/healing/heal_policy.py.
Import from here for path-independent access to HealPolicy and related functions.
"""
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("scripts.pipeline.commands.healing.heal_policy")
_sys.modules[__name__] = _real
