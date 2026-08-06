"""Tests for check_supervisor_artifacts.py (MT021 TC-MT021-07, ST-060)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_CHECKS = Path(__file__).resolve().parents[1] / "checks"
if str(_CHECKS) not in sys.path:
    sys.path.insert(0, str(_CHECKS))

import check_supervisor_artifacts as csa  # noqa: E402


class TestDeclaredOutputs:
    """The contract is parsed from the prompts, never hardcoded here."""

    @pytest.mark.parametrize("stage,minimum", [(1, 11), (2, 17), (3, 14)])
    def test_each_stage_declares_outputs(self, stage, minimum):
        outs = csa.declared_outputs(stage)
        assert len(outs) == minimum
        assert all(o.startswith(f"stage{stage}-") for o in outs)

    def test_parsing_reflects_prompt_edits_rather_than_a_frozen_copy(self, tmp_path, monkeypatch):
        """REGRESSION GATE: a hardcoded list would silently drift from the prompt.

        That drift is the same producer/consumer divergence class this mission line
        exists to remove, so the check must re-read the prompt every run.
        """
        fake = tmp_path / "prompts"; fake.mkdir()
        (fake / "prompt1-post-sprint-audit.md").write_text(
            "## Required Outputs\n- `stage1-only-one.md`\n", encoding="utf-8")
        monkeypatch.setattr(csa, "PROMPTS_DIR", fake)
        assert csa.declared_outputs(1) == ["stage1-only-one.md"]


class TestCompleteness:
    def _mission(self, tmp_path, files):
        d = tmp_path / "MT999-TEST"; d.mkdir()
        for f in files:
            # Machine-readable artifacts must be valid instances, otherwise the
            # conformance pass (correctly) reports them and the completeness
            # assertion under test is confounded.
            if f == "stage1-issue-model.json":
                (d / f).write_text(json.dumps({
                    "mission_id": "MT999", "issues": [],
                    "final_verdict": "SPRINT_ALL_GREEN_VERIFIED"}), encoding="utf-8")
            else:
                (d / f).write_text("x", encoding="utf-8")
        return d

    def test_missing_artifacts_are_reported(self, tmp_path):
        d = self._mission(tmp_path, ["stage1-sprint-audit-summary.md"])
        r = csa.audit_mission(d)
        assert r["ok"] is False
        assert r["stages"]["stage1"]["attempted"] is True
        assert "stage1-issue-model.json" in r["stages"]["stage1"]["missing"]

    def test_absence_is_caught_even_though_no_schema_could_catch_it(self, tmp_path):
        """The failure mode that actually bit: artifacts never produced at all.

        A JSON Schema validates a document's shape; it cannot flag a document that
        does not exist. MT020 produced 4 of 11 stage1 artifacts and nothing noticed.
        """
        d = self._mission(tmp_path, ["stage1-l1-execution-issues.yaml"])
        r = csa.audit_mission(d)
        assert r["missing_total"] >= 10
        assert r["schema_errors"] == {}          # no shape errors -- pure absence

    def test_unattempted_stage_is_skipped_not_failed(self, tmp_path):
        """A mission that never ran stage3 must not be reported as a stage3 failure."""
        d = self._mission(tmp_path, [f for f in csa.declared_outputs(1) if "*" not in f])
        r = csa.audit_mission(d)
        assert r["stages"]["stage1"]["attempted"] is True
        assert r["stages"]["stage3"]["attempted"] is False
        assert r["ok"] is True

    def test_complete_stage1_passes(self, tmp_path):
        d = self._mission(tmp_path, [f for f in csa.declared_outputs(1) if "*" not in f])
        assert csa.audit_mission(d)["ok"] is True

    def test_glob_entry_is_satisfied_by_any_match(self, tmp_path):
        d = tmp_path / "MT998"; (d / "stage2-taskcards").mkdir(parents=True)
        (d / "stage2-taskcards" / "TC-01.yaml").write_text("x", encoding="utf-8")
        r = csa.audit_mission(d)
        assert "stage2-taskcards/*.yaml" not in r["stages"]["stage2"]["missing"]


class TestSchemaConformance:
    def test_valid_instance_passes(self):
        schema = json.loads((csa.SCHEMAS_DIR / "stage1-issue-model.schema.json")
                            .read_text(encoding="utf-8"))
        inst = {"mission_id": "MT999", "final_verdict": "SPRINT_ALL_GREEN_VERIFIED",
                "issues": []}
        assert csa._validate_schema(inst, schema) == []

    def test_missing_required_key_is_reported(self):
        schema = json.loads((csa.SCHEMAS_DIR / "stage1-issue-model.schema.json")
                            .read_text(encoding="utf-8"))
        errs = csa._validate_schema({"mission_id": "MT999"}, schema)
        assert any("issues" in e for e in errs)

    def test_bad_enum_value_is_reported(self):
        schema = json.loads((csa.SCHEMAS_DIR / "stage1-issue-model.schema.json")
                            .read_text(encoding="utf-8"))
        errs = csa._validate_schema(
            {"mission_id": "M", "issues": [], "final_verdict": "TOTALLY_MADE_UP"}, schema)
        assert any("not in allowed values" in e for e in errs)

    def test_scoring_rubric_rejects_out_of_range_score(self):
        schema = json.loads((csa.SCHEMAS_DIR / "stage3-quality-scoring-rubric.schema.json")
                            .read_text(encoding="utf-8"))
        dims = schema["properties"]["items"]["items"]["properties"]["scores"]["required"]
        inst = {"mission_id": "M", "verdict": "EXECUTION_COMPLETE_VERIFIED",
                "items": [{"taskcard_id": "TC-1", "accepted": True,
                           "scores": {d: 5 for d in dims}}]}
        assert csa._validate_schema(inst, schema) == []
        inst["items"][0]["scores"][dims[0]] = 9          # outside 1-5
        assert csa._validate_schema(inst, schema) != []


class TestShippedSchemas:
    """The three schemas the prompt suite declares must exist and be parseable."""

    @pytest.mark.parametrize("name", [
        "stage1-issue-model.schema.json",
        "stage2-taskcard-contract.schema.json",
        "stage3-quality-scoring-rubric.schema.json",
    ])
    def test_schema_exists_and_parses(self, name):
        p = csa.SCHEMAS_DIR / name
        assert p.is_file(), f"{name} declared by the prompt suite but absent"
        assert json.loads(p.read_text(encoding="utf-8"))["type"] == "object"

    def test_prompt2_no_longer_requires_the_underivable_status_enum(self):
        """MT021 removed that dangling requirement rather than inventing an enum."""
        text = (csa.PROMPTS_DIR / "prompt2-plan-hardening.md").read_text(encoding="utf-8")
        assert "valid enum from taskcard-state-machine.schema.json" not in text

    def test_unauthored_schemas_are_marked_not_authored_not_silently_claimed(self):
        """The contracts table must not assert a schema that does not exist.

        Six of its nine rows have no field spec anywhere, so they were annotated
        rather than invented (guessing) or deleted (losing the intent).
        """
        text = (csa.PROMPTS_DIR / "prompt-output-contracts.md").read_text(encoding="utf-8")
        for row in text.splitlines():
            m = [w for w in row.split("`") if w.endswith(".schema.json")]
            if not m or not row.startswith("|"):
                continue
            exists = (csa.SCHEMAS_DIR / Path(m[0]).name).is_file()
            if not exists:
                assert "NOT AUTHORED" in row, f"row claims a missing schema: {row}"
