def test_richtext_collection_properties_are_read_only(self) -> None:
        from aspose.note import NoteTag, RichText, TextRun

        rich_text = RichText(TextRuns=[TextRun(Text="segment")], Tags=[NoteTag.CreateYellowStar("Важно")])

        with self.assertRaises(AttributeError):
            setattr(rich_text, "TextRuns", [TextRun(Text="other")])

        with self.assertRaises(AttributeError):
            setattr(rich_text, "Tags", [])

        rich_text.TextRuns.append(TextRun(Text=" tail"))
        rich_text.Tags.append(NoteTag.CreateQuestionMark("Вопрос"))

        self.assertEqual(rich_text.Text, "segment tail")
        self.assertEqual([tag.Label for tag in rich_text.Tags], ["Важно", "Вопрос"])