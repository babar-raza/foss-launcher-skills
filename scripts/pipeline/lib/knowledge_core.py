"""Re-export from canonical location for importers."""
from commands.knowledge.knowledge_core import *  # noqa: F401,F403
from commands.knowledge.knowledge_core import _KNOWLEDGE_ROOT  # noqa: F401 (R-4 alias -- private, needed by test_knowledge_real_path)
