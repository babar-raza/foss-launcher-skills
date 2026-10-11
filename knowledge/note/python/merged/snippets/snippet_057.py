def test_formatted_richtext_run_boundaries_align_with_visible_text(self) -> None:
        from aspose.note import Document, RichText

        doc = Document(self.path)
        target = next(
            rt for rt in doc.GetChildNodes(RichText) if "hyperlink. This text is not a hyperlink." in rt.Text
        )

        visible_runs = [(run.Text, run.Style) for run in target.TextRuns if run.Text and "HYPERLINK" not in run.Text]
        texts = [text for text, _ in visible_runs]

        self.assertIn("This", texts)
        self.assertIn("text", texts)
        self.assertIn("is ", texts)
        self.assertIn("not", texts)
        self.assertIn("hyperlink", texts)

        style_by_text = {text: style for text, style in visible_runs}
        self.assertEqual(style_by_text["This"].Highlight, 65535)
        self.assertTrue(style_by_text["text"].IsBold)
        self.assertEqual(style_by_text["is "].Highlight, 16776960)
        self.assertTrue(style_by_text["not"].IsItalic)
        self.assertTrue(style_by_text["hyperlink"].IsUnderline)