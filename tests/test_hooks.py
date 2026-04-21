"""Tests for scripts/pre-commit-audit.sh, scripts/commit-msg-skills.sh, scripts/install-hooks.sh.

These are bash scripts — not importable Python — so tests cover:
  1. Existence and shebang correctness
  2. Key logic patterns in the script body (grep for critical strings)
  3. Commit-msg provenance logic exercised inline via Python (mirrors
     the embedded Python snippet in commit-msg-skills.sh)

No bash subprocess is invoked; tests are pure Python inspection of script content.
"""
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

PRE_COMMIT = SCRIPTS_DIR / "pre-commit-audit.sh"
COMMIT_MSG = SCRIPTS_DIR / "commit-msg-skills.sh"
INSTALL_HOOKS = SCRIPTS_DIR / "install-hooks.sh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Existence tests
# ---------------------------------------------------------------------------

class TestHookScriptsExist:
    def test_pre_commit_audit_exists(self):
        assert PRE_COMMIT.exists(), f"Missing: {PRE_COMMIT}"

    def test_commit_msg_skills_exists(self):
        assert COMMIT_MSG.exists(), f"Missing: {COMMIT_MSG}"

    def test_install_hooks_exists(self):
        assert INSTALL_HOOKS.exists(), f"Missing: {INSTALL_HOOKS}"


# ---------------------------------------------------------------------------
# Shebang tests
# ---------------------------------------------------------------------------

class TestHookScriptShebangs:
    def test_pre_commit_has_bash_shebang(self):
        first_line = _read(PRE_COMMIT).splitlines()[0]
        assert first_line == "#!/usr/bin/env bash", (
            f"Expected '#!/usr/bin/env bash', got: {first_line!r}"
        )

    def test_commit_msg_has_bash_shebang(self):
        first_line = _read(COMMIT_MSG).splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_install_hooks_has_bash_shebang(self):
        first_line = _read(INSTALL_HOOKS).splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"


# ---------------------------------------------------------------------------
# pre-commit-audit.sh logic verification
# ---------------------------------------------------------------------------

class TestPreCommitAuditContent:
    def setup_method(self):
        self.text = _read(PRE_COMMIT)

    def test_calls_validate_skills(self):
        assert "validate_skills.py" in self.text

    def test_calls_sync_commands_check(self):
        assert "sync_commands.py --check" in self.text

    def test_calls_sync_agents_check(self):
        assert "sync_agents.py --check" in self.text

    def test_exits_1_on_error(self):
        assert "exit 1" in self.text

    def test_exits_0_on_pass(self):
        assert "exit 0" in self.text

    def test_has_error_counter(self):
        assert "ERRORS" in self.text

    def test_forbidden_paths_include_skills_and_scripts(self):
        assert "skills/" in self.text
        assert "scripts/" in self.text

    def test_forbidden_paths_include_claude_dir(self):
        assert ".claude/" in self.text

    def test_readme_step_present(self):
        assert "readme_sync.py" in self.text

    def test_step_count_at_least_four(self):
        """At least 4 numbered step comments."""
        steps = re.findall(r"Step \d+", self.text)
        assert len(steps) >= 4, f"Expected ≥4 steps, found {len(steps)}: {steps}"


# ---------------------------------------------------------------------------
# commit-msg-skills.sh logic verification
# ---------------------------------------------------------------------------

class TestCommitMsgSkillsContent:
    def setup_method(self):
        self.text = _read(COMMIT_MSG)

    def test_requires_commit_msg_file_arg(self):
        assert "COMMIT_MSG_FILE" in self.text

    def test_exempt_merge_commits(self):
        assert "Merge" in self.text

    def test_exempt_revert_commits(self):
        assert "Revert" in self.text

    def test_exempt_wip_commits(self):
        assert "WIP" in self.text

    def test_exempt_chore_commits(self):
        assert "chore:" in self.text

    def test_checks_content_dir(self):
        assert "content/" in self.text

    def test_requires_skills_invoked_line(self):
        assert "Skills invoked:" in self.text

    def test_validates_ids_against_registry(self):
        assert "registry.yaml" in self.text

    def test_exits_1_for_missing_provenance(self):
        assert "exit 1" in self.text

    def test_exits_0_for_valid_commit(self):
        assert "exit 0" in self.text

    def test_skills_id_pattern_s_hyphen_digits(self):
        assert "S-[0-9]+" in self.text

    def test_manual_override_documented(self):
        assert "manual" in self.text


# ---------------------------------------------------------------------------
# install-hooks.sh logic verification
# ---------------------------------------------------------------------------

class TestInstallHooksContent:
    def setup_method(self):
        self.text = _read(INSTALL_HOOKS)

    def test_installs_pre_commit_hook(self):
        assert "pre-commit" in self.text

    def test_installs_commit_msg_hook(self):
        assert "commit-msg" in self.text

    def test_delegates_to_pre_commit_audit(self):
        assert "pre-commit-audit.sh" in self.text

    def test_delegates_to_commit_msg_skills(self):
        assert "commit-msg-skills.sh" in self.text

    def test_checks_for_git_repo(self):
        assert ".git" in self.text

    def test_chmod_applied(self):
        assert "chmod" in self.text

    def test_not_auto_installed_comment(self):
        """Script must document that it is opt-in, never auto-installed."""
        assert "opt-in" in self.text or "never auto-installed" in self.text or "opt in" in self.text.lower()


# ---------------------------------------------------------------------------
# Commit-msg provenance logic — Python inline validation
#
# The commit-msg-skills.sh embeds a Python snippet to load registry.yaml
# and check cited skill IDs. We test that same logic here using the real
# registry, confirming the validation behavior is correct.
# ---------------------------------------------------------------------------

class TestCommitMsgProvenanceLogic:
    """Exercise the ID-validation logic from commit-msg-skills.sh inline."""

    def _load_registered_ids(self) -> set[str]:
        registry_path = REPO_ROOT / "skills" / "registry.yaml"
        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return {e["id"] for e in data.get("skills", []) if e.get("id")}

    def _validate_skills_line(self, skills_line: str) -> list[str]:
        """Return list of unrecognized IDs (mirrors bash logic)."""
        registered = self._load_registered_ids()
        cited = re.findall(r"S-\d+", skills_line)
        return [sid for sid in cited if sid not in registered]

    def test_valid_skill_id_passes(self):
        unknown = self._validate_skills_line("Skills invoked: S-19, S-23, S-24")
        assert unknown == [], f"Unexpected unknowns: {unknown}"

    def test_unknown_skill_id_detected(self):
        unknown = self._validate_skills_line("Skills invoked: S-999")
        assert "S-999" in unknown

    def test_multiple_valid_ids_pass(self):
        unknown = self._validate_skills_line("Skills invoked: S-01, S-12, S-34, S-56")
        assert unknown == []

    def test_mixed_valid_and_invalid(self):
        unknown = self._validate_skills_line("Skills invoked: S-01, S-9999, S-12")
        assert unknown == ["S-9999"]
        assert "S-01" not in unknown

    def test_manual_keyword_produces_no_ids(self):
        """'Skills invoked: manual' has no S-XX tokens — no validation fails."""
        unknown = self._validate_skills_line("Skills invoked: manual")
        assert unknown == []

    def test_exempt_commit_types(self):
        """Verify that the exempt patterns we test for are realistic first-line prefixes."""
        exempt_prefixes = ["Merge ", "Revert ", "WIP: ", "fixup! ", "squash! ", "chore: "]
        pattern = re.compile(r"^(Merge|Revert|WIP|fixup!|squash!|chore:)")
        for prefix in exempt_prefixes:
            assert pattern.match(prefix), f"Exempt pattern did not match: {prefix!r}"

    def test_non_exempt_commit_not_matched(self):
        pattern = re.compile(r"^(Merge|Revert|WIP|fixup!|squash!|chore:)")
        assert not pattern.match("feat: add new skill")
        assert not pattern.match("fix: correct bug in content")
