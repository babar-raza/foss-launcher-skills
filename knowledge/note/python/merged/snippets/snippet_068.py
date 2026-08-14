def test_question_tag_uses_distinct_color(self) -> None:
        from aspose.note.saving.pdf_writer import _tag_color

        self.assertEqual(_tag_color(15), (0.64, 0.32, 0.82))
        self.assertNotEqual(_tag_color(15), _tag_color(13))