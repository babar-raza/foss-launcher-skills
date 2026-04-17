"""Structural contract tests for S-91 plan-normalize skill.

Static file-content tests only — no network, no LLM, no subprocesses.
Validates:
  (a) Canonical skill has all required structural elements.
  (b) Provider mirrors exist and contain the correct frontmatter.
  (c) Each acceptance fixture contains the keyword markers that define
      its expected normalization verdict.
"""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def read_text(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8", errors="ignore")


class TestPlanNormalizeSkillContract(unittest.TestCase):
    """Canonical skill file structural contract."""

    def setUp(self):
        self.skill_text = read_text("skills/plan-normalize.md")

    def test_contract_block_present(self):
        self.assertIn("<!-- CONTRACT:", self.skill_text)
        self.assertIn("purpose:", self.skill_text)
        self.assertIn("preconditions:", self.skill_text)
        self.assertIn("postcondition", self.skill_text)
        self.assertIn("idempotent:", self.skill_text)

    def test_skill_id_and_title(self):
        self.assertIn("S-91:", self.skill_text)
        self.assertIn("Plan Normalize", self.skill_text)
        self.assertIn("Execution-Safe Plan Quality Gate", self.skill_text)

    def test_three_modes_documented(self):
        self.assertIn("assess", self.skill_text)
        self.assertIn("amend", self.skill_text)
        self.assertIn("launch", self.skill_text)

    def test_seven_section_classifications_present(self):
        for classification in [
            "historical-reference",
            "verified-current-state",
            "completed-archive",
            "open-actionable",
            "operator-guidance",
            "design-rationale",
            "intentionally-omitted",
        ]:
            self.assertIn(classification, self.skill_text,
                          f"Missing section classification: {classification}")

    def test_six_item_statuses_present(self):
        for status in ["ready", "blocked", "stale", "already-done-elsewhere",
                       "needs-replan", "invalid-superseded"]:
            self.assertIn(status, self.skill_text,
                          f"Missing item status: {status}")

    def test_failure_blocking_conditions_present(self):
        self.assertIn("ambiguous", self.skill_text)
        self.assertIn("unverified", self.skill_text)
        self.assertIn("contradicted", self.skill_text)
        self.assertIn("execution-ready-as-is: no", self.skill_text)

    def test_output_schema_six_sections(self):
        for section in ["A. VERDICT", "B. SECTION MAP", "C. OPEN WORK REGISTER",
                        "D. NEXT ITEM", "E. EXCLUSIONS", "F. AMENDED EXECUTION PACK"]:
            self.assertIn(section, self.skill_text,
                          f"Missing output schema section: {section}")

    def test_non_negotiable_rules_present(self):
        self.assertIn("Non-negotiable", self.skill_text)
        self.assertIn("Never execute a plan blindly", self.skill_text)
        self.assertIn("Never flatten", self.skill_text)

    def test_skill_context_gates_present(self):
        self.assertIn("skill_context.py begin", self.skill_text)
        self.assertIn("skill_context.py end", self.skill_text)
        self.assertIn("--skill S-91", self.skill_text)

    def test_arguments_block_present(self):
        self.assertIn("$ARGUMENTS", self.skill_text)
        self.assertIn("--mode", self.skill_text)
        self.assertIn("--related", self.skill_text)
        self.assertIn("--in-place", self.skill_text)


class TestPlanNormalizeProviderMirrors(unittest.TestCase):
    """Provider mirror files exist and have correct frontmatter."""

    def _read_mirror(self, rel_path: str) -> str:
        path = REPO_ROOT / rel_path
        self.assertTrue(path.exists(), f"Provider mirror missing: {rel_path}")
        return path.read_text(encoding="utf-8", errors="ignore")

    def test_claude_mirror_exists_with_frontmatter(self):
        text = self._read_mirror(".claude/commands/plan-normalize.md")
        self.assertIn("name: plan-normalize", text)
        self.assertIn("id: S-91", text)
        self.assertIn("S-91:", text)

    def test_agents_mirror_exists_with_frontmatter(self):
        text = self._read_mirror(".agents/skills/plan-normalize/SKILL.md")
        self.assertIn("name: plan-normalize", text)
        self.assertIn("id: S-91", text)

    def test_kilocode_mirror_exists_with_frontmatter(self):
        text = self._read_mirror(".kilocode/skills/plan-normalize/SKILL.md")
        self.assertIn("name: plan-normalize", text)
        self.assertIn("id: S-91", text)

    def test_all_mirrors_contain_skill_body(self):
        for path in [
            ".claude/commands/plan-normalize.md",
            ".agents/skills/plan-normalize/SKILL.md",
            ".kilocode/skills/plan-normalize/SKILL.md",
        ]:
            text = self._read_mirror(path)
            self.assertIn("execution-ready-as-is", text,
                          f"Mirror missing verdict schema: {path}")
            self.assertIn("historical-reference", text,
                          f"Mirror missing section classification: {path}")


class TestPlanNormalizeFixtures(unittest.TestCase):
    """Acceptance-test fixtures contain keywords matching their expected verdict."""

    FIXTURE_DIR = "tests/fixtures/plan-normalize"

    def _read_fixture(self, name: str) -> str:
        path = REPO_ROOT / self.FIXTURE_DIR / name
        self.assertTrue(path.exists(), f"Fixture missing: {name}")
        return path.read_text(encoding="utf-8", errors="ignore")

    def test_mixed_historical_contains_sprint_and_status_prose(self):
        """Should fail normalization: mixes completed archive with open actions."""
        text = self._read_fixture("mixed-historical-and-current.md")
        # Must contain historical context markers
        self.assertTrue(
            any(kw in text for kw in ["Sprint", "sprint", "retrospective", "Retrospective"]),
            "Fixture should contain sprint/retrospective markers")
        # Must contain completed-work language
        self.assertTrue(
            any(kw in text for kw in ["completed", "Completed", "finished", "done", "Done"]),
            "Fixture should contain completed-work language")
        # Must also contain open-action language (the ambiguity trigger)
        self.assertTrue(
            any(kw in text for kw in ["next", "Next", "still need", "complete the"]),
            "Fixture should contain open-action language creating ambiguity")

    def test_external_next_step_points_outside_plan(self):
        """Should fail normalization: next action references external document."""
        text = self._read_fixture("external-next-step.md")
        # Must reference external document
        self.assertTrue(
            any(kw in text for kw in ["separate", "See the", "wiki", "external"]),
            "Fixture should reference an external document/source")
        # Must present itself as containing a next-step recommendation
        self.assertTrue(
            any(kw in text for kw in ["Next Action", "next action", "Recommended", "recommended"]),
            "Fixture should contain a next-action recommendation")

    def test_intentionally_omitted_contains_exclusion_markers(self):
        """Should pass with omissions in exclusions list."""
        text = self._read_fixture("intentionally-omitted-features.md")
        self.assertTrue(
            any(kw in text for kw in ["must not", "out of scope", "Out of scope",
                                       "explicitly out", "do not"]),
            "Fixture should contain explicit omission markers")
        # Must also have ready work (so it can partially pass)
        self.assertIn("ready", text.lower(),
                      "Fixture should have at least one ready item")

    def test_partially_validated_contains_maturity_markers(self):
        """Should fail normalization: relies on spec-only capability."""
        text = self._read_fixture("partially-validated-capabilities.md")
        self.assertTrue(
            any(kw in text for kw in ["spec-only", "partially validated",
                                       "partially-validated", "not yet"]),
            "Fixture should contain capability maturity markers")
        # The ready item must depend on an unverified capability
        self.assertTrue(
            any(kw in text for kw in ["Relies on", "relies on", "dependent", "requires"]),
            "Fixture should show dependency on the unverified capability")

    def test_clean_plan_has_named_files_and_validation(self):
        """Should pass normalization: clear ready items with files and validation."""
        text = self._read_fixture("clean-execution-plan.md")
        # Must have named files
        self.assertIn("content/", text,
                      "Fixture should reference named content files")
        # Must have a validation method
        self.assertTrue(
            any(kw in text for kw in ["Validation:", "validation:", "validates by",
                                       "expect", "audit"]),
            "Fixture should contain explicit validation method")
        # Must have ready status
        self.assertIn("ready", text.lower(),
                      "Fixture should mark items as ready")
        # Must NOT have ambiguous archive mixing
        self.assertFalse(
            any(kw in text for kw in ["Sprint", "postmortem", "historical"]),
            "Clean fixture should not contain archive/sprint content")


class TestPlanNormalizeAgentsRegistration(unittest.TestCase):
    """AGENTS.md governance integration."""

    def setUp(self):
        self.agents_text = read_text("AGENTS.md")

    def test_s91_in_registry_table(self):
        self.assertIn("S-91", self.agents_text)
        self.assertIn("plan-normalize", self.agents_text)

    def test_s91_in_mental_model_refresh(self):
        """§3 should reference plan-normalize for stale/archive plans."""
        self.assertIn("plan-normalize", self.agents_text)
        # The §3 bullet should exist
        self.assertIn("S-91", self.agents_text)

    def test_plan_execution_gate_section_in_s6(self):
        """§6 should have the plan execution gate section."""
        self.assertIn("Plan execution gate", self.agents_text)
        self.assertIn("execution-ready-as-is: no", self.agents_text)


if __name__ == "__main__":
    unittest.main()
