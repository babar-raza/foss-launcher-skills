"""Integration tests for promote.py — full scout/ -> merged/ pipeline.

Covers the gaps not addressed by test_merge_determinism.py:
- api_surface.json is correctly promoted from scout/ to merged/
- model.yaml is written to merged/ with stale_since: null
- All scout claims land in merged/ with provenance="scout"
- merged/claims.json claim count matches scout input
"""

from __future__ import annotations

import json
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
