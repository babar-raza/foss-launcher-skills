"""VERIFY-04: Tests for the heal -> verify -> persist lifecycle.

Validates the write-policy and manifest interaction after content healing:
  1. After body improvement, the write policy gate returns True (should write)
  2. After body improvement with NO grade change, the write policy gate returns False
  3. The manifest is updated even when frontmatter is not written
  4. Manifest entry reflects the new content hash after healing
  5. Policy gate correctly distinguishes grade-band-crossing from same-band
  6. End-to-end: write_grade + manifest_entry lifecycle

Reference: grading-remediation plan VERIFY-04
"""
from __future__ import annotations

import json
import sys
import tempfile
import textwrap
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from grade_manifest import (
    load_manifest,
    read_manifest_entry,
    save_manifest,
    write_manifest_entry,
)
from grade_writer import (
    _should_write_canonical_grade,
    content_hash,
    read_grade,
    write_grade,
)


def _tmp_file(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    )
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


# ---------------------------------------------------------------------------
# Policy gate after body improvement
# ---------------------------------------------------------------------------

class TestPolicyGateAfterHealing:
    """After a heal pass improves the body, the policy gate must allow or
    suppress frontmatter writes correctly based on grade change."""

    def test_body_improved_grade_improved_should_write(self):
        """After body improvement that raises the grade (e.g. D->B),
        the write policy gate must return True."""
        p = _tmp_file("---\ntitle: Heal Test\n---\nOriginal weak body.\n")
        try:
            # Establish initial low grade
            write_grade(p, "D", grade_reasons=["missing-api-docs"])
            stored = read_grade(p)
            old_hash = stored["content_hash"]

            # Simulate body improvement -> new content hash
            new_body_hash = content_hash("Improved body with API examples.\n")
            assert new_body_hash != old_hash, "Sanity: body hash should differ"

            # Policy gate: body changed AND grade changed (D->B) -> should write
            should, reason = _should_write_canonical_grade(p, "B", new_body_hash)
            assert should is True
            assert "body-changed-grade-changed" in reason
        finally:
            p.unlink(missing_ok=True)

    def test_body_improved_grade_unchanged_should_not_write(self):
        """After body improvement with NO grade change (still C),
        the write policy gate must return False."""
        p = _tmp_file("---\ntitle: No Grade Change\n---\nOriginal body.\n")
        try:
            write_grade(p, "C", grade_reasons=["minor-issues"])
            stored = read_grade(p)
            old_hash = stored["content_hash"]

            # Simulate body improvement that doesn't change grade
            new_body_hash = content_hash("Slightly improved body.\n")
            assert new_body_hash != old_hash

            # Policy gate: body changed but grade unchanged -> should NOT write
            should, reason = _should_write_canonical_grade(p, "C", new_body_hash)
            assert should is False
            assert "body-changed-grade-unchanged" in reason
        finally:
            p.unlink(missing_ok=True)

    def test_grade_band_crossing_always_writes(self):
        """A grade-band crossing (e.g. C->B) should always trigger a write,
        even if the body hash happens to be unchanged (edge case)."""
        p = _tmp_file("---\ntitle: Band Cross\n---\nBody.\n")
        try:
            write_grade(p, "C")
            stored = read_grade(p)
            same_hash = stored["content_hash"]

            # Same body hash but grade improved C->B
            should, reason = _should_write_canonical_grade(p, "B", same_hash)
            assert should is True
            assert "grade-band-crossing" in reason
        finally:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Manifest updated even when frontmatter is not written
# ---------------------------------------------------------------------------

class TestManifestUpdatedWithoutFrontmatter:
    """The manifest must be updated even when the frontmatter write is
    suppressed by the policy gate (ARCH-03)."""

    def test_manifest_entry_written_independently(self, tmp_path):
        """write_manifest_entry works independently of frontmatter writes."""
        manifest_file = tmp_path / "grade_manifest.json"
        manifest = {}

        rel_path = "content/docs.aspose.org/en/fake/python/getting-started.md"
        body_hash = content_hash("Some body content.\n")

        manifest = write_manifest_entry(
            rel_path,
            content_hash=body_hash,
            grade="C",
            grade_reasons=["minor-issues"],
            evaluator_versions={"api_accuracy": "2", "structure": "1"},
            model_sha="abc123",
            logic_version="16",
            enrichment_status="full",
            manifest=manifest,
            manifest_path=manifest_file,
            save=True,
        )

        # Verify manifest was written to disk
        assert manifest_file.exists()
        loaded = load_manifest(manifest_file)
        entry = read_manifest_entry(rel_path, loaded)
        assert entry is not None
        assert entry["grade"] == "C"
        assert entry["content_hash"] == body_hash
        assert entry["evaluator_versions"]["api_accuracy"] == "2"

    def test_manifest_reflects_new_hash_after_heal(self, tmp_path):
        """After healing changes the body, the manifest entry must contain
        the new content hash, even if frontmatter was not updated."""
        manifest_file = tmp_path / "grade_manifest.json"
        manifest = {}
        rel_path = "content/docs.aspose.org/en/fake/python/api-reference.md"

        # Initial entry
        old_hash = content_hash("Old body.\n")
        manifest = write_manifest_entry(
            rel_path, content_hash=old_hash, grade="C",
            manifest=manifest, manifest_path=manifest_file, save=True,
        )

        # Heal: body changes, manifest updated with new hash
        new_hash = content_hash("Improved body with examples.\n")
        assert new_hash != old_hash
        manifest = write_manifest_entry(
            rel_path, content_hash=new_hash, grade="C",
            manifest=manifest, manifest_path=manifest_file, save=True,
        )

        loaded = load_manifest(manifest_file)
        entry = read_manifest_entry(rel_path, loaded)
        assert entry["content_hash"] == new_hash, (
            "Manifest must reflect new content hash after heal"
        )

    def test_manifest_save_false_defers_disk_write(self, tmp_path):
        """When save=False, the manifest dict is updated but disk is not."""
        manifest_file = tmp_path / "grade_manifest.json"
        manifest = {}

        manifest = write_manifest_entry(
            "some/path.md",
            content_hash="abc",
            grade="B",
            manifest=manifest,
            manifest_path=manifest_file,
            save=False,
        )

        # In-memory dict has the entry
        assert "some/path.md" in manifest
        # But file was not written
        assert not manifest_file.exists()

        # Now save explicitly
        save_manifest(manifest, manifest_file)
        assert manifest_file.exists()
        loaded = load_manifest(manifest_file)
        assert "some/path.md" in loaded


# ---------------------------------------------------------------------------
# End-to-end lifecycle: heal -> policy gate -> manifest
# ---------------------------------------------------------------------------

class TestHealLifecycleEndToEnd:
    """Integration test: simulate a heal pass and verify both the policy
    gate decision and manifest state are correct."""

    def test_heal_improves_grade_full_lifecycle(self, tmp_path):
        """Simulate: page at D -> heal -> re-eval at B -> write frontmatter
        + update manifest."""
        p = _tmp_file("---\ntitle: E2E\n---\nWeak original body.\n")
        manifest_file = tmp_path / "grade_manifest.json"
        manifest = {}
        rel_path = str(p).replace("\\", "/")

        try:
            # Step 1: Initial grade D
            write_grade(p, "D", grade_reasons=["missing-examples"])
            stored = read_grade(p)
            old_hash = stored["content_hash"]

            # Record in manifest
            manifest = write_manifest_entry(
                rel_path, content_hash=old_hash, grade="D",
                grade_reasons=["missing-examples"],
                manifest=manifest, manifest_path=manifest_file, save=True,
            )

            # Step 2: Heal the page (simulate body rewrite)
            text = p.read_text(encoding="utf-8")
            new_text = text.replace(
                "Weak original body.",
                "Strong body with code examples and API docs.",
            )
            p.write_text(new_text, encoding="utf-8")

            # Step 3: Re-evaluate -> grade improves to B
            # Compute new body hash
            parts = new_text.split("---", 2)
            new_body = parts[2] if len(parts) >= 3 else ""
            new_hash = content_hash(new_body)
            assert new_hash != old_hash

            # Policy gate: body changed + grade changed (D->B) -> should write
            should, reason = _should_write_canonical_grade(p, "B", new_hash)
            assert should is True

            # Step 4: Write frontmatter with policy mode
            result = write_grade(
                p, "B", grade_reasons=["good-examples"],
                write_mode="policy",
            )
            assert result is True
            final = read_grade(p)
            assert final["grade"] == "B"

            # Step 5: Update manifest
            manifest = write_manifest_entry(
                rel_path, content_hash=new_hash, grade="B",
                grade_reasons=["good-examples"],
                manifest=manifest, manifest_path=manifest_file, save=True,
            )

            entry = read_manifest_entry(rel_path, manifest)
            assert entry["grade"] == "B"
            assert entry["content_hash"] == new_hash
        finally:
            p.unlink(missing_ok=True)

    def test_heal_no_grade_change_manifest_still_updated(self, tmp_path):
        """When healing improves body but grade stays the same, frontmatter
        is NOT rewritten but the manifest IS updated with the new hash."""
        p = _tmp_file("---\ntitle: No Change\n---\nOriginal body.\n")
        manifest_file = tmp_path / "grade_manifest.json"
        manifest = {}
        rel_path = str(p).replace("\\", "/")

        try:
            # Initial grade C
            write_grade(p, "C")
            text_after_grade = p.read_text(encoding="utf-8")
            stored = read_grade(p)
            old_hash = stored["content_hash"]

            manifest = write_manifest_entry(
                rel_path, content_hash=old_hash, grade="C",
                manifest=manifest, manifest_path=manifest_file, save=True,
            )

            # Heal: body changes slightly but grade stays C
            text = p.read_text(encoding="utf-8")
            new_text = text.replace("Original body.", "Slightly better body.")
            p.write_text(new_text, encoding="utf-8")

            parts = new_text.split("---", 2)
            new_body = parts[2] if len(parts) >= 3 else ""
            new_hash = content_hash(new_body)

            # Policy gate says no write (body changed, grade unchanged)
            should, reason = _should_write_canonical_grade(p, "C", new_hash)
            assert should is False

            # write_grade with policy mode -> skip frontmatter
            result = write_grade(p, "C", write_mode="policy")
            assert result is True  # policy-skip, not error

            # But manifest IS updated with the new hash
            manifest = write_manifest_entry(
                rel_path, content_hash=new_hash, grade="C",
                manifest=manifest, manifest_path=manifest_file, save=True,
            )

            entry = read_manifest_entry(rel_path, manifest)
            assert entry["content_hash"] == new_hash, (
                "Manifest must be updated even when frontmatter write is suppressed"
            )
        finally:
            p.unlink(missing_ok=True)
