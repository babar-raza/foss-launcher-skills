# Adapted from aspose.org
"""Compatibility wrapper for the knowledge embedding CLI."""

from __future__ import annotations

import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/knowledge/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

# In aspose.org this imports from embed.py at the pipeline level.
# In foss-launcher the embed module lives in commands/knowledge/embed.py.
from commands.knowledge.embed import main  # noqa: E402


if __name__ == "__main__":
    main()
