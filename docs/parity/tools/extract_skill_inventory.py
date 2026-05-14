#!/usr/bin/env python3
"""Extract a normalized skill inventory from a source repo.

This utility is intentionally read-only against the source repo. It writes
inventory artifacts under the current working repository.
"""

from __future__ import annotations

import argparse
import json
import hashlib
import re
from datetime import date
from pathlib import Path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def field_after(text: str, label: str) -> str:
    pattern = re.compile(r"^\*\*" + re.escape(label) + r"\*\*:\s*(.*)$", re.M)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def bullets_under(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    capture = False
    values: list[str] = []
    for line in lines:
        if re.match(r"^#{1,6}\s+", line):
            if capture:
                break
            if heading.lower() in line.lower():
                capture = True
            continue
        if capture and re.match(r"^\s*[-*]\s+", line):
            values.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
    return values


def paths_mentioned(text: str) -> list[str]:
    candidates: set[str] = set()
    for match in re.finditer(r"`([^`]+)`", text):
        value = match.group(1).strip()
        if any(token in value for token in ["/", ".py", ".json", ".yaml", ".yml", ".md", ".sh"]):
            if not value.startswith(("http://", "https://")) and len(value) < 180:
                candidates.add(value)
    path_re = re.compile(
        r"(?:python\s+)?((?:scripts|skills|\.agents|\.claude|\.kilocode|docs|knowledge|content|reports|data|configs|runs|backlog|plans)/[^\s)\],;]+)"
    )
    for match in path_re.finditer(text):
        candidates.add(match.group(1).strip("`.,"))
    return sorted(candidates)


def env_keys(text: str) -> list[str]:
    keys = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text))
    skip = {
        "README",
        "YAML",
        "JSON",
        "HUGO",
        "CLI",
        "CI",
        "API",
        "URL",
        "HTTP",
        "LLM",
        "FOSS",
        "MVP",
        "PASS",
        "FAIL",
        "WARN",
        "STOP",
        "DENY",
    }
    return sorted(key for key in keys if key not in skip)


def command_refs(text: str) -> list[str]:
    return sorted(set(re.findall(r"/(?!/)([a-z0-9][a-z0-9-]+)", text)))


def rel_to(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def load_registry(repo: Path) -> tuple[dict[str, dict], str | None, dict]:
    json_path = repo / "skills" / "registry.json"
    yaml_path = repo / "skills" / "registry.yaml"
    if json_path.exists():
        data = json.loads(read_text(json_path))
        return {item.get("slug") or item.get("name"): item for item in data.get("skills", [])}, "skills/registry.json", data
    if yaml_path.exists():
        # Lightweight parser for the simple registry.yaml shape used here.
        registry: dict[str, dict] = {}
        current: dict[str, str | bool | None] | None = None
        for line in read_text(yaml_path).splitlines():
            if re.match(r"^\s*-\s+id:\s*", line):
                if current and current.get("name"):
                    registry[str(current["name"])] = current
                current = {"id": line.split(":", 1)[1].strip()}
            elif current is not None and re.match(r"^\s+[a-z_]+:\s*", line):
                key, value = line.strip().split(":", 1)
                value = value.strip()
                if "#" in value:
                    value = value.split("#", 1)[0].strip()
                if value == "null":
                    current[key] = None
                elif value in {"true", "false"}:
                    current[key] = value == "true"
                else:
                    current[key] = value
        if current and current.get("name"):
            registry[str(current["name"])] = current
        return registry, "skills/registry.yaml", {"skill_count": len(registry), "skills": list(registry.values())}
    return {}, None, {"skills": []}


def discover_slugs(repo: Path, registry: dict[str, dict]) -> list[str]:
    slugs = set(registry)
    for path in (repo / "skills").glob("*.md"):
        if path.name.lower() != "readme.md":
            slugs.add(path.stem)
    for path in (repo / ".agents" / "skills").glob("*/SKILL.md"):
        slugs.add(path.parent.name)
    for path in (repo / ".claude" / "commands").glob("*.md"):
        if path.name.lower() != "readme.md":
            slugs.add(path.stem)
    for path in (repo / ".kilocode" / "skills").glob("*/SKILL.md"):
        slugs.add(path.parent.name)
    return sorted(slugs)


def inventory(repo: Path, repo_name: str) -> dict:
    registry, registry_path, registry_data = load_registry(repo)
    records = []
    for slug in discover_slugs(repo, registry):
        paths = {
            "canonical_markdown": repo / "skills" / f"{slug}.md",
            "codex_skill": repo / ".agents" / "skills" / slug / "SKILL.md",
            "claude_command": repo / ".claude" / "commands" / f"{slug}.md",
            "kilocode_skill": repo / ".kilocode" / "skills" / slug / "SKILL.md",
        }
        texts = {key: read_text(path) for key, path in paths.items() if path.exists()}
        primary_text = (
            texts.get("canonical_markdown")
            or texts.get("codex_skill")
            or texts.get("claude_command")
            or texts.get("kilocode_skill")
            or ""
        )
        all_text = "\n".join(texts.values())
        mentioned = paths_mentioned(all_text)
        scripts = sorted(
            {
                item
                for item in mentioned
                if item.startswith("scripts/") or item.endswith(".py") or item.endswith(".sh")
            }
        )
        docs = sorted({item for item in mentioned if item.startswith("docs/") or item.endswith(".md")})
        configs = sorted(
            {
                item
                for item in mentioned
                if item.startswith(("configs/", "data/")) or item.endswith((".json", ".yaml", ".yml", ".toml"))
            }
        )
        tests = sorted({item for item in mentioned if item.startswith("tests/") or "/tests/" in item})
        write_paths = sorted(
            {
                item
                for item in mentioned
                if item.startswith(("content/", "reports/", "knowledge/", "data/", "backlog/", "plans/", "runs/", "repairs/"))
            }
        )
        reg_item = registry.get(slug, {})
        registry_script = reg_item.get("script")
        registry_scripts = [str(registry_script)] if registry_script else []
        combined_scripts = sorted(set(scripts) | set(registry_scripts))
        record = {
            "canonical_name": slug,
            "repo": repo_name,
            "repo_path": str(repo),
            "provider_paths": {key: rel_to(path, repo) if path.exists() else None for key, path in paths.items()},
            "provider_path_hashes": {key: sha256(path) for key, path in paths.items() if path.exists()},
            "id": reg_item.get("id") or field_after(primary_text, "ID"),
            "role_purpose": reg_item.get("description") or field_after(primary_text, "Purpose") or first_heading(primary_text),
            "feature_group": "unclassified_inventory",
            "trigger_invocation": field_after(primary_text, "Invocation")
            or field_after(primary_text, "Arguments")
            or "slash command or internal skill chain; verify in detailed review",
            "registry_script": registry_script,
            "inputs": bullets_under(primary_text, "input") or bullets_under(primary_text, "arguments"),
            "outputs": bullets_under(primary_text, "output") or bullets_under(primary_text, "produces"),
            "side_effects": bullets_under(primary_text, "side effect"),
            "write_paths": write_paths,
            "forbidden_paths": [item for item in mentioned if "forbidden" in item.lower()],
            "dependencies": {
                "skills": command_refs(all_text),
                "scripts": combined_scripts,
                "scripts_mentioned_in_text": scripts,
                "scripts_declared_in_registry": registry_scripts,
                "modules": sorted({item for item in combined_scripts if item.endswith(".py")}),
                "configs": configs,
                "docs_contracts": docs,
                "tests": tests,
                "fixtures": sorted({item for item in mentioned if "fixture" in item.lower()}),
                "external_tools": sorted(
                    set(
                        re.findall(
                            r"\b(?:git|python|pytest|hugo|tree-sitter|mypy|ollama|Gemini|professionalize\.com|LLMRouter)\b",
                            all_text,
                            flags=re.I,
                        )
                    )
                ),
                "repo_layout": sorted(
                    {
                        item
                        for item in mentioned
                        if item.startswith(("content/", "knowledge/", "runs/.clone_cache", "themes/", "layouts/", "configs/"))
                    }
                ),
            },
            "config_keys": env_keys(all_text),
            "required_environment": [
                key
                for key in env_keys(all_text)
                if key
                in {
                    "ASPOSE_CLONE_CACHE",
                    "CONTENT_REPO_PATH",
                    "PYTHONPATH",
                    "AGENT_METRICS_ENDPOINT",
                    "AGENT_METRICS_TOKEN",
                }
            ],
            "governance_hooks": sorted(
                {item for item in mentioned if "hook" in item.lower() or "guard" in item.lower() or "audit" in item.lower()}
            ),
            "ci_references": sorted({item for item in mentioned if item.startswith(".github/") or "ci" in item.lower()}),
            "entrypoints": combined_scripts,
            "generated_artifacts": bullets_under(primary_text, "output") or bullets_under(primary_text, "produces"),
            "runtime_state": sorted({item for item in mentioned if item.startswith(("reports/", "runs/", "backlog/", "plans/"))}),
            "source_of_truth_files": [rel_to(path, repo) for path in paths.values() if path.exists()]
            + ([registry_path] if registry_path and slug in registry else []),
            "maturity_status": "registered" if slug in registry else "unregistered_or_provider_only",
            "feature_status": "inventory_recorded_unverified",
            "verification_status": "not_executed_inventory_only",
            "evidence": {
                "files": [rel_to(path, repo) for path in paths.values() if path.exists()],
                "commands": ["find provider skill trees", f"read {registry_path}", "scan skill text for references"],
                "snippets": [first_heading(primary_text)][:1],
            },
            "confidence": "medium" if primary_text and slug in registry else "low" if primary_text else "very_low",
            "ambiguities": [],
            "notes": "Automatically extracted; detailed behavioral verification deferred to parity and verification phases.",
        }
        if slug not in registry:
            record["ambiguities"].append(f"No {registry_path or 'registry'} entry found for this slug.")
        if not paths["canonical_markdown"].exists():
            record["ambiguities"].append("No canonical skills/*.md file found.")
        if not paths["codex_skill"].exists():
            record["ambiguities"].append("No .agents/skills provider file found.")
        if not combined_scripts:
            record["ambiguities"].append("No backing script path detected in skill text; may be prompt-only or hidden dependency.")
        records.append(record)

    repo_record = {
        "repo": repo_name,
        "role": "Hugo website repo and embedded reference implementation for the skills system"
        if repo_name == "aspose.org"
        else "Standalone skills repository",
        "repo_root": str(repo),
        "inventory_date": str(date.today()),
        "skill_tree_counts": {
            "skills_markdown": len([path for path in (repo / "skills").glob("*.md") if path.name.lower() != "readme.md"]),
            "codex_agents_skills": len(list((repo / ".agents" / "skills").glob("*/SKILL.md"))),
            "claude_commands": len([path for path in (repo / ".claude" / "commands").glob("*.md") if path.name.lower() != "readme.md"]),
            "kilocode_skills": len(list((repo / ".kilocode" / "skills").glob("*/SKILL.md"))),
            "registry_skill_count": registry_data.get("skill_count") or len(registry),
            "normalized_records": len(records),
        },
        "registries": [item for item in [registry_path, "docs/registries/skills.md", "scripts/pipeline/config/registry.yaml"] if item],
        "provider_mirrors": ["skills/*.md", ".agents/skills/*/SKILL.md", ".claude/commands/*.md", ".kilocode/skills/*/SKILL.md"],
        "operator_docs": [
            item
            for item in ["AGENTS.md", "CODEX.md", "CLAUDE.md", "OPERATOR_GUIDE.md", "RUNBOOK.md", "QUICKSTART.md", "docs/QUICKSTART.md"]
            if (repo / item).exists()
        ],
        "governance_docs": [item for item in ["docs/governance/", "docs/workflows/", "docs/registries/"] if (repo / item).exists()],
        "script_roots": [
            item
            for item in ["scripts/", "scripts/pipeline/commands/", "scripts/pipeline/content_eval/", "scripts/gap-eval/", "scripts/translator/", "scripts/ci/"]
            if (repo / item).exists()
        ],
        "test_roots": [item for item in ["tests/", "scripts/pipeline/tests/", "scripts/ci/tests/"] if (repo / item).exists()],
        "fixture_roots": [item for item in ["tests/fixtures/", "scripts/ci/fixtures/", "scripts/gap-eval/profiles/"] if (repo / item).exists()],
        "ci_workflows": sorted(rel_to(path, repo) for path in (repo / ".github" / "workflows").glob("*.yml")),
        "hooks": sorted(rel_to(path, repo) for path in (repo / "scripts" / "ci" / "hooks").glob("*.sh")),
        "runtime_data_roots": [
            item
            for item in ["knowledge/", "runs/.clone_cache/", "content/", "reports/", "backlog/", "plans/", "repairs/", "data/", "golden/", "repos/", "output/"]
            if (repo / item).exists()
        ],
        "content_or_external_repo_coupling": "Direct local Hugo content coupling"
        if (repo / "content").exists()
        else "External content repo coupling via config/env",
        "known_forbidden_write_paths": [],
        "known_output_roots": [
            item
            for item in ["content/", "knowledge/", "reports/", "runs/", "backlog/", "plans/", "repairs/", "data/", "output/"]
            if (repo / item).exists()
        ],
        "known_discovery_mechanisms": [item for item in [registry_path, "skills/README.md", ".agents/skills/README.md", ".claude/commands/README.md"] if item and (repo / item).exists()],
        "known_sync_mechanisms": [
            rel_to(path, repo)
            for path in list((repo / "scripts").glob("*sync*.py")) + list((repo / "scripts" / "pipeline" / "commands" / "ops").glob("*sync*.py"))
        ],
        "known_validation_mechanisms": [
            rel_to(path, repo)
            for path in list((repo / "scripts").glob("*validate*.py")) + list((repo / "scripts" / "ci" / "checks").glob("check_skill*.py"))
        ],
    }
    return {"schema_version": 1, "phase": "skill inventory", "repo_record": repo_record, "records": records}


def write_summary(data: dict, out_path: Path, title: str) -> None:
    counts = data["repo_record"]["skill_tree_counts"]
    records = data["records"]
    provider_keys = ["canonical_markdown", "codex_skill", "claude_command", "kilocode_skill"]
    provider_gaps = {key: [] for key in provider_keys}
    no_script = []
    unregistered = []
    for record in records:
        if record["maturity_status"] != "registered":
            unregistered.append(record["canonical_name"])
        if not record["entrypoints"]:
            no_script.append(record["canonical_name"])
        for key in provider_keys:
            if record["provider_paths"].get(key) is None:
                provider_gaps[key].append(record["canonical_name"])

    lines = [
        f"# {title}\n\n",
        f"Date: {date.today()}\n\n",
        "## Phase Goal\n\nExtract the full normalized skill-system inventory for the source repository.\n\n",
        "## Exit Criteria Status\n\nMet for inventory extraction: normalized records were created for every discovered skill slug. Behavioral parity is not concluded in this phase.\n\n",
        "## Counts\n\n",
    ]
    for key, value in counts.items():
        lines.append(f"- `{key}`: {value}\n")
    lines.append("\n## Provider Gaps\n\n")
    for key, values in provider_gaps.items():
        preview = ", ".join(values[:40])
        suffix = " ..." if len(values) > 40 else ""
        lines.append(f"- `{key}` missing for {len(values)} records: {preview}{suffix}\n")
    lines.append("\n## Registry And Entrypoint Signals\n\n")
    lines.append(f"- Unregistered/provider-only records: {len(unregistered)}")
    if unregistered:
        lines.append(f" - {', '.join(unregistered)}")
    lines.append("\n")
    lines.append(f"- Records with no backing script detected in skill text: {len(no_script)}\n")
    lines.append("\n## High-Confidence Surfaces\n\n")
    for key in ["registries", "provider_mirrors", "script_roots", "test_roots", "ci_workflows", "hooks"]:
        lines.append(f"### {key}\n\n")
        for item in data["repo_record"].get(key, []):
            lines.append(f"- `{item}`\n")
        lines.append("\n")
    lines.append("## Unresolved Ambiguities\n\n")
    lines.append("- Prompt-only records require behavioral review before parity conclusions.\n")
    lines.append("- Detected script paths prove references, not execution success.\n")
    lines.append("- Provider mirror divergence requires dedicated sync/byte comparison checks.\n")
    out_path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--repo-name", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-summary", required=True)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    data = inventory(repo, args.repo_name)
    Path(args.out_json).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    write_summary(data, Path(args.out_summary), f"{args.repo_name} Skill Inventory")
    print(
        json.dumps(
            {
                "repo": args.repo_name,
                "records": len(data["records"]),
                "counts": data["repo_record"]["skill_tree_counts"],
                "out_json": args.out_json,
                "out_summary": args.out_summary,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
