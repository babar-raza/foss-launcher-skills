def test_skip_when_missing(self):
        with EnvGuard(PDF_VALIDATOR_CMD=""):
            with self.assertRaises(unittest.SkipTest):
                validate_pdf(Path("dummy.pdf"))