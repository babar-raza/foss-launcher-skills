def test_outline_has_coordinates_properties(self) -> None:
        from aspose.note import Document, Outline

        doc = Document(self.path)
        outlines = doc.GetChildNodes(Outline)
        self.assertGreaterEqual(len(outlines), 1)

        o = outlines[0]
        self.assertTrue(hasattr(o, "HorizontalOffset"))
        self.assertTrue(hasattr(o, "VerticalOffset"))
        self.assertTrue(hasattr(o, "MaxWidth"))
        self.assertFalse(hasattr(o, "X"))
        self.assertFalse(hasattr(o, "Y"))
        self.assertFalse(hasattr(o, "Width"))

        self.assertTrue(o.HorizontalOffset is None or isinstance(o.HorizontalOffset, float))
        self.assertTrue(o.VerticalOffset is None or isinstance(o.VerticalOffset, float))
        self.assertTrue(o.MaxWidth is None or isinstance(o.MaxWidth, float))