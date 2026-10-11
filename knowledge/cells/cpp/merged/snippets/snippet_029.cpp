TEST(CellDataGoldenTests, styled_cells_roundtrip_and_emit_stylesheet)
{
    TempDir temp("golden-styles");
    const auto path = temp.Path("styles.xlsx");
    auto workbook = CreateStyledWorkbook();
    workbook.Save(path.string());

    ASSERT_TRUE(Package::EntryExists(path, "xl/styles.xml"));
    const auto stylesheetXml = Package::ReadEntryText(path, "xl/styles.xml");
    const auto worksheetXml = Package::ReadEntryText(path, "xl/worksheets/sheet1.xml");

    EXPECT_TRUE(Contains(stylesheetXml, "Arial"));
    EXPECT_TRUE(Contains(stylesheetXml, "0.0000"));
    EXPECT_TRUE(Contains(stylesheetXml, "<strike"));
    EXPECT_TRUE(Contains(stylesheetXml, "patternType=\"lightGrid\""));
    EXPECT_TRUE(Contains(stylesheetXml, "fgColor rgb=\"FFD2DC1E\""));
    EXPECT_TRUE(Contains(stylesheetXml, "bgColor rgb=\"FF0C2D4E\""));
    EXPECT_TRUE(Contains(stylesheetXml, "style=\"dotted\""));
    EXPECT_TRUE(Contains(stylesheetXml, "style=\"mediumDashDot\""));
    EXPECT_TRUE(Contains(stylesheetXml, "style=\"double\""));
    EXPECT_TRUE(Contains(stylesheetXml, "style=\"dashDotDot\""));
    EXPECT_TRUE(Contains(stylesheetXml, "style=\"slantDashDot\""));
    EXPECT_TRUE(Contains(stylesheetXml, "diagonalUp=\"1\""));
    EXPECT_TRUE(Contains(stylesheetXml, "diagonalDown=\"1\""));
    EXPECT_TRUE(Contains(stylesheetXml, "horizontal=\"distributed\""));
    EXPECT_TRUE(Contains(stylesheetXml, "vertical=\"distributed\""));
    EXPECT_TRUE(Contains(stylesheetXml, "indent=\"2\""));
    EXPECT_TRUE(Contains(stylesheetXml, "textRotation=\"45\""));
    EXPECT_TRUE(Contains(stylesheetXml, "shrinkToFit=\"1\""));
    EXPECT_TRUE(Contains(stylesheetXml, "readingOrder=\"2\""));
    EXPECT_TRUE(Contains(stylesheetXml, "relativeIndent=\"1\""));
    EXPECT_TRUE(Contains(stylesheetXml, "wrapText=\"1\""));
    EXPECT_TRUE(Contains(stylesheetXml, "locked=\"0\""));
    EXPECT_TRUE(Contains(stylesheetXml, "hidden=\"1\""));
    EXPECT_TRUE(Contains(stylesheetXml, "numFmtId=\"4\""));
    EXPECT_TRUE(Contains(worksheetXml, "s=\""));

    Workbook loaded(path.string());
    AssertPrimaryStyle(loaded.GetWorksheets()[0].GetCells()["A1"].GetStyle());
    AssertCustomNumberStyle(loaded.GetWorksheets()[0].GetCells()["B2"].GetStyle());
    EXPECT_EQ(CellValueType::Blank, loaded.GetWorksheets()[0].GetCells()["B2"].GetType());
    EXPECT_EQ(CellValueType::DateTime, loaded.GetWorksheets()[0].GetCells()["C3"].GetType());
}