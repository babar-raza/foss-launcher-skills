"""Tests for scripts/pipeline/commands/healing/prune_stale_evidence_apis.py.

Covers the exact bug caught and fixed during development of this tool (an
earlier version of _resolves() fell back to "bare class name exists" for any
dotted token, silently accepting fabricated members on real classes -- the
same shape as the fabricated evidence.apis entries this tool exists to
remove), plus the indent-matching convention this repo's generators actually
use (`apis:` key and its `- Item` bullets at the SAME indentation, not a
deeper one).
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMANDS_HEALING = _HERE.parent / "commands" / "healing"
if str(_COMMANDS_HEALING) not in sys.path:
    sys.path.insert(0, str(_COMMANDS_HEALING))

import prune_stale_evidence_apis as mod  # noqa: E402


def _known_tokens():
    return {
        "StyleCollection",
        "StyleCollection.Count",
        "StyleCollection.Add",
        "Bookmark",
        "Bookmark.Name",
    }


class TestResolves:
    def test_bare_class_resolves(self):
        assert mod._resolves("StyleCollection", _known_tokens())

    def test_known_qualified_member_resolves(self):
        assert mod._resolves("StyleCollection.Count", _known_tokens())

    def test_fabricated_member_on_real_class_does_not_resolve(self):
        # The exact regression class this tool exists to catch: the class is
        # real, the member is not. An earlier version of _resolves() fell
        # back to "class exists" here and wrongly returned True.
        assert not mod._resolves("StyleCollection.GetByName", _known_tokens())

    def test_unknown_class_does_not_resolve(self):
        assert not mod._resolves("TotallyMadeUpClass.Foo", _known_tokens())


class TestFindStaleApiLines:
    def test_same_indent_bullet_convention(self):
        # This repo's generators emit `apis:` and its `- Item` bullets at the
        # SAME indentation (not indented further) -- confirmed against real
        # generated frontmatter. A stricter-than-actual indent comparison
        # would silently find nothing to prune.
        text = (
            "evidence:\n"
            "  apis:\n"
            "  - StyleCollection\n"
            "  - StyleCollection.GetByName\n"
            "  formats:\n"
            "  - ext: docx\n"
        )
        stale = mod.find_stale_api_lines(text, _known_tokens())
        lines = text.split("\n")
        assert [lines[i].strip() for i in stale] == ["- StyleCollection.GetByName"]

    def test_nested_section_apis_block(self):
        text = (
            "evidence:\n"
            "  apis:\n"
            "  - StyleCollection\n"
            "  sections:\n"
            "  - heading: Intro\n"
            "    apis:\n"
            "    - Bookmark\n"
            "    - Bookmark.GetByName\n"
        )
        stale = mod.find_stale_api_lines(text, _known_tokens())
        lines = text.split("\n")
        assert [lines[i].strip() for i in stale] == ["- Bookmark.GetByName"]

    def test_clean_block_finds_nothing(self):
        text = (
            "evidence:\n"
            "  apis:\n"
            "  - StyleCollection\n"
            "  - StyleCollection.Count\n"
            "  formats:\n"
            "  - ext: docx\n"
        )
        assert mod.find_stale_api_lines(text, _known_tokens()) == []

    def test_sibling_key_ends_block(self):
        # A non-bullet, non-blank line (a new sibling key) must end the apis
        # block -- otherwise a bullet-shaped line under an unrelated later
        # key could be misclassified as a stale apis entry.
        text = (
            "evidence:\n"
            "  apis:\n"
            "  - StyleCollection\n"
            "  claims:\n"
            "  - CLM-words-abc123\n"
        )
        assert mod.find_stale_api_lines(text, _known_tokens()) == []


class TestPruneFile:
    def test_prune_removes_only_stale_lines(self, tmp_path):
        f = tmp_path / "page.md"
        f.write_text(
            "---\n"
            "title: Test\n"
            "evidence:\n"
            "  apis:\n"
            "  - StyleCollection\n"
            "  - StyleCollection.GetByName\n"
            "  - StyleCollection.Count\n"
            "---\n"
            "\n"
            "Body text mentioning StyleCollection.GetByName should be untouched.\n",
            encoding="utf-8",
        )
        result = mod.prune_file(f, _known_tokens(), dry_run=False)
        assert result["status"] == "PRUNED"
        assert result["removed"] == ["StyleCollection.GetByName"]

        new_text = f.read_text(encoding="utf-8")
        assert "- StyleCollection.GetByName" not in new_text
        assert "- StyleCollection\n" in new_text
        assert "- StyleCollection.Count" in new_text
        # Body prose is never touched, even though it repeats the same token.
        assert "Body text mentioning StyleCollection.GetByName should be untouched." in new_text

    def test_dry_run_does_not_write(self, tmp_path):
        f = tmp_path / "page.md"
        original = (
            "---\n"
            "evidence:\n"
            "  apis:\n"
            "  - StyleCollection.GetByName\n"
            "---\n"
            "Body\n"
        )
        f.write_text(original, encoding="utf-8")
        result = mod.prune_file(f, _known_tokens(), dry_run=True)
        assert result["status"] == "WOULD_PRUNE"
        assert f.read_text(encoding="utf-8") == original

    def test_clean_file_is_a_no_op(self, tmp_path):
        f = tmp_path / "page.md"
        text = (
            "---\n"
            "evidence:\n"
            "  apis:\n"
            "  - StyleCollection\n"
            "---\n"
            "Body\n"
        )
        f.write_text(text, encoding="utf-8")
        result = mod.prune_file(f, _known_tokens(), dry_run=False)
        assert result["status"] == "CLEAN"
        assert f.read_text(encoding="utf-8") == text
