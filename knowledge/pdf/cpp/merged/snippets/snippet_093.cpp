TEST(CellImageSmoke, BackgroundImageBytesEmbed) {
    const std::string out =
        (std::filesystem::temp_directory_path() / "aspose_cellimg.pdf").string();
    const std::vector<std::byte> jpeg = ReadAllBytes(JpegFixture());
    ASSERT_GE(jpeg.size(), 2u);
    {
        Document doc{(FixtureRoot() / "hello_world.pdf").string()};
        Table table;
        table.Left(72.0f);
        table.Top(700.0f);
        table.ColumnWidths("120 120");
        table.DefaultCellBorder(BorderInfo{BorderSide::All, 1.0f});

        Row& row = table.Rows().Add();
        Cell& imgCell = row.Cells().Add();
        imgCell.BackgroundImage(jpeg);
        row.Cells().Add("label");

        doc.Pages()[1].Paragraphs().Add(table);  // table outlives Save
        doc.Save(out);
    }

    Document doc{out};
    // The cell image is now an image resource of the page.
    EXPECT_GE(doc.Pages()[1].Resources().Images().Count(), 1);
    std::filesystem::remove(out);
}