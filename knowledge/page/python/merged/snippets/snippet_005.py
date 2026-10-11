def test_skip_without_tools(self):
        with EnvGuard(PDF_COMPARE_CMD="", PDF_RENDER_CMD=""):
            with self.assertRaises(unittest.SkipTest):
                compare_pdfs(Path("baseline.pdf"), Path("actual.pdf"))