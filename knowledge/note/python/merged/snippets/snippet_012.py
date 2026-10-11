def test_tables_exposed_with_rows_and_cells(self) -> None:
        from aspose.note import Document, Table, TableRow, TableCell

        doc = Document(self.path)
        tables = doc.GetChildNodes(Table)
        self.assertGreaterEqual(len(tables), 1)

        rows = doc.GetChildNodes(TableRow)
        cells = doc.GetChildNodes(TableCell)
        self.assertGreater(len(rows), 0)
        self.assertGreater(len(cells), 0)

        # Basic structural sanity: each TableRow should have at least 1 cell.
        for row in rows[:10]:
            self.assertGreaterEqual(len(list(row)), 1)