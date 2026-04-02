"""Tests for scripts/validate_skills.py — skill registry integrity checker."""
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from validate_skills import (
    check_id_uniqueness,
    check_registry_vs_files,
    check_files_vs_registry,
    check_commands_sync,
    check_script_refs,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_skill(skills_dir, name, frontmatter="", body="# skill body\n"):
    """Write a skills/*.md file with optional frontmatter."""
    content = f"---\nname: {name}\n{frontmatter}---\n\n{body}" if frontmatter else body
    (skills_dir / f"{name}.md").write_text(content, encoding="utf-8")


def _write_command(commands_dir, name, body="# skill body\n"):
    """Write a .claude/commands/*.md file (body only, no frontmatter)."""
    (commands_dir / f"{name}.md").write_text(body, encoding="utf-8")


def _write_registry(skills_dir, skills: list[dict]):
    """Write a registry.yaml to skills_dir."""
    data = {"schema_version": 1, "skills": skills}
    (skills_dir / "registry.yaml").write_text(
        yaml.dump(data, default_flow_style=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# check_id_uniqueness
# ---------------------------------------------------------------------------

class TestIdUniqueness:
    def test_no_duplicates_returns_empty(self):
        skills = [
            {"id": "S-01", "name": "path-guard"},
            {"id": "S-02", "name": "other-skill"},
        ]
        assert check_id_uniqueness(skills) == []

    def test_duplicate_ids_returns_error(self):
        skills = [
            {"id": "S-42", "name": "category-fix"},
            {"id": "S-42", "name": "evidence-verify"},
        ]
        errors = check_id_uniqueness(skills)
        assert len(errors) == 1
        assert "S-42" in errors[0]
        assert "category-fix" in errors[0]
        assert "evidence-verify" in errors[0]

    def test_missing_id_field_returns_error(self):
        skills = [{"name": "unnamed-skill"}]
        errors = check_id_uniqueness(skills)
        assert len(errors) == 1
        assert "MISSING_ID" in errors[0]

    def test_three_way_duplicate_reports_multiple(self):
        skills = [
            {"id": "S-38", "name": "launch-product"},
            {"id": "S-38", "name": "truth-audit"},
            {"id": "S-38", "name": "other"},
        ]
        errors = check_id_uniqueness(skills)
        assert len(errors) == 2  # second and third collide with first


# ---------------------------------------------------------------------------
# check_registry_vs_files
# ---------------------------------------------------------------------------

class TestRegistryVsFiles:
    def test_all_files_present_returns_empty(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "my-skill")
        skills = [{"id": "S-99", "name": "my-skill"}]
        assert check_registry_vs_files(skills, skills_dir) == []

    def test_missing_file_returns_error(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skills = [{"id": "S-99", "name": "ghost-skill"}]  # file not created
        errors = check_registry_vs_files(skills, skills_dir)
        assert len(errors) == 1
        assert "ghost-skill" in errors[0]
        assert "MISSING_FILE" in errors[0]

    def test_entry_without_name_returns_error(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skills = [{"id": "S-99"}]  # no name
        errors = check_registry_vs_files(skills, skills_dir)
        assert len(errors) == 1
        assert "NO_NAME" in errors[0]


# ---------------------------------------------------------------------------
# check_files_vs_registry
# ---------------------------------------------------------------------------

class TestFilesVsRegistry:
    def test_all_registered_returns_empty(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "my-skill")
        skills = [{"id": "S-99", "name": "my-skill"}]
        assert check_files_vs_registry(skills, skills_dir) == []

    def test_unregistered_file_returns_error(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "mystery-skill")
        skills = []  # registry is empty
        errors = check_files_vs_registry(skills, skills_dir)
        assert len(errors) == 1
        assert "mystery-skill" in errors[0]
        assert "UNREGISTERED" in errors[0]

    def test_registry_yaml_itself_is_ignored(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # registry.yaml should not be checked as a skill file
        (skills_dir / "registry.yaml").write_text("schema_version: 1\nskills: []\n")
        skills = []
        errors = check_files_vs_registry(skills, skills_dir)
        assert errors == []


# ---------------------------------------------------------------------------
# check_commands_sync
# ---------------------------------------------------------------------------

class TestCommandsSync:
    def test_in_sync_returns_empty(self, tmp_path):
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        body = "# my skill\n\nDoes things.\n"
        _write_skill(skills_dir, "my-skill", body=body)
        _write_command(commands_dir, "my-skill", body=body)

        errors = check_commands_sync(skills_dir, commands_dir)
        assert errors == []

    def test_commands_with_frontmatter_stripped_matches(self, tmp_path):
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        body = "# my skill\n\nDoes things.\n"
        # skills/ file has frontmatter
        (skills_dir / "my-skill.md").write_text(
            f"---\nname: my-skill\nid: S-99\n---\n\n{body}", encoding="utf-8"
        )
        # commands/ file has only the body
        _write_command(commands_dir, "my-skill", body=body)

        errors = check_commands_sync(skills_dir, commands_dir)
        assert errors == []

    def test_missing_command_file_detected(self, tmp_path):
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        _write_skill(skills_dir, "my-skill")
        # no command file created

        errors = check_commands_sync(skills_dir, commands_dir)
        assert len(errors) == 1
        assert "MISSING_CMD" in errors[0]

    def test_content_drift_detected(self, tmp_path):
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        _write_skill(skills_dir, "my-skill", body="# updated body\n")
        _write_command(commands_dir, "my-skill", body="# old body\n")

        errors = check_commands_sync(skills_dir, commands_dir)
        assert len(errors) == 1
        assert "DIFFERS" in errors[0]

    def test_extra_command_file_detected(self, tmp_path):
        skills_dir = tmp_path / "skills"
        commands_dir = tmp_path / "commands"
        skills_dir.mkdir()
        commands_dir.mkdir()

        # command file exists but has no canonical in skills/
        _write_command(commands_dir, "ghost-skill")

        errors = check_commands_sync(skills_dir, commands_dir)
        assert len(errors) == 1
        assert "EXTRA_CMD" in errors[0]

    def test_missing_commands_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        missing_dir = tmp_path / "nonexistent"

        errors = check_commands_sync(skills_dir, missing_dir)
        assert len(errors) == 1
        assert "MISSING_DIR" in errors[0]


# ---------------------------------------------------------------------------
# check_script_refs
# ---------------------------------------------------------------------------

class TestScriptRefs:
    def test_null_script_not_checked(self, tmp_path):
        skills = [{"id": "S-01", "name": "path-guard", "script": None}]
        errors = check_script_refs(skills, tmp_path)
        assert errors == []

    def test_existing_script_passes(self, tmp_path):
        script = tmp_path / "scripts" / "my_script.py"
        script.parent.mkdir()
        script.touch()
        skills = [{"id": "S-01", "name": "my-skill", "script": "scripts/my_script.py"}]
        errors = check_script_refs(skills, tmp_path)
        assert errors == []

    def test_missing_script_returns_error(self, tmp_path):
        skills = [{"id": "S-01", "name": "my-skill", "script": "scripts/missing.py"}]
        errors = check_script_refs(skills, tmp_path)
        assert len(errors) == 1
        assert "MISSING_SCRIPT" in errors[0]
        assert "missing.py" in errors[0]


# ---------------------------------------------------------------------------
# run() — integration over real repo
# ---------------------------------------------------------------------------

class TestRunIntegration:
    def test_real_registry_passes_id_uniqueness(self):
        """The actual registry must have no duplicate IDs."""
        from validate_skills import load_registry
        registry_path = REPO_ROOT / "skills" / "registry.yaml"
        if not registry_path.exists():
            pytest.skip("registry.yaml not present")
        skills = load_registry(registry_path)
        errors = check_id_uniqueness(skills)
        assert errors == [], f"ID collisions in registry:\n" + "\n".join(errors)

    def test_real_registry_all_files_present(self):
        """Every registry entry must have a skill file on disk."""
        from validate_skills import load_registry
        registry_path = REPO_ROOT / "skills" / "registry.yaml"
        if not registry_path.exists():
            pytest.skip("registry.yaml not present")
        skills = load_registry(registry_path)
        errors = check_registry_vs_files(skills, REPO_ROOT / "skills")
        assert errors == [], "Registry entries missing skill files:\n" + "\n".join(errors)

    def test_real_registry_all_files_registered(self):
        """Every skills/*.md must appear in the registry."""
        from validate_skills import load_registry
        registry_path = REPO_ROOT / "skills" / "registry.yaml"
        if not registry_path.exists():
            pytest.skip("registry.yaml not present")
        skills = load_registry(registry_path)
        errors = check_files_vs_registry(skills, REPO_ROOT / "skills")
        assert errors == [], "Unregistered skill files:\n" + "\n".join(errors)
