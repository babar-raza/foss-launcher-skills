def test_open_and_save(self):
        """Load from stream, then save to file."""
        with io.FileIO(MY_DIR + "test_full_article.docx") as stream:
            doc = aw.Document(stream)

        doc.save(ARTIFACTS_DIR + "LoadingDocument.OpenAndSave.md", aw.SaveFormat.MARKDOWN)
        assert Path(ARTIFACTS_DIR + "LoadingDocument.OpenAndSave.md").exists()