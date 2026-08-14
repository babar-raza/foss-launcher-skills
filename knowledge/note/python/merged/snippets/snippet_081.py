def test_richtext_tags_exposed(self) -> None:
        p = _fixture_path("TagSizes.one")
        if p is None:
            raise unittest.SkipTest("TagSizes.one not found")

        from aspose.note import Document, OutlineElement, RichText

        doc = Document(p)
        rts = doc.GetChildNodes(RichText)
        self.assertGreaterEqual(len(rts), 1)

        tagged = [rt for rt in rts if getattr(rt, "Tags", None)]
        self.assertGreaterEqual(len(tagged), 1)
        self.assertTrue(any(_tag_is_meaningful(tag) for rt in tagged for tag in rt.Tags))

        # Concrete texts from the numbered list shown in the fixture UI.
        oes = doc.GetChildNodes(OutlineElement)
        oe_texts = [_rt_text_and_labels(oe)[0] for oe in oes]
        oe_texts = [t for t in oe_texts if t]
        self.assertGreaterEqual(len(oe_texts), 4)
        self.assertIn("66(6-9)", oe_texts)
        self.assertIn("10(10-17)", oe_texts)
        self.assertIn("18(18-23)", oe_texts)
        self.assertTrue(any(t in {"24(24-…)", "24(242-…)"} for t in oe_texts))

        # Each of these list items is expected to carry the "Важно" tag.
        for expected_text in ("66(6-9)", "10(10-17)", "18(18-23)"):
            oe = next(o for o in oes if _rt_text_and_labels(o)[0] == expected_text)
            _, labels = _rt_text_and_labels(oe)
            self.assertIn("Важно", labels)

        # For the last one, accept both variants but still require the tag.
        oe_last = next(o for o in oes if _rt_text_and_labels(o)[0] in {"24(24-…)", "24(242-…)"})
        _, labels_last = _rt_text_and_labels(oe_last)
        self.assertIn("Важно", labels_last)