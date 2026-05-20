# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""check_metrics_taxonomy.py — CI gate: validate metrics taxonomy consistency.

Loads scripts/pipeline/config/metrics_taxonomy.yaml and validates:
- Required sections exist
- agent_owner is "Babar Raza"
- Required agents and job types for Slices 0–8 are present
- Posting modes enforce dry_run_default=true, correct limits, test markers
- Non-professionalize boundaries are documented
- No secret-like values appear in taxonomy

Usage:
    python scripts/ci/checks/check_metrics_taxonomy.py
    python scripts/ci/checks/check_metrics_taxonomy.py --taxonomy path/to/taxonomy.yaml
    python scripts/ci/checks/check_metrics_taxonomy.py --json-output

Exit codes:
    0  Taxonomy is valid
    1  One or more validation failures
"""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent.parent.parent))
_DEFAULT_TAXONOMY = _REPO_ROOT / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml"

REQUIRED_SECTIONS = [
    "version",
    "agent_owner",
    "default_website_mapping",
    "website_sections",
    "products",
    "platforms",
    "agents",
    "job_types",
    "field_derivation_rules",
    "non_professionalize_boundaries",
    "posting_modes",
]

REQUIRED_AGENT_OWNER = os.environ.get("REQUIRED_AGENT_OWNER", "Babar Raza")

# Agents required after Slice 8
REQUIRED_AGENTS = [
    "aspose-org-knowledge-enrichment",
    "aspose-org-knowledge-embedding",
    "aspose-org-gap-evaluation",
    "aspose-org-gap-synthesis",
    "aspose-org-translator",
    "aspose-org-seo-recommendation",
]

# Job types required after Slice 8
REQUIRED_JOB_TYPES = [
    "knowledge_enrichment",
    "knowledge_embedding",
    "gap_evaluation",
    "gap_synthesis",
    "content_translation",
    "seo_recommendation",
    "test",
]

# Non-professionalize boundaries required
REQUIRED_BOUNDARIES = ["gemini", "ollama", "m2m100"]

# Secret-like pattern (same as metrics_schema.py)
_SECRET_LIKE = re.compile(
    r"(sk-[A-Za-z0-9]{10,})"
    r"|(ghp_[A-Za-z0-9]{10,})"
    r"|(AIzaSy[A-Za-z0-9_-]{10,})"
    r"|(Bearer\s+[A-Za-z0-9._-]{20,})"
    r"|([?&](api_key|token|key)=[^\s&]{8,})",
    re.IGNORECASE,
)


@dataclass
class TaxonomyFailure:
    code: str
    message: str
    field: str = ""


@dataclass
class TaxonomyCheckResult:
    passed: bool = True
    failures: list[TaxonomyFailure] = field(default_factory=list)
    checked_sections: list[str] = field(default_factory=list)


def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore[import]
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # Minimal fallback: just enough to detect missing keys
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        result: dict = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" in stripped and not stripped.startswith("-"):
                k, _, v = stripped.partition(":")
                k = k.strip().strip('"')
                v = v.strip().strip('"')
                if k and not result.get(k):
                    result[k] = v or True
        return result


def _scan_for_secrets(data: object, path: str = "") -> list[tuple[str, str]]:
    """Recursively scan taxonomy values for secret-like strings."""
    findings: list[tuple[str, str]] = []
    if isinstance(data, str):
        if _SECRET_LIKE.search(data):
            findings.append((path, "[secret-like value detected — not printed]"))
    elif isinstance(data, dict):
        for k, v in data.items():
            findings.extend(_scan_for_secrets(v, f"{path}.{k}" if path else k))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            findings.extend(_scan_for_secrets(item, f"{path}[{i}]"))
    return findings


def run_check(taxonomy_path: Path) -> TaxonomyCheckResult:
    result = TaxonomyCheckResult()

    if not taxonomy_path.exists():
        result.passed = False
        result.failures.append(TaxonomyFailure(
            code="TAXONOMY_MISSING",
            message=f"Taxonomy file not found: {taxonomy_path}",
            field="file",
        ))
        return result

    data = _load_yaml(taxonomy_path)

    # 1. Required sections
    for section in REQUIRED_SECTIONS:
        result.checked_sections.append(section)
        if section not in data:
            result.passed = False
            result.failures.append(TaxonomyFailure(
                code="MISSING_SECTION",
                message=f"Required section missing: {section}",
                field=section,
            ))

    # 2. agent_owner
    owner = data.get("agent_owner", "")
    if owner != REQUIRED_AGENT_OWNER:
        result.passed = False
        result.failures.append(TaxonomyFailure(
            code="WRONG_AGENT_OWNER",
            message=f"agent_owner must be '{REQUIRED_AGENT_OWNER}', got: '{owner}'",
            field="agent_owner",
        ))

    # 3. Required agents
    agents = data.get("agents", {}) or {}
    for agent_id in REQUIRED_AGENTS:
        if agent_id not in agents:
            result.passed = False
            result.failures.append(TaxonomyFailure(
                code="MISSING_AGENT",
                message=f"Required agent missing: {agent_id}",
                field=f"agents.{agent_id}",
            ))

    # 4. Required job types
    job_types = data.get("job_types", {}) or {}
    for jt in REQUIRED_JOB_TYPES:
        if jt not in job_types:
            result.passed = False
            result.failures.append(TaxonomyFailure(
                code="MISSING_JOB_TYPE",
                message=f"Required job type missing: {jt}",
                field=f"job_types.{jt}",
            ))

    # 5. Posting modes
    pm = data.get("posting_modes", {}) or {}
    if pm.get("dry_run_default") is not True:
        result.passed = False
        result.failures.append(TaxonomyFailure(
            code="DRY_RUN_NOT_DEFAULT",
            message="posting_modes.dry_run_default must be true",
            field="posting_modes.dry_run_default",
        ))
    if pm.get("test_mode_job_type") != "test":
        result.passed = False
        result.failures.append(TaxonomyFailure(
            code="TEST_JOB_TYPE_WRONG",
            message="posting_modes.test_mode_job_type must be 'test'",
            field="posting_modes.test_mode_job_type",
        ))
    item_prefix = pm.get("test_mode_item_prefix", "")
    if "[TEST]" not in str(item_prefix):
        result.passed = False
        result.failures.append(TaxonomyFailure(
            code="TEST_PREFIX_WRONG",
            message="posting_modes.test_mode_item_prefix must contain '[TEST]'",
            field="posting_modes.test_mode_item_prefix",
        ))
    max_rows = pm.get("max_test_rows_per_sprint", 0)
    hard_limit = pm.get("hard_test_row_limit", 0)
    try:
        if int(max_rows) > 2:
            result.passed = False
            result.failures.append(TaxonomyFailure(
                code="MAX_TEST_ROWS_TOO_HIGH",
                message=f"max_test_rows_per_sprint must be ≤ 2, got {max_rows}",
                field="posting_modes.max_test_rows_per_sprint",
            ))
        if int(hard_limit) > 3:
            result.passed = False
            result.failures.append(TaxonomyFailure(
                code="HARD_LIMIT_TOO_HIGH",
                message=f"hard_test_row_limit must be ≤ 3, got {hard_limit}",
                field="posting_modes.hard_test_row_limit",
            ))
    except (TypeError, ValueError):
        pass

    # 6. Non-professionalize boundaries
    boundaries = data.get("non_professionalize_boundaries", {}) or {}
    for b in REQUIRED_BOUNDARIES:
        if b not in boundaries:
            result.passed = False
            result.failures.append(TaxonomyFailure(
                code="MISSING_BOUNDARY",
                message=f"Required non-professionalize boundary missing: {b}",
                field=f"non_professionalize_boundaries.{b}",
            ))
        else:
            bdata = boundaries[b] or {}
            if not bdata.get("excluded_from_token_usage") or not bdata.get("excluded_from_api_calls_count"):
                result.passed = False
                result.failures.append(TaxonomyFailure(
                    code="BOUNDARY_NOT_EXCLUDED",
                    message=f"Boundary '{b}' must have excluded_from_token_usage=true and "
                            "excluded_from_api_calls_count=true",
                    field=f"non_professionalize_boundaries.{b}",
                ))

    # 7. Secret scan on all taxonomy values
    secret_findings = _scan_for_secrets(data)
    for path_key, _ in secret_findings:
        result.passed = False
        result.failures.append(TaxonomyFailure(
            code="SECRET_IN_TAXONOMY",
            message=f"Secret-like value detected at taxonomy path: {path_key} [value not printed]",
            field=path_key,
        ))

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate metrics taxonomy YAML for required structure and values.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--taxonomy", default=str(_DEFAULT_TAXONOMY), help="Taxonomy YAML path")
    parser.add_argument("--json-output", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    result = run_check(Path(args.taxonomy))

    if args.json_output:
        print(json.dumps({
            "passed": result.passed,
            "failure_count": len(result.failures),
            "failures": [{"code": f.code, "message": f.message, "field": f.field}
                         for f in result.failures],
        }, indent=2))
    else:
        if result.failures:
            print(f"FAIL — {len(result.failures)} taxonomy validation failure(s):")
            for f in result.failures:
                print(f"  [{f.code}] {f.field}: {f.message}")
        else:
            print(f"PASS — taxonomy valid: {len(result.checked_sections)} sections checked, "
                  "all required agents/job_types/boundaries present")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
