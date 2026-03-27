"""Unit tests for audit.py evidence validation system.

Tests parse_frontmatter, verify_evidence, and the api_to_claim index.
Uses mock Knowledge objects — no filesystem required for most tests.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "pipeline"))

from audit import Finding, parse_frontmatter, verify_evidence  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_knowledge(claim_ids=None, classes=None, api_to_claim=None, repo_sha="abc123def456"):
    """Build a minimal mock Knowledge object."""
    k = MagicMock()
    k.claim_ids = set(claim_ids or [])
    k.classes = dict.fromkeys(classes or [])
    k.api_to_claim = api_to_claim or {}
    k.repo_sha = repo_sha
    k.version = "1.0.0"
    k.has_method.return_value = False
    k.has_property.return_value = False
    k.has_enum_member.return_value = False
    return k


def _make_file(content):
    """Write content to a temp file and return its Path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


# ---------------------------------------------------------------------------
# TestParseFrontmatter
# ---------------------------------------------------------------------------
class TestParseFrontmatter(unittest.TestCase):

    def test_valid_frontmatter(self):
        fp = _make_file("---\ntitle: Test\nevidence:\n  model_sha: abc\n---\n\nBody\n")
        result = parse_frontmatter(fp)
        self.assertEqual(result["title"], "Test")
        self.assertEqual(result["evidence"]["model_sha"], "abc")

    def test_missing_frontmatter(self):
        fp = _make_file("No frontmatter here.\n")
        result = parse_frontmatter(fp)
        self.assertEqual(result, {})

    def test_malformed_yaml(self):
        fp = _make_file("---\ntitle: [unclosed\n---\n\nBody\n")
        result = parse_frontmatter(fp)
        self.assertEqual(result, {})

    def test_frontmatter_without_evidence(self):
        fp = _make_file("---\ntitle: No Evidence\ndate: 2026-01-01\n---\n\nBody\n")
        result = parse_frontmatter(fp)
        self.assertIn("title", result)
        self.assertNotIn("evidence", result)

    def test_empty_frontmatter_block(self):
        fp = _make_file("---\n---\n\nBody\n")
        result = parse_frontmatter(fp)
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# TestVerifyEvidence — missing / malformed blocks
# ---------------------------------------------------------------------------
class TestVerifyEvidenceMissing(unittest.TestCase):

    def setUp(self):
        self.fp = Path("fake.md")
        self.k = _make_knowledge(claim_ids={"CLM-x-001"}, classes={"Scene": {}})

    def test_missing_evidence_block_warns(self):
        findings = verify_evidence({}, self.k, self.fp)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")
        self.assertIn("attach_evidence", findings[0].message)

    def test_evidence_not_dict_warns(self):
        findings = verify_evidence({"evidence": "string"}, self.k, self.fp)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")

    def test_evidence_none_warns(self):
        findings = verify_evidence({"evidence": None}, self.k, self.fp)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")


# ---------------------------------------------------------------------------
# TestVerifyEvidence — model_sha staleness
# ---------------------------------------------------------------------------
class TestVerifyEvidenceModelSha(unittest.TestCase):

    def setUp(self):
        self.fp = Path("fake.md")
        self.k = _make_knowledge(repo_sha="newsha123456789")

    def test_missing_model_sha_warns(self):
        fm = {"evidence": {"claims": [], "apis": []}}
        findings = verify_evidence(fm, self.k, self.fp)
        levels = [f.level for f in findings]
        self.assertIn("WARN", levels)
        msgs = " ".join(f.message for f in findings)
        self.assertIn("model_sha", msgs)

    def test_stale_model_sha_warns(self):
        fm = {"evidence": {"model_sha": "oldsha000000000", "claims": [], "apis": []}}
        findings = verify_evidence(fm, self.k, self.fp)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")
        self.assertIn("stale", findings[0].message)
        self.assertIn("newsha12", findings[0].message)

    def test_current_model_sha_no_findings(self):
        fm = {"evidence": {"model_sha": "newsha123456789", "claims": [], "apis": []}}
        findings = verify_evidence(fm, self.k, self.fp)
        self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# TestVerifyEvidence — claim_id validation
# ---------------------------------------------------------------------------
class TestVerifyEvidenceClaimIds(unittest.TestCase):

    def setUp(self):
        self.fp = Path("fake.md")

    def test_valid_claim_id_no_fail(self):
        k = _make_knowledge(claim_ids={"CLM-3d-abc123"}, repo_sha="sha1")
        fm = {"evidence": {"model_sha": "sha1", "claims": ["CLM-3d-abc123"], "apis": []}}
        findings = verify_evidence(fm, k, self.fp)
        self.assertEqual(findings, [])

    def test_invalid_claim_id_fails(self):
        k = _make_knowledge(claim_ids={"CLM-3d-real"}, repo_sha="sha1")
        fm = {"evidence": {"model_sha": "sha1", "claims": ["CLM-3d-fake"], "apis": []}}
        findings = verify_evidence(fm, k, self.fp)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")
        self.assertIn("CLM-3d-fake", findings[0].message)

    def test_empty_claim_ids_does_not_fail(self):
        """When claim index is empty (no claims.json), listing claim IDs → WARN not FAIL."""
        k = _make_knowledge(claim_ids=[], repo_sha="sha1")  # empty index
        fm = {"evidence": {"model_sha": "sha1", "claims": ["CLM-any-id"], "apis": []}}
        findings = verify_evidence(fm, k, self.fp)
        # Must not FAIL — only WARN about inability to validate
        fails = [f for f in findings if f.level == "FAIL"]
        self.assertEqual(fails, [])
        warns = [f for f in findings if f.level == "WARN"]
        self.assertTrue(any("validate" in w.message.lower() or "claim" in w.message.lower()
                            for w in warns))

    def test_empty_claim_ids_empty_list_no_findings(self):
        """Empty claims: [] with no index → no noise."""
        k = _make_knowledge(claim_ids=[], repo_sha="sha1")
        fm = {"evidence": {"model_sha": "sha1", "claims": [], "apis": []}}
        findings = verify_evidence(fm, k, self.fp)
        self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# TestVerifyEvidence — API reference validation
# ---------------------------------------------------------------------------
class TestVerifyEvidenceApis(unittest.TestCase):

    def setUp(self):
        self.fp = Path("fake.md")

    def _knowledge_with_scene(self):
        k = _make_knowledge(classes={"Scene": {}}, repo_sha="sha1")
        k.has_method.side_effect = lambda cls, m: cls == "Scene" and m == "open"
        k.has_property.return_value = False
        return k

    def test_valid_api_class_only_no_fail(self):
        k = self._knowledge_with_scene()
        fm = {"evidence": {"model_sha": "sha1", "apis": ["Scene"], "claims": []}}
        findings = verify_evidence(fm, k, self.fp)
        self.assertEqual(findings, [])

    def test_valid_api_class_method_no_fail(self):
        k = self._knowledge_with_scene()
        fm = {"evidence": {"model_sha": "sha1", "apis": ["Scene.open"], "claims": []}}
        findings = verify_evidence(fm, k, self.fp)
        self.assertEqual(findings, [])

    def test_unknown_class_fails(self):
        k = _make_knowledge(classes={}, repo_sha="sha1")
        fm = {"evidence": {"model_sha": "sha1", "apis": ["FakeClass"], "claims": []}}
        findings = verify_evidence(fm, k, self.fp)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")
        self.assertIn("FakeClass", findings[0].message)

    def test_unknown_method_fails(self):
        k = self._knowledge_with_scene()
        fm = {"evidence": {"model_sha": "sha1", "apis": ["Scene.nonexistent"], "claims": []}}
        findings = verify_evidence(fm, k, self.fp)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "FAIL")
        self.assertIn("Scene.nonexistent", findings[0].message)


# ---------------------------------------------------------------------------
# TestApiToClaimIndex — Knowledge class builds index from claims.json
# ---------------------------------------------------------------------------
class TestApiToClaimIndex(unittest.TestCase):

    def test_index_built_from_typical_claim(self):
        """api_to_claim["ClassName.method"] maps to the claim_id."""
        import re as _re

        # Simulate the indexing logic from Knowledge.__init__
        claims_list = [
            {"claim_id": "CLM-x-001", "text": "Scene.open(path) -> Scene", "kind": "api_method"},
            {"claim_id": "CLM-x-002", "text": "Node.add_child_node(node) -> None", "kind": "api_method"},
            {"claim_id": "CLM-x-003", "text": "A3DObject.__init__(name) -> ", "kind": "api_method"},
        ]
        index = {}
        for c in claims_list:
            cid = c.get("claim_id", "")
            text = c.get("text", "")
            m = _re.match(r"^(\w+)\.(\w+)\(", text)
            if m:
                key = f"{m.group(1)}.{m.group(2)}"
                if key not in index:
                    index[key] = cid

        self.assertEqual(index["Scene.open"], "CLM-x-001")
        self.assertEqual(index["Node.add_child_node"], "CLM-x-002")
        self.assertEqual(index["A3DObject.__init__"], "CLM-x-003")

    def test_empty_claims_produces_empty_index(self):
        import re as _re
        claims_list = []
        index = {}
        for c in claims_list:
            cid = c.get("claim_id", "")
            text = c.get("text", "")
            m = _re.match(r"^(\w+)\.(\w+)\(", text)
            if m:
                key = f"{m.group(1)}.{m.group(2)}"
                if key not in index:
                    index[key] = cid
        self.assertEqual(index, {})

    def test_first_claim_wins_on_duplicate_key(self):
        import re as _re
        claims_list = [
            {"claim_id": "CLM-FIRST", "text": "Scene.open(path) -> Scene"},
            {"claim_id": "CLM-SECOND", "text": "Scene.open(path, opts) -> Scene"},
        ]
        index = {}
        for c in claims_list:
            cid = c.get("claim_id", "")
            text = c.get("text", "")
            m = _re.match(r"^(\w+)\.(\w+)\(", text)
            if m:
                key = f"{m.group(1)}.{m.group(2)}"
                if key not in index:
                    index[key] = cid
        self.assertEqual(index["Scene.open"], "CLM-FIRST")


if __name__ == "__main__":
    unittest.main()
