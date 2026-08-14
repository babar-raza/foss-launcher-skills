def test_encrypted_load_raises_incorrect_password(self) -> None:
        from aspose.note import Document, IncorrectPasswordException, LoadOptions

        p = _fixture_path("FormattedRichText.one")
        if p is None:
            raise unittest.SkipTest("FormattedRichText.one not found")

        with self.assertRaises(IncorrectPasswordException):
            Document(p, LoadOptions(DocumentPassword="pass"))