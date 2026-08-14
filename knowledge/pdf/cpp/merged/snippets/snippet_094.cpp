TEST(CellImageSmoke, BackgroundImageFileEmbeds) {
    const std::string out =
        (std::filesystem::temp_directory_path() / "aspose_cellimgf.pdf")
            .string();
    {
        Document doc{(FixtureRoot() / "hello_world.pdf").string()};
        Table table;
        table.ColumnWidths("150");
        Row& row = table.Rows().Add();
        Cell& cell = row.Cells().Add();
        cell.BackgroundImageFile(JpegFixture());
        doc.Pages()[1].Paragraphs().Add(table);
        doc.Save(out);
    }
    Document doc{out};
    EXPECT_GE(doc.Pages()[1].Resources().Images().Count(), 1);
    std::filesystem::remove(out);
}