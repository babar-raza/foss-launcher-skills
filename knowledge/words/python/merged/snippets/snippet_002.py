def test_get_text_from_all_formats(self):
        """Extract plain text via get_text() from every input format."""
        for in_label, in_file in INPUT_FILES.items():
            doc = aw.Document(MY_DIR + in_file)
            text = doc.get_text()
            assert len(text) > 0, f"get_text() returned empty for {in_file}"