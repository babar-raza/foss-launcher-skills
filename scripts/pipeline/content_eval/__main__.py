"""Entry point: python -m scripts.pipeline.content_eval ..."""

# Bootstrap: when invoked as `python -m content_eval` from repo root, Python
# adds the content_eval/ package dir to sys.path, NOT its parent (scripts/pipeline/).
# Sibling packages like `core`, `extraction`, etc. live under scripts/pipeline/,
# so we must add that parent explicitly — the same pattern used by audit.py,
# refresh_knowledge.py, and other pipeline entry points.
import sys
from pathlib import Path
_PIPELINE_DIR = Path(__file__).resolve().parents[1]  # scripts/pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from .cli import main

if __name__ == "__main__":
    main()
