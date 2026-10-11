#!/usr/bin/env python3
"""Build migration manifest — classify all in-scope files and count references.

Usage:
    PYTHONPATH=scripts/pipeline python scripts/pipeline/tools/build_manifest.py
    PYTHONPATH=scripts/pipeline python scripts/pipeline/tools/build_manifest.py --diff-against scripts/pipeline/migration_manifest.yaml

Outputs migration_manifest.yaml to scripts/pipeline/ (or stdout with --stdout).
"""
import ast
import json
import pathlib
import re
import sys
import yaml  # PyYAML

# Domain assignment map — authoritative for all known files.
# Built from plan Part I + Part VI + rebaseline amendment Q1.
DOMAIN_MAP = {
    # === Governance (11) ===
    "path_guard.py": "governance",
    "override_manager.py": "governance",
    "change_guard.py": "governance",
    "no_downgrade_guard.py": "governance",
    "check_grade_downgrade.py": "governance",
    "check_grade_integrity.py": "governance",
    "check_grade_presence.py": "governance",
    "check_graded_at_only.py": "governance",
    "structural_lock.py": "governance",
    "skill_context.py": "governance",
    "check_dar_prerequisites.py": "governance",  # Part VI

    # === Content (17) ===
    "audit.py": "content",
    "audit_content_created_at.py": "content",
    "audit_content_hash.py": "content",
    "audit_content_origin.py": "content",
    "content_audit.py": "content",
    "batch_reference.py": "content",
    "remediate.py": "content",
    "ground_check.py": "content",
    "cross_platform_audit.py": "content",
    "page_spec.py": "content",
    "validate_frontmatter.py": "content",
    "validate_plugin_structure.py": "content",
    "validate_product_yaml.py": "content",
    "run_content_eval.py": "content",
    "content_created_at_backfill.py": "content",
    "content_hash_backfill.py": "content",
    "content_origin_recover.py": "content",

    # === Knowledge (12) ===
    "scout.py": "knowledge",
    "enrich.py": "knowledge",
    "promote.py": "knowledge",
    "index.py": "knowledge",
    "embed.py": "knowledge",
    "embed_knowledge.py": "knowledge",
    "refresh_knowledge.py": "knowledge",
    "knowledge_coverage.py": "knowledge",
    "stale_detect.py": "knowledge",
    "check_knowledge_completeness.py": "knowledge",
    "expand_cpp_stubs.py": "knowledge",
    "knowledge_core.py": "knowledge",  # dual-use

    # === Ops (18) ===
    "session_ledger.py": "ops",
    "session_logger.py": "ops",
    "skill_run_manager.py": "ops",
    "llm_router.py": "ops",  # dual-use
    "update_product_registry.py": "ops",
    "project_phase_store.py": "ops",
    "post_refresh_verify.py": "ops",
    "sync_providers.py": "ops",
    "sync_skills.py": "ops",
    "link_validator.py": "ops",
    "check_locale_topology.py": "ops",
    "translation_coverage.py": "ops",
    "page_impact_assess.py": "ops",
    "refresh_review.py": "ops",
    "check_audit_results.py": "ops",
    "harvest_ledger.py": "ops",  # Part VI
    "report_extract.py": "ops",  # Part VI
    "skill_chain.py": "ops",  # Rebaseline Q1

    # === Healing (5) ===
    "backtrack_controller.py": "healing",
    "dependency_resolver.py": "healing",  # dual-use
    "verify.py": "healing",
    "retire_page.py": "healing",
    "attach_evidence.py": "healing",

    # === Launch (8) ===
    "launch_gate.py": "launch",
    "launch_rollback.py": "launch",
    "preflight.py": "launch",
    "readiness_scorecard.py": "launch",
    "site_planner.py": "launch",
    "plan_check.py": "launch",
    "readiness_gate.py": "launch",  # Part VI
    "write_classifier.py": "launch",  # Part VI

    # === Diagnostics (8) ===
    "smoke_test.py": "diagnostics",
    "description_coverage_audit.py": "diagnostics",
    "human_review_sampler.py": "diagnostics",
    "truth_audit.py": "diagnostics",
    "truth_audit_content.py": "diagnostics",
    "provenance_normalize_hash.py": "diagnostics",
    # evidence_verifier.py is pure library — domain assigned via LIBRARY_FILES, not here
    "repo_patrol.py": "diagnostics",  # Part VI

    # === Migration (14) ===
    "apply_origin_decisions.py": "migration",
    "logic_version_backfill.py": "migration",
    "provenance_backfill.py": "migration",
    "source_sha_backfill.py": "migration",
    "cleanup_reviewed_field.py": "migration",
    "fix_grade_field_order.py": "migration",
    "fix_last_mechanism.py": "migration",
    "fix_ta_access.py": "migration",
    "normalize_yaml_style.py": "migration",
    "complete_plugin_structure.py": "migration",
    "regenerate_reference.py": "migration",
    "kilocode_learning.py": "migration",
    "migrate_strip_operational_frontmatter.py": "migration",  # Part VI
    "seed_grade_manifest.py": "migration",  # Part VI

    # === Kilocode (4) ===
    "kilocode_gate.py": "kilocode",
    "kilocode_postcheck.py": "kilocode",
    "kilocode_skill_chain.py": "kilocode",
    "kilocode_skill_validator.py": "kilocode",
}

# Library files — go to lib/
LIBRARY_FILES = {
    "_skill_constants.py", "content_discovery.py", "evidence_verifier.py",
    "grade_writer.py", "heal_policy.py", "kilocode_compliance.py",
    "manual_edit_helpers.py", "org_scanner.py", "path_utils.py",
    "provenance.py", "reconcile_triage.py", "token_ops.py",
    "triage_confirm.py", "heal_controller.py",
    "grade_manifest.py", "section_enhance_validator.py",  # Part VI
}

# Dual-use files — have __main__ AND are imported
DUAL_USE = {"knowledge_core.py", "llm_router.py", "dependency_resolver.py"}

# Hook-sensitive scripts (called from git hooks)
HOOK_SENSITIVE = {
    "path_guard.py", "override_manager.py", "skill_context.py",
    "audit.py", "session_ledger.py", "validate_frontmatter.py",
    "check_graded_at_only.py", "provenance_normalize_hash.py",
    "check_plugin_platform.py", "check_protected_overwrites.py",
    "check_python_placement.py",
}

# Protected files (must-not-break)
PROTECTED = {
    "skill_context.py", "session_ledger.py", "path_guard.py",
    "override_manager.py", "knowledge_core.py",
}


def classify_pipeline(path, text):
    """Classify a pipeline .py file."""
    name = path.name
    if name == "__init__.py":
        return "package-init"
    if name in DUAL_USE:
        return "dual-use"
    if name in LIBRARY_FILES:
        return "library"
    # Check for __main__
    has_main = bool(re.search(r'if\s+__name__\s*==\s*["\x27]__main__["\x27]', text))
    if has_main:
        return "entrypoint"
    # Explicit library markers
    if "pure library" in text[:500].lower() or "no __main__" in text[:500].lower():
        return "library"
    return "library"  # default for no-__main__


def count_external_refs(script_path_str, ref_data):
    """Count how many times this script is referenced externally."""
    count = 0
    for file_path, refs in ref_data.items():
        for r in refs:
            if r["ref"] == script_path_str or r["ref"].endswith("/" + pathlib.Path(script_path_str).name):
                count += 1
    return count


def build_manifest(diff_against=None):
    """Build the migration manifest."""
    # Load reference inventory from rebaseline if available
    ref_data = {}
    for rdir in sorted(pathlib.Path("reports/migration").glob("run-*")):
        ref_file = rdir / "current_reference_inventory.json"
        if ref_file.exists():
            ref_data = json.loads(ref_file.read_text(encoding="utf-8"))
            break

    manifest = {"version": "1.0", "generated_by": "build_manifest.py", "files": {}}

    for scope in ["scripts/pipeline", "scripts/ci", "scripts/gap-eval"]:
        root = pathlib.Path(scope)
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            if f.is_dir() or "__pycache__" in str(f):
                continue
            rel = str(f).replace("\\", "/")
            try:
                text = f.read_text(encoding="utf-8", errors="replace") if f.suffix == ".py" else ""
            except Exception:
                text = ""

            in_subdir = f.parent != root
            subdir = str(f.parent.relative_to(root)).replace("\\", "/") if in_subdir else "."

            # Classification
            if scope == "scripts/pipeline" and not in_subdir and f.suffix == ".py":
                classification = classify_pipeline(f, text)
            elif scope == "scripts/ci" and not in_subdir:
                if f.suffix == ".py":
                    classification = "ci-check"
                elif f.suffix == ".sh":
                    classification = "ci-hook"
                else:
                    classification = "ci-other"
            elif scope == "scripts/gap-eval" and not in_subdir and f.suffix == ".py":
                has_main = bool(re.search(r'if\s+__name__\s*==\s*["\x27]__main__["\x27]', text))
                classification = "entrypoint" if has_main else "library"
            elif f.name.startswith("test_") or "/tests/" in rel or f.name == "conftest.py":
                classification = "test"
            elif "/fixtures/" in rel:
                classification = "fixture"
            elif f.suffix in (".yaml", ".yml"):
                classification = "config"
            elif f.suffix == ".md":
                classification = "documentation"
            elif f.suffix == ".txt":
                classification = "requirements"
            elif f.suffix == ".json":
                classification = "data-file"
            elif f.suffix == ".sh":
                classification = "shell-script"
            elif f.suffix == ".py" and f.name == "__init__.py":
                classification = "package-init"
            elif f.suffix == ".py":
                classification = "library"  # default for subdirectory .py
            else:
                classification = "non-python"

            # Domain assignment
            domain = DOMAIN_MAP.get(f.name, "")
            if not domain and f.name in LIBRARY_FILES:
                domain = "lib"
            if not domain and f.name == "_bootstrap.py":
                domain = "infrastructure"
            if scope == "scripts/ci":
                if f.suffix == ".py":
                    domain = "ci-checks"
                elif f.suffix == ".sh":
                    domain = "ci-hooks"
            elif scope == "scripts/gap-eval":
                domain = "gap-eval-src"

            # Target location
            if classification == "library" and not in_subdir and scope == "scripts/pipeline":
                target = f"scripts/pipeline/lib/{f.name}"
            elif classification in ("entrypoint", "dual-use") and domain and not in_subdir and scope == "scripts/pipeline":
                target = f"scripts/pipeline/commands/{domain}/{f.name}"
            elif classification == "ci-check" and not in_subdir:
                target = f"scripts/ci/checks/{f.name}"
            elif classification == "ci-hook" and not in_subdir:
                target = f"scripts/ci/hooks/{f.name}"
            elif classification == "entrypoint" and scope == "scripts/gap-eval" and not in_subdir:
                target = f"scripts/gap-eval/src/{f.name}"
            elif classification == "library" and scope == "scripts/gap-eval" and not in_subdir:
                target = f"scripts/gap-eval/src/{f.name}"
            elif scope == "scripts/gap-eval" and not in_subdir and f.suffix == ".py":
                target = f"scripts/gap-eval/src/{f.name}"
            else:
                target = rel  # stays in place

            entry = {
                "classification": classification,
                "domain": domain,
                "target": target,
                "hook_sensitive": f.name in HOOK_SENSITIVE,
                "protected": f.name in PROTECTED,
                "dual_use": f.name in DUAL_USE,
                "size_bytes": f.stat().st_size,
                "in_subdir": in_subdir,
                "subdir": subdir,
                "external_ref_count": count_external_refs(rel, ref_data),
                "shim_status": "NOT_NEEDED" if in_subdir or target == rel else "PENDING",
            }
            manifest["files"][rel] = entry

    return manifest


def diff_manifests(current, baseline_path):
    """Diff current manifest against a baseline."""
    baseline = yaml.safe_load(pathlib.Path(baseline_path).read_text(encoding="utf-8"))
    baseline_files = set(baseline.get("files", {}).keys())
    current_files = set(current["files"].keys())

    new_files = current_files - baseline_files
    removed_files = baseline_files - current_files

    classification_changes = []
    for f in current_files & baseline_files:
        c_cls = current["files"][f]["classification"]
        b_cls = baseline["files"][f]["classification"]
        if c_cls != b_cls:
            classification_changes.append((f, b_cls, c_cls))

    print("=== Manifest Diff ===")
    if new_files:
        print(f"\nNEW FILES ({len(new_files)}):")
        for f in sorted(new_files):
            e = current["files"][f]
            print(f"  {f}  [{e['classification']}, {e['domain'] or 'unassigned'}]")
    else:
        print("\nNo new files.")

    if removed_files:
        print(f"\nREMOVED FILES ({len(removed_files)}):")
        for f in sorted(removed_files):
            print(f"  {f}")
    else:
        print("\nNo removed files.")

    if classification_changes:
        print(f"\nCLASSIFICATION CHANGES ({len(classification_changes)}):")
        for f, old, new in classification_changes:
            print(f"  {f}  {old} -> {new}")
    else:
        print("\nNo classification changes.")

    has_issues = bool(new_files or removed_files or classification_changes)
    return 1 if has_issues else 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build migration manifest")
    parser.add_argument("--diff-against", help="Compare against existing manifest")
    parser.add_argument("--out", help="Output path (default: scripts/pipeline/migration_manifest.yaml)")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout instead of file")
    args = parser.parse_args()

    manifest = build_manifest()

    if args.diff_against:
        sys.exit(diff_manifests(manifest, args.diff_against))

    output = yaml.dump(manifest, default_flow_style=False, sort_keys=True, allow_unicode=True)

    if args.stdout:
        print(output)
    else:
        out_path = pathlib.Path(args.out) if args.out else pathlib.Path("scripts/pipeline/migration_manifest.yaml")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Manifest written to {out_path}")

    # Summary
    files = manifest["files"]
    from collections import Counter
    by_cls = Counter(v["classification"] for v in files.values())
    by_domain = Counter(v["domain"] for v in files.values() if v["domain"])
    root_py = {k: v for k, v in files.items()
               if k.startswith("scripts/pipeline/") and not v["in_subdir"] and k.endswith(".py")
               and v["classification"] != "package-init"}

    print(f"\nTotal files: {len(files)}")
    print("By classification:")
    for c, n in sorted(by_cls.items()):
        print(f"  {c}: {n}")
    print("By domain:")
    for d, n in sorted(by_domain.items()):
        print(f"  {d}: {n}")
    print(f"\nPipeline root .py (excl __init__): {len(root_py)}")
    print(f"  entrypoints: {sum(1 for v in root_py.values() if v['classification'] == 'entrypoint')}")
    print(f"  libraries: {sum(1 for v in root_py.values() if v['classification'] == 'library')}")
    print(f"  dual-use: {sum(1 for v in root_py.values() if v['classification'] == 'dual-use')}")
    print(f"  hook_sensitive: {sum(1 for v in root_py.values() if v['hook_sensitive'])}")
    print(f"  protected: {sum(1 for v in root_py.values() if v['protected'])}")

    # Check for unassigned
    unassigned = [k for k, v in root_py.items() if not v["domain"] and v["classification"] != "package-init"]
    if unassigned:
        print(f"\nBLOCKER: {len(unassigned)} unassigned files:")
        for u in sorted(unassigned):
            print(f"  {u}")
        sys.exit(1)
    else:
        print("\nAll pipeline root .py files have domain assignments.")
