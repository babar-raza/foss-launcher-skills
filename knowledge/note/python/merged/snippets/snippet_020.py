def test_richtext_replace_changes_text(self) -> None:
        from aspose.note import Document, RichText

        doc = Document(self.path)
        rts = doc.GetChildNodes(RichText)
        self.assertGreater(len(rts), 0)

        # Pick a non-empty node with a replaceable substring.
        target = None
        for rt in rts:
            if rt.Text and " " in rt.Text:
                target = rt
                break
        if target is None:
            raise unittest.SkipTest("No RichText nodes with replaceable content found")

        before = target.Text
        returned = target.Replace(" ", "  ")
        after = target.Text
        self.assertIs(returned, target)
        self.assertNotEqual(before, after)
        doc.Save("FormattedRichText.pdf", SaveFormat.Pdf)