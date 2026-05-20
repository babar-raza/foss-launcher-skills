#!/usr/bin/env python3
"""Phase 5+6: Build target-architecture.md and all taskcard files."""
import os
import re
from pathlib import Path
from collections import defaultdict

ASPOSE_ROOT = "D:/onedrive/Documents/GitHub/aspose.org"
FOSS_ROOT = "c:/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills-gitlab"
OUT_DIR = f"{FOSS_ROOT}/reports/parity"
TC_DIR = f"{OUT_DIR}/taskcards"

os.makedirs(TC_DIR, exist_ok=True)


# === Parse inventories (simple) ===
def parse_inventory(path):
    skills = {}
    current = None
    covering_tests = []
    in_tests = False
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- canonical_slug:"):
            if current:
                current["covering_tests"] = covering_tests
                skills[current["canonical_slug"]] = current
            current = {"canonical_slug": stripped.split(":", 1)[1].strip()}
            covering_tests = []
            in_tests = False
        elif current is not None:
            if stripped.startswith("covering_tests:"):
                val = stripped.split(":", 1)[1].strip()
                in_tests = val != "[]"
            elif in_tests and stripped.startswith("- "):
                covering_tests.append(stripped[2:])
            elif not stripped.startswith("- ") and ":" in stripped and not in_tests:
                key, val = stripped.split(":", 1)
                val = val.strip()
                if val == "null": val = None
                elif val == "true": val = True
                elif val == "false": val = False
                elif val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1].strip()
                    val = [int(x.strip()) for x in inner.split(",") if x.strip().isdigit()] if inner else []
                else:
                    try: val = float(val) if "." in val else int(val)
                    except: pass
                current[key.strip()] = val
    if current:
        current["covering_tests"] = covering_tests
        skills[current["canonical_slug"]] = current
    return skills


aspose_skills = parse_inventory(f"{OUT_DIR}/aspose-inventory.yaml")
foss_skills = parse_inventory(f"{OUT_DIR}/foss-inventory.yaml")

shared = set(aspose_skills.keys()) & set(foss_skills.keys())
aspose_only = set(aspose_skills.keys()) - set(foss_skills.keys())
foss_only = set(foss_skills.keys()) - set(aspose_skills.keys())

# Parse CI checks
ci_checks = []
with open(f"{OUT_DIR}/aspose-ci-checks-map.yaml", encoding="utf-8") as f:
    lines = f.readlines()
current_ci = None
for line in lines:
    s = line.strip()
    if s.startswith("- filename:"):
        if current_ci:
            ci_checks.append(current_ci)
        current_ci = {"filename": s.split(":", 1)[1].strip()}
    elif current_ci and ":" in s and not s.startswith("-"):
        k, v = s.split(":", 1)
        current_ci[k.strip()] = v.strip()
if current_ci:
    ci_checks.append(current_ci)

# Parse governance docs
gov_docs = []
with open(f"{OUT_DIR}/aspose-governance-map.yaml", encoding="utf-8") as f:
    lines = f.readlines()
current_gd = None
for line in lines:
    s = line.strip()
    if s.startswith("- filename:"):
        if current_gd:
            gov_docs.append(current_gd)
        current_gd = {"filename": s.split(":", 1)[1].strip()}
    elif current_gd and ":" in s and not s.startswith("-"):
        k, v = s.split(":", 1)
        current_gd[k.strip()] = v.strip()
if current_gd:
    gov_docs.append(current_gd)

print(f"CI checks: {len(ci_checks)}, Gov docs: {len(gov_docs)}")

# === TARGET ARCHITECTURE ===
arch_lines = [
    "# Target Architecture — foss-launcher Parity Migration",
    "",
    "**Generated**: 2026-05-15  **Agent**: A (Discovery)  **Plan**: PAR-012",
    "",
    "## Design Principles",
    "",
    "1. **Preserve behavior, redesign organization** — port semantics, not file structure",
    "2. **Rationalize CI checks** — group by domain rather than copying 63 individual scripts",
    "3. **Complement AGENTS.md** — new governance docs extend, not duplicate",
    "4. **Follow foss conventions** — new libraries follow existing scripts/pipeline/ patterns",
    "5. **Incremental + reversible** — every TC is one PR-equivalent unit, rollback defined",
    "",
    "## Gap Category Design Decisions",
    "",
    "### GC1: Missing CI Checks (59 checks → ~20 rationalized modules)",
    "",
    "| Domain | Count | Approach |",
    "|--------|-------|----------|",
    "| skill_governance | 14 | Extend scripts/validate_skills.py with new checks |",
    "| pipeline_integrity | 7 | New scripts/ci/check_pipeline_integrity.py |",
    "| content_quality | 6 | New scripts/ci/check_content_quality.py |",
    "| metrics | 6 | New scripts/ci/check_metrics.py |",
    "| provenance | 5 | New scripts/ci/check_provenance.py |",
    "| other | 19 | Group into scripts/ci/check_misc.py or individual files |",
    "| knowledge | 3 | New scripts/ci/check_knowledge.py |",
    "| locale | 1 | Add to existing scripts/ci/ |",
    "| link_integrity | 1 | New scripts/ci/check_links.py |",
    "| blog | 1 | Skip (blog-specific, aspose.org-only concern) |",
    "",
    "**Priority order**: skill_governance > content_quality > pipeline_integrity > provenance > knowledge > metrics",
    "",
    "### GC2: Missing Governance Docs (22 docs → docs/governance/ + docs/workflows/)",
    "",
    "Create external governance directory structure mirroring aspose.org.",
    "Adapt content for standalone repo (remove Hugo/website-specific references).",
    "",
    "Priority docs to port first:",
    "1. evidence governance (precondition for content work)",
    "2. write boundaries (safety)",
    "3. launch gates (product launch safety)",
    "4. skill chains (workflow understanding)",
    "5. heal policy (remediation guidance)",
    "",
    "### GC3: Missing Backing Scripts (58 governance_only + 2 documented_not_implemented)",
    "",
    "60 foss-launcher skills have no backing script.",
    "Design approach: Add scripts incrementally, highest-value skills first.",
    "",
    "Priority scripts (by skill usage frequency and impact):",
    "- knowledge-diff, stale-detect, page-plan, page-draft, page-update, page-enhance",
    "- cross-platform, content-audit improvements",
    "- gap-eval family (gap-plan, gap-apply, gap-report)",
    "",
    "### GC4: Size Divergence (52 skills where foss file < 70% aspose size)",
    "",
    "For each diverged skill: compare content section by section.",
    "Add missing sections, examples, and edge case documentation.",
    "Do NOT bloat — only add content present in aspose.org that is genuinely useful.",
    "",
    "### GC5: Missing Test Coverage (59 skills with no test file)",
    "",
    "Add test files for the 22 skills that have scripts (implemented_not_verified).",
    "For governance_only skills, add smoke tests that verify skill files parse correctly.",
    "",
    "### GC6: Missing Shared Libraries (scripts/pipeline/lib/)",
    "",
    "aspose.org has 19 shared modules. Create scripts/pipeline/lib/ directory.",
    "Port the 8-10 most-needed modules based on what skills reference them.",
    "",
    "### GC7: Missing Skill Files (2 skills)",
    "",
    "- `blog-migrate`: Evaluate relevance to standalone repo. If relevant, port content.",
    "- `pipeline-harden`: Highly relevant to standalone repo maintenance. Port with adaptation.",
    "",
    "## Implementation Wave Order",
    "",
    "| Wave | Domain | Taskcards | Rationale |",
    "|------|---------|-----------|-----------|",
    "| W1 | Safety + config | CF-*, VF-SAFETY | Foundation; no skill deps |",
    "| W2 | Registry + ID mapping | RG-* | Foundation for all other work |",
    "| W3 | Governance docs | GV-* | Conceptual foundation |",
    "| W4 | Library stubs | LB-* | Required by script work |",
    "| W5 | CI checks (skill_governance) | CI-001..CI-014 | Highest value, validates everything |",
    "| W6 | Backing scripts | SC-* | Core implementation |",
    "| W7 | Skill content updates | SK-* | Content improvements |",
    "| W8 | CI checks (other domains) | CI-015..CI-063 | Remaining validation |",
    "| W9 | Test coverage | TS-* | Verification layer |",
    "| W10 | Verification + closure | VF-*, DC-* | Final sign-off |",
]

arch_path = f"{OUT_DIR}/target-architecture.md"
with open(arch_path, "w", encoding="utf-8") as f:
    f.write("\n".join(arch_lines))
print(f"Wrote {arch_path}")


# === TASKCARD GENERATION ===
all_tcs = []  # list of (domain, number, title, filename)

def write_tc(domain, num, title, purpose, scope, inputs, allowed, forbidden, deps, steps, verify_steps, artifacts, risk, rollback, done_criteria):
    filename = f"TC-{domain}-{num:03d}.md"
    path = f"{TC_DIR}/{filename}"
    lines = [
        f"# TC-{domain}-{num:03d}: {title}",
        "",
        f"**ID**: {domain}-{num:03d}",
        f"**Title**: {title}",
        f"**Purpose**: {purpose}",
        "",
        f"## Scope",
        scope,
        "",
        f"## Inputs",
    ]
    for inp in inputs:
        lines.append(f"- {inp}")
    lines += [
        "",
        "## Allowed Changes",
    ]
    for a in allowed:
        lines.append(f"- {a}")
    lines += [
        "",
        "## Forbidden Changes",
    ]
    for fb in forbidden:
        lines.append(f"- {fb}")
    lines += [
        "",
        "## Dependencies",
    ]
    for d in deps:
        lines.append(f"- {d}")
    if not deps:
        lines.append("- None")
    lines += [
        "",
        "## Implementation Steps",
    ]
    for i, s in enumerate(steps, 1):
        lines.append(f"{i}. {s}")
    lines += [
        "",
        "## Verification Steps",
    ]
    for i, s in enumerate(verify_steps, 1):
        lines.append(f"{i}. {s}")
    lines += [
        "",
        "## Expected Artifacts",
    ]
    for a in artifacts:
        lines.append(f"- {a}")
    lines += [
        "",
        f"**Risk**: {risk}",
        f"**Rollback**: {rollback}",
        "",
        "## Done Criteria",
    ]
    for c in done_criteria:
        lines.append(f"- [ ] {c}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    all_tcs.append((domain, num, title, filename))
    return filename


# === W1: Configuration / Safety ===
write_tc(
    "CF", 1, "Create .env.example with all required env vars",
    "Document all environment variables needed by foss-launcher skills",
    "Create .env.example at repo root listing all env vars with descriptions.",
    ["AGENTS.md (list of config keys)", "skills/registry.yaml (config_keys fields)", "scripts/ (grep for os.getenv)"],
    [".env.example"],
    ["Any script files", "config.yaml", "AGENTS.md"],
    [],
    [
        "Run `grep -r 'os.getenv\\|os.environ' scripts/ | grep -v '.pyc'` to find all env var references",
        "Identify all unique env var names",
        "Write .env.example with each var, a description, and example value",
        "Add comment block explaining CONTENT_REPO_PATH is required for content-writing skills",
    ],
    [
        "Verify .env.example parses as valid shell comments + assignments",
        "Verify all env vars referenced in scripts/ appear in .env.example",
    ],
    [".env.example at repo root"],
    "LOW — documentation only, no code changes",
    "Delete .env.example if introduced incorrectly",
    [".env.example exists at repo root", "All env vars from scripts/ are documented"],
)

write_tc(
    "VF", 1, "Add CONTENT_REPO_PATH safety guard to test suite",
    "Prevent any test from accidentally writing to aspose.org content",
    "Add a pytest fixture or conftest.py check that aborts if CONTENT_REPO_PATH points to aspose.org root.",
    ["tests/conftest.py (if exists)", "AGENTS.md (forbidden paths)"],
    ["tests/conftest.py"],
    ["Any skill files", "scripts/", "aspose.org repo"],
    ["CF-001"],
    [
        "Check if tests/conftest.py exists; create or edit it",
        "Add a session-scoped fixture that checks os.environ.get('CONTENT_REPO_PATH', '')",
        "If CONTENT_REPO_PATH contains 'aspose.org', raise pytest.fail with clear message",
        "Add comment explaining the safety purpose",
    ],
    [
        "Run pytest tests/test_validate_skills.py — must pass",
        "Temporarily set CONTENT_REPO_PATH to aspose.org path and run a test — must abort with clear error",
    ],
    ["tests/conftest.py with safety guard"],
    "LOW — test infrastructure only",
    "Remove the guard from conftest.py",
    ["conftest.py has CONTENT_REPO_PATH guard", "Guard triggers correctly on forbidden path"],
)


# === W2: Registry / ID Mapping ===
write_tc(
    "RG", 1, "Verify docs/id-mapping.md completeness for all 84 aspose.org skills",
    "Ensure every aspose.org skill ID has a correct foss-launcher mapping entry",
    "Cross-reference aspose-inventory.yaml against docs/id-mapping.md. Add missing entries, fix wrong ones.",
    ["reports/parity/aspose-inventory.yaml", "reports/parity/foss-inventory.yaml", "docs/id-mapping.md"],
    ["docs/id-mapping.md"],
    ["skills/registry.yaml", "Any skill .md files"],
    [],
    [
        "For each of 84 aspose.org skills, verify mapping entry exists in docs/id-mapping.md",
        "For each of 82 shared slugs, verify both aspose_id and foss_id are correct",
        "For 2 aspose-only slugs (blog-migrate, pipeline-harden), add 'not-in-foss' entries",
        "For 10 foss-only slugs, verify 'aspose-equiv: none' entries exist",
        "Fix any wrong ID mappings found",
    ],
    [
        "Count entries in docs/id-mapping.md — should cover all 84+10 skills",
        "Spot-check 10 shared slugs against both registries",
    ],
    ["docs/id-mapping.md updated and complete"],
    "LOW — documentation only",
    "git revert docs/id-mapping.md",
    [
        "docs/id-mapping.md has entries for all 84 aspose.org skills",
        "docs/id-mapping.md has entries for all 10 foss-only skills",
        "Every shared skill has correct aspose_id ↔ foss_id mapping",
    ],
)


# === W3: Governance docs (GV-*) ===
# Priority governance docs
priority_govdocs = [
    ("evidence-governance.md", "Port evidence governance doc from aspose.org", "governance"),
    ("write-boundaries.md", "Port write boundaries doc from aspose.org", "governance"),
    ("launch-gates.md", "Port launch gates doc from aspose.org", "governance"),
    ("naming-conventions.md", "Port naming conventions doc from aspose.org", "governance"),
    ("dar-policy.md", "Port DAR policy doc from aspose.org", "governance"),
]
for i, (filename, title, category) in enumerate(priority_govdocs, 1):
    write_tc(
        "GV", i, title,
        f"Create docs/{category}/{filename} adapted from aspose.org equivalent",
        f"Port the {filename} governance doc from aspose.org, removing Hugo-specific references.",
        [f"D:/onedrive/Documents/GitHub/aspose.org/docs/{category}/{filename}"],
        [f"docs/{category}/{filename}"],
        ["AGENTS.md", "skills/", "scripts/"],
        ["RG-001"],
        [
            f"Read D:/onedrive/Documents/GitHub/aspose.org/docs/{category}/{filename}",
            "Remove all Hugo-specific paths, references to /content/, themes/, layouts/",
            "Adapt CONTENT_REPO_PATH references for standalone repo",
            f"Write docs/{category}/{filename}",
            "Verify docs/ directory exists; create docs/{category}/ if needed",
        ],
        [
            f"Verify docs/{category}/{filename} exists",
            "Verify no Hugo-specific paths remain",
            "Verify document is self-contained and references only foss-launcher paths",
        ],
        [f"docs/{category}/{filename}"],
        "LOW — documentation only",
        f"Delete docs/{category}/{filename}",
        [f"docs/{category}/{filename} exists", "No Hugo-specific content", "Reviewable by operator"],
    )

# Workflow docs
workflow_files_raw = []
wf_dir = f"{ASPOSE_ROOT}/docs/workflows"
if os.path.isdir(wf_dir):
    workflow_files_raw = sorted(os.listdir(wf_dir))

for i, fname in enumerate(workflow_files_raw[:7], 1):  # first 7 workflow docs
    write_tc(
        "GV", 5 + i, f"Port docs/workflows/{fname}",
        f"Create docs/workflows/{fname} adapted from aspose.org workflow doc",
        f"Port {fname} from aspose.org workflows, adapting for standalone repo.",
        [f"D:/onedrive/Documents/GitHub/aspose.org/docs/workflows/{fname}"],
        [f"docs/workflows/{fname}"],
        ["AGENTS.md", "skills/", "scripts/"],
        ["GV-001"],
        [
            f"Read D:/onedrive/Documents/GitHub/aspose.org/docs/workflows/{fname}",
            "Remove Hugo-specific references",
            "Adapt skill IDs using docs/id-mapping.md",
            f"Write docs/workflows/{fname}",
        ],
        [
            f"Verify docs/workflows/{fname} exists",
            "Verify skill IDs use foss-launcher numbering",
        ],
        [f"docs/workflows/{fname}"],
        "LOW — documentation only",
        f"Delete docs/workflows/{fname}",
        [f"docs/workflows/{fname} exists", "Skill IDs adapted to foss-launcher scheme"],
    )


# === W4: Library stubs (LB-*) ===
lib_modules = [
    ("grade_writer", "Grade file I/O utilities"),
    ("heal_controller", "Heal operation controller"),
    ("provenance", "Content provenance tracking"),
    ("registry_loader", "Registry loading utilities"),
    ("content_patcher", "Content patching utilities"),
    ("audit_runner", "Audit execution framework"),
    ("evidence_runner", "Evidence processing framework"),
    ("backtrack_resolver", "Causal backtrack dependency resolver"),
]
for i, (name, desc) in enumerate(lib_modules, 1):
    write_tc(
        "LB", i, f"Create scripts/pipeline/lib/{name}.py stub",
        f"Create the {name} shared library module needed by backing scripts",
        f"Port {name}.py from aspose.org's scripts/pipeline/lib/{name}.py with path adaptations.",
        [f"D:/onedrive/Documents/GitHub/aspose.org/scripts/pipeline/lib/{name}.py"],
        [f"scripts/pipeline/lib/{name}.py"],
        ["Any other scripts", "skills/"],
        ["VF-001"],
        [
            f"Read D:/onedrive/Documents/GitHub/aspose.org/scripts/pipeline/lib/{name}.py",
            "Identify all public functions (used by other modules)",
            "Identify any aspose.org-specific path assumptions and replace with foss patterns",
            f"Create scripts/pipeline/lib/__init__.py if not exists",
            f"Write scripts/pipeline/lib/{name}.py with adapted implementation",
            "Add module docstring documenting origin and adaptations",
        ],
        [
            f"python -c 'from scripts.pipeline.lib import {name}' succeeds",
            "All public functions exist and have correct signatures",
            "No aspose.org-specific paths hardcoded",
        ],
        [f"scripts/pipeline/lib/{name}.py"],
        "MEDIUM — code change, may affect script behavior",
        f"Delete scripts/pipeline/lib/{name}.py",
        [
            f"scripts/pipeline/lib/{name}.py exists",
            "Module imports without error",
            f"Public API matches aspose.org version",
        ],
    )


# === W5: CI checks by domain (CI-*) ===
ci_by_domain = defaultdict(list)
for check in ci_checks:
    ci_by_domain[check.get("domain", "other")].append(check)

ci_num = 1
domain_priority = ["skill_governance", "content_quality", "pipeline_integrity", "provenance", "knowledge", "metrics", "locale", "link_integrity", "other"]

for domain in domain_priority:
    checks = ci_by_domain.get(domain, [])
    if not checks:
        continue
    # Group domain checks into one TC
    check_names = [c["filename"] for c in checks]
    write_tc(
        "CI", ci_num, f"Port {domain} CI checks ({len(checks)} checks)",
        f"Add {len(checks)} {domain.replace('_', ' ')} validation checks from aspose.org to foss-launcher",
        f"Create or extend scripts/ci/check_{domain}.py with checks ported from aspose.org.",
        [f"D:/onedrive/Documents/GitHub/aspose.org/scripts/ci/checks/{n}" for n in check_names[:3]] + ["... (see aspose-ci-checks-map.yaml)"],
        [f"scripts/ci/check_{domain}.py"],
        ["skills/", "docs/", "tests/"],
        ["LB-001", "LB-002"] if domain in ["content_quality", "pipeline_integrity"] else ["VF-001"],
        [
            f"For each of the {len(checks)} {domain} checks, read aspose.org source",
            "Identify logic that is portable vs. aspose.org-specific",
            "Extract portable check logic into check functions",
            f"Write scripts/ci/check_{domain}.py with main() and individual check functions",
            "Add --check-only flag for non-destructive CI mode",
            "Integrate with scripts/validate_skills.py or standalone CI runner",
        ],
        [
            f"python scripts/ci/check_{domain}.py --check-only returns 0 on clean repo",
            "All {len(checks)} check functions exist in the module",
            "No aspose.org-specific paths hardcoded",
        ],
        [f"scripts/ci/check_{domain}.py"],
        "MEDIUM — new CI checks may catch new issues",
        f"Delete scripts/ci/check_{domain}.py",
        [
            f"scripts/ci/check_{domain}.py exists with {len(checks)} check functions",
            "--check-only mode works non-destructively",
        ],
    )
    ci_num += 1


# === W6: Backing scripts for high-priority skills (SC-*) ===
# Skills that need scripts the most (governance_only with large aspose files)
priority_scripts = [
    ("knowledge-diff", "Detect upstream repo changes since last knowledge extraction"),
    ("stale-detect", "Identify content pages affected by upstream changes"),
    ("page-plan", "Plan page structure before drafting"),
    ("page-draft", "Draft initial page content from knowledge model"),
    ("page-update", "Update page after knowledge model change"),
    ("page-enhance", "Enhance page quality to meet rubric bar"),
    ("cross-platform", "Family-wide consistency check across platforms"),
    ("gap-plan", "Wave-ordered remediation planning"),
    ("gap-apply", "Execute wave-ordered fix specs"),
    ("blog-migrate", "Blog migration workflow (aspose-only, port to foss)"),
    ("pipeline-harden", "Pipeline hardening/maintenance (aspose-only, port to foss)"),
]

for i, (slug, desc) in enumerate(priority_scripts, 1):
    aspose_script = aspose_skills.get(slug, {}).get("aspose_script")
    write_tc(
        "SC", i, f"Implement backing script for {slug}",
        f"Create a working backing script for the {slug} skill",
        f"Port or implement the backing script for {slug} in foss-launcher.",
        [f"D:/onedrive/Documents/GitHub/aspose.org/{aspose_script}" if aspose_script else f"D:/onedrive/Documents/GitHub/aspose.org/skills/{slug}.md"],
        [f"scripts/pipeline/commands/{'misc' if not aspose_script else aspose_script.split('/')[3]}/{slug.replace('-','_')}.py"],
        ["skills/", "docs/"],
        ["LB-001"],
        [
            f"Read aspose.org backing script for {slug}" if aspose_script else f"Read skills/{slug}.md to understand expected behavior",
            "Identify all CLI flags and I/O contracts",
            "Adapt path handling for CONTENT_REPO_PATH pattern",
            f"Write backing script with main() and --dry-run support",
            f"Update skills/registry.yaml to point script: field to new script",
        ],
        [
            "python <script> --help returns usage without error",
            "python scripts/validate_skills.py exits 0",
        ],
        [f"Script file for {slug}", "Updated skills/registry.yaml"],
        "MEDIUM — new code, must not break existing tests",
        "Delete script file; revert registry.yaml script: field to null",
        [
            "Script file exists and has main()",
            "--dry-run mode works without writing to content",
            "validate_skills.py passes",
        ],
    )


# === W7: Skill content updates (SK-*) ===
# Skills with size_divergence (foss < 70% of aspose)
size_diverged = []
for slug in sorted(shared):
    ad = aspose_skills.get(slug, {})
    fd = foss_skills.get(slug, {})
    a_kb = ad.get("aspose_size_kb") or 0
    f_kb = fd.get("foss_size_kb") or 0
    if a_kb and f_kb and f_kb / a_kb < 0.7:
        size_diverged.append((slug, a_kb, f_kb))

size_diverged.sort(key=lambda x: x[1] - x[2], reverse=True)  # largest gap first

for i, (slug, a_kb, f_kb) in enumerate(size_diverged[:20], 1):  # top 20 by gap
    gap_kb = round(a_kb - f_kb, 1)
    write_tc(
        "SK", i, f"Update skill content: {slug} (+{gap_kb}KB gap)",
        f"Close content depth gap for {slug} (foss {f_kb}KB vs aspose {a_kb}KB)",
        f"Add missing sections from aspose.org {slug}.md to foss-launcher {slug}.md.",
        [f"D:/onedrive/Documents/GitHub/aspose.org/skills/{slug}.md", f"skills/{slug}.md"],
        [f"skills/{slug}.md"],
        ["skills/registry.yaml", "scripts/"],
        [],
        [
            f"Read aspose.org version: D:/onedrive/Documents/GitHub/aspose.org/skills/{slug}.md",
            f"Read foss-launcher version: skills/{slug}.md",
            "Diff the two versions section by section",
            "Identify sections present in aspose.org but absent or truncated in foss-launcher",
            "Add missing sections, preserving foss-launcher's organization",
            "Run python scripts/sync_commands.py --sync and python scripts/sync_agents.py --sync",
        ],
        [
            "python scripts/validate_skills.py exits 0",
            "python scripts/sync_commands.py --check exits 0",
            f"wc -c skills/{slug}.md is within 20% of aspose.org version",
        ],
        [f"Updated skills/{slug}.md"],
        "LOW — documentation only, mirrors synced after",
        f"git revert skills/{slug}.md",
        [
            f"skills/{slug}.md size is within 20% of aspose.org equivalent",
            "validate_skills.py passes",
            "Mirror sync passes",
        ],
    )

# Remaining size-diverged skills as a batch TC
if len(size_diverged) > 20:
    remaining = size_diverged[20:]
    write_tc(
        "SK", 21, f"Batch update remaining {len(remaining)} skill content files",
        "Close content depth gaps for remaining 32 size-diverged skills",
        "For each remaining skill with size divergence, add missing sections.",
        ["reports/parity/parity-matrix.md (size% column)", "D:/onedrive/Documents/GitHub/aspose.org/skills/"],
        ["skills/*.md (32 specific files)"],
        ["skills/registry.yaml", "scripts/"],
        ["SK-001 through SK-020 (to establish pattern)"],
        [
            "Read parity-matrix.md to identify remaining 32 skills by size%",
            "For each: diff aspose.org vs foss-launcher version",
            "Add missing sections in batches of 5",
            "Run sync after each batch of 5",
        ],
        ["validate_skills.py passes", "All 32 updated skills within 20% of aspose size"],
        ["Updated skill files"],
        "LOW — documentation only",
        "git revert affected skills/*.md files",
        ["All 32 remaining skills within 20% of aspose.org equivalent"],
    )

# Missing skills
for i, slug in enumerate(sorted(aspose_only), 1):
    a_kb = aspose_skills[slug].get("aspose_size_kb", 0)
    write_tc(
        "SK", 30 + i, f"Port missing skill: {slug} ({a_kb}KB)",
        f"Create skills/{slug}.md ported from aspose.org",
        f"Port aspose.org skills/{slug}.md to foss-launcher, adapting for standalone repo.",
        [f"D:/onedrive/Documents/GitHub/aspose.org/skills/{slug}.md"],
        [f"skills/{slug}.md", "skills/registry.yaml"],
        ["scripts/"],
        ["RG-001"],
        [
            f"Read D:/onedrive/Documents/GitHub/aspose.org/skills/{slug}.md",
            "Remove Hugo-specific references",
            "Adapt script paths and ID references for foss-launcher",
            f"Write skills/{slug}.md",
            f"Add entry to skills/registry.yaml (assign next available ID)",
            "Run python scripts/sync_commands.py --sync && python scripts/sync_agents.py --sync",
        ],
        [
            "python scripts/validate_skills.py exits 0",
            f"skills/{slug}.md exists",
            "Mirror sync check passes",
        ],
        [f"skills/{slug}.md", "Updated skills/registry.yaml"],
        "LOW — new file, no changes to existing",
        f"Delete skills/{slug}.md; remove registry entry",
        [
            f"skills/{slug}.md exists",
            f"Registry entry for {slug} added with valid ID",
            "validate_skills.py passes",
        ],
    )


# === W8: Test coverage (TS-*) ===
# Skills with scripts but no tests
needs_tests = []
for slug in sorted(shared):
    fd = foss_skills.get(slug, {})
    if fd.get("foss_script_has_main") and not fd.get("covering_tests"):
        needs_tests.append(slug)

for i, slug in enumerate(sorted(needs_tests), 1):
    fd = foss_skills[slug]
    script = fd.get("foss_script", "unknown script")
    write_tc(
        "TS", i, f"Add test coverage for {slug}",
        f"Add at least one test file covering the core contract of {slug}",
        f"Create tests/test_{slug.replace('-','_')}.py with basic contract tests.",
        [f"skills/{slug}.md", f"{script}"],
        [f"tests/test_{slug.replace('-','_')}.py"],
        ["skills/", "scripts/"],
        ["SC-001"] if slug in [s for s, _ in priority_scripts] else [],
        [
            f"Read skills/{slug}.md to understand expected inputs/outputs",
            f"Read {script} to understand implementation contract",
            "Write test class with at minimum: test_help(), test_dry_run_safe(), test_registry_contract()",
            "Add edge case test for invalid inputs",
        ],
        [
            f"pytest tests/test_{slug.replace('-','_')}.py exits 0",
            "All new tests pass",
        ],
        [f"tests/test_{slug.replace('-','_')}.py"],
        "LOW — tests only, no production code changes",
        f"Delete tests/test_{slug.replace('-','_')}.py",
        [
            f"tests/test_{slug.replace('-','_')}.py exists",
            "At least 3 test functions defined",
            "pytest passes",
        ],
    )


# === W10: Verification ===
write_tc(
    "VF", 2, "Run full parity verification and update parity-matrix.md",
    "Re-run parity analysis after all implementation taskcards complete",
    "Re-execute _build_parity_matrix.py and verify all gaps are closed.",
    ["All TC artifacts", "reports/parity/parity-matrix.md"],
    ["reports/parity/parity-matrix.md", "reports/parity/gap-report.md", "reports/parity/verification-evidence.md"],
    ["skills/", "scripts/", "docs/"],
    ["All other TCs"],
    [
        "Run python reports/parity/_build_parity_matrix.py",
        "Verify parity status distribution improved vs baseline",
        "Check no new missing_entirely or documented_not_implemented skills",
        "Write reports/parity/verification-evidence.md with final metrics",
    ],
    [
        "All acceptance criteria from PAR-011 plan met",
        "Zero 'missing_entirely' skills",
        "Governance docs all exist",
        "CI check coverage improved",
    ],
    ["reports/parity/verification-evidence.md", "Updated parity-matrix.md"],
    "LOW — analysis only",
    "No rollback needed (analysis only)",
    [
        "parity-matrix.md shows no missing_entirely skills",
        "All GV-* taskcards reflected in governance map",
        "CI check count increased from 4",
    ],
)


# === TC INDEX ===
index_lines = [
    "# TC-INDEX — Parity Migration Taskcard Index",
    "",
    "**Generated**: 2026-05-15  **Plan**: PAR-012",
    "",
    "## Summary",
    "",
    f"Total taskcards: {len(all_tcs)}",
    "",
    "## Wave Order",
    "",
    "| Wave | Domain Prefix | Description |",
    "|------|--------------|-------------|",
    "| W1 | CF, VF-001 | Safety + configuration |",
    "| W2 | RG | Registry + ID mapping |",
    "| W3 | GV | Governance documentation |",
    "| W4 | LB | Shared library stubs |",
    "| W5 | CI-001..007 | CI checks: skill_governance priority |",
    "| W6 | SC | Backing script implementations |",
    "| W7 | SK | Skill content updates |",
    "| W8 | CI-008+ | CI checks: remaining domains |",
    "| W9 | TS | Test coverage additions |",
    "| W10 | VF-002, DC | Verification + closure |",
    "",
    "## Full Taskcard List",
    "",
    "| TC ID | Title | Domain | Status |",
    "|-------|-------|--------|--------|",
]

domain_order = {"CF": 1, "VF": 2, "RG": 3, "GV": 4, "LB": 5, "CI": 6, "SC": 7, "SK": 8, "TS": 9, "DC": 10}
sorted_tcs = sorted(all_tcs, key=lambda x: (domain_order.get(x[0], 99), x[1]))

for domain, num, title, filename in sorted_tcs:
    tc_id = f"{domain}-{num:03d}"
    index_lines.append(f"| {tc_id} | {title} | {domain} | pending |")

index_path = f"{TC_DIR}/TC-INDEX.md"
with open(index_path, "w", encoding="utf-8") as f:
    f.write("\n".join(index_lines))
print(f"Wrote {index_path}")

print(f"\n=== PAR-012 COMPLETE ===")
print(f"target-architecture.md: written")
print(f"taskcards/: {len(all_tcs)} taskcards")

# Count by domain
from collections import Counter
domain_counts = Counter(d for d, _, _, _ in all_tcs)
for domain in sorted(domain_counts):
    print(f"  {domain}-*: {domain_counts[domain]}")
