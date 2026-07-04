"""Tests for tools/capability_sync/ — unified cross-agent capability synchronization tooling.

These tests exercise the inventory, parity validation, drift detection, orphan detection,
and index generation modules without requiring actual file system state beyond what the
test fixtures set up.
"""

import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure tools/ is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# ── Shared test fixtures ──────────────────────────────────────────────────────

MINIMAL_REGISTRY = {
    "skills": [
        {"id": "S-01", "name": "path-guard", "description": "Enforce write paths", "internal": True, "script": "scripts/path_guard.py"},
        {"id": "S-23", "name": "ground-check", "description": "Pre-write evidence verification", "internal": False, "script": None},
        {"id": "S-81", "name": "commit", "description": "Stage and commit changes", "internal": False, "script": None},
    ]
}


# ── inventory_capabilities ────────────────────────────────────────────────────

class TestInventoryCapabilities:
    def test_build_inventory_returns_expected_structure(self, tmp_path):
        """build_inventory returns a dict with total_capabilities, capabilities list."""
        # Create minimal registry
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "registry.yaml").write_text(
            "skills:\n- id: S-01\n  name: test-skill\n  description: Test\n  internal: false\n  script: null\n",
            encoding="utf-8",
        )
        (skills_dir / "test-skill.md").write_text("# Test skill", encoding="utf-8")

        from tools.capability_sync import inventory_capabilities as inv
        orig_root = inv._REPO_ROOT
        orig_skills = inv._SKILLS_DIR
        orig_registry = inv._SKILLS_REGISTRY
        orig_gov = inv._GOV_REGISTRY
        orig_claude = inv._CLAUDE_COMMANDS
        orig_agents = inv._AGENTS_SKILLS
        orig_kilo = inv._KILO_SKILLS

        try:
            inv._REPO_ROOT = tmp_path
            inv._SKILLS_DIR = skills_dir
            inv._SKILLS_REGISTRY = skills_dir / "registry.yaml"
            inv._GOV_REGISTRY = tmp_path / ".governance" / "capabilities" / "registry.yaml"
            inv._CLAUDE_COMMANDS = tmp_path / ".claude" / "commands"
            inv._AGENTS_SKILLS = tmp_path / ".agents" / "skills"
            inv._KILO_SKILLS = tmp_path / ".kilocode" / "skills"

            result = inv.build_inventory()
            assert result["total_capabilities"] == 1
            assert result["public_capabilities"] == 1
            assert result["internal_capabilities"] == 0
            assert len(result["capabilities"]) == 1
            cap = result["capabilities"][0]
            assert cap["id"] == "S-01"
            assert cap["name"] == "test-skill"
            assert cap["adapters"]["canonical_exists"] is True
        finally:
            inv._REPO_ROOT = orig_root
            inv._SKILLS_DIR = orig_skills
            inv._SKILLS_REGISTRY = orig_registry
            inv._GOV_REGISTRY = orig_gov
            inv._CLAUDE_COMMANDS = orig_claude
            inv._AGENTS_SKILLS = orig_agents
            inv._KILO_SKILLS = orig_kilo

    def test_load_skills_raises_if_registry_missing(self, tmp_path):
        """load_skills raises FileNotFoundError if registry.yaml is absent."""
        from tools.capability_sync import inventory_capabilities as inv
        orig_dir = inv._SKILLS_DIR
        orig_registry = inv._SKILLS_REGISTRY
        try:
            inv._SKILLS_DIR = tmp_path / "nonexistent"
            inv._SKILLS_REGISTRY = tmp_path / "nonexistent" / "registry.yaml"
            with pytest.raises(FileNotFoundError):
                inv.load_skills_registry()
        finally:
            inv._SKILLS_DIR = orig_dir
            inv._SKILLS_REGISTRY = orig_registry


# ── validate_semantic_parity ──────────────────────────────────────────────────

class TestValidateSemanticParity:
    def _make_skill_ecosystem(self, tmp_path, skill_name="ground-check", internal=False, add_command=True, add_agent=True, drift=False):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(parents=True)
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        agents_dir = tmp_path / ".agents" / "skills" / skill_name
        agents_dir.mkdir(parents=True)
        kilo_dir = tmp_path / ".kilocode" / "skills" / skill_name
        kilo_dir.mkdir(parents=True)

        canonical_body = f"# {skill_name}\n\nCanonical skill body."
        frontmatter = f"---\nname: {skill_name}\nid: S-23\n---\n\n"
        (skills_dir / "registry.yaml").write_text(
            f"skills:\n- id: S-23\n  name: {skill_name}\n  description: Test\n  internal: {'true' if internal else 'false'}\n  script: null\n",
            encoding="utf-8",
        )
        (skills_dir / f"{skill_name}.md").write_text(frontmatter + canonical_body, encoding="utf-8")

        if add_command and not internal:
            content = canonical_body if not drift else canonical_body + "\n\nDRIFT"
            (commands_dir / f"{skill_name}.md").write_text(content, encoding="utf-8")

        if add_agent:
            content = frontmatter + (canonical_body if not drift else canonical_body + "\n\nDRIFT")
            (agents_dir / "SKILL.md").write_text(content, encoding="utf-8")
            (kilo_dir / "SKILL.md").write_text(content, encoding="utf-8")

        return skills_dir, commands_dir

    def test_full_parity_when_adapters_match(self, tmp_path):
        from tools.capability_sync import validate_semantic_parity as vsp
        orig_skills = vsp._SKILLS_DIR
        orig_commands = vsp._CLAUDE_COMMANDS
        orig_agents = vsp._AGENTS_SKILLS
        orig_kilo = vsp._KILO_SKILLS

        try:
            skills_dir, commands_dir = self._make_skill_ecosystem(tmp_path)
            vsp._SKILLS_DIR = skills_dir
            vsp._CLAUDE_COMMANDS = tmp_path / ".claude" / "commands"
            vsp._AGENTS_SKILLS = tmp_path / ".agents" / "skills"
            vsp._KILO_SKILLS = tmp_path / ".kilocode" / "skills"

            records, counts = vsp.check_parity()
            assert counts["semantic_drift"] == 0
            assert counts["claude_adapter_missing"] == 0
            assert counts["agent_skill_adapter_missing"] == 0
            assert records[0]["parity_status"] == "FULL_PARITY"
        finally:
            vsp._SKILLS_DIR = orig_skills
            vsp._CLAUDE_COMMANDS = orig_commands
            vsp._AGENTS_SKILLS = orig_agents
            vsp._KILO_SKILLS = orig_kilo

    def test_semantic_drift_detected(self, tmp_path):
        from tools.capability_sync import validate_semantic_parity as vsp
        orig_skills = vsp._SKILLS_DIR
        orig_commands = vsp._CLAUDE_COMMANDS
        orig_agents = vsp._AGENTS_SKILLS
        orig_kilo = vsp._KILO_SKILLS

        try:
            self._make_skill_ecosystem(tmp_path, drift=True)
            vsp._SKILLS_DIR = tmp_path / "skills"
            vsp._CLAUDE_COMMANDS = tmp_path / ".claude" / "commands"
            vsp._AGENTS_SKILLS = tmp_path / ".agents" / "skills"
            vsp._KILO_SKILLS = tmp_path / ".kilocode" / "skills"

            records, counts = vsp.check_parity()
            assert counts["semantic_drift"] > 0
        finally:
            vsp._SKILLS_DIR = orig_skills
            vsp._CLAUDE_COMMANDS = orig_commands
            vsp._AGENTS_SKILLS = orig_agents
            vsp._KILO_SKILLS = orig_kilo

    def test_missing_claude_adapter_detected(self, tmp_path):
        from tools.capability_sync import validate_semantic_parity as vsp
        orig_skills = vsp._SKILLS_DIR
        orig_commands = vsp._CLAUDE_COMMANDS
        orig_agents = vsp._AGENTS_SKILLS
        orig_kilo = vsp._KILO_SKILLS

        try:
            self._make_skill_ecosystem(tmp_path, add_command=False)
            vsp._SKILLS_DIR = tmp_path / "skills"
            vsp._CLAUDE_COMMANDS = tmp_path / ".claude" / "commands"
            vsp._AGENTS_SKILLS = tmp_path / ".agents" / "skills"
            vsp._KILO_SKILLS = tmp_path / ".kilocode" / "skills"

            records, counts = vsp.check_parity()
            assert counts["claude_adapter_missing"] == 1
        finally:
            vsp._SKILLS_DIR = orig_skills
            vsp._CLAUDE_COMMANDS = orig_commands
            vsp._AGENTS_SKILLS = orig_agents
            vsp._KILO_SKILLS = orig_kilo

    def test_internal_skill_skipped_for_claude_adapter(self, tmp_path):
        from tools.capability_sync import validate_semantic_parity as vsp
        orig_skills = vsp._SKILLS_DIR
        orig_commands = vsp._CLAUDE_COMMANDS
        orig_agents = vsp._AGENTS_SKILLS
        orig_kilo = vsp._KILO_SKILLS

        try:
            self._make_skill_ecosystem(tmp_path, internal=True, add_command=False)
            vsp._SKILLS_DIR = tmp_path / "skills"
            vsp._CLAUDE_COMMANDS = tmp_path / ".claude" / "commands"
            vsp._AGENTS_SKILLS = tmp_path / ".agents" / "skills"
            vsp._KILO_SKILLS = tmp_path / ".kilocode" / "skills"

            records, counts = vsp.check_parity()
            assert counts["claude_adapter_missing"] == 0  # internal skill — skip claude check
        finally:
            vsp._SKILLS_DIR = orig_skills
            vsp._CLAUDE_COMMANDS = orig_commands
            vsp._AGENTS_SKILLS = orig_agents
            vsp._KILO_SKILLS = orig_kilo


# ── detect_adapter_drift ──────────────────────────────────────────────────────

class TestDetectAdapterDrift:
    def test_no_drift_when_adapters_match(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)

        canonical_body = "# Test skill\n\nCanonical body."
        (skills_dir / "registry.yaml").write_text(
            "skills:\n- id: S-23\n  name: test-skill\n  description: Test\n  internal: false\n  script: null\n",
            encoding="utf-8",
        )
        (skills_dir / "test-skill.md").write_text(f"---\nname: test-skill\n---\n\n{canonical_body}", encoding="utf-8")
        (commands_dir / "test-skill.md").write_text(canonical_body, encoding="utf-8")

        from tools.capability_sync import detect_adapter_drift as dad
        orig_root = dad._REPO_ROOT
        orig_skills = dad._SKILLS_DIR
        orig_commands = dad._CLAUDE_COMMANDS
        orig_agents = dad._AGENTS_SKILLS
        orig_kilo = dad._KILO_SKILLS
        try:
            dad._REPO_ROOT = tmp_path
            dad._SKILLS_DIR = skills_dir
            dad._CLAUDE_COMMANDS = commands_dir
            dad._AGENTS_SKILLS = tmp_path / ".agents" / "skills"
            dad._KILO_SKILLS = tmp_path / ".kilocode" / "skills"
            drift_entries, total = dad.detect_drift()
            assert len(drift_entries) == 0
            assert total == 1
        finally:
            dad._REPO_ROOT = orig_root
            dad._SKILLS_DIR = orig_skills
            dad._CLAUDE_COMMANDS = orig_commands
            dad._AGENTS_SKILLS = orig_agents
            dad._KILO_SKILLS = orig_kilo

    def test_drift_detected_when_content_differs(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)

        (skills_dir / "registry.yaml").write_text(
            "skills:\n- id: S-23\n  name: test-skill\n  description: Test\n  internal: false\n  script: null\n",
            encoding="utf-8",
        )
        (skills_dir / "test-skill.md").write_text("---\nname: test-skill\n---\n\n# Original", encoding="utf-8")
        (commands_dir / "test-skill.md").write_text("# Modified — drifted content", encoding="utf-8")

        from tools.capability_sync import detect_adapter_drift as dad
        orig_root = dad._REPO_ROOT
        orig_skills = dad._SKILLS_DIR
        orig_commands = dad._CLAUDE_COMMANDS
        orig_agents = dad._AGENTS_SKILLS
        orig_kilo = dad._KILO_SKILLS
        try:
            dad._REPO_ROOT = tmp_path
            dad._SKILLS_DIR = skills_dir
            dad._CLAUDE_COMMANDS = commands_dir
            dad._AGENTS_SKILLS = tmp_path / ".agents" / "skills"
            dad._KILO_SKILLS = tmp_path / ".kilocode" / "skills"
            drift_entries, total = dad.detect_drift()
            assert len(drift_entries) == 1
            assert drift_entries[0]["adapter_type"] == "CLAUDE_COMMAND"
        finally:
            dad._REPO_ROOT = orig_root
            dad._SKILLS_DIR = orig_skills
            dad._CLAUDE_COMMANDS = orig_commands
            dad._AGENTS_SKILLS = orig_agents
            dad._KILO_SKILLS = orig_kilo


# ── detect_orphans ────────────────────────────────────────────────────────────

class TestDetectOrphans:
    def test_no_orphans_when_clean(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)

        (skills_dir / "registry.yaml").write_text(
            "skills:\n- id: S-23\n  name: clean-skill\n  description: Test\n  internal: false\n  script: null\n",
            encoding="utf-8",
        )
        (skills_dir / "clean-skill.md").write_text("# clean-skill", encoding="utf-8")
        (commands_dir / "clean-skill.md").write_text("# clean-skill", encoding="utf-8")

        from tools.capability_sync import detect_orphans as dorp
        orig_root = dorp._REPO_ROOT
        orig_skills = dorp._SKILLS_DIR
        orig_commands = dorp._CLAUDE_COMMANDS
        orig_agents = dorp._AGENTS_SKILLS
        orig_kilo = dorp._KILO_SKILLS
        try:
            dorp._REPO_ROOT = tmp_path
            dorp._SKILLS_DIR = skills_dir
            dorp._CLAUDE_COMMANDS = commands_dir
            dorp._AGENTS_SKILLS = tmp_path / ".agents" / "skills"
            dorp._KILO_SKILLS = tmp_path / ".kilocode" / "skills"
            result = dorp.detect_orphans()
            assert result["total_orphans"] == 0
        finally:
            dorp._REPO_ROOT = orig_root
            dorp._SKILLS_DIR = orig_skills
            dorp._CLAUDE_COMMANDS = orig_commands
            dorp._AGENTS_SKILLS = orig_agents
            dorp._KILO_SKILLS = orig_kilo

    def test_orphan_command_detected(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)

        (skills_dir / "registry.yaml").write_text(
            "skills:\n- id: S-23\n  name: real-skill\n  description: Test\n  internal: false\n  script: null\n",
            encoding="utf-8",
        )
        (skills_dir / "real-skill.md").write_text("# real-skill", encoding="utf-8")
        (commands_dir / "real-skill.md").write_text("# real-skill", encoding="utf-8")
        # Orphan: command with no canonical
        (commands_dir / "ghost-command.md").write_text("# ghost", encoding="utf-8")

        from tools.capability_sync import detect_orphans as dorp
        orig_root = dorp._REPO_ROOT
        orig_skills = dorp._SKILLS_DIR
        orig_commands = dorp._CLAUDE_COMMANDS
        orig_agents = dorp._AGENTS_SKILLS
        orig_kilo = dorp._KILO_SKILLS
        try:
            dorp._REPO_ROOT = tmp_path
            dorp._SKILLS_DIR = skills_dir
            dorp._CLAUDE_COMMANDS = commands_dir
            dorp._AGENTS_SKILLS = tmp_path / ".agents" / "skills"
            dorp._KILO_SKILLS = tmp_path / ".kilocode" / "skills"
            result = dorp.detect_orphans()
            assert result["total_orphans"] == 1
            assert any(o["name"] == "ghost-command" for o in result["orphan_commands"])
        finally:
            dorp._REPO_ROOT = orig_root
            dorp._SKILLS_DIR = orig_skills
            dorp._CLAUDE_COMMANDS = orig_commands
            dorp._AGENTS_SKILLS = orig_agents
            dorp._KILO_SKILLS = orig_kilo


# ── generate_capability_index ─────────────────────────────────────────────────

class TestGenerateCapabilityIndex:
    def test_generates_claude_index_with_markers(self, tmp_path):
        from tools.capability_sync import generate_capability_index as gci
        skills = [
            {"id": "S-23", "name": "ground-check", "description": "Pre-write verification", "internal": False},
            {"id": "S-01", "name": "path-guard", "description": "Enforce paths", "internal": True},
        ]
        gov_meta = {}
        result = gci.generate_claude_index(skills, gov_meta)
        assert "<!-- BEGIN GENERATED CAPABILITY INDEX -->" in result
        assert "<!-- END GENERATED CAPABILITY INDEX -->" in result
        assert "ground-check" in result
        # Internal skill should NOT appear in Claude index
        assert "path-guard" not in result

    def test_generates_codex_index_includes_internal(self, tmp_path):
        from tools.capability_sync import generate_capability_index as gci
        skills = [
            {"id": "S-23", "name": "ground-check", "description": "Verify", "internal": False},
            {"id": "S-01", "name": "path-guard", "description": "Guard", "internal": True},
        ]
        gov_meta = {}
        result = gci.generate_codex_index(skills, gov_meta)
        assert "ground-check" in result
        assert "path-guard" in result  # Codex index includes internal skills

    def test_generated_markers_are_stable(self):
        from tools.capability_sync import generate_capability_index as gci
        skills = [{"id": "S-23", "name": "test", "description": "desc", "internal": False}]
        r1 = gci.generate_claude_index(skills, {})
        r2 = gci.generate_claude_index(skills, {})
        # Strip timestamp line for comparison
        def strip_ts(text):
            return re.sub(r"Generated at: \d{4}-\d{2}-\d{2}", "Generated at: DATE", text)
        assert strip_ts(r1) == strip_ts(r2)


# ── Governance schema validation ──────────────────────────────────────────────

class TestGovernanceSchemas:
    """Basic structural checks on the JSON schemas."""

    def test_capability_schema_exists(self):
        schema_path = _REPO_ROOT / ".governance" / "schemas" / "capability.schema.json"
        assert schema_path.exists(), "capability.schema.json not found"
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        assert data.get("$schema")
        assert "capability_id" in data.get("properties", {})

    def test_execution_receipt_schema_exists(self):
        schema_path = _REPO_ROOT / ".governance" / "schemas" / "execution-receipt.schema.json"
        assert schema_path.exists(), "execution-receipt.schema.json not found"
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "agent_type" in data.get("properties", {})
        assert "verdict" in data.get("properties", {})

    def test_adapter_manifest_schema_exists(self):
        schema_path = _REPO_ROOT / ".governance" / "schemas" / "adapter-manifest.schema.json"
        assert schema_path.exists(), "adapter-manifest.schema.json not found"
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "capability_id" in data.get("properties", {})
        assert "generated_hash" in data.get("properties", {})

    def test_receipt_schema_requires_key_fields(self):
        schema_path = _REPO_ROOT / ".governance" / "schemas" / "execution-receipt.schema.json"
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        required = set(data.get("required", []))
        assert "receipt_id" in required
        assert "capability_id" in required
        assert "agent_type" in required
        assert "verdict" in required
