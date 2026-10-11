def test_attached_file_metadata_is_read_only(self) -> None:
        from aspose.note import AttachedFile, NoteTag

        attached = AttachedFile(FileName="doc.bin", Bytes=b"abc", Tags=[NoteTag.CreateYellowStar("Важно")])

        with self.assertRaises(AttributeError):
            attached.FileName = "other.bin"

        with self.assertRaises(AttributeError):
            attached.Bytes = b"xyz"

        attached.Tags.append(NoteTag.CreateQuestionMark("Вопрос"))
        self.assertEqual([tag.Label for tag in attached.Tags], ["Важно", "Вопрос"])