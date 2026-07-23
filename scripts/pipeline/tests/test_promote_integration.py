"""Integration tests for promote.py — full scout/ -> merged/ pipeline.

Covers the gaps not addressed by test_merge_determinism.py:
- api_surface.json is correctly promoted from scout/ to merged/
- model.yaml is written to merged/ with stale_since: null
- All scout claims land in merged/ with provenance="scout"
- merged/claims.json claim count matches scout input
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

# sys.path is set by tests/conftest.py — no manual insert needed here.
import promote as promote_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SCOUT_CLAIMS = [
    {"claim_id": "CLM-test-p1-001", "text": "Scene.open(filename) loads a 3D file.", "kind": "api_method"},
    {"claim_id": "CLM-test-p1-002", "text": "Scene.save(filename) writes a 3D file.", "kind": "api_method"},
    {"claim_id": "CLM-test-p1-003", "text": "FileFormat.OBJ is a supported format.", "kind": "format"},
    {"claim_id": "CLM-test-p1-004", "text": "Node.name is the node identifier property.", "kind": "api_property"},
    {"claim_id": "CLM-test-p1-005", "text": "AssetInfo.title is the scene title.", "kind": "api_property"},
]

API_SURFACE = [
    {
        "name": "Scene",
        "methods": [
            {"name": "open", "return_type": "Scene", "params": ["filename"]},
            {"name": "save", "return_type": "", "params": ["filename"]},
        ],
        "properties": [{"name": "root_node", "type": "Node", "line": 10}],
        "enum_members": [],
        "bases": [],
    },
    {
        "name": "Node",
        "methods": [{"name": "create_child_node", "return_type": "Node", "params": []}],
        "properties": [{"name": "name", "type": "str", "line": 5}],
        "enum_members": [],
        "bases": [],
    },
    {
        "name": "FileFormat",
        "methods": [],
        "properties": [],
        "enum_members": [{"name": "OBJ", "value": "0"}, {"name": "FBX", "value": "1"}],
        "bases": [],
    },
]

MODEL_YAML = {
    "family": "test",
    "platform": "python",
    "repo_sha": "abc123def456",
    "stale_since": None,
    "class_count": 3,
    "method_count": 3,
    "enum_count": 1,
    "claim_count": 5,
}


def _setup_scout(tmp_path: Path) -> Path:
    """Create a minimal but valid scout/ knowledge tree in tmp_path."""
    knowledge_root = tmp_path / "knowledge"
    scout_dir = knowledge_root / "test" / "python" / "scout"
    scout_dir.mkdir(parents=True)

    (scout_dir / "claims.json").write_text(
        json.dumps(SCOUT_CLAIMS, indent=2), encoding="utf-8"
    )
    (scout_dir / "api_surface.json").write_text(
        json.dumps(API_SURFACE, indent=2), encoding="utf-8"
    )
    (scout_dir / "model.yaml").write_text(
        yaml.dump(MODEL_YAML, default_flow_style=False), encoding="utf-8"
    )
    return knowledge_root


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestPromoteFullPipeline:
    """End-to-end: scout/ -> merged/ with all expected outputs."""

    def test_promote_returns_true_on_success(self, tmp_path):
        kr = _setup_scout(tmp_path)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is True, "promote() should return True on a valid scout tree"

    def test_merged_claims_json_exists(self, tmp_path):
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_claims = kr / "test" / "python" / "merged" / "claims.json"
        assert merged_claims.exists(), "merged/claims.json must be written by promote()"

    def test_all_scout_claims_present_in_merged(self, tmp_path):
        """Every claim from scout/claims.json must appear in merged/claims.json."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        claims = data if isinstance(data, list) else data.get("claims", [])
        claim_ids = {c["claim_id"] for c in claims}
        for original in SCOUT_CLAIMS:
            assert original["claim_id"] in claim_ids, (
                f"Scout claim '{original['claim_id']}' missing from merged/claims.json"
            )

    def test_scout_claims_have_provenance_scout(self, tmp_path):
        """All promoted scout claims must have provenance='scout'."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        claims = data if isinstance(data, list) else data.get("claims", [])
        scout_ids = {c["claim_id"] for c in SCOUT_CLAIMS}
        for claim in claims:
            if claim["claim_id"] in scout_ids:
                assert claim.get("provenance") == "scout", (
                    f"Scout claim '{claim['claim_id']}' should have provenance='scout', "
                    f"got '{claim.get('provenance')}'"
                )

    def test_merged_api_surface_json_exists(self, tmp_path):
        """promote() must copy/promote api_surface.json to merged/."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_api = kr / "test" / "python" / "merged" / "api_surface.json"
        assert merged_api.exists(), "merged/api_surface.json must be written by promote()"

    def test_merged_api_surface_contains_all_classes(self, tmp_path):
        """All classes from scout/api_surface.json must appear in merged/api_surface.json."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_api = kr / "test" / "python" / "merged" / "api_surface.json"
        data = json.loads(merged_api.read_text(encoding="utf-8"))
        assert isinstance(data, list), "merged/api_surface.json should be a list"
        class_names = {cls["name"] for cls in data}
        for original_cls in API_SURFACE:
            assert original_cls["name"] in class_names, (
                f"Class '{original_cls['name']}' missing from merged/api_surface.json"
            )

    def test_merged_model_yaml_exists(self, tmp_path):
        """promote() must write model.yaml to merged/."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_model = kr / "test" / "python" / "merged" / "model.yaml"
        assert merged_model.exists(), "merged/model.yaml must be written by promote()"

    def test_merged_model_has_stale_since_null(self, tmp_path):
        """merged/model.yaml must have stale_since: null after successful promotion."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_model = kr / "test" / "python" / "merged" / "model.yaml"
        model = yaml.safe_load(merged_model.read_text(encoding="utf-8"))
        assert model.get("stale_since") is None, (
            f"merged/model.yaml should have stale_since: null, got {model.get('stale_since')!r}"
        )

    def test_merged_claim_count_matches_scout(self, tmp_path):
        """merged/claims.json count must equal number of scout claims (no enriched)."""
        kr = _setup_scout(tmp_path)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        claims = data if isinstance(data, list) else data.get("claims", [])
        assert len(claims) == len(SCOUT_CLAIMS), (
            f"Expected {len(SCOUT_CLAIMS)} claims in merged output, got {len(claims)}"
        )

    def test_stale_enriched_claims_are_ignored(self, tmp_path):
        """Enriched claims tied to an old API surface must not be promoted."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        (scout_dir / "enriched_claims.json").write_text(
            json.dumps({
                "api_surface_sha": "old-api-sha",
                "claims": [
                    {
                        "claim_id": "CLM-test-stale-enriched",
                        "text": "Stale enriched claim from a previous API surface.",
                        "kind": "api_method",
                    }
                ],
            }),
            encoding="utf-8",
        )

        promote_mod.promote("test", "python", knowledge_root=str(kr))

        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        claims = data if isinstance(data, list) else data.get("claims", [])
        claim_ids = {c["claim_id"] for c in claims}
        assert "CLM-test-stale-enriched" not in claim_ids


class TestPromoteFormatsNotePreservation:
    """Manually-annotated formats.json entries (with 'note' field) must survive promote."""

    def test_note_entries_preserved_when_absent_from_scout(self, tmp_path):
        """Entries with a 'note' field that are absent from scout output are re-injected."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        merged_dir = kr / "test" / "python" / "merged"

        # Write a scout formats.json without the note entry
        scout_formats = [
            {"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True},
        ]
        (scout_dir / "formats.json").write_text(
            json.dumps(scout_formats, indent=2), encoding="utf-8"
        )

        # Pre-create a merged/formats.json that includes a manually-annotated note entry
        merged_dir.mkdir(parents=True, exist_ok=True)
        existing_merged_formats = [
            {"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True},
            {
                "format": "TXT", "enum": "LoadFormat", "direction": "import",
                "functional": True,
                "note": "File-extension alias for TEXT LoadFormat; not emitted by scout",
            },
        ]
        (merged_dir / "formats.json").write_text(
            json.dumps(existing_merged_formats, indent=2), encoding="utf-8"
        )

        promote_mod.promote("test", "python", knowledge_root=str(kr))

        result_formats = json.loads(
            (merged_dir / "formats.json").read_text(encoding="utf-8")
        )
        keys = {(e["format"], e["enum"]) for e in result_formats}
        assert ("TXT", "LoadFormat") in keys, (
            "Note-annotated TXT entry must survive promote() even if absent from scout output"
        )

    def test_scout_entry_not_duplicated_when_present_in_both(self, tmp_path):
        """If a note-bearing entry is also in scout output, it must not be duplicated."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        merged_dir = kr / "test" / "python" / "merged"

        # Scout has OBJ entry
        scout_formats = [
            {"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True},
        ]
        (scout_dir / "formats.json").write_text(
            json.dumps(scout_formats, indent=2), encoding="utf-8"
        )

        # Merged has same OBJ entry (without note) plus a note-only TXT entry
        merged_dir.mkdir(parents=True, exist_ok=True)
        existing_merged = [
            {"format": "OBJ", "enum": "FileFormat", "direction": "export",
             "functional": True, "note": "also annotated"},
            {"format": "TXT", "enum": "LoadFormat", "direction": "import",
             "functional": True, "note": "alias"},
        ]
        (merged_dir / "formats.json").write_text(
            json.dumps(existing_merged, indent=2), encoding="utf-8"
        )

        promote_mod.promote("test", "python", knowledge_root=str(kr))

        result_formats = json.loads(
            (merged_dir / "formats.json").read_text(encoding="utf-8")
        )
        obj_entries = [e for e in result_formats if e["format"] == "OBJ"]
        assert len(obj_entries) == 1, "OBJ entry must not be duplicated"

    def test_manual_true_entry_preserved(self, tmp_path):
        """Entries with 'manual': True (no note key) must also be preserved."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        merged_dir = kr / "test" / "python" / "merged"

        scout_formats = [
            {"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True},
        ]
        (scout_dir / "formats.json").write_text(
            json.dumps(scout_formats, indent=2), encoding="utf-8"
        )

        merged_dir.mkdir(parents=True, exist_ok=True)
        existing_merged_formats = [
            {"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True},
            {
                "format": "CSV", "enum": "SaveFormat", "direction": "export",
                "functional": True,
                "manual": True,  # No "note" key — manual: true only
            },
        ]
        (merged_dir / "formats.json").write_text(
            json.dumps(existing_merged_formats, indent=2), encoding="utf-8"
        )

        promote_mod.promote("test", "python", knowledge_root=str(kr))

        result_formats = json.loads(
            (merged_dir / "formats.json").read_text(encoding="utf-8")
        )
        keys = {(e["format"], e["enum"]) for e in result_formats}
        assert ("CSV", "SaveFormat") in keys, (
            "Entry with manual:True (no note key) must survive promote()"
        )

    def test_malformed_entry_does_not_corrupt_preservation(self, tmp_path):
        """Entries missing 'format' and 'enum' keys must not cause (None, None) collisions."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        merged_dir = kr / "test" / "python" / "merged"

        scout_formats = [
            {"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True},
        ]
        (scout_dir / "formats.json").write_text(
            json.dumps(scout_formats, indent=2), encoding="utf-8"
        )

        merged_dir.mkdir(parents=True, exist_ok=True)
        existing_merged_formats = [
            {"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True},
            # Malformed entry: note field present but no format/enum keys
            {"note": "orphan annotation with no format or enum", "manual": True},
            # Well-formed note entry that SHOULD be preserved
            {"format": "TXT", "enum": "LoadFormat", "direction": "import",
             "functional": True, "note": "alias"},
        ]
        (merged_dir / "formats.json").write_text(
            json.dumps(existing_merged_formats, indent=2), encoding="utf-8"
        )

        # Should not raise; malformed entry is silently skipped
        promote_mod.promote("test", "python", knowledge_root=str(kr))

        result_formats = json.loads(
            (merged_dir / "formats.json").read_text(encoding="utf-8")
        )
        # Well-formed note entry still preserved
        keys = {(e.get("format"), e.get("enum")) for e in result_formats}
        assert ("TXT", "LoadFormat") in keys, "Well-formed note entry must survive"
        # No (None, None) key collision artifacts introduced
        none_entries = [e for e in result_formats
                        if e.get("format") is None and e.get("enum") is None]
        assert len(none_entries) == 0, "Malformed (None/None) entry must not appear in output"


class TestPromoteFormatsOverridesDurability:
    """RPR-J-03 (rescues SW-11): note/manual formats.json entries and the "Known
    Documentation Errors" block must survive a full knowledge/ rebuild (fresh clone),
    not just a plain re-run against an already-populated merged/ directory.
    """

    def test_note_entry_rescued_into_committed_override_on_first_run(self, tmp_path):
        """The first promote() after this fix must copy an existing ephemeral
        merged/formats.json note entry into the committed override store."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        merged_dir = kr / "test" / "python" / "merged"

        (scout_dir / "formats.json").write_text(
            json.dumps([{"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True}], indent=2),
            encoding="utf-8",
        )
        merged_dir.mkdir(parents=True, exist_ok=True)
        (merged_dir / "formats.json").write_text(
            json.dumps([
                {"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True},
                {"format": "TXT", "enum": "LoadFormat", "direction": "import", "functional": True,
                 "note": "File-extension alias for TEXT LoadFormat; not emitted by scout"},
            ], indent=2),
            encoding="utf-8",
        )

        promote_mod.promote("test", "python", knowledge_root=str(kr))

        override_path = kr / "_overrides" / "test" / "python" / "formats_overrides.json"
        assert override_path.exists(), "note entry must be rescued into the committed override store"
        rescued = json.loads(override_path.read_text(encoding="utf-8"))
        rescued_keys = {(e.get("format"), e.get("enum")) for e in rescued}
        assert ("TXT", "LoadFormat") in rescued_keys

    def test_note_entry_survives_full_knowledge_rebuild(self, tmp_path):
        """The real acceptance criterion: delete knowledge/ (except _overrides/) --
        simulating a fresh clone -- and rebuild. The note entry must still appear."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        merged_dir = kr / "test" / "python" / "merged"

        (scout_dir / "formats.json").write_text(
            json.dumps([{"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True}], indent=2),
            encoding="utf-8",
        )
        merged_dir.mkdir(parents=True, exist_ok=True)
        (merged_dir / "formats.json").write_text(
            json.dumps([
                {"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True},
                {"format": "TXT", "enum": "LoadFormat", "direction": "import", "functional": True,
                 "note": "File-extension alias for TEXT LoadFormat; not emitted by scout"},
            ], indent=2),
            encoding="utf-8",
        )

        # First run: rescues the note entry into the committed override store.
        promote_mod.promote("test", "python", knowledge_root=str(kr))

        # Simulate a fresh clone: knowledge/{family}/{platform}/{scout,merged}/ are
        # gitignored and gone; only knowledge/_overrides/ (committed) survives.
        import shutil as _shutil
        _shutil.rmtree(merged_dir)
        _shutil.rmtree(scout_dir)
        scout_dir.mkdir(parents=True)
        (scout_dir / "claims.json").write_text(json.dumps(SCOUT_CLAIMS, indent=2), encoding="utf-8")
        (scout_dir / "api_surface.json").write_text(json.dumps(API_SURFACE, indent=2), encoding="utf-8")
        (scout_dir / "model.yaml").write_text(yaml.dump(MODEL_YAML, default_flow_style=False), encoding="utf-8")
        (scout_dir / "formats.json").write_text(
            json.dumps([{"format": "OBJ", "enum": "FileFormat", "direction": "export", "functional": True}], indent=2),
            encoding="utf-8",
        )

        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is True

        result_formats = json.loads((merged_dir / "formats.json").read_text(encoding="utf-8"))
        keys = {(e["format"], e["enum"]) for e in result_formats}
        assert ("TXT", "LoadFormat") in keys, (
            "note entry must survive a full knowledge/ rebuild via the committed override, "
            "not just a re-run against an already-populated merged/ directory"
        )

    def test_known_errors_block_survives_full_knowledge_rebuild(self, tmp_path):
        """Same durability requirement for the 'Known Documentation Errors' section."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        merged_dir = kr / "test" / "python" / "merged"

        (scout_dir / "limitations.md").write_text("# Limitations\n\nAuto-detected stub.\n", encoding="utf-8")
        merged_dir.mkdir(parents=True, exist_ok=True)
        (merged_dir / "limitations.md").write_text(
            "# Limitations\n\nAuto-detected stub.\n\n"
            "## Known Documentation Errors\n\n- Foo.Bar is mislabeled upstream as deprecated.\n",
            encoding="utf-8",
        )

        promote_mod.promote("test", "python", knowledge_root=str(kr))

        override_path = kr / "_overrides" / "test" / "python" / "known_errors.md"
        assert override_path.exists()
        assert "Foo.Bar is mislabeled" in override_path.read_text(encoding="utf-8")

        # Simulate fresh clone: scout/merged gone, _overrides/ (committed) survives.
        import shutil as _shutil
        _shutil.rmtree(merged_dir)
        _shutil.rmtree(scout_dir)
        scout_dir.mkdir(parents=True)
        (scout_dir / "claims.json").write_text(json.dumps(SCOUT_CLAIMS, indent=2), encoding="utf-8")
        (scout_dir / "api_surface.json").write_text(json.dumps(API_SURFACE, indent=2), encoding="utf-8")
        (scout_dir / "model.yaml").write_text(yaml.dump(MODEL_YAML, default_flow_style=False), encoding="utf-8")
        (scout_dir / "limitations.md").write_text("# Limitations\n\nAuto-detected stub.\n", encoding="utf-8")

        promote_mod.promote("test", "python", knowledge_root=str(kr))

        result_lim = (merged_dir / "limitations.md").read_text(encoding="utf-8")
        assert "Foo.Bar is mislabeled" in result_lim, (
            "Known Documentation Errors block must survive a full knowledge/ rebuild"
        )


class TestPromoteWithMissingScout:
    """promote() must fail gracefully when scout/ artifacts are absent."""

    def test_missing_claims_json_returns_false(self, tmp_path):
        """promote() must return False if scout/claims.json is absent."""
        kr = tmp_path / "knowledge"
        scout_dir = kr / "test" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        # No claims.json
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is False

    def test_fl_directory_presence_returns_false(self, tmp_path):
        """promote() must return False if fl/ directory exists (guard against old layout)."""
        kr = _setup_scout(tmp_path)
        fl_dir = kr / "test" / "python" / "fl"
        fl_dir.mkdir(parents=True)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is False


# ---------------------------------------------------------------------------
# Test: api_surface.md modifier rendering
# ---------------------------------------------------------------------------

class TestApiSurfaceMdModifiers:
    """Verify that is_static/is_abstract/is_sealed render in api_surface.md."""

    def test_static_class_shows_modifier(self, tmp_path):
        """Class with is_static: true → '**Modifiers**: static' in markdown."""
        api_list = [
            {"name": "FieldDateTimeFormatter", "is_static": True,
             "methods": [], "properties": [], "bases": []},
        ]
        promote_mod._generate_api_surface_md(api_list, "pdf", {"repo_sha": "test"}, tmp_path)
        md = (tmp_path / "api_surface.md").read_text(encoding="utf-8")
        assert "**Modifiers**: static" in md

    def test_abstract_sealed_class_shows_modifiers(self, tmp_path):
        """Class with both is_abstract and is_sealed → both listed."""
        api_list = [
            {"name": "BaseProcessor", "is_abstract": True, "is_sealed": True,
             "methods": [], "properties": [], "bases": []},
        ]
        promote_mod._generate_api_surface_md(api_list, "pdf", {"repo_sha": "test"}, tmp_path)
        md = (tmp_path / "api_surface.md").read_text(encoding="utf-8")
        assert "**Modifiers**: abstract, sealed" in md

    def test_regular_class_no_modifier_line(self, tmp_path):
        """Class without modifier flags → no **Modifiers** line."""
        api_list = [
            {"name": "RegularClass",
             "methods": [], "properties": [], "bases": []},
        ]
        promote_mod._generate_api_surface_md(api_list, "pdf", {"repo_sha": "test"}, tmp_path)
        md = (tmp_path / "api_surface.md").read_text(encoding="utf-8")
        assert "**Modifiers**" not in md

    def test_false_modifier_no_line(self, tmp_path):
        """Class with is_static: false → no **Modifiers** line (falsy values)."""
        api_list = [
            {"name": "InstanceClass", "is_static": False,
             "methods": [], "properties": [], "bases": []},
        ]
        promote_mod._generate_api_surface_md(api_list, "pdf", {"repo_sha": "test"}, tmp_path)
        md = (tmp_path / "api_surface.md").read_text(encoding="utf-8")
        assert "**Modifiers**" not in md


# ---------------------------------------------------------------------------
# TC-A12: Promote edge-case tests (merge-conflict, idempotency, large-batch)
# ---------------------------------------------------------------------------

class TestPromoteEdgeCases:
    """TC-A12: merge-conflict, idempotency, and large-batch scenarios."""

    def test_promote_idempotent(self, tmp_path):
        """Running promote() twice on the same scout output produces identical merged/ output."""
        kr = _setup_scout(tmp_path)

        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_dir = kr / "test" / "python" / "merged"
        claims_after_first = json.loads((merged_dir / "claims.json").read_text(encoding="utf-8"))

        promote_mod.promote("test", "python", knowledge_root=str(kr))
        claims_after_second = json.loads((merged_dir / "claims.json").read_text(encoding="utf-8"))

        assert len(claims_after_first) == len(claims_after_second), (
            "Second promote run must not duplicate or lose claims"
        )
        ids_first = {c["claim_id"] for c in claims_after_first}
        ids_second = {c["claim_id"] for c in claims_after_second}
        assert ids_first == ids_second, "Claim IDs must be identical after idempotent promote"

    def test_promote_conflicting_claim_later_wins(self, tmp_path):
        """When merged/ has a stale claim text and scout/ has updated text, scout wins."""
        kr = _setup_scout(tmp_path)
        merged_dir = kr / "test" / "python" / "merged"
        scout_dir = kr / "test" / "python" / "scout"

        # Pre-create merged/ claims with an old text for CLM-test-p1-001
        stale_claims = [
            {"claim_id": "CLM-test-p1-001", "text": "STALE TEXT", "kind": "api_method"},
        ]
        merged_dir.mkdir(parents=True, exist_ok=True)
        (merged_dir / "claims.json").write_text(
            json.dumps(stale_claims, indent=2), encoding="utf-8"
        )

        # Scout has the updated text for the same ID
        fresh_scout_claims = [
            {
                "claim_id": "CLM-test-p1-001",
                "text": "Scene.open(filename) loads a 3D file.",
                "kind": "api_method",
            }
        ]
        (scout_dir / "claims.json").write_text(
            json.dumps(fresh_scout_claims, indent=2), encoding="utf-8"
        )

        promote_mod.promote("test", "python", knowledge_root=str(kr))

        merged_claims = json.loads((merged_dir / "claims.json").read_text(encoding="utf-8"))
        claim_001 = next((c for c in merged_claims if c["claim_id"] == "CLM-test-p1-001"), None)
        assert claim_001 is not None, "CLM-test-p1-001 must exist in merged output"
        assert "STALE" not in claim_001["text"], (
            "Scout text must overwrite stale merged text on promote"
        )

    def test_promote_large_batch_no_truncation(self, tmp_path):
        """promote() must handle 100+ classes without truncating or dropping any."""
        kr = tmp_path / "knowledge"
        scout_dir = kr / "test" / "python" / "scout"
        scout_dir.mkdir(parents=True)

        large_api_surface = [
            {
                "name": f"Class{i:03d}",
                "kind": "class_declaration",
                "methods": [{"name": f"method{i}"}],
                "properties": [],
            }
            for i in range(120)
        ]
        large_claims = [
            {"claim_id": f"CLM-large-{i:04d}", "text": f"Class{i:03d}.method{i}() description.", "kind": "api_method"}
            for i in range(120)
        ]

        (scout_dir / "claims.json").write_text(
            json.dumps(large_claims, indent=2), encoding="utf-8"
        )
        (scout_dir / "api_surface.json").write_text(
            json.dumps(large_api_surface, indent=2), encoding="utf-8"
        )
        # Minimal model.yaml required by promote()
        (scout_dir / "model.yaml").write_text(
            "family: test\nplatform: python\nrepo_sha: abc123\nstale_since: null\n",
            encoding="utf-8",
        )

        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is True, "promote() must succeed with 120-class input"

        merged_dir = kr / "test" / "python" / "merged"
        merged_claims = json.loads((merged_dir / "claims.json").read_text(encoding="utf-8"))
        merged_apis = json.loads((merged_dir / "api_surface.json").read_text(encoding="utf-8"))

        assert len(merged_claims) == 120, (
            f"All 120 claims must appear in merged output; got {len(merged_claims)}"
        )
        assert len(merged_apis) == 120, (
            f"All 120 API classes must appear in merged output; got {len(merged_apis)}"
        )


# ---------------------------------------------------------------------------
# Enriched-claims staleness check — ST-020 Gap 4
# ---------------------------------------------------------------------------

class TestPromoteEnrichedClaimsStaleness:
    """promote() warns when enriched_claims.json was built from a different api_surface."""

    def _setup_with_enriched(
        self,
        tmp_path: Path,
        api_surface_sha: str,
    ) -> Path:
        """Create a minimal scout tree with an enriched_claims.json."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        enriched = {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "model": "gpt-oss",
            "source": "enrich.py (S-37)",
            "family": "test",
            "platform": "python",
            "api_surface_sha": api_surface_sha,
            "claim_count": 1,
            "claims": [
                {
                    "claim_id": "CLM-enriched-01",
                    "text": "Enriched claim one.",
                    "kind": "description",
                    "confidence": 0.9,
                }
            ],
        }
        (scout_dir / "enriched_claims.json").write_text(
            json.dumps(enriched, indent=2), encoding="utf-8"
        )
        return kr

    def test_enriched_claims_merged_when_sha_matches(self, tmp_path, capsys):
        """Enriched claims are included with no warning when SHA matches."""
        import hashlib
        # Compute the SHA of the actual scout api_surface.json that promote() will read.
        # _setup_with_enriched calls _setup_scout which writes API_SURFACE to scout/; compute
        # SHA from the same data so the stored SHA matches.
        current_sha = hashlib.sha256(
            json.dumps(API_SURFACE, sort_keys=True).encode()
        ).hexdigest()[:16]

        kr = self._setup_with_enriched(tmp_path, api_surface_sha=current_sha)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))

        assert result is True
        captured = capsys.readouterr()
        assert "stale" not in captured.out.lower()
        # Enriched claim must appear in merged output
        merged_claims = json.loads(
            (kr / "test" / "python" / "merged" / "claims.json").read_text(encoding="utf-8")
        )
        claim_ids = {c["claim_id"] for c in merged_claims}
        assert "CLM-enriched-01" in claim_ids

    def test_enriched_claims_warn_when_sha_differs(self, tmp_path, capsys):
        """promote() emits a WARNING when enriched_claims.json has a stale SHA."""
        kr = self._setup_with_enriched(tmp_path, api_surface_sha="deadbeef00000000")
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))

        assert result is True  # promote succeeds even with stale enrichment
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "stale" in captured.out.lower()

    def test_enriched_claims_no_sha_field_no_warn(self, tmp_path, capsys):
        """Older enriched_claims.json without api_surface_sha field: no warning emitted."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        # Write enriched_claims without api_surface_sha
        enriched = {
            "claims": [
                {
                    "claim_id": "CLM-old-01",
                    "text": "Old enriched claim.",
                    "kind": "description",
                    "confidence": 0.9,
                }
            ]
        }
        (scout_dir / "enriched_claims.json").write_text(
            json.dumps(enriched, indent=2), encoding="utf-8"
        )
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))

        assert result is True
        captured = capsys.readouterr()
        assert "stale" not in captured.out.lower()


# ---------------------------------------------------------------------------
# TC-02/TC-03: enrichment_status and source fields in model.yaml
# ---------------------------------------------------------------------------

class TestEnrichmentStatusAndSource:

    def test_full_enrichment_status(self, tmp_path):
        import yaml
        family, platform = "cells", "python"
        base = tmp_path / "knowledge" / family / platform
        scout_dir = base / "scout"
        merged_dir = base / "merged"
        scout_dir.mkdir(parents=True)
        merged_dir.mkdir(parents=True)
        scout_model = {
            "product_name": "Aspose.Cells for Python",
            "version": "24.1", "license": "proprietary",
            "repo_url": "https://github.com/aspose-cells/Aspose.Cells-for-Python",
            "repo_sha": "abc123",
        }
        (scout_dir / "model.yaml").write_text(yaml.dump(scout_model), encoding="utf-8")
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "workbook.py", "methods": [], "properties": [], "enum_members": []}
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        scout_claims = [
            {"claim_id": "CLM-cells-python-001", "text": "Scout claim.", "kind": "api",
             "confidence": 0.9, "grounding": ["Workbook"], "provenance": "tree-sitter"}
        ]
        (scout_dir / "claims.json").write_text(json.dumps(scout_claims), encoding="utf-8")
        enriched = {
            "claims": [
                {"claim_id": "ERC-cells-python-aabb", "text": "Enriched claim.", "kind": "api",
                 "confidence": 0.85, "grounding": ["Workbook"]}
            ]
        }
        (scout_dir / "enriched_claims.json").write_text(json.dumps(enriched), encoding="utf-8")
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from promote import promote
        result = promote(family, platform, knowledge_root=str(tmp_path / "knowledge"))
        assert result is True
        model_data = yaml.safe_load((merged_dir / "model.yaml").read_text(encoding="utf-8"))
        assert model_data["enrichment_status"] == "full"
        assert model_data["source"] == "scout_and_enriched"

    def test_scout_only_status(self, tmp_path):
        import yaml
        family, platform = "cells", "python"
        base = tmp_path / "knowledge" / family / platform
        scout_dir = base / "scout"
        merged_dir = base / "merged"
        scout_dir.mkdir(parents=True)
        merged_dir.mkdir(parents=True)
        scout_model = {
            "product_name": "Aspose.Cells for Python",
            "version": "24.1", "license": "proprietary",
            "repo_url": "https://github.com/aspose-cells/Aspose.Cells-for-Python",
            "repo_sha": "abc123",
        }
        (scout_dir / "model.yaml").write_text(yaml.dump(scout_model), encoding="utf-8")
        api_surface = [
            {"name": "Workbook", "doc": "A workbook.", "kind": "class",
             "file": "workbook.py", "methods": [], "properties": [], "enum_members": []}
        ]
        (scout_dir / "api_surface.json").write_text(json.dumps(api_surface), encoding="utf-8")
        scout_claims = [
            {"claim_id": "CLM-cells-python-001", "text": "Scout claim.", "kind": "api",
             "confidence": 0.9, "grounding": ["Workbook"], "provenance": "tree-sitter"}
        ]
        (scout_dir / "claims.json").write_text(json.dumps(scout_claims), encoding="utf-8")
        from promote import promote
        result = promote(family, platform, knowledge_root=str(tmp_path / "knowledge"))
        assert result is True
        model_data = yaml.safe_load((merged_dir / "model.yaml").read_text(encoding="utf-8"))
        assert model_data["enrichment_status"] == "scout-only"
        assert model_data["source"] == "scout_only"


class TestClaimIdCollisionDetection:
    """HARDEN-words-net (2026-07-22): CLM claim_ids are a 6-hex-char (24-bit)
    hash of claim text (extraction/api_surface.py::_make_claim) — a product
    with several thousand claims (words/net: 4171) carries real
    birthday-paradox collision risk. Found while investigating a live
    "20 duplicate CLM claim_id(s)" warning on words/net's first bootstrap
    (verified empirically to be 0 real collisions on words/net itself — all
    20 were identical text, e.g. from a C# partial class scanned across
    multiple files).

    An initial version of this fix hard-failed promote() on any real
    collision. An adversarial review then swept ALL 26 live products' scout
    data and found 7 already-shipped products (3d/java, 3d/net, pdf/java,
    pdf/net, slides/java, slides/net, slides/python) have REAL pre-existing
    collisions — including one confirmed case of already-silently-lost data
    in pdf/net (a "Heading.Top property" claim, dropped in favor of an
    unrelated "Form.SetXfaFieldValues" claim sharing the same hash). Hard-
    failing would have turned "silently succeeds" into "hard blocks" for all
    7 the next time any of them refreshes, with no forewarning.

    Final design: two DIFFERENT claims sharing an id are NEVER silently
    resolved by keeping only the first (real data loss) — but instead of
    aborting, the second (and any further) distinct-text claim is re-hashed
    with more context (text + evidence file + line) so BOTH survive under
    distinct ids. Loud WARNING either way; promote() never fails purely
    because of a hash collision."""

    def _setup_scout_with_claims(self, tmp_path, claims):
        knowledge_root = tmp_path / "knowledge"
        scout_dir = knowledge_root / "test" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        (scout_dir / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
        (scout_dir / "api_surface.json").write_text(json.dumps(API_SURFACE), encoding="utf-8")
        (scout_dir / "model.yaml").write_text(
            yaml.dump(MODEL_YAML, default_flow_style=False), encoding="utf-8"
        )
        return knowledge_root

    def test_identical_text_duplicate_is_safely_deduped(self, tmp_path):
        """The common, harmless case: same claim_id, same text -- silently
        dedupe, promote still succeeds."""
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "Document.Save(string) writes a file.", "kind": "api_method"},
            {"claim_id": "CLM-test-abc123", "text": "Document.Save(string) writes a file.", "kind": "api_method"},
            {"claim_id": "CLM-test-def456", "text": "Shape.Type is the shape's type.", "kind": "api_property"},
        ]
        kr = self._setup_scout_with_claims(tmp_path, claims)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is True

        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        merged = data if isinstance(data, list) else data.get("claims", [])
        assert sum(1 for c in merged if c["claim_id"] == "CLM-test-abc123") == 1

    def test_real_collision_both_claims_survive_under_distinct_ids(self, tmp_path, capsys):
        """The rare, dangerous case: same claim_id, DIFFERENT text -- a true
        hash collision. Must NOT abort, and must NOT silently keep only one --
        both claims must survive, the second under a freshly re-hashed id."""
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "Document.Save(string) writes a file.",
             "kind": "api_method", "evidence": [{"file": "document.py", "line": 10}]},
            {"claim_id": "CLM-test-abc123", "text": "Shape.Anchor sets the shape's anchor point.",
             "kind": "api_property", "evidence": [{"file": "shape.py", "line": 20}]},
        ]
        kr = self._setup_scout_with_claims(tmp_path, claims)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is True, "a hash collision must never fail promote() -- it must be resolved, not aborted"

        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        merged = data if isinstance(data, list) else data.get("claims", [])
        texts = {c["text"] for c in merged}
        assert "Document.Save(string) writes a file." in texts, "first claim must survive"
        assert "Shape.Anchor sets the shape's anchor point." in texts, "second claim must ALSO survive, not be dropped"
        ids = [c["claim_id"] for c in merged]
        assert len(ids) == len(set(ids)), "every surviving claim must have a UNIQUE id"

        out = capsys.readouterr().out
        assert "COLLISION" in out or "collision" in out.lower()

    def test_real_collision_rehashed_id_still_matches_clm_format(self, tmp_path):
        """The re-hashed id must still be a valid CLM-{family}-{hex} shape --
        scripts/ci or downstream claim_id validators assume this format."""
        import re
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "Document.Save(string) writes a file.",
             "kind": "api_method", "evidence": [{"file": "document.py", "line": 10}]},
            {"claim_id": "CLM-test-abc123", "text": "Shape.Anchor sets the shape's anchor point.",
             "kind": "api_property", "evidence": [{"file": "shape.py", "line": 20}]},
        ]
        kr = self._setup_scout_with_claims(tmp_path, claims)
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        merged = data if isinstance(data, list) else data.get("claims", [])
        clm_format = re.compile(r"^CLM-[a-zA-Z0-9]+-[0-9a-f]{4,}$")
        for c in merged:
            assert clm_format.match(c["claim_id"]), f"malformed claim_id: {c['claim_id']}"

    def test_three_way_collision_two_identical_one_different(self, tmp_path):
        """2 identical-text + 1 different-text sharing one id -- the
        different one must be detected and re-hashed even though it's a
        minority, not a majority-vote miss."""
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "Document.Save(string) writes a file.",
             "kind": "api_method", "evidence": [{"file": "document.py", "line": 10}]},
            {"claim_id": "CLM-test-abc123", "text": "Document.Save(string) writes a file.",
             "kind": "api_method", "evidence": [{"file": "document.py", "line": 10}]},
            {"claim_id": "CLM-test-abc123", "text": "Totally unrelated claim about Shape.Anchor.",
             "kind": "api_property", "evidence": [{"file": "shape.py", "line": 99}]},
        ]
        kr = self._setup_scout_with_claims(tmp_path, claims)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is True

        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        merged = data if isinstance(data, list) else data.get("claims", [])
        texts = {c["text"] for c in merged}
        assert "Document.Save(string) writes a file." in texts
        assert "Totally unrelated claim about Shape.Anchor." in texts
        # the 2 identical-text entries collapse to 1, the different one gets its own id
        assert sum(1 for c in merged if c["claim_id"] == "CLM-test-abc123") == 1

    def test_real_words_net_data_zero_real_collisions_all_dedupe_safely(self, tmp_path):
        """Regression guard mirroring the actual words/net finding: 20
        duplicate CLM ids that are ALL identical-text must still just dedupe
        (no spurious re-hashing), proving the collision path doesn't fire on
        harmless data."""
        claims = [
            {"claim_id": "CLM-test-same01", "text": "Repeated claim text.", "kind": "api_method"},
            {"claim_id": "CLM-test-same01", "text": "Repeated claim text.", "kind": "api_method"},
            {"claim_id": "CLM-test-same01", "text": "Repeated claim text.", "kind": "api_method"},
        ]
        kr = self._setup_scout_with_claims(tmp_path, claims)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is True
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        merged = data if isinstance(data, list) else data.get("claims", [])
        assert sum(1 for c in merged if c["claim_id"] == "CLM-test-same01") == 1

    def test_repeat_of_non_first_rehashed_text_collapses_to_one_id(self, tmp_path):
        """HARDEN-words-net finding-1 (adversarial re-review, 2026-07-22): a
        group of [A(first), B, B, C] sharing one id must collapse the two "B"
        copies to a SINGLE re-hashed id, not two different ones -- tracking
        only the first-seen text per group missed this because B is not the
        first occurrence."""
        claims = [
            {"claim_id": "CLM-test-shared1", "text": "Claim A -- the first occurrence.",
             "kind": "api_method", "evidence": [{"file": "a.py", "line": 1}]},
            {"claim_id": "CLM-test-shared1", "text": "Claim B -- differs from first, appears twice.",
             "kind": "api_method", "evidence": [{"file": "b.py", "line": 2}]},
            {"claim_id": "CLM-test-shared1", "text": "Claim B -- differs from first, appears twice.",
             "kind": "api_method", "evidence": [{"file": "b.py", "line": 2}]},
            {"claim_id": "CLM-test-shared1", "text": "Claim C -- also differs from first.",
             "kind": "api_method", "evidence": [{"file": "c.py", "line": 3}]},
        ]
        kr = self._setup_scout_with_claims(tmp_path, claims)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))
        assert result is True

        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        merged = data if isinstance(data, list) else data.get("claims", [])
        b_entries = [c for c in merged if c["text"] == "Claim B -- differs from first, appears twice."]
        assert len(b_entries) == 1, "the two identical 'Claim B' copies must collapse to ONE surviving entry"
        ids = [c["claim_id"] for c in merged]
        assert len(ids) == len(set(ids)), "every surviving claim must have a unique id"
        texts = {c["text"] for c in merged}
        assert texts == {
            "Claim A -- the first occurrence.",
            "Claim B -- differs from first, appears twice.",
            "Claim C -- also differs from first.",
        }

    def test_malformed_evidence_shape_does_not_crash(self, tmp_path):
        """HARDEN-words-net finding-2 (adversarial re-review, 2026-07-22): a
        claim with a malformed `evidence` entry (e.g. a bare string instead
        of a {file, line} dict -- possible from hand-authored
        supplemental_claims.json) must not crash promote() when it's part of
        a real collision needing a re-hash."""
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "Document.Save(string) writes a file.",
             "kind": "api_method", "evidence": ["not-a-dict-just-a-string"]},
            {"claim_id": "CLM-test-abc123", "text": "Shape.Anchor sets the shape's anchor point.",
             "kind": "api_property", "evidence": ["also-not-a-dict"]},
        ]
        kr = self._setup_scout_with_claims(tmp_path, claims)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))  # must not raise
        assert result is True
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        merged = data if isinstance(data, list) else data.get("claims", [])
        texts = {c["text"] for c in merged}
        assert "Document.Save(string) writes a file." in texts
        assert "Shape.Anchor sets the shape's anchor point." in texts

    def test_evidence_container_itself_malformed_does_not_crash(self, tmp_path):
        """HARDEN-words-net finding-2, round 2 (fourth adversarial re-review,
        2026-07-22): the first fix for finding-2 only validated
        evidence[0]'s TYPE, never checked that `evidence` itself is a list at
        all -- a scalar or bare-dict `evidence` value (exactly the mistake a
        hand-authored supplemental_claims.json entry would make: writing
        {"file": ..., "line": ...} instead of [{"file": ..., "line": ...}])
        still crashed promote() with TypeError/KeyError. This must never
        crash regardless of what shape `evidence` takes."""
        claims = [
            {"claim_id": "CLM-test-int1", "text": "Document.Save(string) writes a file.",
             "kind": "api_method", "evidence": 123},
            {"claim_id": "CLM-test-int1", "text": "Shape.Anchor sets the shape's anchor point.",
             "kind": "api_property", "evidence": {"file": "x.py", "line": 1}},
        ]
        kr = self._setup_scout_with_claims(tmp_path, claims)
        result = promote_mod.promote("test", "python", knowledge_root=str(kr))  # must not raise
        assert result is True
        merged_path = kr / "test" / "python" / "merged" / "claims.json"
        data = json.loads(merged_path.read_text(encoding="utf-8"))
        merged = data if isinstance(data, list) else data.get("claims", [])
        texts = {c["text"] for c in merged}
        assert "Document.Save(string) writes a file." in texts
        assert "Shape.Anchor sets the shape's anchor point." in texts


class TestValidateClaimsTypeChecking:
    """HARDEN-words-net (2026-07-22): after 5 rounds of adversarial review
    found 6 real crashes downstream of _validate_claims -- all traceable to
    it checking only that 'text'/'kind' KEYS were present, never that
    claim_id/text VALUES had the right type, and never touching evidence's
    shape at all -- this is the fix at the recommended structural level: a
    single upfront gate (already the one every claims source passes
    through) now enforces those types once, instead of patching each
    downstream access site individually."""

    def test_non_string_claim_id_is_quarantined(self):
        """Bug A from round 5: a JSON-number claim_id (a very plausible
        unquoted-id typo in hand-authored supplemental_claims.json) used to
        crash promote()'s uniqueness gate at `cid.startswith("ERC-")`."""
        claims = [
            {"claim_id": 12345, "text": "Some claim.", "kind": "api_method"},
            {"claim_id": "CLM-test-abc123", "text": "A valid claim.", "kind": "api_method"},
        ]
        result = promote_mod._validate_claims(claims, "test")
        assert len(result) == 1
        assert result[0]["claim_id"] == "CLM-test-abc123"

    def test_none_text_is_quarantined(self):
        """Bug B from round 5: `"text": null` used to crash the collision
        WARNING printer's `sorted()` call (str vs NoneType comparison)."""
        claims = [
            {"claim_id": "CLM-test-null1", "text": None, "kind": "api_method"},
            {"claim_id": "CLM-test-abc123", "text": "A valid claim.", "kind": "api_method"},
        ]
        result = promote_mod._validate_claims(claims, "test")
        assert len(result) == 1
        assert result[0]["text"] == "A valid claim."

    def test_non_string_text_is_quarantined(self):
        claims = [
            {"claim_id": "CLM-test-int1", "text": 42, "kind": "api_method"},
        ]
        result = promote_mod._validate_claims(claims, "test")
        assert result == []

    def test_missing_claim_id_still_allowed(self):
        """No claim_id at all is existing, unchanged behavior (a claim can
        legitimately lack an id, e.g. some hand-authored supplemental
        entries) -- only a claim_id of the WRONG TYPE is new-quarantined."""
        claims = [
            {"text": "A claim with no id.", "kind": "api_method"},
        ]
        result = promote_mod._validate_claims(claims, "test")
        assert len(result) == 1

    def test_non_list_evidence_normalized_not_quarantined(self):
        """Evidence is supplementary, not identity-critical -- a malformed
        evidence value normalizes the claim (coerced to []), it does not
        quarantine the whole claim the way a bad claim_id/text does."""
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "A claim.", "kind": "api_method",
             "evidence": {"file": "x.py", "line": 1}},
        ]
        result = promote_mod._validate_claims(claims, "test")
        assert len(result) == 1
        assert result[0]["evidence"] == []

    def test_evidence_list_with_mixed_valid_invalid_entries_filtered(self):
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "A claim.", "kind": "api_method",
             "evidence": [{"file": "a.py", "line": 1}, "garbage", 42, None]},
        ]
        result = promote_mod._validate_claims(claims, "test")
        assert len(result) == 1
        assert result[0]["evidence"] == [{"file": "a.py", "line": 1}]

    def test_end_to_end_non_string_claim_id_in_collision_group_does_not_crash(self, tmp_path):
        """The exact real-world shape from round-5 Bug A, run through the
        full promote() pipeline, not just _validate_claims in isolation."""
        knowledge_root = tmp_path / "knowledge"
        scout_dir = knowledge_root / "test" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        claims = [
            {"claim_id": 999, "text": "Duplicate-id-shape claim A.", "kind": "api_method"},
            {"claim_id": 999, "text": "Duplicate-id-shape claim A.", "kind": "api_method"},
        ]
        (scout_dir / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
        (scout_dir / "api_surface.json").write_text(json.dumps(API_SURFACE), encoding="utf-8")
        (scout_dir / "model.yaml").write_text(
            yaml.dump(MODEL_YAML, default_flow_style=False), encoding="utf-8")
        result = promote_mod.promote("test", "python", knowledge_root=str(knowledge_root))  # must not raise
        assert result is True

    def test_end_to_end_none_text_in_collision_group_does_not_crash(self, tmp_path):
        """The exact real-world shape from round-5 Bug B, run through the
        full promote() pipeline."""
        knowledge_root = tmp_path / "knowledge"
        scout_dir = knowledge_root / "test" / "python" / "scout"
        scout_dir.mkdir(parents=True)
        claims = [
            {"claim_id": "CLM-test-nulltxt", "text": None, "kind": "api_method"},
            {"claim_id": "CLM-test-nulltxt", "text": "Real text sharing the id.", "kind": "api_method"},
        ]
        (scout_dir / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
        (scout_dir / "api_surface.json").write_text(json.dumps(API_SURFACE), encoding="utf-8")
        (scout_dir / "model.yaml").write_text(
            yaml.dump(MODEL_YAML, default_flow_style=False), encoding="utf-8")
        result = promote_mod.promote("test", "python", knowledge_root=str(knowledge_root))  # must not raise
        assert result is True

    def test_non_string_kind_is_normalized_not_quarantined(self):
        """HARDEN-words-net round 6/7: a non-string 'kind' (e.g. a list)
        used to crash _semantic_dedup_claims's frozenset membership check
        (`kind_i in _EXACT_ONLY_KINDS` -- unhashable type). kind is
        supplementary here (not identity-critical the way claim_id/text
        are), so it's normalized, not quarantined."""
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "A claim.", "kind": ["not", "a", "string"]},
        ]
        result = promote_mod._validate_claims(claims, "test")
        assert len(result) == 1
        assert result[0]["kind"] == ""

    def test_non_numeric_confidence_is_normalized_not_quarantined(self):
        """HARDEN-words-net round 6/7: a None/non-numeric 'confidence' used
        to crash _semantic_dedup_claims's `ci >= cj` comparison."""
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "A claim.", "kind": "api_method",
             "confidence": None},
        ]
        result = promote_mod._validate_claims(claims, "test")
        assert len(result) == 1
        assert result[0]["confidence"] == 0

    def test_non_string_description_is_normalized_not_quarantined(self):
        """HARDEN-words-net round 6/7: when 'text' is legitimately "" (an
        empty string, which passes the str-type check), _semantic_dedup_claims
        falls back to `description` -- a non-string description there used
        to crash `.strip()`."""
        claims = [
            {"claim_id": "CLM-test-abc123", "text": "", "kind": "api_method",
             "description": None},
        ]
        result = promote_mod._validate_claims(claims, "test")
        assert len(result) == 1
        assert result[0]["description"] == ""

    def test_semantic_dedup_survives_all_three_malformed_fields_end_to_end(self):
        """The exact composition that matters: claims pass through
        _validate_claims (as they always do in the real promote() pipeline)
        BEFORE reaching _semantic_dedup_claims -- confirming the two
        functions compose correctly to close round 6/7's findings, not just
        that _validate_claims normalizes fields in isolation."""
        raw_claims = [
            {"claim_id": "CLM-test-k1", "text": "Claim with bad kind.",
             "kind": {"not": "a string"}, "confidence": 0.9},
            {"claim_id": "CLM-test-k2", "text": "Claim with bad confidence.",
             "kind": "feature", "confidence": "high"},
            {"claim_id": "CLM-test-k3", "text": "", "kind": "feature",
             "confidence": 0.9, "description": 12345},
        ]
        validated = promote_mod._validate_claims(raw_claims, "test")
        assert len(validated) == 3
        result = promote_mod._semantic_dedup_claims(validated)  # must not raise
        assert len(result) == 3


class TestReconcileFormatsClaimsFunctionalAware:
    """HARDEN-words-net (2026-07-22): _reconcile_formats_claims only checked
    `direction` (an enum-level signal: "this format enum member represents
    export"), never `functional` (whether it's actually reachable). Once
    extraction/formats.py's FOSS-gate override correctly marks a gated format
    functional=False, a claim confirming "not supported" for that SAME format
    is CONFIRMATION of the data, not a contradiction — but the reconciliation
    check kept firing anyway because it never looked at functional. Found
    live: words/net's HTML format, correctly re-classified functional=False,
    still printed a "format-claims contradiction" warning against the
    accurate "HTML... not supported" enriched claim."""

    def test_functional_false_format_is_not_flagged_as_contradiction(self):
        formats_data = [
            {"format": "Html", "direction": "export", "functional": False},
        ]
        claims = [
            {"text": "HTML and other formats are not supported in this open-source edition."},
        ]
        result = promote_mod._reconcile_formats_claims(formats_data, claims, "words", "net")
        assert result == [], "a confirmed-non-functional format matching its own 'not supported' claim is not a contradiction"

    def test_functional_true_format_still_flagged(self):
        """The check must still fire for genuinely contradictory data --
        this fix narrows a false positive, it must not blind the check."""
        formats_data = [
            {"format": "Html", "direction": "export", "functional": True},
        ]
        claims = [
            {"text": "HTML and other formats are not supported in this open-source edition."},
        ]
        result = promote_mod._reconcile_formats_claims(formats_data, claims, "words", "net")
        assert len(result) == 1
        assert result[0]["format"] == "Html"

    def test_functional_absent_still_flagged(self):
        """Formats predating this fix (no functional key at all) must not
        silently bypass the check -- only an EXPLICIT False skips it."""
        formats_data = [
            {"format": "Html", "direction": "export"},
        ]
        claims = [
            {"text": "HTML and other formats are not supported in this open-source edition."},
        ]
        result = promote_mod._reconcile_formats_claims(formats_data, claims, "words", "net")
        assert len(result) == 1


class TestFormatsMdRespectsFunctionalFlag:
    """HARDEN-words-net (2026-07-23): promote()'s formats.md table builder
    set Import/Export "Yes" purely from `direction`, never checking
    `functional` at all -- so a FOSS-gated format (functional=False,
    confirmed unreachable via an explicit NotSupportedException in the real
    dispatch factory) still rendered as supported in the human-readable
    formats.md table. Confirmed live on words/net: HTML/EPUB/MHTML/Azw3/Mobi
    all showed "Yes" in both columns despite being genuinely unsupported in
    this FOSS edition. formats.md is read by the truth-audit and
    stale-detect skills, so this is not merely cosmetic."""

    def test_functional_false_format_not_rendered_as_supported(self, tmp_path):
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        (scout_dir / "formats.json").write_text(json.dumps([
            {"format": "Html", "direction": "export", "functional": False},
            {"format": "Html", "direction": "import", "functional": False},
        ]), encoding="utf-8")
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_md = kr / "test" / "python" / "merged" / "formats.md"
        lines = merged_md.read_text(encoding="utf-8").splitlines()
        html_line = next((l for l in lines if l.strip().startswith("| HTML")), None)
        assert html_line is not None, "HTML row must still appear in formats.md"
        assert "| - | - |" in html_line.replace(" ", "") or "|-|-|" in html_line.replace(" ", ""), (
            f"functional=False HTML must show as unsupported in both columns, got: {html_line!r}"
        )

    def test_functional_true_format_still_rendered_as_supported(self, tmp_path):
        """The fix must not blind formats.md to genuinely supported formats."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        (scout_dir / "formats.json").write_text(json.dumps([
            {"format": "Docx", "direction": "export", "functional": True},
        ]), encoding="utf-8")
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_md = kr / "test" / "python" / "merged" / "formats.md"
        lines = merged_md.read_text(encoding="utf-8").splitlines()
        docx_line = next((l for l in lines if l.strip().startswith("| DOCX")), None)
        assert docx_line is not None
        assert "Yes" in docx_line

    def test_functional_absent_still_rendered_as_supported(self, tmp_path):
        """Legacy/non-enum entries with no `functional` key at all must not
        be silently dropped from the table -- only an EXPLICIT False hides
        a row's support flag."""
        kr = _setup_scout(tmp_path)
        scout_dir = kr / "test" / "python" / "scout"
        (scout_dir / "formats.json").write_text(json.dumps([
            {"format": "Markdown", "direction": "export"},
        ]), encoding="utf-8")
        promote_mod.promote("test", "python", knowledge_root=str(kr))
        merged_md = kr / "test" / "python" / "merged" / "formats.md"
        lines = merged_md.read_text(encoding="utf-8").splitlines()
        md_line = next((l for l in lines if l.strip().startswith("| MARKDOWN")), None)
        assert md_line is not None
        assert "Yes" in md_line

