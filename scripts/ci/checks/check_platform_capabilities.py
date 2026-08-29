#!/usr/bin/env python3
"""check_platform_capabilities.py — D-1 platform capability contract CI gate.

Mission MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH, TC-MT040-40. Companion CI
check to scripts/pipeline/config/platform_capabilities.yaml and
scripts/pipeline/tests/test_platform_capability_matrix.py -- this is the
"someone edits products.json or a pipeline map and never touches the YAML"
gate: it fails CI, not just a local pytest run a reviewer might skip.

Two check families:

  CHECK A — Platform completeness (BLOCKING):
    Every platform with >=1 active row in data/products.json has a row in
    platform_capabilities.yaml (undeclared_active_platform), and every row
    declared in the YAML still has >=1 active product (stale_declared_platform
    -- also BLOCKING, since a stale row is exactly the kind of silent drift
    this file exists to prevent).

  CHECK B — Per-site value conformance (BLOCKING):
    For every platform declared in the YAML, the declared value for each of
    the 16 capability sites is re-read from the REAL pipeline code (always
    the actual scripts/pipeline/ modules in this checkout -- independent of
    any --repo-root override used for testing the YAML/products.json side)
    and compared against the YAML. Any disagreement is a value_mismatch
    finding: this is what catches "a capability site exists in code but
    isn't declared for some platform that has it" -- e.g. a platform's
    tree_helpers._CLASS_TYPES entry gaining a new kind the YAML doesn't
    know about yet.

Usage:
    python scripts/ci/checks/check_platform_capabilities.py
    python scripts/ci/checks/check_platform_capabilities.py --dry-run   # exit 0 always
    python scripts/ci/checks/check_platform_capabilities.py --json

Exit codes:
    0 — no findings (or --dry-run)
    1 — at least one finding
"""
from __future__ import annotations

import argparse
import json as _json
import sys
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _DEFAULT_REPO_ROOT

# The "code" side of every comparison is always imported from the REAL,
# live scripts/pipeline/ tree of this checkout -- configure(repo_root=...)
# only ever redirects the YAML/products.json side (the data this check
# validates), never the pipeline code it validates that data against. This
# mirrors check_skill_doc_pins.py's own configure() seam but is narrower by
# design: faking the "code" side would defeat the point of a conformance
# check.
_PIPELINE_ROOT = _DEFAULT_REPO_ROOT / "scripts" / "pipeline"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override the repo root used to locate platform_capabilities.yaml and
    data/products.json. Test/operator hook."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def _yaml_path() -> Path:
    return _REPO_ROOT / "scripts" / "pipeline" / "config" / "platform_capabilities.yaml"


def _products_path() -> Path:
    return _REPO_ROOT / "data" / "products.json"


def _load_yaml() -> "dict | None":
    import yaml
    path = _yaml_path()
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_active_platforms() -> set:
    path = _products_path()
    if not path.is_file():
        return set()
    with open(path, encoding="utf-8") as f:
        data = _json.load(f)
    return {p["platform"] for p in data if p.get("active")}


def _pipeline_module(dotted: str):
    if str(_PIPELINE_ROOT) not in sys.path:
        sys.path.insert(0, str(_PIPELINE_ROOT))
    import importlib
    return importlib.import_module(dotted)


# ---------------------------------------------------------------------------
# CHECK A — platform completeness
# ---------------------------------------------------------------------------

def check_platform_completeness(caps: "dict | None", active_platforms: set) -> list[dict]:
    findings: list[dict] = []
    declared = set(caps.get("platforms", {}).keys()) if caps else set()
    for platform in sorted(active_platforms - declared):
        findings.append({
            "kind": "undeclared_active_platform", "platform": platform, "site": None,
            "detail": (
                f"'{platform}' has an active product in data/products.json but "
                f"no row in platform_capabilities.yaml"
            ),
        })
    for platform in sorted(declared - active_platforms):
        findings.append({
            "kind": "stale_declared_platform", "platform": platform, "site": None,
            "detail": (
                f"'{platform}' is declared in platform_capabilities.yaml but "
                f"has no active product in data/products.json"
            ),
        })
    return findings


# ---------------------------------------------------------------------------
# CHECK B — per-site value conformance
# ---------------------------------------------------------------------------

def _finding(kind: str, platform: str, site: str, detail: str) -> dict:
    return {"kind": kind, "platform": platform, "site": site, "detail": detail}


def check_class_func_module_kinds(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    tree_helpers = _pipeline_module("extraction.tree_helpers")
    for site, real_map in (
        ("class_kinds", tree_helpers._CLASS_TYPES),
        ("func_kinds", tree_helpers._FUNC_TYPES),
        ("module_kinds", tree_helpers._MODULE_TYPES),
    ):
        for platform in platforms:
            row = caps["platforms"][platform]
            lang = row["language"]
            declared = set(row[site])
            real = real_map.get(lang, set())
            if declared != real:
                findings.append(_finding(
                    "value_mismatch", platform, site,
                    f"YAML {sorted(declared)} != tree_helpers.{'_CLASS_TYPES' if site == 'class_kinds' else '_FUNC_TYPES' if site == 'func_kinds' else '_MODULE_TYPES'}[{lang!r}] {sorted(real)}",
                ))
    return findings


def check_doc_style(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    tree_helpers = _pipeline_module("extraction.tree_helpers")
    for platform in platforms:
        row = caps["platforms"][platform]
        lang = row["language"]
        declared = row["doc_style"]
        real = tree_helpers._DOC_COMMENT_STYLES.get(lang)
        if declared != real:
            findings.append(_finding(
                "value_mismatch", platform, "doc_style",
                f"YAML {declared!r} != tree_helpers._DOC_COMMENT_STYLES[{lang!r}] {real!r}",
            ))
    return findings


def check_primary_language(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    tree_helpers = _pipeline_module("extraction.tree_helpers")
    for platform in platforms:
        declared = caps["platforms"][platform]["primary_language"]
        real = tree_helpers.PLATFORM_TO_LANG.get(platform)
        if declared != real:
            findings.append(_finding(
                "value_mismatch", platform, "primary_language",
                f"YAML {declared!r} != tree_helpers.PLATFORM_TO_LANG[{platform!r}] {real!r}",
            ))
    return findings


def check_install_parser(caps: dict, platforms: list) -> list[dict]:
    """Sanity-only (no manifest-file synthesis here -- see the pytest matrix
    for the functional version): confirms parse_manifest() dispatches
    somewhere non-trivial for every declared platform (never silently falls
    through to the bare `return {}` catch-all) by checking the dispatcher's
    own recognized platform set includes it."""
    findings: list[dict] = []
    package_manifest = _pipeline_module("extraction.package_manifest")
    import inspect
    src = inspect.getsource(package_manifest.parse_manifest)
    for platform in platforms:
        # Every branch in parse_manifest() tests `platform == "<name>"` or
        # `platform in (...)` against a string literal equal to the
        # platform name itself (net/java/cpp/go/rust/typescript all appear
        # verbatim; python too).
        if f'"{platform}"' not in src and f"'{platform}'" not in src:
            findings.append(_finding(
                "value_mismatch", platform, "install_parser",
                f"platform_manifest.parse_manifest() has no dispatch branch "
                f"mentioning '{platform}' -- declared manifest_files "
                f"{caps['platforms'][platform]['install_parser']['manifest_files']} "
                f"would never be reached",
            ))
    return findings


def check_package_managers(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    install_recipe = _pipeline_module("content_eval.evaluators.install_recipe")
    for platform in platforms:
        decl = caps["platforms"][platform]["package_managers"]
        real = install_recipe._PLATFORM_PKG_MANAGERS.get(platform)
        if isinstance(decl, dict) and decl.get("declared") is False:
            if real is not None:
                findings.append(_finding(
                    "stale_n/a", platform, "package_managers",
                    f"YAML declares package_managers absent, but "
                    f"install_recipe._PLATFORM_PKG_MANAGERS now has an entry: {sorted(real)}",
                ))
        else:
            if real is None:
                findings.append(_finding(
                    "value_mismatch", platform, "package_managers",
                    "YAML declares a value but install_recipe._PLATFORM_PKG_MANAGERS has no entry",
                ))
            elif set(decl) != real:
                findings.append(_finding(
                    "value_mismatch", platform, "package_managers",
                    f"YAML {set(decl)} != install_recipe._PLATFORM_PKG_MANAGERS[{platform!r}] {real}",
                ))
    return findings


def check_foreign_prose_patterns(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    content_eval_config = _pipeline_module("content_eval.config")
    for platform in platforms:
        decl = caps["platforms"][platform]["foreign_prose_patterns"]
        real = content_eval_config.PROSE_FOREIGN_PATTERNS.get(platform)
        if decl.get("declared") is False:
            if real is not None:
                findings.append(_finding(
                    "stale_n/a", platform, "foreign_prose_patterns",
                    "YAML declares foreign_prose_patterns absent, but "
                    "content_eval/config.py:PROSE_FOREIGN_PATTERNS now has an entry",
                ))
        else:
            if real is None:
                findings.append(_finding(
                    "value_mismatch", platform, "foreign_prose_patterns",
                    "YAML declares a value but PROSE_FOREIGN_PATTERNS has no entry",
                ))
            elif len(real) != decl["pattern_count"]:
                findings.append(_finding(
                    "value_mismatch", platform, "foreign_prose_patterns",
                    f"YAML says {decl['pattern_count']} patterns, code has {len(real)}",
                ))
    return findings


def check_smoke_test_langs(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    content_eval_config = _pipeline_module("content_eval.config")
    smoke_test = _pipeline_module("commands.diagnostics.smoke_test")
    csc = _pipeline_module("content_eval.evaluators.code_syntax_check")
    for platform in platforms:
        decl = caps["platforms"][platform]["smoke_test_langs"]
        lang = caps["platforms"][platform]["language"]
        real = content_eval_config.PLATFORM_EXPECTED_LANGS.get(platform)
        if decl.get("declared") is False:
            if real is not None:
                findings.append(_finding(
                    "stale_n/a", platform, "smoke_test_langs",
                    "YAML declares smoke_test_langs absent, but "
                    "PLATFORM_EXPECTED_LANGS now has an entry",
                ))
        else:
            if real is None:
                findings.append(_finding(
                    "value_mismatch", platform, "smoke_test_langs",
                    "YAML declares a value but PLATFORM_EXPECTED_LANGS has no entry",
                ))
            elif set(decl["value"]) != real:
                findings.append(_finding(
                    "value_mismatch", platform, "smoke_test_langs",
                    f"YAML {set(decl['value'])} != PLATFORM_EXPECTED_LANGS[{platform!r}] {real}",
                ))
        smoke_test_present = platform in smoke_test._PLATFORM_LANGS
        if smoke_test_present != decl.get("smoke_test_py_matches", False):
            findings.append(_finding(
                "value_mismatch", platform, "smoke_test_langs",
                f"YAML smoke_test_py_matches={decl.get('smoke_test_py_matches', False)} "
                f"!= real smoke_test.py._PLATFORM_LANGS membership {smoke_test_present}",
            ))
        csc_present = lang in csc._TS_LANGS
        if csc_present != decl.get("code_syntax_check_py_matches", False):
            findings.append(_finding(
                "value_mismatch", platform, "smoke_test_langs",
                f"YAML code_syntax_check_py_matches="
                f"{decl.get('code_syntax_check_py_matches', False)} != real "
                f"code_syntax_check._TS_LANGS membership {csc_present}",
            ))
    return findings


def check_kb_suffix(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    site_planner = _pipeline_module("commands.launch.site_planner")
    for platform in platforms:
        decl = caps["platforms"][platform]["kb_suffix"]
        real_effective = site_planner.KB_PLATFORM_SUFFIX.get(platform, platform)
        really_declared = platform in site_planner.KB_PLATFORM_SUFFIX
        if decl.get("declared") is False:
            if really_declared:
                findings.append(_finding(
                    "stale_n/a", platform, "kb_suffix",
                    "YAML declares kb_suffix absent, but KB_PLATFORM_SUFFIX now has an entry",
                ))
            elif real_effective != decl["effective_value"]:
                findings.append(_finding(
                    "value_mismatch", platform, "kb_suffix",
                    f"YAML effective_value {decl['effective_value']!r} != real fallback {real_effective!r}",
                ))
        else:
            if not really_declared:
                findings.append(_finding(
                    "value_mismatch", platform, "kb_suffix",
                    "YAML declares a value but KB_PLATFORM_SUFFIX has no entry",
                ))
            elif real_effective != decl["value"]:
                findings.append(_finding(
                    "value_mismatch", platform, "kb_suffix",
                    f"YAML {decl['value']!r} != KB_PLATFORM_SUFFIX[{platform!r}] {real_effective!r}",
                ))
    return findings


def check_trouble_platform(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    site_planner = _pipeline_module("commands.launch.site_planner")
    for platform in platforms:
        declared = caps["platforms"][platform]["trouble_platform"]
        real = platform in site_planner.TROUBLE_PLATFORMS
        if declared != real:
            findings.append(_finding(
                "value_mismatch", platform, "trouble_platform",
                f"YAML {declared} != (platform in TROUBLE_PLATFORMS) {real}",
            ))
    return findings


def check_coverage_policy(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    coverage = _pipeline_module("content_eval.evaluators.coverage")
    for platform in platforms:
        declared = caps["platforms"][platform]["coverage_policy"]["concrete_only"]
        real = platform in coverage.CONCRETE_ONLY_PLATFORMS
        if declared != real:
            findings.append(_finding(
                "value_mismatch", platform, "coverage_policy",
                f"YAML concrete_only={declared} != (platform in CONCRETE_ONLY_PLATFORMS) {real}",
            ))
    return findings


def check_reachability_enforced(caps: dict, platforms: list) -> list[dict]:
    findings: list[dict] = []
    reference_filter = _pipeline_module("lib.reference_filter")
    for platform in platforms:
        declared = caps["platforms"][platform]["reachability_adapter"]["enforced"]
        real = platform in reference_filter.REACHABILITY_ENFORCED_PLATFORMS
        if declared != real:
            findings.append(_finding(
                "value_mismatch", platform, "reachability_adapter",
                f"YAML enforced={declared} != (platform in REACHABILITY_ENFORCED_PLATFORMS) {real}",
            ))
    return findings


_SITE_CHECKS = (
    check_class_func_module_kinds,
    check_doc_style,
    check_primary_language,
    check_install_parser,
    check_package_managers,
    check_foreign_prose_patterns,
    check_smoke_test_langs,
    check_kb_suffix,
    check_trouble_platform,
    check_coverage_policy,
    check_reachability_enforced,
)


def check_all() -> list[dict]:
    caps = _load_yaml()
    active_platforms = _load_active_platforms()

    findings = check_platform_completeness(caps, active_platforms)
    if caps is None:
        findings.append({
            "kind": "missing_yaml", "platform": None, "site": None,
            "detail": f"platform_capabilities.yaml not found at {_yaml_path()}",
        })
        return findings

    # Only run per-site value checks against platforms this check can trust
    # to have a well-formed row (declared AND active) -- an
    # undeclared_active_platform finding from CHECK A already covers the
    # missing case; a stale_declared_platform row is skipped here (its own
    # finding already fired, and comparing values for a platform with no
    # active product is not meaningful).
    checkable_platforms = sorted(set(caps["platforms"].keys()) & active_platforms)

    for check_fn in _SITE_CHECKS:
        findings.extend(check_fn(caps, checkable_platforms))

    return findings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check platform_capabilities.yaml against the real pipeline code (D-1, TC-MT040-40)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report findings but always exit 0")
    parser.add_argument("--json", action="store_true", help="Print findings as JSON")
    args = parser.parse_args()

    findings = check_all()

    if args.json:
        print(_json.dumps(findings, indent=2))
    else:
        if not findings:
            print("check_platform_capabilities: PASS -- 0 findings.")
        else:
            print(f"check_platform_capabilities: FAIL -- {len(findings)} finding(s):\n")
            for f in findings:
                where = f["platform"] or "(no platform)"
                site = f.get("site") or "(platform-level)"
                print(f"  [{f['kind'].upper()}] {where} / {site}: {f['detail']}")
        if args.dry_run:
            print("\n--dry-run: not failing the build.")

    if args.dry_run:
        sys.exit(0)
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
