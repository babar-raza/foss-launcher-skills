def test_note_tag_read_only_members_match_dotnet_shape(self) -> None:
        from aspose.note import NoteTag, TagStatus

        tag = NoteTag.CreateQuestionMark("Question")

        self.assertEqual(tag.Status, TagStatus.Open)
        self.assertIsNone(tag.CompletedTime)

        with self.assertRaises(AttributeError):
            setattr(tag, "Status", TagStatus.Disabled)

        with self.assertRaises(AttributeError):
            setattr(tag, "CompletedTime", datetime(2024, 1, 3, tzinfo=timezone.utc))