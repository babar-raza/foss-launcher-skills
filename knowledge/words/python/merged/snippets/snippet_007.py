def test_open_from_stream_with_load_options(self):
        """Load a document from a stream with explicit LoadOptions."""
        opts = aw.loading.LoadOptions()
        opts.load_format = aw.LoadFormat.DOCX

        with io.FileIO(MY_DIR + "test_full_article.docx") as stream:
            doc = aw.Document(stream, opts)
        assert len(doc.get_text()) > 0