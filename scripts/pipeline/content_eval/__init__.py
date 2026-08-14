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
EVALUATOR_LOGIC_VERSION = "18"

# Evaluator freeze gate (C-24).
#
# When set to a version string, CI enforces that EVALUATOR_LOGIC_VERSION
# matches this value exactly.  This prevents accidental evaluator logic
# changes after a freeze has been declared.  Set to None while no freeze
# is active.  To activate the freeze, set this to the current
# EVALUATOR_LOGIC_VERSION value.  Any subsequent ELV bump must also
# update this constant with a documented justification in the commit
# message and GRADE_CONTRACT.md.
EVALUATOR_FREEZE_VERSION: str | None = "18"  # TC-SFH-003: evidence_depth graduated to CANONICAL

# TC-5: Per-evaluator version dict.
#
# Increment the version for an individual evaluator when its logic changes.
# Pages that have graded_evaluator_versions in frontmatter are compared
# evaluator-by-evaluator, so only changed evaluators trigger re-evaluation.
# Bump EVALUATOR_LOGIC_VERSION only for correctness-critical cross-cutting changes
# that require full re-evaluation of the entire corpus.
#
# Version history (evaluators bumped at v15):
#   code_syntax_check:    1→2 (tree-sitter integration)
#   consumer_usefulness:  1→2 (purpose framing + code-context signals)
#   risk_language:        1→2 (API reference table suppression)
# Version history (evaluators bumped at v17):
#   capability_claim_check: 1→2 (FP-001: code-fence filtering in _extract_scannable_lines;
#                                 code blocks in YAML frontmatter text fields are now skipped)
# Version history (evaluators bumped at v18):
#   evidence_depth: 1→2 (TC-SFH-003: graduated to CANONICAL_EVALUATORS; EG_GROUNDING WARN
#                        now caps grade at B; EG_STALE excluded from ceiling by category key)
EVALUATOR_VERSIONS: dict[str, str] = {
    "api_accuracy": "2",  # v2: TS/JS built-ins (Error, JSON, Buffer, Worker, GLB, etc.) added to PLATFORM_SDK_CLASSES
    "api_backtick": "1",
    "claim_coverage": "1",
    "code_block_api": "1",
    "content_substance": "1",
    "dead_internal_link": "1",
    "description_completeness": "1",
    "platform_purity": "1",
    "forbidden_claims": "1",
    "page_role": "1",
    "structure": "1",
    "prose_truth": "2",  # v2: fires without claims/formats,
    "format_truth": "2",  # v2: skip negation check when no direction verb present (eliminates FP on method descriptions)
    "install_recipe": "1",
    "limitations_check": "1",
    "risk_language": "2",
    "evidence_depth": "2",  # v2: graduated to CANONICAL_EVALUATORS (TC-SFH-003 2026-07-14)
    "code_plausibility": "1",
    "coverage": "1",
    "type_accuracy": "3",  # v3: Check 6 — C# static class instantiation escalated to FAIL; abstract stays WARN
    "prose_claim_binding": "1",
    "api_completeness": "1",
    "code_syntax_check": "2",
    "namespace_correctness": "2",  # v2: C# allow-list from api_surface.json canonical_namespace, not NuGet PackageId
    "format_completeness": "1",
    "member_validity": "1",
    "prose_grounding": "1",
    "version_claim_check": "1",
    "capability_claim_check": "2",  # v2: code-fence filtering in _extract_scannable_lines (FP-001 fix)
    "encoding_check": "1",
    "consumer_usefulness": "2",
    "generic_description_check": "1",  # TC-GDF-001: initial version
    "duplicate_content": "1",  # RC-W1-005: initial version — whole-page duplicate + alias-collision detection
}
