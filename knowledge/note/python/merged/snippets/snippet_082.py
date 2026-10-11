def test_outline_element_tags_and_list_metadata(self) -> None:
        p = _fixture_path("NumberedListWithTags.one")
        if p is None:
            raise unittest.SkipTest("NumberedListWithTags.one not found")

        from aspose.note import Document, Outline, OutlineElement, RichText

        doc = Document(p)

        # This fixture is expected to contain two Outline blocks.
        outlines = doc.GetChildNodes(Outline)
        self.assertEqual(len(outlines), 2)

        # The page also contains a TagSizes-style numbered list (as shown in the fixture UI).
        tag_sizes_outline = next(
            (o for o in outlines if any(rt.Text == "66(6-9)" for rt in o.GetChildNodes(RichText))),
            None,
        )
        self.assertIsNotNone(tag_sizes_outline)

        oes_tag_sizes = tag_sizes_outline.GetChildNodes(OutlineElement)  # type: ignore[union-attr]
        tag_sizes_map = {
            _rt_text_and_labels(oe)[0]: _rt_text_and_labels(oe)[1]
            for oe in oes_tag_sizes
            if _rt_text_and_labels(oe)[0]
        }
        self.assertIn("66(6-9)", tag_sizes_map)
        self.assertIn("10(10-17)", tag_sizes_map)
        self.assertIn("18(18-23)", tag_sizes_map)
        self.assertTrue(any(t in {"24(24-…)", "24(242-…)"} for t in tag_sizes_map))
        for t in ("66(6-9)", "10(10-17)", "18(18-23)"):
            self.assertIn("Важно", tag_sizes_map[t])
        last_key = next(k for k in tag_sizes_map if k in {"24(24-…)", "24(242-…)"})
        self.assertIn("Важно", tag_sizes_map[last_key])

        # Find the outline that contains the "First"/"Second" numbered list.
        # (The TagSizes-style list is also numbered, so we cannot select by NumberList presence alone.)
        list_outline = next(
            (o for o in outlines if any(rt.Text == "First" for rt in o.GetChildNodes(RichText))),
            None,
        )
        self.assertIsNotNone(list_outline)

        # This outline should contain two top-level list groups (as shown in the fixture UI).
        top_level = [c for c in list_outline if isinstance(c, OutlineElement)]  # type: ignore[union-attr]
        self.assertEqual(len(top_level), 2)
        self.assertFalse(hasattr(top_level[0], "Tags"))
        self.assertFalse(hasattr(top_level[0], "IndentLevel"))

        # Verify concrete texts and concrete tag labels per top-level list group.
        text0, labels0 = _rt_text_and_labels(top_level[0])
        text1, labels1 = _rt_text_and_labels(top_level[1])
        self.assertEqual(text0, "First")
        self.assertEqual(text1, "Second")
        self.assertIn("Важно", labels0)
        self.assertIn("Вопрос", labels0)
        self.assertIn("Запланировать собрание", labels1)

        # Verify some nested items inside the first group.
        nested = [c for c in top_level[0] if isinstance(c, OutlineElement)]
        self.assertGreaterEqual(len(nested), 3)
        nested_map = {(_rt_text_and_labels(oe)[0]): _rt_text_and_labels(oe)[1] for oe in nested}
        self.assertIn("First-first", nested_map)
        self.assertIn("Важно", nested_map["First-first"])
        self.assertIn("Вопрос", nested_map["First-first"])
        self.assertIn("First-second", nested_map)
        self.assertIn("Важно", nested_map["First-second"])
        self.assertIn("Вопрос", nested_map["First-second"])
        self.assertIn("First-third", nested_map)
        self.assertIn("Контакт", nested_map["First-third"])
        self.assertIn("Послушать музыку", nested_map["First-third"])
        self.assertIn("Запланировать собрание", nested_map["First-third"])

        # Each top-level item should have list metadata.
        self.assertTrue(all(getattr(oe, "NumberList", None) is not None for oe in top_level))

        # The list should contain multiple distinct list formats (e.g., numeric/alpha/roman across nesting).
        all_oes = list_outline.GetChildNodes(OutlineElement)  # type: ignore[union-attr]
        formats = {
            getattr(getattr(oe, "NumberList", None), "Format", None)
            for oe in all_oes
            if getattr(oe, "NumberList", None) is not None
        }
        formats.discard(None)
        self.assertGreaterEqual(len(formats), 2)

        # Tags may be attached to RichText/Image/etc, not necessarily OutlineElement.
        tags = _collect_all_tags(doc)
        self.assertGreaterEqual(len(tags), 1)
        self.assertTrue(any(_tag_is_meaningful(t) for t in tags))
        doc.Save("NumberedListWithTags.pdf", SaveFormat.Pdf)