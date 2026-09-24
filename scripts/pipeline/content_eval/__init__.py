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
EVALUATOR_LOGIC_VERSION = "19"

# Evaluator freeze gate (C-24).
#
# When set to a version string, CI enforces that EVALUATOR_LOGIC_VERSION
# matches this value exactly.  This prevents accidental evaluator logic
# changes after a freeze has been declared.  Set to None while no freeze
# is active.  To activate the freeze, set this to the current
# EVALUATOR_LOGIC_VERSION value.  Any subsequent ELV bump must also
# update this constant with a documented justification in the commit
# message and GRADE_CONTRACT.md.
EVALUATOR_FREEZE_VERSION: str | None = "19"  # PKGINSTALL-GRADE-SAFETY-OVERRIDE (2026-09-10): install_recipe's
# IR_PUBLISH_CLAIM/IR_UNPUBLISHED_DISCLOSURE FAILs now affect grade via
# SAFETY_OVERRIDE_FINDINGS + _is_grade_eligible() (GRADE_CONTRACT.md §10) --
# a correctness-critical cross-cutting change to grade computation itself,
# not a single-evaluator logic tweak, so ELV bumps alongside it.

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
# Version history (bumped out-of-band, ELV unchanged -- 2026-09-23):
#   code_syntax_check: 2→3 (TC-11, MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION:
#                        collapsed this evaluator's own independent tree-sitter loader onto
#                        the shared lib/example_verification/syntax.py one, RC17's fallback-
#                        coverage gap -- java/csharp/typescript/cpp now get the SAME
#                        tree_sitter_language_pack fallback rust already had, and "go" (never
#                        checked here before) now gets a real tree-sitter parse for the first
#                        time. Real portfolio re-run confirmed 0 FAIL/0 WARN before and after --
#                        no page's stored grade actually changes, so ELV/corpus re-evaluation
#                        is not required, matching the install_recipe precedent above)
# Version history (bumped out-of-band, ELV unchanged -- install_recipe stays EXPERIMENTAL,
# never affected any stored grade, so no corpus re-evaluation is required for this bump):
#   install_recipe: 1→2 (PKGINSTALL-VERSION-BUMP-AND-LINT, 2026-09-10: never bumped despite
#                        3 real logic changes in 2026 -- RC-W1-003 _verify_publish_channel_claims
#                        2026-08-14, ST-054 TC-14 _verify_no_unpublished_disclosure added WARN
#                        2026-09-10, ST-054 TC-16 promoted that check to FAIL 2026-09-10 --
#                        so --skip-graded correctly treats pre-2026-08-14 grades as stale for
#                        this evaluator going forward)
#   install_recipe: 2→3 (ST-214, 2026-09-24: _verify_publish_channel_claims now cross-checks a
#                        non-English page's English counterpart before flagging IR_PUBLISH_CLAIM,
#                        suppressing a class of script-blind negation-regex false positives that
#                        previously FAILed -- a real change in which pages get flagged, not
#                        cosmetic)
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
    "install_recipe": "3",  # v3: ST-214, English-counterpart cross-check for IR_PUBLISH_CLAIM (see history above)
    "limitations_check": "1",
    "risk_language": "2",
    "evidence_depth": "2",  # v2: graduated to CANONICAL_EVALUATORS (TC-SFH-003 2026-07-14)
    "code_plausibility": "1",
    "coverage": "1",
    "type_accuracy": "3",  # v3: Check 6 — C# static class instantiation escalated to FAIL; abstract stays WARN
    "prose_claim_binding": "1",
    "api_completeness": "1",
    "code_syntax_check": "3",  # v3: collapsed onto the shared syntax.py tree-sitter loader (TC-11)
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
    "example_execution": "1",  # MT065-2026-09-06-EXAMPLE-VERIFICATION-CENTRALIZATION C8: initial version
    "topic_grounding": "2",  # CE-02 -> ST-198: shared slug verb parser (synonym-led slugs now parse)
}
