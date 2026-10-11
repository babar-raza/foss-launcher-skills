def test_image_read_only_metadata_stays_mutable_via_tags_collection(self) -> None:
        from aspose.note import Image, NoteTag

        image = Image(
            FileName="image.png",
            FilePath="C:/tmp/image.png",
            Format="png",
            Bytes=b"img",
            Width=10.0,
            Height=20.0,
            OriginalWidth=10.0,
            OriginalHeight=20.0,
            Tags=[NoteTag.CreateYellowStar("Важно")],
        )

        with self.assertRaises(AttributeError):
            image.FileName = "renamed.png"

        with self.assertRaises(AttributeError):
            image.Bytes = b"other"

        image.Tags.append(NoteTag.CreateQuestionMark("Вопрос"))
        self.assertEqual([tag.Label for tag in image.Tags], ["Важно", "Вопрос"])