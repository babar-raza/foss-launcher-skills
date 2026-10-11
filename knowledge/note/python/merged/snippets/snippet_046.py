def test_richtext_runs_preserved(self) -> None:
        from aspose.note import Document, RichText

        doc = Document(self.path)
        rts = doc.GetChildNodes(RichText)
        self.assertGreater(len(rts), 0)

        # At least one RichText node should carry extracted formatting runs.
        self.assertTrue(any(len(rt.TextRuns) > 0 for rt in rts))