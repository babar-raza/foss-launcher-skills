"""Deterministic evidence block generator for content pages.

Builds the `evidence:` frontmatter block by extracting verified API tokens
from code blocks and mapping them to claim_ids via the knowledge model index.
No LLM required. Same inputs → same outputs on every run.

Usage:
    python scripts/pipeline/commands/healing/attach_evidence.py 3d python          # one product
    python scripts/pipeline/commands/healing/attach_evidence.py all                 # all products
    python scripts/pipeline/commands/healing/attach_evidence.py --files path1.md   # specific files
    python scripts/pipeline/commands/healing/attach_evidence.py 3d python --dry-run # preview, no writes

Rules:
    - Pages with audit FAIL findings are skipped (evidence only attests verified content)
    - Pages that already have evidence: with the current model_sha are skipped (idempotent)
    - Prose-only pages (no code blocks) get evidence: with claims: [], apis: [] — honest gap
    - Existing evidence: block is merged, not replaced (existing manual claims are preserved)
    - Per-section evidence breakdown via `sections:` array (backward-compatible)

Implementation is in the evidence/ package (Phase 5 refactor).
Import from `evidence` to get all symbols — Python loads evidence/__init__.py
when the package exists alongside this file.
"""
# This file serves as the CLI entry point only.
# All implementation lives in evidence/ sub-modules.
import sys
from pathlib import Path

# cli-entry-point guard: when invoked directly Python adds scripts/pipeline/ automatically; guard is defensive
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent.parent.parent))  # scripts/pipeline/

from evidence.runner import main  # noqa: E402

if __name__ == "__main__":
    main()
