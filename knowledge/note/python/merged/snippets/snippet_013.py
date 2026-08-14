def test_table_collections_are_read_only_properties(self) -> None:
        from aspose.note import NoteTag, Table, TableColumn

        table = Table(Tags=[NoteTag.CreateYellowStar("Важно")], Columns=[TableColumn(Width=70)])

        with self.assertRaises(AttributeError):
            table.Tags = []

        with self.assertRaises(AttributeError):
            table.Columns = []

        table.Tags.append(NoteTag.CreateQuestionMark("Вопрос"))
        table.Columns.append(TableColumn(Width=120))

        self.assertEqual([tag.Label for tag in table.Tags], ["Важно", "Вопрос"])
        self.assertEqual([column.Width for column in table.Columns], [70, 120])