"""SEO-TESTS-CI-WIRING: generates the scripts/seo/{pipeline/,}*.py registry
entries to append to scripts/pipeline/config/registry.yaml. Gitignored
(reports/), one-off -- not a pipeline module.
"""
import json

GAP_NOTE = (
    "no test file exists for this module despite active production use -- "
    "a real gap found while wiring scripts/seo/tests into CI "
    "(SEO-TESTS-CI-WIRING), not an intentional exemption; flagged as a "
    "follow-up rather than fixed here (writing new tests is out of this "
    "card's scope)."
)

# (path, kind, test_targets, requires_test, test_exempt_reason)
ENTRIES = [
    ("scripts/seo/pipeline/analyze.py", "entrypoint", [], False, GAP_NOTE),
    ("scripts/seo/pipeline/apply.py", "entrypoint", ["scripts/seo/tests/test_apply_governance.py"], True, None),
    ("scripts/seo/pipeline/audit_schema_a.py", "entrypoint", ["scripts/seo/tests/test_audit_schema_a.py"], True, None),
    ("scripts/seo/pipeline/autonomy_state.py", "library", ["scripts/seo/tests/test_autonomy_state.py"], True, None),
    ("scripts/seo/pipeline/check_merge_safety.py", "entrypoint", ["scripts/seo/tests/test_check_merge_safety.py"], True, None),
    ("scripts/seo/pipeline/compare.py", "entrypoint", [], False, GAP_NOTE),
    ("scripts/seo/pipeline/demand_hints.py", "library", ["scripts/seo/tests/test_demand_hints.py"], True, None),
    ("scripts/seo/pipeline/faq_keyword_seeding.py", "library", ["scripts/seo/tests/test_faq_keyword_seeding.py"], True, None),
    ("scripts/seo/pipeline/frontmatter_grounding.py", "library", ["scripts/seo/tests/test_frontmatter_grounding.py"], True, None),
    ("scripts/seo/pipeline/frontmatter_grounding_audit.py", "entrypoint", ["scripts/seo/tests/test_frontmatter_grounding_audit.py"], True, None),
    ("scripts/seo/pipeline/gsc_history.py", "library", [], False,
     "new module (SEO-TITLE-PILOT-OBSERVATION-MEASURE, it-0009) with no dedicated "
     "unit-test file yet -- exercised via its own driver script and independently "
     "reviewer-verified live-data calls (hand-checked arithmetic against real GSC "
     "snapshots); a real gap for its next real consumer (SEO-METADATA-OBSERVATION-LOOP) "
     "to close, not silently exempted."),
    ("scripts/seo/pipeline/inventory.py", "entrypoint", [], False, GAP_NOTE),
    ("scripts/seo/pipeline/keyword_gap_report.py", "entrypoint", ["scripts/seo/tests/test_keyword_gap_report.py"], True, None),
    ("scripts/seo/pipeline/keyword_lookup.py", "library", ["scripts/seo/tests/test_keyword_lookup.py"], True, None),
    ("scripts/seo/pipeline/keyword_page_assignment.py", "library", ["scripts/seo/tests/test_keyword_page_assignment.py"], True, None),
    ("scripts/seo/pipeline/map_url.py", "entrypoint", ["scripts/seo/tests/test_map_url_resolution.py"], True, None),
    ("scripts/seo/pipeline/quarantine_stale_entries.py", "entrypoint", ["scripts/seo/tests/test_quarantine_stale_entries.py"], True, None),
    ("scripts/seo/pipeline/recommend.py", "entrypoint", ["scripts/seo/tests/test_metrics_recommend_adapter.py"], True,
     "test_metrics_recommend_adapter.py covers recommend.py's metrics-adapter integration only, not its full recommendation logic -- partial, real coverage, not comprehensive."),
    ("scripts/seo/pipeline/report.py", "entrypoint", [], False, GAP_NOTE),
    ("scripts/seo/pipeline/safety.py", "entrypoint", [], False, GAP_NOTE),
    ("scripts/seo/pipeline/schema.py", "library", ["scripts/seo/tests/test_schema_classification.py"], True, None),
    ("scripts/seo/pipeline/title_consistency_evaluator.py", "entrypoint",
     ["scripts/seo/tests/test_title_consistency_evaluator.py", "scripts/seo/tests/test_title_governance_reconcile.py"], True, None),
    ("scripts/seo/pipeline/title_templates.py", "library", ["scripts/seo/tests/test_title_templates.py"], True, None),
    ("scripts/seo/pipeline/validate.py", "entrypoint", ["scripts/seo/tests/test_schema_classification.py"], True,
     "validate.py is imported and exercised by test_schema_classification.py, not a dedicated test_validate.py -- real but indirect coverage."),
    ("scripts/seo/pipeline/weekly_analysis.py", "entrypoint", ["scripts/seo/tests/test_weekly_analysis.py"], True, None),
    ("scripts/seo/get_keywords.py", "entrypoint",
     ["scripts/seo/tests/test_get_keywords_change_detection.py", "scripts/seo/tests/test_get_keywords_dedup.py", "scripts/seo/tests/test_get_keywords_platform_extraction.py"], True, None),
    ("scripts/seo/migrate_platform_labels.py", "entrypoint", ["scripts/seo/tests/test_migrate_platform_labels.py"], True, None),
    ("scripts/seo/review_keywords.py", "entrypoint", ["scripts/seo/tests/test_review_keywords.py"], True, None),
]


def yaml_block(path, kind, test_targets, requires_test, exempt_reason):
    lines = []
    lines.append(f"  - path: {path}")
    lines.append(f"    kind: {kind}")
    lines.append("    lifecycle: active")
    lines.append("    canonical_impl_path: null")
    lines.append(f"    public_entrypoint: {'true' if kind == 'entrypoint' else 'false'}")
    lines.append(f"    cli_contract: {'stable' if kind == 'entrypoint' else 'none'}")
    lines.append("    owner_domain: seo-content")
    lines.append("    backing:")
    lines.append("      kind: internal")
    lines.append("      ref: null")
    if test_targets:
        lines.append("    test_targets:")
        for t in test_targets:
            lines.append(f"      - {t}")
    else:
        lines.append("    test_targets: []")
    lines.append(f"    requires_test: {'true' if requires_test else 'false'}")
    if exempt_reason:
        # YAML double-quoted scalar; escape embedded double quotes.
        esc = exempt_reason.replace('"', '\\"')
        lines.append(f'    test_exempt_reason: "{esc}"')
    lines.append("    deprecated_since: null")
    lines.append('    notes: "SEO-TESTS-CI-WIRING (2026-09-05): registered as part of wiring scripts/seo/tests into pytest.ini and CI (Finding #61)."')
    return "\n".join(lines)


def main():
    header = "\n\n  # ── SEO pipeline (scripts/seo/) ─ registered by SEO-TESTS-CI-WIRING, Finding #61 ─────────────\n"
    blocks = [yaml_block(*e) for e in ENTRIES]
    out = header + "\n\n".join(blocks) + "\n"
    with open("reports/plan_state/_scratch_mt064_registry_seo_entries.yaml", "w", encoding="utf-8") as f:
        f.write(out)
    print(f"wrote {len(ENTRIES)} entries")


if __name__ == "__main__":
    main()
