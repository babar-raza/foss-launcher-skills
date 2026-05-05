"""Re-export stub: stale_detect.py moved to commands/ops/stale_detect.py.

Backwards-compatibility shim. Do not add new code here.
- When imported: all names (including private _names) are available via sys.modules aliasing.
- When run as script (__main__): delegates to the real module via runpy.
"""
import sys as _sys
import importlib as _importlib
import runpy as _runpy

if __name__ == "__main__":
    # CLI delegation: run the real module as __main__
    _runpy.run_module("commands.ops.stale_detect", run_name="__main__", alter_sys=True)
else:
    # Import delegation: alias this module to the real one
    _real = _importlib.import_module("commands.ops.stale_detect")
    _sys.modules[__name__] = _real
