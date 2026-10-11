"""Unit tests for dirty_classifier.py."""
import unittest
from dirty_classifier import classify_path, parse_porcelain, check_lane_conflicts

class TestClassifyPath(unittest.TestCase):
    def test_claude(self): self.assertEqual(classify_path(".claude/commands/commit.md"),"claude")
    def test_governance_root(self): self.assertEqual(classify_path("AGENTS.md"),"governance")
    def test_governance_docs(self): self.assertEqual(classify_path("docs/governance/write-boundaries.md"),"governance")
    def test_layouts(self): self.assertEqual(classify_path("layouts/shortcodes/foo.html"),"layouts")
    def test_themes(self): self.assertEqual(classify_path("themes/products/layouts/partials/support.html"),"themes")
    def test_configs(self): self.assertEqual(classify_path("configs/docs.aspose.org.toml"),"configs")
    def test_scripts(self): self.assertEqual(classify_path("scripts/pipeline/commands/ops/session_ledger.py"),"scripts")
    def test_data(self): self.assertEqual(classify_path("data/products.json"),"data")
    def test_knowledge(self): self.assertEqual(classify_path("knowledge/cells/java/merged/model.yaml"),"knowledge")
    def test_reports(self): self.assertEqual(classify_path("reports/session-state/123.json"),"reports")
    def test_content_docs(self): self.assertEqual(classify_path("content/docs.aspose.org/en/cells/java/foo.md"),"content-docs")
    def test_content_blog(self): self.assertEqual(classify_path("content/blog.aspose.org/cells/java/_index.md"),"content-blog")
    def test_content_kb(self): self.assertEqual(classify_path("content/kb.aspose.org/en/pdf/java/_index.md"),"content-kb")
    def test_content_reference(self): self.assertEqual(classify_path("content/reference.aspose.org/en/cells/java/cell/index.md"),"content-reference")
    def test_content_products(self): self.assertEqual(classify_path("content/products.aspose.org/en/cells/"),"content-products")
    def test_unknown(self): self.assertEqual(classify_path("random/file.txt"),"unknown")
    def test_backslash(self): self.assertEqual(classify_path("content\docs.aspose.org\en\cells\java\foo.md"),"content-docs")

class TestParsePorcelain(unittest.TestCase):
    def test_modified(self):
        r=parse_porcelain([" M content/docs.aspose.org/en/cells/java/foo.md"])
        self.assertEqual(r[0]["type"],"modified"); self.assertEqual(r[0]["category"],"content-docs")
    def test_untracked(self):
        r=parse_porcelain(["?? scripts/new.py"])
        self.assertEqual(r[0]["type"],"untracked")
    def test_staged(self):
        r=parse_porcelain(["A  content/docs.aspose.org/en/cells/java/new.md"])
        self.assertEqual(r[0]["type"],"staged")
    def test_forbidden(self):
        r=parse_porcelain([" M .claude/commands/commit.md"])
        self.assertTrue(r[0]["forbidden"])
    def test_multiple(self):
        self.assertEqual(len(parse_porcelain([" M .claude/a"," M data/b","?? scripts/c"])),3)
    def test_empty_ignored(self):
        self.assertEqual(len(parse_porcelain([""," M data/foo.json",""])),1)
    def test_renamed(self):
        r=parse_porcelain(["R  old.md -> new.md"])
        self.assertEqual(r[0]["file"],"new.md")

class TestCheckLaneConflicts(unittest.TestCase):
    def test_no_conflict(self):
        c=[{"file":"content/docs.aspose.org/en/pdf/java/foo.md","category":"content-docs"}]
        m=[{"lane_id":"LANE-A","owned_path_prefixes":["content/docs.aspose.org/en/cells/java/"]}]
        self.assertEqual(check_lane_conflicts(c,m),[])
    def test_conflict(self):
        c=[{"file":"content/docs.aspose.org/en/cells/java/foo.md","category":"content-docs"}]
        m=[{"lane_id":"LANE-A","owned_path_prefixes":["content/docs.aspose.org/en/cells/java/"]}]
        conflicts=check_lane_conflicts(c,m)
        self.assertEqual(len(conflicts),1); self.assertEqual(conflicts[0]["lane_id"],"LANE-A")

if __name__=="__main__": unittest.main()
