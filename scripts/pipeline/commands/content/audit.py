"""Deterministic content-vs-knowledge API accuracy auditor.

Extracts every API token (class names, method calls, property access,
enum members, imports) from content files and verifies each against
the merged api_surface.json knowledge model. Also validates the
evidence: frontmatter block required by S-24.

Usage:
    python scripts/audit.py {family} {platform}      # Single product
    python scripts/audit.py all                        # All products
    python scripts/audit.py --files path1.md path2.md  # Specific files
    python scripts/audit.py all --json                 # Machine-readable
    python scripts/audit.py all --no-evidence          # Skip evidence checks

Implementation is in the audit/ package (Phase 5 refactor).
Import from `audit` to get all symbols — Python loads audit/__init__.py
(the package takes precedence over this file when both exist in sys.path).

Relationship to ground_check.py
--------------------------------
ground_check.py is a separate, lighter-weight gate: it only checks backtick
API identifiers (e.g. `ClassName`, `method_name`) against api_surface.json
and returns a numeric grounding ratio with PASS/WARN/FAIL exit codes (0/1/2).
Use ground_check.py for a quick spot-check of a single page grounding ratio.

This file (audit.py) performs a comprehensive token-level audit: it extracts
ALL API references from content prose, checks each against the knowledge model,
and also validates the evidence: frontmatter block. The heal-page skill (S-25)
invokes audit.py at Steps 8 and 11. Use audit.py for full product-level or
file-level accuracy auditing.
"""
# This file serves as the CLI entry point only.
# All implementation lives in audit/ sub-modules.
# For imports: `from audit import X` loads audit/__init__.py, not this file.
import sys
from pathlib import Path

# Ensure scripts/pipeline/ is on sys.path for package imports (audit/, core/, etc.)
_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = str(_HERE.parent.parent)  # commands/content/ -> commands/ -> pipeline/
# Remove commands/content/ from sys.path to avoid audit.py shadowing the audit/ package
if str(_HERE) in sys.path:
    sys.path.remove(str(_HERE))
if _PIPELINE_ROOT not in sys.path:
    sys.path.insert(0, _PIPELINE_ROOT)

from core.env_loader import load_env  # noqa: E402
load_env()

from audit.runner import main  # noqa: E402

if __name__ == "__main__":
    main()
