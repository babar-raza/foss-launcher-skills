def test_set_compression_level(self):
        # ExStart:SetCompressionLevel
        save_options = aw.saving.OoxmlSaveOptions()
        save_options.compression_level = aw.saving.CompressionLevel.MAXIMUM

        self.convert(
            "test_full_article.docx",
            "OoxmlSaveOptions.max_compression.docx",
            save_options=save_options,
        )
        # ExEnd:SetCompressionLevel