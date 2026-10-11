"""Sub-package conftest for tests/content_eval/.

Ensures the pipeline root (scripts/pipeline/) is on sys.path so that
``from content_eval.models import ...`` resolves correctly when pytest
collects these tests as part of the scripts.pipeline package.

The parent tests/conftest.py already does this for the top-level tests/
directory, but pytest needs it repeated here because the __init__.py in
both scripts/pipeline/ and tests/content_eval/ makes Python treat the
collection as a package import — sys.path is checked before the parent
conftest's path mutation takes effect.
"""
import sys
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
