#!/usr/bin/env python3
"""Build Phase 5 target-state design artifacts from Phase 4 parity data."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


WORKSTREAMS = {
    "missing skill": {
        "id": "WS-01",
        "name": "Capability Registration And Command Surface",
        "target": "Add first-class standalone skills or explicit compatibility aliases, with registry entries, provider mirrors, docs, examples, and tests.",
    },
    "missing registration": {
        "id": "WS-01",
        "name": "Capability Registration And Command Surface",
        "target": "Register surfaced behavior in `skills/registry.yaml` or document an intentional alias/shim decision.",
    },
    "hidden feature not surfaced cleanly": {
        "id": "WS-01",
        "name": "Capability Registration And Command Surface",
        "target": "Expose user-facing aliases for practical outcomes that users previously invoked indirectly.",
    },
    "missing dependency": {
        "id": "WS-02",
        "name": "Dependency Port Or Adapter Layer",
        "target": "Port required helper scripts/modules when they are skill-system behavior; otherwise add compatibility wrappers to clean standalone modules or document external content-repo responsibility.",
    },
    "naming/structure mismatch": {
        "id": "WS-03",
        "name": "Compatibility Shims For Reorganized Code",
        "target": "Keep cleaner standalone organization, but add thin legacy-path wrappers or update skill docs/registry to point to the new canonical path.",
    },
    "missing helper utility": {
        "id": "WS-04",
        "name": "Prompt-Orchestration Entrypoint Coverage",
        "target": "For prompt-only skills, define an explicit execution contract and add smoke tests or wrapper entrypoints for representative outcomes.",
    },
    "missing config support": {
        "id": "WS-05",
        "name": "External Content Repo Adapter",
        "target": "Replace website-local assumptions with a documented `CONTENT_REPO_PATH`/config adapter, clone-cache resolver, output-root override, and metrics dry-run policy.",
    },
    "behavioral mismatch": {
        "id": "WS-06",
        "name": "Behavioral Contract Reconciliation",
        "target": "Inspect the aspose.org and standalone skill contracts, preserve required user outcomes, keep standalone wording only where behavior is equivalent or better, and add regression tests.",
    },
}

DEFAULT_WORKSTREAM = {
    "id": "WS-07",
    "name": "Verification-Only Classification",
    "target": "No migration until a dry-run or fixture-based verification proves parity or reveals a concrete defect.",
}


def target_for_categories(categories: list[str]) -> list[dict[str, str]]:
    if not categories:
        return [DEFAULT_WORKSTREAM]
    seen = set()
    result = []
    for category in categories:
        item = WORKSTREAMS.get(category, DEFAULT_WORKSTREAM)
        if item["id"] not in seen:
            result.append(item)
            seen.add(item["id"])
    return result


def primary_design(capability: str, categories: list[str], status: str) -> str:
    if capability == "content-enrich":
        return "Create a standalone `content-enrich` skill backed by the enrichment pipeline if the feature remains current; otherwise add a documented deprecation/redirect to the cleaner evidence or gap pipeline after operator approval."
    if capability == "seo-review":
        return "Create a standalone governance-only/Claude utility skill only if SEO review is still required; keep it separate from evidence-grounded content generation and mark it non-content-writing by default."
    if capability == "translate":
        return "Add a `/translate` compatibility dispatcher that routes to `translate-page` or `translate-batch` without duplicating translation logic."
    if status == "implemented but not verified":
        return "Keep current implementation; add dry-run and registry/discoverability verification before claiming parity."
    if "missing config support" in categories:
        return "Normalize this skill through the external content repo adapter so it works with standalone paths and never assumes in-repo Hugo content."
    if "missing dependency" in categories:
        return "Triage referenced dependencies: port real skill behavior, replace site-only paths with adapters, and add wrappers for legacy references where users rely on them."
    if "behavioral mismatch" in categories:
        return "Run contract reconciliation against the aspose.org skill, then update standalone docs/scripts/tests to preserve practical behavior with cleaner structure."
    if "naming/structure mismatch" in categories:
        return "Keep the cleaner standalone path and add compatibility mapping or update all references to the canonical standalone location."
    return "Verify with fixture/dry-run execution before declaring parity."


def main() -> int:
    matrix = json.loads(Path("docs/parity/parity-matrix-phase4.json").read_text(encoding="utf-8"))
    rows = matrix["rows"]
    designs = []
    by_ws: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        categories = row["gap_categories"]
        workstreams = target_for_categories(categories)
        for ws in workstreams:
            by_ws[ws["id"]].append(row["canonical_name"])
        designs.append(
            {
                "canonical_name": row["canonical_name"],
                "status": row["status"],
                "gap_categories": categories,
                "workstreams": workstreams,
                "target_design": primary_design(row["canonical_name"], categories, row["status"]),
            }
        )

    standalone_only = matrix["standalone_only_capabilities"]
    output = {
        "schema_version": 1,
        "phase": "Phase 5 - target architecture for clean migration",
        "architecture_principles": [
            "Preserve aspose.org practical behavior, not legacy layout.",
            "Keep standalone repo cleaner through adapters, registries, tests, and compatibility shims.",
            "Do not couple standalone execution to in-repo Hugo content; use external content-root and redirected output-root contracts.",
            "Add wrappers only when needed for compatibility or discoverability.",
            "Do not write to aspose.org/content during verification.",
        ],
        "workstreams": list({item["id"]: item for item in WORKSTREAMS.values()}.values()) + [DEFAULT_WORKSTREAM],
        "capability_designs": designs,
        "standalone_only_preservation": [
            {
                "canonical_name": item["canonical_name"],
                "target_design": "Preserve as standalone improvement unless Phase 6 taskcard review proves it obsolete. Add regression tests so migration of aspose.org parity does not remove or weaken it.",
            }
            for item in standalone_only
        ],
        "workstream_capability_counts": {key: len(value) for key, value in sorted(by_ws.items())},
    }
    Path("docs/parity/target-state-migration-design.json").write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")

    status_counts = Counter(item["status"] for item in designs)
    md = []
    md.append("# Target-State Migration Design - Phase 5\n\n")
    md.append("Date: 2026-05-13\n\n")
    md.append("## Phase Goal\n\nDesign how each missing, partial, weakened, undocumented, and unverified capability should be added or reconciled in `foss-launcher-skills-gitlab` without blindly copying `aspose.org` structure.\n\n")
    md.append("## Inputs\n\n")
    md.append("- `docs/parity/parity-matrix-phase4.json`\n")
    md.append("- `docs/parity/gap-report-phase4.md`\n")
    md.append("- Phase 2 and Phase 3 inventory evidence\n\n")
    md.append("## Outputs\n\n")
    md.append("- `docs/parity/target-state-migration-design.json`\n")
    md.append("- This design document\n\n")
    md.append("## Exit Criteria Status\n\nMet. Every Phase 4 aspose.org capability row is mapped to one or more target workstreams and a target design decision. Standalone-only capabilities are explicitly preserved for non-regression review.\n\n")
    md.append("## Architecture Principles\n\n")
    for principle in output["architecture_principles"]:
        md.append(f"- {principle}\n")
    md.append("\n## Target Workstreams\n\n")
    for ws in output["workstreams"]:
        md.append(f"### {ws['id']} - {ws['name']}\n\n{ws['target']}\n\n")
    md.append("## Status Counts From Phase 4\n\n")
    for status, count in sorted(status_counts.items()):
        md.append(f"- `{status}`: {count}\n")
    md.append("\n## Capability Target Design Matrix\n\n")
    md.append("| Capability | Phase 4 Status | Gap Categories | Workstreams | Target Design |\n")
    md.append("|---|---|---|---|---|\n")
    for item in designs:
        cats = ", ".join(item["gap_categories"]) if item["gap_categories"] else "-"
        workstreams = ", ".join(ws["id"] for ws in item["workstreams"])
        design = item["target_design"].replace("|", "\\|")
        md.append(f"| `{item['canonical_name']}` | {item['status']} | {cats} | {workstreams} | {design} |\n")
    md.append("\n## Standalone-Only Improvements To Preserve\n\n")
    for item in output["standalone_only_preservation"]:
        md.append(f"- `{item['canonical_name']}`: {item['target_design']}\n")
    md.append("\n## Migration Quality Rules\n\n")
    md.append("- Port behavior into clean standalone modules before adding compatibility wrappers.\n")
    md.append("- Use wrappers for legacy path compatibility only when a skill, doc, or user workflow still references that path.\n")
    md.append("- Treat `CONTENT_REPO_PATH`, output-root overrides, clone-cache resolution, and metrics dry-run behavior as shared adapter contracts.\n")
    md.append("- Any content-writing workflow must have dry-run or redirected-output verification before it is marked parity-proven.\n")
    md.append("- Website-only Hugo/theme/layout concerns should be represented as external-content-repo contracts, not copied as hard standalone dependencies.\n")
    Path("docs/parity/target-state-migration-design.md").write_text("".join(md), encoding="utf-8")

    print(json.dumps({"capability_designs": len(designs), "standalone_only": len(standalone_only), "workstream_counts": output["workstream_capability_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
