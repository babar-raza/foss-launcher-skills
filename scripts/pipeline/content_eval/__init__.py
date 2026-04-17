"""content_eval — Production-grade content evaluation against repo truth.

Composes with audit.py to provide multi-dimensional content evaluation:
API accuracy, prose truth, section-role compliance, platform purity,
structural correctness, risk language, evidence depth, coverage gaps,
forbidden claims, and cross-page consistency.
"""

__version__ = "0.1.0"

# Bump this when evaluator logic changes in a way that affects grades.
# When this value does not match graded_logic_version in a page's frontmatter,
# --skip-graded will re-grade the page even if graded_model_sha is current.
# Update the AGENTS.md evaluator change checklist when bumping this value.
EVALUATOR_LOGIC_VERSION = "13"
