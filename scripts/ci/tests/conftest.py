"""Conftest: ensure CI tests import from checks/, not from ci/ root shims."""
import importlib
import sys
from pathlib import Path

_CI_DIR = str(Path(__file__).resolve().parent.parent)
_CI_DIR_RESOLVED = str(Path(_CI_DIR).resolve())
_CHECKS_DIR = str(Path(__file__).resolve().parent.parent / "checks")


def _ensure_canonical_import(module_name: str):
    """Force import from checks/ instead of ci/ root shim."""
    if module_name in sys.modules:
        mod = sys.modules[module_name]
        if hasattr(mod, '__file__') and mod.__file__:
            mod_dir = str(Path(mod.__file__).resolve().parent)
            if mod_dir == _CI_DIR_RESOLVED:
                del sys.modules[module_name]


# Ensure checks/ is first in path
if _CHECKS_DIR not in sys.path:
    sys.path.insert(0, _CHECKS_DIR)

# Remove ci/ root to prevent shim shadowing
sys.path[:] = [
    p for p in sys.path
    if not (p and str(Path(p).resolve()) == _CI_DIR_RESOLVED
            and 'checks' not in p and 'tests' not in p)
]
