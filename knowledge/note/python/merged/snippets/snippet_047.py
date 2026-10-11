def test_richtext_has_some_non_default_style(self) -> None:
        from aspose.note import Document, RichText

        doc = Document(self.path)
        rts = doc.GetChildNodes(RichText)

        # Look for any run with a meaningful style attribute.
        def is_styled(rt: RichText) -> bool:
            for run in rt.TextRuns:
                s = run.Style
                if (
                    s.IsBold
                    or s.IsItalic
                    or s.IsUnderline
                    or s.IsStrikethrough
                    or s.IsSuperscript
                    or s.IsSubscript
                    or (s.FontName is not None)
                    or (s.FontSize is not None)
                    or (s.FontColor is not None)
                    or (s.Highlight is not None)
                    or (s.HyperlinkAddress is not None)
                ):
                    return True
            return False

        if not any(rt.TextRuns for rt in rts):
            raise unittest.SkipTest("No RichText nodes with runs extracted")

        self.assertTrue(any(is_styled(rt) for rt in rts))