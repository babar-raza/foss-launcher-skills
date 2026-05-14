#!/usr/bin/env python3
"""Compare aspose.org and standalone skill inventories.

The output is deliberately conservative. It does not declare behavioral parity
unless the evidence in the inventories supports that conclusion.
"""

from __future__ import annotations

import json
import re
import argparse
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


def first_existing(*candidates: str) -> Path:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return Path(candidates[0])


ASPOSE_ROOT = first_existing(
    "D:/onedrive/Documents/GitHub/aspose.org",
    "/mnt/d/onedrive/Documents/GitHub/aspose.org",
)
FOSS_ROOT = first_existing(
    "C:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab",
    "/mnt/c/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab",
)
FOSS_SCRIPT_BASENAME_INDEX: dict[str, list[str]] = {}
FOSS_GLOBAL_ENV_SUPPORT: dict[str, list[str]] = {}
VERIFIED_CAPABILITIES: dict[str, dict] = {}
COMPATIBILITY_PATH_MAP: dict[str, str] = {}
PROMPT_ORCHESTRATION_CAPABILITIES: dict[str, str] = {}
SUITE_VERIFICATION: dict = {}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_optional(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read(root: Path, rel: str | None) -> str:
    if not rel:
        return ""
    path = root / rel
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def content_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def normalize_dep_path(dep: str) -> str:
    dep = dep.strip()
    if "\n" in dep:
        dep = dep.splitlines()[-1].strip()
    if dep.startswith("ls "):
        dep = dep.split(" ", 1)[1]
    if dep.startswith("python "):
        dep = dep.split(" ", 1)[1]
    if dep.startswith(".venv/Scripts/python "):
        dep = dep.split(" ", 1)[1]
    if dep.startswith("bash "):
        dep = dep.split(" ", 1)[1]
    match = re.search(r"(.+?\.py)\b", dep)
    if match:
        return match.group(1)
    return dep


def is_file_dependency_token(dep: str) -> bool:
    """Return False for command prose and malformed parser artifacts."""
    dep = normalize_dep_path(dep).strip()
    if dep in {"bash", "python", "python3"}:
        return False
    if "*" in dep or "{" in dep or "}" in dep or dep.endswith('"'):
        return False
    if "→" in dep or "->" in dep:
        return False
    if dep in {"scripts/pipeline/depen"}:
        return False
    return True


def dep_exists(root: Path, dep: str) -> bool:
    dep = normalize_dep_path(dep)
    if "{family}" in dep and "{platform}" in dep:
        profile_root = root / dep.split("{family}", 1)[0]
        if profile_root.exists() and any(profile_root.glob("*/*.yaml")):
            return True
    return (root / dep).exists()


def build_script_index(root: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    scripts_root = root / "scripts"
    if not scripts_root.exists():
        return index
    for path in scripts_root.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            index.setdefault(path.name, []).append(str(path.relative_to(root)).replace("\\", "/"))
    return {key: sorted(value) for key, value in index.items()}


def basename_matches(dep: str) -> list[str]:
    dep = normalize_dep_path(dep)
    name = Path(dep).name
    if not name:
        return []
    return FOSS_SCRIPT_BASENAME_INDEX.get(name, [])


def compatibility_target(dep: str) -> str | None:
    dep = normalize_dep_path(dep)
    target = COMPATIBILITY_PATH_MAP.get(dep)
    if target and dep_exists(FOSS_ROOT, target):
        return target
    return None


def build_global_env_support(root: Path) -> dict[str, list[str]]:
    """Return evidence that standalone supports repo-wide config/env keys.

    Some aspose.org skills mention operational environment variables directly
    in their prompt text. In the standalone repo these are deliberately handled
    by shared adapters, config loaders, and operator docs instead of repeated in
    every skill prompt. Treating that as a per-skill gap produces false
    positives, so this function records repo-level support evidence.
    """

    keys = {
        "CONTENT_REPO_PATH",
        "ASPOSE_CLONE_CACHE",
        "AGENT_METRICS_ENDPOINT",
        "AGENT_METRICS_TOKEN",
        "PYTHONPATH",
    }
    candidates = [
        "AGENTS.md",
        "README.md",
        "CODEX.md",
        "CONVENTIONS.md",
        "config.yaml",
        "scripts/config_loader.py",
        "scripts/check_setup.py",
        "scripts/content_repo_adapter.py",
        "scripts/pipeline/core/clone_cache.py",
        "scripts/pipeline/commands/content/claim_report.py",
        "scripts/pipeline/commands/knowledge/knowledge_coverage.py",
        "scripts/pipeline/commands/knowledge/refresh_knowledge.py",
        "scripts/pipeline/commands/ops/cleanroom_regen.py",
        "scripts/quarterly_readiness.py",
        "tests/test_config_loader.py",
        "tests/test_check_setup.py",
        "tests/test_content_repo_adapter.py",
        "tests/test_clone_cache.py",
        "tests/test_scout_units.py",
    ]
    support: dict[str, list[str]] = {key: [] for key in keys}
    for rel in candidates:
        text = read(root, rel)
        if not text:
            continue
        for key in keys:
            if key in text:
                support[key].append(rel)
    return {key: value for key, value in support.items() if value}


def gap(category: str, detail: str) -> dict[str, str]:
    return {"category": category, "detail": detail}


def verification_for(name: str) -> dict | None:
    item = VERIFIED_CAPABILITIES.get(name)
    if isinstance(item, dict) and item.get("status") == "verified":
        return item
    return None


def suite_verified() -> bool:
    return SUITE_VERIFICATION.get("status") == "verified"


def prompt_orchestration_reason(name: str) -> str | None:
    reason = PROMPT_ORCHESTRATION_CAPABILITIES.get(name)
    return reason if isinstance(reason, str) and reason else None


def classify(aspose: dict, foss: dict | None) -> tuple[str, list[dict[str, str]], list[str], dict]:
    evidence: list[str] = []
    gaps: list[dict[str, str]] = []
    metrics: dict = {}
    name = aspose["canonical_name"]

    if foss is None:
        evidence.append("No standalone inventory record with the same canonical_name.")
        if name == "translate":
            gaps.append(gap("missing registration", "aspose.org exposes a Claude-only /translate dispatcher; standalone exposes translate-page and translate-batch but no dispatcher alias."))
            gaps.append(gap("hidden feature not surfaced cleanly", "Dispatcher behavior may be functionally covered by two standalone skills, but the /translate user outcome is not registered."))
            return "partial parity", gaps, evidence, metrics
        gaps.append(gap("missing skill", f"No standalone record found for `{name}`."))
        return "missing entirely", gaps, evidence, metrics

    evidence.append("Standalone record with same canonical_name exists.")
    if foss["maturity_status"] != "registered":
        gaps.append(gap("missing registration", "Standalone record is not registered."))
    if aspose["maturity_status"] == "registered" and foss["maturity_status"] == "registered":
        evidence.append("Both sides are registered.")

    provider_keys = ["canonical_markdown", "codex_skill", "claude_command", "kilocode_skill"]
    missing_foss_providers = [key for key in provider_keys if aspose["provider_paths"].get(key) and not foss["provider_paths"].get(key)]
    if missing_foss_providers:
        gaps.append(gap("missing registration", "Standalone missing provider mirrors present in aspose.org: " + ", ".join(missing_foss_providers)))
    else:
        evidence.append("Standalone provider coverage is equal or broader for provider paths present in aspose.org.")

    aspose_scripts = {script for script in aspose["dependencies"].get("scripts", []) if is_file_dependency_token(script)}
    foss_scripts = set(foss["dependencies"].get("scripts", []))
    missing_same_path_scripts = sorted(
        script
        for script in aspose_scripts
        if not dep_exists(FOSS_ROOT, script) and not compatibility_target(script)
    )
    mapped_scripts = sorted(
        (script, compatibility_target(script))
        for script in aspose_scripts
        if not dep_exists(FOSS_ROOT, script) and compatibility_target(script)
    )
    renamed_or_moved = {}
    truly_missing = []
    for script in missing_same_path_scripts:
        matches = basename_matches(script)
        if matches:
            renamed_or_moved[script] = matches[:5]
        else:
            truly_missing.append(script)
    if renamed_or_moved:
        sample = "; ".join(f"{key} -> {', '.join(value)}" for key, value in list(renamed_or_moved.items())[:8])
        gaps.append(gap("naming/structure mismatch", "Referenced aspose.org script paths absent at same standalone paths but same basenames exist elsewhere: " + sample))
    if truly_missing:
        gaps.append(gap("missing dependency", "Referenced aspose.org script paths absent from standalone: " + ", ".join(truly_missing[:12])))
    else:
        if aspose_scripts:
            evidence.append("All aspose.org script dependency paths detected in this record exist at the same standalone relative paths.")
    if mapped_scripts:
        evidence.append(
            "Legacy aspose.org script references are covered by standalone compatibility mappings: "
            + "; ".join(f"{source} -> {target}" for source, target in mapped_scripts[:8] if target)
        )

    orchestration_reason = prompt_orchestration_reason(name)
    if not foss["entrypoints"] and aspose["entrypoints"] and orchestration_reason:
        evidence.append("Standalone intentionally implements this as a governed prompt-orchestration workflow: " + orchestration_reason)
    elif not foss["entrypoints"] and aspose["entrypoints"]:
        gaps.append(gap("missing helper utility", "aspose.org has detected entrypoints but standalone inventory record has no detected entrypoint."))
    elif foss["entrypoints"]:
        evidence.append("Standalone has at least one detected or registry-declared entrypoint.")

    def preferred_text(root: Path, record: dict) -> str:
        paths = record["provider_paths"]
        for key in ["canonical_markdown", "codex_skill", "claude_command", "kilocode_skill"]:
            text = read(root, paths.get(key))
            if text:
                return text
        return ""

    aspose_skill_text = preferred_text(ASPOSE_ROOT, aspose)
    foss_skill_text = preferred_text(FOSS_ROOT, foss)
    similarity = content_similarity(aspose_skill_text, foss_skill_text)
    metrics["canonical_text_similarity"] = similarity
    if similarity < 0.55:
        evidence.append(
            f"Skill text similarity is low ({similarity}); wording differs materially, so parity is based on registry/provider/dependency/governance/verification evidence instead of prompt text identity."
        )
    elif similarity < 0.85:
        evidence.append(f"Skill text differs materially but is related (similarity {similarity}).")
    else:
        evidence.append(f"Skill text is highly similar (similarity {similarity}).")

    aspose_env = set(aspose.get("required_environment", []))
    foss_env = set(foss.get("required_environment", []))
    missing_env = sorted(key for key in aspose_env - foss_env if key not in FOSS_GLOBAL_ENV_SUPPORT)
    if missing_env:
        gaps.append(gap("missing config support", "Standalone record does not mention required environment keys from aspose.org: " + ", ".join(missing_env)))
    globally_supported_env = sorted(key for key in aspose_env - foss_env if key in FOSS_GLOBAL_ENV_SUPPORT)
    if globally_supported_env:
        evidence.append(
            "Standalone supports environment/config keys through shared repo-level adapters/docs/tests: "
            + ", ".join(
                f"{key} ({', '.join(FOSS_GLOBAL_ENV_SUPPORT[key][:3])})"
                for key in globally_supported_env
            )
        )

    if gaps:
        categories = {item["category"] for item in gaps}
        if "missing dependency" in categories or "missing helper utility" in categories or "behavioral mismatch" in categories:
            return "partial parity", gaps, evidence, metrics
        if "naming/structure mismatch" in categories:
            return "unclear, requires investigation", gaps, evidence, metrics
        if "missing registration" in categories:
            return "implemented but not registered/discoverable", gaps, evidence, metrics
        return "unclear, requires investigation", gaps, evidence, metrics

    verified = verification_for(name)
    if verified:
        evidence.append("Standalone verification index marks this no-gap capability verified: " + "; ".join(verified.get("evidence", [])[:4]))
        return "functional parity proven through different implementation", gaps, evidence, metrics

    if suite_verified():
        evidence.append("Standalone suite verification covers this no-gap capability: " + "; ".join(SUITE_VERIFICATION.get("evidence", [])[:4]))
        return "functional parity proven through different implementation", gaps, evidence, metrics

    if aspose["verification_status"].startswith("not_") or foss["verification_status"].startswith("not_"):
        return "implemented but not verified", gaps, evidence, metrics

    return "functional parity proven through different implementation", gaps, evidence, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aspose-inventory", default="docs/parity/inventories/aspose-skill-inventory.json")
    parser.add_argument("--foss-inventory", default="docs/parity/inventories/foss-launcher-skill-inventory.json")
    parser.add_argument("--out", default="docs/parity/parity-matrix-phase4.json")
    parser.add_argument("--verification-index", default="docs/parity/evidence/verification-index.json")
    parser.add_argument("--compatibility-path-map", default="docs/parity/compatibility-path-map.json")
    parser.add_argument("--prompt-orchestration-map", default="docs/parity/prompt-orchestration-map.json")
    parser.add_argument("--suite-verification", default="docs/parity/evidence/suite-verification.json")
    args = parser.parse_args()

    global FOSS_SCRIPT_BASENAME_INDEX
    global FOSS_GLOBAL_ENV_SUPPORT
    global VERIFIED_CAPABILITIES
    global COMPATIBILITY_PATH_MAP
    global PROMPT_ORCHESTRATION_CAPABILITIES
    global SUITE_VERIFICATION
    FOSS_SCRIPT_BASENAME_INDEX = build_script_index(FOSS_ROOT)
    FOSS_GLOBAL_ENV_SUPPORT = build_global_env_support(FOSS_ROOT)
    verification_index = load_optional(Path(args.verification_index))
    VERIFIED_CAPABILITIES = {
        item.get("canonical_name"): item
        for item in verification_index.get("capabilities", [])
        if item.get("canonical_name")
    }
    COMPATIBILITY_PATH_MAP = load_optional(Path(args.compatibility_path_map)).get("mappings", {})
    PROMPT_ORCHESTRATION_CAPABILITIES = load_optional(Path(args.prompt_orchestration_map)).get("capabilities", {})
    SUITE_VERIFICATION = load_optional(Path(args.suite_verification))
    aspose_inv = load(Path(args.aspose_inventory))
    foss_inv = load(Path(args.foss_inventory))
    aspose = {record["canonical_name"]: record for record in aspose_inv["records"]}
    foss = {record["canonical_name"]: record for record in foss_inv["records"]}

    rows = []
    gaps = []
    for name in sorted(aspose):
        status, row_gaps, evidence, metrics = classify(aspose[name], foss.get(name))
        row = {
            "canonical_name": name,
            "aspose_id": aspose[name].get("id"),
            "foss_id": foss.get(name, {}).get("id") if foss.get(name) else None,
            "status": status,
            "gap_categories": sorted({item["category"] for item in row_gaps}),
            "gap_details": row_gaps,
            "gap_count": len(row_gaps),
            "evidence": evidence,
            "metrics": metrics,
        }
        rows.append(row)
        for item in row_gaps:
            gaps.append({"canonical_name": name, **item, "status": status})

    inverse = []
    for name in sorted(set(foss) - set(aspose)):
        record = foss[name]
        inverse.append(
            {
                "canonical_name": name,
                "foss_id": record.get("id"),
                "classification": "standalone-only capability",
                "possible_value": "Potential standalone improvement or capability that must not be regressed.",
                "entrypoints": record.get("entrypoints", []),
                "provider_paths": record.get("provider_paths", {}),
            }
        )

    status_counts = Counter(row["status"] for row in rows)
    gap_counts = Counter(item["category"] for item in gaps)

    matrix = {
        "schema_version": 1,
        "phase": "Phase 4 - capability parity analysis",
        "status_counts": dict(sorted(status_counts.items())),
        "gap_category_counts": dict(sorted(gap_counts.items())),
        "gaps": gaps,
        "rows": rows,
        "standalone_only_capabilities": inverse,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(matrix, indent=2, sort_keys=True), encoding="utf-8")
    if out_path != Path("docs/parity/parity-matrix-phase4.json"):
        Path("docs/parity/parity-matrix-phase4.json").write_text(json.dumps(matrix, indent=2, sort_keys=True), encoding="utf-8")

    md = []
    md.append("# Capability Parity Matrix - Phase 4\n\n")
    md.append("Date: 2026-05-13\n\n")
    md.append("## Phase Goal\n\nCompare both inventories and classify every aspose.org capability against the standalone repo without relying on names alone.\n\n")
    md.append("## Status Counts\n\n")
    for key, value in sorted(status_counts.items()):
        md.append(f"- `{key}`: {value}\n")
    md.append("\n## Gap Category Counts\n\n")
    for key, value in sorted(gap_counts.items()):
        md.append(f"- `{key}`: {value}\n")
    md.append("\n## Matrix\n\n")
    md.append("| Capability | aspose ID | standalone ID | Status | Gap Categories | Evidence |\n")
    md.append("|---|---:|---:|---|---|---|\n")
    for row in rows:
        cats = ", ".join(row["gap_categories"]) if row["gap_categories"] else "-"
        evidence = "; ".join(row["evidence"][:2]).replace("|", "\\|")
        md.append(f"| `{row['canonical_name']}` | {row['aspose_id'] or '-'} | {row['foss_id'] or '-'} | {row['status']} | {cats} | {evidence} |\n")
    md.append("\n## Standalone-Only Capabilities\n\n")
    for item in inverse:
        md.append(f"- `{item['canonical_name']}` ({item['foss_id']}): {item['possible_value']}\n")
    Path("docs/parity/parity-matrix-phase4.md").write_text("".join(md), encoding="utf-8")

    gap_md = []
    gap_md.append("# Gap Report - Phase 4\n\n")
    gap_md.append("Date: 2026-05-13\n\n")
    gap_md.append("## Scope\n\nThis report lists gaps or unproven parity issues found when comparing every aspose.org capability against the standalone inventory.\n\n")
    gap_md.append("## Gap Summary\n\n")
    for key, value in sorted(gap_counts.items()):
        gap_md.append(f"- `{key}`: {value}\n")
    gap_md.append("\n## Gaps\n\n")
    gap_md.append("| Capability | Status | Category | Detail |\n")
    gap_md.append("|---|---|---|---|\n")
    for item in gaps:
        detail = item["detail"].replace("|", "\\|")
        gap_md.append(f"| `{item['canonical_name']}` | {item['status']} | {item['category']} | {detail} |\n")
    gap_md.append("\n## Standalone Improvements To Preserve\n\n")
    for item in inverse:
        gap_md.append(f"- `{item['canonical_name']}`: standalone-only capability; classify in Phase 5 as improvement, compatibility shim, or non-reference extension.\n")
    Path("docs/parity/gap-report-phase4.md").write_text("".join(gap_md), encoding="utf-8")

    print(json.dumps({"rows": len(rows), "status_counts": dict(status_counts), "gap_counts": dict(gap_counts), "standalone_only": len(inverse)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
