#!/usr/bin/env python3
"""Generate Phase 6 executable taskcards from the target-state design."""

from __future__ import annotations

import json
import re
from pathlib import Path


TASKCARD_ROOT = Path("docs/parity/taskcards")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def write_card(card: dict) -> None:
    path = TASKCARD_ROOT / f"{card['taskcard_id']}-{slugify(card['title'])}.md"
    lines = [
        f"# {card['taskcard_id']} - {card['title']}\n\n",
        f"## Purpose\n\n{card['purpose']}\n\n",
        f"## Exact Scope\n\n{card['exact_scope']}\n\n",
        "## Inputs\n\n",
    ]
    for item in card["inputs"]:
        lines.append(f"- `{item}`\n")
    lines.extend(["\n## Files/Areas Allowed To Change\n\n"])
    for item in card["allowed_to_change"]:
        lines.append(f"- `{item}`\n")
    lines.extend(["\n## Files/Areas Forbidden To Change\n\n"])
    for item in card["forbidden_to_change"]:
        lines.append(f"- `{item}`\n")
    lines.extend(["\n## Dependencies\n\n"])
    for item in card["dependencies"]:
        lines.append(f"- {item}\n")
    lines.extend(["\n## Implementation Steps\n\n"])
    for i, item in enumerate(card["implementation_steps"], 1):
        lines.append(f"{i}. {item}\n")
    lines.extend(["\n## Verification Steps\n\n"])
    for i, item in enumerate(card["verification_steps"], 1):
        lines.append(f"{i}. {item}\n")
    lines.extend(["\n## Expected Artifacts\n\n"])
    for item in card["expected_artifacts"]:
        lines.append(f"- `{item}`\n")
    lines.extend(
        [
            f"\n## Risk Notes\n\n{card['risk_notes']}\n\n",
            f"## Rollback Notes\n\n{card['rollback_notes']}\n\n",
            f"## Done Criteria\n\n{card['done_criteria']}\n",
        ]
    )
    path.write_text("".join(lines), encoding="utf-8")


def base_forbidden() -> list[str]:
    return [
        "D:/onedrive/Documents/GitHub/aspose.org/content/**",
        "D:/onedrive/Documents/GitHub/aspose.org/** unless explicitly read-only",
        "C:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab/.git/**",
        "Any production credentials, tokens, or metrics secrets",
    ]


def make_foundation_cards() -> list[dict]:
    return [
        {
            "taskcard_id": "TC-P6-0001",
            "title": "Freeze Current Parity Inputs",
            "purpose": "Create a stable baseline of Phase 1-5 artifacts before migration work starts.",
            "exact_scope": "Record checksums for inventories, parity matrix, gap report, and target design. Do not change capabilities.",
            "inputs": [
                "docs/parity/inventories/aspose-skill-inventory.json",
                "docs/parity/inventories/foss-launcher-skill-inventory.json",
                "docs/parity/parity-matrix-phase4.json",
                "docs/parity/target-state-migration-design.json",
            ],
            "allowed_to_change": ["docs/parity/evidence/**", "docs/parity/taskcards/**"],
            "forbidden_to_change": base_forbidden(),
            "dependencies": ["Phase 5 complete"],
            "implementation_steps": [
                "Compute SHA256 checksums for Phase 1-5 input artifacts.",
                "Write `docs/parity/evidence/phase6-baseline-checksums.txt`.",
                "Record current git status for `docs/parity/**` only.",
            ],
            "verification_steps": [
                "Recompute one checksum manually and confirm it matches the baseline file.",
                "Confirm no files under `aspose.org/content` changed.",
            ],
            "expected_artifacts": ["docs/parity/evidence/phase6-baseline-checksums.txt"],
            "risk_notes": "Low risk. This is read-only except for evidence output.",
            "rollback_notes": "Delete the generated checksum evidence file.",
            "done_criteria": "Baseline checksums exist and reference every Phase 1-5 input artifact.",
        },
        {
            "taskcard_id": "TC-P6-0002",
            "title": "Create External Content Repo Adapter Contract",
            "purpose": "Define the shared standalone contract for content root, clone cache, output root, dry-run mode, and metrics dry-run handling.",
            "exact_scope": "Design and document adapter behavior only; implementation is a later taskcard.",
            "inputs": ["docs/parity/target-state-migration-design.md", "config.yaml", "scripts/config_loader.py"],
            "allowed_to_change": ["docs/parity/design/**", "docs/parity/evidence/**"],
            "forbidden_to_change": base_forbidden(),
            "dependencies": ["TC-P6-0001"],
            "implementation_steps": [
                "Create `docs/parity/design/external-content-repo-adapter-contract.md`.",
                "Specify `CONTENT_REPO_PATH`, `content_root`, `output_root`, clone-cache resolution, and metrics dry-run behavior.",
                "Define fail-closed behavior for missing content root and forbidden `aspose.org/content` writes.",
            ],
            "verification_steps": [
                "Check the contract names every required config key.",
                "Check it includes a non-destructive verification section.",
            ],
            "expected_artifacts": ["docs/parity/design/external-content-repo-adapter-contract.md"],
            "risk_notes": "Medium risk if the contract overfits aspose.org. Keep it adapter-oriented.",
            "rollback_notes": "Revert only the contract document.",
            "done_criteria": "Adapter contract is explicit enough to implement and test.",
        },
        {
            "taskcard_id": "TC-P6-0003",
            "title": "Create Compatibility Shim Policy",
            "purpose": "Define when legacy aspose.org paths should get wrappers versus when skill docs should move to standalone canonical paths.",
            "exact_scope": "Policy and mapping format only; no shims implemented.",
            "inputs": ["docs/parity/gap-report-phase4.md", "docs/parity/target-state-migration-design.md"],
            "allowed_to_change": ["docs/parity/design/**", "docs/parity/evidence/**"],
            "forbidden_to_change": base_forbidden(),
            "dependencies": ["TC-P6-0001"],
            "implementation_steps": [
                "Create `docs/parity/design/compatibility-shim-policy.md`.",
                "Define wrapper eligibility, naming, deprecation notes, and test requirements.",
                "Define a mapping table schema for old path to new path.",
            ],
            "verification_steps": [
                "Confirm the policy prevents copying site-only coupling into standalone.",
                "Confirm every shim must have at least one test or smoke check.",
            ],
            "expected_artifacts": ["docs/parity/design/compatibility-shim-policy.md"],
            "risk_notes": "Medium risk if wrappers hide broken migrations. Require tests.",
            "rollback_notes": "Revert only the policy document.",
            "done_criteria": "Shim policy is ready to drive implementation taskcards.",
        },
        {
            "taskcard_id": "TC-P6-0004",
            "title": "Create Non-Destructive Verification Harness Design",
            "purpose": "Define the fixture, temporary worktree, redirected output, and no-write checks needed for Phase 8.",
            "exact_scope": "Verification design only; implementation follows later.",
            "inputs": ["docs/parity/target-state-migration-design.md", "tests/fixtures/**"],
            "allowed_to_change": ["docs/parity/verification/**", "docs/parity/evidence/**"],
            "forbidden_to_change": base_forbidden(),
            "dependencies": ["TC-P6-0001", "TC-P6-0002"],
            "implementation_steps": [
                "Create `docs/parity/verification/non-destructive-verification-harness.md`.",
                "Define inventory, registry, docs-to-code, config, helper dependency, dry-run, redirected output, and safety checks.",
                "Specify how to prove `aspose.org/content` remains untouched.",
            ],
            "verification_steps": [
                "Confirm the harness design covers every verification category requested by the operator.",
                "Confirm all proposed content writes target temp directories or fixture repos.",
            ],
            "expected_artifacts": ["docs/parity/verification/non-destructive-verification-harness.md"],
            "risk_notes": "High value because it controls migration safety.",
            "rollback_notes": "Revert only the verification design document.",
            "done_criteria": "Harness design is complete enough to decompose into Phase 8 tasks.",
        },
    ]


def make_capability_card(index: int, item: dict) -> dict:
    name = item["canonical_name"]
    workstreams = ", ".join(ws["id"] for ws in item["workstreams"])
    categories = ", ".join(item["gap_categories"]) or "verification-only"
    return {
        "taskcard_id": f"TC-P6-{index:04d}",
        "title": f"Reconcile {name} Capability",
        "purpose": f"Resolve Phase 4 parity status for `{name}` without weakening standalone maintainability.",
        "exact_scope": f"Inspect `{name}` in both inventories and implement or document the target design: {item['target_design']}",
        "inputs": [
            "docs/parity/inventories/aspose-skill-inventory.json",
            "docs/parity/inventories/foss-launcher-skill-inventory.json",
            "docs/parity/parity-matrix-phase4.json",
            "docs/parity/target-state-migration-design.json",
            f"skills/{name}.md",
            f".agents/skills/{name}/SKILL.md",
        ],
        "allowed_to_change": [
            f"skills/{name}.md",
            f".agents/skills/{name}/SKILL.md",
            f".claude/commands/{name}.md",
            f".kilocode/skills/{name}/SKILL.md",
            "skills/registry.yaml",
            "scripts/**",
            "tests/**",
            "docs/parity/evidence/**",
        ],
        "forbidden_to_change": base_forbidden(),
        "dependencies": ["TC-P6-0001", "TC-P6-0002 for config-related work", "TC-P6-0003 for shim-related work"],
        "implementation_steps": [
            f"Read the aspose.org and standalone records for `{name}` from the inventories.",
            f"Classify each gap category for `{name}` as true missing behavior, intentional standalone redesign, stale reference, or verification-only.",
            "If implementation is required, make the smallest additive change in standalone.",
            "Update registry/provider/docs references consistently.",
            "Add or update focused tests, fixtures, or smoke checks.",
            "Record evidence in `docs/parity/evidence/`.",
        ],
        "verification_steps": [
            "Run `python scripts/validate_skills.py`.",
            "Run targeted tests for changed scripts/docs where available.",
            "Run a dry-run or fixture-based command if this capability can write content.",
            "Confirm no writes target `D:/onedrive/Documents/GitHub/aspose.org/content/**`.",
        ],
        "expected_artifacts": [
            "Updated standalone skill/docs/scripts/tests as needed",
            f"docs/parity/evidence/{name}-parity-verification.md",
        ],
        "risk_notes": f"Phase 4 status: `{item['status']}`. Gap categories: {categories}. Workstreams: {workstreams}. Avoid copying website-only coupling.",
        "rollback_notes": "Revert the capability-specific files changed by this taskcard. Do not revert unrelated dirty worktree changes.",
        "done_criteria": f"`{name}` is reclassified as parity-proven, intentionally standalone-different with evidence, or blocked with a precise next action.",
    }


def make_standalone_preservation_card(index: int, item: dict) -> dict:
    name = item["canonical_name"]
    return {
        "taskcard_id": f"TC-P6-{index:04d}",
        "title": f"Preserve Standalone Improvement {name}",
        "purpose": f"Ensure standalone-only capability `{name}` is not regressed while importing aspose.org parity behavior.",
        "exact_scope": "Review docs, registry, tests, and user outcome for this standalone-only capability.",
        "inputs": ["docs/parity/target-state-migration-design.json", f"skills/{name}.md", f".agents/skills/{name}/SKILL.md"],
        "allowed_to_change": [f"skills/{name}.md", f".agents/skills/{name}/SKILL.md", f".claude/commands/{name}.md", f".kilocode/skills/{name}/SKILL.md", "tests/**", "docs/parity/evidence/**"],
        "forbidden_to_change": base_forbidden(),
        "dependencies": ["TC-P6-0001"],
        "implementation_steps": [
            f"Confirm `{name}` is registered and discoverable.",
            "Identify the practical user outcome this standalone-only skill provides.",
            "Add a preservation note or regression test if the outcome is valuable.",
            "If obsolete, document the deprecation recommendation for operator approval.",
        ],
        "verification_steps": [
            "Run `python scripts/validate_skills.py`.",
            "Run any existing tests covering the capability.",
            "Confirm no aspose.org content write is involved.",
        ],
        "expected_artifacts": [f"docs/parity/evidence/{name}-preservation-review.md"],
        "risk_notes": "Standalone-only does not mean optional; losing these may regress the standalone repo's intended improvements.",
        "rollback_notes": "Revert only files touched for this preservation review.",
        "done_criteria": f"`{name}` has a documented preserve, test, or deprecate decision.",
    }


def main() -> int:
    design = json.loads(Path("docs/parity/target-state-migration-design.json").read_text(encoding="utf-8"))
    TASKCARD_ROOT.mkdir(parents=True, exist_ok=True)

    cards = make_foundation_cards()
    next_index = 5
    for item in design["capability_designs"]:
        cards.append(make_capability_card(next_index, item))
        next_index += 1
    for item in design["standalone_only_preservation"]:
        cards.append(make_standalone_preservation_card(next_index, item))
        next_index += 1

    for card in cards:
        write_card(card)

    index_lines = [
        "# Phase 6 Taskcard Index\n\n",
        "Date: 2026-05-13\n\n",
        "## Scope\n\nExecutable taskcards generated from the Phase 5 target-state migration design.\n\n",
        f"Total taskcards: {len(cards)}\n\n",
        "| Taskcard | Title | Primary Purpose |\n",
        "|---|---|---|\n",
    ]
    for card in cards:
        filename = f"{card['taskcard_id']}-{slugify(card['title'])}.md"
        index_lines.append(f"| `{card['taskcard_id']}` | [{card['title']}](taskcards/{filename}) | {card['purpose']} |\n")
    Path("docs/parity/taskcard-index.md").write_text("".join(index_lines), encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "phase": "Phase 6 - taskcard decomposition",
        "taskcard_count": len(cards),
        "taskcards": [
            {
                "taskcard_id": card["taskcard_id"],
                "title": card["title"],
                "path": f"docs/parity/taskcards/{card['taskcard_id']}-{slugify(card['title'])}.md",
                "dependencies": card["dependencies"],
                "forbidden_to_change": card["forbidden_to_change"],
            }
            for card in cards
        ],
    }
    Path("docs/parity/taskcards/taskcard-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"taskcards": len(cards), "index": "docs/parity/taskcard-index.md", "manifest": "docs/parity/taskcards/taskcard-manifest.json"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
